"""
Per-merchant Paystack credentials (secret key on business user document).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from payhero_auth import business_owner_id, user_id_filter

_OBJECT_ID_HEX = re.compile(r"^[0-9a-fA-F]{24}$")

PAYSTACK_BASE = "https://api.paystack.co"

# ISO 4217 — amount sent to Paystack is in smallest currency unit (× multiplier).
CURRENCY_SUBUNIT = {
    "NGN": 100,
    "GHS": 100,
    "ZAR": 100,
    "KES": 100,
    "USD": 100,
    "XOF": 1,
}


def secret_key_from_doc(doc: Optional[dict]) -> Optional[str]:
    from paystack_credentials import resolve_secret_key

    return resolve_secret_key(doc)


def paystack_connected(doc: Optional[dict]) -> bool:
    from paystack_credentials import paystack_connected as _connected

    return _connected(doc)


def parse_connect_body(body: dict) -> Dict[str, Any]:
    secret_key = (body.get("secret_key") or "").strip()
    if not secret_key or not secret_key.startswith("sk_"):
        raise ValueError("Invalid Paystack secret key (must start with sk_)")
    currency = (body.get("currency") or body.get("default_currency") or "NGN").strip().upper()
    if currency not in CURRENCY_SUBUNIT:
        raise ValueError(f"Unsupported currency '{currency}'")
    from paystack_credentials import PAYSTACK_AUTH_MERCHANT

    return {
        "paystack_secret_key": secret_key,
        "paystack_business_name": "",
        "paystack_default_currency": currency,
        "paystack_auth_mode": PAYSTACK_AUTH_MERCHANT,
    }


def amount_to_subunit(amount: float, currency: str) -> int:
    mult = CURRENCY_SUBUNIT.get(currency.upper(), 100)
    return int(round(float(amount) * mult))


def subunit_to_major(amount_subunit: int, currency: str) -> float:
    mult = CURRENCY_SUBUNIT.get(currency.upper(), 100)
    if mult <= 0:
        return float(amount_subunit)
    return float(amount_subunit) / mult
