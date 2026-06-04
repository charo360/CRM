"""
Stripe Connect auth helpers.
"""
from __future__ import annotations

import re
import secrets
from typing import Optional

from payhero_auth import business_owner_id, user_id_filter

from stripe_credentials import platform_secret_key, stripe_connected

__all__ = ["business_owner_id", "user_id_filter", "new_checkout_reference", "stripe_connected", "platform_secret_key"]


def new_checkout_reference(user_id: str, external_ref: str = "") -> str:
    suffix = secrets.token_hex(4)
    base = re.sub(r"[^a-zA-Z0-9_-]", "", (external_ref or "crm"))[:32]
    uid = re.sub(r"[^a-zA-Z0-9]", "", str(user_id))[-8:]
    return f"crm_st_{uid}_{base}_{suffix}"[:64]
