"""
Shared website scraping helper.

Used by:
- backend/seo/routes.py /scrape-website (LLM-synthesized business profile)
- backend/rex/onboarding/scanner.py scan_website() (Day 0 onboarding insights)

Pure-stdlib HTML parsing (no BeautifulSoup); httpx for async fetching.
"""
from __future__ import annotations

import asyncio
import html as _html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx


PRIORITY_SLUGS = [
    "about", "services", "menu", "products", "contact",
    "our-story", "what-we-do", "pricing", "who-we-are",
]

_SOCIAL_DOMAINS = (
    "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
    "threads.net", "github.com",
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_BLOG_SLUGS = ("/blog", "/news", "/articles", "/posts", "/journal")


class DeepParser(HTMLParser):
    """HTML extractor — title, meta tags, og:* tags, links, body text chunks."""

    SKIP_TAGS = {"script", "style", "noscript", "head", "svg", "iframe", "form", "button", "input"}

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta_desc = ""
        self.og_name = ""
        self.og_desc = ""
        self.generator = ""
        self.chunks: list[str] = []
        self.links: list[str] = []
        self._skip_depth = 0
        self._in_title = False
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
            self._in_title = True
            self._buf = ""
        if tag == "meta":
            n = a.get("name", "").lower()
            prop = a.get("property", "").lower()
            c = a.get("content", "")
            if n == "description":
                self.meta_desc = c
            if n == "generator":
                self.generator = c
            if prop == "og:site_name":
                self.og_name = c
            if prop == "og:description":
                self.og_desc = c
        if tag == "a":
            href = a.get("href", "")
            if href and not href.startswith("#") and not href.startswith("javascript"):
                self.links.append(href)
        if tag in ("h1", "h2", "h3", "h4", "p", "li", "td", "th", "span", "div", "article", "section"):
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title" and self._in_title:
            self.title = self._buf.strip()
            self._in_title = False
            self._buf = ""
        if tag in ("h1", "h2", "h3", "h4", "p", "li", "td", "th", "article", "section"):
            self._flush()

    def handle_data(self, data):
        if self._in_title:
            self._buf += data
            return
        if self._skip_depth > 0:
            return
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


@dataclass
class SiteScrape:
    """Parsed result of scraping a website (homepage + sub-pages)."""
    url: str
    title: str = ""
    meta_desc: str = ""
    og_name: str = ""
    og_desc: str = ""
    generator: str = ""
    combined_text: str = ""
    home_html: str = ""
    home_links: list[str] = field(default_factory=list)
    pages_scraped: int = 0


async def fetch_page(client: httpx.AsyncClient, page_url: str, timeout: float = 10.0) -> str:
    """Fetch HTML for a single page; return "" on failure or non-HTML response."""
    try:
        r = await client.get(page_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        pass
    return ""


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    return url


async def scrape_site(
    url: str,
    max_subpages: int = 3,
    homepage_text_chars: int = 4000,
    subpage_text_chars: int = 2000,
) -> Optional[SiteScrape]:
    """
    Fetch homepage + auto-discover and fetch up to `max_subpages` priority sub-pages.

    Returns a SiteScrape with parsed title/meta/og fields and combined text,
    or None if the homepage couldn't be fetched.
    """
    url = _normalize_url(url)
    base = urlparse(url)

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        home_html = await fetch_page(client, url)
        if not home_html:
            return None

        home_parser = DeepParser()
        home_parser.feed(home_html)

        # Discover priority sub-pages from internal links
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
            if len(candidate_pages) >= max_subpages * 2:
                break

        sub_htmls = await asyncio.gather(
            *[fetch_page(client, u) for u in candidate_pages[:max_subpages]]
        )

    all_text_parts: list[str] = []
    main_text = home_parser.get_text(homepage_text_chars)
    if main_text:
        all_text_parts.append(f"=== Homepage ===\n{main_text}")

    for sub_url, sub_html in zip(candidate_pages[:max_subpages], sub_htmls):
        if not sub_html:
            continue
        sp = DeepParser()
        sp.feed(sub_html)
        sub_text = sp.get_text(subpage_text_chars)
        if sub_text:
            slug = urlparse(sub_url).path.strip("/") or "page"
            all_text_parts.append(f"=== {slug} ===\n{sub_text}")

    combined = "\n\n".join(all_text_parts)[:9000]

    return SiteScrape(
        url=url,
        title=_html.unescape(home_parser.title),
        meta_desc=_html.unescape(home_parser.meta_desc or home_parser.og_desc),
        og_name=_html.unescape(home_parser.og_name),
        og_desc=_html.unescape(home_parser.og_desc),
        generator=home_parser.generator,
        combined_text=combined,
        home_html=home_html,
        home_links=home_parser.links,
        pages_scraped=1 + sum(1 for h in sub_htmls if h),
    )


# ── Lightweight inference helpers (no LLM required) ────────────────────────

def infer_tech_stack(scrape: SiteScrape) -> str:
    """Detect Shopify / WordPress / Wix / Squarespace / Webflow from HTML+headers."""
    gen = (scrape.generator or "").lower()
    html = (scrape.home_html or "").lower()

    if "shopify" in gen or "cdn.shopify.com" in html or "shopify.theme" in html:
        return "Shopify"
    if "wordpress" in gen or "wp-content/" in html or "wp-includes/" in html:
        return "WordPress"
    if "wix" in gen or "wixstatic.com" in html or "x-wix-" in html:
        return "Wix"
    if "squarespace" in gen or "squarespace.com" in html or "static1.squarespace" in html:
        return "Squarespace"
    if "webflow" in gen or "webflow.com" in html or "w-webflow-badge" in html:
        return "Webflow"
    if "ghost" in gen:
        return "Ghost"
    if "hubspot" in html or "hs-scripts.com" in html:
        return "HubSpot"
    return ""


def extract_social_links(scrape: SiteScrape) -> list[str]:
    """Filter homepage links down to known social-network domains."""
    found: list[str] = []
    seen: set[str] = set()
    for href in scrape.home_links:
        h = href.lower()
        if not h.startswith("http"):
            continue
        for domain in _SOCIAL_DOMAINS:
            if domain in h and href not in seen:
                found.append(href)
                seen.add(href)
                break
    return found


def extract_contact_email(scrape: SiteScrape) -> str:
    """First plausible email address found in combined text or homepage HTML."""
    blob = scrape.combined_text + "\n" + scrape.home_html
    for match in _EMAIL_RE.finditer(blob):
        email = match.group(0)
        if not any(bad in email.lower() for bad in ("example.com", "sentry", "wixpress", "@2x", "@3x")):
            return email
    return ""


def has_blog(scrape: SiteScrape) -> bool:
    """True if any homepage link points at a blog/news/articles slug."""
    for href in scrape.home_links:
        path = urlparse(href).path.lower()
        if any(s in path for s in _BLOG_SLUGS):
            return True
    return False
