"""
CJdropshipping API v2 client.

Auth flow:
  POST /v1/authentication/getAccessToken  { email, password=api_key }
  → { accessToken, refreshToken, expiresIn }

Access token is cached in-process until 5 min before expiry.
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger(__name__)

CJ_BASE = "https://developers.cjdropshipping.com/api2.0/v1"

# ── In-process token cache (per api_key) ────────────────────────────────────
_token_cache: Dict[str, Dict[str, Any]] = {}   # api_key → {access_token, refresh_token, expires_at}


def _parse_cj_key(raw: str):
    """
    CJ keys can come in two formats:
      1. plain UUID:  5752c1aa3fd64bf4952988c22b727283
      2. compound:    CJ5436522@api@5752c1aa3fd64bf4952988c22b727283
    Returns (email_hint, api_key).
    """
    if "@api@" in raw:
        parts = raw.split("@api@", 1)
        return parts[0], parts[1]
    return None, raw


def _cj_credentials() -> tuple[str, str]:
    """Return (email, api_key) from environment.  Raises if missing."""
    raw = os.environ.get("CJ_API_KEY", "").strip()
    if not raw:
        raise RuntimeError("CJ_API_KEY is not set in environment.")
    # Strip accidental duplicate prefix e.g. "CJ_API_KEY=CJ5436522@api@..."
    if raw.startswith("CJ_API_KEY="):
        raw = raw[len("CJ_API_KEY="):]
    email_hint, api_key = _parse_cj_key(raw)
    # Accept both CJ_API_EMAIL and CJ_EMAIL
    email = (
        os.environ.get("CJ_API_EMAIL", "").strip()
        or os.environ.get("CJ_EMAIL", "").strip()
        or email_hint
        or ""
    )
    if not email:
        raise RuntimeError(
            "CJ_API_EMAIL is not set. Add CJ_API_EMAIL=your@email.com to .env.local"
        )
    return email, api_key


async def _get_access_token() -> str:
    """Return a valid CJ access token, refreshing if needed."""
    email, api_key = _cj_credentials()
    cache = _token_cache.get(api_key)
    now = time.time()

    if cache and cache["expires_at"] > now + 300:
        return cache["access_token"]

    # Try refresh first if we have a refresh token
    if cache and cache.get("refresh_token"):
        try:
            token = await _refresh_token(cache["refresh_token"], api_key)
            if token:
                return token
        except Exception:
            pass

    # Full re-auth
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.post(
            f"{CJ_BASE}/authentication/getAccessToken",
            json={"email": email, "password": api_key},
        )
        data = r.json()

    if not r.is_success or data.get("result") is False:
        raise RuntimeError(f"CJ auth failed: {data.get('message', r.text[:200])}")

    d = data.get("data", {})
    access_token  = d.get("accessToken", "")
    refresh_token = d.get("refreshToken", "")
    expires_at    = _parse_expiry(d.get("accessTokenExpiryDate"), now + 86400)

    _token_cache[api_key] = {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "expires_at":    expires_at,
    }
    return access_token


def _parse_expiry(value: Any, fallback: float) -> float:
    """Parse CJ expiry — either an ISO datetime string or seconds-from-now int."""
    if not value:
        return fallback
    if isinstance(value, (int, float)):
        # If it looks like a unix timestamp (> 1e9), use directly; else treat as seconds
        v = float(value)
        return v if v > 1_000_000_000 else time.time() + v
    try:
        from datetime import datetime, timezone
        s = str(value).strip()
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).timestamp()
    except Exception:
        return fallback


async def _refresh_token(refresh_token: str, api_key: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.post(
            f"{CJ_BASE}/authentication/refreshAccessToken",
            json={"refreshToken": refresh_token},
        )
        data = r.json()
    if not r.is_success or data.get("result") is False:
        return None
    d = data.get("data", {})
    access_token = d.get("accessToken", "")
    expires_at   = _parse_expiry(d.get("accessTokenExpiryDate"), time.time() + 86400)
    _token_cache[api_key].update({
        "access_token":  access_token,
        "expires_at":    expires_at,
        "refresh_token": d.get("refreshToken", refresh_token),
    })
    return access_token


async def cj_get(path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.get(
            f"{CJ_BASE}{path}",
            params=params or {},
            headers={"CJ-Access-Token": token},
        )
    data = r.json()
    if not r.is_success or data.get("result") is False:
        raise RuntimeError(f"CJ GET {path} failed: {data.get('message', r.text[:200])}")
    return data.get("data", data)


async def cj_post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.post(
            f"{CJ_BASE}{path}",
            json=body,
            headers={"CJ-Access-Token": token, "Content-Type": "application/json"},
        )
    data = r.json()
    if not r.is_success or data.get("result") is False:
        raise RuntimeError(f"CJ POST {path} failed: {data.get('message', r.text[:200])}")
    return data.get("data", data)
