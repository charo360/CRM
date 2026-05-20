"""
Google Trends via pytrends — no API key required.
Returns interest over time + related rising queries for a keyword.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


async def get_interest_over_time(
    keyword: str,
    timeframe: str = "today 3-m",
    geo: str = "US",
) -> Dict[str, Any]:
    """Return weekly interest score (0-100) for `keyword` over the past 3 months."""
    def _fetch():
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25), retries=2, backoff_factor=0.5)
        pt.build_payload([keyword], timeframe=timeframe, geo=geo)
        df = pt.interest_over_time()
        if df is None or df.empty:
            return []
        col = keyword if keyword in df.columns else df.columns[0]
        return [
            {"date": str(idx.date()), "value": int(row[col])}
            for idx, row in df.iterrows()
            if not row.get("isPartial", False)
        ]

    try:
        data = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        if not data:
            return {"keyword": keyword, "trend": [], "score": 0, "direction": "flat"}
        values = [d["value"] for d in data]
        # Trend direction: compare last 4 weeks to prior 4 weeks
        recent = values[-4:] if len(values) >= 4 else values
        prior  = values[-8:-4] if len(values) >= 8 else values[:max(1, len(values)//2)]
        avg_recent = sum(recent) / len(recent) if recent else 0
        avg_prior  = sum(prior)  / len(prior)  if prior  else 1
        change_pct = round(((avg_recent - avg_prior) / max(avg_prior, 1)) * 100)
        direction = "rising" if change_pct > 10 else "falling" if change_pct < -10 else "stable"
        return {
            "keyword":    keyword,
            "trend":      data[-12:],   # last 12 weeks
            "score":      int(avg_recent),
            "change_pct": change_pct,
            "direction":  direction,
        }
    except Exception as e:
        log.warning("[trends] %s: %s", keyword, e)
        return {"keyword": keyword, "trend": [], "score": 0, "direction": "unknown", "error": str(e)}


async def get_related_rising(
    keyword: str,
    geo: str = "US",
) -> List[Dict[str, Any]]:
    """Return rising related queries for `keyword` — surface emerging products."""
    def _fetch():
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25), retries=2, backoff_factor=0.5)
        pt.build_payload([keyword], timeframe="today 3-m", geo=geo)
        related = pt.related_queries()
        rising = related.get(keyword, {}).get("rising")
        if rising is None or rising.empty:
            return []
        return [
            {"query": str(row["query"]), "value": str(row["value"])}
            for _, row in rising.head(10).iterrows()
        ]

    try:
        return await asyncio.get_event_loop().run_in_executor(None, _fetch)
    except Exception as e:
        log.warning("[trends/related] %s: %s", keyword, e)
        return []


async def batch_trends(
    keywords: List[str],
    geo: str = "US",
) -> List[Dict[str, Any]]:
    """Fetch trend scores for up to 5 keywords in a single pytrends call."""
    keywords = keywords[:5]

    def _fetch():
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25), retries=2, backoff_factor=0.5)
        pt.build_payload(keywords, timeframe="today 3-m", geo=geo)
        df = pt.interest_over_time()
        if df is None or df.empty:
            return {k: 0 for k in keywords}
        recent = df.tail(4)
        return {k: int(recent[k].mean()) for k in keywords if k in recent.columns}

    try:
        scores = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [{"keyword": k, "score": scores.get(k, 0)} for k in keywords]
    except Exception as e:
        log.warning("[batch_trends] %s", e)
        return [{"keyword": k, "score": 0} for k in keywords]
