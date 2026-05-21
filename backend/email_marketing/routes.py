"""
email_marketing/routes.py
FastAPI router for email campaigns, templates, and provider settings.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email-marketing", tags=["email_marketing"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class EmailSettings(BaseModel):
    provider: str = "platform"       # platform | smtp | sendgrid | brevo | mailgun
    from_name: str = ""
    from_email: str = ""
    credentials: Dict[str, Any] = {}
    link_library: List[Dict[str, str]] = []  # [{label, url}, ...]


class LinkLibraryUpdate(BaseModel):
    links: List[Dict[str, str]] = []


class CampaignCreate(BaseModel):
    name: str
    subject: str
    from_name: str = ""
    from_email: str = ""
    body_html: str
    body_text: str = ""
    recipient_emails: List[str] = []
    recipient_tags: List[str] = []   # pull contacts by tag from CRM


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    recipient_emails: Optional[List[str]] = None
    recipient_tags: Optional[List[str]] = None


class TemplateCreate(BaseModel):
    name: str
    category: str = "general"
    subject: str = ""
    body_html: str


class SendRequest(BaseModel):
    test_email: Optional[str] = None   # if set → single test send, else full send


class ScheduleRequest(BaseModel):
    scheduled_at: str   # ISO datetime string


# ── Helpers ───────────────────────────────────────────────────────────────────

def _id(doc: Dict) -> str:
    return str(doc.get("_id", ""))


def _clean(doc: Dict) -> Dict:
    doc = dict(doc)
    doc["id"] = _id(doc)
    doc.pop("_id", None)
    return doc


def _uid(user: Dict) -> str:
    return str(user.get("business_id") or user["_id"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_settings(db, user_id: str) -> Dict:
    doc = await db.email_settings.find_one({"user_id": user_id})
    if not doc:
        return {"provider": "platform", "from_name": "", "from_email": "", "credentials": {}}
    return _clean(doc)


async def _collect_recipients(db, user_id: str, emails: List[str], tags: List[str]) -> List[str]:
    result = set(emails)
    if tags:
        async for c in db.contacts.find(
            {"user_id": user_id, "tags": {"$in": tags}},
            {"email": 1},
        ):
            if c.get("email"):
                result.add(c["email"])
        async for c in db.customers.find(
            {"user_id": user_id, "tags": {"$in": tags}},
            {"email": 1},
        ):
            if c.get("email"):
                result.add(c["email"])
    return [e for e in result if e and "@" in e]


# ── Settings endpoints ────────────────────────────────────────────────────────

def make_email_marketing_router(get_current_user, db):

    @router.get("/settings")
    async def get_email_settings(user=Depends(get_current_user)):
        user_id = _uid(user)
        s = await _get_settings(db, user_id)
        # Mask credential secrets
        masked = dict(s)
        creds = dict(masked.get("credentials") or {})
        for key in ("api_key", "password"):
            if key in creds:
                creds[key] = "••••••••" + creds[key][-4:] if len(creds.get(key, "")) > 4 else "••••••••"
        masked["credentials"] = creds
        return masked

    @router.post("/settings")
    async def save_email_settings(body: EmailSettings, user=Depends(get_current_user)):
        user_id = _uid(user)
        await db.email_settings.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id":      user_id,
                "provider":     body.provider,
                "from_name":    body.from_name,
                "from_email":   body.from_email,
                "credentials":  body.credentials,
                "link_library": body.link_library,
                "updated_at":   _now(),
            }},
            upsert=True,
        )
        return {"ok": True}

    @router.post("/settings/test")
    async def test_email_settings(body: Dict[str, Any], user=Depends(get_current_user)):
        from email_marketing.client import send_email
        user_id = _uid(user)
        test_to = body.get("test_email")
        if not test_to:
            raise HTTPException(400, "test_email required")
        settings = await _get_settings(db, user_id)
        # Override from_email/name with what user just entered (not yet saved)
        for k in ("provider", "from_name", "from_email", "credentials"):
            if body.get(k):
                settings[k] = body[k]
        try:
            await send_email(
                settings,
                to=[test_to],
                subject="Test email from Zilo",
                html="<p>Your email provider is connected and working correctly! 🎉</p>",
                text="Your email provider is connected and working correctly!",
            )
            return {"ok": True, "message": f"Test email sent to {test_to}"}
        except Exception as e:
            raise HTTPException(502, str(e))

    # ── Campaigns ─────────────────────────────────────────────────────────────

    @router.get("/campaigns")
    async def list_campaigns(user=Depends(get_current_user)):
        user_id = _uid(user)
        docs = await db.email_campaigns.find(
            {"user_id": user_id},
            {"body_html": 0},
        ).sort("created_at", -1).limit(100).to_list(100)
        return {"campaigns": [_clean(d) for d in docs]}

    @router.post("/campaigns")
    async def create_campaign(body: CampaignCreate, user=Depends(get_current_user)):
        user_id = _uid(user)
        doc = {
            "user_id":          user_id,
            "name":             body.name,
            "subject":          body.subject,
            "from_name":        body.from_name,
            "from_email":       body.from_email,
            "body_html":        body.body_html,
            "body_text":        body.body_text,
            "recipient_emails": body.recipient_emails,
            "recipient_tags":   body.recipient_tags,
            "status":           "draft",
            "stats":            {"sent": 0, "failed": 0},
            "created_at":       _now(),
            "updated_at":       _now(),
        }
        result = await db.email_campaigns.insert_one(doc)
        return {"ok": True, "id": str(result.inserted_id)}

    @router.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, user=Depends(get_current_user)):
        user_id = _uid(user)
        doc = await db.email_campaigns.find_one(
            {"_id": ObjectId(campaign_id), "user_id": user_id}
        )
        if not doc:
            raise HTTPException(404, "Campaign not found")
        return _clean(doc)

    @router.patch("/campaigns/{campaign_id}")
    async def update_campaign(campaign_id: str, body: CampaignUpdate, user=Depends(get_current_user)):
        user_id = _uid(user)
        update = {k: v for k, v in body.dict().items() if v is not None}
        if not update:
            raise HTTPException(400, "Nothing to update")
        update["updated_at"] = _now()
        result = await db.email_campaigns.update_one(
            {"_id": ObjectId(campaign_id), "user_id": user_id},
            {"$set": update},
        )
        if not result.matched_count:
            raise HTTPException(404, "Campaign not found")
        return {"ok": True}

    @router.delete("/campaigns/{campaign_id}")
    async def delete_campaign(campaign_id: str, user=Depends(get_current_user)):
        user_id = _uid(user)
        await db.email_campaigns.delete_one({"_id": ObjectId(campaign_id), "user_id": user_id})
        return {"ok": True}

    @router.post("/campaigns/{campaign_id}/send")
    async def send_campaign(campaign_id: str, body: SendRequest, user=Depends(get_current_user)):
        from email_marketing.client import send_email, send_bulk
        user_id = _uid(user)

        doc = await db.email_campaigns.find_one(
            {"_id": ObjectId(campaign_id), "user_id": user_id}
        )
        if not doc:
            raise HTTPException(404, "Campaign not found")

        settings = await _get_settings(db, user_id)
        # Override per-campaign from details if set
        if doc.get("from_name"):
            settings["from_name"] = doc["from_name"]
        if doc.get("from_email"):
            settings["from_email"] = doc["from_email"]

        # Test send
        if body.test_email:
            try:
                await send_email(
                    settings,
                    to=[body.test_email],
                    subject=f"[TEST] {doc['subject']}",
                    html=doc["body_html"],
                    text=doc.get("body_text", ""),
                )
                return {"ok": True, "test": True, "sent_to": body.test_email}
            except Exception as e:
                raise HTTPException(502, str(e))

        # Full send
        recipients = await _collect_recipients(
            db, user_id,
            doc.get("recipient_emails", []),
            doc.get("recipient_tags", []),
        )
        if not recipients:
            raise HTTPException(400, "No recipients found. Add email addresses or tags with contacts.")

        await db.email_campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {"status": "sending", "updated_at": _now()}},
        )

        result = await send_bulk(
            settings,
            recipients=recipients,
            subject=doc["subject"],
            html=doc["body_html"],
            text=doc.get("body_text", ""),
        )

        final_status = "sent" if result["failed"] == 0 else "partial"
        await db.email_campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {
                "status":  final_status,
                "sent_at": _now(),
                "stats":   {"sent": result["sent"], "failed": result["failed"]},
                "updated_at": _now(),
            }},
        )
        return {"ok": True, "sent": result["sent"], "failed": result["failed"],
                "status": final_status}

    @router.post("/campaigns/{campaign_id}/schedule")
    async def schedule_campaign(campaign_id: str, body: ScheduleRequest, user=Depends(get_current_user)):
        user_id = _uid(user)
        try:
            scheduled_at = datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Invalid datetime format. Use ISO 8601.")
        result = await db.email_campaigns.update_one(
            {"_id": ObjectId(campaign_id), "user_id": user_id},
            {"$set": {"status": "scheduled", "scheduled_at": scheduled_at, "updated_at": _now()}},
        )
        if not result.matched_count:
            raise HTTPException(404, "Campaign not found")
        return {"ok": True, "scheduled_at": scheduled_at.isoformat()}

    # ── Templates ─────────────────────────────────────────────────────────────

    @router.get("/templates")
    async def list_templates(user=Depends(get_current_user)):
        user_id = _uid(user)
        docs = await db.email_templates.find({"user_id": user_id}).sort("created_at", -1).to_list(200)
        return {"templates": [_clean(d) for d in docs]}

    @router.post("/templates")
    async def create_template(body: TemplateCreate, user=Depends(get_current_user)):
        user_id = _uid(user)
        doc = {
            "user_id":    user_id,
            "name":       body.name,
            "category":   body.category,
            "subject":    body.subject,
            "body_html":  body.body_html,
            "created_at": _now(),
        }
        result = await db.email_templates.insert_one(doc)
        return {"ok": True, "id": str(result.inserted_id)}

    @router.delete("/templates/{template_id}")
    async def delete_template(template_id: str, user=Depends(get_current_user)):
        user_id = _uid(user)
        await db.email_templates.delete_one({"_id": ObjectId(template_id), "user_id": user_id})
        return {"ok": True}

    # ── Catalog products (for email product picker) ───────────────────────────

    @router.get("/catalog-products")
    async def get_catalog_products(q: str = "", limit: int = 60, user=Depends(get_current_user)):
        """Return the user's product catalog (including Shopify-synced) for email content."""
        user_id = _uid(user)
        query: Dict = {"user_id": user_id}
        if q.strip():
            query["$or"] = [
                {"name":        {"$regex": q.strip(), "$options": "i"}},
                {"description": {"$regex": q.strip(), "$options": "i"}},
                {"category":    {"$regex": q.strip(), "$options": "i"}},
            ]
        docs = await db.products.find(
            query,
            {"name": 1, "price": 1, "discount_price": 1, "description": 1,
             "image_url": 1, "images": 1, "category": 1, "in_stock": 1,
             "shopify_product_id": 1},
        ).sort("updated_at", -1).limit(limit).to_list(limit)

        products = []
        for d in docs:
            products.append({
                "id":          str(d.get("_id", "")),
                "name":        d.get("name", ""),
                "price":       str(d.get("discount_price") or d.get("price") or ""),
                "description": (d.get("description") or "")[:200],
                "image_url":   d.get("image_url", ""),
                "images":      (d.get("images") or [])[:5],
                "category":    d.get("category", ""),
                "in_stock":    d.get("in_stock", True),
                "source":      "shopify" if d.get("shopify_product_id") else "catalog",
            })
        return {"products": products}

    # ── Media library (catalog images + chat-shared images) ───────────────────

    @router.get("/media-library")
    async def get_media_library(limit: int = 120, user=Depends(get_current_user)):
        """Return images from catalog and customer chat history for email use."""
        import re
        user_id = _uid(user)
        images: List[Dict] = []
        seen: set = set()

        def _add(url: str, label: str, source: str):
            if url and url.startswith("http") and url not in seen:
                seen.add(url)
                images.append({"url": url, "label": label, "source": source})

        # Product catalog images
        async for p in db.products.find(
            {"user_id": user_id},
            {"name": 1, "image_url": 1, "images": 1},
        ).sort("updated_at", -1).limit(100):
            name = p.get("name", "Product")
            if p.get("image_url"):
                _add(p["image_url"], name, "catalog")
            for img in (p.get("images") or []):
                _add(img, name, "catalog")

        # Chat-shared images: scan recent conversation messages
        img_re = re.compile(
            r'https?://\S+\.(?:jpg|jpeg|png|webp|gif|avif)(?:[?#]\S*)?',
            re.IGNORECASE,
        )
        async for conv in db.assistant_conversations.find(
            {"user_id": user_id},
            {"messages": {"$slice": -100}},
        ).sort("updated_at", -1).limit(30):
            for msg in (conv.get("messages") or []):
                content = msg.get("content", "")
                if isinstance(content, str):
                    for url in img_re.findall(content):
                        _add(url, "Chat image", "chat")
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "image_url":
                                url = (block.get("image_url") or {}).get("url", "")
                                if url.startswith("http"):
                                    _add(url, "Chat image", "chat")

        return {"images": images[:limit]}

    # ── AI Image Generation via OpenRouter ────────────────────────────────────

    class ImageGenRequest(BaseModel):
        prompt: str
        image_type: str = "hero"            # hero | product
        existing_image_url: str = ""        # if set → enhance rather than generate
        logo_url: str = ""
        accent_color: str = ""
        quality: str = "fast"               # fast | pro

    @router.post("/generate-image")
    async def generate_email_image(body: ImageGenRequest, user=Depends(get_current_user)):
        """Generate or enhance a marketing image via OpenRouter. Returns {url}."""
        from .image_gen import generate_email_image as _gen, enhance_product_image as _enh
        try:
            if body.existing_image_url.strip():
                url = await _enh(
                    body.existing_image_url.strip(),
                    body.prompt,
                    body.logo_url,
                    body.accent_color,
                    body.quality,
                )
            else:
                url = await _gen(
                    body.prompt,
                    body.image_type,
                    body.logo_url,
                    body.accent_color,
                    body.quality,
                )
            return {"url": url}
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Link library ─────────────────────────────────────────────────────────

    @router.post("/link-library")
    async def save_link_library(body: LinkLibraryUpdate, user=Depends(get_current_user)):
        """Save / overwrite the user's reusable email link library."""
        user_id = _uid(user)
        await db.email_settings.update_one(
            {"user_id": user_id},
            {"$set": {"link_library": body.links, "updated_at": _now()}},
            upsert=True,
        )
        return {"ok": True}

    # ── Stats ──────────────────────────────────────────────────────────────────

    @router.get("/stats")
    async def email_stats(user=Depends(get_current_user)):
        user_id = _uid(user)
        total       = await db.email_campaigns.count_documents({"user_id": user_id})
        sent        = await db.email_campaigns.count_documents({"user_id": user_id, "status": "sent"})
        draft       = await db.email_campaigns.count_documents({"user_id": user_id, "status": "draft"})
        scheduled   = await db.email_campaigns.count_documents({"user_id": user_id, "status": "scheduled"})
        pipeline = [
            {"$match": {"user_id": user_id, "status": {"$in": ["sent", "partial"]}}},
            {"$group": {"_id": None, "total_sent": {"$sum": "$stats.sent"}, "total_failed": {"$sum": "$stats.failed"}}},
        ]
        agg = await db.email_campaigns.aggregate(pipeline).to_list(1)
        totals = agg[0] if agg else {"total_sent": 0, "total_failed": 0}
        return {
            "campaigns":   {"total": total, "sent": sent, "draft": draft, "scheduled": scheduled},
            "emails_sent": totals["total_sent"],
            "emails_failed": totals["total_failed"],
        }

    return router


def make_email_marketing_router_factory(get_current_user, db):
    make_email_marketing_router(get_current_user, db)
    return router
