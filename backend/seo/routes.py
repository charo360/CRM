"""SEO + Auto-Blogging module — site audit, keyword research, AI blog writer, auto-publish."""
from __future__ import annotations
import logging, uuid, re, httpx
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# ── VebAPI helpers (keyword research + SERP) ──────────────────────────────────
_VEBAPI_BASE = "https://vebapi.com/api"


def _veb_headers() -> dict:
    import os
    key = os.environ.get("VEBAPI_KEY", "").strip()
    if not key:
        raise RuntimeError("VEBAPI_KEY not set")
    return {"X-API-KEY": key}


async def _veb_get(endpoint: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as hc:
        resp = await hc.get(f"{_VEBAPI_BASE}{endpoint}", headers=_veb_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


def _parse_vol(v) -> int:
    """Parse VebAPI volume strings like '1K', '10,000', or ints."""
    if v is None:
        return 0
    s = str(v).replace(",", "").strip()
    if s.endswith("K"):
        return int(float(s[:-1]) * 1000)
    if s.endswith("M"):
        return int(float(s[:-1]) * 1_000_000)
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _comp_to_difficulty(comp) -> str:
    try:
        c = float(str(comp).replace("%", ""))
    except (ValueError, TypeError):
        return "medium"
    if c < 0.33 or c < 33:
        return "low"
    if c < 0.66 or c < 66:
        return "medium"
    return "high"


def _tid(user): return user.get("business_id", user["_id"])


_TEMPLATE_CATEGORIES: dict[str, str] = {
    "how-to":     "How-To Guides",
    "listicle":   "Top Lists",
    "case-study": "Success Stories",
    "local":      "Local Business",
    "educational":"Education",
    "comparison": "Comparisons",
}


async def _wp_get_or_create_category(wp_url: str, creds: str, name: str) -> "int | None":
    """Returns the WordPress category ID for *name*, creating the category if absent."""
    try:
        headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15) as hc:
            r = await hc.get(
                f"{wp_url.rstrip('/')}/wp-json/wp/v2/categories",
                headers=headers,
                params={"search": name, "per_page": 5},
            )
            if r.status_code == 200:
                for cat in r.json():
                    if cat.get("name", "").lower() == name.lower():
                        return cat["id"]
            cr = await hc.post(
                f"{wp_url.rstrip('/')}/wp-json/wp/v2/categories",
                headers=headers,
                json={"name": name},
            )
            if cr.status_code == 201:
                return cr.json().get("id")
    except Exception:
        pass
    return None


async def _wp_upload_image(wp_url: str, creds: str, image_url: str, filename: str) -> "int | None":
    """Downloads *image_url* and uploads it to the WordPress media library. Returns media ID or None."""
    try:
        async with httpx.AsyncClient(timeout=40) as hc:
            img = await hc.get(image_url)
            img.raise_for_status()
            mr = await hc.post(
                f"{wp_url.rstrip('/')}/wp-json/wp/v2/media",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": "image/png",
                },
                content=img.content,
            )
            if mr.status_code == 201:
                return mr.json().get("id")
    except Exception:
        pass
    return None


def _markdown_to_html(md: str) -> str:
    """Convert markdown content to clean HTML for publishing to WordPress / Shopify."""

    def _inline(text: str) -> str:
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        return text

    def _parse_row(row: str):
        parts = row.split('|')
        if parts and not parts[0].strip():
            parts = parts[1:]
        if parts and not parts[-1].strip():
            parts = parts[:-1]
        return [c.strip() for c in parts]

    # Strip META lines and leading H1 (title shown separately)
    content = re.sub(r'(?m)^\*{0,2}(META_TITLE|META_DESC|TAGS)\*{0,2}:[^\n]*\n?', '', md).strip()

    lines = content.split('\n')
    parts: List[str] = []
    i = 0

    while i < len(lines):
        raw = lines[i]
        s = raw.strip()

        # Skip H1
        if re.match(r'^# [^#]', s):
            i += 1; continue

        # H2 – H4
        if s.startswith('#### '):
            parts.append(f'<h4 style="font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin:20px 0 6px">{_inline(s[5:])}</h4>')
            i += 1; continue
        if s.startswith('### '):
            parts.append(f'<h3 style="font-size:16px;font-weight:600;margin:24px 0 8px">{_inline(s[4:])}</h3>')
            i += 1; continue
        if s.startswith('## '):
            parts.append(f'<h2 style="font-size:20px;font-weight:700;margin:32px 0 10px;border-bottom:1px solid #e2e8f0;padding-bottom:6px">{_inline(s[3:])}</h2>')
            i += 1; continue

        # Table
        if s.startswith('|'):
            tbl: List[str] = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                tbl.append(lines[i]); i += 1
            if len(tbl) >= 2:
                headers = _parse_row(tbl[0])
                body_rows = [_parse_row(r) for r in tbl[2:]]
                th = ''.join(
                    f'<th style="padding:10px 14px;text-align:left;background:#1e293b;color:#fff;font-size:12px;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap">{_inline(h)}</th>'
                    for h in headers
                )
                tbody = ''
                for ri, row in enumerate(body_rows):
                    bg = '#ffffff' if ri % 2 == 0 else '#f8fafc'
                    td = ''.join(
                        f'<td style="padding:10px 14px;border-top:1px solid #e2e8f0;color:#334155">{_inline(c)}</td>'
                        for c in row
                    )
                    tbody += f'<tr style="background:{bg}">{td}</tr>'
                parts.append(
                    f'<table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin:24px 0">'
                    f'<thead><tr>{th}</tr></thead><tbody>{tbody}</tbody></table>'
                )
            continue

        # Unordered list
        if re.match(r'^[*\-] ', s):
            items: List[str] = []
            while i < len(lines) and re.match(r'^[*\-] ', lines[i].strip()):
                items.append(f'<li style="margin-bottom:6px">{_inline(lines[i].strip()[2:])}</li>'); i += 1
            parts.append(f'<ul style="margin:16px 0;padding-left:22px">{"".join(items)}</ul>')
            continue

        # Ordered list
        if re.match(r'^\d+\. ', s):
            items = []
            while i < len(lines) and re.match(r'^\d+\. ', lines[i].strip()):
                text = re.sub(r'^\d+\. ', '', lines[i].strip())
                items.append(f'<li style="margin-bottom:6px">{_inline(text)}</li>'); i += 1
            parts.append(f'<ol style="margin:16px 0;padding-left:22px">{"".join(items)}</ol>')
            continue

        # Blockquote
        if s.startswith('> '):
            bq: List[str] = []
            while i < len(lines) and lines[i].strip().startswith('> '):
                bq.append(_inline(lines[i].strip()[2:])); i += 1
            parts.append(
                f'<blockquote style="border-left:4px solid #10b981;background:#f0fdf4;padding:12px 16px;margin:20px 0;font-style:italic;color:#374151">'
                f'{"<br>".join(bq)}</blockquote>'
            )
            continue

        # HR
        if re.match(r'^---+$', s):
            parts.append('<hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">')
            i += 1; continue

        # Blank
        if not s:
            i += 1; continue

        # Paragraph
        para: List[str] = []
        while i < len(lines):
            ls = lines[i].strip()
            if not ls: break
            if re.match(r'^#{1,4} |^[*\-] |\d+\. |^> |^---+$|^\|', ls): break
            para.append(ls); i += 1
        if para:
            parts.append(f'<p style="margin:0 0 16px;line-height:1.8;color:#374151">{_inline("<br>".join(para))}</p>')

    return '\n'.join(parts)


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
    _PLACEHOLDER_VALUES = {"not specified", "not set", "n/a", "none", "unspecified", "-", "–"}
    loc_parts: List[str] = []
    bl = str(bk.get("business_location") or "").strip()
    if bl and bl.lower() not in _PLACEHOLDER_VALUES:
        loc_parts.append(bl)
    country = str(settings.get("country") or "").strip()
    if country and country.lower() not in _PLACEHOLDER_VALUES:
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
    bt_clean = (business_type or "").strip().replace("-", " ")
    generic = {"general", "retail", "business", "service", "services"}

    # Only use business name if it reads as a descriptive phrase, not a short brand token.
    # Short names (≤ 6 chars) like "Zilo" collide with unrelated brands (Zillow etc.)
    # and produce completely wrong keyword results from VebAPI.
    bn = (business_name or "").strip()
    bn_is_descriptive = len(bn.split()) >= 3 or (len(bn) > 6 and bn.lower() not in generic)

    if bt_clean and bt_clean.lower() not in generic:
        # Combine type + brand only when brand adds semantic value (multi-word)
        if bn_is_descriptive and len(bn.split()) >= 2:
            return f"{bt_clean} {bn}"[:100]
        return bt_clean[:100]

    if snippet:
        frag = snippet.replace("\n", " ").strip()[:100]
        if len(frag) >= 8:
            return frag

    if bn_is_descriptive:
        return bn[:100]

    return bt_clean[:100] if bt_clean else "small business services"


async def _ai_generate_keywords(
    snippet: str, business_type: str, location: str, exclude: set[str]
) -> list[dict]:
    """Generate 25 business-specific keyword phrases with intent + blog angles.
    Returns list of {"keyword": str, "intent": str, "angle": str} dicts.
    Keywords are service+location phrases, NOT generic product/ingredient names.
    """
    exclude_sample = sorted(exclude)[:30]
    exclude_block = (
        "\nDo NOT reuse any of these already-researched keywords:\n"
        + "\n".join(f"- {k}" for k in exclude_sample)
    ) if exclude_sample else ""

    city = location.split(",")[0].strip() if location else ""
    loc_line = f"Location: {location}" if location else ""

    if snippet and snippet.strip():
        context_block = (
            f"Business type: {business_type}\n"
            f"{loc_line}\n"
            f"Business description:\n\"\"\"\n{snippet[:900]}\n\"\"\"\n\n"
            f"Generate 25 search keyword phrases that potential CUSTOMERS of THIS business type in {location or 'their area'} would type into Google."
        )
    else:
        context_block = (
            f"Business type: {business_type}\n"
            f"{loc_line}\n\n"
            f"Generate 25 search keyword phrases that potential CUSTOMERS of a '{business_type}' business{f' in {location}' if location else ''} would type into Google."
        )

    prompt = (
        f"You are an SEO keyword strategist.\n\n"
        f"{context_block}\n\n"
        f"For each keyword output THREE things on one line, separated by ||\n\n"
        f"FORMAT (exactly):\n"
        f"search keyword || intent || Compelling blog title that makes someone click\n\n"
        f"INTENT must be one of: local | transactional | informational | navigational\n\n"
        f"KEYWORD MIX — generate EXACTLY this distribution (5 each):\n"
        f"- 5 LOCAL: '[service] {city}', '[business type] near me', 'best [service] in {city}'\n"
        f"- 5 TRANSACTIONAL: 'buy [product]', 'order [service] online', '[service] price', 'affordable [service]'\n"
        f"- 5 BUYER-INTENT: 'best [service]', '[service] for [customer type]', 'where to get [product]'\n"
        f"- 5 INFORMATIONAL: 'how to [relevant action]', 'what is [relevant thing]', '[service] guide'\n"
        f"- 5 LONG-TAIL: 3-5 word phrases combining service + qualifier + location or customer type\n\n"
        f"KEYWORD RULES:\n"
        f"- 2-5 words that real customers type — based on WHAT THIS BUSINESS SELLS/DOES\n"
        f"- Use '{city}' naturally in local keywords (e.g. 'pharmacy {city}', 'dentist {city}')\n"
        f"- NO standalone product/ingredient/drug names (e.g. NOT 'azithromycin' alone — use 'buy azithromycin {city}' or 'azithromycin price {city}')\n"
        f"- NO generic single-word keywords like a product name with nothing else\n"
        f"- NO brand names of competitors\n"
        f"- Every keyword must describe a SERVICE or BUYING ACTION, not just name a product\n\n"
        f"BLOG TITLE RULES:\n"
        f"- Use numbers, specific outcomes, or provocative questions\n"
        f"- Reference {city} or the customer's situation where natural\n"
        f"- GOOD: '7 Signs You Need a {city} Pharmacist Today', 'Where to Buy Affordable Medicines in {city}'\n"
        f"- BAD: 'A Guide to X', 'Understanding X', 'The Importance of X'\n"
        f"{exclude_block}\n\n"
        f"Output exactly 25 lines in the format: keyword || intent || Blog Title\nNo numbering, no extra text."
    )
    try:
        raw = await _call_ai(prompt, max_tokens=900)
        results = []
        for line in raw.strip().splitlines():
            line = line.strip().strip("-•123456789. ").strip()
            if "||" not in line:
                continue
            parts = [p.strip().strip('"').strip("'") for p in line.split("||")]
            kw = parts[0] if parts else ""
            intent = parts[1].lower().strip() if len(parts) > 1 else "informational"
            angle = parts[2] if len(parts) > 2 else ""
            # Normalise intent
            valid_intents = {"local", "transactional", "informational", "navigational"}
            if intent not in valid_intents:
                intent = "informational"
            if kw and len(kw) >= 3 and kw.lower() not in {e.lower() for e in exclude}:
                results.append({"keyword": kw, "intent": intent, "angle": angle or f"Write about '{kw}'"})
        logger.info("[seo] AI generated %d keyword+intent+angle triples", len(results))
        return results[:25]
    except Exception as e:
        logger.warning("[seo] _ai_generate_keywords failed: %s", e)
    return []


async def _ai_keyword_seeds(snippet: str, business_type: str) -> list[str]:
    """Use AI to extract 3 short, natural Google search seeds from the business description.

    Rules enforced via prompt:
    - 2-5 words each (short enough that VebAPI expands them naturally)
    - No brand name, no location (location is passed separately to VebAPI)
    - What a real customer would type into Google, not marketing language
    """
    prompt = (
        f"You are an SEO keyword strategist. A business has this description and services:\n\n"
        f"\"\"\"\n{snippet[:900]}\n\"\"\"\n\n"
        f"Generate exactly 10 short seed topics for this business. These seeds go into a keyword "
        f"research API that expands them into real searches. STRICT RULES:\n"
        f"- 2-3 words MAXIMUM per seed (e.g. 'crm software', 'sales automation', 'whatsapp business')\n"
        f"- Under 30 characters each\n"
        f"- Generic industry terms people actually google, not marketing phrases\n"
        f"- No brand names, no location words, no hyphens\n"
        f"- Cover: product type, key feature, pain point, use case, alternatives\n"
        f"- Return ONLY the 10 seeds, one per line, no numbering, no explanation"
    )
    try:
        raw = await _call_ai(prompt, max_tokens=120)
        seeds = []
        for line in raw.strip().splitlines():
            s = line.strip().strip("-•123456789. ").strip('"').strip("'")
            if s and 1 <= len(s.split()) <= 3 and 3 <= len(s) <= 30:
                seeds.append(s)
        if seeds:
            logger.info("[seo] AI keyword seeds: %s", seeds)
            return seeds[:10]
    except Exception as e:
        logger.warning("[seo] _ai_keyword_seeds failed: %s", e)
    return []


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
    existing_titles: List[str] = []  # already-published titles for this keyword — avoid repeating angles

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

        # ── DataForSEO setup (shared by both DFS paths below) ───────────────
        dfs_settings = user.get("settings") or {}
        dfs_lc = dfs.resolve_location_code(
            str(dfs_settings.get("country") or ""),
            str(dfs_settings.get("country_code") or user.get("country_code") or ""),
        )
        dfs_lang = dfs.language_code_from_settings(lang)
        # Human-readable country label for the local volume badge (e.g. "Kenya")
        dfs_country_label = (
            str(dfs_settings.get("country") or "").strip()
            or str(user.get("country") or "").strip()
            or "Local"
        )

        # ── PRIMARY: AI generates keywords → DataForSEO search_volume/live ─────
        # Confirmed working: search_volume/live accepts up to 1000 keywords per call.
        # AI generates 25 short (2-3 word) relevant phrases, DataForSEO returns
        # real Google Ads search volumes for each in a single batch call.
        if not keywords and dfs.dfs_enabled() and (snippet or bt):
            try:
                ai_kw_list = await _ai_generate_keywords(snippet, bt, loc, already_saved)
                logger.info("[seo] AI generated %d keyword candidates for volume lookup", len(ai_kw_list))
                if ai_kw_list:
                    # Extract keyword strings for volume lookup
                    kw_strings = [item["keyword"] for item in ai_kw_list]
                    angle_map = {item["keyword"].lower().strip(): item["angle"] for item in ai_kw_list}
                    intent_map = {item["keyword"].lower().strip(): item.get("intent", "informational") for item in ai_kw_list}

                    # Fetch local + global + top markets in parallel.
                    # GLOBAL_MARKETS covers 25 countries across all continents — no hardcoding here.
                    import asyncio as _asyncio
                    _region_codes = [r for r in dfs.GLOBAL_MARKETS if r[0] != dfs_lc][:6]
                    _region_maps = await _asyncio.gather(
                        dfs.fetch_keyword_meta_batch(kw_strings, location_code=dfs_lc, language_code=dfs_lang),
                        dfs.fetch_search_volumes_batch(kw_strings, location_code=None, language_code=dfs_lang),
                        *[dfs.fetch_search_volumes_batch(kw_strings, location_code=rc[0], language_code=dfs_lang)
                          for rc in _region_codes],
                    )
                    local_meta = _region_maps[0]   # {kw: {volume, cpc, competition, competition_index}}
                    global_map = _region_maps[1]
                    region_vol_maps = {rc[1]: _region_maps[2 + i] for i, rc in enumerate(_region_codes)}
                    logger.info("[seo] DataForSEO volumes: local=%d global=%d regions=%d", len(local_meta), len(global_map), len(region_vol_maps))

                    for item in ai_kw_list:
                        kw_text = item["keyword"]
                        key = kw_text.lower().strip()
                        meta = local_meta.get(key, {})
                        local_vol = meta.get("volume", 0)
                        global_vol = global_map.get(key, 0)
                        cpc = meta.get("cpc")
                        trend = meta.get("trend")
                        monthly_searches = meta.get("monthly_searches", [])

                        # SEO difficulty based on global search volume.
                        # High global volume = more established pages competing = harder to rank.
                        ref = global_vol or local_vol
                        diff = "high" if ref >= 50000 else "medium" if ref >= 5000 else "low"

                        # Find top region by volume
                        region_scores = {name: m.get(key, 0) for name, m in region_vol_maps.items()}
                        top_region = max(region_scores, key=region_scores.get) if region_scores else None
                        top_region_vol = region_scores.get(top_region, 0) if top_region else 0
                        if top_region_vol == 0:
                            top_region = None

                        ref_vol = global_vol or local_vol
                        pri = 5 if ref_vol >= 10000 else 4 if ref_vol >= 2000 else 3 if ref_vol >= 500 else 2 if ref_vol >= 50 else 1
                        keywords.append({
                            "keyword": kw_text,
                            "search_volume": local_vol if local_vol else None,
                            "local_country": dfs_country_label if (local_vol and dfs_country_label) else None,
                            "global_search_volume": global_vol if global_vol else None,
                            "top_region": top_region,
                            "top_region_volume": top_region_vol if top_region else None,
                            "cpc": cpc,
                            "difficulty": diff,
                            "trend": trend,
                            "monthly_searches": monthly_searches,
                            "intent": intent_map.get(key, "informational"),
                            "priority": pri,
                            "content_idea": angle_map.get(key, f"Write about '{kw_text}'"),
                            "strategy_type": intent_map.get(key, "informational"),
                        })
                    keyword_source = "ai+dataforseo"
                    with_vol = sum(1 for k in keywords if k.get("global_search_volume"))
                    logger.info("[seo] AI+DataForSEO: %d keywords, %d with global volume", len(keywords), with_vol)

                    # ── SUPPLEMENT: replace zero-volume AI keywords with real DataForSEO ideas ──
                    # AI-invented keywords that got 0 global volume aren't real searches.
                    # Use the zero-vol keyword phrases themselves as seeds (2-3 word extracts)
                    # so the replacements stay strictly on-topic with the business.
                    zero_vol_kws = [k for k in keywords if not k.get("global_search_volume") and not k.get("search_volume")]
                    if len(zero_vol_kws) >= 3:
                        try:
                            # Extract 2-3 word seeds from the zero-vol keyword phrases
                            zv_seeds = list({" ".join(k["keyword"].split()[:3]) for k in zero_vol_kws})[:10]
                            if zv_seeds:
                                already_in = {k["keyword"].lower() for k in keywords}
                                real_kws = await dfs.fetch_keywords_for_seeds(
                                    zv_seeds,
                                    location_code=dfs_lc,
                                    language_code=dfs_lang,
                                    limit=len(zero_vol_kws) + 5,
                                    exclude_phrases=already_saved | already_in,
                                )
                                if real_kws:
                                    # Remove zero-vol AI keywords, add real DataForSEO ones
                                    keywords = [k for k in keywords if k.get("global_search_volume") or k.get("search_volume")]
                                    # Set local_country on supplement keywords — they were fetched with dfs_lc (Kenya)
                                    for rk in real_kws:
                                        rkey = rk["keyword"].lower().strip()
                                        lmeta = local_meta.get(rkey, {})
                                        rk["local_country"] = dfs_country_label if dfs_country_label else None
                                        if lmeta.get("volume"):
                                            rk["search_volume"] = lmeta["volume"]
                                            rk["cpc"] = rk.get("cpc") or lmeta.get("cpc")
                                    keywords.extend(real_kws[:len(zero_vol_kws)])
                                    keywords = keywords[:25]
                                    logger.info("[seo] Supplemented %d zero-vol AI keywords with %d real DataForSEO ideas", len(zero_vol_kws), len(real_kws))
                        except Exception as sup_e:
                            logger.warning("[seo] Keyword supplement skipped: %s", sup_e)

            except Exception as e:
                logger.warning("[seo] AI+DataForSEO primary flow failed: %s", e)
                keywords = []

        # ── FALLBACK A: DataForSEO seed expansion (keyword ideas) ────────────
        if not keywords and dfs.dfs_enabled():
            try:
                seed = _keyword_research_seed(bt, ctx["business_name"], snippet)
                keywords = await dfs.fetch_diverse_keywords(
                    seed,
                    location=loc,
                    location_code=dfs_lc,
                    language_code=dfs_lang,
                    limit=30,
                    exclude_phrases=already_saved,
                )
                if keywords:
                    keyword_source = "dataforseo"
            except Exception as e:
                logger.warning("[seo] DataForSEO keyword ideas skipped: %s", e)

        # ── VebAPI fallback: real keyword data with actual volumes ────────────
        if not keywords:
            try:
                import asyncio as _asyncio
                settings = user.get("settings") or {}
                country_code = str(settings.get("country_code") or user.get("country_code") or "").upper()[:2]

                # Build seed list: AI generates 3 short natural-search phrases from description.
                # No location in seeds — location collisions (e.g. "Kenya airways") come from
                # including geo-terms in the seed itself. The country_code param handles geo.
                seeds: list[str] = []
                if snippet:
                    seeds = await _ai_keyword_seeds(snippet, bt)
                if not seeds:
                    # Static fallback: derive from business_type only (no brand name)
                    static = _keyword_research_seed(bt, "", snippet)
                    if static:
                        seeds = [static]
                    logger.info("[seo] Using static VebAPI seed: %r", seeds)

                seen_texts: set[str] = set(already_saved)
                for i, seed in enumerate(seeds):
                    if i > 0:
                        await _asyncio.sleep(0.5)  # brief pause between VebAPI calls
                    try:
                        veb_data = await _veb_get("/seo/keywordresearch", {"keyword": seed, "country": country_code})
                        raw_kws = veb_data if isinstance(veb_data, list) else veb_data.get("keywords", [])
                        added = 0
                        for kw in raw_kws:
                            text = str(kw.get("text") or "").strip()
                            if not text or text.lower() in seen_texts:
                                continue
                            seen_texts.add(text.lower())
                            vol = _parse_vol(kw.get("vol"))
                            diff = _comp_to_difficulty(kw.get("competition"))
                            pri = 5 if vol >= 10000 else 4 if vol >= 2000 else 3 if vol >= 500 else 2 if vol >= 50 else 1
                            keywords.append({
                                "keyword": text,
                                "search_volume": vol if vol else None,
                                "difficulty": diff,
                                "intent": "informational",
                                "priority": pri,
                                "content_idea": f"Write about '{text}'" + (f" (~{vol:,} searches/mo)" if vol else ""),
                                "strategy_type": "informational",
                                "cpc": kw.get("cpc"),
                            })
                            added += 1
                        logger.info("[seo] VebAPI seed=%r → %d keywords", seed, added)
                    except Exception as e:
                        logger.warning("[seo] VebAPI call failed for seed=%r: %s", seed, e)

                if keywords:
                    keyword_source = "vebapi"
                    logger.info("[seo] VebAPI total keywords merged: %d", len(keywords))
            except Exception as e:
                logger.warning("[seo] VebAPI keyword fallback skipped: %s", e)

        # ── AI fallback: last resort, no real volumes ─────────────────────────
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

        # Strip any bracketed instructions the user may have typed into the topic field
        clean_topic = re.sub(r'\[.*?\]', '', payload.topic).strip()

        word_targets = {"short": "400-500", "medium": "800-1000", "long": "1400-1600"}
        word_target = word_targets.get(payload.length, "800-1000")
        keywords_str = ", ".join(payload.keywords) if payload.keywords else clean_topic
        business_str = f" for {biz_name}" if biz_name else ""

        context_block = ""
        if snippet:
            context_block = f"""

Business context (stay accurate to what they offer):
{snippet[:1400]}
"""

        faq_instruction = """
After the main content, add a FAQ section with 4-5 questions. Format each answer as a self-contained 40-60 word paragraph — written so an AI (ChatGPT, Perplexity, Google AI Overview) can lift it verbatim as a featured snippet answer. Each answer must stand alone without reading the rest of the article.""" if payload.include_faq else ""

        existing_titles_block = ""
        if payload.existing_titles:
            titles_list = "\n".join(f"  - {t}" for t in payload.existing_titles)
            existing_titles_block = f"""
ALREADY PUBLISHED — DO NOT repeat these angles or titles:
{titles_list}
Write from a completely different angle that the above posts do not cover.
"""

        prompt = f"""You are an expert writer and journalist — not an AI assistant. You write the way experienced columnists do: specific, opinionated, grounded in real detail.

ASSIGNMENT:
Business: {biz_name or "a local business"}
Topic: {clean_topic}
Keywords: {keywords_str}
Tone: {payload.tone} | Language: {lang} | Length: {word_target} words
{context_block}{existing_titles_block}
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

━━━ STEP 3 — AI SEARCH OPTIMISATION (AEO) ━━━
AI search engines (Google AI Overviews, ChatGPT, Perplexity) now appear in nearly half of all searches. Your article must be structured so AI can extract and cite it. Apply ALL of these:

STRUCTURE — make content extractable:
- First H2 section: open with a 40-60 word definition paragraph for the main topic. Written so an AI can lift it as a complete answer. Example format: "[Topic] is [what it is]. It works by [how]. Businesses use it to [outcome]. The key benefit is [specific result]."
- Use H2s that are complete questions or statements an AI would index: "What is X", "How to X", "X vs Y", "Why X matters for Y"
- Include at least one comparison table (markdown format) where it makes sense — comparisons are highly cited by AI systems
- Each section's first sentence must be a standalone, complete thought — not "As we mentioned above..."

AUTHORITY — make content citable (proven to increase AI visibility):
- Include at least 2 specific statistics or data points. Use real industry numbers if you know them; if not, cite a plausible range with a source name (e.g. "According to HubSpot research..." or "Industry data shows..."). Statistics increase AI citation by ~37%.
- Include at least one expert-style quotation or insight — either a real quote from an industry source or framed as practitioner wisdom. Expert citations increase AI visibility by ~30%.
- Mention a publish or update date context: write "As of [current year]..." at least once to signal freshness.

NEVER do this (actively hurts AI visibility):
- Keyword stuffing — use the target keyword naturally, not forced into every paragraph
- Vague hedging: "some experts say", "it could be argued", "many people think" — be direct and cite specifically

━━━ STEP 4 — WRITE THE ARTICLE ━━━
- Your chosen opening IS the first paragraph. Start there, not with background context.
- Write like you're talking to one specific person, not addressing a crowd.
- Short sentences. Mix them with longer ones. Never three long sentences in a row.
- Use contractions naturally: don't, it's, you'll, we've, I've.
- Specific beats vague every time: "costs around Ksh 15,000 in Nairobi" beats "can be expensive".
- Name actual places, typical prices, real situations your reader would recognise.
- Each H2 section answers a question the reader is actually thinking.
- Conclusion: one specific action to take next — not "contact us for more info". Use this formula: [Action verb] + [what they get] + [why now]. Example: "Start tracking your top 5 keywords this week — the businesses ranking on page one started 6 months ago."
{(' - FAQ: 4-5 questions a real person would actually search for, each answer 40-60 words, self-contained.' if payload.include_faq else '')}

AUTOMATIC FAIL — if your article contains any of these, rewrite before submitting:
✗ "In today's [adjective] world..."
✗ "In this article, we will..." / "Let's explore..." / "Let's dive into..."
✗ "Are you looking for..."
✗ "[Topic] is an important/essential/crucial aspect of..."
✗ "In conclusion..." / "To summarize..." / "As we've seen..."
✗ Starting any sentence with "Additionally," "Furthermore," "Moreover," "Notably," "Importantly,"
✗ Starting with a sycophantic opener: "Great question", "Absolutely", "Of course", "Certainly"

BANNED WORDS — never use these, they are AI tells that trained readers spot instantly:
✗ Single words: delve, realm, tapestry, beacon, testament, profound, pivotal, groundbreaking, paramount, elevate, foster, synergy, holistic, robust, multifaceted, underscores, signifies, embodies, bustling, vibrant, ever-evolving, landscape (used metaphorically), unleash, spearhead, interplay, nuanced, granular, seamlessly, leverage, revolutionize, transformative, cutting-edge, innovative, streamline, harness, unlock
✗ Phrases: "it goes without saying", "look no further", "it's worth noting", "it is important to note", "needless to say", "at the end of the day", "the bottom line is", "stands as a testament to", "serves as a reminder", "proves to be", "it is worth mentioning", "in the ever-changing", "fast-paced world", "in today's competitive", "game-changer", "harness the power of", "by embracing", "can thrive", "can achieve success"
✗ Hyphenated pairs: ever-changing, fast-paced, cutting-edge, game-changing, ever-growing, wide-ranging, far-reaching, long-standing, well-established, high-quality (unless quoting a price)

STYLE RULES:
✗ No em dashes (—) more than once per article — they are an AI signature
✗ No bolding random mid-sentence phrases — only bold a term if you'd circle it in red pen on a printout
✗ No "inline headers": **Benefits:** followed by a colon and then content on the same line
✗ No title-casing headings: write "How to choose a plumber" not "How To Choose A Plumber"
✗ Don't list things in threes constantly — it signals AI-generated structure
✗ No generic positive conclusion: "By embracing X, businesses can achieve Y" — end with a specific action or provocation instead
✗ Passive voice more than once per section
✗ Three-word adjective stacks: "innovative AI-powered solution", "comprehensive end-to-end platform"
✗ Vague closing CTA like "contact us today" or "learn more" — use the [Action] + [Benefit] + [Urgency] formula instead

After the article write:
META_TITLE: [50-60 chars — reads like a headline, not a label]
META_DESC: [140-160 chars — one specific benefit + location]
TAGS: [5 tags]

Now write the article — starting directly with your chosen opening line:"""

        raw = await _call_ai(prompt, max_tokens=3500)

        # ── Humanizer pass (borrowed from blader/humanizer) ─────────────────
        # Separate content from META lines before the audit so we don't lose them
        _meta_block = "\n".join(
            ln for ln in raw.splitlines()
            if re.match(r"\*{0,2}(META_TITLE|META_DESC|TAGS)\*{0,2}:", ln.strip())
        )
        _content_only = re.sub(r"(?m)^\*{0,2}(META_TITLE|META_DESC|TAGS)\*{0,2}:[^\n]*\n?", "", raw).strip()
        try:
            humanize_prompt = f"""Read this blog article carefully.

{_content_only}

---
List (briefly, 3-5 bullets) what still reads as obviously AI-generated — specific phrases, patterns, or sentences that a human writer would not use. Then rewrite the FULL article fixing every one of those issues. Output ONLY the rewritten article, nothing else. Preserve all markdown formatting (headings, lists, tables)."""
            raw = await _call_ai(humanize_prompt, max_tokens=3500)
            # Re-attach meta lines so downstream parsing still works
            if _meta_block:
                raw = raw.rstrip() + "\n\n" + _meta_block
        except Exception:
            pass  # If humanize pass fails, use original draft

        # Extract meta fields from the end of the response
        meta_title = ""
        meta_desc = ""
        tags: List[str] = []

        meta_title_match = re.search(r"\*{0,2}META_TITLE\*{0,2}:\s*(.+)", raw)
        meta_desc_match = re.search(r"\*{0,2}META_DESC\*{0,2}:\s*(.+)", raw)
        tags_match = re.search(r"\*{0,2}TAGS\*{0,2}:\s*(.+)", raw)

        if meta_title_match: meta_title = re.sub(r'\*+', '', meta_title_match.group(1)).strip()
        if meta_desc_match: meta_desc = re.sub(r'\*+', '', meta_desc_match.group(1)).strip()
        if tags_match: tags = [re.sub(r'\*+', '', t).strip() for t in tags_match.group(1).split(",")]

        # Strip all META_TITLE / META_DESC / TAGS lines from content (handle ** wrapping and start-of-string)
        content = re.sub(r"(?m)^\*{0,2}(META_TITLE|META_DESC|TAGS)\*{0,2}:[^\n]*\n?", "", raw).strip()

        # Extract title from first H1
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else clean_topic

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

    @router.post("/blog/posts/{post_id}/share-social")
    async def share_blog_to_social(post_id: str, payload: dict, user=user_dep):
        """Share a blog post to a connected social account via Zernio and record the share."""
        tid = _tid(user)
        doc = await db.seo_blog_posts.find_one({"_id": post_id, "user_id": tid})
        if not doc:
            raise HTTPException(404, "Post not found")

        platform   = (payload.get("platform") or "").strip()
        account_id = (payload.get("account_id") or "").strip()
        caption    = (payload.get("caption") or "").strip()
        link_url   = (payload.get("link_url") or "").strip()
        image_url  = (payload.get("image_url") or "").strip()

        if not (platform and account_id and caption):
            raise HTTPException(400, "platform, account_id, and caption are required")

        user_doc = await db.users.find_one({"_id": tid}, {"zernio_profile_id": 1})
        profile_id = (user_doc or {}).get("zernio_profile_id") if user_doc else None
        if not profile_id:
            raise HTTPException(400, "No Zernio profile found — connect a social account first in Integrations")

        try:
            from zernio.routes import _post as _zpost
            post_body: Dict[str, Any] = {
                "profileId": profile_id,
                "platform": platform,
                "accountId": account_id,
                "message": caption,
            }
            if link_url:
                post_body["link"] = link_url
            if image_url:
                post_body["imageUrl"] = image_url
            result = await _zpost("/posts", post_body)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"Failed to post to {platform}: {e}")

        social_post_id = str(
            result.get("post_id") or result.get("id") or result.get("_id") or ""
        )
        share_ref = {
            "platform": platform,
            "account_id": account_id,
            "social_post_id": social_post_id,
            "caption": caption,
            "link_url": link_url,
            "shared_at": datetime.utcnow().isoformat(),
        }
        await db.seo_blog_posts.update_one(
            {"_id": post_id, "user_id": tid},
            {"$push": {"social_shares": share_ref}, "$set": {"updated_at": datetime.utcnow()}}
        )
        try:
            await _record_event("blog_shared_social", {"post_id": post_id, "platform": platform}, user)
        except Exception:
            pass
        return {"ok": True, "social_post_id": social_post_id, "platform": platform}

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

    @router.post("/blog/schedule-batch")
    async def schedule_calendar_batch(payload: dict, user=user_dep):
        """Batch-create or update posts as 'scheduled' from calendar topics.
        Payload: { items: [{ title, keywords, scheduled_at, topic?, week?, day? }] }
        If a draft with matching title already exists it is updated to scheduled;
        otherwise a placeholder scheduled post is created.
        """
        tid = _tid(user)
        items = payload.get("items") or []
        results = []
        for item in items[:50]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            scheduled_at = item.get("scheduled_at") or ""
            keywords = item.get("keywords") or []
            topic = item.get("topic") or title
            week = item.get("week")
            day = item.get("day") or ""

            # Try to find an existing draft with matching title (created by generate-drafts)
            existing = await db.seo_blog_posts.find_one(
                {"user_id": tid, "title": title, "status": "draft"}
            )
            if existing:
                await db.seo_blog_posts.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        "status": "scheduled",
                        "scheduled_at": scheduled_at,
                        "updated_at": datetime.utcnow(),
                    }},
                )
                results.append({"post_id": existing["_id"], "title": title, "action": "updated"})
            else:
                doc = {
                    "_id": str(uuid.uuid4()),
                    "user_id": tid,
                    "title": title,
                    "content": "",
                    "meta_title": "",
                    "meta_description": "",
                    "keywords": keywords,
                    "tags": [],
                    "status": "scheduled",
                    "scheduled_at": scheduled_at,
                    "platform": "internal",
                    "calendar_week": week,
                    "calendar_day": day,
                    "calendar_topic": topic,
                    "calendar_keywords": keywords,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
                await db.seo_blog_posts.insert_one(doc)
                results.append({"post_id": doc["_id"], "title": title, "action": "created"})

        return {"ok": True, "scheduled": len(results), "results": results}

    # ── Auto-Share helper ────────────────────────────────────────────────────

    async def _auto_share_if_enabled(db, user, post_id: str, doc: dict, live_url: str, trigger: str):
        """Post to all configured social accounts if auto-share is enabled for this trigger."""
        tid = _tid(user)
        user_doc = await db.users.find_one({"_id": tid}, {"seo_auto_share": 1, "zernio_profile_id": 1})
        if not user_doc:
            return
        settings = user_doc.get("seo_auto_share") or {}
        if not settings.get("enabled"):
            return
        setting_trigger = settings.get("trigger", "published")
        if setting_trigger != "both" and setting_trigger != trigger:
            return
        account_ids: List[str] = settings.get("account_ids") or []
        account_platforms: Dict[str, str] = settings.get("account_platforms") or {}
        if not account_ids:
            return
        profile_id = user_doc.get("zernio_profile_id")
        if not profile_id:
            return

        # Build caption from post content
        title = doc.get("title", "")
        content = doc.get("content", "")
        clean = re.sub(r"<[^>]+>", "", content).strip()
        intro = clean[:240].strip()
        if len(clean) > 240:
            intro += "…"
        link_str = f"\n\n🔗 {live_url}" if live_url else ""
        caption = f"{title}\n\n{intro}{link_str}"

        try:
            from zernio.routes import _post as _zpost
        except Exception as _e:
            logger.warning("[seo/auto-share] Could not import zernio._post: %s", _e)
            return

        share_refs = []
        for acc_id in account_ids:
            platform = account_platforms.get(acc_id, "")
            if not platform:
                continue
            try:
                body: Dict[str, Any] = {
                    "profileId": profile_id,
                    "platform": platform,
                    "accountId": acc_id,
                    "message": caption,
                }
                if live_url:
                    body["link"] = live_url
                if doc.get("image_url"):
                    body["imageUrl"] = doc["image_url"]
                result_z = await _zpost("/posts", body)
                social_post_id = str(result_z.get("post_id") or result_z.get("id") or result_z.get("_id") or "")
                share_refs.append({
                    "platform": platform,
                    "account_id": acc_id,
                    "social_post_id": social_post_id,
                    "caption": caption,
                    "link_url": live_url,
                    "shared_at": datetime.utcnow().isoformat(),
                    "auto": True,
                })
                logger.info("[seo/auto-share] Posted to %s account %s for post %s", platform, acc_id, post_id)
            except Exception as _e:
                logger.warning("[seo/auto-share] Failed to post to %s/%s: %s", platform, acc_id, _e)

        if share_refs:
            await db.seo_blog_posts.update_one(
                {"_id": post_id},
                {"$push": {"social_shares": {"$each": share_refs}}}
            )

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

                # Resolve category from template_id (non-blocking)
                template_id = doc.get("template_id", "")
                cat_name = _TEMPLATE_CATEGORIES.get(template_id, "Blog")
                category_id = await _wp_get_or_create_category(payload.wp_url, creds, cat_name)

                # Generate & upload a relevant featured image (non-blocking)
                featured_media_id: "int | None" = None
                try:
                    from nano_banana_service import generate_creative_image
                    tags = doc.get("tags") or []
                    topic_hint = tags[0] if tags else doc.get("title", "")
                    img_prompt = (
                        f"PHOTOGRAPHY BRIEF — blog featured image\n"
                        f"Blog post title: {doc.get('title', '')}\n"
                        f"Topic: {topic_hint}\n"
                        f"Shoot: a real, plausible scene directly related to the topic. "
                        f"Natural lighting, eye-level angle, shallow depth of field. "
                        f"No text overlays, no logos, no surreal effects."
                    )
                    img_result = await generate_creative_image(prompt=img_prompt, format="landscape", quality="pro")
                    if img_result.get("image_url"):
                        slug = re.sub(r"[^a-z0-9]+", "-", doc.get("title", "post").lower())[:40]
                        featured_media_id = await _wp_upload_image(payload.wp_url, creds, img_result["image_url"], f"{slug}.png")
                except Exception as _img_exc:
                    logger.warning("[seo/publish] Image generation skipped: %s", _img_exc)

                wp_payload: Dict[str, Any] = {
                    "title": doc.get("title", ""),
                    "content": _markdown_to_html(doc.get("content", "")),
                    "status": "publish",
                    "meta": {
                        "_yoast_wpseo_title": doc.get("meta_title", ""),
                        "_yoast_wpseo_metadesc": doc.get("meta_description", ""),
                    },
                }
                if category_id:
                    wp_payload["categories"] = [category_id]
                if featured_media_id:
                    wp_payload["featured_media"] = featured_media_id

                async with httpx.AsyncClient(timeout=30) as hc:
                    resp = await hc.post(
                        f"{payload.wp_url.rstrip('/')}/wp-json/wp/v2/posts",
                        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
                        json=wp_payload,
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
                        json={"article": {"title": doc.get("title", ""), "body_html": _markdown_to_html(doc.get("content", "")), "published": True}},
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
            live_url = result.get("post_url") or result.get("article_url") or ""
            await db.seo_blog_posts.update_one(
                {"_id": payload.post_id},
                {"$set": {"status": "published", "published_at": datetime.utcnow(), "publish_result": result,
                           "site_post_url": live_url or None}},
            )
            await _record_event("post_published", {"post_id": payload.post_id, "platform": payload.platform, "publish_result": result}, user)

            # ── Auto-share to social if enabled ──────────────────────────────
            try:
                await _auto_share_if_enabled(db, user, payload.post_id, doc, live_url, trigger="published")
            except Exception as _as_exc:
                logger.warning("[seo/auto-share] Error during auto-share: %s", _as_exc)

        return result

    # ── Auto-Share Settings ──────────────────────────────────────────────────

    @router.get("/social-auto-share/settings")
    async def get_auto_share_settings(user=user_dep):
        """Return the user's social auto-share settings."""
        tid = _tid(user)
        user_doc = await db.users.find_one({"_id": tid}, {"seo_auto_share": 1})
        defaults = {"enabled": False, "trigger": "published", "account_ids": [], "account_platforms": {}}
        saved = (user_doc or {}).get("seo_auto_share") or {}
        return {**defaults, **saved}

    @router.put("/social-auto-share/settings")
    async def update_auto_share_settings(payload: dict, user=user_dep):
        """Save the user's social auto-share settings."""
        tid = _tid(user)
        allowed = {"enabled", "trigger", "account_ids", "account_platforms"}
        clean = {k: v for k, v in (payload or {}).items() if k in allowed}
        await db.users.update_one({"_id": tid}, {"$set": {"seo_auto_share": clean}}, upsert=True)
        return {"ok": True, "settings": clean}

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

        # ── Pull tracked keywords from Rankings (primary content source) ─────
        ranking_entries = await db.seo_serp_rankings.find(
            {"user_id": tid}
        ).sort("checked_at", -1).to_list(500)

        # Deduplicate to latest entry per keyword
        seen_kws: set = set()
        tracked_keywords: List[dict] = []
        for entry in ranking_entries:
            kw = (entry.get("keyword") or "").strip()
            if kw and kw.lower() not in seen_kws:
                seen_kws.add(kw.lower())
                tracked_keywords.append({
                    "keyword": kw,
                    "search_volume": entry.get("search_volume"),
                    "global_search_volume": entry.get("global_search_volume"),
                    "difficulty": entry.get("difficulty"),
                    "trend": entry.get("trend"),
                    "content_idea": entry.get("content_idea"),
                    "top_region": entry.get("top_region"),
                })

        # Topics already written — avoid repeats
        existing_titles = [p.get("title", "") for p in past_posts if p.get("title")]

        # Audit issues to address in new content
        audit_issues: List[str] = []
        if last_audit:
            for iss in (last_audit.get("issues") or [])[:5]:
                f = iss.get("field", "")
                if f and iss.get("type") in ("critical", "warning"):
                    audit_issues.append(f)

        # Fallback: saved keywords if no rankings yet
        saved_keywords: List[str] = []
        if not tracked_keywords and saved_kw:
            for k in (saved_kw.get("keywords") or [])[:10]:
                kw = k.get("keyword", "") if isinstance(k, dict) else str(k)
                if kw:
                    saved_keywords.append(kw)

        # Published vs draft counts
        pub_count = sum(1 for p in past_posts if p.get("status") == "published")
        draft_count = sum(1 for p in past_posts if p.get("status") == "draft")

        # Build memory block for the prompt
        memory_block = ""
        if tracked_keywords:
            kw_lines = []
            for k in tracked_keywords[:20]:
                line = f"  - \"{k['keyword']}\""
                parts = []
                vol = k.get("global_search_volume") or k.get("search_volume")
                if vol: parts.append(f"{vol:,}/mo global")
                if k.get("difficulty"): parts.append(f"difficulty: {k['difficulty']}")
                if k.get("trend"): parts.append(f"trend: {k['trend']}")
                if k.get("top_region"): parts.append(f"top market: {k['top_region']}")
                if k.get("content_idea"): parts.append(f"idea: {k['content_idea']}")
                if parts: line += f" ({', '.join(parts)})"
                kw_lines.append(line)
            memory_block += f"\nTRACKED KEYWORDS (build every post around one of these — this is what the business is trying to rank for):\n" + "\n".join(kw_lines) + "\n"
            memory_block += f"\nEach week's posts MUST target different keywords from the list above. Distribute them so all {len(tracked_keywords[:total])} keywords are covered across the {weeks} weeks.\n"
        elif saved_keywords:
            memory_block += f"\nKeywords to incorporate: {', '.join(saved_keywords)}\n"
        if existing_titles:
            titles_str = "\n".join(f"  - {t}" for t in existing_titles[:15])
            memory_block += f"\nAlready written (DO NOT repeat — find fresh angles):\n{titles_str}\n"
        if audit_issues:
            memory_block += f"\nSEO issues to address through content: {', '.join(audit_issues)}\n"
        if pub_count > 0 or draft_count > 0:
            memory_block += f"\nContent history: {pub_count} published, {draft_count} drafts. Go deeper on high-traffic topics and fill gaps.\n"

        extra = ""
        if snippet:
            extra = f"\nBusiness context (align topics with real offerings):\n{snippet[:1000]}\n"

        ranking_note = (
            f"This calendar is built around {len(tracked_keywords)} tracked keywords the business wants to rank for."
            if tracked_keywords else
            f"No ranked keywords found — generate topics based on the business type and location."
        )

        prompt = f"""Create a {weeks}-week content calendar for a {bt} business{location_str}.
Generate exactly {total} blog post ideas ({posts_per_week} per week).

{ranking_note}
{memory_block}{extra}
Title rules — every title must:
- Be punchy and specific like a magazine headline ("5 Ways to...", "How to...", "Why...", "The Truth About...")
- Directly target one of the tracked keywords above (include the keyword naturally in the title)
- Be unique — do NOT repeat any already-written title above
- Use different formats across weeks: listicle / how-to / comparison / guide / case study / question

Distribution rules:
- Spread tracked keywords evenly across all {weeks} weeks
- Week 1: highest-volume or rising-trend keywords first
- Later weeks: go deeper with long-tail angles on the same keywords
- Mix intent: informational, transactional, local across each week

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {{
    "week": 1,
    "day": "Monday",
    "title": "Full punchy blog post title targeting the keyword",
    "topic": "one sentence: what angle this post takes",
    "keywords": ["primary keyword", "secondary keyword"],
    "intent": "informational|transactional|local",
    "estimated_traffic": "low|medium|high"
  }}
]"""

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
            prompt = f"""Write a {word_target}-word blog post{business_str}. Tone: {payload.tone}. Language: {lang}.

Topic: {topic}
Target keywords: {keywords_str}
{context_block}
WRITING RULES:
- Open with a scene, surprising fact, or direct question — never "In today's world..." or "Are you looking for..."
- Use contractions (don't, it's, you'll). Short sentences mixed with longer ones.
- Specific beats vague: real numbers, places, prices over generic claims.
- H2 headings must be questions or complete statements an AI system can index.

AEO (AI SEARCH) RULES — AI search now appears in ~45% of searches:
- Second paragraph: include a 40-60 word definition of the main topic, written so an AI can use it as a standalone answer.
- Include at least 2 statistics or data points with a source name.
- Include at least one comparison table (markdown) where relevant.
- Each section's first sentence must be a complete standalone thought.

BANNED WORDS — do not use: streamline, leverage, innovative, seamlessly, revolutionize, dive into, delve into, cutting-edge, transformative, game-changer, it's worth noting, needless to say

Structure: H1 → strong opening → AEO definition paragraph → H2 sections → conclusion with [Action] + [Benefit] + [Urgency] CTA → FAQ (4 questions, each answer 40-60 words, self-contained).

After the article write:
META_TITLE: [50-60 char — reads like a headline]
META_DESC: [140-160 char — one specific benefit]
TAGS: [comma-separated tags]

Write the full article now:"""

            try:
                raw = await _call_ai(prompt, max_tokens=2500)
                meta_title = ""
                meta_desc  = ""
                tags: List[str] = []
                mt = re.search(r"\*{0,2}META_TITLE\*{0,2}:\s*(.+)", raw)
                md = re.search(r"\*{0,2}META_DESC\*{0,2}:\s*(.+)", raw)
                tg = re.search(r"\*{0,2}TAGS\*{0,2}:\s*(.+)", raw)
                if mt: meta_title = re.sub(r'\*+', '', mt.group(1)).strip()
                if md: meta_desc  = re.sub(r'\*+', '', md.group(1)).strip()
                if tg: tags = [re.sub(r'\*+', '', t).strip() for t in tg.group(1).split(",")]
                content = re.sub(r"(?m)^\*{0,2}(META_TITLE|META_DESC|TAGS)\*{0,2}:[^\n]*\n?", "", raw).strip()
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

        # SEO write-post counts (seo_blog_posts collection)
        seo_total    = await db.seo_blog_posts.count_documents({"user_id": tid})
        seo_published = await db.seo_blog_posts.count_documents({"user_id": tid, "status": "published"})
        seo_drafts   = await db.seo_blog_posts.count_documents({"user_id": tid, "status": "draft"})
        seo_scheduled = await db.seo_blog_posts.count_documents({"user_id": tid, "status": "scheduled"})

        # Autoblog posts (posts_log collection — published by the scheduler/manual trigger)
        autoblog_published = await db.posts_log.count_documents({"client_id": tid})

        # Combined totals
        total_published = seo_published + autoblog_published
        total_posts     = seo_total + autoblog_published  # seo_total already includes published

        # Audits
        total_audits = await db.seo_audits.count_documents({"user_id": tid})

        # Keywords saved (total across all months)
        all_kw_docs = await db.seo_saved_keywords.find({"user_id": tid}).to_list(200)
        keywords_saved = sum(len(doc.get("keywords", [])) for doc in all_kw_docs)

        # Rankings tracked
        rankings_count = await db.seo_rankings.count_documents({"user_id": tid}) if hasattr(db, "seo_rankings") else 0
        try:
            rankings_count = await db.seo_rankings.count_documents({"user_id": tid})
        except Exception:
            rankings_count = 0

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
            "total_posts":      total_posts,
            "published_posts":  total_published,
            "draft_posts":      seo_drafts,
            "scheduled_posts":  seo_scheduled,
            "autoblog_posts":   autoblog_published,
            "keywords_saved":   keywords_saved,
            "rankings_tracked": rankings_count,
            "total_audits":     total_audits,
            "avg_seo_score":    avg_score,
            "last_audit":       _ser(last_audit) if last_audit else None,
            "audit_trend":      audit_trend,
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
        """Return AI-generated local keywords based on the user's business profile."""
        tid = _tid(user)
        ctx = _seo_business_context(user)
        raw_location = ctx.get("location", "").strip()
        # Treat placeholder/default values as "no location set"
        _no_location = {"your city", "city", "location", "", "not specified", "not set", "n/a", "none"}
        has_location = raw_location.lower() not in _no_location
        location = raw_location if has_location else "Worldwide"
        business_type = ctx.get("business_type", "business")
        business_name = ctx.get("business_name", "")
        snippet = ctx.get("context_snippet", "")
        city = location.split(",")[0].strip() if has_location else ""

        if has_location:
            location_instruction = (
                f"- City + service combinations using '{city}' (real city name, no placeholders)\n"
                f"- Question-based local searches like 'where to find X in {city}'"
            )
        else:
            location_instruction = (
                "- Online/worldwide searches (no city — do NOT use '[City]', '[Location]' or any placeholder)\n"
                "- Use 'near me', 'online', or 'worldwide' for location-based variants"
            )

        prompt = f"""You are a local SEO expert. Generate 12 highly targeted search keywords for this business.

Business: {business_name or business_type}
Type: {business_type}
Location: {location if has_location else "Not specified — treat as a worldwide/online business"}
Products/Services: {snippet[:600] if snippet else 'Not specified'}

Generate 12 keywords a potential customer would type into Google to find this business.
IMPORTANT: Never use placeholder text like [City], [Location], or [Place]. Use real words only.
Cover a mix of:
- "near me" searches
- "best", "affordable", "top" modifier searches
- Specific service/product keywords
- {location_instruction}

Return ONLY a JSON array, no explanation:
[
  {{"keyword": "exact search phrase", "difficulty": "low|medium|high", "content_idea": "specific blog/page title to rank for this"}}
]"""

        import json as _json
        try:
            raw = await _call_ai(prompt, max_tokens=900)
            raw = raw.strip()
            if raw.startswith("```"): raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
            ai_keywords = _json.loads(raw)
            keywords = [
                {
                    # Strip any leftover [City] / [Location] placeholders the AI ignored
                    "keyword": re.sub(r'\[(?:City|Location|Place|Your City)[^\]]*\]', 'online', str(kw.get("keyword", ""))).strip(),
                    "location": location,
                    "difficulty": str(kw.get("difficulty", "medium")),
                    "content_idea": re.sub(r'\[(?:City|Location|Place|Your City)[^\]]*\]', location if has_location else 'online', str(kw.get("content_idea", ""))).strip(),
                    "note": "ai-generated",
                }
                for kw in ai_keywords if kw.get("keyword")
            ]
        except Exception:
            # Fallback to enriched templates if AI fails
            loc_suffix = f" in {city}" if city else " online"
            loc_label = city if city else "online"
            keywords = [
                {"keyword": f"{business_type} near me", "location": location, "difficulty": "high", "content_idea": f"Why {business_name or business_type} Is the Best Choice Near You", "note": "suggested"},
                {"keyword": f"{business_type}{loc_suffix}", "location": location, "difficulty": "medium", "content_idea": f"Top {business_type} Services {loc_label.title()}", "note": "suggested"},
                {"keyword": f"best {business_type} {loc_label}", "location": location, "difficulty": "medium", "content_idea": f"Best {business_type} {loc_label.title()}: What to Look For", "note": "suggested"},
                {"keyword": f"affordable {business_type} {loc_label}", "location": location, "difficulty": "low", "content_idea": f"Affordable {business_type} Options {loc_label.title()}", "note": "suggested"},
                {"keyword": f"{business_type} services{loc_suffix}", "location": location, "difficulty": "medium", "content_idea": f"Complete Guide to {business_type} Services {loc_label.title()}", "note": "suggested"},
                {"keyword": f"top {business_type} {loc_label}", "location": location, "difficulty": "medium", "content_idea": f"Top-Rated {business_type} Providers {loc_label.title()}", "note": "suggested"},
                {"keyword": f"{business_type} {loc_label} reviews", "location": location, "difficulty": "low", "content_idea": f"What Customers Say About Our {business_type} {loc_label.title()}", "note": "suggested"},
                {"keyword": f"how to find {business_type}{loc_suffix}", "location": location, "difficulty": "low", "content_idea": f"How to Find the Right {business_type} {loc_label.title()}", "note": "suggested"},
            ]
        # ── Enrich with real search volumes (DataForSEO) ─────────────────────
        import os as _os
        from seo.dataforseo import (
            dfs_enabled, fetch_search_volumes_batch,
            resolve_location_code, language_code_from_settings,
        )

        settings = user.get("settings") or {}
        country = str(settings.get("country") or "")
        country_code = str(settings.get("country_code") or user.get("country_code") or "")
        primary_language = str(settings.get("primary_language") or "English")
        loc_code = resolve_location_code(country, country_code)
        lang_code = language_code_from_settings(primary_language)

        if dfs_enabled():
            try:
                import re as _re_vol
                kw_list = [k["keyword"] for k in keywords]

                # First pass: look up exact keywords
                vol_map = await fetch_search_volumes_batch(kw_list, location_code=loc_code, language_code=lang_code)

                # For keywords that returned 0, also try global (no location filter) —
                # local phrases often have 0 in regional data but non-zero globally
                zero_kws = [k for k in kw_list if not vol_map.get(k.lower().strip())]
                if zero_kws:
                    global_map = await fetch_search_volumes_batch(zero_kws, location_code=None, language_code=lang_code)
                    for kw in zero_kws:
                        gv = global_map.get(kw.lower().strip(), 0)
                        if gv:
                            vol_map[kw.lower().strip()] = gv

                # For still-zero keywords, strip location modifiers and look up the base phrase —
                # "best dentist near me in nairobi" → "dentist" → real volume
                _loc_patterns = _re_vol.compile(
                    r'\b(near me|in \w+|best|top|affordable|cheap|local|'
                    r'services?|provider|near|around|close to)\b', _re_vol.I
                )
                still_zero = [k for k in kw_list if not vol_map.get(k.lower().strip())]
                if still_zero:
                    base_map: dict[str, str] = {}  # base_kw → original_kw
                    for kw in still_zero:
                        base = _loc_patterns.sub("", kw).strip()
                        base = _re_vol.sub(r'\s{2,}', ' ', base).strip()
                        if base and base.lower() != kw.lower():
                            base_map[base] = kw
                    if base_map:
                        base_vol = await fetch_search_volumes_batch(list(base_map.keys()), location_code=loc_code, language_code=lang_code)
                        for base, orig in base_map.items():
                            bv = base_vol.get(base.lower().strip(), 0)
                            if bv:
                                vol_map[orig.lower().strip()] = bv

                for k in keywords:
                    k["search_volume"] = vol_map.get(k["keyword"].lower().strip()) or 0
                logger.info("[local/keywords] volumes: %d/%d keywords have data",
                            sum(1 for k in keywords if k.get("search_volume")), len(keywords))
            except Exception as _ve:
                logger.warning("[local/keywords] DataForSEO volume fetch failed: %s", _ve)

        # ── Enrich with tracked SERP positions ───────────────────────────────
        serp_rows = await db.seo_serp_rankings.find(
            {"user_id": tid}
        ).sort("checked_at", -1).to_list(2000)

        # Build: keyword_lower → [positions sorted newest-first]
        pos_history: dict[str, list[int | None]] = {}
        for row in serp_rows:
            kw_key = (row.get("keyword") or "").lower().strip()
            pos = row.get("position")
            if kw_key:
                pos_history.setdefault(kw_key, []).append(pos)

        for k in keywords:
            kw_key = k["keyword"].lower().strip()
            history = pos_history.get(kw_key, [])
            latest = next((p for p in history if p is not None), None)
            k["position"] = latest  # None = not tracked yet

            # Trend: compare latest vs previous non-null position
            non_null = [p for p in history if p is not None]
            if len(non_null) >= 2:
                diff = non_null[0] - non_null[1]  # negative = moved up (improved)
                k["trend"] = "up" if diff < 0 else ("down" if diff > 0 else "stable")
            else:
                k["trend"] = "new" if latest is not None else "untracked"

        return {"keywords": keywords, "source": "ai_generated"}

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
        location = ctx.get("location", "your area")
        city = location.split(",")[0].strip() or location
        biz_name = ctx.get("business_name", "") or ctx.get("business_type", "your business")
        biz_type = ctx.get("business_type", "business")

        # Which platforms are already listed?
        saved_docs = await db.local_seo_listings.find({"user_id": tid}, {"platform": 1, "status": 1}).to_list(100)
        saved_platforms = {d.get("platform", "") for d in saved_docs}
        all_platforms = ["google-business", "yelp", "apple-maps", "bing-places"]
        platform_labels = {
            "google-business": "Google Business Profile",
            "yelp": "Yelp",
            "apple-maps": "Apple Maps",
            "bing-places": "Bing Places",
        }
        missing_platforms = [platform_labels[p] for p in all_platforms if p not in saved_platforms]

        listings_score = min(100, listing_count * 25)
        verified_score = min(100, verified_count * 34)
        citations_score = min(100, len(saved_platforms) * 25)
        rankings_score = min(100, listing_count * 20)
        all_scores = [listings_score, verified_score, citations_score, rankings_score]
        overall = round(sum(all_scores) / len(all_scores)) if listing_count > 0 else 0

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
            recommendations.append(
                f"Add {biz_name} to Google Business Profile first — it's the #1 driver of local search visibility in {city}."
            )
        elif "google-business" not in saved_platforms:
            recommendations.append(
                f"Google Business Profile is missing for {biz_name}. It drives over 60% of local search clicks — add it now."
            )
        if missing_platforms:
            joined = ", ".join(missing_platforms[:3])
            recommendations.append(
                f"{biz_name} is not listed on: {joined}. Each listing adds a citation signal that boosts local rankings in {city}."
            )
        if verified_count < listing_count:
            unverified = listing_count - verified_count
            recommendations.append(
                f"{unverified} listing{'s are' if unverified > 1 else ' is'} still pending verification. "
                f"Verified listings rank significantly higher for '{biz_type} in {city}' searches."
            )
        if listing_count >= 1 and verified_count == listing_count:
            recommendations.append(
                f"All listings verified — great! Next step: ask satisfied customers to leave a Google review for {biz_name} in {city}."
            )
        recommendations.append(
            f"Publish a blog post targeting '{biz_type} in {city}' or '{biz_type} near me' to reinforce your local authority."
        )

        return {
            "overall": overall,
            "grade": grade,
            "listing_count": listing_count,
            "verified_count": verified_count,
            "breakdown": {
                "business_listings": listings_score,
                "reviews_ratings": verified_score,
                "local_rankings": rankings_score,
                "citations": citations_score,
            },
            "recommendations": recommendations,
        }

    # ── AI Visibility Audit History ───────────────────────────────────────────

    @router.get("/ai-audits")
    async def get_ai_audits(limit: int = 30, user=user_dep):
        """List AI visibility audit history from veb_ai_visibility_audit tool."""
        tid = _tid(user)
        docs = await db.seo_ai_audits.find({"user_id": tid}).sort("created_at", -1).limit(limit).to_list(limit)
        return {
            "audits": [
                {
                    "url": d.get("url", ""),
                    "ai_score": d.get("ai_score"),
                    "grade": d.get("grade", ""),
                    "issues_count": d.get("issues_count", 0),
                    "created_at": d["created_at"].isoformat() if hasattr(d.get("created_at"), "isoformat") else str(d.get("created_at", "")),
                }
                for d in docs
            ]
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
            "location_code": payload.get("location_code"),
            "language_code": payload.get("language_code", "en"),
            "checked_at": datetime.utcnow(),
            "search_volume": payload.get("search_volume"),
            "local_country": payload.get("local_country"),
            "global_search_volume": payload.get("global_search_volume"),
            "competition": payload.get("competition"),
        }
        await db.seo_serp_rankings.insert_one(doc)
        return {"success": True}

    @router.get("/serp/rankings")
    async def get_serp_rankings(keyword: str = None, domain: str = None, limit: int = 50, user=user_dep):
        """Get historical SERP ranking data with published post counts per keyword."""
        tid = _tid(user)
        query = {"user_id": tid}
        if keyword:
            query["keyword"] = keyword
        if domain:
            query["domain"] = domain

        rankings = await db.seo_serp_rankings.find(query).sort("checked_at", -1).limit(limit).to_list(limit)

        # Load content links grouped by keyword for post counts
        link_docs = await db.seo_content_links.find({"user_id": tid}).sort("published_at", -1).to_list(500)
        content_map: dict = {}
        for d in link_docs:
            key = d["keyword"].lower().strip()
            if key not in content_map:
                content_map[key] = []
            content_map[key].append({
                "title": d.get("title", ""),
                "url": d.get("url", ""),
                "published_at": d["published_at"].isoformat() if hasattr(d["published_at"], "isoformat") else str(d["published_at"]),
            })

        # Format for frontend
        formatted = []
        for r in rankings:
            kw_key = r["keyword"].lower().strip()
            formatted.append({
                "keyword": r["keyword"],
                "domain": r["domain"],
                "position": r["position"],
                "global_position": r.get("global_position"),
                "checked_at": r["checked_at"].isoformat() if hasattr(r["checked_at"], "isoformat") else str(r["checked_at"]),
                "location_code": r.get("location_code"),
                "search_volume": r.get("search_volume"),
                "local_country": r.get("local_country"),
                "global_search_volume": r.get("global_search_volume"),
                "top_region": r.get("top_region"),
                "top_region_volume": r.get("top_region_volume"),
                "cpc": r.get("cpc"),
                "difficulty": r.get("difficulty"),
                "trend": r.get("trend"),
                "content_idea": r.get("content_idea"),
                "posts": content_map.get(kw_key, []),
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
            ca = r.get("checked_at")
            if ca is None:
                continue
            if isinstance(ca, str):
                try:
                    from datetime import datetime as _dt
                    ca = _dt.fromisoformat(ca.replace("Z", "").split("+")[0])
                except Exception:
                    continue
            try:
                date_key = ca.date().isoformat()
            except Exception:
                continue
            if date_key not in trends:
                trends[date_key] = []
            trends[date_key].append(r["position"])

        # Average positions per day
        trend_data = []
        for date, positions in sorted(trends.items()):
            non_null = [p for p in positions if p is not None]
            avg_position = sum(non_null) / len(non_null) if non_null else None
            trend_data.append({
                "date": date,
                "position": avg_position,
                "checks": len(positions)
            })

        return {"trends": trend_data, "keyword": keyword, "domain": domain}

    @router.delete("/serp/rankings")
    async def delete_ranking_keyword(keyword: str, domain: str, user=user_dep):
        """Remove all ranking history for a keyword+domain pair."""
        tid = _tid(user)
        result = await db.seo_serp_rankings.delete_many({
            "user_id": tid,
            "keyword": keyword,
            "domain": domain,
        })
        return {"deleted": result.deleted_count, "keyword": keyword, "domain": domain}

    @router.post("/serp/check")
    async def check_serp_position(payload: dict, user=user_dep):
        """Check where a domain ranks for a keyword using DataForSEO SERP — saves to history."""
        from . import dataforseo as dfs
        keyword = str(payload.get("keyword") or "").strip()
        domain = str(payload.get("domain") or "").strip()
        if not keyword or not domain:
            raise HTTPException(400, "keyword and domain are required")

        settings = user.get("settings") or {}
        loc_code = dfs.resolve_location_code(
            country=str(settings.get("country") or user.get("country") or ""),
            country_code=str(settings.get("country_code") or user.get("country_code") or ""),
        )
        lang_code = dfs.language_code_from_settings(
            str(settings.get("primary_language") or "English")
        )

        tid = _tid(user)
        clean_domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/").split("/")[0]

        serp = await dfs.check_serp_position_dfs(
            keyword, clean_domain,
            location_code=loc_code,
            language_code=lang_code,
            depth=20,
        )
        found_position = serp["position"]
        global_position = serp["global_position"]
        top_results = serp["top_results"]

        doc = {
            "user_id": tid,
            "keyword": keyword,
            "domain": clean_domain,
            "position": found_position,
            "global_position": global_position,
            "location_code": loc_code,
            "language_code": lang_code,
            "search_volume": None,
            "checked_at": datetime.utcnow(),
            "source": "dataforseo",
        }
        await db.seo_serp_rankings.insert_one(doc)

        return {
            "keyword": keyword,
            "domain": clean_domain,
            "position": found_position,
            "global_position": global_position,
            "checked_at": doc["checked_at"].isoformat(),
            "top_results": top_results[:5],
            "total_results": len(top_results),
        }

    @router.post("/serp/bulk-check")
    async def bulk_check_serp(payload: dict, user=user_dep):
        """Import keywords to tracking with optional search_volume. No live SERP call — use /serp/refresh-all for positions."""
        raw_keywords: list = payload.get("keywords") or []
        domain: str = str(payload.get("domain") or "").strip()
        if not domain:
            raise HTTPException(400, "domain is required")
        if not raw_keywords:
            raise HTTPException(400, "keywords list is required")

        tid = _tid(user)
        clean_domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/").split("/")[0]

        now = datetime.utcnow()
        docs = []
        for item in raw_keywords[:50]:
            if isinstance(item, dict):
                kw = str(item.get("keyword") or "").strip()
                vol = item.get("search_volume")
            else:
                kw = str(item).strip()
                vol = None
            if not kw:
                continue
            doc: dict = {
                "user_id": tid,
                "keyword": kw,
                "domain": clean_domain,
                "position": None,
                "location_code": None,
                "language_code": "en",
                "search_volume": int(vol) if vol else None,
                "checked_at": now,
                "source": "bulk_import",
            }
            if isinstance(item, dict):
                for field in ("global_search_volume", "local_country", "top_region",
                              "top_region_volume", "cpc", "difficulty", "trend",
                              "monthly_searches", "content_idea"):
                    v = item.get(field)
                    if v is not None:
                        doc[field] = v
            docs.append(doc)

        if docs:
            await db.seo_serp_rankings.insert_many(docs)

        results = [{"keyword": d["keyword"], "position": None, "checked_at": now.isoformat()} for d in docs]
        return {"domain": clean_domain, "results": results, "checked": len(docs), "failed": 0}

    # ── Content Links (posts created per tracked keyword) ──────────────────────

    @router.post("/content-links")
    async def add_content_link(payload: dict, user=user_dep):
        """Record a blog post published for a tracked keyword."""
        tid = _tid(user)
        keyword = str(payload.get("keyword") or "").strip()
        domain = str(payload.get("domain") or "").strip().replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/").split("/")[0]
        title = str(payload.get("title") or "").strip()
        url = str(payload.get("url") or "").strip()
        if not keyword or not title:
            raise HTTPException(400, "keyword and title are required")
        doc = {
            "user_id": tid,
            "keyword": keyword,
            "domain": domain,
            "title": title,
            "url": url,
            "published_at": datetime.utcnow(),
        }
        await db.seo_content_links.insert_one(doc)
        return {"ok": True, "keyword": keyword, "title": title}

    @router.get("/content-links")
    async def get_content_links(user=user_dep):
        """Get all content links for the user, grouped by keyword."""
        tid = _tid(user)
        docs = await db.seo_content_links.find({"user_id": tid}).sort("published_at", -1).to_list(500)
        grouped: dict = {}
        for d in docs:
            key = d["keyword"].lower().strip()
            if key not in grouped:
                grouped[key] = []
            grouped[key].append({
                "title": d.get("title", ""),
                "url": d.get("url", ""),
                "published_at": d["published_at"].isoformat() if hasattr(d["published_at"], "isoformat") else str(d["published_at"]),
            })
        return {"links": grouped}

    @router.post("/suggest-angles")
    async def suggest_angles(payload: dict, user=user_dep):
        """Return 4 punchy, distinct article angle suggestions for a keyword, skipping already-written titles."""
        keyword = str(payload.get("keyword") or "").strip()
        if not keyword:
            raise HTTPException(400, "keyword is required")
        existing_titles: list[str] = [str(t) for t in (payload.get("existing_titles") or []) if t]
        ctx = _seo_business_context(user)
        biz_name = ctx.get("business_name") or "our business"
        biz_type = ctx.get("business_type") or "business"
        lang = ctx.get("language") or "English"

        existing_block = ""
        if existing_titles:
            existing_block = "ALREADY WRITTEN — do NOT suggest these or close variations:\n" + "\n".join(f"  - {t}" for t in existing_titles[:10]) + "\n\n"

        prompt = f"""You are a top-tier content strategist for {biz_name} ({biz_type}). Write in {lang}.

Target keyword: "{keyword}"

{existing_block}Generate exactly 4 blog post title ideas for this keyword. Each title must:
- Be punchy, direct, and specific — like a great magazine headline
- Target the keyword from a DIFFERENT angle (listicle / how-to / comparison / story / beginner guide / mistake-avoidance / case study)
- Use power words: numbers, "you", "how", "why", "stop", "best", "without", "mistakes", "secrets", etc.
- Sound like something a real person would click, NOT like corporate marketing copy

Good title examples (match this energy):
- "7 Ways to Stop Losing Sales on WhatsApp"
- "How to Set Up a WhatsApp CRM in Under an Hour"
- "WhatsApp CRM vs Email: Which One Actually Converts?"
- "The Beginner's Guide to Managing Customers on WhatsApp"

Each of the 4 titles must use a DIFFERENT format from this list:
1. Numbered list ("X Ways / X Mistakes / X Tips")
2. How-to or step-by-step
3. Comparison or "vs" or "or"
4. Question, story, or beginner guide

Reply with ONLY a valid JSON array of 4 objects — no extra text, no markdown:
[
  {{"title": "...", "angle": "one sentence: who this is for and what they will learn"}},
  {{"title": "...", "angle": "..."}},
  {{"title": "...", "angle": "..."}},
  {{"title": "...", "angle": "..."}}
]"""

        raw = await _call_ai(prompt, max_tokens=700)
        import json as _json, re as _re
        try:
            raw = raw.strip()
            if raw.startswith("```"): raw = _re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
            match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
            angles = _json.loads(match.group(0)) if match else []
        except Exception:
            angles = []

        return {"keyword": keyword, "angles": angles[:4]}

    @router.post("/serp/backfill-volumes")
    async def backfill_ranking_volumes(user=user_dep):
        """Update search_volume on existing ranking entries using saved keyword data or VebAPI lookup."""
        import asyncio as _asyncio
        tid = _tid(user)

        settings = user.get("settings") or {}
        country_code = str(
            settings.get("country_code") or user.get("country_code") or ""
        ).upper()[:2]

        # Step 1: build vol_map from saved keywords (fast, free)
        saved_docs = await db.seo_saved_keywords.find({"user_id": tid}).to_list(24)
        vol_map: dict = {}
        for doc in saved_docs:
            for kw in (doc.get("keywords") or []):
                text = str(kw.get("keyword") or kw.get("text") or "").strip().lower()
                vol = kw.get("search_volume") or kw.get("avg_monthly_searches")
                if text and vol and text not in vol_map:
                    try:
                        vol_map[text] = int(vol)
                    except (ValueError, TypeError):
                        pass

        # Step 2: find all tracked keywords with null volume
        null_vol_entries = await db.seo_serp_rankings.find(
            {"user_id": tid, "search_volume": None},
            {"keyword": 1}
        ).to_list(200)
        null_kws = list({e["keyword"] for e in null_vol_entries})

        # Step 3: for keywords not in vol_map, try DataForSEO batch volume lookup
        updated = 0
        missing_kws = [kw for kw in null_kws if kw.lower().strip() not in vol_map]

        if missing_kws:
            from . import dataforseo as dfs
            if dfs.dfs_enabled():
                try:
                    settings2 = user.get("settings") or {}
                    lc = dfs.resolve_location_code(
                        str(settings2.get("country") or ""),
                        str(settings2.get("country_code") or user.get("country_code") or ""),
                    )
                    dlang = dfs.language_code_from_settings("en")
                    dfs_vols = await dfs.fetch_search_volumes_batch(
                        missing_kws[:50], location_code=lc, language_code=dlang
                    )
                    for kw_lower, vol in dfs_vols.items():
                        if vol:
                            vol_map[kw_lower] = vol
                    logger.info("[serp/backfill-volumes] DataForSEO returned volumes for %d/%d keywords",
                                len(dfs_vols), len(missing_kws))
                except Exception as e:
                    logger.warning("[serp/backfill-volumes] DataForSEO volume lookup failed: %s", e)

        # Step 4: apply all volumes to DB
        for kw_lower, vol in vol_map.items():
            result = await db.seo_serp_rankings.update_many(
                {"user_id": tid, "keyword": {"$regex": f"^{kw_lower}$", "$options": "i"}, "search_volume": None},
                {"$set": {"search_volume": vol}}
            )
            updated += result.modified_count

        return {"updated": updated}

    @router.post("/serp/refresh-all")
    async def refresh_all_rankings(payload: dict, user=user_dep):
        """Re-check live SERP positions for all tracked keywords using DataForSEO."""
        import asyncio as _asyncio
        from . import dataforseo as dfs
        tid = _tid(user)

        settings = user.get("settings") or {}
        loc_code = dfs.resolve_location_code(
            country=str(settings.get("country") or user.get("country") or ""),
            country_code=str(settings.get("country_code") or user.get("country_code") or ""),
        )
        lang_code = dfs.language_code_from_settings(
            str(settings.get("primary_language") or "English")
        )

        # Build volume map from saved keywords to fill gaps
        saved_docs = await db.seo_saved_keywords.find({"user_id": tid}).to_list(24)
        vol_map: dict = {}
        for doc in saved_docs:
            for kw in (doc.get("keywords") or []):
                text = str(kw.get("keyword") or kw.get("text") or "").strip().lower()
                vol = kw.get("search_volume") or kw.get("avg_monthly_searches")
                if text and vol and text not in vol_map:
                    try:
                        vol_map[text] = int(vol)
                    except (ValueError, TypeError):
                        pass

        # Get latest unique keyword+domain pairs tracked by this user
        all_entries = await db.seo_serp_rankings.find(
            {"user_id": tid},
            {"keyword": 1, "domain": 1, "search_volume": 1}
        ).sort("checked_at", -1).to_list(500)

        seen: set = set()
        pairs: list = []
        for e in all_entries:
            key = f"{e['keyword']}||{e['domain']}"
            if key not in seen:
                seen.add(key)
                pairs.append({"keyword": e["keyword"], "domain": e["domain"], "search_volume": e.get("search_volume")})

        if not pairs:
            return {"checked": 0, "failed": 0, "results": []}

        results = []
        failed = 0
        for idx, pair in enumerate(pairs[:50]):
            if idx > 0:
                await _asyncio.sleep(1.0)
            kw = pair["keyword"]
            clean_domain = pair["domain"].replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/").split("/")[0]
            found_position: int | None = None
            global_position: int | None = None
            try:
                serp = await dfs.check_serp_position_dfs(
                    kw, clean_domain,
                    location_code=loc_code,
                    language_code=lang_code,
                    depth=20,
                )
                found_position = serp["position"]
                global_position = serp["global_position"]
            except Exception as e:
                logger.warning("[serp/refresh-all] failed keyword=%r: %s", kw, e)
                failed += 1

            vol = pair.get("search_volume") or vol_map.get(kw.lower().strip())
            doc = {
                "user_id": tid,
                "keyword": kw,
                "domain": clean_domain,
                "position": found_position,
                "global_position": global_position,
                "location_code": loc_code,
                "language_code": lang_code,
                "search_volume": vol,
                "checked_at": datetime.utcnow(),
                "source": "dataforseo",
            }
            await db.seo_serp_rankings.insert_one(doc)
            results.append({"keyword": kw, "position": found_position, "global_position": global_position, "checked_at": doc["checked_at"].isoformat()})

        return {"checked": len(results), "failed": failed, "results": results}

    # ── Analytics: Google Search Console (via Composio) ───────────────────────

    @router.get("/analytics/search-console/sitemaps")
    async def get_search_console_sitemaps(site_url: str = "", user=user_dep):
        """Fetch sitemaps and their index/submitted counts from Google Search Console."""
        from composio_service import composio_proxy, get_connection_status
        from urllib.parse import quote as _q
        tid = _tid(user)
        status = await get_connection_status(tid, "googlesearchconsole")
        if not status.get("connected"):
            return {"connected": False, "sitemaps": []}
        ctx = _seo_business_context(user)
        raw = site_url.strip() or ctx.get("website_url", "")
        if not raw:
            return {"connected": True, "sitemaps": [], "error": "No site URL provided"}
        # Try sc-domain: first (works when site is registered as domain property),
        # then fall back to https URL-prefix variants.
        _clean = raw.strip().rstrip("/")
        if _clean.startswith("sc-domain:"):
            _bare = _clean[len("sc-domain:"):].lstrip("www.")
        elif "://" in _clean:
            _bare = _clean.split("://", 1)[1].lstrip("www.").rstrip("/")
        else:
            _bare = _clean.lstrip("www.").rstrip("/")
        candidates = [
            f"sc-domain:{_bare}",
            f"https://www.{_bare}/",
            f"https://{_bare}/",
            f"https://www.{_bare}",
            f"https://{_bare}",
            f"http://www.{_bare}/",
            f"http://{_bare}/",
        ]
        for site in candidates:
            try:
                data = await composio_proxy(
                    tid, "googlesearchconsole", "GET",
                    f"https://searchconsole.googleapis.com/webmasters/v3/sites/{_q(site, safe='')}/sitemaps",
                )
                # If the call returned an API-level error object, try the next candidate
                if data.get("error") or data.get("code"):
                    logger.info("[gsc/sitemaps] error response for %s: %s", site, data)
                    continue
                # Successful call — return even if no sitemaps submitted
                raw_maps = data.get("sitemap") or []
                sitemaps = []
                for s in raw_maps:
                    contents = s.get("contents") or []
                    submitted = sum(int(c.get("submitted", 0)) for c in contents)
                    indexed   = sum(int(c.get("indexed", 0)) for c in contents)
                    sitemaps.append({
                        "path": s.get("path", ""),
                        "last_submitted": s.get("lastSubmitted", ""),
                        "last_downloaded": s.get("lastDownloaded", ""),
                        "is_pending": s.get("isPending", False),
                        "warnings": int(s.get("warnings", 0)),
                        "errors": int(s.get("errors", 0)),
                        "submitted": submitted,
                        "indexed": indexed,
                    })
                return {
                    "connected": True,
                    "site_url": site,
                    "sitemaps": sitemaps,
                    "note": "No sitemaps have been submitted to Search Console yet." if not sitemaps else None,
                }
            except Exception as exc:
                logger.info("[gsc/sitemaps] candidate %s failed: %s", site, exc)
                continue
        return {"connected": True, "sitemaps": [], "error": "Could not retrieve sitemaps — check site URL."}

    @router.get("/analytics/search-console/indexing")
    async def get_page_indexing_status(
        site_url: str = "",
        sitemap_url: str = "",
        max_urls: int = 20,
        user=user_dep,
    ):
        """
        Inspect each sitemap URL via the GSC URL Inspection API and return a
        breakdown of why pages are (or aren't) indexed — mirroring the
        'Why pages aren't indexed' table in GSC.
        """
        import httpx as _hx
        import xml.etree.ElementTree as _ET
        from composio_service import composio_proxy, get_connection_status

        try:
            tid = _tid(user)
            status = await get_connection_status(tid, "googlesearchconsole")
        except Exception as exc:
            logger.error("[gsc/indexing] auth error: %s", exc)
            return {"connected": False, "reasons": [], "error": str(exc)}

        if not status.get("connected"):
            return {"connected": False, "reasons": []}

        try:
            ctx = _seo_business_context(user)
        except Exception:
            ctx = {}

        # gsc_property = exact GSC property URL (used in URL Inspection API siteUrl field)
        # http_site    = actual https:// URL (used to fetch sitemap)
        raw_input = (site_url.strip() or ctx.get("website_url", "")).strip().rstrip("/")
        if not raw_input:
            return {"connected": True, "reasons": [], "error": "No site URL provided — load your sites with 'List my sites' then run the analysis."}

        if raw_input.startswith("sc-domain:"):
            # Domain property: e.g. sc-domain:example.com
            gsc_property = raw_input  # keep as-is for URL Inspection API
            domain = raw_input[len("sc-domain:"):]
            http_site = f"https://{domain}"
        elif raw_input.startswith("http"):
            gsc_property = raw_input.rstrip("/") + "/"  # GSC URL-prefix props end with /
            http_site = raw_input
        else:
            gsc_property = f"https://{raw_input}/"
            http_site = f"https://{raw_input}"

        # Derive sitemap URL
        sm_url = sitemap_url.strip() or f"{http_site}/sitemap.xml"

        # Fetch and parse sitemap XML for the list of page URLs
        urls_to_inspect: list[str] = []
        try:
            async with _hx.AsyncClient(timeout=12, follow_redirects=True) as cl:
                resp = await cl.get(sm_url)
                if resp.status_code == 200:
                    root = _ET.fromstring(resp.content)
                    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                    for loc in root.findall(".//sm:url/sm:loc", ns):
                        if loc.text:
                            urls_to_inspect.append(loc.text.strip())
                    # Handle sitemap index files
                    if not urls_to_inspect:
                        for loc in root.findall(".//sm:sitemap/sm:loc", ns):
                            if loc.text:
                                urls_to_inspect.append(loc.text.strip())
        except Exception as exc:
            logger.warning("[gsc/indexing] sitemap fetch failed %s: %s", sm_url, exc)

        if not urls_to_inspect:
            return {
                "connected": True, "reasons": [],
                "error": f"Could not fetch or parse sitemap at {sm_url}",
            }

        urls_to_inspect = urls_to_inspect[: min(max_urls, 50)]

        # Actionable advice per GSC coverage state
        _ADVICE: dict[str, dict] = {
            "Submitted and indexed": {
                "color": "green", "fix": None,
                "label": "Indexed ✓",
            },
            "Crawled - currently not indexed": {
                "color": "red",
                "label": "Crawled – not indexed",
                "fix": (
                    "Google read these pages but decided they weren't valuable enough to index. "
                    "Add more unique, in-depth content (aim for 500+ words). Remove duplicate or thin pages. "
                    "Strengthen internal linking to these pages."
                ),
            },
            "Alternate page with proper canonical tag": {
                "color": "amber",
                "label": "Alternate page (canonical set)",
                "fix": (
                    "These pages have a canonical tag pointing to a different URL. "
                    "If they should be indexed, update the canonical tag to point to themselves. "
                    "If intentional, this is fine — Google is indexing the canonical version."
                ),
            },
            "Page with redirect": {
                "color": "amber",
                "label": "Page with redirect",
                "fix": (
                    "These sitemap URLs redirect to other pages. Update your sitemap to use the final "
                    "destination URLs instead. Remove any unnecessary redirect chains."
                ),
            },
            "Discovered - currently not indexed": {
                "color": "blue",
                "label": "Discovered – not yet crawled",
                "fix": (
                    "Google found these pages but hasn't crawled them yet. "
                    "Use the URL Inspection tool in GSC and click 'Request Indexing' for each one. "
                    "Also improve internal linking to these pages."
                ),
            },
            "Duplicate, submitted URL not selected as canonical": {
                "color": "amber",
                "label": "Duplicate (not chosen as canonical)",
                "fix": (
                    "Google considers these duplicates of other pages and chose a different canonical. "
                    "Add a self-referencing canonical tag or consolidate the content into one URL."
                ),
            },
            "Blocked by robots.txt": {
                "color": "red",
                "label": "Blocked by robots.txt",
                "fix": (
                    "Your robots.txt is preventing Google from crawling these pages. "
                    "Update robots.txt to allow Googlebot access to these URLs."
                ),
            },
            "Not found (404)": {
                "color": "red",
                "label": "Not found (404)",
                "fix": (
                    "These pages return 404. Either restore the pages, redirect to relevant existing "
                    "pages with a 301, or remove them from your sitemap."
                ),
            },
            "Soft 404": {
                "color": "red",
                "label": "Soft 404",
                "fix": (
                    "These pages return a 200 status but show empty or 'not found' content. "
                    "Fix the page content or return a proper 404 status code."
                ),
            },
            "Server error (5xx)": {
                "color": "red",
                "label": "Server error",
                "fix": (
                    "These pages are returning server errors. Check your server logs and fix the "
                    "underlying errors before Google can index them."
                ),
            },
        }
        _DEFAULT_ADVICE = {
            "color": "slate", "label": "Other",
            "fix": "Use the URL Inspection tool in GSC for details on this page.",
        }

        reasons_map: dict[str, dict] = {}
        indexed_count = 0
        not_indexed_count = 0

        for url in urls_to_inspect:
            try:
                result = await composio_proxy(
                    tid, "googlesearchconsole", "POST",
                    "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                    json={"inspectionUrl": url, "siteUrl": gsc_property},
                    timeout=20.0,
                )
                ir = result.get("inspectionResult") or result
                idx = ir.get("indexStatusResult") or {}
                verdict = idx.get("verdict", "")
                coverage = idx.get("coverageState") or verdict or "Unknown"

                if verdict == "PASS":
                    indexed_count += 1
                else:
                    not_indexed_count += 1

                if coverage not in reasons_map:
                    advice = _ADVICE.get(coverage, _DEFAULT_ADVICE)
                    reasons_map[coverage] = {
                        "reason": coverage,
                        "label": advice.get("label", coverage),
                        "color": advice["color"],
                        "fix": advice["fix"],
                        "count": 0,
                        "urls": [],
                    }
                reasons_map[coverage]["count"] += 1
                if len(reasons_map[coverage]["urls"]) < 3:
                    reasons_map[coverage]["urls"].append(url)

            except Exception as exc:
                logger.warning("[gsc/indexing] inspect failed %s: %s", url, exc)
                continue

        reasons = sorted(reasons_map.values(), key=lambda r: -r["count"])
        if not reasons and indexed_count == 0 and not_indexed_count == 0:
            return {
                "connected": True,
                "total_inspected": len(urls_to_inspect),
                "indexed": 0, "not_indexed": 0,
                "reasons": [],
                "sitemap_url": sm_url,
                "error": (
                    f"Google's URL Inspection API returned no data for property '{gsc_property}'. "
                    "Use 'List my sites' to discover your exact GSC property URLs and select one before running analysis."
                ),
            }
        return {
            "connected": True,
            "total_inspected": len(urls_to_inspect),
            "indexed": indexed_count,
            "not_indexed": not_indexed_count,
            "reasons": reasons,
            "sitemap_url": sm_url,
        }

    @router.get("/analytics/search-console/sites")
    async def list_search_console_sites(user=user_dep):
        """List all sites the user has verified in Google Search Console."""
        from composio_service import composio_proxy, get_connection_status
        tid = _tid(user)
        status = await get_connection_status(tid, "googlesearchconsole")
        if not status.get("connected"):
            return {"connected": False, "sites": []}
        try:
            data = await composio_proxy(
                tid, "googlesearchconsole", "GET",
                "https://searchconsole.googleapis.com/webmasters/v3/sites",
            )
            raw_sites = data.get("siteEntry") or data.get("sites") or []
            sites = [
                {"url": s.get("siteUrl", ""), "level": s.get("permissionLevel", "")}
                for s in raw_sites if s.get("siteUrl")
            ]
            return {"connected": True, "sites": sites}
        except Exception as e:
            return {"connected": True, "sites": [], "error": str(e)}

    @router.get("/analytics/search-console")
    async def get_search_console_data(site_url: str = "", days: int = 28, search_type: str = "web", user=user_dep):
        """Fetch real Search Console data via Composio connection."""
        from composio_service import composio_proxy, get_connection_status
        tid = _tid(user)

        status = await get_connection_status(tid, "googlesearchconsole")
        if not status.get("connected"):
            return {"connected": False, "error": "Google Search Console not connected"}

        ctx = _seo_business_context(user)
        raw_input = site_url.strip() or ctx.get("website_url", "")
        if not raw_input:
            return {"connected": True, "error": "No site URL provided. Enter your site URL above."}

        # Normalise input → extract bare domain regardless of what the user typed
        _clean = raw_input.strip().rstrip("/")
        if _clean.startswith("sc-domain:"):
            _bare = _clean[len("sc-domain:"):].lstrip("www.")
        elif "://" in _clean:
            _bare = _clean.split("://", 1)[1].lstrip("www.").rstrip("/")
        else:
            _bare = _clean.lstrip("www.").rstrip("/")

        # Always try sc-domain: first (domain properties cover both www+non-www),
        # then every URL-prefix variant — this way the exact registered format is found.
        candidates = [
            f"sc-domain:{_bare}",
            f"sc-domain:www.{_bare}",
            f"https://www.{_bare}/",
            f"https://{_bare}/",
            f"https://www.{_bare}",
            f"https://{_bare}",
            f"http://www.{_bare}/",
            f"http://{_bare}/",
        ]
        # If user explicitly gave sc-domain or a full URL, honour it as first priority
        if raw_input.strip() not in candidates:
            candidates.insert(0, raw_input.strip())

        from datetime import timedelta
        from urllib.parse import quote as _quote
        # GSC data has a ~2-day processing lag; offset end_date to match what the GSC UI shows
        end_date = datetime.utcnow().date() - timedelta(days=2)
        start_date = end_date - timedelta(days=days)

        def _parse_rows(data, dim_key):
            rows = data.get("rows") or []
            return [
                {
                    dim_key: (r.get("keys") or [""])[0],
                    "clicks": r.get("clicks", 0),
                    "impressions": r.get("impressions", 0),
                    "ctr": round((r.get("ctr") or 0) * 100, 1),
                    "position": round(r.get("position") or 0, 1),
                }
                for r in rows
            ]

        last_error = ""
        for website in candidates:
          try:
            encoded = _quote(website, safe="")
            base_url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query"
            # Use the requested search type; default "web" matches GSC's default view
            stype = search_type if search_type in ("web", "image", "video", "news") else "web"
            query_body = {"startDate": start_date.isoformat(), "endDate": end_date.isoformat(), "rowLimit": 25, "type": stype}

            queries_data = await composio_proxy(tid, "googlesearchconsole", "POST", base_url,
                json={**query_body, "dimensions": ["query"]})
            pages_data = await composio_proxy(tid, "googlesearchconsole", "POST", base_url,
                json={**query_body, "dimensions": ["page"]})

            # GSC returns empty rows for unrecognised sites — treat as failure and try next
            if not queries_data.get("rows") and not pages_data.get("rows"):
                last_error = f"No data for '{website}' — site may not be indexed yet or URL format is wrong."
                logger.info("[gsc] no rows for %s, trying next candidate", website)
                continue

            # True site-wide totals — query with NO dimensions returns a single aggregate row
            try:
                totals_data = await composio_proxy(tid, "googlesearchconsole", "POST", base_url,
                    json={"startDate": start_date.isoformat(), "endDate": end_date.isoformat(), "type": stype})
                totals_row = (totals_data.get("rows") or [{}])[0]
                total_clicks = int(totals_row.get("clicks") or 0)
                total_impressions = int(totals_row.get("impressions") or 0)
                avg_ctr = round((totals_row.get("ctr") or 0) * 100, 1)
                avg_position = round(totals_row.get("position") or 0, 1)
            except Exception:
                # Fallback: sum from top-25 rows if totals query fails
                top_q_tmp = _parse_rows(queries_data, "query")
                total_clicks = sum(q["clicks"] for q in top_q_tmp)
                total_impressions = sum(q["impressions"] for q in top_q_tmp)
                avg_ctr = round(total_clicks / total_impressions * 100, 1) if total_impressions else 0
                avg_position = round(sum(q["position"] for q in top_q_tmp) / len(top_q_tmp), 1) if top_q_tmp else 0

            # Device & country breakdown (best-effort — don't fail if these error)
            try:
                device_data = await composio_proxy(tid, "googlesearchconsole", "POST", base_url,
                    json={**query_body, "dimensions": ["device"], "rowLimit": 5})
                devices = _parse_rows(device_data, "device")
            except Exception:
                devices = []

            try:
                country_data = await composio_proxy(tid, "googlesearchconsole", "POST", base_url,
                    json={**query_body, "dimensions": ["country"], "rowLimit": 10})
                countries = _parse_rows(country_data, "country")
            except Exception:
                countries = []

            # Date trend (daily clicks + impressions)
            try:
                date_data = await composio_proxy(tid, "googlesearchconsole", "POST", base_url,
                    json={**query_body, "dimensions": ["date"], "rowLimit": days})
                trend = [
                    {
                        "date": (r.get("keys") or [""])[0],
                        "clicks": r.get("clicks", 0),
                        "impressions": r.get("impressions", 0),
                    }
                    for r in (date_data.get("rows") or [])
                ]
            except Exception:
                trend = []

            top_queries = _parse_rows(queries_data, "query")
            top_pages = _parse_rows(pages_data, "page")

            return {
                "connected": True,
                "site_url": website,
                "period_days": days,
                "summary": {
                    "total_clicks": total_clicks,
                    "total_impressions": total_impressions,
                    "avg_ctr": avg_ctr,
                    "avg_position": avg_position,
                },
                "top_queries": top_queries,
                "top_pages": top_pages,
                "devices": devices,
                "countries": countries,
                "trend": trend,
            }
          except Exception as e:
            last_error = str(e)
            logger.info("[gsc] candidate %s failed: %s", website, e)
            continue

        # All candidates exhausted
        tried = ", ".join(candidates[:4])
        return {
            "connected": True,
            "error": (
                f"No data returned after trying {len(candidates)} URL formats "
                f"(e.g. {tried}…). "
                "Use the 'List my sites' button to see the exact URL registered in your Search Console account."
            ),
        }

    @router.get("/analytics/ga4")
    async def get_ga4_data(property_id: str = "", days: int = 28, user=user_dep):
        """Fetch real Google Analytics 4 data via Composio connection."""
        from composio_service import composio_proxy, get_connection_status
        tid = _tid(user)

        status = await get_connection_status(tid, "googleanalytics")
        if not status.get("connected"):
            return {"connected": False, "error": "Google Analytics not connected"}

        if not property_id.strip():
            return {"connected": True, "error": "No GA4 property ID configured. Enter your GA4 property ID (e.g. 123456789)."}

        from datetime import timedelta
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)

        try:
            data = await composio_proxy(
                tid, "googleanalytics",
                "POST",
                f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
                json={
                    "dateRanges": [{"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}],
                    "metrics": [
                        {"name": "sessions"},
                        {"name": "totalUsers"},
                        {"name": "screenPageViews"},
                        {"name": "bounceRate"},
                        {"name": "averageSessionDuration"},
                    ],
                    "dimensions": [{"name": "date"}],
                    "orderBys": [{"dimension": {"dimensionName": "date"}}],
                    "limit": days,
                },
            )

            rows = data.get("rows") or []
            daily = []
            total_sessions = 0
            total_users = 0
            total_views = 0
            for row in rows:
                dims = row.get("dimensionValues") or []
                mets = row.get("metricValues") or []
                date_val = (dims[0].get("value") or "") if dims else ""
                sessions = int(float((mets[0].get("value") or 0))) if len(mets) > 0 else 0
                users = int(float((mets[1].get("value") or 0))) if len(mets) > 1 else 0
                views = int(float((mets[2].get("value") or 0))) if len(mets) > 2 else 0
                bounce = round(float((mets[3].get("value") or 0)) * 100, 1) if len(mets) > 3 else 0
                duration = round(float((mets[4].get("value") or 0)), 0) if len(mets) > 4 else 0
                daily.append({"date": date_val, "sessions": sessions, "users": users, "views": views, "bounce_rate": bounce, "avg_session_duration": duration})
                total_sessions += sessions
                total_users += users
                total_views += views

            return {
                "connected": True,
                "property_id": property_id,
                "period_days": days,
                "summary": {
                    "total_sessions": total_sessions,
                    "total_users": total_users,
                    "total_views": total_views,
                },
                "daily": daily,
            }
        except Exception as e:
            logger.warning("[seo/analytics/ga4] %s", e)
            return {"connected": True, "error": str(e)}

    @router.get("/analytics/google-ads")
    async def get_google_ads_data(customer_id: str = "", days: int = 30, user=user_dep):
        """Fetch Google Ads campaign data via Composio connection."""
        from composio_service import composio_proxy, get_connection_status
        tid = _tid(user)

        status = await get_connection_status(tid, "googleads")
        if not status.get("connected"):
            return {"connected": False, "error": "Google Ads not connected"}

        if not customer_id.strip():
            return {"connected": True, "error": "No Customer ID provided. Find it in Google Ads → top-right corner (format: 123-456-7890)."}

        cid = customer_id.strip().replace("-", "").replace(" ", "")

        from datetime import timedelta, date as _date
        end_dt = datetime.utcnow().date()
        start_dt = end_dt - timedelta(days=days)

        gaql = (
            f"SELECT campaign.id, campaign.name, campaign.status, "
            f"metrics.impressions, metrics.clicks, metrics.cost_micros, "
            f"metrics.ctr, metrics.average_cpc "
            f"FROM campaign "
            f"WHERE segments.date BETWEEN '{start_dt.isoformat()}' AND '{end_dt.isoformat()}' "
            f"AND campaign.status = 'ENABLED' "
            f"ORDER BY metrics.cost_micros DESC "
            f"LIMIT 20"
        )

        try:
            data = await composio_proxy(
                tid, "googleads",
                "POST",
                f"https://googleads.googleapis.com/v17/customers/{cid}/googleAds:search",
                json={"query": gaql},
            )
            results = data.get("results") or []
            total_impressions = 0
            total_clicks = 0
            total_cost_micros = 0
            campaigns = []
            for r in results:
                m = r.get("metrics") or {}
                c = r.get("campaign") or {}
                impressions = int(m.get("impressions") or 0)
                clicks = int(m.get("clicks") or 0)
                cost_micros = int(m.get("costMicros") or m.get("cost_micros") or 0)
                cost = round(cost_micros / 1_000_000, 2)
                ctr = round(float(m.get("ctr") or 0) * 100, 2)
                avg_cpc = round(int(m.get("averageCpc") or m.get("average_cpc") or 0) / 1_000_000, 2)
                total_impressions += impressions
                total_clicks += clicks
                total_cost_micros += cost_micros
                campaigns.append({
                    "id": str(c.get("id") or ""),
                    "name": c.get("name") or "—",
                    "status": c.get("status") or "",
                    "impressions": impressions,
                    "clicks": clicks,
                    "cost": cost,
                    "ctr": ctr,
                    "avg_cpc": avg_cpc,
                })
            total_cost = round(total_cost_micros / 1_000_000, 2)
            overall_ctr = round(total_clicks / total_impressions * 100, 2) if total_impressions else 0
            avg_cpc_overall = round(total_cost / total_clicks, 2) if total_clicks else 0
            return {
                "connected": True,
                "customer_id": cid,
                "period_days": days,
                "summary": {
                    "total_spend": total_cost,
                    "total_clicks": total_clicks,
                    "total_impressions": total_impressions,
                    "avg_ctr": overall_ctr,
                    "avg_cpc": avg_cpc_overall,
                },
                "campaigns": campaigns,
            }
        except Exception as e:
            logger.warning("[seo/analytics/google-ads] %s", e)
            return {"connected": True, "error": str(e)}

    # ── AI Visibility Audit endpoints ─────────────────────────────────────────

    @router.get("/ai-audits")
    async def get_ai_audits(user=user_dep):
        tid = _tid(user)
        docs = await db.seo_ai_audits.find({"user_id": tid}).sort("created_at", -1).limit(20).to_list(20)
        for d in docs:
            d["id"] = str(d.pop("_id", ""))
        return {"audits": docs}

    return router
