"""Charging for AI drafts that are not themselves a message.

Everywhere else, usage is counted by reading db.messages: each outgoing send
carries a message_cost, and the month's allowance is the sum of those weights.
That works because the thing being charged for is the thing being stored.

A broadcast draft is not. One press of "write with AI" produces one piece of
text that may go to four hundred people, or to nobody. Charging it through
db.messages would mean inventing a message that was never sent, which would
then appear in delivery statistics, exports and anything else that counts what
the business has sent. So the charges live in their own collection, and both
usage counters add them in.

Both counters. entitlements.count_monthly_outbound and
plan_enforcement.get_monthly_message_count are separate implementations of the
same question, and they have disagreed before -- one excluded provider-rejected
sends and the other did not, so the same month billed differently depending on
which one was asked. A new source of usage that only one of them knows about
would be that bug again.
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION = "ai_draft_charges"


async def monthly_draft_cost(db, business_id, since: datetime) -> int:
    """What this business has spent on AI drafts since `since`.

    The caller passes its own month boundary rather than computing one here:
    the two counters build that boundary differently (one naive, one
    timezone-aware) and this must agree with whichever is asking.
    """
    try:
        cursor = db[COLLECTION].aggregate([
            {"$match": {"user_id": business_id, "created_at": {"$gte": since}}},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$cost", 1]}}}},
        ])
        async for row in cursor:
            return int(row.get("total") or 0)
    except Exception as exc:
        # Never let a billing read break the feature it is measuring.
        logger.warning(f"[AIDraftBilling] could not read draft charges: {exc}")
    return 0


async def charge_draft(
    db,
    business_id,
    model_pref: Optional[str] = None,
    kind: str = "broadcast",
    detail: Optional[str] = None,
) -> int:
    """Record one AI draft against the allowance. Returns what it cost.

    Charged at the rate of the model the owner picked, the same weight an
    auto-reply on that model costs -- writing with Claude is worth ten plain
    messages because that is what it costs to produce.

    Called only after the model has actually answered. A draft that failed to
    generate is not something to bill for.
    """
    from ai_service import model_message_cost

    cost = model_message_cost(model_pref)
    try:
        await db[COLLECTION].insert_one({
            "user_id": business_id,
            "kind": kind,
            "model": model_pref or "standard",
            "cost": cost,
            "detail": (detail or "")[:200],
            "created_at": datetime.utcnow(),
        })
    except Exception as exc:
        # If the ledger write fails the owner keeps their draft. Losing a
        # charge is better than losing the work they asked for.
        logger.warning(f"[AIDraftBilling] could not record draft charge: {exc}")
        return 0
    return cost
