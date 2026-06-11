"""
PayHero HTTP routes (connection, channels, STK, rates, usage, webhooks).
"""
from __future__ import annotations

import logging
import os
from typing import Callable

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from payhero_billing import (
    create_payment_intent,
    list_recent_ledger,
    mark_intent_failed,
    mark_intent_stk_sent,
    usage_summary,
)
from payhero_rates import mpesa_fee_quote, public_rate_card
from payhero_auth import (
    business_owner_id,
    credentials_from_connect_body,
    user_id_filter,
    verify_payhero_credentials,
)
from payhero_credentials import (
    PAYHERO_AUTH_MERCHANT,
    PAYHERO_AUTH_PLATFORM,
    channel_connect_fields_from_body,
    payhero_connected,
    platform_account_id,
    platform_authorization_header,
    platform_configured,
)
from payhero_service import (
    list_bank_paybills,
    list_channels_for_user,
    parse_webhook,
    process_payment,
    register_payment_channel,
    stk_push_for_user,
)

logger = logging.getLogger(__name__)


def register_payhero_routes(
    api_router: APIRouter,
    db,
    get_current_user: Callable,
) -> None:
    @api_router.get("/payhero/rates")
    async def payhero_rates_public():
        """Published PayHero Kenya fee tiers (no auth)."""
        card = dict(public_rate_card())
        card["platform_available"] = platform_configured()
        card["platform_account_configured"] = platform_account_id() is not None
        return card

    @api_router.get("/payhero/bank_paybills")
    async def payhero_bank_paybills(user=Depends(get_current_user)):
        """Banks PayHero supports for settlement (name + paybill)."""
        del user
        if not platform_configured():
            raise HTTPException(
                status_code=503,
                detail="M-Pesa bank setup is not enabled on this server.",
            )
        auth = platform_authorization_header()
        if not auth:
            raise HTTPException(status_code=503, detail="PayHero platform credentials missing.")
        try:
            banks = await list_bank_paybills(auth)
        except httpx.TimeoutException as e:
            raise HTTPException(
                status_code=504,
                detail="PayHero bank list timed out. Try again.",
            ) from e
        except httpx.HTTPStatusError as e:
            detail = (e.response.text or "")[:300]
            raise HTTPException(
                status_code=502,
                detail=f"Could not load PayHero banks: {detail}",
            ) from e
        except Exception as e:
            logger.exception("[PayHero] bank_paybills failed")
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"banks": banks}

    @api_router.get("/payhero/fees/quote")
    async def payhero_fee_quote(amount: float, user=Depends(get_current_user)):
        q = mpesa_fee_quote(amount)
        return {
            "gross_kes": q.gross_kes,
            "payhero_fee_kes": q.payhero_fee_kes,
            "merchant_receives_kes": q.merchant_receives_kes,
            "tier_min_kes": q.tier_min_kes,
            "tier_max_kes": q.tier_max_kes,
            "rate_card_version": public_rate_card()["version"],
        }

    @api_router.get("/payhero/usage/summary")
    async def payhero_usage_summary(user=Depends(get_current_user)):
        user_id = str(user.get("business_id", user["_id"]))
        return await usage_summary(db, user_id)

    @api_router.get("/payhero/usage/ledger")
    async def payhero_usage_ledger(limit: int = 50, user=Depends(get_current_user)):
        user_id = str(user.get("business_id", user["_id"]))
        return {"entries": await list_recent_ledger(db, user_id, min(limit, 100))}

    @api_router.get("/payhero/connection")
    async def payhero_get_connection(user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "payhero_username": 1,
                "payhero_api_token": 1,
                "payhero_channel_id": 1,
                "payhero_auth_mode": 1,
                "payhero_channel_type": 1,
                "payhero_short_code": 1,
                "payhero_account_number": 1,
                "payhero_channel_description": 1,
                "payhero_channel_active": 1,
            },
        )
        connected = payhero_connected(doc)
        mode = (doc or {}).get("payhero_auth_mode")
        return {
            "connected": connected,
            "username": (doc or {}).get("payhero_username") if connected else None,
            "channel_id": (doc or {}).get("payhero_channel_id") if connected else None,
            "auth_mode": mode,
            "platform_managed": mode == PAYHERO_AUTH_PLATFORM,
            "channel_type": (doc or {}).get("payhero_channel_type") if connected else None,
            "short_code": (doc or {}).get("payhero_short_code") if connected else None,
            "account_number": (doc or {}).get("payhero_account_number") if connected else None,
            "channel_description": (doc or {}).get("payhero_channel_description") if connected else None,
            "channel_active": (doc or {}).get("payhero_channel_active") if connected else None,
            "platform_available": platform_configured(),
            "platform_account_configured": platform_account_id() is not None,
        }

    @api_router.post("/payhero/connect")
    async def payhero_connect(body: dict, user=Depends(get_current_user)):
        body = body or {}
        store_fields: dict
        channel_id = None

        is_channel_form = bool(
            (body.get("channel_type") or body.get("type") or "").strip()
            or (body.get("short_code") or body.get("paybill") or body.get("till"))
        )

        try:
            if is_channel_form:
                if not platform_configured():
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "M-Pesa setup is not enabled on this server yet. "
                            "Contact support — you only need your paybill, till, or bank details."
                        ),
                    )
                account_id = platform_account_id()
                if account_id is None:
                    raise HTTPException(
                        status_code=503,
                        detail="PayHero platform account is not configured (PAYHERO_PLATFORM_ACCOUNT_ID).",
                    )
                ch = channel_connect_fields_from_body(body)
                auth_header = platform_authorization_header()
                if not auth_header:
                    raise HTTPException(503, "PayHero platform credentials missing.")
                created = await register_payment_channel(
                    auth_header,
                    account_id=account_id,
                    channel_type=ch["channel_type"],
                    short_code=ch["short_code"],
                    account_number=ch["account_number"],
                    description=ch["description"],
                )
                channel_id = created.get("id")
                if channel_id is None:
                    raise ValueError("PayHero did not return a channel id")
                is_active = created.get("is_active", True)
                store_fields = {
                    "payhero_auth_mode": PAYHERO_AUTH_PLATFORM,
                    "payhero_channel_id": channel_id,
                    "payhero_channel_type": ch["channel_type"],
                    "payhero_short_code": ch["short_code"],
                    "payhero_account_number": ch["account_number"],
                    "payhero_channel_description": ch["description"],
                    "payhero_channel_active": bool(is_active),
                    "payhero_username": ch["display_label"],
                }
            else:
                auth_header, cred_fields = credentials_from_connect_body(body)
                await verify_payhero_credentials(auth_header)
                store_fields = {
                    **cred_fields,
                    "payhero_auth_mode": PAYHERO_AUTH_MERCHANT,
                }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except HTTPException:
            raise
        except httpx.TimeoutException as e:
            raise HTTPException(
                status_code=504,
                detail="PayHero API timed out. Check your network and try again.",
            ) from e
        except httpx.HTTPStatusError as e:
            detail = (e.response.text or "")[:300]
            raise HTTPException(
                502,
                f"PayHero could not register your M-Pesa destination: {detail}",
            ) from e
        except Exception as e:
            logger.exception("[PayHero] connect failed")
            raise HTTPException(
                status_code=502,
                detail=f"PayHero connect failed: {e}",
            ) from e

        try:
            owner_id = business_owner_id(user)
            update: dict = {"$set": store_fields}
            if is_channel_form:
                update["$unset"] = {
                    "payhero_api_token": "",
                    "payhero_password": "",
                }
            result = await db.users.update_one(
                user_id_filter(owner_id),
                update,
            )
            if result.matched_count == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Business account not found — log out and log in again.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("[PayHero] could not save credentials")
            raise HTTPException(
                status_code=500,
                detail="Could not save PayHero credentials.",
            ) from e

        display = store_fields.get("payhero_username") or "Connected"
        return {
            "status": "connected",
            "connected": True,
            "username": display,
            "channel_id": channel_id,
            "channel_active": store_fields.get("payhero_channel_active"),
        }

    @api_router.delete("/payhero/connect")
    async def payhero_disconnect(user=Depends(get_current_user)):
        await db.users.update_one(
            user_id_filter(business_owner_id(user)),
            {
                "$unset": {
                    "payhero_username": "",
                    "payhero_password": "",
                    "payhero_api_token": "",
                    "payhero_channel_id": "",
                    "payhero_auth_mode": "",
                    "payhero_channel_type": "",
                    "payhero_short_code": "",
                    "payhero_account_number": "",
                    "payhero_channel_description": "",
                    "payhero_channel_active": "",
                }
            },
        )
        return {"status": "disconnected", "connected": False}

    @api_router.get("/payhero/channels")
    async def payhero_list_channels_route(user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "payhero_username": 1,
                "payhero_password": 1,
                "payhero_api_token": 1,
                "payhero_channel_id": 1,
                "payhero_auth_mode": 1,
                "payhero_channel_type": 1,
                "payhero_short_code": 1,
                "payhero_channel_description": 1,
            },
        )
        if not payhero_connected(doc):
            raise HTTPException(400, "PayHero not connected")
        try:
            channels = await list_channels_for_user(doc)
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                502,
                f"PayHero API error ({e.response.status_code}): {(e.response.text or '')[:200]}",
            ) from e
        except Exception as e:
            raise HTTPException(502, f"PayHero API error: {e}") from e
        return {
            "channels": channels,
            "selected_channel_id": doc.get("payhero_channel_id"),
        }

    @api_router.post("/payhero/channel")
    async def payhero_set_channel(body: dict, user=Depends(get_current_user)):
        channel_id = body.get("channel_id")
        if not channel_id:
            raise HTTPException(400, "channel_id required")
        await db.users.update_one(
            user_id_filter(business_owner_id(user)),
            {"$set": {"payhero_channel_id": channel_id}},
        )
        return {"status": "ok", "channel_id": channel_id}

    @api_router.post("/payhero/stk-push")
    async def payhero_stk_push_route(body: dict, user=Depends(get_current_user)):
        phone = (body.get("phone") or "").strip()
        amount = body.get("amount")
        external_reference = (
            body.get("external_reference") or body.get("order_number") or ""
        ).strip()
        customer_name = (body.get("customer_name") or "").strip()
        order_id = body.get("order_id")

        if not phone or amount is None:
            raise HTTPException(400, "phone and amount are required")

        user_id = str(business_owner_id(user))
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "payhero_username": 1,
                "payhero_password": 1,
                "payhero_api_token": 1,
                "payhero_channel_id": 1,
                "payhero_auth_mode": 1,
            },
        )
        if not payhero_connected(doc):
            raise HTTPException(400, "PayHero not connected")
        if not doc.get("payhero_channel_id"):
            raise HTTPException(
                400,
                "No PayHero channel selected — go to Integrations and pick a channel",
            )

        quote = mpesa_fee_quote(float(amount))
        intent = await create_payment_intent(
            db,
            user_id=user_id,
            amount=float(amount),
            phone=phone,
            external_reference=external_reference,
            order_id=order_id,
            customer_name=customer_name,
            channel_id=int(doc["payhero_channel_id"]),
        )

        backend_url = os.environ.get("BACKEND_URL", "").rstrip("/")
        callback_url = f"{backend_url}/api/webhooks/payhero"

        try:
            result = await stk_push_for_user(
                doc,
                channel_id=int(doc["payhero_channel_id"]),
                phone=phone,
                amount=float(amount),
                external_reference=external_reference,
                callback_url=callback_url,
                customer_name=customer_name,
            )
            await mark_intent_stk_sent(db, intent["_id"], result)
        except httpx.HTTPStatusError as e:
            await mark_intent_failed(db, intent["_id"], e.response.text[:200])
            raise HTTPException(
                502, f"PayHero rejected the request: {e.response.text[:200]}"
            ) from e
        except Exception as e:
            await mark_intent_failed(db, intent["_id"], str(e))
            raise HTTPException(502, f"PayHero error: {e}") from e

        return {
            "status": "sent",
            "intent_id": str(intent["_id"]),
            "fee_quote": {
                "payhero_fee_kes": quote.payhero_fee_kes,
                "merchant_receives_kes": quote.merchant_receives_kes,
            },
            "payhero_response": result,
        }

    @api_router.post("/webhooks/payhero")
    async def payhero_webhook(request: Request, background_tasks: BackgroundTasks):
        try:
            payload = await request.json()
        except Exception:
            return {"status": "ok"}

        parsed = parse_webhook(payload)
        logging.info(
            "[PayHero webhook] status=%s phone=%s amount=%s ref=%s",
            parsed["status"],
            parsed["phone"],
            parsed["amount"],
            parsed["external_ref"],
        )

        if not parsed["success"]:
            return {"status": "ok", "note": "non-success event acknowledged"}

        background_tasks.add_task(_payhero_process_and_notify, db, payload, parsed)
        return {"status": "ok"}


async def _payhero_process_and_notify(db, payload: dict, parsed: dict):
    try:
        ctx = await process_payment(db, parsed, raw_payload=payload)
    except Exception as e:
        logging.error("[PayHero] process_payment error: %s", e)
        return

    if not ctx.get("handled"):
        logging.warning("[PayHero] Payment not handled: %s", ctx.get("reason"))
        return

    user_id = ctx["user_id"]
    user = ctx["user"]
    customer_name = ctx["customer_name"]
    phone = ctx["phone"]
    amount = ctx["amount"]
    order_number = ctx.get("order_number")
    provider_ref = ctx.get("provider_ref", "")
    fee = ctx.get("payhero_fee_kes")

    receipt_lines = [f"✅ *Payment Received — KES {int(amount):,}*"]
    if order_number:
        receipt_lines.append(f"Order: *{order_number}*")
    if provider_ref:
        receipt_lines.append(f"M-Pesa Ref: *{provider_ref}*")
    receipt_lines.append("Thank you! We'll process your order shortly. 🙏")
    receipt_text = "\n".join(receipt_lines)

    try:
        from whatsapp_service import get_whatsapp_service

        ws = get_whatsapp_service(db)
        await ws.send_message(
            user_id=str(user_id),
            to_number=phone,
            message=receipt_text,
            customer_name=customer_name,
            send_context="payment_receipt",
        )
    except Exception as e:
        logging.error("[PayHero] WhatsApp receipt failed: %s", e)

    push_token = user.get("push_token")
    if push_token:
        try:
            from notification_service import get_notification_service

            ns = get_notification_service()
            title = f"💰 KES {int(amount):,} received"
            body = customer_name + (
                f" — {order_number}" if order_number else ""
            ) + (f" (Ref: {provider_ref})" if provider_ref else "")
            if fee is not None:
                body += f" · est. PayHero fee KES {fee}"
            await ns.send_notification(
                push_token=push_token,
                title=title,
                body=body,
                data={"type": "payment_received"},
            )
        except Exception as e:
            logging.error("[PayHero] Push notification failed: %s", e)

    try:
        from workflows.engine import fire_trigger
        from workflows.models import WorkflowEvent
        from whatsapp_service import get_whatsapp_service

        ws = get_whatsapp_service(db)
        event = WorkflowEvent(
            trigger_type="payhero_payment_received",
            user_id=user_id,
            customer_id=ctx.get("customer_id"),
            from_number=phone,
            data={
                "amount": amount,
                "order_number": order_number,
                "provider_ref": provider_ref,
                "customer_name": customer_name,
                "payhero_fee_kes": fee,
            },
        )
        await fire_trigger(db, event, ws)
    except Exception as e:
        logging.error("[PayHero] Workflow trigger failed: %s", e)
