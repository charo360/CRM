"""Composio proxy helper — drop-in replacement for assistant/nango.py.

Implements ``composio_proxy()`` with the same signature as the old
``nango_proxy()`` so existing tool code needs only an import swap.

Nango integration key → Composio toolkit slug mapping is handled here,
so tools that still reference Nango key names (e.g. "google-mail",
"microsoft", "google-sheet") continue to work transparently.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Nango-key → Composio-toolkit mapping ──────────────────────────────────────
# Any key not in this map is passed through unchanged (e.g. "shopify", "slack").
_NANGO_TO_COMPOSIO: Dict[str, str] = {
    "google-mail":     "gmail",
    "google-calendar": "googlecalendar",
    "google-sheet":    "googlesheets",
    "microsoft":       "outlook",
}


def _resolve_toolkit(integration_key: str) -> str:
    """Map a Nango integration key to the equivalent Composio toolkit slug."""
    return _NANGO_TO_COMPOSIO.get(integration_key, integration_key)


async def composio_proxy(
    business_id: str,
    integration_key: str,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Proxy a raw HTTP request through the user's Composio connected account.

    Signature matches ``nango.nango_proxy()`` so callers only need to change
    their import statement.

    Args:
        business_id:     User's business_id (Composio entityId/userUuid).
        integration_key: Nango-style integration key OR Composio toolkit slug.
        method:          HTTP method ("GET", "POST", "PUT", "PATCH", "DELETE").
        path:            API path (e.g. "/admin/api/2024-01/orders.json").
        params:          URL query parameters.
        json:            JSON request body.
        timeout:         Request timeout in seconds.

    Returns:
        Parsed JSON response dict.

    Raises:
        RuntimeError: When Composio is not configured, the integration is not
                      connected, or the upstream API returns an error.
    """
    # Resolve the toolkit slug (handles legacy Nango key names)
    toolkit = _resolve_toolkit(integration_key)

    # Import composio_service at call-time to avoid circular imports; the
    # backend adds its root directory to sys.path so this always resolves.
    try:
        import composio_service  # type: ignore[import]
    except ModuleNotFoundError:
        # Fallback: add backend root to path if running from a subdirectory
        backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)
        import composio_service  # type: ignore[import]

    return await composio_service.composio_proxy(
        user_id=business_id,
        toolkit=toolkit,
        method=method,
        path=path,
        params=params,
        json=json,
        timeout=timeout,
    )
