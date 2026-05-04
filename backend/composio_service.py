"""Composio integration service for Zilo CRM.

Handles OAuth connections (Gmail, Google Calendar) and action execution.
Uses Composio managed auth — only COMPOSIO_API_KEY needed.

Correct Composio REST endpoints (from SDK source inspection):
  Base:  https://backend.composio.dev   (no /api prefix)
  Paths: /v1/connectedAccounts, /v1/integrations, /v1/apps/{name}
  Key body field: "userUuid" (not entityId/userId)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://backend.composio.dev/api"

# Composio app name (lowercase slug, as stored in appName field)
_APP_NAMES: Dict[str, str] = {
    # Email / Calendar
    "gmail":           "gmail",
    "googlecalendar":  "googlecalendar",
    "outlook":         "outlook",
    # Productivity
    "slack":           "slack",
    "googlesheets":    "googlesheets",
    "notion":          "notion",
    # E-commerce / Payments
    "shopify":         "shopify",
    "stripe":          "stripe",
    # Marketing
    "klaviyo":         "klaviyo",
    "mailchimp":       "mailchimp",
    "brevo":           "brevo",
}

TOOLKIT_GMAIL        = "gmail"
TOOLKIT_CALENDAR     = "googlecalendar"
TOOLKIT_OUTLOOK      = "outlook"
TOOLKIT_SLACK        = "slack"
TOOLKIT_GOOGLESHEETS = "googlesheets"
TOOLKIT_NOTION       = "notion"
TOOLKIT_SHOPIFY      = "shopify"
TOOLKIT_STRIPE       = "stripe"
TOOLKIT_KLAVIYO      = "klaviyo"
TOOLKIT_MAILCHIMP    = "mailchimp"
TOOLKIT_BREVO        = "brevo"

ALL_TOOLKITS = list(_APP_NAMES.keys())

# ── Action name constants ──────────────────────────────────────────────────────
ACTION_GMAIL_FETCH        = "GMAIL_FETCH_EMAILS"
ACTION_GMAIL_SEND         = "GMAIL_SEND_EMAIL"
ACTION_GMAIL_DRAFT        = "GMAIL_CREATE_EMAIL_DRAFT"
ACTION_CALENDAR_LIST      = "GOOGLECALENDAR_LIST_EVENTS"
ACTION_CALENDAR_CREATE    = "GOOGLECALENDAR_CREATE_EVENT"
ACTION_CALENDAR_DELETE    = "GOOGLECALENDAR_DELETE_EVENT"
ACTION_OUTLOOK_FETCH      = "OUTLOOK_OUTLOOK_LIST_MESSAGES"
ACTION_OUTLOOK_SEND       = "OUTLOOK_OUTLOOK_SEND_EMAIL"
ACTION_OUTLOOK_REPLY      = "OUTLOOK_OUTLOOK_REPLY_EMAIL"
ACTION_OUTLOOK_SEARCH     = "OUTLOOK_OUTLOOK_SEARCH_MESSAGES"

# Shopify — prefer packaged actions over raw REST where possible
ACTION_SHOPIFY_GET_ORDERS_WITH_FILTERS = "SHOPIFY_GET_ORDERS_WITH_FILTERS"
ACTION_SHOPIFY_GET_PRODUCTS_PAGINATED = "SHOPIFY_GET_PRODUCTS_PAGINATED"


def _get_key() -> str:
    return os.getenv("COMPOSIO_API_KEY", "").strip()


def _headers() -> Dict[str, str]:
    return {"x-api-key": _get_key(), "Content-Type": "application/json"}


def is_configured() -> bool:
    return bool(_get_key())


# ── Integration helpers ────────────────────────────────────────────────────────

async def _get_or_create_integration_id(client: httpx.AsyncClient, app_name: str) -> Optional[str]:
    """Find an existing Composio integration for the app, or create one."""
    # 1. List existing integrations
    try:
        resp = await client.get(
            f"{_BASE}/v1/integrations",
            headers=_headers(),
            params={"showDisabled": "false", "pageSize": 100},
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items") or data.get("data") or data.get("integrations") or []
            if isinstance(items, dict):
                items = items.get("items") or []
            for item in items:
                name = str(item.get("appName") or item.get("name") or "").lower()
                if name == app_name.lower() or app_name.lower() in name:
                    iid = item.get("id")
                    if iid:
                        logger.info("[composio] found integration %s → %s", app_name, iid)
                        return str(iid)
    except Exception as e:
        logger.warning("[composio] list integrations error: %s", e)

    # 2. Get the Composio app metadata to find appId
    try:
        resp = await client.get(f"{_BASE}/v1/apps/{app_name}", headers=_headers())
        logger.info("[composio] GET /v1/apps/%s → %d %s", app_name, resp.status_code, resp.text[:200])
        if resp.status_code != 200:
            return None
        app_data = resp.json()
        app_id = app_data.get("appId") or app_data.get("id")
        if not app_id:
            return None
    except Exception as e:
        logger.warning("[composio] get app metadata error: %s", e)
        return None

    # 3. Create a new integration using Composio's managed OAuth
    try:
        import time
        ts = int(time.time())
        payload = {
            "appId": app_id,
            "name": f"{app_name}_zilo_{ts}",
            "authScheme": "OAUTH2",
            "useComposioAuth": True,
        }
        resp = await client.post(f"{_BASE}/v1/integrations", headers=_headers(), json=payload)
        logger.info("[composio] create integration %s → %d %s", app_name, resp.status_code, resp.text[:300])
        if resp.status_code in (200, 201):
            data = resp.json()
            iid = data.get("id")
            if iid:
                return str(iid)
    except Exception as e:
        logger.warning("[composio] create integration error: %s", e)

    return None


# ── OAuth connect ──────────────────────────────────────────────────────────────

async def get_connect_url(user_id: str, toolkit: str, redirect_url: str) -> Dict[str, Any]:
    """Initiate OAuth for a toolkit and return the redirect URL."""
    key = _get_key()
    if not key:
        return {"error": "COMPOSIO_API_KEY not configured in .env"}

    app_name = _APP_NAMES.get(toolkit.lower())
    if not app_name:
        return {"error": f"Unknown toolkit '{toolkit}'. Use: gmail or googlecalendar"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            integration_id = await _get_or_create_integration_id(client, app_name)
            if not integration_id:
                return {"error": f"Could not find or create Composio integration for {app_name}"}

            payload: Dict[str, Any] = {
                "integrationId": integration_id,
                "userUuid": user_id,
                "data": {},
                "labels": [],
                "redirectUri": redirect_url,
            }
            logger.info("[composio] POST /v1/connectedAccounts payload=%s", payload)
            resp = await client.post(
                f"{_BASE}/v1/connectedAccounts",
                headers=_headers(),
                json=payload,
            )
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text[:500]}

            logger.info("[composio] POST /v1/connectedAccounts → %d body=%s", resp.status_code, str(data)[:500])

            if resp.status_code not in (200, 201):
                return {
                    "error": (
                        data.get("message") or data.get("error")
                        or f"Composio HTTP {resp.status_code}: {str(data)[:300]}"
                    )
                }

            url = (
                data.get("redirectUrl")
                or data.get("redirect_url")
                or data.get("authUrl")
            )
            cid = data.get("connectedAccountId") or data.get("id")
            if not url:
                return {"error": f"Composio did not return a redirect URL. Response: {str(data)[:300]}"}
            return {"redirect_url": url, "connection_id": cid}

    except Exception as e:
        logger.error("[composio] get_connect_url error: %s", e)
        return {"error": str(e)}


# ── Connection status ──────────────────────────────────────────────────────────

async def get_connection_status(user_id: str, toolkit: str) -> Dict[str, Any]:
    """Return {"connected": bool, "connection_id": str|None}.

    Always verifies the returned connection's userUuid matches user_id so that
    if the Composio API ignores the filter and returns all accounts, we do not
    incorrectly mark a new user as connected with someone else's account.
    """
    if not _get_key():
        return {"connected": False, "error": "COMPOSIO_API_KEY not configured"}

    app_name = _APP_NAMES.get(toolkit.lower(), toolkit.lower())

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BASE}/v1/connectedAccounts",
                headers=_headers(),
                params={"userUuid": user_id, "showActiveOnly": "true"},
            )
            if resp.status_code != 200:
                return {"connected": False}
            data = resp.json()
            items = data.get("items") or data.get("data") or data.get("connectedAccounts") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Verify this connection actually belongs to the requesting user.
                # Composio may return all accounts when the userUuid filter is
                # not applied server-side — we enforce isolation here.
                item_user = str(
                    item.get("userUuid") or item.get("clientUniqueUserId") or item.get("entityId") or ""
                ).strip()
                if item_user and item_user != user_id:
                    logger.debug(
                        "[composio] skipping account %s: belongs to %s, not %s",
                        item.get("id"), item_user, user_id,
                    )
                    continue
                item_app = str(
                    item.get("appName") or item.get("appUniqueId") or ""
                ).lower()
                item_status = str(item.get("status") or "ACTIVE").upper()
                if app_name not in item_app and toolkit.lower() not in item_app:
                    continue
                if item_status in ("ACTIVE", ""):
                    return {"connected": True, "connection_id": item.get("id")}
            return {"connected": False}
    except Exception as e:
        logger.warning("[composio] get_connection_status error: %s", e)
        return {"connected": False, "error": str(e)}


async def get_all_connection_statuses(user_id: str) -> Dict[str, bool]:
    """Return connection status for all Zilo-supported toolkits (all apps)."""
    if not _get_key():
        return {t: False for t in ALL_TOOLKITS}
    # Fetch connected accounts once and check each toolkit
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                f"{_BASE}/v1/connectedAccounts",
                headers=_headers(),
                params={"userUuid": user_id, "showActiveOnly": "true"},
            )
            if resp.status_code != 200:
                return {t: False for t in ALL_TOOLKITS}
            data = resp.json()
            items = data.get("items") or data.get("data") or data.get("connectedAccounts") or []
    except Exception as e:
        logger.warning("[composio] get_all_connection_statuses error: %s", e)
        return {t: False for t in ALL_TOOLKITS}

    # Build set of connected app names (validated by userUuid)
    connected_apps: set = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_user = str(
            item.get("userUuid") or item.get("clientUniqueUserId") or item.get("entityId") or ""
        ).strip()
        if item_user and item_user != user_id:
            continue
        item_status = str(item.get("status") or "ACTIVE").upper()
        if item_status not in ("ACTIVE", ""):
            continue
        app = str(item.get("appName") or item.get("appUniqueId") or "").lower()
        if app:
            connected_apps.add(app)

    results: Dict[str, bool] = {}
    for toolkit, app_name in _APP_NAMES.items():
        results[toolkit] = any(app_name in a or a in app_name for a in connected_apps)
    return results


# ── Disconnect ─────────────────────────────────────────────────────────────────

async def disconnect(user_id: str, toolkit: str) -> Dict[str, Any]:
    """Disconnect a user's active connection for a toolkit."""
    if not _get_key():
        return {"error": "COMPOSIO_API_KEY not configured"}

    status = await get_connection_status(user_id, toolkit)
    conn_id = status.get("connection_id")
    if not conn_id:
        return {"disconnected": True, "note": "No active connection found"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{_BASE}/v1/connectedAccounts/{conn_id}",
                headers=_headers(),
            )
            if resp.status_code in (200, 204):
                return {"disconnected": True}
            data = resp.json() if resp.content else {}
            return {"error": data.get("message") or f"HTTP {resp.status_code}"}
    except Exception as e:
        logger.error("[composio] disconnect error: %s", e)
        return {"error": str(e)}


# ── Raw proxy (replaces nango_proxy for tool execution) ───────────────────────

async def composio_proxy(
    user_id: str,
    toolkit: str,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Make a raw HTTP request through a user's Composio connected account.

    Mirrors the nango_proxy() signature so it can be used as a drop-in replacement.
    Uses Composio's proxy endpoint (/v2/actions/proxy) which handles OAuth token
    refresh and routes to the correct base URL per integration.

    Args:
        user_id:  The user's business_id (used as Composio userUuid/entityId).
        toolkit:  Composio app slug (e.g. "shopify", "slack", "googlesheets").
        method:   HTTP method ("GET", "POST", "PUT", "PATCH", "DELETE").
        path:     API path (e.g. "/admin/api/2024-01/orders.json").
        params:   Optional URL query parameters.
        json:     Optional JSON request body.
        timeout:  Request timeout seconds.

    Returns:
        Parsed JSON response dict.

    Raises:
        RuntimeError: If Composio is not configured, not connected, or call fails.
    """
    if not _get_key():
        raise RuntimeError("COMPOSIO_API_KEY is not configured")

    # Resolve connectedAccountId
    status = await get_connection_status(user_id, toolkit)
    if not status.get("connected"):
        raise RuntimeError(
            f"No {toolkit} connection found for this account. "
            f"Connect {toolkit} in the Integrations page first."
        )
    conn_id = status.get("connection_id")

    # Build Composio proxy request
    # Parameters must be a list of {name, value, in} objects
    param_list = []
    if params:
        for k, v in params.items():
            param_list.append({"name": str(k), "value": str(v), "in": "query"})

    proxy_body: Dict[str, Any] = {
        "endpoint": path.lstrip("/") if not path.startswith("http") else path,
        "method": method.upper(),
        "parameters": param_list,
        "body": json or {},
    }
    if conn_id:
        proxy_body["connectedAccountId"] = conn_id
    else:
        proxy_body["entityId"] = user_id

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{_BASE}/v2/actions/proxy",
                headers=_headers(),
                json=proxy_body,
            )
    except Exception as e:
        raise RuntimeError(f"Composio proxy request failed: {e}") from e

    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:300]
        raise RuntimeError(f"{toolkit} proxy error {resp.status_code}: {body}")

    try:
        data = resp.json()
    except Exception:
        return {"raw": resp.text[:2000]}

    # Composio wraps responses: { data: { responseData: {...}, successfull: bool } }
    inner = data.get("data") or data
    if isinstance(inner, dict):
        response_data = inner.get("responseData") or inner.get("response_data") or inner
        if isinstance(response_data, dict) and (
            "responseData" not in response_data and "successfull" not in response_data
        ):
            return response_data
        return response_data
    return data


# ── Toolkit from action name ──────────────────────────────────────────────────

def _toolkit_for_action(action: str) -> Optional[str]:
    """Derive toolkit slug from Composio action name prefix (e.g. SHOPIFY_* → shopify)."""
    a = action.upper()
    if a.startswith("GMAIL_"):
        return TOOLKIT_GMAIL
    if a.startswith("GOOGLECALENDAR_"):
        return TOOLKIT_CALENDAR
    if a.startswith("OUTLOOK_"):
        return TOOLKIT_OUTLOOK
    if a.startswith("SHOPIFY_"):
        return TOOLKIT_SHOPIFY
    if a.startswith("SLACK_"):
        return TOOLKIT_SLACK
    if a.startswith("STRIPE_"):
        return TOOLKIT_STRIPE
    if a.startswith("KLAVIYO_"):
        return TOOLKIT_KLAVIYO
    if a.startswith("MAILCHIMP_"):
        return TOOLKIT_MAILCHIMP
    if a.startswith("BREVO_") or a.startswith("SENDINBLUE_"):
        return TOOLKIT_BREVO
    if a.startswith("NOTION_"):
        return TOOLKIT_NOTION
    if a.startswith("GOOGLESHEETS_") or a.startswith("GOOGLE_SHEETS_"):
        return TOOLKIT_GOOGLESHEETS
    return None


def _extract_list_from_execute(
    exec_result: Dict[str, Any],
    key: str,
) -> Optional[list]:
    """Pull a list from execute_action() output; None means caller should fall back."""
    if exec_result.get("error"):
        return None
    if not exec_result.get("success"):
        return None
    d = exec_result.get("data")
    if d is None:
        return None
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        if key in d and isinstance(d[key], list):
            return d[key]
        for inner in (d.get("data"), d.get("response"), d.get("body"), d.get("result")):
            if isinstance(inner, dict) and isinstance(inner.get(key), list):
                return inner[key]
    return None


async def shopify_orders_via_composio_or_proxy(
    user_id: str,
    *,
    status: str,
    limit: int,
    created_at_min: str,
    financial_status: Optional[str] = None,
) -> Dict[str, Any]:
    """List orders: try Composio packaged action first, then Admin REST proxy."""
    params: Dict[str, Any] = {
        "status": status,
        "limit": min(max(limit, 1), 250),
        "created_at_min": created_at_min,
    }
    if financial_status:
        params["financial_status"] = financial_status
    r = await execute_action(user_id, ACTION_SHOPIFY_GET_ORDERS_WITH_FILTERS, params)
    orders = _extract_list_from_execute(r, "orders")
    if orders is not None:
        return {"orders": orders}
    qparams: Dict[str, str] = {
        "status": status,
        "limit": str(limit),
        "created_at_min": created_at_min,
    }
    if financial_status:
        qparams["financial_status"] = financial_status
    return await composio_proxy(
        user_id,
        TOOLKIT_SHOPIFY,
        "GET",
        "/admin/api/2024-01/orders.json",
        params=qparams,
    )


async def shopify_products_via_composio_or_proxy(
    user_id: str,
    *,
    limit: int,
    product_status: str,
) -> Dict[str, Any]:
    """List products: try Composio paginated action, filter by status; else REST proxy."""
    lim = min(max(limit, 1), 250)
    r = await execute_action(
        user_id,
        ACTION_SHOPIFY_GET_PRODUCTS_PAGINATED,
        {"limit": lim},
    )
    products = _extract_list_from_execute(r, "products")
    if products is not None:
        ps = (product_status or "active").lower()
        products = [p for p in products if str(p.get("status") or "").lower() == ps]
        return {"products": products[:lim]}
    return await composio_proxy(
        user_id,
        TOOLKIT_SHOPIFY,
        "GET",
        "/admin/api/2024-01/products.json",
        params={"limit": str(lim), "status": product_status},
    )


# ── Execute action ─────────────────────────────────────────────────────────────

async def execute_action(user_id: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a Composio action on behalf of a user."""
    if not _get_key():
        return {"error": "COMPOSIO_API_KEY not configured in .env"}

    # Look up connectedAccountId (required by Composio v2 execute for auth apps)
    conn_id: Optional[str] = None
    toolkit = _toolkit_for_action(action)
    if toolkit:
        status = await get_connection_status(user_id, toolkit)
        conn_id = status.get("connection_id")
        if not status.get("connected"):
            return {
                "error": f"{toolkit.title()} is not connected. Connect it in the Integrations page first.",
            }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            body: Dict[str, Any] = {
                "entityId": user_id,
                "input": params,
            }
            if conn_id:
                body["connectedAccountId"] = conn_id
            resp = await client.post(
                f"{_BASE}/v2/actions/{action}/execute",
                headers=_headers(),
                json=body,
            )
            data = resp.json()
            if resp.status_code not in (200, 201):
                err = data.get("message") or data.get("error") or f"HTTP {resp.status_code}"
                logger.warning("[composio] execute_action %s error: %s", action, err)
                return {"error": err}
            result = data.get("data") or data.get("response") or data.get("result") or data
            if isinstance(result, dict) and result.get("error"):
                return {"error": result["error"]}
            return {"success": True, "data": result}
    except Exception as e:
        logger.error("[composio] execute_action %s error: %s", action, e)
        return {"error": str(e)}
