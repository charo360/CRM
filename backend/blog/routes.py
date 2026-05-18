"""Zilo Autoblog — HTTP routes mounted at /api/blog/*"""
from __future__ import annotations
import logging, os
from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def make_blog_router(db, get_current_user):
    router = APIRouter(prefix="/blog", tags=["blog"])
    user_dep = Depends(get_current_user)

    from blog.blog_service import ZiloBlogService
    svc = ZiloBlogService(db)

    def _uid(user) -> str:
        raw = user.get("_id") or user.get("id", "")
        return str(raw)

    # ── Status ────────────────────────────────────────────────────────────────

    @router.get("/status")
    async def get_status(user=user_dep):
        uid = _uid(user)
        blog = await db.blogs.find_one({"client_id": uid})
        if not blog:
            return {"connected": False}
        posts_count = await db.posts_log.count_documents({"client_id": uid})
        last_post = await db.posts_log.find_one(
            {"client_id": uid}, sort=[("published_at", -1)]
        )
        return {
            "connected": True,
            "active": blog.get("active", True),
            "blog_url": blog.get("blog_url", ""),
            "wp_slug": blog.get("wp_slug", ""),
            "client_id": uid,
            "posts_count": posts_count,
            "industry": blog.get("industry", ""),
            "location": blog.get("location", ""),
            "business_name": blog.get("business_name", ""),
            "schedule": blog.get("schedule", "weekly"),
            "last_published": (
                last_post.get("published_at").isoformat()
                if last_post and last_post.get("published_at")
                else None
            ),
        }

    # ── Posts list ────────────────────────────────────────────────────────────

    @router.get("/posts/{client_id}")
    async def get_posts(client_id: str, user=user_dep):
        uid = _uid(user)
        if client_id != uid:
            raise HTTPException(status_code=403, detail="Forbidden")
        raw = await db.posts_log.find(
            {"client_id": uid}, sort=[("published_at", -1)]
        ).limit(50).to_list(50)
        posts = []
        for p in raw:
            posts.append({
                "title": p.get("title", "Untitled"),
                "published_at": (
                    p["published_at"].isoformat()
                    if isinstance(p.get("published_at"), datetime)
                    else str(p.get("published_at", ""))
                ),
                "wp_id": p.get("wp_id"),
                "url": p.get("post_url") or p.get("url"),
                "status": p.get("status", "published"),
                "template": p.get("template_used"),
                "industry": p.get("industry"),
            })
        return {"posts": posts}

    # ── Provision ─────────────────────────────────────────────────────────────

    class ProvisionBody(BaseModel):
        business_name: str
        client_email: Optional[str] = None
        industry: Optional[str] = "services"
        location: Optional[str] = ""

    @router.post("/provision")
    async def provision(body: ProvisionBody, user=user_dep):
        uid = _uid(user)
        email = body.client_email or user.get("email", "")
        existing = await db.blogs.find_one({"client_id": uid})
        if existing:
            posts_count = await db.posts_log.count_documents({"client_id": uid})
            return {
                "connected": True,
                "active": existing.get("active", True),
                "blog_url": existing.get("blog_url", ""),
                "wp_slug": existing.get("wp_slug", ""),
                "client_id": uid,
                "posts_count": posts_count,
                "industry": existing.get("industry", body.industry),
                "location": existing.get("location", body.location),
                "business_name": existing.get("business_name", body.business_name),
            }
        try:
            result = await svc.create_client_blog(
                client_id=uid,
                business_name=body.business_name,
                client_email=email,
                industry=body.industry or "services",
                location=body.location or "",
            )
        except Exception as exc:
            logger.error("[blog] provision error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))
        blog = await db.blogs.find_one({"client_id": uid})
        return {
            "connected": True,
            "active": True,
            "blog_url": result.get("blog_url", ""),
            "wp_slug": blog.get("wp_slug", "") if blog else "",
            "client_id": uid,
            "posts_count": 0,
            "industry": body.industry,
            "location": body.location,
            "business_name": body.business_name,
        }

    # ── Publish now ───────────────────────────────────────────────────────────

    class ClientIdBody(BaseModel):
        client_id: str

    @router.post("/publish-now")
    async def publish_now(body: ClientIdBody, user=user_dep):
        uid = _uid(user)
        if body.client_id != uid:
            raise HTTPException(status_code=403, detail="Forbidden")
        blog = await db.blogs.find_one({"client_id": uid})
        if not blog:
            raise HTTPException(status_code=404, detail="No blog found")
        try:
            from blog.post_generator import PostGenerator
            gen = PostGenerator(db)
            result = await gen.generate_and_publish(uid)
            return {"ok": True, "template_used": result.get("template_used"), "post_url": result.get("post_url")}
        except Exception as exc:
            logger.error("[blog] publish_now error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Activate / Deactivate ─────────────────────────────────────────────────

    @router.post("/activate")
    async def activate(body: ClientIdBody, user=user_dep):
        uid = _uid(user)
        if body.client_id != uid:
            raise HTTPException(status_code=403, detail="Forbidden")
        await db.blogs.update_one({"client_id": uid}, {"$set": {"active": True}})
        return {"ok": True}

    @router.post("/deactivate")
    async def deactivate(body: ClientIdBody, user=user_dep):
        uid = _uid(user)
        if body.client_id != uid:
            raise HTTPException(status_code=403, detail="Forbidden")
        await db.blogs.update_one({"client_id": uid}, {"$set": {"active": False}})
        return {"ok": True}

    # ── Refresh favicon ───────────────────────────────────────────────────────

    @router.post("/refresh-favicon")
    async def refresh_favicon(user=user_dep):
        uid = _uid(user)
        blog = await db.blogs.find_one({"client_id": uid})
        if not blog:
            raise HTTPException(status_code=404, detail="No blog found")
        subsite_url = blog.get("blog_url", "")
        wp_slug = blog.get("wp_slug", "")
        try:
            import httpx, base64
            logo_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "static", "zilo-logo.png")
            )
            if not os.path.exists(logo_path):
                return {"status": "skipped", "message": "Logo file not found on server"}
            with open(logo_path, "rb") as f:
                logo_bytes = f.read()
            wp_user = os.environ.get("WP_ADMIN_USER", "ziloadmin")
            wp_pass = os.environ.get("WP_ADMIN_PASSWORD", "")
            token = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
            headers = {"Authorization": f"Basic {token}"}
            async with httpx.AsyncClient(timeout=20) as hc:
                mr = await hc.post(
                    f"{subsite_url}/wp-json/wp/v2/media",
                    headers={**headers, "Content-Disposition": f'attachment; filename="zilo-logo.png"', "Content-Type": "image/png"},
                    content=logo_bytes,
                )
                if mr.status_code != 201:
                    return {"status": "error", "message": f"Media upload failed: {mr.status_code}"}
                media_id = mr.json().get("id")
                await hc.post(
                    f"{subsite_url}/wp-json/wp/v2/settings",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"site_icon": media_id},
                )
        except Exception as exc:
            logger.warning("[blog] favicon refresh error: %s", exc)
            return {"status": "error", "message": str(exc)}
        return {"status": "ok", "message": "Favicon updated. Refresh your WordPress site to see it."}

    # ── Keyword tracker ───────────────────────────────────────────────────────

    class KeywordBody(BaseModel):
        keyword: str
        search_volume: Optional[int] = 0
        difficulty: Optional[str] = "medium"
        intent: Optional[str] = "informational"

    @router.get("/keyword-tracker")
    async def get_keyword_tracker(user=user_dep):
        uid = _uid(user)
        doc = await db.blog_keyword_tracker.find_one({"user_id": uid})
        return {"keywords": (doc or {}).get("keywords", [])}

    @router.post("/keyword-tracker")
    async def save_keyword_to_tracker(body: KeywordBody, user=user_dep):
        uid = _uid(user)
        kw = {
            "keyword": body.keyword,
            "search_volume": body.search_volume,
            "difficulty": body.difficulty,
            "intent": body.intent,
            "added_at": datetime.utcnow().isoformat(),
        }
        await db.blog_keyword_tracker.update_one(
            {"user_id": uid},
            {"$addToSet": {"keywords": kw}},
            upsert=True,
        )
        return {"ok": True}

    @router.post("/enrich-volumes")
    async def enrich_volumes(user=user_dep):
        uid = _uid(user)
        doc = await db.blog_keyword_tracker.find_one({"user_id": uid})
        if not doc:
            return {"updated": 0}
        keywords = doc.get("keywords", [])
        updated = 0
        for kw in keywords:
            if not kw.get("search_volume"):
                kw["search_volume"] = 0
                updated += 1
        if updated:
            await db.blog_keyword_tracker.update_one(
                {"user_id": uid}, {"$set": {"keywords": keywords}}
            )
        return {"updated": updated}

    # ── Publish from SEO write tool ───────────────────────────────────────────

    class PublishFromSeoBody(BaseModel):
        title: str
        content: str
        keywords: Optional[list] = []
        excerpt: Optional[str] = ""

    @router.post("/publish-from-seo")
    async def publish_from_seo(body: PublishFromSeoBody, user=user_dep):
        uid = _uid(user)
        blog = await db.blogs.find_one({"client_id": uid})
        if not blog:
            raise HTTPException(status_code=404, detail="No blog found")
        try:
            result = await svc.publish_post(
                wp_slug=blog.get("wp_slug", ""),
                title=body.title,
                content=body.content,
                excerpt=body.excerpt or "",
                keywords=body.keywords or [],
            )
            return {"ok": True, "post_url": result.get("post_url")}
        except Exception as exc:
            logger.error("[blog] publish_from_seo error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Link post to keyword ──────────────────────────────────────────────────

    class LinkBody(BaseModel):
        keyword: str
        post_title: str
        post_url: Optional[str] = None

    @router.post("/link-keyword")
    async def link_keyword(body: LinkBody, user=user_dep):
        uid = _uid(user)
        await db.blog_keyword_tracker.update_one(
            {"user_id": uid, "keywords.keyword": body.keyword},
            {"$set": {
                "keywords.$.linked_post_title": body.post_title,
                "keywords.$.linked_post_url": body.post_url,
            }},
        )
        return {"ok": True}

    # ── Client list (admin) ───────────────────────────────────────────────────

    @router.get("/clients")
    async def list_clients(user=user_dep):
        raw = await db.blogs.find({}).to_list(200)
        sites = []
        for b in raw:
            cid = b.get("client_id", "")
            posts_count = await db.posts_log.count_documents({"client_id": cid})
            sites.append({
                "client_id": cid,
                "business_name": b.get("business_name", ""),
                "blog_url": b.get("blog_url", ""),
                "wp_slug": b.get("wp_slug", ""),
                "active": b.get("active", True),
                "industry": b.get("industry", ""),
                "location": b.get("location", ""),
                "posts_count": posts_count,
            })
        return {"sites": sites}

    @router.get("/clients/pending-counts")
    async def pending_counts(user=user_dep):
        return {"counts": {}}

    return router
