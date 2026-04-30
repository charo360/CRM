"""Zernio Ads API integration — wraps /v1/ads/* endpoints using the existing ZERNIO_API_KEY."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

ZERNIO_BASE = os.environ.get("ZERNIO_API_BASE", "https://zernio.com/api/v1").rstrip("/")
ZERNIO_API_KEY = os.environ.get("ZERNIO_API_KEY", "").strip()

_TIMEOUT = 20.0


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {ZERNIO_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _is_configured() -> bool:
    return bool(ZERNIO_API_KEY)


async def list_ad_accounts() -> Dict[str, Any]:
    """GET /v1/ads/accounts — returns connected ad accounts."""
    if not _is_configured():
        return {"accounts": [], "error": "ZERNIO_API_KEY not configured"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(f"{ZERNIO_BASE}/ads/accounts", headers=_headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio ads/accounts error %s: %s", e.response.status_code, e.response.text[:300])
            return {"accounts": [], "error": f"API error {e.response.status_code}"}
        except Exception as e:
            logger.error("Zernio ads/accounts exception: %s", e)
            return {"accounts": [], "error": str(e)}


async def list_campaigns(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    days: int = 30,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    """GET /v1/ads/campaigns — list campaigns with spend/impressions/clicks metrics."""
    if not _is_configured():
        return {"campaigns": [], "error": "ZERNIO_API_KEY not configured"}
    params: Dict[str, Any] = {"days": days}
    if platform:
        params["platform"] = platform
    if status:
        params["status"] = status
    if account_id:
        params["accountId"] = account_id
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(f"{ZERNIO_BASE}/ads/campaigns", headers=_headers(), params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio list_campaigns %s: %s", e.response.status_code, e.response.text[:300])
            return {"campaigns": [], "error": f"API error {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error("Zernio list_campaigns exception: %s", e)
            return {"campaigns": [], "error": str(e)}


async def get_ads_tree(
    platform: Optional[str] = None,
    days: int = 30,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    """GET /v1/ads/tree — full Campaign > AdSet > Ad hierarchy with metrics."""
    if not _is_configured():
        return {"tree": [], "error": "ZERNIO_API_KEY not configured"}
    params: Dict[str, Any] = {"days": days}
    if platform:
        params["platform"] = platform
    if account_id:
        params["accountId"] = account_id
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(f"{ZERNIO_BASE}/ads/tree", headers=_headers(), params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio get_ads_tree %s: %s", e.response.status_code, e.response.text[:300])
            return {"tree": [], "error": f"API error {e.response.status_code}"}
        except Exception as e:
            logger.error("Zernio get_ads_tree exception: %s", e)
            return {"tree": [], "error": str(e)}


async def get_ad_analytics(ad_id: str, days: int = 30) -> Dict[str, Any]:
    """GET /v1/ads/{adId}/analytics — detailed analytics with daily timeline."""
    if not _is_configured():
        return {"error": "ZERNIO_API_KEY not configured"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(
                f"{ZERNIO_BASE}/ads/{ad_id}/analytics",
                headers=_headers(),
                params={"days": days},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio get_ad_analytics %s: %s", e.response.status_code, e.response.text[:300])
            return {"error": f"API error {e.response.status_code}"}
        except Exception as e:
            logger.error("Zernio get_ad_analytics exception: %s", e)
            return {"error": str(e)}


async def update_campaign_status(
    campaign_id: str,
    status: str,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """PUT /v1/ads/campaigns/{id}/status — pause or activate all ads in a campaign."""
    if not _is_configured():
        return {"error": "ZERNIO_API_KEY not configured"}
    body: Dict[str, Any] = {"status": status}
    if platform:
        body["platform"] = platform
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.put(
                f"{ZERNIO_BASE}/ads/campaigns/{campaign_id}/status",
                headers=_headers(),
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio update_campaign_status %s: %s", e.response.status_code, e.response.text[:300])
            return {"error": f"API error {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error("Zernio update_campaign_status exception: %s", e)
            return {"error": str(e)}


async def update_campaign_budget(
    campaign_id: str,
    daily_budget: Optional[float] = None,
    lifetime_budget: Optional[float] = None,
    bid_strategy: Optional[str] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """PUT /v1/ads/campaigns/{id} — update budget / bid strategy."""
    if not _is_configured():
        return {"error": "ZERNIO_API_KEY not configured"}
    body: Dict[str, Any] = {}
    if daily_budget is not None:
        body["dailyBudget"] = daily_budget
    if lifetime_budget is not None:
        body["lifetimeBudget"] = lifetime_budget
    if bid_strategy:
        body["bidStrategy"] = bid_strategy
    if platform:
        body["platform"] = platform
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.put(
                f"{ZERNIO_BASE}/ads/campaigns/{campaign_id}",
                headers=_headers(),
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio update_campaign_budget %s: %s", e.response.status_code, e.response.text[:300])
            return {"error": f"API error {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error("Zernio update_campaign_budget exception: %s", e)
            return {"error": str(e)}


async def bulk_update_status(campaign_ids: List[str], status: str, platform: Optional[str] = None) -> Dict[str, Any]:
    """POST /v1/ads/campaigns/bulk-status — pause or activate multiple campaigns at once."""
    if not _is_configured():
        return {"error": "ZERNIO_API_KEY not configured"}
    body: Dict[str, Any] = {"campaignIds": campaign_ids, "status": status}
    if platform:
        body["platform"] = platform
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{ZERNIO_BASE}/ads/campaigns/bulk-status",
                headers=_headers(),
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio bulk_update_status %s: %s", e.response.status_code, e.response.text[:300])
            return {"error": f"API error {e.response.status_code}"}
        except Exception as e:
            logger.error("Zernio bulk_update_status exception: %s", e)
            return {"error": str(e)}


async def boost_post(
    post_id: str,
    platform: str,
    daily_budget: float,
    duration_days: int,
    objective: Optional[str] = None,
    audience: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """POST /v1/ads/boost — boost an existing social post as a paid ad."""
    if not _is_configured():
        return {"error": "ZERNIO_API_KEY not configured"}
    body: Dict[str, Any] = {
        "postId": post_id,
        "platform": platform,
        "dailyBudget": daily_budget,
        "durationDays": duration_days,
    }
    if objective:
        body["objective"] = objective
    if audience:
        body["audience"] = audience
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(f"{ZERNIO_BASE}/ads/boost", headers=_headers(), json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio boost_post %s: %s", e.response.status_code, e.response.text[:300])
            return {"error": f"API error {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error("Zernio boost_post exception: %s", e)
            return {"error": str(e)}


async def create_ctwa_ad(
    platform: str,
    whatsapp_number: str,
    creative: Dict[str, Any],
    daily_budget: float,
    duration_days: int,
    audience: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """POST /v1/ads/ctwa — Click-to-WhatsApp ad."""
    if not _is_configured():
        return {"error": "ZERNIO_API_KEY not configured"}
    body: Dict[str, Any] = {
        "platform": platform,
        "whatsappNumber": whatsapp_number,
        "creative": creative,
        "dailyBudget": daily_budget,
        "durationDays": duration_days,
    }
    if audience:
        body["audience"] = audience
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(f"{ZERNIO_BASE}/ads/ctwa", headers=_headers(), json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Zernio create_ctwa_ad %s: %s", e.response.status_code, e.response.text[:300])
            return {"error": f"API error {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error("Zernio create_ctwa_ad exception: %s", e)
            return {"error": str(e)}
