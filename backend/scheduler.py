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
from apscheduler.triggers.interval import IntervalTrigger
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


async def _sweep_depth(db, user: dict) -> str:
    """
    Determine sweep depth by plan tier.

    free/trial  → light  : record event + journal only. No AI agent calls.
    starter     → standard: Scout + pipeline + inbox drafts.
    growth/pro  → full   : standard + WhatsApp/Telegram briefing delivery.
    """
    from plan_enforcement import get_active_plan_limits
    user_id = str(user.get("_id", ""))
    try:
        limits = await get_active_plan_limits(db, user_id)
        plan = limits.get("plan_name", "Free Trial").lower()
    except Exception:
        plan = "free trial"

    if any(k in plan for k in ("pro", "premium", "growth", "operator")):
        return "full"
    if any(k in plan for k in ("starter", "standard")):
        return "standard"
    return "light"


async def _sweep_one_user(
    db,
    store,
    doc: dict,
    summary: dict,
) -> None:
    """Sweep a single user. Called concurrently inside zilo_nightly_sweep."""
    from rex.integrations.platform_sweep import run_platform_sweep
    from rex.ranks.events import TrustEvent

    uid = doc.get("user_id")
    bid = doc.get("business_id") or uid
    if not uid:
        return

    try:
        user_doc = await db.users.find_one({"_id": uid}) or {"_id": uid}
        depth = await _sweep_depth(db, user_doc)

        orch = await store.load(uid, business_id=bid)
        if orch is None:
            summary["skipped"] += 1
            return

        if depth == "light":
            event = TrustEvent.background_work()
            orch.event_store.append(event)
            await store.save(uid, business_id=bid, orch=orch)
            summary["completed"] += 1
            logger.info("[zilo-sweep] light uid=%s", uid)
            return

        # Standard + Full: full platform sweep
        report = await run_platform_sweep(db, user_doc, orch, force=True)
        await store.save(uid, business_id=bid, orch=orch)
        summary["completed"] += 1
        logger.info(
            "[zilo-sweep] %s uid=%s staged=%s emails=%s leads=%s",
            depth, uid,
            report.get("staged", 0),
            (report.get("email") or {}).get("fetched", 0),
            report.get("opps_imported", 0),
        )

        # Full tier: deliver WhatsApp morning briefing
        if depth == "full":
            try:
                phone = user_doc.get("phone_number")
                wa_cfg = user_doc.get("whatsapp", {})
                if phone and wa_cfg.get("instance_name"):
                    from rex.api_serializers import serialize_home
                    from whatsapp_service import get_whatsapp_service
                    home = serialize_home(orch)
                    briefing_text = _format_briefing_whatsapp(home)
                    if briefing_text:
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=uid,
                            to_number=phone,
                            message=briefing_text,
                            send_context="zilo_morning_briefing",
                        )
                        logger.info("[zilo-sweep] briefing sent uid=%s", uid)
            except Exception as e:
                logger.warning("[zilo-sweep] briefing delivery failed uid=%s: %s", uid, e)

    except Exception as e:
        logger.error("[zilo-sweep] failed uid=%s: %s", uid, e)
        summary["failed"] += 1
        summary["errors"].append({"uid": uid, "error": str(e)})


async def zilo_nightly_sweep(db: AsyncIOMotorDatabase):
    """
    6am UTC nightly sweep — runs for every active Zilo user regardless of
    whether they opened the app. This is the core of the product promise:
    "Zilo works while you sleep."

    Users are processed in concurrent batches of 10 with a 1-second pause
    between batches to stay within API rate limits at any user count.

    Depth is gated by subscription tier:
      light    (free/trial)  — record BACKGROUND_WORK event only, no AI calls
      standard (starter)     — Scout + pipeline + inbox scan + stage actions
      full     (growth/pro)  — standard + deliver morning briefing via WhatsApp
    """
    import time
    from redis_client import get_redis
    redis_client = await get_redis()
    lock_key = "scheduler:lock:zilo_nightly_sweep"

    if redis_client:
        if not await _acquire_lock(redis_client, lock_key, ttl_seconds=3600):
            logger.info("[zilo-sweep] already running on another instance, skipping")
            return

    run_id = await _log_scheduler_run(db, "zilo_nightly_sweep", "running")
    started_at = time.monotonic()

    summary: dict = {
        "total_users": 0,
        "completed": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "duration_seconds": 0,
    }

    try:
        from rex.persistence.session import ZiloSessionStore
        store = ZiloSessionStore(db)

        session_docs = await db[store._col.name].find(
            {}, {"user_id": 1, "business_id": 1}
        ).to_list(5000)

        # Filter out docs with no user_id up front
        valid_docs = [d for d in session_docs if d.get("user_id")]
        summary["total_users"] = len(valid_docs)
        logger.info("[zilo-sweep] starting — %d users, batch_size=10", len(valid_docs))

        # Process in batches of 10 concurrently
        batch_size = 10
        for i in range(0, len(valid_docs), batch_size):
            batch = valid_docs[i : i + batch_size]
            await asyncio.gather(*[
                _sweep_one_user(db, store, doc, summary)
                for doc in batch
            ])
            if i + batch_size < len(valid_docs):
                await asyncio.sleep(1)  # rate-limit pause between batches

        summary["duration_seconds"] = round(time.monotonic() - started_at, 1)

        logger.info(
            "[zilo-sweep] complete — total=%d completed=%d skipped=%d failed=%d duration=%.1fs",
            summary["total_users"], summary["completed"],
            summary["skipped"], summary["failed"],
            summary["duration_seconds"],
        )
        await _update_scheduler_run(db, run_id, "completed", summary)

        # Write a sweep_log document for the founder-facing sweep history
        await db.zilo_sweep_log.insert_one({
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "run_id": run_id,
            **summary,
            "logged_at": datetime.utcnow(),
        })

    except Exception as e:
        summary["duration_seconds"] = round(time.monotonic() - started_at, 1)
        logger.error("[zilo-sweep] fatal error: %s", e)
        await _update_scheduler_run(db, run_id, "failed", {"error": str(e), **summary})
    finally:
        if redis_client:
            await _release_lock(redis_client, lock_key)


def _format_briefing_whatsapp(home: dict) -> str:
    """
    Format the morning briefing as a terse WhatsApp message in Zilo's voice.
    Returns empty string if there is nothing to report.
    """
    actions = home.get("actions") or []
    staged = [a for a in actions if a.get("state") == "staged"]
    if not staged:
        return ""

    day = home.get("relationship_day", "?")
    lines = [f"Day {day}. Morning briefing.\n"]
    for i, a in enumerate(staged[:3], 1):
        summary = a.get("summary") or a.get("body") or ""
        if summary:
            lines.append(f"{i}. {summary[:120]}")
    if len(staged) > 3:
        lines.append(f"\n+{len(staged) - 3} more staged. Open the app to review.")
    lines.append("\n— Zilo")
    return "\n".join(lines)


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


async def renew_outlook_subscriptions_job(db: AsyncIOMotorDatabase):
    """Pick up and renew Outlook webhook subscriptions nearing expiration."""
    try:
        from redis_client import get_redis
        redis_client = await get_redis()
        if not redis_client:
            return
            
        lock_key = "scheduler:lock:renew_outlook_subscriptions"
        if not await _acquire_lock(redis_client, lock_key, ttl_seconds=800):
            logger.info("[scheduler] renew_outlook_subscriptions_job already running on another instance, skipping")
            return
            
        run_id = await _log_scheduler_run(db, "renew_outlook_subscriptions_job", "running")
        try:
            from outlook_webhook_service import renew_outlook_subscriptions
            res = await renew_outlook_subscriptions(db)
            await _update_scheduler_run(db, run_id, "completed", res)
        except Exception as e:
            logger.error(f"[scheduler] renew_outlook_subscriptions_job failed: {e}")
            await _update_scheduler_run(db, run_id, "failed", {"error": str(e)})
        finally:
            await _release_lock(redis_client, lock_key)
            
    except Exception as e:
        logger.error(f"[scheduler] Fatal error in renew_outlook_subscriptions_job: {e}")


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

    # Outlook webhook subscription renewal every 6 hours
    scheduler.add_job(
        renew_outlook_subscriptions_job,
        CronTrigger(hour="*/6"),
        args=[db],
        id="renew_outlook_subscriptions",
        name="Renew Outlook Subscriptions (every 6 hours)",
        replace_existing=True
    )

    # Zilo nightly sweep — 6am UTC daily
    # Runs platform sweep for every active user whether or not they opened the app.
    # Depth gated by plan: light (free) / standard (starter) / full (growth/pro).
    scheduler.add_job(
        zilo_nightly_sweep,
        CronTrigger(hour=6, minute=0),
        args=[db],
        id="zilo_nightly_sweep",
        name="Zilo Nightly Sweep (6 AM UTC)",
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
    
    # Social DM AI auto-reply poller — every 45s.
    # IG DMs have no Composio push trigger, so we poll for new inbound messages and let the
    # shared autoreply engine respond. max_instances=1 + coalesce prevents overlapping cycles.
    from social_autoreply import run_social_autoreply_poll
    scheduler.add_job(
        run_social_autoreply_poll,
        IntervalTrigger(seconds=45),
        args=[db],
        id="social_dm_autoreply",
        name="Social DM AI Auto-Reply (every 45s)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Comment auto-reply poller — every 90s (Composio FB/IG; no webhook required).
    from social_comment_autoreply import run_comment_autoreply_poll
    scheduler.add_job(
        run_comment_autoreply_poll,
        IntervalTrigger(seconds=90),
        args=[db],
        id="social_comment_autoreply",
        name="Social Comment Auto-Reply (every 90s)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Storefront stock held by abandoned online payments — every 15 min.
    # Without this the count stays down for good and the product eventually
    # reads as out of stock.
    from storefront_routes import release_expired_storefront_reservations
    scheduler.add_job(
        release_expired_storefront_reservations,
        IntervalTrigger(minutes=15),
        args=[db],
        id="storefront_stock_release",
        name="Release Abandoned Storefront Stock (every 15 min)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Shop orders the merchant has not confirmed — every 30 min. The buyer was
    # told the business would confirm shortly, so a sitting order is a promise
    # going unkept.
    from storefront_routes import remind_unconfirmed_storefront_orders
    scheduler.add_job(
        remind_unconfirmed_storefront_orders,
        IntervalTrigger(minutes=30),
        args=[db],
        id="storefront_pending_orders",
        name="Remind Unconfirmed Storefront Orders (every 30 min)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Delegate scheduled runs — every 5 min (time-based automations).
    from delegate.service import run_due_scheduled_delegations
    scheduler.add_job(
        run_due_scheduled_delegations,
        IntervalTrigger(minutes=5),
        args=[db],
        id="delegate_scheduled_runs",
        name="Delegate Scheduled Runs (every 5 min)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started: Digests at 8 AM & 3 PM UTC, Motivation on Monday + 2 random days")


def stop_scheduler():
    """Stop the scheduler"""
    scheduler.shutdown()
    logger.info("Scheduler stopped")
