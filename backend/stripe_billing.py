"""
Stripe Connect payment intents and transaction ledger (idempotent by session / PI id).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

INTENTS = "stripe_payment_intents"
LEDGER = "stripe_transactions"


async def ensure_stripe_indexes(db) -> None:
    await db[INTENTS].create_index([("user_id", 1), ("created_at", -1)])
    await db[INTENTS].create_index([("user_id", 1), ("status", 1)])
    await db[INTENTS].create_index("checkout_reference", unique=True, sparse=True)
    await db[INTENTS].create_index("stripe_session_id", sparse=True)
    await db[LEDGER].create_index([("user_id", 1), ("created_at", -1)])
    await db[LEDGER].create_index(
        "stripe_payment_id",
        unique=True,
        sparse=True,
        name="stripe_payment_id_unique",
    )


async def create_payment_intent(
    db,
    *,
    user_id: str,
    amount_major: float,
    currency: str,
    email: str,
    checkout_reference: str,
    external_reference: str = "",
    order_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    customer_name: str = "",
    success_url: str = "",
    cancel_url: str = "",
) -> Dict[str, Any]:
    doc = {
        "user_id": user_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "amount_major": float(amount_major),
        "currency": currency.upper(),
        "email": email,
        "checkout_reference": checkout_reference,
        "external_reference": external_reference,
        "customer_name": customer_name,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = await db[INTENTS].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def mark_intent_checkout_open(
    db,
    intent_id: Any,
    *,
    session_id: str,
    checkout_url: str,
    raw: Optional[dict] = None,
) -> None:
    await db[INTENTS].update_one(
        {"_id": intent_id},
        {
            "$set": {
                "status": "checkout_open",
                "stripe_session_id": session_id,
                "checkout_url": checkout_url,
                "stripe_session": raw,
                "updated_at": datetime.utcnow(),
            }
        },
    )


async def mark_intent_failed(db, intent_id: Any, error: str) -> None:
    await db[INTENTS].update_one(
        {"_id": intent_id},
        {"$set": {"status": "failed", "error": error[:500], "updated_at": datetime.utcnow()}},
    )


async def record_successful_charge(
    db,
    *,
    user_id: str,
    stripe_payment_id: str,
    amount_major: float,
    currency: str,
    order_id: Optional[str] = None,
    intent_id: Optional[Any] = None,
    session_id: str = "",
    customer_email: str = "",
    raw_payload: Optional[dict] = None,
) -> Dict[str, Any]:
    ref = (stripe_payment_id or "").strip()
    if not ref:
        return {"inserted": False, "reason": "missing payment id"}

    existing = await db[LEDGER].find_one({"stripe_payment_id": ref})
    if existing:
        return {"inserted": False, "ledger_id": str(existing["_id"])}

    doc = {
        "user_id": user_id,
        "stripe_payment_id": ref,
        "stripe_session_id": session_id or None,
        "amount_major": float(amount_major),
        "currency": currency.upper(),
        "customer_email": customer_email,
        "order_id": order_id,
        "intent_id": str(intent_id) if intent_id else None,
        "status": "success",
        "raw_payload": raw_payload,
        "created_at": datetime.utcnow(),
    }
    try:
        res = await db[LEDGER].insert_one(doc)
    except Exception as e:
        logger.warning("[Stripe ledger] insert: %s", e)
        existing = await db[LEDGER].find_one({"stripe_payment_id": ref})
        if existing:
            return {"inserted": False, "ledger_id": str(existing["_id"])}
        raise

    if intent_id:
        await db[INTENTS].update_one(
            {"_id": intent_id},
            {
                "$set": {
                    "status": "succeeded",
                    "stripe_payment_id": ref,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
    elif session_id:
        await db[INTENTS].update_one(
            {"stripe_session_id": session_id, "user_id": user_id},
            {"$set": {"status": "succeeded", "stripe_payment_id": ref, "updated_at": datetime.utcnow()}},
        )

    return {"inserted": True, "ledger_id": str(res.inserted_id)}


async def usage_summary(db, user_id: str) -> Dict[str, Any]:
    pipeline = [
        {"$match": {"user_id": user_id, "status": "success"}},
        {
            "$group": {
                "_id": "$currency",
                "count": {"$sum": 1},
                "volume_major": {"$sum": "$amount_major"},
            }
        },
    ]
    rows = await db[LEDGER].aggregate(pipeline).to_list(20)
    by_currency = {r["_id"]: r for r in rows}
    total_count = sum(r.get("count", 0) for r in rows)
    return {
        "payments": {
            "count": total_count,
            "by_currency": {
                k: {"count": v.get("count", 0), "volume_major": v.get("volume_major", 0)}
                for k, v in by_currency.items()
            },
        }
    }


async def list_recent_ledger(db, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    cursor = db[LEDGER].find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    out = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        if doc.get("created_at"):
            doc["created_at"] = doc["created_at"].isoformat() + "Z"
        out.append(doc)
    return out


async def mark_ledger_refunded(
    db,
    *,
    user_id: str,
    ledger_id: str,
    provider_refund_id: str = "",
) -> bool:
    from bson import ObjectId

    try:
        oid = ObjectId(ledger_id)
    except Exception:
        return False
    res = await db[LEDGER].update_one(
        {"_id": oid, "user_id": user_id, "status": "success"},
        {
            "$set": {
                "status": "refunded",
                "refunded_at": datetime.utcnow(),
                "provider_refund_id": provider_refund_id or None,
            }
        },
    )
    return res.modified_count > 0


async def get_ledger_entry(db, user_id: str, ledger_id: str) -> Optional[Dict[str, Any]]:
    from bson import ObjectId

    try:
        oid = ObjectId(ledger_id)
    except Exception:
        return None
    return await db[LEDGER].find_one({"_id": oid, "user_id": user_id})


async def find_intent_by_reference(db, checkout_reference: str) -> Optional[Dict[str, Any]]:
    ref = (checkout_reference or "").strip()
    if not ref:
        return None
    return await db[INTENTS].find_one({"checkout_reference": ref})


async def find_intent_by_session_id(db, session_id: str) -> Optional[Dict[str, Any]]:
    sid = (session_id or "").strip()
    if not sid:
        return None
    return await db[INTENTS].find_one({"stripe_session_id": sid})
