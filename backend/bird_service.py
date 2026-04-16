"""
bird_service.py — Bird.com Conversations webhook + outbound messages (AccessKey API).

Inbound: POST /webhook/bird — Bird sends conversation.created / conversation.updated
        with lastMessage from type \"contact\" (see Bird Conversations API events).

Store Bird workspace → CRM user in db.bird_connections:
  { user_id, workspace_id, created_at, updated_at }

Env:
  BIRD_API_KEY            — AccessKey (required for send + optional fetch)
  BIRD_WORKSPACE_ID       — default workspace UUID if webhook body omits it
  BIRD_DEFAULT_USER_ID    — fallback CRM user _id (24-char hex) when using env workspace only
  BIRD_WEBHOOK_SIGNING_KEY — if set, POST /webhook/bird verifies MessageBird signature headers
  BIRD_WEBHOOK_PUBLIC_URL — full URL Bird uses when signing (must match subscription URL)
  BIRD_API_BASE           — default https://api.bird.com
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
    for p in conv.get("featuredParticipants") or []:
        if p.get("type") == "user":
            return p.get("id")
    return None


def _normalize_uid(raw) -> Any:
    if isinstance(raw, ObjectId):
        return raw
    if isinstance(raw, str) and len(raw) == 24 and ObjectId.is_valid(raw):
        return ObjectId(raw)
    return raw


async def get_connection_by_workspace(db, workspace_id: str) -> Optional[Dict[str, Any]]:
    conn = await db.bird_connections.find_one({"workspace_id": workspace_id})
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
    user_participant_id: str,
    text: str,
) -> bool:
    if not BIRD_API_KEY:
        logger.error("[Bird] BIRD_API_KEY not set")
        return False
    url = f"{BIRD_API_BASE}/workspaces/{workspace_id}/conversations/{conversation_id}/messages"
    payload = {
        "body": {"type": "text", "text": {"text": text[:4000]}},
        "participantId": user_participant_id,
        "participantType": "user",
        "addMissingParticipants": True,
    }
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
