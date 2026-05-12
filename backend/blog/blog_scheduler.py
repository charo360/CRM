"""
Zilo Autoblogging — Daily Post Scheduler.
Runs every day at 9 AM Nairobi time (6 AM UTC) and publishes one post per active client,
respecting per-plan weekly post limits.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from blog.blog_service import ZiloBlogService
from blog.topic_generator import generate_topic_from_chats
from blog.post_generator import generate_blog_post

logger = logging.getLogger(__name__)

WEEKLY_LIMITS: dict = {
    "free": 2,
    "starter": 5,
    "growth": 7,
    "premium": 7,
}

_blog_scheduler: Optional[AsyncIOScheduler] = None


async def _get_posts_this_week(db, client_id: str) -> int:
    week_ago = datetime.utcnow() - timedelta(days=7)
    return await db.posts_log.count_documents(
        {"client_id": client_id, "published_at": {"$gte": week_ago}}
    )


async def publish_daily_posts(db) -> None:
    """
    Main job: runs at 9 AM EAT daily.
    Iterates every active blog, checks weekly quota, generates topic + post, publishes.
    """
    logger.info("[blog-scheduler] Starting daily autoblog publish job")
    blog_service = ZiloBlogService(db)

    active_blogs = await db.blogs.find({"active": True}).to_list(None)
    logger.info(f"[blog-scheduler] Found {len(active_blogs)} active blogs")

    for blog in active_blogs:
        client_id = blog.get("client_id")
        business_name = blog.get("business_name", "Unknown")
        try:
            plan = blog.get("plan", "free")
            posts_this_week = await _get_posts_this_week(db, client_id)
            limit = WEEKLY_LIMITS.get(plan, 2)

            if posts_this_week >= limit:
                logger.info(
                    f"[blog-scheduler] Skipping {business_name} — "
                    f"weekly limit reached ({posts_this_week}/{limit})"
                )
                continue

            topic = await generate_topic_from_chats(db, client_id)
            post = await generate_blog_post(
                business_name=business_name,
                industry=blog.get("industry", "services"),
                location=blog.get("location", "Nairobi"),
                topic=topic,
            )
            result = await blog_service.publish_post(
                wp_slug=blog["wp_slug"],
                title=post["title"],
                content=post["content"],
                excerpt=post["excerpt"],
                keywords=post["keywords"],
            )
            logger.info(
                f"[blog-scheduler] Published for {business_name}: {result['post_url']}"
            )

        except Exception as e:
            logger.error(
                f"[blog-scheduler] Failed to publish for {business_name} ({client_id}): {e}"
            )
            continue

    logger.info("[blog-scheduler] Daily publish job complete")


def start_blog_scheduler(db) -> None:
    """
    Registers the daily publish job with APScheduler and starts it.
    Safe to call multiple times — uses replace_existing=True.
    """
    global _blog_scheduler
    if _blog_scheduler is not None and _blog_scheduler.running:
        logger.info("[blog-scheduler] Already running, skipping start")
        return

    _blog_scheduler = AsyncIOScheduler(timezone="Africa/Nairobi")

    _blog_scheduler.add_job(
        publish_daily_posts,
        CronTrigger(hour=9, minute=0),  # 9 AM Nairobi (EAT = UTC+3 → 6 AM UTC)
        args=[db],
        id="autoblog_daily_publish",
        name="Autoblog Daily Publish (9 AM EAT)",
        replace_existing=True,
    )

    _blog_scheduler.start()
    logger.info("[blog-scheduler] Started — daily posts at 9 AM EAT")


def stop_blog_scheduler() -> None:
    global _blog_scheduler
    if _blog_scheduler and _blog_scheduler.running:
        _blog_scheduler.shutdown()
        logger.info("[blog-scheduler] Stopped")
