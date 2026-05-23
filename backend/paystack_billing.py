"""
Paystack payment intents and transaction ledger (idempotent by reference).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

INTENTS = "paystack_payment_intents"
LEDGER = "paystack_transactions"


async def ensure_paystack_indexes(db) -> None:
    await db[INTENTS].create_index([("user_id", 1), ("created_at", -1)])
    await db[INTENTS].create_index([("user_id", 1), ("status", 1)])
    await db[INTENTS].create_index("reference", unique=True, sparse=True)
    await db[INTENTS].create_index("external_reference")
    await db[LEDGER].create_index([("user_id", 1), ("created_at", -1)])
    await db[LEDGER].create_index(
        "paystack_reference",
        unique=True,
        sparse=True,
        name="paystack_reference_unique",
    )


async def create_payment_intent(
    db,
    *,
    user_id: str,
    amount_major: float,
    currency: str,
    email: str,
    reference: str,
    external_reference: str = "",
    order_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    customer_name: str = "",
    callback_url: str = "",
) -> Dict[str, Any]:
    doc = {
        "user_id": user_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "amount_major": float(amount_major),
        "currency": currency.upper(),
        "email": email,
        "reference": reference,
        "external_reference": external_reference,
        "customer_name": customer_name,
        "callback_url": callback_url,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = await db[INTENTS].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def mark_intent_initialized(
    db,
    intent_id: Any,
    *,
    authorization_url: str,
    access_code: str,
    paystack_reference: str,
    raw: Optional[dict] = None,
) -> None:
    await db[INTENTS].update_one(
        {"_id": intent_id},
        {
            "$set": {
                "status": "checkout_open",
                "authorization_url": authorization_url,
                "access_code": access_code,
                "paystack_reference": paystack_reference,
                "paystack_init": raw,
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
    paystack_reference: str,
    amount_major: float,
    currency: str,
    order_id: Optional[str] = None,
    intent_id: Optional[Any] = None,
    channel: str = "",
    customer_email: str = "",
    raw_payload: Optional[dict] = None,
) -> Dict[str, Any]:
    ref = (paystack_reference or "").strip()
    if not ref:
        return {"inserted": False, "reason": "missing reference"}

    existing = await db[LEDGER].find_one({"paystack_reference": ref})
    if existing:
        return {"inserted": False, "ledger_id": str(existing["_id"])}

    doc = {
        "user_id": user_id,
        "paystack_reference": ref,
        "amount_major": float(amount_major),
        "currency": currency.upper(),
        "channel": channel,
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
        logger.warning("[Paystack ledger] insert: %s", e)
        existing = await db[LEDGER].find_one({"paystack_reference": ref})
        if existing:
            return {"inserted": False, "ledger_id": str(existing["_id"])}
        raise

    if intent_id:
        await db[INTENTS].update_one(
            {"_id": intent_id},
            {
                "$set": {
                    "status": "succeeded",
                    "paystack_reference": ref,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
    else:
        await db[INTENTS].update_one(
            {"reference": ref, "user_id": user_id},
            {"$set": {"status": "succeeded", "updated_at": datetime.utcnow()}},
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
                k: {
                    "count": v.get("count", 0),
                    "volume_major": v.get("volume_major", 0),
                }
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


async def find_intent_by_reference(db, reference: str) -> Optional[Dict[str, Any]]:
    ref = (reference or "").strip()
    if not ref:
        return None
    return await db[INTENTS].find_one(
        {
            "$or": [
                {"reference": ref},
                {"paystack_reference": ref},
            ]
        }
    )
