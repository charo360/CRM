"""
Facebook Ad Library — free public API.
Requires FACEBOOK_AD_LIBRARY_TOKEN in env (platform-level long-lived token).

Getting a token:
  1. Create a Facebook app at developers.facebook.com
  2. Add "Marketing API" product
  3. Generate a long-lived user token with `ads_read` permission
  4. Add to .env.local: FACEBOOK_AD_LIBRARY_TOKEN=your_token
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

FB_AD_LIBRARY_URL = "https://graph.facebook.com/v18.0/ads_archive"


def _fb_token() -> Optional[str]:
    return os.environ.get("FACEBOOK_AD_LIBRARY_TOKEN", "").strip() or None


async def search_ads(
    keyword: str,
    countries: List[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search the Facebook Ad Library for active ads matching `keyword`.
    Returns ad count + sample ads with page name, spend, and creative text.
    """
    token = _fb_token()
    if not token:
        return {"available": False, "reason": "FACEBOOK_AD_LIBRARY_TOKEN not configured", "ads": [], "total": 0}

    if countries is None:
        countries = ["US"]

    params = {
        "access_token":        token,
        "ad_type":             "ALL",
        "ad_active_status":    "ACTIVE",
        "ad_reached_countries": str(countries).replace("'", '"'),
        "search_terms":        keyword,
        "fields":              "id,ad_creation_time,ad_creative_bodies,page_name,currency,spend,impressions,ad_snapshot_url",
        "limit":               str(min(limit, 50)),
    }

    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.get(FB_AD_LIBRARY_URL, params=params)
        data = r.json()
    except Exception as e:
        log.warning("[fb_ads] request error: %s", e)
        return {"available": False, "reason": str(e), "ads": [], "total": 0}

    if "error" in data:
        err = data["error"]
        log.warning("[fb_ads] API error: %s", err)
        return {"available": False, "reason": err.get("message", str(err)), "ads": [], "total": 0}

    raw_ads = data.get("data", [])
    ads = []
    for a in raw_ads:
        bodies = a.get("ad_creative_bodies") or []
        ads.append({
            "id":           a.get("id", ""),
            "page":         a.get("page_name", ""),
            "created":      a.get("ad_creation_time", ""),
            "body":         bodies[0][:200] if bodies else "",
            "spend":        a.get("spend", {}),
            "impressions":  a.get("impressions", {}),
            "snapshot_url": a.get("ad_snapshot_url", ""),
        })

    paging = data.get("paging", {})
    # Estimate total from cursors — FB doesn't return exact counts
    total_est = len(ads)
    if paging.get("next"):
        total_est = len(ads) * 5   # rough floor — there are more pages

    return {
        "available":    True,
        "keyword":      keyword,
        "ads":          ads,
        "total":        total_est,
        "has_more":     bool(paging.get("next")),
    }


async def get_ad_count(keyword: str, countries: List[str] = None) -> int:
    """Quick helper — returns estimated active ad count for a keyword."""
    result = await search_ads(keyword, countries=countries, limit=10)
    return result.get("total", 0)
