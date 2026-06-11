"""Meta Ads via Composio METAADS toolkit (per-user OAuth)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from composio_service import TOOLKIT_METAADS, execute_action, get_connection_status, is_configured
from social_composio_publish import list_facebook_pages

logger = logging.getLogger(__name__)

ACTION_GET_AD_ACCOUNTS = "METAADS_GET_AD_ACCOUNTS"
ACTION_GET_INSIGHTS = "METAADS_GET_INSIGHTS"
ACTION_GET_OBJECT = "METAADS_GET_OBJECT"
ACTION_UPDATE_CAMPAIGN = "METAADS_UPDATE_CAMPAIGN"
ACTION_CREATE_CAMPAIGN = "METAADS_CREATE_CAMPAIGN"
ACTION_CREATE_AD_SET = "METAADS_CREATE_AD_SET"
ACTION_CREATE_AD = "METAADS_CREATE_AD"
ACTION_CREATE_AD_CREATIVE = "METAADS_CREATE_AD_CREATIVE"


def _extract_data(result: Dict[str, Any]) -> Any:
    if result.get("error"):
        return None
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("data", "response", "result"):
            inner = data.get(key)
            if inner is not None:
                return inner
    return data


def _rows(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ("data", "campaigns", "items"):
            val = raw.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []


def _days_to_preset(days: int) -> str:
    mapping = {1: "today", 3: "last_3d", 7: "last_7d", 14: "last_14d", 30: "last_30d", 90: "last_90d"}
    best = min(mapping.keys(), key=lambda k: abs(k - days))
    return mapping[best]


def _extract_id(result: Dict[str, Any]) -> Optional[str]:
    data = _extract_data(result)
    if isinstance(data, dict):
        for key in ("id", "campaign_id", "adset_id", "ad_id", "creative_id"):
            val = data.get(key)
            if val:
                return str(val)
    if isinstance(data, str) and data.strip():
        return data.strip()
    return None


def _account_numeric(act_id: str) -> str:
    return act_id.replace("act_", "") if act_id.startswith("act_") else act_id


def _end_time_iso(duration_days: int) -> str:
    end = datetime.now(timezone.utc) + timedelta(days=max(1, duration_days))
    return end.strftime("%Y-%m-%dT%H:%M:%S+0000")


def _default_targeting(audience: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    aud = audience if isinstance(audience, dict) else {}
    countries = aud.get("countries") or aud.get("geo_locations", {}).get("countries") or ["US"]
    if isinstance(countries, str):
        countries = [countries]
    return {
        "geo_locations": {"countries": countries},
        "age_min": int(aud.get("age_min") or 18),
        "age_max": int(aud.get("age_max") or 65),
    }


async def _resolve_facebook_page_id(user_id: str) -> Optional[str]:
    pages_res = await list_facebook_pages(user_id)
    if pages_res.get("error"):
        return None
    pages = pages_res.get("pages") or pages_res.get("data") or []
    if pages and isinstance(pages[0], dict):
        return str(pages[0].get("id") or "") or None
    return None


def _normalize_post_id(post_id: str, page_id: Optional[str]) -> str:
    pid = str(post_id or "").strip()
    if "_" in pid or not page_id:
        return pid
    return f"{page_id}_{pid}"


def _whatsapp_digits(number: str) -> str:
    return re.sub(r"\D", "", str(number or ""))


def _parse_conversions(row: Dict[str, Any]) -> int:
    total = 0
    for action in row.get("actions") or []:
        if not isinstance(action, dict):
            continue
        atype = str(action.get("action_type") or "")
        if "purchase" in atype or atype.endswith(".lead"):
            try:
                total += int(float(action.get("value") or 0))
            except (TypeError, ValueError):
                pass
    return total


def _normalize_campaign(campaign: Dict[str, Any], insights: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metrics = insights or {}
    daily_budget = campaign.get("daily_budget")
    daily_dollars = None
    if daily_budget is not None:
        try:
            daily_dollars = round(float(daily_budget) / 100, 2)
        except (TypeError, ValueError):
            daily_dollars = float(daily_budget) if daily_budget else None

    spend = float(metrics.get("spend", 0) or 0)
    purchase_value = 0.0
    for av in metrics.get("action_values") or []:
        if isinstance(av, dict) and "purchase" in str(av.get("action_type") or ""):
            try:
                purchase_value += float(av.get("value") or 0)
            except (TypeError, ValueError):
                pass
    roas = round(purchase_value / spend, 2) if spend > 0 else 0.0

    return {
        "id": str(campaign.get("id") or metrics.get("campaign_id") or ""),
        "name": campaign.get("name") or metrics.get("campaign_name") or "Unknown",
        "status": str(campaign.get("status") or "").lower(),
        "platform": "facebook",
        "objective": campaign.get("objective"),
        "daily_budget": daily_dollars,
        "metrics": {
            "spend": spend,
            "impressions": int(metrics.get("impressions", 0) or 0),
            "reach": int(metrics.get("reach", 0) or 0),
            "clicks": int(metrics.get("clicks", 0) or 0),
            "ctr": float(metrics.get("ctr", 0) or 0),
            "cpc": float(metrics.get("cpc", 0) or 0),
            "cpm": float(metrics.get("cpm", 0) or 0),
            "roas": roas,
            "conversions": _parse_conversions(metrics),
        },
    }


async def is_user_configured(user_id: str) -> bool:
    if not is_configured():
        return False
    status = await get_connection_status(user_id, TOOLKIT_METAADS)
    return bool(status.get("connected"))


async def resolve_ad_account_id(user_id: str, account_id: Optional[str] = None) -> Optional[str]:
    if account_id:
        aid = str(account_id).strip()
        return aid if aid.startswith("act_") else f"act_{aid}"

    result = await execute_action(
        user_id,
        ACTION_GET_AD_ACCOUNTS,
        {"limit": 25, "fields": "id,name,account_id,account_status"},
    )
    rows = _rows(_extract_data(result))
    for row in rows:
        raw = row.get("id") or row.get("account_id")
        if raw:
            s = str(raw).strip()
            return s if s.startswith("act_") else f"act_{s}"
    return None


async def list_ad_accounts(user_id: str) -> Dict[str, Any]:
    if not await is_user_configured(user_id):
        return {"accounts": [], "error": "Meta Ads not connected via Composio. Connect in Integrations."}

    result = await execute_action(
        user_id,
        ACTION_GET_AD_ACCOUNTS,
        {"limit": 50, "fields": "id,name,account_id,currency,account_status"},
    )
    if result.get("error"):
        return {"accounts": [], "error": result["error"]}

    accounts = []
    for row in _rows(_extract_data(result)):
        raw_id = row.get("id") or row.get("account_id")
        if not raw_id:
            continue
        aid = str(raw_id).strip()
        if not aid.startswith("act_"):
            aid = f"act_{aid}"
        accounts.append({
            "id": aid,
            "name": row.get("name") or aid,
            "platform": "facebook",
            "currency": row.get("currency"),
            "status": row.get("account_status"),
        })
    return {"accounts": accounts}


async def _fetch_campaign_objects(user_id: str, act_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """List campaigns on an ad account via METAADS_GET_OBJECT edges."""
    result = await execute_action(
        user_id,
        ACTION_GET_OBJECT,
        {
            "object_id": act_id,
            "fields": ["campaigns{id,name,status,objective,daily_budget,lifetime_budget}"],
        },
    )
    data = _extract_data(result)
    if isinstance(data, dict):
        campaigns = data.get("campaigns")
        if isinstance(campaigns, dict):
            return _rows(campaigns.get("data"))[:limit]
        if isinstance(campaigns, list):
            return campaigns[:limit]
    return []


async def _fetch_campaign_insights(
    user_id: str,
    act_id: str,
    *,
    days: int = 30,
) -> Dict[str, Dict[str, Any]]:
    preset = _days_to_preset(days)
    result = await execute_action(
        user_id,
        ACTION_GET_INSIGHTS,
        {
            "object_id": act_id,
            "level": "campaign",
            "date_preset": preset,
            "fields": [
                "campaign_id", "campaign_name", "spend", "impressions", "clicks",
                "ctr", "cpc", "cpm", "reach", "actions", "action_values",
            ],
        },
    )
    if result.get("error"):
        logger.warning("[meta_ads_composio] insights: %s", result["error"])
        return {}

    by_id: Dict[str, Dict[str, Any]] = {}
    for row in _rows(_extract_data(result)):
        cid = str(row.get("campaign_id") or "")
        if cid:
            by_id[cid] = row
    return by_id


async def list_campaigns_with_metrics(
    user_id: str,
    *,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    days: int = 30,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    if platform and platform.lower() not in ("facebook", "meta", ""):
        return {"campaigns": [], "error": f"Platform '{platform}' not supported"}

    if not await is_user_configured(user_id):
        return {"campaigns": [], "error": "Meta Ads not connected via Composio. Connect in Integrations."}

    act_id = await resolve_ad_account_id(user_id, account_id)
    if not act_id:
        return {"campaigns": [], "error": "No Meta ad account found for this connection."}

    campaigns_raw = await _fetch_campaign_objects(user_id, act_id, limit=100)
    insights_by_id = await _fetch_campaign_insights(user_id, act_id, days=days)

    campaigns: List[Dict[str, Any]] = []
    for c in campaigns_raw:
        cid = str(c.get("id") or "")
        normalized = _normalize_campaign(c, insights_by_id.get(cid))
        if status and normalized["status"] != status.lower():
            continue
        campaigns.append(normalized)

    if not campaigns and insights_by_id:
        for cid, ins in insights_by_id.items():
            normalized = _normalize_campaign({"id": cid, "name": ins.get("campaign_name")}, ins)
            if status and normalized["status"] != status.lower():
                continue
            campaigns.append(normalized)

    return {"campaigns": campaigns}


async def update_campaign_status(
    user_id: str,
    campaign_id: str,
    status: str,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    del platform
    status_up = status.upper()
    if status_up not in ("ACTIVE", "PAUSED", "DELETED"):
        return {"error": f"Invalid status '{status}'"}

    result = await execute_action(
        user_id,
        ACTION_UPDATE_CAMPAIGN,
        {"campaign_id": campaign_id, "status": status_up},
    )
    if result.get("error"):
        return {"error": result["error"]}
    return {"success": True, "campaign_id": campaign_id, "status": status_up}


async def update_campaign_budget_compat(
    user_id: str,
    campaign_id: str,
    *,
    daily_budget: Optional[float] = None,
    lifetime_budget: Optional[float] = None,
    bid_strategy: Optional[str] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    del lifetime_budget, bid_strategy, platform
    if daily_budget is None:
        return {"error": "daily_budget is required"}

    params: Dict[str, Any] = {"campaign_id": campaign_id, "daily_budget": float(daily_budget)}
    result = await execute_action(user_id, ACTION_UPDATE_CAMPAIGN, params)
    if result.get("error"):
        return {"error": result["error"]}
    return {"success": True, "campaign_id": campaign_id, "daily_budget": daily_budget}


async def boost_post(
    user_id: str,
    post_id: str,
    platform: str,
    daily_budget: float,
    duration_days: int,
    objective: Optional[str] = None,
    audience: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create campaign + ad set + creative + ad promoting an existing post (paused)."""
    if not await is_user_configured(user_id):
        return {"error": "Meta Ads not connected via Composio. Connect in Integrations."}

    act_id = await resolve_ad_account_id(user_id)
    if not act_id:
        return {"error": "No Meta ad account connected."}

    page_id = await _resolve_facebook_page_id(user_id)
    object_story_id = _normalize_post_id(post_id, page_id)
    obj = objective or "OUTCOME_ENGAGEMENT"
    targeting = _default_targeting(audience)
    account_num = _account_numeric(act_id)

    camp = await execute_action(
        user_id,
        ACTION_CREATE_CAMPAIGN,
        {
            "account_id": account_num,
            "name": f"Boost {object_story_id[-24:]}",
            "status": "PAUSED",
            "objective": obj,
            "special_ad_categories": [],
            "is_adset_budget_sharing_enabled": True,
        },
    )
    if camp.get("error"):
        return {"error": camp["error"]}
    campaign_id = _extract_id(camp)
    if not campaign_id:
        return {"error": "Campaign created but ID missing — check Meta Ads Manager."}

    adset_params: Dict[str, Any] = {
        "account_id": account_num,
        "campaign_id": campaign_id,
        "name": f"Boost AdSet {object_story_id[-16:]}",
        "status": "PAUSED",
        "targeting": targeting,
        "optimization_goal": "POST_ENGAGEMENT",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "daily_budget": float(daily_budget),
        "end_time": _end_time_iso(duration_days),
    }
    if page_id:
        adset_params["promoted_object"] = {"page_id": page_id}

    adset = await execute_action(user_id, ACTION_CREATE_AD_SET, adset_params)
    if adset.get("error"):
        return {"error": adset["error"], "campaign_id": campaign_id}
    adset_id = _extract_id(adset)
    if not adset_id:
        return {"error": "Ad set created but ID missing.", "campaign_id": campaign_id}

    creative_payload: Dict[str, Any] = {"object_story_id": object_story_id}
    creative = await execute_action(
        user_id,
        ACTION_CREATE_AD_CREATIVE,
        {
            "account_id": act_id,
            "name": f"Boost Creative {object_story_id[-16:]}",
            "creative": creative_payload,
        },
    )
    if creative.get("error"):
        return {"error": creative["error"], "campaign_id": campaign_id, "ad_set_id": adset_id}
    creative_id = _extract_id(creative)
    if not creative_id:
        return {"error": "Creative created but ID missing.", "campaign_id": campaign_id, "ad_set_id": adset_id}

    ad = await execute_action(
        user_id,
        ACTION_CREATE_AD,
        {
            "ad_account_id": act_id,
            "ad_set_id": adset_id,
            "name": f"Boost Ad {object_story_id[-16:]}",
            "status": "PAUSED",
            "creative": {"creative_id": creative_id},
        },
    )
    if ad.get("error"):
        return {
            "error": ad["error"],
            "campaign_id": campaign_id,
            "ad_set_id": adset_id,
            "creative_id": creative_id,
        }
    ad_id = _extract_id(ad)

    return {
        "success": True,
        "status": "PAUSED",
        "campaign_id": campaign_id,
        "ad_set_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad_id,
        "object_story_id": object_story_id,
        "message": (
            "Boost campaign created (paused). Review targeting and budget in Meta Ads Manager, "
            "then activate the campaign when ready."
        ),
        "platform": platform,
        "daily_budget": daily_budget,
        "duration_days": duration_days,
    }


async def create_ctwa_ad(
    user_id: str,
    platform: str,
    whatsapp_number: str,
    creative: Dict[str, Any],
    daily_budget: float,
    duration_days: int,
    audience: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a Click-to-WhatsApp ad (paused) via Composio METAADS."""
    if not await is_user_configured(user_id):
        return {"error": "Meta Ads not connected via Composio. Connect in Integrations."}

    act_id = await resolve_ad_account_id(user_id)
    if not act_id:
        return {"error": "No Meta ad account connected."}

    page_id = await _resolve_facebook_page_id(user_id)
    if not page_id:
        return {"error": "Facebook Page required for Click-to-WhatsApp ads. Connect Facebook first."}

    wa_digits = _whatsapp_digits(whatsapp_number)
    if not wa_digits:
        return {"error": "Valid whatsapp_number is required."}

    cr = creative if isinstance(creative, dict) else {}
    headline = str(cr.get("headline") or cr.get("title") or "Chat with us on WhatsApp")
    body = str(cr.get("message") or cr.get("body") or cr.get("text") or headline)
    image_url = cr.get("image_url") or cr.get("picture") or cr.get("image")

    targeting = _default_targeting(audience)
    account_num = _account_numeric(act_id)

    camp = await execute_action(
        user_id,
        ACTION_CREATE_CAMPAIGN,
        {
            "account_id": account_num,
            "name": f"CTWA {wa_digits[-8:]}",
            "status": "PAUSED",
            "objective": "OUTCOME_ENGAGEMENT",
            "special_ad_categories": [],
            "is_adset_budget_sharing_enabled": True,
        },
    )
    if camp.get("error"):
        return {"error": camp["error"]}
    campaign_id = _extract_id(camp)
    if not campaign_id:
        return {"error": "Campaign created but ID missing."}

    adset = await execute_action(
        user_id,
        ACTION_CREATE_AD_SET,
        {
            "account_id": account_num,
            "campaign_id": campaign_id,
            "name": f"CTWA AdSet {wa_digits[-8:]}",
            "status": "PAUSED",
            "targeting": targeting,
            "optimization_goal": "CONVERSATIONS",
            "billing_event": "IMPRESSIONS",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "daily_budget": float(daily_budget),
            "end_time": _end_time_iso(duration_days),
            "promoted_object": {
                "page_id": page_id,
                "whatsapp_phone_number": wa_digits,
            },
        },
    )
    if adset.get("error"):
        return {"error": adset["error"], "campaign_id": campaign_id}
    adset_id = _extract_id(adset)
    if not adset_id:
        return {"error": "Ad set created but ID missing.", "campaign_id": campaign_id}

    link_data: Dict[str, Any] = {
        "message": body,
        "name": headline,
        "call_to_action": {
            "type": "WHATSAPP_MESSAGE",
            "value": {"app_destination": "WHATSAPP"},
        },
    }
    if image_url:
        link_data["picture"] = str(image_url)

    creative_spec = {
        "object_story_spec": {
            "page_id": page_id,
            "link_data": link_data,
        },
    }
    creative_res = await execute_action(
        user_id,
        ACTION_CREATE_AD_CREATIVE,
        {
            "account_id": act_id,
            "name": f"CTWA Creative {wa_digits[-8:]}",
            "creative": creative_spec,
        },
    )
    if creative_res.get("error"):
        return {"error": creative_res["error"], "campaign_id": campaign_id, "ad_set_id": adset_id}
    creative_id = _extract_id(creative_res)
    if not creative_id:
        return {"error": "Creative created but ID missing.", "campaign_id": campaign_id, "ad_set_id": adset_id}

    ad = await execute_action(
        user_id,
        ACTION_CREATE_AD,
        {
            "ad_account_id": act_id,
            "ad_set_id": adset_id,
            "name": f"CTWA Ad {wa_digits[-8:]}",
            "status": "PAUSED",
            "creative": {"creative_id": creative_id},
        },
    )
    if ad.get("error"):
        return {
            "error": ad["error"],
            "campaign_id": campaign_id,
            "ad_set_id": adset_id,
            "creative_id": creative_id,
        }
    ad_id = _extract_id(ad)

    return {
        "success": True,
        "status": "PAUSED",
        "campaign_id": campaign_id,
        "ad_set_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad_id,
        "whatsapp_number": wa_digits,
        "platform": platform or "facebook",
        "daily_budget": daily_budget,
        "duration_days": duration_days,
        "message": (
            "Click-to-WhatsApp ad created (paused). Verify creative and WhatsApp number in "
            "Meta Ads Manager, then activate when ready."
        ),
    }
