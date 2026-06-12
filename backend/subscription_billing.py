"""
Web subscription billing (Stripe Checkout + Customer Portal) and entitlement APIs.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from entitlements import (
    PAID_PLAN_IDS,
    TRIAL_DAYS,
    WEB_USD_MONTHLY,
    build_entitlements,
    marketing_features_for_plan,
    normalize_plan_id,
    paid_subscription_active,
    provision_signup_trial,
    trial_end_from_start,
    trial_provision_update,
)

PLAN_DISPLAY_NAMES = {"starter": "Starter", "standard": "Growth", "pro": "Pro"}


def get_web_plans() -> list:
    """Web product catalog (Stripe checkout): USD pricing with web-tier caps.
    Separate from the mobile app's /subscription/plans catalog."""
    plans = []
    for plan_id in PAID_PLAN_IDS:
        amount = WEB_USD_MONTHLY[plan_id]
        plans.append({
            "id": plan_id,
            "name": PLAN_DISPLAY_NAMES.get(plan_id, plan_id.title()),
            "amount": amount,
            "currency": "USD",
            "amount_display": f"USD {amount}/month",
            "interval": "monthly",
            "features": marketing_features_for_plan(plan_id),
        })
    return plans

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
WEB_APP_URL = os.environ.get("WEB_APP_URL", os.environ.get("FRONTEND_URL", "http://localhost:3000")).rstrip("/")

# Stripe Price IDs per plan (create in Dashboard; set in env)
STRIPE_PRICE_IDS = {
    "free": os.environ.get("STRIPE_PRICE_FREE", ""),
    "starter": os.environ.get("STRIPE_PRICE_STARTER", ""),
    "standard": os.environ.get("STRIPE_PRICE_GROWTH", os.environ.get("STRIPE_PRICE_STANDARD", "")),
    "pro": os.environ.get("STRIPE_PRICE_PRO", ""),
}
FREE_PLAN_ID = "free"


def _stripe():
    try:
        import stripe
    except ImportError as e:
        raise HTTPException(status_code=503, detail="Stripe is not installed on the server") from e
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured")
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


class CheckoutBody(BaseModel):
    plan_id: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class PortalBody(BaseModel):
    return_url: Optional[str] = None


def register_subscription_billing_routes(
    api_router: APIRouter,
    db,
    get_current_user: Callable,
    get_regional_plans: Callable,
) -> None:
    """Mount billing routes on the main API router."""

    @api_router.get("/subscription/plans/public")
    async def public_plans(currency: str = "USD"):
        """Catalog for the logged-out web pricing page (web product)."""
        return get_web_plans()

    @api_router.get("/subscription/plans/web")
    async def web_plans(user=Depends(get_current_user)):
        """Catalog for the logged-in web billing page (web product)."""
        return get_web_plans()

    @api_router.get("/subscription/entitlements")
    async def entitlements(user=Depends(get_current_user)):
        return await build_entitlements(db, user)

    @api_router.post("/subscription/start-trial")
    async def start_trial(user=Depends(get_current_user)):
        owner_id = user.get("business_id") or user["_id"]
        if user.get("business_id") and user.get("business_id") != user["_id"]:
            raise HTTPException(status_code=403, detail="Only the business owner can start a trial")
        record = await db.users.find_one({"_id": owner_id})
        if not record:
            raise HTTPException(status_code=404, detail="User not found")
        if record.get("trial_started_at"):
            raise HTTPException(status_code=400, detail="Free trial already used for this account")
        if record.get("subscription_active") and normalize_plan_id(record.get("subscription_plan")) in PAID_PLAN_IDS:
            raise HTTPException(status_code=400, detail="You already have an active subscription")
        started = datetime.utcnow()
        ends = trial_end_from_start(started)
        await db.users.update_one(
            {"_id": owner_id},
            {"$set": trial_provision_update(started)},
        )
        updated = await db.users.find_one({"_id": owner_id})
        ent = await build_entitlements(db, updated)
        return {"status": "ok", "trial_days": TRIAL_DAYS, "trial_ends_at": ends, **ent}

    @api_router.post("/subscription/checkout")
    async def checkout(body: CheckoutBody, user=Depends(get_current_user)):
        raw_plan = (body.plan_id or "").strip().lower()
        plan_id = FREE_PLAN_ID if raw_plan in (FREE_PLAN_ID, "trial") else normalize_plan_id(body.plan_id)
        if plan_id not in PAID_PLAN_IDS and plan_id != FREE_PLAN_ID:
            raise HTTPException(status_code=400, detail="Invalid plan")
        if user.get("business_id") and user.get("business_id") != user["_id"]:
            raise HTTPException(status_code=403, detail="Only the business owner can manage billing")

        owner_id = user["_id"]
        billing_user = await db.users.find_one({"_id": owner_id}) or user

        if plan_id == FREE_PLAN_ID:
            if billing_user.get("trial_started_at"):
                raise HTTPException(status_code=400, detail="Free trial already used for this account")
            if paid_subscription_active(billing_user):
                raise HTTPException(status_code=400, detail="You already have an active subscription")

        stripe = _stripe()
        price_id = STRIPE_PRICE_IDS.get(plan_id)
        if not price_id:
            raise HTTPException(
                status_code=503,
                detail=f"Stripe price not configured for plan '{plan_id}'",
            )

        customer_id = user.get("stripe_customer_id")
        if not customer_id:
            customer = stripe.Customer.create(
                email=user.get("email"),
                name=user.get("business_name") or user.get("name"),
                metadata={"user_id": owner_id},
            )
            customer_id = customer.id
            await db.users.update_one({"_id": owner_id}, {"$set": {"stripe_customer_id": customer_id}})

        success = body.success_url or f"{WEB_APP_URL}/dashboard/billing?checkout=success"
        cancel = body.cancel_url or f"{WEB_APP_URL}/dashboard/billing?checkout=cancel"

        subscription_data: Dict[str, Any] = {"metadata": {"plan_id": plan_id, "user_id": owner_id}}
        if plan_id in PAID_PLAN_IDS and not billing_user.get("trial_started_at") and not paid_subscription_active(billing_user):
            subscription_data["trial_period_days"] = TRIAL_DAYS

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success,
            cancel_url=cancel,
            client_reference_id=owner_id,
            metadata={"plan_id": plan_id, "user_id": owner_id},
            subscription_data=subscription_data,
        )
        return {"url": session.url, "session_id": session.id}

    @api_router.post("/subscription/portal")
    async def billing_portal(body: PortalBody, user=Depends(get_current_user)):
        if user.get("business_id") and user.get("business_id") != user["_id"]:
            raise HTTPException(status_code=403, detail="Only the business owner can manage billing")
        customer_id = user.get("stripe_customer_id")
        if not customer_id:
            raise HTTPException(status_code=400, detail="No billing account yet. Subscribe to a plan first.")
        stripe = _stripe()
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=body.return_url or f"{WEB_APP_URL}/dashboard/billing",
        )
        return {"url": session.url}

    @api_router.post("/webhooks/stripe")
    async def stripe_webhook(request: Request):
        """Stripe billing webhooks (no JWT). URL: /api/webhooks/stripe"""
        return await handle_stripe_webhook(request, db)

    @api_router.get("/subscription/invoices")
    async def list_invoices(user=Depends(get_current_user)):
        if user.get("business_id") and user.get("business_id") != user["_id"]:
            raise HTTPException(status_code=403, detail="Only the business owner can view invoices")
        customer_id = user.get("stripe_customer_id")
        if not customer_id:
            return {"invoices": []}
        stripe = _stripe()
        inv = stripe.Invoice.list(customer=customer_id, limit=24)
        rows = []
        for i in inv.auto_paging_iter():
            rows.append(
                {
                    "id": i.id,
                    "number": i.number,
                    "status": i.status,
                    "amount_due": i.amount_due,
                    "currency": i.currency,
                    "created": datetime.utcfromtimestamp(i.created) if i.created else None,
                    "hosted_invoice_url": i.hosted_invoice_url,
                    "invoice_pdf": i.invoice_pdf,
                }
            )
            if len(rows) >= 24:
                break
        return {"invoices": rows}

    # Enrich existing status endpoint data is done in server patch


async def _user_id_for_stripe_customer(db, customer_id: Optional[str]) -> Optional[str]:
    if not customer_id:
        return None
    u = await db.users.find_one({"stripe_customer_id": customer_id})
    return u.get("_id") if u else None


def _stripe_invoice_user_id(invoice: Dict[str, Any]) -> Optional[str]:
    """Resolve CRM user_id from invoice (Stripe API often puts metadata on lines/parent, not invoice root)."""
    root = invoice.get("metadata") or {}
    if root.get("user_id"):
        return root["user_id"]
    parent = invoice.get("parent") or {}
    sub_meta = (parent.get("subscription_details") or {}).get("metadata") or {}
    if sub_meta.get("user_id"):
        return sub_meta["user_id"]
    for line in (invoice.get("lines") or {}).get("data") or []:
        line_meta = line.get("metadata") or {}
        if line_meta.get("user_id"):
            return line_meta["user_id"]
    return None


def _stripe_invoice_subscription_id(invoice: Dict[str, Any]) -> Optional[str]:
    if invoice.get("subscription"):
        return invoice["subscription"]
    parent = invoice.get("parent") or {}
    return (parent.get("subscription_details") or {}).get("subscription")


async def record_stripe_subscription_payment(db, invoice: Dict[str, Any]) -> None:
    """Persist a paid subscription invoice (idempotent by Stripe invoice id)."""
    inv_id = invoice.get("id")
    if not inv_id:
        return
    user_id = _stripe_invoice_user_id(invoice)
    if not user_id:
        user_id = await _user_id_for_stripe_customer(db, invoice.get("customer"))
    created_ts = invoice.get("created")
    doc = {
        "stripe_invoice_id": inv_id,
        "stripe_customer_id": invoice.get("customer"),
        "user_id": user_id,
        "amount_paid": invoice.get("amount_paid") or 0,
        "amount_due": invoice.get("amount_due") or 0,
        "currency": (invoice.get("currency") or "").lower(),
        "status": invoice.get("status"),
        "subscription_id": _stripe_invoice_subscription_id(invoice),
        "hosted_invoice_url": invoice.get("hosted_invoice_url"),
        "invoice_pdf": invoice.get("invoice_pdf"),
        "stripe_created": datetime.utcfromtimestamp(created_ts) if created_ts else None,
        "recorded_at": datetime.utcnow(),
        "billing_provider": "stripe",
    }
    await db.subscription_payments.update_one(
        {"stripe_invoice_id": inv_id},
        {"$set": doc},
        upsert=True,
    )
    logger.info(
        "subscription_payments upsert invoice=%s user_id=%s amount_paid=%s",
        inv_id,
        user_id,
        doc.get("amount_paid"),
    )


async def apply_stripe_subscription_to_user(db, user_id: str, sub: Dict[str, Any]) -> None:
    """Sync Stripe subscription object onto user document."""
    plan_id = normalize_plan_id((sub.get("metadata") or {}).get("plan_id"))
    status = sub.get("status")
    active = status in ("active", "trialing")
    period_end = sub.get("current_period_end")
    period_end_dt = datetime.utcfromtimestamp(period_end) if period_end else None
    cancel_at_end = bool(sub.get("cancel_at_period_end"))
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "subscription_plan": plan_id if plan_id in PAID_PLAN_IDS else sub.get("metadata", {}).get("plan_id"),
                "subscription_active": active,
                "subscription_date": datetime.utcnow(),
                "subscription_current_period_end": period_end_dt,
                "subscription_cancel_at_period_end": cancel_at_end,
                "stripe_subscription_id": sub.get("id"),
                "billing_provider": "stripe",
            }
        },
    )


async def handle_stripe_webhook(request: Request, db) -> Dict[str, str]:
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    stripe = _stripe()
    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            import json

            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
            logger.warning("STRIPE_WEBHOOK_SECRET not set — webhook signature not verified")
    except Exception as e:
        logger.error("Stripe webhook error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid payload") from e

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        user_id = data.get("client_reference_id") or (data.get("metadata") or {}).get("user_id")
        plan_meta = (data.get("metadata") or {}).get("plan_id")
        if user_id and plan_meta in (FREE_PLAN_ID, "trial"):
            await provision_signup_trial(db, user_id)
        sub_id = data.get("subscription")
        if user_id and sub_id:
            sub = stripe.Subscription.retrieve(sub_id)
            await apply_stripe_subscription_to_user(db, user_id, sub)

    elif etype in (
        "customer.subscription.updated",
        "customer.subscription.created",
        "customer.subscription.deleted",
    ):
        user_id = (data.get("metadata") or {}).get("user_id")
        if not user_id:
            user_id = await _user_id_for_stripe_customer(db, data.get("customer"))
        if user_id:
            if etype == "customer.subscription.deleted":
                await db.users.update_one(
                    {"_id": user_id},
                    {"$set": {"subscription_active": False, "subscription_cancel_at_period_end": False}},
                )
            else:
                await apply_stripe_subscription_to_user(db, user_id, data)

    elif etype == "invoice.paid":
        await record_stripe_subscription_payment(db, data)
        user_id = _stripe_invoice_user_id(data)
        if not user_id:
            user_id = await _user_id_for_stripe_customer(db, data.get("customer"))
        sub_id = _stripe_invoice_subscription_id(data)
        if user_id and sub_id:
            sub = stripe.Subscription.retrieve(sub_id)
            await apply_stripe_subscription_to_user(db, user_id, sub)

    elif etype == "invoice.payment_failed":
        inv_id = data.get("id")
        if inv_id:
            await db.subscription_payments.update_one(
                {"stripe_invoice_id": inv_id},
                {
                    "$set": {
                        "status": data.get("status") or "open",
                        "amount_due": data.get("amount_due") or 0,
                        "recorded_at": datetime.utcnow(),
                        "billing_provider": "stripe",
                    }
                },
                upsert=True,
            )

    return {"status": "ok"}


def plan_feature_bullets() -> Dict[str, list]:
    return {p: marketing_features_for_plan(p) for p in PAID_PLAN_IDS}
