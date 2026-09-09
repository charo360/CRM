"""What a business has earned, and how much of it has actually reached them.

Two different numbers, routinely confused:

  * **Received** — what customers paid. Our own ledger records this from the
    webhook, so it is always available and always ours.
  * **Settled** — what Paystack has actually paid out to the business's bank
    or M-Pesa. Only Paystack knows this, and it lags the first number by a
    settlement cycle.

The gap between them is money the business has earned and cannot yet spend.
Showing only "received" invites "where is my money"; inventing a split
would be worse. When Paystack cannot tell us, we say so rather than guess.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _major(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _received(db, user_id: str) -> Dict[str, Any]:
    """Successful charges from our own ledger, grouped by currency."""
    from paystack_billing import LEDGER

    totals: Dict[str, Dict[str, Any]] = {}
    cursor = db[LEDGER].aggregate([
        {"$match": {"user_id": user_id, "status": "success"}},
        {"$group": {
            "_id": "$currency",
            "count": {"$sum": 1},
            "amount": {"$sum": "$amount_major"},
        }},
    ])
    async for row in cursor:
        currency = row.get("_id") or ""
        totals[currency] = {"count": row.get("count", 0), "amount": _major(row.get("amount"))}
    return totals


async def _settled(user: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """What Paystack says it has paid out, or None when it will not say.

    None is meaningful and must not be turned into zero: "nothing settled
    yet" and "we could not ask" look identical to a worried owner, and only
    one of them is a reason to contact support.
    """
    subaccount = (user or {}).get("paystack_subaccount_code") or ""
    try:
        from paystack_auth import secret_key_from_doc
        from paystack_client import PaystackClient

        secret = secret_key_from_doc(user)
        if not secret:
            return None
        rows = await PaystackClient(secret).list_settlements(subaccount=subaccount)
    except Exception as exc:
        logger.warning("[earnings] settlements unavailable: %s", exc)
        return None

    out: Dict[str, float] = {}
    for row in rows:
        # Paystack settlement statuses are success, processing, pending and
        # failed. Only success has actually reached the business; the rest
        # are still in flight and belong in "still held".
        if str(row.get("status") or "").lower() != "success":
            continue
        currency = row.get("currency") or ""
        # effective_amount is what lands in the account — total_amount before
        # total_fees is deducted. Showing the gross would tell a business it
        # had been paid more than its bank will ever show.
        amount = row.get("effective_amount")
        if amount is None:
            amount = row.get("total_amount")
        # Paystack reports money in subunits.
        out[currency] = out.get(currency, 0.0) + _major(amount) / 100.0
    return out


async def earnings_summary(db, user: Dict[str, Any]) -> Dict[str, Any]:
    """Received, settled and still-held totals per currency."""
    user_id = str(user["_id"])
    received = await _received(db, user_id)
    settled = await _settled(user)

    currencies = sorted(set(received) | set(settled or {}))
    rows: List[Dict[str, Any]] = []
    for currency in currencies:
        got = received.get(currency, {"count": 0, "amount": 0.0})
        line: Dict[str, Any] = {
            "currency": currency,
            "payments": got["count"],
            "received": round(got["amount"], 2),
        }
        if settled is not None:
            paid_out = round(settled.get(currency, 0.0), 2)
            line["settled"] = paid_out
            # Never show a negative "still held": a settlement can cover a
            # charge our webhook missed, and a minus sign here reads as a
            # bug or a debt.
            line["held"] = max(0.0, round(line["received"] - paid_out, 2))
        rows.append(line)

    return {
        "connected": bool((user or {}).get("paystack_subaccount_code") or (user or {}).get("paystack_secret_key")),
        "settlement_data": settled is not None,
        "currencies": rows,
    }


async def recent_transactions(db, user: Dict[str, Any], limit: int = 30) -> List[Dict[str, Any]]:
    """The payments behind those totals, newest first."""
    from paystack_billing import LEDGER

    user_id = str(user["_id"])
    out: List[Dict[str, Any]] = []
    cursor = db[LEDGER].find(
        {"user_id": user_id},
        {"paystack_reference": 1, "amount_major": 1, "currency": 1, "status": 1,
         "channel": 1, "customer_email": 1, "order_id": 1, "created_at": 1, "refunded": 1},
    ).sort("created_at", -1).limit(max(1, min(limit, 100)))
    async for row in cursor:
        out.append({
            "reference": row.get("paystack_reference") or "",
            "amount": _major(row.get("amount_major")),
            "currency": row.get("currency") or "",
            "status": "refunded" if row.get("refunded") else (row.get("status") or ""),
            "channel": row.get("channel") or "",
            "customer": row.get("customer_email") or "",
            "order_id": row.get("order_id") or "",
            "created_at": row.get("created_at"),
        })
    return out
