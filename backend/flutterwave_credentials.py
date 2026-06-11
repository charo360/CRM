"""
Flutterwave credentials — platform secret only (no merchant FLWSECK on user docs).

Subaccount split at connect: split_value is the percentage paid to the merchant
subaccount; the platform keeps (100 - split_value). Override via
FLUTTERWAVE_MERCHANT_SPLIT_PERCENT (default 90).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

# Checkout currencies supported in CRM (amounts sent in major units to Flutterwave).
FLUTTERWAVE_CURRENCIES = frozenset({"NGN", "KES", "GHS", "ZAR", "USD", "EUR", "GBP", "XAF", "XOF", "TZS", "UGX", "ZMW"})

CURRENCY_COUNTRY = {
    "NGN": "NG",
    "KES": "KE",
    "GHS": "GH",
    "ZAR": "ZA",
    "USD": "US",
    "EUR": "FR",
    "GBP": "GB",
    "XAF": "CM",
    "XOF": "SN",
    "TZS": "TZ",
    "UGX": "UG",
    "ZMW": "ZM",
}


def platform_configured() -> bool:
    return platform_secret_key() is not None


def platform_secret_key() -> Optional[str]:
    key = (os.environ.get("FLUTTERWAVE_PLATFORM_SECRET_KEY") or "").strip()
    if key.startswith("FLWSECK"):
        return key
    return None


def webhook_secret_hash() -> Optional[str]:
    h = (os.environ.get("FLUTTERWAVE_SECRET_HASH") or "").strip()
    return h or None


def merchant_split_percent() -> float:
    """
    Percentage of each payment settled to the merchant subaccount (0–100, human-readable).
    Platform commission = 100 - this value. Convert to API fraction via merchant_split_fraction().
    """
    raw = (os.environ.get("FLUTTERWAVE_MERCHANT_SPLIT_PERCENT") or "90").strip()
    try:
        v = float(raw)
    except ValueError:
        v = 90.0
    return max(0.0, min(100.0, v))


def merchant_split_fraction() -> float:
    """Flutterwave subaccount API: decimal share (0.9 = 90% to subaccount), not whole 90."""
    return round(merchant_split_percent() / 100.0, 4)


def flutterwave_connected(doc: Optional[dict]) -> bool:
    if not doc or not platform_configured():
        return False
    return bool((doc.get("flutterwave_subaccount_id") or "").strip())


def platform_connect_fields(body: dict) -> Dict[str, Any]:
    currency = (body.get("currency") or body.get("default_currency") or "NGN").strip().upper()
    if currency not in FLUTTERWAVE_CURRENCIES:
        raise ValueError(f"Unsupported currency '{currency}'")
    country = (body.get("country") or CURRENCY_COUNTRY.get(currency) or "").strip().upper()
    if len(country) != 2:
        raise ValueError("Country is required (2-letter code, e.g. NG, KE).")
    return {
        "flutterwave_default_currency": currency,
        "flutterwave_country": country,
    }


def public_setup_card() -> Dict[str, Any]:
    return {
        "platform_available": platform_configured(),
        "currencies": sorted(FLUTTERWAVE_CURRENCIES),
        "default_currency": "NGN",
        "merchant_split_percent": merchant_split_percent(),
    }
