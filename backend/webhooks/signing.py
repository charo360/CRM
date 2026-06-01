"""
HMAC signature helpers for outbound webhooks.

Every webhook POST includes two headers:
  X-Zilo-Signature: sha256=<hex-digest>
  X-Zilo-Timestamp: <unix-epoch-seconds>

The signature is computed as:
  HMAC-SHA256(secret, f"{timestamp}.{json_body}")

Receivers should:
  1. Read X-Zilo-Timestamp — reject if more than 300 s in the past.
  2. Compute expected = HMAC-SHA256(secret, f"{ts}.{raw_body}")
  3. Compare with X-Zilo-Signature using constant-time comparison.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Tuple


def sign_payload(secret: str, body: str, *, timestamp: int | None = None) -> Tuple[str, int]:
    """Return (signature_header_value, unix_timestamp) for a webhook payload.

    Args:
        secret:    The tenant's webhook signing secret (plain string).
        body:      The JSON-serialized payload string.
        timestamp: Override the timestamp (for testing). Defaults to now.

    Returns:
        A 2-tuple: (signature, timestamp) where signature is the full header
        value including the "sha256=" prefix.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    msg = f"{ts}.{body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"sha256={digest}", ts


def verify_signature(
    secret: str,
    body: str,
    signature_header: str,
    timestamp_header: str | int,
    *,
    max_age_sec: int = 300,
) -> bool:
    """Verify an incoming webhook signature (for webhook echo endpoints / tests).

    Returns True if the signature is valid and the timestamp is fresh.
    """
    try:
        ts = int(timestamp_header)
        if abs(time.time() - ts) > max_age_sec:
            return False
        expected, _ = sign_payload(secret, body, timestamp=ts)
        return hmac.compare_digest(expected, signature_header)
    except Exception:
        return False
