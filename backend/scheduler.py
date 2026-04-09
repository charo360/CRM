"""
Task Scheduler for Daily Digests
Sends notifications at 8 AM and 3 PM daily
"""
import logging
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from motor.motor_asyncio import AsyncIOMotorDatabase
from digest_service import get_digest_service
from notification_service import get_notification_service
from motivation_service import get_motivation_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def send_daily_digest(db: AsyncIOMotorDatabase, digest_type: str = "morning"):
    """
    Send daily digest to all active users
    
    Args:
        db: MongoDB database instance
        digest_type: "morning" (8 AM) or "afternoon" (3 PM)
    """
    try:
        logger.info(f"Starting {digest_type} digest delivery...")
        
        # Get all active users with notifications enabled
        users = await db.users.find({
            "notifications_enabled": {"$ne": False}  # Default to enabled if not set
        }).to_list(1000)
        
        digest_service = get_digest_service(db)
        notification_service = get_notification_service()
        
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                user_id = user["_id"]
                business_id = user.get("business_id", user_id)
                
                # Generate digest
                digest = await digest_service.generate_digest(business_id, digest_type)
                
                # Skip if no action items (afternoon only - always send morning)
                if digest_type == "afternoon" and digest["total_action_items"] == 0:
                    logger.info(f"Skipping afternoon digest for {user_id} - no pending items")
                    continue
                
                # Send via WhatsApp
                wa_sent = False
                if user.get("phone_number") and user.get("whatsapp", {}).get("instance_name"):
                    try:
                        from whatsapp_service import get_whatsapp_service
                        ws = get_whatsapp_service(db)
                        message = digest_service.format_whatsapp_message(digest)
                        result = await ws.send_message(
                            user_id=user_id,
                            to_number=user["phone_number"],
                            message=message,
                            send_context="digest"
                        )
                        wa_sent = result.get("status") not in ("error", "limit_reached", None)
                        if wa_sent:
                            logger.info(f"WhatsApp digest sent to {user['phone_number']}")
                    except Exception as e:
                        logger.error(f"WhatsApp delivery failed for {user_id}: {e}")
                
                # Send via Push Notification
                push_sent = False
                if user.get("push_token"):
                    try:
                        notification = digest_service.format_push_notification(digest)
                        push_sent = await notification_service.send_notification(
                            push_token=user["push_token"],
                            title=notification["title"],
                            body=notification["body"],
                            data=notification["data"]
                        )
                        if push_sent:
                            logger.info(f"Push notification sent to {user_id}")
                    except Exception as e:
                        logger.error(f"Push delivery failed for {user_id}: {e}")
                
                if wa_sent or push_sent:
                    sent_count += 1
                else:
                    failed_count += 1
                    logger.warning(f"No delivery method succeeded for {user_id}")
                    
            except Exception as e:
                logger.error(f"Error processing digest for user {user.get('_id')}: {e}")
                failed_count += 1
        
        logger.info(f"{digest_type.capitalize()} digest complete: {sent_count} sent, {failed_count} failed")
        
    except Exception as e:
        logger.error(f"Fatal error in {digest_type} digest job: {e}")


async def send_motivation_message(db: AsyncIOMotorDatabase, is_monday: bool = False):
    """
    Send motivational message to all active users
    
    Args:
        db: MongoDB database instance
        is_monday: If True, sends Monday-specific motivation
    """
    try:
        day_name = "Monday" if is_monday else datetime.utcnow().strftime("%A")
        logger.info(f"Starting {day_name} motivation delivery...")
        
        # Get all active users with notifications enabled
        users = await db.users.find({
            "notifications_enabled": {"$ne": False}
        }).to_list(1000)
        
        motivation_service = get_motivation_service(db)
        
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                user_id = user["_id"]
                
                # Generate motivation message with tracking
                if is_monday:
                    motivation = await motivation_service.get_monday_motivation(user_id)
                else:
                    motivation = await motivation_service.get_midweek_motivation(user_id)
                
                # Send via WhatsApp
                if user.get("phone_number") and user.get("whatsapp", {}).get("instance_name"):
                    try:
                        from whatsapp_service import get_whatsapp_service
                        ws = get_whatsapp_service(db)
                        result = await ws.send_message(
                            user_id=user_id,
                            to_number=user["phone_number"],
                            message=motivation["message"],
                            send_context="motivation"
                        )
                        if result.get("status") not in ("error", "limit_reached", None):
                            sent_count += 1
                            logger.info(f"Motivation sent to {user['phone_number']}")
                        else:
                            failed_count += 1
                    except Exception as e:
                        logger.error(f"WhatsApp delivery failed for {user_id}: {e}")
                        failed_count += 1
                        
            except Exception as e:
                logger.error(f"Error processing motivation for user {user.get('_id')}: {e}")
                failed_count += 1
        
        logger.info(f"{day_name} motivation complete: {sent_count} sent, {failed_count} failed")
        
    except Exception as e:
        logger.error(f"Fatal error in motivation job: {e}")


def start_scheduler(db: AsyncIOMotorDatabase):
    """
    Start the scheduler with daily digest jobs
    
    Args:
        db: MongoDB database instance
    """
    # Morning digest at 8:00 AM (user's local time - assuming UTC+3 for East Africa)
    # For UTC+3, 8 AM local = 5 AM UTC
    scheduler.add_job(
        send_daily_digest,
        CronTrigger(hour=5, minute=0),  # 8 AM EAT = 5 AM UTC
        args=[db, "morning"],
        id="morning_digest",
        name="Morning Digest (8 AM)",
        replace_existing=True
    )
    
    # Afternoon reminder at 3:00 PM (user's local time)
    # For UTC+3, 3 PM local = 12 PM UTC
    scheduler.add_job(
        send_daily_digest,
        CronTrigger(hour=12, minute=0),  # 3 PM EAT = 12 PM UTC
        args=[db, "afternoon"],
        id="afternoon_digest",
        name="Afternoon Reminder (3 PM)",
        replace_existing=True
    )
    
    # Monday motivation at 9:00 AM (after morning digest)
    # For UTC+3, 9 AM local = 6 AM UTC
    scheduler.add_job(
        send_motivation_message,
        CronTrigger(day_of_week='mon', hour=6, minute=0),  # 9 AM EAT Monday
        args=[db, True],  # is_monday=True
        id="monday_motivation",
        name="Monday Motivation (9 AM)",
        replace_existing=True
    )
    
    # Get 2 random weekdays for this week
    from motivation_service import MotivationService
    random_days = MotivationService.get_random_weekdays()
    day_names = ['mon', 'tue', 'wed', 'thu', 'fri']
    
    for idx, day_num in enumerate(random_days):
        day_name = day_names[day_num]
        scheduler.add_job(
            send_motivation_message,
            CronTrigger(day_of_week=day_name, hour=6, minute=0),  # 9 AM EAT
            args=[db, False],  # is_monday=False
            id=f"motivation_{day_name}",
            name=f"{day_name.capitalize()} Motivation (9 AM)",
            replace_existing=True
        )
        logger.info(f"Scheduled motivation for {day_name.upper()}")
    
    # Start the scheduler
    scheduler.start()
    logger.info(f"Scheduler started: Digests at 8 AM & 3 PM, Motivation on Monday + 2 random days")


def stop_scheduler():
    """Stop the scheduler"""
    scheduler.shutdown()
    logger.info("Scheduler stopped")
