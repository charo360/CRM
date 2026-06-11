"""
Flutterwave auth helpers — platform keys and user document fields.
"""
from __future__ import annotations

import re
import secrets
from typing import Optional

from payhero_auth import business_owner_id, user_id_filter

from flutterwave_credentials import (
    flutterwave_connected,
    platform_secret_key,
)

FLUTTERWAVE_BASE = "https://api.flutterwave.com/v3"


def secret_key_from_doc(doc: Optional[dict]) -> Optional[str]:
    if not doc or not flutterwave_connected(doc):
        return None
    return platform_secret_key()


def new_transaction_reference(user_id: str, external_ref: str = "") -> str:
    suffix = secrets.token_hex(4)
    base = re.sub(r"[^a-zA-Z0-9_-]", "", (external_ref or "crm"))[:32]
    uid = re.sub(r"[^a-zA-Z0-9]", "", str(user_id))[-8:]
    return f"crm_fw_{uid}_{base}_{suffix}"[:64]
