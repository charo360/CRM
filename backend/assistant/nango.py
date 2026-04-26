"""Nango proxy helper for the AI assistant.

Provides a single `nango_proxy()` coroutine that:
  1. Looks up the Nango connection ID for a given user + integration.
  2. Routes the API call through the Nango proxy (handles OAuth token refresh).

Usage:
    data = await nango_proxy(business_id, "shopify", "GET", "/admin/api/2024-01/orders.json",
                             params={"status": "any", "limit": 50})

Returns the parsed JSON response dict, or raises RuntimeError on failure.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_NANGO_API = os.getenv("NANGO_API_URL", "https://api.nango.dev")


async def _get_connection_id(
    business_id: str,
    integration_key: str,
    secret: str,
) -> Optional[str]:
    """Return the first Nango connection ID for this user + integration, or None."""
    import httpx
    url = f"{_NANGO_API}/connection"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                url,
                params={"end_user_id": business_id, "provider_config_key": integration_key},
                headers={"Authorization": f"Bearer {secret}"},
            )
            if resp.status_code != 200:
                logger.warning(f"[Nango] connection lookup {integration_key}: HTTP {resp.status_code}")
                return None
            data = resp.json()
            conns = data.get("connections") or []
            if not conns:
                return None
            return conns[0].get("id") or conns[0].get("connection_id")
    except Exception as e:
        logger.warning(f"[Nango] connection lookup error {integration_key}: {e}")
        return None


async def nango_proxy(
    business_id: str,
    integration_key: str,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Route an API call through the Nango proxy.

    Args:
        business_id:      The user's business_id (used as Nango end_user_id).
        integration_key:  Nango provider_config_key (e.g. "shopify", "stripe").
        method:           HTTP method ("GET", "POST", "PUT", etc.).
        path:             API path without the base URL (e.g. "/admin/api/2024-01/orders.json").
        params:           Optional query parameters.
        json:             Optional JSON body.
        timeout:          Request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        RuntimeError: If Nango is not configured, the integration is not connected,
                      or the upstream API returns an error.
    """
    import httpx

    secret = os.getenv("NANGO_SECRET_KEY")
    if not secret:
        raise RuntimeError("Nango is not configured (NANGO_SECRET_KEY missing)")

    conn_id = await _get_connection_id(business_id, integration_key, secret)
    if not conn_id:
        raise RuntimeError(
            f"No {integration_key} connection found for this account. "
            f"Connect {integration_key} in the Integrations page first."
        )

    # Strip leading slash — Nango proxy URL is /{path}
    clean_path = path.lstrip("/")
    proxy_url = f"{_NANGO_API}/proxy/{clean_path}"

    headers = {
        "Authorization": f"Bearer {secret}",
        "Connection-Id": conn_id,
        "Provider-Config-Key": integration_key,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method.upper(),
                proxy_url,
                params=params,
                json=json,
                headers=headers,
            )
    except Exception as e:
        raise RuntimeError(f"Nango proxy request failed: {e}") from e

    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:300]
        raise RuntimeError(
            f"{integration_key} API error {resp.status_code}: {body}"
        )

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:2000]}
