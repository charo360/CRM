"""DataForSEO Live API — optional real keyword metrics (same DATAFORSEO_TOKEN as the SEO agent)."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Common location_code values (DataForSEO); extend as needed.
_LOCATION_CODES: dict[str, int] = {
    "kenya": 2404,
    "ke": 2404,
    "nigeria": 2566,
    "ng": 2566,
    "united states": 2710,
    "united states of america": 2710,
    "usa": 2710,
    "us": 2710,
    "united kingdom": 2826,
    "uk": 2826,
    "gb": 2826,
    "india": 2356,
    "in": 2356,
    "australia": 2036,
    "au": 2036,
    "canada": 2124,
    "ca": 2124,
    "south africa": 2713,
    "za": 2713,
}


def dfs_enabled() -> bool:
    return bool(os.environ.get("DATAFORSEO_TOKEN", "").strip())


def resolve_location_code(country: str = "", country_code: str = "") -> int:
    cc = (country_code or "").strip().lower()
    if cc in _LOCATION_CODES:
        return _LOCATION_CODES[cc]
    key = (country or "").strip().lower()
    return _LOCATION_CODES.get(key, 2404)


def language_code_from_settings(primary_language: str) -> str:
    pl = (primary_language or "English").strip().lower()
    return {
        "english": "en",
        "swahili": "sw",
        "french": "fr",
        "spanish": "es",
        "arabic": "ar",
    }.get(pl, "en")


def _headers() -> dict[str, str]:
    token = os.environ.get("DATAFORSEO_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DATAFORSEO_TOKEN is not set")
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


async def dfs_post(endpoint: str, payload: list) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=45) as hc:
        resp = await hc.post(
            f"https://api.dataforseo.com/v3/{endpoint}",
            headers=_headers(),
            json=payload,
        )
    resp.raise_for_status()
    return resp.json()


async def fetch_diverse_keywords(
    seed_keyword: str,
    location: str = "",
    *,
    location_code: int = 2404,
    language_code: str = "en",
    limit: int = 30,
    exclude_phrases: set | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch keywords using multiple seed strategies so results include long-tail variety.
    Seeds used: main term · "how to X" · "best X in city" · "X for [use]" · "X near me".
    Merges all results, deduplicates, removes already-seen phrases, sorts by volume.
    """
    seed_keyword = (seed_keyword or "").strip()
    if not seed_keyword:
        return []

    exclude = {k.lower().strip() for k in (exclude_phrases or set())}
    city = location.split(",")[0].strip() if location else ""

    seeds = [seed_keyword]
    if city:
        seeds.append(f"best {seed_keyword} in {city}")
        seeds.append(f"{seed_keyword} near me")
    seeds.append(f"how to {seed_keyword}")
    seeds.append(f"affordable {seed_keyword}")

    seen: dict[str, dict] = {}
    per_seed = max(15, limit // len(seeds) + 5)

    for seed in seeds:
        try:
            batch = await fetch_keyword_ideas_live(
                seed,
                location_code=location_code,
                language_code=language_code,
                limit=per_seed,
            )
            for item in batch:
                kw = (item.get("keyword") or "").lower().strip()
                if kw and kw not in exclude and kw not in seen:
                    seen[kw] = item
        except Exception as e:
            logger.warning("[dataforseo] diverse seed %r failed: %s", seed, e)

    sorted_results = sorted(seen.values(), key=lambda x: x.get("search_volume") or 0, reverse=True)
    logger.info("[dataforseo] diverse fetch: %d unique fresh keywords (excluded %d known)", len(sorted_results), len(exclude))
    return sorted_results[:limit]


async def fetch_search_volumes_batch(
    keywords: list[str],
    *,
    location_code: int = 2404,
    language_code: str = "en",
) -> dict[str, int]:
    """Look up exact search volumes for a list of known keywords.
    Returns {keyword_lower: volume} mapping. Missing keywords get volume=0.
    Uses keywords_data/google_ads/search_volume/live (works on all plans).
    """
    kws = [k.strip() for k in keywords if k.strip()]
    if not kws:
        return {}
    out: dict[str, int] = {}
    try:
        # DataForSEO accepts up to 1000 keywords per call; chunk at 100 to stay safe
        chunk_size = 100
        for i in range(0, len(kws), chunk_size):
            batch = kws[i:i + chunk_size]
            data = await dfs_post(
                "keywords_data/google_ads/search_volume/live",
                [{
                    "keywords": batch,
                    "location_code": location_code,
                    "language_code": language_code,
                }],
            )
            tasks = data.get("tasks") or []
            if not tasks or tasks[0].get("status_code") != 20000:
                msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
                logger.warning("[dataforseo] search_volume batch status: %s", msg)
                continue
            items = tasks[0].get("result") or []
            for item in items:
                kw = (item.get("keyword") or "").lower().strip()
                vol = int(item.get("search_volume") or 0)
                if kw:
                    out[kw] = vol
    except Exception as e:
        logger.warning("[dataforseo] fetch_search_volumes_batch failed: %s", e)
    return out


async def fetch_keyword_ideas_live(
    seed_keyword: str,
    *,
    location_code: int = 2404,
    language_code: str = "en",
    limit: int = 25,
) -> list[dict[str, Any]]:
    seed_keyword = (seed_keyword or "").strip()
    if not seed_keyword:
        return []
    lim = max(1, min(int(limit), 50))

    # Use the standard keywords_data endpoint (works on all plans).
    # The Labs endpoint (dataforseo_labs/google/keyword_ideas/live) requires a
    # separate Labs subscription and silently returns [] when not available.
    try:
        data = await dfs_post(
            "keywords_data/google_ads/keywords_for_keywords/live",
            [{
                "keywords": [seed_keyword],
                "location_code": location_code,
                "language_code": language_code,
                "include_seed_keyword": True,
                "include_serp_info": False,
                "limit": lim,
            }],
        )
    except Exception as e:
        logger.warning("[dataforseo] keyword_ideas request failed: %s", e)
        return []

    tasks = data.get("tasks") or []
    if not tasks or tasks[0].get("status_code") != 20000:
        msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
        logger.warning("[dataforseo] keyword_ideas API status: %s | code: %s",
                       msg, tasks[0].get("status_code") if tasks else "N/A")
        return []

    # keywords_for_keywords/live wraps items under result[0]["items"], not result[] directly
    result = tasks[0].get("result") or []
    if not result:
        logger.warning("[dataforseo] keyword_ideas returned empty result for seed=%r", seed_keyword)
        return []
    items = result[0].get("items") or []
    if not items:
        logger.warning("[dataforseo] keyword_ideas returned no items for seed=%r", seed_keyword)
        return []

    items.sort(key=lambda x: x.get("search_volume") or 0, reverse=True)

    out: list[dict[str, Any]] = []
    for item in items:
        kw = item.get("keyword") or ""
        if not kw:
            continue
        vol = int(item.get("search_volume") or 0)
        cpc_raw = item.get("cpc")
        comp_raw = item.get("competition")  # 0.0–1.0 float

        # Map competition float → difficulty string
        if comp_raw is None:
            diff_s = "medium"
        elif comp_raw < 0.33:
            diff_s = "low"
        elif comp_raw < 0.66:
            diff_s = "medium"
        else:
            diff_s = "high"

        if vol >= 10000:
            pri = 5
        elif vol >= 2000:
            pri = 4
        elif vol >= 500:
            pri = 3
        elif vol >= 50:
            pri = 2
        else:
            pri = 1

        idea = f"Create content for people searching \"{kw}\""
        idea += f" (~{vol:,}/mo)." if vol else "."

        row: dict[str, Any] = {
            "keyword": kw,
            "intent": "informational",
            "difficulty": diff_s,
            "priority": pri,
            "content_idea": idea,
            "search_volume": vol if vol else None,
        }
        try:
            row["cpc"] = float(cpc_raw) if cpc_raw is not None else None
        except (TypeError, ValueError):
            row["cpc"] = None
        if comp_raw is not None:
            row["competition"] = comp_raw

        out.append(row)
        if len(out) >= lim:
            break

    logger.info("[dataforseo] Returning %d keyword ideas for seed=%r", len(out), seed_keyword)
    return out
