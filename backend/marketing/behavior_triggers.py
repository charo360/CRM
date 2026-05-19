"""
Behavior-Triggered Discount System
Tracks visitor behavior and automatically sends personalized discounts
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from enum import Enum

logger = logging.getLogger(__name__)


class TriggerEvent(str, Enum):
    """Events that can trigger discount campaigns"""
    CART_ABANDONED = "cart_abandoned"
    BROWSED_PRODUCT = "browsed_product"
    VISITED_MULTIPLE_TIMES = "visited_multiple_times"
    HIGH_VALUE_VISITOR = "high_value_visitor"
    FIRST_TIME_VISITOR = "first_time_visitor"
    RETURNING_VISITOR = "returning_visitor"
    EXIT_INTENT = "exit_intent"
    TIME_ON_SITE = "time_on_site"
    PAGE_VIEWS_THRESHOLD = "page_views_threshold"
    PRODUCT_VIEW_NO_PURCHASE = "product_view_no_purchase"


class DeliveryMethod(str, Enum):
    """How to deliver the discount"""
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    POPUP = "popup"
    BANNER = "banner"


class DiscountCampaign:
    """Represents a behavior-triggered discount campaign"""
    
    def __init__(
        self,
        campaign_id: str,
        name: str,
        trigger_event: TriggerEvent,
        discount_type: str,  # "percentage", "fixed_amount", "free_shipping"
        discount_value: float,
        delivery_method: DeliveryMethod,
        conditions: Dict[str, Any],
        message_template: str,
        active: bool = True,
    ):
        self.campaign_id = campaign_id
        self.name = name
        self.trigger_event = trigger_event
        self.discount_type = discount_type
        self.discount_value = discount_value
        self.delivery_method = delivery_method
        self.conditions = conditions
        self.message_template = message_template
        self.active = active
        self.created_at = datetime.utcnow()
        self.sent_count = 0
        self.conversion_count = 0


class BehaviorTriggerEngine:
    """Monitors visitor behavior and triggers discount campaigns"""
    
    def __init__(self, db):
        self.db = db
        self.campaigns: Dict[str, DiscountCampaign] = {}
    
    async def load_campaigns(self, business_id: str) -> List[DiscountCampaign]:
        """Load active campaigns for a business"""
        campaigns = await self.db.discount_campaigns.find({
            "business_id": business_id,
            "active": True
        }).to_list(None)
        
        return [
            DiscountCampaign(
                campaign_id=str(c["_id"]),
                name=c["name"],
                trigger_event=TriggerEvent(c["trigger_event"]),
                discount_type=c["discount_type"],
                discount_value=c["discount_value"],
                delivery_method=DeliveryMethod(c["delivery_method"]),
                conditions=c.get("conditions", {}),
                message_template=c["message_template"],
                active=c.get("active", True),
            )
            for c in campaigns
        ]
    
    async def track_event(
        self,
        business_id: str,
        visitor_id: str,
        event_type: TriggerEvent,
        event_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Track a visitor event and check if it should trigger a discount
        
        Args:
            business_id: Business/client ID
            visitor_id: Unique visitor identifier (from GA4 client_id or email)
            event_type: Type of event that occurred
            event_data: Additional event data (product_id, cart_value, etc.)
        
        Returns:
            Discount offer if triggered, None otherwise
        """
        # Load active campaigns for this business
        campaigns = await self.load_campaigns(business_id)
        
        # Find matching campaigns
        for campaign in campaigns:
            if campaign.trigger_event != event_type:
                continue
            
            # Check if visitor already received this campaign recently
            if await self._already_sent(business_id, visitor_id, campaign.campaign_id):
                continue
            
            # Check campaign conditions
            if not self._check_conditions(campaign.conditions, event_data):
                continue
            
            # Generate discount code
            discount_code = await self._generate_discount_code(business_id, campaign)
            
            # Create discount offer
            offer = {
                "campaign_id": campaign.campaign_id,
                "campaign_name": campaign.name,
                "discount_code": discount_code,
                "discount_type": campaign.discount_type,
                "discount_value": campaign.discount_value,
                "message": self._format_message(campaign.message_template, discount_code, campaign),
                "delivery_method": campaign.delivery_method,
                "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            }
            
            # Log the trigger
            await self._log_trigger(business_id, visitor_id, campaign.campaign_id, offer)
            
            # Send the discount
            await self._deliver_discount(business_id, visitor_id, offer, event_data)
            
            return offer
        
        return None
    
    def _check_conditions(self, conditions: Dict[str, Any], event_data: Dict[str, Any]) -> bool:
        """Check if event data meets campaign conditions"""
        if not conditions:
            return True
        
        # Check minimum cart value
        if "min_cart_value" in conditions:
            cart_value = event_data.get("cart_value", 0)
            if cart_value < conditions["min_cart_value"]:
                return False
        
        # Check minimum page views
        if "min_page_views" in conditions:
            page_views = event_data.get("page_views", 0)
            if page_views < conditions["min_page_views"]:
                return False
        
        # Check minimum time on site (seconds)
        if "min_time_on_site" in conditions:
            time_on_site = event_data.get("time_on_site", 0)
            if time_on_site < conditions["min_time_on_site"]:
                return False
        
        # Check product category
        if "product_categories" in conditions:
            product_category = event_data.get("product_category")
            if product_category not in conditions["product_categories"]:
                return False
        
        # Check visitor type
        if "visitor_type" in conditions:
            visitor_type = event_data.get("visitor_type", "new")
            if visitor_type != conditions["visitor_type"]:
                return False
        
        return True
    
    async def _already_sent(self, business_id: str, visitor_id: str, campaign_id: str) -> bool:
        """Check if visitor already received this campaign recently (within 30 days)"""
        cutoff = datetime.utcnow() - timedelta(days=30)
        
        existing = await self.db.discount_triggers.find_one({
            "business_id": business_id,
            "visitor_id": visitor_id,
            "campaign_id": campaign_id,
            "triggered_at": {"$gte": cutoff}
        })
        
        return existing is not None
    
    async def _generate_discount_code(self, business_id: str, campaign: DiscountCampaign) -> str:
        """Generate a unique discount code"""
        import random
        import string
        
        # Generate random code
        code_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        discount_code = f"{campaign.name.upper().replace(' ', '')[:4]}{code_suffix}"
        
        # Store in database
        await self.db.discount_codes.insert_one({
            "business_id": business_id,
            "campaign_id": campaign.campaign_id,
            "code": discount_code,
            "discount_type": campaign.discount_type,
            "discount_value": campaign.discount_value,
            "used": False,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=7),
        })
        
        return discount_code
    
    def _format_message(self, template: str, discount_code: str, campaign: DiscountCampaign) -> str:
        """Format discount message with variables"""
        return template.format(
            discount_code=discount_code,
            discount_value=campaign.discount_value,
            discount_type=campaign.discount_type,
        )
    
    async def _log_trigger(
        self,
        business_id: str,
        visitor_id: str,
        campaign_id: str,
        offer: Dict[str, Any]
    ):
        """Log that a discount was triggered"""
        await self.db.discount_triggers.insert_one({
            "business_id": business_id,
            "visitor_id": visitor_id,
            "campaign_id": campaign_id,
            "offer": offer,
            "triggered_at": datetime.utcnow(),
            "converted": False,
        })
        
        # Update campaign stats
        await self.db.discount_campaigns.update_one(
            {"_id": campaign_id},
            {"$inc": {"sent_count": 1}}
        )
    
    async def _deliver_discount(
        self,
        business_id: str,
        visitor_id: str,
        offer: Dict[str, Any],
        event_data: Dict[str, Any]
    ):
        """Deliver the discount to the visitor"""
        delivery_method = offer["delivery_method"]
        
        if delivery_method == DeliveryMethod.EMAIL:
            await self._send_email_discount(business_id, visitor_id, offer, event_data)
        elif delivery_method == DeliveryMethod.SMS:
            await self._send_sms_discount(business_id, visitor_id, offer, event_data)
        elif delivery_method == DeliveryMethod.WHATSAPP:
            await self._send_whatsapp_discount(business_id, visitor_id, offer, event_data)
        elif delivery_method == DeliveryMethod.POPUP:
            # Store for popup display on next page load
            await self._queue_popup_discount(business_id, visitor_id, offer)
        elif delivery_method == DeliveryMethod.BANNER:
            # Store for banner display
            await self._queue_banner_discount(business_id, visitor_id, offer)
        
        logger.info(f"[behavior-trigger] Delivered {delivery_method} discount to {visitor_id}")
    
    async def _send_email_discount(
        self,
        business_id: str,
        visitor_id: str,
        offer: Dict[str, Any],
        event_data: Dict[str, Any]
    ):
        """Send discount via email"""
        # Get visitor email
        visitor_email = event_data.get("email")
        if not visitor_email:
            logger.warning(f"[behavior-trigger] No email for visitor {visitor_id}")
            return
        
        # Queue email for sending
        await self.db.email_queue.insert_one({
            "business_id": business_id,
            "to": visitor_email,
            "subject": f"Special Offer: {offer['discount_value']}% Off!",
            "body": offer["message"],
            "type": "discount_offer",
            "campaign_id": offer["campaign_id"],
            "queued_at": datetime.utcnow(),
            "sent": False,
        })
    
    async def _send_sms_discount(
        self,
        business_id: str,
        visitor_id: str,
        offer: Dict[str, Any],
        event_data: Dict[str, Any]
    ):
        """Send discount via SMS"""
        phone = event_data.get("phone")
        if not phone:
            logger.warning(f"[behavior-trigger] No phone for visitor {visitor_id}")
            return
        
        # Queue SMS
        await self.db.sms_queue.insert_one({
            "business_id": business_id,
            "to": phone,
            "message": offer["message"],
            "type": "discount_offer",
            "campaign_id": offer["campaign_id"],
            "queued_at": datetime.utcnow(),
            "sent": False,
        })
    
    async def _send_whatsapp_discount(
        self,
        business_id: str,
        visitor_id: str,
        offer: Dict[str, Any],
        event_data: Dict[str, Any]
    ):
        """Send discount via WhatsApp"""
        phone = event_data.get("phone")
        if not phone:
            logger.warning(f"[behavior-trigger] No phone for visitor {visitor_id}")
            return
        
        # Queue WhatsApp message
        await self.db.whatsapp_queue.insert_one({
            "business_id": business_id,
            "to": phone,
            "message": offer["message"],
            "type": "discount_offer",
            "campaign_id": offer["campaign_id"],
            "queued_at": datetime.utcnow(),
            "sent": False,
        })
    
    async def _queue_popup_discount(self, business_id: str, visitor_id: str, offer: Dict[str, Any]):
        """Queue discount for popup display"""
        await self.db.popup_queue.insert_one({
            "business_id": business_id,
            "visitor_id": visitor_id,
            "offer": offer,
            "shown": False,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=24),
        })
    
    async def _queue_banner_discount(self, business_id: str, visitor_id: str, offer: Dict[str, Any]):
        """Queue discount for banner display"""
        await self.db.banner_queue.insert_one({
            "business_id": business_id,
            "visitor_id": visitor_id,
            "offer": offer,
            "shown": False,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=24),
        })
    
    async def track_conversion(self, business_id: str, discount_code: str):
        """Track when a discount code is used (conversion)"""
        # Mark code as used
        await self.db.discount_codes.update_one(
            {"business_id": business_id, "code": discount_code},
            {"$set": {"used": True, "used_at": datetime.utcnow()}}
        )
        
        # Find the trigger record
        code_doc = await self.db.discount_codes.find_one({
            "business_id": business_id,
            "code": discount_code
        })
        
        if code_doc:
            campaign_id = code_doc.get("campaign_id")
            
            # Update trigger record
            await self.db.discount_triggers.update_one(
                {"business_id": business_id, "campaign_id": campaign_id},
                {"$set": {"converted": True, "converted_at": datetime.utcnow()}}
            )
            
            # Update campaign stats
            await self.db.discount_campaigns.update_one(
                {"_id": campaign_id},
                {"$inc": {"conversion_count": 1}}
            )
            
            logger.info(f"[behavior-trigger] Conversion tracked for code {discount_code}")
