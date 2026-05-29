"""
Business Leads — finds real businesses by keyword + location using
DataForSEO Google Maps SERP (returns name, phone, address, website, category, rating).
Email is scraped from the company website (free, no extra API key needed).
"""
import asyncio
import os
import re
import logging
from typing import Dict, Any, List, Optional

import httpx

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'[\w\.\+\-]+@[\w\-\.]+\.[a-z]{2,}', re.I)
_BAD_EMAIL = {"png", "jpg", "jpeg", "gif", "svg", "example", "sentry", "wix", "squarespace",
              "noreply", "no-reply", "donotreply", "schema.org", "@2x"}
_PHONE_RE  = re.compile(r'tel:([\+\d\s\(\)\-\.]{7,20})')

# Countries → DataForSEO location_code (most reliable, no string parsing issues)
_COUNTRY_CODES: Dict[str, int] = {
    "united states": 2840, "us": 2840, "usa": 2840, "america": 2840,
    "canada": 2124, "ca": 2124,
    "united kingdom": 2826, "uk": 2826, "gb": 2826, "england": 2826, "britain": 2826,
    "australia": 2036, "au": 2036,
    "india": 2356, "in": 2356,
    "germany": 2276, "de": 2276,
    "france": 2250, "fr": 2250,
    "south africa": 2710, "za": 2710,
    "kenya": 2404, "ke": 2404,
    "nigeria": 2566, "ng": 2566,
    "finland": 2246, "fi": 2246,
    "netherlands": 2528, "nl": 2528,
    "new zealand": 2554, "nz": 2554,
    "singapore": 2702, "sg": 2702,
    "uae": 2784, "united arab emirates": 2784,
    "dubai": 2784, "ireland": 2372, "ie": 2372,
    "brazil": 2076, "br": 2076,
    "mexico": 2484, "mx": 2484,
    "spain": 2724, "es": 2724,
    "italy": 2380, "it": 2380,
    "japan": 2392, "jp": 2392,
    "china": 2156, "cn": 2156,
    "pakistan": 2586, "pk": 2586,
    "ghana": 2288, "gh": 2288,
    "ethiopia": 2231, "et": 2231,
    "tanzania": 2834, "tz": 2834,
    "uganda": 2800, "ug": 2800,
    "rwanda": 2646, "rw": 2646,
}

# US states → canonical name (for appending ",United States")
_US_STATES: Dict[str, str] = {
    "alabama": "Alabama", "al": "Alabama",
    "alaska": "Alaska", "ak": "Alaska",
    "arizona": "Arizona", "az": "Arizona",
    "arkansas": "Arkansas", "ar": "Arkansas",
    "california": "California", "ca": "California",
    "colorado": "Colorado", "co": "Colorado",
    "connecticut": "Connecticut", "ct": "Connecticut",
    "delaware": "Delaware", "de": "Delaware",
    "florida": "Florida", "fl": "Florida",
    "georgia": "Georgia", "ga": "Georgia",
    "hawaii": "Hawaii", "hi": "Hawaii",
    "idaho": "Idaho", "id": "Idaho",
    "illinois": "Illinois", "il": "Illinois",
    "indiana": "Indiana", "in": "Indiana",
    "iowa": "Iowa", "ia": "Iowa",
    "kansas": "Kansas", "ks": "Kansas",
    "kentucky": "Kentucky", "ky": "Kentucky",
    "louisiana": "Louisiana", "la": "Louisiana",
    "maine": "Maine", "me": "Maine",
    "maryland": "Maryland", "md": "Maryland",
    "massachusetts": "Massachusetts", "ma": "Massachusetts",
    "michigan": "Michigan", "mi": "Michigan",
    "minnesota": "Minnesota", "mn": "Minnesota",
    "mississippi": "Mississippi", "ms": "Mississippi",
    "missouri": "Missouri", "mo": "Missouri",
    "montana": "Montana", "mt": "Montana",
    "nebraska": "Nebraska", "ne": "Nebraska",
    "nevada": "Nevada", "nv": "Nevada",
    "new hampshire": "New Hampshire", "nh": "New Hampshire",
    "new jersey": "New Jersey", "nj": "New Jersey",
    "new mexico": "New Mexico", "nm": "New Mexico",
    "new york": "New York", "ny": "New York",
    "north carolina": "North Carolina", "nc": "North Carolina",
    "north dakota": "North Dakota", "nd": "North Dakota",
    "ohio": "Ohio", "oh": "Ohio",
    "oklahoma": "Oklahoma", "ok": "Oklahoma",
    "oregon": "Oregon", "or": "Oregon",
    "pennsylvania": "Pennsylvania", "pa": "Pennsylvania",
    "rhode island": "Rhode Island", "ri": "Rhode Island",
    "south carolina": "South Carolina", "sc": "South Carolina",
    "south dakota": "South Dakota", "sd": "South Dakota",
    "tennessee": "Tennessee", "tn": "Tennessee",
    "texas": "Texas", "tx": "Texas",
    "utah": "Utah", "ut": "Utah",
    "vermont": "Vermont", "vt": "Vermont",
    "virginia": "Virginia", "va": "Virginia",
    "washington": "Washington", "wa": "Washington",
    "west virginia": "West Virginia", "wv": "West Virginia",
    "wisconsin": "Wisconsin", "wi": "Wisconsin",
    "wyoming": "Wyoming", "wy": "Wyoming",
    "washington dc": "Washington,District of Columbia,United States",
    "washington d.c.": "Washington,District of Columbia,United States",
    "washingtondc": "Washington,District of Columbia,United States",
    "dc": "Washington,District of Columbia,United States",
    "d.c.": "Washington,District of Columbia,United States",
    "district of columbia": "Washington,District of Columbia,United States",
}

# Canadian provinces
_CA_PROVINCES: Dict[str, str] = {
    "ontario": "Ontario", "on": "Ontario",
    "quebec": "Quebec", "qc": "Quebec",
    "british columbia": "British Columbia", "bc": "British Columbia",
    "alberta": "Alberta", "ab": "Alberta",
    "manitoba": "Manitoba", "mb": "Manitoba",
    "saskatchewan": "Saskatchewan", "sk": "Saskatchewan",
    "nova scotia": "Nova Scotia", "ns": "Nova Scotia",
    "new brunswick": "New Brunswick", "nb": "New Brunswick",
}

# Well-known cities → exact DataForSEO location_name
_CITY_MAP: Dict[str, str] = {
    # New York variants
    "new york city": "New York City,New York,United States",
    "new york":      "New York City,New York,United States",
    "newyork":       "New York City,New York,United States",
    "newyorkcity":   "New York City,New York,United States",
    "nyc":           "New York City,New York,United States",
    "ny city":       "New York City,New York,United States",
    # Los Angeles variants
    "los angeles":   "Los Angeles,California,United States",
    "losangeles":    "Los Angeles,California,United States",
    "la":            "Los Angeles,California,United States",
    # San Francisco variants
    "san francisco": "San Francisco,California,United States",
    "sanfrancisco":  "San Francisco,California,United States",
    "sf":            "San Francisco,California,United States",
    # San Diego
    "san diego":     "San Diego,California,United States",
    "sandiego":      "San Diego,California,United States",
    # San Jose
    "san jose":      "San Jose,California,United States",
    "sanjose":       "San Jose,California,United States",
    # San Antonio
    "san antonio":   "San Antonio,Texas,United States",
    "sanantonio":    "San Antonio,Texas,United States",
    # Las Vegas
    "las vegas":     "Las Vegas,Nevada,United States",
    "lasvegas":      "Las Vegas,Nevada,United States",
    "lv":            "Las Vegas,Nevada,United States",
    # Cape Town
    "cape town":     "Cape Town,Western Cape,South Africa",
    "capetown":      "Cape Town,Western Cape,South Africa",
    # Other major cities (single-word names)
    "chicago":       "Chicago,Illinois,United States",
    "houston":       "Houston,Texas,United States",
    "phoenix":       "Phoenix,Arizona,United States",
    "philadelphia":  "Philadelphia,Pennsylvania,United States",
    "philly":        "Philadelphia,Pennsylvania,United States",
    "dallas":        "Dallas,Texas,United States",
    "austin":        "Austin,Texas,United States",
    "jacksonville":  "Jacksonville,Florida,United States",
    "columbus":      "Columbus,Ohio,United States",
    "charlotte":     "Charlotte,North Carolina,United States",
    "indianapolis":  "Indianapolis,Indiana,United States",
    "indy":          "Indianapolis,Indiana,United States",
    "seattle":       "Seattle,Washington,United States",
    "denver":        "Denver,Colorado,United States",
    "boston":        "Boston,Massachusetts,United States",
    "nashville":     "Nashville,Tennessee,United States",
    "portland":      "Portland,Oregon,United States",
    "miami":         "Miami,Florida,United States",
    "atlanta":       "Atlanta,Georgia,United States",
    "minneapolis":   "Minneapolis,Minnesota,United States",
    "toronto":       "Toronto,Ontario,Canada",
    "vancouver":     "Vancouver,British Columbia,Canada",
    "montreal":      "Montreal,Quebec,Canada",
    "london":        "London,England,United Kingdom",
    "manchester":    "Manchester,England,United Kingdom",
    "birmingham":    "Birmingham,England,United Kingdom",
    "sydney":        "Sydney,New South Wales,Australia",
    "melbourne":     "Melbourne,Victoria,Australia",
    "nairobi":       "Nairobi,Nairobi County,Kenya",
    "lagos":         "Lagos,Lagos State,Nigeria",
    "accra":         "Accra,Greater Accra,Ghana",
    "johannesburg":  "Johannesburg,Gauteng,South Africa",
    "jozi":          "Johannesburg,Gauteng,South Africa",
    "joburg":        "Johannesburg,Gauteng,South Africa",
    "dubai":         "Dubai,Dubai,United Arab Emirates",
    "singapore":     "Singapore,Singapore",
    "helsinki":      "Helsinki,Uusimaa,Finland",
    "amsterdam":     "Amsterdam,North Holland,Netherlands",
    "berlin":        "Berlin,Berlin,Germany",
    "paris":         "Paris,Ile-de-France,France",
    "mumbai":        "Mumbai,Maharashtra,India",
    "bombay":        "Mumbai,Maharashtra,India",
    "delhi":         "Delhi,Delhi,India",
    "bangalore":     "Bangalore,Karnataka,India",
    "bengaluru":     "Bangalore,Karnataka,India",
}


def _normalize_location(raw: str) -> Dict:
    """
    Convert free-text location into the DataForSEO Maps payload param.
    Priority: country code → city map → US state → CA province → comma-parts → raw title.
    Falls back to no-location on failure (handled by _maps_search retry).
    """
    if not raw or not raw.strip():
        return {"location_code": 2840}   # default US

    loc = raw.strip().lower()

    # 1. Exact country match → use integer code (most reliable)
    if loc in _COUNTRY_CODES:
        return {"location_code": _COUNTRY_CODES[loc]}

    # 2. Known city shortcut (exact)
    if loc in _CITY_MAP:
        return {"location_name": _CITY_MAP[loc]}

    # 3. Squished (no-space) version of input — catches "newyork", "losangeles", etc.
    squished = loc.replace(" ", "").replace("-", "").replace("_", "")
    if squished in _CITY_MAP:
        return {"location_name": _CITY_MAP[squished]}

    # 4. US state (full name or 2-letter abbreviation)
    if loc in _US_STATES:
        canonical = _US_STATES[loc]
        if "," in canonical:
            return {"location_name": canonical}
        return {"location_name": f"{canonical},United States"}

    # 5. Canadian province
    if loc in _CA_PROVINCES:
        return {"location_name": f"{_CA_PROVINCES[loc]},Canada"}

    # 6. "City, State" or "City, Country" typed by user → title-case and pass
    parts = [p.strip().title() for p in raw.split(",") if p.strip()]
    if len(parts) >= 2:
        return {"location_name": ",".join(parts)}

    # 7. Single word/phrase — title-case and try; _maps_search retries without location on 40501
    return {"location_name": raw.strip().title()}


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — DataForSEO Maps search
# ─────────────────────────────────────────────────────────────────────────────

def _build_location_param(location: str) -> Dict:
    """Wrapper kept for backward compat — delegates to _normalize_location."""
    return _normalize_location(location)


async def _maps_search(keyword: str, location: str) -> List[Dict]:
    token = os.environ.get("DATAFORSEO_TOKEN", "").strip()
    if not token:
        logger.warning("[biz_leads] DATAFORSEO_TOKEN not set")
        return []

    loc_param = _build_location_param(location)
    depth = 100   # fetch all available — dedup handles seen leads

    task_body: Dict = {
        "keyword": keyword,
        "language_name": "English",
        "depth": depth,
        **loc_param,
    }

    async def _call(payload_body: Dict) -> Optional[Dict]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.dataforseo.com/v3/serp/google/maps/live/advanced",
                    headers={
                        "Authorization": f"Basic {token}",
                        "Content-Type": "application/json",
                    },
                    json=[payload_body],
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error("[biz_leads] DataForSEO Maps call failed: %s", e)
            return None

    data = await _call(task_body)

    # If location_name was rejected (40501), retry using US country code (Maps requires SOME location)
    if data:
        for task in data.get("tasks", []):
            if task.get("status_code") == 40501:
                sent_loc = task_body.get("location_name") or task_body.get("location_code")
                logger.warning("[biz_leads] location rejected (%r → sent %r) — retrying with US country code", location, sent_loc)
                fallback_body = {
                    "keyword": keyword,
                    "language_name": "English",
                    "depth": 100,
                    "location_code": 2840,   # United States
                }
                data = await _call(fallback_body)
                break

    if not data:
        return []

    results: List[Dict] = []
    for task in data.get("tasks", []):
        if task.get("status_code") != 20000:
            logger.warning("[biz_leads] task error %s: %s", task.get("status_code"), task.get("status_message"))
            continue
        for res in (task.get("result") or []):
            for item in (res.get("items") or []):
                if item.get("type") != "maps_search":
                    continue   # skip ads
                domain = (item.get("domain") or "").lower().strip()
                url    = item.get("url") or ""
                phone  = (item.get("phone") or "").strip()
                if not domain and not phone:
                    continue   # not useful without at least one contact signal
                results.append({
                    "name":       item.get("title", ""),
                    "phone":      phone or None,
                    "address":    item.get("address") or item.get("snippet") or None,
                    "city":       (item.get("address_info") or {}).get("city") or None,
                    "region":     (item.get("address_info") or {}).get("region") or None,
                    "country":    (item.get("address_info") or {}).get("country_code") or None,
                    "website":    url or (f"https://{domain}" if domain else None),
                    "domain":     domain or None,
                    "category":   item.get("category") or None,
                    "rating":     (item.get("rating") or {}).get("value") or None,
                    "reviews":    (item.get("rating") or {}).get("votes_count") or None,
                    "place_id":   item.get("place_id") or None,
                    "email":      None,   # filled in by scraper
                    "keyword":    keyword,
                })
    logger.info("[biz_leads] maps returned %d usable results", len(results))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Scrape website for email
# ─────────────────────────────────────────────────────────────────────────────

def _extract_email(html: str) -> Optional[str]:
    # Prefer mailto: links
    for m in re.finditer(r'mailto:([\w\.\+\-]+@[\w\-\.]+\.[a-z]{2,})', html, re.I):
        e = m.group(1).lower()
        if not any(bad in e for bad in _BAD_EMAIL):
            return e
    # Fall back to any email-like pattern
    for m in _EMAIL_RE.finditer(html):
        e = m.group(0).lower()
        if not any(bad in e for bad in _BAD_EMAIL) and len(e) < 80:
            return e
    return None


async def _scrape_email(client: httpx.AsyncClient, domain: str) -> Optional[str]:
    if not domain:
        return None
    base = f"https://{domain}"
    pages = [base, f"{base}/contact", f"{base}/contact-us", f"{base}/about"]
    for url in pages:
        try:
            r = await client.get(url, timeout=10.0, follow_redirects=True)
            if r.status_code == 200 and "text" in r.headers.get("content-type", ""):
                email = _extract_email(r.text)
                if email:
                    return email
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — AI keyword expansion
# ─────────────────────────────────────────────────────────────────────────────

_BAD_EXPANSION_WORDS = {
    "services", "service", "company", "business", "inc", "llc", "corp", "ltd",
    "co", "lp", "limited", "group", "office", "center", "centre", "shop", "store",
    "the", "and", "or", "of", "for", "in", "at", "by", "to",
}


def _is_valid_expansion(kw: str) -> bool:
    """Reject abbreviations, single letters, generic noise, and overly short terms."""
    kw = kw.strip()
    if len(kw) < 5:
        return False
    # All-caps short tokens like "DC", "USA", "LLC"
    tokens = [t for t in kw.split() if t]
    if any(len(t) <= 3 and t.isupper() for t in tokens):
        return False
    # Pure generic words
    if kw.lower() in _BAD_EXPANSION_WORDS:
        return False
    # Contains digits / punctuation noise
    if any(ch.isdigit() for ch in kw):
        return False
    return True


async def expand_keywords(keyword: str) -> List[str]:
    """
    Use AI to generate up to 8 STRICTLY same-category business search terms.
    Validates the output to reject abbreviations and generic noise.
    """
    try:
        import json
        import openai
        client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    f'Generate Google Maps search terms for finding businesses of EXACTLY the same category as: "{keyword}".\n\n'
                    "STRICT RULES:\n"
                    "- Every term MUST be a business of the same category as the original keyword.\n"
                    '- NO abbreviations or acronyms (no "DC", "LLC", "Inc", "USA", etc.).\n'
                    '- NO generic words alone ("services", "company", "business").\n'
                    "- NO single-word terms shorter than 5 letters.\n"
                    "- Each term must be 2+ words OR a complete, descriptive business category name.\n"
                    '- If the keyword is too vague (e.g. just "colleges"), give specific sub-categories ("community college", "technical college").\n\n'
                    f'GOOD example for "dental clinic": ["dentist office","orthodontist","oral surgeon","pediatric dentist","cosmetic dentist","dental implants","emergency dentist","teeth whitening clinic"]\n'
                    f'GOOD example for "colleges": ["community college","technical college","vocational school","university","junior college","business school","liberal arts college","trade school"]\n'
                    f'BAD example (NEVER do this): ["DC","school","education","academic","services"]\n\n'
                    "Return ONLY a JSON array of exactly 8 strings. No explanation, no markdown fence."
                ),
            }],
            temperature=0.2,
            max_tokens=250,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
            text = text.rstrip("`").strip()
        raw_expansions = json.loads(text)

        # Always start with the original keyword (verbatim)
        seen = {keyword.lower()}
        result = [keyword]
        for k in raw_expansions:
            k = str(k).strip()
            if not k or k.lower() in seen:
                continue
            if not _is_valid_expansion(k):
                logger.info("[biz_leads] rejected expansion %r (failed validation)", k)
                continue
            seen.add(k.lower())
            result.append(k)
            if len(result) >= 9:
                break
        logger.info("[biz_leads] expanded %r → %s", keyword, result)
        return result
    except Exception as e:
        logger.warning("[biz_leads] keyword expansion failed (%s), using original only", e)
        return [keyword]


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Multi-keyword search + deduplicate + email scrape
# ─────────────────────────────────────────────────────────────────────────────

def _score(l: Dict) -> int:
    return (
        (4 if l.get("email") else 0) +
        (3 if l.get("phone") else 0) +
        (1 if (l.get("rating") or 0) >= 4.0 else 0) +
        (1 if l.get("website") else 0)
    )


async def search_all_keywords(
    keyword: str,
    location: str = "",
    expanded_keywords: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Expand keyword with AI (or use pre-expanded list), search all variants in
    parallel on DataForSEO Maps, deduplicate, scrape top-60 emails.
    Returns all unique leads sorted by quality score.
    """
    keywords = expanded_keywords if expanded_keywords else await expand_keywords(keyword)

    logger.info("[biz_leads] searching %d keywords across %r", len(keywords), location or "US")

    # Parallel Maps searches — one per keyword
    all_results = await asyncio.gather(
        *[_maps_search(kw, location) for kw in keywords],
        return_exceptions=True,
    )

    # Merge and deduplicate by domain (or name as fallback)
    seen: set = set()
    unique: List[Dict] = []
    for result_set in all_results:
        if isinstance(result_set, Exception):
            continue
        for r in result_set:
            key = r.get("domain") or r["name"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(r)

    logger.info("[biz_leads] %d unique leads from %d keyword searches", len(unique), len(keywords))

    # Pre-sort by phone+rating to prioritise email scraping on best leads
    unique.sort(key=lambda l: (3 if l.get("phone") else 0) + (1 if (l.get("rating") or 0) >= 4 else 0), reverse=True)

    # Scrape emails for top 60 (keeps response time reasonable)
    scrape_batch = unique[:60]
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(headers=headers, timeout=12.0) as client:
        emails = await asyncio.gather(
            *[_scrape_email(client, r.get("domain")) for r in scrape_batch],
            return_exceptions=True,
        )

    for lead, email in zip(scrape_batch, emails):
        if isinstance(email, str):
            lead["email"] = email

    unique.sort(key=_score, reverse=True)
    return unique


async def search_business_leads(keyword: str, location: str = "") -> List[Dict]:
    """Public entry point — uses AI keyword expansion for broader coverage."""
    return await search_all_keywords(keyword, location=location)
