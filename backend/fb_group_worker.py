"""
Facebook Group Worker — scheduled API Direct scans for Field Agents users.

Runs every 30 minutes for users with saved Facebook group URLs + keywords.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from apidirect_collector import is_configured, scan_user_facebook_groups

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 1800  # 30 minutes
SCAN_COOLDOWN_HOURS = 6


async def run_fb_group_worker(db) -> None:
    if not is_configured():
        logger.info("[fb_group_worker] APIDIRECT_API_KEY not set — worker idle")
        return

    logger.info("[fb_group_worker] Started. Checking every %ds.", CHECK_INTERVAL_SEC)
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SEC)
        try:
            await _run_due_scans(db)
        except Exception as e:
            logger.exception("[fb_group_worker] loop error: %s", e)


async def _run_due_scans(db) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=SCAN_COOLDOWN_HOURS)

    social_docs = await db.action_mode_social.find({
        "groups": {"$exists": True, "$ne": []},
        "$or": [
            {"keywords": {"$exists": True, "$ne": []}},
        ],
    }).to_list(500)

    if not social_docs:
        return

    ran = 0
    for doc in social_docs:
        uid = doc.get("user_id")
        if not uid:
            continue

        settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
        if not settings.get("enabled"):
            continue

        groups = doc.get("groups") or []
        if not any("facebook.com/group" in (g or "").lower() for g in groups):
            continue

        keywords = doc.get("keywords") or []
        last = doc.get("last_fb_scan_at")
        if last and last > cutoff:
            continue

        biz = await db.users.find_one({"_id": uid}) or {}
        if not keywords and not (biz.get("business_type") or biz.get("industry")):
            continue

        try:
            result = await scan_user_facebook_groups(db, uid, doc, biz)
            if result.get("api_pages") or result.get("alerts"):
                ran += 1
                logger.info("[fb_group_worker] user=%s result=%s", uid, result)
        except Exception as e:
            logger.error("[fb_group_worker] scan failed user=%s: %s", uid, e)

    if ran:
        logger.info("[fb_group_worker] completed %d user scan(s)", ran)
