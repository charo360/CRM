"""
Trend data cache — MongoDB-backed, TTL-aware.
Saves Meta Ads Library and TikTok Creative Center results so the
design agent gets instant responses without hitting external APIs every call.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COLLECTION = "trend_cache"
DEFAULT_TTL_HOURS = 24

# Categories we pre-warm every night — add more as your user base grows
PREWARM_CATEGORIES = [
    "skincare", "fashion", "food", "fitness", "tech",
    "beauty", "health", "ecommerce", "home", "education",
]

# Countries to pre-warm (your primary markets)
PREWARM_COUNTRIES_META   = [["KE"], ["NG"], ["ZA"], ["US"]]
PREWARM_COUNTRY_TIKTOK   = ["KE", "NG", "US"]


def _cache_key(platform: str, query: str, country: str) -> str:
    raw = f"{platform}:{query.lower().strip()}:{country.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


async def ensure_ttl_index(db) -> None:
    """Create TTL index on expires_at once at startup."""
    try:
        await db[COLLECTION].create_index(
            "expires_at",
            expireAfterSeconds=0,
            background=True,
        )
        await db[COLLECTION].create_index("cache_key", unique=True, background=True)
    except Exception as e:
        logger.warning("[trend_cache] Index creation skipped: %s", e)


async def get_cached(db, platform: str, query: str, country: str) -> Optional[Dict[str, Any]]:
    """Return cached data if still fresh, else None."""
    key = _cache_key(platform, query, country)
    doc = await db[COLLECTION].find_one({"cache_key": key})
    if not doc:
        return None
    if doc.get("expires_at") and doc["expires_at"] < datetime.utcnow():
        return None
    return doc.get("data")


async def set_cached(
    db,
    platform: str,
    query: str,
    country: str,
    data: Dict[str, Any],
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> None:
    """Upsert trend data into the cache with an expiry timestamp."""
    key = _cache_key(platform, query, country)
    now = datetime.utcnow()
    doc = {
        "cache_key":  key,
        "platform":   platform,
        "query":      query.lower().strip(),
        "country":    country.lower().strip(),
        "data":       data,
        "fetched_at": now,
        "expires_at": now + timedelta(hours=ttl_hours),
    }
    try:
        await db[COLLECTION].update_one(
            {"cache_key": key},
            {"$set": doc},
            upsert=True,
        )
    except Exception as e:
        logger.warning("[trend_cache] Failed to write cache: %s", e)


async def prewarm_all(db) -> None:
    """
    Nightly job: refresh trend data for common categories across primary markets.
    Runs at 2 AM UTC (5 AM EAT) so the cache is hot when users start their day.
    """
    from trend_service import search_meta_ads, search_tiktok_top_ads

    logger.info("[trend_cache] Starting nightly pre-warm...")
    meta_hits = tiktok_hits = errors = 0

    # Meta Ads Library — per category × per country list
    for category in PREWARM_CATEGORIES:
        for countries in PREWARM_COUNTRIES_META:
            country_key = ",".join(countries)
            try:
                existing = await get_cached(db, "meta", category, country_key)
                if existing:
                    continue  # still fresh from a user query earlier today
                result = await search_meta_ads(category, countries, limit=25)
                if not result.get("error"):
                    await set_cached(db, "meta", category, country_key, result)
                    meta_hits += 1
                else:
                    logger.warning("[trend_cache] Meta pre-warm error %s/%s: %s", category, country_key, result["error"])
                    errors += 1
            except Exception as e:
                logger.error("[trend_cache] Meta pre-warm exception %s/%s: %s", category, country_key, e)
                errors += 1

    # TikTok Creative Center — per category × per country
    for category in PREWARM_CATEGORIES:
        for country in PREWARM_COUNTRY_TIKTOK:
            try:
                existing = await get_cached(db, "tiktok", category, country)
                if existing:
                    continue
                result = await search_tiktok_top_ads(category, country_code=country, period=30)
                if not result.get("error"):
                    await set_cached(db, "tiktok", category, country, result)
                    tiktok_hits += 1
                else:
                    # TikTok key may not be configured yet — log quietly
                    logger.debug("[trend_cache] TikTok pre-warm skipped %s/%s: %s", category, country, result["error"])
            except Exception as e:
                logger.error("[trend_cache] TikTok pre-warm exception %s/%s: %s", category, country, e)
                errors += 1

    logger.info(
        "[trend_cache] Pre-warm complete — meta:%d tiktok:%d errors:%d",
        meta_hits, tiktok_hits, errors,
    )
