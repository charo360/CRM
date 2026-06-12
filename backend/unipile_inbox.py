"""LinkedIn inbox via Unipile (DMs, InMail threads)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from unipile_service import (
    _request,
    is_configured,
    public_account_id,
    resolve_linkedin_account_id,
    start_linkedin_chat,
    strip_public_account_id,
)

logger = logging.getLogger(__name__)


def is_available() -> bool:
    return is_configured()


def _normalize_time(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return ""
    if s.endswith("Z") or "+" in s:
        return s
    return f"{s}Z"


def _linkedin_channel(chat: Dict[str, Any]) -> str:
    content_type = str(chat.get("content_type") or "").lower()
    folders = chat.get("folder") or []
    if isinstance(folders, str):
        folders = [folders]
    folder_set = {str(f).upper() for f in folders if f}
    if content_type == "inmail":
        return "inmail"
    # Company/page inbox messages (the member administers the page) arrive in this folder.
    # Detect them before the subject-based inmail heuristic, since page threads have subjects.
    if "INBOX_LINKEDIN_ORGANIZATION" in folder_set:
        return "organization"
    if "INBOX_LINKEDIN_SALES_NAVIGATOR" in folder_set:
        return "sales_navigator"
    if "INBOX_LINKEDIN_RECRUITER" in folder_set:
        return "recruiter"
    if "INBOX_LINKEDIN_CLASSIC" in folder_set:
        return "classic"
    if chat.get("subject"):
        return "inmail"
    return "classic"


def _chat_participant(chat: Dict[str, Any]) -> tuple[str, str]:
    attendees = chat.get("attendees") or chat.get("participants") or []
    if isinstance(attendees, dict):
        attendees = attendees.get("items") or attendees.get("data") or []
    if isinstance(attendees, list):
        for att in attendees:
            if not isinstance(att, dict):
                continue
            name = (
                att.get("display_name")
                or att.get("displayName")
                or att.get("name")
                or att.get("username")
                or ""
            )
            pid = att.get("id") or att.get("provider_id") or att.get("providerId") or ""
            if name or pid:
                return str(name or f"User {str(pid)[-6:]}"), str(pid)
    # The /chats list response embeds no attendees array — the 1:1 counterpart's provider id
    # is on the chat itself as attendee_provider_id. (Group chats omit it -> empty id.)
    pid = str(chat.get("attendee_provider_id") or "")
    name = chat.get("name") or chat.get("title")
    if not name:
        name = f"User {pid[-6:]}" if pid else "LinkedIn contact"
    return str(name), pid


async def list_conversations(db, user_oid: Any, business_id: str) -> List[Dict[str, Any]]:
    if not is_configured():
        return []

    account_id = await resolve_linkedin_account_id(db, user_oid, business_id)
    if not account_id:
        return []

    result = await _request(
        "GET",
        "/api/v1/chats",
        params={"account_id": account_id, "limit": 50},
    )
    if result.get("error"):
        logger.warning("[unipile-inbox] list chats failed: %s", result["error"])
        return []

    data = result.get("data") or {}
    chats = data.get("items") or data.get("data") or data.get("chats") or []
    if isinstance(chats, dict):
        chats = chats.get("items") or chats.get("data") or []

    conversations: List[Dict[str, Any]] = []
    pub_acct = public_account_id(account_id)
    for chat in chats[:50]:
        if not isinstance(chat, dict):
            continue
        chat_id = chat.get("id") or chat.get("chat_id")
        if not chat_id:
            continue
        participant_name, participant_id = _chat_participant(chat)
        last_msg = (
            chat.get("last_message")
            or chat.get("lastMessage")
            or chat.get("snippet")
            or chat.get("preview")
            or ""
        )
        if isinstance(last_msg, dict):
            last_text = last_msg.get("text") or last_msg.get("body") or "[Message]"
            last_at = _normalize_time(last_msg.get("timestamp") or last_msg.get("created_at"))
        else:
            last_text = str(last_msg or "")
            last_at = _normalize_time(
                chat.get("updated_at") or chat.get("last_message_at") or chat.get("timestamp")
            )

        channel = _linkedin_channel(chat)
        conversations.append({
            "id": str(chat_id),
            "platform": "linkedin",
            "source": "unipile",
            "accountId": pub_acct,
            "account_id": pub_acct,
            "participantId": participant_id,
            "participant_name": participant_name,
            "participant": participant_name,
            "last_message": last_text or "[Message]",
            "last_message_at": last_at,
            "unread": int(chat.get("unread_count") or chat.get("unread") or 0),
            "linkedin_channel": channel,
            "subject": chat.get("subject") or "",
            "content_type": chat.get("content_type") or "",
        })
    return conversations


async def get_conversation_messages(
    db,
    user_oid: Any,
    business_id: str,
    conversation_id: str,
    account_id: str = "",
) -> List[Dict[str, Any]]:
    if not is_configured():
        return []

    resolved_account = strip_public_account_id(account_id) if account_id else ""
    if not resolved_account:
        resolved_account = await resolve_linkedin_account_id(db, user_oid, business_id) or ""
    if not resolved_account:
        return []

    result = await _request(
        "GET",
        f"/api/v1/chats/{conversation_id}/messages",
        params={"account_id": resolved_account, "limit": 100},
    )
    if result.get("error"):
        logger.warning("[unipile-inbox] get messages failed: %s", result["error"])
        return []

    data = result.get("data") or {}
    raw_msgs = data.get("items") or data.get("data") or data.get("messages") or []
    if isinstance(raw_msgs, dict):
        raw_msgs = raw_msgs.get("items") or raw_msgs.get("data") or []

    messages: List[Dict[str, Any]] = []
    for msg in raw_msgs:
        if not isinstance(msg, dict):
            continue
        text = msg.get("text") or msg.get("body") or msg.get("message") or ""
        sender = (
            (msg.get("from") or {}).get("name")
            if isinstance(msg.get("from"), dict)
            else msg.get("sender_name") or msg.get("sender") or "User"
        )
        direction = "outbound" if msg.get("is_sender") or msg.get("isSender") else "inbound"
        messages.append({
            "id": str(msg.get("id") or ""),
            "text": text,
            "body": text,
            "message": text,
            "direction": direction,
            # sender_id is the reliable inbound/outbound signal: on company-page mailboxes our
            # OWN replies have is_sender=0 (sender_id = page mailbox id), so is_sender/direction
            # cannot tell our messages from the contact's. Match sender_id to the chat's external
            # attendee id instead. (See social_autoreply._maybe_reply_linkedin_conversation.)
            "sender_id": str(msg.get("sender_id") or msg.get("senderId") or ""),
            "created_at": _normalize_time(msg.get("timestamp") or msg.get("created_at")),
            "sender": str(sender),
        })

    messages.sort(key=lambda m: m.get("created_at") or "")
    return messages


async def send_message(
    db,
    user_oid: Any,
    business_id: str,
    conversation_id: str,
    account_id: str,
    message: str,
) -> Dict[str, Any]:
    if not is_configured():
        return {"error": "Unipile is not configured (UNIPILE_API_KEY / UNIPILE_DSN)."}

    text = (message or "").strip()
    if not text:
        return {"error": "Message text is required."}

    resolved_account = strip_public_account_id(account_id)
    if not resolved_account:
        resolved_account = await resolve_linkedin_account_id(db, user_oid, business_id) or ""
    if not resolved_account:
        return {"error": "LinkedIn messaging is not connected. Connect via Integrations."}

    result = await _request(
        "POST",
        f"/api/v1/chats/{conversation_id}/messages",
        json={"account_id": resolved_account, "text": text},
    )
    if result.get("error"):
        return {"error": result["error"]}

    return {"success": True, "data": result.get("data")}


async def send_inmail(
    db,
    user_oid: Any,
    business_id: str,
    *,
    recipient_id: str,
    message: str,
    subject: str = "",
    account_id: str = "",
    linkedin_api: Optional[str] = None,
    inmail: bool = True,
) -> Dict[str, Any]:
    if not is_configured():
        return {"error": "Unipile is not configured (UNIPILE_API_KEY / UNIPILE_DSN)."}

    resolved_account = strip_public_account_id(account_id)
    if not resolved_account:
        resolved_account = await resolve_linkedin_account_id(db, user_oid, business_id) or ""
    if not resolved_account:
        return {"error": "LinkedIn is not connected. Connect via Integrations."}

    return await start_linkedin_chat(
        resolved_account,
        attendee_ids=[recipient_id],
        text=message,
        subject=subject or None,
        linkedin_api=linkedin_api,
        inmail=inmail,
    )
