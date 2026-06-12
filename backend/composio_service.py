"""Composio integration service for Zilo CRM.



Handles OAuth connections (Gmail, Google Calendar, social channels) and action execution.

Uses Composio dashboard auth configs with COMPOSIO_API_KEY.



Correct Composio REST base: https://backend.composio.dev/api

  - OAuth toolkits: v3.1 auth_configs + POST /v3.1/connected_accounts (auth_config.id).

  - Legacy v1 integrations remain as a best-effort fallback for older Composio accounts.

"""

from __future__ import annotations



import logging

import os

from typing import Any, Dict, List, Optional



import httpx



logger = logging.getLogger(__name__)



_BASE = "https://backend.composio.dev/api"



# ── Direct Shopify credential store (DB-backed, bypasses Composio for Shopify) ──

_db = None  # Set by server.py via set_db() after MongoDB init


def set_db(db) -> None:
    """Inject the MongoDB database reference so Shopify direct-creds can be resolved."""
    global _db
    _db = db


async def _get_shopify_direct_creds(user_id: str) -> Optional[Dict[str, str]]:
    """Return {domain, token} if the user has stored direct Shopify credentials."""
    if _db is None:
        return None
    try:
        import bson
        try:
            oid = bson.ObjectId(user_id)
        except Exception:
            oid = None
        query = {"$or": [{"business_id": user_id}]}
        if oid:
            query["$or"].append({"_id": oid})
        user = await _db.users.find_one(
            query,
            {"shopify_domain": 1, "shopify_token": 1,
             "shopify_token_expires_at": 1, "shopify_refresh_token": 1,
             "shopify_refresh_token_expires_at": 1},
        )
        if not user:
            return None
        domain = (user.get("shopify_domain") or "").strip()
        token  = (user.get("shopify_token")  or "").strip()
        if domain and token:
            return {
                "domain": domain,
                "token": token,
                "expires_at": user.get("shopify_token_expires_at"),
                "refresh_token": user.get("shopify_refresh_token") or "",
                "refresh_token_expires_at": user.get("shopify_refresh_token_expires_at"),
                "user_query": query,
            }
        return None
    except Exception as exc:
        logger.warning("[shopify-direct] _get_shopify_direct_creds error: %s", exc)
        return None


async def _shopify_refresh_access_token(creds: Dict[str, Any]) -> Optional[str]:
    """Use the refresh token to get a new expiring access token and persist it."""
    refresh_token = creds.get("refresh_token", "")
    if not refresh_token or _db is None:
        return None
    import os as _os, time as _time
    client_id = _os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
    client_secret = _os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    domain = creds["domain"]
    shop = domain.replace("https://", "").replace("http://", "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15.0) as _hc:
            r = await _hc.post(
                f"https://{shop}/admin/oauth/access_token",
                data={"client_id": client_id, "client_secret": client_secret,
                      "grant_type": "refresh_token", "refresh_token": refresh_token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except Exception as exc:
        logger.warning("[shopify-refresh] HTTP error: %s", exc)
        return None
    if r.status_code != 200:
        logger.warning("[shopify-refresh] Failed %s: %s", r.status_code, r.text[:200])
        return None
    try:
        data = r.json()
    except Exception:
        return None
    new_token = data.get("access_token", "")
    if not new_token:
        return None
    now_ts = int(_time.time())
    update_fields: Dict[str, Any] = {
        "shopify_token": new_token,
        "shopify_token_expires_at": now_ts + int(data.get("expires_in") or 3600),
    }
    new_refresh = data.get("refresh_token", "")
    if new_refresh:
        update_fields["shopify_refresh_token"] = new_refresh
        update_fields["shopify_refresh_token_expires_at"] = now_ts + int(data.get("refresh_token_expires_in") or 7776000)
    try:
        await _db.users.update_one(creds["user_query"], {"$set": update_fields})
    except Exception as exc:
        logger.warning("[shopify-refresh] DB update error: %s", exc)
    logger.info("[shopify-refresh] Token refreshed for shop=%s", shop)
    return new_token


async def _shopify_direct_proxy(
    domain: str,
    token: str,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Make a direct Shopify Admin REST call without going through Composio."""
    domain = domain.rstrip("/")
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    url = f"{domain}{path}" if path.startswith("/") else f"{domain}/{path}"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method.upper(), url, headers=headers, params=params, json=json
            )
    except Exception as exc:
        raise RuntimeError(f"Shopify direct call failed: {exc}") from exc

    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:300]
        raise RuntimeError(f"Shopify error {resp.status_code}: {body}")

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:2000]}


# No Composio-managed OAuth — use v3.1 auth_configs + connected_accounts in get_connect_url.

_COMPOSIO_NO_MANAGED_OAUTH: frozenset[str] = frozenset({"brevo", "shopify", "klaviyo"})

# Try v3.1 auth_configs FIRST for every OAuth toolkit. The legacy v1
# integration discovery endpoints now return 410 for newer Composio projects.
_COMPOSIO_TRY_V31_FIRST: frozenset[str] = frozenset({
    "gmail", "googlecalendar", "outlook",
    "slack", "googlesheets", "notion",
    "stripe", "mailchimp",
    "googlesearchconsole", "googleanalytics", "googleads",
    "facebook", "instagram", "youtube",
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

    # Social (Meta)
    "facebook":             "facebook",
    "instagram":            "instagram",
    "youtube":              "youtube",

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

TOOLKIT_FACEBOOK           = "facebook"

TOOLKIT_INSTAGRAM          = "instagram"

TOOLKIT_YOUTUBE            = "youtube"



ALL_TOOLKITS = list(_APP_NAMES.keys())



# ── Action name constants ──────────────────────────────────────────────────────

ACTION_GMAIL_FETCH        = "GMAIL_FETCH_EMAILS"

ACTION_GMAIL_SEND         = "GMAIL_SEND_EMAIL"

ACTION_GMAIL_DRAFT        = "GMAIL_CREATE_EMAIL_DRAFT"

ACTION_CALENDAR_LIST      = "GOOGLECALENDAR_EVENTS_LIST"

ACTION_CALENDAR_CREATE    = "GOOGLECALENDAR_CREATE_EVENT"

ACTION_CALENDAR_DELETE    = "GOOGLECALENDAR_DELETE_EVENT"

ACTION_OUTLOOK_FETCH      = "OUTLOOK_OUTLOOK_LIST_MESSAGES"

ACTION_OUTLOOK_SEND       = "OUTLOOK_OUTLOOK_SEND_EMAIL"

ACTION_OUTLOOK_REPLY      = "OUTLOOK_OUTLOOK_REPLY_EMAIL"

ACTION_OUTLOOK_SEARCH     = "OUTLOOK_OUTLOOK_SEARCH_MESSAGES"



# Shopify — prefer packaged actions over raw REST where possible

ACTION_SHOPIFY_GET_ORDERS_WITH_FILTERS = "SHOPIFY_GET_ORDER_LIST"

ACTION_SHOPIFY_GET_PRODUCTS_PAGINATED = "SHOPIFY_GET_PRODUCTS"



# Stripe

ACTION_STRIPE_LIST_INVOICES = "STRIPE_LIST_INVOICES"

ACTION_STRIPE_LIST_PAYMENT_INTENTS = "STRIPE_LIST_PAYMENT_INTENTS"



# Klaviyo

ACTION_KLAVIYO_GET_FLOWS = "KLAVIYO_GET_FLOWS"

ACTION_KLAVIYO_GET_METRICS = "KLAVIYO_GET_METRICS"



# Slack

ACTION_SLACK_TEST_AUTH = "SLACK_FETCH_TEAM_INFO"

ACTION_SLACK_LIST_CONVERSATIONS = "SLACK_LIST_CONVERSATIONS"

ACTION_SLACK_SEND_MESSAGE = "SLACK_SEND_MESSAGE"



# Facebook / Instagram (Meta Graph via Composio)
ACTION_FB_LIST_PAGES      = "FACEBOOK_GET_USER_PAGES"
ACTION_FB_CREATE_POST     = "FACEBOOK_CREATE_POST"
ACTION_FB_CREATE_PHOTO    = "FACEBOOK_CREATE_PHOTO_POST"
ACTION_FB_CREATE_VIDEO    = "FACEBOOK_CREATE_VIDEO_POST"
ACTION_IG_CREATE_MEDIA    = "INSTAGRAM_CREATE_MEDIA_CONTAINER"
ACTION_IG_PUBLISH_MEDIA   = "INSTAGRAM_CREATE_POST"
ACTION_IG_USER_INFO       = "INSTAGRAM_GET_USER_INFO"

# YouTube
ACTION_YT_MULTIPART_UPLOAD = "YOUTUBE_MULTIPART_UPLOAD_VIDEO"





def _get_key() -> str:

    return os.getenv("COMPOSIO_API_KEY", "").strip()





def _headers() -> Dict[str, str]:

    return {"x-api-key": _get_key(), "Content-Type": "application/json"}





def is_configured() -> bool:

    return bool(_get_key())


async def upload_file_for_tool(
    toolkit_slug: str,
    tool_slug: str,
    filename: str,
    data: bytes,
    mimetype: str,
) -> Dict[str, Any]:
    """Upload bytes to Composio file storage for tool actions (e.g. YouTube video)."""
    import hashlib

    key = _get_key()
    if not key:
        return {"error": "COMPOSIO_API_KEY not configured"}
    if not data:
        return {"error": "Empty file payload"}

    md5 = hashlib.md5(data).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            presign = await client.post(
                f"{_BASE}/v3/files/upload/request",
                headers=_headers(),
                json={
                    "md5": md5,
                    "toolkit_slug": toolkit_slug,
                    "tool_slug": tool_slug,
                    "filename": filename,
                    "mimetype": mimetype,
                },
            )
            if presign.status_code != 200:
                return {"error": f"Composio presign failed: HTTP {presign.status_code}"}
            pdata = presign.json()
            s3key = pdata.get("key")
            upload_url = pdata.get("new_presigned_url") or pdata.get("url")
            if not s3key or not upload_url:
                return {"error": "Composio presign missing upload fields"}
            if not pdata.get("exists"):
                put = await client.put(
                    upload_url,
                    content=data,
                    headers={"Content-Type": mimetype},
                )
                if put.status_code not in (200, 201, 204):
                    return {"error": f"Composio file upload failed: HTTP {put.status_code}"}
    except Exception as exc:
        logger.warning("[composio] upload_file_for_tool error: %s", exc)
        return {"error": str(exc)}

    return {"file": {"name": filename, "mimetype": mimetype, "s3key": s3key}}





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

        if resp.status_code in (401, 403):

            return {"error": _composio_err_text(data, resp.status_code)}

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



async def get_connect_url(user_id: str, toolkit: str, redirect_url: str, extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

    """Initiate OAuth for a toolkit and return the redirect URL."""

    _ACCOUNTS_CACHE.pop(user_id, None)

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

                    return out

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

                "data": extra_data or {},

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



_CONNECTED_STATUSES = {"ACTIVE", "CONNECTED", "VALID", "SUCCESS", "ENABLED"}

# OAuth in progress — must NOT show as connected in the UI
_PENDING_STATUSES = {"INITIATED", "INITIALIZING", "PENDING", "IN_PROGRESS"}
_ACCOUNTS_CACHE: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
CACHE_TTL = 5.0  # short TTL so post-OAuth status checks see fresh data quickly


def _normalize_app(s: str) -> str:
    import re
    return re.sub(r"[_\-\s]+", "", (s or "").lower())


async def _v3_list_user_accounts(user_id: str) -> List[Dict[str, Any]]:
    """Fetch all Composio connected accounts for a given user_id (v3, paginated).

    The v1 endpoint /api/v1/connectedAccounts was deprecated and now returns
    HTTP 410 Gone, so this is the only working list endpoint.
    """
    import time
    now = time.time()
    if user_id in _ACCOUNTS_CACHE:
        ts, cached = _ACCOUNTS_CACHE[user_id]
        if now - ts < CACHE_TTL:
            return cached

    items: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    async with httpx.AsyncClient(timeout=12.0) as client:
        while True:
            params: Dict[str, Any] = {"user_ids": user_id, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get(
                f"{_BASE}/v3/connected_accounts",
                headers=_headers(),
                params=params,
            )
            if resp.status_code != 200:
                logger.warning(
                    "[composio] v3 connected_accounts list failed: %s %s",
                    resp.status_code, resp.text[:200],
                )
                return items
            data = resp.json() if resp.content else {}
            page = data.get("items") or []
            for it in page:
                # Defensive: ignore items that don't belong to this user
                if isinstance(it, dict) and str(it.get("user_id") or "") == user_id:
                    items.append(it)
            cursor = data.get("next_cursor")
            if not cursor or not page:
                break
    _ACCOUNTS_CACHE[user_id] = (now, items)
    return items


def _account_matches_toolkit(item: Dict[str, Any], toolkit: str) -> bool:
    app_name_norm = _normalize_app(_APP_NAMES.get(toolkit.lower(), toolkit.lower()))
    toolkit_norm = _normalize_app(toolkit)
    slug = (item.get("toolkit") or {}).get("slug", "") if isinstance(item.get("toolkit"), dict) else ""
    slug_norm = _normalize_app(slug)
    if not slug_norm:
        return False
    return (
        app_name_norm in slug_norm
        or slug_norm in app_name_norm
        or toolkit_norm in slug_norm
    )


def _accounts_for_toolkit(
    items: List[Dict[str, Any]],
    toolkit: str,
    *,
    connected_only: bool = False,
    pending_only: bool = False,
) -> List[Dict[str, Any]]:
    matched: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not _account_matches_toolkit(item, toolkit):
            continue
        status = str(item.get("status") or "").upper()
        if connected_only and status not in _CONNECTED_STATUSES:
            continue
        if pending_only and status not in _PENDING_STATUSES:
            continue
        matched.append(item)
    return matched


async def get_connection_status(user_id: str, toolkit: str, force_refresh: bool = False) -> Dict[str, Any]:
    """Return {"connected": bool, "connection_id": str|None} for one toolkit.

    Pass force_refresh=True to bypass the short account-list cache and always
    fetch live data from Composio (used right after an OAuth popup closes).
    """

    # Shopify uses direct credentials stored in DB — bypass Composio entirely
    if toolkit.lower() == "shopify":
        creds = await _get_shopify_direct_creds(user_id)
        return {"connected": bool(creds), "connection_id": None}

    if not _get_key():
        return {"connected": False, "error": "COMPOSIO_API_KEY not configured"}

    # Always bust cache for single-toolkit checks so post-OAuth polling
    # immediately sees the newly ACTIVE account instead of stale data.
    if force_refresh:
        _ACCOUNTS_CACHE.pop(user_id, None)

    try:
        items = await _v3_list_user_accounts(user_id)
    except Exception as e:
        logger.warning("[composio] get_connection_status error: %s", e)
        return {"connected": False, "error": str(e)}

    for item in items:
        if not _account_matches_toolkit(item, toolkit):
            continue
        status = str(item.get("status") or "").upper()
        if status in _CONNECTED_STATUSES:
            return {"connected": True, "connection_id": item.get("id")}

    return {"connected": False}



async def get_all_connection_statuses(user_id: str) -> Dict[str, bool]:
    """Return connection status for all Zilo-supported toolkits (all apps)."""

    if not _get_key():
        return {t: False for t in ALL_TOOLKITS}

    try:
        items = await _v3_list_user_accounts(user_id)
    except Exception as e:
        logger.warning("[composio] get_all_connection_statuses error: %s", e)
        return {t: False for t in ALL_TOOLKITS}

    connected_slugs: set = set()
    for item in items:
        status = str(item.get("status") or "").upper()
        if status not in _CONNECTED_STATUSES:
            continue
        slug = (item.get("toolkit") or {}).get("slug", "") if isinstance(item.get("toolkit"), dict) else ""
        if slug:
            connected_slugs.add(_normalize_app(slug))

    results: Dict[str, bool] = {}
    for toolkit, app_name in _APP_NAMES.items():
        an = _normalize_app(app_name)
        tk = _normalize_app(toolkit)
        results[toolkit] = any(
            an in cn or cn in an or tk in cn
            for cn in connected_slugs
        )

    # Overlay direct Shopify credential status (DB-backed, no Composio account needed)
    shopify_creds = await _get_shopify_direct_creds(user_id)
    results["shopify"] = bool(shopify_creds)

    return results





# ── Disconnect ─────────────────────────────────────────────────────────────────



async def disconnect(user_id: str, toolkit: str) -> Dict[str, Any]:

    """Disconnect a user's connection(s) for a toolkit (active + stale pending OAuth)."""

    _ACCOUNTS_CACHE.pop(user_id, None)

    if not _get_key():

        return {"error": "COMPOSIO_API_KEY not configured"}

    try:
        items = await _v3_list_user_accounts(user_id)
    except Exception as e:
        logger.warning("[composio] disconnect list error: %s", e)
        return {"error": str(e)}

    to_remove = _accounts_for_toolkit(items, toolkit)
    if not to_remove:
        return {"disconnected": True, "note": "No connection found"}

    removed = 0
    errors: List[str] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for item in to_remove:
                conn_id = item.get("id")
                if not conn_id:
                    continue
                resp = await client.delete(
                    f"{_BASE}/v3/connected_accounts/{conn_id}",
                    headers=_headers(),
                )
                if resp.status_code in (200, 204, 404):
                    removed += 1
                else:
                    data = resp.json() if resp.content else {}
                    errors.append(data.get("message") or f"HTTP {resp.status_code}")
    except Exception as e:
        logger.error("[composio] disconnect error: %s", e)
        return {"error": str(e)}

    if errors and removed == 0:
        return {"error": "; ".join(errors)}
    return {"disconnected": True, "removed": removed}


async def cleanup_pending_connection(user_id: str, toolkit: str) -> Dict[str, Any]:
    """Remove in-progress OAuth accounts (e.g. user closed popup without logging in)."""
    if not _get_key():
        return {"error": "COMPOSIO_API_KEY not configured"}

    try:
        items = await _v3_list_user_accounts(user_id)
    except Exception as e:
        logger.warning("[composio] cleanup_pending list error: %s", e)
        return {"error": str(e)}

    pending = _accounts_for_toolkit(items, toolkit, pending_only=True)
    if not pending:
        return {"cleaned": 0}

    cleaned = 0
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for item in pending:
                conn_id = item.get("id")
                if not conn_id:
                    continue
                resp = await client.delete(
                    f"{_BASE}/v3/connected_accounts/{conn_id}",
                    headers=_headers(),
                )
                if resp.status_code in (200, 204, 404):
                    cleaned += 1
    except Exception as e:
        logger.warning("[composio] cleanup_pending error: %s", e)
        return {"error": str(e)}

    return {"cleaned": cleaned}





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

    # Shopify uses direct DB credentials — skip Composio entirely
    if toolkit.lower() == "shopify":
        creds = await _get_shopify_direct_creds(user_id)
        if not creds:
            raise RuntimeError(
                "Shopify is not connected. Go to the Shopify page and connect your store."
            )
        token = creds["token"]
        # Auto-refresh if expiring token is expired (or expires within 60s)
        import time as _time
        expires_at = creds.get("expires_at")
        if expires_at and int(_time.time()) >= int(expires_at) - 60:
            refreshed = await _shopify_refresh_access_token(creds)
            if refreshed:
                token = refreshed
        return await _shopify_direct_proxy(
            creds["domain"], token, method, path,
            params=params, json=json, timeout=timeout,
        )

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

    if a.startswith("FACEBOOK_"):

        return TOOLKIT_FACEBOOK

    if a.startswith("INSTAGRAM_"):

        return TOOLKIT_INSTAGRAM

    if a.startswith("YOUTUBE_"):

        return TOOLKIT_YOUTUBE

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





async def shopify_customers_via_composio_or_proxy(
    user_id: str,
    *,
    limit: int,
    created_at_min: Optional[str] = None,
) -> Dict[str, Any]:
    """List customers via Shopify Admin REST proxy."""
    lim = min(max(limit, 1), 250)
    params: Dict[str, str] = {"limit": str(lim)}
    if created_at_min:
        params["created_at_min"] = created_at_min
    return await composio_proxy(
        user_id,
        TOOLKIT_SHOPIFY,
        "GET",
        "/admin/api/2024-01/customers.json",
        params=params,
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
    """Execute a Composio action on behalf of a user (v3 tools/execute endpoint).

    v2 (/api/v2/actions/{action}/execute) was retired with HTTP 410.
    v3 uses /api/v3/tools/execute/{slug} with body {user_id, arguments,
    connected_account_id?} and response {data, successful, error, log_id}.
    """
    if not _get_key():
        return {"error": "COMPOSIO_API_KEY not configured in .env"}

    # Resolve connected_account_id for auth-requiring toolkits
    conn_id: Optional[str] = None
    toolkit = _toolkit_for_action(action)
    if toolkit:
        status = await get_connection_status(user_id, toolkit)
        conn_id = status.get("connection_id")
        if not status.get("connected"):
            return {
                "error": f"{toolkit.title()} is not connected. Connect it in the Integrations page first.",
            }

    body: Dict[str, Any] = {
        "user_id": user_id,
        "arguments": params or {},
    }
    if conn_id:
        body["connected_account_id"] = conn_id

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_BASE}/v3/tools/execute/{action}",
                headers=_headers(),
                json=body,
            )
            try:
                data = resp.json()
            except Exception:
                logger.warning("[composio] execute_action %s non-JSON response (HTTP %s)", action, resp.status_code)
                return {"error": f"HTTP {resp.status_code}"}

            if resp.status_code not in (200, 201):
                err = (
                    (data.get("error") or {}).get("message") if isinstance(data.get("error"), dict)
                    else data.get("error")
                ) or data.get("message") or f"HTTP {resp.status_code}"
                logger.warning("[composio] execute_action %s error: %s", action, err)
                return {"error": str(err)}

            # v3 wrapper: {data, successful, error, log_id}
            if data.get("successful") is False:
                err = data.get("error") or "action failed"
                logger.warning("[composio] execute_action %s not successful: %s", action, err)
                return {"error": str(err)}

            result = data.get("data")
            if result is None:
                result = data
            return {"success": True, "data": result}
    except Exception as e:
        logger.error("[composio] execute_action %s error: %s", action, e)
        return {"error": str(e)}

