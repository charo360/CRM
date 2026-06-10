"""
Resolve PayHero API credentials: platform (Sam CRM) vs per-merchant (legacy).

Platform mode scales many tenants on one PayHero account; each merchant only
registers their paybill/till/bank channel. Webhooks route by payhero_channel_id.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

from payhero_auth import authorization_from_user_doc, format_basic_authorization

PAYHERO_AUTH_PLATFORM = "platform"
PAYHERO_AUTH_MERCHANT = "merchant"

VALID_CHANNEL_TYPES = frozenset({"paybill", "till", "bank"})


def platform_configured() -> bool:
    return bool((os.environ.get("PAYHERO_PLATFORM_API_TOKEN") or "").strip())


def platform_account_id() -> Optional[int]:
    raw = (os.environ.get("PAYHERO_PLATFORM_ACCOUNT_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def platform_authorization_header() -> Optional[str]:
    token = (os.environ.get("PAYHERO_PLATFORM_API_TOKEN") or "").strip()
    if not token:
        return None
    return format_basic_authorization(token)


def payhero_auth_mode(doc: Optional[dict]) -> Optional[str]:
    if not doc:
        return None
    mode = (doc.get("payhero_auth_mode") or "").strip().lower()
    if mode in (PAYHERO_AUTH_PLATFORM, PAYHERO_AUTH_MERCHANT):
        return mode
    if (doc.get("payhero_api_token") or "").strip() or (
        doc.get("payhero_username") or ""
    ).strip():
        return PAYHERO_AUTH_MERCHANT
    if doc.get("payhero_channel_id") and platform_configured():
        return PAYHERO_AUTH_PLATFORM
    return None


def payhero_connected(doc: Optional[dict]) -> bool:
    """Connected when we can take payments (channel) or legacy merchant API creds."""
    if not doc:
        return False
    if doc.get("payhero_channel_id"):
        return True
    return bool((doc.get("payhero_api_token") or "").strip()) or bool(
        (doc.get("payhero_username") or "").strip()
    )


def resolve_authorization_header(doc: Optional[dict]) -> Optional[str]:
    if not doc:
        return None
    mode = payhero_auth_mode(doc)
    if mode == PAYHERO_AUTH_PLATFORM:
        return platform_authorization_header()
    return authorization_from_user_doc(doc)


def channel_connect_fields_from_body(body: dict) -> Dict[str, Any]:
    """Merchant-facing M-Pesa destination (no API keys)."""
    channel_type = (body.get("channel_type") or body.get("type") or "").strip().lower()
    short_code = (body.get("short_code") or body.get("paybill") or body.get("till") or "").strip()
    account_number = (
        body.get("account_number") or body.get("account") or ""
    ).strip()
    description = (
        body.get("description") or body.get("label") or body.get("name") or ""
    ).strip()

    if channel_type not in VALID_CHANNEL_TYPES:
        raise ValueError("Choose destination type: Paybill, Till, or Bank")
    if not short_code:
        raise ValueError("Short code / paybill / till number is required")
    if not description:
        raise ValueError("Business or bank name is required")
    if channel_type in ("paybill", "bank") and not account_number:
        raise ValueError("Account number is required for Paybill and Bank")

    if channel_type == "till" and not account_number:
        account_number = short_code

    digits = re.sub(r"\D", "", short_code)
    if not digits:
        raise ValueError("Short code must be a valid number")

    return {
        "channel_type": channel_type,
        "short_code": digits,
        "account_number": account_number[:64],
        "description": description[:120],
        "display_label": description[:80] or digits,
    }
