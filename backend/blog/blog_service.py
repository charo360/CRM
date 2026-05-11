"""
Zilo Autoblogging — WordPress Multisite service.
Handles subsite creation and post publishing via WP REST API.
"""
import httpx
import base64
import os
import secrets
import string
import logging
from datetime import datetime
from slugify import slugify

logger = logging.getLogger(__name__)


def _get_wp_auth() -> str:
    user = os.getenv("WP_ADMIN_USER", "")
    password = os.getenv("WP_ADMIN_APP_PASSWORD", "")
    return base64.b64encode(f"{user}:{password}".encode()).decode()


def _wp_headers() -> dict:
    return {
        "Authorization": f"Basic {_get_wp_auth()}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return os.getenv("WP_BASE_URL", "https://zilo.pro").rstrip("/")


def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class ZiloBlogService:
    """Creates WordPress subsites and publishes posts on behalf of Zilo clients."""

    def __init__(self, db):
        self.db = db

    # ── Public API ─────────────────────────────────────────────────────────────

    async def create_client_blog(
        self,
        client_id: str,
        business_name: str,
        client_email: str,
        industry: str,
        location: str,
    ) -> dict:
        """
        Auto-creates a WordPress subsite for a new Zilo client.
        Called when client clicks 'Activate My Blog' on the Zilo dashboard.
        """
        slug = slugify(business_name)
        base = _base_url()
        headers = _wp_headers()

        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Create a WordPress user for the business
            user_res = await client.post(
                f"{base}/wp-json/wp/v2/users",
                headers=headers,
                json={
                    "username": slug,
                    "email": client_email,
                    "password": _generate_password(),
                    "roles": ["author"],
                },
            )
            wp_user = user_res.json() if user_res.status_code in (200, 201) else {}
            if user_res.status_code not in (200, 201):
                logger.warning(
                    f"[blog] WP user creation returned {user_res.status_code}: {user_res.text[:300]}"
                )

        # 2. Create subsite via WP-CLI on the server
        site_url = f"https://{slug}.zilo.pro"
        try:
            import subprocess
            result = subprocess.run(
                [
                    "wp", "--allow-root",
                    "--path=/var/www/html/zilo",
                    "site", "create",
                    f"--slug={slug}",
                    f"--title={business_name}",
                    f"--email={client_email}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"[blog] wp site create stderr: {result.stderr[:300]}")
        except Exception as e:
            logger.warning(f"[blog] wp site create failed (may be non-VPS env): {e}")

        # 3. Apply industry-specific theme
        await self._apply_industry_theme(slug, industry)

        # 4. Persist to MongoDB
        blog_doc = {
            "client_id": client_id,
            "business_name": business_name,
            "client_email": client_email,
            "industry": industry,
            "location": location,
            "blog_url": site_url,
            "wp_slug": slug,
            "wp_user_id": wp_user.get("id"),
            "active": True,
            "plan": "free",
            "posts_count": 0,
            "created_at": datetime.utcnow(),
        }
        await self.db.blogs.update_one(
            {"client_id": client_id},
            {"$set": blog_doc},
            upsert=True,
        )

        logger.info(f"[blog] Created blog for '{business_name}' → {site_url}")
        return {"blog_url": site_url, "status": "created"}

    async def publish_post(
        self,
        wp_slug: str,
        title: str,
        content: str,
        excerpt: str,
        keywords: list,
        category: str = "Business",
    ) -> dict:
        """
        Publishes a single blog post to a client's WordPress subsite.
        """
        subsite_url = f"https://{wp_slug}.zilo.pro"
        headers = _wp_headers()

        async with httpx.AsyncClient(timeout=30) as client:
            post_res = await client.post(
                f"{subsite_url}/wp-json/wp/v2/posts",
                headers=headers,
                json={
                    "title": title,
                    "content": content,
                    "excerpt": excerpt,
                    "status": "publish",
                    "tags": keywords,
                    "meta": {
                        "_yoast_wpseo_focuskw": keywords[0] if keywords else "",
                        "_yoast_wpseo_metadesc": excerpt,
                    },
                },
            )

        if post_res.status_code == 201:
            post = post_res.json()
            blog = await self.db.blogs.find_one({"wp_slug": wp_slug})
            client_id = blog.get("client_id") if blog else None

            # Update blog stats
            await self.db.blogs.update_one(
                {"wp_slug": wp_slug},
                {
                    "$inc": {"posts_count": 1},
                    "$set": {"last_posted_at": datetime.utcnow()},
                },
            )

            # Log to posts_log for rate-limit tracking
            if client_id:
                await self.db.posts_log.insert_one(
                    {
                        "client_id": client_id,
                        "wp_slug": wp_slug,
                        "post_id": post.get("id"),
                        "post_url": post.get("link"),
                        "title": title,
                        "published_at": datetime.utcnow(),
                    }
                )

            logger.info(f"[blog] Published '{title}' → {post.get('link')}")
            return {"post_url": post.get("link"), "post_id": post.get("id")}
        else:
            raise RuntimeError(
                f"WP publish failed ({post_res.status_code}): {post_res.text[:400]}"
            )

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _apply_industry_theme(self, slug: str, industry: str):
        """Sets the correct Zilo child theme based on business industry."""
        theme_map = {
            "salon": "zilo-salon",
            "beauty": "zilo-salon",
            "hair": "zilo-salon",
            "restaurant": "zilo-restaurant",
            "food": "zilo-restaurant",
            "hotel": "zilo-restaurant",
            "catering": "zilo-restaurant",
            "retail": "zilo-retail",
            "hardware": "zilo-retail",
            "shop": "zilo-retail",
            "supermarket": "zilo-retail",
            "services": "zilo-services",
            "plumber": "zilo-services",
            "electrician": "zilo-services",
            "mechanic": "zilo-services",
            "startup": "zilo-startup",
            "tech": "zilo-startup",
            "saas": "zilo-startup",
            "app": "zilo-startup",
            "software": "zilo-startup",
            "agency": "zilo-startup",
            "consulting": "zilo-startup",
            "fintech": "zilo-startup",
        }
        theme = theme_map.get(industry.lower(), "zilo-default")

        try:
            import subprocess
            subprocess.run(
                [
                    "wp", "--allow-root",
                    "--path=/var/www/html/zilo",
                    f"--url=https://{slug}.zilo.pro",
                    "theme", "activate", theme,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except Exception as e:
            logger.warning(f"[blog] theme activate failed (may be non-VPS env): {e}")
