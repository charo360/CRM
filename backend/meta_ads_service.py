"""
meta_ads_service.py — Meta Marketing API (Ads) integration.

Provides helpers to:
  - List campaigns in an ad account
  - Fetch campaign-level insights (spend, impressions, clicks, CTR, CPC, ROAS)
  - Update campaign status (ACTIVE / PAUSED / DELETED)
  - Update campaign daily budget

Required env vars:
  META_ADS_ACCESS_TOKEN — system user or page access token with ads_management + ads_read
  META_ADS_ACCOUNT_ID   — ad account ID, with or without "act_" prefix (e.g. act_123456789)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v19.0"
GRAPH_BASE    = f"https://graph.facebook.com/{GRAPH_VERSION}"

META_ADS_ACCESS_TOKEN: str = os.environ.get("META_ADS_ACCESS_TOKEN", "").strip()
_raw_account_id: str       = os.environ.get("META_ADS_ACCOUNT_ID", "").strip()
META_ADS_ACCOUNT_ID: str   = (
    _raw_account_id if _raw_account_id.startswith("act_") else f"act_{_raw_account_id}"
) if _raw_account_id else ""

_CAMPAIGN_FIELDS = (
    "id,name,status,objective,daily_budget,lifetime_budget,"
    "start_time,stop_time,created_time,updated_time"
)

_INSIGHT_FIELDS = (
    "campaign_id,campaign_name,spend,impressions,clicks,"
    "ctr,cpc,cpm,reach,actions,action_values,date_start,date_stop"
)


def _token_params() -> Dict[str, str]:
    return {"access_token": META_ADS_ACCESS_TOKEN}


def _is_configured() -> bool:
    return bool(META_ADS_ACCESS_TOKEN and META_ADS_ACCOUNT_ID)


# ── Campaign listing ──────────────────────────────────────────────────────────

async def list_campaigns(
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return campaigns in the ad account.

    status_filter: ACTIVE | PAUSED | ARCHIVED | DELETED | ALL (default ALL)
    """
    if not _is_configured():
        return []

    params: Dict[str, Any] = {
        **_token_params(),
        "fields": _CAMPAIGN_FIELDS,
        "limit": limit,
    }
    if status_filter and status_filter.upper() != "ALL":
        params["effective_status"] = f'["{status_filter.upper()}"]'

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{GRAPH_BASE}/{META_ADS_ACCOUNT_ID}/campaigns",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data") or []
    except Exception as e:
        logger.error("[meta_ads] list_campaigns error: %s", e)
        return []


# ── Campaign insights ─────────────────────────────────────────────────────────

async def get_campaign_insights(
    campaign_id: str,
    days: int = 7,
) -> Optional[Dict[str, Any]]:
    """Fetch spend / clicks / impressions / ROAS for a single campaign."""
    if not _is_configured():
        return None

    params: Dict[str, Any] = {
        **_token_params(),
        "fields": _INSIGHT_FIELDS,
        "date_preset": _days_to_preset(days),
        "level": "campaign",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{GRAPH_BASE}/{campaign_id}/insights",
                params=params,
            )
            resp.raise_for_status()
            rows = resp.json().get("data") or []
            if not rows:
                return None
            row = rows[0]
            # Parse purchase ROAS from action_values
            purchase_value = 0.0
            for av in (row.get("action_values") or []):
                if av.get("action_type") == "offsite_conversion.fb_pixel_purchase":
                    purchase_value = float(av.get("value") or 0)
            spend = float(row.get("spend") or 0)
            roas = round(purchase_value / spend, 2) if spend > 0 else 0.0
            return {
                "campaign_id":  row.get("campaign_id"),
                "campaign_name": row.get("campaign_name"),
                "spend":        spend,
                "impressions":  int(row.get("impressions") or 0),
                "clicks":       int(row.get("clicks") or 0),
                "reach":        int(row.get("reach") or 0),
                "ctr":          round(float(row.get("ctr") or 0), 4),
                "cpc":          round(float(row.get("cpc") or 0), 4),
                "cpm":          round(float(row.get("cpm") or 0), 4),
                "roas":         roas,
                "purchase_value": purchase_value,
                "period_days":  days,
                "date_start":   row.get("date_start"),
                "date_stop":    row.get("date_stop"),
            }
    except Exception as e:
        logger.error("[meta_ads] get_campaign_insights %s error: %s", campaign_id, e)
        return None


async def get_account_insights(days: int = 7) -> List[Dict[str, Any]]:
    """Fetch insights for ALL campaigns in the account (one call)."""
    if not _is_configured():
        return []

    params: Dict[str, Any] = {
        **_token_params(),
        "fields": _INSIGHT_FIELDS,
        "date_preset": _days_to_preset(days),
        "level": "campaign",
        "limit": 100,
    }
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(
                f"{GRAPH_BASE}/{META_ADS_ACCOUNT_ID}/insights",
                params=params,
            )
            resp.raise_for_status()
            rows = resp.json().get("data") or []
            results = []
            for row in rows:
                purchase_value = 0.0
                for av in (row.get("action_values") or []):
                    if av.get("action_type") == "offsite_conversion.fb_pixel_purchase":
                        purchase_value = float(av.get("value") or 0)
                spend = float(row.get("spend") or 0)
                roas  = round(purchase_value / spend, 2) if spend > 0 else 0.0
                results.append({
                    "campaign_id":    row.get("campaign_id"),
                    "campaign_name":  row.get("campaign_name"),
                    "spend":          spend,
                    "impressions":    int(row.get("impressions") or 0),
                    "clicks":         int(row.get("clicks") or 0),
                    "reach":          int(row.get("reach") or 0),
                    "ctr":            round(float(row.get("ctr") or 0), 4),
                    "cpc":            round(float(row.get("cpc") or 0), 4),
                    "cpm":            round(float(row.get("cpm") or 0), 4),
                    "roas":           roas,
                    "purchase_value": purchase_value,
                })
            return results
    except Exception as e:
        logger.error("[meta_ads] get_account_insights error: %s", e)
        return []


# ── Campaign mutation ─────────────────────────────────────────────────────────

async def update_campaign_status(
    campaign_id: str,
    status: str,
    platform: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Set campaign status: ACTIVE | PAUSED | DELETED."""
    if user_id:
        from meta_ads_composio_service import is_user_configured, update_campaign_status as composio_status
        if await is_user_configured(user_id):
            return await composio_status(user_id, campaign_id, status, platform)

    del platform
    if not _is_configured():
        return {"error": "META_ADS_ACCESS_TOKEN / META_ADS_ACCOUNT_ID not configured"}

    allowed = {"ACTIVE", "PAUSED", "DELETED"}
    status_up = status.upper()
    if status_up not in allowed:
        return {"error": f"Invalid status '{status}'. Must be one of {allowed}"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{GRAPH_BASE}/{campaign_id}",
                params=_token_params(),
                data={"status": status_up},
            )
            resp.raise_for_status()
            return {"success": True, "campaign_id": campaign_id, "status": status_up}
    except httpx.HTTPStatusError as e:
        logger.error("[meta_ads] update_campaign_status %s: %s", campaign_id, e.response.text[:300])
        return {"error": e.response.text[:300]}
    except Exception as e:
        logger.error("[meta_ads] update_campaign_status %s error: %s", campaign_id, e)
        return {"error": str(e)}


async def update_campaign_budget(
    campaign_id: str,
    daily_budget_cents: int,
) -> Dict[str, Any]:
    """Set the campaign daily budget (value in cents, e.g. $50 = 5000)."""
    if not _is_configured():
        return {"error": "META_ADS_ACCESS_TOKEN / META_ADS_ACCOUNT_ID not configured"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{GRAPH_BASE}/{campaign_id}",
                params=_token_params(),
                data={"daily_budget": str(daily_budget_cents)},
            )
            resp.raise_for_status()
            return {
                "success": True,
                "campaign_id": campaign_id,
                "daily_budget_cents": daily_budget_cents,
                "daily_budget_dollars": round(daily_budget_cents / 100, 2),
            }
    except httpx.HTTPStatusError as e:
        logger.error("[meta_ads] update_campaign_budget %s: %s", campaign_id, e.response.text[:300])
        return {"error": e.response.text[:300]}
    except Exception as e:
        logger.error("[meta_ads] update_campaign_budget error: %s", e)
        return {"error": str(e)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _days_to_preset(days: int) -> str:
    mapping = {
        1: "today", 3: "last_3d", 7: "last_7d",
        14: "last_14d", 30: "last_30d", 90: "last_90d",
    }
    # Find closest preset
    best = min(mapping.keys(), key=lambda k: abs(k - days))
    return mapping[best]


def _parse_conversions(row: Dict[str, Any]) -> int:
    total = 0
    for action in row.get("actions") or []:
        atype = str(action.get("action_type") or "")
        if "purchase" in atype or atype.endswith(".lead"):
            total += int(float(action.get("value") or 0))
    return total


def _normalize_campaign(campaign: Dict[str, Any], insights: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = insights or {}
    daily_budget = campaign.get("daily_budget")
    daily_budget_dollars = None
    if daily_budget is not None:
        try:
            daily_budget_dollars = round(float(daily_budget) / 100, 2)
        except (TypeError, ValueError):
            daily_budget_dollars = None

    return {
        "id": str(campaign.get("id") or ""),
        "name": campaign.get("name") or "Unknown",
        "status": str(campaign.get("status") or "").lower(),
        "platform": "facebook",
        "objective": campaign.get("objective"),
        "daily_budget": daily_budget_dollars,
        "metrics": {
            "spend": float(metrics.get("spend", 0) or 0),
            "impressions": int(metrics.get("impressions", 0) or 0),
            "reach": int(metrics.get("reach", 0) or 0),
            "clicks": int(metrics.get("clicks", 0) or 0),
            "ctr": float(metrics.get("ctr", 0) or 0),
            "cpc": float(metrics.get("cpc", 0) or 0),
            "cpm": float(metrics.get("cpm", 0) or 0),
            "roas": float(metrics.get("roas", 0) or 0),
            "conversions": int(metrics.get("conversions", 0) or 0),
        },
    }


async def list_campaigns_with_metrics(
    *,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    days: int = 30,
    account_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Campaign list with embedded metrics — Composio METAADS first, env token fallback."""
    if user_id:
        from meta_ads_composio_service import is_user_configured, list_campaigns_with_metrics as composio_list
        if await is_user_configured(user_id):
            return await composio_list(
                user_id,
                platform=platform,
                status=status,
                days=days,
                account_id=account_id,
            )

    if platform and platform.lower() not in ("facebook", "meta", ""):
        return {"campaigns": [], "error": f"Platform '{platform}' not supported via Meta Ads API"}

    if not _is_configured():
        return {
            "campaigns": [],
            "error": "Meta Ads not connected. Connect Meta Ads in Integrations or set META_ADS_ACCESS_TOKEN.",
        }

    status_filter = status.upper() if status else None
    raw_campaigns = await list_campaigns(status_filter=status_filter, limit=100)
    insight_rows = await get_account_insights(days=days)
    insights_by_id = {str(r.get("campaign_id") or ""): r for r in insight_rows}

    campaigns: List[Dict[str, Any]] = []
    for campaign in raw_campaigns:
        cid = str(campaign.get("id") or "")
        row = insights_by_id.get(cid)
        insights = None
        if row:
            insights = {
                **row,
                "conversions": _parse_conversions(row),
            }
        normalized = _normalize_campaign(campaign, insights)
        if status and normalized["status"] != status.lower():
            continue
        campaigns.append(normalized)

    return {"campaigns": campaigns}


async def list_ad_accounts(user_id: Optional[str] = None) -> Dict[str, Any]:
    if user_id:
        from meta_ads_composio_service import is_user_configured, list_ad_accounts as composio_accounts
        if await is_user_configured(user_id):
            return await composio_accounts(user_id)

    if not _is_configured():
        return {"accounts": [], "error": "Meta Ads not connected via Composio or env token."}
    return {
        "accounts": [{
            "id": META_ADS_ACCOUNT_ID,
            "name": META_ADS_ACCOUNT_ID,
            "platform": "facebook",
        }],
    }


async def boost_post(
    post_id: str,
    platform: str,
    daily_budget: float,
    duration_days: int,
    objective: Optional[str] = None,
    audience: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    if user_id:
        from meta_ads_composio_service import boost_post as composio_boost, is_user_configured
        if await is_user_configured(user_id):
            return await composio_boost(
                user_id, post_id, platform, daily_budget, duration_days, objective, audience,
            )
    del post_id, platform, daily_budget, duration_days, objective, audience
    return {
        "error": "Post boosting requires Composio Meta Ads connection or Meta Ads Manager.",
    }


async def create_ctwa_ad(
    platform: str,
    whatsapp_number: str,
    creative: Dict[str, Any],
    daily_budget: float,
    duration_days: int,
    audience: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    if user_id:
        from meta_ads_composio_service import create_ctwa_ad as composio_ctwa, is_user_configured
        if await is_user_configured(user_id):
            return await composio_ctwa(
                user_id, platform, whatsapp_number, creative, daily_budget, duration_days, audience,
            )
    del platform, whatsapp_number, creative, daily_budget, duration_days, audience
    return {
        "error": "Click-to-WhatsApp ads require Composio Meta Ads or Meta Ads Manager.",
    }


async def update_campaign_budget_compat(
    campaign_id: str,
    *,
    daily_budget: Optional[float] = None,
    lifetime_budget: Optional[float] = None,
    bid_strategy: Optional[str] = None,
    platform: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    if user_id:
        from meta_ads_composio_service import is_user_configured, update_campaign_budget_compat as composio_budget
        if await is_user_configured(user_id):
            return await composio_budget(
                user_id,
                campaign_id,
                daily_budget=daily_budget,
                lifetime_budget=lifetime_budget,
                bid_strategy=bid_strategy,
                platform=platform,
            )
    del lifetime_budget, bid_strategy, platform
    if daily_budget is None:
        return {"error": "daily_budget is required"}
    cents = int(round(float(daily_budget) * 100))
    return await update_campaign_budget(campaign_id, cents)
