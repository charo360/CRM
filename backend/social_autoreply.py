"""
social_autoreply.py — server-side AI auto-reply for social DMs (Instagram via Composio).

Why this exists
---------------
Instagram DMs reach us by *polling* Composio read actions (INSTAGRAM_LIST_ALL_CONVERSATIONS
/ INSTAGRAM_LIST_ALL_MESSAGES) — there is no Composio push trigger for IG messages, so we
can't do real-time webhooks the way Gmail does. The dashboard already polls while it's open;
this module does the same thing server-side on a short interval so auto-reply works 24/7,
even with no browser tab open.

Flow per cycle (driven by scheduler.run_social_autoreply_poll):
  1. Find users with settings.social_dm_autoreply_enabled == True.
  2. For each, if Instagram is connected, pull recent conversations via Composio.
  3. Detect genuinely-new inbound DMs (newest message is inbound + unseen).
  4. Sync the conversation into Mongo (CRM customer + message history).
  5. Fire the shared autoreply engine (autoreply.engine.process_message), which sends the
     reply back out through Composio (INSTAGRAM_SEND_TEXT_MESSAGE) and persists the outbound.

Safety:
  - On first sight of a conversation we record a baseline and DO NOT reply to backlog, unless
    the newest inbound message is recent (< NEW_MESSAGE_WINDOW_MINUTES) — so a first-time
    customer still gets an instant reply, but turning the feature on never blasts old threads.
  - Per-customer opt-out honoured (customer.auto_reply is False).
  - Dedup by Composio message id so a message is never answered twice.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Caps so one cycle can't run away on a large account.
MAX_USERS_PER_CYCLE = 50
MAX_CONVERSATIONS_PER_CYCLE = 15
# A brand-new conversation whose newest inbound message is within this window is treated as
# "live" and answered even with no prior state. Older = backlog, baseline only (no reply).
NEW_MESSAGE_WINDOW_MINUTES = 10

# LinkedIn-specific safety limits. LinkedIn (via Unipile session automation) is not officially
# sanctioned for auto-messaging, so keep the footprint small: a conservative per-account daily
# reply cap and fewer conversations scanned per cycle than Instagram.
MAX_LINKEDIN_AUTOREPLIES_PER_DAY = 15
MAX_LINKEDIN_CONVERSATIONS_PER_CYCLE = 10


def _parse_ts(value: str) -> Optional[datetime]:
    """Parse the ISO-ish timestamps composio_inbox emits (e.g. '2026-05-07T12:49:51Z')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=None)
    except Exception:
        return None


async def run_social_autoreply_poll(db) -> None:
    """Entry point — invoked on an interval by the scheduler.

    Polls Instagram (Composio) and/or LinkedIn (Unipile) per user, each gated by its own
    opt-in flag. LinkedIn is a separate flag because its automation carries account risk.
    """
    try:
        users = await db.users.find(
            {"$or": [
                {"settings.social_dm_autoreply_enabled": True},
                {"settings.linkedin_dm_autoreply_enabled": True},
            ]}
        ).to_list(MAX_USERS_PER_CYCLE)
    except Exception as exc:
        logger.error(f"[SocialAutoReply] user query failed: {exc}")
        return

    if not users:
        return

    logger.info(f"[SocialAutoReply] polling {len(users)} user(s) for social DM auto-reply")
    for user in users:
        settings = user.get("settings") or {}
        if settings.get("social_dm_autoreply_enabled"):
            try:
                await _poll_user_instagram(db, user)
            except Exception as exc:
                logger.error(
                    f"[SocialAutoReply] IG user {user.get('_id')} failed: {exc}", exc_info=True
                )
        if settings.get("linkedin_dm_autoreply_enabled"):
            try:
                await _poll_user_linkedin(db, user)
            except Exception as exc:
                logger.error(
                    f"[SocialAutoReply] LinkedIn user {user.get('_id')} failed: {exc}", exc_info=True
                )


async def _poll_user_instagram(db, user: dict) -> None:
    import composio_inbox
    from composio_service import get_connection_status

    # The working inbox routes pass user["_id"] straight to Composio — mirror that exactly.
    composio_uid = str(user["_id"])

    status = await get_connection_status(composio_uid, "instagram")
    if not (status.get("connected") and status.get("connection_id")):
        return
    connection_id = status["connection_id"]

    convs = await composio_inbox.list_conversations(composio_uid, "instagram")
    if not convs:
        return

    for conv in convs[:MAX_CONVERSATIONS_PER_CYCLE]:
        try:
            await _maybe_reply_to_conversation(
                db, user, composio_uid, conv, connection_id
            )
        except Exception as exc:
            logger.warning(
                f"[SocialAutoReply] conversation {conv.get('id')} failed: {exc}"
            )


async def _maybe_reply_to_conversation(
    db, user: dict, composio_uid: str, conv: dict, connection_id: str
) -> None:
    import composio_inbox

    conv_id = conv.get("id")
    if not conv_id:
        return

    account_id = conv.get("accountId") or connection_id
    messages = await composio_inbox.get_conversation_messages(
        composio_uid, conv_id, account_id
    )
    if not messages:
        return

    latest = messages[-1]
    # Only act when the newest message is from the customer (not our own last reply).
    if latest.get("direction") != "in":
        return

    latest_mid = str(latest.get("id") or "")
    latest_text = (latest.get("content") or "").strip()
    if not latest_mid or not latest_text or latest_text == "[Attachment]":
        return

    db_user_id = user["_id"]
    state = await db.social_autoreply_state.find_one(
        {"user_id": db_user_id, "conversation_id": conv_id}
    )

    # Already answered this exact message — nothing to do.
    if state and state.get("last_handled_mid") == latest_mid:
        return

    # First time we see this conversation: only reply if the message is live (recent),
    # otherwise just record a baseline so we never spam existing backlog on first enable.
    if not state:
        ts = _parse_ts(latest.get("created_at") or "")
        is_live = bool(
            ts and (datetime.utcnow() - ts) <= timedelta(minutes=NEW_MESSAGE_WINDOW_MINUTES)
        )
        if not is_live:
            await db.social_autoreply_state.update_one(
                {"user_id": db_user_id, "conversation_id": conv_id},
                {"$set": {
                    "user_id": db_user_id,
                    "conversation_id": conv_id,
                    "last_handled_mid": latest_mid,
                    "baseline_only": True,
                    "updated_at": datetime.utcnow(),
                }},
                upsert=True,
            )
            return

    participant_id = conv.get("participantId") or ""
    participant_name = conv.get("participant_name") or conv.get("participant") or ""
    if not participant_id:
        logger.warning(f"[SocialAutoReply] no participant id for conv {conv_id}; skipping")
        return

    # Sync conversation into the CRM (customer + message history minus the newest inbound,
    # which the engine receives as the current turn — avoids a duplicated last message).
    customer = await _get_or_create_social_customer(
        db, db_user_id, "instagram", participant_id, participant_name, conv_id
    )

    # Per-customer opt-out wins over the global toggle.
    if customer.get("auto_reply") is False:
        await _mark_handled(db, db_user_id, conv_id, latest_mid)
        return

    # Mirror prior turns into db.messages (everything EXCEPT the newest inbound, which the
    # engine receives as `message` and appends itself — so nothing is duplicated). Composio
    # stays the source of truth: our reply lands there and is mirrored on the next cycle.
    await _sync_history(db, db_user_id, customer["_id"], messages[:-1])

    # Fire the shared engine. It loads history from db.messages, appends `message`, replies,
    # and the sender below sends the reply out through Composio.
    from autoreply.engine import process_message

    sender = _ComposioSender(
        composio_uid=composio_uid,
        conversation_id=conv_id,
        connection_id=account_id,
    )

    await process_message(
        db=db,
        user=user,
        customer=customer,
        customer_id=customer["_id"],
        message=latest_text,
        from_number=f"meta_instagram_{participant_id}",
        whatsapp_service=sender,
    )

    await _mark_handled(db, db_user_id, conv_id, latest_mid)

    logger.info(
        f"[SocialAutoReply] ✓ replied user={db_user_id} conv={conv_id} "
        f"to={participant_name or participant_id}"
    )


async def _poll_user_linkedin(db, user: dict) -> None:
    """Poll the user's LinkedIn DMs (Unipile) and auto-reply to live inbound messages."""
    import unipile_inbox
    from unipile_service import resolve_linkedin_account_id

    if not unipile_inbox.is_available():
        return

    user_oid = user["_id"]
    business_id = str(user.get("business_id") or user_oid)
    account_id = await resolve_linkedin_account_id(db, user_oid, business_id)
    if not account_id:
        return

    convs = await unipile_inbox.list_conversations(db, user_oid, business_id)
    if not convs:
        return

    for conv in convs[:MAX_LINKEDIN_CONVERSATIONS_PER_CYCLE]:
        try:
            # Scope: classic 1:1 DMs + company-page (organization) inbox threads.
            # Skip InMail / Sales Navigator / Recruiter to keep the footprint narrow.
            if conv.get("linkedin_channel") not in (None, "", "classic", "organization"):
                continue
            await _maybe_reply_linkedin_conversation(
                db, user, user_oid, business_id, account_id, conv
            )
        except Exception as exc:
            logger.warning(
                f"[SocialAutoReply] linkedin conv {conv.get('id')} failed: {exc}"
            )


async def _maybe_reply_linkedin_conversation(
    db, user: dict, user_oid: Any, business_id: str, account_id: str, conv: dict
) -> None:
    import unipile_inbox

    conv_id = conv.get("id")
    if not conv_id:
        return

    # The external contact's provider id. On company-page mailboxes our OWN replies come back
    # with is_sender=0 (sender_id = the page mailbox id), so `direction`/`is_sender` cannot tell
    # our messages from the contact's — which previously caused an auto-reply loop. The reliable
    # signal is: a message is inbound iff its sender_id equals this external attendee id.
    participant_id = str(conv.get("participantId") or "")
    participant_name = conv.get("participant_name") or conv.get("participant") or ""
    if not participant_id:
        # No stable counterpart id (group/title-only chat) — skip to keep replies 1:1.
        logger.warning(f"[SocialAutoReply] no participant id for LinkedIn conv {conv_id}; skipping")
        return

    messages = await unipile_inbox.get_conversation_messages(
        db, user_oid, business_id, conv_id, account_id
    )
    if not messages:
        return

    latest = messages[-1]
    # Only act when the newest message was sent BY the contact (not our own reply).
    if str(latest.get("sender_id") or "") != participant_id:
        return

    latest_mid = str(latest.get("id") or "")
    latest_text = (latest.get("text") or latest.get("body") or "").strip()
    if not latest_mid or not latest_text or latest_text == "[Attachment]":
        return

    db_user_id = user["_id"]
    state = await db.social_autoreply_state.find_one(
        {"user_id": db_user_id, "conversation_id": conv_id}
    )
    if state and state.get("last_handled_mid") == latest_mid:
        return

    # First sight: only reply if the message is live; otherwise baseline (no backlog blast).
    if not state:
        ts = _parse_ts(latest.get("created_at") or "")
        is_live = bool(
            ts and (datetime.utcnow() - ts) <= timedelta(minutes=NEW_MESSAGE_WINDOW_MINUTES)
        )
        if not is_live:
            await db.social_autoreply_state.update_one(
                {"user_id": db_user_id, "conversation_id": conv_id},
                {"$set": {
                    "user_id": db_user_id,
                    "conversation_id": conv_id,
                    "last_handled_mid": latest_mid,
                    "baseline_only": True,
                    "updated_at": datetime.utcnow(),
                }},
                upsert=True,
            )
            return

    # Ban-risk safety: stop once the per-account daily cap is hit.
    if await _linkedin_daily_count(db, db_user_id, account_id) >= MAX_LINKEDIN_AUTOREPLIES_PER_DAY:
        logger.info(
            f"[SocialAutoReply] LinkedIn daily cap reached (user={db_user_id}); skipping"
        )
        return

    customer = await _get_or_create_social_customer(
        db, db_user_id, "linkedin", participant_id, participant_name, conv_id
    )
    if customer.get("auto_reply") is False:
        await _mark_handled(db, db_user_id, conv_id, latest_mid)
        return

    await _sync_history(
        db, db_user_id, customer["_id"], messages[:-1],
        channel="linkedin", participant_id=participant_id,
    )

    from autoreply.engine import process_message

    sender = _UnipileSender(
        db=db,
        user_oid=user_oid,
        business_id=business_id,
        conversation_id=conv_id,
        account_id=account_id,
    )

    await process_message(
        db=db,
        user=user,
        customer=customer,
        customer_id=customer["_id"],
        message=latest_text,
        from_number=f"meta_linkedin_{participant_id}",
        whatsapp_service=sender,
    )

    await _bump_linkedin_daily_count(db, db_user_id, account_id)
    await _mark_handled(db, db_user_id, conv_id, latest_mid)

    logger.info(
        f"[SocialAutoReply] ✓ LinkedIn replied user={db_user_id} conv={conv_id} "
        f"to={participant_name or participant_id}"
    )


class _UnipileSender:
    """Adapter so autoreply.engine can send a LinkedIn reply via Unipile (send-only).

    Like _ComposioSender, it does not persist to db.messages — the reply lands in Unipile
    and is mirrored into db.messages on the next poll cycle.
    """

    def __init__(self, db, user_oid, business_id, conversation_id, account_id):
        self.db = db
        self.user_oid = user_oid
        self.business_id = business_id
        self.conversation_id = conversation_id
        self.account_id = account_id

    async def send_message(
        self,
        user_id=None,
        to_number=None,
        message="",
        customer_name="",
        send_context="auto_reply",
        media_url=None,
        media_type="image",
        **kwargs,
    ) -> bool:
        import unipile_inbox

        text = (message or "").strip()
        if not text:
            return False
        res = await unipile_inbox.send_message(
            self.db,
            self.user_oid,
            self.business_id,
            self.conversation_id,
            self.account_id,
            text,
        )
        ok = bool(res.get("success")) and not res.get("error")
        if not ok:
            logger.warning(f"[SocialAutoReply] Unipile send failed: {res.get('error') or res}")
        return ok


class _ComposioSender:
    """Adapter so autoreply.engine can send without knowing it's Composio/Instagram.

    Sends only — does not persist to db.messages. The reply lands in Composio and is
    mirrored into db.messages on the next poll cycle (Composio is the source of truth),
    which keeps history free of duplicates.
    """

    def __init__(self, composio_uid, conversation_id, connection_id):
        self.composio_uid = composio_uid
        self.conversation_id = conversation_id
        self.connection_id = connection_id

    async def send_message(
        self,
        user_id=None,
        to_number=None,
        message="",
        customer_name="",
        send_context="auto_reply",
        media_url=None,
        media_type="image",
        **kwargs,
    ) -> bool:
        import composio_inbox

        text = (message or "").strip()
        if media_url and not text:
            # INSTAGRAM_SEND_TEXT_MESSAGE is text-only; image-only sends are skipped for now.
            logger.info("[SocialAutoReply] skipping image-only send (IG DM media not supported yet)")
            return False
        if not text:
            return False

        res = await composio_inbox.send_message(
            self.composio_uid, self.conversation_id, self.connection_id, text
        )
        ok = bool(res.get("success") or res.get("data")) and not res.get("error")
        if not ok:
            logger.warning(f"[SocialAutoReply] Composio send failed: {res.get('error') or res}")
        return ok


# ── Mongo sync helpers ──────────────────────────────────────────────────────────

async def _get_or_create_social_customer(
    db, user_id, channel: str, participant_id: str, participant_name: str, conv_id: str
) -> dict:
    """Find or create the CRM customer for a social DM participant.

    Uses the same synthetic phone key as the Meta webhook path (meta_<channel>_<id>) so an
    Instagram contact is one record regardless of which ingestion path saw it first.
    """
    phone = f"meta_{channel}_{participant_id}"
    customer = await db.customers.find_one({"user_id": user_id, "phone": phone})
    if customer:
        # Keep the conversation id fresh for sends/lookups.
        if customer.get("social_conversation_id") != conv_id:
            await db.customers.update_one(
                {"_id": customer["_id"]},
                {"$set": {"social_conversation_id": conv_id, "updated_at": datetime.utcnow()}},
            )
        return customer

    now = datetime.utcnow()
    doc = {
        "user_id": user_id,
        "phone": phone,
        "name": participant_name or f"{channel.title()} User {participant_id[-6:]}",
        "channel": channel,
        "source": channel,
        "meta_id": participant_id,
        "social_conversation_id": conv_id,
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "notes": "",
        "vip": False,
    }
    result = await db.customers.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(f"[SocialAutoReply] created {channel} customer {participant_id} for user {user_id}")
    return doc


async def _sync_history(
    db, user_id, customer_id, messages: List[dict],
    channel: str = "instagram", participant_id: Optional[str] = None,
) -> None:
    """Upsert prior inbox messages into db.messages (dedup by social_mid).

    Channel-agnostic: Composio (IG) messages carry text in `content` and direction in/out;
    Unipile (LinkedIn) messages carry text in `text` and direction inbound/outbound — both
    shapes are normalized here. When `participant_id` is given (LinkedIn), incoming/outgoing is
    derived from sender_id (reliable on page mailboxes where is_sender is always 0).
    """
    inbound_dirs = ("in", "inbound")
    for m in messages:
        mid = str(m.get("id") or "")
        content = (m.get("content") or m.get("text") or "").strip()
        if not mid or not content or content == "[Attachment]":
            continue
        if participant_id is not None:
            is_incoming = str(m.get("sender_id") or "") == participant_id
        else:
            is_incoming = m.get("direction") in inbound_dirs
        direction = "incoming" if is_incoming else "outgoing"
        await db.messages.update_one(
            {"user_id": user_id, "social_mid": mid},
            {"$setOnInsert": {
                "user_id": user_id,
                "customer_id": customer_id,
                "direction": direction,
                "content": content,
                "channel": channel,
                "social_mid": mid,
                "message_type": "text",
                "send_context": "incoming" if direction == "incoming" else "auto_reply",
                "created_at": _parse_ts(m.get("created_at") or "") or datetime.utcnow(),
            }},
            upsert=True,
        )


async def _mark_handled(db, user_id, conv_id: str, mid: str) -> None:
    await db.social_autoreply_state.update_one(
        {"user_id": user_id, "conversation_id": conv_id},
        {"$set": {
            "user_id": user_id,
            "conversation_id": conv_id,
            "last_handled_mid": mid,
            "baseline_only": False,
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )


# ── LinkedIn daily reply cap (ban-risk mitigation) ───────────────────────────────

def _utc_date_key() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


async def _linkedin_daily_count(db, user_id, account_id: str) -> int:
    """Auto-replies already sent for this account today (UTC). Resets implicitly via date key."""
    doc = await db.social_autoreply_limits.find_one(
        {"user_id": user_id, "account_id": account_id, "date": _utc_date_key()}
    )
    return int((doc or {}).get("count") or 0)


async def _bump_linkedin_daily_count(db, user_id, account_id: str) -> None:
    await db.social_autoreply_limits.update_one(
        {"user_id": user_id, "account_id": account_id, "date": _utc_date_key()},
        {"$inc": {"count": 1}, "$set": {"updated_at": datetime.utcnow()}},
        upsert=True,
    )
