"""
Zilo Autoblogging — WordPress Multisite service.
Handles subsite creation and post publishing via WP REST API.
"""
import asyncio
import httpx
import base64
import os
import secrets
import string
import logging
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import urlparse
from slugify import slugify
from typing import List

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular import issues at module load time
async def _seed_products(site_url, business_name, industry, location):
    from blog.product_seeder import seed_products
    return await seed_products(site_url, business_name, industry, location)

async def _seed_forms(site_url, business_name, industry):
    from blog.form_seeder import seed_forms
    return await seed_forms(site_url, business_name, industry)


async def _seed_forms_via_cli(slug: str, site_url: str, business_name: str, industry: str) -> dict:
    """
    Creates industry-specific WPForms directly via WP-CLI wp post create.
    Works with WPForms Lite (no Pro REST API required).
    Returns dict {contact, order, survey} → WPForms post IDs (strings).
    """
    import json as _json
    from blog.form_seeder import _get_forms_for_industry, _build_wpforms_payload

    forms = _get_forms_for_industry(industry)
    result = {"contact": "", "order": "", "survey": ""}

    for i, form_def in enumerate(forms):
        payload = _build_wpforms_payload(form_def, business_name)
        form_json = _json.dumps(payload)
        r = await _wp_cli(
            "post", "create",
            "--post_type=wpforms",
            f"--post_title={form_def['name']}",
            f"--post_content={form_json}",
            "--post_status=publish",
            "--porcelain",
            url=site_url,
        )
        if r.returncode == 0:
            fid = r.stdout.strip()
            name_l = form_def["name"].lower()
            if "contact" in name_l:
                result.setdefault("contact", fid) or result.update({"contact": fid})
                result["contact"] = fid
            elif any(k in name_l for k in ["order", "inquiry", "booking", "reservation", "quote", "request"]):
                result["order"] = fid
            elif any(k in name_l for k in ["survey", "feedback", "customer", "satisfaction"]):
                result["survey"] = fid
            else:
                # positional fallback
                key = ["contact", "order", "survey"][min(i, 2)]
                if not result[key]:
                    result[key] = fid
            logger.info(f"[blog] WPForms form '{form_def['name']}' id={fid} created for {slug}")
        else:
            logger.warning(f"[blog] WP-CLI form create failed for '{form_def['name']}': {r.stderr[:150]}")

    # Fill any missing slots with whatever we got
    all_ids = [v for v in result.values() if v]
    if all_ids:
        for key in result:
            if not result[key]:
                result[key] = all_ids[0]
    return result


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


def _wp_bridge_url() -> str:
    """Base URL of the PHP WP bridge on the WordPress server (e.g. https://wp.zilo.pro)."""
    return os.getenv("WP_BRIDGE_URL", "").rstrip("/")


def _wp_bridge_secret() -> str:
    return os.getenv("WP_BRIDGE_SECRET", "")


async def _wp_cli(*args, url: str = None) -> SimpleNamespace:
    """
    Run a WP-CLI command.
    - If WP_BRIDGE_URL is set: calls the PHP bridge on Hostinger via HTTP (Render-safe).
    - Otherwise: falls back to local subprocess (same-server / local dev).
    Returns a SimpleNamespace with .returncode, .stdout, .stderr
    """
    bridge_url = _wp_bridge_url()
    if bridge_url:
        secret = _wp_bridge_secret()
        payload: dict = {"args": list(args)}
        if url:
            payload["url"] = url
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    f"{bridge_url}/wp-bridge.php",
                    json=payload,
                    headers={"X-Bridge-Key": secret},
                )
            if resp.status_code == 200:
                data = resp.json()
                return SimpleNamespace(
                    returncode=data.get("returncode", 1),
                    stdout=data.get("stdout", ""),
                    stderr=data.get("stderr", ""),
                )
            else:
                logger.warning(f"[wp-bridge] HTTP {resp.status_code}: {resp.text[:200]}")
                return SimpleNamespace(returncode=1, stdout="", stderr=f"Bridge HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning(f"[wp-bridge] request failed: {exc}")
            return SimpleNamespace(returncode=1, stdout="", stderr=str(exc))
    else:
        import subprocess
        cmd = ["wp", "--allow-root", f"--path={_wp_cli_path()}"]
        if url:
            cmd.append(f"--url={url}")
        cmd.extend(args)
        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=90
            )
            return SimpleNamespace(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except Exception as exc:
            return SimpleNamespace(returncode=1, stdout="", stderr=str(exc))


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


def _build_homepage_content(business_name: str, industry: str) -> str:
    """
    Returns Gutenberg block HTML for a polished Astra-styled homepage.
    Hero + 3-column features + CTA band.
    """
    industry_l = industry.lower()

    INDUSTRY_COPY = {
        "salon":       ("Transform Your Look", "Expert styling & beauty treatments in a relaxing environment.", [("✂️ Expert Stylists", "Award-winning team with years of experience."), ("💅 Full Beauty Menu", "Hair, nails, facials & more under one roof."), ("📅 Easy Booking", "Reserve your spot instantly via WhatsApp.")], "Book Your Appointment", "/contact"),
        "beauty":      ("Feel Your Best Every Day", "Premium beauty services tailored just for you.", [("💄 Beauty Experts", "Skilled professionals dedicated to your glow."), ("🌸 Premium Products", "Only the best brands used on your skin."), ("✨ Instant Results", "Walk out looking and feeling amazing.")], "Book a Session", "/contact"),
        "hair":        ("Great Hair Starts Here", "Precision cuts, colour & treatments by top stylists.", [("✂️ Precision Cuts", "Tailored styles that suit your personality."), ("🎨 Expert Colouring", "Balayage, highlights & vivid colours."), ("💆 Scalp Treatments", "Nourish and restore your hair health.")], "Book Now", "/contact"),
        "spa":         ("Relax. Restore. Renew.", "Indulge in world-class spa & wellness treatments.", [("🧖 Full Body Treatments", "Massages, wraps & detox therapies."), ("🌿 Natural Ingredients", "Pure botanical products for your skin."), ("☮️ Serene Atmosphere", "Escape the stress of everyday life.")], "Book a Treatment", "/contact"),
        "restaurant":  ("Taste the Difference", "Fresh ingredients, bold flavours, unforgettable meals.", [("🍽️ Chef-Crafted Menu", "Seasonal dishes made from locally sourced produce."), ("🥂 Perfect Ambience", "Great food deserves a great setting."), ("🚀 Fast Delivery", "Hot meals delivered to your door.")], "Order Now", "/shop"),
        "food":        ("Delicious Food, Delivered Fast", "From our kitchen to your table in minutes.", [("🍳 Fresh Daily", "Prepared fresh every morning with quality ingredients."), ("📦 Easy Ordering", "Order online or via WhatsApp — no fuss."), ("⭐ Top Rated", "Loved by hundreds of happy customers.")], "Order Online", "/shop"),
        "bakery":      ("Baked With Love", "Artisan breads, cakes & pastries made fresh daily.", [("🥐 Fresh Every Morning", "Baked before sunrise so you get it at its best."), ("🎂 Custom Cakes", "Birthday, wedding & celebration cakes to order."), ("🌾 Quality Ingredients", "No preservatives — just real, wholesome ingredients.")], "Shop Our Bakes", "/shop"),
        "hotel":       ("Your Home Away From Home", "Comfortable stays with exceptional service.", [("🛏️ Comfortable Rooms", "Well-appointed rooms for rest and relaxation."), ("🍳 Daily Breakfast", "Start your day with a hearty meal on us."), ("📍 Prime Location", "Close to everything you need.")], "Check Availability", "/contact"),
        "catering":    ("Exceptional Catering for Every Event", "From corporate lunches to wedding receptions.", [("👨‍🍳 Professional Chefs", "Experienced catering team for any occasion."), ("🍱 Custom Menus", "Tailored to your dietary needs & preferences."), ("✅ Full Setup Included", "We handle everything — you enjoy the event.")], "Get a Quote", "/contact"),
        "retail":      (f"Shop {business_name}", "Quality products at unbeatable prices.", [("🏷️ Great Prices", "Competitive pricing on all our products."), ("📦 Fast Fulfilment", "Order today, receive quickly."), ("🔄 Easy Returns", "Hassle-free returns & exchanges.")], "Shop Now", "/shop"),
        "hardware":    ("Everything You Need to Build", "Tools, materials & supplies for every project.", [("🔨 Wide Selection", "Thousands of products always in stock."), ("👷 Expert Advice", "Our team helps you choose the right tool."), ("🚚 Bulk Delivery", "Large orders delivered to your site.")], "Browse Products", "/shop"),
        "supermarket": ("Fresh, Fast & Affordable", "Your neighbourhood supermarket — now online.", [("🥦 Fresh Produce Daily", "Farm-fresh fruits and vegetables."), ("💳 Great Value", "Everyday low prices on all essentials."), ("🚗 Click & Collect", "Order online, pick up in minutes.")], "Shop Groceries", "/shop"),
        "fashion":     ("Define Your Style", "Trendy fashion for every occasion.", [("👗 New Arrivals Weekly", "Stay ahead with the latest fashion drops."), ("📏 All Sizes", "Inclusive sizing for every body."), ("🔁 Free Returns", "Shop confidently with hassle-free returns.")], "Shop the Collection", "/shop"),
        "fitness":     ("Stronger Every Day", "Achieve your fitness goals with expert guidance.", [("💪 Expert Coaching", "Personalised training plans that get results."), ("🏋️ Modern Equipment", "State-of-the-art gym facilities."), ("🥗 Nutrition Advice", "Fuel your body the right way.")], "Join Now", "/contact"),
        "gym":         ("Push Your Limits", "Where results are made, every single day.", [("🏆 Results Guaranteed", "Proven programmes for real transformation."), ("👥 Group Classes", "Motivating classes for all fitness levels."), ("🕐 Open 7 Days", "Train on your schedule, not ours.")], "Start Today", "/contact"),
        "services":    (f"Welcome to {business_name}", "Professional services you can count on.", [("✅ Reliable & Trusted", "Hundreds of satisfied clients across the region."), ("⚡ Fast Turnaround", "We respect your time and deliver on schedule."), ("💬 Always Reachable", "Reach us instantly via WhatsApp.")], "Get a Free Quote", "/contact"),
        "plumber":     ("Fast, Reliable Plumbing", "24/7 emergency & scheduled plumbing services.", [("🔧 Emergency Response", "We arrive fast when you need us most."), ("🏠 All Job Sizes", "From a dripping tap to full installations."), ("💯 Guaranteed Work", "All work backed by our satisfaction guarantee.")], "Call Us Now", "/contact"),
        "electrician": ("Safe, Certified Electrical Work", "Licensed electricians for homes & businesses.", [("⚡ Fully Licensed", "All work meets national safety standards."), ("🏗️ Installations & Repairs", "New wiring, fuse boards, lighting & more."), ("📞 Same-Day Service", "Emergency callouts available 7 days a week.")], "Get a Quote", "/contact"),
        "mechanic":    ("Expert Auto Repairs", "Keeping your vehicle safe on the road.", [("🔧 Full Diagnostics", "State-of-the-art diagnostic equipment."), ("🚗 All Makes & Models", "We service petrol, diesel & hybrid vehicles."), ("✅ Honest Pricing", "No hidden fees — ever.")], "Book a Service", "/contact"),
        "tech":        (f"Innovative Solutions by {business_name}", "Technology that drives your business forward.", [("💡 Custom Development", "Software built specifically for your needs."), ("☁️ Cloud Solutions", "Scalable, secure infrastructure."), ("🛡️ Ongoing Support", "We're with you long after launch.")], "Start a Project", "/contact"),
        "agency":      (f"Grow Faster with {business_name}", "Digital marketing & design that delivers results.", [("📈 Proven Results", "Data-driven strategies that grow your brand."), ("🎨 Creative Design", "Stunning visuals that stop the scroll."), ("📣 Full-Service", "SEO, social, ads & more in one place.")], "Get Started", "/contact"),
        "consulting":  (f"{business_name} — Expert Consulting", "Strategic advice that transforms businesses.", [("🎯 Strategic Focus", "Clarity and direction for complex challenges."), ("🤝 Trusted Partner", "Long-term relationships built on results."), ("📊 Data-Driven", "Every recommendation backed by research.")], "Book a Consultation", "/contact"),
    }

    copy = INDUSTRY_COPY.get(industry_l, (
        f"Welcome to {business_name}",
        "Quality products and services you can trust.",
        [("⭐ Quality First", "We never compromise on quality."), ("🚀 Fast & Reliable", "Efficient service with consistent results."), ("💬 Great Support", "We're always here to help you.")],
        "Get In Touch",
        "/contact",
    ))

    headline, subheadline, features, cta_text, cta_link = copy

    feat_blocks = ""
    for icon_title, desc in features:
        feat_blocks += (
            "<!-- wp:column {\"textAlign\":\"center\"} -->"
            "<div class=\"wp-block-column\" style=\"text-align:center\">"
            f"<!-- wp:heading {{\"textAlign\":\"center\",\"level\":4}} --><h4 class=\"wp-block-heading has-text-align-center\">{icon_title}</h4><!-- /wp:heading -->"
            f"<!-- wp:paragraph {{\"align\":\"center\"}} --><p class=\"has-text-align-center\">{desc}</p><!-- /wp:paragraph -->"
            "</div>"
            "<!-- /wp:column -->"
        )

    return (
        # ── Hero ──────────────────────────────────────────────────────────────
        "<!-- wp:cover {\"minHeight\":520,\"minHeightUnit\":\"px\",\"align\":\"full\","
        "\"overlayColor\":\"ast-global-color-0\",\"dimRatio\":70,"
        "\"style\":{\"spacing\":{\"padding\":{\"top\":\"80px\",\"bottom\":\"80px\"}}}} -->"
        "<div class=\"wp-block-cover alignfull\" style=\"min-height:520px;padding-top:80px;padding-bottom:80px\">"
        "<span aria-hidden=\"true\" class=\"wp-block-cover__background has-ast-global-color-0-background-color has-background-dim-70 has-background-dim\"></span>"
        "<div class=\"wp-block-cover__inner-container\">"
        "<!-- wp:heading {\"textAlign\":\"center\",\"level\":1,\"textColor\":\"white\","
        "\"style\":{\"typography\":{\"fontSize\":\"clamp(2rem,5vw,3.5rem)\"}}} -->"
        f"<h1 class=\"wp-block-heading has-text-align-center has-white-color has-text-color\">{headline}</h1>"
        "<!-- /wp:heading -->"
        "<!-- wp:paragraph {\"align\":\"center\",\"textColor\":\"white\","
        "\"style\":{\"typography\":{\"fontSize\":\"1.2rem\"},\"spacing\":{\"margin\":{\"top\":\"16px\",\"bottom\":\"32px\"}}}} -->"
        f"<p class=\"has-text-align-center has-white-color has-text-color\" style=\"margin-top:16px;margin-bottom:32px;font-size:1.2rem\">{subheadline}</p>"
        "<!-- /wp:paragraph -->"
        "<!-- wp:buttons {\"layout\":{\"type\":\"flex\",\"justifyContent\":\"center\"},\"style\":{\"spacing\":{\"blockGap\":\"16px\"}}} -->"
        "<div class=\"wp-block-buttons\">"
        "<!-- wp:button {\"style\":{\"border\":{\"radius\":\"30px\"}},\"backgroundColor\":\"white\",\"textColor\":\"ast-global-color-0\"} -->"
        f"<div class=\"wp-block-button\"><a class=\"wp-block-button__link has-ast-global-color-0-color has-white-background-color has-text-color has-background\" href=\"{cta_link}\" style=\"border-radius:30px\">{cta_text}</a></div>"
        "<!-- /wp:button -->"
        "<!-- wp:button {\"style\":{\"border\":{\"radius\":\"30px\"},\"color\":{\"background\":\"#25d366\"}},\"textColor\":\"white\"} -->"
        "<div class=\"wp-block-button\"><a class=\"wp-block-button__link has-white-color has-text-color has-background\" href=\"https://wa.me/?text=Hi%2C+I+found+you+on+Zilo\" target=\"_blank\" rel=\"noreferrer noopener\" style=\"border-radius:30px;background-color:#25d366\">💬 WhatsApp Us</a></div>"
        "<!-- /wp:button -->"
        "</div>"
        "<!-- /wp:buttons -->"
        "</div>"
        "</div>"
        "<!-- /wp:cover -->"

        # ── Features strip ────────────────────────────────────────────────────
        "<!-- wp:group {\"align\":\"full\",\"style\":{\"spacing\":{\"padding\":{\"top\":\"60px\",\"bottom\":\"60px\",\"left\":\"2rem\",\"right\":\"2rem\"}},\"color\":{\"background\":\"#f8f9fa\"}}} -->"
        "<div class=\"wp-block-group alignfull\" style=\"padding:60px 2rem;background-color:#f8f9fa\">"
        "<!-- wp:heading {\"textAlign\":\"center\",\"level\":2} -->"
        f"<h2 class=\"wp-block-heading has-text-align-center\">Why Choose {business_name}?</h2>"
        "<!-- /wp:heading -->"
        "<!-- wp:columns {\"align\":\"wide\",\"style\":{\"spacing\":{\"margin\":{\"top\":\"40px\"}}}} -->"
        "<div class=\"wp-block-columns alignwide\" style=\"margin-top:40px\">"
        + feat_blocks +
        "</div>"
        "<!-- /wp:columns -->"
        "</div>"
        "<!-- /wp:group -->"

        # ── CTA band ──────────────────────────────────────────────────────────
        "<!-- wp:group {\"align\":\"full\",\"style\":{\"spacing\":{\"padding\":{\"top\":\"60px\",\"bottom\":\"60px\"}}},\"backgroundColor\":\"ast-global-color-0\"} -->"
        "<div class=\"wp-block-group alignfull has-ast-global-color-0-background-color has-background\" style=\"padding:60px 0\">"
        "<!-- wp:heading {\"textAlign\":\"center\",\"level\":2,\"textColor\":\"white\"} -->"
        "<h2 class=\"wp-block-heading has-text-align-center has-white-color has-text-color\">Ready to Get Started?</h2>"
        "<!-- /wp:heading -->"
        "<!-- wp:paragraph {\"align\":\"center\",\"textColor\":\"white\"} -->"
        "<p class=\"has-text-align-center has-white-color has-text-color\">Contact us today and let us help you.</p>"
        "<!-- /wp:paragraph -->"
        "<!-- wp:buttons {\"layout\":{\"type\":\"flex\",\"justifyContent\":\"center\"},\"style\":{\"spacing\":{\"margin\":{\"top\":\"24px\"}}}} -->"
        "<div class=\"wp-block-buttons\" style=\"margin-top:24px\">"
        "<!-- wp:button {\"backgroundColor\":\"white\",\"textColor\":\"ast-global-color-0\",\"style\":{\"border\":{\"radius\":\"30px\"}}} -->"
        "<div class=\"wp-block-button\"><a class=\"wp-block-button__link has-ast-global-color-0-color has-white-background-color has-text-color has-background\" href=\"/contact\" style=\"border-radius:30px\">Get In Touch Today</a></div>"
        "<!-- /wp:button -->"
        "</div>"
        "<!-- /wp:buttons -->"
        "</div>"
        "<!-- /wp:group -->"
    )


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

        # 1. Create a WordPress user for the business (via WP-CLI bridge)
        wp_user_id = None
        try:
            user_password = _generate_password()
            result = await _wp_cli(
                "user", "create", slug, client_email,
                f"--user_pass={user_password}",
                "--role=author",
                "--porcelain",
            )
            if result.returncode == 0:
                wp_user_id = result.stdout.strip()
                logger.info(f"[blog] WordPress user created: {slug} (ID: {wp_user_id})")
            else:
                logger.info(f"[blog] WP user create: {result.stderr[:200]}")
        except Exception as e:
            logger.warning(f"[blog] WP user creation failed (may already exist): {e}")

        # 2. Create subsite via WP-CLI
        site_url = wp_subsite_public_url(slug)      # public URL (slug.zilo.pro)
        internal_url = _wp_internal_subsite_url(slug)
        blog_id: int | None = None
        try:
            result = await _wp_cli(
                "site", "create",
                f"--slug={slug}",
                f"--title={business_name}",
                f"--email={client_email}",
                "--porcelain",
            )
            if result.returncode == 0:
                try:
                    blog_id = int(result.stdout.strip())
                    logger.info(f"[blog] wp site created blog_id={blog_id} at {site_url}")
                except ValueError:
                    pass
            else:
                logger.warning(f"[blog] wp site create stderr: {result.stderr[:300]}")
        except Exception as e:
            logger.warning(f"[blog] wp site create failed: {e}")

        # 2b. Domain mapping: point slug.zilo.pro → the WordPress subsite
        if blog_id and site_url != internal_url:
            try:
                public_domain = site_url.replace("https://", "").replace("http://", "")
                await _wp_cli(
                    "db", "query",
                    f"UPDATE wp_blogs SET domain='{public_domain}' WHERE blog_id={blog_id};",
                )
                await _wp_cli(
                    "db", "query",
                    f"UPDATE wp_{blog_id}_options SET option_value='{site_url}' "
                    f"WHERE option_name='siteurl' OR option_name='home';",
                )
                logger.info(f"[blog] Domain mapped blog_id={blog_id} → {site_url}")
            except Exception as exc:
                logger.warning(f"[blog] domain mapping failed: {exc}")

        # 3. Apply industry-specific theme
        await self._apply_industry_theme(slug, industry)

        # 3b. Create industry homepage (hero + features + CTA, Astra-styled)
        await self._create_industry_homepage(slug, site_url, business_name, industry)

        # 4. Activate plugins (WooCommerce shop + WPForms) — use public URL (now mapped)
        await self._activate_site_plugins(slug, site_url)

        # 5. AI-seed products (industry-specific via Claude → WooCommerce REST)
        prod_result = await _seed_products(site_url, business_name, industry, location)
        logger.info(f"[blog] AI products seeded: {prod_result}")

        # 6. Seed Zilo Forms (stored in MongoDB, rendered by JS widget)
        from forms_routes import seed_blog_forms
        seeded_ids = await seed_blog_forms(self.db, client_id, business_name, industry)
        logger.info(f"[blog] Zilo Forms seeded: {seeded_ids}")

        # 6b. Embed Zilo Forms widget into Contact, Order Forms, and Survey pages
        try:
            api_base = os.getenv("BACKEND_PUBLIC_URL", "https://crm-1-pnfo.onrender.com").rstrip("/")

            def _zilo_form_block(slug: str) -> str:
                if not slug:
                    return ""
                uid = f"zf-{slug[-10:].replace('-', '')}"
                src = f"{api_base}/api/forms/widget.js"
                call = f"ZiloForm.render('{uid}','{slug}')"
                return (
                    "<!-- wp:html -->"
                    f'<div id="{uid}"></div>'
                    f'<script src="{src}" onload="{call}"></script>'
                    "<!-- /wp:html -->"
                )

            auth_header = base64.b64encode(
                f"{os.getenv('WP_ADMIN_USER', '')}:{os.getenv('WP_ADMIN_APP_PASSWORD', '')}".encode()
            ).decode()
            _headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}
            page_patches = {
                "contact": (
                    "<!-- wp:paragraph --><p>We’d love to hear from you. Reach us instantly on WhatsApp or fill in the form below.</p><!-- /wp:paragraph -->"
                    "<!-- wp:buttons {\"layout\":{\"type\":\"flex\",\"justifyContent\":\"center\"}} -->"
                    "<div class=\"wp-block-buttons\">"
                    "<!-- wp:button {\"style\":{\"color\":{\"background\":\"#25d366\"}},\"textColor\":\"white\"} -->"
                    "<div class=\"wp-block-button\">"
                    "<a class=\"wp-block-button__link has-white-color has-text-color has-background\" "
                    "href=\"https://wa.me/?text=Hi%2C+I+found+you+on+Zilo\" target=\"_blank\" rel=\"noreferrer noopener\">"
                    "💬 Chat on WhatsApp</a></div>"
                    "<!-- /wp:button --></div>"
                    "<!-- /wp:buttons -->"
                    + _zilo_form_block(seeded_ids.get("contact", ""))
                ),
                "forms": (
                    "<!-- wp:paragraph --><p>Fill in the form below to place an order or make an inquiry. "
                    "We'll get back to you via WhatsApp within minutes.</p><!-- /wp:paragraph -->"
                    + _zilo_form_block(seeded_ids.get("order", ""))
                ),
                "survey": (
                    "<!-- wp:paragraph --><p>We value your feedback! Take 2 minutes to help us serve you better.</p><!-- /wp:paragraph -->"
                    + _zilo_form_block(seeded_ids.get("survey", ""))
                ),
            }
            async with httpx.AsyncClient(timeout=15) as _hc:
                for page_slug, new_content in page_patches.items():
                    chk = await _hc.get(
                        f"{site_url}/wp-json/wp/v2/pages?slug={page_slug}&status=any",
                        headers=_headers,
                    )
                    pages_found = chk.json() if chk.status_code == 200 else []
                    if pages_found:
                        pid = pages_found[0]["id"]
                        await _hc.post(
                            f"{site_url}/wp-json/wp/v2/pages/{pid}",
                            headers=_headers,
                            json={"content": new_content, "status": "publish"},
                        )
                        logger.info(f"[blog] Patched /{page_slug} with Zilo Form widget for {slug}")
        except Exception as exc:
            logger.warning(f"[blog] page-form patch failed (non-fatal): {exc}")

        # 7. Persist to MongoDB
        blog_doc = {
            "client_id": client_id,
            "business_name": business_name,
            "client_email": client_email,
            "industry": industry,
            "location": location,
            "blog_url": site_url,
            "wp_slug": slug,
            "wp_user_id": wp_user_id,
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
        Automatically generates a Gemini featured image and attaches it.
        """
        subsite_url = wp_subsite_public_url(wp_slug)

        # Look up blog record for industry/business context used for image generation
        blog = await self.db.blogs.find_one({"wp_slug": wp_slug})
        client_id = blog.get("client_id") if blog else None

        # Generate and upload featured image via Gemini (non-blocking — post publishes even if this fails)
        featured_media_id = await self._generate_and_upload_featured_image(
            subsite_url=subsite_url,
            title=title,
            business_name=blog.get("business_name", "") if blog else "",
            industry=blog.get("industry", "business") if blog else "business",
            location=blog.get("location", "") if blog else "",
            wp_slug=wp_slug,
        )

        kw_list = keywords if isinstance(keywords, list) else []
        focus_kw = (kw_list[0] if kw_list and isinstance(kw_list[0], str) else "") or ""

        post_payload: dict = {
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": "publish",
            "meta": {
                "_yoast_wpseo_focuskw": focus_kw,
                "_yoast_wpseo_metadesc": excerpt,
            },
        }
        if featured_media_id:
            post_payload["featured_media"] = featured_media_id

        post_url = f"{subsite_url}/wp-json/wp/v2/posts"
        headers = _wp_headers()
        
        logger.info(f"[blog] Publishing to: {post_url}")
        logger.debug(f"[blog] Auth header present: {bool(headers.get('Authorization'))}")
        
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            post_res = await client.post(
                post_url,
                headers=headers,
                json=post_payload,
            )

        logger.info(f"[blog] WordPress response: {post_res.status_code}")
        content_type = post_res.headers.get("content-type", "")
        
        if post_res.status_code == 201:
            post = post_res.json()

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
                        "featured_image": bool(featured_media_id),
                        "published_at": datetime.utcnow(),
                    }
                )

            logger.info(
                "[blog] Published '%s' → %s (featured_image=%s)",
                title, post.get("link"), "yes" if featured_media_id else "no",
            )
            return {"post_url": post.get("link"), "post_id": post.get("id")}
        else:
            error_detail = f"WP publish failed ({post_res.status_code})"
            if "text/html" in content_type:
                error_detail += f" - Got HTML instead of JSON. URL: {post_url}. Check WP_ADMIN_USER and WP_ADMIN_APP_PASSWORD."
            else:
                error_detail += f": {post_res.text[:400]}"
            logger.error(f"[blog] {error_detail}")
            raise RuntimeError(error_detail)

    async def _generate_and_upload_featured_image(
        self,
        subsite_url: str,
        title: str,
        business_name: str,
        industry: str,
        location: str,
        wp_slug: str,
    ) -> "int | None":
        """
        Generates a featured image with Gemini via nano_banana_service and uploads it
        to the WordPress media library. Returns the WP media ID or None on failure.
        """
        try:
            from nano_banana_service import generate_creative_image

            image_prompt = (
                f"A professional, editorial-quality blog featured image for a {industry} business "
                f"called '{business_name}' based in {location}.\n\n"
                f"Post topic: {title}\n\n"
                f"Style requirements:\n"
                f"- Photorealistic, magazine-quality photography — NOT illustration, NOT AI art style\n"
                f"- Relevant to {industry}: show the environment, products, or people naturally\n"
                f"- Warm, vibrant, high-contrast lighting — the kind that stops scrolling\n"
                f"- Wide landscape composition suitable for a blog header\n"
                f"- NO text, NO words, NO watermarks anywhere in the image\n"
                f"- Premium editorial feel — like a photo from a top magazine spread\n"
                f"- Mood: confident, professional, locally authentic to {location}"
            )

            result = await generate_creative_image(
                prompt=image_prompt,
                format="landscape",
                quality="fast",
            )

            if result.get("error") or not result.get("image_url"):
                logger.warning("[blog] Gemini image generation failed: %s", result.get("error"))
                return None

            return await self._upload_image_to_wp_media(subsite_url, result["image_url"], wp_slug)

        except Exception as exc:
            logger.warning("[blog] Featured image pipeline failed (publishing without): %s", exc)
            return None

    async def _upload_image_to_wp_media(
        self,
        subsite_url: str,
        image_url: str,
        wp_slug: str,
    ) -> "int | None":
        """
        Downloads an image from its URL and uploads it to the WordPress media library.
        Returns the WordPress media attachment ID or None on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=40) as client:
                img_resp = await client.get(image_url)
                img_resp.raise_for_status()

                media_resp = await client.post(
                    f"{subsite_url}/wp-json/wp/v2/media",
                    headers={
                        "Authorization": f"Basic {_get_wp_auth()}",
                        "Content-Disposition": f'attachment; filename="featured-{wp_slug}.png"',
                        "Content-Type": "image/png",
                    },
                    content=img_resp.content,
                )

            if media_resp.status_code == 201:
                media_id = media_resp.json().get("id")
                logger.info("[blog] Featured image uploaded to WP media id=%s", media_id)
                return media_id

            logger.warning("[blog] WP media upload failed (%s): %s", media_resp.status_code, media_resp.text[:200])
            return None

        except Exception as exc:
            logger.warning("[blog] WP media upload error: %s", exc)
            return None

    async def create_order(
        self,
        wp_slug: str,
        customer_info: dict,
        items: List[dict],
        notes: str = "",
    ) -> dict:
        """
        Creates an order in WooCommerce via REST API.
        customer_info: {first_name, last_name, email, phone, address_1, city}
        items: [{product_id, quantity}] - product_id is the WC numeric ID
        """
        subsite_url = wp_subsite_public_url(wp_slug)
        wc_key = os.getenv("WC_CONSUMER_KEY", "")
        wc_secret = os.getenv("WC_CONSUMER_SECRET", "")
        
        if not wc_key or not wc_secret:
            raise RuntimeError("WooCommerce API keys not configured")

        line_items = []
        for it in items:
            pid = str(it.get("product_id", ""))
            if pid.startswith("wc_"):
                pid = pid.replace("wc_", "")
            try:
                line_items.append({
                    "product_id": int(pid),
                    "quantity": int(it.get("quantity", 1))
                })
            except ValueError:
                continue

        payload = {
            "payment_method": "bacs",
            "payment_method_title": "Direct Bank Transfer",
            "set_paid": False,
            "billing": customer_info,
            "shipping": customer_info,
            "line_items": line_items,
            "customer_note": notes,
            "status": "pending"
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{subsite_url}/wp-json/wc/v3/orders",
                auth=(wc_key, wc_secret),
                json=payload,
            )
            
        if resp.status_code in (200, 201):
            return resp.json()
        else:
            raise RuntimeError(f"WC order creation failed ({resp.status_code}): {resp.text[:400]}")

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _activate_site_plugins(self, slug: str, site_url: str):
        """
        Activates WooCommerce + WPForms and runs WooCommerce initial setup
        (shop/cart/checkout pages, sample product, permalink flush) via WP-CLI bridge.
        """
        cli_path = _wp_cli_path()

        async def _wp(*args):
            return await _wp_cli(*args, url=site_url)

        # 1. Activate plugins
        for plugin in ["woocommerce", "wpforms-lite"]:
            try:
                r = await _wp("plugin", "activate", plugin)
                if r.returncode != 0:
                    logger.warning(f"[blog] activate {plugin}: {r.stderr[:150]}")
                else:
                    logger.info(f"[blog] {plugin} activated for {slug}")
            except Exception as exc:
                logger.warning(f"[blog] activate {plugin} failed: {exc}")

        # 2. WooCommerce: create core pages (shop, cart, checkout, my-account)
        try:
            r = await _wp("wc", "tool", "run", "install_pages", "--user=1")
            if r.returncode != 0:
                logger.warning(f"[blog] wc install_pages: {r.stderr[:150]}")
        except Exception as exc:
            logger.warning(f"[blog] wc install_pages failed: {exc}")

        # 3. Import WooCommerce sample products (built-in XML demo data)
        try:
            sample_xml = f"{cli_path}/wp-content/plugins/woocommerce/sample-data/sample_products.xml"
            r = await _wp_cli(
                "import", sample_xml,
                "--authors=skip",
                "--quiet",
                url=site_url,
            )
            if r.returncode != 0:
                logger.warning(f"[blog] wc sample import: {r.stderr[:150]}")
            else:
                logger.info(f"[blog] WooCommerce sample products imported for {slug}")
        except Exception as exc:
            logger.warning(f"[blog] wc sample import failed: {exc}")

        # 4. Set permalink structure to /%postname%/ (required for WC REST API)
        try:
            await _wp("rewrite", "structure", "/%postname%/", "--hard")
            await _wp("rewrite", "flush", "--hard")
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
                ),
            },
            {
                "slug": "survey",
                "title": "Customer Survey",
                "content": (
                    "<!-- wp:paragraph -->"
                    "<p>We value your feedback! Take 2 minutes to help us serve you better.</p>"
                    "<!-- /wp:paragraph -->"
                ),
            },
            {
                "slug": "contact",
                "title": "Contact Us",
                "content": (
                    "<!-- wp:paragraph -->"
                    "<p>We\u2019d love to hear from you. Reach us instantly on WhatsApp or fill in the form below.</p>"
                    "<!-- /wp:paragraph -->"
                    "<!-- wp:buttons {\"layout\":{\"type\":\"flex\",\"justifyContent\":\"center\"}} -->"
                    "<div class=\"wp-block-buttons\">"
                    "<!-- wp:button {\"style\":{\"color\":{\"background\":\"#25d366\"}},\"textColor\":\"white\"} -->"
                    "<div class=\"wp-block-button\">"
                    "<a class=\"wp-block-button__link has-white-color has-text-color has-background\" "
                    "href=\"https://wa.me/?text=Hi%2C+I+found+you+on+Zilo\" target=\"_blank\" rel=\"noreferrer noopener\">"
                    "\U0001f4ac Chat on WhatsApp</a></div>"
                    "<!-- /wp:button --></div>"
                    "<!-- /wp:buttons -->"
                    "<!-- wp:paragraph -->"
                    "<p></p>"
                    "<!-- /wp:paragraph -->"
                    "<!-- wp:shortcode -->"
                    "[wpforms id=\"\" title=\"false\"]"
                    "<!-- /wp:shortcode -->"
                ),
            },
        ]
        for page in pages:
            try:
                r = await _wp(
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

        # 6. Create blog page and set it as posts page
        try:
            r = await _wp(
                "post", "create",
                "--post_type=page",
                "--post_status=publish",
                "--post_title=Blog",
                "--post_name=blog",
                "--post_content=",
                "--porcelain",
            )
            blog_page_id = r.stdout.strip() if r.returncode == 0 else None
            if blog_page_id:
                await _wp("option", "update", "page_for_posts", blog_page_id)
                logger.info(f"[blog] Set Blog (id={blog_page_id}) as posts page for {slug}")
        except Exception as exc:
            logger.warning(f"[blog] blog page configuration failed: {exc}")

        # 7. Remove the default "Sample Page" WordPress creates on every new site
        try:
            await _wp(
                "eval",
                '$p=get_page_by_path("sample-page");'
                'if($p){wp_delete_post($p->ID,true);echo "deleted";}',
            )
            logger.info(f"[blog] Sample Page removed for {slug}")
        except Exception as exc:
            logger.warning(f"[blog] Sample Page removal failed: {exc}")

    async def _create_industry_homepage(self, slug: str, site_url: str, business_name: str, industry: str):
        """
        Creates a polished Gutenberg homepage (hero + features + CTA) styled by Astra,
        then sets it as the site front page.
        """
        content = _build_homepage_content(business_name, industry)

        async def _wp(*args):
            return await _wp_cli(*args, url=site_url)

        r = await _wp(
            "post", "create",
            "--post_type=page",
            "--post_status=publish",
            "--post_title=Home",
            "--post_name=home",
            f"--post_content={content}",
            "--porcelain",
        )
        if r.returncode == 0:
            home_id = r.stdout.strip()
            await _wp("option", "update", "show_on_front", "page")
            await _wp("option", "update", "page_on_front", home_id)
            logger.info(f"[blog] Homepage created (id={home_id}) and set as front page for {slug}")
        else:
            logger.warning(f"[blog] Homepage creation failed for {slug}: {r.stderr[:150]}")

    async def _apply_industry_theme(self, slug: str, industry: str):
        """
        Installs Astra (free, WooCommerce-optimised) network-wide if not present,
        activates it for the new subsite, then applies industry-specific accent colours
        via Astra's customizer options so every client site looks distinct.
        """
        import json as _json

        subsite = wp_subsite_public_url(slug)

        async def _wp(*args):
            return await _wp_cli(*args)

        async def _wp_site(*args):
            return await _wp_cli(*args, url=subsite)

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
            check = await _wp("theme", "is-installed", "astra")
            if check.returncode != 0:
                r = await _wp("theme", "install", "astra", "--activate-network")
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
            r = await _wp_site("theme", "activate", "astra")
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
                await _wp_site("option", "update", option_name, option_value)
            except Exception as exc:
                logger.warning(f"[blog] Astra option {option_name} failed: {exc}")

        logger.info(f"[blog] Astra theme + {industry} colours applied for {slug}")
