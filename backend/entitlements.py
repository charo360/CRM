"""
Single source of truth for SaaS plan tiers, trials, and feature entitlements.
Plan ids: starter, standard (Growth), pro. Legacy alias: growth -> standard.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypedDict

# Landing-aligned USD reference (regional checkout may differ)
LANDING_USD_MONTHLY = (49, 79, 200)
MONTHLY_MESSAGE_CAPS = {
    "starter": 5_000,
    "standard": 10_000,
    "pro": 25_000,
}
TRIAL_PLAN_ID = "trial"
TRIAL_CREDITS = int(os.environ.get("BILLING_TRIAL_CREDITS", "100"))
TRIAL_MESSAGE_CAP = TRIAL_CREDITS
TRIAL_DAYS = int(os.environ.get("BILLING_TRIAL_DAYS", "14"))

PAID_PLAN_IDS = ("starter", "standard", "pro")


class PlanFlags(TypedDict):
    ai_replies: bool
    followups_broadcasts: bool
    unlimited_customers: bool
    outbound_messaging: bool
    priority_support: bool
    dedicated_support: bool
    advanced_analytics: bool
    custom_templates: bool


def normalize_plan_id(plan: Optional[str]) -> str:
    if not plan:
        return "free"
    p = str(plan).strip().lower()
    if p in ("growth", "standard"):
        return "standard"
    if p in PAID_PLAN_IDS:
        return p
    if p == TRIAL_PLAN_ID:
        return TRIAL_PLAN_ID
    return "free"


def billing_owner_id(user: dict) -> str:
    """Subscription is stored on the business owner."""
    return str(user.get("business_id") or user["_id"])


def _plan_flags(plan_id: str, *, paid_active: bool, trial_active: bool) -> PlanFlags:
    """Tier-specific perks only when paid on the correct plan (not during trial)."""
    base_paid = paid_active and plan_id in PAID_PLAN_IDS
    trial_core = trial_active
    core = base_paid or trial_core
    return PlanFlags(
        ai_replies=core,
        followups_broadcasts=core,
        unlimited_customers=core,
        outbound_messaging=core,
        priority_support=base_paid and plan_id == "standard",
        dedicated_support=base_paid and plan_id == "pro",
        advanced_analytics=base_paid and plan_id == "pro",
        custom_templates=base_paid and plan_id == "pro",
    )


def monthly_message_cap(plan_id: str, *, trial_active: bool, paid_active: bool) -> int:
    if trial_active:
        return TRIAL_MESSAGE_CAP
    if paid_active and plan_id in MONTHLY_MESSAGE_CAPS:
        return MONTHLY_MESSAGE_CAPS[plan_id]
    return 0


def trial_window(record: dict, now: Optional[datetime] = None) -> tuple[bool, Optional[datetime], Optional[datetime]]:
    now = now or datetime.utcnow()
    started = record.get("trial_started_at")
    ends = record.get("trial_ends_at")
    if not started or not ends:
        return False, started, ends
    if isinstance(started, str):
        started = datetime.fromisoformat(started.replace("Z", "+00:00").replace("+00:00", ""))
    if isinstance(ends, str):
        ends = datetime.fromisoformat(ends.replace("Z", "+00:00").replace("+00:00", ""))
    active = started <= now < ends
    return active, started, ends


def paid_subscription_active(record: dict, now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    if not record.get("subscription_active"):
        return False
    period_end = record.get("subscription_current_period_end")
    if period_end:
        if isinstance(period_end, str):
            period_end = datetime.fromisoformat(period_end.replace("Z", "+00:00").replace("+00:00", ""))
        if period_end < now:
            return False
    plan = normalize_plan_id(record.get("subscription_plan"))
    return plan in PAID_PLAN_IDS


def has_dashboard_access(record: dict, now: Optional[datetime] = None) -> bool:
    trial_active, _, _ = trial_window(record, now)
    if trial_active:
        return True
    return paid_subscription_active(record, now)


async def count_monthly_outbound(db, business_id: str, now: Optional[datetime] = None) -> int:
    now = now or datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return await db.messages.count_documents(
        {
            "user_id": business_id,
            "direction": "outgoing",
            "created_at": {"$gte": month_start},
        }
    )


async def load_billing_record(db, user: dict) -> dict:
    owner_id = billing_owner_id(user)
    if owner_id == user.get("_id"):
        return user
    owner = await db.users.find_one({"_id": owner_id})
    return owner or user


async def build_entitlements(db, user: dict) -> Dict[str, Any]:
    record = await load_billing_record(db, user)
    now = datetime.utcnow()
    trial_active, trial_started_at, trial_ends_at = trial_window(record, now)
    paid_active = paid_subscription_active(record, now)
    plan_id = normalize_plan_id(record.get("subscription_plan"))
    trial_entitled = trial_active and not paid_active
    if paid_active:
        effective_plan = plan_id
    elif trial_entitled:
        effective_plan = TRIAL_PLAN_ID
    else:
        effective_plan = "free"

    business_id = billing_owner_id(user)
    usage = await count_monthly_outbound(db, business_id, now)
    cap = monthly_message_cap(
        plan_id,
        trial_active=trial_entitled,
        paid_active=paid_active,
    )
    flags = _plan_flags(
        plan_id,
        paid_active=paid_active,
        trial_active=trial_entitled,
    )
    dashboard = has_dashboard_access(record, now)

    return {
        "owner_id": business_id,
        "effective_plan": effective_plan,
        "subscription_plan": record.get("subscription_plan"),
        "subscription_active": bool(record.get("subscription_active")),
        "paid_active": paid_active,
        "trial_active": trial_entitled,
        "trial_started_at": trial_started_at,
        "trial_ends_at": trial_ends_at,
        "trial_available": not record.get("trial_started_at"),
        "dashboard_access": dashboard,
        "subscription_current_period_end": record.get("subscription_current_period_end"),
        "subscription_cancel_at_period_end": bool(record.get("subscription_cancel_at_period_end")),
        "stripe_customer_id": record.get("stripe_customer_id"),
        "billing_provider": record.get("billing_provider") or ("stripe" if record.get("stripe_customer_id") else None),
        "usage": {
            "outbound_messages_month": usage,
            "outbound_messages_cap": cap,
            "outbound_messages_remaining": max(0, cap - usage) if cap else 0,
            "trial_credits": TRIAL_CREDITS if trial_entitled else 0,
        },
        "trial_credits": TRIAL_CREDITS if trial_entitled else 0,
        "features": dict(flags),
        "limits": {
            "monthly_messages": cap,
            "products": product_catalog_limit(effective_plan, paid_active, trial_entitled),
        },
    }


PRODUCT_CATALOG_LIMITS: Dict[str, Optional[int]] = {
    "free": 5,
    "trial": 20,
    "starter": 20,
    "standard": 50,
    "pro": None,
}


def product_catalog_limit(effective_plan: str, paid_active: bool, trial_active: bool) -> Optional[int]:
    if trial_active:
        return PRODUCT_CATALOG_LIMITS["trial"]
    if paid_active and effective_plan in PRODUCT_CATALOG_LIMITS:
        return PRODUCT_CATALOG_LIMITS[effective_plan]
    return PRODUCT_CATALOG_LIMITS["free"]


def assert_feature(ent: Dict[str, Any], feature: str, message: str = "Upgrade your plan to use this feature.") -> None:
    from fastapi import HTTPException

    if not ent.get("dashboard_access"):
        raise HTTPException(status_code=402, detail="Choose a plan or start your free trial to continue.")
    if not (ent.get("features") or {}).get(feature):
        raise HTTPException(status_code=403, detail=message)


def assert_outbound_allowed(ent: Dict[str, Any]) -> None:
    from fastapi import HTTPException

    if not ent.get("dashboard_access"):
        raise HTTPException(status_code=402, detail="Choose a plan or start your free trial to continue.")
    usage = ent.get("usage") or {}
    cap = usage.get("outbound_messages_cap") or 0
    if cap <= 0:
        raise HTTPException(status_code=402, detail="Subscribe or start a free trial to send messages.")
    if usage.get("outbound_messages_month", 0) >= cap:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly message limit reached ({cap:,}). Upgrade your plan for more capacity.",
        )


def trial_end_from_start(started: datetime) -> datetime:
    return started + timedelta(days=TRIAL_DAYS)


def trial_provision_update(started: Optional[datetime] = None) -> Dict[str, Any]:
    """Mongo $set fields for a new or restarted in-app trial."""
    started = started or datetime.utcnow()
    ends = trial_end_from_start(started)
    return {
        "trial_started_at": started,
        "trial_ends_at": ends,
        "subscription_plan": TRIAL_PLAN_ID,
        "trial_credits_granted": TRIAL_CREDITS,
    }


async def provision_signup_trial(db, owner_id: str) -> bool:
    """Start the one-time product trial for a new account. Returns True if applied."""
    record = await db.users.find_one({"_id": owner_id})
    if not record or record.get("trial_started_at"):
        return False
    if paid_subscription_active(record):
        return False
    await db.users.update_one({"_id": owner_id}, {"$set": trial_provision_update()})
    return True


def marketing_features_for_plan(plan_id: str) -> List[str]:
    """Human-readable bullets aligned with landing page."""
    caps = MONTHLY_MESSAGE_CAPS.get(plan_id, TRIAL_MESSAGE_CAP)
    rows = [
        f"{TRIAL_DAYS}-day free trial with {TRIAL_CREDITS:,} outbound messages on every plan",
        f"{caps:,} outbound messages / month",
        "Unlimited customers",
        "AI replies (autoreply & drafted WhatsApp responses)",
        "Follow-ups and broadcasts",
    ]
    if plan_id == "standard":
        rows.append("Priority support")
    if plan_id == "pro":
        rows.extend(["Dedicated support", "Advanced analytics", "Custom templates"])
    return rows
