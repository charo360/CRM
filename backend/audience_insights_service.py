"""
audience_insights_service.py — Fetch audience demographics from Facebook Graph API
and LinkedIn Organisation API for connected social accounts.

Data fetched:
  Facebook: age/gender breakdown, top countries, top cities, reach by age/gender
  LinkedIn: follower seniority, industry, geo (via Zernio per-account analytics)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE      = "https://graph.facebook.com/v19.0"
ZERNIO_BASE     = "https://zernio.com/api/v1"
ZERNIO_API_KEY  = os.getenv("ZERNIO_API_KEY", "")

_FB_INSIGHT_METRICS = ",".join([
    "page_fans_gender_age",
    "page_fans_country",
    "page_fans_city",
    "page_impressions_by_age_gender_unique",
    "page_fan_adds",
])


# ── helpers ──────────────────────────────────────────────────────────────────

def _top_n(d: Dict[str, int], n: int = 5) -> List[Dict[str, Any]]:
    return [{"label": k, "value": v} for k, v in sorted(d.items(), key=lambda x: -x[1])[:n]]


def _parse_gender_age(raw_values: List[Dict]) -> Dict[str, Any]:
    """Parse page_fans_gender_age into structured age buckets and gender split."""
    buckets: Dict[str, int] = {}
    male_total = female_total = 0
    for item in raw_values:
        val = item.get("value") or {}
        for key, count in val.items():
            gender, age = key.split(".", 1) if "." in key else ("U", key)
            buckets[age] = buckets.get(age, 0) + count
            if gender == "M":
                male_total += count
            elif gender == "F":
                female_total += count
    total = male_total + female_total or 1
    age_sorted = sorted(buckets.items(), key=lambda x: -x[1])
    return {
        "age_buckets": [{"range": k, "count": v} for k, v in age_sorted],
        "gender": {
            "male_pct": round(male_total / total * 100, 1),
            "female_pct": round(female_total / total * 100, 1),
        },
        "top_age_range": age_sorted[0][0] if age_sorted else None,
    }


# ── Facebook ──────────────────────────────────────────────────────────────────

async def get_facebook_audience_insights(page_id: str, page_token: str) -> Dict[str, Any]:
    """Call Facebook Graph API Page Insights and return structured demographics."""
    params = {
        "metric": _FB_INSIGHT_METRICS,
        "period": "lifetime",
        "access_token": page_token,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{GRAPH_BASE}/{page_id}/insights", params=params)
        if resp.status_code != 200:
            logger.warning(f"[AudienceInsights] FB insights {resp.status_code}: {resp.text[:300]}")
            return {"error": f"Graph API {resp.status_code}"}

        data = resp.json().get("data") or []
        result: Dict[str, Any] = {}

        for metric in data:
            name   = metric.get("name", "")
            values = metric.get("values") or []
            if not values:
                continue
            # Use the most recent non-empty value
            latest = next((v for v in reversed(values) if v.get("value")), {})
            val = latest.get("value") or {}

            if name == "page_fans_gender_age":
                result["age_gender"] = _parse_gender_age(values)
            elif name == "page_fans_country":
                result["top_countries"] = _top_n(val, 8)
            elif name == "page_fans_city":
                result["top_cities"] = _top_n(val, 8)
            elif name == "page_impressions_by_age_gender_unique":
                result["reach_by_age_gender"] = _parse_gender_age(values)

        result["source"] = "facebook"
        result["page_id"] = page_id
        result["fetched_at"] = datetime.utcnow().isoformat()
        return result

    except Exception as exc:
        logger.error(f"[AudienceInsights] FB error: {exc}")
        return {"error": str(exc)}


# ── LinkedIn ──────────────────────────────────────────────────────────────────

async def get_linkedin_audience_insights(account_id: str) -> Dict[str, Any]:
    """Fetch LinkedIn follower demographic breakdown via Zernio per-account analytics."""
    if not ZERNIO_API_KEY:
        return {"error": "ZERNIO_API_KEY not configured"}
    headers = {"Authorization": f"Bearer {ZERNIO_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{ZERNIO_BASE}/accounts/{account_id}/followers",
                headers=headers,
            )
            if resp.status_code != 200 or "<html" in resp.text[:50]:
                # Fallback: try analytics endpoint
                resp2 = await client.get(
                    f"{ZERNIO_BASE}/accounts/{account_id}/analytics",
                    headers=headers,
                    params={"metrics": "followerDemographics,followersByGeo,followersByIndustry,followersBySeniority"},
                )
                data = resp2.json() if resp2.status_code == 200 else {}
            else:
                data = resp.json()

        # If fallback endpoint wrapped metrics in 'analytics' or 'data'
        if "analytics" in data and isinstance(data["analytics"], dict):
            data = data["analytics"]
        elif "data" in data and isinstance(data["data"], dict):
            data = data["data"]

        demographics = data.get("demographics") or data.get("followerDemographics") or {}
        geo          = data.get("geo") or data.get("followersByGeo") or {}
        industry     = data.get("industry") or data.get("followersByIndustry") or {}
        seniority    = data.get("seniority") or data.get("followersBySeniority") or {}

        # Default empty dicts for standard keys if missing
        if not isinstance(geo, dict): geo = {}
        if not isinstance(industry, dict): industry = {}
        if not isinstance(seniority, dict): seniority = {}

        return {
            "source": "linkedin",
            "account_id": account_id,
            "top_countries": _top_n(geo, 8) if geo else [],
            "top_industries": _top_n(industry, 8) if industry else [],
            "seniority": _top_n(seniority, 6) if seniority else [],
            "demographics": demographics,
            "fetched_at": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error(f"[AudienceInsights] LinkedIn error: {exc}")
        return {"error": str(exc)}


# ── Main entry point ──────────────────────────────────────────────────────────

async def get_audience_insights_for_user(db, user_id: str) -> Dict[str, Any]:
    """
    Fetch audience insights for all connected platforms for a given user.
    Returns a dict keyed by platform with demographics data.
    Caches results in db.audience_insights_cache for 24 hours.
    """
    # Check cache first
    cached = await db.audience_insights_cache.find_one(
        {"user_id": user_id, "expires_at": {"$gt": datetime.utcnow()}}
    )
    if cached:
        return {k: v for k, v in cached.items() if k not in ("_id", "user_id", "expires_at")}

    results: Dict[str, Any] = {}

    # Facebook — look up stored page token
    fb_conn = await db.meta_connections.find_one({"user_id": user_id, "channel": "messenger"})
    if fb_conn and fb_conn.get("page_access_token") and fb_conn.get("page_id"):
        fb_data = await get_facebook_audience_insights(fb_conn["page_id"], fb_conn["page_access_token"])
        if not fb_data.get("error"):
            results["facebook"] = fb_data

    # LinkedIn — find LinkedIn account via Zernio
    user_doc = await db.users.find_one({"_id": user_id}, {"zernio_profile_id": 1})
    if user_doc and user_doc.get("zernio_profile_id"):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                accs_resp = await client.get(
                    f"{ZERNIO_BASE}/accounts",
                    headers={"Authorization": f"Bearer {ZERNIO_API_KEY}"},
                    params={"profileId": user_doc["zernio_profile_id"]},
                )
            if accs_resp.status_code == 200:
                acc_payload = accs_resp.json()
                accounts = acc_payload.get("accounts") or acc_payload.get("data") or []
                if not isinstance(accounts, list):
                    accounts = []
                for acc in accounts:
                    # Zernio may use 'platform', 'type', 'channelType', 'network', or 'channel'
                    acc_platform = str(
                        acc.get("platform")
                        or acc.get("type")
                        or acc.get("channelType")
                        or acc.get("network")
                        or acc.get("channel")
                        or ""
                    ).strip().lower()
                    if acc_platform == "linkedin":
                        acc_id = str(acc.get("_id") or acc.get("id") or acc.get("accountId") or "")
                        if not acc_id:
                            continue
                        li_data = await get_linkedin_audience_insights(acc_id)
                        if not li_data.get("error"):
                            results["linkedin"] = li_data
                        break
        except Exception as exc:
            logger.warning(f"[AudienceInsights] LinkedIn account lookup failed: {exc}")

    if results:
        expires = datetime.utcnow() + timedelta(hours=24)
        await db.audience_insights_cache.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "expires_at": expires, **results}},
            upsert=True,
        )

    return results
