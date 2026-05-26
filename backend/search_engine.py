"""
Multi-Engine Search Pipeline
Runs DDG + Brave Search + Reddit + NewsAPI in parallel.
No new dependencies needed — uses httpx (already installed).

Env vars (all optional, degrade gracefully):
  BRAVE_SEARCH_API_KEY   — https://api.search.brave.com (free: 2000/month)
  NEWS_API_KEY           — https://newsapi.org (free: 100/day)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Result schema: {"title", "url", "snippet", "source"}
# ─────────────────────────────────────────────────────────────────────────────

SearchResult = Dict[str, str]


def _dedup(results: List[SearchResult]) -> List[SearchResult]:
    seen: set = set()
    out: List[SearchResult] = []
    for r in results:
        u = r.get("url", "")
        if u and u not in seen:
            seen.add(u)
            out.append(r)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# DDG (duckduckgo-search) — runs in thread pool (sync lib)
# ─────────────────────────────────────────────────────────────────────────────

async def _search_ddg(query: str, max_results: int = 6) -> List[SearchResult]:
    try:
        def _run():
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        hits = await asyncio.to_thread(_run)
        return [
            {"title": r.get("title", ""), "url": r.get("href", ""),
             "snippet": r.get("body", "")[:400]}
            for r in hits if r.get("href")
        ]
    except Exception as e:
        logger.debug("[search_ddg] %s: %s", query[:60], e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Brave Search API — excellent coverage, independent index
# ─────────────────────────────────────────────────────────────────────────────

async def _search_brave(
    client: httpx.AsyncClient,
    query: str,
    max_results: int = 6,
    country: str = "us",
) -> List[SearchResult]:
    key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not key:
        return []
    try:
        params = {"q": query, "count": max_results, "search_lang": "en"}
        if country and country.lower() != "xx":
            params["country"] = country
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            params=params,
            timeout=12.0,
        )
        r.raise_for_status()
        data = r.json()
        results = []
        for item in (data.get("web", {}).get("results") or []):
            results.append({
                "title":   item.get("title", ""),
                "url":     item.get("url", ""),
                "snippet": item.get("description", "")[:400],
            })
        return results
    except Exception as e:
        logger.debug("[search_brave] %s: %s", query[:60], e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Reddit JSON API — no key needed, real buyer intent from communities
# ─────────────────────────────────────────────────────────────────────────────

async def _search_reddit(
    client: httpx.AsyncClient,
    query: str,
    subreddits: Optional[List[str]] = None,
    max_results: int = 8,
) -> List[SearchResult]:
    """
    Search Reddit without a key via the public JSON search endpoint.
    Optionally scoped to specific subreddits.
    """
    results: List[SearchResult] = []
    headers = {"User-Agent": "ZiloBusinessAgent/1.0"}

    targets = []
    if subreddits:
        for sub in subreddits[:3]:
            targets.append(f"https://www.reddit.com/r/{sub}/search.json?q={query}&restrict_sr=1&sort=new&limit={max_results}")
    else:
        targets.append(f"https://www.reddit.com/search.json?q={query}&sort=new&limit={max_results}&t=month")

    for url in targets:
        try:
            r = await client.get(url, headers=headers, timeout=10.0)
            if r.status_code != 200:
                continue
            data = r.json()
            for post in (data.get("data", {}).get("children") or []):
                p = post.get("data", {})
                post_url = p.get("url") or f"https://reddit.com{p.get('permalink','')}"
                title    = p.get("title", "")
                body     = (p.get("selftext") or "")[:300]
                if title:
                    results.append({
                        "title":   title,
                        "url":     post_url,
                        "snippet": body or title,
                    })
        except Exception as e:
            logger.debug("[search_reddit] %s: %s", url[:80], e)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Currents News API — surface grant announcements, funding news, RFPs, tenders
# ─────────────────────────────────────────────────────────────────────────────

async def _search_news(
    client: httpx.AsyncClient,
    query: str,
    max_results: int = 5,
) -> List[SearchResult]:
    key = os.environ.get("NEWS_API_KEY", "")
    if not key:
        return []
    try:
        r = await client.get(
            "https://api.currentsapi.services/v1/search",
            params={
                "keywords": query,
                "limit":    max_results,
                "language": "en",
                "apiKey":   key,
            },
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        results = []
        for art in (data.get("news") or []):
            url = art.get("url", "")
            if url:
                results.append({
                    "title":   art.get("title", ""),
                    "url":     url,
                    "snippet": (art.get("description") or "")[:400],
                })
        return results
    except Exception as e:
        logger.debug("[search_news] %s: %s", query[:60], e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# US-Specific surface: grants.gov, SAM.gov, SBA, SBIR, state portals
# ─────────────────────────────────────────────────────────────────────────────

async def _search_us_gov_grants(
    client: httpx.AsyncClient,
    query: str,
) -> List[SearchResult]:
    """Search US government grant and contract databases via DDG site: operators."""
    gov_queries = [
        f'site:grants.gov "{query}" "open"',
        f'site:sam.gov "{query}" solicitation 2025',
        f'site:sbir.gov "{query}"',
        f'site:sba.gov "{query}" grant OR loan 2025',
    ]
    results: List[SearchResult] = []
    for q in gov_queries:
        hits = await _search_ddg(q, max_results=3)
        results.extend(hits)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Smart Search Planner — LLM builds the full search plan
# ─────────────────────────────────────────────────────────────────────────────

async def build_search_plan(
    agent_goal: str,
    biz_context: str,
    country: str = "US",
    n_queries: int = 16,
) -> Dict[str, Any]:
    """
    Ask the LLM to build a full multi-dimensional search plan:
    - A list of DDG/Brave queries (diverse angles, niche sources)
    - Relevant Reddit subreddits to scan
    - News search terms for recent announcements
    - Whether to hit US gov grant portals

    Returns:
    {
      "queries": [...],
      "reddit_subreddits": [...],
      "news_terms": [...],
      "search_us_gov": bool,
      "brave_country": "us" | "gb" | "ke" | etc.
    }
    """
    import json as _json

    is_us = country in ("US", "USA", "United States")
    prompt = (
        f"You are a world-class business intelligence researcher building a search plan.\n\n"
        f"Business context: {biz_context}\n"
        f"Agent goal: {agent_goal}\n"
        f"Primary country: {country}\n\n"
        f"Create a comprehensive, multi-dimensional search plan. Return ONLY valid JSON:\n"
        f"{{\n"
        f'  "queries": ["{n_queries} diverse DDG/web queries — mix niche, site-specific, date-filtered, operator-enhanced"],\n'
        f'  "reddit_subreddits": ["5-8 most relevant subreddits where ideal customers/partners/funders are active"],\n'
        f'  "news_terms": ["3-4 news search phrases to catch recent announcements, grants, funding rounds, RFPs"],\n'
        f'  "search_us_gov": {str(is_us).lower()},\n'
        f'  "brave_country": "{("us" if is_us else country[:2].lower())}"\n'
        f"}}\n\n"
        f"For queries: go DEEP — obscure directories, state/local gov portals, industry associations, "
        f"LinkedIn Sales Navigator equivalent searches, classifieds, event sites, niche forums. "
        f"{'Include US-specific: SBA, grants.gov, state economic development offices, SBIR, angel networks by city.' if is_us else ''}\n"
        f"Return ONLY the JSON object. No markdown, no explanation."
    )

    for key_env, base_url, model in [
        ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "deepseek-chat"),
        ("OPENAI_API_KEY",   "https://api.openai.com/v1",   "gpt-4o-mini"),
    ]:
        api_key = os.environ.get(key_env, "")
        if not api_key:
            continue
        try:
            async with httpx.AsyncClient(timeout=25.0) as c:
                resp = await c.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": 1200,
                    },
                )
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"].strip()
                raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
                plan = _json.loads(raw)
                # Validate & normalise
                plan.setdefault("queries", [])
                plan.setdefault("reddit_subreddits", [])
                plan.setdefault("news_terms", [])
                plan.setdefault("search_us_gov", is_us)
                plan.setdefault("brave_country", "us" if is_us else "xx")
                return plan
        except Exception as e:
            logger.warning("[search_planner] %s failed: %s", key_env, e)
            continue

    # Fallback plan if LLM unavailable
    return {
        "queries": [f"{agent_goal} {country} 2025"],
        "reddit_subreddits": [],
        "news_terms": [],
        "search_us_gov": is_us,
        "brave_country": "us" if is_us else "xx",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Master search runner — executes the plan with full parallelism
# ─────────────────────────────────────────────────────────────────────────────

async def run_search_plan(
    plan: Dict[str, Any],
    max_total: int = 120,
) -> List[SearchResult]:
    """
    Execute a search plan in parallel across all engines.
    Returns deduplicated results up to max_total.
    """
    queries          = plan.get("queries", [])
    subreddits       = plan.get("reddit_subreddits", [])
    news_terms       = plan.get("news_terms", [])
    search_us_gov    = plan.get("search_us_gov", False)
    brave_country    = plan.get("brave_country", "us")

    all_results: List[SearchResult] = []

    async with httpx.AsyncClient(timeout=15.0) as client:

        # ── 1. DDG queries in parallel (batch of 8 at a time to avoid rate limits) ──
        for i in range(0, len(queries), 8):
            batch = queries[i:i+8]
            ddg_tasks = [_search_ddg(q, max_results=5) for q in batch]
            batched = await asyncio.gather(*ddg_tasks, return_exceptions=True)
            for res in batched:
                if isinstance(res, list):
                    all_results.extend(res)

        # ── 2. Brave Search in parallel ───────────────────────────────────────
        if os.environ.get("BRAVE_SEARCH_API_KEY"):
            brave_tasks = [
                _search_brave(client, q, max_results=5, country=brave_country)
                for q in queries[:10]
            ]
            brave_results = await asyncio.gather(*brave_tasks, return_exceptions=True)
            for res in brave_results:
                if isinstance(res, list):
                    all_results.extend(res)

        # ── 3. Reddit scan ────────────────────────────────────────────────────
        if subreddits:
            reddit_tasks = [
                _search_reddit(client, q, subreddits=subreddits, max_results=8)
                for q in queries[:4]
            ]
            reddit_results = await asyncio.gather(*reddit_tasks, return_exceptions=True)
            for res in reddit_results:
                if isinstance(res, list):
                    all_results.extend(res)

        # Also search Reddit with just subreddits + first query
        if subreddits and queries:
            reddit_sub_results = await _search_reddit(
                client, queries[0], subreddits=subreddits, max_results=10
            )
            all_results.extend(reddit_sub_results)

        # ── 4. News search ────────────────────────────────────────────────────
        if news_terms and os.environ.get("NEWS_API_KEY"):
            news_tasks = [_search_news(client, term, max_results=5) for term in news_terms]
            news_results = await asyncio.gather(*news_tasks, return_exceptions=True)
            for res in news_results:
                if isinstance(res, list):
                    all_results.extend(res)

        # ── 5. US gov grant portals ───────────────────────────────────────────
        if search_us_gov and queries:
            gov_results = await _search_us_gov_grants(client, queries[0])
            all_results.extend(gov_results)

    deduped = _dedup(all_results)
    logger.info("[search_engine] total=%d deduped=%d", len(all_results), len(deduped))
    return deduped[:max_total]


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: one-call search (plan + execute)
# ─────────────────────────────────────────────────────────────────────────────

async def smart_search(
    agent_goal: str,
    biz_context: str,
    country: str = "US",
    n_queries: int = 16,
    max_results: int = 120,
) -> List[SearchResult]:
    """
    Full pipeline: LLM builds the plan, then executes it in parallel
    across DDG + Brave + Reddit + News + (optionally) US gov portals.
    """
    plan = await build_search_plan(agent_goal, biz_context, country, n_queries)
    logger.info(
        "[smart_search] plan: %d queries, %d subreddits, %d news terms, us_gov=%s",
        len(plan["queries"]), len(plan["reddit_subreddits"]),
        len(plan["news_terms"]), plan["search_us_gov"],
    )
    return await run_search_plan(plan, max_total=max_results)
