"""
Flutterwave HTTP routes — connection, checkout, verify, usage, webhooks.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from flutterwave_billing import (
    ensure_flutterwave_indexes,
    list_recent_ledger,
    usage_summary,
)
from flutterwave_client import FlutterwaveApiError, FlutterwaveClient, normalize_bank_option
from flutterwave_credentials import (
    CURRENCY_COUNTRY,
    flutterwave_connected,
    platform_configured,
    platform_connect_fields,
    platform_secret_key,
    public_setup_card,
)
from flutterwave_service import (
    build_subaccount_payload,
    initialize_checkout_for_user,
    parse_webhook_event,
    process_charge_success,
    verify_webhook_hash,
)
from payhero_auth import business_owner_id, user_id_filter
from flutterwave_auth import secret_key_from_doc

logger = logging.getLogger(__name__)


def _clean_text(value: object, *, max_len: int = 120) -> str:
    if value is None:
        return ""
    return str(value).strip()[:max_len]


def _parse_connect_body(body: dict) -> dict:
    currency = _clean_text(body.get("currency") or body.get("default_currency") or "NGN", max_len=8).upper()
    country = _clean_text(
        body.get("country") or CURRENCY_COUNTRY.get(currency) or "",
        max_len=2,
    ).upper()
    account_bank = _clean_text(body.get("account_bank") or body.get("settlement_bank") or body.get("bank_code"), max_len=64)
    account_number = _clean_text(body.get("account_number"), max_len=64)
    business_name = _clean_text(body.get("business_name") or body.get("subaccount_name"), max_len=80)
    business_email = _clean_text(body.get("business_email") or body.get("email"), max_len=120)
    business_contact = _clean_text(
        body.get("business_contact") or body.get("business_mobile") or body.get("phone"),
        max_len=32,
    )

    if len(country) != 2:
        raise ValueError("Country is required (2-letter code).")
    if not account_bank:
        raise ValueError("Choose a bank.")
    if not account_number:
        raise ValueError("Enter an account number.")
    if not business_name:
        raise ValueError("Enter a business / subaccount name.")
    if not business_email or "@" not in business_email:
        raise ValueError("Enter a valid business email.")
    if not business_contact:
        raise ValueError("Enter a business phone number.")

    return {
        "currency": currency,
        "country": country,
        "account_bank": account_bank,
        "account_number": account_number,
        "business_name": business_name,
        "business_email": business_email,
        "business_contact": business_contact,
    }


def register_flutterwave_routes(
    api_router: APIRouter,
    db,
    get_current_user: Callable,
) -> None:

    @api_router.get("/flutterwave/setup")
    async def flutterwave_setup_public():
        return public_setup_card()

    @api_router.get("/flutterwave/connection")
    async def flutterwave_get_connection(user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "flutterwave_subaccount_id": 1,
                "flutterwave_subaccount_name": 1,
                "flutterwave_default_currency": 1,
                "flutterwave_country": 1,
                "flutterwave_account_bank": 1,
                "flutterwave_account_number": 1,
                "flutterwave_business_email": 1,
            },
        )
        connected = flutterwave_connected(doc)
        return {
            "connected": connected,
            "business_name": (doc or {}).get("flutterwave_subaccount_name") if connected else None,
            "default_currency": (doc or {}).get("flutterwave_default_currency") if connected else None,
            "subaccount_id": (doc or {}).get("flutterwave_subaccount_id") if connected else None,
            "subaccount_name": (doc or {}).get("flutterwave_subaccount_name") if connected else None,
            "settlement_bank": (doc or {}).get("flutterwave_account_bank") if connected else None,
            "account_number": (doc or {}).get("flutterwave_account_number") if connected else None,
            "business_email": (doc or {}).get("flutterwave_business_email") if connected else None,
            "country": (doc or {}).get("flutterwave_country") if connected else None,
            "platform_managed": True,
            "platform_available": platform_configured(),
        }

    @api_router.get("/flutterwave/payout-options")
    async def flutterwave_payout_options(currency: str = "NGN"):
        if not platform_configured():
            raise HTTPException(503, "Flutterwave platform secret key is not configured.")
        cur = (currency or "NGN").upper()
        country = CURRENCY_COUNTRY.get(cur)
        if not country:
            raise HTTPException(400, f"No bank list mapping for currency {cur}.")
        try:
            rows = await FlutterwaveClient(platform_secret_key() or "").list_banks(country=country)
        except FlutterwaveApiError as e:
            raise HTTPException(502, str(e)) from e
        except Exception as e:
            logger.exception("[Flutterwave] payout options failed")
            raise HTTPException(502, f"Could not load banks: {e}") from e

        options: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            opt = normalize_bank_option(row)
            if not opt or opt["code"] in seen:
                continue
            seen.add(opt["code"])
            options.append(opt)
        options.sort(key=lambda o: o["name"].lower())
        if not options:
            raise HTTPException(
                502,
                detail=f"Flutterwave returned no banks for {cur} ({country}).",
            )
        return {"currency": cur, "country": country, "options": options}

    @api_router.post("/flutterwave/connect")
    async def flutterwave_connect(body: dict, user=Depends(get_current_user)):
        if not platform_configured():
            raise HTTPException(
                503,
                detail="Flutterwave is not enabled on this server. Set FLUTTERWAVE_PLATFORM_SECRET_KEY.",
            )
        try:
            sub = _parse_connect_body(body or {})
            fields = platform_connect_fields(body or {})
            client = FlutterwaveClient(platform_secret_key() or "")
            sub_payload = build_subaccount_payload(
                account_bank=sub["account_bank"],
                account_number=sub["account_number"],
                business_name=sub["business_name"],
                business_email=sub["business_email"],
                business_contact=sub["business_contact"],
                country=sub["country"],
            )
            created = await client.create_subaccount(sub_payload)
            sub_id = _clean_text(created.get("id") or created.get("subaccount_id"), max_len=80)
            if not sub_id:
                raise HTTPException(502, "Flutterwave did not return a subaccount id.")
            fields.update(
                {
                    "flutterwave_subaccount_id": sub_id,
                    "flutterwave_subaccount_name": sub["business_name"],
                    "flutterwave_account_bank": sub["account_bank"],
                    "flutterwave_account_number": sub["account_number"],
                    "flutterwave_business_email": sub["business_email"],
                    "flutterwave_default_currency": sub["currency"],
                    "flutterwave_country": sub["country"],
                }
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except FlutterwaveApiError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        owner_id = business_owner_id(user)
        result = await db.users.update_one(user_id_filter(owner_id), {"$set": fields})
        if result.matched_count == 0:
            raise HTTPException(404, "Business account not found")
        return {
            "status": "connected",
            "connected": True,
            "business_name": fields.get("flutterwave_subaccount_name") or "Connected",
            "default_currency": fields.get("flutterwave_default_currency"),
            "subaccount_id": fields.get("flutterwave_subaccount_id"),
            "platform_managed": True,
        }

    @api_router.delete("/flutterwave/connect")
    async def flutterwave_disconnect(user=Depends(get_current_user)):
        await db.users.update_one(
            user_id_filter(business_owner_id(user)),
            {
                "$unset": {
                    "flutterwave_subaccount_id": "",
                    "flutterwave_subaccount_name": "",
                    "flutterwave_default_currency": "",
                    "flutterwave_country": "",
                    "flutterwave_account_bank": "",
                    "flutterwave_account_number": "",
                    "flutterwave_business_email": "",
                }
            },
        )
        return {"status": "disconnected", "connected": False}

    @api_router.get("/flutterwave/usage/summary")
    async def flutterwave_usage_summary_route(user=Depends(get_current_user)):
        user_id = str(business_owner_id(user))
        return await usage_summary(db, user_id)

    @api_router.get("/flutterwave/usage/ledger")
    async def flutterwave_usage_ledger_route(limit: int = 50, user=Depends(get_current_user)):
        user_id = str(business_owner_id(user))
        return {"entries": await list_recent_ledger(db, user_id, min(limit, 100))}

    @api_router.post("/flutterwave/transaction/initialize")
    async def flutterwave_initialize(body: dict, user=Depends(get_current_user)):
        email = (body.get("email") or "").strip()
        amount = body.get("amount")
        if not email or amount is None:
            raise HTTPException(400, "email and amount are required")

        user_id = str(business_owner_id(user))
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "flutterwave_subaccount_id": 1,
                "flutterwave_default_currency": 1,
            },
        )
        if not flutterwave_connected(doc):
            raise HTTPException(400, "Flutterwave not connected — enable it in Integrations")

        frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
        redirect_url = (body.get("callback_url") or body.get("redirect_url") or "").strip()
        if not redirect_url and frontend:
            redirect_url = f"{frontend}/dashboard/orders?flutterwave=success"

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
                redirect_url=redirect_url,
            )
        except FlutterwaveApiError as e:
            raise HTTPException(502, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            logger.exception("[Flutterwave] initialize failed")
            raise HTTPException(502, f"Flutterwave error: {e}") from e

        return {"status": "ok", **result}

    @api_router.get("/flutterwave/transaction/verify/{reference}")
    async def flutterwave_verify(reference: str, user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {"flutterwave_subaccount_id": 1},
        )
        secret = secret_key_from_doc(doc)
        if not secret:
            raise HTTPException(400, "Flutterwave not connected")
        try:
            data = await FlutterwaveClient(secret).verify_by_reference(reference)
        except FlutterwaveApiError as e:
            raise HTTPException(502, str(e)) from e

        status = (data.get("status") or "").lower()
        if status in ("successful", "success"):
            meta = data.get("meta") or {}
            if not isinstance(meta, dict):
                meta = {}
            parsed = parse_webhook_event(
                {
                    "event": "charge.completed",
                    "data": {
                        "tx_ref": data.get("tx_ref") or reference,
                        "status": status,
                        "amount": data.get("amount"),
                        "currency": data.get("currency"),
                        "meta": meta,
                        "customer": data.get("customer"),
                    },
                }
            )
            await process_charge_success(db, parsed, raw_payload={"source": "verify", "data": data})

        return {"status": "ok", "data": data}

    @api_router.post("/webhooks/flutterwave")
    async def flutterwave_webhook(request: Request, background_tasks: BackgroundTasks):
        raw = await request.body()
        verif = request.headers.get("verif-hash", "")

        if not verify_webhook_hash(verif):
            logger.warning("[Flutterwave webhook] invalid verif-hash")
            return {"status": "ok"}

        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {"status": "ok"}
        if not isinstance(payload, dict):
            return {"status": "ok"}

        parsed = parse_webhook_event(payload)
        if not parsed.get("success"):
            return {"status": "ok", "note": "ignored event"}

        background_tasks.add_task(_flutterwave_process_and_notify, db, payload, parsed)
        return {"status": "ok"}


async def _flutterwave_process_and_notify(db, payload: dict, parsed: dict):
    try:
        ctx = await process_charge_success(db, parsed, raw_payload=payload)
    except Exception as e:
        logger.error("[Flutterwave] process_charge_success: %s", e)
        return

    if not ctx.get("handled") or ctx.get("duplicate"):
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
            logger.error("[Flutterwave] WhatsApp receipt failed: %s", e)

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
                data={"type": "payment_received", "provider": "flutterwave"},
            )
        except Exception as e:
            logger.error("[Flutterwave] push failed: %s", e)

    try:
        from workflows.engine import fire_trigger
        from workflows.models import WorkflowEvent
        from whatsapp_service import get_whatsapp_service

        ws = get_whatsapp_service(db)
        event = WorkflowEvent(
            trigger_type="flutterwave_payment_received",
            user_id=user_id,
            from_number=phone or None,
            data={
                "amount": amount,
                "currency": currency,
                "order_number": order_number,
                "reference": reference,
                "customer_name": customer_name,
                "provider": "flutterwave",
            },
        )
        await fire_trigger(db, event, ws)
    except Exception as e:
        logger.error("[Flutterwave] workflow failed: %s", e)


async def setup_flutterwave(db) -> None:
    await ensure_flutterwave_indexes(db)
