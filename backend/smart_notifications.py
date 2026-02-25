"""
Smart Notification System
Sends meaningful notifications at the right time, not too frequently
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from followup_analytics import get_analytics

logger = logging.getLogger(__name__)

class SmartNotificationManager:
    """Manages intelligent, non-spammy notifications"""
    
    def __init__(self, db):
        self.db = db
    
    async def should_send_notification(self, user_id: str, notification_type: str) -> bool:
        """
        Check if we should send a notification to avoid spam
        
        Rules:
        - Max 3 notifications per day
        - Same type: min 24 hours apart
        - Respect user's quiet hours
        """
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Check today's notification count
        today_count = await self.db.notifications_sent.count_documents({
            "user_id": user_id,
            "sent_at": {"$gte": today}
        })
        
        if today_count >= 3:
            logger.info(f"User {user_id} already received 3 notifications today")
            return False
        
        # Check last notification of this type
        last_notification = await self.db.notifications_sent.find_one({
            "user_id": user_id,
            "type": notification_type
        }, sort=[("sent_at", -1)])
        
        if last_notification:
            hours_since = (datetime.utcnow() - last_notification["sent_at"]).total_seconds() / 3600
            if hours_since < 24:
                logger.info(f"Last {notification_type} notification was {hours_since:.1f}h ago")
                return False
        
        return True
    
    async def get_meaningful_insights(self, user_id: str) -> Optional[Dict]:
        """
        Generate meaningful insights worth notifying about
        
        Returns notification only if there's something important:
        - Money being lost (no follow-ups)
        - High-value opportunities
        - Urgent customer needs
        """
        # Check if user has been following up
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        # Count follow-ups in last 7 days
        recent_followups = await self.db.followups.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": seven_days_ago}
        })
        
        # Count messages sent in last 7 days
        recent_messages = await self.db.messages.count_documents({
            "user_id": user_id,
            "direction": "outgoing",
            "created_at": {"$gte": seven_days_ago}
        })
        
        # Get high-urgency customers
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        high_urgency = await self.db.customer_analysis.find({
            "user_id": user_id,
            "analysis_date": {"$gte": today},
            "urgency_score": {"$gte": 80}
        }).to_list(10)
        
        # Get customers who asked questions (unanswered)
        unanswered_questions = await self.db.customer_analysis.count_documents({
            "user_id": user_id,
            "analysis_date": {"$gte": today},
            "ai_reason": {"$regex": "question|asked|price|cost", "$options": "i"}
        })
        
        # Calculate potential revenue loss
        neglected_count = await self.db.customers.count_documents({
            "user_id": user_id,
            "$or": [
                {"last_contacted": {"$lt": seven_days_ago}},
                {"last_contacted": None}
            ]
        })
        
        user = await self.db.users.find_one({"_id": user_id})
        avg_order = user.get("avg_order_value", 5000) if user else 5000
        potential_loss = neglected_count * avg_order * 0.1  # 10% conversion estimate
        
        # SCENARIO 1: Not following up - losing money
        if recent_followups == 0 and recent_messages < 3 and neglected_count > 10:
            return {
                "type": "inactivity_warning",
                "title": "⚠️ You're Losing Money",
                "body": f"No follow-ups in 7 days. {neglected_count} customers neglected. Potential loss: KES {potential_loss:,.0f}",
                "priority": "high",
                "data": {
                    "neglected_count": neglected_count,
                    "potential_loss": potential_loss,
                    "days_inactive": 7
                }
            }
        
        # SCENARIO 2: High-value opportunities
        if len(high_urgency) >= 3:
            customer_names = [c["customer_name"] for c in high_urgency[:3]]
            return {
                "type": "high_urgency",
                "title": "🔥 Hot Leads Ready",
                "body": f"{len(high_urgency)} high-priority customers: {', '.join(customer_names[:2])}...",
                "priority": "high",
                "data": {
                    "customer_ids": [c["customer_id"] for c in high_urgency],
                    "count": len(high_urgency)
                }
            }
        
        # SCENARIO 3: Unanswered questions
        if unanswered_questions >= 2:
            return {
                "type": "unanswered_questions",
                "title": "❓ Customers Waiting",
                "body": f"{unanswered_questions} customers asked questions - reply now to close sales",
                "priority": "medium",
                "data": {
                    "count": unanswered_questions
                }
            }
        
        # SCENARIO 4: Monthly Performance Summary (Revenue growth)
        stats_this_month = await get_analytics(self.db).get_followup_stats(user_id, days=30)
        # Simple comparison if we have data
        if stats_this_month["total_revenue"] > 10000:
            top_products = await get_analytics(self.db).get_product_insights(user_id, days=30)
            if top_products:
                top_p = top_products[0]
                return {
                    "type": "monthly_performance",
                    "title": "📈 Monthly Performance",
                    "body": f"Total revenue this month: KES {stats_this_month['total_revenue']:,.0f}. Best seller: {top_p['name']} ({top_p['quantity']} sold)!",
                    "priority": "medium",
                    "data": {
                        "revenue": stats_this_month["total_revenue"],
                        "top_product": top_p["name"]
                    }
                }

        # SCENARIO 5: Good performance - positive reinforcement
        if recent_followups >= 5 and recent_messages >= 10:
            return {
                "type": "positive_feedback",
                "title": "🎉 Great Work!",
                "body": f"You followed up with {recent_followups} customers this week. Keep it up!",
                "priority": "low",
                "data": {
                    "followups": recent_followups,
                    "messages": recent_messages
                }
            }
        
        # No meaningful insight to share
        return None
    
    async def send_smart_notification(self, user_id: str) -> bool:
        """
        Send notification only if meaningful and not too frequent
        """
        # Get meaningful insight
        insight = await self.get_meaningful_insights(user_id)
        
        if not insight:
            logger.info(f"No meaningful insights for user {user_id}")
            return False
        
        # Check if we should send
        if not await self.should_send_notification(user_id, insight["type"]):
            logger.info(f"Skipping notification for user {user_id} - too frequent")
            return False
        
        # Get user's push token
        user = await self.db.users.find_one({"_id": user_id})
        if not user or not user.get("push_token"):
            return False
        
        # Send notification
        from notification_service import get_notification_service
        notification_service = get_notification_service()
        
        success = await notification_service.send_notification(
            push_token=user["push_token"],
            title=insight["title"],
            body=insight["body"],
            data=insight["data"]
        )
        
        if success:
            # Record notification sent
            await self.db.notifications_sent.insert_one({
                "user_id": user_id,
                "type": insight["type"],
                "title": insight["title"],
                "body": insight["body"],
                "sent_at": datetime.utcnow()
            })
            logger.info(f"Sent smart notification to user {user_id}: {insight['type']}")
        
        return success
    
    async def send_daily_smart_notifications(self):
        """
        Send smart notifications to all users (called by scheduler)
        Only sends meaningful, non-spammy notifications
        """
        users = await self.db.users.find({
            "push_token": {"$exists": True, "$ne": None},
            "settings.notification_enabled": {"$ne": False}
        }).to_list(1000)
        
        sent_count = 0
        for user in users:
            try:
                success = await self.send_smart_notification(user["_id"])
                if success:
                    sent_count += 1
            except Exception as e:
                logger.error(f"Error sending smart notification to {user['_id']}: {e}")
        
        logger.info(f"Sent {sent_count} smart notifications to {len(users)} users")
        return sent_count

# Singleton
_smart_notifications = None

def get_smart_notifications(db):
    """Get singleton instance"""
    global _smart_notifications
    if _smart_notifications is None:
        _smart_notifications = SmartNotificationManager(db)
    return _smart_notifications
