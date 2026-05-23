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
from paystack_auth import (
    parse_connect_body,
    paystack_connected,
    secret_key_from_doc,
)
from paystack_billing import ensure_paystack_indexes, list_recent_ledger, usage_summary
from paystack_client import PaystackApiError, PaystackClient
from paystack_service import (
    initialize_checkout_for_user,
    parse_webhook_event,
    process_charge_success,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)


def register_paystack_routes(
    api_router: APIRouter,
    db,
    get_current_user: Callable,
) -> None:

    @api_router.get("/paystack/connection")
    async def paystack_get_connection(user=Depends(get_current_user)):
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "paystack_secret_key": 1,
                "paystack_business_name": 1,
                "paystack_default_currency": 1,
            },
        )
        connected = paystack_connected(doc)
        return {
            "connected": connected,
            "business_name": (doc or {}).get("paystack_business_name") if connected else None,
            "default_currency": (doc or {}).get("paystack_default_currency") if connected else None,
        }

    @api_router.post("/paystack/connect")
    async def paystack_connect(body: dict, user=Depends(get_current_user)):
        try:
            fields = parse_connect_body(body or {})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        secret = fields["paystack_secret_key"]
        try:
            biz = await PaystackClient(secret).fetch_business()
            fields["paystack_business_name"] = (biz.get("name") or biz.get("business_name") or "")[:120]
        except PaystackApiError as e:
            msg = str(e).strip() or "Invalid key"
            if msg.lower() in ("paystack http 404", "paystack http 401"):
                msg = "Paystack rejected this key — use a valid test or live secret key"
            raise HTTPException(status_code=400, detail=msg) from e
        except Exception as e:
            logger.exception("[Paystack] connect verify failed")
            raise HTTPException(status_code=502, detail=f"Paystack unreachable: {e}") from e

        owner_id = business_owner_id(user)
        result = await db.users.update_one(user_id_filter(owner_id), {"$set": fields})
        if result.matched_count == 0:
            raise HTTPException(404, "Business account not found")
        return {
            "status": "connected",
            "connected": True,
            "business_name": fields.get("paystack_business_name") or "Connected",
            "default_currency": fields.get("paystack_default_currency"),
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
            {"paystack_secret_key": 1, "paystack_default_currency": 1},
        )
        if not paystack_connected(doc):
            raise HTTPException(400, "Paystack not connected — add your secret key in Integrations")

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
            {"paystack_secret_key": 1},
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
            {"paystack_secret_key": 1},
        )
        secret = secret_key_from_doc(user_doc)
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
