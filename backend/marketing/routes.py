"""REST for Marketing — ad campaign drafts in Mongo (Meta + X), aligned with assistant save/list tools."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

ALLOWED_STATUS = frozenset({"draft", "active", "paused", "ended"})


def _tenant_id(user: Dict[str, Any]) -> str:
    return user.get("business_id", user["_id"])


def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
    ca = row.get("created_at")
    return {
        "id": str(row["_id"]),
        "name": row.get("name") or "",
        "objective": row.get("objective") or "awareness",
        "daily_budget": float(row.get("daily_budget") or 0),
        "currency": (row.get("currency") or "USD").upper()[:8],
        "notes": row.get("notes") or "",
        "status": row.get("status") or "draft",
        "source": row.get("source") or "",
        "created_at": ca.isoformat() if hasattr(ca, "isoformat") else None,
    }


class DraftCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1)
    objective: str = "awareness"
    daily_budget: float = 0
    currency: str = "USD"
    notes: str = ""
    status: str = "draft"


class DraftUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = None
    objective: Optional[str] = None
    daily_budget: Optional[float] = None
    currency: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class SocialPostDraftBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(..., min_length=3, max_length=4000)
    channels: List[str] = Field(default_factory=lambda: ["facebook"])


def make_marketing_router(db, user_dep):
    router = APIRouter(prefix="/marketing", tags=["marketing"])

    @router.get("/meta-ads/drafts")
    async def list_meta_ads_drafts(user=user_dep):
        uid = _tenant_id(user)
        rows = await db.meta_ads_campaign_drafts.find({"user_id": uid}).sort("created_at", -1).to_list(200)
        return {"drafts": [_serialize(r) for r in rows]}

    @router.post("/meta-ads/drafts")
    async def create_meta_ads_draft(body: DraftCreate, user=user_dep):
        uid = _tenant_id(user)
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name is required")
        st = (body.status or "draft").strip().lower()
        if st not in ALLOWED_STATUS:
            st = "draft"
        doc: Dict[str, Any] = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "name": name,
            "objective": (body.objective or "awareness").strip(),
            "daily_budget": float(body.daily_budget or 0),
            "currency": (body.currency or "USD").strip().upper()[:8],
            "notes": (body.notes or "").strip(),
            "status": st,
            "created_at": datetime.utcnow(),
            "source": "meta_ads_ui",
        }
        await db.meta_ads_campaign_drafts.insert_one(doc)
        return {"draft": _serialize(doc)}

    @router.patch("/meta-ads/drafts/{draft_id}")
    async def update_meta_ads_draft(draft_id: str, body: DraftUpdate, user=user_dep):
        uid = _tenant_id(user)
        existing = await db.meta_ads_campaign_drafts.find_one({"_id": draft_id, "user_id": uid})
        if not existing:
            raise HTTPException(404, "Draft not found")
        updates: Dict[str, Any] = {}
        if body.name is not None:
            n = body.name.strip()
            if not n:
                raise HTTPException(400, "name cannot be empty")
            updates["name"] = n
        if body.objective is not None:
            updates["objective"] = body.objective.strip()
        if body.daily_budget is not None:
            updates["daily_budget"] = float(body.daily_budget)
        if body.currency is not None:
            updates["currency"] = body.currency.strip().upper()[:8]
        if body.notes is not None:
            updates["notes"] = body.notes.strip()
        if body.status is not None:
            st = body.status.strip().lower()
            if st not in ALLOWED_STATUS:
                raise HTTPException(400, f"invalid status: {body.status}")
            updates["status"] = st
        if updates:
            await db.meta_ads_campaign_drafts.update_one(
                {"_id": draft_id, "user_id": uid},
                {"$set": updates},
            )
        row = await db.meta_ads_campaign_drafts.find_one({"_id": draft_id, "user_id": uid})
        return {"draft": _serialize(row or existing)}

    @router.delete("/meta-ads/drafts/{draft_id}")
    async def delete_meta_ads_draft(draft_id: str, user=user_dep):
        uid = _tenant_id(user)
        res = await db.meta_ads_campaign_drafts.delete_one({"_id": draft_id, "user_id": uid})
        if res.deleted_count == 0:
            raise HTTPException(404, "Draft not found")
        return {"status": "deleted", "id": draft_id}

    @router.get("/x-ads/drafts")
    async def list_x_ads_drafts(user=user_dep):
        uid = _tenant_id(user)
        rows = await db.x_ads_campaign_drafts.find({"user_id": uid}).sort("created_at", -1).to_list(200)
        return {"drafts": [_serialize(r) for r in rows]}

    @router.post("/x-ads/drafts")
    async def create_x_ads_draft(body: DraftCreate, user=user_dep):
        uid = _tenant_id(user)
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name is required")
        st = (body.status or "draft").strip().lower()
        if st not in ALLOWED_STATUS:
            st = "draft"
        obj = (body.objective or "reach").strip() or "reach"
        doc: Dict[str, Any] = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "name": name,
            "objective": obj,
            "daily_budget": float(body.daily_budget or 0),
            "currency": (body.currency or "USD").strip().upper()[:8],
            "notes": (body.notes or "").strip(),
            "status": st,
            "created_at": datetime.utcnow(),
            "source": "x_ads_ui",
        }
        await db.x_ads_campaign_drafts.insert_one(doc)
        return {"draft": _serialize(doc)}

    @router.patch("/x-ads/drafts/{draft_id}")
    async def update_x_ads_draft(draft_id: str, body: DraftUpdate, user=user_dep):
        uid = _tenant_id(user)
        existing = await db.x_ads_campaign_drafts.find_one({"_id": draft_id, "user_id": uid})
        if not existing:
            raise HTTPException(404, "Draft not found")
        updates: Dict[str, Any] = {}
        if body.name is not None:
            n = body.name.strip()
            if not n:
                raise HTTPException(400, "name cannot be empty")
            updates["name"] = n
        if body.objective is not None:
            updates["objective"] = body.objective.strip()
        if body.daily_budget is not None:
            updates["daily_budget"] = float(body.daily_budget)
        if body.currency is not None:
            updates["currency"] = body.currency.strip().upper()[:8]
        if body.notes is not None:
            updates["notes"] = body.notes.strip()
        if body.status is not None:
            st = body.status.strip().lower()
            if st not in ALLOWED_STATUS:
                raise HTTPException(400, f"invalid status: {body.status}")
            updates["status"] = st
        if updates:
            await db.x_ads_campaign_drafts.update_one(
                {"_id": draft_id, "user_id": uid},
                {"$set": updates},
            )
        row = await db.x_ads_campaign_drafts.find_one({"_id": draft_id, "user_id": uid})
        return {"draft": _serialize(row or existing)}

    @router.delete("/x-ads/drafts/{draft_id}")
    async def delete_x_ads_draft(draft_id: str, user=user_dep):
        uid = _tenant_id(user)
        res = await db.x_ads_campaign_drafts.delete_one({"_id": draft_id, "user_id": uid})
        if res.deleted_count == 0:
            raise HTTPException(404, "Draft not found")
        return {"status": "deleted", "id": draft_id}

    @router.post("/social-post-draft")
    async def social_post_draft(body: SocialPostDraftBody, user=user_dep):
        """Generate title + caption for the social scheduler using the same AI stack as broadcasts."""
        from ai_service import get_drafter

        drafter = get_drafter()
        if not drafter.clients:
            raise HTTPException(
                status_code=503,
                detail="AI is not configured. Add OPENAI_API_KEY or another provider on the server.",
            )

        business_name = (user.get("business_name") or user.get("name") or "Your business").strip()
        model_pref = (user.get("settings") or {}).get("ai_model", "standard") or "standard"
        chans = [c.strip().lower() for c in (body.channels or []) if c and str(c).strip()]
        if not chans:
            chans = ["facebook"]

        result = await drafter.draft_social_post(
            prompt=body.prompt.strip(),
            channels=chans,
            business_name=business_name,
            model_pref=model_pref,
        )
        title = (result.get("title") or "").strip()
        caption = (result.get("body") or "").strip()
        if not caption:
            raise HTTPException(500, "AI returned empty caption")
        return {"title": title or "Untitled post", "body": caption}

    return router
