"""
Shopify store lead enrichment.

Discovery:
  1. DataForSEO Technologies API — searches their index of Shopify stores by
     niche keyword. Returns the most stores and is already in the .env.
  2. Tavily / Brave web-search fallback — finds myshopify.com URLs via web search.

Enrichment (per domain, all free / no extra keys):
  1. Shopify public API  (/products.json, /collections.json)
     → product count, price range, top products, categories, vendors
  2. Homepage scrape
     → store name, description, email, phone, social links
  3. RapidAPI store/info (optional, rate-limited to 1 req/s on BASIC plan)
     → additional contact details if available
"""
import asyncio
import os
import re
import httpx
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_MYSHOPIFY_RE = re.compile(r'([a-z0-9][a-z0-9\-]{1,60}\.myshopify\.com)', re.I)
_EMAIL_RE     = re.compile(r'[\w\.\+\-]+@[\w\-\.]+\.[a-z]{2,}', re.I)
_PHONE_RE     = re.compile(r'tel:([\+\d\s\(\)\-\.]{7,20})')
_SOC = {
    "facebook":  re.compile(r'https?://(?:www\.)?facebook\.com/(?!sharer|share|dialog|photo|groups/feed)[a-zA-Z0-9_./-]{2,}', re.I),
    "instagram": re.compile(r'https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_.]{2,}', re.I),
    "tiktok":    re.compile(r'https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9_.]{2,}', re.I),
    "twitter":   re.compile(r'https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9_]{2,}', re.I),
    "youtube":   re.compile(r'https?://(?:www\.)?youtube\.com/(?:c/|channel/|@)[a-zA-Z0-9_\-]{2,}', re.I),
    "pinterest": re.compile(r'https?://(?:www\.)?pinterest\.com/[a-zA-Z0-9_/]{2,}', re.I),
}
_BAD_EMAIL_PARTS = {"png", "jpg", "jpeg", "gif", "svg", "schema", "example", "@sentry", "wix", "squarespace"}


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Store discovery
# ─────────────────────────────────────────────────────────────────────────────

async def _find_via_dataforseo(niche: str, country: str, limit: int) -> List[str]:
    """
    DataForSEO Technologies API — the most reliable way to find Shopify stores
    by niche. Their index is refreshed monthly and covers millions of sites.
    """
    token = os.environ.get("DATAFORSEO_TOKEN", "").strip()
    if not token:
        return []

    payload: List[Dict] = [{
        "technology_type": "cms",
        "technology_name": "Shopify",
        "keywords": [niche],
        "limit": min(limit * 2, 100),   # fetch extra, we'll deduplicate
    }]
    if country:
        payload[0]["country_iso_code"] = country[:2].upper()

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://api.dataforseo.com/v3/technologies/domains_by_technology",
                headers={
                    "Authorization": f"Basic {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            domains: List[str] = []
            for task in data.get("tasks", []):
                for result in (task.get("result") or []):
                    for item in (result.get("items") or []):
                        d = item.get("domain", "").lower().strip()
                        if d and "myshopify.com" in d:
                            domains.append(d)
                        elif d:
                            # Custom domain — keep as-is, we'll still scrape
                            domains.append(d)
            logger.info("[shopify_leads] dataforseo returned %d domains", len(domains))
            return domains[:limit]
    except Exception as e:
        logger.warning("[shopify_leads] dataforseo failed: %s", e)
        return []


async def _find_via_web_search(niche: str, country: str, limit: int) -> List[str]:
    """Fallback: Tavily/Brave search for myshopify.com URLs."""
    loc = f" {country}" if country else ""
    queries = [
        f'site:myshopify.com "{niche}"',
        f'"{niche}" myshopify.com shop contact email{loc}',
        f'inurl:myshopify.com {niche} store{loc}',
        f'"{niche}" online store myshopify{loc}',
    ]
    raw_results: List[Dict] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        tavily_key = os.environ.get("TAVILY_API_KEY", "")
        if tavily_key:
            tasks = [
                client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": tavily_key, "query": q, "max_results": 8, "search_depth": "basic"},
                    timeout=15.0,
                )
                for q in queries
            ]
            for resp in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(resp, Exception): continue
                try:
                    resp.raise_for_status()
                    raw_results.extend(resp.json().get("results", []))
                except Exception:
                    pass

        if not raw_results:
            brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
            if brave_key:
                for q in queries[:2]:
                    try:
                        r = await client.get(
                            "https://api.search.brave.com/res/v1/web/search",
                            params={"q": q, "count": 10},
                            headers={"Accept": "application/json", "X-Subscription-Token": brave_key},
                            timeout=12.0,
                        )
                        r.raise_for_status()
                        for item in r.json().get("web", {}).get("results", []):
                            raw_results.append({"url": item.get("url",""), "title": item.get("title","")})
                    except Exception:
                        pass

    seen: set = set()
    domains: List[str] = []
    for r in raw_results:
        for text in (r.get("url",""), r.get("title",""), r.get("content",""), r.get("snippet","")):
            for m in _MYSHOPIFY_RE.findall(text):
                d = m.lower()
                if d not in seen:
                    seen.add(d)
                    domains.append(d)

    logger.info("[shopify_leads] web-search returned %d domains", len(domains))
    return domains[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Rich per-store enrichment (Shopify public API + scraping)
# ─────────────────────────────────────────────────────────────────────────────

async def _enrich_from_shopify_public(client: httpx.AsyncClient, domain: str) -> Dict[str, Any]:
    """
    Free enrichment using Shopify's own public endpoints.
    No API key required — any Shopify store exposes these.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ZiloBot/1.0)"}
    result: Dict[str, Any] = {
        "domain": domain,
        "name": None,
        "email": None,
        "phone": None,
        "description": None,
        "facebook": None, "instagram": None, "tiktok": None,
        "twitter": None, "youtube": None, "pinterest": None,
        "product_count": 0,
        "price_min": None,
        "price_max": None,
        "avg_price": None,
        "categories": [],
        "top_products": [],
        "vendors": [],
        "tags_sample": [],
        "has_free_shipping": False,
        "currency": None,
        "platform": "Shopify",
        "source": "shopify_public",
    }

    base = f"https://{domain}"

    # ── 1. Products API ────────────────────────────────────────────────────────
    try:
        r = await client.get(f"{base}/products.json?limit=250", headers=headers, timeout=12.0)
        if r.status_code == 200:
            products = r.json().get("products", [])
            result["product_count"] = len(products)

            prices = []
            for p in products:
                for v in p.get("variants", []):
                    try:
                        prices.append(float(v["price"]))
                    except (KeyError, ValueError):
                        pass

            if prices:
                result["price_min"] = round(min(prices), 2)
                result["price_max"] = round(max(prices), 2)
                result["avg_price"] = round(sum(prices) / len(prices), 2)

            categories = list(dict.fromkeys(
                p["product_type"] for p in products if p.get("product_type")
            ))
            result["categories"] = categories[:6]

            vendors = list(dict.fromkeys(
                p["vendor"] for p in products if p.get("vendor")
            ))
            result["vendors"] = vendors[:5]

            # Top 5 products by variant count (more variants = more popular)
            sorted_prods = sorted(products, key=lambda p: len(p.get("variants", [])), reverse=True)
            result["top_products"] = [
                {
                    "title": p["title"],
                    "price": p["variants"][0]["price"] if p.get("variants") else None,
                    "type": p.get("product_type"),
                }
                for p in sorted_prods[:5]
            ]

            # Sample tags
            all_tags: List[str] = []
            for p in products:
                all_tags.extend(p.get("tags", "").split(",") if isinstance(p.get("tags"), str) else [])
            tag_freq: Dict[str, int] = {}
            for t in all_tags:
                t = t.strip()
                if t: tag_freq[t] = tag_freq.get(t, 0) + 1
            result["tags_sample"] = [t for t, _ in sorted(tag_freq.items(), key=lambda x: -x[1])[:8]]

    except Exception as e:
        logger.debug("[shopify_enrich] products.json failed %s: %s", domain, e)

    # ── 2. Homepage scrape ─────────────────────────────────────────────────────
    try:
        r = await client.get(base, headers=headers, timeout=12.0)
        if r.status_code == 200:
            html = r.text

            # Store name
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if m:
                raw = re.sub(r"<[^>]+>", "", m.group(1))
                result["name"] = raw.split("|")[0].split("–")[0].split("-")[0].strip()[:80]

            # Description (meta)
            m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{10,300})["\']', html, re.I)
            if m:
                result["description"] = m.group(1).strip()

            # Social links
            for net, pat in _SOC.items():
                m = pat.search(html)
                if m:
                    result[net] = m.group(0).rstrip("/")

            # Email
            for em in _EMAIL_RE.findall(html):
                if not any(bad in em.lower() for bad in _BAD_EMAIL_PARTS):
                    result["email"] = em
                    break

            # Phone (tel: links)
            m = _PHONE_RE.search(html)
            if m:
                result["phone"] = m.group(1).strip()

            # Currency hint (JSON-LD or meta)
            m = re.search(r'"priceCurrency"\s*:\s*"([A-Z]{3})"', html)
            if m:
                result["currency"] = m.group(1)

    except Exception as e:
        logger.debug("[shopify_enrich] homepage failed %s: %s", domain, e)

    # ── 3. Contact page ────────────────────────────────────────────────────────
    if not result["email"]:
        try:
            r = await client.get(f"{base}/pages/contact", headers=headers, timeout=8.0)
            if r.status_code == 200:
                for em in _EMAIL_RE.findall(r.text):
                    if not any(bad in em.lower() for bad in _BAD_EMAIL_PARTS):
                        result["email"] = em
                        break
                if not result["phone"]:
                    m = _PHONE_RE.search(r.text)
                    if m:
                        result["phone"] = m.group(1).strip()
        except Exception:
            pass

    return result


async def _enrich_rapidapi(domain: str) -> Dict[str, Any]:
    """Optional RapidAPI enrichment — use only if RAPIDAPI_KEY is set."""
    key  = os.environ.get("RAPIDAPI_KEY", "").strip()
    host = os.environ.get("RAPIDAPI_SHOPIFY_HOST", "shopify-stores-info.p.rapidapi.com").strip()
    if not key:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://{host}/store/info",
                headers={"x-rapidapi-key": key, "x-rapidapi-host": host},
                params={"url": f"https://{domain}"},
            )
            if resp.status_code == 200:
                di = resp.json().get("domain_info") or {}
                out: Dict[str, Any] = {}
                emails = di.get("emails") or []
                if emails: out["email"] = emails[0]
                phones = di.get("phoneNumbers") or []
                if phones: out["phone"] = phones[0]
                if di.get("site_name"): out["name"] = di["site_name"]
                for s in (di.get("socialMedia") or []):
                    net = s.get("social","").lower()
                    url = s.get("url")
                    for k in ("facebook","instagram","tiktok","twitter","youtube","pinterest"):
                        if k in net and url:
                            out[k] = url
                return out
    except Exception as e:
        logger.debug("[shopify_rapidapi] %s: %s", domain, e)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

async def search_shopify_leads(
    niche: str,
    country: str = "",
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Find Shopify store owners as B2B leads with rich data.

    Discovery: DataForSEO Technologies API → web search fallback
    Enrichment: Shopify public API (products, homepage, contact page) +
                optional RapidAPI for additional contact fields
    """
    # ── Discovery ──────────────────────────────────────────────────────────────
    domains = await _find_via_dataforseo(niche, country, limit)
    if not domains:
        logger.info("[shopify_leads] dataforseo empty, falling back to web search")
        domains = await _find_via_web_search(niche, country, limit)

    if not domains:
        return []

    logger.info("[shopify_leads] enriching %d stores for niche=%s", len(domains), niche)

    # ── Enrich in parallel (public Shopify API, no rate limit) ────────────────
    use_rapidapi = bool(os.environ.get("RAPIDAPI_KEY", "").strip())
    rapidapi_calls = 0
    MAX_RAPIDAPI = 8  # stay well under the BASIC plan limit

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10),
    ) as client:
        tasks = [_enrich_from_shopify_public(client, d) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched: List[Dict[str, Any]] = []
    for domain, res in zip(domains, results):
        if isinstance(res, Exception):
            res = {
                "domain": domain, "name": None, "email": None, "phone": None,
                "platform": "Shopify", "source": "error",
            }

        # Optional: top up missing contact info from RapidAPI
        if use_rapidapi and rapidapi_calls < MAX_RAPIDAPI and not (res.get("email") or res.get("phone")):
            await asyncio.sleep(1.2)
            extra = await _enrich_rapidapi(domain)
            rapidapi_calls += 1
            for k, v in extra.items():
                if v and not res.get(k):
                    res[k] = v

        res["niche"] = niche
        enriched.append(res)

    # Sort: most data first
    def _score(lead: Dict) -> int:
        return (
            bool(lead.get("email")) * 4 +
            bool(lead.get("phone")) * 3 +
            bool(lead.get("product_count")) * 2 +
            bool(lead.get("instagram") or lead.get("facebook")) * 1
        )

    enriched.sort(key=_score, reverse=True)
    return enriched


# ─────────────────────────────────────────────────────────────────────────────
# Single-store enrichment (used by /enrich-shopify endpoint)
# ─────────────────────────────────────────────────────────────────────────────

async def get_shopify_store_info(domain: str) -> Dict[str, Any]:
    """
    Full enrichment for a single known store domain.
    Uses Shopify public API first, RapidAPI as supplement.
    """
    domain = domain.replace("https://","").replace("http://","").split("/")[0].strip()

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        result = await _enrich_from_shopify_public(client, domain)

    if os.environ.get("RAPIDAPI_KEY"):
        extra = await _enrich_rapidapi(domain)
        for k, v in extra.items():
            if v and not result.get(k):
                result[k] = v

    return result


async def enrich_shopify_directly(domain: str) -> Dict[str, Any]:
    """Legacy alias — kept for backwards compatibility."""
    return await get_shopify_store_info(domain)
