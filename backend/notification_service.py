"""
Push Notification Service
Handles sending push notifications via Expo
"""
import httpx
from typing import List, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class NotificationService:
    """Service for sending push notifications"""
    
    async def send_daily_insights_notification(
        self,
        push_token: str,
        insights: List[Dict],
        count: int = 3
    ) -> bool:
        """
        Send daily insights notification to user
        
        Args:
            push_token: Expo push token
            insights: List of customer analyses (sorted by urgency)
            count: Number of customers to mention in notification
        
        Returns:
            True if sent successfully
        """
        if not push_token or not push_token.startswith('ExponentPushToken'):
            logger.warning(f"Invalid push token: {push_token}")
            return False
        
        if not insights:
            logger.info("No insights to send notification for")
            return False
        
        # Get top N customers
        top_customers = insights[:count]
        
        # Build notification message
        if len(top_customers) == 1:
            customer = top_customers[0]
            title = "📋 Follow-up Needed"
            body = f"{customer['customer_name']} - {customer['ai_reason']}"
        else:
            title = f"📋 {len(top_customers)} Customers Need Attention"
            names = [c['customer_name'] for c in top_customers]
            if len(names) > 2:
                body = f"{names[0]}, {names[1]}, and {len(names)-2} more need follow-up"
            else:
                body = f"{', '.join(names)} need follow-up"
        
        # Send notification
        return await self.send_notification(
            push_token=push_token,
            title=title,
            body=body,
            data={
                "type": "daily_insights",
                "customer_count": len(top_customers),
                "top_customer_id": top_customers[0]['customer_id'] if top_customers else None
            }
        )
    
    async def send_notification(
        self,
        push_token: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        sound: str = "default",
        badge: Optional[int] = None
    ) -> bool:
        """
        Send a push notification via Expo
        
        Args:
            push_token: Expo push token
            title: Notification title
            body: Notification body
            data: Additional data to send
            sound: Notification sound
            badge: Badge count
        
        Returns:
            True if sent successfully
        """
        if not push_token:
            logger.warning("No push token provided")
            return False
        
        message = {
            "to": push_token,
            "title": title,
            "body": body,
            "sound": sound,
            "priority": "high",
        }
        
        if data:
            message["data"] = data
        
        if badge is not None:
            message["badge"] = badge
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    EXPO_PUSH_URL,
                    json=message,
                    headers={"Content-Type": "application/json"}
                )
                
                response.raise_for_status()
                result = response.json()
                
                # Check if notification was accepted
                if 'data' in result and len(result['data']) > 0:
                    ticket = result['data'][0]
                    if ticket.get('status') == 'ok':
                        logger.info(f"Notification sent successfully to {push_token[:20]}...")
                        return True
                    else:
                        logger.error(f"Notification failed: {ticket.get('message')}")
                        return False
                
                logger.warning(f"Unexpected response from Expo: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False
    
    async def send_reminder_notification(
        self,
        push_token: str,
        customer_name: str,
        reminder_type: str,
        reminder_time: datetime
    ) -> bool:
        """
        Send notification for a specific reminder
        
        Args:
            push_token: Expo push token
            customer_name: Name of customer
            reminder_type: Type of reminder (call, whatsapp, etc)
            reminder_time: When the reminder is due
        
        Returns:
            True if sent successfully
        """
        type_icons = {
            'call': '📞',
            'whatsapp': '💬',
            'meeting': '👥',
            'email': '📧'
        }
        
        icon = type_icons.get(reminder_type, '🔔')
        
        # Format time
        now = datetime.utcnow()
        if reminder_time.date() == now.date():
            time_str = "today"
        else:
            time_str = reminder_time.strftime("%b %d")
        
        return await self.send_notification(
            push_token=push_token,
            title=f"{icon} Reminder: {customer_name}",
            body=f"{reminder_type.capitalize()} reminder for {time_str}",
            data={
                "type": "reminder",
                "customer_name": customer_name,
                "reminder_type": reminder_type
            }
        )


# Singleton instance
_notification_service = None

def get_notification_service() -> NotificationService:
    """Get singleton instance of NotificationService"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
