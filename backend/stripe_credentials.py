"""
Stripe Connect — platform secret key and merchant split (destination charges).

Merchants onboard as Express connected accounts; checkout uses destination
charges with application_fee_amount (platform keeps 100 - merchant_transfer_percent).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

# Express Connect + destination charges: connected account country must support the
# `card_payments` capability (see https://stripe.com/global). Kenya, Nigeria, Ghana,
# and similar markets need cross-border Connect (not supported in this CRM flow).
STRIPE_CONNECT_COUNTRIES: Tuple[str, ...] = (
    "US",
    "GB",
    "IE",
    "CA",
    "AU",
    "NZ",
    "AT",
    "BE",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "FR",
    "DE",
    "GR",
    "HU",
    "IT",
    "LV",
    "LT",
    "LU",
    "MT",
    "NL",
    "NO",
    "PL",
    "PT",
    "RO",
    "SK",
    "SI",
    "ES",
    "SE",
    "CH",
    "MX",
    "BR",
    "SG",
    "HK",
    "JP",
    "IN",
    "MY",
    "TH",
    "ZA",
)

_STRIPE_CONNECT_COUNTRY_SET = frozenset(STRIPE_CONNECT_COUNTRIES)

# Default Connect country when a currency is chosen in Integrations.
CURRENCY_DEFAULT_COUNTRY: Dict[str, str] = {
    "USD": "US",
    "EUR": "IE",
    "GBP": "GB",
    "CAD": "CA",
    "AUD": "AU",
    "NZD": "NZ",
    "CHF": "CH",
    "SEK": "SE",
    "NOK": "NO",
    "DKK": "DK",
    "PLN": "PL",
    "CZK": "CZ",
    "HUF": "HU",
    "RON": "RO",
    "BGN": "BG",
    "MXN": "MX",
    "BRL": "BR",
    "SGD": "SG",
    "HKD": "HK",
    "JPY": "JP",
    "INR": "IN",
    "MYR": "MY",
    "THB": "TH",
    "ZAR": "ZA",
}

# Checkout / onboarding currencies whose default country is Connect-eligible.
STRIPE_CURRENCIES = frozenset(
    cur
    for cur, cc in CURRENCY_DEFAULT_COUNTRY.items()
    if cc in _STRIPE_CONNECT_COUNTRY_SET
)

ZERO_DECIMAL_CURRENCIES = frozenset(
    {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
)


def platform_configured() -> bool:
    return platform_secret_key() is not None


def platform_secret_key() -> Optional[str]:
    key = (
        os.environ.get("STRIPE_PLATFORM_SECRET_KEY")
        or os.environ.get("STRIPE_SECRET_KEY")
        or ""
    ).strip()
    if key.startswith("sk_"):
        return key
    return None


def webhook_secret_platform() -> Optional[str]:
    h = (
        os.environ.get("STRIPE_WEBHOOK_SECRET")
        or os.environ.get("STRIPE_WEBHOOK_SECRET_PLATFORM")
        or ""
    ).strip()
    return h or None


def webhook_secret_connect() -> Optional[str]:
    h = (os.environ.get("STRIPE_WEBHOOK_SECRET_CONNECT") or "").strip()
    return h or None


def stripe_api_version() -> str:
    return (os.environ.get("STRIPE_API_VERSION") or "2026-04-22.dahlia").strip()


def merchant_transfer_percent() -> float:
    """Share of gross (before Stripe fees) routed to the connected account."""
    raw = (os.environ.get("STRIPE_MERCHANT_TRANSFER_PERCENT") or "90").strip()
    try:
        v = float(raw)
    except ValueError:
        v = 90.0
    return max(0.0, min(100.0, v))


def platform_fee_percent() -> float:
    return round(100.0 - merchant_transfer_percent(), 4)


def amount_to_minor(major: float, currency: str) -> int:
    cur = currency.upper()
    if cur in ZERO_DECIMAL_CURRENCIES:
        return int(round(float(major)))
    return int(round(float(major) * 100))


def minor_to_major(minor: int, currency: str) -> float:
    cur = currency.upper()
    if cur in ZERO_DECIMAL_CURRENCIES:
        return float(minor)
    return float(minor) / 100.0


def application_fee_minor(total_minor: int, currency: str) -> int:
    pct = platform_fee_percent()
    if pct <= 0 or total_minor <= 0:
        return 0
    fee = int(round(total_minor * pct / 100.0))
    return max(0, min(fee, total_minor))


def stripe_connected(doc: Optional[dict]) -> bool:
    if not doc or not platform_configured():
        return False
    acct = (doc.get("stripe_connect_account_id") or "").strip()
    return acct.startswith("acct_")


def stripe_checkout_ready(doc: Optional[dict]) -> bool:
    if not stripe_connected(doc):
        return False
    return bool(doc.get("stripe_charges_enabled"))


def stripe_connection_status(doc: Optional[dict]) -> str:
    """UI-facing lifecycle: not_connected | onboarding | verification_pending | ready."""
    if not stripe_connected(doc):
        return "not_connected"
    if stripe_checkout_ready(doc):
        return "ready"
    if doc.get("stripe_details_submitted") and not doc.get("stripe_charges_enabled"):
        return "verification_pending"
    return "onboarding"


def public_setup_card() -> Dict[str, Any]:
    return {
        "platform_available": platform_configured(),
        "currencies": sorted(STRIPE_CURRENCIES),
        "countries": list(STRIPE_CONNECT_COUNTRIES),
        "default_currency": "USD",
        "default_country": "US",
        "merchant_transfer_percent": merchant_transfer_percent(),
        "platform_fee_percent": platform_fee_percent(),
        "connect_note": (
            "Countries listed support Express Connect with card checkout. "
            "For Kenya, Nigeria, or Ghana use Paystack or PayHero in Integrations."
        ),
    }
