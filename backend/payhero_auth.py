"""
PayHero API authentication per https://docs.payhero.co.ke/docs/authorization

Use the Basic Authorization token from PayHero Dashboard → API Keys (not login password).
"""
from __future__ import annotations

import base64
import re
from typing import Any, Dict, Optional, Tuple

import httpx

PAYHERO_BASE = "https://backend.payhero.co.ke/api/v2"

_OBJECT_ID_HEX = re.compile(r"^[0-9a-fA-F]{24}$")


def _strip_basic_prefix(value: str) -> str:
    s = value.strip()
    if s.lower().startswith("basic "):
        return s[6:].strip()
    return s


def format_basic_authorization(credential: str) -> str:
    """Build `Authorization` header value from pasted token or base64 secret."""
    c = (credential or "").strip()
    if not c:
        raise ValueError("Empty credential")
    if c.lower().startswith("basic "):
        c = c[6:].strip()
    return f"Basic {c}"


def credentials_from_connect_body(body: dict) -> Tuple[str, Dict[str, Any]]:
    """
    Parse connect payload. Returns (Authorization header value, fields to store on user).
    """
    api_token = (
        (body.get("api_token") or body.get("auth_token") or body.get("token") or "")
    ).strip()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    label = (body.get("label") or username or "PayHero").strip()[:80]

    if api_token:
        auth = format_basic_authorization(api_token)
        return auth, {
            "payhero_api_token": _strip_basic_prefix(api_token),
            "payhero_username": label,
            "payhero_password": "",
        }

    # Single field: user pasted token into username only
    if username and not password:
        auth = format_basic_authorization(username)
        return auth, {
            "payhero_api_token": _strip_basic_prefix(username),
            "payhero_username": label or "API Key",
            "payhero_password": "",
        }

    if username and password:
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        auth = format_basic_authorization(encoded)
        return auth, {
            "payhero_username": username,
            "payhero_password": password,
        }

    raise ValueError("Provide your PayHero API Basic Auth token (from API Keys)")


def authorization_from_user_doc(doc: Optional[dict]) -> Optional[str]:
    if not doc:
        return None
    token = (doc.get("payhero_api_token") or "").strip()
    if token:
        return format_basic_authorization(token)
    username = (doc.get("payhero_username") or "").strip()
    password = (doc.get("payhero_password") or "").strip()
    if username and password:
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return format_basic_authorization(encoded)
    if username:
        return format_basic_authorization(username)
    return None


def payhero_connected(doc: Optional[dict]) -> bool:
    if not doc:
        return False
    if (doc.get("payhero_api_token") or "").strip():
        return True
    return bool((doc.get("payhero_username") or "").strip())


def business_owner_id(user: dict) -> Any:
    return user.get("business_id") or user["_id"]


def user_id_filter(uid: Any) -> dict:
    if isinstance(uid, str) and _OBJECT_ID_HEX.match(uid):
        try:
            from bson import ObjectId

            return {"_id": ObjectId(uid)}
        except Exception:
            pass
    return {"_id": uid}


async def verify_payhero_credentials(auth_header: str) -> None:
    """Call PayHero until a known channels endpoint accepts the token."""
    paths = ("/payment_channels", "/channels")
    last_status = 0
    last_body = ""
    timeout = httpx.Timeout(12.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for path in paths:
            try:
                r = await client.get(
                    f"{PAYHERO_BASE}{path}",
                    headers={
                        "Authorization": auth_header,
                        "Content-Type": "application/json",
                    },
                )
            except httpx.TimeoutException:
                raise ValueError(
                    "PayHero API timed out. Check your internet connection and try again."
                ) from None
            except httpx.RequestError as e:
                raise ValueError(
                    f"Could not reach PayHero ({e}). Check your network and try again."
                ) from e
            last_status = r.status_code
            last_body = (r.text or "")[:300]
            if r.status_code == 200:
                return
            if r.status_code == 401:
                raise ValueError(
                    "PayHero rejected this token (401). In PayHero Dashboard → API Keys, "
                    "create a key and paste the full Basic Authorization token here."
                )
    if last_status == 404:
        raise ValueError("PayHero API endpoint not found — try again later.")
    raise ValueError(
        f"PayHero could not verify credentials (HTTP {last_status}). {last_body}".strip()
    )
