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
    "gmail":           "gmail",
    "googlecalendar":  "googlecalendar",
    "outlook":         "outlook",         # Microsoft Outlook via Composio
}

TOOLKIT_GMAIL    = "gmail"
TOOLKIT_CALENDAR = "googlecalendar"
TOOLKIT_OUTLOOK  = "outlook"

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
    """Return connection status for all Zilo-supported toolkits."""
    if not _get_key():
        return {TOOLKIT_GMAIL: False, TOOLKIT_CALENDAR: False, TOOLKIT_OUTLOOK: False}
    results: Dict[str, bool] = {}
    for toolkit in (TOOLKIT_GMAIL, TOOLKIT_CALENDAR, TOOLKIT_OUTLOOK):
        status = await get_connection_status(user_id, toolkit)
        results[toolkit] = status.get("connected", False)
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


# ── Toolkit from action name ──────────────────────────────────────────────────

def _toolkit_for_action(action: str) -> Optional[str]:
    """Derive toolkit slug from action name prefix."""
    a = action.upper()
    if a.startswith("GMAIL_"):
        return TOOLKIT_GMAIL
    if a.startswith("GOOGLECALENDAR_"):
        return TOOLKIT_CALENDAR
    if a.startswith("OUTLOOK_"):
        return TOOLKIT_OUTLOOK
    return None


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
