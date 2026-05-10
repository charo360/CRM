"""
payhero_service.py — PayHero M-Pesa integration (Kenya).

Handles:
  - Listing channels (paybill / till numbers)
  - STK push (send payment request to customer phone)
  - Webhook processing (auto-confirm payments, match to orders)

PayHero API base: https://backend.payhero.co.ke/api/v2/
Auth: Basic (base64 username:password)
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

PAYHERO_BASE = "https://backend.payhero.co.ke/api/v2"


# ── Auth ───────────────────────────────────────────────────────────────────────

def _auth_header(username: str, password: str) -> str:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {encoded}"


# ── Phone normalisation ────────────────────────────────────────────────────────

def _normalise_phone(raw: str) -> str:
    """Return the bare digits without leading + or country prefix, e.g. '712345678'."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("254"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    return digits


def _phones_match(a: str, b: str) -> bool:
    return bool(a and b and _normalise_phone(a) == _normalise_phone(b))


# ── API calls ─────────────────────────────────────────────────────────────────

async def list_channels(username: str, password: str) -> List[Dict]:
    """Return the list of payment channels for this PayHero account."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{PAYHERO_BASE}/channels",
            headers={"Authorization": _auth_header(username, password)},
        )
        r.raise_for_status()
        data = r.json()
        # PayHero returns {"results": [...]} or just [...]
        if isinstance(data, dict):
            return data.get("results", data.get("channels", []))
        return data if isinstance(data, list) else []


async def stk_push(
    username: str,
    password: str,
    channel_id: int,
    phone: str,
    amount: float,
    external_reference: str,
    callback_url: str,
    customer_name: str = "",
) -> Dict:
    """
    Initiate an STK push (M-Pesa payment prompt) to the customer's phone.
    Returns the raw PayHero response dict.
    """
    payload: Dict[str, Any] = {
        "amount": int(amount),
        "phone_number": phone,
        "channel_id": channel_id,
        "provider": "m-pesa",
        "external_reference": external_reference,
        "callback_url": callback_url,
    }
    if customer_name:
        payload["customer_name"] = customer_name

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{PAYHERO_BASE}/payments",
            json=payload,
            headers={
                "Authorization": _auth_header(username, password),
                "Content-Type": "application/json",
            },
        )
        r.raise_for_status()
        return r.json()


# ── Webhook processing ────────────────────────────────────────────────────────

def parse_webhook(payload: Dict) -> Dict:
    """
    Normalise a PayHero webhook payload to a consistent internal dict.

    PayHero sends different field names depending on channel type.
    We unify them here so the rest of the code doesn't care.
    """
    status = (
        payload.get("status")
        or payload.get("payment_status")
        or ""
    ).upper()

    amount_raw = payload.get("amount") or payload.get("paid_amount") or 0
    try:
        amount = float(str(amount_raw).replace(",", ""))
    except (ValueError, TypeError):
        amount = 0.0

    phone = (
        payload.get("phone_number")
        or payload.get("msisdn")
        or payload.get("phone")
        or ""
    )

    # The reference the business set when initiating STK push (our order ref)
    external_ref = (
        payload.get("external_reference")
        or payload.get("account_reference")
        or payload.get("reference")
        or ""
    )

    # The M-Pesa confirmation code (e.g. QJX87YZ)
    provider_ref = (
        payload.get("provider_reference")
        or payload.get("mpesa_reference")
        or payload.get("transaction_id")
        or ""
    )

    channel_id = payload.get("channel_id") or payload.get("channelId")

    return {
        "status": status,
        "success": status in ("SUCCESS", "COMPLETED", "SUCCESSFUL"),
        "amount": amount,
        "phone": phone,
        "external_ref": external_ref,
        "provider_ref": provider_ref,
        "channel_id": channel_id,
        "raw": payload,
    }


async def process_payment(db, parsed: Dict) -> Dict:
    """
    After a successful PayHero webhook:
      1. Find the business that owns this channel
      2. Find the customer by phone
      3. Find the best matching order
      4. Mark order as paid
      5. Return context for receipt/notifications

    Returns a result dict the webhook handler uses to send receipt + notify.
    """
    if not parsed["success"]:
        return {"handled": False, "reason": f"Payment status: {parsed['status']}"}

    phone = parsed["phone"]
    amount = parsed["amount"]
    external_ref = parsed["external_ref"]
    channel_id = parsed["channel_id"]

    # 1. Find business by channel_id stored on connect
    user = None
    if channel_id:
        user = await db.users.find_one({"payhero_channel_id": channel_id})
    # Fallback: business stored channel as string
    if not user and channel_id:
        user = await db.users.find_one({"payhero_channel_id": str(channel_id)})

    if not user:
        logger.warning(f"[PayHero] No business found for channel_id={channel_id}")
        return {"handled": False, "reason": "No matching business for channel"}

    user_id = user["_id"]

    # 2. Find customer by phone (try multiple formats)
    bare = _normalise_phone(phone)
    customer = await db.customers.find_one({
        "user_id": user_id,
        "$or": [
            {"phone_number": phone},
            {"phone_number": f"+254{bare}"},
            {"phone_number": f"0{bare}"},
            {"phone_number": bare},
            {"phone_number": f"254{bare}"},
        ],
    })

    customer_id = customer["_id"] if customer else None
    customer_name = customer.get("name", "Customer") if customer else "Customer"

    # 3. Find the matching order
    order = await _find_order(db, user_id, customer_id, amount, external_ref)

    # 4. Mark order paid
    order_number = None
    if order:
        order_number = order.get("order_number") or ("ORD-" + str(order["_id"])[:6].upper())
        await db.orders.update_one(
            {"_id": order["_id"]},
            {
                "$set": {
                    "payment_status": "Paid",
                    "payment_method": "M-Pesa",
                    "payment_reference": parsed["provider_ref"],
                    "paid_at": datetime.utcnow(),
                    "paid_amount": amount,
                }
            },
        )
        logger.info(f"[PayHero] Order {order_number} marked Paid for user {user_id}")

    return {
        "handled": True,
        "user_id": user_id,
        "user": user,
        "customer_id": customer_id,
        "customer": customer,
        "customer_name": customer_name,
        "phone": phone,
        "amount": amount,
        "order": order,
        "order_number": order_number,
        "provider_ref": parsed["provider_ref"],
        "external_ref": external_ref,
    }


async def _find_order(db, user_id, customer_id, amount: float, external_ref: str):
    """Find best matching unpaid order. Priority: external_ref > amount match > most recent."""
    base_query: Dict = {
        "user_id": user_id,
        "payment_status": {"$in": ["Pending", "pending", "Partial", "partial", "unpaid", "Unpaid", ""]},
    }
    if customer_id:
        base_query["customer_id"] = customer_id

    # 1. Match by external_reference (set during STK push)
    if external_ref:
        order = await db.orders.find_one({**base_query, "order_number": {"$regex": re.escape(external_ref), "$options": "i"}})
        if order:
            return order
        # Also try _id match
        order = await db.orders.find_one({**base_query, "_id": external_ref})
        if order:
            return order

    # 2. Amount match ±5%
    if amount:
        candidates = await db.orders.find(base_query).sort("created_at", -1).to_list(20)
        for o in candidates:
            order_amt = float(o.get("total_amount") or o.get("amount") or 0)
            if order_amt > 0 and abs(amount - order_amt) / order_amt <= 0.05:
                return o

    # 3. Fallback: most recent unpaid
    return await db.orders.find_one(base_query, sort=[("created_at", -1)])
