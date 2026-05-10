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

    try:
        data = await dfs_post(
            "dataforseo_labs/google/keyword_ideas/live",
            [{
                "keywords": [seed_keyword],
                "location_code": location_code,
                "language_code": language_code,
                "limit": lim,
            }],
        )
    except Exception as e:
        logger.warning("[dataforseo] keyword_ideas request failed: %s", e)
        return []

    tasks = data.get("tasks") or []
    if not tasks or tasks[0].get("status_code") != 20000:
        msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
        logger.warning("[dataforseo] keyword_ideas API status: %s", msg)
        return []

    items = (tasks[0].get("result") or [{}])[0].get("items") or []
    if not items:
        return []

    items.sort(
        key=lambda x: (x.get("keyword_info") or {}).get("search_volume") or 0,
        reverse=True,
    )

    out: list[dict[str, Any]] = []
    for item in items:
        kw = item.get("keyword") or ""
        if not kw:
            continue
        ki = item.get("keyword_info") or {}
        vol = int(ki.get("search_volume") or 0)
        kd_raw = (item.get("keyword_properties") or {}).get("keyword_difficulty")
        kd: int | None = int(kd_raw) if kd_raw is not None else None
        intent = (item.get("search_intent_info") or {}).get("main_intent") or "informational"
        cpc = ki.get("cpc")
        comp = ki.get("competition_level") or ""

        if kd is None:
            diff_s = "medium"
        elif kd < 30:
            diff_s = "low"
        elif kd < 60:
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
            "intent": str(intent).lower(),
            "difficulty": diff_s,
            "priority": pri,
            "content_idea": idea,
            "search_volume": vol if vol else None,
        }
        if cpc is not None:
            try:
                row["cpc"] = float(cpc)
            except (TypeError, ValueError):
                row["cpc"] = None
        else:
            row["cpc"] = None
        if comp:
            row["competition"] = comp
        if kd is not None:
            row["keyword_difficulty_score"] = kd

        out.append(row)
        if len(out) >= lim:
            break

    return out
