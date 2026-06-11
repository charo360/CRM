"""
Stripe Connect — onboarding, Checkout (destination charges), webhooks, orders.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

import stripe

from payhero_auth import user_id_filter
from stripe_auth import new_checkout_reference
from stripe_billing import (
    create_payment_intent,
    find_intent_by_reference,
    find_intent_by_session_id,
    mark_intent_checkout_open,
    mark_intent_failed,
    record_successful_charge,
)
from stripe_client import StripeApiError, StripeClient
from stripe_credentials import (
    application_fee_minor,
    amount_to_minor,
    minor_to_major,
    platform_secret_key,
    stripe_checkout_ready,
    stripe_connected,
    webhook_secret_connect,
    webhook_secret_platform,
)

logger = logging.getLogger(__name__)


def verify_webhook_payload(raw_body: bytes, signature_header: str, *, connect: bool = False) -> Optional[Dict[str, Any]]:
    secret = webhook_secret_connect() if connect else webhook_secret_platform()
    if not secret or not signature_header:
        return None
    key = platform_secret_key()
    if not key:
        return None
    try:
        stripe.api_key = key
        event = stripe.Webhook.construct_event(raw_body, signature_header, secret)
        if hasattr(event, "to_dict"):
            return event.to_dict()
        return dict(event)
    except Exception as e:
        logger.warning("[Stripe webhook] verify failed connect=%s: %s", connect, e)
        return None


def account_status_from_stripe(acct: Dict[str, Any]) -> Dict[str, Any]:
    caps = acct.get("capabilities") or {}
    card = caps.get("card_payments") if isinstance(caps, dict) else None
    return {
        "charges_enabled": bool(acct.get("charges_enabled")),
        "payouts_enabled": bool(acct.get("payouts_enabled")),
        "details_submitted": bool(acct.get("details_submitted")),
        "card_payments_status": card if isinstance(card, str) else (card or {}).get("status") if isinstance(card, dict) else None,
    }


async def sync_account_fields(db, user_id: str, account_id: str) -> Dict[str, Any]:
    client = StripeClient()
    acct = await client.retrieve_account(account_id)
    status = account_status_from_stripe(acct)
    fields = {
        "stripe_charges_enabled": status["charges_enabled"],
        "stripe_payouts_enabled": status["payouts_enabled"],
        "stripe_details_submitted": status["details_submitted"],
        "stripe_business_name": (
            (acct.get("business_profile") or {}).get("name")
            or acct.get("email")
            or ""
        )[:200],
    }
    await db.users.update_one(user_id_filter(user_id), {"$set": fields})
    return {**status, **fields}


async def create_or_refresh_onboarding_link(
    db,
    *,
    user_id: str,
    user_doc: dict,
    return_url: str,
    refresh_url: str,
) -> Dict[str, Any]:
    client = StripeClient()
    account_id = (user_doc.get("stripe_connect_account_id") or "").strip()
    if not account_id:
        raise ValueError("Stripe account not created yet")

    link = await client.create_account_link(
        account_id=account_id,
        return_url=return_url,
        refresh_url=refresh_url,
    )
    url = (link.get("url") or "").strip()
    if not url:
        raise StripeApiError("Stripe did not return an onboarding URL")
    await sync_account_fields(db, user_id, account_id)
    return {"onboarding_url": url, "account_id": account_id}


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
    success_url: str = "",
    cancel_url: str = "",
) -> Dict[str, Any]:
    if not stripe_checkout_ready(user_doc):
        raise ValueError(
            "Stripe payouts are not ready — complete Connect onboarding in Integrations"
        )

    destination = (user_doc.get("stripe_connect_account_id") or "").strip()
    if not destination.startswith("acct_"):
        raise ValueError("Stripe Connect account missing")

    cur = (currency or user_doc.get("stripe_default_currency") or "USD").upper()
    checkout_reference = new_checkout_reference(user_id, external_reference or order_id or "")

    intent = await create_payment_intent(
        db,
        user_id=user_id,
        amount_major=amount_major,
        currency=cur,
        email=email,
        checkout_reference=checkout_reference,
        external_reference=external_reference,
        order_id=order_id,
        customer_id=customer_id,
        customer_name=customer_name,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    total_minor = amount_to_minor(amount_major, cur)
    fee_minor = application_fee_minor(total_minor, cur)

    metadata = {
        "crm_user_id": str(user_id),
        "order_id": str(order_id) if order_id else "",
        "external_reference": external_reference or "",
        "intent_id": str(intent["_id"]),
        "checkout_reference": checkout_reference,
    }

    line_name = external_reference or "Order payment"
    if customer_name:
        line_name = f"{line_name} — {customer_name}"[:120]

    session_payload: Dict[str, Any] = {
        "mode": "payment",
        "customer_email": email,
        "client_reference_id": checkout_reference,
        "success_url": success_url or "https://stripe.com",
        "cancel_url": cancel_url or success_url or "https://stripe.com",
        "line_items": [
            {
                "quantity": 1,
                "price_data": {
                    "currency": cur.lower(),
                    "unit_amount": total_minor,
                    "product_data": {"name": line_name[:120]},
                },
            }
        ],
        "payment_intent_data": {
            "metadata": metadata,
            "transfer_data": {"destination": destination},
        },
        "metadata": metadata,
    }
    if fee_minor > 0:
        session_payload["payment_intent_data"]["application_fee_amount"] = fee_minor

    client = StripeClient()
    try:
        session = await client.create_checkout_session(session_payload)
    except StripeApiError as e:
        await mark_intent_failed(db, intent["_id"], str(e))
        raise

    session_id = session.get("id") or ""
    checkout_url = session.get("url") or ""
    await mark_intent_checkout_open(
        db,
        intent["_id"],
        session_id=session_id,
        checkout_url=checkout_url,
        raw=session,
    )

    return {
        "authorization_url": checkout_url,
        "checkout_url": checkout_url,
        "session_id": session_id,
        "reference": checkout_reference,
        "checkout_reference": checkout_reference,
        "intent_id": str(intent["_id"]),
        "currency": cur,
        "amount_major": amount_major,
    }


def _metadata_from_event(obj: Dict[str, Any]) -> Dict[str, str]:
    meta = obj.get("metadata") or {}
    if not isinstance(meta, dict):
        return {}
    return {str(k): str(v) for k, v in meta.items() if v is not None}


async def process_checkout_completed(
    db,
    session: Dict[str, Any],
    *,
    raw_payload: Optional[Dict] = None,
) -> Dict[str, Any]:
    payment_status = (session.get("payment_status") or "").lower()
    if payment_status not in ("paid", "no_payment_required"):
        return {"handled": False, "reason": f"payment_status={payment_status}"}

    meta = _metadata_from_event(session)
    session_id = (session.get("id") or "").strip()
    intent_doc = await find_intent_by_session_id(db, session_id)
    if not intent_doc and meta.get("checkout_reference"):
        intent_doc = await find_intent_by_reference(db, meta["checkout_reference"])

    user_id = (intent_doc or {}).get("user_id") or meta.get("crm_user_id")
    if not user_id:
        logger.warning("[Stripe] checkout.session.completed without merchant user_id")
        return {"handled": False, "reason": "unknown merchant"}

    user = await db.users.find_one(
        user_id_filter(user_id),
        {"stripe_connect_account_id": 1, "push_token": 1},
    )
    if not user or not stripe_connected(user):
        return {"handled": False, "reason": "merchant not connected"}

    currency = (session.get("currency") or (intent_doc or {}).get("currency") or "USD").upper()
    amount_total = session.get("amount_total")
    if amount_total is None:
        amount_major = float((intent_doc or {}).get("amount_major") or 0)
    else:
        amount_major = minor_to_major(int(amount_total), currency)

    payment_intent_id = session.get("payment_intent")
    if isinstance(payment_intent_id, dict):
        payment_intent_id = payment_intent_id.get("id")
    stripe_payment_id = (payment_intent_id or session_id or "").strip()

    order_id = (intent_doc or {}).get("order_id") or meta.get("order_id") or None
    if order_id == "":
        order_id = None

    ledger = await record_successful_charge(
        db,
        user_id=str(user_id),
        stripe_payment_id=stripe_payment_id,
        amount_major=amount_major,
        currency=currency,
        order_id=str(order_id) if order_id else None,
        intent_id=intent_doc["_id"] if intent_doc else None,
        session_id=session_id,
        customer_email=session.get("customer_details", {}).get("email")
        if isinstance(session.get("customer_details"), dict)
        else (session.get("customer_email") or ""),
        raw_payload=raw_payload,
    )

    if not ledger.get("inserted"):
        return {"handled": True, "duplicate": True, "user_id": user_id}

    return await _finalize_order_and_context(
        db,
        user=user,
        user_id=str(user_id),
        intent_doc=intent_doc,
        meta=meta,
        amount_major=amount_major,
        currency=currency,
        order_id=order_id,
        reference=stripe_payment_id,
        customer_email=session.get("customer_email") or "",
    )


async def process_payment_intent_succeeded(
    db,
    payment_intent: Dict[str, Any],
    *,
    raw_payload: Optional[Dict] = None,
) -> Dict[str, Any]:
    meta = _metadata_from_event(payment_intent)
    pi_id = (payment_intent.get("id") or "").strip()
    intent_doc = None
    if meta.get("checkout_reference"):
        intent_doc = await find_intent_by_reference(db, meta["checkout_reference"])

    user_id = (intent_doc or {}).get("user_id") or meta.get("crm_user_id")
    if not user_id:
        return {"handled": False, "reason": "unknown merchant"}

    user = await db.users.find_one(
        user_id_filter(user_id),
        {"stripe_connect_account_id": 1, "push_token": 1},
    )
    if not user or not stripe_connected(user):
        return {"handled": False, "reason": "merchant not connected"}

    currency = (payment_intent.get("currency") or "USD").upper()
    amount_major = minor_to_major(int(payment_intent.get("amount") or 0), currency)

    order_id = (intent_doc or {}).get("order_id") or meta.get("order_id") or None
    if order_id == "":
        order_id = None

    ledger = await record_successful_charge(
        db,
        user_id=str(user_id),
        stripe_payment_id=pi_id,
        amount_major=amount_major,
        currency=currency,
        order_id=str(order_id) if order_id else None,
        intent_id=intent_doc["_id"] if intent_doc else None,
        session_id="",
        customer_email="",
        raw_payload=raw_payload,
    )

    if not ledger.get("inserted"):
        return {"handled": True, "duplicate": True, "user_id": user_id}

    return await _finalize_order_and_context(
        db,
        user=user,
        user_id=str(user_id),
        intent_doc=intent_doc,
        meta=meta,
        amount_major=amount_major,
        currency=currency,
        order_id=order_id,
        reference=pi_id,
        customer_email="",
    )


async def process_connect_account_event(db, event: Dict[str, Any]) -> Dict[str, Any]:
    """Update merchant onboarding flags from account.updated or v2 account events."""
    event_type = (event.get("type") or "").strip()
    data = event.get("data") or {}
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        obj = data if isinstance(data, dict) else {}

    account_id = (obj.get("id") or obj.get("account") or "").strip()
    if not account_id.startswith("acct_"):
        return {"handled": False, "reason": "no account id"}

    user = await db.users.find_one(
        {"stripe_connect_account_id": account_id},
        {"_id": 1},
    )
    if not user:
        return {"handled": False, "reason": "unknown account"}

    user_id = str(user["_id"])
    if event_type.startswith("v2.core.account"):
        status = {
            "charges_enabled": bool(obj.get("charges_enabled")),
            "payouts_enabled": bool(obj.get("payouts_enabled")),
            "details_submitted": bool(obj.get("details_submitted")),
        }
        if not any(status.values()):
            try:
                synced = await sync_account_fields(db, user_id, account_id)
                status = synced
            except Exception as e:
                logger.warning("[Stripe] v2 account sync fallback: %s", e)
    else:
        status = account_status_from_stripe(obj)
        await db.users.update_one(
            user_id_filter(user_id),
            {
                "$set": {
                    "stripe_charges_enabled": status["charges_enabled"],
                    "stripe_payouts_enabled": status["payouts_enabled"],
                    "stripe_details_submitted": status["details_submitted"],
                }
            },
        )

    return {"handled": True, "user_id": user_id, **status}


async def dispatch_webhook_event(db, event: Dict[str, Any], *, raw_payload: Optional[dict] = None) -> Dict[str, Any]:
    event_type = (event.get("type") or "").strip()

    if event_type == "checkout.session.completed":
        obj = (event.get("data") or {}).get("object") or {}
        return await process_checkout_completed(db, obj, raw_payload=raw_payload)

    if event_type == "payment_intent.succeeded":
        obj = (event.get("data") or {}).get("object") or {}
        return await process_payment_intent_succeeded(db, obj, raw_payload=raw_payload)

    if event_type in ("account.updated",) or event_type.startswith("v2.core.account"):
        return await process_connect_account_event(db, event)

    return {"handled": False, "reason": f"ignored {event_type}"}


async def _finalize_order_and_context(
    db,
    *,
    user: dict,
    user_id: str,
    intent_doc: Optional[dict],
    meta: dict,
    amount_major: float,
    currency: str,
    order_id: Optional[str],
    reference: str,
    customer_email: str,
) -> Dict[str, Any]:
    order = await _find_order(
        db,
        user["_id"],
        order_id=order_id,
        amount=amount_major,
        external_ref=(intent_doc or {}).get("external_reference") or meta.get("external_reference") or "",
    )

    order_number = None
    if order:
        order_number = order.get("order_number") or ("ORD-" + str(order["_id"])[:6].upper())
        await db.orders.update_one(
            {"_id": order["_id"]},
            {
                "$set": {
                    "payment_status": "Paid",
                    "payment_method": "Stripe",
                    "payment_reference": reference,
                    "paid_at": datetime.utcnow(),
                    "paid_amount": amount_major,
                }
            },
        )

    customer_name = (intent_doc or {}).get("customer_name") or "Customer"
    phone = ""
    customer_id = (intent_doc or {}).get("customer_id")
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
        "amount": amount_major,
        "currency": currency.upper(),
        "order_number": order_number,
        "reference": reference,
        "customer_email": customer_email,
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
