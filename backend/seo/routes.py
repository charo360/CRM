"""SEO + Auto-Blogging module — site audit, keyword research, AI blog writer, auto-publish."""
from __future__ import annotations
import logging, uuid, re, httpx
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


def _tid(user): return user.get("business_id", user["_id"])


def _seo_business_context(user: dict) -> Dict[str, str]:
    """Merge Settings + Business Knowledge into defaults for SEO flows."""
    bk = user.get("business_knowledge") or {}
    settings = user.get("settings") or {}
    business_type = (
        str(bk.get("business_type") or "").strip()
        or str(settings.get("business_type") or "").strip()
        or str(user.get("business_type") or "").strip()
        or "general"
    )
    loc_parts: List[str] = []
    bl = str(bk.get("business_location") or "").strip()
    if bl:
        loc_parts.append(bl)
    country = str(settings.get("country") or "").strip()
    if country:
        loc_parts.append(country)
    location = ", ".join(loc_parts)
    language = str(settings.get("primary_language") or "English").strip() or "English"
    business_name = str(user.get("business_name") or "").strip()
    desc = str(bk.get("business_description") or "").strip()
    products = str(bk.get("products_services") or "").strip()
    snippet_parts: List[str] = []
    if desc:
        snippet_parts.append(desc[:900])
    if products:
        snippet_parts.append(products[:900])
    context_snippet = "\n\n".join(snippet_parts)
    website_url = str(bk.get("website_url") or "").strip()
    return {
        "business_type": business_type,
        "location": location,
        "language": language,
        "business_name": business_name,
        "context_snippet": context_snippet,
        "website_url": website_url,
    }


def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at", "published_at", "scheduled_at"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"): doc[f] = v.isoformat()
    return doc

# ── Pydantic models ──────────────────────────────────────────────────────────

class AuditRequest(BaseModel):
    url: str

class ScrapeWebsiteRequest(BaseModel):
    url: str

class KeywordRequest(BaseModel):
    """Empty strings fall back to the signed-in user's business profile / settings."""
    business_type: str = ""
    location: str = ""
    language: str = ""


def _merge_seo_keyword_payload(payload: KeywordRequest, user: dict) -> tuple[str, str, str, str]:
    ctx = _seo_business_context(user)
    bt = payload.business_type.strip() or ctx["business_type"]
    loc = payload.location.strip() or ctx["location"]
    lang = payload.language.strip() or ctx["language"]
    snippet = ctx["context_snippet"]
    return bt, loc, lang, snippet


def _keyword_research_seed(business_type: str, business_name: str, snippet: str) -> str:
    bn = (business_name or "").strip()
    if len(bn) >= 2:
        return bn[:100]
    bt_clean = (business_type or "").strip().replace("-", " ")
    generic = {"general", "retail", "business", "service", "services"}
    if bt_clean and bt_clean.lower() not in generic:
        return bt_clean[:100]
    if snippet:
        frag = snippet.replace("\n", " ").strip()[:100]
        if len(frag) >= 8:
            return frag
    return bt_clean[:100] if bt_clean else "small business"


class SaveKeywordsRequest(BaseModel):
    keywords: List[dict]
    month: str = ""          # e.g. "2025-05"  — defaults to current month
    business_type: str = ""
    location: str = ""


class CalendarDraftRequest(BaseModel):
    """Bulk-generate blog drafts for a list of calendar items."""
    items: List[dict]   # each: {title, keywords, topic, week, day}
    tone: str = "professional"
    length: str = "medium"


class PublishCredentials(BaseModel):
    platform: str          # wordpress | shopify
    wp_url: str = ""
    wp_username: str = ""
    wp_password: str = ""
    shopify_domain: str = ""
    shopify_token: str = ""


class BlogGenerateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    topic: str
    keywords: List[str] = []
    tone: str = "professional"       # professional | casual | friendly
    length: str = "medium"           # short(400w) | medium(800w) | long(1500w)
    language: str = "English"
    business_name: str = ""
    include_faq: bool = True
    model_pref: str = "standard"

class BlogPost(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str
    content: str
    meta_title: str = ""
    meta_description: str = ""
    image_url: Optional[str] = None
    keywords: List[str] = []
    tags: List[str] = []
    status: str = "draft"            # draft | scheduled | published
    scheduled_at: Optional[str] = None
    platform: str = "internal"       # internal | wordpress | shopify

class BlogPostUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: Optional[str] = None
    content: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    image_url: Optional[str] = None
    keywords: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    scheduled_at: Optional[str] = None
    platform: Optional[str] = None

class PublishRequest(BaseModel):
    post_id: str
    platform: str   # wordpress | shopify
    wp_url: Optional[str] = None
    wp_username: Optional[str] = None
    wp_password: Optional[str] = None
    shopify_domain: Optional[str] = None
    shopify_token: Optional[str] = None

# ── AI helpers ───────────────────────────────────────────────────────────────

async def _call_ai(prompt: str, model_pref: str = "standard", max_tokens: int = 2000) -> str:
    """Route to available AI provider."""
    import os, httpx
    # Try OpenAI first
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=openai_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"[seo] OpenAI failed: {e}")

    # Fallback to Claude
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if claude_key:
        try:
            async with httpx.AsyncClient(timeout=60) as hc:
                resp = await hc.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": claude_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
                )
                data = resp.json()
                return data["content"][0]["text"]
        except Exception as e:
            logger.warning(f"[seo] Claude failed: {e}")

    raise HTTPException(500, "No AI provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.")


async def _audit_url(url: str) -> dict:
    """Fetch a URL and run comprehensive SEO checks including technical SEO."""
    from html.parser import HTMLParser
    import json

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = ""
            self.meta: Dict[str, str] = {}
            self.h1s: List[str] = []
            self.h2s: List[str] = []
            self.images_missing_alt: int = 0
            self.total_images: int = 0
            self.structured_data: List[dict] = []
            self._in_title = False
            self._word_count = 0
            self._in_script = False
            self._script_content = ""

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "title": self._in_title = True
            if tag == "meta":
                name = a.get("name", "").lower()
                prop = a.get("property", "").lower()
                content = a.get("content", "")
                if name in ("description", "keywords", "robots"): self.meta[name] = content
                if prop.startswith("og:"): self.meta[prop] = content
            if tag in ("h1",): self.h1s.append("")
            if tag in ("h2",): self.h2s.append("")
            if tag == "img":
                self.total_images += 1
                if not a.get("alt"): self.images_missing_alt += 1
            if tag == "script":
                self._in_script = True
                if a.get("type") == "application/ld+json":
                    self._script_content = ""

        def handle_endtag(self, tag):
            if tag == "title": self._in_title = False
            if tag == "script" and self._in_script:
                self._in_script = False
                if self._script_content.strip():
                    try:
                        data = json.loads(self._script_content)
                        self.structured_data.append(data)
                    except:
                        pass
                self._script_content = ""

        def handle_data(self, data):
            if self._in_title: self.title += data
            if self._in_script: self._script_content += data
            if self.h1s and data.strip(): self.h1s[-1] += data
            if self.h2s and data.strip(): self.h2s[-1] += data

    try:
        headers = {"User-Agent": "ZiloSEOBot/1.0"}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as hc:
            resp = await hc.get(url, headers=headers)
        html = resp.text
        word_count = len(re.sub(r"<[^>]+>", " ", html).split())
        response_headers = dict(resp.headers)
    except Exception as e:
        raise HTTPException(400, f"Could not fetch URL: {e}")

    parser = _Parser()
    parser.feed(html)

    issues = []
    score = 100

    # Basic on-page checks
    title = parser.title.strip()
    if not title:
        issues.append({"type": "critical", "field": "title", "message": "Missing page title tag"})
        score -= 20
    elif len(title) < 30:
        issues.append({"type": "warning", "field": "title", "message": f"Title too short ({len(title)} chars). Aim for 50–60."})
        score -= 5
    elif len(title) > 65:
        issues.append({"type": "warning", "field": "title", "message": f"Title too long ({len(title)} chars). Keep under 65."})
        score -= 5

    desc = parser.meta.get("description", "")
    if not desc:
        issues.append({"type": "critical", "field": "meta_description", "message": "Missing meta description"})
        score -= 15
    elif len(desc) < 80:
        issues.append({"type": "warning", "field": "meta_description", "message": f"Meta description short ({len(desc)} chars). Aim for 140–160."})
        score -= 5
    elif len(desc) > 165:
        issues.append({"type": "warning", "field": "meta_description", "message": f"Meta description too long ({len(desc)} chars). Keep under 160."})
        score -= 5

    if not parser.h1s:
        issues.append({"type": "critical", "field": "h1", "message": "No H1 heading found"})
        score -= 15
    elif len(parser.h1s) > 1:
        issues.append({"type": "warning", "field": "h1", "message": f"Multiple H1 tags ({len(parser.h1s)}). Use only one."})
        score -= 5

    if parser.images_missing_alt > 0:
        issues.append({"type": "warning", "field": "images", "message": f"{parser.images_missing_alt} of {parser.total_images} images missing alt text"})
        score -= min(10, parser.images_missing_alt * 2)

    if not parser.meta.get("og:title"):
        issues.append({"type": "info", "field": "og_tags", "message": "Missing Open Graph tags (og:title, og:description, og:image)"})
        score -= 5

    if word_count < 300:
        issues.append({"type": "warning", "field": "content", "message": f"Low word count ({word_count} words). Aim for 500+ for better ranking."})
        score -= 10

    # Technical SEO checks
    # Robots.txt check
    try:
        robots_url = f"{url.rstrip('/')}/robots.txt"
        robots_resp = await httpx.AsyncClient(timeout=10).get(robots_url, headers=headers)
        if robots_resp.status_code == 200:
            robots_content = robots_resp.text
            if "User-agent: *" in robots_content and "Disallow:" in robots_content:
                # Has some blocking rules - this is generally good
                pass
            else:
                issues.append({"type": "info", "field": "robots_txt", "message": "Robots.txt exists but may not be properly configured"})
        else:
            issues.append({"type": "warning", "field": "robots_txt", "message": "Missing robots.txt file"})
            score -= 5
    except:
        issues.append({"type": "warning", "field": "robots_txt", "message": "Could not check robots.txt"})
        score -= 5

    # Sitemap check
    try:
        sitemap_urls = [
            f"{url.rstrip('/')}/sitemap.xml",
            f"{url.rstrip('/')}/sitemap_index.xml"
        ]
        sitemap_found = False
        for sitemap_url in sitemap_urls:
            try:
                sitemap_resp = await httpx.AsyncClient(timeout=10).get(sitemap_url, headers=headers)
                if sitemap_resp.status_code == 200:
                    sitemap_found = True
                    break
            except:
                continue
        if not sitemap_found:
            issues.append({"type": "warning", "field": "sitemap", "message": "Missing XML sitemap"})
            score -= 10
    except:
        issues.append({"type": "warning", "field": "sitemap", "message": "Could not check sitemap"})
        score -= 10

    # Structured data check
    if not parser.structured_data:
        issues.append({"type": "info", "field": "structured_data", "message": "No structured data (Schema.org) found"})
        score -= 5
    else:
        # Check for common schema types
        schema_types = []
        for data in parser.structured_data:
            if "@type" in data:
                schema_types.append(data["@type"])
            elif "type" in data:
                schema_types.append(data["type"])
        if schema_types:
            issues.append({"type": "info", "field": "structured_data", "message": f"Found structured data types: {', '.join(schema_types)}"})

    # Security headers check
    security_headers = {
        "strict-transport-security": "Missing HSTS header",
        "x-content-type-options": "Missing X-Content-Type-Options header",
        "x-frame-options": "Missing X-Frame-Options header",
        "content-security-policy": "Missing Content Security Policy"
    }
    security_score_deducted = 0
    for header, message in security_headers.items():
        if header not in [h.lower() for h in response_headers.keys()]:
            issues.append({"type": "warning", "field": "security_headers", "message": message})
            security_score_deducted += 2
    if security_score_deducted > 0:
        score -= min(10, security_score_deducted)

    # HTTPS check
    if not url.startswith("https://"):
        issues.append({"type": "critical", "field": "https", "message": "Website not using HTTPS"})
        score -= 20

    score = max(0, score)

    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

    return {
        "url": url,
        "score": score,
        "grade": grade,
        "title": title,
        "meta_description": desc,
        "h1_count": len(parser.h1s),
        "h2_count": len(parser.h2s),
        "word_count": word_count,
        "total_images": parser.total_images,
        "images_missing_alt": parser.images_missing_alt,
        "structured_data_count": len(parser.structured_data),
        "issues": issues,
        "og_tags": {k: v for k, v in parser.meta.items() if k.startswith("og:")},
        "technical_checks": {
            "robots_txt": "present" if any("robots" in issue["field"] and "missing" not in issue["message"].lower() for issue in issues) else "missing",
            "sitemap": "present" if any("sitemap" in issue["field"] and "missing" not in issue["message"].lower() for issue in issues) else "missing",
            "https": url.startswith("https://"),
            "security_headers_score": max(0, 10 - security_score_deducted // 2)
        }
    }


# ── Router factory ────────────────────────────────────────────────────────────

def make_seo_router(db, user_dep):
    router = APIRouter(prefix="/seo", tags=["seo"])

    async def _record_event(event_type: str, payload: dict, user=user_dep):
        """Record an analytics event to `seo_analytics` collection for the current user."""
        try:
            tid = _tid(user)
            doc = {
                "_id": str(uuid.uuid4()),
                "user_id": tid,
                "type": event_type,
                "payload": payload,
                "created_at": datetime.utcnow(),
            }
            await db.seo_analytics.insert_one(doc)
        except Exception:
            logger.exception("Failed to record SEO analytics event")

    @router.get("/context")
    async def get_seo_business_context_endpoint(user=user_dep):
        """Merge Settings + Business Knowledge for keyword/blog/calendar defaults."""
        from . import dataforseo as dfs
        base = _seo_business_context(user)
        return {**base, "live_keyword_data": dfs.dfs_enabled()}

    # ── Scrape website to auto-fill business info ────────────────────────────

    @router.post("/scrape-website")
    async def scrape_website(payload: ScrapeWebsiteRequest, user=user_dep):
        """Scrape a website and use LLM to write rich, full business profile content for all Settings fields."""
        import html as _html
        from html.parser import HTMLParser
        from urllib.parse import urljoin, urlparse

        url = payload.url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        # ── Deep HTML extractor ──────────────────────────────────────────────
        class _DeepParser(HTMLParser):
            SKIP_TAGS = {"script", "style", "noscript", "head", "svg", "iframe", "form", "button", "input"}

            def __init__(self):
                super().__init__()
                self.title = ""; self.meta_desc = ""; self.og_name = ""; self.og_desc = ""
                self.phone = ""; self.email = ""
                self.chunks: list[str] = []          # all meaningful text blocks
                self.links: list[str] = []           # href values for sub-page discovery
                self._skip_depth = 0
                self._in_title = False
                self._current_tag = ""
                self._buf = ""

            def _flush(self):
                t = self._buf.strip()
                if t and len(t) > 8:
                    self.chunks.append(t)
                self._buf = ""

            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if tag in self.SKIP_TAGS:
                    self._skip_depth += 1
                    return
                if tag == "title":
                    self._in_title = True; self._buf = ""
                if tag == "meta":
                    n = a.get("name", "").lower(); prop = a.get("property", "").lower(); c = a.get("content", "")
                    if n == "description": self.meta_desc = c
                    if prop == "og:site_name": self.og_name = c
                    if prop == "og:description": self.og_desc = c
                if tag == "a":
                    href = a.get("href", "")
                    if href and not href.startswith("#") and not href.startswith("javascript"):
                        self.links.append(href)
                if tag in ("h1", "h2", "h3", "h4", "p", "li", "td", "th", "span", "div", "article", "section"):
                    self._flush()
                self._current_tag = tag

            def handle_endtag(self, tag):
                if tag in self.SKIP_TAGS:
                    self._skip_depth = max(0, self._skip_depth - 1)
                    return
                if tag == "title" and self._in_title:
                    self.title = self._buf.strip(); self._in_title = False; self._buf = ""
                if tag in ("h1", "h2", "h3", "h4", "p", "li", "td", "th", "article", "section"):
                    self._flush()

            def handle_data(self, data):
                if self._skip_depth > 0: return
                if self._in_title:
                    self._buf += data
                else:
                    cleaned = " ".join(data.split())
                    if cleaned:
                        self._buf += " " + cleaned

            def get_text(self, max_chars: int = 6000) -> str:
                seen: set[str] = set()
                out: list[str] = []
                total = 0
                for c in self.chunks:
                    norm = " ".join(c.split())
                    if norm in seen or len(norm) < 10:
                        continue
                    seen.add(norm)
                    out.append(norm)
                    total += len(norm)
                    if total >= max_chars:
                        break
                return "\n".join(out)

        async def _fetch_page(client: httpx.AsyncClient, page_url: str) -> str:
            try:
                r = await client.get(page_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0)
                if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                    return r.text
            except Exception:
                pass
            return ""

        # ── Fetch homepage + up to 3 sub-pages ──────────────────────────────
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                home_html = await _fetch_page(client, url)
                if not home_html:
                    raise HTTPException(status_code=400, detail="Could not fetch website — check the URL.")

                home_parser = _DeepParser()
                home_parser.feed(home_html)

                # Discover relevant sub-pages from internal links
                base = urlparse(url)
                PRIORITY_SLUGS = ["about", "services", "menu", "products", "contact",
                                  "our-story", "what-we-do", "pricing", "who-we-are"]
                candidate_pages: list[str] = []
                seen_urls: set[str] = {url}
                for href in home_parser.links:
                    if href.startswith("//"):
                        href = base.scheme + ":" + href
                    elif href.startswith("/"):
                        href = f"{base.scheme}://{base.netloc}{href}"
                    elif not href.startswith("http"):
                        href = urljoin(url, href)
                    parsed = urlparse(href)
                    if parsed.netloc != base.netloc:
                        continue
                    slug = parsed.path.strip("/").lower()
                    if any(p in slug for p in PRIORITY_SLUGS) and href not in seen_urls:
                        candidate_pages.append(href)
                        seen_urls.add(href)
                    if len(candidate_pages) >= 6:
                        break

                # Fetch up to 3 sub-pages concurrently
                import asyncio
                sub_htmls = await asyncio.gather(*[_fetch_page(client, u) for u in candidate_pages[:3]])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not fetch website: {e}")

        # ── Parse & merge all page text ──────────────────────────────────────
        try:
            all_text_parts: list[str] = []
            main_text = home_parser.get_text(4000)
            if main_text:
                all_text_parts.append(f"=== Homepage ===\n{main_text}")

            for i, (sub_url, sub_html) in enumerate(zip(candidate_pages[:3], sub_htmls)):
                if not sub_html:
                    continue
                sp = _DeepParser()
                sp.feed(sub_html)
                sub_text = sp.get_text(2000)
                if sub_text:
                    slug = urlparse(sub_url).path.strip("/") or "page"
                    all_text_parts.append(f"=== {slug} ===\n{sub_text}")

            combined_text = "\n\n".join(all_text_parts)[:9000]
            og_name = _html.unescape(home_parser.og_name)
            meta_desc = _html.unescape(home_parser.meta_desc or home_parser.og_desc)
            site_title = _html.unescape(home_parser.title)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse website: {e}")

        # ── LLM: write rich, full content for every field ────────────────────
        prompt = f"""You are an expert business profile writer. You have been given the full text content scraped from a business website across multiple pages. Your job is to write a complete, rich, professional business profile by reading everything and synthesising the best possible content.

WEBSITE CONTENT (from homepage + sub-pages):
{combined_text}

---

Write a complete business profile. For each field, write PROPER, FULL content — not just a quote from the site, but a well-crafted, informative text. Use everything you read to make each field as useful as possible.

Return ONLY a valid JSON object with these fields:

{{
  "business_name": "The exact business name",

  "business_description": "Write 2-4 full, engaging sentences describing what this business is, what they do, who they serve, and what makes them unique. This is shown to the AI assistant so be descriptive and accurate.",

  "products_services": "Write a detailed list of all products and services offered. Group them if needed. Mention key offerings, specialties, and anything the business is known for. Aim for 3-8 items/lines.",

  "business_location": "Full address or area. Include city, neighbourhood, and country if available.",

  "business_hours": "All operating hours in a clear readable format. E.g. Mon-Fri 9am-6pm, Sat 10am-4pm, Closed Sunday.",

  "pricing_info": "Any pricing details, ranges, package info, or value statements. Write '' if truly not mentioned anywhere.",

  "business_type": "Exactly one of: retail, restaurant, salon, spa, services, repair, cleaning, fitness, events, healthcare, rental, hotel, support, creator, wholesale, bakery, grocery, general",

  "faqs": "Write 3-5 realistic FAQ entries in Q&A format based on what the business offers. Format as: Q: ...\\nA: ...\\n\\nQ: ...\\nA: ...",

  "special_offers": "Any promotions, loyalty programmes, discounts, or special deals mentioned. Write '' if none found.",

  "delivery_info": "Any delivery, shipping, collection, or fulfilment information. Write '' if not applicable."
}}

Rules:
- Always write something meaningful for business_description, products_services, and faqs — use context clues if explicit info is sparse.
- Do NOT copy-paste raw HTML or navigation text.
- Do NOT leave business_description or products_services blank.
- Return ONLY the JSON object with no extra text or markdown fences."""

        import json
        raw = await _call_ai(prompt, max_tokens=2000)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
        # Sometimes LLMs wrap in extra braces — find first valid JSON object
        try:
            data = json.loads(raw)
        except Exception:
            # Try to extract JSON substring
            m = re.search(r"\{[\s\S]+\}", raw)
            if m:
                try:
                    data = json.loads(m.group())
                except Exception:
                    data = {}
            else:
                data = {}

        # Fallbacks
        if og_name and not data.get("business_name"):
            data["business_name"] = og_name
        if not data.get("business_description") and meta_desc:
            data["business_description"] = meta_desc
        if not data.get("business_description") and site_title:
            data["business_description"] = site_title

        return {"url": url, "extracted": data, "pages_scraped": 1 + len([h for h in sub_htmls if h])}

    # ── Site Audit ──────────────────────────────────────────────────────────

    @router.post("/audit")
    async def run_audit(payload: AuditRequest, user=user_dep):
        url = payload.url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        result = await _audit_url(url)

        # Persist audit result
        tid = _tid(user)
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "created_at": datetime.utcnow(),
            **result,
        }
        await db.seo_audits.insert_one(doc)
        return _ser(doc)

    @router.get("/audits")
    async def list_audits(user=user_dep):
        tid = _tid(user)
        docs = await db.seo_audits.find({"user_id": tid}).sort("created_at", -1).limit(50).to_list(50)
        return [_ser(d) for d in docs]

    # ── AI-powered audit fix suggestions ───────────────────────────────────

    @router.post("/audit/ai-fix")
    async def ai_fix_suggestions(payload: AuditRequest, user=user_dep):
        url = payload.url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        audit = await _audit_url(url)
        if not audit["issues"]:
            return {"suggestions": [], "message": "No major issues found! Your page looks good."}

        issues_text = "\n".join(f"- [{i['type'].upper()}] {i['field']}: {i['message']}" for i in audit["issues"])
        prompt = f"""You are an SEO expert. A website page at {url} has these SEO issues:

{issues_text}

Page title: "{audit['title']}"
Meta description: "{audit['meta_description']}"

For each issue, provide a specific, actionable fix. If the title or meta description is missing/bad, write a better version.
Return a JSON array like:
[
  {{"field": "title", "issue": "...", "fix": "...", "example": "..."}}
]
Only return the JSON array, no other text."""

        raw = await _call_ai(prompt, max_tokens=1500)
        try:
            import json
            raw = raw.strip()
            if raw.startswith("```"): raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
            suggestions = json.loads(raw)
        except Exception:
            suggestions = [{"field": "general", "issue": "Multiple issues found", "fix": raw, "example": ""}]

        return {"url": url, "score": audit["score"], "grade": audit["grade"], "suggestions": suggestions}

    # ── Keyword Research ────────────────────────────────────────────────────

    @router.post("/keywords")
    async def generate_keywords(payload: KeywordRequest, user=user_dep):
        import json as _json
        from . import dataforseo as dfs

        bt, loc, lang, snippet = _merge_seo_keyword_payload(payload, user)
        ctx = _seo_business_context(user)
        tid = _tid(user)
        keywords: List[Any] = []
        keyword_source = "ai"
        website_content = ""

        # ── Load all previously saved keywords so we never repeat them ──────
        already_saved: set[str] = set()
        try:
            all_saved_docs = await db.seo_saved_keywords.find({"user_id": tid}).to_list(100)
            for doc in all_saved_docs:
                for k in (doc.get("keywords") or []):
                    phrase = (k.get("keyword") if isinstance(k, dict) else str(k) or "").lower().strip()
                    if phrase:
                        already_saved.add(phrase)
            logger.info("[seo] Excluding %d already-saved keyword phrases for user %s", len(already_saved), tid)
        except Exception as e:
            logger.warning("[seo] Could not load saved keywords for dedup: %s", e)

        # ── Load published / draft blog post keywords to mark status ────────
        published_kws: set[str] = set()
        draft_kws: set[str] = set()
        try:
            posts = await db.seo_blog_posts.find(
                {"user_id": tid}, {"keywords": 1, "status": 1}
            ).to_list(200)
            for p in posts:
                for kw in (p.get("keywords") or []):
                    kw_low = (kw or "").lower().strip()
                    if p.get("status") == "published":
                        published_kws.add(kw_low)
                    else:
                        draft_kws.add(kw_low)
        except Exception as e:
            logger.warning("[seo] Could not load blog post keywords: %s", e)

        # ── Optional: scrape website for extra context ───────────────────────
        if ctx.get("website_url"):
            try:
                import html as _html
                from html.parser import HTMLParser
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(ctx["website_url"], headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code == 200:
                        class _KwParser(HTMLParser):
                            def __init__(self):
                                super().__init__()
                                self.title=""; self.meta_desc=""; self.headings=[]; self.paragraphs=[]
                                self._in_title=False; self._in_h=False; self._in_p=False; self._buf=""
                            def handle_starttag(self, tag, attrs):
                                a=dict(attrs)
                                if tag=="title": self._in_title=True; self._buf=""
                                elif tag in ("h1","h2","h3") and len(self.headings)<10: self._in_h=True; self._buf=""
                                elif tag=="p" and len(self.paragraphs)<5: self._in_p=True; self._buf=""
                                elif tag=="meta" and a.get("name","").lower()=="description": self.meta_desc=a.get("content","")
                            def handle_endtag(self, tag):
                                if tag=="title" and self._in_title: self.title=self._buf.strip(); self._in_title=False
                                elif tag in ("h1","h2","h3") and self._in_h: self.headings.append(self._buf.strip()); self._in_h=False
                                elif tag=="p" and self._in_p: self.paragraphs.append(self._buf.strip()); self._in_p=False
                            def handle_data(self, data):
                                if self._in_title or self._in_h or self._in_p: self._buf+=data
                        kp = _KwParser(); kp.feed(resp.text)
                        parts = []
                        if kp.title: parts.append(f"Title: {_html.unescape(kp.title)}")
                        if kp.meta_desc: parts.append(f"Description: {_html.unescape(kp.meta_desc)}")
                        if kp.headings: parts.append("Headings: " + " | ".join([_html.unescape(h) for h in kp.headings]))
                        if kp.paragraphs: parts.append(" ".join([_html.unescape(p) for p in kp.paragraphs]))
                        website_content = "\n".join(parts)[:2000]
            except Exception as e:
                logger.warning("[seo] Failed to scrape website %s: %s", ctx.get("website_url"), e)

        # ── DataForSEO: multi-seed diverse long-tail fetch ───────────────────
        if dfs.dfs_enabled():
            try:
                settings = user.get("settings") or {}
                lc = dfs.resolve_location_code(
                    str(settings.get("country") or ""),
                    str(settings.get("country_code") or user.get("country_code") or ""),
                )
                dlang = dfs.language_code_from_settings(lang)
                seed = _keyword_research_seed(bt, ctx["business_name"], snippet)
                keywords = await dfs.fetch_diverse_keywords(
                    seed,
                    location=loc,
                    location_code=lc,
                    language_code=dlang,
                    limit=30,
                    exclude_phrases=already_saved,
                )
                if keywords:
                    keyword_source = "dataforseo"
            except Exception as e:
                logger.warning("[seo] DataForSEO keyword ideas skipped: %s", e)

        # ── AI fallback: request fresh long-tail keywords, exclude known ones ─
        if not keywords:
            location_str = f" in {loc}" if loc else ""
            city = loc.split(",")[0].strip() if loc else ""

            exclude_block = ""
            if already_saved:
                sample = sorted(already_saved)[:40]
                exclude_block = f"\n\nDO NOT include any of these already-researched keywords:\n" + "\n".join(f"- {k}" for k in sample)

            extra = ""
            if website_content:
                extra = f"\n\nWebsite content (extract keywords from what's actually on their site):\n{website_content}"
            elif snippet:
                extra = f"\n\nBusiness context:\n{snippet[:1200]}"

            prompt = f"""You are an expert SEO keyword strategist. Generate 25 FRESH, UNTAPPED keyword ideas for a {bt} business{location_str}.
{extra}{exclude_block}

Apply ALL of these keyword strategies — return a mix of each type:

1. LONG-TAIL (3-5 words, specific): e.g. "affordable wedding photographer {city}", "best {bt} for beginners"
2. QUESTION-BASED: e.g. "how to choose a {bt}", "what is the best {bt} in {city}", "why use a {bt}"
3. LOCAL/GEO: e.g. "{bt} {city}", "near me {bt}", "{bt} delivery {city}"
4. BUYER-INTENT: e.g. "hire {bt}", "book {bt} online", "{bt} price {city}", "cheap {bt} {city}"
5. COMPARISON: e.g. "best {bt} vs DIY", "{bt} options {city}", "top {bt} services"
6. INFORMATIONAL: e.g. "tips for {bt}", "{bt} guide", "how {bt} works"

Return a JSON array of 25 keywords. Each:
{{
  "keyword": "exact phrase (3-6 words preferred)",
  "intent": "informational|transactional|local|navigational",
  "difficulty": "low|medium|high",
  "priority": 1-5,
  "content_idea": "specific blog post title idea for this keyword",
  "strategy_type": "long-tail|question|local|buyer-intent|comparison|informational"
}}

Rules:
- Every keyword must be different from the excluded list above
- Prefer 3-5 word phrases over single words (long-tail = less competition, easier to rank)
- Use {loc} and {city} naturally in local keywords
- Priority 4-5 = high traffic + low competition (best targets)
- Language: {lang}

Only return the JSON array."""

            raw = await _call_ai(prompt, max_tokens=2500)
            try:
                raw = raw.strip()
                if raw.startswith("```"): raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
                keywords = _json.loads(raw)
            except Exception:
                keywords = []

        # ── Tag each keyword with tracking status ────────────────────────────
        for kw in keywords:
            phrase = (kw.get("keyword") or "").lower().strip()
            if phrase in published_kws:
                kw["status"] = "published"
            elif phrase in draft_kws:
                kw["status"] = "draft"
            else:
                kw["status"] = "new"

        return {
            "keywords": keywords,
            "business_type": bt,
            "location": loc,
            "keyword_source": keyword_source,
            "website_url": ctx.get("website_url", ""),
            "excluded_count": len(already_saved),
        }

    # ── Blog Post Generation ────────────────────────────────────────────────

    @router.post("/blog/generate")
    async def generate_blog_post(payload: BlogGenerateRequest, user=user_dep):
        ctx = _seo_business_context(user)
        biz_name = payload.business_name.strip() or ctx["business_name"]
        lang = payload.language.strip() or ctx["language"]
        snippet = ctx["context_snippet"]

        word_targets = {"short": "400-500", "medium": "800-1000", "long": "1400-1600"}
        word_target = word_targets.get(payload.length, "800-1000")
        keywords_str = ", ".join(payload.keywords) if payload.keywords else payload.topic
        business_str = f" for {biz_name}" if biz_name else ""

        context_block = ""
        if snippet:
            context_block = f"""

Business context (stay accurate to what they offer):
{snippet[:1400]}
"""

        faq_instruction = """
After the main content, add a FAQ section with 3-5 relevant questions and answers (good for AI search and Google featured snippets).""" if payload.include_faq else ""

        prompt = f"""You are an expert writer and journalist — not an AI assistant. You write the way experienced columnists do: specific, opinionated, grounded in real detail.

ASSIGNMENT:
Business: {biz_name or "a local business"}
Topic: {payload.topic}
Keywords: {keywords_str}
Tone: {payload.tone} | Language: {lang} | Length: {word_target} words
{context_block}

━━━ STEP 1 — CHOOSE YOUR OPENING (do this before writing anything else) ━━━

Pick ONE of these six opening types. Each one works. Do NOT pick the same type twice across different articles.

A) SCENE — drop the reader into a moment they recognise:
   "You've just received three quotes for [service]. All different prices. No explanation why."
   "The last customer who walked into [type of shop] thought they knew exactly what they wanted. They didn't."

B) COUNTER-INTUITIVE FACT — say something true that surprises:
   "Most businesses in [location] spend twice what they need to on [topic] — and the expensive option isn't even better."
   "The advice everyone gives about [topic] is wrong for 80% of situations."

C) DIRECT QUESTION — start a conversation:
   "How do you know if you're getting a fair price for [service]?"
   "When was the last time [topic] actually worked the way it was supposed to?"

D) CONFESSION OR OBSERVATION — from your own experience:
   "I've worked with dozens of [industry] businesses in [location]. The ones that struggle share one thing in common."
   "After seeing this mistake made over and over, I had to write about it."

E) SPECIFIC NUMBER — a stat or figure that makes a point:
   "Three out of five [location] businesses get this wrong in the first year."
   "In [location], the average person spends [X] more than necessary on [topic] — not because they have to."

F) BOLD STATEMENT — take a clear position:
   "[Common belief about topic] is outdated advice. Here's what actually works."
   "Stop [common but wrong approach]. It's costing you more than you think."

━━━ STEP 2 — HEADLINE ━━━
Write an H1 that matches your opening type. It must earn the click.
GOOD: "Why Your [Topic] Is Costing You More Than It Should in [Location]"
GOOD: "5 Mistakes [Location] Businesses Make With [Topic] (And How to Fix Them)"
BAD: "A Guide to [Topic]", "Understanding [Topic]", "Everything About [Topic]"

━━━ STEP 3 — WRITE THE ARTICLE ━━━
- Your chosen opening IS the first paragraph. Start there, not with background context.
- Write like you're talking to one specific person, not addressing a crowd.
- Short sentences. Mix them with longer ones. Never three long sentences in a row.
- Use contractions naturally: don't, it's, you'll, we've, I've.
- Specific beats vague every time: "costs around Ksh 15,000 in Nairobi" beats "can be expensive".
- Name actual places, typical prices, real situations your reader would recognise.
- Each H2 section answers a question the reader is actually thinking.
- Conclusion: tell them one specific thing to do next — not "contact us for more info".
{(' - FAQ: 3-5 questions a real person would actually search for, with direct useful answers.' if payload.include_faq else '')}

AUTOMATIC FAIL — if your article contains any of these, rewrite before submitting:
✗ "In today's [adjective] world..."
✗ "In this article, we will..."
✗ "Are you looking for..."
✗ "[Topic] is an important/essential/crucial aspect of..."
✗ "In conclusion..." / "To summarize..." / "As we've seen..."
✗ Any of: dive into, delve into, game-changer, leverage, seamlessly, unlock, revolutionize, transformative, cutting-edge, harness the power, it goes without saying, look no further

After the article write:
META_TITLE: [50-60 chars — reads like a headline, not a label]
META_DESC: [140-160 chars — one specific benefit + location]
TAGS: [5 tags]

Now write the article — starting directly with your chosen opening line:"""

        raw = await _call_ai(prompt, max_tokens=3000)

        # Extract meta fields from the end of the response
        meta_title = ""
        meta_desc = ""
        tags: List[str] = []

        meta_title_match = re.search(r"META_TITLE:\s*(.+)", raw)
        meta_desc_match = re.search(r"META_DESC:\s*(.+)", raw)
        tags_match = re.search(r"TAGS:\s*(.+)", raw)

        if meta_title_match: meta_title = meta_title_match.group(1).strip()
        if meta_desc_match: meta_desc = meta_desc_match.group(1).strip()
        if tags_match: tags = [t.strip() for t in tags_match.group(1).split(",")]

        # Clean meta lines from content
        content = re.sub(r"\n(META_TITLE|META_DESC|TAGS):[^\n]+", "", raw).strip()

        # Extract title from first H1
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else payload.topic

        return {
            "title": title,
            "content": content,
            "meta_title": meta_title or title[:60],
            "meta_description": meta_desc,
            "tags": tags,
            "word_count": len(content.split()),
            "topic": payload.topic,
            "keywords": payload.keywords,
        }

    # ── Blog Post CRUD ──────────────────────────────────────────────────────

    @router.get("/blog/posts")
    async def list_posts(user=user_dep):
        tid = _tid(user)
        docs = await db.seo_blog_posts.find({"user_id": tid}).sort("created_at", -1).limit(100).to_list(100)
        return [_ser(d) for d in docs]

    @router.post("/blog/posts")
    async def create_post(payload: BlogPost, user=user_dep):
        tid = _tid(user)
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            **payload.model_dump(),
        }
        await db.seo_blog_posts.insert_one(doc)
        # Analytics: record post creation
        await _record_event("post_created", {"post_id": doc["_id"], "title": doc.get("title"), "status": doc.get("status")}, user)
        return _ser(doc)

    @router.get("/blog/posts/{post_id}")
    async def get_post(post_id: str, user=user_dep):
        tid = _tid(user)
        doc = await db.seo_blog_posts.find_one({"_id": post_id, "user_id": tid})
        if not doc: raise HTTPException(404, "Post not found")
        return _ser(doc)

    @router.patch("/blog/posts/{post_id}")
    async def update_post(post_id: str, payload: BlogPostUpdate, user=user_dep):
        tid = _tid(user)
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for f, v in payload.model_dump(exclude_none=True).items():
            upd[f] = v
        result = await db.seo_blog_posts.update_one({"_id": post_id, "user_id": tid}, {"$set": upd})
        if result.matched_count == 0: raise HTTPException(404, "Post not found")
        doc = await db.seo_blog_posts.find_one({"_id": post_id})
        # Analytics: record post update (include changed fields)
        await _record_event("post_updated", {"post_id": post_id, "updated_fields": list(payload.model_dump(exclude_none=True).keys())}, user)
        return _ser(doc)

    @router.delete("/blog/posts/{post_id}")
    async def delete_post(post_id: str, user=user_dep):
        tid = _tid(user)
        result = await db.seo_blog_posts.delete_one({"_id": post_id, "user_id": tid})
        if result.deleted_count == 0: raise HTTPException(404, "Post not found")
        return {"ok": True}

    @router.get("/blog/scheduled")
    async def list_scheduled_posts(user=user_dep):
        """Return all posts with status='scheduled', ordered by scheduled_at ascending."""
        tid = _tid(user)
        docs = await db.seo_blog_posts.find(
            {"user_id": tid, "status": "scheduled"}
        ).sort("scheduled_at", 1).limit(50).to_list(50)
        result = []
        for d in docs:
            s = _ser(d)
            content = s.get("content", "")
            s["content_preview"] = content[:120].strip() + ("…" if len(content) > 120 else "")
            result.append(s)
        return result

    # ── Auto-Publish ────────────────────────────────────────────────────────

    @router.post("/blog/publish")
    async def publish_post(payload: PublishRequest, user=user_dep):
        tid = _tid(user)
        doc = await db.seo_blog_posts.find_one({"_id": payload.post_id, "user_id": tid})
        if not doc: raise HTTPException(404, "Post not found")

        result: Dict[str, Any] = {"platform": payload.platform, "ok": False}

        if payload.platform == "wordpress":
            if not all([payload.wp_url, payload.wp_username, payload.wp_password]):
                raise HTTPException(400, "WordPress URL, username, and password required")
            try:
                import base64
                creds = base64.b64encode(f"{payload.wp_username}:{payload.wp_password}".encode()).decode()
                async with httpx.AsyncClient(timeout=30) as hc:
                    resp = await hc.post(
                        f"{payload.wp_url.rstrip('/')}/wp-json/wp/v2/posts",
                        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
                        json={
                            "title": doc.get("title", ""),
                            "content": doc.get("content", ""),
                            "status": "publish",
                            "meta": {
                                "_yoast_wpseo_title": doc.get("meta_title", ""),
                                "_yoast_wpseo_metadesc": doc.get("meta_description", ""),
                            },
                        },
                    )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    result.update({"ok": True, "post_url": data.get("link", ""), "wp_id": data.get("id")})
                else:
                    result["error"] = resp.text[:300]
            except Exception as e:
                result["error"] = str(e)

        elif payload.platform == "shopify":
            if not all([payload.shopify_domain, payload.shopify_token]):
                raise HTTPException(400, "Shopify domain and access token required")
            try:
                async with httpx.AsyncClient(timeout=30) as hc:
                    resp = await hc.post(
                        f"https://{payload.shopify_domain}/admin/api/2024-01/blogs/articles.json",
                        headers={"X-Shopify-Access-Token": payload.shopify_token, "Content-Type": "application/json"},
                        json={"article": {"title": doc.get("title", ""), "body_html": doc.get("content", ""), "published": True}},
                    )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    result.update({"ok": True, "article_id": data.get("article", {}).get("id")})
                else:
                    result["error"] = resp.text[:300]
            except Exception as e:
                result["error"] = str(e)
        else:
            raise HTTPException(400, f"Unsupported platform: {payload.platform}. Use 'wordpress' or 'shopify'.")

        if result["ok"]:
            await db.seo_blog_posts.update_one(
                {"_id": payload.post_id},
                {"$set": {"status": "published", "published_at": datetime.utcnow(), "publish_result": result}},
            )
            # Analytics: record publish event
            await _record_event("post_published", {"post_id": payload.post_id, "platform": payload.platform, "publish_result": result}, user)

        return result

    # ── Content Calendar ────────────────────────────────────────────────────

    @router.post("/blog/content-calendar")
    async def generate_content_calendar(
        business_type: str = "",
        posts_per_week: int = 2,
        weeks: int = 4,
        location: str = "",
        user=user_dep,
    ):
        import json as _json
        tid = _tid(user)
        ctx = _seo_business_context(user)
        bt = business_type.strip() or ctx["business_type"]
        loc = location.strip() or ctx["location"]
        snippet = ctx["context_snippet"]
        location_str = f" in {loc}" if loc else ""
        total = posts_per_week * weeks

        # ── Pull SEO memory for progressive improvement ──────────────────────
        past_posts = await db.seo_blog_posts.find(
            {"user_id": tid}
        ).sort("created_at", -1).limit(30).to_list(30)

        last_audit = await db.seo_audits.find_one({"user_id": tid}, sort=[("created_at", -1)])
        saved_kw = await db.seo_saved_keywords.find_one({"user_id": tid}, sort=[("month", -1)])

        # Topics already written — avoid repeats
        existing_titles = [p.get("title", "") for p in past_posts if p.get("title")]

        # Audit issues to address in new content
        audit_issues: List[str] = []
        if last_audit:
            for iss in (last_audit.get("issues") or [])[:5]:
                f = iss.get("field", "")
                if f and iss.get("type") in ("critical", "warning"):
                    audit_issues.append(f)

        # Saved keywords to weave in
        saved_keywords: List[str] = []
        if saved_kw:
            for k in (saved_kw.get("keywords") or [])[:10]:
                kw = k.get("keyword", "") if isinstance(k, dict) else str(k)
                if kw:
                    saved_keywords.append(kw)

        # Published vs draft counts
        pub_count = sum(1 for p in past_posts if p.get("status") == "published")
        draft_count = sum(1 for p in past_posts if p.get("status") == "draft")

        # Build memory block for the prompt
        memory_block = ""
        if existing_titles:
            titles_str = "\n".join(f"  - {t}" for t in existing_titles[:15])
            memory_block += f"\nAlready written (DO NOT repeat these topics — find fresh angles or complementary content):\n{titles_str}\n"
        if audit_issues:
            memory_block += f"\nSEO audit flagged these issues — create content that helps fix them: {', '.join(audit_issues)}\n"
        if saved_keywords:
            memory_block += f"\nSaved keywords to naturally incorporate: {', '.join(saved_keywords)}\n"
        if pub_count > 0 or draft_count > 0:
            memory_block += f"\nContent history: {pub_count} published, {draft_count} drafts. Build on momentum — go deeper on high-traffic topics and fill gaps.\n"

        extra = ""
        if snippet:
            extra = f"\nBusiness context (align topics with real offerings):\n{snippet[:1000]}\n"

        prompt = f"""Create a {weeks}-week content calendar for a {bt} business{location_str}.
Generate {total} blog post ideas ({posts_per_week} per week).

This is a PROGRESSIVE calendar — it builds on what has already been done and improves each cycle.
{memory_block}{extra}
Rules:
- Each title must be unique and NOT repeat any existing topic above
- Vary intent: mix informational, transactional, and local posts
- Prioritise keywords with high traffic potential
- Week 1 should address any quick-win SEO issues; later weeks go deeper

Return a JSON array:
[
  {{
    "week": 1,
    "day": "Monday",
    "title": "Full blog post title",
    "topic": "short topic summary",
    "keywords": ["keyword1", "keyword2"],
    "intent": "informational|transactional|local",
    "estimated_traffic": "low|medium|high"
  }}
]
Only return the JSON array."""

        raw = await _call_ai(prompt, max_tokens=2200)
        try:
            raw = raw.strip()
            if raw.startswith("```"): raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
            calendar = _json.loads(raw)
        except Exception:
            calendar = []

        return {
            "calendar": calendar,
            "weeks": weeks,
            "posts_per_week": posts_per_week,
            "memory_used": bool(existing_titles or audit_issues or saved_keywords),
        }

    # ── Bulk Calendar Draft Generation ──────────────────────────────────────

    @router.post("/calendar/generate-drafts")
    async def generate_calendar_drafts(payload: CalendarDraftRequest, user=user_dep):
        """Generate blog drafts for every item in the current calendar in one shot."""
        import json as _json
        tid = _tid(user)
        ctx = _seo_business_context(user)
        biz_name = ctx["business_name"]
        lang = ctx["language"]
        snippet = ctx["context_snippet"]

        word_targets = {"short": "400-500", "medium": "800-1000", "long": "1400-1600"}
        word_target = word_targets.get(payload.length, "800-1000")

        context_block = f"\nBusiness context:\n{snippet[:900]}\n" if snippet else ""

        results = []
        for item in payload.items[:20]:          # cap at 20 items per call
            topic   = str(item.get("title") or item.get("topic") or "").strip()
            kws     = item.get("keywords") or []
            week    = item.get("week", 1)
            day     = item.get("day", "")
            if not topic:
                continue

            keywords_str = ", ".join(kws) if kws else topic
            business_str = f" for {biz_name}" if biz_name else ""
            prompt = f"""Write a {word_target}-word SEO-optimized blog post{business_str}.

Topic: {topic}
Target keywords: {keywords_str}
Tone: {payload.tone}
Language: {lang}
{context_block}
Structure: H1 title → intro → H2 sections → conclusion with CTA.
After the article write:
META_TITLE: [50-60 char SEO title]
META_DESC: [140-160 char meta description]
TAGS: [comma-separated tags]

Write the full article now:"""

            try:
                raw = await _call_ai(prompt, max_tokens=2500)
                meta_title = ""
                meta_desc  = ""
                tags: List[str] = []
                mt = re.search(r"META_TITLE:\s*(.+)", raw)
                md = re.search(r"META_DESC:\s*(.+)", raw)
                tg = re.search(r"TAGS:\s*(.+)", raw)
                if mt: meta_title = mt.group(1).strip()
                if md: meta_desc  = md.group(1).strip()
                if tg: tags = [t.strip() for t in tg.group(1).split(",")]
                content = re.sub(r"\n(META_TITLE|META_DESC|TAGS):[^\n]+", "", raw).strip()
                word_count = len(content.split())

                doc = {
                    "_id": str(uuid.uuid4()),
                    "user_id": tid,
                    "title": meta_title or topic,
                    "content": content,
                    "meta_title": meta_title,
                    "meta_description": meta_desc,
                    "keywords": kws,
                    "tags": tags,
                    "status": "draft",
                    "platform": "internal",
                    "created_at": datetime.utcnow(),
                    "word_count": word_count,
                    # Calendar provenance
                    "calendar_week": week,
                    "calendar_day": day,
                    "calendar_topic": topic,
                    "calendar_keywords": kws,
                }
                await db.seo_blog_posts.insert_one(doc)
                # Analytics: record draft generation
                try:
                    await _record_event("draft_generated", {"post_id": doc["_id"], "title": doc.get("title"), "week": week, "day": day}, user)
                except Exception:
                    logger.exception("Failed to record draft_generated event")
                results.append({
                    "post_id": doc["_id"],
                    "title": doc["title"],
                    "week": week,
                    "day": day,
                    "status": "draft",
                    "word_count": word_count,
                })
            except Exception as e:
                logger.warning("[seo] draft gen failed for '%s': %s", topic, e)
                results.append({"title": topic, "week": week, "day": day, "status": "error", "error": str(e)})

        return {"drafts": results, "total": len(results)}

    # ── SEO Memory (progressive improvement) ────────────────────────────────

    @router.get("/seo-memory")
    async def get_seo_memory(user=user_dep):
        """Return structured history of what worked/didn't so the next cycle can improve."""
        import json as _json
        tid = _tid(user)

        # Last 3 months of audits
        audits = await db.seo_audits.find({"user_id": tid}).sort("created_at", -1).limit(15).to_list(15)
        # Blog posts with calendar provenance
        posts = await db.seo_blog_posts.find({"user_id": tid}).sort("created_at", -1).limit(50).to_list(50)
        # Saved keyword months
        kw_months = await db.seo_saved_keywords.find({"user_id": tid}).sort("month", -1).limit(3).to_list(3)

        # Build audit trend
        audit_history = []
        for a in audits:
            sa = _ser(a)
            issues = [i.get("field") for i in (a.get("issues") or []) if i.get("type") == "critical"]
            audit_history.append({
                "date": sa.get("created_at", "")[:10],
                "score": a.get("score", 0),
                "url": a.get("url", ""),
                "critical_issues": issues[:5],
            })

        # What topics/keywords have been written about
        published_topics = [
            {"title": p.get("title", ""), "tags": p.get("tags", []), "keywords": p.get("calendar_keywords", [])}
            for p in posts if p.get("status") == "published"
        ]
        draft_topics = [
            {"title": p.get("title", ""), "tags": p.get("tags", []), "keywords": p.get("calendar_keywords", [])}
            for p in posts if p.get("status") == "draft"
        ]

        # Score direction
        score_trend = "stable"
        if len(audit_history) >= 2:
            delta = audit_history[0]["score"] - audit_history[-1]["score"]
            score_trend = "improving" if delta > 5 else ("declining" if delta < -5 else "stable")

        # AI analysis of what to do differently
        analysis_prompt = None
        if audit_history or published_topics:
            audit_lines = "\n".join(
                f"  {a['date']} score={a['score']} issues={a['critical_issues']}"
                for a in audit_history[:5]
            ) or "  No audits yet."
            pub_lines = "\n".join(f"  - {p['title']}" for p in published_topics[:10]) or "  None published yet."
            draft_lines = "\n".join(f"  - {p['title']}" for p in draft_topics[:5]) or "  None."
            kw_line = ", ".join(
                str(k.get("keyword", "")) for m in kw_months for k in (m.get("keywords") or [])[:5]
            ) or "None saved."
            analysis_prompt = f"""You are an SEO strategist. Analyse this business's SEO history and tell them:
1. What is clearly working (topics/content types with good intent or high-traffic potential)
2. What isn't working (recurring audit issues, gaps)
3. What they should focus on NEXT month — specific topics or improvements

Audit history:
{audit_lines}

Published posts:
{pub_lines}

Draft posts (not yet live):
{draft_lines}

Keywords saved this month: {kw_line}

Respond with a JSON object:
{{
  "working": ["short point 1", ...],
  "not_working": ["short point 1", ...],
  "next_month_focus": ["specific action 1", ...],
  "score_trend": "{score_trend}"
}}
Only return the JSON."""

        analysis: dict = {"working": [], "not_working": [], "next_month_focus": [], "score_trend": score_trend}
        if analysis_prompt:
            try:
                raw = await _call_ai(analysis_prompt, max_tokens=600)
                raw = raw.strip()
                if raw.startswith("```"): raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
                analysis = _json.loads(raw)
            except Exception:
                pass

        return {
            "audit_history": audit_history,
            "published_count": len(published_topics),
            "draft_count": len(draft_topics),
            "published_topics": published_topics[:10],
            "draft_topics": draft_topics[:5],
            "score_trend": score_trend,
            "analysis": analysis,
            "kw_months": [m.get("month") for m in kw_months],
        }

    # ── SEO Stats summary ───────────────────────────────────────────────────

    @router.get("/summary")
    async def get_summary(user=user_dep):
        tid = _tid(user)
        total_posts = await db.seo_blog_posts.count_documents({"user_id": tid})
        published = await db.seo_blog_posts.count_documents({"user_id": tid, "status": "published"})
        drafts = await db.seo_blog_posts.count_documents({"user_id": tid, "status": "draft"})
        total_audits = await db.seo_audits.count_documents({"user_id": tid})

        last_audit = await db.seo_audits.find_one({"user_id": tid}, sort=[("created_at", -1)])
        avg_score = None
        audit_trend: List[dict] = []
        if last_audit:
            scores = await db.seo_audits.find({"user_id": tid}).sort("created_at", -1).limit(10).to_list(10)
            if scores:
                avg_score = round(sum(s.get("score", 0) for s in scores[:5]) / min(5, len(scores)))
                audit_trend = [
                    {
                        "date": _ser(s).get("created_at", ""),
                        "score": s.get("score", 0),
                        "url": s.get("url", ""),
                    }
                    for s in reversed(scores)
                ]

        return {
            "total_posts": total_posts,
            "published_posts": published,
            "draft_posts": drafts,
            "total_audits": total_audits,
            "avg_seo_score": avg_score,
            "last_audit": _ser(last_audit) if last_audit else None,
            "audit_trend": audit_trend,
        }

    # ── Analytics endpoints ───────────────────────────────────────────────

    @router.post("/analytics/event")
    async def record_analytics_event(payload: dict, user=user_dep):
        """Record a custom analytics event. Payload should include 'type' and optional 'payload' dict."""
        tid = _tid(user)
        event_type = str(payload.get("type") or "custom")
        evt_payload = payload.get("payload") or payload
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "type": event_type,
            "payload": evt_payload,
            "created_at": datetime.utcnow(),
        }
        await db.seo_analytics.insert_one(doc)
        return {"ok": True, "id": doc["_id"]}

    @router.get("/analytics/events")
    async def list_analytics_events(limit: int = 100, user=user_dep):
        tid = _tid(user)
        docs = await db.seo_analytics.find({"user_id": tid}).sort("created_at", -1).limit(limit).to_list(limit)
        return [_ser(d) for d in docs]

    # ── Saved Keywords ──────────────────────────────────────────────────────

    @router.post("/keywords/save")
    async def save_keywords(payload: SaveKeywordsRequest, user=user_dep):
        tid = _tid(user)
        import datetime as _dt
        month = payload.month.strip() or _dt.datetime.utcnow().strftime("%Y-%m")
        doc = {
            "_id": f"{tid}:{month}",
            "user_id": tid,
            "month": month,
            "keywords": payload.keywords,
            "business_type": payload.business_type,
            "location": payload.location,
            "saved_at": datetime.utcnow(),
        }
        await db.seo_saved_keywords.replace_one({"_id": f"{tid}:{month}"}, doc, upsert=True)
        return {"ok": True, "month": month, "count": len(payload.keywords)}

    @router.get("/keywords/saved")
    async def list_saved_keywords(user=user_dep):
        tid = _tid(user)
        docs = await db.seo_saved_keywords.find({"user_id": tid}).sort("month", -1).limit(12).to_list(12)
        return [
            {
                "month": d.get("month"),
                "keywords": d.get("keywords", []),
                "business_type": d.get("business_type", ""),
                "location": d.get("location", ""),
                "saved_at": d.get("saved_at").isoformat() if d.get("saved_at") else "",
                "count": len(d.get("keywords", [])),
            }
            for d in docs
        ]

    @router.get("/keywords/saved/{month}")
    async def get_saved_keywords(month: str, user=user_dep):
        tid = _tid(user)
        doc = await db.seo_saved_keywords.find_one({"_id": f"{tid}:{month}"})
        if not doc:
            raise HTTPException(404, "No saved keywords for that month")
        return {
            "month": doc.get("month"),
            "keywords": doc.get("keywords", []),
            "business_type": doc.get("business_type", ""),
            "location": doc.get("location", ""),
        }

    # ── Publish Credentials (save per platform so user doesn't re-enter) ────

    @router.put("/publish-credentials")
    async def save_publish_credentials(payload: PublishCredentials, user=user_dep):
        tid = _tid(user)
        doc_id = f"{tid}:{payload.platform}"
        data: dict = {"user_id": tid, "platform": payload.platform, "updated_at": datetime.utcnow()}
        if payload.platform == "wordpress":
            if payload.wp_url: data["wp_url"] = payload.wp_url
            if payload.wp_username: data["wp_username"] = payload.wp_username
            if payload.wp_password: data["wp_password"] = payload.wp_password
        elif payload.platform == "shopify":
            if payload.shopify_domain: data["shopify_domain"] = payload.shopify_domain
            if payload.shopify_token: data["shopify_token"] = payload.shopify_token
        await db.seo_publish_creds.replace_one({"_id": doc_id}, {"_id": doc_id, **data}, upsert=True)
        return {"ok": True}

    @router.get("/publish-credentials/{platform}")
    async def get_publish_credentials(platform: str, user=user_dep):
        tid = _tid(user)
        doc = await db.seo_publish_creds.find_one({"_id": f"{tid}:{platform}"})
        if not doc:
            return {}
        doc.pop("_id", None)
        doc.pop("user_id", None)
        v = doc.pop("updated_at", None)
        if v and hasattr(v, "isoformat"): doc["updated_at"] = v.isoformat()
        return doc

    # ── Monthly Improvement Suggestions ─────────────────────────────────────

    @router.get("/improvement-suggestions")
    async def get_improvement_suggestions(user=user_dep):
        """Compare last 2 audits + current keyword/blog stats and return AI improvement tips."""
        tid = _tid(user)
        ctx = _seo_business_context(user)

        audits = await db.seo_audits.find({"user_id": tid}).sort("created_at", -1).limit(2).to_list(2)
        total_posts = await db.seo_blog_posts.count_documents({"user_id": tid})
        published = await db.seo_blog_posts.count_documents({"user_id": tid, "status": "published"})
        saved_kw_doc = await db.seo_saved_keywords.find_one({"user_id": tid}, sort=[("month", -1)])
        kw_count = len((saved_kw_doc or {}).get("keywords", []))

        # Build context for AI
        audit_lines = []
        for a in audits:
            issues_summary = "; ".join(
                f"{i['field']} ({i['type']})" for i in (a.get("issues") or [])[:5]
            )
            audit_lines.append(
                f"- Score {a.get('score', 0)}/100 on {a.get('url', '')} "
                f"({_ser(a).get('created_at', '')[:10]}): {issues_summary or 'No issues'}"
            )

        score_change = ""
        if len(audits) == 2:
            delta = audits[0].get("score", 0) - audits[1].get("score", 0)
            score_change = f"Score changed by {'+' if delta >= 0 else ''}{delta} points since last audit."

        prompt = f"""You are an SEO strategist reviewing a business's monthly SEO progress.

Business: {ctx.get('business_name') or 'Unknown'} ({ctx.get('business_type', '')} in {ctx.get('location', '')})

SEO activity this month:
- Blog posts total: {total_posts} ({published} published)
- Saved keywords: {kw_count}
- Recent audits:
{chr(10).join(audit_lines) if audit_lines else '  No audits run yet.'}
{score_change}

Generate 5 specific, actionable improvement suggestions for next month.
Keep each suggestion to 1-2 sentences. Be concrete — reference their actual situation above.
Return a JSON array:
[
  {{"priority": "high|medium|low", "action": "Short action title", "detail": "1-2 sentence explanation"}}
]
Only return the JSON array."""

        try:
            raw = await _call_ai(prompt, max_tokens=800)
            raw = raw.strip()
            if raw.startswith("```"): raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
            import json as _json
            suggestions = _json.loads(raw)
        except Exception:
            suggestions = [
                {"priority": "high", "action": "Run a site audit", "detail": "You haven't audited your site yet. Start with the Audit tab to find quick wins."},
                {"priority": "high", "action": "Save your keyword list", "detail": "Generate keywords and save them for this month so your content stays focused."},
                {"priority": "medium", "action": "Publish at least 2 blog posts", "detail": "Fresh content signals activity to Google. Use the Calendar to plan topics."},
                {"priority": "medium", "action": "Add meta descriptions", "detail": "Missing meta descriptions reduce click-through rates from Google results."},
                {"priority": "low", "action": "Check for broken image alt text", "detail": "Images without alt text miss a ranking opportunity and hurt accessibility."},
            ]

        return {"suggestions": suggestions, "generated_at": datetime.utcnow().isoformat()}

    # ── Local SEO Routes ───────────────────────────────────────────────────

    @router.get("/local/listings")
    async def get_local_listings(user=user_dep):
        """Return saved business listings from the database."""
        tid = _tid(user)
        docs = await db.local_seo_listings.find({"user_id": tid}).sort("created_at", -1).to_list(100)
        return {"listings": [_ser(d) for d in docs]}

    @router.post("/local/listings")
    async def add_local_listing(payload: Dict[str, Any], user=user_dep):
        """Persist a new business listing to the database."""
        tid = _tid(user)
        required = ["platform", "name", "address"]
        for field in required:
            if not payload.get(field, "").strip():
                raise HTTPException(400, f"Missing required field: {field}")
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "platform": payload["platform"],
            "name": payload["name"].strip(),
            "address": payload["address"].strip(),
            "phone": payload.get("phone", "").strip(),
            "website": payload.get("website", "").strip(),
            "status": payload.get("status", "pending"),
            "rating": payload.get("rating"),
            "reviews": payload.get("reviews"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await db.local_seo_listings.insert_one(doc)
        return {"success": True, "listing": _ser(doc)}

    @router.patch("/local/listings/{listing_id}")
    async def update_local_listing(listing_id: str, payload: Dict[str, Any], user=user_dep):
        """Update an existing listing."""
        tid = _tid(user)
        allowed = {"platform", "name", "address", "phone", "website", "status", "rating", "reviews"}
        upd = {k: v for k, v in payload.items() if k in allowed}
        upd["updated_at"] = datetime.utcnow()
        result = await db.local_seo_listings.update_one(
            {"_id": listing_id, "user_id": tid}, {"$set": upd}
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Listing not found")
        doc = await db.local_seo_listings.find_one({"_id": listing_id})
        return {"success": True, "listing": _ser(doc)}

    @router.delete("/local/listings/{listing_id}")
    async def delete_local_listing(listing_id: str, user=user_dep):
        """Delete a business listing from the database."""
        tid = _tid(user)
        result = await db.local_seo_listings.delete_one({"_id": listing_id, "user_id": tid})
        if result.deleted_count == 0:
            raise HTTPException(404, "Listing not found")
        return {"ok": True}

    @router.get("/local/keywords")
    async def get_local_keywords(user=user_dep):
        """Return suggested local keywords based on the user's business profile."""
        tid = _tid(user)
        ctx = _seo_business_context(user)
        location = ctx.get("location", "Your City")
        business_type = ctx.get("business_type", "business")
        city = location.split(",")[0].strip()
        keywords = [
            {"keyword": f"{business_type} near me", "location": location, "difficulty": "high", "note": "suggested"},
            {"keyword": f"{business_type} in {city}", "location": location, "difficulty": "medium", "note": "suggested"},
            {"keyword": f"best {business_type} {city}", "location": location, "difficulty": "medium", "note": "suggested"},
            {"keyword": f"affordable {business_type} {city}", "location": location, "difficulty": "low", "note": "suggested"},
            {"keyword": f"{business_type} services {city}", "location": location, "difficulty": "medium", "note": "suggested"},
        ]
        return {"keywords": keywords, "source": "business_profile"}

    @router.get("/local/competitors")
    async def get_local_competitors(user=user_dep):
        """Return placeholder competitor slots — connect Google Places for real data."""
        tid = _tid(user)
        return {"competitors": [], "note": "Connect Google Places API for live competitor data."}

    @router.get("/local/score")
    async def get_local_seo_score(user=user_dep):
        """Compute local SEO score from actual saved listings."""
        tid = _tid(user)
        listing_count = await db.local_seo_listings.count_documents({"user_id": tid})
        verified_count = await db.local_seo_listings.count_documents({"user_id": tid, "status": "verified"})
        ctx = _seo_business_context(user)
        country = ctx.get("location", "your area")

        listings_score = min(100, listing_count * 25)
        verified_score = min(100, verified_count * 34)
        overall = round((listings_score + verified_score) / 2) if listing_count > 0 else 0

        if overall >= 80:
            grade = "Excellent"
        elif overall >= 60:
            grade = "Good"
        elif overall >= 40:
            grade = "Fair"
        else:
            grade = "Needs Work"

        recommendations = []
        if listing_count == 0:
            recommendations.append("Add your first business listing (start with Google Business Profile).")
        if listing_count < 3:
            recommendations.append("List your business on Yelp, Apple Maps and Bing Places for wider coverage.")
        if verified_count < listing_count:
            recommendations.append("Verify your pending listings to boost your score.")
        recommendations.append(f"Target local keyword opportunities in {country}.")

        return {
            "overall": overall,
            "grade": grade,
            "listing_count": listing_count,
            "verified_count": verified_count,
            "breakdown": {
                "business_listings": listings_score,
                "verified_listings": verified_score,
            },
            "recommendations": recommendations,
        }

    # ── SERP Ranking History ───────────────────────────────────────────────

    @router.post("/serp/rankings")
    async def save_serp_ranking(payload: Dict[str, Any], user=user_dep):
        """Save a SERP ranking check result for historical tracking"""
        tid = _tid(user)
        doc = {
            "user_id": tid,
            "keyword": payload["keyword"],
            "domain": payload["domain"],
            "position": payload.get("position"),
            "location_code": payload.get("location_code", 2404),
            "language_code": payload.get("language_code", "en"),
            "checked_at": datetime.utcnow(),
            "search_volume": payload.get("search_volume"),
            "competition": payload.get("competition"),
        }
        await db.seo_serp_rankings.insert_one(doc)
        return {"success": True}

    @router.get("/serp/rankings")
    async def get_serp_rankings(keyword: str = None, domain: str = None, limit: int = 50, user=user_dep):
        """Get historical SERP ranking data"""
        tid = _tid(user)
        query = {"user_id": tid}
        if keyword:
            query["keyword"] = keyword
        if domain:
            query["domain"] = domain

        rankings = await db.seo_serp_rankings.find(query).sort("checked_at", -1).limit(limit).to_list(limit)

        # Format for frontend
        formatted = []
        for r in rankings:
            formatted.append({
                "keyword": r["keyword"],
                "domain": r["domain"],
                "position": r["position"],
                "checked_at": r["checked_at"].isoformat() if hasattr(r["checked_at"], "isoformat") else str(r["checked_at"]),
                "location_code": r.get("location_code"),
                "search_volume": r.get("search_volume"),
            })

        return {"rankings": formatted}

    @router.get("/serp/rankings/trends")
    async def get_serp_trends(keyword: str, domain: str, days: int = 30, user=user_dep):
        """Get ranking trends for a specific keyword/domain combination"""
        tid = _tid(user)
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)

        rankings = await db.seo_serp_rankings.find({
            "user_id": tid,
            "keyword": keyword,
            "domain": domain,
            "checked_at": {"$gte": cutoff}
        }).sort("checked_at", 1).to_list(1000)

        # Group by date and calculate trends
        trends = {}
        for r in rankings:
            date_key = r["checked_at"].date().isoformat()
            if date_key not in trends:
                trends[date_key] = []
            trends[date_key].append(r["position"])

        # Average positions per day
        trend_data = []
        for date, positions in sorted(trends.items()):
            avg_position = sum(p for p in positions if p) / len([p for p in positions if p]) if positions else None
            trend_data.append({
                "date": date,
                "position": avg_position,
                "checks": len(positions)
            })

        return {"trends": trend_data, "keyword": keyword, "domain": domain}

    return router
