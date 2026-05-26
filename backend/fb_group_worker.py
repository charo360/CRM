"""
Facebook Group Worker — scheduled ScrapeCreators scans for Field Agents users.

Runs every 30 minutes for users with saved Facebook group URLs + keywords.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from scrapecreators import is_configured, scan_user_facebook_groups, scan_marketplace

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 1800  # 30 minutes
SCAN_COOLDOWN_HOURS = 6


async def run_fb_group_worker(db) -> None:
    if not is_configured():
        logger.info("[fb_group_worker] SCRAPECREATORS_API_KEY not set — worker idle")
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
        "$or": [
            {"groups": {"$exists": True, "$ne": []}},
            {"marketplace_lat": {"$exists": True}},
        ],
    }).to_list(500)

    if not social_docs:
        return

    ran = 0
    for doc in social_docs:
        uid = doc.get("user_id")
        if not uid:
            continue

        groups = doc.get("groups") or []
        keywords = doc.get("keywords") or []
        has_fb_groups = any("facebook.com/groups" in (g or "").lower() for g in groups)
        has_marketplace = doc.get("marketplace_lat") is not None
        has_keywords = bool(keywords)

        if not has_fb_groups and not has_marketplace:
            continue

        last = doc.get("last_sc_scan_at")
        if last and last > cutoff:
            continue

        biz = await db.users.find_one({"_id": uid}) or {}
        if not has_keywords and not (biz.get("business_type") or biz.get("industry")):
            continue

        try:
            groups_result = {"alerts": 0, "credits": 0}
            market_result = {"alerts": 0, "credits": 0}

            if has_fb_groups:
                groups_result = await scan_user_facebook_groups(db, uid, doc, biz)

            if has_marketplace:
                market_result = await scan_marketplace(db, uid, doc, biz)

            total = int(groups_result.get("alerts", 0)) + int(market_result.get("alerts", 0))
            if total or groups_result.get("credits") or market_result.get("credits"):
                ran += 1
                logger.info(
                    "[fb_group_worker] user=%s alerts=%d credits=%d",
                    uid, total,
                    int(groups_result.get("credits", 0)) + int(market_result.get("credits", 0)),
                )
        except Exception as e:
            logger.error("[fb_group_worker] scan failed user=%s: %s", uid, e)

    if ran:
        logger.info("[fb_group_worker] completed %d user scan(s)", ran)
