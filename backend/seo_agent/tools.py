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
    if db is None:
        db = _seo_db.get()
    if not user_id:
        user_id = _seo_user_id.get()
    return db, user_id


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
    loc = f" in {location}" if location else ""
    prompt = f"""You are an SEO keyword research expert. Generate 15 keyword ideas for a {business_type} business{loc}.

For each keyword return this format (one per line):
KEYWORD | intent | difficulty | content_idea

Where:
- intent: informational, transactional, or local
- difficulty: low, medium, or high
- content_idea: one short blog/page idea (max 8 words)

Language: {language}
Focus on: long-tail phrases, local keywords, buying-intent keywords, question keywords.
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
        logger.info("[get_business_context] db=%s user_id=%s", "OK" if db is not None else "NONE", user_id or "NONE")
        if db is None or not user_id:
            return "No business data available — context not set."

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

        logger.info("[get_business_context] user_found=%s", user is not None)
        business_name = (user or {}).get("business_name", "your business")
        settings = (user or {}).get("settings", {})
        bk = (user or {}).get("business_knowledge", {})
        business_type = settings.get("business_type") or bk.get("business_type") or (user or {}).get("business_type", "general")
        location = settings.get("location") or bk.get("location") or (user or {}).get("location", "")
        website = settings.get("website_url") or bk.get("website_url") or bk.get("website") or ""
        country_code = (user or {}).get("country_code", "")

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
        logger.error("[get_business_context] exception: %s", e, exc_info=True)
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
    if resp.status_code == 402:
        raise RuntimeError("DataForSEO account has no credits (402 Payment Required). Add credits at dataforseo.com or use research_keywords as fallback.")
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
            sc = tasks[0].get("status_code", 0) if tasks else 0
            msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
            if sc == 40200:
                raise RuntimeError("DataForSEO account has no credits. Use research_keywords as fallback.")
            return f"DataForSEO error: {msg}. Use research_keywords tool as fallback."

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
        return f"DataForSEO unavailable: {e}. Use research_keywords tool as fallback."
    except Exception as e:
        return f"Search volume lookup failed: {e}. Use research_keywords tool as fallback."


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
            sc = tasks[0].get("status_code", 0) if tasks else 0
            msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
            if sc == 40200:
                raise RuntimeError("DataForSEO account has no credits. Use research_keywords as fallback.")
            return f"DataForSEO error: {msg}. Use research_keywords tool as fallback."

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
        return f"DataForSEO unavailable: {e}. Use research_keywords tool as fallback."
    except Exception as e:
        return f"Keyword ideas lookup failed: {e}. Use research_keywords tool as fallback."


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
            sc = tasks[0].get("status_code", 0) if tasks else 0
            msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
            if sc == 40200:
                raise RuntimeError("DataForSEO account has no credits. Use research_keywords as fallback.")
            return f"DataForSEO error: {msg}. Use research_keywords tool as fallback."

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
            sc = tasks[0].get("status_code", 0) if tasks else 0
            msg = tasks[0].get("status_message", "unknown") if tasks else "no response"
            if sc == 40200:
                raise RuntimeError("DataForSEO account has no credits. Use research_keywords as fallback.")
            return f"DataForSEO error: {msg}. Use research_keywords tool as fallback."

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

VEBAPI_BASE = "https://vebapi.com"


def _veb_headers() -> dict:
    key = os.environ.get("VEBAPI_KEY", "")
    if not key:
        raise RuntimeError("VEBAPI_KEY is not set. Add it to your environment variables.")
    return {"X-API-KEY": key}


async def _veb_get(endpoint: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as hc:
        resp = await hc.get(
            f"{VEBAPI_BASE}{endpoint}",
            headers=_veb_headers(),
            params={k: v for k, v in params.items() if v is not None},
        )
    if resp.status_code == 401:
        raise RuntimeError("VebAPI: Invalid or missing API key.")
    if resp.status_code == 402:
        raise RuntimeError("VebAPI: No credits remaining. Add credits at vebapi.com.")
    resp.raise_for_status()
    return resp.json()


async def _veb_post(endpoint: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=60) as hc:
        resp = await hc.post(
            f"{VEBAPI_BASE}{endpoint}",
            headers={**_veb_headers(), "Content-Type": "application/json"},
            json=body,
        )
    if resp.status_code == 401:
        raise RuntimeError("VebAPI: Invalid or missing API key.")
    if resp.status_code == 402:
        raise RuntimeError("VebAPI: No credits remaining. Add credits at vebapi.com.")
    resp.raise_for_status()
    return resp.json()


# ── VebAPI Tools ─────────────────────────────────────────────────────────────

@tool
async def veb_keyword_research(keyword: str, country: str = "KE", mode: str = "related") -> str:
    """
    Research keywords using VebAPI. Returns related keyword ideas with volume and CPC data.
    Use mode='related' for multiple keyword ideas, mode='single' for one keyword's full stats.
    Use this as primary keyword research when DataForSEO is unavailable or as a supplementary source.

    Args:
        keyword: The keyword or topic to research.
        country: 2-letter ISO country code (KE=Kenya, NG=Nigeria, US=USA, GB=UK). Default KE.
        mode: 'related' for keyword ideas list (default), 'single' for one keyword detail.
    """
    try:
        if mode == "single":
            data = await _veb_get("/seo/singlekeyword", {"keyword": keyword, "country": country})
            vol = data.get("vol", "N/A")
            cpc = data.get("cpc", "N/A")
            comp = data.get("competition", "N/A")
            score = data.get("score", "N/A")
            return "\n".join([
                f"Keyword: {keyword}",
                f"Monthly Searches: {vol}",
                f"CPC: ${cpc}",
                f"Competition: {comp}",
                f"Score: {score}/100",
            ])

        data = await _veb_get("/seo/keywordresearch", {"keyword": keyword, "country": country})
        keywords = data if isinstance(data, list) else data.get("keywords", [])
        if not keywords:
            return f"No keyword ideas found for '{keyword}'. Try a broader seed term."

        keywords.sort(
            key=lambda k: int(str(k.get("vol", 0)).replace(",", "").replace("K", "000") or 0),
            reverse=True,
        )

        lines = [f"Keyword Ideas — {keyword} ({country})", f"{len(keywords)} results found", ""]
        lines.append(f"{'Keyword':<45} {'Vol/mo':>10} {'CPC':>8} {'Competition':>14}")
        lines.append("-" * 82)
        for kw in keywords[:25]:
            text = str(kw.get("text", ""))[:44]
            vol = str(kw.get("vol", "?"))
            cpc = str(kw.get("cpc", "?"))
            comp = str(kw.get("competition", "?"))
            lines.append(f"{text:<45} {vol:>10} {cpc:>8} {comp:>14}")
        return "\n".join(lines)

    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"VebAPI keyword research failed: {e}"


@tool
async def veb_keyword_density(keyword: str, website: str) -> str:
    """
    Check how often a keyword appears on a specific page and whether it's in the title/meta.
    Use this to analyse on-page keyword optimisation for any URL.

    Args:
        keyword: The keyword phrase to analyse.
        website: Domain or URL of the page (e.g. 'example.com' or 'example.com/page').
    """
    try:
        data = await _veb_get("/seo/keyworddensity", {"keyword": keyword, "website": website})
        title = data.get("title", "")
        desc = data.get("description", "")
        words = data.get("words", [])

        kw_entry = next(
            (w for w in words if str(w.get("word", "")).lower() == keyword.lower()), None
        )

        lines = [f"Keyword Density: '{keyword}' on {website}", ""]
        lines.append(f"Page Title: {title or '(not found)'}")
        lines.append(f"Meta Description: {(desc[:80] + '...') if len(desc) > 80 else desc or '(not found)'}")
        lines.append("")

        if kw_entry:
            count = kw_entry.get("occurrences", kw_entry.get("count", 0))
            density = kw_entry.get("density", "?")
            in_title = kw_entry.get("in_title", False)
            in_meta = kw_entry.get("in_meta", False)
            lines += [
                f"Occurrences: {count}",
                f"Density: {density}%",
                f"In title: {'✓ Yes' if in_title else '✗ No'}",
                f"In meta description: {'✓ Yes' if in_meta else '✗ No'}",
            ]
        else:
            lines.append(f"Keyword not found on this page.")

        if words:
            lines.append(f"\nTop words on page:")
            for w in words[:10]:
                lines.append(f"  {str(w.get('word','')):<30} {w.get('occurrences', w.get('count', '?'))} occurrences")

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Keyword density check failed: {e}"


@tool
async def veb_ai_visibility_audit(website: str, config: RunnableConfig) -> str:
    """
    Run a full AI Visibility Audit — checks whether AI search engines (ChatGPT, Perplexity,
    Claude etc.) can discover and index a page. Returns AI score, indexability, robots.txt
    analysis, llms.txt presence, and prioritised improvement actions.
    Use this when the user asks about AI search visibility or AI SEO.

    Args:
        website: Full URL of the page (e.g. 'https://example.com').
    """
    try:
        if not website.startswith("http"):
            website = "https://" + website
        data = await _veb_get("/api/seo/ai-visibility-checker/v2", {"website": website})

        ai_score = data.get("ai_score", {})
        score = ai_score.get("score", "?")
        grade = ai_score.get("grade", "?")
        ai_vis = data.get("ai_visibility", {})
        structure = data.get("structure", {})
        content = data.get("content", {})
        ai_disc = data.get("ai_discovery", {})
        issues = data.get("issues", [])
        suggestions = data.get("suggestions", [])

        lines = [
            f"AI Visibility Audit: {website}",
            f"AI Score: {score}/100  Grade: {grade}",
            "",
            f"Indexability: {ai_vis.get('status', 'Unknown')}",
            f"robots.txt: {'✓ Found' if ai_disc.get('robots_found') else '✗ Not found'}",
            f"llms.txt:   {'✓ Found' if ai_disc.get('llms_txt') else '✗ Missing (important for AI visibility)'}",
            f"Sitemap:    {'✓ Found' if ai_disc.get('sitemap') else '✗ Not found'}",
            "",
            f"Title: {structure.get('title', '(missing)')}",
            f"Word count: {content.get('word_count', '?')}",
            f"Reading time: {content.get('reading_time', '?')}",
        ]

        if issues:
            lines += ["", f"Issues ({len(issues)}):"]
            for iss in issues[:8]:
                sev = iss.get("severity", "").upper()
                msg = iss.get("message", iss.get("issue", str(iss)))
                lines.append(f"  [{sev}] {msg}")

        if suggestions:
            lines += ["", "Top Actions:"]
            for s in suggestions[:5]:
                text = s.get("suggestion", s) if isinstance(s, dict) else s
                lines.append(f"  • {text}")

        try:
            db, user_id = _get_db_and_user(config)
            if db is not None and user_id:
                await db.seo_ai_audits.insert_one({
                    "_id": str(uuid.uuid4()), "user_id": user_id, "url": website,
                    "ai_score": score, "grade": grade, "issues_count": len(issues),
                    "created_at": datetime.utcnow(),
                })
        except Exception:
            pass

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"AI visibility audit failed: {e}"


@tool
async def veb_page_analysis(website: str, config: RunnableConfig) -> str:
    """
    Run a comprehensive on-page SEO analysis covering technical, content, performance,
    security, and AI-readiness. Returns scored categories and prioritised fixes.
    Use this for a deep-dive audit — more detailed than audit_website.

    Args:
        website: URL to analyse (with or without https://).
    """
    try:
        if not website.startswith("http"):
            website = "https://" + website
        clean = website.replace("https://", "").replace("http://", "")
        data = await _veb_get("/seo/analyze/v2", {"website": clean})

        summary = data.get("summary", {})
        scores = data.get("scores", {})
        findings = data.get("findings", [])
        basic = data.get("basic_info", {})

        overall = summary.get("score", summary.get("overall_score", "?"))
        grade = summary.get("grade", "?")

        lines = [f"On-Page SEO Analysis: {website}", f"Overall: {overall}/100  Grade: {grade}", ""]
        lines.append("Category Scores:")
        for key, label in [
            ("performance", "Performance"), ("technical", "Technical"),
            ("on_page", "On-Page"), ("security", "Security"),
            ("accessibility", "Accessibility"), ("ai_readiness", "AI-Readiness"),
        ]:
            val = scores.get(key)
            if val is not None:
                lines.append(f"  {label:<16} {val}/100")

        title = basic.get("title", "")
        status = basic.get("http_status", "")
        if title or status:
            lines.append("")
            if title:  lines.append(f"Title: {title}")
            if status: lines.append(f"HTTP Status: {status}")

        critical = [f for f in findings if f.get("severity", "").lower() in ("critical", "error", "high")]
        warnings  = [f for f in findings if f.get("severity", "").lower() in ("warning", "medium")]

        if critical:
            lines += ["", f"Critical Issues ({len(critical)}):"]
            for f in critical[:6]:
                lines.append(f"  ✗ {f.get('message', f.get('description', str(f)))}")
        if warnings:
            lines += ["", f"Warnings ({len(warnings)}):"]
            for f in warnings[:5]:
                lines.append(f"  ⚠ {f.get('message', f.get('description', str(f)))}")

        try:
            db, user_id = _get_db_and_user(config)
            if db is not None and user_id:
                await db.seo_audits.insert_one({
                    "_id": str(uuid.uuid4()), "user_id": user_id, "url": website,
                    "score": int(overall) if str(overall).isdigit() else 0, "grade": grade,
                    "issues": [{"message": f.get("message", str(f)), "type": f.get("severity", "info")} for f in findings[:20]],
                    "created_at": datetime.utcnow(),
                })
        except Exception:
            pass

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Page analysis failed: {e}"


@tool
async def veb_domain_data(domain: str) -> str:
    """
    Look up WHOIS registration data, DNS records, and domain age for any domain.
    Use this when the user asks who owns a domain, when it expires, or its DNS records.

    Args:
        domain: Domain to look up (e.g. 'example.com').
    """
    try:
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
        data = await _veb_get("/api/seo/domainnamedata/v2", {"website": domain})

        reg = data.get("registration", {})
        dns = data.get("dns", {})

        lines = [f"Domain Data: {domain}", ""]
        lines += [
            "Registration:",
            f"  Created:    {reg.get('creation_date', reg.get('created', 'Unknown'))}",
            f"  Expires:    {reg.get('expiration_date', reg.get('expires', 'Unknown'))}",
            f"  Registrar:  {reg.get('registrar', 'Unknown')}",
        ]
        ns = reg.get("nameservers", [])
        if ns:
            lines.append(f"  Nameservers: {', '.join(ns[:3])}")

        if dns:
            lines.append("")
            lines.append("DNS Records:")
            for rtype in ("A", "AAAA", "MX", "TXT"):
                recs = dns.get(rtype, [])
                if recs:
                    lines.append(f"  {rtype}: {', '.join(str(r) for r in (recs if isinstance(recs, list) else [recs])[:3])}")

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Domain data lookup failed: {e}"


@tool
async def veb_speed_check(url: str) -> str:
    """
    Test website loading speed and get a performance score with Core Web Vitals data.
    Use this when the user asks about site speed, page load time, or performance.

    Args:
        url: Full URL to test (e.g. 'https://example.com').
    """
    try:
        if not url.startswith("http"):
            url = "https://" + url
        data = await _veb_get("/seo/loadingspeeddata/v2", {"website": url})

        summary = data.get("summary", {})
        improve = data.get("improve_page_performance", {})

        lines = [f"Speed Analysis: {url}", ""]
        lines += [
            f"Performance Score: {summary.get('performance_score', summary.get('score', '?'))}/100",
            f"First Contentful Paint: {summary.get('first_contentful_paint', '?')}",
            f"Largest Contentful Paint: {summary.get('largest_contentful_paint', '?')}",
            f"Time to Interactive: {summary.get('time_to_interactive', '?')}",
            f"Total Blocking Time: {summary.get('total_blocking_time', '?')}",
        ]

        if improve:
            lines += ["", "Areas to Improve:"]
            for key, val in list(improve.items())[:6]:
                label = key.replace("_", " ").title()
                grade = val.get("grade", val.get("score", val)) if isinstance(val, dict) else val
                lines.append(f"  {label}: {grade}")

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Speed check failed: {e}"


@tool
async def veb_backlinks(domain: str, analysis_type: str = "all") -> str:
    """
    Analyse backlinks for any domain. See all links, recent additions, toxic links, or referring domains.
    Use this for link building analysis, competitor research, or checking your own domain authority.

    Args:
        domain: Domain to analyse (e.g. 'example.com').
        analysis_type: 'all' = full backlink list, 'new' = recently found links,
                       'poor' = toxic/low-quality links, 'referral' = referring domains summary.
    """
    try:
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
        endpoint_map = {
            "all": "/seo/backlinkdata",
            "new": "/seo/newbacklinks",
            "poor": "/seo/poorbacklinks",
            "referral": "/seo/referraldomains",
        }
        endpoint = endpoint_map.get(analysis_type, "/seo/backlinkdata")
        params: dict = {"website": domain}
        if analysis_type == "referral":
            params["rows"] = "50"

        data = await _veb_get(endpoint, params)
        lines = [f"Backlinks ({analysis_type.title()}): {domain}", ""]

        if analysis_type == "referral":
            referrers = data.get("referrers", [])
            lines.append(f"Referring Domains: {len(referrers)}")
            lines.append("")
            lines.append(f"{'Domain':<40} {'Backlinks':>10} {'DoFollow':>10} {'DR':>6}")
            lines.append("-" * 72)
            for r in referrers[:20]:
                lines.append(
                    f"{r.get('refdomain',''):<40} {str(r.get('backlinks',0)):>10} "
                    f"{str(r.get('dofollow_backlinks',0)):>10} {str(r.get('domain_inlink_rank','?')):>6}"
                )

        elif analysis_type == "all":
            counts = data.get("counts", {})
            backlinks = data.get("backlinks", [])
            lines += [
                f"Total Backlinks: {counts.get('total', len(backlinks))}",
                f"DoFollow: {counts.get('dofollow', '?')}",
                f"Referring Domains: {counts.get('referring_domains', '?')}",
                "",
                f"{'Source URL':<55} {'Anchor':<20} {'DR':>6}",
                "-" * 85,
            ]
            for bl in backlinks[:15]:
                url_from = str(bl.get("url_from", ""))[:54]
                anchor = str(bl.get("anchor", "") or "")[:19]
                dr = bl.get("inlink_rank", "?")
                lines.append(f"{url_from:<55} {anchor:<20} {str(dr):>6}")

        else:
            items = data.get("backlinks", data if isinstance(data, list) else [])
            label = "New" if analysis_type == "new" else "Poor/Toxic"
            lines.append(f"{label} Backlinks: {len(items)}")
            lines.append("")
            for bl in items[:15]:
                url_from = bl.get("url_from", "")
                anchor = bl.get("anchor", "(no anchor)")
                dr = bl.get("inlink_rank", "?")
                lines.append(f"  {url_from}")
                lines.append(f"  Anchor: {anchor}   DR: {dr}")
                lines.append("")

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Backlink analysis failed: {e}"


@tool
async def veb_top_search_keywords(domain: str, config: RunnableConfig) -> str:
    """
    Get the top keywords a domain currently ranks for in Google — with position, volume, and SEO clicks.
    Works for your own domain or any competitor. Auto-saves keywords to your tracker.
    Use this to discover existing rankings or spy on competitor traffic sources.

    Args:
        domain: Domain to look up (e.g. 'example.com' — no https://).
    """
    try:
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
        data = await _veb_get("/seo/topsearchkeywords", {"website": domain})
        keywords = data.get("keywords", [])
        if not keywords:
            return f"No ranking keywords found for {domain}. The domain may be too new or have low organic traffic."

        lines = [f"Top Search Keywords: {domain}", f"{len(keywords)} keywords found", ""]
        lines.append(f"{'Keyword':<45} {'Rank':>6} {'±Change':>8} {'Volume/mo':>12} {'SEO Clicks':>12}")
        lines.append("-" * 90)
        for kw in keywords[:30]:
            keyword = str(kw.get("keyword", ""))[:44]
            rank = kw.get("rank", "?")
            change = kw.get("rankChange", 0)
            vol = kw.get("searchVolume", "?")
            clicks = kw.get("seoClicks", "?")
            change_str = (f"+{change}" if isinstance(change, (int, float)) and change > 0 else str(change))
            lines.append(f"{keyword:<45} {str(rank):>6} {change_str:>8} {str(vol):>12} {str(clicks):>12}")

        try:
            db, user_id = _get_db_and_user(config)
            if db is not None and user_id and keywords:
                month = datetime.utcnow().strftime("%Y-%m")
                kw_docs = [
                    {"keyword": kw.get("keyword", ""), "search_volume": kw.get("searchVolume"),
                     "rank": kw.get("rank"), "source": "veb_top_keywords"}
                    for kw in keywords[:30] if kw.get("keyword")
                ]
                await db.seo_saved_keywords.update_one(
                    {"user_id": user_id, "month": month, "source": "veb_top_keywords"},
                    {"$set": {"keywords": kw_docs, "domain": domain, "updated_at": datetime.utcnow()}},
                    upsert=True,
                )
        except Exception:
            pass

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Top keyword lookup failed: {e}"


@tool
async def veb_ai_crawler_check(domain: str) -> str:
    """
    Check which AI bots can crawl a website — GPTBot, ClaudeBot, PerplexityBot, Google-Extended, etc.
    Use this to find out if the site is being blocked from AI search engines and get fix recommendations.

    Args:
        domain: Domain to check (e.g. 'example.com').
    """
    try:
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
        data = await _veb_get("/api/seo/aiseochecker", {"website": domain})

        ai_access = data.get("ai_access", {})
        all_allowed = data.get("ai_bots_allowed", None)
        robots_found = data.get("robots_found", None)
        suggestions = data.get("suggestions", [])

        allowed_bots = [b for b, ok in ai_access.items() if ok]
        blocked_bots = [b for b, ok in ai_access.items() if not ok]

        lines = [
            f"AI Crawler Access: {domain}",
            f"robots.txt: {'✓ Found' if robots_found else '✗ Not found'}",
            f"AI Access:  {'✓ All bots allowed' if all_allowed else '✗ Some bots blocked'}",
            "",
        ]
        if allowed_bots:
            lines.append(f"✓ Allowed ({len(allowed_bots)}): {', '.join(allowed_bots)}")
        if blocked_bots:
            lines.append(f"✗ Blocked ({len(blocked_bots)}): {', '.join(blocked_bots)}")

        if suggestions:
            lines += ["", "Recommendations:"]
            for s in suggestions[:5]:
                lines.append(f"  • {s}")

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"AI crawler check failed: {e}"


@tool
async def veb_google_serp(keyword: str, country: str = "KE") -> str:
    """
    Get live Google search results for any keyword — see who ranks, their domain authority, and URLs.
    Use this to research competition for a keyword before writing content.

    Args:
        keyword: Search query to look up.
        country: 2-letter ISO country code (KE=Kenya, NG=Nigeria, US=USA, GB=UK). Default KE.
    """
    try:
        data = await _veb_get("/seo/google_serp", {"keyword": keyword, "country": country})
        results = data.get("results", [])
        if not results:
            return f"No SERP results for '{keyword}' in {country}."

        lines = [f"Google SERP: '{keyword}' ({country})", f"{len(results)} results", ""]
        lines.append(f"{'#':>3}  {'Domain':<35} {'Title':<45} {'DR':>6}")
        lines.append("-" * 94)
        for r in results[:20]:
            rank = r.get("rank", "?")
            title = str(r.get("title", "") or "")[:44]
            domain = str(r.get("hostname", r.get("domain", "")) or "")[:34]
            dr = r.get("domain_inlink_rank", "?")
            lines.append(f"{str(rank):>3}  {domain:<35} {title:<45} {str(dr):>6}")

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Google SERP lookup failed: {e}"


@tool
async def veb_youtube_research(keyword: str) -> str:
    """
    Get YouTube keyword research (search volume, competition, difficulty) AND tag suggestions.
    Use this for YouTube SEO — before uploading a video, to find the right keywords and tags.

    Args:
        keyword: Topic or keyword to research for YouTube.
    """
    try:
        import asyncio as _asyncio
        kw_data, tag_data = await _asyncio.gather(
            _veb_get("/youtube/keywordresearch", {"keyword": keyword}),
            _veb_get("/youtube/taggenerator", {"keyword": keyword}),
        )

        lines = [f"YouTube Research: {keyword}", ""]

        exact = kw_data.get("exact_keyword", {})
        if exact:
            lines += [
                "This Keyword:",
                f"  Monthly Searches: {exact.get('monthlysearch', '?')}",
                f"  Competition Score: {exact.get('competition_score', '?')}",
                f"  Difficulty: {exact.get('difficulty', '?')}",
                f"  Overall Score: {exact.get('overallscore', '?')}",
                "",
            ]

        related = kw_data.get("related_keywords", [])
        if related:
            lines += [f"Related Keywords ({len(related)}):", ""]
            lines.append(f"{'Keyword':<42} {'Vol/mo':>10} {'Difficulty':>12}")
            lines.append("-" * 68)
            for kw in related[:15]:
                text = str(kw.get("keyword", ""))[:41]
                vol = kw.get("monthlysearch", "?")
                diff = kw.get("difficulty", "?")
                lines.append(f"{text:<42} {str(vol):>10} {str(diff):>12}")
            lines.append("")

        tags = tag_data.get("tags", [])
        if tags:
            clean_tags = [(f"#{t}" if not str(t).startswith("#") else t) for t in tags[:20]]
            lines += [f"Suggested Tags ({len(tags)}):", " ".join(clean_tags)]

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"YouTube research failed: {e}"


@tool
async def veb_domain_check(domain: str, tlds: str = "com,net,org,co,io") -> str:
    """
    Check if a domain name is available across multiple TLD extensions (.com, .net, .org, etc.).
    Use this when the user wants to register a new domain or find an available name.

    Args:
        domain: Name to check without any extension (e.g. 'mybusiness').
        tlds: Comma-separated extensions to check (e.g. 'com,net,org,co,io'). Default: 5 common ones.
    """
    try:
        domain = domain.replace("https://", "").replace("http://", "").replace("www.", "")
        domain = domain.split(".")[0].strip()
        tld_list = [t.strip().lstrip(".") for t in tlds.split(",") if t.strip()]

        if len(tld_list) == 1:
            data = await _veb_get("/tools/domainsearchsingle", {"domain": domain, "tld": tld_list[0]})
            results = data if isinstance(data, list) else [data]
        else:
            data = await _veb_get("/tools/domainsearchmulti", {"domain": domain, "tlds": tlds})
            results = data if isinstance(data, list) else []

        available, taken = [], []
        for r in results:
            full = f"{r.get('domain', domain)}.{r.get('tld', '')}"
            if "available" in str(r.get("status", "")).lower():
                available.append(full)
            else:
                taken.append(full)

        lines = [f"Domain Availability: {domain}", ""]
        if available:
            lines.append(f"✓ Available ({len(available)}):")
            lines += [f"  {d}" for d in available]
        if taken:
            lines.append(f"\n✗ Taken ({len(taken)}):")
            lines += [f"  {d}" for d in taken]

        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Domain check failed: {e}"


@tool
async def veb_com_generator(keyword: str) -> str:
    """
    Generate available .com domain name ideas based on a keyword or business name.
    Use this when the user needs a creative available domain for a new site or project.

    Args:
        keyword: Business name, niche, or keyword to build domain ideas around.
    """
    try:
        seed = keyword.replace("https://", "").replace("http://", "").split(".")[0]
        data = await _veb_get("/tools/comdomaingenerator", {"domain": seed})
        results = data if isinstance(data, list) else data.get("domains", [])
        if not results:
            return f"No available .com domains found for '{keyword}'. Try a different keyword."

        lines = [f"Available .com Domains for: {keyword}", f"{len(results)} options", ""]
        for r in results[:20]:
            domain = r.get("newdomain", "")
            variant = r.get("generated", "")
            if domain:
                lines.append(f"  ✓ {domain}  ({variant})")
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Domain generator failed: {e}"


@tool
async def veb_screenshot(url: str) -> str:
    """
    Capture a screenshot of any website and return a shareable image link.
    Use this when the user wants to visualise a webpage for reports or competitor analysis.

    Args:
        url: Full URL to screenshot (must include https://).
    """
    try:
        if not url.startswith("http"):
            url = "https://" + url
        data = await _veb_post("/websitescreenshot", {
            "jobId": str(uuid.uuid4()),
            "url": url,
            "width": 1280,
            "height": 800,
            "fullPage": False,
            "format": "png",
            "blockCookieBanners": True,
        })
        img_url = data.get("url", "")
        if not img_url:
            return "Screenshot failed — no image URL returned."

        return "\n".join([
            f"Screenshot: {url}",
            f"Image URL: {img_url}",
            f"Expires: {data.get('expiresAt', 'N/A')}",
            f"Size: {data.get('bytes', '?')} bytes",
        ])
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Screenshot failed: {e}"


@tool
async def veb_instagram_hashtags(keyword: str) -> str:
    """
    Get Instagram hashtag suggestions with live post-per-hour data for any topic.
    Use this when the user wants to improve Instagram reach or social media strategy.

    Args:
        keyword: Topic or niche to find hashtags for.
    """
    try:
        data = await _veb_get("/tools/instagramhashtags", {"keyword": keyword})
        hashtags = data if isinstance(data, list) else data.get("hashtags", [])
        if not hashtags:
            return f"No Instagram hashtags found for '{keyword}'."

        lines = [f"Instagram Hashtags: {keyword}", f"{len(hashtags)} suggestions", ""]
        lines.append(f"{'Hashtag':<35} {'Posts/hr':>10}")
        lines.append("-" * 47)
        for h in hashtags[:30]:
            tag = str(h.get("keyword", ""))
            posts = h.get("post_last_hr", "?")
            lines.append(f"{tag:<35} {str(posts):>10}")

        lines += ["", "Copy-paste set:"]
        lines.append(" ".join(str(h.get("keyword", "")) for h in hashtags[:15]))
        return "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Instagram hashtag lookup failed: {e}"


# ── Tool registry exported to graph ──────────────────────────────────────────

SEO_TOOLS = [
    get_business_context,
    # ── DataForSEO: SERP + Keywords + Competitor Analysis ──
    get_keyword_ideas,
    get_keyword_search_volume,
    check_serp_ranking,
    get_competitor_keywords,
    # ── VebAPI: AI visibility, page analysis, backlinks, domain tools ──
    veb_keyword_research,
    veb_keyword_density,
    veb_ai_visibility_audit,
    veb_page_analysis,
    veb_speed_check,
    veb_backlinks,
    veb_top_search_keywords,
    veb_ai_crawler_check,
    veb_google_serp,
    veb_domain_data,
    veb_youtube_research,
    veb_domain_check,
    veb_com_generator,
    veb_screenshot,
    veb_instagram_hashtags,
    # ── Content & writing tools ──
    audit_website,
    research_keywords,
    write_blog_post,
    generate_content_calendar,
    fix_seo_issues,
    list_saved_posts,
    publish_post_to_platform,
    get_seo_summary,
    add_keywords_to_tracker,
    web_search,
]
