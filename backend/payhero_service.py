"""
payhero_service.py — PayHero M-Pesa integration (Kenya).

Handles:
  - Listing channels (paybill / till numbers)
  - STK push (send payment request to customer phone)
  - Webhook processing (auto-confirm payments, match to orders)

PayHero API base: https://backend.payhero.co.ke/api/v2/
Auth: Basic token from PayHero Dashboard → API Keys
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from payhero_auth import PAYHERO_BASE
from payhero_credentials import (
    PAYHERO_AUTH_PLATFORM,
    payhero_auth_mode,
    resolve_authorization_header,
)

logger = logging.getLogger(__name__)


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

def merchant_channel_snapshot(user_doc: dict) -> List[Dict]:
    """Single stored destination for platform-managed PayHero tenants."""
    cid = user_doc.get("payhero_channel_id")
    if not cid:
        return []
    label = (
        user_doc.get("payhero_channel_description")
        or user_doc.get("payhero_username")
        or "M-Pesa"
    )
    return [
        {
            "id": int(cid) if str(cid).isdigit() else cid,
            "name": label,
            "description": user_doc.get("payhero_channel_description"),
            "channel_type": user_doc.get("payhero_channel_type"),
            "short_code": user_doc.get("payhero_short_code"),
            "paybill": str(user_doc.get("payhero_short_code") or ""),
        }
    ]


async def register_payment_channel(
    auth_header: str,
    *,
    account_id: int,
    channel_type: str,
    short_code: str,
    account_number: str,
    description: str,
) -> Dict:
    payload = {
        "channel_type": channel_type,
        "account_id": account_id,
        "short_code": str(short_code).strip(),
        "account_number": account_number,
        "description": description,
    }
    timeout = httpx.Timeout(25.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{PAYHERO_BASE}/payment_channels",
            json=payload,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            return data
        raise ValueError("Unexpected PayHero response when registering channel")


async def list_bank_paybills(auth_header: str) -> List[Dict[str, Any]]:
    """PayHero-registered banks (name + M-Pesa paybill) for bank destination setup."""
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(
            f"{PAYHERO_BASE}/bank_paybills",
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
        )
        r.raise_for_status()
        data = r.json()

    raw = []
    if isinstance(data, dict):
        raw = data.get("bank_paybills") or data.get("banks") or []
    elif isinstance(data, list):
        raw = data

    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or item.get("bank_name") or "").strip()
        paybill = str(item.get("paybill") or item.get("short_code") or "").strip()
        if not name or not paybill:
            continue
        out.append(
            {
                "id": item.get("id"),
                "name": name,
                "paybill": paybill,
            }
        )
    out.sort(key=lambda x: (x.get("name") or "").lower())
    return out

async def list_channels_for_user(user_doc: dict) -> List[Dict]:
    """Return payment channels using stored PayHero credentials."""
    if payhero_auth_mode(user_doc) == PAYHERO_AUTH_PLATFORM:
        return merchant_channel_snapshot(user_doc)

    auth = resolve_authorization_header(user_doc)
    if not auth:
        raise ValueError("PayHero not connected")
    async with httpx.AsyncClient(timeout=15) as client:
        last_err = None
        for path in ("/payment_channels", "/channels"):
            r = await client.get(
                f"{PAYHERO_BASE}{path}",
                headers={"Authorization": auth, "Content-Type": "application/json"},
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    raw = (
                        data.get("results")
                        or data.get("channels")
                        or data.get("payment_channels")
                        or data.get("data")
                    )
                    return raw if isinstance(raw, list) else []
                return data if isinstance(data, list) else []
            last_err = r
        if last_err is not None:
            last_err.raise_for_status()
        return []


async def list_channels(username: str, password: str) -> List[Dict]:
    """Legacy: username/password or token in username field."""
    doc: Dict[str, Any] = {"payhero_username": username, "payhero_password": password}
    if password:
        return await list_channels_for_user(doc)
    doc["payhero_api_token"] = username
    return await list_channels_for_user(doc)


async def stk_push_for_user(
    user_doc: dict,
    channel_id: int,
    phone: str,
    amount: float,
    external_reference: str,
    callback_url: str,
    customer_name: str = "",
) -> Dict:
    auth = resolve_authorization_header(user_doc)
    if not auth:
        raise ValueError("PayHero not connected")
    return await _stk_push_request(
        auth, channel_id, phone, amount, external_reference, callback_url, customer_name
    )


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
    doc: Dict[str, Any] = {"payhero_username": username, "payhero_password": password}
    if not password:
        doc["payhero_api_token"] = username
    return await stk_push_for_user(
        doc, channel_id, phone, amount, external_reference, callback_url, customer_name
    )


async def _stk_push_request(
    auth_header: str,
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
                "Authorization": auth_header,
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


async def process_payment(db, parsed: Dict, *, raw_payload: Optional[Dict] = None) -> Dict:
    """
    After a successful PayHero webhook:
      1. Idempotent ledger (PayHero fee estimate)
      2. Find the business that owns this channel
      3. Find the customer by phone
      4. Find the best matching order
      5. Mark order as paid
      6. Return context for receipt/notifications

    Returns a result dict the webhook handler uses to send receipt + notify.
    """
    if not parsed["success"]:
        return {"handled": False, "reason": f"Payment status: {parsed['status']}"}

    phone = parsed["phone"]
    amount = parsed["amount"]
    external_ref = parsed["external_ref"]
    channel_id = parsed["channel_id"]
    provider_ref = parsed.get("provider_ref") or ""

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

    from payhero_billing import INTENTS, record_mpesa_payment_success

    intent = None
    if external_ref:
        intent = await db[INTENTS].find_one(
            {"user_id": str(user_id), "external_reference": external_ref},
            sort=[("created_at", -1)],
        )

    ledger = await record_mpesa_payment_success(
        db,
        user_id=str(user_id),
        gross_kes=amount,
        provider_ref=provider_ref,
        order_id=str(intent["order_id"]) if intent and intent.get("order_id") else None,
        intent_id=intent["_id"] if intent else None,
        external_reference=external_ref,
        phone=phone,
        raw_payload=raw_payload,
    )

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
        "payhero_fee_kes": ledger.get("fee_kes"),
        "ledger_inserted": ledger.get("inserted"),
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
