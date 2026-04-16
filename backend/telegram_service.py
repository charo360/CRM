"""
telegram_service.py — Telegram Bot integration for Zilo CRM.

Flow:
  1. Customer sends message to @Zilocrmbot
  2. Telegram fires webhook → /webhook/telegram on our backend
  3. We find which CRM user owns this bot token
  4. AutoReplyV2 processes the message and replies via Telegram API

Each CRM user stores their bot token in db.telegram_connections:
  { user_id, bot_token, bot_username, created_at }
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional, Dict

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot"


# ── Send a reply via Telegram ──────────────────────────────────────────────────

async def send_telegram_message(bot_token: str, chat_id: int, text: str) -> bool:
    """Send a text reply to a Telegram chat."""
    url = f"{TELEGRAM_API}{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text":    text[:4096],  # Telegram 4096-char limit
        "parse_mode": "Markdown",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.error(f"[Telegram] Send failed {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as exc:
        logger.error(f"[Telegram] Send error: {exc}")
        return False


# ── Register webhook with Telegram ────────────────────────────────────────────

async def set_telegram_webhook(bot_token: str, webhook_url: str) -> bool:
    """Tell Telegram where to send updates for this bot."""
    url = f"{TELEGRAM_API}{bot_token}/setWebhook"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={"url": webhook_url})
        data = resp.json()
        if data.get("ok"):
            logger.info(f"[Telegram] Webhook set to {webhook_url}")
            return True
        logger.error(f"[Telegram] Webhook set failed: {data}")
        return False
    except Exception as exc:
        logger.error(f"[Telegram] Webhook set error: {exc}")
        return False


async def delete_telegram_webhook(bot_token: str) -> bool:
    """Remove Telegram webhook (on disconnect)."""
    url = f"{TELEGRAM_API}{bot_token}/deleteWebhook"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url)
        return resp.json().get("ok", False)
    except Exception:
        return False


async def get_bot_info(bot_token: str) -> Optional[Dict]:
    """Fetch bot username and ID from Telegram."""
    url = f"{TELEGRAM_API}{bot_token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        data = resp.json()
        if data.get("ok"):
            return data["result"]
        return None
    except Exception:
        return None


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def get_user_by_bot_token(db, bot_token: str) -> Optional[Dict]:
    """Find the CRM user who owns this bot token."""
    conn = await db.telegram_connections.find_one({"bot_token": bot_token})
    if not conn:
        return None
    user = await db.users.find_one({"_id": conn["user_id"]})
    if user:
        user["_tg_token"] = bot_token
    return user


async def get_or_create_telegram_customer(db, user_id: str, chat_id: int, sender_name: str) -> Dict:
    """Find or create a customer record for a Telegram sender."""
    tg_phone = f"telegram_{chat_id}"
    customer = await db.customers.find_one({"user_id": user_id, "phone": tg_phone})
    if customer:
        return customer

    now = datetime.utcnow()
    doc = {
        "user_id":    user_id,
        "phone":      tg_phone,
        "name":       sender_name or f"Telegram User {chat_id}",
        "channel":    "telegram",
        "meta_id":    str(chat_id),
        "created_at": now,
        "updated_at": now,
        "tags":       [],
        "notes":      "",
        "vip":        False,
    }
    result = await db.customers.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(f"[Telegram] Created customer chat_id={chat_id} for user {user_id}")
    return doc


async def save_telegram_message(db, user_id: str, customer_id, chat_id: int, text: str, direction: str, message_id: int = 0) -> None:
    """Save a Telegram message to the messages collection."""
    if direction == "incoming":
        existing = await db.messages.find_one({"telegram_message_id": message_id, "user_id": user_id})
        if existing:
            return
    await db.messages.insert_one({
        "user_id":            user_id,
        "customer_id":        customer_id,
        "direction":          direction,
        "content":            text,
        "channel":            "telegram",
        "telegram_message_id": message_id,
        "from_number":        f"telegram_{chat_id}",
        "message_type":       "text",
        "send_context":       "incoming" if direction == "incoming" else "auto_reply",
        "created_at":         datetime.utcnow(),
    })
