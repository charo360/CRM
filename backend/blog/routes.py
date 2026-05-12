"""
Zilo Autoblogging — FastAPI Routes.
Prefix: /api/blog
"""
import base64
import logging
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from blog.blog_service import ZiloBlogService, wp_subsite_public_url
from blog.topic_generator import generate_topic_from_chats
from blog.post_generator import generate_blog_post
from blog.blog_scheduler import publish_daily_posts

logger = logging.getLogger(__name__)


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
        excerpt = req.excerpt or (req.content[:155].replace("<", "").replace(">", "") + "…")
        try:
            result = await blog_service.publish_post(
                wp_slug=blog["wp_slug"],
                title=req.title,
                content=req.content,
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
