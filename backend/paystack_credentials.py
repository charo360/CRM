"""
Paystack credentials: platform (Sam CRM) vs per-merchant secret key (legacy).

Platform mode stores no secret on the user document; payments use
PAYSTACK_PLATFORM_SECRET_KEY and route webhooks via metadata / intent reference.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from paystack_auth import CURRENCY_SUBUNIT

PAYSTACK_AUTH_PLATFORM = "platform"
PAYSTACK_AUTH_MERCHANT = "merchant"

PAYSTACK_PAYOUT_BANK = "bank"
PAYSTACK_PAYOUT_MOBILE_MONEY = "mobile_money"
PAYSTACK_PAYOUT_TYPES = (PAYSTACK_PAYOUT_BANK, PAYSTACK_PAYOUT_MOBILE_MONEY)

# Zilo's platform flow is deliberately Kenya-only. Other Paystack countries
# connect their own merchant account rather than being placed below Zilo's
# Paystack account.
PAYSTACK_PLATFORM_COUNTRY = "KE"
PAYSTACK_PLATFORM_CURRENCY = "KES"
PAYSTACK_MOBILE_MONEY_CURRENCIES = frozenset({PAYSTACK_PLATFORM_CURRENCY})


def platform_configured() -> bool:
    return platform_secret_key() is not None


def platform_secret_key() -> Optional[str]:
    key = (os.environ.get("PAYSTACK_PLATFORM_SECRET_KEY") or "").strip()
    if key.startswith("sk_"):
        return key
    return None


def paystack_auth_mode(doc: Optional[dict]) -> Optional[str]:
    if not doc:
        return None
    mode = (doc.get("paystack_auth_mode") or "").strip().lower()
    if mode in (PAYSTACK_AUTH_PLATFORM, PAYSTACK_AUTH_MERCHANT):
        return mode
    if (doc.get("paystack_secret_key") or "").strip().startswith("sk_"):
        return PAYSTACK_AUTH_MERCHANT
    return None


def merchant_secret_from_doc(doc: Optional[dict]) -> Optional[str]:
    if not doc:
        return None
    key = (doc.get("paystack_secret_key") or "").strip()
    if key.startswith("sk_"):
        return key
    return None


def resolve_secret_key(doc: Optional[dict]) -> Optional[str]:
    if not doc:
        return platform_secret_key() if platform_configured() else None
    mode = paystack_auth_mode(doc)
    if mode == PAYSTACK_AUTH_PLATFORM:
        return platform_secret_key()
    return merchant_secret_from_doc(doc)


def paystack_connected(doc: Optional[dict]) -> bool:
    if not doc:
        return False
    mode = paystack_auth_mode(doc)
    if mode == PAYSTACK_AUTH_PLATFORM:
        return platform_configured()
    return merchant_secret_from_doc(doc) is not None


def platform_connect_fields(body: dict) -> Dict[str, Any]:
    """Merchant-facing connect — no API keys."""
    currency = (
        body.get("currency") or body.get("default_currency") or PAYSTACK_PLATFORM_CURRENCY
    ).strip().upper()
    if currency not in CURRENCY_SUBUNIT:
        raise ValueError(f"Unsupported currency '{currency}'")
    if currency != PAYSTACK_PLATFORM_CURRENCY:
        raise ValueError(
            "Zilo-managed Paystack payouts are available only in Kenya (KES). "
            "For other countries, connect your own Paystack account with its secret key."
        )
    payout_type = (body.get("payout_type") or body.get("payoutType") or "").strip().lower()
    if payout_type and payout_type not in PAYSTACK_PAYOUT_TYPES:
        raise ValueError("Invalid payout type. Use 'bank' or 'mobile_money'.")
    payout_type = payout_type or PAYSTACK_PAYOUT_BANK
    if payout_type == PAYSTACK_PAYOUT_MOBILE_MONEY and currency not in PAYSTACK_MOBILE_MONEY_CURRENCIES:
        supported = ", ".join(sorted(PAYSTACK_MOBILE_MONEY_CURRENCIES))
        raise ValueError(
            f"Mobile money subaccounts are not available for {currency} on Paystack. "
            f"Use Bank for {currency}, or choose {supported} for mobile money."
        )
    return {
        "paystack_auth_mode": PAYSTACK_AUTH_PLATFORM,
        "paystack_default_currency": currency,
        "paystack_payout_type": payout_type,
        "paystack_business_name": "",
    }


def public_setup_card() -> Dict[str, Any]:
    return {
        "platform_available": platform_configured(),
        "platform_country": PAYSTACK_PLATFORM_COUNTRY,
        "currencies": [PAYSTACK_PLATFORM_CURRENCY],
        "default_currency": PAYSTACK_PLATFORM_CURRENCY,
        "payout_types": list(PAYSTACK_PAYOUT_TYPES),
        "mobile_money_currencies": sorted(PAYSTACK_MOBILE_MONEY_CURRENCIES),
        "own_account_supported": True,
    }
