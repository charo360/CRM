"""
Zilo Autoblogging — FastAPI Routes.
Prefix: /api/blog
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from blog.blog_service import ZiloBlogService
from blog.topic_generator import generate_topic_from_chats
from blog.post_generator import generate_blog_post
from blog.blog_scheduler import publish_daily_posts

logger = logging.getLogger(__name__)


class CreateBlogRequest(BaseModel):
    client_id: str
    business_name: str
    client_email: str
    industry: str
    location: str


class ManualPublishRequest(BaseModel):
    client_id: str


def make_blog_router(db, get_current_user):
    router = APIRouter(prefix="/api/blog", tags=["blog"])
    blog_service = ZiloBlogService(db)

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
        blog = await db.blogs.find_one({"client_id": client_id})
        if not blog:
            return {"connected": False}

        last_posted = blog.get("last_posted_at")
        return {
            "connected": True,
            "blog_url": blog.get("blog_url"),
            "wp_slug": blog.get("wp_slug"),
            "industry": blog.get("industry"),
            "location": blog.get("location"),
            "plan": blog.get("plan", "free"),
            "posts_count": blog.get("posts_count", 0),
            "last_posted_at": last_posted.isoformat() if last_posted else None,
            "active": blog.get("active", True),
        }

    # ── My blog (current authenticated user) ──────────────────────────────────

    @router.get("/my")
    async def get_my_blog(user=Depends(get_current_user)):
        """Returns the blog record for the currently authenticated user."""
        user_id = str(user.get("_id") or user.get("id", ""))
        blog = await db.blogs.find_one({"client_id": user_id})
        if not blog:
            return {"connected": False}

        last_posted = blog.get("last_posted_at")
        return {
            "connected": True,
            "blog_url": blog.get("blog_url"),
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
        blog = await db.blogs.find_one({"client_id": req.client_id})
        if not blog:
            raise HTTPException(status_code=404, detail="Blog not found")

        try:
            topic = await generate_topic_from_chats(db, req.client_id)
            post = await generate_blog_post(
                business_name=blog["business_name"],
                industry=blog["industry"],
                location=blog["location"],
                topic=topic,
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
            }
        except Exception as e:
            logger.error(f"[blog/publish-now] {e}")
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
        posts = await db.posts_log.find(
            {"client_id": client_id},
            {"_id": 0},
        ).sort("published_at", -1).limit(limit).to_list(None)

        for p in posts:
            if isinstance(p.get("published_at"), datetime):
                p["published_at"] = p["published_at"].isoformat()

        return {"posts": posts}

    return router
