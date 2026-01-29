"""
Daily Notification Scheduler
Runs AI analysis and sends push notifications at scheduled times
"""
import asyncio
import logging
from datetime import datetime, time
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient
from daily_analyzer import DailyCustomerAnalyzer
from notification_service import get_notification_service
import os

logger = logging.getLogger(__name__)


class DailyScheduler:
    """Scheduler for daily customer analysis and notifications"""
    
    def __init__(self, db):
        self.db = db
        self.notification_service = get_notification_service()
        self.analyzer = DailyCustomerAnalyzer(db)
        self.running = False
    
    async def send_daily_notifications(self):
        """Send daily notifications to all users"""
        logger.info("Starting daily notification send...")
        
        # Get all users with push tokens and notifications enabled
        users = await self.db.users.find({
            "push_token": {"$exists": True, "$ne": None},
            "settings.notification_enabled": {"$ne": False}  # Default to enabled
        }).to_list(1000)
        
        logger.info(f"Found {len(users)} users with push notifications enabled")
        
        sent_count = 0
        for user in users:
            try:
                user_id = user["_id"]
                push_token = user.get("push_token")
                
                if not push_token or not push_token.startswith('ExponentPushToken'):
                    continue
                
                # Get user's timezone (default to UTC if not set)
                settings = user.get("settings", {})
                user_timezone = settings.get("timezone", "UTC")
                daily_alert_count = settings.get("daily_alert_count", 5)
                
                # Check if it's time to send notification for this user's timezone
                from datetime import timezone as tz
                import pytz
                
                try:
                    user_tz = pytz.timezone(user_timezone)
                    user_now = datetime.now(user_tz)
                    user_hour = user_now.hour
                    
                    # Check if current hour matches any notification time (with 1-hour window)
                    notification_hours = settings.get("notification_times", [8, 13, 18])
                    should_notify = user_hour in notification_hours
                    
                    if not should_notify:
                        continue  # Skip this user, not their notification time
                        
                except Exception as e:
                    logger.warning(f"Invalid timezone {user_timezone} for user {user_id}, using UTC")
                    user_tz = pytz.UTC
                
                # Run analysis for this user if not already done today
                today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                existing_analysis = await self.db.customer_analysis.find_one({
                    "user_id": user_id,
                    "analysis_date": {"$gte": today}
                })
                
                if not existing_analysis:
                    logger.info(f"Running analysis for user {user_id}")
                    await self.analyzer.analyze_all_customers(user_id)
                
                # Get today's insights
                insights = await self.analyzer.get_todays_insights(user_id, limit=daily_alert_count)
                
                if not insights:
                    logger.info(f"No insights for user {user_id}")
                    continue
                
                # Send notification
                success = await self.notification_service.send_daily_insights_notification(
                    push_token=push_token,
                    insights=insights,
                    count=min(3, len(insights))  # Show top 3 in notification
                )
                
                if success:
                    # Mark insights as notified
                    customer_ids = [i['customer_id'] for i in insights]
                    await self.db.customer_analysis.update_many(
                        {
                            "user_id": user_id,
                            "customer_id": {"$in": customer_ids},
                            "analysis_date": {"$gte": today}
                        },
                        {"$set": {"notification_sent": True}}
                    )
                    sent_count += 1
                    logger.info(f"Sent notification to user {user_id}")
                
            except Exception as e:
                logger.error(f"Error sending notification to user {user.get('_id')}: {e}")
                continue
        
        logger.info(f"Daily notifications complete. Sent to {sent_count}/{len(users)} users")
        return sent_count
    
    
    async def run_scheduler(self, check_interval_minutes: int = 60):
        """
        Run the scheduler in a loop, checking every hour for users who need notifications
        
        Args:
            check_interval_minutes: How often to check (default: 60 minutes)
        """
        self.running = True
        logger.info(f"Scheduler started. Will check for notifications every {check_interval_minutes} minutes")
        logger.info("Notifications will be sent based on each user's local timezone")
        
        while self.running:
            try:
                # Run notification check
                await self.send_daily_notifications()
                
                # Wait for next check
                wait_seconds = check_interval_minutes * 60
                logger.info(f"Next check in {check_interval_minutes} minutes")
                await asyncio.sleep(wait_seconds)
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                # Wait 10 minutes before retrying on error
                await asyncio.sleep(600)
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Scheduler stopped")


# Global scheduler instance
_scheduler = None

async def get_scheduler(db) -> DailyScheduler:
    """Get or create scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = DailyScheduler(db)
    return _scheduler


async def start_daily_scheduler(db, check_interval_minutes: int = 60):
    """
    Start the daily scheduler in the background
    
    Args:
        db: MongoDB database instance
        check_interval_minutes: How often to check for notifications (default: 60 minutes)
    """
    scheduler = await get_scheduler(db)
    
    # Run in background task
    asyncio.create_task(scheduler.run_scheduler(check_interval_minutes))
    logger.info(f"Timezone-aware scheduler started - checking every {check_interval_minutes} minutes")
