"""
FastAPI routes for email marketing.
Mount via: api_router.include_router(make_email_marketing_router(get_current_user, db))
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .client import send_bulk, send_email

log = logging.getLogger(__name__)

# ── Pydantic models ───────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str
    subject: str
    from_name: str = ""
    from_email: str = ""
    body_html: str
    body_text: str = ""
    recipient_emails: List[str] = []
    recipient_tags: List[str] = []

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    recipient_emails: Optional[List[str]] = None
    recipient_tags: Optional[List[str]] = None

class SendRequest(BaseModel):
    test_email: Optional[str] = None

class SettingsSave(BaseModel):
    provider: str = "platform"
    from_name: str = ""
    from_email: str = ""
    credentials: Dict[str, Any] = {}

class SettingsTest(BaseModel):
    provider: str = "platform"
    from_name: str = ""
    from_email: str = ""
    credentials: Dict[str, Any] = {}
    test_email: str

# ── Router factory ────────────────────────────────────────────────────────────

def make_email_marketing_router(get_current_user: Callable, db: Any) -> APIRouter:
    router = APIRouter(prefix="/api/email-marketing", tags=["email-marketing"])

    # ── Settings ──────────────────────────────────────────────────────────────

    @router.get("/settings")
    async def get_settings(user=Depends(get_current_user)):
        doc = await db.email_settings.find_one({"user_id": user["id"]})
        if not doc:
            return {"provider": "platform", "from_name": "", "from_email": "", "credentials": {}}
        creds = dict(doc.get("credentials") or {})
        for k in ("api_key", "password"):
            if k in creds:
                creds[k] = "••••••••"
        return {
            "provider":   doc.get("provider", "platform"),
            "from_name":  doc.get("from_name", ""),
            "from_email": doc.get("from_email", ""),
            "credentials": creds,
        }

    @router.post("/settings")
    async def save_settings(body: SettingsSave, user=Depends(get_current_user)):
        await db.email_settings.update_one(
            {"user_id": user["id"]},
            {"$set": {
                "user_id":     user["id"],
                "provider":    body.provider,
                "from_name":   body.from_name,
                "from_email":  body.from_email,
                "credentials": body.credentials,
                "updated_at":  datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        return {"ok": True}

    @router.post("/settings/test")
    async def test_settings(body: SettingsTest, user=Depends(get_current_user)):
        settings = {
            "provider":    body.provider,
            "from_name":   body.from_name,
            "from_email":  body.from_email,
            "credentials": body.credentials,
        }
        try:
            await send_email(
                settings,
                to=[body.test_email],
                subject="Zilo Email Test",
                html="<p>Your email provider is working correctly!</p>",
                text="Your email provider is working correctly!",
            )
            return {"ok": True, "message": f"Test email sent to {body.test_email}"}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # ── Campaigns ─────────────────────────────────────────────────────────────

    @router.get("/campaigns")
    async def list_campaigns(user=Depends(get_current_user)):
        docs = await db.email_campaigns.find(
            {"user_id": user["id"]}, {"body_html": 0}
        ).sort("created_at", -1).limit(100).to_list(100)
        return {
            "campaigns": [
                {
                    "id":         str(d["_id"]),
                    "name":       d.get("name", ""),
                    "subject":    d.get("subject", ""),
                    "status":     d.get("status", "draft"),
                    "recipients": len(d.get("recipient_emails", [])),
                    "stats":      d.get("stats", {}),
                    "sent_at":    d.get("sent_at"),
                    "created_at": d.get("created_at"),
                }
                for d in docs
            ]
        }

    @router.post("/campaigns")
    async def create_campaign(body: CampaignCreate, user=Depends(get_current_user)):
        now = datetime.now(timezone.utc)
        doc = {
            "user_id":          user["id"],
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
            "created_at":       now,
            "updated_at":       now,
        }
        result = await db.email_campaigns.insert_one(doc)
        return {"id": str(result.inserted_id), "status": "draft"}

    @router.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, user=Depends(get_current_user)):
        doc = await db.email_campaigns.find_one(
            {"_id": ObjectId(campaign_id), "user_id": user["id"]}
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Campaign not found")
        doc["id"] = str(doc.pop("_id"))
        return doc

    @router.patch("/campaigns/{campaign_id}")
    async def update_campaign(campaign_id: str, body: CampaignUpdate,
                               user=Depends(get_current_user)):
        updates = {k: v for k, v in body.dict(exclude_none=True).items()}
        if not updates:
            raise HTTPException(status_code=400, detail="Nothing to update")
        updates["updated_at"] = datetime.now(timezone.utc)
        res = await db.email_campaigns.update_one(
            {"_id": ObjectId(campaign_id), "user_id": user["id"]},
            {"$set": updates},
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return {"ok": True}

    @router.delete("/campaigns/{campaign_id}")
    async def delete_campaign(campaign_id: str, user=Depends(get_current_user)):
        res = await db.email_campaigns.delete_one(
            {"_id": ObjectId(campaign_id), "user_id": user["id"]}
        )
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return {"ok": True}

    @router.post("/campaigns/{campaign_id}/send")
    async def send_campaign(campaign_id: str, body: SendRequest,
                             user=Depends(get_current_user)):
        doc = await db.email_campaigns.find_one(
            {"_id": ObjectId(campaign_id), "user_id": user["id"]}
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Campaign not found")

        settings_doc = await db.email_settings.find_one({"user_id": user["id"]})
        settings: Dict[str, Any] = dict(settings_doc) if settings_doc else {"provider": "platform"}
        if doc.get("from_name"):
            settings["from_name"] = doc["from_name"]
        if doc.get("from_email"):
            settings["from_email"] = doc["from_email"]

        # Test send
        if body.test_email:
            try:
                await send_email(
                    settings, to=[body.test_email],
                    subject=f"[TEST] {doc['subject']}",
                    html=doc["body_html"], text=doc.get("body_text", ""),
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            return {"ok": True, "test": True, "sent_to": body.test_email}

        # Collect recipients
        recipients: set = set(doc.get("recipient_emails") or [])
        for tag in (doc.get("recipient_tags") or []):
            async for c in db.contacts.find(
                {"user_id": user["id"], "tags": tag}, {"email": 1}
            ):
                if c.get("email"):
                    recipients.add(c["email"])
            async for c in db.customers.find(
                {"user_id": user["id"], "tags": tag}, {"email": 1}
            ):
                if c.get("email"):
                    recipients.add(c["email"])

        recipients_list = [e for e in recipients if e and "@" in e]
        if not recipients_list:
            raise HTTPException(status_code=400, detail="No valid recipients found")

        await db.email_campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {"status": "sending", "updated_at": datetime.now(timezone.utc)}},
        )

        result = await send_bulk(
            settings, recipients=recipients_list,
            subject=doc["subject"], html=doc["body_html"],
            text=doc.get("body_text", ""),
        )

        final_status = "sent" if result["failed"] == 0 else "partial"
        await db.email_campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {
                "status":     final_status,
                "sent_at":    datetime.now(timezone.utc),
                "stats":      result,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return {"ok": True, "status": final_status, **result}

    # ── Stats ─────────────────────────────────────────────────────────────────

    @router.get("/stats")
    async def get_stats(user=Depends(get_current_user)):
        uid = user["id"]
        total     = await db.email_campaigns.count_documents({"user_id": uid})
        sent      = await db.email_campaigns.count_documents({"user_id": uid, "status": "sent"})
        draft     = await db.email_campaigns.count_documents({"user_id": uid, "status": "draft"})
        scheduled = await db.email_campaigns.count_documents({"user_id": uid, "status": "scheduled"})
        pipeline = [
            {"$match": {"user_id": uid, "status": {"$in": ["sent", "partial"]}}},
            {"$group": {
                "_id": None,
                "emails_sent":   {"$sum": "$stats.sent"},
                "emails_failed": {"$sum": "$stats.failed"},
            }},
        ]
        agg = await db.email_campaigns.aggregate(pipeline).to_list(1)
        totals = agg[0] if agg else {}
        return {
            "campaigns":     {"total": total, "sent": sent, "draft": draft, "scheduled": scheduled},
            "emails_sent":   totals.get("emails_sent", 0),
            "emails_failed": totals.get("emails_failed", 0),
        }

    return router
