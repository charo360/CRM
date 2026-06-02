"""
Funding Finder — user-driven funding opportunity discovery.

Takes sector + location + funding types from the user, runs a smart
multi-engine web search via search_engine.smart_search, AI-scores the
results, and returns the top N as opportunity dicts.

Unlike the legacy _run_funding_hunter (which uses a fixed query and is
Africa-biased), this is fully driven by what the user typed.
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_AMOUNT_NEAR_RE = re.compile(
    r"(?:up to |award(?:s)? of |grants? of |funding of |maximum of |worth |valued at )?"
    r"(?:USD?|EUR|GBP|\$|€|£)\s?[\d,]+(?:\.\d+)?\s?(?:K|k|M|m|million|billion|thousand)?",
)

# Funding type → query expansion fragment
_FUNDING_TYPE_TERMS = {
    "grant":         "grants",
    "vc":            "venture capital firms VCs investors",
    "accelerator":   "accelerator program incubator",
    "angel":         "angel investors",
    "government":    "government programs public funding",
    "crowdfunding":  "crowdfunding equity crowdfunding platforms",
    "loan":          "business loans financing",
}

# Stage → query expansion fragment
_STAGE_TERMS = {
    "pre_seed":   "pre-seed",
    "seed":       "seed stage",
    "series_a":   "series A",
    "series_b":   "series B series C growth stage",
    "established": "established business mature company",
}


def _build_query(
    sector: str = "",
    location: str = "",
    funding_types: Optional[List[str]] = None,
    stage: str = "",
    keywords: str = "",
) -> str:
    parts: List[str] = []
    type_terms = " or ".join(
        _FUNDING_TYPE_TERMS[t] for t in (funding_types or []) if t in _FUNDING_TYPE_TERMS
    ) or "funding opportunities grants accelerators VCs"
    parts.append(f"Find {type_terms}")
    if stage and stage in _STAGE_TERMS:
        parts.append(f"for {_STAGE_TERMS[stage]}")
    if sector:
        parts.append(f"{sector} business")
    if location:
        parts.append(f"in {location}")
    if keywords:
        parts.append(keywords)
    return " ".join(parts)


async def find_funding(
    sector: str = "",
    location: str = "",
    funding_types: Optional[List[str]] = None,
    stage: str = "",
    keywords: str = "",
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """
    Discover funding opportunities matching the user's criteria.

    Returns a list of dicts with: title, url, snippet, score, source.
    The caller decides whether to persist them.
    """
    query = _build_query(
        sector=sector, location=location,
        funding_types=funding_types, stage=stage, keywords=keywords,
    )
    biz_context = f"A {sector or 'business'} {('in ' + location) if location else ''} looking for funding."

    logger.info("[funding_finder] searching: %s", query)

    try:
        from search_engine import smart_search
        raw_results = await smart_search(
            agent_goal=query,
            biz_context=biz_context,
            country=location or "US",
            n_queries=12,
            max_results=80,
        )
    except Exception as e:
        logger.error("[funding_finder] smart_search failed: %s", e)
        return []

    if not raw_results:
        return []

    # AI score for relevance
    try:
        from action_mode_routes import _ai_score_results   # reuse the existing scorer
        scored = await _ai_score_results(
            raw_results,
            context=biz_context,
            agent_goal=f"Find real, actionable funding for: {query}",
        )
    except Exception as e:
        logger.warning("[funding_finder] AI scoring failed (%s), returning unscored", e)
        scored = [
            {**(r if isinstance(r, dict) else r.__dict__), "score": 5}
            for r in raw_results
        ]

    # Normalise + dedupe by URL
    seen_urls: set = set()
    out: List[Dict[str, Any]] = []
    for r in scored:
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        if not url or not title or url in seen_urls:
            continue
        seen_urls.add(url)
        out.append({
            "title":   title,
            "url":     url,
            "snippet": (r.get("snippet") or r.get("description") or "")[:500],
            "score":   float(r.get("score") or 5),
            "source":  r.get("source") or r.get("engine") or "web",
        })
        if len(out) >= limit:
            break

    # Enrich each with status + deadline + amount (best-effort, batched AI call)
    out = await _enrich_funding_metadata(out)

    logger.info("[funding_finder] returning %d opportunities", len(out))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Deadline + status extraction
# ─────────────────────────────────────────────────────────────────────────────

_DATE_PATTERNS = [
    # ISO: 2026-04-30
    (re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b"), "iso"),
    # "April 30, 2026" / "Apr 30 2026"
    (re.compile(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b",
        re.I,
    ), "monthname"),
    # "30 April 2026"
    (re.compile(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(20\d{2})\b",
        re.I,
    ), "daymonth"),
]
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_ROLLING_RE = re.compile(r"\b(rolling basis|always open|year[\s-]?round|no deadline|ongoing)\b", re.I)
_CLOSED_RE  = re.compile(r"\b(closed|deadline (passed|over)|application(s)? closed|no longer accepting)\b", re.I)


def _extract_deadline_regex(text: str) -> Optional[str]:
    """Return ISO date string for the LATEST date found in text, or None."""
    if not text:
        return None
    candidates: List[date] = []
    for pattern, kind in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                if kind == "iso":
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                elif kind == "monthname":
                    mo = _MONTH_MAP.get(m.group(1).lower()[:3])
                    d, y = int(m.group(2)), int(m.group(3))
                else:  # daymonth
                    d = int(m.group(1))
                    mo = _MONTH_MAP.get(m.group(2).lower()[:3])
                    y = int(m.group(3))
                if mo and 1 <= mo <= 12 and 1 <= d <= 31 and 2024 <= y <= 2099:
                    candidates.append(date(y, mo, d))
            except (ValueError, AttributeError):
                continue
    if not candidates:
        return None
    # Pick the future-most date (deadlines are usually future)
    today = date.today()
    future = [c for c in candidates if c >= today]
    chosen = max(future) if future else max(candidates)
    return chosen.isoformat()


def _regex_status(text: str, deadline_iso: Optional[str]) -> str:
    if not text:
        return "unknown"
    if _ROLLING_RE.search(text):
        return "rolling"
    if _CLOSED_RE.search(text):
        return "closed"
    if deadline_iso:
        try:
            d = date.fromisoformat(deadline_iso)
            return "open" if d >= date.today() else "closed"
        except ValueError:
            pass
    return "unknown"


async def _enrich_funding_metadata(opps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add `status` ("open"|"closed"|"rolling"|"unknown"), `deadline` (ISO or null),
    and `amount` (text or null) to each opportunity. Tries AI first; falls back to regex.
    """
    if not opps:
        return opps

    # First: cheap regex pass — gives us a baseline even if AI fails
    for o in opps:
        combined = f"{o.get('title','')} {o.get('snippet','')}"
        deadline = _extract_deadline_regex(combined)
        o["deadline"] = deadline
        o["status"]   = _regex_status(combined, deadline)
        o["amount"]   = None

    # Then: AI pass for the same batch (overrides regex when AI is confident)
    api_key = (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return opps

    today = date.today().isoformat()
    items_txt = "\n".join(
        f"{i+1}. TITLE: {o.get('title','')}\n   SNIPPET: {o.get('snippet','')[:300]}"
        for i, o in enumerate(opps)
    )
    prompt = (
        f"Today is {today}. For each funding opportunity below, extract:\n"
        '- "status": "open" | "closed" | "rolling" | "unknown"\n'
        '- "deadline": ISO date "YYYY-MM-DD" or null\n'
        '- "amount": funding amount as text (e.g. "$50K-$500K", "€2M", "up to $100k") or null\n\n'
        "Rules:\n"
        '- "rolling" = applications accepted any time (no fixed deadline)\n'
        '- "open" = clear future deadline OR worded as currently accepting\n'
        '- "closed" = deadline passed OR explicitly closed\n'
        '- "unknown" = no signal either way\n'
        "- Pick the LATEST/RELEVANT deadline if multiple dates appear.\n"
        "- Be conservative — only fill amount if a specific figure is stated.\n\n"
        f"Opportunities:\n{items_txt}\n\n"
        'Return ONLY a JSON array: [{"idx":1,"status":"open","deadline":"2026-04-30","amount":"$50K-$500K"},...]\n'
        "No markdown, no explanation."
    )

    base_url, model = (
        ("https://api.deepseek.com/v1", "deepseek-chat")
        if os.environ.get("DEEPSEEK_API_KEY") else
        ("https://api.openai.com/v1", "gpt-4o-mini")
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1500,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            start, end = raw.find("["), raw.rfind("]")
            if start == -1 or end == -1:
                return opps
            extracted = json.loads(raw[start:end+1])
    except Exception as e:
        logger.warning("[funding_finder] metadata enrichment AI call failed: %s", e)
        return opps

    valid_status = {"open", "closed", "rolling", "unknown"}
    for item in extracted:
        try:
            idx = int(item.get("idx", 0)) - 1
            if not (0 <= idx < len(opps)):
                continue
            st = str(item.get("status", "")).lower().strip()
            if st in valid_status:
                opps[idx]["status"] = st
            dl = item.get("deadline")
            if isinstance(dl, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", dl):
                opps[idx]["deadline"] = dl
            amt = item.get("amount")
            if isinstance(amt, str) and amt.strip():
                opps[idx]["amount"] = amt.strip()[:60]
        except (ValueError, TypeError):
            continue

    # For any opportunity that's "open" but still missing a deadline, fetch the
    # actual page and scan the full text for a date. Capped concurrency to be
    # polite and avoid blowing up response time.
    needs_fetch = [
        (i, o) for i, o in enumerate(opps)
        if o.get("status") == "open" and not o.get("deadline") and o.get("url")
    ]
    if needs_fetch:
        logger.info("[funding_finder] fetching pages for %d open opps with missing deadlines", len(needs_fetch))
        await _backfill_from_pages(opps, needs_fetch)

    return opps


async def _backfill_from_pages(opps: List[Dict[str, Any]], targets: List[tuple]) -> None:
    """Fetch each URL once, scan extracted text for a deadline / amount. Updates `opps` in place."""
    sem = asyncio.Semaphore(4)   # cap parallel fetches
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ZiloBot/1.0; +https://zilo.pro/bot)",
        "Accept": "text/html,application/xhtml+xml",
    }

    async def _fetch(idx: int, url: str) -> None:
        async with sem:
            try:
                async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as client:
                    resp = await client.get(url)
                if resp.status_code != 200 or "text" not in resp.headers.get("content-type", ""):
                    return
                # Strip HTML to plain text, collapse whitespace
                text = _HTML_TAG_RE.sub(" ", resp.text)
                text = _WHITESPACE_RE.sub(" ", text)[:50_000]   # cap so we don't burn memory

                if not opps[idx].get("deadline"):
                    dl = _extract_deadline_regex(text)
                    if dl:
                        opps[idx]["deadline"] = dl
                        # Recompute status if the new date is in the past
                        try:
                            opps[idx]["status"] = "open" if date.fromisoformat(dl) >= date.today() else "closed"
                        except ValueError:
                            pass

                if not opps[idx].get("amount"):
                    m = _AMOUNT_NEAR_RE.search(text)
                    if m:
                        amt = _WHITESPACE_RE.sub(" ", m.group(0)).strip()
                        if 3 < len(amt) < 60:
                            opps[idx]["amount"] = amt
            except Exception as e:
                logger.debug("[funding_finder] page fetch failed for %s: %s", url, e)

    await asyncio.gather(*[_fetch(i, o["url"]) for i, o in targets])
