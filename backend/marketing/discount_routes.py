"""
Behavior-Triggered Discount Campaign Routes
API endpoints for managing discount campaigns
"""
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from bson import ObjectId

from marketing.behavior_triggers import (
    BehaviorTriggerEngine,
    TriggerEvent,
    DeliveryMethod,
)

logger = logging.getLogger(__name__)


# ── Request Models ────────────────────────────────────────────────────────────


class CreateCampaignRequest(BaseModel):
    name: str
    trigger_event: str
    discount_type: str  # "percentage", "fixed_amount", "free_shipping"
    discount_value: float
    delivery_method: str
    message_template: str
    conditions: dict = {}
    active: bool = True


class UpdateCampaignRequest(BaseModel):
    name: Optional[str] = None
    trigger_event: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    delivery_method: Optional[str] = None
    message_template: Optional[str] = None
    conditions: Optional[dict] = None
    active: Optional[bool] = None


class TrackEventRequest(BaseModel):
    visitor_id: str
    event_type: str
    event_data: dict = {}


class ValidateCodeRequest(BaseModel):
    discount_code: str


# ── Route Factory ─────────────────────────────────────────────────────────────


def make_discount_routes(db, get_current_user):
    router = APIRouter(prefix="/marketing/behavior-discounts", tags=["marketing"])
    trigger_engine = BehaviorTriggerEngine(db)

    def _user_id(user) -> str:
        return str(user.get("_id") or user.get("id", ""))

    # ── Create Campaign ───────────────────────────────────────────────────────

    @router.post("/campaigns")
    async def create_campaign(req: CreateCampaignRequest, user=Depends(get_current_user)):
        """Create a new behavior-triggered discount campaign"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        # Validate trigger event
        try:
            TriggerEvent(req.trigger_event)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid trigger event: {req.trigger_event}")

        # Validate delivery method
        try:
            DeliveryMethod(req.delivery_method)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid delivery method: {req.delivery_method}")

        # Create campaign
        campaign_doc = {
            "business_id": user_id,
            "name": req.name,
            "trigger_event": req.trigger_event,
            "discount_type": req.discount_type,
            "discount_value": req.discount_value,
            "delivery_method": req.delivery_method,
            "message_template": req.message_template,
            "conditions": req.conditions,
            "active": req.active,
            "created_at": datetime.utcnow(),
            "sent_count": 0,
            "conversion_count": 0,
        }

        result = await db.discount_campaigns.insert_one(campaign_doc)
        campaign_doc["_id"] = str(result.inserted_id)

        logger.info(f"[discount-campaign] Created campaign {campaign_doc['_id']} for user {user_id}")
        return {"status": "created", "campaign": campaign_doc}

    # ── List Campaigns ────────────────────────────────────────────────────────

    @router.get("/campaigns")
    async def list_campaigns(user=Depends(get_current_user)):
        """List all campaigns for the current user"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        campaigns = await db.discount_campaigns.find({"business_id": user_id}).to_list(None)

        # Convert ObjectId to string
        for campaign in campaigns:
            campaign["_id"] = str(campaign["_id"])

        return {"campaigns": campaigns}

    # ── Get Campaign ──────────────────────────────────────────────────────────

    @router.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, user=Depends(get_current_user)):
        """Get a specific campaign"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        try:
            campaign = await db.discount_campaigns.find_one({
                "_id": ObjectId(campaign_id),
                "business_id": user_id
            })
        except:
            raise HTTPException(status_code=400, detail="Invalid campaign ID")

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        campaign["_id"] = str(campaign["_id"])
        return {"campaign": campaign}

    # ── Update Campaign ───────────────────────────────────────────────────────

    @router.put("/campaigns/{campaign_id}")
    async def update_campaign(
        campaign_id: str,
        req: UpdateCampaignRequest,
        user=Depends(get_current_user)
    ):
        """Update a campaign"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        # Build update document
        update_doc = {}
        if req.name is not None:
            update_doc["name"] = req.name
        if req.trigger_event is not None:
            try:
                TriggerEvent(req.trigger_event)
                update_doc["trigger_event"] = req.trigger_event
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid trigger event: {req.trigger_event}")
        if req.discount_type is not None:
            update_doc["discount_type"] = req.discount_type
        if req.discount_value is not None:
            update_doc["discount_value"] = req.discount_value
        if req.delivery_method is not None:
            try:
                DeliveryMethod(req.delivery_method)
                update_doc["delivery_method"] = req.delivery_method
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid delivery method: {req.delivery_method}")
        if req.message_template is not None:
            update_doc["message_template"] = req.message_template
        if req.conditions is not None:
            update_doc["conditions"] = req.conditions
        if req.active is not None:
            update_doc["active"] = req.active

        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_doc["updated_at"] = datetime.utcnow()

        try:
            result = await db.discount_campaigns.update_one(
                {"_id": ObjectId(campaign_id), "business_id": user_id},
                {"$set": update_doc}
            )
        except:
            raise HTTPException(status_code=400, detail="Invalid campaign ID")

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return {"status": "updated"}

    # ── Delete Campaign ───────────────────────────────────────────────────────

    @router.delete("/campaigns/{campaign_id}")
    async def delete_campaign(campaign_id: str, user=Depends(get_current_user)):
        """Delete a campaign"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        try:
            result = await db.discount_campaigns.delete_one({
                "_id": ObjectId(campaign_id),
                "business_id": user_id
            })
        except:
            raise HTTPException(status_code=400, detail="Invalid campaign ID")

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Campaign not found")

        logger.info(f"[discount-campaign] Deleted campaign {campaign_id}")
        return {"status": "deleted"}

    # ── Track Event (Public) ──────────────────────────────────────────────────

    @router.post("/track/{business_id}")
    async def track_event(business_id: str, req: TrackEventRequest):
        """
        Track a visitor event and trigger discounts if applicable.
        This is a public endpoint called from the website widget.
        """
        try:
            event_type = TriggerEvent(req.event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {req.event_type}")

        # Track the event
        offer = await trigger_engine.track_event(
            business_id=business_id,
            visitor_id=req.visitor_id,
            event_type=event_type,
            event_data=req.event_data,
        )

        if offer:
            return {"triggered": True, "offer": offer}
        else:
            return {"triggered": False}

    # ── Check for Pending Offers ──────────────────────────────────────────────

    @router.get("/check")
    async def check_pending_offer(visitor_id: str, user=Depends(get_current_user)):
        """Check if there's a pending popup/banner offer for this visitor"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        # Check popup queue
        popup = await db.popup_queue.find_one({
            "business_id": user_id,
            "visitor_id": visitor_id,
            "shown": False,
            "expires_at": {"$gte": datetime.utcnow()}
        })

        if popup:
            return {"offer": popup["offer"], "type": "popup"}

        # Check banner queue
        banner = await db.banner_queue.find_one({
            "business_id": user_id,
            "visitor_id": visitor_id,
            "shown": False,
            "expires_at": {"$gte": datetime.utcnow()}
        })

        if banner:
            return {"offer": banner["offer"], "type": "banner"}

        return {"offer": None}

    # ── Mark Offer as Shown ───────────────────────────────────────────────────

    @router.post("/mark-shown")
    async def mark_offer_shown(
        visitor_id: str,
        campaign_id: str,
        offer_type: str,
        user=Depends(get_current_user)
    ):
        """Mark a popup/banner offer as shown"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        if offer_type == "popup":
            await db.popup_queue.update_one(
                {"business_id": user_id, "visitor_id": visitor_id, "offer.campaign_id": campaign_id},
                {"$set": {"shown": True, "shown_at": datetime.utcnow()}}
            )
        elif offer_type == "banner":
            await db.banner_queue.update_one(
                {"business_id": user_id, "visitor_id": visitor_id, "offer.campaign_id": campaign_id},
                {"$set": {"shown": True, "shown_at": datetime.utcnow()}}
            )

        return {"status": "marked"}

    # ── Validate Discount Code ────────────────────────────────────────────────

    @router.post("/validate")
    async def validate_discount_code(req: ValidateCodeRequest, user=Depends(get_current_user)):
        """Validate a discount code and return discount details"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        code_doc = await db.discount_codes.find_one({
            "business_id": user_id,
            "code": req.discount_code.upper(),
            "used": False,
            "expires_at": {"$gte": datetime.utcnow()}
        })

        if not code_doc:
            return {"valid": False, "message": "Invalid or expired discount code"}

        return {
            "valid": True,
            "discount_type": code_doc["discount_type"],
            "discount_value": code_doc["discount_value"],
            "expires_at": code_doc["expires_at"].isoformat(),
        }

    # ── Apply Discount Code ───────────────────────────────────────────────────

    @router.post("/apply")
    async def apply_discount_code(req: ValidateCodeRequest, user=Depends(get_current_user)):
        """Mark a discount code as used (called at checkout)"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        # Track conversion
        await trigger_engine.track_conversion(user_id, req.discount_code.upper())

        return {"status": "applied"}

    # ── Campaign Analytics ────────────────────────────────────────────────────

    @router.get("/analytics")
    async def get_campaign_analytics(user=Depends(get_current_user)):
        """Get analytics for all campaigns"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        campaigns = await db.discount_campaigns.find({"business_id": user_id}).to_list(None)

        analytics = []
        for campaign in campaigns:
            campaign_id = str(campaign["_id"])
            sent_count = campaign.get("sent_count", 0)
            conversion_count = campaign.get("conversion_count", 0)
            conversion_rate = (conversion_count / sent_count * 100) if sent_count > 0 else 0

            # Get revenue from conversions
            revenue = 0
            conversions = await db.discount_triggers.find({
                "business_id": user_id,
                "campaign_id": campaign_id,
                "converted": True
            }).to_list(None)

            for conv in conversions:
                # Get order value if available
                order_value = conv.get("order_value", 0)
                revenue += order_value

            analytics.append({
                "campaign_id": campaign_id,
                "campaign_name": campaign["name"],
                "trigger_event": campaign["trigger_event"],
                "sent_count": sent_count,
                "conversion_count": conversion_count,
                "conversion_rate": round(conversion_rate, 2),
                "revenue": revenue,
                "active": campaign.get("active", True),
            })

        return {"analytics": analytics}

    # ── Campaign Performance ──────────────────────────────────────────────────

    @router.get("/campaigns/{campaign_id}/performance")
    async def get_campaign_performance(campaign_id: str, user=Depends(get_current_user)):
        """Get detailed performance for a specific campaign"""
        user_id = _user_id(user)
        if not user_id:
            raise HTTPException(status_code=400, detail="Cannot identify user")

        try:
            campaign = await db.discount_campaigns.find_one({
                "_id": ObjectId(campaign_id),
                "business_id": user_id
            })
        except:
            raise HTTPException(status_code=400, detail="Invalid campaign ID")

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Get all triggers
        triggers = await db.discount_triggers.find({
            "business_id": user_id,
            "campaign_id": campaign_id
        }).to_list(None)

        # Calculate metrics
        total_sent = len(triggers)
        total_converted = sum(1 for t in triggers if t.get("converted", False))
        conversion_rate = (total_converted / total_sent * 100) if total_sent > 0 else 0

        # Get codes generated
        codes = await db.discount_codes.find({
            "business_id": user_id,
            "campaign_id": campaign_id
        }).to_list(None)

        used_codes = sum(1 for c in codes if c.get("used", False))

        # Recent triggers
        recent_triggers = sorted(triggers, key=lambda x: x.get("triggered_at", datetime.min), reverse=True)[:10]
        for t in recent_triggers:
            t["_id"] = str(t.get("_id", ""))
            if "triggered_at" in t:
                t["triggered_at"] = t["triggered_at"].isoformat()
            if "converted_at" in t:
                t["converted_at"] = t["converted_at"].isoformat()

        return {
            "campaign": {
                "_id": str(campaign["_id"]),
                "name": campaign["name"],
                "trigger_event": campaign["trigger_event"],
                "discount_type": campaign["discount_type"],
                "discount_value": campaign["discount_value"],
                "active": campaign.get("active", True),
            },
            "metrics": {
                "total_sent": total_sent,
                "total_converted": total_converted,
                "conversion_rate": round(conversion_rate, 2),
                "codes_generated": len(codes),
                "codes_used": used_codes,
            },
            "recent_triggers": recent_triggers,
        }

    return router
