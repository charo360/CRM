"""
Paystack — initialize checkout, verify, webhooks, order reconciliation.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime
from typing import Any, Dict, Optional

from paystack_auth import (
    amount_to_subunit,
    paystack_connected,
    secret_key_from_doc,
    subunit_to_major,
)
from paystack_billing import (
    create_payment_intent,
    find_intent_by_reference,
    mark_intent_failed,
    mark_intent_initialized,
    record_successful_charge,
)
from paystack_client import PaystackApiError, PaystackClient

logger = logging.getLogger(__name__)


def verify_webhook_signature(secret_key: str, raw_body: bytes, signature_header: str) -> bool:
    if not secret_key or not signature_header:
        return False
    digest = hmac.new(
        secret_key.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(digest, signature_header.strip())


def new_transaction_reference(user_id: str, external_ref: str = "") -> str:
    suffix = secrets.token_hex(4)
    base = re.sub(r"[^a-zA-Z0-9_-]", "", (external_ref or "crm"))[:32]
    uid = re.sub(r"[^a-zA-Z0-9]", "", str(user_id))[-8:]
    return f"crm_{uid}_{base}_{suffix}"[:64]


def parse_webhook_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    event = (payload.get("event") or "").strip()
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    reference = (
        data.get("reference")
        or data.get("transaction_reference")
        or ""
    )
    status = (data.get("status") or "").lower()
    amount_sub = data.get("amount") or 0
    currency = (data.get("currency") or "NGN").upper()
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    customer = data.get("customer") or {}
    email = ""
    if isinstance(customer, dict):
        email = customer.get("email") or ""

    success = event == "charge.success" or status == "success"

    return {
        "event": event,
        "success": success,
        "reference": reference,
        "amount_major": subunit_to_major(int(amount_sub or 0), currency),
        "currency": currency,
        "metadata": metadata,
        "customer_email": email,
        "channel": data.get("channel") or "",
        "raw": payload,
    }


async def initialize_checkout_for_user(
    db,
    user_doc: dict,
    *,
    user_id: str,
    email: str,
    amount_major: float,
    currency: Optional[str] = None,
    external_reference: str = "",
    order_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    customer_name: str = "",
    callback_url: str = "",
) -> Dict[str, Any]:
    secret = secret_key_from_doc(user_doc)
    if not secret:
        raise ValueError("Paystack not connected")

    cur = (currency or user_doc.get("paystack_default_currency") or "NGN").upper()
    reference = new_transaction_reference(user_id, external_reference or order_id or "")

    intent = await create_payment_intent(
        db,
        user_id=user_id,
        amount_major=amount_major,
        currency=cur,
        email=email,
        reference=reference,
        external_reference=external_reference,
        order_id=order_id,
        customer_id=customer_id,
        customer_name=customer_name,
        callback_url=callback_url,
    )

    metadata = {
        "crm_user_id": str(user_id),
        "order_id": str(order_id) if order_id else "",
        "external_reference": external_reference or "",
        "intent_id": str(intent["_id"]),
    }

    payload = {
        "email": email,
        "amount": amount_to_subunit(amount_major, cur),
        "currency": cur,
        "reference": reference,
        "metadata": metadata,
    }
    subaccount_code = (user_doc.get("paystack_subaccount_code") or "").strip()
    if subaccount_code:
        payload["subaccount"] = subaccount_code
    if callback_url:
        payload["callback_url"] = callback_url

    client = PaystackClient(secret)
    try:
        data = await client.initialize_transaction(payload)
    except PaystackApiError as e:
        await mark_intent_failed(db, intent["_id"], str(e))
        raise

    auth_url = data.get("authorization_url") or ""
    access_code = data.get("access_code") or ""
    ps_ref = data.get("reference") or reference

    await mark_intent_initialized(
        db,
        intent["_id"],
        authorization_url=auth_url,
        access_code=access_code,
        paystack_reference=ps_ref,
        raw=data,
    )

    return {
        "authorization_url": auth_url,
        "access_code": access_code,
        "reference": ps_ref,
        "intent_id": str(intent["_id"]),
        "currency": cur,
        "amount_major": amount_major,
    }


async def process_charge_success(
    db,
    parsed: Dict[str, Any],
    *,
    raw_payload: Optional[Dict] = None,
) -> Dict[str, Any]:
    if not parsed.get("success"):
        return {"handled": False, "reason": f"event={parsed.get('event')}"}

    reference = (parsed.get("reference") or "").strip()
    if not reference:
        return {"handled": False, "reason": "no reference"}

    intent = await find_intent_by_reference(db, reference)
    metadata = parsed.get("metadata") or {}
    user_id = None
    if intent:
        user_id = intent.get("user_id")
    elif metadata.get("crm_user_id"):
        user_id = metadata.get("crm_user_id")

    if not user_id:
        logger.warning("[Paystack] No user for reference=%s", reference)
        return {"handled": False, "reason": "unknown merchant"}

    from payhero_auth import user_id_filter

    user = await db.users.find_one(
        user_id_filter(user_id),
        {
            "paystack_secret_key": 1,
            "paystack_auth_mode": 1,
            "paystack_default_currency": 1,
            "push_token": 1,
        },
    )
    if not user or not paystack_connected(user):
        return {"handled": False, "reason": "merchant not connected"}

    order_id = (intent or {}).get("order_id") or metadata.get("order_id") or None
    if order_id == "":
        order_id = None

    ledger = await record_successful_charge(
        db,
        user_id=str(user_id),
        paystack_reference=reference,
        amount_major=parsed["amount_major"],
        currency=parsed["currency"],
        order_id=str(order_id) if order_id else None,
        intent_id=intent["_id"] if intent else None,
        channel=parsed.get("channel") or "",
        customer_email=parsed.get("customer_email") or "",
        raw_payload=raw_payload,
    )

    if not ledger.get("inserted"):
        return {"handled": True, "duplicate": True, "user_id": user_id}

    order = await _find_order(
        db,
        user["_id"],
        order_id=order_id,
        amount=parsed["amount_major"],
        external_ref=(intent or {}).get("external_reference") or metadata.get("external_reference") or "",
    )

    order_number = None
    if order:
        order_number = order.get("order_number") or ("ORD-" + str(order["_id"])[:6].upper())
        await db.orders.update_one(
            {"_id": order["_id"]},
            {
                "$set": {
                    "payment_status": "Paid",
                    "payment_method": "Paystack",
                    "payment_reference": reference,
                    "paid_at": datetime.utcnow(),
                    "paid_amount": parsed["amount_major"],
                }
            },
        )

    customer_name = (intent or {}).get("customer_name") or "Customer"
    phone = ""
    customer_id = (intent or {}).get("customer_id")
    if customer_id:
        cust = await db.customers.find_one({"_id": customer_id})
        if cust:
            customer_name = cust.get("name", customer_name)
            phone = cust.get("phone_number") or ""

    return {
        "handled": True,
        "user_id": user_id,
        "user": user,
        "customer_name": customer_name,
        "phone": phone,
        "amount": parsed["amount_major"],
        "currency": parsed["currency"],
        "order_number": order_number,
        "reference": reference,
        "customer_email": parsed.get("customer_email"),
    }


async def _find_order(
    db,
    user_id,
    *,
    order_id: Optional[str] = None,
    amount: float = 0,
    external_ref: str = "",
):
    base_query: Dict = {
        "user_id": user_id,
        "payment_status": {"$in": ["Pending", "pending", "Partial", "partial", "unpaid", "Unpaid", ""]},
    }

    if order_id:
        from bson import ObjectId

        try:
            oid = ObjectId(order_id)
            order = await db.orders.find_one({**base_query, "_id": oid})
            if order:
                return order
        except Exception:
            pass
        order = await db.orders.find_one({**base_query, "_id": order_id})
        if order:
            return order

    if external_ref:
        order = await db.orders.find_one(
            {**base_query, "order_number": {"$regex": re.escape(external_ref), "$options": "i"}}
        )
        if order:
            return order

    if amount:
        candidates = await db.orders.find(base_query).sort("created_at", -1).to_list(20)
        for o in candidates:
            order_amt = float(o.get("total_amount") or o.get("amount") or 0)
            if order_amt > 0 and abs(amount - order_amt) / order_amt <= 0.05:
                return o

    return await db.orders.find_one(base_query, sort=[("created_at", -1)])
