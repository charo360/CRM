"""
PayHero usage ledger — idempotent fee accrual for M-Pesa, SMS, and WhatsApp.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from payhero_rates import (
    RATE_CARD_VERSION,
    channel_message_fee_kes,
    mpesa_transaction_fee_kes,
)

logger = logging.getLogger(__name__)

COLLECTION = "payhero_usage_ledger"
INTENTS = "payhero_payment_intents"


async def ensure_payhero_indexes(db) -> None:
    await db[INTENTS].create_index([("user_id", 1), ("created_at", -1)])
    await db[INTENTS].create_index([("user_id", 1), ("status", 1)])
    await db[INTENTS].create_index("external_reference")
    await db[COLLECTION].create_index([("user_id", 1), ("created_at", -1)])
    await db[COLLECTION].create_index(
        "provider_ref",
        unique=True,
        sparse=True,
        name="payhero_provider_ref_unique",
    )
    await db[COLLECTION].create_index(
        "idempotency_key",
        unique=True,
        sparse=True,
        name="payhero_idempotency_unique",
    )


async def create_payment_intent(
    db,
    *,
    user_id: str,
    amount: float,
    phone: str,
    external_reference: str,
    order_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    customer_name: str = "",
    channel_id: Optional[int] = None,
) -> Dict[str, Any]:
    fee = mpesa_transaction_fee_kes(amount)
    doc = {
        "user_id": user_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "amount": float(amount),
        "phone": phone,
        "external_reference": external_reference,
        "customer_name": customer_name,
        "channel_id": channel_id,
        "status": "pending",
        "estimated_fee_kes": fee,
        "rate_card_version": RATE_CARD_VERSION,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = await db[INTENTS].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def mark_intent_stk_sent(db, intent_id, payhero_response: dict) -> None:
    await db[INTENTS].update_one(
        {"_id": intent_id},
        {
            "$set": {
                "status": "stk_sent",
                "payhero_response": payhero_response,
                "updated_at": datetime.utcnow(),
            }
        },
    )


async def mark_intent_failed(db, intent_id, error: str) -> None:
    await db[INTENTS].update_one(
        {"_id": intent_id},
        {"$set": {"status": "failed", "error": error[:500], "updated_at": datetime.utcnow()}},
    )


async def record_mpesa_payment_success(
    db,
    *,
    user_id: str,
    gross_kes: float,
    provider_ref: str,
    order_id: Optional[str] = None,
    intent_id: Optional[Any] = None,
    external_reference: str = "",
    phone: str = "",
    raw_payload: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Idempotent ledger entry for a successful M-Pesa payment.
    Returns {inserted: bool, ledger_id, fee_kes}.
    """
    provider_ref = (provider_ref or "").strip()
    idempotency_key = f"mpesa:{provider_ref}" if provider_ref else None
    if not idempotency_key:
        idempotency_key = f"mpesa:{user_id}:{external_reference}:{int(gross_kes)}:{phone}"

    if provider_ref:
        existing = await db[COLLECTION].find_one(
            {
                "$or": [
                    {"provider_ref": provider_ref},
                    {"idempotency_key": idempotency_key},
                ]
            }
        )
    else:
        existing = await db[COLLECTION].find_one({"idempotency_key": idempotency_key})
    if existing:
        return {
            "inserted": False,
            "ledger_id": str(existing["_id"]),
            "fee_kes": existing.get("payhero_fee_kes", 0),
        }

    fee = mpesa_transaction_fee_kes(gross_kes)
    doc = {
        "user_id": user_id,
        "kind": "mpesa_payment",
        "gross_kes": float(gross_kes),
        "payhero_fee_kes": fee,
        "merchant_receives_kes": float(gross_kes),
        "provider_ref": provider_ref or None,
        "idempotency_key": idempotency_key,
        "order_id": order_id,
        "intent_id": str(intent_id) if intent_id else None,
        "external_reference": external_reference,
        "phone": phone,
        "rate_card_version": RATE_CARD_VERSION,
        "status": "accrued",
        "raw_payload": raw_payload,
        "created_at": datetime.utcnow(),
    }
    try:
        res = await db[COLLECTION].insert_one(doc)
    except Exception as e:
        logger.warning("[PayHero ledger] insert conflict: %s", e)
        existing = await db[COLLECTION].find_one({"idempotency_key": idempotency_key})
        if existing:
            return {
                "inserted": False,
                "ledger_id": str(existing["_id"]),
                "fee_kes": existing.get("payhero_fee_kes", 0),
            }
        raise

    if intent_id:
        await db[INTENTS].update_one(
            {"_id": intent_id},
            {
                "$set": {
                    "status": "succeeded",
                    "provider_ref": provider_ref,
                    "actual_fee_kes": fee,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
    elif provider_ref:
        await db[INTENTS].update_one(
            {"user_id": user_id, "provider_ref": provider_ref},
            {"$set": {"status": "succeeded", "actual_fee_kes": fee, "updated_at": datetime.utcnow()}},
        )

    return {"inserted": True, "ledger_id": str(res.inserted_id), "fee_kes": fee}


async def record_channel_message(
    db,
    *,
    user_id: str,
    channel: str,
    count: int = 1,
    message_id: Optional[str] = None,
) -> None:
    """Accrue PayHero SMS / WhatsApp channel costs (per message)."""
    if channel not in ("sms", "whatsapp"):
        return
    unit = float(channel_message_fee_kes(channel))  # type: ignore[arg-type]
    fee_total = round(unit * max(1, count), 2)
    idem = f"{channel}:{message_id}" if message_id else None
    if idem:
        if await db[COLLECTION].find_one({"idempotency_key": idem}):
            return
    doc = {
        "user_id": user_id,
        "kind": channel,
        "message_count": count,
        "payhero_fee_kes": fee_total,
        "unit_fee_kes": unit,
        "rate_card_version": RATE_CARD_VERSION,
        "status": "accrued",
        "idempotency_key": idem,
        "created_at": datetime.utcnow(),
    }
    try:
        await db[COLLECTION].insert_one(doc)
    except Exception:
        pass


async def usage_summary(
    db,
    user_id: str,
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> Dict[str, Any]:
    match: Dict[str, Any] = {"user_id": user_id}
    if since or until:
        match["created_at"] = {}
        if since:
            match["created_at"]["$gte"] = since
        if until:
            match["created_at"]["$lte"] = until

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$kind",
                "count": {"$sum": 1},
                "fees_kes": {"$sum": "$payhero_fee_kes"},
                "gross_kes": {"$sum": {"$ifNull": ["$gross_kes", 0]}},
            }
        },
    ]
    rows = await db[COLLECTION].aggregate(pipeline).to_list(20)
    by_kind = {r["_id"]: r for r in rows}
    mpesa = by_kind.get("mpesa_payment", {})
    sms = by_kind.get("sms", {})
    wa = by_kind.get("whatsapp", {})

    total_fees = sum(r.get("fees_kes", 0) or 0 for r in rows)

    return {
        "rate_card_version": RATE_CARD_VERSION,
        "currency": "KES",
        "mpesa_payments": {
            "count": mpesa.get("count", 0),
            "gross_collected_kes": mpesa.get("gross_kes", 0),
            "estimated_payhero_fees_kes": mpesa.get("fees_kes", 0),
        },
        "sms": {"messages": sms.get("count", 0), "fees_kes": sms.get("fees_kes", 0)},
        "whatsapp": {"messages": wa.get("count", 0), "fees_kes": wa.get("fees_kes", 0)},
        "total_estimated_fees_kes": total_fees,
    }


async def list_recent_ledger(
    db, user_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    cursor = db[COLLECTION].find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    out = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        if doc.get("created_at"):
            doc["created_at"] = doc["created_at"].isoformat() + "Z"
        out.append(doc)
    return out
