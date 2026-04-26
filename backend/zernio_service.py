import logging
import os
import httpx
from datetime import datetime
from typing import Any, Dict, Optional
from bson import ObjectId

logger = logging.getLogger(__name__)

ZERNIO_BASE = os.environ.get("ZERNIO_API_BASE", "https://zernio.com/api/v1").rstrip("/")
ZERNIO_API_KEY = os.environ.get("ZERNIO_API_KEY", "").strip()

def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {ZERNIO_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

async def get_user_by_zernio_profile(db, profile_id: str) -> Optional[Dict[str, Any]]:
    """Resolve CRM user by their Zernio Profile ID."""
    if not profile_id:
        return None
    return await db.users.find_one({"zernio_profile_id": profile_id})

async def get_or_create_zernio_customer(db, user_id, sender_id: str, sender_name: str, platform: str, conversation_id: str) -> Dict[str, Any]:
    """Find or create a CRM customer based on the inbound Zernio message sender."""
    phone = f"zernio_{platform}_{sender_id}"
    customer = await db.customers.find_one({"user_id": user_id, "phone": phone})
    if customer:
        if customer.get("zernio_conversation_id") != conversation_id:
            await db.customers.update_one({"_id": customer["_id"]}, {"$set": {"zernio_conversation_id": conversation_id}})
            customer["zernio_conversation_id"] = conversation_id
        return customer
        
    now = datetime.utcnow()
    name = sender_name.strip() or f"{platform.capitalize()} User {sender_id[-8:]}"
    doc = {
        "user_id": user_id,
        "phone": phone,
        "phone_number": phone, # Treat as unique identifier
        "name": name,
        "channel": platform,
        "zernio_sender_id": sender_id,
        "zernio_conversation_id": conversation_id,
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "notes": "",
        "vip": False,
    }
    result = await db.customers.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(f"[ZernioService] Created customer {phone} for user {user_id}")
    return doc

async def save_incoming_zernio_message(
    db, user_id, customer_id, text: str, message_id: str, platform: str
) -> None:
    if not message_id:
        return
    existing = await db.messages.find_one({"zernio_message_id": message_id})
    if existing:
        return
    await db.messages.insert_one({
        "user_id": user_id,
        "customer_id": customer_id,
        "direction": "incoming",
        "content": text,
        "channel": platform,
        "zernio_message_id": message_id,
        "message_type": "text",
        "send_context": "incoming",
        "created_at": datetime.utcnow(),
    })

async def save_outgoing_zernio_message(db, user_id, customer_id, text: str, platform: str) -> None:
    await db.messages.insert_one({
        "user_id": user_id,
        "customer_id": customer_id,
        "direction": "outgoing",
        "content": text,
        "channel": platform,
        "message_type": "text",
        "send_context": "auto_reply",
        "created_at": datetime.utcnow(),
    })

async def send_zernio_message(
    conversation_id: str,
    text: str,
    media_url: Optional[str] = None,
) -> bool:
    """Send a reply via Zernio Inbox API."""
    if not ZERNIO_API_KEY:
        logger.error("[ZernioService] ZERNIO_API_KEY not set")
        return False

    # Resolve relative URLs to absolute
    if media_url and media_url.startswith("/"):
        backend_base = os.environ.get("BACKEND_PUBLIC_URL", "https://crm-1-pnfo.onrender.com").rstrip("/")
        media_url = backend_base + media_url

    url = f"{ZERNIO_BASE}/messages/send-inbox-message"
    payload = {
        "conversation_id": conversation_id,
        "message": text[:4000],
    }
    if media_url:
        payload["media_url"] = media_url

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload, headers=_auth_headers())
            
        if resp.status_code not in (200, 201):
            logger.error(f"[ZernioService] Send failed {resp.status_code}: {resp.text[:300]}")
            return False
            
        logger.info(f"[ZernioService] Message sent to conv {conversation_id} (HTTP {resp.status_code})")
        return True
    except Exception as exc:
        logger.error(f"[ZernioService] Send error: {exc}")
        return False
