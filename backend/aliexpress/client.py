"""
AliExpress Open Platform API client (DS Center / Dropship).

Credentials required (per-user or from environment):
  ALIEXPRESS_APP_KEY     — your app key from open.aliexpress.com
  ALIEXPRESS_APP_SECRET  — your app secret
  ALIEXPRESS_ACCESS_TOKEN — OAuth access token (self-authorization for your own account)

Per-user mode: pass creds={"app_key": ..., "app_secret": ..., "access_token": ...}
to any function to use that user's credentials instead of env vars.

Auth:
  Every request is signed with HMAC-SHA256 over sorted parameters.

Docs: https://open.aliexpress.com/doc/api.htm
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger(__name__)

AE_BASE     = "https://api-sg.aliexpress.com/sync"
AE_BASE_EU  = "https://api-eur.aliexpress.com/sync"


def _ae_credentials() -> tuple[str, str, str]:
    app_key      = os.environ.get("ALIEXPRESS_APP_KEY", "").strip()
    app_secret   = os.environ.get("ALIEXPRESS_APP_SECRET", "").strip()
    access_token = os.environ.get("ALIEXPRESS_ACCESS_TOKEN", "").strip()
    if not app_key or not app_secret:
        raise RuntimeError(
            "ALIEXPRESS_APP_KEY and ALIEXPRESS_APP_SECRET are required. "
            "Create an app at https://open.aliexpress.com and add the keys to .env.local"
        )
    return app_key, app_secret, access_token


def _sign(params: Dict[str, str], app_secret: str) -> str:
    """AliExpress HMAC-SHA256 signature over sorted param key+value pairs."""
    sorted_keys = sorted(params.keys())
    s = "".join(f"{k}{params[k]}" for k in sorted_keys)
    return hmac.new(
        app_secret.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()


async def ae_call(method: str, params: Dict[str, Any], *, creds: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Make a signed request to the AliExpress Open Platform."""
    if creds:
        app_key      = creds["app_key"]
        app_secret   = creds["app_secret"]
        access_token = creds.get("access_token", "")
    else:
        app_key, app_secret, access_token = _ae_credentials()

    all_params: Dict[str, str] = {
        "method":       method,
        "app_key":      app_key,
        "timestamp":    str(int(time.time() * 1000)),
        "format":       "json",
        "v":            "2.0",
        "sign_method":  "sha256",
    }
    if access_token:
        all_params["access_token"] = access_token

    # Merge method-specific params (stringify values)
    for k, v in params.items():
        if v is not None:
            all_params[k] = str(v)

    all_params["sign"] = _sign({k: v for k, v in all_params.items()}, app_secret)

    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.post(AE_BASE, data=all_params)

    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"AliExpress API non-JSON response: {r.text[:300]}")

    if "error_response" in data:
        err = data["error_response"]
        raise RuntimeError(f"AliExpress API error [{err.get('code')}]: {err.get('msg', err)}")

    # Unwrap the nested response key (e.g. "aliexpress_ds_text_search_response")
    response_key = method.replace(".", "_") + "_response"
    body = data.get(response_key, data)

    # Some endpoints embed errors inside the unwrapped body (code without a result/data)
    if isinstance(body, dict):
        code = body.get("code")
        if code and not any(k in body for k in ("result", "data", "products")):
            msg = body.get("message") or body.get("msg") or code
            if code == "EXCEPTION_TEXT_SEARCH_FOR_DS":
                msg = "AliExpress DS text search requires an OAuth access_token — connect via /api/aliexpress/oauth/start"
            raise RuntimeError(f"AliExpress API error [{code}]: {msg}")
    return body


_SORT_MAP = {
    "SALE_PRICE_ASC":     "min_price,asc",
    "SALE_PRICE_DESC":    "min_price,desc",
    "LAST_VOLUME_DESC":   "orders,desc",
    "LAST_VOLUME_ASC":    "orders,asc",
}


async def ae_ds_search(
    keyword: str,
    *,
    category_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    page_size: int = 20,
    page_no: int = 1,
    sort: str = "SALE_PRICE_ASC",
    country_code: str = "US",
    currency: str = "USD",
    local: str = "en_US",
    creds: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Search AliExpress DS product catalog via aliexpress.ds.text.search.

    Requires an access_token (per-user OAuth) — without it the API returns
    EXCEPTION_TEXT_SEARCH_FOR_DS.
    """
    params: Dict[str, Any] = {
        "keyWord":     keyword,
        "countryCode": country_code,
        "currency":    currency,
        "local":       local,
        "pageSize":    min(page_size, 50),
        "pageIndex":   page_no,
        "sortBy":      _SORT_MAP.get(sort, sort),
    }
    if category_id:
        params["categoryId"] = category_id
    if min_price is not None:
        params["minPrice"] = min_price
    if max_price is not None:
        params["maxPrice"] = max_price
    return await ae_call("aliexpress.ds.text.search", params, creds=creds)


async def ae_ds_product_detail(product_id: str, ship_to: str = "US", *, creds: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Get full AliExpress DS product detail including variants and images."""
    return await ae_call("aliexpress.ds.product.get", {
        "product_id":       product_id,
        "ship_to_country":  ship_to,
        "target_currency":  "USD",
        "target_language":  "en",
    }, creds=creds)


async def ae_ds_create_order(order_payload: Dict[str, Any], *, creds: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Create a DS order on AliExpress."""
    return await ae_call("aliexpress.ds.order.create", {
        "param_place_order_request4_open_api_d_t_o": str(order_payload).replace("'", '"'),
    }, creds=creds)


async def ae_ds_get_order(ae_order_id: str, *, creds: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Get DS order status and tracking."""
    return await ae_call("aliexpress.ds.order.get", {"order_id": ae_order_id}, creds=creds)


async def ae_get_categories(*, creds: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Get AliExpress top-level DS categories."""
    return await ae_call("aliexpress.ds.category.get", {}, creds=creds)
