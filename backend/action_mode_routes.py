"""
Action Mode — Autonomous AI business agent.
Runs background agents: Funding Hunter, Lead Gen, Social Scout, Admin Autopilot.
"""
import logging
import uuid
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _uid(user) -> str:
    return str(user["_id"])


async def queue_social_match(
    db,
    user_id: str,
    text: str,
    author: str,
    group_name: str,
    platform: str,
    url: str,
) -> bool:
    """
    Keyword-match `text` against the user's social settings and, if matched,
    draft a reply and insert it into action_mode_queue.

    Returns True if a queue item was created, False otherwise.
    Called from the Evolution API webhook for WhatsApp group messages
    and can be reused for any real-time message pipeline.
    """
    try:
        social_cfg = await db.action_mode_social.find_one({"user_id": user_id})
        if not social_cfg:
            return False

        keywords = social_cfg.get("keywords") or []
        if not keywords:
            return False

        lower = text.lower()
        matched = [kw for kw in keywords if kw and kw.lower().strip() in lower]
        if not matched:
            return False

        biz = await db.users.find_one({"_id": user_id}) or {}
        biz_name     = biz.get("business_name", "")
        biz_type     = biz.get("business_type", "")
        location     = social_cfg.get("location") or ""
        mode         = social_cfg.get("mode", "review")
        status       = "approved" if mode == "auto" else "pending"

        draft = _draft_contextual_comment(biz_name, biz_type, text, matched[0], location)

        await db.action_mode_queue.insert_one({
            "_id":          str(uuid.uuid4()),
            "user_id":      user_id,
            "agent":        "social_extension",
            "action_type":  "post_comment",
            "title":        f"{platform.title()}: {text[:70]}",
            "draft_content": draft,
            "metadata": {
                "url":        url,
                "platform":   platform,
                "snippet":    text[:300],
                "keyword":    matched[0],
                "author":     author,
                "group_name": group_name,
            },
            "status":       status,
            "posted":       False,
            "created_at":   datetime.utcnow(),
        })

        await db.action_mode_feed.insert_one({
            "_id":        str(uuid.uuid4()),
            "user_id":    user_id,
            "agent":      "social_extension",
            "title":      f"🎯 Match in {group_name}",
            "detail":     f"{author}: {text[:120]}",
            "kind":       "opportunity",
            "created_at": datetime.utcnow(),
        })
        return True

    except Exception as e:
        logger.error("[queue_social_match] user=%s error=%s", user_id, e)
        return False


class ActionModeSettings(BaseModel):
    enabled: bool = False
    goals: Optional[str] = None
    agents: Optional[Dict[str, bool]] = None


class QueueAction(BaseModel):
    item_id: Optional[str] = None
    action: Optional[str] = None
    edited_content: Optional[str] = None


class CustomAgentBody(BaseModel):
    name: str
    emoji: Optional[str] = "🤖"
    description: str
    schedule: Optional[str] = "on_demand"
    enabled: Optional[bool] = True


class SocialEngagementSettings(BaseModel):
    platforms: Optional[List[str]] = []
    keywords: Optional[List[str]] = []
    groups: Optional[List[str]] = []
    location: Optional[str] = ""
    daily_limit: Optional[int] = 10
    auto_run: Optional[bool] = True
    mode: Optional[str] = "review"
    google_review_link: Optional[str] = None


class CommandQueryBody(BaseModel):
    query: str


class ExtensionPost(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    group_name: Optional[str] = None
    platform: Optional[str] = "facebook"
    matched_keywords: Optional[List[str]] = []
    timestamp: Optional[str] = None


class MarkPostedBody(BaseModel):
    item_id: Optional[str] = None


class ReviewRequestBody(BaseModel):
    phone: Optional[str] = None
    customer_name: Optional[str] = None
    review_link: Optional[str] = None


def make_action_mode_router(db, user_dep):
    router = APIRouter(prefix="/action-mode", tags=["action-mode"])

    # ─────────────────────────────────────────────────────────────────────────
    # Settings — on/off toggle + goals
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/settings")
    async def get_settings(user=Depends(user_dep)):
        uid = _uid(user)
        doc = await db.action_mode_settings.find_one({"user_id": uid})
        if not doc:
            return {"enabled": False, "goals": "", "agents": _default_agents()}
        doc.pop("_id", None)
        return doc

    @router.put("/settings")
    async def update_settings(body: ActionModeSettings, user=Depends(user_dep)):
        uid = _uid(user)
        await db.action_mode_settings.update_one(
            {"user_id": uid},
            {"$set": {
                "user_id": uid,
                "enabled": body.enabled,
                "goals": body.goals or "",
                "agents": body.agents or _default_agents(),
                "updated_at": datetime.utcnow(),
            }},
            upsert=True,
        )
        return {"status": "saved"}

    # ─────────────────────────────────────────────────────────────────────────
    # Activity feed — what the agent did
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/feed")
    async def get_feed(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.action_mode_activity.find(
            {"user_id": uid}
        ).sort("created_at", -1).to_list(50)
        for i in items:
            i["_id"] = str(i["_id"])
        return {"items": items}

    # ─────────────────────────────────────────────────────────────────────────
    # Approval queue — items waiting for user action
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/queue")
    async def get_queue(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.action_mode_queue.find(
            {"user_id": uid, "status": "pending"}
        ).sort("created_at", -1).to_list(30)
        for i in items:
            i["_id"] = str(i["_id"])
        return {"items": items}

    @router.post("/queue/action")
    async def queue_action(body: QueueAction, bg: BackgroundTasks, user=Depends(user_dep)):
        uid = _uid(user)
        if not body.item_id or not body.action:
            raise HTTPException(400, "item_id and action are required")
        item = await db.action_mode_queue.find_one({"_id": body.item_id, "user_id": uid})
        if not item:
            raise HTTPException(404, "Item not found")

        if body.action == "approve":
            content = body.edited_content or item.get("draft_content", "")
            await db.action_mode_queue.update_one(
                {"_id": body.item_id},
                {"$set": {"status": "approved", "approved_at": datetime.utcnow()}},
            )
            bg.add_task(_execute_approved_action, db, uid, item, content)
            return {"status": "approved"}

        elif body.action == "skip":
            await db.action_mode_queue.update_one(
                {"_id": body.item_id},
                {"$set": {"status": "skipped", "skipped_at": datetime.utcnow()}},
            )
            return {"status": "skipped"}

        raise HTTPException(400, "Invalid action")

    # ─────────────────────────────────────────────────────────────────────────
    # Run agents manually (also called by scheduler)
    # ─────────────────────────────────────────────────────────────────────────

    @router.post("/run")
    async def run_now(bg: BackgroundTasks, user=Depends(user_dep)):
        """Trigger all enabled agents immediately."""
        uid = _uid(user)
        settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        agents_cfg = settings.get("agents", _default_agents())
        goals = settings.get("goals", "")

        biz = await db.users.find_one({"_id": uid}) or {}
        biz_context = {
            "business_name": biz.get("business_name", ""),
            "business_type": biz.get("business_type", ""),
            "country": biz.get("country", "Kenya"),
            "goals": goals,
        }

        if agents_cfg.get("funding_hunter", True):
            bg.add_task(_run_funding_hunter, db, uid, biz_context)
        if agents_cfg.get("lead_gen", True):
            bg.add_task(_run_lead_gen, db, uid, biz_context)
        if agents_cfg.get("social_scout", True):
            bg.add_task(_run_social_scout, db, uid, biz_context)
        if agents_cfg.get("admin_autopilot", True):
            bg.add_task(_run_admin_autopilot, db, uid, biz_context)

        # Social engagement agent — runs if configured and auto_run enabled
        social_cfg = await db.action_mode_social.find_one({"user_id": uid})
        if social_cfg and social_cfg.get("auto_run", True) and social_cfg.get("keywords"):
            bg.add_task(_run_social_engagement, db, uid, social_cfg, biz_context)

        return {"status": "started", "message": "All agents are running in background"}

    @router.post("/run/{agent}")
    async def run_agent(agent: str, bg: BackgroundTasks, user=Depends(user_dep)):
        """Run a specific agent."""
        uid = _uid(user)
        biz = await db.users.find_one({"_id": uid}) or {}
        settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        biz_context = {
            "business_name": biz.get("business_name", ""),
            "business_type": biz.get("business_type", ""),
            "country": biz.get("country", "Kenya"),
            "goals": settings.get("goals", ""),
        }
        runners = {
            "funding_hunter": _run_funding_hunter,
            "lead_gen": _run_lead_gen,
            "social_scout": _run_social_scout,
            "admin_autopilot": _run_admin_autopilot,
        }
        if agent not in runners:
            raise HTTPException(400, f"Unknown agent: {agent}")
        bg.add_task(runners[agent], db, uid, biz_context)
        return {"status": "started", "agent": agent}

    # ─────────────────────────────────────────────────────────────────────────
    # Opportunities store (funding, leads, groups, etc.)
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/opportunities")
    async def get_opportunities(user=Depends(user_dep), kind: Optional[str] = None):
        uid = _uid(user)
        query: Dict[str, Any] = {"user_id": uid}
        if kind:
            query["kind"] = kind
        items = await db.action_mode_opportunities.find(query).sort(
            [("score", -1), ("created_at", -1)]
        ).to_list(50)
        for i in items:
            i["_id"] = str(i["_id"])
        return {"opportunities": items}

    # ─────────────────────────────────────────────────────────────────────────
    # Custom Agents — users build their own agents in plain English
    # ─────────────────────────────────────────────────────────────────────────

    @router.post("/agents")
    async def create_custom_agent(body: CustomAgentBody, user=Depends(user_dep)):
        uid = _uid(user)
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "name": body.name,
            "emoji": body.emoji or "🤖",
            "description": body.description,
            "schedule": body.schedule or "on_demand",
            "enabled": True if body.enabled is None else body.enabled,
            "created_at": datetime.utcnow(),
        }
        await db.action_mode_custom_agents.insert_one(doc)
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @router.get("/agents")
    async def list_custom_agents(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.action_mode_custom_agents.find(
            {"user_id": uid}
        ).sort("created_at", -1).to_list(50)
        for i in items:
            if hasattr(i.get("created_at"), "isoformat"):
                i["created_at"] = i["created_at"].isoformat()
        return {"agents": items}

    @router.put("/agents/{agent_id}")
    async def update_custom_agent(agent_id: str, body: CustomAgentBody, user=Depends(user_dep)):
        uid = _uid(user)
        result = await db.action_mode_custom_agents.update_one(
            {"_id": agent_id, "user_id": uid},
            {"$set": {
                "name": body.name,
                "emoji": body.emoji or "🤖",
                "description": body.description,
                "schedule": body.schedule or "on_demand",
                "enabled": True if body.enabled is None else body.enabled,
                "updated_at": datetime.utcnow(),
            }}
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Agent not found")
        return {"status": "updated"}

    @router.delete("/agents/{agent_id}")
    async def delete_custom_agent(agent_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        result = await db.action_mode_custom_agents.delete_one(
            {"_id": agent_id, "user_id": uid}
        )
        if result.deleted_count == 0:
            raise HTTPException(404, "Agent not found")
        return {"status": "deleted"}

    # ─────────────────────────────────────────────────────────────────────────
    # Social Engagement Agent — find conversations, draft replies, queue for review
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/social/settings")
    async def get_social_settings(user=Depends(user_dep)):
        uid = _uid(user)
        doc = await db.action_mode_social.find_one({"user_id": uid})
        if not doc:
            return {
                "platforms": ["facebook"],
                "keywords": [],
                "groups": [],
                "location": "",
                "daily_limit": 10,
                "auto_run": True,
                "mode": "review",
                "google_review_link": None,
            }
        doc.pop("_id", None)
        doc.pop("user_id", None)
        doc.setdefault("groups", [])
        doc.setdefault("mode", "review")
        doc.setdefault("google_review_link", None)
        doc.setdefault("keywords", [])
        doc.setdefault("platforms", ["facebook"])
        doc.setdefault("location", "")
        doc.setdefault("daily_limit", 10)
        doc.setdefault("auto_run", True)
        return doc

    @router.put("/social/settings")
    async def save_social_settings(body: SocialEngagementSettings, user=Depends(user_dep)):
        uid = _uid(user)
        await db.action_mode_social.update_one(
            {"user_id": uid},
            {"$set": {**body.dict(), "user_id": uid, "updated_at": datetime.utcnow()}},
            upsert=True,
        )
        return {"status": "saved"}

    @router.get("/social/suggest-urls")
    async def suggest_watch_urls(
        platforms: str = Query(default=""),
        keywords: str  = Query(default=""),
        user=Depends(user_dep),
    ):
        """Search for relevant group/community/hashtag URLs per platform."""
        plat_list = [p.strip() for p in platforms.split(",") if p.strip()]
        kw_list   = [k.strip() for k in keywords.split(",")  if k.strip()]

        if not plat_list or not kw_list:
            return {"suggestions": []}

        # Per-platform DDG site: prefix and URL pattern
        PLATFORM_CONFIG = {
            "facebook":  {"site": "facebook.com/groups", "url_prefix": "facebook.com/groups"},
            "linkedin":  {"site": "linkedin.com/groups",  "url_prefix": "linkedin.com/groups"},
            "reddit":    {"site": "reddit.com/r",         "url_prefix": "reddit.com/r"},
            "telegram":  {"site": "t.me",                 "url_prefix": "t.me"},
            "whatsapp":  {"site": "chat.whatsapp.com",    "url_prefix": "chat.whatsapp.com"},
        }
        # Hashtag-based platforms — generate URLs directly, no search needed
        HASHTAG_PLATFORMS = {
            "tiktok":    lambda kw: f"https://www.tiktok.com/tag/{kw.replace(' ', '')}",
            "instagram": lambda kw: f"https://www.instagram.com/explore/tags/{kw.replace(' ', '')}",
        }

        suggestions = []

        # Hashtag platforms — instant, no DDG call
        for plat in plat_list:
            if plat in HASHTAG_PLATFORMS:
                for kw in kw_list[:3]:
                    suggestions.append({
                        "platform": plat,
                        "url":   HASHTAG_PLATFORMS[plat](kw),
                        "title": f"#{kw.replace(' ', '')} on {plat.title()}",
                    })

        # Search-based platforms
        search_plats = [p for p in plat_list if p in PLATFORM_CONFIG]
        if search_plats and kw_list:
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    for plat in search_plats:
                        cfg  = PLATFORM_CONFIG[plat]
                        seen = set()
                        for kw in kw_list[:2]:
                            query = f'site:{cfg["site"]} "{kw}"'
                            try:
                                results = list(ddgs.text(query, max_results=4))
                            except Exception:
                                results = []
                            for r in results:
                                url = r.get("href", "")
                                if cfg["url_prefix"] in url and url not in seen:
                                    seen.add(url)
                                    suggestions.append({
                                        "platform": plat,
                                        "url":      url,
                                        "title":    r.get("title", url),
                                    })
            except Exception as e:
                logger.warning("[suggest-urls] search error: %s", e)

        return {"suggestions": suggestions[:20]}

    # ── Extension inbound endpoint ────────────────────────────────────────────

    @router.post("/extension/post")
    async def receive_extension_post(body: ExtensionPost, user=Depends(user_dep)):
        """Receives a keyword-matched post from the Chrome extension."""
        uid = _uid(user)

        if not body.url or not body.text:
            raise HTTPException(400, "url and text are required")

        # Deduplicate by URL
        existing = await db.action_mode_queue.find_one({"user_id": uid, "metadata.url": body.url})
        if existing:
            return {"status": "duplicate"}

        biz = await db.users.find_one({"_id": uid}) or {}
        social_cfg = await db.action_mode_social.find_one({"user_id": uid}) or {}

        biz_name = biz.get("business_name") or "our business"
        biz_type = biz.get("business_type") or ""
        location = social_cfg.get("location") or ""
        keyword = (body.matched_keywords or [""])[0]

        draft = _draft_contextual_comment(biz_name, biz_type, body.text, keyword, location)
        mode = social_cfg.get("mode", "review")
        # Auto mode: mark immediately approved so extension posts it next cycle
        status = "approved" if mode == "auto" else "pending"

        title = f"{(body.platform or 'social').title()}: {body.text[:70]}"
        await db.action_mode_queue.insert_one({
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "agent": "social_extension",
            "action_type": "post_comment",
            "title": title,
            "draft_content": draft,
            "metadata": {
                "url": body.url,
                "platform": body.platform or "facebook",
                "snippet": body.text[:300],
                "keyword": keyword,
                "author": body.author or "",
                "group_name": body.group_name or "",
            },
            "status": status,
            "posted": False,
            "created_at": datetime.utcnow(),
        })

        await _log_activity(db, uid, "social_extension",
                            f"🔍 Extension match on {(body.platform or 'social').title()}",
                            f"{body.author or 'Someone'}: {body.text[:120]}",
                            kind="opportunity")

        return {"status": "queued", "mode": mode}

    @router.get("/extension/approved-posts")
    async def get_approved_posts(user=Depends(user_dep)):
        """Extension polls this to get approved post_comment items ready to auto-post."""
        uid = _uid(user)
        items = await db.action_mode_queue.find({
            "user_id": uid,
            "action_type": "post_comment",
            "status": "approved",
            "posted": {"$ne": True},
        }).sort("created_at", 1).to_list(10)  # max 10 per batch
        for i in items:
            i["_id"] = str(i["_id"])
        return {"items": items}

    @router.post("/extension/mark-posted")
    async def mark_posted(body: MarkPostedBody, user=Depends(user_dep)):
        uid = _uid(user)
        if not body.item_id:
            raise HTTPException(400, "item_id required")
        await db.action_mode_queue.update_one(
            {"_id": body.item_id, "user_id": uid},
            {"$set": {"posted": True, "posted_at": datetime.utcnow(), "status": "posted"}},
        )
        item = await db.action_mode_queue.find_one({"_id": body.item_id})
        if item:
            await _log_activity(db, uid, item.get("agent", "social_extension"),
                                f"✅ Auto-posted on {item.get('metadata', {}).get('platform', 'social').title()}",
                                item.get("title", "")[:120],
                                kind="action")
        return {"status": "posted"}

    # ── Google review request via WhatsApp ───────────────────────────────────

    @router.post("/request-review")
    async def request_review(body: ReviewRequestBody, user=Depends(user_dep)):
        """Send a WhatsApp message asking a customer to leave a Google review."""
        uid = _uid(user)
        if not body.phone:
            raise HTTPException(400, "phone required")

        biz = await db.users.find_one({"_id": uid}) or {}
        biz_name = biz.get("business_name") or "us"

        # Prefer the link provided, fall back to saved setting
        social_cfg = await db.action_mode_social.find_one({"user_id": uid}) or {}
        link = body.review_link or social_cfg.get("google_review_link") or ""

        name = body.customer_name or "there"
        msg  = (
            f"Hi {name}! 🙏 Thank you for choosing {biz_name}. "
            f"We'd love to hear your feedback — a quick Google review means the world to us and helps others find us."
        )
        if link:
            msg += f"\n\n⭐ Leave a review here: {link}"

        try:
            from whatsapp_service import WhatsAppService
            wa = WhatsAppService(db)
            result = await wa.send_message(uid, body.phone, msg, customer_name=name)
            if not result.get("success"):
                raise HTTPException(500, result.get("error", "WhatsApp send failed"))
        except ImportError:
            raise HTTPException(503, "WhatsApp service not available")

        await _log_activity(db, uid, "google_reviews",
                            f"⭐ Review request sent to {name}",
                            f"Sent to {body.phone}", kind="action")
        return {"status": "sent"}

    @router.post("/run-social")
    async def run_social(bg: BackgroundTasks, user=Depends(user_dep)):
        uid = _uid(user)
        social_cfg = await db.action_mode_social.find_one({"user_id": uid})
        if not social_cfg or not social_cfg.get("keywords"):
            raise HTTPException(400, "Add at least one keyword in Social Engagement settings first")
        biz = await db.users.find_one({"_id": uid}) or {}
        settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        biz_context = {
            "business_name": biz.get("business_name", ""),
            "business_type": biz.get("business_type", ""),
            "country": biz.get("country", "Kenya"),
            "goals": settings.get("goals", ""),
        }
        bg.add_task(_run_social_engagement, db, uid, social_cfg, biz_context)
        return {"status": "started"}

    # ─────────────────────────────────────────────────────────────────────────
    # Fusion Engine — cluster weak signals into high-confidence opportunities
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/clusters")
    async def get_clusters(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.action_mode_clusters.find(
            {"user_id": uid}
        ).sort("confidence", -1).to_list(30)
        for i in items:
            i["_id"] = str(i["_id"])
            if hasattr(i.get("created_at"), "isoformat"):
                i["created_at"] = i["created_at"].isoformat()
        return {"clusters": items}

    @router.post("/clusters/run")
    async def run_fusion_engine(bg: BackgroundTasks, user=Depends(user_dep)):
        uid = _uid(user)
        biz = await db.users.find_one({"_id": uid}) or {}
        settings_doc = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        biz_context = {
            "business_name": biz.get("business_name", ""),
            "business_type": biz.get("business_type", ""),
            "country": biz.get("country", "Kenya"),
            "goals": settings_doc.get("goals", ""),
        }
        bg.add_task(_run_fusion_engine, db, uid, biz_context)
        return {"status": "started"}

    @router.delete("/clusters/{cluster_id}")
    async def dismiss_cluster(cluster_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        await db.action_mode_clusters.delete_one({"_id": cluster_id, "user_id": uid})
        return {"status": "dismissed"}

    # ─────────────────────────────────────────────────────────────────────────
    # Predictive Radar — forecast opportunities in the next 30-90 days
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/predictions")
    async def get_predictions(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.action_mode_predictions.find(
            {"user_id": uid}
        ).sort("days_until", 1).to_list(20)
        for i in items:
            i["_id"] = str(i["_id"])
            if hasattr(i.get("created_at"), "isoformat"):
                i["created_at"] = i["created_at"].isoformat()
        return {"predictions": items}

    @router.post("/predictions/run")
    async def run_predictive_radar(bg: BackgroundTasks, user=Depends(user_dep)):
        uid = _uid(user)
        biz = await db.users.find_one({"_id": uid}) or {}
        settings_doc = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        social_cfg   = await db.action_mode_social.find_one({"user_id": uid}) or {}
        biz_context  = {
            "business_name": biz.get("business_name", ""),
            "business_type": biz.get("business_type", ""),
            "country":       biz.get("country", "Kenya"),
            "goals":         settings_doc.get("goals", ""),
            "keywords":      social_cfg.get("keywords", []),
        }
        bg.add_task(_run_predictive_radar, db, uid, biz_context)
        return {"status": "started"}

    @router.delete("/predictions/{prediction_id}")
    async def dismiss_prediction(prediction_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        await db.action_mode_predictions.delete_one({"_id": prediction_id, "user_id": uid})
        return {"status": "dismissed"}

    # ─────────────────────────────────────────────────────────────────────────
    # Recon Engine — job boards, new businesses, permits/tenders
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/recon")
    async def get_recon(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.action_mode_recon.find(
            {"user_id": uid}
        ).sort("confidence", -1).to_list(40)
        for i in items:
            i["_id"] = str(i["_id"])
            if hasattr(i.get("created_at"), "isoformat"):
                i["created_at"] = i["created_at"].isoformat()
        return {"recon": items}

    @router.post("/recon/run")
    async def run_recon_engine(bg: BackgroundTasks, user=Depends(user_dep)):
        uid = _uid(user)
        biz = await db.users.find_one({"_id": uid}) or {}
        settings_doc = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        social_cfg   = await db.action_mode_social.find_one({"user_id": uid}) or {}
        biz_context  = {
            "business_name": biz.get("business_name", ""),
            "business_type": biz.get("business_type", ""),
            "country":       biz.get("country", "Kenya"),
            "city":          biz.get("city", ""),
            "goals":         settings_doc.get("goals", ""),
            "keywords":      social_cfg.get("keywords", []),
        }
        bg.add_task(_run_recon_engine, db, uid, biz_context)
        return {"status": "started"}

    @router.delete("/recon/{recon_id}")
    async def dismiss_recon(recon_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        await db.action_mode_recon.delete_one({"_id": recon_id, "user_id": uid})
        return {"status": "dismissed"}

    # ─────────────────────────────────────────────────────────────────────────
    # Command Query — natural language → approval queue items
    # ─────────────────────────────────────────────────────────────────────────

    @router.post("/command-query")
    async def run_command_query(body: CommandQueryBody, bg: BackgroundTasks, user=Depends(user_dep)):
        uid = _uid(user)
        biz = await db.users.find_one({"_id": uid}) or {}
        settings_doc = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        biz_context = {
            "business_name": biz.get("business_name", "My Business"),
            "business_type": biz.get("business_type", ""),
            "country":       biz.get("country", ""),
            "city":          biz.get("city", ""),
            "goals":         settings_doc.get("goals", ""),
        }
        bg.add_task(_process_command_query, db, uid, body.query, biz_context)
        return {"status": "processing"}

    # ─────────────────────────────────────────────────────────────────────────
    # Instant Action Mode — approval-gated automation queue
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/instant")
    async def get_instant_actions(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.action_mode_instant.find(
            {"user_id": uid, "status": {"$ne": "rejected"}}
        ).sort("created_at", -1).to_list(60)
        for i in items:
            if isinstance(i.get("created_at"), datetime):
                i["created_at"] = i["created_at"].isoformat()
            if isinstance(i.get("approved_at"), datetime):
                i["approved_at"] = i["approved_at"].isoformat()
        return {"items": items}

    @router.post("/instant/generate")
    async def generate_instant_actions(bg: BackgroundTasks, user=Depends(user_dep)):
        uid = _uid(user)
        biz = await db.users.find_one({"_id": uid}) or {}
        settings_doc = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        biz_context = {
            "business_name": biz.get("business_name", "My Business"),
            "business_type": biz.get("business_type", ""),
            "country":       biz.get("country", ""),
            "city":          biz.get("city", ""),
            "goals":         settings_doc.get("goals", ""),
        }
        bg.add_task(_generate_instant_actions, db, uid, biz_context)
        return {"status": "generating"}

    @router.post("/instant/{action_id}/approve")
    async def approve_instant_action(action_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        await db.action_mode_instant.update_one(
            {"_id": action_id, "user_id": uid},
            {"$set": {"status": "approved", "approved_at": datetime.utcnow()}}
        )
        return {"ok": True}

    @router.post("/instant/{action_id}/execute")
    async def execute_instant_action(action_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        await db.action_mode_instant.update_one(
            {"_id": action_id, "user_id": uid},
            {"$set": {"status": "executed", "executed_at": datetime.utcnow()}}
        )
        return {"ok": True}

    @router.delete("/instant/{action_id}")
    async def reject_instant_action(action_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        await db.action_mode_instant.update_one(
            {"_id": action_id, "user_id": uid},
            {"$set": {"status": "rejected"}}
        )
        return {"ok": True}

    @router.post("/run-custom/{agent_id}")
    async def run_custom_agent_route(agent_id: str, bg: BackgroundTasks, user=Depends(user_dep)):
        uid = _uid(user)
        agent_doc = await db.action_mode_custom_agents.find_one(
            {"_id": agent_id, "user_id": uid}
        )
        if not agent_doc:
            raise HTTPException(404, "Agent not found")
        biz = await db.users.find_one({"_id": uid}) or {}
        settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        biz_context = {
            "business_name": biz.get("business_name", ""),
            "business_type": biz.get("business_type", ""),
            "country": biz.get("country", "Kenya"),
            "goals": settings.get("goals", ""),
        }
        bg.add_task(_run_custom_agent, db, uid, agent_doc, biz_context)
        return {"status": "started", "agent": agent_id}

    return router


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _default_agents() -> Dict[str, bool]:
    return {
        "funding_hunter": True,
        "lead_gen": True,
        "social_scout": True,
        "admin_autopilot": True,
    }


async def _log_activity(db, uid: str, agent: str, title: str, detail: str, kind: str = "info"):
    await db.action_mode_activity.insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": uid,
        "agent": agent,
        "title": title,
        "detail": detail,
        "kind": kind,   # "info" | "opportunity" | "action" | "warning"
        "created_at": datetime.utcnow(),
    })


async def _add_to_queue(db, uid: str, agent: str, action_type: str, title: str,
                        draft_content: str, metadata: Dict[str, Any]):
    await db.action_mode_queue.insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": uid,
        "agent": agent,
        "action_type": action_type,   # "send_email" | "post_comment" | "submit_application" | "send_whatsapp"
        "title": title,
        "draft_content": draft_content,
        "metadata": metadata,
        "status": "pending",
        "created_at": datetime.utcnow(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# AI helper — score & enrich a batch of raw search results
# ─────────────────────────────────────────────────────────────────────────────

async def _ai_score_results(
    results: List[Dict[str, Any]],
    context: str,
    agent_goal: str,
) -> List[Dict[str, Any]]:
    """
    Uses the LLM to score each result 1-10 for relevance, filter out junk,
    and rewrite the snippet into a 1-sentence actionable insight.
    Returns only results scoring >= 6, sorted best-first.
    Falls back gracefully if LLM is unavailable.
    """
    if not results:
        return results
    try:
        import json as _json, os as _os, httpx as _httpx

        items_txt = "\n".join(
            f"{i+1}. TITLE: {r.get('title','')}\n   URL: {r.get('url','')}\n   SNIPPET: {r.get('snippet','')[:200]}"
            for i, r in enumerate(results)
        )
        prompt = (
            f"You are an expert business opportunity analyst.\n"
            f"Context about this business: {context}\n"
            f"Agent goal: {agent_goal}\n\n"
            f"Rate each result 1-10 for how SPECIFICALLY useful it is to this business "
            f"(10 = direct match, actionable, not generic; 1 = completely irrelevant or a generic article).\n"
            f"Also rewrite the snippet as one sentence: what action should the business owner take?\n\n"
            f"Results:\n{items_txt}\n\n"
            f'Return ONLY a JSON array: [{{"idx":1,"score":8,"insight":"..."}},...]\n'
            f"No markdown, no explanation."
        )

        for key_env, base_url, model in [
            ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "deepseek-chat"),
            ("OPENAI_API_KEY",   "https://api.openai.com/v1",   "gpt-4o-mini"),
        ]:
            api_key = _os.environ.get(key_env, "")
            if not api_key:
                continue
            try:
                async with _httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                            "max_tokens": 800,
                        },
                    )
                    resp.raise_for_status()
                    raw = resp.json()["choices"][0]["message"]["content"].strip()
                    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
                    scores = _json.loads(raw)
                    scored = []
                    for item in scores:
                        idx = item.get("idx", 0) - 1
                        score = int(item.get("score", 0))
                        insight = item.get("insight", "")
                        if 0 <= idx < len(results) and score >= 6:
                            r = dict(results[idx])
                            r["score"] = score
                            if insight:
                                r["snippet"] = insight
                            scored.append(r)
                    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
                    return scored
            except Exception as e:
                logger.warning("[ai_score] %s failed: %s", key_env, e)
                continue
    except Exception as e:
        logger.warning("[ai_score] skipped: %s", e)
    return results


async def _ai_generate_queries(
    template: str,
    context: str,
    n: int = 10,
) -> List[str]:
    """
    Ask the LLM to generate n diverse, creative, non-obvious search queries
    based on a template and business context. Falls back to template list.
    """
    try:
        import json as _json, os as _os, httpx as _httpx

        prompt = (
            f"You are a world-class business intelligence researcher.\n"
            f"Business context: {context}\n"
            f"Search goal: {template}\n\n"
            f"Generate {n} highly specific, diverse, non-obvious search queries that would surface "
            f"results BEYOND the first page of a typical Google search. Mix:\n"
            f"- Very niche/specific queries (exact program names, local governments, diaspora funds)\n"
            f"- 'intitle:' or 'site:' tricks\n"
            f"- Year/date-specific (2025, 2026, 'now open', 'deadline')\n"
            f"- Local language/regional terms when relevant\n"
            f"- Forum/community sources (reddit, groups, forums)\n\n"
            f"Return ONLY a JSON array of {n} query strings. No explanation."
        )
        for key_env, base_url, model in [
            ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "deepseek-chat"),
            ("OPENAI_API_KEY",   "https://api.openai.com/v1",   "gpt-4o-mini"),
        ]:
            api_key = _os.environ.get(key_env, "")
            if not api_key:
                continue
            try:
                async with _httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.7,
                            "max_tokens": 600,
                        },
                    )
                    resp.raise_for_status()
                    raw = resp.json()["choices"][0]["message"]["content"].strip()
                    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
                    queries = _json.loads(raw)
                    if isinstance(queries, list) and queries:
                        return [str(q) for q in queries[:n]]
            except Exception as e:
                logger.warning("[ai_generate_queries] %s failed: %s", key_env, e)
                continue
    except Exception as e:
        logger.warning("[ai_generate_queries] skipped: %s", e)
    return []


# ─────────────────────────────────────────────────────────────────────────────
# AGENT: Funding Hunter
# Deep multi-strategy search for VCs, grants, accelerators
# ─────────────────────────────────────────────────────────────────────────────

async def _run_funding_hunter(db, uid: str, ctx: Dict[str, Any]):
    try:
        biz_name = ctx.get("business_name", "my business")
        biz_type = ctx.get("business_type", "business")
        country = ctx.get("country", "Kenya")
        goals = ctx.get("goals", "")
        region = "East Africa" if country in ("Kenya", "Uganda", "Tanzania", "Rwanda", "Ethiopia") else \
                 "West Africa" if country in ("Nigeria", "Ghana", "Senegal", "Ivory Coast") else \
                 "Southern Africa" if country in ("South Africa", "Zimbabwe", "Zambia") else "Africa"

        await _log_activity(db, uid, "funding_hunter",
                            "🔍 Funding Hunter started",
                            f"Running deep multi-strategy search for {biz_name}...")

        biz_context = f"{biz_name} is a {biz_type} business in {country}. Goals: {goals or 'grow and scale'}."

        # ── Step 1: Smart multi-engine search ────────────────────────────────
        from search_engine import smart_search as _smart_search
        raw_results = await _smart_search(
            agent_goal=f"Find funding opportunities, grants, accelerators, VCs, angel investors, government programs for a {biz_type} business in {country}",
            biz_context=biz_context,
            country=country,
            n_queries=16,
            max_results=120,
        )
        if not raw_results:
            raw_results = _fallback_opportunities(country, biz_type)
        unique = raw_results

        # ── Step 2: AI scores & enriches, filters out junk ───────────────────
        await _log_activity(db, uid, "funding_hunter",
                            "🧠 AI scoring opportunities",
                            f"Analysing {len(unique)} AI-sourced results for relevance...")
        enriched = await _ai_score_results(
            unique,
            context=biz_context,
            agent_goal=f"Find real, actionable funding opportunities for {biz_name}",
        )

        # ── Step 3: Save top results & queue application drafts ───────────────
        saved = 0
        for opp in enriched[:10]:
            if not opp.get("title") or not opp.get("url"):
                continue
            existing = await db.action_mode_opportunities.find_one({"user_id": uid, "url": opp["url"]})
            if existing:
                continue

            await db.action_mode_opportunities.insert_one({
                "_id":        str(uuid.uuid4()),
                "user_id":    uid,
                "kind":       "funding",
                "agent":      "funding_hunter",
                "title":      opp["title"],
                "url":        opp["url"],
                "snippet":    opp["snippet"],
                "score":      opp.get("score", 7),
                "created_at": datetime.utcnow(),
            })
            saved += 1

            draft = _draft_eoi(biz_name, biz_type, opp["title"], goals)
            await _add_to_queue(db, uid, "funding_hunter", "send_email",
                                f"Apply: {opp['title'][:60]}",
                                draft,
                                {"url": opp["url"], "opportunity_title": opp["title"]})

        await _log_activity(db, uid, "funding_hunter",
                            f"💰 Found {saved} high-quality funding opportunities",
                            f"AI-scored from {len(unique)} results — drafts ready in your queue",
                            kind="opportunity")

    except Exception as e:
        logger.error("[funding_hunter] error: %s", e)
        await _log_activity(db, uid, "funding_hunter",
                            "⚠️ Funding Hunter error",
                            str(e), kind="warning")


def _draft_eoi(biz_name: str, biz_type: str, opportunity: str, goals: str) -> str:
    return f"""Subject: Expression of Interest — {biz_name}

Dear Team,

I am reaching out to express my interest in {opportunity}.

{biz_name} is a {biz_type} business based in East Africa. {f"Our current goals include: {goals}." if goals else ""}

We are actively looking for funding and partnership opportunities to accelerate our growth and would love to learn more about how we can work together.

Could you please share more details on the application process and eligibility criteria?

Best regards,
[Your Name]
{biz_name}
[Phone/Email]"""


def _fallback_opportunities(country: str, biz_type: str) -> list:
    return [
        {
            "title": "Antler East Africa Accelerator",
            "url": "https://www.antler.co/location/east-africa",
            "snippet": "Antler backs exceptional founders from day zero. Apply for their East Africa program.",
            "query": "accelerator",
        },
        {
            "title": "Tony Elumelu Foundation Entrepreneurship Programme",
            "url": "https://www.tonyelumelufoundation.org/teep",
            "snippet": "Provides seed capital, training and mentoring to 1,000 African entrepreneurs annually.",
            "query": "grant",
        },
        {
            "title": "Mercy Corps Ventures — East Africa",
            "url": "https://www.mercycorpsventures.org",
            "snippet": "Invests in early-stage startups addressing community needs in emerging markets.",
            "query": "VC",
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# AGENT: Lead Gen
# Finds potential customers based on business type
# ─────────────────────────────────────────────────────────────────────────────

async def _run_lead_gen(db, uid: str, ctx: Dict[str, Any]):
    try:
        biz_name = ctx.get("business_name", "my business")
        biz_type = ctx.get("business_type", "business")
        country = ctx.get("country", "Kenya")
        goals   = ctx.get("goals", "")

        await _log_activity(db, uid, "lead_gen",
                            "🎯 Lead Gen started",
                            f"Running deep buyer-intent search for {biz_name}...")

        biz_context = f"{biz_name} is a {biz_type} business in {country}. Goals: {goals or 'find new customers'}."

        # ── Step 1: Smart multi-engine search ────────────────────────────────
        from search_engine import smart_search as _smart_search
        raw_results = await _smart_search(
            agent_goal=(
                f"Find active buyer-intent signals for {biz_type} in {country}: "
                f"people and groups actively looking to buy, needing this service, or asking for recommendations. "
                f"Include classifieds (Jiji, OLX, Craigslist, Facebook Marketplace), community groups, "
                f"WhatsApp/Telegram directories, Reddit, LinkedIn, local forums."
            ),
            biz_context=biz_context,
            country=country,
            n_queries=16,
            max_results=120,
        )
        unique = raw_results

        # ── Step 2: AI scores for buyer-intent relevance ──────────────────────
        await _log_activity(db, uid, "lead_gen",
                            "🧠 AI scoring leads",
                            f"Analysing {len(unique)} AI-sourced results for buyer intent...")
        enriched = await _ai_score_results(
            unique,
            context=biz_context,
            agent_goal=f"Find active buyer-intent signals — real people or groups looking to buy {biz_type} in {country}",
        )

        # ── Step 3: Save best results ─────────────────────────────────────────
        saved = 0
        for opp in enriched[:10]:
            url = opp.get("url", "")
            if not url or not opp.get("title"):
                continue
            existing = await db.action_mode_opportunities.find_one({"user_id": uid, "url": url})
            if existing:
                continue

            is_group = any(x in url for x in ["facebook.com/groups", "facebook.com/group", "whatsapp.com", "t.me", "telegram"])
            kind_val  = "group" if is_group else "group"

            await db.action_mode_opportunities.insert_one({
                "_id":        str(uuid.uuid4()),
                "user_id":    uid,
                "kind":       kind_val,
                "agent":      "lead_gen",
                "title":      opp["title"],
                "url":        url,
                "snippet":    opp["snippet"],
                "score":      opp.get("score", 7),
                "created_at": datetime.utcnow(),
            })
            saved += 1

            action = "join_group" if is_group else "post_comment"
            draft  = (
                f"Potential customer group found: {opp['title']}\n\n"
                f"{opp['snippet']}\n\nURL: {url}"
            ) if is_group else (
                f"Buyer-intent signal detected: {opp['title']}\n\n"
                f"{opp['snippet']}\n\nURL: {url}\n\n"
                f"Suggested action: Reach out and offer your {biz_type} services."
            )
            await _add_to_queue(db, uid, "lead_gen", action,
                                f"{'Join group' if is_group else 'Engage'}: {opp['title'][:55]}",
                                draft,
                                {"url": url, "group_name": opp["title"]})

        await _log_activity(db, uid, "lead_gen",
                            f"👥 Found {saved} buyer-intent opportunities",
                            f"AI-filtered from {len(unique)} results — review in your queue",
                            kind="opportunity")

    except Exception as e:
        logger.error("[lead_gen] error: %s", e)
        await _log_activity(db, uid, "lead_gen",
                            "⚠️ Lead Gen error", str(e), kind="warning")


# ─────────────────────────────────────────────────────────────────────────────
# AGENT: Social Scout
# Finds conversation opportunities on social media
# ─────────────────────────────────────────────────────────────────────────────

async def _run_social_scout(db, uid: str, ctx: Dict[str, Any]):
    try:
        biz_type = ctx.get("business_type", "business")
        country  = ctx.get("country", "Kenya")
        biz_name = ctx.get("business_name", "")
        goals    = ctx.get("goals", "")

        await _log_activity(db, uid, "social_scout",
                            "🌐 Social Scout started",
                            "Scanning multiple platforms for live engagement opportunities...")

        biz_context = f"{biz_name} is a {biz_type} business in {country}. Goals: {goals or 'engage with potential customers'}."

        # ── Step 1: Smart multi-engine search ────────────────────────────────
        from search_engine import smart_search as _smart_search
        raw_results = await _smart_search(
            agent_goal=(
                f"Find live social media conversations, forum threads, and community posts "
                f"where people are asking about, looking for, or discussing {biz_type} in {country}. "
                f"Include Facebook, Reddit, Quora, LinkedIn, Twitter/X, local forums, review sites."
            ),
            biz_context=biz_context,
            country=country,
            n_queries=16,
            max_results=120,
        )
        unique = raw_results

        # ── Step 2: AI scores for engagement-worthiness ───────────────────────
        await _log_activity(db, uid, "social_scout",
                            "🧠 AI scoring social signals",
                            f"Analysing {len(unique)} AI-sourced social posts...")
        enriched = await _ai_score_results(
            unique,
            context=biz_context,
            agent_goal=f"Find real social posts where commenting as {biz_name} would be genuine, welcome, and likely to generate leads",
        )

        # ── Step 3: Save & draft contextual comments ─────────────────────────
        saved = 0
        for opp in enriched[:10]:
            url = opp.get("url", "")
            if not url or not opp.get("title"):
                continue
            existing = await db.action_mode_opportunities.find_one({"user_id": uid, "url": url})
            if existing:
                continue

            await db.action_mode_opportunities.insert_one({
                "_id":        str(uuid.uuid4()),
                "user_id":    uid,
                "kind":       "social",
                "agent":      "social_scout",
                "title":      opp["title"],
                "url":        url,
                "snippet":    opp["snippet"],
                "score":      opp.get("score", 7),
                "created_at": datetime.utcnow(),
            })
            saved += 1

            comment_draft = _draft_contextual_comment(
                biz_name, biz_type,
                opp.get("snippet", opp.get("title", "")),
                biz_type, country,
            )
            await _add_to_queue(db, uid, "social_scout", "post_comment",
                                f"Engage: {opp['title'][:55]}",
                                comment_draft,
                                {"url": url, "snippet": opp["snippet"][:300]})

        await _log_activity(db, uid, "social_scout",
                            f"💬 Found {saved} high-value social opportunities",
                            f"AI-selected from {len(unique)} results — contextual comments ready",
                            kind="opportunity")

    except Exception as e:
        logger.error("[social_scout] error: %s", e)
        await _log_activity(db, uid, "social_scout",
                            "⚠️ Social Scout error", str(e), kind="warning")


# ─────────────────────────────────────────────────────────────────────────────
# AGENT: Admin Autopilot
# Handles business admin: overdue invoices, cold customers, follow-ups
# ─────────────────────────────────────────────────────────────────────────────

async def _run_admin_autopilot(db, uid: str, ctx: Dict[str, Any]):
    try:
        biz_name = ctx.get("business_name", "us")
        now = datetime.utcnow()

        await _log_activity(db, uid, "admin_autopilot",
                            "⚙️ Admin Autopilot started",
                            "Checking overdue invoices, cold customers...")

        actions = 0

        # Overdue invoices → draft WhatsApp reminders
        overdue_invoices = await db.invoices.find({
            "user_id": uid,
            "status": {"$in": ["unpaid", "Pending"]},
            "created_at": {"$lt": now - timedelta(days=7)},
        }).to_list(20)

        for inv in overdue_invoices:
            cust = await db.customers.find_one({"_id": inv.get("customer_id")})
            if not cust or not cust.get("phone"):
                continue
            existing = await db.action_mode_queue.find_one({
                "user_id": uid,
                "status": "pending",
                "metadata.invoice_id": str(inv["_id"]),
            })
            if existing:
                continue
            amount = inv.get("amount", 0)
            name = cust.get("name", "there")
            days_overdue = (now - inv["created_at"]).days if inv.get("created_at") else 7
            draft = (
                f"Hi {name.split()[0]}! 👋 Hope you're doing well.\n\n"
                f"Just a friendly reminder about invoice #{inv.get('invoice_number', str(inv['_id'])[-6:])} "
                f"for KES {amount:,.0f} which has been outstanding for {days_overdue} days.\n\n"
                f"Please let us know if you have any questions or need alternative payment arrangements.\n\n"
                f"Thank you! — {biz_name}"
            )
            await _add_to_queue(db, uid, "admin_autopilot", "send_whatsapp",
                                f"Invoice reminder: {name} — KES {amount:,.0f}",
                                draft,
                                {
                                    "phone": cust.get("phone"),
                                    "customer_name": name,
                                    "invoice_id": str(inv["_id"]),
                                    "amount": amount,
                                })
            actions += 1

        # Cold customers (45+ days) → draft re-engagement
        cutoff = now - timedelta(days=45)
        cold = await db.customers.find({
            "user_id": uid,
            "$or": [
                {"last_contacted": {"$lt": cutoff}},
                {"last_contacted": {"$exists": False}},
            ],
            "is_customer": {"$ne": False},
        }).to_list(10)

        for c in cold:
            existing = await db.action_mode_queue.find_one({
                "user_id": uid,
                "status": "pending",
                "metadata.customer_id": str(c["_id"]),
                "action_type": "send_whatsapp",
            })
            if existing:
                continue
            name = c.get("name", "there")
            first = name.split()[0]
            days = (now - c["last_contacted"]).days if c.get("last_contacted") else 60
            draft = (
                f"Hi {first}! 😊 It's been a while since we last connected "
                f"({days} days!) and we've been thinking of you.\n\n"
                f"We have some great new products and offers at {biz_name} "
                f"that you might love. Would love to have you back!\n\n"
                f"Reply to this message and let's catch up. 🙏"
            )
            await _add_to_queue(db, uid, "admin_autopilot", "send_whatsapp",
                                f"Re-engage: {name} ({days}d inactive)",
                                draft,
                                {
                                    "phone": c.get("phone"),
                                    "customer_name": name,
                                    "customer_id": str(c["_id"]),
                                })
            actions += 1

        await _log_activity(db, uid, "admin_autopilot",
                            f"✅ Admin Autopilot: {actions} actions queued",
                            f"{len(overdue_invoices)} invoice reminders, {len(cold)} re-engagement messages",
                            kind="action")

    except Exception as e:
        logger.error("[admin_autopilot] error: %s", e)
        await _log_activity(db, uid, "admin_autopilot",
                            "⚠️ Admin Autopilot error", str(e), kind="warning")


# ─────────────────────────────────────────────────────────────────────────────
# Execute approved actions
# ─────────────────────────────────────────────────────────────────────────────

async def _execute_approved_action(db, uid: str, item: Dict[str, Any], content: str):
    action_type = item.get("action_type", "")
    meta = item.get("metadata", {})

    try:
        if action_type == "send_whatsapp":
            phone = meta.get("phone", "")
            if phone:
                try:
                    from whatsapp_service import get_whatsapp_service
                    wa = get_whatsapp_service()
                    user = await db.users.find_one({"_id": uid})
                    instance = (user or {}).get("evolution_instance", "")
                    if instance:
                        await wa.send_message(instance, phone, content)
                except Exception as e:
                    logger.warning("[action-mode] WhatsApp send failed: %s", e)

            await _log_activity(db, uid, item.get("agent", ""),
                                f"📱 WhatsApp sent to {meta.get('customer_name', phone)}",
                                content[:200], kind="action")

        elif action_type == "send_email":
            await _log_activity(db, uid, item.get("agent", ""),
                                f"📧 Email draft approved: {item.get('title', '')}",
                                "Open your email client and send the drafted message.",
                                kind="action")

        elif action_type in ("post_comment", "join_group"):
            await _log_activity(db, uid, item.get("agent", ""),
                                f"✅ Approved: {item.get('title', '')}",
                                f"Open the link and take action: {meta.get('url', '')}",
                                kind="action")

    except Exception as e:
        logger.error("[action-mode] execute error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT: Custom Agent
# Executes a user-defined plain-English task description via web search
# ─────────────────────────────────────────────────────────────────────────────

async def _scan_zernio_for_keywords(
    db,
    uid: str,
    keywords: List[str],
    cfg: Dict[str, Any],
) -> int:
    """
    Scan Zernio inbox (WhatsApp Business DMs, Facebook/Instagram DMs) and
    post comments for keyword matches. Queues any matches into action-mode.

    Returns the number of new items queued.
    """
    if not keywords:
        return 0

    zernio_key = os.environ.get("ZERNIO_API_KEY", "").strip()
    if not zernio_key:
        return 0

    user_doc = await db.users.find_one({"_id": uid}, {"zernio_profile_id": 1})
    profile_id = (user_doc or {}).get("zernio_profile_id")
    if not profile_id:
        return 0  # User hasn't connected Zernio

    headers = {
        "Authorization": f"Bearer {zernio_key}",
        "Content-Type":  "application/json",
    }
    base    = os.environ.get("ZERNIO_API_BASE", "https://zernio.com/api/v1").rstrip("/")
    found   = 0
    mode    = cfg.get("mode", "review")

    # Track which Zernio items we've already queued to avoid duplicates
    seen_col = db.action_mode_zernio_seen

    import httpx

    async with httpx.AsyncClient(timeout=20) as client:

        # ── 1. Inbox: WhatsApp Business + other DMs ───────────────────────────
        try:
            resp = await client.get(
                f"{base}/inbox/conversations",
                headers=headers,
                params={"profileId": profile_id, "limit": 50},
            )
            if resp.status_code == 200:
                data         = resp.json()
                conversations = (
                    data.get("conversations") or
                    data.get("data") or
                    data.get("messages") or []
                )
                for conv in conversations:
                    conv_id  = str(conv.get("_id") or conv.get("id") or "")
                    if not conv_id:
                        continue

                    already_seen = await seen_col.find_one({"uid": uid, "ref": conv_id})
                    if already_seen:
                        continue

                    # Latest message text
                    last_msg = conv.get("lastMessage") or conv.get("last_message") or {}
                    text     = (
                        last_msg.get("text") or
                        last_msg.get("body") or
                        last_msg.get("content") or
                        conv.get("snippet") or ""
                    ).strip()

                    if not text or len(text) < 5:
                        continue

                    lower   = text.lower()
                    matched = [kw for kw in keywords if kw and kw.lower().strip() in lower]
                    if not matched:
                        await seen_col.insert_one({"uid": uid, "ref": conv_id, "ts": datetime.utcnow()})
                        continue

                    platform = str(conv.get("platform") or "whatsapp").lower()
                    sender   = (
                        conv.get("senderName") or
                        conv.get("contact", {}).get("name") or
                        conv.get("from") or "Customer"
                    )

                    await queue_social_match(
                        db, uid,
                        text       = text,
                        author     = sender,
                        group_name = f"{platform.title()} DM",
                        platform   = platform,
                        url        = f"https://web.whatsapp.com/",
                    )
                    await seen_col.insert_one({"uid": uid, "ref": conv_id, "ts": datetime.utcnow()})
                    found += 1
        except Exception as e:
            logger.warning("[zernio_scan] inbox error: %s", e)

        # ── 2. Comments on your own posts ─────────────────────────────────────
        try:
            resp = await client.get(
                f"{base}/comments",
                headers=headers,
                params={"profileId": profile_id, "limit": 50},
            )
            if resp.status_code == 200:
                data  = resp.json()
                posts = data.get("posts") or data.get("data") or []
                for post in posts:
                    comments = post.get("comments") or []
                    post_url = post.get("permalink") or post.get("url") or ""
                    platform = str(post.get("platform") or "facebook").lower()

                    for comment in comments:
                        comment_id = str(comment.get("_id") or comment.get("id") or "")
                        if not comment_id:
                            continue

                        already_seen = await seen_col.find_one({"uid": uid, "ref": f"c_{comment_id}"})
                        if already_seen:
                            continue

                        text   = (comment.get("text") or comment.get("message") or "").strip()
                        if not text or len(text) < 5:
                            continue

                        lower   = text.lower()
                        matched = [kw for kw in keywords if kw and kw.lower().strip() in lower]

                        await seen_col.insert_one({"uid": uid, "ref": f"c_{comment_id}", "ts": datetime.utcnow()})

                        if not matched:
                            continue

                        author = comment.get("from", {}).get("name") or comment.get("authorName") or "Commenter"
                        await queue_social_match(
                            db, uid,
                            text       = text,
                            author     = author,
                            group_name = f"{platform.title()} Post Comment",
                            platform   = platform,
                            url        = post_url,
                        )
                        found += 1
        except Exception as e:
            logger.warning("[zernio_scan] comments error: %s", e)

    # TTL cleanup — remove seen entries older than 7 days
    try:
        cutoff = datetime.utcnow() - timedelta(days=7)
        await seen_col.delete_many({"uid": uid, "ts": {"$lt": cutoff}})
    except Exception:
        pass

    if found:
        logger.info("[zernio_scan] user=%s found=%d keyword matches", uid, found)
    return found


async def _run_social_engagement(db, uid: str, cfg: Dict[str, Any], biz: Dict[str, Any]):
    """
    Social Engagement Agent.
    Searches configured platforms for conversations matching user keywords,
    drafts a contextual comment, and queues it for 'Open & Post' approval.
    """
    import random

    platforms = cfg.get("platforms") or ["facebook"]
    keywords = cfg.get("keywords") or []
    location = cfg.get("location", "")
    daily_limit = int(cfg.get("daily_limit") or 10)
    biz_name = biz.get("business_name") or "our business"
    biz_type = biz.get("business_type") or ""

    PLATFORM_SITE = {
        "facebook": "facebook.com",
        "instagram": "instagram.com",
        "linkedin": "linkedin.com",
        "reddit": "reddit.com",
        "tiktok": "tiktok.com",
    }

    await _log_activity(db, uid, "social_engagement",
                        "🔍 Social Engagement Agent started",
                        f"Scanning {len(platforms)} platform(s) · {len(keywords)} keyword(s)")

    found = 0

    try:
        from duckduckgo_search import DDGS

        for platform in platforms:
            if found >= daily_limit:
                break
            site = PLATFORM_SITE.get(platform, platform)

            for keyword in keywords:
                if found >= daily_limit:
                    break

                query = f'"{keyword}" {location} site:{site}'.strip()
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(query, max_results=5))
                except Exception as e:
                    logger.warning("[social_engagement] search error (%s/%s): %s", platform, keyword, e)
                    continue

                for r in results:
                    if found >= daily_limit:
                        break
                    url = r.get("href", "")
                    title = r.get("title", "")
                    snippet = r.get("body", "")

                    if not url or site not in url:
                        continue

                    # No duplicate URLs in queue
                    existing = await db.action_mode_queue.find_one({"user_id": uid, "metadata.url": url})
                    if existing:
                        continue

                    draft = _draft_social_comment(biz_name, biz_type, keyword, location)
                    q_status = "approved" if cfg.get("mode") == "auto" else "pending"

                    await db.action_mode_queue.insert_one({
                        "_id": str(uuid.uuid4()),
                        "user_id": uid,
                        "agent": "social_engagement",
                        "action_type": "post_comment",
                        "title": f"{platform.title()}: {title[:70]}",
                        "draft_content": draft,
                        "metadata": {
                            "url": url,
                            "platform": platform,
                            "snippet": snippet[:300],
                            "keyword": keyword,
                        },
                        "status": q_status,
                        "posted": False,
                        "created_at": datetime.utcnow(),
                    })

                    await _log_activity(db, uid, "social_engagement",
                                        f"💬 {platform.title()} post found",
                                        title[:120],
                                        kind="opportunity")
                    found += 1

    except Exception as e:
        logger.error("[social_engagement] error: %s", e)
        await _log_activity(db, uid, "social_engagement",
                            "⚠️ Social Engagement error", str(e), kind="warning")
        return

    # ── Zernio inbox + comments scan (official WhatsApp Business & social DMs) ──
    zernio_found = await _scan_zernio_for_keywords(db, uid, keywords, cfg)
    found += zernio_found

    await _log_activity(db, uid, "social_engagement",
                        f"✅ Social agent done — {found} posts queued for review",
                        "Open your Approval Queue, review each draft, and click 'Open & Post'",
                        kind="action")


def _draft_contextual_comment(biz_name: str, biz_type: str, post_text: str, keyword: str, location: str) -> str:
    """Generates a reply that responds to the actual post content."""
    import random
    lower = post_text.lower()
    loc = f"in {location}" if location else "in the region"
    service = biz_type or keyword or "this"

    if any(w in lower for w in ["urgent", "asap", "today", "tomorrow", "quickly", "immediately"]):
        templates = [
            f"Hi! {biz_name} can help urgently with {service} {loc} 🚀 DM us right away and we'll sort you out!",
            f"Hey! We handle urgent {service} requests at {biz_name} {loc}. Message us now and we'll respond fast! ⚡",
        ]
    elif any(w in lower for w in ["price", "cost", "how much", "budget", "affordable", "cheap", "quote"]):
        templates = [
            f"Hi! {biz_name} offers very competitive rates on {service} {loc} 😊 Send us a DM and we'll give you a free quote!",
            f"Hey! We have great pricing at {biz_name} for {service}. Drop us a message and we'll share our rates! 💬",
        ]
    elif any(w in lower for w in ["recommend", "best", "good", "quality", "professional", "reliable"]):
        templates = [
            f"Hi! {biz_name} comes highly recommended for {service} {loc} 🙌 Check our page or send us a message!",
            f"Hey! We're known for quality {service} at {biz_name} {loc}. Would love to show you what we can do! 💪",
        ]
    elif any(w in lower for w in ["looking for", "need", "want", "searching", "anyone know", "where can"]):
        templates = [
            f"Hi! We at {biz_name} specialize in {service} {loc} 😊 Would love to help! Feel free to DM us or check our page.",
            f"Hey! This is exactly what {biz_name} does! We offer {service} {loc}. Drop us a message! 🙏",
        ]
    else:
        templates = [
            f"Hi! {biz_name} might be able to help here — we specialize in {service} {loc}. Feel free to reach out! 😊",
            f"Hey! We handle {service} at {biz_name} {loc}. Send us a DM if you'd like to know more! 🙌",
        ]

    return random.choice(templates)


def _draft_social_comment(biz_name: str, biz_type: str, keyword: str, location: str) -> str:
    import random
    loc = f"in {location}" if location else "in the region"
    service = biz_type or keyword
    templates = [
        f"Hi! We might be able to help with this 😊 {biz_name} specialises in {service} and we serve clients {loc}. Feel free to check our page or send us a message!",
        f"Hey! This is exactly what we do at {biz_name} 🙌 We're a {service} business {loc}. Would love to connect — drop us a DM!",
        f"Looking for {keyword}? {biz_name} can help! We've worked with many clients {loc} and deliver great results. Check our page for more info 👆",
        f"Hi there! {biz_name} specialises in {service}. We serve clients {loc} and would love to help. Feel free to reach out! 🙏",
        f"This is our area of expertise at {biz_name}! We handle {service} {loc} and would be happy to discuss your needs. Send us a message! 📩",
    ]
    return random.choice(templates)


async def _run_custom_agent(db, uid: str, agent_doc: Dict[str, Any], ctx: Dict[str, Any]):
    agent_id = str(agent_doc["_id"])
    name = agent_doc.get("name", "Custom Agent")
    emoji = agent_doc.get("emoji", "🤖")
    description = agent_doc.get("description", "")
    biz_name = ctx.get("business_name", "my business")
    biz_type = ctx.get("business_type", "business")
    country = ctx.get("country", "Kenya")
    goals   = ctx.get("goals", "")

    try:
        await _log_activity(db, uid, f"custom:{agent_id}",
                            f"{emoji} {name} started",
                            f"Generating search strategy for: {description[:120]}...")

        biz_context = f"{biz_name} is a {biz_type} business in {country}. Goals: {goals or 'grow'}."

        # Smart multi-engine search from plain-English description
        from search_engine import smart_search as _smart_search
        raw_results = await _smart_search(
            agent_goal=description,
            biz_context=biz_context,
            country=country,
            n_queries=12,
            max_results=100,
        )
        unique = raw_results

        # AI scores & filters
        await _log_activity(db, uid, f"custom:{agent_id}",
                            f"🧠 {name} — AI scoring results",
                            f"Analysing {len(unique)} AI-sourced results...")
        enriched = await _ai_score_results(
            unique,
            context=biz_context,
            agent_goal=f"{name}: {description}",
        )

        saved = 0
        for r in enriched[:8]:
            url = r.get("url", "")
            if not url or not r.get("title"):
                continue
            existing = await db.action_mode_opportunities.find_one({"user_id": uid, "url": url})
            if existing:
                continue
            await db.action_mode_opportunities.insert_one({
                "_id":        str(uuid.uuid4()),
                "user_id":    uid,
                "kind":       "custom",
                "agent":      f"custom:{agent_id}",
                "agent_name": name,
                "title":      r["title"],
                "url":        url,
                "snippet":    r["snippet"],
                "score":      r.get("score", 7),
                "created_at": datetime.utcnow(),
            })
            saved += 1

            draft = (
                f"Found by {emoji} {name}:\n\n"
                f"Title: {r['title']}\n"
                f"URL: {url}\n\n"
                f"Insight: {r['snippet']}\n\n"
                f"Agent goal: {description[:200]}\n\n"
                f"Suggested action: Review this result and take action for {biz_name}."
            )
            await _add_to_queue(db, uid, f"custom:{agent_id}", "review_result",
                                f"{emoji} {r['title'][:60]}",
                                draft,
                                {"url": url, "agent_name": name})

        await _log_activity(db, uid, f"custom:{agent_id}",
                            f"{emoji} {name}: {saved} results found",
                            f"Goal: {description[:120]}",
                            kind="opportunity")

    except Exception as e:
        logger.error("[custom_agent:%s] error: %s", name, e)
        await _log_activity(db, uid, f"custom:{agent_id}",
                            f"⚠️ {name} error", str(e), kind="warning")


# ─────────────────────────────────────────────────────────────────────────────
# Fusion Engine — cross-reference all signals, cluster into opportunities
# ─────────────────────────────────────────────────────────────────────────────

async def _run_fusion_engine(db, uid: str, biz_context: dict):
    """
    Reads all signals (opportunities, social matches, feed activity),
    sends them to the LLM to find multi-signal patterns,
    and saves high-confidence clusters to action_mode_clusters.
    """
    import json as _json, os as _os

    try:
        opportunities  = await db.action_mode_opportunities.find({"user_id": uid}).sort("created_at", -1).to_list(40)
        queue_items    = await db.action_mode_queue.find({"user_id": uid}).sort("created_at", -1).to_list(30)
        feed_items     = await db.action_mode_feed.find({"user_id": uid}).sort("created_at", -1).to_list(20)

        if not opportunities and not queue_items:
            await _log_activity(db, uid, "fusion_engine",
                                "🔮 Fusion Engine: not enough signals yet",
                                "Run some agents first to collect signals", kind="info")
            return

        signal_lines: List[str] = []
        for o in opportunities:
            signal_lines.append(f"[{o.get('kind','opp').upper()}] {o.get('title','')[:80]} — {o.get('snippet','')[:100]}")
        for q in queue_items:
            m = q.get("metadata", {})
            signal_lines.append(f"[SOCIAL:{m.get('platform','?')}] {q.get('title','')[:80]} — keyword: {m.get('keyword','')}")
        for f in feed_items:
            if f.get("kind") == "opportunity":
                signal_lines.append(f"[FEED] {f.get('title','')[:80]}")

        biz_name = biz_context.get("business_name", "this business")
        biz_type = biz_context.get("business_type", "")
        country  = biz_context.get("country", "")
        goals    = biz_context.get("goals", "")

        prompt = f"""You are an intelligence analyst for {biz_name} ({biz_type}) in {country}.
Business goals: {goals or 'grow revenue and find new customers'}

Analyze these {len(signal_lines)} signals collected by AI business agents:

{chr(10).join(signal_lines[:60])}

Find patterns. Where 2+ signals point to the same underlying opportunity, cluster them into an OPPORTUNITY BUNDLE — this is stronger than any single signal alone.

Return ONLY a JSON array (no markdown, no explanation) of up to 8 clusters. Each:
{{
  "title": "Short compelling title (max 60 chars)",
  "category": "lead" | "funding" | "partnership" | "market_gap" | "timing",
  "confidence": 0.0-1.0,
  "signal_count": integer,
  "signals": ["signal description 1", "signal 2", "signal 3"],
  "insight": "One sentence pattern explanation (max 130 chars)",
  "action_hint": "Specific action to take this week (max 110 chars)",
  "urgency": "high" | "medium" | "low"
}}

Only include clusters with confidence >= 0.6. Focus on what {biz_name} can act on immediately."""

        provider = _os.environ.get("AI_PROVIDER", "openai").strip().lower()
        raw = ""

        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=_os.environ.get("ANTHROPIC_API_KEY", ""))
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
        else:
            import openai as _openai
            client = _openai.AsyncOpenAI(api_key=_os.environ.get("OPENAI_API_KEY", ""))
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            raw = resp.choices[0].message.content or "[]"

        # Parse — strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")].strip()

        try:
            parsed = _json.loads(raw)
            if isinstance(parsed, dict):
                parsed = parsed.get("clusters", parsed.get("opportunities", list(parsed.values())[0] if parsed else []))
            clusters_data = parsed if isinstance(parsed, list) else []
        except Exception:
            clusters_data = []

        # Clear stale clusters before writing fresh ones
        await db.action_mode_clusters.delete_many({"user_id": uid})

        now   = datetime.utcnow()
        saved = 0
        for c in clusters_data[:8]:
            if not isinstance(c, dict):
                continue
            confidence = float(c.get("confidence", 0))
            if confidence < 0.6:
                continue
            await db.action_mode_clusters.insert_one({
                "_id":          str(uuid.uuid4()),
                "user_id":      uid,
                "title":        str(c.get("title", "Opportunity cluster"))[:80],
                "category":     str(c.get("category", "lead")),
                "confidence":   round(confidence, 2),
                "signal_count": max(1, int(c.get("signal_count", 1))),
                "signals":      [str(s)[:120] for s in (c.get("signals") or [])[:4]],
                "insight":      str(c.get("insight", ""))[:150],
                "action_hint":  str(c.get("action_hint", ""))[:120],
                "urgency":      str(c.get("urgency", "medium")),
                "created_at":   now,
            })
            saved += 1

        await _log_activity(db, uid, "fusion_engine",
                            f"🔮 Fusion Engine: {saved} opportunity cluster{'s' if saved != 1 else ''} found",
                            f"Analysed {len(signal_lines)} signals across all agents",
                            kind="opportunity")

    except Exception as e:
        logger.error("[fusion_engine] user=%s error=%s", uid, e)
        await _log_activity(db, uid, "fusion_engine",
                            "⚠️ Fusion Engine error", str(e)[:120], kind="warning")


# ─────────────────────────────────────────────────────────────────────────────
# Predictive Radar — forecast opportunities for the next 30-90 days
# ─────────────────────────────────────────────────────────────────────────────

async def _run_predictive_radar(db, uid: str, biz_context: dict):
    """
    Uses current date + business context to forecast opportunities likely to
    emerge in the next 30-90 days: grant windows, seasonal peaks, event-driven
    leads, and hiring waves that signal service demand.
    Saves results to action_mode_predictions.
    """
    import json as _json, os as _os

    try:
        biz_name  = biz_context.get("business_name", "this business")
        biz_type  = biz_context.get("business_type", "")
        country   = biz_context.get("country", "Kenya")
        goals     = biz_context.get("goals", "")
        keywords  = biz_context.get("keywords", [])

        today     = datetime.utcnow()
        today_str = today.strftime("%B %d, %Y")  # e.g. "May 07, 2026"
        month_num = today.month

        prompt = f"""You are a strategic forecasting engine for {biz_name} ({biz_type}) based in {country}.
Today's date: {today_str}
Business goals: {goals or 'grow revenue, find new customers, reduce costs'}
Focus keywords: {', '.join(keywords[:8]) if keywords else 'general business'}

Predict SPECIFIC upcoming opportunities for this business in the next 30-90 days.
Draw on your knowledge of:
- Grant and funding cycles (government, NGO, accelerator cohorts, application windows)
- Seasonal demand spikes for {biz_type} businesses in {country} and neighbouring markets
- Industry conferences and events where buyers cluster (buyer intent peaks)
- Hiring waves: companies hiring X role often need Y service 4-8 weeks later
- Regulatory deadlines (tax filings, compliance renewals) that create urgent service demand
- Academic calendar events that drive purchasing cycles

Return ONLY a JSON array (no markdown). Up to 10 predictions, each:
{{
  "title": "Short title (max 65 chars)",
  "category": "grant" | "seasonal" | "event" | "hiring" | "regulatory" | "market",
  "predicted_window": "e.g. Jun 1 – Jun 30, 2026",
  "days_until": integer days from today until the START of the window (can be 0-90),
  "confidence": 0.0-1.0,
  "reasoning": "Why this will happen — specific pattern or known cycle (max 140 chars)",
  "action_hint": "What to do NOW to be ready (max 110 chars)",
  "signals": ["supporting evidence 1", "supporting evidence 2"]
}}

Only include predictions with confidence >= 0.65 and days_until <= 90.
Ground predictions in real patterns. Be specific about dates. Current month is {today.strftime('%B %Y')}."""

        provider = _os.environ.get("AI_PROVIDER", "openai").strip().lower()
        raw = ""

        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=_os.environ.get("ANTHROPIC_API_KEY", ""))
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
        else:
            import openai as _openai
            client = _openai.AsyncOpenAI(api_key=_os.environ.get("OPENAI_API_KEY", ""))
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            raw = resp.choices[0].message.content or "[]"

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")].strip()

        try:
            parsed = _json.loads(raw)
            if isinstance(parsed, dict):
                parsed = list(parsed.values())[0] if parsed else []
            preds_data = parsed if isinstance(parsed, list) else []
        except Exception:
            preds_data = []

        # Replace stale predictions
        await db.action_mode_predictions.delete_many({"user_id": uid})

        now   = datetime.utcnow()
        saved = 0
        for p in preds_data[:10]:
            if not isinstance(p, dict):
                continue
            confidence = float(p.get("confidence", 0))
            days_until = int(p.get("days_until", 999))
            if confidence < 0.65 or days_until > 90:
                continue
            await db.action_mode_predictions.insert_one({
                "_id":              str(uuid.uuid4()),
                "user_id":          uid,
                "title":            str(p.get("title", ""))[:80],
                "category":         str(p.get("category", "market")),
                "predicted_window": str(p.get("predicted_window", ""))[:60],
                "days_until":       max(0, days_until),
                "confidence":       round(confidence, 2),
                "reasoning":        str(p.get("reasoning", ""))[:160],
                "action_hint":      str(p.get("action_hint", ""))[:120],
                "signals":          [str(s)[:120] for s in (p.get("signals") or [])[:3]],
                "created_at":       now,
            })
            saved += 1

        await _log_activity(db, uid, "predictive_radar",
                            f"📡 Predictive Radar: {saved} forecast{'s' if saved != 1 else ''} for the next 90 days",
                            f"Grounded in seasonal patterns, grant cycles & market timing for {country}",
                            kind="opportunity")

    except Exception as e:
        logger.error("[predictive_radar] user=%s error=%s", uid, e)
        await _log_activity(db, uid, "predictive_radar",
                            "⚠️ Predictive Radar error", str(e)[:120], kind="warning")


# ─────────────────────────────────────────────────────────────────────────────
# Recon Engine — job boards + new businesses + tenders/permits
# ─────────────────────────────────────────────────────────────────────────────

async def _run_recon_engine(db, uid: str, biz_context: dict):
    """
    Runs three parallel recon scrapers using DuckDuckGo:
      1. Job Board Intel  — companies hiring roles that signal service demand
      2. New Business Radar — recently opened businesses that need services
      3. Tender / Permit Tracker — government tenders and construction permits
    Scores results with the LLM and saves to action_mode_recon.
    """
    import json as _json, os as _os

    try:
        from duckduckgo_search import DDGS
    except ImportError:
        await _log_activity(db, uid, "recon_engine",
                            "⚠️ Recon Engine: duckduckgo_search not installed", "", kind="warning")
        return

    try:
        biz_name  = biz_context.get("business_name", "")
        biz_type  = biz_context.get("business_type", "general")
        country   = biz_context.get("country", "Kenya")
        city      = biz_context.get("city", "") or country
        keywords  = biz_context.get("keywords", [])
        kw_str    = ", ".join(keywords[:5]) if keywords else biz_type

        today_year = datetime.utcnow().year

        # ── Build search queries for each recon type ──────────────────────────
        JOB_QUERIES = [
            f'site:linkedin.com/jobs "{biz_type}" "{country}" hiring',
            f'site:indeed.com "{biz_type}" "{city}" jobs',
            f'"{city}" hiring "{biz_type}" OR "{kw_str}" job vacancy {today_year}',
        ]
        NEW_BIZ_QUERIES = [
            f'"new {biz_type}" OR "recently opened" OR "just launched" "{city}" {today_year}',
            f'"{country}" "new business" "{kw_str}" {today_year} launch',
            f'site:businessregistrations.go.ke OR site:cac.gov.ng OR site:cipc.co.za "{biz_type}" {today_year}',
        ]
        TENDER_QUERIES = [
            f'"{country}" tender "{biz_type}" OR "{kw_str}" {today_year}',
            f'"{city}" construction permit OR building permit {today_year}',
            f'"{country}" government tender procurement "{biz_type}" {today_year}',
        ]

        raw_results: List[Dict[str, Any]] = []

        with DDGS() as ddgs:
            for recon_type, queries in [
                ("job_posting", JOB_QUERIES),
                ("new_business", NEW_BIZ_QUERIES),
                ("tender", TENDER_QUERIES),
            ]:
                for q in queries:
                    try:
                        results = list(ddgs.text(q, max_results=5))
                        for r in results:
                            raw_results.append({
                                "recon_type": recon_type,
                                "title":      r.get("title", "")[:120],
                                "snippet":    r.get("body", "")[:200],
                                "url":        r.get("href", ""),
                            })
                    except Exception:
                        pass

        if not raw_results:
            await _log_activity(db, uid, "recon_engine",
                                "🔍 Recon Engine: no raw results found", "", kind="info")
            return

        # ── LLM scoring pass ──────────────────────────────────────────────────
        results_text = "\n".join(
            f"[{r['recon_type'].upper()}] {r['title']} — {r['snippet']} ({r['url'][:60]})"
            for r in raw_results[:40]
        )

        prompt = f"""You are a business intelligence analyst for {biz_name} ({biz_type}) in {city}, {country}.
Keywords: {kw_str}

Below are {len(raw_results)} raw search results from job boards, business registrations, and tender databases.
Extract the MOST relevant opportunities where {biz_name} could win business.

Logic:
- Job posting (hiring X role) → company is growing and may need {biz_type} services in 30-60 days
- New business / recently opened → immediate need for {biz_type} services
- Tender / permit → direct procurement opportunity

Raw results:
{results_text}

Return ONLY a JSON array (no markdown). Up to 12 items, each:
{{
  "title": "Company or project name + what they're doing (max 70 chars)",
  "recon_type": "job_posting" | "new_business" | "tender",
  "company": "company or entity name",
  "location": "city or region",
  "source_url": "the URL from results",
  "why_relevant": "Why this signals a need for {biz_type} services (max 120 chars)",
  "action_hint": "Specific outreach action to take (max 110 chars)",
  "confidence": 0.0-1.0
}}

Only include items with confidence >= 0.6. Discard irrelevant or duplicate results."""

        provider = _os.environ.get("AI_PROVIDER", "openai").strip().lower()
        raw_llm = ""

        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=_os.environ.get("ANTHROPIC_API_KEY", ""))
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_llm = resp.content[0].text
        else:
            import openai as _openai
            client = _openai.AsyncOpenAI(api_key=_os.environ.get("OPENAI_API_KEY", ""))
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2500,
            )
            raw_llm = resp.choices[0].message.content or "[]"

        raw_llm = raw_llm.strip()
        if raw_llm.startswith("```"):
            raw_llm = raw_llm.split("```")[1].lstrip("json").strip()
        if raw_llm.endswith("```"):
            raw_llm = raw_llm[: raw_llm.rfind("```")].strip()

        try:
            parsed = _json.loads(raw_llm)
            if isinstance(parsed, dict):
                parsed = list(parsed.values())[0] if parsed else []
            recon_data = parsed if isinstance(parsed, list) else []
        except Exception:
            recon_data = []

        # Replace stale recon findings
        await db.action_mode_recon.delete_many({"user_id": uid})

        now   = datetime.utcnow()
        saved = 0
        seen_urls: set = set()
        for item in recon_data[:12]:
            if not isinstance(item, dict):
                continue
            confidence = float(item.get("confidence", 0))
            if confidence < 0.6:
                continue
            url = str(item.get("source_url", ""))[:300]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            await db.action_mode_recon.insert_one({
                "_id":          str(uuid.uuid4()),
                "user_id":      uid,
                "title":        str(item.get("title", ""))[:80],
                "recon_type":   str(item.get("recon_type", "job_posting")),
                "company":      str(item.get("company", ""))[:80],
                "location":     str(item.get("location", city))[:60],
                "source_url":   url,
                "why_relevant": str(item.get("why_relevant", ""))[:140],
                "action_hint":  str(item.get("action_hint", ""))[:120],
                "confidence":   round(confidence, 2),
                "created_at":   now,
            })
            saved += 1

        await _log_activity(db, uid, "recon_engine",
                            f"🔍 Recon Engine: {saved} intelligence target{'s' if saved != 1 else ''} found",
                            f"Scanned job boards, new businesses & tenders in {city}, {country}",
                            kind="opportunity")

    except Exception as e:
        logger.error("[recon_engine] user=%s error=%s", uid, e)
        await _log_activity(db, uid, "recon_engine",
                            "⚠️ Recon Engine error", str(e)[:120], kind="warning")


# ─────────────────────────────────────────────────────────────────────────────
# Instant Action Mode — generate approval-gated actions from intelligence data
# ─────────────────────────────────────────────────────────────────────────────

async def _generate_instant_actions(db, uid: str, biz_context: dict):
    """
    Reads clusters, predictions, and recon items then asks the LLM to produce
    5-8 fully-drafted, ready-to-send actions (emails, posts, applications).
    Saves them to action_mode_instant with status="pending".
    """
    import os as _os
    import json as _json

    try:
        biz_name  = biz_context.get("business_name", "My Business")
        biz_type  = biz_context.get("business_type", "")
        country   = biz_context.get("country", "")
        city      = biz_context.get("city", "")
        goals     = biz_context.get("goals", "grow revenue and find new customers")

        # ── Gather intelligence signals ──────────────────────────────────────
        clusters     = await db.action_mode_clusters.find({"user_id": uid}).sort("confidence", -1).to_list(8)
        predictions  = await db.action_mode_predictions.find({"user_id": uid, "days_until": {"$lte": 45}}).sort("days_until", 1).to_list(8)
        recon_items  = await db.action_mode_recon.find({"user_id": uid}).sort("confidence", -1).to_list(12)

        signal_lines: list[str] = []
        for c in clusters:
            signal_lines.append(
                f"[CLUSTER:{c.get('category','?').upper()}] {c.get('title','')} "
                f"(confidence {round(c.get('confidence',0)*100)}%, {c.get('urgency','?')} urgency) — "
                f"Action hint: {c.get('action_hint','')}"
            )
        for p in predictions:
            signal_lines.append(
                f"[PREDICTION:{p.get('category','?').upper()}] {p.get('title','')} "
                f"in {p.get('days_until',0)} days — Action hint: {p.get('action_hint','')}"
            )
        for r in recon_items:
            signal_lines.append(
                f"[RECON:{r.get('recon_type','?').upper()}] {r.get('title','')} "
                f"at {r.get('company','')} in {r.get('location','')} — "
                f"Why relevant: {r.get('why_relevant','')}. Action hint: {r.get('action_hint','')}"
            )

        if not signal_lines:
            await _log_activity(db, uid, "instant_actions",
                                "ℹ️ No intelligence signals found",
                                "Run agents, Fusion Engine, Radar or Recon first to collect signals.",
                                kind="info")
            return

        signals_text = "\n".join(signal_lines[:25])

        prompt = f"""You are an AI business assistant for: {biz_name} ({biz_type}) in {city}, {country}.
Business goals: {goals}

Based on the intelligence signals below, generate 5-8 specific, ready-to-execute actions for the business owner.
Each action must have fully written draft content — not templates, but actual ready-to-send messages.

INTELLIGENCE SIGNALS:
{signals_text}

Return a JSON array ONLY (no markdown fences, no explanation):
[
  {{
    "action_type": "email_outreach" | "apply_grant" | "social_post" | "follow_up" | "direct_message",
    "title": "Short action title (max 65 chars)",
    "target_name": "Target person, company, or platform name",
    "target_contact": "email address or social handle if known, else null",
    "draft_content": "Complete ready-to-send message. For emails: include Subject line first, then body. For social posts: full post text. For grant applications: a strong opening paragraph. Must be at least 3 sentences.",
    "source_type": "cluster" | "prediction" | "recon",
    "source_title": "Exact title of the signal that triggered this action",
    "confidence": 0.0-1.0
  }}
]

Rules:
- draft_content must be fully written, not a template. Write it as if you are {biz_name}.
- Each action must come from a different signal to maximise coverage.
- Confidence < 0.55 should not be included.
- Mix action types — don't return all emails.
- Be specific about the target (named company, grant programme, or platform).
- For grant/tender actions: mention deadline urgency if from a prediction."""

        provider = _os.environ.get("AI_PROVIDER", "openai").strip().lower()

        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=_os.environ.get("ANTHROPIC_API_KEY", ""))
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
        else:
            import openai as _openai
            client = _openai.AsyncOpenAI(api_key=_os.environ.get("OPENAI_API_KEY", ""))
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
            )
            raw = resp.choices[0].message.content or "[]"

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")].strip()

        try:
            parsed = _json.loads(raw)
            if isinstance(parsed, dict):
                parsed = list(parsed.values())[0] if parsed else []
            actions_data = parsed if isinstance(parsed, list) else []
        except Exception:
            actions_data = []

        # Replace pending items; keep approved / executed history
        await db.action_mode_instant.delete_many({"user_id": uid, "status": "pending"})

        now   = datetime.utcnow()
        saved = 0
        for a in actions_data[:8]:
            if not isinstance(a, dict):
                continue
            confidence = float(a.get("confidence", 0))
            if confidence < 0.55:
                continue
            await db.action_mode_instant.insert_one({
                "_id":            str(uuid.uuid4()),
                "user_id":        uid,
                "action_type":    str(a.get("action_type", "email_outreach")),
                "title":          str(a.get("title", ""))[:80],
                "target_name":    str(a.get("target_name", ""))[:80],
                "target_contact": a.get("target_contact"),
                "draft_content":  str(a.get("draft_content", ""))[:1500],
                "source_type":    str(a.get("source_type", "")),
                "source_title":   str(a.get("source_title", ""))[:100],
                "confidence":     round(confidence, 2),
                "status":         "pending",
                "created_at":     now,
                "approved_at":    None,
                "executed_at":    None,
            })
            saved += 1

        await _log_activity(db, uid, "instant_actions",
                            f"⚡ Instant Action Mode: {saved} action draft{'s' if saved != 1 else ''} ready for your approval",
                            "Review and approve the actions in the Instant Actions tab.",
                            kind="action")

    except Exception as e:
        logger.error("[instant_actions] user=%s error=%s", uid, e)
        await _log_activity(db, uid, "instant_actions",
                            "⚠️ Instant Action Mode error", str(e)[:120], kind="warning")


# ─────────────────────────────────────────────────────────────────────────────
# Command Query — converts a natural language request into approval queue items
# ─────────────────────────────────────────────────────────────────────────────

async def _process_command_query(db, uid: str, query: str, biz_context: dict):
    """
    Takes whatever the user typed in the command bar, searches for relevant
    content via DuckDuckGo, and drafts 3-5 ready-to-act queue items for approval.
    """
    import os as _os
    import json as _json

    try:
        biz_name = biz_context.get("business_name", "My Business")
        biz_type = biz_context.get("business_type", "")
        country  = biz_context.get("country", "")
        city     = biz_context.get("city", "")
        goals    = biz_context.get("goals", "")

        await _log_activity(db, uid, "command_query",
                            f'🔍 Processing: "{query}"',
                            "Searching and drafting actions for your approval queue…",
                            kind="info")

        # ── Search for relevant content ──────────────────────────────────────
        search_results: list[str] = []
        try:
            from duckduckgo_search import DDGS
            location_hint = f"{city} {country}".strip()
            search_q = f"{query} {location_hint}" if location_hint else query
            ddg = DDGS()
            raw = list(ddg.text(search_q, max_results=8))
            for r in raw[:8]:
                title = r.get("title", "")
                body  = r.get("body", "")[:120]
                url   = r.get("href", "")
                if title:
                    search_results.append(f"- {title}: {body} ({url})")
        except Exception as se:
            logger.warning("[command_query] DDG search failed: %s", se)

        results_text = "\n".join(search_results) if search_results else "(No live search results — use your general knowledge)"

        prompt = f"""You are an AI business assistant for {biz_name} ({biz_type}) in {city}, {country}.
Business goals: {goals or 'grow revenue and find new customers'}

The business owner typed this into the command bar:
"{query}"

Search results:
{results_text}

Generate 3-5 SPECIFIC actionable items. Each must have:
- A real URL from the search results (or the most likely real URL for this opportunity)
- The contact person or company name
- Their contact details (email / phone / social handle) if discoverable
- A full ready-to-send message or action

Return a JSON array ONLY (no markdown, no explanation):
[
  {{
    "action_type": "send_email" | "send_whatsapp" | "post_comment" | "join_group" | "submit_application" | "review_result",
    "kind": "funding" | "group" | "social" | "custom",
    "title": "What this action achieves — be specific (max 75 chars)",
    "contact_name": "Person or company name",
    "contact_info": "email address, phone number, or @handle — real if found in results, plausible if not",
    "url": "Direct URL to the opportunity, profile, post, or listing — from search results or best-guess",
    "snippet": "One sentence describing the specific opportunity (max 120 chars)",
    "draft_content": "Complete ready-to-send message written in first person as {biz_name}. For emails: Subject line first, then body. For messages: full text. For applications: opening paragraph. NO placeholders — write real names and specifics."
  }}
]

Rules:
- Every item must have a url and contact_name — infer from context if not in results.
- draft_content must be complete and specific to this exact query: "{query}"
- Make it feel like a human assistant spent an hour researching and writing this."""

        provider = _os.environ.get("AI_PROVIDER", "openai").strip().lower()

        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=_os.environ.get("ANTHROPIC_API_KEY", ""))
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_llm = resp.content[0].text
        else:
            import openai as _openai
            client = _openai.AsyncOpenAI(api_key=_os.environ.get("OPENAI_API_KEY", ""))
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2500,
            )
            raw_llm = resp.choices[0].message.content or "[]"

        raw_llm = raw_llm.strip()
        if raw_llm.startswith("```"):
            raw_llm = raw_llm.split("```")[1].lstrip("json").strip()
        if raw_llm.endswith("```"):
            raw_llm = raw_llm[: raw_llm.rfind("```")].strip()

        try:
            parsed = _json.loads(raw_llm)
            if not isinstance(parsed, list):
                logger.warning("[command_query] LLM returned non-list: %s", raw_llm[:200])
                parsed = []
        except Exception as je:
            logger.warning("[command_query] JSON parse failed: %s | raw: %s", je, raw_llm[:300])
            # Try to extract a JSON array if it's wrapped in extra text
            import re as _re
            m = _re.search(r'\[.*\]', raw_llm, _re.DOTALL)
            if m:
                try:
                    parsed = _json.loads(m.group())
                    if not isinstance(parsed, list):
                        parsed = []
                except Exception:
                    parsed = []
            else:
                parsed = []

        now   = datetime.utcnow()
        saved = 0
        for item in parsed[:5]:
            if not isinstance(item, dict):
                continue
            title         = str(item.get("title", ""))[:80]
            draft_content = str(item.get("draft_content", ""))[:1200]
            action_type   = str(item.get("action_type", "review_result"))
            if not title or not draft_content:
                continue

            url          = str(item.get("url", ""))[:500]
            contact_name = str(item.get("contact_name", ""))[:120]
            contact_info = str(item.get("contact_info", ""))[:120]
            snippet      = str(item.get("snippet", ""))[:200]
            kind         = str(item.get("kind", "custom"))

            item_id = str(uuid.uuid4())

            await db.action_mode_queue.insert_one({
                "_id":           item_id,
                "user_id":       uid,
                "agent":         "command_query",
                "action_type":   action_type,
                "title":         title,
                "draft_content": draft_content,
                "metadata": {
                    "source":       "command_query",
                    "query":        query[:120],
                    "url":          url,
                    "snippet":      snippet,
                    "contact_name": contact_name,
                    "contact_info": contact_info,
                    "kind":         kind,
                },
                "status":        "pending",
                "created_at":    now,
            })

            # Also surface in Opportunities tab
            await db.action_mode_opportunities.insert_one({
                "_id":        str(uuid.uuid4()),
                "user_id":    uid,
                "kind":       kind,
                "agent":      "command_query",
                "agent_name": "Command Query",
                "title":      title,
                "url":        url,
                "snippet":    snippet or draft_content[:160],
                "score":      0.75,
                "contact_name": contact_name,
                "contact_info": contact_info,
                "queue_id":   item_id,
                "created_at": now,
            })

            saved += 1

        if saved > 0:
            await _log_activity(db, uid, "command_query",
                                f'✅ "{query}" → {saved} action{"s" if saved != 1 else ""} added to Approval Queue',
                                "Go to Approval Queue to review, edit and act on them.",
                                kind="action")
        else:
            await _log_activity(db, uid, "command_query",
                                f'⚠️ "{query}" — no actions generated',
                                f"LLM returned {len(parsed)} item(s) but none had both title and draft_content. Check server logs.",
                                kind="warning")

    except Exception as e:
        logger.error("[command_query] user=%s error=%s", uid, e)
        await _log_activity(db, uid, "command_query",
                            f'⚠️ Error processing "{query}"', str(e)[:120], kind="warning")
