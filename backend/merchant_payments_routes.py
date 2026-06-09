"""
Manage Payment dashboard API — unified ledger, default provider, refunds.
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException

from payhero_auth import business_owner_id, user_id_filter
from merchant_payments_service import (
    PROVIDERS,
    connected_connections_only,
    connected_provider_keys,
    connection_snapshot,
    issue_full_refund,
    list_unified_transactions,
)

logger = logging.getLogger(__name__)


def register_merchant_payments_routes(
    api_router: APIRouter,
    db,
    get_current_user: Callable,
) -> None:

    @api_router.get("/merchant-payments/overview")
    async def merchant_payments_overview(limit: int = 50, user=Depends(get_current_user)):
        owner_id = str(business_owner_id(user))
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "paystack_secret_key": 1,
                "paystack_auth_mode": 1,
                "paystack_business_name": 1,
                "paystack_default_currency": 1,
                "paystack_subaccount_code": 1,
                "stripe_connect_account_id": 1,
                "stripe_business_name": 1,
                "stripe_default_currency": 1,
                "stripe_charges_enabled": 1,
                "stripe_payouts_enabled": 1,
                "stripe_details_submitted": 1,
                "flutterwave_secret_key": 1,
                "flutterwave_auth_mode": 1,
                "flutterwave_business_name": 1,
                "flutterwave_default_currency": 1,
                "flutterwave_subaccount_id": 1,
                "payhero_api_token": 1,
                "payhero_username": 1,
                "payhero_channel_id": 1,
                "payhero_auth_mode": 1,
                "merchant_default_payment_provider": 1,
            },
        )
        preferred = (doc or {}).get("merchant_default_payment_provider") or ""
        if preferred and preferred not in PROVIDERS:
            preferred = ""
        connected = connected_provider_keys(doc)
        if preferred and preferred not in connected:
            preferred = ""
        return {
            "connected_providers": connected,
            "connections": connected_connections_only(doc),
            "preferred_provider": preferred or None,
            "transactions": await list_unified_transactions(
                db,
                owner_id,
                user_doc=doc,
                limit=min(limit, 100),
            ),
        }

    @api_router.put("/merchant-payments/preferred-provider")
    async def merchant_payments_set_preferred(body: dict, user=Depends(get_current_user)):
        provider = (body.get("provider") or "").strip().lower()
        if provider and provider not in PROVIDERS:
            raise HTTPException(400, "provider must be paystack, stripe, flutterwave, payhero, or null")
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "paystack_secret_key": 1,
                "paystack_auth_mode": 1,
                "stripe_connect_account_id": 1,
                "stripe_charges_enabled": 1,
                "stripe_payouts_enabled": 1,
                "stripe_details_submitted": 1,
                "flutterwave_secret_key": 1,
                "flutterwave_auth_mode": 1,
                "payhero_api_token": 1,
                "payhero_username": 1,
                "payhero_channel_id": 1,
                "payhero_auth_mode": 1,
            },
        )
        if provider:
            snap = connection_snapshot(doc)
            if not snap.get(provider, {}).get("connected"):
                raise HTTPException(
                    400,
                    f"Connect {provider} in Integrations before setting it as default",
                )
            if provider == "stripe" and not snap["stripe"].get("checkout_ready"):
                raise HTTPException(400, "Finish Stripe Connect onboarding before using it as default")
            if provider == "payhero" and not doc.get("payhero_channel_id"):
                raise HTTPException(400, "Select a PayHero channel before using it as default")
        if provider:
            await db.users.update_one(
                user_id_filter(business_owner_id(user)),
                {"$set": {"merchant_default_payment_provider": provider}},
            )
        else:
            await db.users.update_one(
                user_id_filter(business_owner_id(user)),
                {"$unset": {"merchant_default_payment_provider": ""}},
            )
        return {"preferred_provider": provider or None}

    @api_router.post("/merchant-payments/refund")
    async def merchant_payments_refund(body: dict, user=Depends(get_current_user)):
        provider = (body.get("provider") or "").strip().lower()
        ledger_id = (body.get("ledger_id") or body.get("transaction_id") or "").strip()
        if not provider or not ledger_id:
            raise HTTPException(400, "provider and ledger_id are required")

        owner_id = str(business_owner_id(user))
        doc = await db.users.find_one(
            user_id_filter(business_owner_id(user)),
            {
                "paystack_secret_key": 1,
                "paystack_auth_mode": 1,
                "stripe_connect_account_id": 1,
                "stripe_charges_enabled": 1,
                "stripe_payouts_enabled": 1,
                "stripe_details_submitted": 1,
                "flutterwave_secret_key": 1,
                "flutterwave_auth_mode": 1,
                "payhero_api_token": 1,
                "payhero_username": 1,
                "payhero_channel_id": 1,
                "payhero_auth_mode": 1,
            },
        )
        try:
            result = await issue_full_refund(
                db,
                doc or {},
                user_id=owner_id,
                provider=provider,
                ledger_id=ledger_id,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            logger.exception("[merchant-payments] refund failed")
            raise HTTPException(502, f"Refund failed: {e}") from e
        return result
