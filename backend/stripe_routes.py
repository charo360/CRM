"""
Stripe Connect HTTP routes — onboarding, checkout, webhooks.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from payhero_auth import business_owner_id, user_id_filter
from stripe_billing import ensure_stripe_indexes, list_recent_ledger, usage_summary
from stripe_client import STRIPE_PLATFORM_PROFILE_URL, StripeApiError, StripeClient
from stripe_credentials import (
    CURRENCY_DEFAULT_COUNTRY,
    STRIPE_CONNECT_COUNTRIES,
    STRIPE_CURRENCIES,
    platform_configured,
    public_setup_card,
    stripe_checkout_ready,
    stripe_connected,
    stripe_connection_status,
)
from stripe_service import (
    create_or_refresh_onboarding_link,
    dispatch_webhook_event,
    initialize_checkout_for_user,
    process_checkout_completed,
    sync_account_fields,
    verify_webhook_payload,
)

logger = logging.getLogger(__name__)


def _clean_text(value: object, *, max_len: int = 120) -> str:
    if value is None:
        return ""
    return str(value).strip()[:max_len]


def _frontend_urls() -> tuple[str, str]:
    frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
    if not frontend:
        frontend = "http://localhost:3000"
    return (
        f"{frontend}/dashboard/integrations?stripe=return",
        f"{frontend}/dashboard/integrations?stripe=refresh",
    )


def _http_exception_for_stripe_api_error(exc: StripeApiError) -> HTTPException:
    if getattr(exc, "code", None) == "stripe_platform_profile_incomplete":
        return HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "code": exc.code,
                "action_url": exc.action_url or STRIPE_PLATFORM_PROFILE_URL,
            },
        )
    if getattr(exc, "code", None) == "stripe_connect_country_unsupported":
        return HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "code": exc.code,
                "action_url": exc.action_url or "https://stripe.com/global",
            },
        )
    return HTTPException(status_code=502, detail=str(exc))


def _parse_connect_body(body: dict) -> dict:
    email = _clean_text(body.get("email") or body.get("business_email"), max_len=120)
    business_name = _clean_text(body.get("business_name"), max_len=120)
    currency = _clean_text(body.get("currency") or body.get("default_currency") or "USD", max_len=8).upper()
    country = _clean_text(body.get("country") or CURRENCY_DEFAULT_COUNTRY.get(currency) or "", max_len=2).upper()

    if not email or "@" not in email:
        raise ValueError("Enter a valid business email.")
    if not business_name:
        raise ValueError("Enter a business name.")
    if currency not in STRIPE_CURRENCIES:
        raise ValueError(f"Unsupported currency '{currency}'.")
    if country not in STRIPE_CONNECT_COUNTRIES:
        raise ValueError(
            f"Country '{country}' is not supported for Stripe Express card checkout. "
            "Pick a country from the Integrations list (see https://stripe.com/global), "
            "or use Paystack / PayHero for Kenya and similar markets."
        )

    return {
        "email": email,
        "business_name": business_name,
        "currency": currency,
        "country": country,
    }


def register_stripe_routes(
    api_router: APIRouter,
    db,
    get_current_user: Callable,
) -> None:

    @api_router.get("/stripe/setup")
    async def stripe_setup_public():
        return public_setup_card()

    @api_router.get("/stripe/connection")
    async def stripe_get_connection(user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "stripe_connect_account_id": 1,
                "stripe_business_name": 1,
                "stripe_default_currency": 1,
                "stripe_country": 1,
                "stripe_connect_email": 1,
                "stripe_charges_enabled": 1,
                "stripe_payouts_enabled": 1,
                "stripe_details_submitted": 1,
            },
        )
        connected = stripe_connected(doc)
        checkout_ready = stripe_checkout_ready(doc)
        account_id = (doc or {}).get("stripe_connect_account_id") if connected else None

        if connected and account_id and platform_configured():
            try:
                await sync_account_fields(db, str(business_owner_id(user)), account_id)
                doc = await db.users.find_one(
                    user_id_filter(business_owner_id(user)),
                    {
                        "stripe_connect_account_id": 1,
                        "stripe_business_name": 1,
                        "stripe_default_currency": 1,
                        "stripe_country": 1,
                        "stripe_connect_email": 1,
                        "stripe_charges_enabled": 1,
                        "stripe_payouts_enabled": 1,
                        "stripe_details_submitted": 1,
                    },
                )
                checkout_ready = stripe_checkout_ready(doc)
            except Exception as e:
                logger.warning("[Stripe] connection sync: %s", e)

        status = stripe_connection_status(doc) if connected else "not_connected"

        return {
            "connected": connected,
            "checkout_ready": checkout_ready,
            "status": status,
            "business_name": (doc or {}).get("stripe_business_name") if connected else None,
            "default_currency": (doc or {}).get("stripe_default_currency") if connected else None,
            "country": (doc or {}).get("stripe_country") if connected else None,
            "connect_email": (doc or {}).get("stripe_connect_email") if connected else None,
            "account_id": account_id,
            "charges_enabled": bool((doc or {}).get("stripe_charges_enabled")) if connected else False,
            "payouts_enabled": bool((doc or {}).get("stripe_payouts_enabled")) if connected else False,
            "details_submitted": bool((doc or {}).get("stripe_details_submitted")) if connected else False,
            "platform_managed": True,
            "platform_available": platform_configured(),
        }

    @api_router.post("/stripe/connect")
    async def stripe_connect(body: dict, user=Depends(get_current_user)):
        if not platform_configured():
            raise HTTPException(
                503,
                detail="Stripe Connect is not enabled. Set STRIPE_PLATFORM_SECRET_KEY in backend/.env.",
            )
        try:
            fields = _parse_connect_body(body or {})
        except ValueError as e:
            raise HTTPException(400, detail=str(e)) from e

        owner_id = str(business_owner_id(user))
        doc = await db.users.find_one(
            user_id_filter(owner_id),
            {"stripe_connect_account_id": 1},
        )
        client = StripeClient()
        return_url, refresh_url = _frontend_urls()

        account_id = (doc or {}).get("stripe_connect_account_id") or ""
        if not account_id:
            try:
                acct = await client.create_connect_account(
                    email=fields["email"],
                    country=fields["country"],
                    business_name=fields["business_name"],
                    default_currency=fields["currency"],
                )
            except StripeApiError as e:
                raise _http_exception_for_stripe_api_error(e) from e
            account_id = _clean_text(acct.get("id"), max_len=64)
            if not account_id.startswith("acct_"):
                raise HTTPException(502, "Stripe did not return a Connect account id.")

            await db.users.update_one(
                user_id_filter(owner_id),
                {
                    "$set": {
                        "stripe_connect_account_id": account_id,
                        "stripe_business_name": fields["business_name"],
                        "stripe_connect_email": fields["email"],
                        "stripe_default_currency": fields["currency"],
                        "stripe_country": fields["country"],
                    }
                },
            )

        try:
            link = await create_or_refresh_onboarding_link(
                db,
                user_id=owner_id,
                user_doc={"stripe_connect_account_id": account_id},
                return_url=return_url,
                refresh_url=refresh_url,
            )
        except ValueError as e:
            raise HTTPException(400, detail=str(e)) from e
        except StripeApiError as e:
            raise _http_exception_for_stripe_api_error(e) from e

        return {
            "status": "onboarding",
            "connected": True,
            "checkout_ready": False,
            "onboarding_url": link["onboarding_url"],
            "account_id": account_id,
            "business_name": fields["business_name"],
            "default_currency": fields["currency"],
            "platform_managed": True,
        }

    @api_router.post("/stripe/connect/account-link")
    async def stripe_account_link(user=Depends(get_current_user)):
        if not platform_configured():
            raise HTTPException(503, detail="Stripe Connect is not configured.")
        owner_id = str(business_owner_id(user))
        doc = await db.users.find_one(
            user_id_filter(owner_id),
            {"stripe_connect_account_id": 1},
        )
        if not stripe_connected(doc):
            raise HTTPException(400, detail="Stripe Connect not set up for this workspace.")
        return_url, refresh_url = _frontend_urls()
        try:
            link = await create_or_refresh_onboarding_link(
                db,
                user_id=owner_id,
                user_doc=doc,
                return_url=return_url,
                refresh_url=refresh_url,
            )
        except ValueError as e:
            raise HTTPException(400, detail=str(e)) from e
        except StripeApiError as e:
            raise _http_exception_for_stripe_api_error(e) from e
        return {"onboarding_url": link["onboarding_url"]}

    @api_router.delete("/stripe/connect")
    async def stripe_disconnect(user=Depends(get_current_user)):
        await db.users.update_one(
            user_id_filter(business_owner_id(user)),
            {
                "$unset": {
                    "stripe_connect_account_id": "",
                    "stripe_business_name": "",
                    "stripe_default_currency": "",
                    "stripe_country": "",
                    "stripe_connect_email": "",
                    "stripe_charges_enabled": "",
                    "stripe_payouts_enabled": "",
                    "stripe_details_submitted": "",
                }
            },
        )
        return {"status": "disconnected", "connected": False}

    @api_router.get("/stripe/usage/summary")
    async def stripe_usage_summary_route(user=Depends(get_current_user)):
        user_id = str(business_owner_id(user))
        return await usage_summary(db, user_id)

    @api_router.get("/stripe/usage/ledger")
    async def stripe_usage_ledger_route(limit: int = 50, user=Depends(get_current_user)):
        user_id = str(business_owner_id(user))
        return {"entries": await list_recent_ledger(db, user_id, min(limit, 100))}

    @api_router.post("/stripe/checkout/initialize")
    async def stripe_checkout_initialize(body: dict, user=Depends(get_current_user)):
        email = (body.get("email") or "").strip()
        amount = body.get("amount")
        if not email or amount is None:
            raise HTTPException(400, "email and amount are required")

        user_id = str(business_owner_id(user))
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "stripe_connect_account_id": 1,
                "stripe_default_currency": 1,
                "stripe_charges_enabled": 1,
            },
        )
        if not stripe_checkout_ready(doc):
            raise HTTPException(
                400,
                "Stripe checkout is not ready — finish Connect onboarding in Integrations.",
            )

        frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
        success_url = (body.get("success_url") or body.get("callback_url") or "").strip()
        cancel_url = (body.get("cancel_url") or "").strip()
        if not success_url and frontend:
            success_url = f"{frontend}/dashboard/orders?stripe=success"
        if not cancel_url and frontend:
            cancel_url = f"{frontend}/dashboard/orders?stripe=cancel"

        try:
            result = await initialize_checkout_for_user(
                db,
                doc,
                user_id=user_id,
                email=email,
                amount_major=float(amount),
                currency=body.get("currency"),
                external_reference=(body.get("external_reference") or body.get("order_number") or "").strip(),
                order_id=body.get("order_id"),
                customer_id=body.get("customer_id"),
                customer_name=(body.get("customer_name") or "").strip(),
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except StripeApiError as e:
            raise HTTPException(502, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            logger.exception("[Stripe] checkout initialize failed")
            raise HTTPException(502, f"Stripe error: {e}") from e

        return {"status": "ok", **result}

    @api_router.get("/stripe/checkout/verify/{session_id}")
    async def stripe_checkout_verify(session_id: str, user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {"stripe_connect_account_id": 1, "stripe_charges_enabled": 1},
        )
        if not stripe_connected(doc):
            raise HTTPException(400, "Stripe not connected")
        try:
            session = await StripeClient().retrieve_checkout_session(session_id)
        except StripeApiError as e:
            raise HTTPException(502, str(e)) from e

        if (session.get("payment_status") or "").lower() == "paid":
            await process_checkout_completed(db, session, raw_payload={"source": "verify"})

        return {"status": "ok", "data": session}

    @api_router.post("/webhooks/stripe")
    async def stripe_webhook_platform(request: Request, background_tasks: BackgroundTasks):
        raw = await request.body()
        signature = request.headers.get("stripe-signature", "")
        event = verify_webhook_payload(raw, signature, connect=False)
        if not event:
            logger.warning("[Stripe webhook platform] invalid signature or missing secret")
            return {"status": "ok"}

        background_tasks.add_task(_stripe_process_webhook, db, event, raw)
        return {"status": "ok"}

    @api_router.post("/webhooks/stripe/connect")
    async def stripe_webhook_connect(request: Request, background_tasks: BackgroundTasks):
        raw = await request.body()
        signature = request.headers.get("stripe-signature", "")
        event = verify_webhook_payload(raw, signature, connect=True)
        if not event:
            logger.warning("[Stripe webhook connect] invalid signature or missing secret")
            return {"status": "ok"}

        background_tasks.add_task(_stripe_process_webhook, db, event, raw)
        return {"status": "ok"}


async def _stripe_process_webhook(db, event: dict, raw: bytes):
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else event
    except Exception:
        payload = event

    try:
        ctx = await dispatch_webhook_event(db, event, raw_payload=payload)
    except Exception as e:
        logger.error("[Stripe] webhook dispatch: %s", e)
        return

    if not ctx.get("handled") or ctx.get("duplicate"):
        return
    if not ctx.get("amount"):
        return

    user = ctx.get("user") or {}
    user_id = ctx["user_id"]
    phone = ctx.get("phone") or ""
    amount = ctx.get("amount")
    currency = ctx.get("currency", "")
    order_number = ctx.get("order_number")
    reference = ctx.get("reference")
    customer_name = ctx.get("customer_name", "Customer")

    if phone:
        receipt_lines = [
            f"✅ *Payment received — {currency} {amount:,.2f}*".replace(".00", ""),
        ]
        if order_number:
            receipt_lines.append(f"Order: *{order_number}*")
        if reference:
            receipt_lines.append(f"Ref: *{reference}*")
        receipt_lines.append("Thank you! We'll process your order shortly. 🙏")
        try:
            from whatsapp_service import get_whatsapp_service

            ws = get_whatsapp_service(db)
            await ws.send_message(
                user_id=str(user_id),
                to_number=phone,
                message="\n".join(receipt_lines),
                customer_name=customer_name,
                send_context="payment_receipt",
            )
        except Exception as e:
            logger.error("[Stripe] WhatsApp receipt failed: %s", e)

    push_token = user.get("push_token")
    if push_token:
        try:
            from notification_service import get_notification_service

            ns = get_notification_service()
            title = f"💰 {currency} {amount:,.0f} received"
            body = customer_name + (f" — {order_number}" if order_number else "")
            await ns.send_notification(
                push_token=push_token,
                title=title,
                body=body,
                data={"type": "payment_received", "provider": "stripe"},
            )
        except Exception as e:
            logger.error("[Stripe] push failed: %s", e)

    try:
        from workflows.engine import fire_trigger
        from workflows.models import WorkflowEvent
        from whatsapp_service import get_whatsapp_service

        ws = get_whatsapp_service(db)
        wf_event = WorkflowEvent(
            trigger_type="stripe_payment_received",
            user_id=user_id,
            from_number=phone or None,
            data={
                "amount": amount,
                "currency": currency,
                "order_number": order_number,
                "reference": reference,
                "customer_name": customer_name,
                "provider": "stripe",
            },
        )
        await fire_trigger(db, wf_event, ws)
    except Exception as e:
        logger.error("[Stripe] workflow failed: %s", e)


async def setup_stripe(db) -> None:
    await ensure_stripe_indexes(db)
