"""
Flutterwave — initialize checkout, webhooks, order reconciliation.
"""
from __future__ import annotations

import hmac
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

from flutterwave_auth import new_transaction_reference, secret_key_from_doc
from flutterwave_billing import (
    create_payment_intent,
    find_intent_by_tx_ref,
    mark_intent_failed,
    mark_intent_initialized,
    record_successful_charge,
)
from flutterwave_client import FlutterwaveApiError, FlutterwaveClient
from flutterwave_credentials import (
    flutterwave_connected,
    merchant_split_fraction,
    webhook_secret_hash,
)

logger = logging.getLogger(__name__)


def verify_webhook_hash(signature_header: str) -> bool:
    expected = webhook_secret_hash()
    if not expected or not signature_header:
        return False
    return hmac.compare_digest(signature_header.strip(), expected.strip())


def parse_webhook_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    event = (payload.get("event") or payload.get("event.type") or "").strip()
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    tx_ref = (data.get("tx_ref") or data.get("txRef") or "").strip()
    status = (data.get("status") or "").lower()
    amount = data.get("amount")
    try:
        amount_major = float(amount) if amount is not None else 0.0
    except (TypeError, ValueError):
        amount_major = 0.0
    currency = (data.get("currency") or "NGN").upper()
    meta = data.get("meta") or data.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}

    customer = data.get("customer") or {}
    email = ""
    if isinstance(customer, dict):
        email = customer.get("email") or ""

    success = event in ("charge.completed",) or status in ("successful", "success")

    return {
        "event": event,
        "success": success,
        "tx_ref": tx_ref,
        "amount_major": amount_major,
        "currency": currency,
        "meta": meta,
        "customer_email": email,
        "channel": data.get("payment_type") or data.get("processor_response") or "",
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
    redirect_url: str = "",
) -> Dict[str, Any]:
    secret = secret_key_from_doc(user_doc)
    if not secret:
        raise ValueError("Flutterwave not connected")

    cur = (currency or user_doc.get("flutterwave_default_currency") or "NGN").upper()
    tx_ref = new_transaction_reference(user_id, external_reference or order_id or "")

    intent = await create_payment_intent(
        db,
        user_id=user_id,
        amount_major=amount_major,
        currency=cur,
        email=email,
        tx_ref=tx_ref,
        external_reference=external_reference,
        order_id=order_id,
        customer_id=customer_id,
        customer_name=customer_name,
        redirect_url=redirect_url,
    )

    meta = {
        "crm_user_id": str(user_id),
        "order_id": str(order_id) if order_id else "",
        "external_reference": external_reference or "",
        "intent_id": str(intent["_id"]),
    }

    sub_id = (user_doc.get("flutterwave_subaccount_id") or "").strip()
    payload: Dict[str, Any] = {
        "tx_ref": tx_ref,
        "amount": round(float(amount_major), 2),
        "currency": cur,
        "redirect_url": redirect_url or "https://flutterwave.com/ng/",
        "customer": {
            "email": email,
            "name": (customer_name or email.split("@")[0])[:120],
        },
        "meta": meta,
        "customizations": {
            "title": "Order payment",
            "description": external_reference or "CRM checkout",
        },
    }
    if sub_id:
        payload["subaccounts"] = [{"id": sub_id}]

    client = FlutterwaveClient(secret)
    try:
        data = await client.create_payment(payload)
    except FlutterwaveApiError as e:
        await mark_intent_failed(db, intent["_id"], str(e))
        raise

    link = data.get("link") or data.get("checkout_url") or ""
    flw_ref = str(data.get("flw_ref") or data.get("id") or "")

    await mark_intent_initialized(
        db,
        intent["_id"],
        payment_link=link,
        flw_ref=flw_ref,
        raw=data,
    )

    return {
        "payment_link": link,
        "authorization_url": link,
        "tx_ref": tx_ref,
        "reference": tx_ref,
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

    tx_ref = (parsed.get("tx_ref") or "").strip()
    if not tx_ref:
        return {"handled": False, "reason": "no tx_ref"}

    intent = await find_intent_by_tx_ref(db, tx_ref)
    meta = parsed.get("meta") or {}
    user_id = None
    if intent:
        user_id = intent.get("user_id")
    elif meta.get("crm_user_id"):
        user_id = meta.get("crm_user_id")

    if not user_id:
        logger.warning("[Flutterwave] No user for tx_ref=%s", tx_ref)
        return {"handled": False, "reason": "unknown merchant"}

    from payhero_auth import user_id_filter

    user = await db.users.find_one(
        user_id_filter(user_id),
        {
            "flutterwave_subaccount_id": 1,
            "flutterwave_default_currency": 1,
            "push_token": 1,
        },
    )
    if not user or not flutterwave_connected(user):
        return {"handled": False, "reason": "merchant not connected"}

    order_id = (intent or {}).get("order_id") or meta.get("order_id") or None
    if order_id == "":
        order_id = None

    ledger = await record_successful_charge(
        db,
        user_id=str(user_id),
        flutterwave_tx_ref=tx_ref,
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
        external_ref=(intent or {}).get("external_reference") or meta.get("external_reference") or "",
    )

    order_number = None
    if order:
        order_number = order.get("order_number") or ("ORD-" + str(order["_id"])[:6].upper())
        await db.orders.update_one(
            {"_id": order["_id"]},
            {
                "$set": {
                    "payment_status": "Paid",
                    "payment_method": "Flutterwave",
                    "payment_reference": tx_ref,
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
        "reference": tx_ref,
        "customer_email": parsed.get("customer_email"),
    }


def build_subaccount_payload(
    *,
    account_bank: str,
    account_number: str,
    business_name: str,
    business_email: str,
    business_contact: str,
    country: str,
) -> Dict[str, Any]:
    # Dashboard shows "Subaccount's share (%)" as 100.00; API wants decimal fraction 1.0 / 0.9.
    split_value = merchant_split_fraction()
    return {
        "account_bank": account_bank,
        "account_number": account_number,
        "business_name": business_name,
        "business_email": business_email,
        "business_contact": business_contact,
        "business_mobile": business_contact,
        "country": country.upper(),
        "split_type": "percentage",
        "split_value": split_value,
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
