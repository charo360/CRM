"""
Winning product analyzer — combines Google Trends + CJ Hot Products + Facebook Ads
into a single opportunity score per product.

Opportunity Score (0-100):
  - Trend score     × 0.30  (Google Trends recent avg, 0-100)
  - Sales score     × 0.45  (CJ order volume, normalized to 0-100)
  - Ad spend score  × 0.25  (FB ad count, capped at 200 → 100)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _normalize(value: float, max_val: float) -> float:
    if max_val <= 0:
        return 0.0
    return min(100.0, (value / max_val) * 100)


def _opportunity_score(trend: float, sales: float, ads: float) -> int:
    return round(trend * 0.30 + sales * 0.45 + ads * 0.25)


async def find_winning_products(
    niche: str,
    country: str = "US",
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Full market analysis for a niche.
    Returns ranked winning products with scores from all three sources.
    """
    from market_intelligence.trends import get_interest_over_time, get_related_rising
    from market_intelligence.fb_ads import search_ads

    # Run trends + FB ads in parallel (CJ hot products separate)
    trends_task  = asyncio.create_task(get_interest_over_time(niche, geo=country))
    rising_task  = asyncio.create_task(get_related_rising(niche, geo=country))
    fb_task      = asyncio.create_task(search_ads(niche, countries=[country], limit=20))

    # CJ hot products
    cj_products: List[Dict[str, Any]] = []
    try:
        from cj_dropship.client import cj_get
        data = await cj_get("/product/list", {
            "pageNum": 1, "pageSize": min(limit * 2, 50),
            "productNameEn": niche,
        })
        raw = data.get("list", []) if isinstance(data, dict) else []
        raw.sort(key=lambda p: int(p.get("listedNum", 0) or 0), reverse=True)
        for p in raw[:limit]:
            cost = float(str(p.get("sellPrice", 0)).split()[0].replace(",", "") or 0)
            cj_products.append({
                "cj_pid":       p.get("pid", ""),
                "title":        p.get("productNameEn") or p.get("productName", ""),
                "category":     p.get("categoryName", ""),
                "cost":         cost,
                "sell_price":   round(cost * 2.5, 2),
                "margin":       round(cost * 1.5, 2),
                "orders":       int(p.get("listedNum", 0) or 0),
                "free_ship":    bool(p.get("isFreeShipping", False)),
                "image":        p.get("productImage", ""),
            })
    except Exception as e:
        log.warning("[analyzer] CJ fetch failed: %s", e)

    trend_data, rising, fb_data = await asyncio.gather(trends_task, rising_task, fb_task)

    # Normalize sales volume
    max_orders = max((p["orders"] for p in cj_products), default=1)
    fb_total   = fb_data.get("total", 0) if fb_data.get("available") else 0
    trend_score = trend_data.get("score", 0)
    ads_score   = _normalize(fb_total, 200)   # 200 active ads = max score

    # Build product cards with opportunity scores
    products = []
    for p in cj_products:
        s_score = _normalize(p["orders"], max_orders)
        opp     = _opportunity_score(trend_score, s_score, ads_score)
        products.append({**p, "opportunity_score": opp})

    products.sort(key=lambda x: x["opportunity_score"], reverse=True)

    return {
        "niche":        niche,
        "country":      country,
        "trend":        trend_data,
        "rising":       rising[:8],
        "fb_ads": {
            "available":  fb_data.get("available", False),
            "total":      fb_total,
            "sample_ads": fb_data.get("ads", [])[:5],
        },
        "products":     products[:limit],
        "summary": {
            "trend_direction":  trend_data.get("direction", "unknown"),
            "trend_change_pct": trend_data.get("change_pct", 0),
            "active_fb_ads":    fb_total,
            "top_cj_orders":    cj_products[0]["orders"] if cj_products else 0,
        },
    }
