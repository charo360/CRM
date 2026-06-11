"""
Web research for Decision Room — gives Zilo outside-world context (benchmarks,
competitor pricing, market norms) so sparring isn't limited to CRM data.

Self-contained: Tavily when TAVILY_API_KEY is set, DuckDuckGo otherwise.
Best-effort and time-boxed — never blocks or fails a spar.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def web_research(query: str, *, max_results: int = 5) -> dict[str, Any]:
    """Return {answer, results:[{title,url,snippet}], source}. Empty on failure."""
    query = (query or "").strip()
    if not query:
        return {"answer": "", "results": [], "source": "none"}
    max_results = max(1, min(int(max_results or 5), 8))

    tavily_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if tavily_key:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                        "include_answer": True,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "answer": data.get("answer") or "",
                        "results": [
                            {
                                "title": r.get("title", ""),
                                "url": r.get("url", ""),
                                "snippet": r.get("content", ""),
                            }
                            for r in (data.get("results") or [])
                        ][:max_results],
                        "source": "tavily",
                    }
                logger.warning("[decision-research] Tavily HTTP %s", resp.status_code)
        except Exception as e:
            logger.warning("[decision-research] Tavily failed: %s — falling back", e)

    # DuckDuckGo fallback — no key required.
    try:
        from duckduckgo_search import AsyncDDGS

        async with AsyncDDGS() as ddgs:
            raw = await ddgs.text(query, max_results=max_results)
        results = [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in (raw or [])
        ]
        if results:
            return {"answer": "", "results": results[:max_results], "source": "duckduckgo"}
    except Exception as e:
        logger.warning("[decision-research] DuckDuckGo failed: %s", e)

    return {"answer": "", "results": [], "source": "none"}


def build_research_query(question: str, ctx: dict[str, Any]) -> str:
    """Craft a market/benchmark query from the founder's decision + business context."""
    bk = ctx.get("business_knowledge") or {}
    industry = (
        bk.get("industry")
        or bk.get("business_type")
        or ctx.get("business_type")
        or ""
    )
    base = question.strip()
    if industry:
        return f"{base} — {industry} small business benchmarks, pricing, and industry norms 2026"
    return f"{base} — small business benchmarks, pricing norms, and best practices 2026"


def format_research_for_prompt(research: dict[str, Any]) -> str:
    """Compact web-context block for the spar prompt. Empty string if nothing useful."""
    results = research.get("results") or []
    answer = (research.get("answer") or "").strip()
    if not results and not answer:
        return ""
    lines: list[str] = []
    if answer:
        lines.append(f"Web summary: {answer[:600]}")
    for r in results[:5]:
        snippet = (r.get("snippet") or "").strip().replace("\n", " ")
        if snippet:
            lines.append(f"- {r.get('title', '')[:90]}: {snippet[:240]}")
    return "\n".join(lines)
