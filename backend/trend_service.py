"""
Ad trend intelligence — Meta Ads Library + TikTok Creative Center.
All results are cached in MongoDB (trend_cache collection) with a 24-hour TTL.
The design agent always hits the cache first — external APIs only called on a miss.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

META_APP_ID     = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")

META_ADS_LIBRARY_URL = "https://graph.facebook.com/v23.0/ads_archive"
TIKTOK_AD_QUERY_URL  = "https://business-api.tiktok.com/open_api/v1.3/cc/discovery/top_ads/list/"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _meta_app_token() -> str:
    return f"{META_APP_ID}|{META_APP_SECRET}"


def _days_running(start_str: Optional[str]) -> Optional[int]:
    """How many days has an ad been running (longer = higher confidence it's working)."""
    if not start_str:
        return None
    try:
        start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        return (datetime.now(start.tzinfo) - start).days
    except Exception:
        return None


def _summarise_meta_ads(ads: List[Dict]) -> List[Dict]:
    """Reduce raw Meta API rows to what the design agent actually needs."""
    out = []
    for ad in ads:
        bodies   = ad.get("ad_creative_bodies") or []
        titles   = ad.get("ad_creative_link_titles") or []
        captions = ad.get("ad_creative_link_captions") or []
        imps     = ad.get("impressions") or {}
        days     = _days_running(ad.get("ad_delivery_start_time"))
        platforms = ad.get("publisher_platforms") or []

        out.append({
            "page":         ad.get("page_name", ""),
            "headline":     titles[0] if titles else "",
            "copy":         bodies[0] if bodies else "",
            "caption":      captions[0] if captions else "",
            "platforms":    platforms,
            "days_running": days,
            "impressions":  f"{imps.get('lower_bound','?')}–{imps.get('upper_bound','?')}",
            "snapshot_url": ad.get("ad_snapshot_url", ""),
            "signal":       "proven" if days and days >= 21 else ("active" if days and days >= 7 else "new"),
        })

    # Sort: proven winners first, then by days running
    out.sort(key=lambda x: (x["signal"] != "proven", -(x["days_running"] or 0)))
    return out


# ─── Meta Ads Library ─────────────────────────────────────────────────────────

async def search_meta_ads(
    search_terms: str,
    countries: List[str],
    limit: int = 20,
    active_only: bool = True,
    days_back: int = 90,
    db=None,
) -> Dict[str, Any]:
    """
    Search Meta Ads Library for active ads matching search_terms in given countries.
    Checks MongoDB cache first — only hits Meta API on a cache miss.
    """
    if not META_APP_ID or not META_APP_SECRET:
        return {"error": "META_APP_ID / META_APP_SECRET not configured"}

    country_key = ",".join(sorted(countries))

    # ── Cache check ──────────────────────────────────────────────────────────
    if db is not None:
        from trend_cache import get_cached, set_cached
        cached = await get_cached(db, "meta", search_terms, country_key)
        if cached:
            logger.debug("[trend_service] Meta cache hit: %s / %s", search_terms, country_key)
            cached["_from_cache"] = True
            return cached

    date_min = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params: Dict[str, Any] = {
        "access_token":        _meta_app_token(),
        "search_terms":        search_terms,
        "ad_reached_countries": str(countries).replace("'", '"'),
        "ad_type":             "ALL",
        "ad_active_status":    "ACTIVE" if active_only else "ALL",
        "ad_delivery_date_min": date_min,
        "fields": ",".join([
            "page_name",
            "ad_creative_bodies",
            "ad_creative_link_titles",
            "ad_creative_link_captions",
            "ad_delivery_start_time",
            "ad_snapshot_url",
            "publisher_platforms",
            "impressions",
        ]),
        "limit": limit,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(META_ADS_LIBRARY_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("[meta_ads] HTTP error %s: %s", e.response.status_code, e.response.text[:400])
        return {"error": f"Meta API error {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        logger.error("[meta_ads] Request failed: %s", e)
        return {"error": str(e)}

    raw_ads: List[Dict] = data.get("data", [])
    if not raw_ads:
        return {
            "success": True,
            "total_found": 0,
            "ads": [],
            "insights": f"No active ads found for '{search_terms}' in {countries}. This could mean low competition — an opportunity.",
        }

    ads = _summarise_meta_ads(raw_ads)
    proven = [a for a in ads if a["signal"] == "proven"]

    # Build a plain-English insights block for the agent
    top_headlines  = [a["headline"] for a in ads if a["headline"]][:5]
    top_copy_hooks = [a["copy"][:80] for a in ads if a["copy"]][:5]
    platforms_used = list({p for a in ads for p in a["platforms"]})

    insights_lines = [
        f"Found {len(ads)} active ads for '{search_terms}' in {countries}.",
        f"{len(proven)} ads have been running 21+ days — these are proven performers.",
        f"Platforms in use: {', '.join(platforms_used) if platforms_used else 'unknown'}.",
    ]
    if top_headlines:
        insights_lines.append(f"Common headline themes: {' | '.join(top_headlines)}")
    if top_copy_hooks:
        insights_lines.append(f"Opening copy hooks: {' | '.join(top_copy_hooks)}")
    if proven:
        insights_lines.append(
            f"Top proven ad (running {proven[0]['days_running']} days, ~{proven[0]['impressions']} impressions): "
            f"\"{proven[0]['headline']}\" by {proven[0]['page']}"
        )

    result = {
        "success":      True,
        "total_found":  len(ads),
        "ads":          ads[:10],
        "insights":     " ".join(insights_lines),
        "proven_count": len(proven),
    }

    # ── Cache save ───────────────────────────────────────────────────────────
    if db is not None:
        from trend_cache import set_cached
        await set_cached(db, "meta", search_terms, country_key, result)

    return result


# ─── TikTok Creative Center ───────────────────────────────────────────────────

# TikTok industry IDs (most common — full list at developers.tiktok.com)
TIKTOK_INDUSTRIES: Dict[str, str] = {
    "beauty":       "24600001",
    "skincare":     "24600001",
    "fashion":      "24600002",
    "food":         "24600003",
    "fitness":      "24600004",
    "tech":         "24600005",
    "home":         "24600006",
    "health":       "24600007",
    "education":    "24600008",
    "finance":      "24600009",
    "travel":       "24600010",
    "ecommerce":    "24600011",
    "entertainment":"24600012",
}


def _guess_industry_id(category: str) -> str:
    """Best-effort map of a free-text category to a TikTok industry ID."""
    cat = category.lower()
    for keyword, iid in TIKTOK_INDUSTRIES.items():
        if keyword in cat:
            return iid
    return "24600011"  # default: ecommerce


async def search_tiktok_top_ads(
    category: str,
    country_code: str = "US",
    period: int = 30,
    limit: int = 20,
    db=None,
) -> Dict[str, Any]:
    """
    Fetch top-performing TikTok ads for a category using TikTok Creative Center API.
    Checks MongoDB cache first — only hits TikTok API on a cache miss.
    Requires TIKTOK_ACCESS_TOKEN in .env (apply at developers.tiktok.com → Commercial Content API).
    """
    # ── Cache check ──────────────────────────────────────────────────────────
    if db is not None:
        from trend_cache import get_cached
        cached = await get_cached(db, "tiktok", category, country_code)
        if cached:
            logger.debug("[trend_service] TikTok cache hit: %s / %s", category, country_code)
            cached["_from_cache"] = True
            return cached

    if not TIKTOK_ACCESS_TOKEN:
        return {
            "error": (
                "TIKTOK_ACCESS_TOKEN not configured. "
                "Apply for TikTok Commercial Content API access at https://developers.tiktok.com "
                "then add TIKTOK_ACCESS_TOKEN=your_token to .env"
            )
        }

    industry_id = _guess_industry_id(category)

    params = {
        "industry_id":  industry_id,
        "country_code": country_code.upper(),
        "period":       period,
        "page":         1,
        "page_size":    limit,
    }
    headers = {
        "Access-Token": TIKTOK_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(TIKTOK_AD_QUERY_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("[tiktok_ads] HTTP error %s: %s", e.response.status_code, e.response.text[:400])
        return {"error": f"TikTok API error {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        logger.error("[tiktok_ads] Request failed: %s", e)
        return {"error": str(e)}

    if data.get("code") != 0:
        return {"error": f"TikTok API returned code {data.get('code')}: {data.get('message', 'unknown error')}"}

    raw_ads: List[Dict] = (data.get("data") or {}).get("list") or []
    if not raw_ads:
        return {
            "success": True,
            "total_found": 0,
            "ads": [],
            "insights": f"No top ads found for '{category}' in {country_code} over the last {period} days.",
        }

    ads = []
    for ad in raw_ads:
        ads.append({
            "ad_title":    ad.get("ad_title", ""),
            "brand_name":  ad.get("brand_name", ""),
            "cover_url":   ad.get("cover_url", ""),
            "video_url":   ad.get("video_url", ""),
            "like_count":  ad.get("like_count", 0),
            "comment_count": ad.get("comment_count", 0),
            "share_count": ad.get("share_count", 0),
            "ctr_rank":    ad.get("ctr_rank", ""),
            "duration":    ad.get("video_info", {}).get("duration", ""),
        })

    # Sort by like count as a proxy for performance
    ads.sort(key=lambda x: x["like_count"], reverse=True)

    top_titles  = [a["ad_title"]   for a in ads if a["ad_title"]][:5]
    top_brands  = [a["brand_name"] for a in ads if a["brand_name"]][:5]

    insights_lines = [
        f"Found {len(ads)} top TikTok ads for '{category}' in {country_code} (last {period} days).",
        f"Top brands running ads: {', '.join(top_brands)}." if top_brands else "",
        f"Top ad titles/hooks: {' | '.join(top_titles)}." if top_titles else "",
        "Short-form video (15–30s) dominates TikTok ads in this category." if ads else "",
    ]

    result = {
        "success":     True,
        "total_found": len(ads),
        "ads":         ads[:10],
        "insights":    " ".join(l for l in insights_lines if l),
    }

    # ── Cache save ───────────────────────────────────────────────────────────
    if db is not None:
        from trend_cache import set_cached
        await set_cached(db, "tiktok", category, country_code, result)

    return result
