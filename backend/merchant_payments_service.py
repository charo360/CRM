"""
Unified merchant payment dashboard — connections, ledgers, refunds, default provider.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from flutterwave_auth import flutterwave_connected, secret_key_from_doc as flutterwave_secret
from flutterwave_billing import (
    get_ledger_entry as flutterwave_get_ledger,
    list_recent_ledger as flutterwave_ledger,
    mark_ledger_refunded as flutterwave_mark_refunded,
)
from flutterwave_client import FlutterwaveApiError, FlutterwaveClient
from payhero_auth import payhero_connected
from payhero_billing import (
    get_mpesa_ledger_entry,
    list_recent_ledger as payhero_ledger,
    mark_mpesa_ledger_refunded,
)
from paystack_auth import paystack_connected, secret_key_from_doc as paystack_secret
from paystack_billing import (
    get_ledger_entry as paystack_get_ledger,
    list_recent_ledger as paystack_ledger,
    mark_ledger_refunded as paystack_mark_refunded,
)
from paystack_client import PaystackApiError, PaystackClient
from stripe_billing import (
    get_ledger_entry as stripe_get_ledger,
    list_recent_ledger as stripe_ledger,
    mark_ledger_refunded as stripe_mark_refunded,
)
from stripe_client import StripeApiError, StripeClient
from stripe_credentials import stripe_checkout_ready, stripe_connected

logger = logging.getLogger(__name__)

PROVIDERS = ("paystack", "stripe", "flutterwave", "payhero")


def connection_snapshot(user_doc: Optional[dict]) -> Dict[str, Any]:
    doc = user_doc or {}
    return {
        "paystack": {
            "connected": bool(paystack_connected(doc)),
            "label": doc.get("paystack_business_name") or "Paystack",
            "currency": doc.get("paystack_default_currency"),
            "subaccount_code": doc.get("paystack_subaccount_code"),
        },
        "stripe": {
            "connected": bool(stripe_connected(doc)),
            "checkout_ready": bool(stripe_checkout_ready(doc)),
            "label": doc.get("stripe_business_name") or "Stripe",
            "currency": doc.get("stripe_default_currency"),
        },
        "flutterwave": {
            "connected": bool(flutterwave_connected(doc)),
            "label": doc.get("flutterwave_business_name") or "Flutterwave",
            "currency": doc.get("flutterwave_default_currency"),
            "subaccount_id": doc.get("flutterwave_subaccount_id"),
        },
        "payhero": {
            "connected": bool(payhero_connected(doc)),
            "label": doc.get("payhero_username") or "PayHero",
            "channel_id": doc.get("payhero_channel_id"),
        },
    }


def connected_provider_keys(user_doc: Optional[dict]) -> List[str]:
    snap = connection_snapshot(user_doc)
    return [p for p in PROVIDERS if snap.get(p, {}).get("connected")]


def connected_connections_only(user_doc: Optional[dict]) -> Dict[str, Any]:
    snap = connection_snapshot(user_doc)
    return {k: v for k, v in snap.items() if v.get("connected")}


async def list_unified_transactions(
    db,
    user_id: str,
    *,
    user_doc: Optional[dict] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    per = max(10, min(limit, 100))
    chunk = per
    active = set(connected_provider_keys(user_doc))

    rows: List[Dict[str, Any]] = []

    if "paystack" in active:
        for entry in await paystack_ledger(db, user_id, chunk):
            rows.append(
                {
                    "id": entry.get("id"),
                    "provider": "paystack",
                    "reference": entry.get("paystack_reference") or "",
                    "amount_major": entry.get("amount_major"),
                    "currency": entry.get("currency") or "NGN",
                    "status": entry.get("status") or "success",
                    "order_id": entry.get("order_id"),
                    "customer_email": entry.get("customer_email") or "",
                    "channel": entry.get("channel") or "",
                    "created_at": entry.get("created_at"),
                    "refundable": (entry.get("status") or "success") == "success",
                }
            )

    if "stripe" in active:
        for entry in await stripe_ledger(db, user_id, chunk):
            rows.append(
                {
                    "id": entry.get("id"),
                    "provider": "stripe",
                    "reference": entry.get("stripe_payment_id") or "",
                    "amount_major": entry.get("amount_major"),
                    "currency": entry.get("currency") or "USD",
                    "status": entry.get("status") or "success",
                    "order_id": entry.get("order_id"),
                    "customer_email": entry.get("customer_email") or "",
                    "channel": "card",
                    "created_at": entry.get("created_at"),
                    "refundable": (entry.get("status") or "success") == "success",
                }
            )

    if "flutterwave" in active:
        for entry in await flutterwave_ledger(db, user_id, chunk):
            rows.append(
                {
                    "id": entry.get("id"),
                    "provider": "flutterwave",
                    "reference": entry.get("flutterwave_tx_ref") or "",
                    "amount_major": entry.get("amount_major"),
                    "currency": entry.get("currency") or "NGN",
                    "status": entry.get("status") or "success",
                    "order_id": entry.get("order_id"),
                    "customer_email": entry.get("customer_email") or "",
                    "channel": entry.get("channel") or "",
                    "created_at": entry.get("created_at"),
                    "refundable": (entry.get("status") or "success") == "success",
                }
            )

    if "payhero" in active:
        for entry in await payhero_ledger(db, user_id, chunk):
            if entry.get("kind") != "mpesa_payment":
                continue
            st = entry.get("status") or "accrued"
            rows.append(
                {
                    "id": entry.get("id"),
                    "provider": "payhero",
                    "reference": entry.get("provider_ref") or entry.get("external_reference") or "",
                    "amount_major": entry.get("gross_kes"),
                    "currency": "KES",
                    "status": "refunded" if st == "refunded" else "success",
                    "order_id": entry.get("order_id"),
                    "customer_email": "",
                    "channel": entry.get("phone") or "M-Pesa",
                    "created_at": entry.get("created_at"),
                    "refundable": st == "accrued",
                    "refund_mode": "manual",
                }
            )

    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[:per]


async def _mark_order_refunded(db, user_id, order_id: Optional[str]) -> None:
    if not order_id:
        return
    filt: Dict[str, Any] = {"user_id": user_id}
    try:
        filt["_id"] = ObjectId(order_id)
    except Exception:
        filt["_id"] = order_id
    await db.orders.update_one(
        filt,
        {
            "$set": {
                "payment_status": "Refunded",
                "refunded_at": datetime.utcnow(),
            }
        },
    )


async def issue_full_refund(
    db,
    user_doc: dict,
    *,
    user_id: str,
    provider: str,
    ledger_id: str,
) -> Dict[str, Any]:
    prov = (provider or "").strip().lower()
    if prov not in PROVIDERS:
        raise ValueError("Invalid payment provider")

    if prov == "paystack":
        if not paystack_connected(user_doc):
            raise ValueError("Paystack is not connected")
        entry = await paystack_get_ledger(db, user_id, ledger_id)
        if not entry or entry.get("status") != "success":
            raise ValueError("Payment not found or already refunded")
        ref = (entry.get("paystack_reference") or "").strip()
        secret = paystack_secret(user_doc)
        if not secret or not ref:
            raise ValueError("Cannot refund this payment")
        client = PaystackClient(secret)
        try:
            result = await client.create_refund(transaction=ref)
        except PaystackApiError as e:
            raise ValueError(str(e)) from e
        refund_id = str(result.get("id") or result.get("transaction") or "")
        await paystack_mark_refunded(
            db, user_id=user_id, ledger_id=ledger_id, provider_refund_id=refund_id
        )
        await _mark_order_refunded(db, user_id, entry.get("order_id"))
        return {"status": "refunded", "provider": prov, "provider_refund_id": refund_id}

    if prov == "stripe":
        if not stripe_checkout_ready(user_doc):
            raise ValueError("Stripe checkout is not ready")
        entry = await stripe_get_ledger(db, user_id, ledger_id)
        if not entry or entry.get("status") != "success":
            raise ValueError("Payment not found or already refunded")
        pi_id = (entry.get("stripe_payment_id") or "").strip()
        if not pi_id.startswith("pi_"):
            raise ValueError("Missing Stripe payment intent for refund")
        client = StripeClient()
        try:
            result = await client.create_refund(payment_intent_id=pi_id)
        except StripeApiError as e:
            raise ValueError(str(e)) from e
        refund_id = str(result.get("id") or "")
        await stripe_mark_refunded(
            db, user_id=user_id, ledger_id=ledger_id, provider_refund_id=refund_id
        )
        await _mark_order_refunded(db, user_id, entry.get("order_id"))
        return {"status": "refunded", "provider": prov, "provider_refund_id": refund_id}

    if prov == "flutterwave":
        if not flutterwave_connected(user_doc):
            raise ValueError("Flutterwave is not connected")
        entry = await flutterwave_get_ledger(db, user_id, ledger_id)
        if not entry or entry.get("status") != "success":
            raise ValueError("Payment not found or already refunded")
        tx_ref = (entry.get("flutterwave_tx_ref") or "").strip()
        secret = flutterwave_secret(user_doc)
        if not secret or not tx_ref:
            raise ValueError("Cannot refund this payment")
        client = FlutterwaveClient(secret)
        try:
            verified = await client.verify_by_reference(tx_ref)
            flw_id = verified.get("id")
            if not flw_id:
                raise ValueError("Could not resolve Flutterwave transaction id")
            result = await client.create_refund(transaction_id=int(flw_id))
        except FlutterwaveApiError as e:
            raise ValueError(str(e)) from e
        refund_id = str(result.get("id") or result.get("flw_ref") or "")
        await flutterwave_mark_refunded(
            db, user_id=user_id, ledger_id=ledger_id, provider_refund_id=refund_id
        )
        await _mark_order_refunded(db, user_id, entry.get("order_id"))
        return {"status": "refunded", "provider": prov, "provider_refund_id": refund_id}

    if prov == "payhero":
        if not payhero_connected(user_doc):
            raise ValueError("PayHero is not connected")
        entry = await get_mpesa_ledger_entry(db, user_id, ledger_id)
        if not entry or entry.get("status") != "accrued":
            raise ValueError("Payment not found or already refunded")
        note = (
            "Marked refunded in Zilo. Send M-Pesa to the customer from your PayHero balance "
            "(funds may already be in your linked bank account)."
        )
        await mark_mpesa_ledger_refunded(db, user_id=user_id, ledger_id=ledger_id, note=note)
        await _mark_order_refunded(db, user_id, entry.get("order_id"))
        return {
            "status": "refunded",
            "provider": prov,
            "manual_followup": note,
        }

    raise ValueError("Unsupported provider")
