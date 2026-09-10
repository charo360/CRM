"""
Plan Enforcement Module for Zilo CRM
Tracks and enforces monthly usage limits for Messages and Blogposts
across standard regional subscriptions and Shopify partner plans.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, Any
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def get_start_of_month() -> datetime:
    """Return the start of the current UTC calendar month."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)


async def get_monthly_message_count(db, user_id: str) -> int:
    """
    Calculate total outgoing messages (WhatsApp + Emails) sent in the current calendar month.
    """
    start = get_start_of_month()

    # Count WhatsApp messages (direction="outgoing"). A reply on a paid model
    # is worth several plan messages, so sum the stored weight rather than the
    # documents; sends from before weighting carry none and count as one.
    wa_count = 0
    async for row in db.messages.aggregate([
        {"$match": {"user_id": user_id, "direction": "outgoing",
                    # A send the provider rejected must not be charged for.
                    # count_monthly_outbound has always excluded these; this
                    # counter did not, so the same month billed differently
                    # depending on which one was asked.
                    "delivery_status": {"$ne": "failed"},
                    "created_at": {"$gte": start}}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$message_cost", 1]}}}},
    ]):
        wa_count = int(row.get("total") or 0)

    # Count Outgoing emails (is_outgoing=True)
    # Support both datetime and ISO string fallback checks
    email_count = await db.email_messages.count_documents({
        "user_id": user_id,
        "is_outgoing": True,
        "date": {"$gte": start}
    })

    # Writing with AI is charged as well, from its own ledger rather than
    # db.messages -- a draft is not a send. entitlements.count_monthly_outbound
    # adds the identical figure; these two counters answering differently is a
    # bug that has already happened once.
    from ai_draft_billing import monthly_draft_cost
    draft_cost = await monthly_draft_cost(db, user_id, start)

    total = wa_count + email_count + draft_cost
    logger.info(
        f"[PlanEnforcement] User {user_id} monthly messages: WhatsApp={wa_count}, "
        f"Email={email_count}, AI drafts={draft_cost}, Total={total}"
    )
    return total


async def get_monthly_blogpost_count(db, user_id: str) -> int:
    """
    Count total published blogposts in the current calendar month.
    """
    start = get_start_of_month()

    post_count = await db.seo_blog_posts.count_documents({
        "user_id": user_id,
        "status": "published",
        "published_at": {"$gte": start}
    })

    logger.info(f"[PlanEnforcement] User {user_id} monthly published blogposts: {post_count}")
    return post_count


async def get_active_plan_limits(db, user_id: str) -> Dict[str, Any]:
    """
    Identify user subscription status and return corresponding plan limits.
    """
    user = await db.users.find_one({"_id": user_id})
    if not user:
        return {"messages": 100, "blogposts": 1, "plan_name": "Free"}

    is_shopify = user.get("auth_provider") == "shopify" or "shopify_plan" in user
    plan_id = "free"

    if is_shopify:
        billing_status = user.get("shopify_billing_status")
        if billing_status == "active":
            plan_id = user.get("shopify_plan", "starter")
        else:
            plan_id = "free"
    else:
        if user.get("subscription_active"):
            plan_id = user.get("subscription_plan", "starter")
        else:
            plan_id = "free"

    plan_id = str(plan_id).lower().strip()

    # Shopify Specific Limits (from shopify_billing.py)
    if is_shopify:
        if plan_id == "starter":
            return {"messages": 5000, "blogposts": 2, "plan_name": "Shopify Starter"}
        elif plan_id in ("growth", "standard"):
            return {"messages": 10000, "blogposts": 5, "plan_name": "Shopify Growth"}
        elif plan_id in ("pro", "premium"):
            return {"messages": 25000, "blogposts": float("inf"), "plan_name": "Shopify Pro"}
    
    # Standard Regional / IAP Limits
    else:
        if plan_id == "starter":
            return {"messages": 2500, "blogposts": 2, "plan_name": "Starter"}
        elif plan_id in ("standard", "growth"):
            return {"messages": 5000, "blogposts": 5, "plan_name": "Growth"}
        elif plan_id in ("pro", "premium"):
            return {"messages": 10000, "blogposts": float("inf"), "plan_name": "Pro"}

    # Fallback to Free Trial / Inactive Subscription tier
    return {"messages": 100, "blogposts": 1, "plan_name": "Free Trial"}


async def enforce_message_limit(db, user_id: str, additional_messages: int = 1) -> None:
    """
    Verify if the user can send more messages. Raises HTTPException 403 if limit is exceeded.
    """
    from entitlements import build_entitlements

    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Business account not found.")
    ent = await build_entitlements(db, user)
    if not ent.get("dashboard_access"):
        raise HTTPException(status_code=402, detail="Choose a plan or start a free trial to send messages.")

    usage = ent.get("usage") or {}
    remaining = int(usage.get("outbound_messages_remaining") or 0)
    if additional_messages > remaining:
        raise HTTPException(
            status_code=403,
            detail=(
                "Your included monthly messages and extra messages are used. "
                "Buy more messages or upgrade your subscription to continue."
            )
        )


async def enforce_blogpost_limit(db, user_id: str) -> None:
    """
    Verify if the user can publish more blogposts. Raises HTTPException 403 if limit is exceeded.
    """
    limits = await get_active_plan_limits(db, user_id)
    current = await get_monthly_blogpost_count(db, user_id)
    allowed = limits["blogposts"]

    if current >= allowed:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Plan limit reached. You have published {current} of {allowed} monthly blogposts "
                f"on your {limits['plan_name']} plan. Please upgrade your subscription to publish more."
            )
        )
