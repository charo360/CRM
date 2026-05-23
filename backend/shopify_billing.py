"""Shopify Billing API — recurring subscription charges.

Plans are defined here. Prices and trial days are env-var overridable
so they can be updated without code changes.

Flow:
  1. After OAuth → redirect merchant to plan selection page
  2. Merchant picks plan → POST /shopify/billing/create → get confirmation_url
  3. Redirect to Shopify billing page → merchant approves
  4. Shopify sends merchant to /shopify/billing/confirm?charge_id=...
  5. We activate the charge → store plan on user document
  6. Redirect to dashboard

On reinstall: charge must be re-created and re-approved (Shopify rule 1.2.2).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_API_VERSION = "2024-01"

# ── Plan definitions ──────────────────────────────────────────────────────────
# Prices are read from env so they can be updated without a code deploy.
# Feature limits are stored but NOT enforced yet — enforcement comes later.

PLANS: Dict[str, Dict[str, Any]] = {
    "starter": {
        "id":          "starter",
        "name":        "Starter",
        "price":       float(os.environ.get("SHOPIFY_PLAN_STARTER_PRICE", "49.00")),
        "trial_days":  int(os.environ.get("SHOPIFY_TRIAL_DAYS", "14")),
        "messages":    5_000,
        "customers":   None,   # Unlimited
        "features": [
            "5,000 messages/month",
            "Unlimited customers",
            "AI replies",
            "Follow-ups & broadcasts",
        ],
    },
    "growth": {
        "id":          "growth",
        "name":        "Growth",
        "price":       float(os.environ.get("SHOPIFY_PLAN_GROWTH_PRICE", "79.00")),
        "trial_days":  int(os.environ.get("SHOPIFY_TRIAL_DAYS", "14")),
        "messages":    10_000,
        "customers":   None,
        "features": [
            "10,000 messages/month",
            "Unlimited customers",
            "AI replies",
            "Follow-ups & broadcasts",
            "Priority support",
        ],
    },
    "pro": {
        "id":          "pro",
        "name":        "Pro",
        "price":       float(os.environ.get("SHOPIFY_PLAN_PRO_PRICE", "200.00")),
        "trial_days":  int(os.environ.get("SHOPIFY_TRIAL_DAYS", "14")),
        "messages":    25_000,
        "customers":   None,
        "features": [
            "25,000 messages/month",
            "Unlimited customers",
            "AI replies",
            "Follow-ups & broadcasts",
            "Dedicated support",
            "Advanced analytics",
            "Custom templates",
        ],
    },
}


def _headers(token: str) -> Dict[str, str]:
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }


def _base(shop: str) -> str:
    return f"https://{shop}/admin/api/{_API_VERSION}"


async def create_charge(
    shop: str,
    access_token: str,
    plan_id: str,
    return_url: str,
    test: bool = False,
) -> Dict[str, Any]:
    """Create a RecurringApplicationCharge and return Shopify's confirmation URL.

    Args:
        shop:         Store domain (e.g. "mystore.myshopify.com").
        access_token: Shopify offline access token.
        plan_id:      One of "starter", "growth", "pro".
        return_url:   URL Shopify redirects to after merchant approves/declines.
        test:         True in dev — charge won't bill the merchant.

    Returns:
        {"charge_id": ..., "confirmation_url": ..., "plan": ...}
    """
    plan = PLANS.get(plan_id)
    if not plan:
        raise ValueError(f"Unknown plan: {plan_id}")

    payload = {
        "recurring_application_charge": {
            "name":        f"Zilo CRM — {plan['name']}",
            "price":       plan["price"],
            "return_url":  return_url,
            "trial_days":  plan["trial_days"],
            "test":        test,
        }
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_base(shop)}/recurring_application_charges.json",
            json=payload,
            headers=_headers(access_token),
        )

    if resp.status_code not in (200, 201):
        logger.error(
            "[shopify-billing] create_charge failed shop=%s plan=%s status=%d body=%s",
            shop, plan_id, resp.status_code, resp.text[:300],
        )
        raise RuntimeError(f"Shopify billing API error {resp.status_code}: {resp.text[:200]}")

    charge = resp.json().get("recurring_application_charge", {})
    logger.info(
        "[shopify-billing] charge created shop=%s plan=%s charge_id=%s",
        shop, plan_id, charge.get("id"),
    )
    return {
        "charge_id":        charge["id"],
        "confirmation_url": charge["confirmation_url"],
        "status":           charge.get("status"),
        "plan":             plan_id,
    }


async def get_charge(
    shop: str,
    access_token: str,
    charge_id: int,
) -> Dict[str, Any]:
    """Fetch a charge from Shopify and return its current status."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_base(shop)}/recurring_application_charges/{charge_id}.json",
            headers=_headers(access_token),
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Shopify billing API error {resp.status_code}")
    return resp.json().get("recurring_application_charge", {})


async def activate_charge(
    shop: str,
    access_token: str,
    charge_id: int,
) -> Dict[str, Any]:
    """Activate an accepted charge. Must be called before it expires (~48 h)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_base(shop)}/recurring_application_charges/{charge_id}/activate.json",
            json={"recurring_application_charge": {"id": charge_id}},
            headers=_headers(access_token),
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Shopify activate_charge failed {resp.status_code}: {resp.text[:200]}"
        )
    charge = resp.json().get("recurring_application_charge", {})
    logger.info(
        "[shopify-billing] charge activated shop=%s charge_id=%s status=%s",
        shop, charge_id, charge.get("status"),
    )
    return charge


async def cancel_charge(
    shop: str,
    access_token: str,
    charge_id: int,
) -> bool:
    """Cancel (delete) an active recurring charge — called on app uninstall."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(
            f"{_base(shop)}/recurring_application_charges/{charge_id}.json",
            headers=_headers(access_token),
        )
    success = resp.status_code in (200, 204)
    logger.info(
        "[shopify-billing] cancel_charge shop=%s charge_id=%s success=%s",
        shop, charge_id, success,
    )
    return success


async def get_active_charge(
    shop: str,
    access_token: str,
) -> Optional[Dict[str, Any]]:
    """Return the currently active charge for this shop, or None."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_base(shop)}/recurring_application_charges.json",
            headers=_headers(access_token),
        )
    if resp.status_code != 200:
        return None
    charges = resp.json().get("recurring_application_charges", [])
    for c in charges:
        if c.get("status") == "active":
            return c
    return None
