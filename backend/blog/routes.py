"""
Zilo Autoblogging — FastAPI Routes.
Prefix: /api/blog
"""
import base64
import logging
import os
import re
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from blog.blog_service import ZiloBlogService, wp_subsite_public_url, _wp_cli
from blog.topic_generator import research_seo_topic
from blog.post_generator import generate_blog_post
from blog.blog_scheduler import publish_daily_posts

logger = logging.getLogger(__name__)


def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, code) to HTML."""
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def markdown_to_wp_html(content: str, title: str = "", keywords: list = None) -> str:
    """
    Convert markdown to beautifully styled WordPress HTML.
    Hero banner, card lists, accent headings, lead paragraph, closing CTA.
    All inline CSS — works with any WordPress theme.
    """
    if keywords is None:
        keywords = []

    # Strip leading H1 (WP renders post title itself)
    content = re.sub(r"^#+\s+[^\n]*\n?", "", content, count=1).lstrip()
    lines = content.split("\n")

    # ── Colour palette ────────────────────────────────────────────────────────
    BLU   = "#2563eb"
    BLUDK = "#1e40af"
    BLULT = "#dbeafe"
    SLATE = "#0f172a"
    TEXT  = "#374151"
    MUTED = "#64748b"
    BDR   = "#e2e8f0"
    BG    = "#f8fafc"
    WHT   = "#ffffff"

    # ── Hero banner ───────────────────────────────────────────────────────────
    wc        = len(content.split())
    read_min  = max(1, round(wc / 200))
    kw_chips  = "".join(
        '<span style="display:inline-block;background:rgba(255,255,255,0.18);'
        'color:#fff;font-size:11px;font-weight:600;padding:3px 12px;'
        'border-radius:20px;margin:3px 4px 3px 0;">' + kw + '</span>'
        for kw in (keywords or [])[:6]
    )
    hero = (
        '<div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 55%,'
        + BLU + ' 100%);border-radius:16px;padding:36px 30px 28px;'
        'margin-bottom:32px;position:relative;overflow:hidden;">'
        '<div style="position:absolute;top:-50px;right:-50px;width:240px;height:240px;'
        'background:rgba(255,255,255,0.04);border-radius:50%;"></div>'
        '<div style="position:absolute;bottom:-60px;left:-20px;width:180px;height:180px;'
        'background:rgba(255,255,255,0.03);border-radius:50%;"></div>'
        '<div style="position:relative;z-index:1;">'
        '<div style="font-size:11px;font-weight:700;color:rgba(255,255,255,0.55);'
        'text-transform:uppercase;letter-spacing:2px;margin-bottom:16px;">'
        '&#10022; Zilo AI &nbsp;&#183;&nbsp; Quality Article</div>'
        '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;">'
        '<span style="background:rgba(255,255,255,0.12);color:rgba(255,255,255,0.85);'
        'font-size:12px;font-weight:500;padding:4px 14px;border-radius:20px;">'
        '&#9200; ' + str(read_min) + ' min read</span>'
        '<span style="background:rgba(255,255,255,0.12);color:rgba(255,255,255,0.85);'
        'font-size:12px;font-weight:500;padding:4px 14px;border-radius:20px;">'
        '&#128221; ' + str(wc) + ' words</span>'
        '</div>'
        + ('<div>' + kw_chips + '</div>' if kw_chips else '')
        + '</div></div>'
    )

    # ── Build HTML ────────────────────────────────────────────────────────────
    parts = [hero]
    i = 0
    first_para = True

    while i < len(lines):
        ln = lines[i]
        s  = ln.strip()

        if not s:
            i += 1
            continue

        # H2
        if s.startswith("## "):
            t = _inline_md(s[3:])
            parts.append(
                '<h2 style="font-size:21px;font-weight:800;color:' + SLATE + ';'
                'border-left:4px solid ' + BLU + ';padding-left:14px;'
                'margin:44px 0 14px;line-height:1.3;'
                'font-family:-apple-system,BlinkMacSystemFont,sans-serif;">' + t + '</h2>'
            )
            i += 1; continue

        # H3
        if s.startswith("### "):
            t = _inline_md(s[4:])
            parts.append(
                '<h3 style="font-size:17px;font-weight:700;color:' + SLATE + ';'
                'margin:28px 0 10px;'
                'font-family:-apple-system,BlinkMacSystemFont,sans-serif;">' + t + '</h3>'
            )
            i += 1; continue

        # H4
        if s.startswith("#### "):
            t = _inline_md(s[5:])
            parts.append(
                '<h4 style="font-size:12px;font-weight:700;color:' + MUTED + ';'
                'text-transform:uppercase;letter-spacing:1.5px;margin:20px 0 8px;'
                'font-family:-apple-system,sans-serif;">' + t + '</h4>'
            )
            i += 1; continue

        # Unordered list
        if re.match(r"^[*\-]\s+", s):
            items = []
            while i < len(lines) and re.match(r"^[*\-]\s+", lines[i].strip()):
                c = _inline_md(lines[i].strip()[2:])
                items.append(
                    '<li style="padding:9px 14px 9px 38px;position:relative;color:' + TEXT + ';'
                    'font-size:15px;line-height:1.6;border-bottom:1px solid ' + BDR + ';">'
                    '<span style="position:absolute;left:12px;top:10px;color:' + BLU + ';'
                    'font-size:20px;font-weight:900;line-height:1;">&#8250;</span>' + c + '</li>'
                )
                i += 1
            parts.append(
                '<ul style="list-style:none;padding:0;margin:20px 0;'
                'border:1px solid ' + BDR + ';border-radius:12px;'
                'overflow:hidden;background:' + WHT + ';'
                'box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
                + "".join(items) + '</ul>'
            )
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", s):
            items = []
            num = 1
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_raw = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                c = _inline_md(item_raw)
                items.append(
                    '<li style="padding:11px 16px 11px 54px;position:relative;color:' + TEXT + ';'
                    'font-size:15px;line-height:1.6;border-bottom:1px solid ' + BDR + ';'
                    'background:' + WHT + ';">'
                    '<span style="position:absolute;left:12px;top:11px;background:' + BLU + ';'
                    'color:#fff;width:24px;height:24px;border-radius:50%;'
                    'display:inline-flex;align-items:center;justify-content:center;'
                    'font-size:11px;font-weight:800;">' + str(num) + '</span>' + c + '</li>'
                )
                num += 1
                i += 1
            parts.append(
                '<ol style="list-style:none;padding:0;margin:20px 0;'
                'border:1px solid ' + BDR + ';border-radius:12px;'
                'overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
                + "".join(items) + '</ol>'
            )
            continue

        # Blockquote
        if s.startswith("> "):
            t = _inline_md(s[2:])
            parts.append(
                '<blockquote style="border-left:4px solid ' + BLU + ';'
                'background:' + BLULT + ';padding:18px 22px;'
                'border-radius:0 12px 12px 0;margin:28px 0;'
                'font-style:italic;color:' + BLUDK + ';font-size:15px;line-height:1.7;">'
                + t + '</blockquote>'
            )
            i += 1; continue

        # Horizontal rule
        if s in ("---", "***", "___"):
            parts.append('<hr style="border:none;border-top:2px solid ' + BDR + ';margin:36px 0;">')
            i += 1; continue

        # Paragraph — collect consecutive plain lines
        para_lines = []
        while (
            i < len(lines)
            and lines[i].strip()
            and not re.match(r"^#{1,6}\s+", lines[i].strip())
            and not re.match(r"^[*\-]\s+", lines[i].strip())
            and not re.match(r"^\d+\.\s+", lines[i].strip())
            and not lines[i].strip().startswith("> ")
            and lines[i].strip() not in ("---", "***", "___")
        ):
            para_lines.append(_inline_md(lines[i]))
            i += 1
        if para_lines:
            t = "<br>\n".join(para_lines)
            if first_para:
                first_para = False
                parts.append(
                    '<p style="font-size:17px;line-height:1.9;color:' + TEXT + ';'
                    'padding:18px 22px;background:' + BG + ';'
                    'border-left:4px solid ' + BLU + ';'
                    'border-radius:0 10px 10px 0;margin:0 0 28px;">' + t + '</p>'
                )
            else:
                parts.append(
                    '<p style="font-size:16px;line-height:1.8;color:' + TEXT + ';'
                    'margin:0 0 18px;">' + t + '</p>'
                )

    # ── Closing CTA strip ─────────────────────────────────────────────────────
    parts.append(
        '<div style="background:linear-gradient(135deg,' + BLU + ' 0%,' + BLUDK + ' 100%);'
        'border-radius:14px;padding:28px 24px;margin-top:44px;text-align:center;">'
        '<p style="color:rgba(255,255,255,0.75);font-size:12px;margin:0 0 6px;'
        'text-transform:uppercase;letter-spacing:1.5px;font-weight:600;">'
        'Ready to get started?</p>'
        '<p style="color:#fff;font-size:20px;font-weight:800;margin:0 0 18px;line-height:1.4;">'
        "Let&#39;s build something great together</p>"
        '<a href="/contact" style="display:inline-block;background:#fff;color:' + BLU + ';'
        'font-size:13px;font-weight:700;padding:11px 28px;border-radius:30px;'
        'text-transform:uppercase;letter-spacing:1px;text-decoration:none;">'
        'Get in Touch &#8594;</a>'
        '</div>'
    )

    wrapper = (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,'
        "'Segoe UI',Georgia,serif;color:#1e293b;line-height:1.8;"
        'max-width:740px;width:100%;margin:0 auto;box-sizing:border-box;">'
    )
    return wrapper + "\n".join(parts) + "</div>"


def _canonical_blog_url(blog: dict) -> str | None:
    """
    Subsite homepage URL from multisite env (WP_BASE_URL, etc.).
    Prefer this over Mongo `blog_url`, which goes stale after changing network domains.
    """
    slug = blog.get("wp_slug")
    if slug:
        try:
            return wp_subsite_public_url(str(slug))
        except ValueError:
            pass
    raw = blog.get("blog_url")
    if isinstance(raw, str) and raw.startswith(("http://", "https://")):
        return raw.strip().rstrip("/")
    return None


async def _blog_url_for_response(db, blog: dict) -> str | None:
    """Canonical URL exposed to dashboards; persists it when Mongo was outdated."""
    url = _canonical_blog_url(blog)
    cid = blog.get("client_id")
    if url and cid and blog.get("blog_url") != url:
        await db.blogs.update_one({"client_id": cid}, {"$set": {"blog_url": url}})
    return url or (blog.get("blog_url").strip().rstrip("/") if isinstance(blog.get("blog_url"), str) else None)


class CreateBlogRequest(BaseModel):
    client_id: str
    business_name: str
    client_email: str
    industry: str
    location: str


class ManualPublishRequest(BaseModel):
    client_id: str


class ProvisionBlogRequest(BaseModel):
    business_name: str
    client_email: str
    industry: str
    location: str


class PublishFromSeoRequest(BaseModel):
    title: str
    content: str
    keywords: list = []
    excerpt: str = ""


class KeywordTrackerEntry(BaseModel):
    keyword: str
    search_volume: int = 0
    difficulty: str = ""
    intent: str = ""
    content_idea: str = ""


def make_blog_router(db, get_current_user):
    router = APIRouter(prefix="/blog", tags=["blog"])
    blog_service = ZiloBlogService(db)

    def _user_id(user) -> str:
        return str(user.get("_id") or user.get("id", "") or "")

    def _require_own_client(client_id: str, user) -> str:
        uid = _user_id(user)
        if not uid:
            raise HTTPException(status_code=400, detail="Cannot identify user")
        if client_id != uid:
            raise HTTPException(status_code=403, detail="Not allowed")
        return uid

    # ── Create / activate a client blog ───────────────────────────────────────

    @router.post("/create")
    async def create_blog(req: CreateBlogRequest, user=Depends(get_current_user)):
        """
        Called when a client clicks 'Activate My Blog' on the Zilo dashboard.
        Creates a WordPress subsite and stores the blog record in MongoDB.
        """
        try:
            result = await blog_service.create_client_blog(
                client_id=req.client_id,
                business_name=req.business_name,
                client_email=req.client_email,
                industry=req.industry,
                location=req.location,
            )
            return result
        except Exception as e:
            logger.error(f"[blog/create] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ── Blog status for a client ───────────────────────────────────────────────

    @router.get("/status/{client_id}")
    async def get_blog_status(client_id: str, user=Depends(get_current_user)):
        """Returns blog info, post count and last post date for a client."""
        _require_own_client(client_id, user)
        blog = await db.blogs.find_one({"client_id": client_id})
        if not blog:
            return {"connected": False}

        last_posted = blog.get("last_posted_at")
        blog_url = await _blog_url_for_response(db, blog)
        return {
            "connected": True,
            "client_id": client_id,
            "blog_url": blog_url,
            "wp_slug": blog.get("wp_slug"),
            "industry": blog.get("industry"),
            "location": blog.get("location"),
            "plan": blog.get("plan", "free"),
            "posts_count": blog.get("posts_count", 0),
            "last_posted_at": last_posted.isoformat() if last_posted else None,
            "active": blog.get("active", True),
        }

    # ── Auto-provision blog from settings (idempotent) ────────────────────────

    @router.post("/provision")
    async def provision_blog(req: ProvisionBlogRequest, user=Depends(get_current_user)):
        """
        Called automatically when the user saves Business Settings or completes onboarding.
        Uses the user's own _id as client_id — idempotent, safe to call multiple times.
        If blog already exists, returns it without recreating.
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        existing = await db.blogs.find_one({"client_id": user_id})
        if existing:
            last_posted = existing.get("last_posted_at")
            blog_url = await _blog_url_for_response(db, existing)
            return {
                "status": "already_exists",
                "connected": True,
                "client_id": user_id,
                "blog_url": blog_url,
                "wp_slug": existing.get("wp_slug"),
                "industry": existing.get("industry"),
                "location": existing.get("location"),
                "active": existing.get("active", True),
                "posts_count": existing.get("posts_count", 0),
                "last_posted_at": last_posted.isoformat() if last_posted else None,
            }

        try:
            result = await blog_service.create_client_blog(
                client_id=user_id,
                business_name=req.business_name,
                client_email=req.client_email,
                industry=req.industry,
                location=req.location,
            )
            return {**result, "status": "created", "connected": True, "client_id": user_id}
        except Exception as e:
            logger.error(f"[blog/provision] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ── My blog (current authenticated user) ──────────────────────────────────

    @router.get("/my")
    async def get_my_blog(user=Depends(get_current_user)):
        """Returns the blog record for the currently authenticated user."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id})
        if not blog:
            return {"connected": False}

        last_posted = blog.get("last_posted_at")
        blog_url = await _blog_url_for_response(db, blog)
        return {
            "connected": True,
            "client_id": user_id,
            "blog_url": blog_url,
            "wp_slug": blog.get("wp_slug"),
            "industry": blog.get("industry"),
            "location": blog.get("location"),
            "plan": blog.get("plan", "free"),
            "posts_count": blog.get("posts_count", 0),
            "last_posted_at": last_posted.isoformat() if last_posted else None,
            "active": blog.get("active", True),
        }

    # ── Deactivate a blog ─────────────────────────────────────────────────────

    @router.patch("/deactivate/{client_id}")
    async def deactivate_blog(client_id: str, user=Depends(get_current_user)):
        """Pauses autoblogging for a client without deleting their subsite."""
        _require_own_client(client_id, user)
        result = await db.blogs.update_one(
            {"client_id": client_id},
            {"$set": {"active": False, "deactivated_at": datetime.utcnow()}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Blog not found")
        return {"status": "deactivated"}

    # ── Reactivate a blog ─────────────────────────────────────────────────────

    @router.patch("/activate/{client_id}")
    async def activate_blog(client_id: str, user=Depends(get_current_user)):
        """Re-enables autoblogging for a paused client blog."""
        _require_own_client(client_id, user)
        result = await db.blogs.update_one(
            {"client_id": client_id},
            {"$set": {"active": True}, "$unset": {"deactivated_at": ""}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Blog not found")
        return {"status": "activated"}

    # ── Manually trigger a post for one client ─────────────────────────────────

    @router.post("/publish-now")
    async def publish_now(req: ManualPublishRequest, user=Depends(get_current_user)):
        """
        Manually triggers immediate generation and publishing of one post
        for the given client. Useful for testing or on-demand publishing.
        """
        _require_own_client(req.client_id, user)
        blog = await db.blogs.find_one({"client_id": req.client_id})
        if not blog:
            raise HTTPException(status_code=404, detail="Blog not found")

        try:
            seo = await research_seo_topic(db, req.client_id)
            posts_count = blog.get("posts_count", 0)
            post = await generate_blog_post(
                business_name=blog["business_name"],
                industry=blog["industry"],
                location=blog["location"],
                topic=seo["topic"],
                posts_count=posts_count,
                focus_keyword=seo.get("focus_keyword", ""),
                seo_keywords=seo.get("keywords", []),
            )
            result = await blog_service.publish_post(
                wp_slug=blog["wp_slug"],
                title=post["title"],
                content=post["content"],
                excerpt=post["excerpt"],
                keywords=post["keywords"],
            )
            return {
                "status": "published",
                "topic": topic,
                "post_url": result["post_url"],
                "post_id": result["post_id"],
                "template_used": post.get("template_used", ""),
            }
        except Exception as e:
            logger.error(f"[blog/publish-now] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ── Publish a pre-written SEO post to user's blog ────────────────────────

    @router.post("/publish-from-seo")
    async def publish_from_seo(req: PublishFromSeoRequest, user=Depends(get_current_user)):
        """
        Takes a fully-written post from the SEO page (title, content, keywords)
        and publishes it directly to the authenticated user's WordPress subsite.
        No topic generation needed — content already written.
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id})
        if not blog:
            raise HTTPException(
                status_code=404,
                detail="No blog found. Go to Autoblog → Activate your blog first.",
            )
        if not blog.get("active", True):
            raise HTTPException(status_code=400, detail="Blog is paused. Activate it first.")

        blog_url_out = await _blog_url_for_response(db, blog)
        # Convert markdown → HTML and strip leading H1 (WP renders the title itself)
        html_content = markdown_to_wp_html(req.content, title=req.title, keywords=req.keywords)
        excerpt = req.excerpt or (req.content[:155].replace("<", "").replace(">", "").strip() + "…")
        try:
            result = await blog_service.publish_post(
                wp_slug=blog["wp_slug"],
                title=req.title,
                content=html_content,
                excerpt=excerpt,
                keywords=req.keywords,
            )
            return {
                "status": "published",
                "post_url": result["post_url"],
                "post_id": result["post_id"],
                "blog_url": blog_url_out,
            }
        except Exception as e:
            logger.error(f"[blog/publish-from-seo] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ── Admin: run the full daily job manually ─────────────────────────────────

    @router.post("/run-daily-job")
    async def run_daily_job(user=Depends(get_current_user)):
        """Admin endpoint to manually trigger the full daily publish job."""
        try:
            await publish_daily_posts(db)
            return {"status": "completed"}
        except Exception as e:
            logger.error(f"[blog/run-daily-job] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ── Recent posts log for a client ─────────────────────────────────────────

    @router.get("/posts/{client_id}")
    async def get_posts(client_id: str, limit: int = 20, user=Depends(get_current_user)):
        """Returns the most recent published posts for a client."""
        _require_own_client(client_id, user)
        posts = await db.posts_log.find(
            {"client_id": client_id},
            {"_id": 0},
        ).sort("published_at", -1).limit(limit).to_list(None)

        for p in posts:
            if isinstance(p.get("published_at"), datetime):
                p["published_at"] = p["published_at"].isoformat()

        return {"posts": posts}

    # ── Keyword tracker — save keywords with blog link ─────────────────────────

    @router.post("/keyword-tracker/save")
    async def save_keyword_entry(req: KeywordTrackerEntry, user=Depends(get_current_user)):
        """Save/update a keyword in the tracker. Called after publishing from SEO page."""
        user_id = str(user.get("_id") or user.get("id", ""))
        await db.keyword_tracker.update_one(
            {"user_id": user_id, "keyword": req.keyword},
            {"$set": {
                "user_id": user_id,
                "keyword": req.keyword,
                "search_volume": req.search_volume,
                "difficulty": req.difficulty,
                "intent": req.intent,
                "content_idea": req.content_idea,
                "updated_at": datetime.utcnow(),
            }, "$setOnInsert": {"created_at": datetime.utcnow(), "posts": []}},
            upsert=True,
        )
        return {"ok": True}

    @router.post("/keyword-tracker/link-post")
    async def link_post_to_keyword(
        keyword: str,
        post_title: str,
        post_url: str,
        user=Depends(get_current_user),
    ):
        """Link a published blog post to a keyword in the tracker."""
        user_id = str(user.get("_id") or user.get("id", ""))
        await db.keyword_tracker.update_one(
            {"user_id": user_id, "keyword": keyword},
            {"$push": {"posts": {
                "title": post_title,
                "url": post_url,
                "published_at": datetime.utcnow().isoformat(),
            }}},
        )
        return {"ok": True}

    @router.get("/keyword-tracker")
    async def get_keyword_tracker(user=Depends(get_current_user)):
        """Returns all tracked keywords with their linked blog posts."""
        user_id = str(user.get("_id") or user.get("id", ""))
        entries = await db.keyword_tracker.find(
            {"user_id": user_id},
            {"_id": 0, "user_id": 0},
        ).sort("search_volume", -1).to_list(None)

        for e in entries:
            if isinstance(e.get("updated_at"), datetime):
                e["updated_at"] = e["updated_at"].isoformat()
            if isinstance(e.get("created_at"), datetime):
                e["created_at"] = e["created_at"].isoformat()

        return {"keywords": entries}

    # ── Client Sites dashboard ─────────────────────────────────────────────────

    @router.get("/clients")
    async def list_client_sites(user=Depends(get_current_user)):
        """
        Returns all provisioned client sites (blogs) for the current user.
        Each entry includes blog + shop + forms feature flags and live URL.
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        docs = await db.blogs.find({"client_id": user_id}).sort("created_at", -1).to_list(None)
        sites = []
        for doc in docs:
            doc.pop("_id", None)
            if isinstance(doc.get("created_at"), datetime):
                doc["created_at"] = doc["created_at"].isoformat()
            if isinstance(doc.get("last_posted_at"), datetime):
                doc["last_posted_at"] = doc["last_posted_at"].isoformat()
            blog_url = await _blog_url_for_response(db, doc)
            doc["blog_url"] = blog_url
            doc.setdefault("features", {"shop": True, "forms": True, "blog": True})
            sites.append(doc)
        return {"sites": sites}

    @router.get("/clients/pending-counts")
    async def get_pending_comment_counts(user=Depends(get_current_user)):
        """
        Returns {counts: {wp_slug: N}} with the number of pending/hold
        comments across all client sites for the current user.
        One lightweight WP REST call per site (per_page=1 just to get total).
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        docs = await db.blogs.find({"client_id": user_id}, {"wp_slug": 1, "custom_domain": 1, "blog_subdomain": 1}).to_list(None)
        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}"}
        counts: dict[str, int] = {}

        async def _fetch_count(doc):
            slug = doc.get("wp_slug", "")
            site_base = await _blog_url_for_response(db, doc)
            if not site_base:
                counts[slug] = 0
                return
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    r = await client.get(
                        f"{site_base}/wp-json/wp/v2/comments?status=hold&per_page=1",
                        headers=headers,
                    )
                    if r.status_code == 200:
                        total = int(r.headers.get("X-WP-Total", "0"))
                        counts[slug] = total
                    else:
                        counts[slug] = 0
            except Exception:
                counts[slug] = 0

        import asyncio
        await asyncio.gather(*[_fetch_count(doc) for doc in docs])
        return {"counts": counts}

    @router.patch("/clients/{wp_slug}/features")
    async def patch_site_features(
        wp_slug: str,
        body: dict,
        user=Depends(get_current_user),
    ):
        """Update which features (shop/forms/blog) are enabled for a client site."""
        user_id = str(user.get("_id") or user.get("id", ""))
        result = await db.blogs.update_one(
            {"client_id": user_id, "wp_slug": wp_slug},
            {"$set": {"features": body.get("features", {})}},
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Site not found")
        return {"status": "updated"}

    # ── WooCommerce orders for a client subsite ────────────────────────────────

    @router.get("/clients/{wp_slug}/orders")
    async def get_client_orders(wp_slug: str, user=Depends(get_current_user)):
        """Fetch recent WooCommerce orders from a client's subsite via REST API."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            return {"orders": [], "reason": "Site URL unavailable"}

        wc_key = os.getenv("WC_CONSUMER_KEY", "")
        wc_secret = os.getenv("WC_CONSUMER_SECRET", "")
        if not wc_key:
            return {"orders": [], "reason": "WooCommerce API keys not configured"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{site_base}/wp-json/wc/v3/orders?per_page=10&orderby=date&order=desc",
                    auth=(wc_key, wc_secret),
                )
                if r.status_code == 200:
                    orders = r.json()
                    total = int(r.headers.get("X-WP-Total", len(orders)))
                    return {"orders": orders, "total": total}
                return {"orders": [], "reason": f"WC API {r.status_code}"}
        except Exception as exc:
            logger.warning("[blog] WC orders fetch failed for %s: %s", wp_slug, exc)
            return {"orders": [], "reason": str(exc)}

    # ── WooCommerce products for a client subsite ──────────────────────────────

    @router.get("/clients/{wp_slug}/products")
    async def get_client_products(wp_slug: str, user=Depends(get_current_user)):
        """Fetch WooCommerce products from a client's subsite."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            return {"products": [], "reason": "Site URL unavailable"}

        wc_key = os.getenv("WC_CONSUMER_KEY", "")
        wc_secret = os.getenv("WC_CONSUMER_SECRET", "")
        if not wc_key:
            return {"products": [], "reason": "WooCommerce API keys not configured"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{site_base}/wp-json/wc/v3/products?per_page=20&status=publish",
                    auth=(wc_key, wc_secret),
                )
                if r.status_code == 200:
                    products = r.json()
                    total = int(r.headers.get("X-WP-Total", len(products)))
                    return {"products": products, "total": total}
                return {"products": [], "reason": f"WC API {r.status_code}"}
        except Exception as exc:
            logger.warning("[blog] WC products fetch failed for %s: %s", wp_slug, exc)
            return {"products": [], "reason": str(exc)}

    # ── WPForms submissions for a client subsite ───────────────────────────────

    @router.get("/clients/{wp_slug}/form-entries")
    async def get_client_form_entries(wp_slug: str, user=Depends(get_current_user)):
        """
        Fetch WPForms entries from a client subsite via the WPForms REST API endpoint.
        Requires WPForms 1.7.7+ with REST API enabled, or the WPForms REST API plugin.
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            return {"entries": [], "reason": "Site URL unavailable"}

        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        if not wp_user:
            return {"entries": [], "reason": "WordPress credentials not configured"}

        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{site_base}/wp-json/wpforms/v1/entries?per_page=20",
                    headers=headers,
                )
                if r.status_code == 200:
                    return {"entries": r.json()}
                return {"entries": [], "reason": f"WPForms API {r.status_code}"}
        except Exception as exc:
            logger.warning("[blog] WPForms entries fetch failed for %s: %s", wp_slug, exc)
            return {"entries": [], "reason": str(exc)}

    # ── WordPress comments for a client subsite ────────────────────────────────

    @router.get("/clients/{wp_slug}/comments")
    async def get_client_comments(wp_slug: str, user=Depends(get_current_user)):
        """Fetch recent WordPress comments from a client subsite."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            return {"comments": [], "reason": "Site URL unavailable"}

        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        if not wp_user:
            return {"comments": [], "reason": "WordPress credentials not configured"}

        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}"}

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # Fetch all comments regardless of moderation status
                r = await client.get(
                    f"{site_base}/wp-json/wp/v2/comments"
                    "?per_page=50&orderby=date&order=desc&status=any",
                    headers=headers,
                )
                if r.status_code != 200:
                    return {"comments": [], "reason": f"WP API {r.status_code}"}

                raw = r.json()

                # Resolve post titles for all unique post IDs in one batch
                post_ids = list({c.get("post") for c in raw if c.get("post")})
                post_titles: dict[int, str] = {}
                post_links: dict[int, str] = {}
                if post_ids:
                    ids_param = ",".join(str(p) for p in post_ids)
                    pr = await client.get(
                        f"{site_base}/wp-json/wp/v2/posts?include={ids_param}&per_page=50",
                        headers=headers,
                    )
                    if pr.status_code == 200:
                        for p in pr.json():
                            post_titles[p["id"]] = p.get("title", {}).get("rendered", f"Post {p['id']}")
                            post_links[p["id"]] = p.get("link", "")

                comments = [
                    {
                        "id": c.get("id"),
                        "post_id": c.get("post"),
                        "post_title": post_titles.get(c.get("post"), f"Post {c.get('post')}"),
                        "post_link": post_links.get(c.get("post"), ""),
                        "author": c.get("author_name"),
                        "email": c.get("author_email"),
                        "content": c.get("content", {}).get("rendered", ""),
                        "date": c.get("date"),
                        "status": c.get("status"),
                        "parent": c.get("parent", 0),
                    }
                    for c in raw
                ]
                return {"comments": comments}
        except Exception as exc:
            logger.warning("[blog] Comments fetch failed for %s: %s", wp_slug, exc)
            return {"comments": [], "reason": str(exc)}

    # ── Approve a pending WordPress comment from the CRM ──────────────────────

    @router.post("/clients/{wp_slug}/comments/{comment_id}/approve")
    async def approve_comment(wp_slug: str, comment_id: int, user=Depends(get_current_user)):
        """Approve a pending comment so it becomes visible on the blog post."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")

        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{site_base}/wp-json/wp/v2/comments/{comment_id}",
                headers=headers,
                json={"status": "approved"},
            )
            if r.status_code in (200, 201):
                return {"status": "approved"}
            raise HTTPException(r.status_code, f"WordPress error: {r.text[:200]}")

    # ── Delete a WordPress comment from the CRM ───────────────────────────────

    @router.delete("/clients/{wp_slug}/comments/{comment_id}")
    async def delete_comment(wp_slug: str, comment_id: int, user=Depends(get_current_user)):
        """Permanently delete a comment from a client subsite."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")
        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")
        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.delete(
                f"{site_base}/wp-json/wp/v2/comments/{comment_id}?force=true",
                headers=headers,
            )
            if r.status_code in (200, 201):
                return {"status": "deleted"}
            raise HTTPException(r.status_code, f"WordPress error: {r.text[:200]}")

    # ── List posts for a client subsite ───────────────────────────────────────

    @router.get("/clients/{wp_slug}/posts")
    async def list_client_posts(wp_slug: str, user=Depends(get_current_user)):
        """List all published and draft posts for a client subsite."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")
        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            return {"posts": [], "reason": "Site URL unavailable"}
        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}"}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(
                    f"{site_base}/wp-json/wp/v2/posts?per_page=50&orderby=date&order=desc&status=publish,draft",
                    headers=headers,
                )
                if r.status_code != 200:
                    return {"posts": [], "reason": f"WP API {r.status_code}"}
                posts = [
                    {
                        "id": p.get("id"),
                        "title": p.get("title", {}).get("rendered", ""),
                        "status": p.get("status"),
                        "date": p.get("date"),
                        "link": p.get("link", ""),
                    }
                    for p in r.json()
                ]
                return {"posts": posts}
        except Exception as exc:
            logger.warning("[blog] list posts failed for %s: %s", wp_slug, exc)
            return {"posts": [], "reason": str(exc)}

    # ── Delete a post from a client subsite ───────────────────────────────────

    @router.delete("/clients/{wp_slug}/posts/{post_id}")
    async def delete_client_post(wp_slug: str, post_id: int, user=Depends(get_current_user)):
        """Permanently delete a post from a client subsite."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")
        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")
        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.delete(
                f"{site_base}/wp-json/wp/v2/posts/{post_id}?force=true",
                headers=headers,
            )
            if r.status_code in (200, 201):
                return {"status": "deleted"}
            raise HTTPException(r.status_code, f"WordPress error: {r.text[:200]}")

    # ── Unpublish (draft) a post from a client subsite ────────────────────────

    @router.post("/clients/{wp_slug}/posts/{post_id}/unpublish")
    async def unpublish_client_post(wp_slug: str, post_id: int, user=Depends(get_current_user)):
        """Set a published post back to draft so it's hidden from the public."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")
        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")
        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{site_base}/wp-json/wp/v2/posts/{post_id}",
                headers=headers,
                json={"status": "draft"},
            )
            if r.status_code in (200, 201):
                return {"status": "draft"}
            raise HTTPException(r.status_code, f"WordPress error: {r.text[:200]}")

    # ── Reply to a WordPress comment from the CRM ──────────────────────────────

    @router.post("/clients/{wp_slug}/comments/{comment_id}/reply")
    async def reply_to_comment(wp_slug: str, comment_id: int, body: dict, user=Depends(get_current_user)):
        """Post a reply to a visitor comment on behalf of the site owner."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")

        reply_text = (body.get("content") or "").strip()
        if not reply_text:
            raise HTTPException(400, "Reply content is required")

        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}

        # First fetch the parent comment to get its post_id
        async with httpx.AsyncClient(timeout=15) as client:
            parent = await client.get(
                f"{site_base}/wp-json/wp/v2/comments/{comment_id}",
                headers=headers,
            )
            if parent.status_code != 200:
                raise HTTPException(404, "Parent comment not found")
            post_id = parent.json().get("post", 0)

            r = await client.post(
                f"{site_base}/wp-json/wp/v2/comments",
                headers=headers,
                json={
                    "post": post_id,
                    "parent": comment_id,
                    "content": reply_text,
                    "author_name": blog.get("business_name", "Site Owner"),
                    "status": "approved",
                },
            )
            if r.status_code in (200, 201):
                return {"status": "replied", "comment_id": r.json().get("id")}
            raise HTTPException(r.status_code, f"WordPress error: {r.text[:200]}")

    # ── Helper: find real WPForms form IDs on a subsite ────────────────────────

    async def _find_all_wpforms_ids(site_base: str, auth_headers: dict) -> dict:
        """
        Returns a dict {contact, order, survey} with the best matching WPForms
        form ID for each page type.  Falls back by position if no keyword match.
        All values default to "" if no forms exist.
        """
        result = {"contact": "", "order": "", "survey": ""}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{site_base}/wp-json/wp/v2/wpforms?per_page=50&orderby=date&order=asc",
                    headers=auth_headers,
                )
                if r.status_code != 200 or not r.json():
                    return result
                forms = r.json()
                titles = [(str(f["id"]), (f.get("title", {}).get("rendered") or "").lower()) for f in forms]
                def _best(keywords):
                    for fid, t in titles:
                        if any(k in t for k in keywords):
                            return fid
                    return ""
                result["contact"] = _best(["contact"]) or (titles[0][0] if titles else "")
                result["order"]   = _best(["order", "inquiry", "booking", "reservation", "quote", "request"]) or (titles[1][0] if len(titles) > 1 else titles[0][0] if titles else "")
                result["survey"]  = _best(["survey", "feedback", "customer", "satisfaction"]) or (titles[-1][0] if titles else "")
        except Exception as exc:
            logger.debug("[blog] _find_all_wpforms_ids failed: %s", exc)
        return result

    async def _find_wpforms_id(site_base: str, auth_headers: dict) -> str:
        ids = await _find_all_wpforms_ids(site_base, auth_headers)
        return ids["contact"]

    # ── Recreate standard pages for an existing client site ───────────────────

    @router.post("/clients/{wp_slug}/recreate-pages")
    async def recreate_pages(wp_slug: str, user=Depends(get_current_user)):
        """
        Creates or updates the standard Zilo pages (contact, forms, survey) for an existing site.
        Safe to run on any site — skips pages that already exist.
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")

        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        if not wp_user:
            raise HTTPException(500, "WordPress credentials not configured")

        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}

        # Look up real WPForms form IDs for all page types
        form_ids = await _find_all_wpforms_ids(site_base, headers)
        contact_form_id = form_ids["contact"]
        order_form_id   = form_ids["order"]
        survey_form_id  = form_ids["survey"]
        wa_number = blog.get("whatsapp_number", "")
        wa_url = (
            f"https://wa.me/{wa_number}?text=Hi%2C+I+found+you+on+Zilo"
            if wa_number
            else "https://wa.me/?text=Hi%2C+I+found+you+on+Zilo"
        )
        contact_intro = (
            "We\u2019d love to hear from you. Reach us instantly on WhatsApp"
            + (" or fill in the form below." if contact_form_id else ".")
        )
        contact_content = (
            "<!-- wp:paragraph -->"
            f"<p>{contact_intro}</p>"
            "<!-- /wp:paragraph -->"
            f"<!-- wp:buttons {{\"layout\":{{\"type\":\"flex\",\"justifyContent\":\"center\"}}}} -->"
            "<div class=\"wp-block-buttons\">"
            "<!-- wp:button {\"style\":{\"color\":{\"background\":\"#25d366\"}},\"textColor\":\"white\"} -->"
            "<div class=\"wp-block-button\">"
            f"<a class=\"wp-block-button__link has-white-color has-text-color has-background\" "
            f"href=\"{wa_url}\" target=\"_blank\" rel=\"noreferrer noopener\">"
            "\U0001f4ac Chat on WhatsApp</a></div>"
            "<!-- /wp:button --></div>"
            "<!-- /wp:buttons -->"
            + (
                "<!-- wp:paragraph --><p></p><!-- /wp:paragraph -->"
                f"<!-- wp:shortcode -->[wpforms id=\"{contact_form_id}\" title=\"false\"]<!-- /wp:shortcode -->"
                if contact_form_id else ""
            )
        )

        def _shortcode_block(fid: str) -> str:
            if fid:
                return (
                    "<!-- wp:paragraph --><p></p><!-- /wp:paragraph -->"
                    f"<!-- wp:shortcode -->[wpforms id=\"{fid}\" title=\"false\"]<!-- /wp:shortcode -->"
                )
            return ""

        pages = [
            {
                "slug": "contact",
                "title": "Contact Us",
                "content": contact_content,
            },
            {
                "slug": "forms",
                "title": "Order Forms",
                "content": (
                    "<!-- wp:paragraph -->"
                    "<p>Fill in the form below to place an order or make an inquiry.</p>"
                    "<!-- /wp:paragraph -->"
                    + _shortcode_block(order_form_id)
                ),
            },
            {
                "slug": "survey",
                "title": "Customer Survey",
                "content": (
                    "<!-- wp:paragraph -->"
                    "<p>We value your feedback! Take 2 minutes to help us serve you better.</p>"
                    "<!-- /wp:paragraph -->"
                    + _shortcode_block(survey_form_id)
                ),
            },
        ]

        created, updated = [], []
        async with httpx.AsyncClient(timeout=20) as client:
            for page in pages:
                # Check if page already exists — update it if so
                chk = await client.get(
                    f"{site_base}/wp-json/wp/v2/pages?slug={page['slug']}&status=any",
                    headers=headers,
                )
                existing = chk.json() if chk.status_code == 200 else []
                if existing:
                    page_id = existing[0]["id"]
                    r = await client.post(
                        f"{site_base}/wp-json/wp/v2/pages/{page_id}",
                        headers=headers,
                        json={"title": page["title"], "slug": page["slug"],
                              "status": "publish", "content": page["content"]},
                    )
                    if r.status_code in (200, 201):
                        updated.append(page["slug"])
                    else:
                        logger.warning("[blog] recreate-pages update %s/%s → %s", wp_slug, page["slug"], r.status_code)
                    continue
                r = await client.post(
                    f"{site_base}/wp-json/wp/v2/pages",
                    headers=headers,
                    json={"title": page["title"], "slug": page["slug"],
                          "status": "publish", "content": page["content"]},
                )
                if r.status_code in (200, 201):
                    created.append(page["slug"])
                else:
                    logger.warning("[blog] recreate-pages %s/%s → %s", wp_slug, page["slug"], r.status_code)

        return {"created": created, "updated": updated}

    # ── Activate plugins on an existing client subsite ────────────────────────

    @router.post("/clients/{wp_slug}/activate-plugins")
    async def activate_plugins(wp_slug: str, user=Depends(get_current_user)):
        """
        Activates wpforms-lite (and woocommerce) on a subsite via WP-CLI.
        Fixes the raw [wpforms ...] shortcode showing as text.
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")

        results = {}
        for plugin in ["wpforms-lite", "woocommerce"]:
            r = await _wp_cli("plugin", "activate", plugin, url=site_base)
            results[plugin] = "ok" if r.returncode == 0 else r.stderr[:120]
            if r.returncode != 0:
                logger.warning("[blog] activate %s on %s: %s", plugin, wp_slug, r.stderr[:150])
            else:
                logger.info("[blog] activated %s on %s", plugin, wp_slug)

        return {"status": "done", "results": results}

    # ── Save / update WhatsApp number for a client site ───────────────────────

    @router.patch("/clients/{wp_slug}/whatsapp")
    async def set_whatsapp_number(wp_slug: str, body: dict, user=Depends(get_current_user)):
        """
        Saves the client's WhatsApp number to MongoDB and immediately patches
        the live WordPress contact page so the 'Chat on WhatsApp' button
        uses the correct wa.me URL.
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        number_raw = (body.get("whatsapp_number") or "").strip()
        # Keep only digits and a leading + (supports any country code)
        import re as _re
        number = _re.sub(r"[^\d+]", "", number_raw)
        # Strip leading + for wa.me URL (wa.me expects digits only)
        number = number.lstrip("+")

        # Persist to DB
        await db.blogs.update_one(
            {"client_id": user_id, "wp_slug": wp_slug},
            {"$set": {"whatsapp_number": number}},
        )

        # Patch the live contact page on WordPress
        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            return {"status": "saved", "wp_updated": False, "whatsapp_number": number}

        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd  = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}

        from urllib.parse import quote
        business = blog.get("business_name", "")
        wa_url = (
            f"https://wa.me/{number}?text={quote(f'Hi, I found {business} on Zilo')}"
            if business
            else f"https://wa.me/{number}?text=Hi%2C+I+found+you+on+Zilo"
        )

        form_id = await _find_wpforms_id(site_base, headers)
        contact_intro = (
            "We\u2019d love to hear from you. Reach us instantly on WhatsApp"
            + (" or fill in the form below." if form_id else ".")
        )
        contact_content = (
            "<!-- wp:paragraph -->"
            f"<p>{contact_intro}</p>"
            "<!-- /wp:paragraph -->"
            f"<!-- wp:buttons {{\"layout\":{{\"type\":\"flex\",\"justifyContent\":\"center\"}}}} -->"
            "<div class=\"wp-block-buttons\">"
            "<!-- wp:button {\"style\":{\"color\":{\"background\":\"#25d366\"}},\"textColor\":\"white\"} -->"
            "<div class=\"wp-block-button\">"
            f"<a class=\"wp-block-button__link has-white-color has-text-color has-background\" "
            f"href=\"{wa_url}\" target=\"_blank\" rel=\"noreferrer noopener\">"
            "\U0001f4ac Chat on WhatsApp</a></div>"
            "<!-- /wp:button --></div>"
            "<!-- /wp:buttons -->"
            + (
                "<!-- wp:paragraph --><p></p><!-- /wp:paragraph -->"
                f"<!-- wp:shortcode -->[wpforms id=\"{form_id}\" title=\"false\"]<!-- /wp:shortcode -->"
                if form_id else ""
            )
        )

        wp_updated = False
        async with httpx.AsyncClient(timeout=15) as client:
            chk = await client.get(
                f"{site_base}/wp-json/wp/v2/pages?slug=contact&status=any",
                headers=headers,
            )
            pages_found = chk.json() if chk.status_code == 200 else []
            if pages_found:
                page_id = pages_found[0]["id"]
                r = await client.post(
                    f"{site_base}/wp-json/wp/v2/pages/{page_id}",
                    headers=headers,
                    json={"content": contact_content, "status": "publish"},
                )
                wp_updated = r.status_code in (200, 201)

        return {"status": "saved", "wp_updated": wp_updated, "whatsapp_number": number}

    # ── Re-seed AI products for a client site ─────────────────────────────────

    @router.post("/clients/{wp_slug}/reseed-products")
    async def reseed_products(wp_slug: str, user=Depends(get_current_user)):
        """
        Re-runs the AI product seeder for a client site.
        Useful when changing industry or after a fresh site install.
        Generates industry-specific products via Claude → pushes to WooCommerce REST.
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable — check WP_BASE_URL env var")

        try:
            from blog.product_seeder import seed_products
            result = await seed_products(
                site_url=site_base,
                business_name=blog.get("business_name", "Business"),
                industry=blog.get("industry", "General"),
                location=blog.get("location", "Nairobi"),
            )
            return {"status": "ok", "products_pushed": result.get("pushed", 0), "detail": result}
        except Exception as exc:
            logger.error("[blog] reseed_products error: %s", exc)
            raise HTTPException(500, str(exc))

    # ── Re-seed AI forms for a client site ────────────────────────────────────

    @router.post("/clients/{wp_slug}/reseed-forms")
    async def reseed_forms(wp_slug: str, user=Depends(get_current_user)):
        """
        Re-runs the AI form seeder for a client site.
        Creates industry-specific WPForms (booking, inquiry, support, etc.).
        """
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable — check WP_BASE_URL env var")

        try:
            from blog.form_seeder import seed_forms
            result = await seed_forms(
                site_url=site_base,
                business_name=blog.get("business_name", "Business"),
                industry=blog.get("industry", "General"),
            )
            return {"status": "ok", "forms_pushed": result.get("pushed", 0), "detail": result}
        except Exception as exc:
            logger.error("[blog] reseed_forms error: %s", exc)
            raise HTTPException(500, str(exc))

    # ── Create a WooCommerce product ───────────────────────────────────────────

    @router.post("/clients/{wp_slug}/products")
    async def create_client_product(wp_slug: str, body: dict, user=Depends(get_current_user)):
        """Create a WooCommerce product on a client subsite."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")
        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")
        wc_key = os.getenv("WC_CONSUMER_KEY", "")
        wc_secret = os.getenv("WC_CONSUMER_SECRET", "")
        if not wc_key:
            raise HTTPException(400, "WooCommerce API keys not configured")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{site_base}/wp-json/wc/v3/products",
                    auth=(wc_key, wc_secret),
                    json=body,
                )
                if r.status_code in (200, 201):
                    return {"status": "created", "product": r.json()}
                raise HTTPException(r.status_code, r.text[:300])
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(500, str(exc))

    # ── Delete a WooCommerce product ───────────────────────────────────────────

    @router.delete("/clients/{wp_slug}/products/{product_id}")
    async def delete_client_product(wp_slug: str, product_id: int, user=Depends(get_current_user)):
        """Delete (trash) a WooCommerce product from a client subsite."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")
        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")
        wc_key = os.getenv("WC_CONSUMER_KEY", "")
        wc_secret = os.getenv("WC_CONSUMER_SECRET", "")
        if not wc_key:
            raise HTTPException(400, "WooCommerce API keys not configured")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.delete(
                    f"{site_base}/wp-json/wc/v3/products/{product_id}?force=true",
                    auth=(wc_key, wc_secret),
                )
                if r.status_code in (200, 204):
                    return {"status": "deleted"}
                raise HTTPException(r.status_code, r.text[:300])
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(500, str(exc))

    # ── Get site customisation settings ────────────────────────────────────────

    @router.get("/clients/{wp_slug}/site-settings")
    async def get_site_settings(wp_slug: str, user=Depends(get_current_user)):
        """Return stored site customisation settings (MongoDB + live WP title/tagline)."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")
        site_base = await _blog_url_for_response(db, blog)
        stored = blog.get("site_settings", {})
        result = {
            "title":        stored.get("title", blog.get("business_name", "")),
            "tagline":      stored.get("tagline", ""),
            "logo_url":     stored.get("logo_url", ""),
            "accent_color": stored.get("accent_color", "#009B3A"),
            "button_color": stored.get("button_color", "#009B3A"),
            "phone":        stored.get("phone", ""),
            "email":        stored.get("email", ""),
            "whatsapp":     stored.get("whatsapp", ""),
            "address":      stored.get("address", ""),
            "facebook":     stored.get("facebook", ""),
            "instagram":    stored.get("instagram", ""),
            "tiktok":       stored.get("tiktok", ""),
            "twitter":      stored.get("twitter", ""),
            "front_page":   stored.get("front_page", "shop"),
        }
        if site_base:
            wp_user = os.getenv("WP_ADMIN_USER", "")
            wp_pwd  = os.getenv("WP_ADMIN_APP_PASSWORD", "")
            auth_h  = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        f"{site_base}/wp-json/wp/v2/settings",
                        headers={"Authorization": f"Basic {auth_h}"},
                    )
                    if r.status_code == 200:
                        wp = r.json()
                        result["title"]   = wp.get("title",       result["title"])
                        result["tagline"] = wp.get("description", result["tagline"])
            except Exception:
                pass
        return result

    # ── Update site customisation settings ─────────────────────────────────────

    @router.patch("/clients/{wp_slug}/site-settings")
    async def update_site_settings(wp_slug: str, body: dict, user=Depends(get_current_user)):
        """Push site customisation to WordPress and persist to MongoDB."""
        import subprocess as _sp, json as _json
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")
        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            raise HTTPException(400, "Site URL unavailable")

        wp_user  = os.getenv("WP_ADMIN_USER", "")
        wp_pwd   = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        auth_h   = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        wp_hdrs  = {"Authorization": f"Basic {auth_h}", "Content-Type": "application/json"}
        cli_path = os.getenv("WP_CLI_PATH", "/var/www/html/zilo")
        errors: list = []

        def _wpcli(*args, timeout=15):
            return _sp.run(
                ["wp", "--allow-root", f"--path={cli_path}", f"--url={site_base}", *args],
                capture_output=True, text=True, timeout=timeout,
            )

        # 1. Title + tagline via WP REST API
        wp_payload: dict = {}
        if body.get("title"):
            wp_payload["title"] = body["title"]
        if "tagline" in body:
            wp_payload["description"] = body["tagline"]
        if wp_payload:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(
                        f"{site_base}/wp-json/wp/v2/settings",
                        headers=wp_hdrs, json=wp_payload,
                    )
                    if r.status_code not in (200, 201):
                        errors.append(f"WP settings {r.status_code}")
            except Exception as exc:
                errors.append(f"WP settings: {exc}")

        # 2. Accent/button colours → Astra settings option
        accent = body.get("accent_color", "")
        button = body.get("button_color", accent)
        if accent:
            try:
                raw = _wpcli("option", "get", "astra-settings", "--format=json")
                try:
                    astra = _json.loads(raw.stdout.strip()) if raw.returncode == 0 else {}
                except Exception:
                    astra = {}
                astra.update({
                    "link-color": accent,
                    "theme-color": button,
                    "heading-base-color": accent,
                    "button-bg-color": button,
                    "button-bg-h-color": accent,
                })
                _wpcli("option", "update", "astra-settings", _json.dumps(astra))
            except Exception as exc:
                errors.append(f"Astra colors: {exc}")

        # 3. Front page / Blog page layout
        front_pref = body.get("front_page")
        if front_pref in ("shop", "blog"):
            try:
                # Find IDs
                r_shop = _wpcli("post", "list", "--post_type=page", "--name=shop", "--format=ids")
                r_blog = _wpcli("post", "list", "--post_type=page", "--name=blog", "--format=ids")
                
                shop_id = r_shop.stdout.strip() if r_shop.returncode == 0 else None
                blog_id = r_blog.stdout.strip() if r_blog.returncode == 0 else None

                if front_pref == "shop" and shop_id:
                    _wpcli("option", "update", "show_on_front", "page")
                    _wpcli("option", "update", "page_on_front", shop_id)
                    if blog_id:
                        _wpcli("option", "update", "page_for_posts", blog_id)
                elif front_pref == "blog":
                    _wpcli("option", "update", "show_on_front", "posts")
                    # Optionally clear these to avoid confusion
                    # _wpcli("option", "update", "page_on_front", "0")
                    # _wpcli("option", "update", "page_for_posts", "0")
                
                logger.info(f"[blog] Updated front_page preference to {front_pref} for {wp_slug}")
            except Exception as exc:
                errors.append(f"Front page setting: {exc}")

        # 4. Social links → Astra settings option
        social_map = {"facebook": "facebook-link", "instagram": "instagram-link",
                      "twitter": "twitter-link", "tiktok": "tiktok-link"}
        social_updates = {v: body[k] for k, v in social_map.items() if k in body and body[k]}
        if social_updates:
            try:
                raw = _wpcli("option", "get", "astra-settings", "--format=json")
                try:
                    astra = _json.loads(raw.stdout.strip()) if raw.returncode == 0 else {}
                except Exception:
                    astra = {}
                astra.update(social_updates)
                _wpcli("option", "update", "astra-settings", _json.dumps(astra))
            except Exception as exc:
                errors.append(f"Social links: {exc}")

        # 5. Persist everything to MongoDB
        allowed = {"title", "tagline", "logo_url", "accent_color", "button_color", "front_page",
                   "phone", "email", "whatsapp", "address",
                   "facebook", "instagram", "tiktok", "twitter"}
        to_save = {k: v for k, v in body.items() if k in allowed}
        if to_save:
            await db.blogs.update_one(
                {"client_id": user_id, "wp_slug": wp_slug},
                {"$set": {f"site_settings.{k}": v for k, v in to_save.items()}},
            )
        return {"status": "ok", "errors": errors}

    # ── Sync stats for a client site ───────────────────────────────────────────

    @router.post("/clients/{wp_slug}/sync")
    async def sync_client_stats(wp_slug: str, user=Depends(get_current_user)):
        """Pull live post count, order count and product count from WP/WC and persist them."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id, "wp_slug": wp_slug})
        if not blog:
            raise HTTPException(404, "Site not found")

        site_base = await _blog_url_for_response(db, blog)
        if not site_base:
            return {"status": "skipped", "reason": "Site URL unavailable"}

        wp_user = os.getenv("WP_ADMIN_USER", "")
        wp_pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
        wc_key = os.getenv("WC_CONSUMER_KEY", "")
        wc_secret = os.getenv("WC_CONSUMER_SECRET", "")

        auth_header = base64.b64encode(f"{wp_user}:{wp_pwd}".encode()).decode()
        wp_headers = {"Authorization": f"Basic {auth_header}"}

        stats: dict = {}
        errors: list = []

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.get(f"{site_base}/wp-json/wp/v2/posts?per_page=1", headers=wp_headers)
                if r.status_code == 200:
                    stats["posts_count"] = int(r.headers.get("X-WP-Total", blog.get("posts_count", 0)))
            except Exception as exc:
                errors.append(f"posts: {exc}")

            if wc_key:
                try:
                    r = await client.get(
                        f"{site_base}/wp-json/wc/v3/orders?per_page=1",
                        auth=(wc_key, wc_secret),
                    )
                    if r.status_code == 200:
                        stats["orders_count"] = int(r.headers.get("X-WP-Total", 0))
                except Exception as exc:
                    errors.append(f"orders: {exc}")

                try:
                    r = await client.get(
                        f"{site_base}/wp-json/wc/v3/products?per_page=1",
                        auth=(wc_key, wc_secret),
                    )
                    if r.status_code == 200:
                        stats["products_count"] = int(r.headers.get("X-WP-Total", 0))
                except Exception as exc:
                    errors.append(f"products: {exc}")

        if stats:
            stats["last_synced"] = datetime.utcnow().isoformat()
            await db.blogs.update_one(
                {"client_id": user_id, "wp_slug": wp_slug},
                {"$set": stats},
            )

        return {"status": "ok", "stats": stats, "errors": errors}

    return router
