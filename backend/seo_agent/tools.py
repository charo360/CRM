"""
LangGraph tool definitions for the SEO agent.
Each tool is a pure async function decorated with @tool.
db and user_id are injected via LangGraph RunnableConfig.
"""
from __future__ import annotations
import os, re, uuid, httpx, logging
from datetime import datetime, timedelta
from typing import Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


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
        db = config["configurable"].get("db")
        user_id = config["configurable"].get("user_id")
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

    prompt = f"""You are a senior content writer and SEO expert with deep real-world experience in this topic. You write like a human who has lived it — not like an AI summarising the web.

Topic: {topic}
Keywords (weave in naturally — never force): {kw_str}
Tone: {tone}
Length: {target} words{biz}
{faq_note}

STEP 1 — Before writing, think like a journalist:
- What does someone searching this topic ACTUALLY want to know?
- What's the surprising angle most articles miss?
- What specific detail can only an expert include?
- What's the real pain or goal behind this search?

STEP 2 — Write the article with these rules:

HEADLINE (H1) — must do one of:
• Promise a specific outcome: "How to [X] in [place] Without [fear]"
• Use a number: "5 Things to Know About [topic] Before You [action]"
• Challenge an assumption: "Why Most People Get [topic] Wrong"
• Speak to pain: "Struggling with [problem]? Here's What Actually Works"
NEVER: "The Ultimate Guide", "A Comprehensive Overview", "Everything You Need to Know"

OPENING — Start with ONE of:
• A scene the reader recognises ("You've been quoted three prices for...")
• A counter-intuitive fact ("Most people spend twice what they need to...")
• A direct question ("How do you know if you're getting a good deal?")
NEVER start with a definition or "In today's world..."

BODY — Each H2 section must answer a real question:
- Write in second person or first person: "you'll want...", "I've seen clients..."
- Short sentences. Then longer ones that explain. Mix the rhythm.
- Use contractions: don't, it's, you'll, we've
- Name specific details: local areas, real price ranges, seasons, actual examples
- Every paragraph must teach or surprise — no filler

BANNED phrases: "dive into", "delve into", "game-changer", "leverage", "seamlessly", "unlock potential", "revolutionize", "transformative", "in today's world", "it's important to note", "comprehensive guide", "ultimate guide", "cutting-edge", "harness the power", "at the end of the day"

STRUCTURE:
- H1 headline
- Hook paragraph
- H2 sections (each answers a specific reader question)
- H3 subsections where needed
- Conclusion with a SPECIFIC call-to-action (not "contact us today" — say what happens when they do)
{('- FAQ section: 3-5 questions a real person would actually ask, with genuinely useful answers' if include_faq else '')}

After the article write these 3 lines exactly:
META_TITLE: [50-60 char SEO title — reads like a headline, not a label]
META_DESC: [140-160 char meta description — specific benefit, no fluff]
TAGS: [5 comma-separated tags]"""

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
        db = config["configurable"].get("db") if config else None
        user_id = config["configurable"].get("user_id") if config else None
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
        db = config["configurable"].get("db")
        user_id = config["configurable"].get("user_id")
        if not db or not user_id:
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
        db = config["configurable"].get("db") if config else None
        user_id = config["configurable"].get("user_id") if config else None
        if not db or not user_id:
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
        db = config["configurable"].get("db")
        user_id = config["configurable"].get("user_id")
        if not db or not user_id:
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
        db = config["configurable"].get("db")
        user_id = config["configurable"].get("user_id")
        if not db or not user_id:
            return "No business data available."

        # Fetch user/business profile
        user = await db.users.find_one({"_id": user_id})
        if not user:
            # Try as business_id (team member scenario)
            user = await db.users.find_one({"business_id": user_id})

        business_name = (user or {}).get("business_name", "your business") if user else "your business"
        settings = (user or {}).get("settings", {})
        business_type = settings.get("business_type", "general")
        location = settings.get("location", "")
        website = settings.get("website_url", "")
        country_code = (user or {}).get("country_code", "")

        # Fetch products
        products = await db.products.find({"user_id": user_id}).limit(10).to_list(10)
        product_names = [p.get("name", "") for p in products if p.get("name")]
        product_count = await db.products.count_documents({"user_id": user_id})

        # Fetch customer count
        customer_count = await db.customers.count_documents({"user_id": user_id})

        # Fetch SEO performance data
        last_audit = await db.seo_audits.find_one({"user_id": user_id}, sort=[("created_at", -1)])
        seo_summary = await db.seo_summary.find_one({"user_id": user_id})
        
        # Fetch content performance
        posts = await db.seo_blog_posts.find({"user_id": user_id}).sort("created_at", -1).limit(10).to_list(10)
        published_posts = [p for p in posts if p.get("status") == "published"]
        draft_posts = [p for p in posts if p.get("status") == "draft"]
        
        # Calculate content velocity (posts in last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_posts = [p for p in posts if p.get("created_at") and datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")) > thirty_days_ago]
        
        # Fetch SEO memory if available
        seo_memory = await db.seo_memory.find_one({"user_id": user_id}, sort=[("created_at", -1)])
        
        # Fetch saved keywords
        saved_keywords = await db.seo_saved_keywords.find_one({"user_id": user_id}, sort=[("month", -1)])

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
        db = config["configurable"].get("db")
        user_id = config["configurable"].get("user_id")
        if not db or not user_id:
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


# ── Tool registry exported to graph ──────────────────────────────────────────

SEO_TOOLS = [
    get_business_context,
    audit_website,
    research_keywords,
    get_keyword_search_volume,
    get_keyword_ideas,
    check_serp_ranking,
    get_competitor_keywords,
    write_blog_post,
    generate_content_calendar,
    fix_seo_issues,
    list_saved_posts,
    publish_post_to_platform,
    get_seo_summary,
    add_keywords_to_tracker,
    web_search,
]
