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

async def update_campaign_status(campaign_id: str, status: str) -> Dict[str, Any]:
    """Set campaign status: ACTIVE | PAUSED | DELETED."""
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
