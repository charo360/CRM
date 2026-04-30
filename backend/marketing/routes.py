"""REST for Marketing — ad campaign drafts in Mongo (Meta + X), aligned with assistant save/list tools."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

ALLOWED_STATUS = frozenset({"draft", "active", "paused", "ended"})
ALLOWED_POST_STATUS = frozenset({"draft", "scheduled", "published", "failed"})


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


class AlertRuleBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=1)
    condition: str
    operator: str
    value: float
    action: str = "alert_only"
    min_spend: float = 5.0
    min_impressions: int = 300
    notify_whatsapp: bool = True
    enabled: bool = True


class SocialPostDraftBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(..., min_length=3, max_length=4000)
    channels: List[str] = Field(default_factory=lambda: ["facebook"])


class PostAsset(BaseModel):
    file_name: str
    mime_type: str
    preview_data_url: Optional[str] = None
    s3_url: Optional[str] = None


class ScheduledPostCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    channels: List[str] = Field(default_factory=lambda: ["facebook"])
    scheduled_at: str = ""  # ISO string
    status: str = "draft"
    post_kind: Optional[str] = None
    placement_id: Optional[str] = None
    placement_width: Optional[int] = None
    placement_height: Optional[int] = None
    link_url: Optional[str] = None
    assets: Optional[List[PostAsset]] = None
    image_url: Optional[str] = None  # AI-generated design image


class ScheduledPostUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = None
    body: Optional[str] = None
    channels: Optional[List[str]] = None
    scheduled_at: Optional[str] = None
    status: Optional[str] = None
    post_kind: Optional[str] = None
    placement_id: Optional[str] = None
    placement_width: Optional[int] = None
    placement_height: Optional[int] = None
    link_url: Optional[str] = None
    assets: Optional[List[PostAsset]] = None
    image_url: Optional[str] = None


def _serialize_post(row: Dict[str, Any]) -> Dict[str, Any]:
    def _dt(v):
        return v.isoformat() if hasattr(v, "isoformat") else (v or "")
    return {
        "id": str(row["_id"]),
        "title": row.get("title") or "",
        "body": row.get("body") or "",
        "channels": row.get("channels") or ["facebook"],
        "scheduled_at": _dt(row.get("scheduled_at")),
        "status": row.get("status") or "draft",
        "created_at": _dt(row.get("created_at")),
        "updated_at": _dt(row.get("updated_at")),
        "post_kind": row.get("post_kind"),
        "placement_id": row.get("placement_id"),
        "placement_width": row.get("placement_width"),
        "placement_height": row.get("placement_height"),
        "link_url": row.get("link_url"),
        "assets": row.get("assets") or [],
        "image_url": row.get("image_url"),
    }


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

    # ── Scheduled posts ──────────────────────────────────────────────────────────

    @router.get("/social-posts")
    async def list_social_posts(status: Optional[str] = None, user=user_dep):
        uid = _tenant_id(user)
        q: Dict[str, Any] = {"user_id": uid}
        if status and status in ALLOWED_POST_STATUS:
            q["status"] = status
        rows = await db.scheduled_posts.find(q).sort("scheduled_at", 1).to_list(500)
        return {"posts": [_serialize_post(r) for r in rows]}

    @router.post("/social-posts")
    async def create_social_post(body: ScheduledPostCreate, user=user_dep):
        uid = _tenant_id(user)
        st = (body.status or "draft").strip().lower()
        if st not in ALLOWED_POST_STATUS:
            st = "draft"
        now = datetime.utcnow()
        try:
            sched = datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00")) if body.scheduled_at else now
        except Exception:
            sched = now
        doc: Dict[str, Any] = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "title": body.title.strip(),
            "body": body.body.strip(),
            "channels": [c.strip().lower() for c in (body.channels or ["facebook"]) if c.strip()],
            "scheduled_at": sched,
            "status": st,
            "created_at": now,
            "updated_at": now,
            "post_kind": body.post_kind,
            "placement_id": body.placement_id,
            "placement_width": body.placement_width,
            "placement_height": body.placement_height,
            "link_url": body.link_url,
            "assets": [a.model_dump() for a in (body.assets or [])],
            "image_url": body.image_url,
        }
        await db.scheduled_posts.insert_one(doc)
        return {"post": _serialize_post(doc)}

    @router.patch("/social-posts/{post_id}")
    async def update_social_post(post_id: str, body: ScheduledPostUpdate, user=user_dep):
        uid = _tenant_id(user)
        existing = await db.scheduled_posts.find_one({"_id": post_id, "user_id": uid})
        if not existing:
            raise HTTPException(404, "Post not found")
        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if body.title is not None:
            t = body.title.strip()
            if not t:
                raise HTTPException(400, "title cannot be empty")
            updates["title"] = t
        if body.body is not None:
            updates["body"] = body.body.strip()
        if body.channels is not None:
            updates["channels"] = [c.strip().lower() for c in body.channels if c.strip()]
        if body.scheduled_at is not None:
            try:
                updates["scheduled_at"] = datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
            except Exception:
                pass
        if body.status is not None:
            st = body.status.strip().lower()
            if st not in ALLOWED_POST_STATUS:
                raise HTTPException(400, f"invalid status: {body.status}")
            updates["status"] = st
        if body.post_kind is not None:
            updates["post_kind"] = body.post_kind
        if body.placement_id is not None:
            updates["placement_id"] = body.placement_id
        if body.placement_width is not None:
            updates["placement_width"] = body.placement_width
        if body.placement_height is not None:
            updates["placement_height"] = body.placement_height
        if body.link_url is not None:
            updates["link_url"] = body.link_url
        if body.assets is not None:
            updates["assets"] = [a.model_dump() for a in body.assets]
        if body.image_url is not None:
            updates["image_url"] = body.image_url
        await db.scheduled_posts.update_one({"_id": post_id, "user_id": uid}, {"$set": updates})
        row = await db.scheduled_posts.find_one({"_id": post_id, "user_id": uid})
        return {"post": _serialize_post(row or existing)}

    @router.delete("/social-posts/{post_id}")
    async def delete_social_post(post_id: str, user=user_dep):
        uid = _tenant_id(user)
        res = await db.scheduled_posts.delete_one({"_id": post_id, "user_id": uid})
        if res.deleted_count == 0:
            raise HTTPException(404, "Post not found")
        return {"status": "deleted", "id": post_id}

    @router.get("/social-posts/analytics")
    async def social_posts_analytics(days: int = 30, channel: Optional[str] = None, user=user_dep):
        """Engagement analytics summary for published posts."""
        from datetime import timedelta
        uid = _tenant_id(user)
        since = datetime.utcnow() - timedelta(days=days)
        q: Dict[str, Any] = {
            "user_id": uid,
            "status": "published",
            "scheduled_at": {"$gte": since},
        }
        if channel:
            q["channels"] = {"$in": [channel.strip().lower()]}

        posts = await db.scheduled_posts.find(q).sort("scheduled_at", -1).to_list(500)

        totals = {"likes": 0, "comments": 0, "shares": 0, "reach": 0, "clicks": 0, "saves": 0}
        by_channel: Dict[str, Any] = {}
        top_posts = []

        for p in posts:
            eng = p.get("engagement") or {}
            l = int(eng.get("likes", 0))
            c = int(eng.get("comments", 0))
            s = int(eng.get("shares", 0))
            r = int(eng.get("reach", 0))
            cl = int(eng.get("clicks", 0))
            sv = int(eng.get("saves", 0))
            totals["likes"] += l; totals["comments"] += c; totals["shares"] += s
            totals["reach"] += r; totals["clicks"] += cl; totals["saves"] += sv
            for ch in (p.get("channels") or []):
                bc = by_channel.setdefault(ch, {"likes": 0, "comments": 0, "shares": 0,
                                               "reach": 0, "clicks": 0, "posts": 0})
                bc["likes"] += l; bc["comments"] += c; bc["shares"] += s
                bc["reach"] += r; bc["clicks"] += cl; bc["posts"] += 1
            sa = p.get("scheduled_at")
            top_posts.append({
                "id": str(p["_id"]), "title": p.get("title") or "",
                "channels": p.get("channels") or [],
                "date": sa.isoformat() if hasattr(sa, "isoformat") else str(sa or ""),
                "likes": l, "comments": c, "shares": s, "reach": r, "clicks": cl,
                "engagement_score": l + c * 2 + s * 3 + cl,
                "zernio_post_id": p.get("zernio_post_id"),
                "engagement_synced_at": (
                    p["engagement_synced_at"].isoformat()
                    if hasattr(p.get("engagement_synced_at"), "isoformat") else None
                ),
            })

        top_posts.sort(key=lambda x: x["engagement_score"], reverse=True)
        return {
            "period_days": days,
            "total_posts": len(posts),
            "unsynced_posts": sum(1 for p in posts if not p.get("engagement")),
            "totals": totals,
            "by_channel": by_channel,
            "top_posts": top_posts[:10],
            "avg_reach_per_post": round(totals["reach"] / len(posts), 1) if posts else 0,
            "avg_engagement_rate": (
                round((totals["likes"] + totals["comments"] + totals["shares"])
                      / totals["reach"] * 100, 2) if totals["reach"] > 0 else 0
            ),
        }

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

    # ── Zernio Live Ads ───────────────────────────────────────────────────────────

    @router.get("/meta-ads/live-campaigns")
    async def live_campaigns(
        platform: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        days: int = Query(30, ge=1, le=365),
        user=user_dep,
    ):
        """Fetch live campaigns from Zernio Ads API."""
        from zernio_ads_service import list_campaigns
        result = await list_campaigns(platform=platform, status=status, days=days)
        return result

    @router.get("/meta-ads/insights")
    async def ads_insights(
        platform: Optional[str] = Query(None),
        days: int = Query(30, ge=1, le=365),
        user=user_dep,
    ):
        """Fetch aggregated insights (spend, impressions, clicks, CTR) from Zernio Ads API."""
        from zernio_ads_service import list_campaigns

        result = await list_campaigns(platform=platform, days=days)
        campaigns = result.get("campaigns") or result.get("data") or []

        total_spend = 0.0
        total_impressions = 0
        total_clicks = 0
        total_reach = 0
        total_conversions = 0

        for c in campaigns:
            metrics = c.get("metrics") or c.get("insights") or c
            total_spend += float(metrics.get("spend", 0) or 0)
            total_impressions += int(metrics.get("impressions", 0) or 0)
            total_clicks += int(metrics.get("clicks", 0) or 0)
            total_reach += int(metrics.get("reach", 0) or 0)
            total_conversions += int(metrics.get("conversions", 0) or 0)

        ctr = round(total_clicks / total_impressions * 100, 2) if total_impressions else 0
        cpc = round(total_spend / total_clicks, 4) if total_clicks else 0
        cpm = round(total_spend / total_impressions * 1000, 4) if total_impressions else 0

        return {
            "period_days": days,
            "total_campaigns": len(campaigns),
            "spend": round(total_spend, 2),
            "impressions": total_impressions,
            "clicks": total_clicks,
            "reach": total_reach,
            "conversions": total_conversions,
            "ctr": ctr,
            "cpc": cpc,
            "cpm": cpm,
            "campaigns": campaigns,
            "error": result.get("error"),
        }

    @router.post("/meta-ads/campaigns/{campaign_id}/status")
    async def update_live_campaign_status(
        campaign_id: str,
        body: Dict[str, Any],
        user=user_dep,
    ):
        """Pause or activate a live campaign via Zernio Ads API."""
        from zernio_ads_service import update_campaign_status

        status = body.get("status", "").strip().lower()
        if status not in ("active", "paused"):
            raise HTTPException(400, "status must be 'active' or 'paused'")
        platform = body.get("platform")
        result = await update_campaign_status(campaign_id, status=status, platform=platform)
        if result.get("error"):
            raise HTTPException(502, result["error"])
        return result

    @router.put("/meta-ads/campaigns/{campaign_id}/budget")
    async def update_live_campaign_budget(
        campaign_id: str,
        body: Dict[str, Any],
        user=user_dep,
    ):
        """Update budget or bid strategy for a live campaign via Zernio Ads API."""
        from zernio_ads_service import update_campaign_budget

        result = await update_campaign_budget(
            campaign_id,
            daily_budget=body.get("daily_budget"),
            lifetime_budget=body.get("lifetime_budget"),
            bid_strategy=body.get("bid_strategy"),
            platform=body.get("platform"),
        )
        if result.get("error"):
            raise HTTPException(502, result["error"])
        return result

    @router.get("/meta-ads/accounts")
    async def live_ad_accounts(user=user_dep):
        """List connected ad accounts from Zernio."""
        from zernio_ads_service import list_ad_accounts
        return await list_ad_accounts()

    @router.post("/meta-ads/boost")
    async def boost_post(body: Dict[str, Any], user=user_dep):
        """Boost an existing social post as a paid ad via Zernio."""
        from zernio_ads_service import boost_post as _boost

        required = ["post_id", "platform", "daily_budget", "duration_days"]
        for f in required:
            if not body.get(f):
                raise HTTPException(400, f"'{f}' is required")
        result = await _boost(
            post_id=str(body["post_id"]),
            platform=str(body["platform"]),
            daily_budget=float(body["daily_budget"]),
            duration_days=int(body["duration_days"]),
            objective=body.get("objective"),
            audience=body.get("audience"),
        )
        if result.get("error"):
            raise HTTPException(502, result["error"])
        return result

    @router.post("/meta-ads/ctwa")
    async def create_ctwa(body: Dict[str, Any], user=user_dep):
        """Create a Click-to-WhatsApp ad via Zernio."""
        from zernio_ads_service import create_ctwa_ad

        required = ["platform", "whatsapp_number", "creative", "daily_budget", "duration_days"]
        for f in required:
            if not body.get(f):
                raise HTTPException(400, f"'{f}' is required")
        result = await create_ctwa_ad(
            platform=str(body["platform"]),
            whatsapp_number=str(body["whatsapp_number"]),
            creative=body["creative"],
            daily_budget=float(body["daily_budget"]),
            duration_days=int(body["duration_days"]),
            audience=body.get("audience"),
        )
        if result.get("error"):
            raise HTTPException(502, result["error"])
        return result

    # ── Ad Health Monitor ─────────────────────────────────────────────────────────

    @router.get("/ad-health")
    async def get_ad_health(
        days: int = Query(7, ge=1, le=90),
        zone: Optional[str] = Query(None),
        user=user_dep,
    ):
        """Current health scores for all live campaigns."""
        from zernio_ads_service import list_campaigns
        from ad_health_monitor import score_campaign, ensure_default_rules

        uid = _tenant_id(user)
        await ensure_default_rules(db, uid)

        result = await list_campaigns(days=days)
        campaigns = result.get("campaigns") or result.get("data") or []

        scored = []
        for c in campaigns:
            metrics = c.get("metrics") or c.get("insights") or c
            health_score, issues, z = score_campaign(metrics)
            if zone and z != zone:
                continue
            scored.append({
                "campaign_id":   str(c.get("id") or c.get("campaignId") or ""),
                "name":          c.get("name") or c.get("campaignName") or "Unknown",
                "status":        c.get("status", ""),
                "platform":      c.get("platform", ""),
                "health_score":  health_score,
                "zone":          z,
                "issues":        issues[:4],
                "spend":         float(metrics.get("spend", 0) or 0),
                "impressions":   int(metrics.get("impressions", 0) or 0),
                "clicks":        int(metrics.get("clicks", 0) or 0),
                "ctr":           float(metrics.get("ctr", 0) or 0),
                "cpc":           float(metrics.get("cpc", 0) or 0),
                "roas":          float(metrics.get("roas", 0) or 0),
                "conversions":   int(metrics.get("conversions", 0) or 0),
            })
        scored.sort(key=lambda x: x["health_score"])
        return {
            "campaigns": scored,
            "summary": {
                "critical": sum(1 for c in scored if c["zone"] == "critical"),
                "warning":  sum(1 for c in scored if c["zone"] == "warning"),
                "healthy":  sum(1 for c in scored if c["zone"] == "healthy"),
                "total":    len(scored),
            },
            "days": days,
            "error": result.get("error"),
        }

    @router.get("/ad-health/history")
    async def get_alert_history(
        limit: int = Query(50, ge=1, le=200),
        user=user_dep,
    ):
        """Recent alert actions (auto-pauses + warnings) for this user."""
        uid = _tenant_id(user)
        rows = await db.ad_alert_history.find({"user_id": uid}).sort("fired_at", -1).to_list(limit)

        def _ser(r: Dict[str, Any]) -> Dict[str, Any]:
            fa = r.get("fired_at")
            return {
                "id":            str(r["_id"]),
                "campaign_id":   r.get("campaign_id", ""),
                "campaign_name": r.get("campaign_name", ""),
                "rule_name":     r.get("rule_name", ""),
                "action":        r.get("action", ""),
                "health_score":  r.get("health_score"),
                "zone":          r.get("zone", ""),
                "metrics":       r.get("metrics", {}),
                "fired_at":      fa.isoformat() if hasattr(fa, "isoformat") else str(fa or ""),
            }
        return {"history": [_ser(r) for r in rows]}

    @router.get("/ad-health/rules")
    async def list_alert_rules(user=user_dep):
        """List all alert rules for this user."""
        from ad_health_monitor import ensure_default_rules

        uid = _tenant_id(user)
        await ensure_default_rules(db, uid)
        rows = await db.ad_alert_rules.find({"user_id": uid}).sort("created_at", 1).to_list(100)

        def _ser(r: Dict[str, Any]) -> Dict[str, Any]:
            ca = r.get("created_at")
            return {
                "id":               str(r["_id"]),
                "name":             r.get("name", ""),
                "condition":        r.get("condition", ""),
                "operator":         r.get("operator", ""),
                "value":            r.get("value", 0),
                "action":           r.get("action", "alert_only"),
                "min_spend":        r.get("min_spend", 0),
                "min_impressions":  r.get("min_impressions", 0),
                "notify_whatsapp":  r.get("notify_whatsapp", True),
                "enabled":          r.get("enabled", True),
                "is_default":       r.get("is_default", False),
                "created_at":       ca.isoformat() if hasattr(ca, "isoformat") else None,
            }
        return {"rules": [_ser(r) for r in rows]}

    @router.post("/ad-health/rules")
    async def create_alert_rule(body: AlertRuleBody, user=user_dep):
        """Create a new alert rule."""
        import uuid as _uuid
        uid = _tenant_id(user)
        allowed_conditions = {"health_score", "ctr", "roas", "cpc", "cpm", "spend", "clicks"}
        allowed_operators  = {"lt", "gt", "lte", "gte"}
        allowed_actions    = {"auto_pause", "alert_only"}
        if body.condition not in allowed_conditions:
            raise HTTPException(400, f"Invalid condition: {body.condition}")
        if body.operator not in allowed_operators:
            raise HTTPException(400, f"Invalid operator: {body.operator}")
        if body.action not in allowed_actions:
            raise HTTPException(400, f"Invalid action: {body.action}")

        now = datetime.utcnow()
        doc: Dict[str, Any] = {
            "_id":             str(_uuid.uuid4()),
            "user_id":         uid,
            "name":            body.name,
            "condition":       body.condition,
            "operator":        body.operator,
            "value":           body.value,
            "action":          body.action,
            "min_spend":       body.min_spend,
            "min_impressions": body.min_impressions,
            "notify_whatsapp": body.notify_whatsapp,
            "enabled":         body.enabled,
            "is_default":      False,
            "created_at":      now,
            "updated_at":      now,
        }
        await db.ad_alert_rules.insert_one(doc)
        doc["id"] = doc["_id"]
        return {"rule": doc}

    @router.patch("/ad-health/rules/{rule_id}")
    async def update_alert_rule(rule_id: str, body: Dict[str, Any], user=user_dep):
        """Update an existing alert rule (partial update)."""
        uid = _tenant_id(user)
        existing = await db.ad_alert_rules.find_one({"_id": rule_id, "user_id": uid})
        if not existing:
            raise HTTPException(404, "Rule not found")
        allowed = {"name", "condition", "operator", "value", "action", "min_spend", "min_impressions", "notify_whatsapp", "enabled"}
        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for k, v in body.items():
            if k in allowed:
                updates[k] = v
        if updates:
            await db.ad_alert_rules.update_one({"_id": rule_id}, {"$set": updates})
        row = await db.ad_alert_rules.find_one({"_id": rule_id})
        ca = row.get("created_at")
        return {"rule": {
            "id": str(row["_id"]),
            "name": row.get("name", ""),
            "condition": row.get("condition", ""),
            "operator": row.get("operator", ""),
            "value": row.get("value", 0),
            "action": row.get("action", "alert_only"),
            "min_spend": row.get("min_spend", 0),
            "min_impressions": row.get("min_impressions", 0),
            "notify_whatsapp": row.get("notify_whatsapp", True),
            "enabled": row.get("enabled", True),
            "is_default": row.get("is_default", False),
            "created_at": ca.isoformat() if hasattr(ca, "isoformat") else None,
        }}

    @router.delete("/ad-health/rules/{rule_id}")
    async def delete_alert_rule(rule_id: str, user=user_dep):
        """Delete an alert rule."""
        uid = _tenant_id(user)
        res = await db.ad_alert_rules.delete_one({"_id": rule_id, "user_id": uid})
        if res.deleted_count == 0:
            raise HTTPException(404, "Rule not found")
        return {"status": "deleted", "id": rule_id}

    return router
