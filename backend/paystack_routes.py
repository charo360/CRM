"""
Paystack HTTP routes — connection, checkout, verify, usage, webhooks.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from payhero_auth import business_owner_id, user_id_filter
from paystack_auth import parse_connect_body
from paystack_credentials import (
    PAYSTACK_AUTH_PLATFORM,
    PAYSTACK_PLATFORM_CURRENCY,
    PAYSTACK_MOBILE_MONEY_CURRENCIES,
    PAYSTACK_PAYOUT_BANK,
    PAYSTACK_PAYOUT_MOBILE_MONEY,
    platform_configured,
    platform_connect_fields,
    platform_secret_key,
    public_setup_card,
    paystack_connected,
    paystack_auth_mode,
)
from paystack_auth import secret_key_from_doc
from paystack_billing import ensure_paystack_indexes, list_recent_ledger, usage_summary
from paystack_client import PaystackApiError, PaystackClient, normalize_bank_option
from paystack_service import (
    initialize_checkout_for_user,
    parse_webhook_event,
    process_charge_success,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)


def _clean_text(value: object, *, max_len: int = 120) -> str:
    if value is None:
        return ""
    return str(value).strip()[:max_len]


def _parse_subaccount_payload(body: dict) -> dict:
    payout_type = (body.get("payout_type") or body.get("payoutType") or PAYSTACK_PAYOUT_BANK).strip().lower()
    if payout_type not in (PAYSTACK_PAYOUT_BANK, PAYSTACK_PAYOUT_MOBILE_MONEY):
        raise ValueError("Invalid payout type. Use 'bank' or 'mobile_money'.")

    currency = _clean_text(
        body.get("currency") or body.get("default_currency") or PAYSTACK_PLATFORM_CURRENCY,
        max_len=8,
    ).upper()
    settlement_bank = _clean_text(body.get("settlement_bank") or body.get("bank_code") or body.get("bank"), max_len=64)
    account_number = _clean_text(body.get("account_number"), max_len=64)
    business_name = _clean_text(body.get("business_name") or body.get("subaccount_name"), max_len=80)

    if not settlement_bank:
        raise ValueError("Choose a bank or mobile money provider.")
    if not account_number:
        raise ValueError("Enter an account number.")
    if not business_name:
        raise ValueError("Enter a subaccount name.")

    return {
        "currency": currency,
        "payout_type": payout_type,
        "settlement_bank": settlement_bank,
        "account_number": account_number,
        "business_name": business_name,
    }


def register_paystack_routes(
    api_router: APIRouter,
    db,
    get_current_user: Callable,
) -> None:

    @api_router.get("/paystack/setup")
    async def paystack_setup_public():
        """Whether platform Paystack is enabled and supported checkout currencies."""
        return public_setup_card()

    @api_router.get("/paystack/connection")
    async def paystack_get_connection(user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "paystack_secret_key": 1,
                "paystack_business_name": 1,
                "paystack_default_currency": 1,
                "paystack_payout_type": 1,
                "paystack_subaccount_code": 1,
                "paystack_subaccount_name": 1,
                "paystack_settlement_bank": 1,
                "paystack_account_number": 1,
                "paystack_auth_mode": 1,
            },
        )
        connected = paystack_connected(doc)
        mode = paystack_auth_mode(doc)
        return {
            "connected": connected,
            "business_name": (doc or {}).get("paystack_business_name") if connected else None,
            "default_currency": (doc or {}).get("paystack_default_currency") if connected else None,
            "payout_type": (doc or {}).get("paystack_payout_type") if connected else None,
            "subaccount_code": (doc or {}).get("paystack_subaccount_code") if connected else None,
            "subaccount_name": (doc or {}).get("paystack_subaccount_name") if connected else None,
            "settlement_bank": (doc or {}).get("paystack_settlement_bank") if connected else None,
            "account_number": (doc or {}).get("paystack_account_number") if connected else None,
            "auth_mode": mode,
            "platform_managed": mode == PAYSTACK_AUTH_PLATFORM,
            "platform_available": platform_configured(),
        }

    @api_router.get("/paystack/payout-options")
    async def paystack_payout_options(
        currency: str = PAYSTACK_PLATFORM_CURRENCY,
        payout_type: str = PAYSTACK_PAYOUT_BANK,
    ):
        if not platform_configured():
            raise HTTPException(503, "Paystack platform secret key is not configured.")
        cur = (currency or PAYSTACK_PLATFORM_CURRENCY).upper()
        kind = (payout_type or PAYSTACK_PAYOUT_BANK).strip().lower()
        if cur != PAYSTACK_PLATFORM_CURRENCY:
            return {
                "currency": cur,
                "payout_type": kind,
                "options": [],
                "supported": False,
                "hint": (
                    "Zilo-managed bank and mobile-money payouts are available only in Kenya (KES). "
                    "For this country, connect your own Paystack account instead."
                ),
            }
        if kind == PAYSTACK_PAYOUT_MOBILE_MONEY and cur not in PAYSTACK_MOBILE_MONEY_CURRENCIES:
            return {
                "currency": cur,
                "payout_type": kind,
                "options": [],
                "supported": False,
                "hint": (
                    f"Paystack does not offer mobile money subaccounts for {cur}. "
                    f"Use Bank for {cur}, or choose currency "
                    f"{', '.join(sorted(PAYSTACK_MOBILE_MONEY_CURRENCIES))} for mobile money."
                ),
            }
        try:
            rows = await PaystackClient(platform_secret_key() or "").list_banks(
                currency=cur,
                payout_type=kind,
            )
        except PaystackApiError as e:
            raise HTTPException(502, str(e)) from e
        except Exception as e:
            logger.exception("[Paystack] payout options failed")
            raise HTTPException(502, f"Could not load payout options: {e}") from e

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
            logger.warning(
                "[Paystack] payout-options empty currency=%s payout_type=%s raw_rows=%s",
                currency,
                payout_type,
                len(rows),
            )
            raise HTTPException(
                502,
                detail=(
                    f"Paystack returned no payout options for {cur} ({kind}). "
                    "Check PAYSTACK_PLATFORM_SECRET_KEY or try another currency."
                ),
            )
        return {
            "currency": cur,
            "payout_type": kind,
            "options": options,
            "supported": True,
        }

    @api_router.post("/paystack/connect")
    async def paystack_connect(body: dict, user=Depends(get_current_user)):
        body = body or {}
        secret_in_body = (body.get("secret_key") or "").strip()
        requested_currency = _clean_text(
            body.get("currency") or body.get("default_currency") or "", max_len=8
        ).upper()
        country_code = _clean_text(
            user.get("country_code") or (user.get("settings") or {}).get("country_code"),
            max_len=16,
        ).upper()
        kenya_currency = requested_currency == PAYSTACK_PLATFORM_CURRENCY
        kenya_business = not country_code or country_code in {"KE", "KENYA"}
        use_platform = (
            platform_configured()
            and not secret_in_body
            and kenya_currency
            and kenya_business
        )

        if not secret_in_body and not use_platform:
            if kenya_currency and not kenya_business:
                raise HTTPException(
                    400,
                    detail=(
                        "Zilo-managed Paystack bank and M-Pesa payouts are for Kenyan businesses only. "
                        "Connect your own Paystack account for this business."
                    ),
                )
            if kenya_currency and not platform_configured():
                raise HTTPException(
                    503,
                    detail="Zilo Paystack for Kenya is not enabled on this server yet. Contact support.",
                )
            raise HTTPException(
                400,
                detail=(
                    "For Nigeria and other supported countries, connect your own Paystack account "
                    "by entering its sk_test_ or sk_live_ secret key."
                ),
            )

        try:
            if use_platform:
                if not platform_configured():
                    raise HTTPException(
                        503,
                        detail="Paystack is not enabled on this server yet. Contact support.",
                    )
                sub = _parse_subaccount_payload(body)
                client = PaystackClient(platform_secret_key() or "")
                rows = await client.list_banks(
                    currency=sub["currency"],
                    payout_type=sub["payout_type"],
                )
                codes = {
                    o["code"]
                    for r in rows
                    if (o := normalize_bank_option(r))
                }
                if sub["payout_type"] == PAYSTACK_PAYOUT_MOBILE_MONEY:
                    if sub["currency"] not in PAYSTACK_MOBILE_MONEY_CURRENCIES:
                        raise HTTPException(
                            400,
                            detail=(
                                f"Mobile money is not supported for {sub['currency']} on Paystack."
                            ),
                        )
                if sub["settlement_bank"] not in codes:
                    raise HTTPException(
                        400,
                        detail="Choose a valid payout provider for this currency and type.",
                    )
                fields = platform_connect_fields(body)
                secret = platform_secret_key()
                sub_payload = {
                    "business_name": sub["business_name"],
                    "settlement_bank": sub["settlement_bank"],
                    "account_number": sub["account_number"],
                    "percentage_charge": 0,
                    "description": f"Zilo workspace payout ({sub['payout_type']})",
                    "currency": sub["currency"],
                }
                created = await client.create_subaccount(sub_payload)
                sub_code = _clean_text(created.get("subaccount_code"), max_len=64)
                if not sub_code:
                    raise HTTPException(502, "Paystack did not return a subaccount code.")
                fields.update(
                    {
                        "paystack_subaccount_code": sub_code,
                        "paystack_subaccount_name": sub["business_name"],
                        "paystack_settlement_bank": sub["settlement_bank"],
                        "paystack_account_number": sub["account_number"],
                        "paystack_default_currency": sub["currency"],
                        "paystack_payout_type": sub["payout_type"],
                    }
                )
            else:
                fields = parse_connect_body(body)
                secret = fields["paystack_secret_key"]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except PaystackApiError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        if not secret:
            raise HTTPException(503, "Paystack platform secret key is not configured.")

        try:
            biz = await PaystackClient(secret).fetch_business()
            fields["paystack_business_name"] = (
                (biz.get("name") or biz.get("business_name") or "Paystack")[:120]
            )
        except PaystackApiError as e:
            msg = str(e).strip() or "Invalid key"
            if msg.lower() in ("paystack http 404", "paystack http 401"):
                msg = (
                    "Paystack rejected the platform key — check PAYSTACK_PLATFORM_SECRET_KEY"
                    if use_platform
                    else "Invalid Paystack secret key — use sk_test_ or sk_live_ from your dashboard"
                )
            raise HTTPException(status_code=400, detail=msg) from e
        except Exception as e:
            logger.exception("[Paystack] connect verify failed")
            raise HTTPException(status_code=502, detail=f"Paystack unreachable: {e}") from e

        owner_id = business_owner_id(user)
        update: dict = {"$set": fields}
        if use_platform:
            update["$unset"] = {"paystack_secret_key": ""}
        else:
            update["$unset"] = {
                "paystack_payout_type": "",
                "paystack_subaccount_code": "",
                "paystack_subaccount_name": "",
                "paystack_settlement_bank": "",
                "paystack_account_number": "",
            }
        result = await db.users.update_one(user_id_filter(owner_id), update)
        if result.matched_count == 0:
            raise HTTPException(404, "Business account not found")
        return {
            "status": "connected",
            "connected": True,
            "business_name": fields.get("paystack_business_name") or "Connected",
            "default_currency": fields.get("paystack_default_currency"),
            "payout_type": fields.get("paystack_payout_type"),
            "subaccount_code": fields.get("paystack_subaccount_code"),
            "platform_managed": use_platform,
        }

    @api_router.delete("/paystack/connect")
    async def paystack_disconnect(user=Depends(get_current_user)):
        await db.users.update_one(
            user_id_filter(business_owner_id(user)),
            {
                "$unset": {
                    "paystack_secret_key": "",
                    "paystack_business_name": "",
                    "paystack_default_currency": "",
                    "paystack_payout_type": "",
                    "paystack_subaccount_code": "",
                    "paystack_subaccount_name": "",
                    "paystack_settlement_bank": "",
                    "paystack_account_number": "",
                    "paystack_auth_mode": "",
                }
            },
        )
        return {"status": "disconnected", "connected": False}

    @api_router.get("/paystack/usage/summary")
    async def paystack_usage_summary_route(user=Depends(get_current_user)):
        user_id = str(business_owner_id(user))
        return await usage_summary(db, user_id)

    @api_router.get("/paystack/usage/ledger")
    async def paystack_usage_ledger_route(limit: int = 50, user=Depends(get_current_user)):
        user_id = str(business_owner_id(user))
        return {"entries": await list_recent_ledger(db, user_id, min(limit, 100))}

    @api_router.post("/paystack/transaction/initialize")
    async def paystack_initialize(body: dict, user=Depends(get_current_user)):
        email = (body.get("email") or "").strip()
        amount = body.get("amount")
        if not email or amount is None:
            raise HTTPException(400, "email and amount are required")

        user_id = str(business_owner_id(user))
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "paystack_secret_key": 1,
                "paystack_auth_mode": 1,
                "paystack_default_currency": 1,
                "paystack_subaccount_code": 1,
            },
        )
        if not paystack_connected(doc):
            raise HTTPException(
                400,
                "Paystack not connected — enable it in Integrations",
            )

        frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
        callback_url = (body.get("callback_url") or "").strip()
        if not callback_url and frontend:
            callback_url = f"{frontend}/dashboard/orders?paystack=success"

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
                callback_url=callback_url,
            )
        except PaystackApiError as e:
            raise HTTPException(502, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            logger.exception("[Paystack] initialize failed")
            raise HTTPException(502, f"Paystack error: {e}") from e

        return {"status": "ok", **result}

    @api_router.get("/paystack/transaction/verify/{reference}")
    async def paystack_verify(reference: str, user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {"paystack_secret_key": 1, "paystack_auth_mode": 1},
        )
        secret = secret_key_from_doc(doc)
        if not secret:
            raise HTTPException(400, "Paystack not connected")
        try:
            data = await PaystackClient(secret).verify_transaction(reference)
        except PaystackApiError as e:
            raise HTTPException(502, str(e)) from e

        if (data.get("status") or "").lower() == "success":
            parsed = parse_webhook_event(
                {"event": "charge.success", "data": data}
            )
            await process_charge_success(db, parsed, raw_payload={"source": "verify", "data": data})

        return {"status": "ok", "data": data}

    @api_router.post("/webhooks/paystack")
    async def paystack_webhook(request: Request, background_tasks: BackgroundTasks):
        raw = await request.body()
        signature = request.headers.get("x-paystack-signature", "")

        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {"status": "ok"}
        if not isinstance(payload, dict):
            return {"status": "ok"}

        parsed = parse_webhook_event(payload)
        if parsed["event"] not in ("charge.success",) and not parsed["success"]:
            return {"status": "ok", "note": "ignored event"}

        reference = parsed.get("reference")
        intent = None
        if reference:
            from paystack_billing import find_intent_by_reference

            intent = await find_intent_by_reference(db, reference)

        user_id = None
        if intent:
            user_id = intent.get("user_id")
        else:
            meta = parsed.get("metadata") or {}
            user_id = meta.get("crm_user_id")

        if not user_id:
            logger.warning("[Paystack webhook] no tenant for ref=%s", reference)
            return {"status": "ok"}

        user_doc = await db.users.find_one(
            user_id_filter(user_id),
            {"paystack_secret_key": 1, "paystack_auth_mode": 1},
        )
        secret = secret_key_from_doc(user_doc) or platform_secret_key()
        if not secret or not verify_webhook_signature(secret, raw, signature):
            logger.warning("[Paystack webhook] invalid signature for user=%s", user_id)
            return {"status": "ok"}

        background_tasks.add_task(_paystack_process_and_notify, db, payload, parsed)
        return {"status": "ok"}


async def _paystack_process_and_notify(db, payload: dict, parsed: dict):
    try:
        ctx = await process_charge_success(db, parsed, raw_payload=payload)
    except Exception as e:
        logger.error("[Paystack] process_charge_success: %s", e)
        return

    if not ctx.get("handled"):
        return
    if ctx.get("duplicate"):
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
            logger.error("[Paystack] WhatsApp receipt failed: %s", e)

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
                data={"type": "payment_received", "provider": "paystack"},
            )
        except Exception as e:
            logger.error("[Paystack] push failed: %s", e)

    try:
        from workflows.engine import fire_trigger
        from workflows.models import WorkflowEvent
        from whatsapp_service import get_whatsapp_service

        ws = get_whatsapp_service(db)
        event = WorkflowEvent(
            trigger_type="paystack_payment_received",
            user_id=user_id,
            from_number=phone or None,
            data={
                "amount": amount,
                "currency": currency,
                "order_number": order_number,
                "reference": reference,
                "customer_name": customer_name,
            },
        )
        await fire_trigger(db, event, ws)
    except Exception as e:
        logger.error("[Paystack] workflow failed: %s", e)


async def setup_paystack(db) -> None:
    await ensure_paystack_indexes(db)
