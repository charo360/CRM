"""
bird_service.py — Bird.com Conversations webhook + outbound messages (AccessKey API).

Inbound: POST /webhook/bird — conversation.created / conversation.updated
        with lastMessage from type \"contact\".

Routing (db.bird_connections):
  • Preferred: { channel_id, user_id, workspace_id? } — one Bird channel → one CRM business.
    You provision via POST /api/bird/provision-channel with X-Bird-Provision-Secret (operator-only).
  • Legacy: { workspace_id, user_id } with no channel_id — single-tenant workspace match.
  • Env fallback: BIRD_WORKSPACE_ID + BIRD_DEFAULT_USER_ID when no DB row matches.

Env:
  BIRD_API_KEY             — AccessKey (server only)
  BIRD_WORKSPACE_ID        — default workspace UUID for API paths / webhook fallback
  BIRD_DEFAULT_USER_ID     — optional single-tenant fallback (CRM user ObjectId hex)
  OPERATOR_PROVISION_SECRET — required for /api/bird/provision-channel and /api/telegram/provision-bot
                            (fallback: BIRD_PROVISION_SECRET)
  BIRD_WEBHOOK_SIGNING_KEY — optional webhook HMAC
  BIRD_WEBHOOK_PUBLIC_URL
  BIRD_API_BASE
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from bson import ObjectId

logger = logging.getLogger(__name__)

BIRD_API_BASE = os.environ.get("BIRD_API_BASE", "https://api.bird.com").rstrip("/")
BIRD_API_KEY = os.environ.get("BIRD_API_KEY", "").strip()
BIRD_WORKSPACE_ID = os.environ.get("BIRD_WORKSPACE_ID", "").strip()
BIRD_WEBHOOK_SIGNING_KEY = os.environ.get("BIRD_WEBHOOK_SIGNING_KEY", "").strip()


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"AccessKey {BIRD_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def verify_webhook_signature(
    body: bytes,
    signature_b64: Optional[str],
    timestamp: Optional[str],
    request_url: str,
) -> bool:
    """Bird / MessageBird HMAC-SHA256 (see verifying-a-webhook-subscription)."""
    if not BIRD_WEBHOOK_SIGNING_KEY:
        return True
    if not signature_b64 or not timestamp:
        return False
    try:
        raw_sig = base64.b64decode(signature_b64)
    except Exception:
        return False
    body_hash = hashlib.sha256(body).digest()
    msg = timestamp.encode("utf-8") + b"\n" + request_url.encode("utf-8") + b"\n" + body_hash
    expected = hmac.new(
        BIRD_WEBHOOK_SIGNING_KEY.encode("utf-8"),
        msg,
        hashlib.sha256,
    ).digest()
    return hmac.compare_digest(expected, raw_sig)


def extract_text_from_last_message(last_message: Dict[str, Any]) -> str:
    if not last_message:
        return ""
    preview = last_message.get("preview") or {}
    pt = preview.get("text")
    if isinstance(pt, str):
        return pt.strip()
    if isinstance(pt, dict) and "text" in pt:
        return str(pt.get("text", "")).strip()
    body = last_message.get("body")
    if isinstance(body, dict) and body.get("type") == "text":
        inner = body.get("text")
        if isinstance(inner, dict) and "text" in inner:
            return str(inner.get("text", "")).strip()
    return ""


def find_user_participant_id(conv: Dict[str, Any]) -> Optional[str]:
    participants = conv.get("featuredParticipants") or conv.get("participants") or []
    # Preferred: flow participant (matches flow-type API keys)
    for p in participants:
        if p.get("type") == "flow":
            logger.info(f"[Bird] Using flow participant id={p.get('id')}")
            return p.get("id")
    # Fallback: user type
    for p in participants:
        if p.get("type") == "user":
            return p.get("id")
    # Any non-contact participant
    for p in participants:
        if p.get("type") not in ("contact", None, ""):
            logger.info(f"[Bird] Using participant type={p.get('type')} id={p.get('id')} as sender")
            return p.get("id")
    return None


def _normalize_uid(raw) -> Any:
    if isinstance(raw, ObjectId):
        return raw
    if isinstance(raw, str) and len(raw) == 24 and ObjectId.is_valid(raw):
        return ObjectId(raw)
    return raw


def normalize_crm_user_id(raw) -> Any:
    """CRM users._id from JSON (string ObjectId) or ObjectId."""
    return _normalize_uid(raw)


async def get_connection_for_inbound(
    db,
    workspace_id: str,
    channel_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Resolve which CRM user owns this webhook.
    1) Match Bird channel_id (multi-tenant, same workspace for all clients).
    2) Else match workspace_id on a row with no channel_id (legacy / single business).
    3) Else env BIRD_DEFAULT_USER_ID if workspace matches BIRD_WORKSPACE_ID.
    """
    if channel_id:
        conn = await db.bird_connections.find_one({"channel_id": channel_id})
        if conn:
            return conn

    if workspace_id:
        conn = await db.bird_connections.find_one({
            "workspace_id": workspace_id,
            "$or": [
                {"channel_id": {"$exists": False}},
                {"channel_id": None},
                {"channel_id": ""},
            ],
        })
        if conn:
            return conn

    if BIRD_WORKSPACE_ID and workspace_id == BIRD_WORKSPACE_ID:
        uid = os.environ.get("BIRD_DEFAULT_USER_ID", "").strip()
        if uid:
            return {"user_id": _normalize_uid(uid), "workspace_id": workspace_id}
    return None


async def get_user_for_bird(db, conn: Dict[str, Any]):
    uid = _normalize_uid(conn.get("user_id"))
    return await db.users.find_one({"_id": uid})


async def fetch_conversation_participants(workspace_id: str, conversation_id: str) -> Optional[str]:
    """Fetch conversation participants and return the first non-contact participant ID."""
    if not BIRD_API_KEY:
        return None
    url = f"{BIRD_API_BASE}/workspaces/{workspace_id}/conversations/{conversation_id}/participants"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=_auth_headers())
        if resp.status_code != 200:
            logger.warning(f"[Bird] fetch participants {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        participants = data.get("results") or data.get("items") or (data if isinstance(data, list) else [])
        logger.info(f"[Bird] participants: {participants}")
        for p in participants:
            if p.get("type") not in ("contact", None, ""):
                logger.info(f"[Bird] Found sender participant type={p.get('type')} id={p.get('id')}")
                return p.get("id")
        # Last resort: any participant with an id that isn't the contact
        for p in participants:
            pid = p.get("id") or p.get("participantId")
            if pid:
                logger.info(f"[Bird] Using fallback participant type={p.get('type')} id={pid}")
                return pid
        return None
    except Exception as exc:
        logger.error(f"[Bird] fetch participants error: {exc}")
        return None


async def fetch_conversation(workspace_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    if not BIRD_API_KEY:
        return None
    url = f"{BIRD_API_BASE}/workspaces/{workspace_id}/conversations/{conversation_id}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=_auth_headers())
        if resp.status_code != 200:
            logger.warning(f"[Bird] fetch conversation {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()
    except Exception as exc:
        logger.error(f"[Bird] fetch conversation error: {exc}")
        return None


async def get_or_create_bird_customer(db, user_id, sender: Dict[str, Any], channel_id: str) -> Dict[str, Any]:
    contact = sender.get("contact") or {}
    ident = (
        contact.get("platformAddress")
        or contact.get("identifierValue")
        or sender.get("id")
        or "unknown"
    )
    phone = f"bird_{ident}"
    customer = await db.customers.find_one({"user_id": user_id, "phone": phone})
    if customer:
        return customer
    now = datetime.utcnow()
    name = (sender.get("displayName") or "").strip() or f"Bird {str(ident)[-8:]}"
    doc = {
        "user_id": user_id,
        "phone": phone,
        "phone_number": phone,
        "name": name,
        "channel": "bird",
        "bird_channel_id": channel_id,
        "bird_contact": {
            "identifierKey": contact.get("identifierKey"),
            "identifierValue": contact.get("identifierValue"),
            "platformAddress": contact.get("platformAddress"),
        },
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "notes": "",
        "vip": False,
    }
    result = await db.customers.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(f"[Bird] Created customer {phone} for user {user_id}")
    return doc


async def save_incoming_bird_message(
    db, user_id, customer_id, text: str, bird_message_id: str, channel_id: str
) -> None:
    if not bird_message_id:
        return
    existing = await db.messages.find_one({"bird_message_id": bird_message_id})
    if existing:
        return
    await db.messages.insert_one({
        "user_id": user_id,
        "customer_id": customer_id,
        "direction": "incoming",
        "content": text,
        "channel": "bird",
        "bird_message_id": bird_message_id,
        "bird_channel_id": channel_id,
        "from_number": f"bird_{channel_id}",
        "message_type": "text",
        "send_context": "incoming",
        "created_at": datetime.utcnow(),
    })


async def save_outgoing_bird_message(db, user_id, customer_id, text: str) -> None:
    await db.messages.insert_one({
        "user_id": user_id,
        "customer_id": customer_id,
        "direction": "outgoing",
        "content": text,
        "channel": "bird",
        "message_type": "text",
        "send_context": "auto_reply",
        "created_at": datetime.utcnow(),
    })


async def send_conversation_message(
    workspace_id: str,
    conversation_id: str,
    user_participant_id: Optional[str],
    text: str,
) -> bool:
    if not BIRD_API_KEY:
        logger.error("[Bird] BIRD_API_KEY not set")
        return False
    url = f"{BIRD_API_BASE}/workspaces/{workspace_id}/conversations/{conversation_id}/messages"
    payload: Dict[str, Any] = {
        "body": {"type": "text", "text": {"text": text[:4000]}},
        "participantType": "flow",
        "addMissingParticipants": True,
    }
    if user_participant_id:
        payload["participantId"] = user_participant_id
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload, headers=_auth_headers())
        if resp.status_code not in (200, 201):
            logger.error(f"[Bird] send failed {resp.status_code}: {resp.text[:300]}")
            return False
        return True
    except Exception as exc:
        logger.error(f"[Bird] send error: {exc}")
        return False
