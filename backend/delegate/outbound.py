"""Route approved Delegate drafts to the contact's actual channel."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_SYNTHETIC_PREFIXES = ("meta_", "telegram_", "linkedin_", "bird_", "slack_")

_CHANNEL_ALIASES = {
    "messenger": "facebook",
    "fb": "facebook",
    "ig": "instagram",
    "wa": "whatsapp",
    "gmail": "email",
    "mail": "email",
}


def normalize_channel(raw: str | None) -> str:
    ch = (raw or "").strip().lower()
    return _CHANNEL_ALIASES.get(ch, ch)


def is_real_whatsapp_phone(phone: str | None) -> bool:
    p = (phone or "").strip()
    if not p:
        return False
    if any(p.startswith(prefix) for prefix in _SYNTHETIC_PREFIXES):
        return False
    digits = re.sub(r"\D", "", p)
    return len(digits) >= 8


def channel_from_synthetic_phone(phone: str | None) -> str | None:
    p = (phone or "").strip().lower()
    if p.startswith("meta_instagram_"):
        return "instagram"
    if p.startswith("meta_messenger_") or p.startswith("meta_facebook_"):
        return "facebook"
    if p.startswith("telegram_"):
        return "telegram"
    if p.startswith("linkedin_"):
        return "linkedin"
    if p.startswith("bird_"):
        return "bird"
    if p.startswith("slack_"):
        return "slack"
    return None


async def resolve_reply_channel(
    db: Any,
    user_id: Any,
    contact: dict[str, Any] | None,
    subtask: dict[str, Any],
) -> str:
    """Pick the channel the founder originally reached this person on."""
    explicit = normalize_channel(subtask.get("reply_channel"))
    if explicit:
        return explicit

    if contact:
        if contact.get("slack_channel_id"):
            return "slack"

        for key in ("channel", "source", "platform"):
            ch = normalize_channel(contact.get(key))
            if ch and ch not in ("crm", "unknown", "scouted"):
                return ch

        synthetic = channel_from_synthetic_phone(
            contact.get("phone") or contact.get("phone_number")
        )
        if synthetic:
            return synthetic

        if contact.get("social_conversation_id") and contact.get("channel"):
            return normalize_channel(contact.get("channel"))

        if contact.get("email") and not is_real_whatsapp_phone(
            contact.get("phone_number") or contact.get("phone")
        ):
            # Prefer email only when there is no real phone and no social channel marker.
            last = await _last_inbound_channel(db, user_id, contact.get("_id"))
            if last:
                return last
            return "email"

        if is_real_whatsapp_phone(contact.get("phone_number") or contact.get("phone")):
            return "whatsapp"

        cid = contact.get("_id")
        if cid:
            last = await _last_inbound_channel(db, user_id, cid)
            if last:
                return last

    phone = subtask.get("phone")
    if is_real_whatsapp_phone(phone):
        return "whatsapp"
    synthetic = channel_from_synthetic_phone(phone)
    if synthetic:
        return synthetic
    if subtask.get("email"):
        return "email"
    return ""


async def _last_inbound_channel(db: Any, user_id: Any, customer_id: Any) -> str:
    if not customer_id:
        return ""
    msg = await db.messages.find_one(
        {
            "user_id": user_id,
            "customer_id": customer_id,
            "direction": "incoming",
            "channel": {"$exists": True, "$ne": ""},
        },
        sort=[("created_at", -1)],
    )
    return normalize_channel((msg or {}).get("channel"))


async def send_delegate_message(
    db: Any,
    user_id: Any,
    *,
    contact: dict[str, Any] | None,
    subtask: dict[str, Any],
    message: str,
    profile: dict[str, str],
) -> dict[str, Any]:
    """Send on the contact's channel. Returns send_status fields for the subtask."""
    from personal_profile import apply_personal_signature, substitute_social_template

    channel = await resolve_reply_channel(db, user_id, contact, subtask)
    uid = str(user_id)
    now = datetime.utcnow().isoformat() + "Z"
    contact_id = str((contact or {}).get("_id") or subtask.get("contact_id") or "")

    if not channel:
        return {
            "send_status": "no_channel",
            "send_channel": "manual",
            "send_error": "Could not detect which channel this contact used. Open their thread and reply manually.",
            "sent_at": now,
        }

    platform_for_template = "whatsapp" if channel == "whatsapp" else channel
    text = substitute_social_template(message, profile, platform=platform_for_template)
    text = apply_personal_signature(text, profile, append_if_missing=False)

    try:
        if channel == "whatsapp":
            return await _send_whatsapp(db, uid, contact, subtask, text, now, contact_id)
        if channel == "email":
            return await _send_email(db, uid, user_id, contact, subtask, text, now, contact_id)
        if channel == "telegram":
            return await _send_telegram(db, uid, user_id, contact, text, now, contact_id)
        if channel in ("instagram", "facebook"):
            return await _send_social_dm(db, uid, user_id, contact, text, channel, now, contact_id)
        if channel == "linkedin":
            return await _send_linkedin(db, uid, user_id, contact, text, now, contact_id)
        if channel == "bird":
            return await _send_bird(db, uid, user_id, contact, text, now, contact_id)
        if channel == "slack":
            return await _send_slack(db, uid, user_id, contact, text, now, contact_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] %s send failed: %s", channel, e)
        return {
            "send_status": "failed",
            "send_channel": channel,
            "send_error": str(e),
            "sent_at": now,
            "contact_id": contact_id or None,
        }

    return {
        "send_status": "no_channel",
        "send_channel": channel,
        "send_error": f"Sending via {channel} is not configured yet.",
        "sent_at": now,
        "contact_id": contact_id or None,
    }


async def _send_whatsapp(
    db: Any, uid: str, contact: dict | None, subtask: dict, text: str, now: str, contact_id: str
) -> dict[str, Any]:
    from whatsapp_service import get_whatsapp_service

    phone = (
        (contact or {}).get("phone_number")
        or (contact or {}).get("phone")
        or subtask.get("phone")
    )
    if not is_real_whatsapp_phone(phone):
        return {
            "send_status": "failed",
            "send_channel": "whatsapp",
            "send_error": "No WhatsApp number on this contact.",
            "sent_at": now,
        }
    ws = get_whatsapp_service(db)
    result = await ws.send_message(
        user_id=uid,
        to_number=str(phone),
        message=text,
        customer_name=subtask.get("label"),
        send_context="delegate",
    )
    if result.get("status") == "success":
        return {
            "send_status": "sent",
            "send_channel": "whatsapp",
            "sent_at": now,
            "contact_id": result.get("customer_id") or contact_id or None,
            "message_id": result.get("message_id"),
        }
    err = result.get("message") or result.get("status") or "WhatsApp send failed"
    return {"send_status": "failed", "send_channel": "whatsapp", "send_error": str(err), "sent_at": now}


async def _send_email(
    db: Any, uid: str, user_id: Any, contact: dict | None, subtask: dict, text: str, now: str, contact_id: str
) -> dict[str, Any]:
    from composio_service import ACTION_GMAIL_SEND, TOOLKIT_GMAIL, execute_action, get_connection_status

    email = (contact or {}).get("email") or subtask.get("email")
    if not email:
        return {
            "send_status": "failed",
            "send_channel": "email",
            "send_error": "No email on this contact.",
            "sent_at": now,
        }
    gmail = await get_connection_status(uid, TOOLKIT_GMAIL)
    if not gmail.get("connected"):
        return {
            "send_status": "failed",
            "send_channel": "email",
            "send_error": "Connect Gmail in Integrations to send email replies.",
            "sent_at": now,
        }
    lines = text.strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or "Following up"
        body = "\n".join(lines[1:]).strip() or text
    else:
        subject, body = "Following up", text
    result = await execute_action(uid, ACTION_GMAIL_SEND, {
        "recipient_email": email,
        "subject": subject,
        "body": body,
    })
    if result.get("success") and not result.get("error"):
        return {
            "send_status": "sent",
            "send_channel": "email",
            "sent_at": now,
            "contact_id": contact_id or None,
        }
    err = result.get("error") or "Email send failed"
    return {"send_status": "failed", "send_channel": "email", "send_error": str(err), "sent_at": now}


async def _send_telegram(
    db: Any, uid: str, user_id: Any, contact: dict | None, text: str, now: str, contact_id: str
) -> dict[str, Any]:
    from telegram_service import save_telegram_message, send_telegram_message

    chat_id = None
    if contact:
        meta_id = contact.get("meta_id")
        if meta_id:
            try:
                chat_id = int(meta_id)
            except (TypeError, ValueError):
                pass
        if chat_id is None:
            phone = (contact.get("phone") or "").strip()
            if phone.startswith("telegram_"):
                try:
                    chat_id = int(phone.split("_", 1)[1])
                except (TypeError, ValueError, IndexError):
                    pass
    if chat_id is None:
        return {
            "send_status": "failed",
            "send_channel": "telegram",
            "send_error": "Could not resolve Telegram chat for this contact.",
            "sent_at": now,
        }
    conn = await db.telegram_connections.find_one({"user_id": user_id})
    token = (conn or {}).get("bot_token")
    if not token:
        return {
            "send_status": "failed",
            "send_channel": "telegram",
            "send_error": "Connect your Telegram bot in Integrations.",
            "sent_at": now,
        }
    ok = await send_telegram_message(token, chat_id, text)
    if ok and contact_id:
        await save_telegram_message(db, user_id, contact_id, chat_id, text, "outgoing")
        return {
            "send_status": "sent",
            "send_channel": "telegram",
            "sent_at": now,
            "contact_id": contact_id,
        }
    return {
        "send_status": "failed",
        "send_channel": "telegram",
        "send_error": "Telegram send failed.",
        "sent_at": now,
    }


async def _send_social_dm(
    db: Any,
    uid: str,
    user_id: Any,
    contact: dict | None,
    text: str,
    channel: str,
    now: str,
    contact_id: str,
) -> dict[str, Any]:
    conv_id = (contact or {}).get("social_conversation_id")
    meta_id = (contact or {}).get("meta_id")

    # Composio inbox path (IG/FB DMs synced via Meta toolkit)
    if conv_id:
        from composio_service import get_connection_status
        from composio_inbox import send_message as composio_send

        plat = "instagram" if channel == "instagram" else "facebook"
        status = await get_connection_status(uid, plat)
        connection_id = status.get("connection_id")
        if status.get("connected") and connection_id:
            res = await composio_send(uid, conv_id, connection_id, text)
            if res.get("success") or res.get("data"):
                await _save_outgoing_channel_message(db, user_id, contact_id, text, channel)
                return {
                    "send_status": "sent",
                    "send_channel": channel,
                    "sent_at": now,
                    "contact_id": contact_id or None,
                }
            err = res.get("error") or "Social DM send failed"
            return {
                "send_status": "failed",
                "send_channel": channel,
                "send_error": str(err),
                "sent_at": now,
            }

    # Meta webhook token path
    if meta_id:
        from meta_service import save_outgoing_message, send_instagram_message, send_messenger_message

        meta_channel = "instagram" if channel == "instagram" else "messenger"
        conn = await db.meta_connections.find_one({"user_id": user_id, "channel": meta_channel})
        token = (conn or {}).get("page_access_token")
        if token:
            if channel == "instagram":
                ok = await send_instagram_message(token, str(meta_id), text)
            else:
                ok = await send_messenger_message(token, str(meta_id), text)
            if ok and contact_id:
                await save_outgoing_message(db, user_id, contact_id, text, meta_channel)
                return {
                    "send_status": "sent",
                    "send_channel": channel,
                    "sent_at": now,
                    "contact_id": contact_id,
                }

    return {
        "send_status": "failed",
        "send_channel": channel,
        "send_error": f"Connect {channel.title()} in Integrations to reply on that channel.",
        "sent_at": now,
        "contact_id": contact_id or None,
    }


async def _send_linkedin(
    db: Any, uid: str, user_id: Any, contact: dict | None, text: str, now: str, contact_id: str
) -> dict[str, Any]:
    import unipile_inbox
    from unipile_inbox import resolve_linkedin_account_id

    chat_id = (contact or {}).get("social_conversation_id")
    if not chat_id:
        return {
            "send_status": "failed",
            "send_channel": "linkedin",
            "send_error": "No LinkedIn conversation linked to this contact.",
            "sent_at": now,
        }
    user = await db.users.find_one({"_id": user_id}) or {}
    business_id = str(user.get("business_id") or user_id)
    account_id = await resolve_linkedin_account_id(db, user_id, business_id)
    if not account_id:
        return {
            "send_status": "failed",
            "send_channel": "linkedin",
            "send_error": "Connect LinkedIn in Integrations.",
            "sent_at": now,
        }
    res = await unipile_inbox.send_message(db, user_id, business_id, chat_id, account_id, text)
    if res.get("success"):
        if contact_id:
            from unipile_routes import save_outgoing_unipile_message

            await save_outgoing_unipile_message(db, user_id, contact_id, text)
        return {
            "send_status": "sent",
            "send_channel": "linkedin",
            "sent_at": now,
            "contact_id": contact_id or None,
        }
    return {
        "send_status": "failed",
        "send_channel": "linkedin",
        "send_error": str(res.get("error") or "LinkedIn send failed"),
        "sent_at": now,
    }


async def _send_slack(
    db: Any, uid: str, user_id: Any, contact: dict | None, text: str, now: str, contact_id: str
) -> dict[str, Any]:
    from composio_service import (
        TOOLKIT_SLACK,
        get_connection_status,
        slack_post_message_via_composio_or_proxy,
    )

    status = await get_connection_status(uid, TOOLKIT_SLACK)
    if not status.get("connected"):
        return {
            "send_status": "failed",
            "send_channel": "slack",
            "send_error": "Connect Slack in Integrations to reply there.",
            "sent_at": now,
        }

    channel_id = ""
    thread_ts = None
    if contact:
        channel_id = (contact.get("slack_channel_id") or contact.get("meta_id") or "").strip()
        thread_ts = contact.get("slack_thread_ts") or contact.get("thread_ts")
        if not channel_id:
            phone = (contact.get("phone") or contact.get("phone_number") or "").strip()
            if phone.lower().startswith("slack_"):
                channel_id = phone.split("_", 1)[1]

    if not channel_id:
        return {
            "send_status": "failed",
            "send_channel": "slack",
            "send_error": "No Slack channel or user ID on this contact.",
            "sent_at": now,
        }

    data = await slack_post_message_via_composio_or_proxy(
        uid,
        channel=channel_id,
        text=text,
        thread_ts=str(thread_ts) if thread_ts else None,
    )
    if data.get("ok") is True or data.get("ts"):
        await _save_outgoing_channel_message(db, user_id, contact_id, text, "slack")
        return {
            "send_status": "sent",
            "send_channel": "slack",
            "sent_at": now,
            "contact_id": contact_id or None,
        }
    err = data.get("error") or "Slack send failed"
    return {
        "send_status": "failed",
        "send_channel": "slack",
        "send_error": str(err),
        "sent_at": now,
        "contact_id": contact_id or None,
    }


async def _send_bird(
    db: Any, uid: str, user_id: Any, contact: dict | None, text: str, now: str, contact_id: str
) -> dict[str, Any]:
    from bird_service import get_connection_for_inbound, save_outgoing_bird_message, send_channel_message

    if not contact:
        return {
            "send_status": "failed",
            "send_channel": "bird",
            "send_error": "No Bird contact record.",
            "sent_at": now,
        }
    channel_id = contact.get("bird_channel_id") or ""
    identifier_key = contact.get("bird_identifier_key") or "phonenumber"
    identifier_value = contact.get("bird_identifier_value") or contact.get("phone") or ""
    conn = await get_connection_for_inbound(db, user_id)
    workspace_id = (conn or {}).get("workspace_id") or ""
    if not workspace_id or not channel_id:
        return {
            "send_status": "failed",
            "send_channel": "bird",
            "send_error": "Bird channel not configured for this contact.",
            "sent_at": now,
        }
    ok = await send_channel_message(
        workspace_id, channel_id, identifier_key, identifier_value, text
    )
    if ok and contact_id:
        await save_outgoing_bird_message(db, user_id, contact_id, text)
        return {
            "send_status": "sent",
            "send_channel": "bird",
            "sent_at": now,
            "contact_id": contact_id,
        }
    return {
        "send_status": "failed",
        "send_channel": "bird",
        "send_error": "Bird send failed.",
        "sent_at": now,
    }


async def _save_outgoing_channel_message(
    db: Any, user_id: Any, customer_id: str, text: str, channel: str
) -> None:
    if not customer_id:
        return
    await db.messages.insert_one({
        "user_id": user_id,
        "customer_id": customer_id,
        "direction": "outgoing",
        "content": text,
        "channel": channel,
        "message_type": "text",
        "send_context": "delegate",
        "created_at": datetime.utcnow(),
    })


def reply_channel_from_contact(contact: dict[str, Any]) -> str:
    """Expose channel on subtasks when staging drafts."""
    if contact.get("slack_channel_id"):
        return "slack"
    ch = normalize_channel(contact.get("channel") or contact.get("source"))
    if ch and ch not in ("crm", "unknown", "scouted"):
        return ch
    synthetic = channel_from_synthetic_phone(contact.get("phone") or contact.get("phone_number"))
    if synthetic:
        return synthetic
    if contact.get("email") and not is_real_whatsapp_phone(
        contact.get("phone_number") or contact.get("phone")
    ):
        return "email"
    if is_real_whatsapp_phone(contact.get("phone_number") or contact.get("phone")):
        return "whatsapp"
    return ch or ""
