"""
LinkedIn Leads — discover LinkedIn profile URLs by title/location/company via
Tavily search, then enrich URLs with emails via the RapidAPI "LinkedIn Email
Finder" ($1 per 1000 emails).

Usage:
    from linkedin_leads import find_linkedin_urls, enrich_linkedin_urls
    urls = await find_linkedin_urls(title="marketing director", location="New York")
    results = await enrich_linkedin_urls([u["linkedin_url"] for u in urls])

Each result: {linkedin_url, email, name, status}
  status: "ok" | "no_email" | "error"
"""
import asyncio
import logging
import os
import re
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_HOST = os.environ.get("RAPIDAPI_LINKEDIN_EMAIL_HOST", "").strip()
_PATH = os.environ.get("RAPIDAPI_LINKEDIN_EMAIL_PATH", "/rapidapi/linkedin-email-finder/").strip()
_KEY  = os.environ.get("RAPIDAPI_KEY", "").strip()
_LINKEDIN_URL_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(in|pub)/[^/?#\s]+", re.I)


def _slug_to_name(url: str) -> str:
    """Extract a human-readable name from a LinkedIn URL slug."""
    m = re.search(r"/(in|pub)/([^/?#]+)", url, re.I)
    if not m:
        return ""
    slug = m.group(2)
    # Strip trailing UUIDs that LinkedIn sometimes appends (e.g. ondra-urban-12a3b4c5)
    slug = re.sub(r"-[0-9a-f]{6,}$", "", slug, flags=re.I)
    # Replace hyphens/underscores → spaces, title case
    name = slug.replace("-", " ").replace("_", " ").strip()
    return " ".join(w.capitalize() for w in name.split() if w)


def _normalize_url(raw: str) -> Optional[str]:
    """Find the first LinkedIn profile URL in the input string."""
    raw = raw.strip()
    if not raw:
        return None
    m = _LINKEDIN_URL_RE.search(raw)
    return m.group(0).rstrip("/") + "/" if m else None


async def _enrich_one(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> Dict:
    """Call the RapidAPI Email Finder for one URL, with rate limiting + retry on 429."""
    name = _slug_to_name(url)
    base = {"linkedin_url": url, "name": name, "email": None}

    if not _HOST or not _KEY:
        logger.warning("[linkedin_leads] RAPIDAPI_LINKEDIN_EMAIL_HOST or RAPIDAPI_KEY not set")
        return {**base, "status": "error", "error": "API not configured"}

    async with sem:                              # cap concurrent requests
        data = None
        for attempt in range(3):                 # up to 3 tries on 429
            try:
                resp = await client.post(
                    f"https://{_HOST}{_PATH}",
                    headers={
                        "Content-Type":    "application/json",
                        "x-rapidapi-host": _HOST,
                        "x-rapidapi-key":  _KEY,
                    },
                    json={"linkedin": url},
                    timeout=25.0,
                )
                if resp.status_code == 429:
                    wait = 2.0 * (attempt + 1)
                    logger.info("[linkedin_leads] 429 for %s — retrying in %.1fs", url, wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code != 200:
                    logger.warning("[linkedin_leads] %s → HTTP %d: %s", url, resp.status_code, resp.text[:200])
                    return {**base, "status": "error", "error": f"HTTP {resp.status_code}"}
                data = resp.json() if resp.content else {}
                break
            except Exception as e:
                logger.error("[linkedin_leads] request failed for %s: %s", url, e)
                return {**base, "status": "error", "error": str(e)}
        # Small gap after each call to be polite to the API
        await asyncio.sleep(0.3)
        if data is None:
            return {**base, "status": "error", "error": "Rate limited after retries"}

    # Extract the lead from the response. The "$1/1K emails" provider returns:
    #   [{ "✨Leads": [{ name, email, title, headline, position_history: [{company_name}] }] }]
    lead_obj: Optional[Dict] = None
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            # Try the "sparkle" key first, then any key whose name contains "leads"
            arr = first.get("✨Leads") or first.get("Leads") or first.get("leads")
            if not arr:
                for k, v in first.items():
                    if isinstance(v, list) and "lead" in k.lower():
                        arr = v
                        break
            if isinstance(arr, list) and arr:
                lead_obj = arr[0] if isinstance(arr[0], dict) else None
            elif "email" in first:    # flat-dict provider variant
                lead_obj = first
    elif isinstance(data, dict):
        # Either flat or nested under data/result/response
        if "email" in data:
            lead_obj = data
        else:
            for k in ("data", "result", "response"):
                inner = data.get(k)
                if isinstance(inner, dict) and "email" in inner:
                    lead_obj = inner
                    break
                if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                    lead_obj = inner[0]
                    break

    email = None
    if lead_obj:
        v = lead_obj.get("email") or lead_obj.get("Email") or lead_obj.get("primary_email")
        if isinstance(v, str) and "@" in v:
            email = v.strip().lower()
        # Best-quality name
        nm = lead_obj.get("name") or lead_obj.get("full_name") or lead_obj.get("fullName")
        if isinstance(nm, str) and nm.strip():
            base["name"] = nm.strip()
        # Title from this exact role
        ttl = lead_obj.get("title") or lead_obj.get("position")
        if isinstance(ttl, str) and ttl.strip():
            base["title"] = ttl.strip()
        # Company — prefer the most recent in position_history, fall back to top-level
        company = None
        hist = lead_obj.get("position_history")
        if isinstance(hist, list) and hist and isinstance(hist[0], dict):
            company = hist[0].get("company_name") or hist[0].get("company")
        if not company:
            company = lead_obj.get("company") or lead_obj.get("organization") or lead_obj.get("current_company")
        if isinstance(company, str) and company.strip():
            base["company"] = company.strip()

    if email:
        base["email"] = email
        return {**base, "status": "ok"}
    return {**base, "status": "no_email"}


async def enrich_linkedin_urls(urls: List[str]) -> List[Dict]:
    """
    Enrich a batch of LinkedIn URLs with emails in parallel.
    Skips invalid/duplicate inputs.
    """
    seen: set = set()
    valid: List[str] = []
    for raw in urls:
        u = _normalize_url(raw)
        if u and u not in seen:
            seen.add(u)
            valid.append(u)

    if not valid:
        return []

    logger.info("[linkedin_leads] enriching %d LinkedIn URLs", len(valid))

    # Cap parallel requests — the cheap RapidAPI plan rate-limits hard
    sem = asyncio.Semaphore(2)

    async with httpx.AsyncClient() as client:
        tasks = [_enrich_one(client, u, sem) for u in valid]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    out: List[Dict] = []
    for u, r in zip(valid, results):
        if isinstance(r, Exception):
            out.append({"linkedin_url": u, "name": _slug_to_name(u), "email": None, "status": "error", "error": str(r)})
        else:
            out.append(r)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Find LinkedIn URLs via Tavily / Brave search
# ─────────────────────────────────────────────────────────────────────────────

_TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "").strip()
_BRAVE_KEY  = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()


def _build_query(title: str = "", location: str = "", company: str = "", keywords: str = "") -> str:
    """Build a Google-style query that targets linkedin.com/in/ profiles."""
    parts: List[str] = ['site:linkedin.com/in/']
    if title:    parts.append(f'"{title.strip()}"')
    if company:  parts.append(f'"{company.strip()}"')
    if location: parts.append(f'"{location.strip()}"')
    if keywords: parts.append(keywords.strip())
    return " ".join(parts)


def _extract_profile_from_result(url: str, title: str = "", snippet: str = "") -> Optional[Dict]:
    """Pull a clean LinkedIn profile URL + best-guess name out of a search result."""
    u = _normalize_url(url)
    if not u:
        return None
    name = _slug_to_name(u)
    # Search result titles often look like "Jane Doe - Marketing Director at Acme | LinkedIn"
    headline = ""
    if title:
        clean = re.sub(r"\s*[\|\-–—]\s*LinkedIn.*$", "", title, flags=re.I).strip()
        parts = re.split(r"\s+[-–]\s+", clean, maxsplit=1)
        if len(parts) == 2 and parts[0].strip():
            name = parts[0].strip()
            headline = parts[1].strip()
        else:
            # No separator — title may BE the headline
            headline = clean
    return {"linkedin_url": u, "name": name, "headline": headline, "snippet": snippet}


async def _search_tavily(query: str, limit: int) -> List[Dict]:
    """Hit Tavily's search API restricted to linkedin.com/in/. Uses deep search for more coverage."""
    if not _TAVILY_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:   # deep search is slower
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key":        _TAVILY_KEY,
                    "query":          query,
                    "search_depth":   "advanced",   # 2x coverage vs basic
                    "include_domains": ["linkedin.com"],
                    "max_results":    min(limit, 30),
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error("[linkedin_leads] Tavily search failed: %s", e)
        return []

    results: List[Dict] = []
    for r in (data.get("results") or []):
        url = r.get("url", "")
        if "/in/" not in url:
            continue   # skip company pages
        item = _extract_profile_from_result(url, r.get("title", ""), r.get("content", ""))
        if item:
            results.append(item)
    return results


async def _search_brave(query: str, limit: int) -> List[Dict]:
    """Fallback: Brave Search API."""
    if not _BRAVE_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": _BRAVE_KEY, "Accept": "application/json"},
                params={"q": query, "count": min(limit, 20)},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error("[linkedin_leads] Brave search failed: %s", e)
        return []

    results: List[Dict] = []
    for r in (data.get("web", {}).get("results") or []):
        url = r.get("url", "")
        if "/in/" not in url:
            continue
        item = _extract_profile_from_result(url, r.get("title", ""), r.get("description", ""))
        if item:
            results.append(item)
    return results


async def expand_job_titles(title: str) -> List[str]:
    """Use AI to generate up to 6 closely related job titles for broader coverage."""
    title = (title or "").strip()
    if not title:
        return []
    try:
        import json
        import openai
        client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    f'Generate 6 closely related JOB TITLES for LinkedIn searches related to: "{title}".\n\n'
                    "STRICT RULES:\n"
                    "- Each must be a real job title at the SAME seniority and function as the original.\n"
                    "- Include common synonyms and adjacent roles (e.g. for \"marketing director\" → "
                    '"VP of Marketing", "Head of Marketing", "Marketing Manager", "CMO", "Marketing Lead").\n'
                    "- NO generic words alone (no \"manager\" or \"director\" by itself).\n"
                    "- Each title must be 2+ words OR a known C-level acronym (CMO, CTO, CFO, CEO, COO).\n\n"
                    "Return ONLY a JSON array of 6 strings. No explanation, no markdown fence."
                ),
            }],
            temperature=0.3,
            max_tokens=200,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:]).rstrip("`").strip()
        arr = json.loads(text)
        seen = {title.lower()}
        result = [title]
        for t in arr:
            t = str(t).strip()
            if t and t.lower() not in seen and len(t) >= 3:
                seen.add(t.lower())
                result.append(t)
            if len(result) >= 7:
                break
        logger.info("[linkedin_leads] expanded title %r → %s", title, result)
        return result
    except Exception as e:
        logger.warning("[linkedin_leads] title expansion failed: %s", e)
        return [title]


async def find_linkedin_urls(
    title: str = "",
    location: str = "",
    company: str = "",
    keywords: str = "",
    limit: int = 20,
    expand_title: bool = True,
) -> Dict:
    """
    Search the web for LinkedIn profile URLs matching the given criteria.
    When a title is provided and expand_title=True, AI expands it into related
    titles and runs all searches in parallel for broader coverage.
    Returns: {profiles: [...], expanded_titles: [...]}.
    """
    # Build the list of titles to search
    titles: List[str] = []
    if title and expand_title:
        titles = await expand_job_titles(title)
    elif title:
        titles = [title]
    else:
        titles = [""]   # no title — just one search with location/company/keywords

    # Build queries
    queries = [
        _build_query(title=t, location=location, company=company, keywords=keywords)
        for t in titles
    ]
    queries = [q for q in queries if q != "site:linkedin.com/in/"]   # drop empty
    if not queries:
        return {"profiles": [], "expanded_titles": titles}

    logger.info("[linkedin_leads] running %d parallel searches", len(queries))

    # Run all searches in parallel (Tavily for each), then Brave as fallback for any empty
    per_query_limit = max(8, limit // max(1, len(queries)))
    tavily_tasks = [_search_tavily(q, per_query_limit) for q in queries]
    tavily_results = await asyncio.gather(*tavily_tasks, return_exceptions=True)

    all_results: List[Dict] = []
    for q, res in zip(queries, tavily_results):
        if isinstance(res, Exception):
            continue
        if not res:
            # Fall back to Brave for this query
            brave = await _search_brave(q, per_query_limit)
            all_results.extend(brave)
        else:
            all_results.extend(res)

    # Deduplicate by URL
    seen: set = set()
    unique: List[Dict] = []
    for r in all_results:
        if r["linkedin_url"] in seen:
            continue
        seen.add(r["linkedin_url"])
        unique.append(r)

    logger.info("[linkedin_leads] found %d unique LinkedIn URLs across %d queries", len(unique), len(queries))
    return {"profiles": unique[:limit], "expanded_titles": titles}
