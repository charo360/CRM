"""
ad_health_monitor.py — Intelligent ad performance monitor backed by Zernio Ads API.

Runs every 30 minutes per business:
  1. Fetches all live campaigns + metrics from Zernio
  2. Scores each campaign 0–100 (CTR, CPC, ROAS, spend efficiency)
  3. Applies per-user alert rules (stored in MongoDB `ad_alert_rules`)
  4. Auto-pauses campaigns that trigger a kill rule
  5. Sends WhatsApp alert to business owner
  6. Snapshots health scores in `ad_health_snapshots` for trend tracking

Health zones:  75–100 = Healthy (green)  |  45–74 = Warning (amber)  |  0–44 = Critical (red)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Default thresholds (overridden per-user via ad_alert_rules) ───────────────
_MIN_SPEND_TO_JUDGE      = 3.0    # $ — don't judge a campaign that spent less
_MIN_IMPRESSIONS_TO_JUDGE = 300   # impressions — need enough eyeballs
_MIN_CAMPAIGN_AGE_HOURS  = 24     # hours — respect learning phase
_CHECK_INTERVAL_SECONDS  = 1800   # 30 minutes


# ── Scoring engine ────────────────────────────────────────────────────────────

def score_campaign(metrics: Dict[str, Any], spend_target: float = 0.0) -> Tuple[int, List[str], str]:
    """
    Return (score 0-100, issues list, zone).
    zone is one of: 'healthy', 'warning', 'critical', 'insufficient_data'
    """
    spend       = float(metrics.get("spend", 0) or 0)
    impressions = int(metrics.get("impressions", 0) or 0)
    clicks      = int(metrics.get("clicks", 0) or 0)
    ctr         = float(metrics.get("ctr", 0) or 0)   # already as %
    cpc         = float(metrics.get("cpc", 0) or 0)
    roas        = float(metrics.get("roas", 0) or 0)
    conversions = int(metrics.get("conversions", 0) or 0)

    # Not enough data to judge
    if spend < _MIN_SPEND_TO_JUDGE and impressions < _MIN_IMPRESSIONS_TO_JUDGE:
        return 65, ["Insufficient data — campaign too new or spend too low to evaluate"], "insufficient_data"

    score  = 100
    issues: List[str] = []
    wins:   List[str] = []

    # ── ROAS (highest weight — directly measures ROI) ──────────────────────
    if roas > 0:
        if roas < 1.0:
            score -= 45
            issues.append(f"ROAS {roas:.2f}× — spending more than earning (critical)")
        elif roas < 1.5:
            score -= 22
            issues.append(f"ROAS {roas:.2f}× — barely breaking even")
        elif roas < 2.0:
            score -= 8
            issues.append(f"ROAS {roas:.2f}× — below target (aim for 2×+)")
        elif roas >= 4.0:
            score += 10
            wins.append(f"Excellent ROAS {roas:.2f}×")
        elif roas >= 2.5:
            score += 5
            wins.append(f"Good ROAS {roas:.2f}×")

    # ── CTR (creative quality signal) ─────────────────────────────────────
    if impressions >= _MIN_IMPRESSIONS_TO_JUDGE:
        if clicks == 0 and spend >= 5.0:
            score -= 45
            issues.append(f"Zero clicks with ${spend:.2f} spent — creative not resonating at all")
        elif ctr < 0.3:
            score -= 35
            issues.append(f"CTR {ctr:.2f}% — very poor (industry avg ~1%)")
        elif ctr < 0.8:
            score -= 20
            issues.append(f"CTR {ctr:.2f}% — below average (aim for >1%)")
        elif ctr < 1.5:
            score -= 8
            issues.append(f"CTR {ctr:.2f}% — average; room to improve creative")
        elif ctr >= 3.0:
            score += 10
            wins.append(f"Strong CTR {ctr:.2f}%")
        elif ctr >= 2.0:
            score += 5
            wins.append(f"Good CTR {ctr:.2f}%")

    # ── CPC (cost efficiency) ──────────────────────────────────────────────
    if clicks >= 5 and cpc > 0:
        target = spend_target if spend_target > 0 else 2.0
        if cpc > target * 4:
            score -= 20
            issues.append(f"CPC ${cpc:.2f} — very expensive clicks")
        elif cpc > target * 2:
            score -= 10
            issues.append(f"CPC ${cpc:.2f} — above-average cost per click")
        elif cpc < target * 0.5 and cpc > 0:
            score += 5
            wins.append(f"Efficient CPC ${cpc:.2f}")

    # ── Zero conversions with meaningful spend ─────────────────────────────
    if conversions == 0 and spend >= 20.0 and roas == 0:
        score -= 10
        issues.append(f"No conversions tracked with ${spend:.2f} spent — check pixel/tracking")

    score = max(0, min(100, score))

    if score >= 75:
        zone = "healthy"
    elif score >= 45:
        zone = "warning"
    else:
        zone = "critical"

    return score, issues + (["✓ " + w for w in wins] if wins else []), zone


def _campaign_age_ok(campaign: Dict[str, Any]) -> bool:
    """Return True if campaign is old enough to be judged (past learning phase)."""
    for key in ("created_time", "start_time", "created_at", "startedAt"):
        raw = campaign.get(key)
        if not raw:
            continue
        try:
            if isinstance(raw, datetime):
                created = raw
            else:
                from dateutil import parser as dp
                created = dp.parse(str(raw)).replace(tzinfo=None)
            age_hours = (datetime.utcnow() - created).total_seconds() / 3600
            return age_hours >= _MIN_CAMPAIGN_AGE_HOURS
        except Exception:
            continue
    return True  # If we can't determine age, assume it's old enough


# ── Alert rule evaluation ─────────────────────────────────────────────────────

def _matches_rule(rule: Dict[str, Any], metrics: Dict[str, Any], health_score: int) -> bool:
    """Check if a single alert rule fires for these metrics."""
    condition = rule.get("condition", "health_score")
    operator  = rule.get("operator", "lt")
    value     = float(rule.get("value", 0))
    min_spend = float(rule.get("min_spend", 0))
    min_impr  = int(rule.get("min_impressions", 0))

    spend       = float(metrics.get("spend", 0) or 0)
    impressions = int(metrics.get("impressions", 0) or 0)

    # Guard thresholds
    if spend < min_spend or impressions < min_impr:
        return False

    metric_val: float
    if condition == "health_score":
        metric_val = float(health_score)
    elif condition == "ctr":
        metric_val = float(metrics.get("ctr", 0) or 0)
    elif condition == "roas":
        metric_val = float(metrics.get("roas", 0) or 0)
    elif condition == "cpc":
        metric_val = float(metrics.get("cpc", 0) or 0)
    elif condition == "cpm":
        metric_val = float(metrics.get("cpm", 0) or 0)
    elif condition == "spend":
        metric_val = spend
    elif condition == "clicks":
        metric_val = float(metrics.get("clicks", 0) or 0)
    else:
        return False

    if operator == "lt":
        return metric_val < value
    elif operator == "gt":
        return metric_val > value
    elif operator == "lte":
        return metric_val <= value
    elif operator == "gte":
        return metric_val >= value
    elif operator == "eq":
        return abs(metric_val - value) < 0.0001
    return False


DEFAULT_RULES = [
    {
        "name": "Kill switch — losing money",
        "condition": "roas",
        "operator": "lt",
        "value": 1.0,
        "min_spend": 10.0,
        "min_impressions": 0,
        "action": "auto_pause",
        "notify_whatsapp": True,
        "enabled": True,
        "is_default": True,
    },
    {
        "name": "Dead creative — zero clicks",
        "condition": "ctr",
        "operator": "lt",
        "value": 0.01,
        "min_spend": 5.0,
        "min_impressions": 500,
        "action": "auto_pause",
        "notify_whatsapp": True,
        "enabled": True,
        "is_default": True,
    },
    {
        "name": "Poor CTR warning",
        "condition": "ctr",
        "operator": "lt",
        "value": 0.5,
        "min_spend": 3.0,
        "min_impressions": 1000,
        "action": "alert_only",
        "notify_whatsapp": True,
        "enabled": True,
        "is_default": True,
    },
    {
        "name": "Critical health score",
        "condition": "health_score",
        "operator": "lt",
        "value": 40,
        "min_spend": 5.0,
        "min_impressions": 300,
        "action": "auto_pause",
        "notify_whatsapp": True,
        "enabled": True,
        "is_default": True,
    },
]


async def ensure_default_rules(db, user_id: str) -> None:
    """Create default alert rules for a user if they don't have any yet."""
    count = await db.ad_alert_rules.count_documents({"user_id": user_id})
    if count > 0:
        return
    now = datetime.utcnow()
    docs = [{"user_id": user_id, "created_at": now, **r} for r in DEFAULT_RULES]
    await db.ad_alert_rules.insert_many(docs)
    logger.info("[ad_health_monitor] Created %d default alert rules for user %s", len(docs), user_id)


# ── WhatsApp notification ─────────────────────────────────────────────────────

async def _notify_owner(db, user_id: str, message: str) -> None:
    """Send a WhatsApp message to the business owner's own number."""
    try:
        user = await db.users.find_one({"_id": user_id})
        if not user:
            return
        phone = (
            user.get("phone_number")
            or user.get("owner_phone")
            or user.get("phone")
            or ""
        ).strip()
        if not phone:
            return

        from whatsapp_service import get_whatsapp_service
        wa = get_whatsapp_service()
        if wa:
            await wa.send_message(phone, message)
            logger.info("[ad_health_monitor] Notified owner %s via WhatsApp", user_id)
    except Exception as e:
        logger.warning("[ad_health_monitor] WhatsApp notify failed for user %s: %s", user_id, e)


# ── Core monitor logic ────────────────────────────────────────────────────────

async def _check_campaigns_for_user(db, user_id: str, campaigns: List[Dict[str, Any]]) -> None:
    """Run health check for one user's campaigns (campaigns pre-fetched globally)."""
    from meta_ads_service import update_campaign_status

    if not campaigns:
        return

    rules = await db.ad_alert_rules.find({"user_id": user_id, "enabled": True}).to_list(100)
    now = datetime.utcnow()
    alerts_to_send: List[str] = []

    for campaign in campaigns:
        cid  = str(campaign.get("id") or campaign.get("campaignId") or "")
        name = campaign.get("name") or campaign.get("campaignName") or "Unknown campaign"
        status = str(campaign.get("status") or "").lower()

        if not cid or status not in ("active", "running", "enabled"):
            continue

        if not _campaign_age_ok(campaign):
            continue

        metrics = campaign.get("metrics") or campaign.get("insights") or campaign
        health_score, issues, zone = score_campaign(metrics)

        # Store health snapshot
        await db.ad_health_snapshots.insert_one({
            "user_id":      user_id,
            "campaign_id":  cid,
            "campaign_name": name,
            "platform":     campaign.get("platform"),
            "health_score": health_score,
            "zone":         zone,
            "metrics":      {
                "spend":       float(metrics.get("spend", 0) or 0),
                "impressions": int(metrics.get("impressions", 0) or 0),
                "clicks":      int(metrics.get("clicks", 0) or 0),
                "ctr":         float(metrics.get("ctr", 0) or 0),
                "cpc":         float(metrics.get("cpc", 0) or 0),
                "roas":        float(metrics.get("roas", 0) or 0),
                "conversions": int(metrics.get("conversions", 0) or 0),
            },
            "issues":    issues,
            "checked_at": now,
        })

        # Check user rules
        for rule in rules:
            if not _matches_rule(rule, metrics, health_score):
                continue

            action = rule.get("action", "alert_only")
            rule_name = rule.get("name", "Alert rule")

            # Check cooldown: don't fire same rule on same campaign more than once per 2 hours
            recent = await db.ad_alert_history.find_one({
                "user_id":     user_id,
                "campaign_id": cid,
                "rule_name":   rule_name,
                "fired_at":    {"$gte": now - timedelta(hours=2)},
            })
            if recent:
                continue

            await db.ad_alert_history.insert_one({
                "user_id":       user_id,
                "campaign_id":   cid,
                "campaign_name": name,
                "rule_name":     rule_name,
                "action":        action,
                "health_score":  health_score,
                "zone":          zone,
                "metrics": {
                    "spend":  float(metrics.get("spend", 0) or 0),
                    "ctr":    float(metrics.get("ctr", 0) or 0),
                    "roas":   float(metrics.get("roas", 0) or 0),
                },
                "fired_at": now,
            })

            if action == "auto_pause":
                pause_result = await update_campaign_status(
                    cid, "paused", campaign.get("platform"), user_id=user_id,
                )
                if not pause_result.get("error"):
                    msg = (
                        f"🛑 *Ad Auto-Paused*\n"
                        f"Campaign: {name}\n"
                        f"Rule: {rule_name}\n"
                        f"Health score: {health_score}/100 ({zone.upper()})\n"
                        f"Action: Paused to protect your budget.\n"
                        f"Review in the CRM → Meta Ads → Reporting tab."
                    )
                    alerts_to_send.append(msg)
                    logger.warning(
                        "[ad_health_monitor] AUTO-PAUSED '%s' (%s) for user %s — rule: %s",
                        name, cid, user_id, rule_name,
                    )
                else:
                    logger.error(
                        "[ad_health_monitor] Failed to pause '%s': %s", cid, pause_result.get("error")
                    )
            elif rule.get("notify_whatsapp"):
                alerts_to_send.append(
                    f"⚠️ *Ad Alert — {zone.upper()}*\n"
                    f"Campaign: {name}\n"
                    f"Rule: {rule_name}\n"
                    f"Health score: {health_score}/100\n"
                    f"Review in CRM → Meta Ads → Reporting."
                )

    # Send all alerts in one batch (deduplicated)
    if alerts_to_send:
        combined = "\n\n".join(alerts_to_send)
        await _notify_owner(db, user_id, combined)


async def check_all_users(db) -> None:
    """Run a single health-check pass across all users who have ad alert rules."""
    from meta_ads_service import list_campaigns_with_metrics

    try:
        users = await db.users.find(
            {"is_active": {"$ne": False}},
            {"_id": 1, "business_id": 1},
        ).to_list(500)

        for user in users:
            uid = str(user["_id"])
            business_id = str(user.get("business_id") or uid)
            try:
                await ensure_default_rules(db, uid)
                campaigns_result = await list_campaigns_with_metrics(days=7, user_id=business_id)
                if campaigns_result.get("error") and not campaigns_result.get("campaigns"):
                    continue
                campaigns: List[Dict[str, Any]] = (
                    campaigns_result.get("campaigns")
                    or campaigns_result.get("data")
                    or []
                )
                if not campaigns:
                    continue
                await _check_campaigns_for_user(db, uid, campaigns)
            except Exception as e:
                logger.error("[ad_health_monitor] Error checking user %s: %s", uid, e)
    except Exception as e:
        logger.exception("[ad_health_monitor] check_all_users error: %s", e)


async def run_ad_health_monitor(db) -> None:
    """Main background loop — runs every 30 minutes."""
    logger.info("[ad_health_monitor] Started. Checking every %d min.", _CHECK_INTERVAL_SECONDS // 60)
    # Delay first run by 2 minutes to let the server settle
    await asyncio.sleep(120)
    while True:
        try:
            await check_all_users(db)
        except Exception as e:
            logger.exception("[ad_health_monitor] Unexpected loop error: %s", e)
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
