"""
Client Sites — WordPress Multisite Management.
Manages client websites (shop + forms + blog) via WordPress REST API.
Each CRM user creates/manages client subsites at *.zilo.pro.

Routes prefix: /client-sites
"""
import base64
import logging
import os
import re
import secrets
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── WordPress helpers ──────────────────────────────────────────────────────────

def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _get_wp_base() -> str:
    return os.getenv("WP_BASE_URL", "").rstrip("/")


def _wp_auth_header() -> str:
    user = os.getenv("WP_ADMIN_USER", "")
    pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    return f"Basic {token}"


def _wp_headers() -> dict:
    return {
        "Authorization": _wp_auth_header(),
        "Content-Type": "application/json",
    }


def _wp_configured() -> bool:
    return bool(
        _get_wp_base()
        and os.getenv("WP_ADMIN_USER")
        and os.getenv("WP_ADMIN_APP_PASSWORD")
    )


def _parent_domain() -> str:
    override = os.getenv("WP_SUBDOMAIN_PARENT_HOST", "").strip().lower()
    if override:
        return override.lstrip(".")
    base = _get_wp_base()
    if base:
        host = (urlparse(base).netloc or "zilo.pro").lower()
        return host[4:] if host.startswith("www.") else host
    return "zilo.pro"


def _site_url(slug: str) -> str:
    return f"https://{slug}.{_parent_domain()}"


# ── Pydantic models ────────────────────────────────────────────────────────────

class CreateSiteBody(BaseModel):
    client_name: str
    client_email: str
    subdomain: str
    industry: Optional[str] = ""
    features: Optional[Dict[str, bool]] = None


class PatchSiteBody(BaseModel):
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    industry: Optional[str] = None
    features: Optional[Dict[str, bool]] = None
    wp_status: Optional[str] = None


# ── Router factory ─────────────────────────────────────────────────────────────

def make_wp_sites_router(db, user_dep):
    router = APIRouter(prefix="/client-sites", tags=["client-sites"])

    def _uid(user) -> str:
        return str(user["_id"])

    def _clean_slug(raw: str) -> str:
        slug = re.sub(r"[^a-z0-9-]", "", raw.lower().replace(" ", "-").replace("_", "-"))
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug[:40]

    def _serialize(doc: dict) -> dict:
        doc["id"] = str(doc.pop("_id"))
        return doc

    # ── List all client sites ──────────────────────────────────────────────────

    @router.get("")
    async def list_sites(user=Depends(user_dep)):
        uid = _uid(user)
        cursor = db.client_sites.find({"owner_id": uid}).sort("created_at", -1)
        sites = []
        async for doc in cursor:
            sites.append(_serialize(doc))
        return {"sites": sites, "wp_configured": _wp_configured(), "parent_domain": _parent_domain()}

    # ── Create a new client site ───────────────────────────────────────────────

    @router.post("")
    async def create_site(body: CreateSiteBody, user=Depends(user_dep)):
        uid = _uid(user)
        slug = _clean_slug(body.subdomain)
        if not slug:
            raise HTTPException(400, "Invalid subdomain — use only letters, numbers and hyphens")

        existing = await db.client_sites.find_one({"owner_id": uid, "subdomain": slug})
        if existing:
            raise HTTPException(409, f"A site with subdomain '{slug}' already exists")

        features = body.features or {"shop": True, "forms": True, "blog": True}
        site_url = _site_url(slug)

        wp_site_id = None
        wp_status = "pending"
        wp_error = None

        if _wp_configured():
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.post(
                        f"{_get_wp_base()}/wp-json/wp/v2/sites",
                        headers=_wp_headers(),
                        json={
                            "domain": f"{slug}.{_parent_domain()}",
                            "path": "/",
                            "title": body.client_name,
                            "admin_user": body.client_email.split("@")[0],
                            "admin_email": body.client_email,
                            "admin_password": _generate_password(),
                        },
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        wp_site_id = data.get("id") or data.get("blog_id")
                        wp_status = "active"
                    else:
                        wp_error = f"WP API {resp.status_code}"
                        logger.warning("WP site create failed (%s): %s", resp.status_code, resp.text[:300])
            except Exception as exc:
                wp_error = str(exc)
                logger.warning("WP site create error: %s", exc)

        now = datetime.now(timezone.utc).isoformat()
        doc: Dict[str, Any] = {
            "owner_id": uid,
            "client_name": body.client_name,
            "client_email": body.client_email,
            "subdomain": slug,
            "industry": body.industry or "",
            "features": features,
            "site_url": site_url,
            "wp_site_id": wp_site_id,
            "wp_status": wp_status,
            "wp_error": wp_error,
            "stats": {"posts": 0, "orders": 0, "form_submissions": 0, "products": 0},
            "created_at": now,
            "updated_at": now,
            "last_synced": None,
        }
        result = await db.client_sites.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc)

    # ── Get single site ────────────────────────────────────────────────────────

    @router.get("/{site_id}")
    async def get_site(site_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        try:
            oid = ObjectId(site_id)
        except Exception:
            raise HTTPException(400, "Invalid site id")
        doc = await db.client_sites.find_one({"_id": oid, "owner_id": uid})
        if not doc:
            raise HTTPException(404, "Site not found")
        return _serialize(doc)

    # ── Patch site settings ────────────────────────────────────────────────────

    @router.patch("/{site_id}")
    async def patch_site(site_id: str, body: PatchSiteBody, user=Depends(user_dep)):
        uid = _uid(user)
        try:
            oid = ObjectId(site_id)
        except Exception:
            raise HTTPException(400, "Invalid site id")
        updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if body.client_name is not None:
            updates["client_name"] = body.client_name
        if body.client_email is not None:
            updates["client_email"] = body.client_email
        if body.industry is not None:
            updates["industry"] = body.industry
        if body.features is not None:
            updates["features"] = body.features
        if body.wp_status is not None:
            updates["wp_status"] = body.wp_status
        result = await db.client_sites.update_one({"_id": oid, "owner_id": uid}, {"$set": updates})
        if result.matched_count == 0:
            raise HTTPException(404, "Site not found")
        doc = await db.client_sites.find_one({"_id": oid, "owner_id": uid})
        return _serialize(doc)

    # ── Sync stats from WordPress ──────────────────────────────────────────────

    @router.post("/{site_id}/sync")
    async def sync_site_stats(site_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        try:
            oid = ObjectId(site_id)
        except Exception:
            raise HTTPException(400, "Invalid site id")
        doc = await db.client_sites.find_one({"_id": oid, "owner_id": uid})
        if not doc:
            raise HTTPException(404, "Site not found")

        slug = doc["subdomain"]
        site_base = _site_url(slug)
        stats: Dict[str, int] = dict(doc.get("stats") or {})
        errors: List[str] = []

        if not _wp_configured():
            return {"status": "skipped", "reason": "WordPress not configured", "stats": stats}

        wc_key = os.getenv("WC_CONSUMER_KEY", "")
        wc_secret = os.getenv("WC_CONSUMER_SECRET", "")

        async with httpx.AsyncClient(timeout=15) as client:
            # Blog posts
            try:
                r = await client.get(
                    f"{site_base}/wp-json/wp/v2/posts?per_page=1",
                    headers=_wp_headers(),
                )
                if r.status_code == 200:
                    stats["posts"] = int(r.headers.get("X-WP-Total", stats.get("posts", 0)))
            except Exception as exc:
                errors.append(f"posts: {exc}")

            # WooCommerce orders
            try:
                auth = (wc_key, wc_secret) if wc_key else None
                r = await client.get(
                    f"{site_base}/wp-json/wc/v3/orders?per_page=1",
                    auth=auth,
                )
                if r.status_code == 200:
                    stats["orders"] = int(r.headers.get("X-WP-Total", stats.get("orders", 0)))
            except Exception as exc:
                errors.append(f"orders: {exc}")

            # WooCommerce products
            try:
                auth = (wc_key, wc_secret) if wc_key else None
                r = await client.get(
                    f"{site_base}/wp-json/wc/v3/products?per_page=1",
                    auth=auth,
                )
                if r.status_code == 200:
                    stats["products"] = int(r.headers.get("X-WP-Total", stats.get("products", 0)))
            except Exception as exc:
                errors.append(f"products: {exc}")

        now = datetime.now(timezone.utc).isoformat()
        await db.client_sites.update_one(
            {"_id": oid, "owner_id": uid},
            {"$set": {"stats": stats, "updated_at": now, "last_synced": now}},
        )
        return {"status": "ok", "stats": stats, "errors": errors}

    # ── Recent WooCommerce orders for a site ────────────────────────────────────

    @router.get("/{site_id}/orders")
    async def get_site_orders(site_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        try:
            oid = ObjectId(site_id)
        except Exception:
            raise HTTPException(400, "Invalid site id")
        doc = await db.client_sites.find_one({"_id": oid, "owner_id": uid})
        if not doc:
            raise HTTPException(404, "Site not found")
        if not _wp_configured():
            return {"orders": [], "reason": "WordPress not configured"}

        site_base = _site_url(doc["subdomain"])
        wc_key = os.getenv("WC_CONSUMER_KEY", "")
        wc_secret = os.getenv("WC_CONSUMER_SECRET", "")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{site_base}/wp-json/wc/v3/orders?per_page=10&orderby=date&order=desc",
                    auth=(wc_key, wc_secret) if wc_key else None,
                )
                if r.status_code == 200:
                    return {"orders": r.json()}
        except Exception as exc:
            logger.warning("WC orders fetch failed for %s: %s", doc["subdomain"], exc)
        return {"orders": []}

    # ── Recent blog posts for a site ───────────────────────────────────────────

    @router.get("/{site_id}/posts")
    async def get_site_posts(site_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        try:
            oid = ObjectId(site_id)
        except Exception:
            raise HTTPException(400, "Invalid site id")
        doc = await db.client_sites.find_one({"_id": oid, "owner_id": uid})
        if not doc:
            raise HTTPException(404, "Site not found")
        if not _wp_configured():
            return {"posts": [], "reason": "WordPress not configured"}

        site_base = _site_url(doc["subdomain"])
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{site_base}/wp-json/wp/v2/posts?per_page=5&_fields=id,title,status,date,link",
                    headers=_wp_headers(),
                )
                if r.status_code == 200:
                    return {"posts": r.json()}
        except Exception as exc:
            logger.warning("WP posts fetch failed for %s: %s", doc["subdomain"], exc)
        return {"posts": []}

    # ── Delete site ────────────────────────────────────────────────────────────

    @router.delete("/{site_id}")
    async def delete_site(site_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        try:
            oid = ObjectId(site_id)
        except Exception:
            raise HTTPException(400, "Invalid site id")
        result = await db.client_sites.delete_one({"_id": oid, "owner_id": uid})
        if result.deleted_count == 0:
            raise HTTPException(404, "Site not found")
        return {"status": "deleted"}

    return router
