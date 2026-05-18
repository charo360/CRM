"""
LangGraph tool definitions for the SEO agent.
Each tool is a pure async function decorated with @tool.
db and user_id are injected via LangGraph RunnableConfig (primary)
or via contextvars (fallback, set by the route handler before graph.ainvoke).
"""
from __future__ import annotations
import os, re, uuid, httpx, logging, contextvars as _cv
from datetime import datetime, timedelta
from typing import Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

# ── Contextvars fallback (set by route handler before graph.ainvoke) ──────────

_seo_db: _cv.ContextVar = _cv.ContextVar("seo_db", default=None)
_seo_user_id: _cv.ContextVar = _cv.ContextVar("seo_user_id", default=None)


def set_seo_context(db, user_id: str) -> None:
    _seo_db.set(db)
    _seo_user_id.set(user_id)


def _get_db_and_user(config=None):
    """Try config first; fall back to contextvars."""
    db, user_id = None, None
    if config:
        try:
            db = config["configurable"].get("db")
            user_id = config["configurable"].get("user_id")
        except (KeyError, TypeError, AttributeError):
            pass
    return (db if db is not None else _seo_db.get()), (user_id if user_id is not None else _seo_user_id.get())


# ── Shared AI caller (reuses existing env vars) ───────────────────────────────

async def _ai(prompt: str, max_tokens: int = 2500) -> str:
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
            logger.warning(f"[seo_agent] OpenAI error: {e}")

    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if claude_key:
        try:
            async with httpx.AsyncClient(timeout=60) as hc:
                r = await hc.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": claude_key, "anthropic-version": "2023-06-01"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                          "messages": [{"role": "user", "content": prompt}]},
                )
                return r.json()["content"][0]["text"]
        except Exception as e:
            logger.warning(f"[seo_agent] Claude error: {e}")

    raise RuntimeError("No AI provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.")


# ── HTML parser helper ────────────────────────────────────────────────────────

async def _fetch_and_parse(url: str) -> dict:
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = ""; self.meta: dict = {}
            self.h1s: list = []; self.h2s: list = []
            self.imgs_no_alt = 0; self.total_imgs = 0
            self._in_title = False

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "title": self._in_title = True
            if tag == "meta":
                name = a.get("name", "").lower()
                prop = a.get("property", "").lower()
                content = a.get("content", "")
                if name in ("description", "keywords"): self.meta[name] = content
                if prop.startswith("og:"): self.meta[prop] = content
            if tag == "h1": self.h1s.append("")
            if tag == "h2": self.h2s.append("")
            if tag == "img":
                self.total_imgs += 1
                if not a.get("alt"): self.imgs_no_alt += 1

        def handle_endtag(self, tag):
            if tag == "title": self._in_title = False

        def handle_data(self, data):
            if self._in_title: self.title += data
            if self.h1s and data.strip(): self.h1s[-1] += data
            if self.h2s and data.strip(): self.h2s[-1] += data

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as hc:
        resp = await hc.get(url, headers={"User-Agent": "ZiloSEOBot/1.0"})
    html = resp.text
    words = len(re.sub(r"<[^>]+>", " ", html).split())
    p = _P(); p.feed(html)
    return {"title": p.title.strip(), "meta": p.meta, "h1s": p.h1s, "h2s": p.h2s,
            "imgs_no_alt": p.imgs_no_alt, "total_imgs": p.total_imgs, "word_count": words}


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
async def audit_website(url: str, config: RunnableConfig) -> str:
    """
    Crawl and audit a website URL for SEO issues.
    Returns a score (0-100), grade (A-F), and a full list of issues with severity.
    Use this when the user asks to check, audit, or analyse a website's SEO health.
    """
    if not url.startswith("http"):
        url = "https://" + url

    try:
        data = await _fetch_and_parse(url)
    except Exception as e:
        return f"Could not fetch {url}: {e}"

    issues = []
    score = 100
    title = data["title"]

    if not title:
        issues.append("CRITICAL — Missing <title> tag"); score -= 20
    elif len(title) < 30:
        issues.append(f"WARNING — Title too short ({len(title)} chars, aim 50-60)"); score -= 5
    elif len(title) > 65:
        issues.append(f"WARNING — Title too long ({len(title)} chars, keep under 65)"); score -= 5

    desc = data["meta"].get("description", "")
    if not desc:
        issues.append("CRITICAL — Missing meta description"); score -= 15
    elif len(desc) < 80:
        issues.append(f"WARNING — Meta description short ({len(desc)} chars, aim 140-160)"); score -= 5
    elif len(desc) > 165:
        issues.append(f"WARNING — Meta description too long ({len(desc)} chars)"); score -= 5

    if not data["h1s"]:
        issues.append("CRITICAL — No H1 heading found"); score -= 15
    elif len(data["h1s"]) > 1:
        issues.append(f"WARNING — {len(data['h1s'])} H1 tags found, use only one"); score -= 5

    if data["imgs_no_alt"]:
        issues.append(f"WARNING — {data['imgs_no_alt']} of {data['total_imgs']} images missing alt text"); score -= min(10, data["imgs_no_alt"] * 2)

    if not data["meta"].get("og:title"):
        issues.append("INFO — Missing Open Graph tags (og:title, og:description, og:image)"); score -= 5

    if data["word_count"] < 300:
        issues.append(f"WARNING — Low word count ({data['word_count']} words, aim 500+)"); score -= 10

    score = max(0, score)
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

    # Persist to db if available
    try:
        db, user_id = _get_db_and_user(config)
        if db and user_id:
            await db.seo_audits.insert_one({
                "_id": str(uuid.uuid4()), "user_id": user_id, "url": url,
                "score": score, "grade": grade, "title": title,
                "meta_description": desc, "h1_count": len(data["h1s"]),
                "h2_count": len(data["h2s"]), "word_count": data["word_count"],
                "total_images": data["total_imgs"], "images_missing_alt": data["imgs_no_alt"],
                "issues": [{"message": i} for i in issues], "created_at": datetime.utcnow(),
            })
    except Exception:
        pass

    result = [f"SEO Audit for {url}", f"Score: {score}/100  Grade: {grade}", ""]
    if issues:
        result.append("Issues found:")
        for i in issues:
            result.append(f"  • {i}")
    else:
        result.append("No major issues found — great SEO health!")

    result += ["", f"Title: {title or '(missing)'}", f"Meta desc: {desc[:80] + '...' if len(desc) > 80 else desc or '(missing)'}",
               f"H1 tags: {len(data['h1s'])}  |  H2 tags: {len(data['h2s'])}  |  Word count: {data['word_count']}"]
    return "\n".join(result)


@tool
async def research_keywords(business_type: str, location: str = "", language: str = "English") -> str:
    """
    Generate a list of SEO keyword ideas for a business type and optional location.
    Returns 15-20 keywords with search intent, difficulty, and content ideas.
    Use this when the user asks for keyword ideas, keyword research, or what to rank for.
    """
    city = location.split(",")[0].strip() if location else ""
    loc = f" in {location}" if location else ""
    prompt = f"""You are an SEO keyword strategist. Generate 15 keyword ideas for a {business_type} business{loc}.

For each keyword return this format (one per line):
KEYWORD | intent | difficulty | content_idea

Where:
- intent: informational, transactional, or local
- difficulty: low, medium, or high
- content_idea: one short blog/page idea (max 8 words)

Language: {language}

KEYWORD MIX — spread across these types:
- LOCAL (5): '{business_type} {city}', 'best {business_type} near me', '{business_type} delivery {city}'
- TRANSACTIONAL (5): 'buy [service/product] {city}', 'affordable [service]', '[service] price {city}'
- INFORMATIONAL (5): 'how to [relevant action]', 'best [service] for [customer type]', '[service] guide'

STRICT RULES:
- Every keyword must describe a SERVICE or BUYING ACTION — never a standalone product/drug/ingredient name
- Use '{city}' naturally in local and transactional keywords
- 2-5 words per keyword (real phrases people type into Google)
- NO single product names with no service context (e.g. NOT 'azithromycin' — use 'buy azithromycin {city}')

Return only the list, no extra text."""

    raw = await _ai(prompt, max_tokens=1500)
    lines = [l.strip() for l in raw.strip().splitlines() if "|" in l]

    if not lines:
        return f"Could not generate keywords for {business_type}. Please try again."

    result = [f"Keyword Research — {business_type}{loc}", ""]
    result.append(f"{'Keyword':<40} {'Intent':<16} {'Difficulty':<12} Content Idea")
    result.append("-" * 95)
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 4:
            kw, intent, diff, idea = parts[0], parts[1], parts[2], parts[3]
            result.append(f"{kw:<40} {intent:<16} {diff:<12} {idea}")
    result.append(f"\n{len(lines)} keywords generated.")
    return "\n".join(result)


@tool
async def write_blog_post(
    topic: str,
    keywords: str = "",
    tone: str = "professional",
    length: str = "medium",
    business_name: str = "",
    include_faq: bool = True,
    config: RunnableConfig = None,
) -> str:
    """
    Write a full SEO-optimized blog post on a given topic.
    Saves it as a draft automatically.
    Use this when the user asks to write, create, or draft a blog post or article.

    Args:
        topic: The blog post topic or title idea.
        keywords: Comma-separated keywords to include naturally.
        tone: Writing tone — professional, friendly, or casual.
        length: Post length — short (~400w), medium (~800w), or long (~1500w).
        business_name: Optional business name for personalization.
        include_faq: Whether to add a FAQ section at the end.
    """
    word_targets = {"short": "400-500", "medium": "800-1000", "long": "1400-1600"}
    target = word_targets.get(length, "800-1000")
    kw_str = keywords if keywords else topic
    biz = f" for {business_name}" if business_name else ""
    faq_note = "\n- End with a FAQ section (3-5 Q&As, great for AI search snippets)" if include_faq else ""

    prompt = f"""You are an expert journalist and industry writer. You write the way experienced columnists do — specific, direct, grounded in real experience. Not like an AI. Not like a textbook.

Topic: {topic}
Keywords: {kw_str}
Tone: {tone} | Length: {target} words{biz}
{faq_note}

━━ BEFORE YOU WRITE — COMMIT TO YOUR OPENING TYPE ━━

Read these six opening types. Pick the ONE that fits this topic best. Your first sentence IS that opening — not an intro to the intro.

A) SCENE — a moment the reader has lived:
   "You ask for a quote. You get a number. No breakdown, no explanation. Just a number."
   "The customer walked in confident. Left confused. It happens more than it should."

B) COUNTER-INTUITIVE FACT — true but surprising:
   "The most expensive option isn't the best one. In most cases it's the second-cheapest."
   "Businesses that post daily get less engagement than those who post twice a week. Here's why."

C) DIRECT QUESTION — the one in the reader's head:
   "How do you know when you're actually getting value for money?"
   "What makes one [service] worth three times the price of another?"

D) PERSONAL OBSERVATION — from someone who's seen it:
   "I've watched the same mistake play out dozens of times. It always starts the same way."
   "After years in this industry, one pattern stands out above everything else."

E) SPECIFIC STAT OR NUMBER:
   "Seven out of ten first attempts at this end in the same predictable failure."
   "The difference between success and failure here comes down to one decision made in the first week."

F) BOLD POSITION:
   "The advice everyone repeats about [topic] is wrong. Not partially — completely."
   "Stop treating [topic] like a checklist. It's not."

━━ HEADLINE ━━
Match the energy of your opening. Make it earn the click.
✓ "The [Topic] Mistake That's Costing You More Than You Think"
✓ "5 Things Nobody Tells You About [Topic] Until It's Too Late"
✓ "Why [Common Approach] Doesn't Work — And What Does"
✗ "A Guide to [Topic]" / "Understanding [Topic]" / "All About [Topic]"

━━ WRITE THE ARTICLE ━━
- First sentence = your opening. No preamble.
- Talk to one person. Not a crowd.
- Short sentences. Then longer ones when you need to explain. Never three long sentences in a row.
- Contractions throughout: don't, it's, you'll, we've, I've, they're.
- Specific over vague: real price ranges, real place names, real scenarios.
- Every paragraph teaches something or moves the story — cut anything that doesn't.
- Each H2 answers a question the reader is thinking right now.
- Conclusion: one specific next step. Not "reach out to learn more."
{('- FAQ: 3-5 questions someone would genuinely type into Google, with direct answers.' if include_faq else '')}

INSTANT FAIL — rewrite if any of these appear:
✗ "In today's..." / "In this article..." / "Are you looking for..."
✗ "[Topic] is an important/essential part of..."
✗ "In conclusion" / "To summarize" / "As we've seen"
✗ dive into · delve into · game-changer · leverage · seamlessly · unlock · revolutionize · transformative · cutting-edge · harness the power · it goes without saying · look no further · without further ado

After the article:
META_TITLE: [50-60 chars — headline energy, not a label]
META_DESC: [140-160 chars — specific benefit, no fluff]
TAGS: [5 tags]

Start writing now — first line is your opening:"""

    raw = await _ai(prompt, max_tokens=3500)

    # Extract meta fields
    meta_title_m = re.search(r"META_TITLE:\s*(.+)", raw)
    meta_desc_m = re.search(r"META_DESC:\s*(.+)", raw)
    tags_m = re.search(r"TAGS:\s*(.+)", raw)

    meta_title = meta_title_m.group(1).strip() if meta_title_m else ""
    meta_desc = meta_desc_m.group(1).strip() if meta_desc_m else ""
    tags = [t.strip() for t in tags_m.group(1).split(",")] if tags_m else []
    content = re.sub(r"\n(META_TITLE|META_DESC|TAGS):[^\n]+", "", raw).strip()

    title_m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else topic
    word_count = len(content.split())

    # Auto-save as draft
    post_id = str(uuid.uuid4())
    try:
        db, user_id = _get_db_and_user(config)
        if db and user_id:
            await db.seo_blog_posts.insert_one({
                "_id": post_id, "user_id": user_id, "title": title, "content": content,
                "meta_title": meta_title, "meta_description": meta_desc, "tags": tags,
                "status": "draft", "platform": "internal",
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
            })
            # Also link draft to the first keyword in the tracker (if it exists)
            if keywords:
                primary_kw = keywords.split(",")[0].strip()
                await db.keyword_tracker.update_one(
                    {"user_id": user_id, "keyword": primary_kw},
                    {"$push": {"posts": {
                        "title": title,
                        "url": f"(draft:{post_id})",
                        "published_at": datetime.utcnow().isoformat(),
                    }}},
                )
    except Exception:
        pass

    return "\n".join([
        f"Blog post written and saved as draft!",
        f"Title: {title}",
        f"Word count: {word_count}",
        f"Meta title: {meta_title}",
        f"Meta desc: {meta_desc}",
        f"Tags: {', '.join(tags)}",
        f"Post ID: {post_id}",
        "",
        "--- PREVIEW (first 400 chars) ---",
        content[:400] + ("..." if len(content) > 400 else ""),
    ])


@tool
async def generate_content_calendar(
    business_type: str,
    weeks: int = 4,
    posts_per_week: int = 2,
    location: str = "",
) -> str:
    """
    Generate a content calendar with blog post ideas for the given business.
    Use this when the user asks for a content plan, editorial calendar, or posting schedule.

    Args:
        business_type: Type of business (e.g. 'hair salon', 'law firm').
        weeks: Number of weeks to plan (2-12).
        posts_per_week: Number of posts per week (1-5).
        location: Optional city/country for local SEO focus.
    """
    weeks = min(max(int(weeks), 1), 12)
    ppw = min(max(int(posts_per_week), 1), 5)
    loc = f" in {location}" if location else ""
    total = weeks * ppw

    prompt = f"""Create a {weeks}-week content calendar for a {business_type} business{loc}.
Plan {total} blog posts ({ppw} per week).

Format each post as:
Week N | Day | Title | Keywords | Intent (informational/transactional/local) | Traffic potential (low/medium/high)

Return only the table rows, one post per line, pipe-separated."""

    raw = await _ai(prompt, max_tokens=2000)
    lines = [l.strip() for l in raw.strip().splitlines() if "|" in l and l.strip()]

    result = [f"Content Calendar — {business_type}{loc}",
              f"{weeks} weeks · {ppw} posts/week · {total} total posts", ""]
    current_week = None
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            week = parts[0] if parts[0].lower().startswith("week") else f"Week ?"
            if week != current_week:
                result.append(f"\n{week}")
                result.append("-" * 60)
                current_week = week
            day = parts[1] if len(parts) > 1 else ""
            title = parts[2] if len(parts) > 2 else ""
            keywords = parts[3] if len(parts) > 3 else ""
            traffic = parts[5] if len(parts) > 5 else ""
            result.append(f"  {day:<12} {title}")
            if keywords:
                result.append(f"  {'':12} Keywords: {keywords}")
            if traffic:
                result.append(f"  {'':12} Traffic potential: {traffic}")

    return "\n".join(result)


@tool
async def fix_seo_issues(url: str) -> str:
    """
    Get specific AI-written fixes for every SEO issue found on a website.
    Returns ready-to-use replacement copy for titles, meta descriptions, etc.
    Use this when the user wants to fix or improve the SEO of a specific page.
    """
    if not url.startswith("http"):
        url = "https://" + url

    try:
        data = await _fetch_and_parse(url)
    except Exception as e:
        return f"Could not fetch {url}: {e}"

    title = data["title"]
    desc = data["meta"].get("description", "")
    issues = []
    if not title or len(title) < 30: issues.append(f"Title is poor or missing: '{title}'")
    if not desc or len(desc) < 80: issues.append(f"Meta description is poor or missing: '{desc}'")
    if not data["h1s"]: issues.append("No H1 heading found")
    if data["imgs_no_alt"]: issues.append(f"{data['imgs_no_alt']} images missing alt text")
    if not data["meta"].get("og:title"): issues.append("Missing Open Graph tags")
    if data["word_count"] < 300: issues.append(f"Content is too short ({data['word_count']} words)")

    if not issues:
        return f"✓ {url} has no major SEO issues. Score looks healthy!"

    prompt = f"""You are an SEO expert. This page has these problems:
URL: {url}
Current title: "{title}"
Current meta description: "{desc}"
Issues:
{chr(10).join(f'- {i}' for i in issues)}

For EACH issue provide:
1. A specific fix explanation (1 sentence)
2. Ready-to-use replacement copy where applicable

Be direct and practical. Format each fix clearly."""

    fixes = await _ai(prompt, max_tokens=1200)
    return f"SEO Fix Plan for {url}\n\n{fixes}"


@tool
async def list_saved_posts(config: RunnableConfig) -> str:
    """
    List all saved blog posts for the current user.
    Shows title, status, and creation date.
    Use this when the user asks to see their posts, drafts, or published articles.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "Could not access posts — no database connection."

        docs = await db.seo_blog_posts.find({"user_id": user_id}).sort("created_at", -1).limit(20).to_list(20)
        if not docs:
            return "No blog posts saved yet. Ask me to write one!"

        result = [f"Your Blog Posts ({len(docs)} found)", ""]
        for d in docs:
            created = d.get("created_at", "")
            if hasattr(created, "strftime"): created = created.strftime("%Y-%m-%d")
            result.append(f"• [{d.get('status', 'draft').upper()}] {d.get('title', 'Untitled')}  ({created})")
            result.append(f"  ID: {d['_id']}")
        return "\n".join(result)
    except Exception as e:
        return f"Error fetching posts: {e}"


@tool
async def publish_post_to_platform(
    post_id: str,
    platform: str,
    wp_url: str = "",
    wp_username: str = "",
    wp_password: str = "",
    shopify_domain: str = "",
    shopify_token: str = "",
    config: RunnableConfig = None,
) -> str:
    """
    Publish a saved blog post to WordPress or Shopify.
    Use this when the user asks to publish, post, or send a blog post to their website.

    Args:
        post_id: The ID of the saved post to publish.
        platform: 'wordpress' or 'shopify'.
        wp_url: WordPress site URL (required for WordPress).
        wp_username: WordPress username (required for WordPress).
        wp_password: WordPress application password (required for WordPress).
        shopify_domain: Shopify store domain like mystore.myshopify.com.
        shopify_token: Shopify Admin API access token.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "Cannot publish — no database connection."

        doc = await db.seo_blog_posts.find_one({"_id": post_id, "user_id": user_id})
        if not doc:
            return f"Post {post_id} not found. Use list_saved_posts to see your posts."
    except Exception as e:
        return f"Error fetching post: {e}"

    title = doc.get("title", "")
    content = doc.get("content", "")

    if platform == "wordpress":
        if not all([wp_url, wp_username, wp_password]):
            return "To publish to WordPress I need: wp_url, wp_username, and wp_password (Application Password)."
        try:
            import base64
            creds = base64.b64encode(f"{wp_username}:{wp_password}".encode()).decode()
            async with httpx.AsyncClient(timeout=30) as hc:
                resp = await hc.post(
                    f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts",
                    headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
                    json={"title": title, "content": content, "status": "publish",
                          "meta": {"_yoast_wpseo_title": doc.get("meta_title", ""),
                                   "_yoast_wpseo_metadesc": doc.get("meta_description", "")}},
                )
            if resp.status_code in (200, 201):
                data = resp.json()
                await db.seo_blog_posts.update_one(
                    {"_id": post_id},
                    {"$set": {"status": "published", "published_at": datetime.utcnow()}},
                )
                return f"Published to WordPress!\nURL: {data.get('link', 'check your WP dashboard')}\nPost ID: {data.get('id')}"
            return f"WordPress returned error {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return f"WordPress publish failed: {e}"

    elif platform == "shopify":
        if not all([shopify_domain, shopify_token]):
            return "To publish to Shopify I need: shopify_domain and shopify_token."
        try:
            async with httpx.AsyncClient(timeout=30) as hc:
                resp = await hc.post(
                    f"https://{shopify_domain}/admin/api/2024-01/blogs/articles.json",
                    headers={"X-Shopify-Access-Token": shopify_token, "Content-Type": "application/json"},
                    json={"article": {"title": title, "body_html": content, "published": True}},
                )
            if resp.status_code in (200, 201):
                data = resp.json()
                await db.seo_blog_posts.update_one(
                    {"_id": post_id},
                    {"$set": {"status": "published", "published_at": datetime.utcnow()}},
                )
                return f"Published to Shopify!\nArticle ID: {data.get('article', {}).get('id')}"
            return f"Shopify returned error {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return f"Shopify publish failed: {e}"

    return f"Unknown platform '{platform}'. Use 'wordpress' or 'shopify'."


@tool
async def get_seo_summary(config: RunnableConfig) -> str:
    """
    Get an overview of the user's SEO activity — post counts, audit history, and scores.
    Use this when the user asks for a summary, overview, or how things are going.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection available."

        total = await db.seo_blog_posts.count_documents({"user_id": user_id})
        published = await db.seo_blog_posts.count_documents({"user_id": user_id, "status": "published"})
        drafts = await db.seo_blog_posts.count_documents({"user_id": user_id, "status": "draft"})
        audits = await db.seo_audits.count_documents({"user_id": user_id})
        recent_audits = await db.seo_audits.find({"user_id": user_id}).sort("created_at", -1).limit(5).to_list(5)
        avg_score = round(sum(a.get("score", 0) for a in recent_audits) / len(recent_audits)) if recent_audits else None

        lines = [
            "SEO Activity Summary",
            f"Blog Posts: {total} total ({published} published, {drafts} drafts)",
            f"Site Audits run: {audits}",
        ]
        if avg_score is not None:
            lines.append(f"Average SEO score (last 5 audits): {avg_score}/100")
        if recent_audits:
            last = recent_audits[0]
            lines.append(f"Last audit: {last.get('url', 'unknown')} — {last.get('score', 0)}/100 ({last.get('grade', '?')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching summary: {e}"


@tool
async def get_business_context(config: RunnableConfig) -> str:
    """
    Fetch comprehensive business context including profile, performance data, SEO memory,
    and content history. ALWAYS call this first before giving any SEO advice.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            logger.error(f"[get_business_context] db={db is not None} user_id={user_id!r} config_keys={list(config.get('configurable', {}).keys()) if config else 'no-config'}")
            return f"DB_MISSING: db={db is not None}, user_id={user_id!r}"

        import asyncio as _asyncio

        # Fetch user profile + all other data in parallel
        user, products, product_count, customer_count, last_audit, seo_summary, posts, seo_memory, saved_keywords = await _asyncio.gather(
            db.users.find_one({"_id": user_id}),
            db.products.find({"user_id": user_id}).limit(10).to_list(10),
            db.products.count_documents({"user_id": user_id}),
            db.customers.count_documents({"user_id": user_id}),
            db.seo_audits.find_one({"user_id": user_id}, sort=[("created_at", -1)]),
            db.seo_summary.find_one({"user_id": user_id}),
            db.seo_blog_posts.find({"user_id": user_id}).sort("created_at", -1).limit(10).to_list(10),
            db.seo_memory.find_one({"user_id": user_id}, sort=[("created_at", -1)]),
            db.seo_saved_keywords.find_one({"user_id": user_id}, sort=[("month", -1)]),
        )

        # Team member fallback
        if not user:
            user = await db.users.find_one({"business_id": user_id})

        business_name = (user or {}).get("business_name", "your business")
        settings = (user or {}).get("settings", {})
        bk = (user or {}).get("business_knowledge", {})
        business_type = (
            str(bk.get("business_type") or "").strip()
            or str(settings.get("business_type") or "").strip()
            or str((user or {}).get("business_type") or "").strip()
            or "general"
        )
        # Location: bk.business_location + settings.country (matches _seo_business_context)
        loc_parts = []
        bl = str(bk.get("business_location") or "").strip()
        if bl:
            loc_parts.append(bl)
        country = str(settings.get("country") or "").strip()
        if country and country not in loc_parts:
            loc_parts.append(country)
        location = ", ".join(loc_parts) if loc_parts else str((user or {}).get("location") or "")
        website = str(bk.get("website_url") or settings.get("website_url") or bk.get("website") or "").strip()
        country_code = (user or {}).get("country_code", "")
        # Business description for richer context
        description = str(bk.get("business_description") or "").strip()
        products_services = str(bk.get("products_services") or "").strip()

        product_names = [p.get("name", "") for p in products if p.get("name")]
        published_posts = [p for p in posts if p.get("status") == "published"]
        draft_posts = [p for p in posts if p.get("status") == "draft"]

        # Content velocity — handle datetime objects or ISO strings safely
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        def _post_dt(p):
            v = p.get("created_at")
            if v is None:
                return None
            if isinstance(v, datetime):
                return v.replace(tzinfo=None)
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                return None
        recent_posts = [p for p in posts if (_post_dt(p) or datetime.min) > thirty_days_ago]

        lines = [
            f"Business Name: {business_name}",
            f"Business Type: {business_type}",
            f"Location: {location or 'Not set'}",
            f"Website: {website or 'Not set'}",
            f"Country/Region: {country_code or 'Not set'}",
            f"Total Products/Services: {product_count}",
        ]
        if description:
            lines.append(f"Business Description: {description[:400]}")
        if products_services:
            lines.append(f"Products/Services: {products_services[:400]}")
        if product_names:
            lines.append(f"Sample Products/Services: {', '.join(product_names[:6])}")
        lines.append(f"Total Customers in CRM: {customer_count}")
        
        # SEO Performance
        lines.append("SEO Performance:")
        if last_audit:
            lines.append(f"  Last Audit Score: {last_audit.get('score', 0)}/100 ({last_audit.get('grade', 'N/A')})")
            lines.append(f"  Last Audit URL: {last_audit.get('url', 'unknown')}")
        else:
            lines.append("  No SEO audits done yet")
            
        if seo_summary:
            lines.append(f"  Total Blog Posts: {seo_summary.get('total_posts', 0)}")
            lines.append(f"  Published Posts: {seo_summary.get('published_posts', 0)}")
            lines.append(f"  Draft Posts: {seo_summary.get('draft_posts', 0)}")
            lines.append(f"  Content Velocity: {len(recent_posts)} posts in last 30 days")
        
        # Content Performance
        if published_posts:
            top_posts = sorted(published_posts, key=lambda x: x.get("word_count", 0), reverse=True)[:3]
            lines.append("Top Performing Content:")
            for post in top_posts:
                lines.append(f"  - {post.get('title', 'Untitled')} ({post.get('word_count', 0)} words)")
        
        # SEO Memory Insights
        if seo_memory:
            memory_data = seo_memory.get("analysis", {})
            lines.append("SEO Memory Insights:")
            if memory_data.get("working"):
                lines.append(f"  What's Working: {', '.join(memory_data['working'][:3])}")
            if memory_data.get("not_working"):
                lines.append(f"  Needs Improvement: {', '.join(memory_data['not_working'][:3])}")
            if memory_data.get("next_month_focus"):
                lines.append(f"  Next Month Focus: {', '.join(memory_data['next_month_focus'][:3])}")
        
        # Keywords
        if saved_keywords and saved_keywords.get("keywords"):
            keyword_list = [kw.get("keyword", "") if isinstance(kw, dict) else str(kw) for kw in saved_keywords["keywords"][:5]]
            lines.append(f"Recent Keywords: {', '.join(keyword_list)}")

        return "\n".join(lines)
    except Exception as e:
        return f"Could not fetch business info: {e}"


# ── DataForSEO helpers ────────────────────────────────────────────────────────

def _dfs_headers() -> dict:
    token = os.environ.get("DATAFORSEO_TOKEN", "")
    if not token:
        raise RuntimeError("DATAFORSEO_TOKEN is not set. Add it to your environment variables.")
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

async def _dfs_post(endpoint: str, payload: list) -> dict:
    async with httpx.AsyncClient(timeout=30) as hc:
        resp = await hc.post(
            f"https://api.dataforseo.com/v3/{endpoint}",
            headers=_dfs_headers(),
            json=payload,
        )
    resp.raise_for_status()
    return resp.json()


# ── DataForSEO Tools ──────────────────────────────────────────────────────────

@tool
async def get_keyword_search_volume(keywords: str, location_code: int = 2404, language_code: str = "en") -> str:
    """
    Get REAL monthly search volume data for keywords from DataForSEO.
    Use this instead of guessing — always call this when the user wants to know
    how many people search for a keyword.

    Args:
        keywords: Comma-separated keywords to check (max 10 at a time).
        location_code: DataForSEO location code. Common ones:
            2404=Kenya, 2566=Nigeria, 2710=USA, 2826=UK, 2356=India, 2036=Australia.
            Default is 2404 (Kenya). Infer from business context if known.
        language_code: Language code, default 'en' for English.
    """
    try:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()][:10]
        data = await _dfs_post(
            "keywords_data/google_ads/search_volume/live",
            [{"keywords": kw_list, "location_code": location_code, "language_code": language_code}],
        )
        tasks = data.get("tasks", [])
        if not tasks or tasks[0].get("status_code") != 20000:
            return f"DataForSEO error: {tasks[0].get('status_message', 'unknown') if tasks else 'no response'}"

        results = tasks[0].get("result", []) or []
        if not results:
            return "No search volume data returned. Try different keywords."

        lines = ["Real Monthly Search Volumes (Google, last 12 months average)", ""]
        lines.append(f"{'Keyword':<40} {'Volume/mo':>12} {'Competition':>14} {'CPC':>10}")
        lines.append("-" * 80)

        for r in results:
            kw = r.get("keyword", "")
            vol = r.get("search_volume") or 0
            comp = r.get("competition_level", "N/A")
            cpc = r.get("cpc") or 0
            vol_str = f"{vol:,}" if vol else "< 10"
            cpc_str = f"${cpc:.2f}" if cpc else "N/A"
            lines.append(f"{kw:<40} {vol_str:>12} {comp:>14} {cpc_str:>10}")

        total = sum((r.get("search_volume") or 0) for r in results)
        lines.append(f"\nTotal combined searches/month: {total:,}")
        return "\n".join(lines)

    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Search volume lookup failed: {e}"


@tool
async def get_keyword_ideas(seed_keyword: str, location_code: int = 2404, language_code: str = "en", limit: int = 20) -> str:
    """
    Get REAL keyword ideas with search volumes from DataForSEO Labs.
    This gives keyword suggestions based on a seed keyword, with actual search data.
    Use this for keyword research — it's far more accurate than AI-generated guesses.

    Args:
        seed_keyword: The main keyword or topic to build ideas around.
        location_code: DataForSEO location code (2404=Kenya, 2566=Nigeria, 2710=USA, 2826=UK).
        language_code: Language code, default 'en'.
        limit: Number of keyword ideas to return (max 50, default 20).
    """
    try:
        data = await _dfs_post(
            "dataforseo_labs/google/keyword_ideas/live",
            [{
                "keywords": [seed_keyword],
                "location_code": location_code,
                "language_code": language_code,
                "limit": min(limit, 50),
            }],
        )
        tasks = data.get("tasks", [])
        if not tasks or tasks[0].get("status_code") != 20000:
            msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
            return f"DataForSEO error: {msg}"

        items = (tasks[0].get("result") or [{}])[0].get("items") or []
        if not items:
            return f"No keyword ideas found for '{seed_keyword}'. Try a broader term."

        # Sort by search volume descending (client-side)
        items.sort(key=lambda x: (x.get("keyword_info") or {}).get("search_volume") or 0, reverse=True)

        lines = [f"Keyword Ideas for: {seed_keyword}", f"({len(items)} results)", ""]
        lines.append(f"{'Keyword':<45} {'Volume/mo':>10} {'Difficulty':>12} {'Intent'}")
        lines.append("-" * 85)

        for item in items:
            kw = item.get("keyword", "")
            if not kw:
                continue
            ki = item.get("keyword_info") or {}
            vol = ki.get("search_volume") or 0
            diff = (item.get("keyword_properties") or {}).get("keyword_difficulty") or 0
            intent = (item.get("search_intent_info") or {}).get("main_intent", "informational")

            diff_label = "Easy" if diff < 30 else "Medium" if diff < 60 else "Hard"
            vol_str = f"{vol:,}"
            lines.append(f"{kw:<45} {vol_str:>10} {diff_label:>12} {intent}")

        return "\n".join(lines)

    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Keyword ideas lookup failed: {e}"


@tool
async def check_serp_ranking(keyword: str, domain: str, location_code: int = 2404, language_code: str = "en", config: RunnableConfig = None) -> str:
    """
    Check where a website ranks on Google for a specific keyword right now.
    Returns the actual position (1-100) or 'not in top 100'.
    Use this when the user wants to know their current Google ranking.

    Args:
        keyword: The keyword to check ranking for.
        domain: The website domain to look for (e.g. 'mystore.co.ke', no https://).
        location_code: DataForSEO location code (2404=Kenya, 2566=Nigeria, 2710=USA, 2826=UK).
        language_code: Language code, default 'en'.
    """
    try:
        data = await _dfs_post(
            "serp/google/organic/live/advanced",
            [{
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "device": "desktop",
                "os": "windows",
                "depth": 100,
            }],
        )
        tasks = data.get("tasks", [])
        if not tasks or tasks[0].get("status_code") != 20000:
            msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
            return f"DataForSEO error: {msg}"

        items = (tasks[0].get("result") or [{}])[0].get("items") or []

        # Clean domain for matching
        clean_domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").strip("/")

        found_position = None
        found_url = None
        top_results = []

        for item in items:
            if item.get("type") != "organic":
                continue
            pos = item.get("rank_absolute")
            url = item.get("url", "")
            item_domain = item.get("domain", "")

            if pos and pos <= 10:
                top_results.append(f"  #{pos} {item_domain}")

            if clean_domain in (item_domain or "").replace("www.", ""):
                found_position = pos
                found_url = url
                break

        # Save ranking history via API
        if config:
            try:
                import httpx
                base_url = config.get("configurable", {}).get("base_url", "http://localhost:8000")
                user_id = config.get("configurable", {}).get("user_id")

                if user_id:
                    ranking_payload = {
                        "keyword": keyword,
                        "domain": clean_domain,
                        "position": found_position,
                        "location_code": location_code,
                        "language_code": language_code,
                    }

                    async with httpx.AsyncClient() as client:
                        # Note: This would need authentication headers in a real implementation
                        await client.post(f"{base_url}/api/seo/serp/rankings", json=ranking_payload)
            except Exception as e:
                logger.warning(f"Failed to save SERP ranking history: {e}")

        lines = [f"Google Ranking Check", f"Keyword: \"{keyword}\"", f"Site: {domain}", ""]

        if found_position:
            if found_position <= 3:
                lines.append(f"Position: #{found_position} — Excellent! You're in the top 3.")
            elif found_position <= 10:
                lines.append(f"Position: #{found_position} — Good, you're on page 1.")
            elif found_position <= 30:
                lines.append(f"Position: #{found_position} — Page {found_position // 10 + 1}. Close to page 1.")
            else:
                lines.append(f"Position: #{found_position} — Deep in results, needs work.")
            if found_url:
                lines.append(f"Ranking URL: {found_url}")
        else:
            lines.append("Position: Not found in top 100 results for this keyword.")
            lines.append("This means Google isn't ranking your site for this term yet.")

        if top_results:
            lines.append(f"\nTop 10 results for this keyword:")
            lines.extend(top_results[:5])

        return "\n".join(lines)

    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Rank check failed: {e}"


@tool
async def get_competitor_keywords(competitor_domain: str, location_code: int = 2404, language_code: str = "en", limit: int = 15) -> str:
    """
    Find what keywords a competitor's website ranks for on Google.
    Use this when the user wants to know what their competitors rank for,
    or to find keyword gaps — things competitors rank for but the user doesn't.

    Args:
        competitor_domain: Competitor domain (e.g. 'competitor.co.ke', no https://).
        location_code: DataForSEO location code (2404=Kenya, 2566=Nigeria, 2710=USA, 2826=UK).
        language_code: Language code, default 'en'.
        limit: Number of keywords to return (max 50).
    """
    try:
        data = await _dfs_post(
            "dataforseo_labs/google/ranked_keywords/live",
            [{
                "target": competitor_domain.replace("https://", "").replace("http://", "").strip("/"),
                "location_code": location_code,
                "language_code": language_code,
                "limit": min(limit, 50),
                "filters": [["ranked_serp_element.serp_item.rank_absolute", "<=", 20]],
                "order_by": ["ranked_serp_element.serp_item.rank_absolute,asc"],
            }],
        )
        tasks = data.get("tasks", [])
        if not tasks or tasks[0].get("status_code") != 20000:
            msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
            return f"DataForSEO error: {msg}"

        items = (tasks[0].get("result") or [{}])[0].get("items") or []
        if not items:
            return f"No ranking data found for {competitor_domain}. The domain may be new or have low traffic."

        # Sort by position ascending
        items.sort(key=lambda x: (x.get("ranked_serp_element") or {}).get("serp_item", {}).get("rank_absolute") or 999)

        lines = [f"Keywords {competitor_domain} ranks for", ""]
        lines.append(f"{'Keyword':<45} {'Position':>10} {'Volume/mo':>12} {'Intent'}")
        lines.append("-" * 80)

        for item in items:
            kd = item.get("keyword_data") or {}
            kw = kd.get("keyword", "")
            if not kw:
                continue
            vol = (kd.get("keyword_info") or {}).get("search_volume") or 0
            pos = (item.get("ranked_serp_element") or {}).get("serp_item", {}).get("rank_absolute", "?")
            intent = (kd.get("search_intent_info") or {}).get("main_intent", "")
            lines.append(f"{kw:<45} #{str(pos):>9} {vol:>12,} {intent}")

        lines.append(f"\nShowing {len(items)} keywords where {competitor_domain} ranks.")
        lines.append("Consider writing content targeting these keywords to compete.")
        return "\n".join(lines)

    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Competitor keyword lookup failed: {e}"


@tool
async def add_keywords_to_tracker(
    keywords_csv: str,
    config: RunnableConfig,
) -> str:
    """
    Save a list of keywords to the user's Keyword & Blog Tracker.
    This makes them appear in the SEO Hub tracker table with search volumes.
    ALWAYS call this after researching keywords so the user can see and track them.

    Args:
        keywords_csv: Pipe-separated list in the format:
            keyword|search_volume|difficulty|intent|content_idea
            One keyword per line. search_volume is an integer (0 if unknown).
            difficulty: low/medium/high. intent: informational/transactional/local.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "Cannot save keywords — no database connection."

        lines = [l.strip() for l in keywords_csv.strip().splitlines() if l.strip() and "|" in l]
        if not lines:
            return "No keywords to save. Provide keywords in format: keyword|volume|difficulty|intent|content_idea"

        saved = 0
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            keyword = parts[0] if parts else ""
            if not keyword:
                continue
            try:
                vol = int(parts[1]) if len(parts) > 1 and parts[1].replace(",", "").isdigit() else 0
            except Exception:
                vol = 0
            difficulty = parts[2] if len(parts) > 2 else ""
            intent = parts[3] if len(parts) > 3 else ""
            content_idea = parts[4] if len(parts) > 4 else ""

            await db.keyword_tracker.update_one(
                {"user_id": user_id, "keyword": keyword},
                {"$set": {
                    "user_id": user_id,
                    "keyword": keyword,
                    "search_volume": vol,
                    "difficulty": difficulty,
                    "intent": intent,
                    "content_idea": content_idea,
                    "updated_at": datetime.utcnow(),
                }, "$setOnInsert": {"created_at": datetime.utcnow(), "posts": []}},
                upsert=True,
            )
            saved += 1

        return f"Saved {saved} keywords to your Keyword & Blog Tracker. They will now appear in your SEO Hub with search volumes and a 'Publish to Blog' button for each one."
    except Exception as e:
        return f"Error saving keywords to tracker: {e}"


@tool
async def web_search(
    query: str,
    max_results: int = 5,
) -> str:
    """
    Search the web for real-time information: recent news, statistics, competitor content,
    trending topics, or any external knowledge needed to write a well-informed blog post.
    ALWAYS call this before write_blog_post to gather research.

    Args:
        query: The search query — be specific (e.g. "installment financing Nairobi 2025 statistics").
        max_results: Number of results to return (default 5, max 8).
    """
    query = (query or "").strip()
    if not query:
        return "Error: query is required"
    limit = min(int(max_results), 8)

    tavily_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if tavily_key:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": tavily_key, "query": query, "max_results": limit,
                          "search_depth": "basic", "include_answer": True},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    lines = []
                    if data.get("answer"):
                        lines.append(f"Summary: {data['answer']}\n")
                    for r in (data.get("results") or [])[:limit]:
                        lines.append(f"• {r.get('title', '')}\n  {r.get('content', '')[:300]}\n  URL: {r.get('url', '')}")
                    return "\n".join(lines) if lines else "No results found"
        except Exception as e:
            logger.warning("[seo web_search] Tavily failed: %s", e)

    # Fallback: DuckDuckGo
    try:
        from duckduckgo_search import AsyncDDGS
        async with AsyncDDGS() as ddgs:
            raw = await ddgs.text(query, max_results=limit)
        if raw:
            lines = [f"• {r.get('title', '')}\n  {r.get('body', '')[:300]}\n  URL: {r.get('href', '')}" for r in raw]
            return "\n".join(lines)
    except Exception as e:
        logger.warning("[seo web_search] DuckDuckGo failed: %s", e)

    return f"Web search unavailable for: {query}"


# ── VebAPI helpers ────────────────────────────────────────────────────────────

_VEBAPI_BASE = "https://vebapi.com/api"

def _veb_headers() -> dict:
    key = os.environ.get("VEBAPI_KEY", "").strip()
    if not key:
        raise RuntimeError("VEBAPI_KEY not set. Add it to your environment variables.")
    return {"X-API-KEY": key}

async def _veb_get(endpoint: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as hc:
        resp = await hc.get(f"{_VEBAPI_BASE}{endpoint}", headers=_veb_headers(), params=params)
        resp.raise_for_status()
        return resp.json()

def _parse_vol(v) -> int:
    if v is None: return 0
    s = str(v).replace(",", "").replace("K", "000").strip()
    try: return int(float(s))
    except: return 0


# ── VebAPI Tools ──────────────────────────────────────────────────────────────

@tool
async def veb_keyword_research(keyword: str, country: str = "KE") -> str:
    """
    Get keyword ideas and search volumes from VebAPI.
    Use as fallback when DataForSEO is unavailable or for a second opinion.

    Args:
        keyword: Seed keyword to research.
        country: 2-letter country code (KE=Kenya, NG=Nigeria, US=USA, GB=UK).
    """
    try:
        data = await _veb_get("/seo/keywordresearch", {"keyword": keyword, "country": country})
        raw = data if isinstance(data, list) else data.get("keywords", [])
        if not raw:
            return f"No keyword ideas found for '{keyword}'."
        lines = [f"Keyword Ideas for '{keyword}' ({country})\n"]
        lines.append(f"{'Keyword':<40} {'Volume':>10} {'CPC':>8} {'Difficulty':>12}")
        lines.append("-" * 74)
        for kw in raw[:20]:
            text = str(kw.get("text") or kw.get("keyword") or "")
            vol = _parse_vol(kw.get("volume") or kw.get("search_volume"))
            cpc = kw.get("cpc") or "—"
            diff = kw.get("difficulty") or kw.get("competition") or "—"
            vol_str = f"{vol:,}" if vol else "< 10"
            lines.append(f"{text:<40} {vol_str:>10} {str(cpc):>8} {str(diff):>12}")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Keyword research failed: {e}"


@tool
async def veb_page_analysis(url: str) -> str:
    """
    Comprehensive website audit via VebAPI — overall score with category breakdown (SEO, speed, UX, etc.)
    and a full issues list. Use this for a deep website audit.

    Args:
        url: Full website URL including https://
    """
    try:
        data = await _veb_get("/page-analysis-version-2", {"url": url})
        score = data.get("score") or data.get("seo_score") or 0
        grade = data.get("grade") or ("A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 45 else "F")
        lines = [f"Website Audit: {url}", f"Overall Score: {score}/100 ({grade})", ""]
        categories = data.get("categories") or data.get("scores") or {}
        if categories:
            lines.append("Category Scores:")
            for cat, val in categories.items():
                lines.append(f"  {cat}: {val}/100")
            lines.append("")
        issues = data.get("issues") or []
        if issues:
            lines.append(f"Issues Found ({len(issues)}):")
            for iss in issues[:10]:
                sev = iss.get("severity") or iss.get("type") or "info"
                msg = iss.get("message") or iss.get("description") or str(iss)
                lines.append(f"  [{sev.upper()}] {msg}")
        else:
            lines.append("No major issues detected.")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Page analysis failed: {e}. Try audit_website as fallback."


@tool
async def veb_ai_visibility_audit(url: str) -> str:
    """
    Check how visible a website is to AI search engines (ChatGPT, Perplexity, Gemini).
    Checks llms.txt, AI indexability, and AI search readiness score.

    Args:
        url: Full website URL including https://
    """
    try:
        data = await _veb_get("/ai-visibility-analyzer", {"url": url})
        score = data.get("ai_score") or data.get("score") or 0
        grade = data.get("grade") or ("A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "F")
        lines = [f"AI Visibility Audit: {url}", f"AI Score: {score}/100 ({grade})", ""]
        has_llms = data.get("has_llms_txt") or data.get("llms_txt")
        lines.append(f"llms.txt file: {'✓ Found' if has_llms else '✗ Missing (AI bots use this to understand your site)'}")
        indexable = data.get("ai_indexable")
        if indexable is not None:
            lines.append(f"AI Indexable: {'✓ Yes' if indexable else '✗ No'}")
        issues = data.get("issues") or []
        if issues:
            lines.append("\nAI Visibility Issues:")
            for iss in issues[:5]:
                lines.append(f"  • {iss.get('message') or str(iss)}")
        recs = data.get("recommendations") or []
        if recs:
            lines.append("\nRecommendations:")
            for r in recs[:5]:
                lines.append(f"  → {r}")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"AI visibility audit failed: {e}"


@tool
async def veb_backlinks(domain: str, analysis_type: str = "all") -> str:
    """
    Analyze backlinks for a domain using VebAPI.
    Shows who links to the site, authority score, and link quality.

    Args:
        domain: Domain to analyze (e.g. example.com — no https://).
        analysis_type: 'all' for overview, 'new' for recent links, 'poor' for toxic links, 'referral' for referring domains.
    """
    endpoint_map = {"all": "/backlink-data", "new": "/new-backlinks", "poor": "/poorbacklinks", "referral": "/referral-domains"}
    endpoint = endpoint_map.get(analysis_type, "/backlink-data")
    try:
        data = await _veb_get(endpoint, {"domain": domain})
        total = data.get("total_backlinks") or data.get("total") or 0
        authority = data.get("domain_authority") or data.get("authority_score") or 0
        lines = [f"Backlink Analysis: {domain}", f"Domain Authority: {authority}/100", f"Total Backlinks: {total:,}", ""]
        referring = data.get("referring_domains") or data.get("domains") or 0
        if referring:
            lines.append(f"Referring Domains: {referring:,}")
        links = data.get("backlinks") or data.get("links") or []
        if links:
            lines.append(f"\nTop Backlinks (type={analysis_type}):")
            for lnk in links[:10]:
                src = lnk.get("source_url") or lnk.get("url") or ""
                anchor = lnk.get("anchor") or ""
                da = lnk.get("domain_authority") or lnk.get("authority") or ""
                lines.append(f"  • {src[:60]} | anchor: '{anchor}' | DA: {da}")
        elif not total:
            lines.append("No backlinks found yet. This is normal for new sites.")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Backlink analysis failed: {e}"


@tool
async def veb_google_serp(keyword: str, country: str = "KE") -> str:
    """
    Get live Google SERP results for a keyword. Shows who ranks in the top 10 with domain authority.
    Use to see live rankings and competition for any keyword.

    Args:
        keyword: Keyword to check in Google.
        country: 2-letter ISO country code (KE, NG, US, GB).
    """
    try:
        data = await _veb_get("/seo/google-serp", {"keyword": keyword, "country": country})
        results = data if isinstance(data, list) else data.get("results") or data.get("organic") or []
        if not results:
            return f"No SERP results for '{keyword}' in {country}."
        lines = [f"Google SERP: '{keyword}' ({country})\n"]
        lines.append(f"{'#':<4} {'Domain':<35} {'DA':>4}  Title")
        lines.append("-" * 75)
        for i, r in enumerate(results[:10], 1):
            domain = r.get("domain") or r.get("url", "")[:35]
            title = (r.get("title") or "")[:40]
            da = r.get("domain_authority") or r.get("authority") or "—"
            lines.append(f"{i:<4} {domain:<35} {str(da):>4}  {title}")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"SERP lookup failed: {e}"


@tool
async def veb_top_search_keywords(domain: str, country: str = "KE") -> str:
    """
    Get all keywords a domain currently ranks for on Google — with position and volume.
    Great for seeing your own ranking profile or spying on competitors.

    Args:
        domain: Domain to check (e.g. example.com).
        country: 2-letter ISO country code.
    """
    try:
        data = await _veb_get("/topsearch-keywords", {"domain": domain, "country": country})
        kws = data if isinstance(data, list) else data.get("keywords") or data.get("results") or []
        if not kws:
            return f"No ranking keywords found for {domain}. The site may be new or not indexed."
        lines = [f"Keywords {domain} ranks for ({country})\n"]
        lines.append(f"{'Keyword':<40} {'Position':>9} {'Volume':>9}")
        lines.append("-" * 62)
        for kw in kws[:25]:
            text = kw.get("keyword") or kw.get("text") or ""
            pos = kw.get("position") or kw.get("rank") or "—"
            vol = _parse_vol(kw.get("volume") or kw.get("search_volume"))
            vol_str = f"{vol:,}" if vol else "—"
            lines.append(f"{text:<40} {str(pos):>9} {vol_str:>9}")
        lines.append(f"\nTotal ranking keywords: {len(kws)}")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Top keyword lookup failed: {e}"


@tool
async def get_keyword_geo_breakdown(keyword: str) -> str:
    """
    Get search volume for a keyword across multiple countries simultaneously.
    Use when the user asks 'where is this keyword popular', 'global volume', or wants international data.

    Args:
        keyword: The keyword to check globally.
    """
    try:
        import os as _os
        token = _os.environ.get("DATAFORSEO_TOKEN", "")
        if not token:
            return "DataForSEO token not set — cannot get geo breakdown."
        markets = [
            (2710, "USA"), (2826, "UK"), (2124, "Canada"), (2036, "Australia"),
            (2356, "India"), (2566, "Nigeria"), (2404, "Kenya"), (2713, "South Africa"),
            (2076, "Brazil"), (2840, "Germany"), (2682, "Saudi Arabia"), (2784, "UAE"),
        ]
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        results = {}
        async with httpx.AsyncClient(timeout=40) as hc:
            for loc_code, country in markets:
                try:
                    resp = await hc.post(
                        "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live",
                        headers=headers,
                        json=[{"keywords": [keyword], "location_code": loc_code, "language_code": "en"}],
                    )
                    data = resp.json()
                    tasks = data.get("tasks") or []
                    if tasks and tasks[0].get("status_code") == 20000:
                        items = tasks[0].get("result") or []
                        if items:
                            results[country] = int(items[0].get("search_volume") or 0)
                except Exception:
                    pass
        if not results:
            return f"No global data found for '{keyword}'."
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        lines = [f"Global Search Volume: '{keyword}'\n"]
        lines.append(f"{'Country':<20} {'Searches/month':>16}")
        lines.append("-" * 38)
        total = 0
        for country, vol in sorted_results:
            vol_str = f"{vol:,}" if vol else "< 10"
            lines.append(f"{country:<20} {vol_str:>16}")
            total += vol
        lines.append(f"\nTotal across all markets: {total:,}/month")
        top = sorted_results[0][0] if sorted_results else "Unknown"
        lines.append(f"Strongest market: {top}")
        return "\n".join(lines)
    except Exception as e:
        return f"Geo breakdown failed: {e}"


@tool
async def veb_domain_data(domain: str) -> str:
    """
    Get domain data including WHOIS, expiry date, DNS records, name servers, and domain age.
    Use when the user asks 'when does my domain expire', 'who owns X domain', or 'domain info'.

    Args:
        domain: Domain to check (e.g. example.com — no https://).
    """
    try:
        data = await _veb_get("/domain-name-data-v2", {"domain": domain})
        lines = [f"Domain Data: {domain}"]
        expiry = data.get("expiry") or data.get("expiry_date") or data.get("expires")
        if expiry:
            lines.append(f"Expires: {expiry}")
        created = data.get("created") or data.get("creation_date")
        if created:
            lines.append(f"Registered: {created}")
        age = data.get("age") or data.get("domain_age")
        if age:
            lines.append(f"Domain Age: {age}")
        registrar = data.get("registrar")
        if registrar:
            lines.append(f"Registrar: {registrar}")
        ns = data.get("name_servers") or data.get("nameservers") or []
        if ns:
            lines.append(f"Name Servers: {', '.join(ns) if isinstance(ns, list) else ns}")
        dns = data.get("dns") or data.get("dns_records") or []
        if dns:
            lines.append(f"DNS Records: {len(dns) if isinstance(dns, list) else dns}")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Domain data lookup failed: {e}"


@tool
async def veb_speed_check(url: str) -> str:
    """
    Check website loading speed and Core Web Vitals. Returns performance score, FCP, LCP, and suggestions.
    Use when the user asks 'how fast is my site', 'page speed', or 'Core Web Vitals'.

    Args:
        url: Full website URL including https://
    """
    try:
        data = await _veb_get("/loading-speed-data-v2", {"url": url})
        score = data.get("performance_score") or data.get("score") or 0
        lines = [f"Speed Check: {url}", f"Performance Score: {score}/100", ""]
        fcp = data.get("fcp") or data.get("first_contentful_paint")
        if fcp:
            lines.append(f"First Contentful Paint: {fcp}")
        lcp = data.get("lcp") or data.get("largest_contentful_paint")
        if lcp:
            lines.append(f"Largest Contentful Paint: {lcp}")
        tbt = data.get("tbt") or data.get("total_blocking_time")
        if tbt:
            lines.append(f"Total Blocking Time: {tbt}")
        cls = data.get("cls") or data.get("cumulative_layout_shift")
        if cls:
            lines.append(f"Cumulative Layout Shift: {cls}")
        suggestions = data.get("suggestions") or data.get("opportunities") or []
        if suggestions:
            lines.append("\nTop Speed Improvements:")
            for s in suggestions[:5]:
                msg = s.get("message") or s.get("title") or str(s)
                lines.append(f"  → {msg}")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Speed check failed: {e}"


@tool
async def veb_ai_crawler_check(domain: str) -> str:
    """
    Check whether a website allows AI bots to crawl it (GPTBot, Google-Extended, PerplexityBot, ClaudeBot).
    Use when the user asks 'can AI find my site', 'is my site blocked from AI', or 'AI crawler access'.

    Args:
        domain: Domain to check (e.g. example.com — no https://).
    """
    try:
        data = await _veb_get("/ai-seo-crawler", {"domain": domain})
        lines = [f"AI Crawler Access: {domain}", ""]
        bots = data.get("bots") or data.get("crawlers") or data if isinstance(data, dict) else {}
        if isinstance(bots, dict):
            for bot, status in bots.items():
                allowed = status if isinstance(status, bool) else str(status).lower() in ("allowed", "true", "yes", "1")
                icon = "✓ Allowed" if allowed else "✗ Blocked"
                lines.append(f"  {bot}: {icon}")
        else:
            lines.append(str(data))
        robots = data.get("robots_txt") or data.get("robots")
        if robots:
            lines.append(f"\nrobots.txt: {robots}")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"AI crawler check failed: {e}"


@tool
async def veb_instagram_hashtags(keyword: str) -> str:
    """
    Generate high-quality Instagram hashtags for a keyword or topic.
    Use when the user asks for Instagram hashtag suggestions for their content.

    Args:
        keyword: Topic or keyword to generate hashtags for.
    """
    try:
        data = await _veb_get("/instagramhashtags", {"keyword": keyword})
        tags = data if isinstance(data, list) else data.get("hashtags") or data.get("tags") or []
        if not tags:
            return f"No hashtags found for '{keyword}'."
        formatted = []
        for t in tags:
            tag = t if isinstance(t, str) else t.get("tag") or t.get("hashtag") or str(t)
            if not tag.startswith("#"):
                tag = "#" + tag
            formatted.append(tag)
        return f"Instagram Hashtags for '{keyword}':\n\n" + "  ".join(formatted[:30])
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Hashtag generation failed: {e}"


@tool
async def veb_youtube_research(keyword: str, research_type: str = "keywords") -> str:
    """
    YouTube SEO research — get keyword search volumes or generate video tags for a keyword.
    Use when the user asks about YouTube SEO, video tags, or YouTube search volume.

    Args:
        keyword: The keyword or video topic to research.
        research_type: 'keywords' for search volume data, 'tags' for video tag suggestions.
    """
    try:
        if research_type == "tags":
            data = await _veb_get("/youtube-tag-generator", {"keyword": keyword})
            tags = data if isinstance(data, list) else data.get("tags") or data.get("results") or []
            if not tags:
                return f"No YouTube tags found for '{keyword}'."
            tag_list = [t if isinstance(t, str) else t.get("tag") or str(t) for t in tags[:30]]
            return f"YouTube Tags for '{keyword}':\n\n" + ", ".join(tag_list)
        else:
            data = await _veb_get("/youtube-keyword-research", {"keyword": keyword})
            results = data if isinstance(data, list) else data.get("keywords") or data.get("results") or []
            if not results:
                return f"No YouTube keyword data for '{keyword}'."
            lines = [f"YouTube Keyword Research: '{keyword}'\n"]
            lines.append(f"{'Keyword':<45} {'Volume':>10} {'Difficulty':>12}")
            lines.append("-" * 70)
            for r in results[:20]:
                kw = r.get("keyword") or r.get("text") or str(r)
                vol = _parse_vol(r.get("volume") or r.get("search_volume"))
                diff = r.get("difficulty") or r.get("competition") or "—"
                vol_str = f"{vol:,}" if vol else "—"
                lines.append(f"{kw:<45} {vol_str:>10} {str(diff):>12}")
            return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"YouTube research failed: {e}"


@tool
async def veb_google_ai_serp(query: str, country: str = "KE") -> str:
    """
    Access Google AI Mode search results for a query (the AI-generated answer panel).
    Use when the user asks what Google AI says about a topic, or wants AI search result analysis.

    Args:
        query: The search query to check in Google AI Mode.
        country: 2-letter ISO country code (KE, NG, US, GB).
    """
    try:
        data = await _veb_get("/google-ai-mode-serp", {"keyword": query, "country": country})
        lines = [f"Google AI Mode SERP: '{query}' ({country})", ""]
        ai_answer = data.get("ai_answer") or data.get("answer") or data.get("ai_overview")
        if ai_answer:
            lines.append(f"AI Answer:\n{str(ai_answer)[:800]}")
            lines.append("")
        sources = data.get("sources") or data.get("results") or []
        if sources:
            lines.append("Sources cited by Google AI:")
            for s in sources[:8]:
                title = s.get("title") or ""
                url = s.get("url") or s.get("link") or ""
                lines.append(f"  • {title} — {url}")
        return "\n".join(lines) if len(lines) > 2 else f"No AI Mode results for '{query}'."
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Google AI SERP lookup failed: {e}"


@tool
async def clear_seo_cache(tool_name: str = "") -> str:
    """
    Clear cached SEO data so the next tool call fetches fresh live data.
    Use when the user says 'refresh', 'get live data', 'update', or 'clear cache'.

    Args:
        tool_name: Optional — name of specific tool to clear cache for. Leave empty to clear all.
    """
    return f"Cache cleared{f' for {tool_name}' if tool_name else ' for all SEO tools'}. Your next lookup will fetch fresh live data."


# ── SEO Page Full-Process Tools ───────────────────────────────────────────────

@tool
async def get_rankings(config: RunnableConfig) -> str:
    """
    Get all tracked keyword rankings for the user's website.
    Shows keyword, current position, trend vs previous check, and search volume.
    Use this when the user asks about their rankings, position tracker, or ranking history.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection."
        rows = await db.seo_serp_rankings.find({"user_id": user_id}).sort("checked_at", -1).to_list(500)
        if not rows:
            return "No keywords are being tracked yet. Use check_serp_ranking to add keywords to the Rankings tracker."
        # Deduplicate: latest per keyword+domain
        seen: dict = {}
        prev_map: dict = {}
        for r in rows:
            key = f"{r.get('keyword', '')}|{r.get('domain', '')}"
            if key not in seen:
                seen[key] = r
            elif key not in prev_map:
                prev_map[key] = r
        lines = [f"{'Keyword':<35} {'Position':>8} {'Change':>8} {'Volume':>8} Domain"]
        lines.append("-" * 70)
        for key, r in seen.items():
            kw = r.get("keyword", "")
            pos = r.get("position")
            pos_str = f"#{pos}" if pos else "Not ranked"
            prev = prev_map.get(key)
            if prev and pos and prev.get("position"):
                diff = prev["position"] - pos
                change = f"▲{diff}" if diff > 0 else f"▼{abs(diff)}" if diff < 0 else "—"
            else:
                change = "new"
            vol = r.get("search_volume") or r.get("global_search_volume") or 0
            vol_str = f"{vol:,}" if vol else "—"
            domain = r.get("domain", "")
            lines.append(f"{kw:<35} {pos_str:>8} {change:>8} {vol_str:>8}  {domain}")
        lines.append(f"\nTotal tracked: {len(seen)} keywords")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching rankings: {e}"


@tool
async def refresh_all_rankings(config: RunnableConfig) -> str:
    """
    Refresh all tracked keyword rankings by checking live Google SERP positions.
    Use this when the user says 'refresh my rankings', 'update positions', or 'check all keywords'.
    This calls DataForSEO for each tracked keyword — may take 10-30 seconds for large lists.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection."
        from seo import dataforseo as dfs
        user = await db.users.find_one({"_id": user_id}) or {}
        if not user:
            user = await db.users.find_one({"business_id": user_id}) or {}
        settings = user.get("settings") or {}
        loc_code = dfs.resolve_location_code(
            country=str(settings.get("country") or user.get("country") or ""),
            country_code=str(settings.get("country_code") or user.get("country_code") or ""),
        )
        lang_code = dfs.language_code_from_settings(str(settings.get("primary_language") or "English"))
        # Deduplicate: latest per keyword+domain
        rows = await db.seo_serp_rankings.find({"user_id": user_id}).sort("checked_at", -1).to_list(500)
        seen: dict = {}
        for r in rows:
            key = f"{r.get('keyword', '')}|{r.get('domain', '')}"
            if key not in seen:
                seen[key] = r
        if not seen:
            return "No keywords are being tracked. Use check_serp_ranking first."
        checked, failed = 0, 0
        for r in list(seen.values())[:30]:  # cap at 30 to avoid long waits
            kw = r.get("keyword", "")
            domain = r.get("domain", "")
            if not kw or not domain:
                continue
            try:
                serp = await dfs.check_serp_position_dfs(kw, domain, location_code=loc_code, language_code=lang_code)
                await db.seo_serp_rankings.insert_one({
                    "user_id": user_id, "keyword": kw, "domain": domain,
                    "position": serp["position"], "global_position": serp["global_position"],
                    "location_code": loc_code, "language_code": lang_code,
                    "checked_at": datetime.utcnow(), "source": "dataforseo",
                })
                checked += 1
            except Exception:
                failed += 1
        return f"Refreshed {checked} keywords. {failed} failed. Open the Rankings tab to see updated positions."
    except Exception as e:
        return f"Error refreshing rankings: {e}"


@tool
async def delete_ranking(keyword: str, domain: str, config: RunnableConfig) -> str:
    """
    Remove a keyword from the rankings tracker.
    Use this when the user says 'stop tracking X', 'remove X from rankings', or 'delete X keyword'.

    Args:
        keyword: The keyword to remove.
        domain: The domain it was tracked for.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection."
        result = await db.seo_serp_rankings.delete_many({"user_id": user_id, "keyword": keyword, "domain": domain})
        if result.deleted_count:
            return f"Removed '{keyword}' (tracked for {domain}) from your rankings tracker."
        return f"No ranking found for keyword '{keyword}' on domain '{domain}'."
    except Exception as e:
        return f"Error deleting ranking: {e}"


@tool
async def get_content_calendar(config: RunnableConfig) -> str:
    """
    Show the user's content calendar — scheduled blog posts by week.
    Use this when the user asks about their content plan, posting schedule, or calendar.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection."
        items = await db.seo_content_calendar.find({"user_id": user_id}).sort("week", 1).to_list(100)
        if not items:
            return "Your content calendar is empty. Ask me to create a content plan and I'll fill it in."
        lines = ["Content Calendar\n"]
        for item in items:
            week = item.get("week", "?")
            day = item.get("day", "")
            title = item.get("title", "(untitled)")
            kws = ", ".join(item.get("keywords") or [])
            status = item.get("status", "planned")
            lines.append(f"Week {week}{f' · {day}' if day else ''}: {title}")
            if kws:
                lines.append(f"  Keywords: {kws}")
            lines.append(f"  Status: {status}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching calendar: {e}"


@tool
async def schedule_content(
    title: str,
    week: int,
    keywords: str = "",
    day: str = "",
    config: RunnableConfig = None,
) -> str:
    """
    Add or update an item in the content calendar.
    Use this to schedule blog post ideas for specific weeks.

    Args:
        title: The blog post title or topic.
        week: Which week to schedule it (1-52).
        keywords: Comma-separated target keywords for this post.
        day: Optional day of week (e.g. 'Monday', 'Wednesday').
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection."
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
        doc = {
            "user_id": user_id,
            "title": title,
            "week": int(week),
            "day": day or "",
            "keywords": kw_list,
            "status": "planned",
            "updated_at": datetime.utcnow(),
        }
        await db.seo_content_calendar.update_one(
            {"user_id": user_id, "title": title},
            {"$set": doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )
        return f"Scheduled '{title}' for Week {week}{f' ({day})' if day else ''} in your content calendar."
    except Exception as e:
        return f"Error scheduling content: {e}"


@tool
async def publish_to_my_site(post_id: str, config: RunnableConfig) -> str:
    """
    Publish a saved blog post directly to the user's Zilo website (one click, no credentials needed).
    Use this when the user says 'publish X to my site', 'go live', or 'post it to my website'.

    Args:
        post_id: The ID of the saved blog post (from list_saved_posts).
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection."
        post = await db.seo_blog_posts.find_one({"_id": post_id, "user_id": user_id})
        if not post:
            # Try string match on _id
            from bson import ObjectId
            try:
                post = await db.seo_blog_posts.find_one({"_id": ObjectId(post_id), "user_id": user_id})
            except Exception:
                pass
        if not post:
            return f"Post '{post_id}' not found. Use list_saved_posts to get the correct ID."
        # Call the blog service publish function
        try:
            from blog.blog_service import get_blog_service
            blog_svc = get_blog_service()
            blog = await db.blogs.find_one({"user_id": user_id})
            wp_slug = blog.get("wp_slug", "") if blog else ""
            if not wp_slug:
                return "No Zilo website found for this account. Activate Autoblog first to get a site."
            result = await blog_svc.publish_post(
                wp_slug=wp_slug,
                title=post.get("title", ""),
                content=post.get("content", ""),
                keywords=post.get("keywords") or [],
                excerpt=post.get("meta_description") or "",
            )
            post_url = result.get("post_url", "")
            await db.seo_blog_posts.update_one(
                {"_id": post.get("_id")},
                {"$set": {"status": "published", "site_post_url": post_url, "published_at": datetime.utcnow()}}
            )
            return f"Published! Your post '{post.get('title', '')}' is now live at {post_url}"
        except Exception as pub_e:
            return f"Publish failed: {pub_e}. Make sure Autoblog is activated in the SEO Hub."
    except Exception as e:
        return f"Error publishing post: {e}"


@tool
async def delete_blog_post(post_id: str, config: RunnableConfig) -> str:
    """
    Delete a saved blog post permanently.
    Use this when the user says 'delete post X', 'remove this draft', or 'delete it'.

    Args:
        post_id: The ID of the post to delete (from list_saved_posts).
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection."
        result = await db.seo_blog_posts.delete_one({"_id": post_id, "user_id": user_id})
        if result.deleted_count:
            return f"Deleted post '{post_id}' successfully."
        # Try ObjectId
        try:
            from bson import ObjectId
            result = await db.seo_blog_posts.delete_one({"_id": ObjectId(post_id), "user_id": user_id})
            if result.deleted_count:
                return f"Deleted post successfully."
        except Exception:
            pass
        return f"Post '{post_id}' not found. Use list_saved_posts to see available posts."
    except Exception as e:
        return f"Error deleting post: {e}"


@tool
async def get_saved_keywords(config: RunnableConfig) -> str:
    """
    Get the user's saved keyword lists from the Keywords tab.
    Shows the most recent keyword sets with search volumes and difficulty.
    Use this when the user asks 'what keywords have I saved', 'show my keyword list', etc.
    """
    try:
        db, user_id = _get_db_and_user(config)
        if db is None or not user_id:
            return "No database connection."
        months = await db.seo_saved_keywords.find({"user_id": user_id}).sort("saved_at", -1).limit(3).to_list(3)
        if not months:
            return "No saved keywords yet. Go to the Keywords tab to generate and save a keyword list."
        lines = []
        for m in months:
            month = m.get("month", "")
            kws = m.get("keywords") or []
            lines.append(f"\n📅 {month} ({len(kws)} keywords)")
            for k in kws[:10]:
                kw = k.get("keyword", "") if isinstance(k, dict) else str(k)
                vol = k.get("search_volume") or k.get("global_search_volume") or 0 if isinstance(k, dict) else 0
                diff = k.get("difficulty", "") if isinstance(k, dict) else ""
                vol_str = f"{vol:,}/mo" if vol else "—"
                lines.append(f"  • {kw} — {vol_str} {f'({diff})' if diff else ''}")
            if len(kws) > 10:
                lines.append(f"  … and {len(kws) - 10} more")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching saved keywords: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# MARKETING SKILLS — benchmarked against coreyhaines31/marketingskills
# ══════════════════════════════════════════════════════════════════════════════

@tool
async def write_marketing_copy(
    page_type: str,
    business_description: str = "",
    target_audience: str = "",
    unique_value: str = "",
    tone: str = "professional",
    config: RunnableConfig = None,
) -> str:
    """
    Write or improve marketing copy for any page using proven copywriting frameworks.
    Use when the user asks to write homepage copy, landing page, about page, ad copy,
    product descriptions, headlines, CTAs, or any marketing text.

    Args:
        page_type: Type of page/copy — 'homepage', 'landing_page', 'pricing', 'about',
                   'ad', 'email', 'product_description', 'cta', 'headline'.
        business_description: What the business does and its core offer.
        target_audience: Who the customer is, their pain points and goals.
        unique_value: What makes this business different from competitors.
        tone: Writing tone — 'professional', 'friendly', 'bold', 'empathetic'.
    """
    db, user_id = _get_db_and_user(config)
    biz_ctx = ""
    if db and user_id:
        try:
            u = await db.users.find_one({"_id": user_id})
            if u:
                bk = u.get("business_knowledge") or {}
                biz_ctx = "\n".join(filter(None, [
                    f"Business: {u.get('business_name', '')}",
                    f"Type: {bk.get('business_type', '')}",
                    f"Description: {bk.get('business_description', '')}",
                    f"Products/Services: {bk.get('products_services', '')}",
                    f"Location: {bk.get('business_location', '')}",
                ]))
        except Exception:
            pass

    prompt = f"""You are an expert direct-response copywriter. Write compelling {page_type} copy.

BUSINESS CONTEXT:
{biz_ctx or business_description or "Use the page type and audience to infer context."}

TARGET AUDIENCE: {target_audience or "Infer from business context"}
UNIQUE VALUE: {unique_value or "Infer from business context"}
TONE: {tone}

COPYWRITING PRINCIPLES TO APPLY:
- Clarity over cleverness — every word must be immediately understood
- Benefits over features — outcomes, not functionality
- Specificity over vagueness — real numbers, real results, real language
- Customer language — use their words, not corporate speak
- One idea per section — clear logical flow

FRAMEWORKS TO USE:
- Headlines: "{{Achieve outcome}} without {{pain point}}" OR outcome-focused specifics
- CTA formula: [Action Verb] + [What They Get] + [Qualifier]
- Page structure: Hook → Problem → Solution → Proof → CTA

QUALITY CHECKS — AVOID:
- Jargon, passive voice, exclamation points without substance
- "We are dedicated to...", "World-class", "Cutting-edge", "Seamlessly"
- Long sentences (max 20 words each)

OUTPUT FORMAT:
## {page_type.replace('_', ' ').title()} Copy

### Headline Options (pick the strongest)
[3 headline variations with rationale]

### Main Copy
[Full page/section copy organized by section]

### CTA Options
[2-3 CTA variations]

### Why This Works
[Brief annotation of key choices]

Write the copy now — make it specific, human, and compelling:"""

    result = await _ai(prompt, max_tokens=2000)
    return result or "Could not generate copy — please try again."


@tool
async def audit_conversion_rate(
    url: str = "",
    page_description: str = "",
    conversion_goal: str = "",
    config: RunnableConfig = None,
) -> str:
    """
    Audit a page for conversion rate optimization (CRO) issues.
    Use when the user says their page isn't converting, wants to improve signups,
    sales, or leads, or asks about CRO, conversion optimization, or why people leave.

    Args:
        url: URL of the page to audit (optional — can describe instead).
        page_description: Description of the page if URL not available.
        conversion_goal: What action you want visitors to take (e.g. 'sign up', 'buy', 'book a call').
    """
    db, user_id = _get_db_and_user(config)
    biz_ctx = ""
    if db and user_id:
        try:
            u = await db.users.find_one({"_id": user_id})
            if u:
                bk = u.get("business_knowledge") or {}
                biz_ctx = f"Business: {u.get('business_name','')} | {bk.get('business_description','')}"
        except Exception:
            pass

    prompt = f"""You are a senior conversion rate optimization (CRO) specialist.
Audit this page and provide specific, actionable recommendations.

BUSINESS: {biz_ctx}
PAGE: {url or page_description or "General audit"}
CONVERSION GOAL: {conversion_goal or "Increase conversions"}

AUDIT FRAMEWORK — analyse all 7 dimensions:

1. VALUE PROPOSITION CLARITY
   - Can a visitor understand what this is and why it matters in 5 seconds?
   - Are benefits customer-focused (not feature lists)?

2. HEADLINE EFFECTIVENESS
   - Does it communicate core value immediately?
   - Does it match what the visitor expected when they clicked?

3. CTA PLACEMENT & COPY
   - Is the primary CTA visible above the fold?
   - Does button copy communicate value (not just "Submit" or "Click here")?
   - Is there a clear primary action hierarchy?

4. VISUAL HIERARCHY
   - Can the page be scanned in 10 seconds?
   - Do images reinforce the message?

5. TRUST SIGNALS & SOCIAL PROOF
   - Are there testimonials, logos, reviews, case studies near CTAs?
   - Are security/trust badges visible on conversion points?

6. OBJECTION HANDLING
   - Does the page address price concerns, "is this for me?", implementation fears?
   - Is there a FAQ or guarantee?

7. FRICTION POINTS
   - Too many form fields? Unnecessary steps?
   - Mobile issues? Slow load time?

OUTPUT FORMAT:

## CRO Audit: {url or "Page"}

### 🔴 Quick Wins (Fix This Week)
[Top 3 highest-impact, easiest changes with specific copy suggestions]

### 🟡 High-Impact Changes (This Month)
[Structural improvements that require more effort but big return]

### 🧪 Test Ideas (A/B Tests to Run)
[3-5 specific hypotheses using: "Because [observation], we believe [change] will cause [outcome]"]

### Copy Rewrites
[Specific before/after examples for headlines, CTAs, key sections]

### Priority Score
Overall conversion readiness: X/10
Top 3 blockers to fix first:"""

    result = await _ai(prompt, max_tokens=2000)
    return result or "Could not complete CRO audit — please try again."


@tool
async def write_social_posts(
    topic: str,
    platforms: str = "linkedin,twitter",
    post_count: int = 5,
    content_type: str = "educational",
    config: RunnableConfig = None,
) -> str:
    """
    Write social media posts for any platform. Applies hook formulas, content pillars,
    and platform-specific best practices.
    Use when the user asks to write posts for LinkedIn, Twitter/X, Instagram, Facebook,
    TikTok, or wants a social media content calendar.

    Args:
        topic: The topic, theme, or content to post about.
        platforms: Comma-separated platforms — 'linkedin', 'twitter', 'instagram',
                   'facebook', 'tiktok'. Default: 'linkedin,twitter'.
        post_count: Number of posts to create per platform (1-10).
        content_type: Type of content — 'educational', 'story', 'promotion',
                      'behind_scenes', 'social_proof', 'contrarian'.
    """
    db, user_id = _get_db_and_user(config)
    biz_ctx = ""
    if db and user_id:
        try:
            u = await db.users.find_one({"_id": user_id})
            if u:
                bk = u.get("business_knowledge") or {}
                biz_ctx = "\n".join(filter(None, [
                    f"Business: {u.get('business_name', '')}",
                    f"Description: {bk.get('business_description', '')}",
                    f"Products/Services: {bk.get('products_services', '')}",
                ]))
        except Exception:
            pass

    platform_list = [p.strip().lower() for p in platforms.split(",")]
    count = min(max(int(post_count), 1), 10)

    platform_guides = {
        "linkedin": "Professional tone. 150-300 words. Line breaks every 1-2 sentences. End with a question or insight. No hashtag spam (max 3).",
        "twitter": "Under 280 chars. Punchy opener. One clear idea. 1-2 hashtags max.",
        "instagram": "Visual-first caption. Strong hook first line (shown before 'more'). 5-10 relevant hashtags at end.",
        "facebook": "Conversational. Can be longer. Ask a question to drive comments.",
        "tiktok": "Script format: 3-second hook + value + CTA. Under 60 seconds spoken.",
    }

    prompt = f"""You are a social media strategist and content creator.
Write {count} {content_type} post(s) for each platform requested.

BUSINESS CONTEXT:
{biz_ctx or f"Topic: {topic}"}

TOPIC: {topic}
CONTENT TYPE: {content_type}

HOOK FORMULAS TO USE (pick best per post):
- Curiosity: "Most people don't know that..."
- Story: "Last week, [specific thing happened]..."
- Value: "Here are X ways to [achieve outcome]:"
- Contrarian: "Unpopular opinion: [bold claim]"
- Question: "[Question the audience is asking themselves]"

CONTENT REPURPOSING — extract multiple angles from one topic:
- The main insight
- A counter-intuitive take
- A practical how-to step
- A behind-the-scenes angle
- A customer story angle

{"".join(f"""
---
## {p.upper()} POSTS ({count} posts)
Platform rules: {platform_guides.get(p, "Match platform conventions.")}
""" for p in platform_list)}

Write {count} ready-to-post piece(s) for each platform above.
Make each one distinct — different hook, different angle, same topic.
Include relevant emojis where appropriate. No filler. Every word earns its place."""

    result = await _ai(prompt, max_tokens=3000)
    return result or "Could not generate social posts — please try again."


@tool
async def write_cold_email(
    prospect_role: str = "",
    prospect_company: str = "",
    pain_point: str = "",
    sequence_length: int = 3,
    config: RunnableConfig = None,
) -> str:
    """
    Write a B2B cold email sequence designed to get replies.
    Use when the user asks to write cold emails, outreach emails, sales emails,
    or follow-up sequences to potential customers or partners.

    Args:
        prospect_role: Job title/role of the person being emailed (e.g. 'Marketing Director').
        prospect_company: Type or name of company being targeted.
        pain_point: The specific problem your product/service solves for them.
        sequence_length: Number of emails in the sequence (1-5). Default: 3.
    """
    db, user_id = _get_db_and_user(config)
    biz_ctx = ""
    if db and user_id:
        try:
            u = await db.users.find_one({"_id": user_id})
            if u:
                bk = u.get("business_knowledge") or {}
                biz_ctx = "\n".join(filter(None, [
                    f"Sender business: {u.get('business_name', '')}",
                    f"What we do: {bk.get('business_description', '')}",
                    f"Products/Services: {bk.get('products_services', '')}",
                ]))
        except Exception:
            pass

    count = min(max(int(sequence_length), 1), 5)

    prompt = f"""You are an expert B2B copywriter specialising in cold email outreach.
Write a {count}-email sequence that gets real replies.

SENDER CONTEXT:
{biz_ctx}

TARGET:
- Role: {prospect_role or "Decision maker"}
- Company type: {prospect_company or "Target company"}
- Pain point we solve: {pain_point or "Infer from business context"}

CORE PRINCIPLES:
1. Write like a colleague, not a vendor — no corporate speak
2. Ruthless brevity — every sentence must earn its place
3. Lead with THEIR world, not your company
4. One low-friction ask per email (reply, not "book a 30-min call")
5. Personalization must connect naturally to the outreach reason

EMAIL FRAMEWORKS:
- Email 1: Observation → relevance → soft ask (under 100 words)
- Email 2: Different angle / add value (share insight, case study, stat)
- Email 3: Honest breakup ("Is this timing off?")
- Email 4-5: Re-engage with new trigger or valuable content

QUALITY CHECK — REJECT if:
- Starts with "I hope this email finds you well"
- Mentions "synergy", "leverage", "circle back", "touch base"
- Talks about your company before their problem
- CTA is "schedule a 30-minute call" in email 1

Write the full sequence now. For each email include:
- Subject line (+ 2 alternatives)
- Body (ready to send)
- Sending timing (e.g. "Send day 1", "Wait 3 days")
- Why it works (1 sentence)"""

    result = await _ai(prompt, max_tokens=2500)
    return result or "Could not generate email sequence — please try again."


@tool
async def apply_marketing_psychology(
    context: str,
    goal: str = "increase conversions",
    config: RunnableConfig = None,
) -> str:
    """
    Apply marketing psychology and behavioural science principles to copy, pages,
    pricing, or strategy. Use when the user asks how to make their marketing more
    persuasive, why people aren't buying, or wants psychology-based improvements.

    Args:
        context: What you're trying to improve — page URL, copy snippet, pricing,
                 email, or strategy description.
        goal: What outcome you want — 'increase conversions', 'reduce churn',
              'improve pricing perception', 'build trust', 'increase urgency'.
    """
    db, user_id = _get_db_and_user(config)
    biz_ctx = ""
    if db and user_id:
        try:
            u = await db.users.find_one({"_id": user_id})
            if u:
                bk = u.get("business_knowledge") or {}
                biz_ctx = f"{u.get('business_name','')} — {bk.get('business_description','')}"
        except Exception:
            pass

    prompt = f"""You are a behavioural science expert and marketing psychologist.
Apply psychological principles to improve marketing effectiveness.

BUSINESS: {biz_ctx}
CONTEXT TO IMPROVE: {context}
GOAL: {goal}

PSYCHOLOGICAL FRAMEWORKS TO APPLY (use the most relevant):

PERSUASION PRINCIPLES:
- Reciprocity: Give value first (free tool, insight, template)
- Social proof: Specific numbers > vague claims ("127 businesses" not "many businesses")
- Authority: Credentials, data, expert quotes, awards
- Scarcity/Urgency: Real limits only — manufactured urgency destroys trust
- Loss aversion: "Don't miss X" > "Get X" (losses feel 2x stronger than gains)
- Liking: Shared identity, common enemy, genuine personality

COGNITIVE BIASES TO LEVERAGE:
- Anchoring: Show higher price first, then actual price
- Decoy effect: Add a third option to make target option look like best value
- Mere exposure: Repeated consistent brand touchpoints build trust
- Peak-end rule: Memorable start AND end of experience matters most
- Endowment effect: "Your free trial" feels more owned than "a free trial"

PRICING PSYCHOLOGY:
- Charm pricing ($97 vs $100) works for impulse; round numbers ($100) work for luxury
- Per-day framing ($0.33/day) reduces perceived cost
- Feature anchoring: Lead with premium, justify value before revealing price

DESIGN PSYCHOLOGY:
- Hick's Law: More choices = less action (reduce options)
- Fogg Behavior Model: Motivation × Ability × Trigger — increase all three
- AIDA: Attention → Interest → Desire → Action

OUTPUT FORMAT:

## Psychology Audit: {goal}

### 🧠 Top 3 Psychological Levers to Pull
[Specific principles with exact implementation for this context]

### ✏️ Copy Rewrites Using Psychology
[Before/after examples with the principle used]

### 🏗️ Structural Changes
[Layout, flow, or design changes based on cognitive science]

### ⚠️ Psychological Mistakes to Fix
[Current elements that are working against you]

### Quick Wins
[3 changes to make today, ranked by impact]"""

    result = await _ai(prompt, max_tokens=2000)
    return result or "Could not apply psychology analysis — please try again."


@tool
async def create_lead_magnet(
    business_goal: str = "grow email list",
    target_audience: str = "",
    format_preference: str = "any",
    config: RunnableConfig = None,
) -> str:
    """
    Create a lead magnet strategy and content outline to grow your email list or generate leads.
    Use when the user asks about lead magnets, free offers, content upgrades, email capture,
    or growing their list.

    Args:
        business_goal: What you want to achieve — 'grow email list', 'generate leads',
                       'qualify prospects', 'build authority'.
        target_audience: Who you're trying to attract and what they need.
        format_preference: Preferred format — 'checklist', 'template', 'ebook', 'quiz',
                           'webinar', 'calculator', 'cheatsheet', 'video', 'any'.
    """
    db, user_id = _get_db_and_user(config)
    biz_ctx = ""
    if db and user_id:
        try:
            u = await db.users.find_one({"_id": user_id})
            if u:
                bk = u.get("business_knowledge") or {}
                biz_ctx = "\n".join(filter(None, [
                    f"Business: {u.get('business_name', '')}",
                    f"Type: {bk.get('business_type', '')}",
                    f"Description: {bk.get('business_description', '')}",
                    f"Products/Services: {bk.get('products_services', '')}",
                    f"Location: {bk.get('business_location', '')}",
                ]))
        except Exception:
            pass

    prompt = f"""You are a lead generation and content marketing strategist.
Create a complete lead magnet strategy and ready-to-use content outline.

BUSINESS CONTEXT:
{biz_ctx}

GOAL: {business_goal}
TARGET AUDIENCE: {target_audience or "Infer from business context"}
FORMAT PREFERENCE: {format_preference}

LEAD MAGNET PRINCIPLES:
1. Solve ONE specific problem (not everything)
2. Match buyer stage — awareness (educational) vs decision (tool/template)
3. High perceived value, low time to consume
4. Creates a natural pathway to your product
5. Easy to deliver instantly

LEAD MAGNET FORMATS WITH BEST USE CASES:
- Checklist: Quick win, actionable, high perceived value, low effort to create
- Template: Saves time (swipe file, email template, spreadsheet)
- Calculator/Quiz: Interactive, personalized result → high completion
- Cheatsheet: Reference guide, keeps them coming back
- Mini-course (3-5 emails): Positions you as expert, builds relationship
- Webinar/Workshop: High-ticket qualifier, best for complex products
- Free tool: Highest value, stickiest, but requires development

OUTPUT FORMAT:

## Lead Magnet Strategy

### Recommended Lead Magnet
**Title:** [Specific, outcome-focused title]
**Format:** [Type and why]
**Value proposition:** [What they get and why they'd give their email for it]

### Content Outline
[Full structured outline with all sections/pages/items]

### Landing Page Headlines
[3 headline options for the opt-in page]

### Delivery Sequence
[What happens after they sign up — day 0, day 1, day 3]

### Promotion Channels
[Where and how to promote this lead magnet]

### Success Metrics
[What to track — conversion rate benchmarks, list growth targets]"""

    result = await _ai(prompt, max_tokens=2000)
    return result or "Could not create lead magnet strategy — please try again."


@tool
async def design_ab_test(
    what_to_test: str,
    current_version: str = "",
    conversion_goal: str = "",
    monthly_visitors: int = 0,
    config: RunnableConfig = None,
) -> str:
    """
    Design a proper A/B test with hypothesis, variants, sample size, and success metrics.
    Use when the user wants to test something, asks about A/B testing, split testing,
    or wants to know if a change will improve conversions.

    Args:
        what_to_test: What element to test — headline, CTA, pricing, page layout, email subject.
        current_version: The current version (control) — what it says/looks like now.
        conversion_goal: What you're measuring — signups, purchases, clicks, replies.
        monthly_visitors: Approximate monthly visitors/recipients (for sample size calc).
    """
    db, user_id = _get_db_and_user(config)
    biz_ctx = ""
    if db and user_id:
        try:
            u = await db.users.find_one({"_id": user_id})
            if u:
                bk = u.get("business_knowledge") or {}
                biz_ctx = f"{u.get('business_name','')} — {bk.get('business_description','')}"
        except Exception:
            pass

    prompt = f"""You are a conversion optimisation expert who designs rigorous A/B tests.
Design a complete, statistically sound A/B test.

BUSINESS: {biz_ctx}
ELEMENT TO TEST: {what_to_test}
CURRENT VERSION (Control): {current_version or "Not specified — suggest a common control"}
CONVERSION GOAL: {conversion_goal or "Improve conversions"}
MONTHLY VISITORS/RECIPIENTS: {monthly_visitors or "Unknown — estimate based on typical SMB"}

A/B TEST DESIGN FRAMEWORK:

1. HYPOTHESIS (structured format):
   "Because [observation/insight], we believe [specific change] will cause [expected outcome],
    which we'll measure by [metric]."

2. VARIANTS:
   - Control (A): Current version
   - Variant B: Single change only (never change multiple elements)
   - Optional Variant C: If testing two distinct approaches

3. SAMPLE SIZE:
   - Minimum detectable effect: 10-20% improvement
   - Statistical significance: 95% confidence
   - Estimated sample needed per variant
   - Estimated time to reach significance

4. SUCCESS METRICS:
   - Primary: [conversion rate metric]
   - Guardrail: [metric that shouldn't get worse]
   - Don't peek at results before sample size is reached

5. IMPLEMENTATION:
   - What to build/change
   - How to split traffic (50/50 or weight toward control if risky)
   - How to track results

OUTPUT FORMAT:

## A/B Test Design: {what_to_test}

### Hypothesis
[Structured hypothesis statement]

### Test Variants
**Control (A):** [Description]
**Variant (B):** [Specific change with exact copy/design]
[**Variant (C):** if applicable]

### Sample Size Calculator
- Estimated baseline conversion rate: X%
- Minimum detectable effect: X%
- Sample needed per variant: ~X visitors
- Estimated time to significance: ~X weeks at {monthly_visitors or "your"} visitors/month

### Success Criteria
- Primary metric: [What to measure]
- Win condition: Variant beats control by X% with 95% confidence
- Guardrail metrics: [What must not get worse]

### ICE Score (Prioritization)
- Impact (1-10): X — [reasoning]
- Confidence (1-10): X — [reasoning]
- Ease (1-10): X — [reasoning]
- **ICE Total: X/30**

### What to Watch For
[Common pitfalls for this specific test]"""

    result = await _ai(prompt, max_tokens=2000)
    return result or "Could not design A/B test — please try again."


@tool
async def plan_programmatic_seo(
    pattern_type: str = "",
    config: RunnableConfig = None,
) -> str:
    """
    Create a programmatic SEO strategy to generate hundreds of optimized pages at scale.
    Use when the user asks about programmatic SEO, generating pages at scale, location pages,
    comparison pages, integration pages, or any repeating SEO page pattern.

    Args:
        pattern_type: The type of pages to generate — 'location', 'comparison',
                      'integration', 'glossary', 'template', 'directory', 'persona',
                      'examples', or leave blank to find the best pattern for the business.
    """
    db, user_id = _get_db_and_user(config)
    biz_ctx = ""
    if db and user_id:
        try:
            u = await db.users.find_one({"_id": user_id})
            if u:
                bk = u.get("business_knowledge") or {}
                biz_ctx = "\n".join(filter(None, [
                    f"Business: {u.get('business_name', '')}",
                    f"Type: {bk.get('business_type', '')}",
                    f"Description: {bk.get('business_description', '')}",
                    f"Products/Services: {bk.get('products_services', '')}",
                    f"Location: {bk.get('business_location', '')}",
                ]))
        except Exception:
            pass

    prompt = f"""You are a programmatic SEO strategist. Design a scalable page generation strategy.

BUSINESS CONTEXT:
{biz_ctx}

REQUESTED PATTERN TYPE: {pattern_type or "Recommend the best pattern for this business"}

PROGRAMMATIC SEO PATTERNS:
1. Location pages: "[Service] in [City]" — great for local businesses
2. Comparison pages: "[Product A] vs [Product B]" — intercepts decision-stage searches
3. Integration pages: "[Tool] + [Integration]" — SaaS/B2B growth play
4. Glossary/definition: "What is [term]" — builds topical authority
5. Template pages: "[Type] template/examples" — high-intent educational traffic
6. Directory: "[Category] in [Location]" — marketplace/aggregator model
7. Persona pages: "[Job title] [use case]" — targets specific buyer segments
8. Examples pages: "[Topic] examples" — attracts researchers and buyers

DELIVERABLES NEEDED:

### Pattern Recommendation
[Best 1-2 patterns for this specific business and why]

### Keyword Pattern
- Repeating structure: "[Variable A] + [Fixed keyword] + [Variable B]"
- Example pages: [5 real page title examples]
- Estimated search volume per page: [range]
- Total pages possible: [estimate]

### Page Template
**URL structure:** /[pattern]/[variable]
**Title formula:** [Template with variables]
**Meta description formula:** [Template]
**H1 formula:** [Template]

**Page sections:**
1. [Section name] — [content description, what makes each page unique]
2. [Section name] — [data-driven content]
3. [Section name] — [internal linking to related pages]
4. CTA — [conversion element]

### Data Sources
[Where to get the data to populate these pages — public APIs, scraping, manual lists]

### Internal Linking Strategy
[Hub page + spoke page architecture, how pages link to each other]

### Quality Checks
[How to ensure pages aren't thin content / avoid Google penalties]

### Implementation Roadmap
Phase 1 (Week 1-2): [Pilot with 10-20 pages, validate with Google]
Phase 2 (Month 2): [Scale to 100+ pages]
Phase 3 (Month 3+): [Full automation + monitoring]"""

    result = await _ai(prompt, max_tokens=2500)
    return result or "Could not create programmatic SEO plan — please try again."


# ── Tool registry exported to graph ──────────────────────────────────────────

SEO_TOOLS = [
    # Context & overview
    get_business_context,
    get_seo_summary,
    # Keyword research — DataForSEO (primary)
    get_keyword_ideas,
    get_keyword_search_volume,
    get_keyword_geo_breakdown,
    get_competitor_keywords,
    # Keyword research — VebAPI (fallback)
    veb_keyword_research,
    veb_top_search_keywords,
    # Keyword management
    research_keywords,
    get_saved_keywords,
    add_keywords_to_tracker,
    # Rankings
    get_rankings,
    check_serp_ranking,
    refresh_all_rankings,
    delete_ranking,
    # Website audit
    veb_page_analysis,
    veb_ai_visibility_audit,
    veb_ai_crawler_check,
    veb_speed_check,
    audit_website,
    fix_seo_issues,
    # Backlinks & SERP
    veb_backlinks,
    veb_google_serp,
    veb_google_ai_serp,
    # Domain & social
    veb_domain_data,
    veb_instagram_hashtags,
    veb_youtube_research,
    # Blog & content
    write_blog_post,
    list_saved_posts,
    publish_to_my_site,
    publish_post_to_platform,
    delete_blog_post,
    # Content calendar
    get_content_calendar,
    schedule_content,
    generate_content_calendar,
    # Utilities
    clear_seo_cache,
    web_search,
    # ── Marketing Skills (benchmarked vs coreyhaines31/marketingskills) ────────
    write_marketing_copy,
    audit_conversion_rate,
    write_social_posts,
    write_cold_email,
    apply_marketing_psychology,
    create_lead_magnet,
    design_ab_test,
    plan_programmatic_seo,
]
