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
from urllib.parse import urlparse
from slugify import slugify

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular import issues at module load time
async def _seed_products(site_url, business_name, industry, location):
    from blog.product_seeder import seed_products
    return await seed_products(site_url, business_name, industry, location)

async def _seed_forms(site_url, business_name, industry):
    from blog.form_seeder import seed_forms
    return await seed_forms(site_url, business_name, industry)


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


def _wp_cli_path() -> str:
    """Filesystem path passed to `wp --path=...` (your multisite WP root on the server)."""
    return os.getenv("WP_CLI_PATH", "/var/www/html/zilo").rstrip("/")


def _multisite_subdirectory() -> bool:
    """Subdirectory multisite: sites live at {base}/{slug}/ instead of {slug}.{network_host}."""
    return os.getenv("WP_MULTISITE_SUBDIRECTORY", "").strip().lower() in ("1", "true", "yes")


def _subdomain_parent_host() -> str:
    """
    Host used for subdomain-style multisite URLs: https://{slug}.{host}
    Defaults to the host part of WP_BASE_URL (e.g. mybrand.com → https://salon.mybrand.com).
    Override if subsites sit on a different parent (WP_SUBDOMAIN_PARENT_HOST=mybrand.com).
    """
    override = os.getenv("WP_SUBDOMAIN_PARENT_HOST", "").strip().lower()
    if override:
        return override.lstrip(".")
    parsed = urlparse(_base_url())
    host = (parsed.netloc or "zilo.pro").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def wp_subsite_public_url(wp_slug: str) -> str:
    """
    Full public URL of a client subsite (must match WordPress Sites → URLs).
    """
    slug = (wp_slug or "").strip().strip("/")
    if not slug:
        raise ValueError("wp_slug required")
    if _multisite_subdirectory():
        return f"{_base_url()}/{slug}".rstrip("/")
    host = _subdomain_parent_host()
    return f"https://{slug}.{host}".rstrip("/")


def _wp_internal_subsite_url(wp_slug: str) -> str:
    """
    The URL WordPress actually registers the subsite under (slug.{WP_BASE_URL host}).
    Used for WP-CLI --url= flag. May differ from the public URL when
    WP_SUBDOMAIN_PARENT_HOST overrides the parent domain.
    """
    slug = (wp_slug or "").strip().strip("/")
    if _multisite_subdirectory():
        return f"{_base_url()}/{slug}".rstrip("/")
    parsed = urlparse(_base_url())
    base_host = (parsed.netloc or "blogs.zilo.pro").lower().lstrip("www.").lstrip(".")
    return f"https://{slug}.{base_host}".rstrip("/")


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
        site_url = wp_subsite_public_url(slug)      # public URL (slug.zilo.pro)
        internal_url = _wp_internal_subsite_url(slug)  # WP-internal URL (slug.blogs.zilo.pro)
        cli_path = _wp_cli_path()
        blog_id: int | None = None
        try:
            import subprocess
            result = subprocess.run(
                [
                    "wp", "--allow-root",
                    f"--path={cli_path}",
                    "site", "create",
                    f"--slug={slug}",
                    f"--title={business_name}",
                    f"--email={client_email}",
                    "--porcelain",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                try:
                    blog_id = int(result.stdout.strip())
                    logger.info(f"[blog] wp site created blog_id={blog_id} at {internal_url}")
                except ValueError:
                    pass
            else:
                logger.warning(f"[blog] wp site create stderr: {result.stderr[:300]}")
        except Exception as e:
            logger.warning(f"[blog] wp site create failed (may be non-VPS env): {e}")

        # 2b. Domain mapping: point slug.zilo.pro → the WordPress subsite
        if blog_id and site_url != internal_url:
            try:
                import subprocess
                public_domain = site_url.replace("https://", "").replace("http://", "")
                subprocess.run(
                    ["wp", "--allow-root", f"--path={cli_path}", "db", "query",
                     f"UPDATE wp_blogs SET domain='{public_domain}' WHERE blog_id={blog_id};"],
                    capture_output=True, text=True, timeout=15,
                )
                subprocess.run(
                    ["wp", "--allow-root", f"--path={cli_path}", "db", "query",
                     f"UPDATE wp_{blog_id}_options SET option_value='{site_url}' "
                     f"WHERE option_name='siteurl' OR option_name='home';"],
                    capture_output=True, text=True, timeout=15,
                )
                logger.info(f"[blog] Domain mapped blog_id={blog_id} → {site_url}")
            except Exception as exc:
                logger.warning(f"[blog] domain mapping failed: {exc}")

        # 3. Apply industry-specific theme
        await self._apply_industry_theme(slug, industry)

        # 4. Activate plugins (WooCommerce shop + WPForms) — use public URL (now mapped)
        await self._activate_site_plugins(slug, site_url)

        # 5. AI-seed products (industry-specific via Claude → WooCommerce REST)
        prod_result = await _seed_products(site_url, business_name, industry, location)
        logger.info(f"[blog] AI products seeded: {prod_result}")

        # 6. AI-seed forms (industry-specific WPForms)
        form_result = await _seed_forms(site_url, business_name, industry)
        logger.info(f"[blog] AI forms seeded: {form_result}")

        # 7. Persist to MongoDB
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
            "features": {"shop": True, "forms": True, "blog": True},
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
        subsite_url = wp_subsite_public_url(wp_slug)
        headers = _wp_headers()

        async with httpx.AsyncClient(timeout=30) as client:
            kw_list = keywords if isinstance(keywords, list) else []
            focus_kw = (kw_list[0] if kw_list and isinstance(kw_list[0], str) else "") or ""
            post_res = await client.post(
                f"{subsite_url}/wp-json/wp/v2/posts",
                headers=headers,
                json={
                    "title": title,
                    "content": content,
                    "excerpt": excerpt,
                    "status": "publish",
                    # WordPress expects tag *IDs* here, not keyword strings — omit to avoid 4xx/500 from REST.
                    "meta": {
                        "_yoast_wpseo_focuskw": focus_kw,
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

    async def _activate_site_plugins(self, slug: str, site_url: str):
        """
        Activates WooCommerce + WPForms and runs WooCommerce initial setup
        (shop/cart/checkout pages, sample product, permalink flush) via WP-CLI.
        """
        import subprocess
        cli_path = _wp_cli_path()

        def _wp(*args, timeout=30):
            return subprocess.run(
                ["wp", "--allow-root", f"--path={cli_path}", f"--url={site_url}", *args],
                capture_output=True, text=True, timeout=timeout,
            )

        # 1. Activate plugins
        for plugin in ["woocommerce", "wpforms-lite"]:
            try:
                r = _wp("plugin", "activate", plugin)
                if r.returncode != 0:
                    logger.warning(f"[blog] activate {plugin}: {r.stderr[:150]}")
                else:
                    logger.info(f"[blog] {plugin} activated for {slug}")
            except Exception as exc:
                logger.warning(f"[blog] activate {plugin} failed: {exc}")

        # 2. WooCommerce: create core pages (shop, cart, checkout, my-account)
        try:
            r = _wp("wc", "tool", "run", "install_pages", "--user=1")
            if r.returncode != 0:
                logger.warning(f"[blog] wc install_pages: {r.stderr[:150]}")
        except Exception as exc:
            logger.warning(f"[blog] wc install_pages failed: {exc}")

        # 3. Import WooCommerce sample products (built-in XML demo data)
        try:
            sample_xml = f"{cli_path}/wp-content/plugins/woocommerce/sample-data/sample_products.xml"
            r = _wp(
                "import", sample_xml,
                "--authors=skip",
                "--quiet",
                timeout=60,
            )
            if r.returncode != 0:
                logger.warning(f"[blog] wc sample import: {r.stderr[:150]}")
            else:
                logger.info(f"[blog] WooCommerce sample products imported for {slug}")
        except Exception as exc:
            logger.warning(f"[blog] wc sample import failed: {exc}")

        # 4. Set permalink structure to /%postname%/ (required for WC REST API)
        try:
            _wp("rewrite", "structure", "/%postname%/", "--hard")
            _wp("rewrite", "flush", "--hard")
        except Exception as exc:
            logger.warning(f"[blog] rewrite flush failed: {exc}")

        # 5. Create the standard Zilo client pages
        pages = [
            {
                "slug": "forms",
                "title": "Order Forms",
                "content": (
                    "<!-- wp:paragraph -->"
                    "<p>Fill in the form below to place an order or make an inquiry. "
                    "We'll get back to you via WhatsApp within minutes.</p>"
                    "<!-- /wp:paragraph -->"
                    "\n[wpforms id=\"\" title=\"false\"]"
                ),
            },
            {
                "slug": "survey",
                "title": "Customer Survey",
                "content": (
                    "<!-- wp:paragraph -->"
                    "<p>We value your feedback! Take 2 minutes to help us serve you better.</p>"
                    "<!-- /wp:paragraph -->"
                    "\n[wpforms id=\"\" title=\"false\"]"
                ),
            },
            {
                "slug": "contact",
                "title": "Contact Us",
                "content": (
                    "<!-- wp:paragraph -->"
                    "<p>We&rsquo;d love to hear from you. Reach us instantly on WhatsApp:</p>"
                    "<!-- /wp:paragraph -->"
                    "<!-- wp:buttons {\"layout\":{\"type\":\"flex\",\"justifyContent\":\"center\"}} -->"
                    "<div class=\"wp-block-buttons\">"
                    "<!-- wp:button {\"backgroundColor\":\"vivid-green-cyan\",\"textColor\":\"white\"} -->"
                    "<div class=\"wp-block-button\">"
                    "<a class=\"wp-block-button__link has-white-color has-vivid-green-cyan-background-color has-text-color has-background\" "
                    "href=\"https://wa.me/?text=Hi%2C+I+found+you+on+Zilo\" target=\"_blank\" rel=\"noreferrer noopener\">"
                    "💬 Chat on WhatsApp</a></div>"
                    "<!-- /wp:button --></div>"
                    "<!-- /wp:buttons -->"
                ),
            },
        ]
        for page in pages:
            try:
                r = _wp(
                    "post", "create",
                    "--post_type=page",
                    "--post_status=publish",
                    f"--post_title={page['title']}",
                    f"--post_name={page['slug']}",
                    f"--post_content={page['content']}",
                    "--porcelain",
                )
                if r.returncode == 0:
                    logger.info(f"[blog] Created page /{page['slug']} for {slug}")
                else:
                    logger.warning(f"[blog] page /{page['slug']} failed: {r.stderr[:150]}")
            except Exception as exc:
                logger.warning(f"[blog] page create {page['slug']} failed: {exc}")

        # 6. Set blog page (posts page) to /blog slug
        try:
            r = _wp(
                "post", "create",
                "--post_type=page",
                "--post_status=publish",
                "--post_title=Blog",
                "--post_name=blog",
                "--post_content=",
                "--porcelain",
            )
            if r.returncode == 0:
                blog_page_id = r.stdout.strip()
                _wp("option", "update", "page_for_posts", blog_page_id)
                logger.info(f"[blog] Created /blog page (id={blog_page_id}) for {slug}")
        except Exception as exc:
            logger.warning(f"[blog] /blog page create failed: {exc}")

    async def _apply_industry_theme(self, slug: str, industry: str):
        """
        Installs Astra (free, WooCommerce-optimised) network-wide if not present,
        activates it for the new subsite, then applies industry-specific accent colours
        via Astra's customizer options so every client site looks distinct.
        """
        import subprocess, json as _json

        cli_path = _wp_cli_path()
        subsite = wp_subsite_public_url(slug)

        def _wp(*args, timeout=30):
            return subprocess.run(
                ["wp", "--allow-root", f"--path={cli_path}", *args],
                capture_output=True, text=True, timeout=timeout,
            )

        def _wp_site(*args, timeout=30):
            return subprocess.run(
                ["wp", "--allow-root", f"--path={cli_path}", f"--url={subsite}", *args],
                capture_output=True, text=True, timeout=timeout,
            )

        # Industry → Astra accent colour + button colour
        INDUSTRY_COLORS = {
            "salon":       {"link": "#c2185b", "button": "#e91e8c", "heading": "#37474f"},
            "beauty":      {"link": "#c2185b", "button": "#e91e8c", "heading": "#37474f"},
            "hair":        {"link": "#c2185b", "button": "#e91e8c", "heading": "#37474f"},
            "spa":         {"link": "#8e24aa", "button": "#ab47bc", "heading": "#37474f"},
            "restaurant":  {"link": "#bf360c", "button": "#e64a19", "heading": "#3e2723"},
            "food":        {"link": "#bf360c", "button": "#e64a19", "heading": "#3e2723"},
            "hotel":       {"link": "#bf360c", "button": "#e64a19", "heading": "#3e2723"},
            "catering":    {"link": "#bf360c", "button": "#e64a19", "heading": "#3e2723"},
            "bakery":      {"link": "#6d4c41", "button": "#8d6e63", "heading": "#3e2723"},
            "retail":      {"link": "#1565c0", "button": "#1976d2", "heading": "#1a237e"},
            "hardware":    {"link": "#1565c0", "button": "#1976d2", "heading": "#1a237e"},
            "supermarket": {"link": "#2e7d32", "button": "#388e3c", "heading": "#1b5e20"},
            "fashion":     {"link": "#4a148c", "button": "#7b1fa2", "heading": "#1a237e"},
            "services":    {"link": "#00695c", "button": "#00897b", "heading": "#004d40"},
            "plumber":     {"link": "#01579b", "button": "#0288d1", "heading": "#01579b"},
            "electrician": {"link": "#f57f17", "button": "#f9a825", "heading": "#e65100"},
            "mechanic":    {"link": "#37474f", "button": "#546e7a", "heading": "#263238"},
            "startup":     {"link": "#283593", "button": "#3949ab", "heading": "#1a237e"},
            "tech":        {"link": "#283593", "button": "#3949ab", "heading": "#1a237e"},
            "saas":        {"link": "#283593", "button": "#3949ab", "heading": "#1a237e"},
            "agency":      {"link": "#283593", "button": "#3949ab", "heading": "#1a237e"},
            "consulting":  {"link": "#283593", "button": "#3949ab", "heading": "#1a237e"},
            "fitness":     {"link": "#c62828", "button": "#e53935", "heading": "#b71c1c"},
            "gym":         {"link": "#c62828", "button": "#e53935", "heading": "#b71c1c"},
        }
        colors = INDUSTRY_COLORS.get(
            industry.lower(),
            {"link": "#009B3A", "button": "#00c44e", "heading": "#071a10"},  # Zilo brand default
        )

        # 1. Install Astra network-wide (skip if already installed)
        try:
            check = _wp("theme", "is-installed", "astra")
            if check.returncode != 0:
                r = _wp("theme", "install", "astra", "--activate-network", timeout=120)
                if r.returncode == 0:
                    logger.info("[blog] Astra theme installed network-wide")
                else:
                    logger.warning(f"[blog] Astra install: {r.stderr[:200]}")
            else:
                logger.info("[blog] Astra already installed")
        except Exception as exc:
            logger.warning(f"[blog] Astra install check failed: {exc}")

        # 2. Activate Astra for this subsite
        try:
            r = _wp_site("theme", "activate", "astra")
            if r.returncode != 0:
                logger.warning(f"[blog] Astra activate for {slug}: {r.stderr[:150]}")
            else:
                logger.info(f"[blog] Astra activated for {slug}")
        except Exception as exc:
            logger.warning(f"[blog] theme activate failed: {exc}")

        # 3. Apply industry accent colours via Astra customizer options
        astra_settings = {
            "astra-color-global-palette": _json.dumps({
                "palette": [
                    {"slug": "palette-1", "color": colors["button"]},
                    {"slug": "palette-2", "color": colors["link"]},
                    {"slug": "palette-3", "color": colors["heading"]},
                    {"slug": "palette-4", "color": "#f4f6f9"},
                    {"slug": "palette-5", "color": "#ffffff"},
                    {"slug": "palette-6", "color": "#3a3a3a"},
                    {"slug": "palette-7", "color": "#747474"},
                    {"slug": "palette-8", "color": "#e8e8e8"},
                    {"slug": "palette-9", "color": "#f2f2f2"},
                ]
            }),
            "astra-settings": _json.dumps({
                "link-color": colors["link"],
                "theme-color": colors["button"],
                "heading-base-color": colors["heading"],
                "button-bg-color": colors["button"],
                "button-bg-h-color": colors["link"],
                "button-color": "#ffffff",
                "button-h-color": "#ffffff",
                "site-layout-outside-bg-obj": {"desktop": colors["button"]},
                "header-bg-color": "#ffffff",
                "footer-bg-color": "#071a10",
                "footer-color": "#cccccc",
                "footer-link-color": "#ffffff",
            }),
        }
        for option_name, option_value in astra_settings.items():
            try:
                _wp_site("option", "update", option_name, option_value)
            except Exception as exc:
                logger.warning(f"[blog] Astra option {option_name} failed: {exc}")

        logger.info(f"[blog] Astra theme + {industry} colours applied for {slug}")
