"""
meta_service.py — Facebook Messenger & Instagram DM integration.

Flow per channel:
  1. Customer sends DM on Messenger or Instagram
  2. Meta fires webhook → /webhook/messenger or /webhook/instagram
  3. We normalize the message → save to db.messages
  4. AutoReplyV2 engine processes and replies via Meta Graph API

Each CRM user stores their own Page Access Token in db.meta_connections:
  { user_id, page_id, instagram_id, page_access_token, channel, created_at }
"""
from __future__ import annotations

import logging
import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "crm_meta_webhook_2026")
META_APP_SECRET   = os.environ.get("META_APP_SECRET", "")


# ── Send a reply via Messenger ─────────────────────────────────────────────────

async def send_messenger_message(page_access_token: str, recipient_id: str, text: str) -> bool:
    """Send a text reply to a Messenger user."""
    url = f"{GRAPH_BASE}/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message":   {"text": text[:2000]},  # Messenger 2000-char limit
        "messaging_type": "RESPONSE",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, params={"access_token": page_access_token})
        if resp.status_code != 200:
            logger.error(f"[Meta] Messenger send failed {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as exc:
        logger.error(f"[Meta] Messenger send error: {exc}")
        return False


async def send_instagram_message(page_access_token: str, recipient_id: str, text: str) -> bool:
    """Send a text reply to an Instagram DM user."""
    url = f"{GRAPH_BASE}/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message":   {"text": text[:1000]},  # Instagram 1000-char limit
        "messaging_type": "RESPONSE",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, params={"access_token": page_access_token})
        if resp.status_code != 200:
            logger.error(f"[Meta] Instagram send failed {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as exc:
        logger.error(f"[Meta] Instagram send error: {exc}")
        return False


# ── Lookup which CRM user owns a given page/instagram account ─────────────────

async def get_user_by_page_id(db, page_id: str) -> Optional[Dict]:
    """Find CRM user by their connected Facebook Page ID."""
    conn = await db.meta_connections.find_one({"page_id": page_id, "channel": "messenger"})
    if not conn:
        return None
    user = await db.users.find_one({"_id": conn["user_id"]})
    if user:
        user["_meta_token"] = conn["page_access_token"]
        user["_meta_page_id"] = page_id
    return user


async def get_user_by_instagram_id(db, instagram_id: str) -> Optional[Dict]:
    """Find CRM user by their connected Instagram account ID."""
    conn = await db.meta_connections.find_one({"instagram_id": instagram_id, "channel": "instagram"})
    if not conn:
        return None
    user = await db.users.find_one({"_id": conn["user_id"]})
    if user:
        user["_meta_token"] = conn["page_access_token"]
        user["_meta_instagram_id"] = instagram_id
    return user


# ── Normalize sender ID → customer record ─────────────────────────────────────

async def get_or_create_meta_customer(db, user_id: str, sender_id: str, channel: str, sender_name: str = "") -> Dict:
    """Find or create a customer record for a Messenger/Instagram sender."""
    # Use a synthetic phone-like ID: meta_<channel>_<sender_id>
    meta_phone = f"meta_{channel}_{sender_id}"

    customer = await db.customers.find_one({"user_id": user_id, "phone": meta_phone})
    if customer:
        return customer

    now = datetime.utcnow()
    doc = {
        "user_id":    user_id,
        "phone":      meta_phone,
        "name":       sender_name or f"{channel.title()} User {sender_id[-6:]}",
        "channel":    channel,
        "meta_id":    sender_id,
        "created_at": now,
        "updated_at": now,
        "tags":       [],
        "notes":      "",
        "vip":        False,
    }
    result = await db.customers.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(f"[Meta] Created {channel} customer {sender_id} for user {user_id}")
    return doc


# ── Save incoming message to db ────────────────────────────────────────────────

async def save_incoming_message(db, user_id: str, customer_id, sender_id: str, text: str, channel: str, mid: str) -> None:
    """Save an inbound Meta message to the messages collection."""
    # Dedup by message ID
    existing = await db.messages.find_one({"meta_mid": mid})
    if existing:
        return

    await db.messages.insert_one({
        "user_id":     user_id,
        "customer_id": customer_id,
        "direction":   "incoming",
        "content":     text,
        "channel":     channel,
        "meta_mid":    mid,
        "from_number": f"meta_{channel}_{sender_id}",
        "message_type": "text",
        "send_context": "incoming",
        "created_at":  datetime.utcnow(),
    })


async def save_outgoing_message(db, user_id: str, customer_id, text: str, channel: str) -> None:
    """Save an outbound Meta reply to the messages collection."""
    await db.messages.insert_one({
        "user_id":     user_id,
        "customer_id": customer_id,
        "direction":   "outgoing",
        "content":     text,
        "channel":     channel,
        "message_type": "text",
        "send_context": "auto_reply",
        "created_at":  datetime.utcnow(),
    })
