"""SEO + Auto-Blogging module — site audit, keyword research, AI blog writer, auto-publish."""
from __future__ import annotations
import logging, uuid, re, httpx
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


def _tid(user): return user.get("business_id", user["_id"])

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

class KeywordRequest(BaseModel):
    business_type: str
    location: str = ""
    language: str = "English"

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
    """Fetch a URL and run basic SEO checks."""
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = ""
            self.meta: Dict[str, str] = {}
            self.h1s: List[str] = []
            self.h2s: List[str] = []
            self.images_missing_alt: int = 0
            self.total_images: int = 0
            self._in_title = False
            self._word_count = 0

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

        def handle_endtag(self, tag):
            if tag == "title": self._in_title = False

        def handle_data(self, data):
            if self._in_title: self.title += data
            if self.h1s and data.strip(): self.h1s[-1] += data
            if self.h2s and data.strip(): self.h2s[-1] += data

    try:
        headers = {"User-Agent": "ZiloSEOBot/1.0"}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as hc:
            resp = await hc.get(url, headers=headers)
        html = resp.text
        word_count = len(re.sub(r"<[^>]+>", " ", html).split())
    except Exception as e:
        raise HTTPException(400, f"Could not fetch URL: {e}")

    parser = _Parser()
    parser.feed(html)

    issues = []
    score = 100

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
        "issues": issues,
        "og_tags": {k: v for k, v in parser.meta.items() if k.startswith("og:")},
    }


# ── Router factory ────────────────────────────────────────────────────────────

def make_seo_router(db, user_dep):
    router = APIRouter(prefix="/seo", tags=["seo"])

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
        location_str = f" in {payload.location}" if payload.location else ""
        prompt = f"""You are an SEO keyword research expert. Generate keyword ideas for a {payload.business_type} business{location_str}.

Return a JSON array of 20 keywords. Each item:
{{
  "keyword": "exact keyword phrase",
  "intent": "informational|transactional|local|navigational",
  "difficulty": "low|medium|high",
  "priority": 1-5,
  "content_idea": "one blog post or page idea for this keyword"
}}

Focus on: local keywords, buying intent keywords, long-tail phrases, question-based keywords.
Language: {payload.language}
Only return the JSON array."""

        raw = await _call_ai(prompt, max_tokens=2000)
        try:
            import json
            raw = raw.strip()
            if raw.startswith("```"): raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
            keywords = json.loads(raw)
        except Exception:
            keywords = []

        return {"keywords": keywords, "business_type": payload.business_type, "location": payload.location}

    # ── Blog Post Generation ────────────────────────────────────────────────

    @router.post("/blog/generate")
    async def generate_blog_post(payload: BlogGenerateRequest, user=user_dep):
        word_targets = {"short": "400-500", "medium": "800-1000", "long": "1400-1600"}
        word_target = word_targets.get(payload.length, "800-1000")
        keywords_str = ", ".join(payload.keywords) if payload.keywords else payload.topic
        business_str = f" for {payload.business_name}" if payload.business_name else ""

        faq_instruction = """
After the main content, add a FAQ section with 3-5 relevant questions and answers (good for AI search and Google featured snippets).""" if payload.include_faq else ""

        prompt = f"""Write a {word_target}-word SEO-optimized blog post{business_str}.

Topic: {payload.topic}
Target keywords to include naturally: {keywords_str}
Tone: {payload.tone}
Language: {payload.language}
{faq_instruction}

Structure the post with:
- An engaging H1 title (include main keyword)
- Introduction paragraph
- Multiple H2 sections with H3 subsections where needed
- Conclusion with call-to-action
{' - FAQ section at the end' if payload.include_faq else ''}

After the article, on a new line write:
META_TITLE: [SEO title, 50-60 chars]
META_DESC: [Meta description, 140-160 chars]
TAGS: [comma-separated tags]

Write the full article now:"""

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
        return _ser(doc)

    @router.delete("/blog/posts/{post_id}")
    async def delete_post(post_id: str, user=user_dep):
        tid = _tid(user)
        result = await db.seo_blog_posts.delete_one({"_id": post_id, "user_id": tid})
        if result.deleted_count == 0: raise HTTPException(404, "Post not found")
        return {"ok": True}

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

        return result

    # ── Content Calendar ────────────────────────────────────────────────────

    @router.post("/blog/content-calendar")
    async def generate_content_calendar(
        business_type: str,
        posts_per_week: int = 2,
        weeks: int = 4,
        location: str = "",
        user=user_dep,
    ):
        location_str = f" in {location}" if location else ""
        total = posts_per_week * weeks
        prompt = f"""Create a {weeks}-week content calendar for a {business_type} business{location_str}.
Generate {total} blog post ideas ({posts_per_week} per week).

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

        raw = await _call_ai(prompt, max_tokens=2000)
        try:
            import json
            raw = raw.strip()
            if raw.startswith("```"): raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
            calendar = json.loads(raw)
        except Exception:
            calendar = []

        return {"calendar": calendar, "weeks": weeks, "posts_per_week": posts_per_week}

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
        if last_audit:
            scores = await db.seo_audits.find({"user_id": tid}).sort("created_at", -1).limit(5).to_list(5)
            if scores:
                avg_score = round(sum(s.get("score", 0) for s in scores) / len(scores))

        return {
            "total_posts": total_posts,
            "published_posts": published,
            "draft_posts": drafts,
            "total_audits": total_audits,
            "avg_seo_score": avg_score,
            "last_audit": _ser(last_audit) if last_audit else None,
        }

    return router
