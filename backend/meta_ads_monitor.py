"""
meta_ads_monitor.py — Background worker that monitors Meta Ads campaign performance
and automatically pauses campaigns that are critically underperforming.

Runs every hour. For each user with META_ADS_ACCESS_TOKEN configured:
  1. Fetches all ACTIVE campaigns and their last-7-day insights
  2. Checks against thresholds: ROAS < 1.0, CTR < 0.8%, or spend > $10 with 0 clicks
  3. Auto-pauses critical campaigns and logs the action in MongoDB
  4. Never pauses a campaign that has been running < 48 hours (learning phase)

Required env vars (per deployment):
  META_ADS_ACCESS_TOKEN — system user token with ads_management + ads_read
  META_ADS_ACCOUNT_ID   — ad account ID (act_XXXXXXXXX)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
_CTR_CRITICAL   = 0.8    # % — below this after meaningful spend → pause
_ROAS_CRITICAL  = 1.0    # below 1.0 → losing money
_SPEND_NO_CLICK = 10.0   # $ — spent this much with 0 clicks → pause
_MIN_SPEND_TO_JUDGE = 5.0  # $ — don't judge campaigns that spent < $5
_MIN_RUN_HOURS  = 48     # hours — don't touch campaigns newer than this


async def _should_pause(campaign: Dict[str, Any], insights: Dict[str, Any]) -> tuple[bool, str]:
    """Return (should_pause, reason) based on campaign insights."""
    spend    = insights.get("spend", 0.0)
    clicks   = insights.get("clicks", 0)
    ctr      = insights.get("ctr", 0.0) * 100   # convert to %
    roas     = insights.get("roas", 0.0)

    # Check minimum spend threshold — not enough data yet
    if spend < _MIN_SPEND_TO_JUDGE:
        return False, ""

    # Check minimum run time — Meta learning phase protection
    created_raw = campaign.get("created_time") or campaign.get("start_time")
    if created_raw:
        try:
            from dateutil import parser as dateutil_parser
            created_dt = dateutil_parser.parse(created_raw)
            age_hours = (datetime.utcnow() - created_dt.replace(tzinfo=None)).total_seconds() / 3600
            if age_hours < _MIN_RUN_HOURS:
                return False, ""
        except Exception:
            pass

    # Critical: spending with zero clicks
    if spend >= _SPEND_NO_CLICK and clicks == 0:
        return True, f"Spent ${spend:.2f} with 0 clicks — ad not delivering. Auto-paused."

    # Critical: ROAS below 1.0 (losing money on tracked purchases)
    if roas > 0 and roas < _ROAS_CRITICAL:
        return True, f"ROAS {roas:.2f}× (below 1.0) — spending more than earning. Auto-paused."

    # Critical: CTR below 0.8% with meaningful spend
    if ctr < _CTR_CRITICAL and spend >= 20.0:
        return True, f"CTR {ctr:.2f}% (below 0.8%) with ${spend:.2f} spend — creative not engaging. Auto-paused."

    return False, ""


async def _log_action(db, user_id: str, campaign_id: str, campaign_name: str, reason: str) -> None:
    """Write an audit log entry to MongoDB."""
    await db.meta_ads_monitor_log.insert_one({
        "user_id":       user_id,
        "campaign_id":   campaign_id,
        "campaign_name": campaign_name,
        "action":        "AUTO_PAUSED",
        "reason":        reason,
        "created_at":    datetime.utcnow(),
    })
    logger.warning(
        "[meta_ads_monitor] AUTO-PAUSED campaign %s (%s) for user %s — %s",
        campaign_id, campaign_name, user_id, reason,
    )


async def run_meta_ads_monitor(db) -> None:
    """Main loop — runs every 60 minutes."""
    logger.info("[meta_ads_monitor] Started. Checking every 60 min.")
    while True:
        await asyncio.sleep(3600)  # 1 hour

        # Only run if Meta Ads is configured at the deployment level
        access_token = os.environ.get("META_ADS_ACCESS_TOKEN", "").strip()
        account_id   = os.environ.get("META_ADS_ACCOUNT_ID", "").strip()
        if not access_token or not account_id:
            continue

        try:
            from meta_ads_service import list_campaigns, get_account_insights, update_campaign_status

            # Fetch active campaigns
            campaigns: List[Dict[str, Any]] = await list_campaigns(status_filter="ACTIVE")
            if not campaigns:
                continue

            logger.info("[meta_ads_monitor] Checking %d active campaigns", len(campaigns))

            # Fetch last-7-day insights for all campaigns in one call
            insights_list: List[Dict[str, Any]] = await get_account_insights(days=7)
            insights_by_id: Dict[str, Dict[str, Any]] = {
                row["campaign_id"]: row for row in insights_list
            }

            for campaign in campaigns:
                cid  = campaign.get("id") or campaign.get("campaign_id")
                name = campaign.get("name", "Unknown")
                if not cid:
                    continue

                insights = insights_by_id.get(cid)
                if not insights:
                    continue

                should_pause, reason = await _should_pause(campaign, insights)
                if not should_pause:
                    continue

                # Execute the pause
                result = await update_campaign_status(cid, "PAUSED")
                if result.get("success"):
                    # Use a placeholder user_id since this is account-level (not per-CRM-user)
                    user_id = os.environ.get("META_ADS_DEFAULT_USER_ID", "system")
                    await _log_action(db, user_id, cid, name, reason)
                else:
                    logger.error(
                        "[meta_ads_monitor] Failed to pause campaign %s: %s",
                        cid, result.get("error"),
                    )

        except Exception as e:
            logger.exception("[meta_ads_monitor] Unexpected error in monitor loop: %s", e)
