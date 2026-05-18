"""Composio integration service for Zilo CRM.



Handles OAuth connections (Gmail, Google Calendar) and action execution.

Uses Composio managed auth — only COMPOSIO_API_KEY needed.



Correct Composio REST base: https://backend.composio.dev/api

  - Managed OAuth toolkits: v1 integrations + POST /v1/connectedAccounts (integrationId, userUuid).

  - Shopify/Brevo/Klaviyo (no managed app): v3.1 auth_configs + POST /v3.1/connected_accounts (auth_config.id).

"""

from __future__ import annotations



import logging

import os

from typing import Any, Dict, Optional



import httpx



logger = logging.getLogger(__name__)



_BASE = "https://backend.composio.dev/api"



# No Composio-managed OAuth — use v3.1 auth_configs + connected_accounts in get_connect_url.

_COMPOSIO_NO_MANAGED_OAUTH: frozenset[str] = frozenset({"brevo", "shopify", "klaviyo"})

# Try v3.1 auth_configs FIRST for these toolkits (managed OAuth works but custom apps are common)
_COMPOSIO_TRY_V31_FIRST: frozenset[str] = frozenset({
    "googlesearchconsole", "googleanalytics", "googleads",
})



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

    "brevo":                "brevo",

    # Google Analytics toolkits
    "googlesearchconsole":  "googlesearchconsole",
    "googleanalytics":      "googleanalytics",
    "googleads":            "googleads",

}



TOOLKIT_GMAIL              = "gmail"

TOOLKIT_CALENDAR           = "googlecalendar"

TOOLKIT_OUTLOOK            = "outlook"

TOOLKIT_SLACK              = "slack"

TOOLKIT_GOOGLESHEETS       = "googlesheets"

TOOLKIT_NOTION             = "notion"

TOOLKIT_SHOPIFY            = "shopify"

TOOLKIT_STRIPE             = "stripe"

TOOLKIT_KLAVIYO            = "klaviyo"

TOOLKIT_MAILCHIMP          = "mailchimp"

TOOLKIT_BREVO              = "brevo"

TOOLKIT_SEARCHCONSOLE      = "googlesearchconsole"

TOOLKIT_GOOGLEANALYTICS    = "googleanalytics"

TOOLKIT_GOOGLEADS          = "googleads"



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



# Stripe

ACTION_STRIPE_LIST_INVOICES = "STRIPE_LIST_INVOICES"

ACTION_STRIPE_LIST_PAYMENT_INTENTS = "STRIPE_LIST_PAYMENT_INTENTS"



# Klaviyo

ACTION_KLAVIYO_GET_FLOWS = "KLAVIYO_GET_FLOWS"

ACTION_KLAVIYO_GET_METRICS = "KLAVIYO_GET_METRICS"



# Slack

ACTION_SLACK_TEST_AUTH = "SLACK_TEST_AUTH"

ACTION_SLACK_LIST_CONVERSATIONS = "SLACK_LIST_CONVERSATIONS"

ACTION_SLACK_SEND_MESSAGE = "SLACK_SEND_MESSAGE"





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

            import re as _re_i
            def _inorm(s: str) -> str:
                return _re_i.sub(r"[_\-\s]+", "", s.lower())
            app_name_in = _inorm(app_name)
            for item in items:

                name = str(item.get("appName") or item.get("name") or "").lower()
                name_norm = _inorm(name)

                if name_norm == app_name_in or app_name_in in name_norm or name_norm in app_name_in:

                    iid = item.get("id")

                    if iid:

                        print(f"[composio] found integration {app_name} → {iid}", flush=True)
                        logger.info("[composio] found integration %s → %s", app_name, iid)

                        return str(iid)

    except Exception as e:

        logger.warning("[composio] list integrations error: %s", e)



    # 2. Get the Composio app metadata to find appId
    # Try direct slug first (lower + upper), then search the full app list by name.

    app_id: Optional[str] = None

    for slug in (app_name, app_name.upper(), app_name.lower()):
        try:
            resp = await client.get(f"{_BASE}/v1/apps/{slug}", headers=_headers())
            logger.info("[composio] GET /v1/apps/%s → %d", slug, resp.status_code)
            if resp.status_code == 200:
                app_data = resp.json()
                app_id = str(app_data.get("appId") or app_data.get("id") or "").strip() or None
                if app_id:
                    break
        except Exception as e:
            logger.warning("[composio] GET /v1/apps/%s error: %s", slug, e)

    # Fallback: search full app list by name keywords (normalized)
    if not app_id:
        try:
            import re as _re_a
            def _anorm(s: str) -> str:
                return _re_a.sub(r"[_\-\s]+", "", s.lower())
            app_name_norm = _anorm(app_name)
            for page in (1, 2):
                r = await client.get(
                    f"{_BASE}/v1/apps",
                    headers=_headers(),
                    params={"limit": 100, "page": page},
                )
                if r.status_code != 200:
                    print(f"[composio] GET /v1/apps page={page} → {r.status_code}", flush=True)
                    break
                items = r.json().get("items") or r.json().get("data") or []
                for item in items:
                    raw = str(item.get("name") or item.get("appName") or item.get("key") or "")
                    aname_norm = _anorm(raw)
                    if app_name_norm in aname_norm or aname_norm in app_name_norm:
                        candidate = str(item.get("appId") or item.get("id") or "").strip()
                        if candidate:
                            app_id = candidate
                            print(f"[composio] found app via list: {raw} → id={app_id}", flush=True)
                            logger.info("[composio] found app via list search: %s → id=%s", raw, app_id)
                            break
                if app_id:
                    break
        except Exception as e:
            logger.warning("[composio] app list search error: %s", e)

    if not app_id:
        print(f"[composio] could not resolve appId for {app_name}", flush=True)
        logger.warning("[composio] could not resolve appId for %s", app_name)
        return None



    # 3. Create integration (Composio-managed OAuth only where supported).

    use_composio_managed = app_name.lower() not in _COMPOSIO_NO_MANAGED_OAUTH

    try:

        import time

        ts = int(time.time())

        payload = {

            "appId": app_id,

            "name": f"{app_name}_zilo_{ts}",

            "authScheme": "OAUTH2",

            "useComposioAuth": use_composio_managed,

        }

        resp = await client.post(f"{_BASE}/v1/integrations", headers=_headers(), json=payload)

        logger.info(

            "[composio] create integration %s managed=%s → %d %s",

            app_name,

            use_composio_managed,

            resp.status_code,

            resp.text[:300],

        )

        if resp.status_code in (200, 201):

            data = resp.json()

            iid = data.get("id")

            if iid:

                return str(iid)

    except Exception as e:

        logger.warning("[composio] create integration error: %s", e)



    return None





def _composio_err_text(data: Any, http_status: int) -> str:

    if isinstance(data, dict):

        err = data.get("error")

        if isinstance(err, dict):

            msg = err.get("message") or err.get("suggested_fix")

            if msg:

                return str(msg)

        m = data.get("message")

        if m:

            return str(m)

        return f"Composio HTTP {http_status}: {str(data)[:400]}"

    return f"Composio HTTP {http_status}"





def _v31_extract_redirect(data: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:

    cid = data.get("id")

    url = data.get("redirect_url") or data.get("redirect_uri")

    if url:

        return str(url), str(cid) if cid is not None else None

    cd = data.get("connectionData")

    if isinstance(cd, dict):

        val = cd.get("val")

        if isinstance(val, dict):

            u2 = val.get("redirectUrl") or val.get("authUri") or val.get("callbackUrl")

            if u2:

                return str(u2), str(cid) if cid is not None else None

    return None, str(cid) if cid is not None else None





_SETUP_GUIDE_URL: Dict[str, str] = {

    "shopify": "https://composio.dev/auth/shopify",

    "brevo": "https://docs.composio.dev/toolkits/brevo",

    "klaviyo": "https://docs.composio.dev/toolkits/klaviyo",

}





def _auth_config_item_matches_toolkit(item: Dict[str, Any], app_name: str) -> bool:

    want = app_name.lower()

    tk = item.get("toolkit")

    if isinstance(tk, dict):

        for key in ("slug", "name", "appName", "unique_slug"):

            v = tk.get(key)

            if v is not None and want == str(v).strip().lower():

                return True

    for key in ("toolkit_slug", "appName", "app_name", "appUniqueKey"):

        v = item.get(key)

        if v is not None and want in str(v).lower():

            return True

    return False





async def _resolve_auth_config_nanoid(client: httpx.AsyncClient, app_name: str) -> Optional[str]:

    """v3.1 auth config id. Override with COMPOSIO_AUTH_CONFIG_ID_SHOPIFY (etc.) in .env."""

    env_key = f"COMPOSIO_AUTH_CONFIG_ID_{app_name.upper().replace('-', '_')}"

    forced = os.getenv(env_key, "").strip()

    if forced:

        logger.info("[composio] using %s from environment", env_key)

        return forced

    for slug in (app_name.upper(), app_name.lower()):

        r = await client.get(

            f"{_BASE}/v3.1/auth_configs",

            headers=_headers(),

            params={"toolkit_slug": slug, "limit": 25, "show_disabled": "false"},

        )

        if r.status_code != 200:

            logger.warning(

                "[composio] GET v3.1/auth_configs slug=%s → %d %s",

                slug,

                r.status_code,

                r.text[:250],

            )

            continue

        try:

            body = r.json()

        except Exception:

            continue

        for it in body.get("items") or []:

            if not isinstance(it, dict):

                continue

            iid = it.get("id") or it.get("nanoid")

            if iid:

                logger.info("[composio] auth_config from API id=%s slug=%s", iid, slug)

                return str(iid)



    r2 = await client.get(

        f"{_BASE}/v3.1/auth_configs",

        headers=_headers(),

        params={"limit": 80, "show_disabled": "false"},

    )

    if r2.status_code != 200:

        logger.warning("[composio] GET v3.1/auth_configs unfiltered → %d", r2.status_code)

        return None

    try:

        body2 = r2.json()

    except Exception:

        return None

    for it in body2.get("items") or []:

        if not isinstance(it, dict):

            continue

        if not _auth_config_item_matches_toolkit(it, app_name):

            continue

        iid = it.get("id") or it.get("nanoid")

        if iid:

            logger.info("[composio] auth_config matched toolkit %s id=%s", app_name, iid)

            return str(iid)

    return None





async def _init_connected_account_v31(

    client: httpx.AsyncClient,

    auth_config_id: str,

    user_id: str,

    callback_url: str,

) -> Dict[str, Any]:

    attempts: list[Dict[str, Any]] = [

        {

            "auth_config": {"id": auth_config_id},

            "connection": {

                "user_id": user_id,

                "callback_url": callback_url,

                "state": {

                    "authScheme": "OAUTH2",

                    "val": {"status": "INITIALIZING"},

                },

            },

        },

        {

            "auth_config": {"id": auth_config_id},

            "user_id": user_id,

            "callback_url": callback_url,

        },

    ]

    last_err = ""

    for payload in attempts:

        resp = await client.post(

            f"{_BASE}/v3.1/connected_accounts",

            headers=_headers(),

            json=payload,

        )

        try:

            data = resp.json()

        except Exception:

            data = {"raw": resp.text[:500]}

        logger.info(

            "[composio] POST v3.1/connected_accounts → %d %s",

            resp.status_code,

            str(data)[:500],

        )

        if resp.status_code in (200, 201) and isinstance(data, dict):

            url, cid = _v31_extract_redirect(data)

            if url:

                return {"redirect_url": url, "connection_id": cid}

            last_err = f"Composio returned no redirect URL: {str(data)[:400]}"

        else:

            last_err = _composio_err_text(data, resp.status_code)

    return {"error": last_err or "Composio v3.1 connected_accounts failed"}





def _no_auth_config_help(app_name: str) -> str:

    guide = _SETUP_GUIDE_URL.get(

        app_name.lower(),

        f"https://docs.composio.dev/toolkits/{app_name.lower()}",

    )

    u = app_name.upper().replace("-", "_")

    return (

        f"No Composio auth configuration found for {app_name}. "

        f"In the Composio dashboard, create an auth config for this toolkit (OAuth or API key), "

        f"or set COMPOSIO_AUTH_CONFIG_ID_{u}=<auth config id> in backend .env. "

        f"Docs: {guide}"

    )





# ── OAuth connect ──────────────────────────────────────────────────────────────



async def get_connect_url(user_id: str, toolkit: str, redirect_url: str) -> Dict[str, Any]:

    """Initiate OAuth for a toolkit and return the redirect URL."""

    key = _get_key()

    if not key:

        return {"error": "COMPOSIO_API_KEY not configured in .env"}



    app_name = _APP_NAMES.get(toolkit.lower())

    if not app_name:

        return {"error": f"Unknown toolkit '{toolkit}'. Supported: {', '.join(sorted(ALL_TOOLKITS))}"}



    try:

        async with httpx.AsyncClient(timeout=30.0) as client:

            if app_name.lower() in _COMPOSIO_NO_MANAGED_OAUTH:

                auth_cid = await _resolve_auth_config_nanoid(client, app_name)

                if not auth_cid:

                    return {"error": _no_auth_config_help(app_name)}

                out = await _init_connected_account_v31(client, auth_cid, user_id, redirect_url)

                return out

            # For Google analytics toolkits: try v3.1 auth_configs first (users often set
            # up custom OAuth credentials in Composio dashboard for these).
            if app_name.lower() in _COMPOSIO_TRY_V31_FIRST:

                auth_cid = await _resolve_auth_config_nanoid(client, app_name)

                if auth_cid:

                    out = await _init_connected_account_v31(client, auth_cid, user_id, redirect_url)

                    if "redirect_url" in out:

                        return out

                    logger.info("[composio] v3.1 attempt failed for %s, falling through to v1", app_name)

            integration_id = await _get_or_create_integration_id(client, app_name)

            if not integration_id:

                # Final fallback: try v3.1 auth_configs even for non-priority toolkits
                auth_cid = await _resolve_auth_config_nanoid(client, app_name)

                if auth_cid:

                    return await _init_connected_account_v31(client, auth_cid, user_id, redirect_url)

                return {
                    "error": (
                        f"Could not connect {app_name} via Composio. "
                        f"Please open your Composio dashboard, create an auth config for '{app_name}', "
                        f"then try again. Docs: https://docs.composio.dev/toolkits/{app_name}"
                    )
                }



            payload: Dict[str, Any] = {

                "integrationId": integration_id,

                "userUuid": user_id,

                "entityId": user_id,

                "data": {},

                "labels": [],

                "redirectUri": redirect_url,

            }

            print(f"[composio] POST /v1/connectedAccounts integrationId={integration_id} user={user_id}", flush=True)
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

            print(f"[composio] POST /v1/connectedAccounts → {resp.status_code} {str(data)[:400]}", flush=True)
            logger.info("[composio] POST /v1/connectedAccounts → %d body=%s", resp.status_code, str(data)[:500])



            if resp.status_code not in (200, 201):

                return {"error": _composio_err_text(data, resp.status_code)}



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

                params={"userUuid": user_id},

            )

            if resp.status_code != 200:

                return {"connected": False}

            data = resp.json()

            items = data.get("items") or data.get("data") or data.get("connectedAccounts") or []

            logger.info("[composio] get_connection_status(%s) → %d accounts", toolkit, len(items))

            import re as _re_norm
            def _norm(s: str) -> str:
                return _re_norm.sub(r"[_\-\s]+", "", s.lower())

            app_name_norm = _norm(app_name)
            toolkit_norm  = _norm(toolkit.lower())

            # Statuses that indicate a usable connection
            _OK_STATUSES = {"ACTIVE", "CONNECTED", "VALID", "INITIATED", "SUCCESS", "ENABLED", ""}

            for item in items:

                if not isinstance(item, dict):
                    continue

                item_user = str(
                    item.get("userUuid") or item.get("clientUniqueUserId") or item.get("entityId") or ""
                ).strip()

                if item_user and item_user != user_id:
                    logger.debug(
                        "[composio] skipping account %s: belongs to %s, not %s",
                        item.get("id"), item_user, user_id,
                    )
                    continue

                item_app = str(item.get("appName") or item.get("appUniqueId") or "").lower()
                item_status = str(item.get("status") or "").upper()

                logger.info(
                    "[composio] account id=%s app=%s status=%s user=%s",
                    item.get("id"), item_app, item_status, item_user or "(no uuid)"
                )

                item_app_norm = _norm(item_app)

                if (
                    app_name_norm not in item_app_norm
                    and item_app_norm not in app_name_norm
                    and toolkit_norm not in item_app_norm
                ):
                    continue

                if item_status in _OK_STATUSES:
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

                params={"userUuid": user_id},

            )

            if resp.status_code != 200:

                return {t: False for t in ALL_TOOLKITS}

            data = resp.json()

            items = data.get("items") or data.get("data") or data.get("connectedAccounts") or []

    except Exception as e:

        logger.warning("[composio] get_all_connection_statuses error: %s", e)

        return {t: False for t in ALL_TOOLKITS}

    _OK = {"ACTIVE", "CONNECTED", "VALID", "INITIATED", "SUCCESS", "ENABLED", ""}

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

        item_status = str(item.get("status") or "").upper()

        if item_status not in _OK:

            continue

        app = str(item.get("appName") or item.get("appUniqueId") or "").lower()

        if app:

            connected_apps.add(app)



    import re as _re2
    def _norm2(s: str) -> str:
        return _re2.sub(r"[_\-\s]+", "", s.lower())

    connected_norm = {_norm2(a) for a in connected_apps}

    results: Dict[str, bool] = {}

    for toolkit, app_name in _APP_NAMES.items():
        an = _norm2(app_name)
        tk = _norm2(toolkit)
        results[toolkit] = any(
            an in cn or cn in an or tk in cn
            for cn in connected_norm
        )

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

    }

    if method.upper() not in ("GET", "HEAD"):

        proxy_body["body"] = json or {}

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





def _unwrap_execute_dict(exec_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:

    if exec_result.get("error") or not exec_result.get("success"):

        return None

    d = exec_result.get("data")

    if isinstance(d, dict):

        return d

    return None





def _stripe_list_objects(exec_result: Dict[str, Any]) -> Optional[list]:

    inner = _unwrap_execute_dict(exec_result)

    if not inner:

        return None

    items = inner.get("data")

    if isinstance(items, list):

        return items

    return None





def _klaviyo_flow_filter_expression(status: str) -> Optional[str]:

    s = (status or "all").strip().lower()

    if s == "all":

        return None

    if s == "live":

        return 'equals(status,"live")'

    if s == "draft":

        return 'equals(status,"draft")'

    if s == "archived":

        return 'equals(archived,"true")'

    return None





async def stripe_invoices_via_composio_or_proxy(

    user_id: str,

    *,

    limit: int,

    status: str,

) -> Dict[str, Any]:

    lim = min(max(int(limit), 1), 100)

    params: Dict[str, Any] = {"limit": lim}

    st = (status or "open").lower()

    if st != "all":

        params["status"] = st

    r = await execute_action(user_id, ACTION_STRIPE_LIST_INVOICES, params)

    items = _stripe_list_objects(r)

    if items is not None:

        return {"data": items}

    qparams: Dict[str, str] = {"limit": str(lim)}

    if st != "all":

        qparams["status"] = st

    return await composio_proxy(user_id, TOOLKIT_STRIPE, "GET", "/v1/invoices", params=qparams)





async def stripe_payment_intents_via_composio_or_proxy(

    user_id: str,

    *,

    limit: int,

) -> Dict[str, Any]:

    lim = min(max(int(limit), 1), 100)

    r = await execute_action(

        user_id,

        ACTION_STRIPE_LIST_PAYMENT_INTENTS,

        {"limit": lim},

    )

    items = _stripe_list_objects(r)

    if items is not None:

        return {"data": items}

    return await composio_proxy(

        user_id,

        TOOLKIT_STRIPE,

        "GET",

        "/v1/payment_intents",

        params={"limit": str(lim)},

    )





async def klaviyo_flows_via_composio_or_proxy(

    user_id: str,

    *,

    status: str,

) -> Dict[str, Any]:

    filt = _klaviyo_flow_filter_expression(status)

    params: Dict[str, Any] = {"page__size": 50}

    if filt:

        params["filter"] = filt

    r = await execute_action(user_id, ACTION_KLAVIYO_GET_FLOWS, params)

    inner = _unwrap_execute_dict(r)

    if inner is not None:

        data_arr = inner.get("data")

        if isinstance(data_arr, list):

            return {"data": data_arr}

    rest_params: Dict[str, Any] = {"page[size]": 50}

    st = (status or "all").lower()

    if st != "all":

        rest_params["filter"] = f"equals(status,'{st}')"

    return await composio_proxy(user_id, TOOLKIT_KLAVIYO, "GET", "/api/flows/", params=rest_params)





async def klaviyo_metrics_via_composio_or_proxy(

    user_id: str,

    *,

    limit: int,

) -> Dict[str, Any]:

    lim = min(max(int(limit), 1), 200)

    r = await execute_action(user_id, ACTION_KLAVIYO_GET_METRICS, {})

    inner = _unwrap_execute_dict(r)

    if inner is not None:

        data_arr = inner.get("data")

        if isinstance(data_arr, list):

            return {"data": data_arr[:lim]}

    return await composio_proxy(

        user_id,

        TOOLKIT_KLAVIYO,

        "GET",

        "/api/metrics/",

        params={"page[size]": str(lim)},

    )





async def slack_auth_test_via_composio_or_proxy(user_id: str) -> Dict[str, Any]:

    r = await execute_action(user_id, ACTION_SLACK_TEST_AUTH, {})

    inner = _unwrap_execute_dict(r)

    if inner is not None and inner.get("ok") is not False and (

        inner.get("ok") is True or inner.get("team_id") or inner.get("team")

    ):

        return inner

    return await composio_proxy(user_id, TOOLKIT_SLACK, "POST", "auth.test", json={})





async def slack_conversations_list_via_composio_or_proxy(

    user_id: str,

    *,

    types: str,

    limit: int,

    exclude_archived: bool,

    cursor: Optional[str] = None,

) -> Dict[str, Any]:

    lim = min(max(int(limit), 1), 1000)

    params: Dict[str, Any] = {

        "types": types,

        "limit": lim,

        "exclude_archived": exclude_archived,

    }

    if cursor:

        params["cursor"] = cursor

    r = await execute_action(user_id, ACTION_SLACK_LIST_CONVERSATIONS, params)

    inner = _unwrap_execute_dict(r)

    if inner:

        if isinstance(inner.get("channels"), list):

            return inner

        nested = inner.get("data")

        if isinstance(nested, dict) and isinstance(nested.get("channels"), list):

            return nested

    slack_json: Dict[str, Any] = {

        "types": types,

        "limit": lim,

        "exclude_archived": exclude_archived,

    }

    if cursor:

        slack_json["cursor"] = cursor

    return await composio_proxy(

        user_id,

        TOOLKIT_SLACK,

        "POST",

        "conversations.list",

        json=slack_json,

        timeout=20.0,

    )





async def slack_post_message_via_composio_or_proxy(

    user_id: str,

    *,

    channel: str,

    text: str,

    thread_ts: Optional[str] = None,

) -> Dict[str, Any]:

    params: Dict[str, Any] = {"channel": channel, "text": text}

    if thread_ts:

        params["thread_ts"] = thread_ts

    r = await execute_action(user_id, ACTION_SLACK_SEND_MESSAGE, params)

    inner = _unwrap_execute_dict(r)

    if inner is not None and inner.get("ok") is not False and (

        inner.get("ok") is True or inner.get("ts")

    ):

        return inner

    payload: Dict[str, Any] = {"channel": channel, "text": text}

    if thread_ts:

        payload["thread_ts"] = thread_ts

    return await composio_proxy(

        user_id,

        TOOLKIT_SLACK,

        "POST",

        "chat.postMessage",

        json=payload,

        timeout=15.0,

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

