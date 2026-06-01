"""
Task Scheduler for Daily Digests
Sends notifications at 8 AM and 3 PM daily
"""
from __future__ import annotations
import logging
import asyncio
import uuid
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from motor.motor_asyncio import AsyncIOMotorDatabase
from digest_service import get_digest_service
from notification_service import get_notification_service
from motivation_service import get_motivation_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _acquire_lock(redis, lock_key: str, ttl_seconds: int = 300) -> bool:
    """Acquire a Redis distributed lock. Returns True if acquired."""
    try:
        result = await redis.set(lock_key, "1", nx=True, ex=ttl_seconds)
        return result is not None
    except Exception:
        return True  # fail-open


async def _release_lock(redis, lock_key: str) -> None:
    try:
        await redis.delete(lock_key)
    except Exception:
        pass


async def _log_scheduler_run(db, job_name: str, status: str, details: dict = None) -> str:
    try:
        run_id = str(uuid.uuid4())
        await db.scheduler_runs.insert_one({
            "_id": run_id,
            "job_name": job_name,
            "status": status,
            "details": details or {},
            "timestamp": datetime.utcnow()
        })
        return run_id
    except Exception as e:
        logger.error(f"[scheduler] failed to write run log: {e}")
        return ""


async def _update_scheduler_run(db, run_id: str, status: str, details: dict = None) -> None:
    if not run_id:
        return
    try:
        await db.scheduler_runs.update_one(
            {"_id": run_id},
            {"$set": {
                "status": status,
                "completed_at": datetime.utcnow(),
                "details": details or {}
            }}
        )
    except Exception as e:
        logger.error(f"[scheduler] failed to update run log: {e}")


async def send_daily_digest(db: AsyncIOMotorDatabase, digest_type: str = "morning"):
    """
    Send daily digest to all active users
    
    Args:
        db: MongoDB database instance
        digest_type: "morning" (8 AM) or "afternoon" (3 PM)
    """
    from redis_client import get_redis
    redis_client = await get_redis()
    job_name = f"send_daily_digest_{digest_type}"
    
    if redis_client:
        lock_key = f"scheduler:lock:{job_name}"
        if not await _acquire_lock(redis_client, lock_key, ttl_seconds=1700):
            logger.info(f"[scheduler] {job_name} already running on another instance, skipping")
            return
            
    run_id = await _log_scheduler_run(db, job_name, "running")
    sent_count = 0
    failed_count = 0
    
    try:
        logger.info(f"Starting {digest_type} digest delivery...")
        
        # Get all active users with notifications enabled
        users = await db.users.find({
            "notifications_enabled": {"$ne": False}  # Default to enabled if not set
        }).to_list(1000)
        
        digest_service = get_digest_service(db)
        notification_service = get_notification_service()
        
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
        await _update_scheduler_run(db, run_id, "completed", {"sent": sent_count, "failed": failed_count})
        
    except Exception as e:
        logger.error(f"Fatal error in {digest_type} digest job: {e}")
        await _update_scheduler_run(db, run_id, "failed", {"error": str(e)})
    finally:
        if redis_client:
            await _release_lock(redis_client, lock_key)


async def send_motivation_message(db: AsyncIOMotorDatabase, is_monday: bool = False):
    """
    Send motivational message to all active users
    
    Args:
        db: MongoDB database instance
        is_monday: If True, sends Monday-specific motivation
    """
    from redis_client import get_redis
    redis_client = await get_redis()
    day_name = "Monday" if is_monday else datetime.utcnow().strftime("%A")
    job_name = f"send_motivation_message_{day_name.lower()}"
    
    if redis_client:
        lock_key = f"scheduler:lock:{job_name}"
        if not await _acquire_lock(redis_client, lock_key, ttl_seconds=1700):
            logger.info(f"[scheduler] {job_name} already running on another instance, skipping")
            return
            
    run_id = await _log_scheduler_run(db, job_name, "running")
    sent_count = 0
    failed_count = 0
    
    try:
        logger.info(f"Starting {day_name} motivation delivery...")
        
        # Get all active users with notifications enabled
        users = await db.users.find({
            "notifications_enabled": {"$ne": False}
        }).to_list(1000)
        
        motivation_service = get_motivation_service(db)
        
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
        await _update_scheduler_run(db, run_id, "completed", {"sent": sent_count, "failed": failed_count})
        
    except Exception as e:
        logger.error(f"Fatal error in motivation job: {e}")
        await _update_scheduler_run(db, run_id, "failed", {"error": str(e)})
    finally:
        if redis_client:
            await _release_lock(redis_client, lock_key)


async def retry_dlq_job(db: AsyncIOMotorDatabase):
    """Pick up and retry unresolved DLQ jobs."""
    try:
        from redis_client import get_redis
        redis_client = await get_redis()
        if not redis_client:
            return
            
        lock_key = "scheduler:lock:retry_dlq_job"
        if not await _acquire_lock(redis_client, lock_key, ttl_seconds=800):
            logger.info("[scheduler] retry_dlq_job already running on another instance, skipping")
            return
            
        run_id = await _log_scheduler_run(db, "retry_dlq_job", "running")
        requeued_count = 0
        try:
            from rex.integrations.dead_letter import retry_dead_letter_jobs
            from redis_client import QUEUE_BROADCAST, QUEUE_RECEIPT
            r1 = await retry_dead_letter_jobs(db, redis_client, QUEUE_BROADCAST, limit=20)
            r2 = await retry_dead_letter_jobs(db, redis_client, QUEUE_RECEIPT, limit=20)
            requeued_count = r1 + r2
            await _update_scheduler_run(db, run_id, "completed", {"requeued": requeued_count})
        except Exception as e:
            logger.error(f"[scheduler] retry_dlq_job failed: {e}")
            await _update_scheduler_run(db, run_id, "failed", {"error": str(e)})
        finally:
            await _release_lock(redis_client, lock_key)
            
    except Exception as e:
        logger.error(f"[scheduler] Fatal error in retry_dlq_job: {e}")


def start_scheduler(db: AsyncIOMotorDatabase):
    """
    Start the scheduler with daily digest jobs
    
    Args:
        db: MongoDB database instance
    """
    # Morning digest at 8:00 AM UTC
    scheduler.add_job(
        send_daily_digest,
        CronTrigger(hour=8, minute=0),
        args=[db, "morning"],
        id="morning_digest",
        name="Morning Digest (8 AM UTC)",
        replace_existing=True
    )

    # Afternoon reminder at 3:00 PM UTC
    scheduler.add_job(
        send_daily_digest,
        CronTrigger(hour=15, minute=0),
        args=[db, "afternoon"],
        id="afternoon_digest",
        name="Afternoon Reminder (3 PM UTC)",
        replace_existing=True
    )

    # Monday motivation at 9:00 AM UTC
    scheduler.add_job(
        send_motivation_message,
        CronTrigger(day_of_week='mon', hour=9, minute=0),
        args=[db, True],  # is_monday=True
        id="monday_motivation",
        name="Monday Motivation (9 AM)",
        replace_existing=True
    )
    
    # DLQ retry job every 15 minutes
    scheduler.add_job(
        retry_dlq_job,
        CronTrigger(minute="*/15"),
        args=[db],
        id="retry_dlq_job",
        name="Retry DLQ Jobs (every 15 min)",
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
            CronTrigger(day_of_week=day_name, hour=9, minute=0),
            args=[db, False],  # is_monday=False
            id=f"motivation_{day_name}",
            name=f"{day_name.capitalize()} Motivation (9 AM)",
            replace_existing=True
        )
        logger.info(f"Scheduled motivation for {day_name.upper()}")
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started: Digests at 8 AM & 3 PM UTC, Motivation on Monday + 2 random days")


def stop_scheduler():
    """Stop the scheduler"""
    scheduler.shutdown()
    logger.info("Scheduler stopped")
