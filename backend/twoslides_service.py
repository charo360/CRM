"""
2Slides API service — generates professional presentations via AI.
API docs: https://2slides.com/api
"""
import asyncio
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://2slides.com/api/v1"
_POLL_INTERVAL = 20  # seconds between status checks (per API docs)
_MAX_POLLS = 12      # 4 minutes max


def _get_key() -> str:
    key = os.getenv("TWOSLIDES_API_KEY", "")
    if not key:
        raise ValueError("TWOSLIDES_API_KEY is not set in environment")
    return key


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_key()}",
        "Content-Type": "application/json",
    }


async def search_themes(query: str = "professional", limit: int = 5) -> list:
    """Search available themes/templates by keyword."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/themes/search",
                headers=_headers(),
                params={"query": query, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            # Response: {"success": true, "data": {"themes": [...]}}
            if isinstance(data, list):
                return data
            return data.get("data", {}).get("themes", data.get("themes", []))
    except Exception as e:
        logger.warning("[2slides] theme search failed: %s", e)
        return []


async def generate_presentation(
    prompt: str,
    theme_id: Optional[str] = None,
    n_slides: int = 10,
    language: str = "en",
    resolution: str = "2K",
    design_style: Optional[str] = None,
    reference_image_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a presentation via 2Slides API.

    Routes:
    - reference_image_url provided → POST /slides/create-like-this (style clone)
    - theme_id provided            → POST /slides/generate (fast PPT, pre-built theme)
    - neither                      → POST /slides/create-pdf-slides (AI-designed, no theme needed)

    Returns dict with: download_url, job_id, status, error
    """
    # ── Route A: style clone from reference image ──────────────────────────
    if reference_image_url:
        payload: Dict[str, Any] = {
            "userInput": prompt,
            "referenceImageUrl": reference_image_url,
            "responseLanguage": language,
            "resolution": resolution,
            "page": n_slides,
            "contentDetail": "standard",
            "mode": "async",
        }
        return await _post_and_poll(f"{_BASE}/slides/create-like-this", payload)

    # ── Route B: fast PPT with pre-built theme ─────────────────────────────
    if theme_id:
        payload = {
            "userInput": prompt,
            "themeId": theme_id,
            "responseLanguage": language,
            "mode": "async",
        }
        return await _post_and_poll(f"{_BASE}/slides/generate", payload)

    # ── Route C: No theme provided — search for one automatically ───────────
    # slides/generate (1 credit/page) is much cheaper than create-pdf-slides (100 credits/page)
    style_kw = design_style or "professional modern"
    themes = await search_themes(style_kw, limit=5)
    if not themes:
        # Fallback: try a generic search
        themes = await search_themes("business", limit=5)

    if themes:
        auto_theme_id = themes[0].get("id") or themes[0].get("themeId")
        logger.info("[2slides] auto-selected theme: %s (%s)", auto_theme_id, themes[0].get("name"))
        payload = {
            "userInput": prompt,
            "themeId": auto_theme_id,
            "responseLanguage": language,
            "mode": "async",
        }
        return await _post_and_poll(f"{_BASE}/slides/generate", payload)

    # Last resort: create-pdf-slides (costs more credits)
    payload = {
        "userInput": prompt,
        "responseLanguage": language,
        "resolution": resolution,
        "page": n_slides,
        "contentDetail": "standard",
        "mode": "async",
    }
    if design_style:
        payload["designStyle"] = design_style
    return await _post_and_poll(f"{_BASE}/slides/create-pdf-slides", payload)


async def _post_and_poll(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST to endpoint and poll for job completion."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(endpoint, headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("[2slides] request failed: %s — %s", e.response.status_code, e.response.text)
        return {"error": f"2Slides API error {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        logger.error("[2slides] request error: %s", e)
        return {"error": str(e)}

    # Response can be flat or nested: {"success": true, "data": {"jobId": "..."}} or {"jobId": "..."}
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    download_url = inner.get("downloadUrl") or inner.get("url") or data.get("downloadUrl")
    job_id = inner.get("jobId") or inner.get("id") or data.get("jobId")

    if download_url and not job_id:
        return {"status": "success", "download_url": download_url, "job_id": None}

    if not job_id:
        return {"error": f"Unexpected 2Slides response: {data}"}

    logger.info("[2slides] job started: %s", job_id)
    return await poll_job(job_id)


async def poll_job(job_id: str) -> Dict[str, Any]:
    """Poll a job until done or failed."""
    for attempt in range(_MAX_POLLS):
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{_BASE}/jobs/{job_id}",
                    headers=_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("[2slides] poll attempt %d failed: %s", attempt + 1, e)
            continue

        # Response may be nested: {"success": true, "data": {"status": "...", "downloadUrl": "..."}}
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        status = (inner.get("status") or data.get("status") or "").lower()
        logger.info("[2slides] job %s status: %s (attempt %d)", job_id, status, attempt + 1)

        if status in ("success", "completed", "done"):
            download_url = inner.get("downloadUrl") or inner.get("url") or data.get("downloadUrl")
            pages = inner.get("pages", data.get("pages", []))
            thumbnail = pages[0] if pages else None
            return {
                "status": "success",
                "download_url": download_url,
                "thumbnail_url": thumbnail,
                "job_id": job_id,
                "pages": pages,
            }
        elif status in ("failed", "error"):
            return {"error": inner.get("message") or data.get("message") or "2Slides render failed", "job_id": job_id}
        # Still processing — keep polling

    return {"error": "2Slides render timed out after 2 minutes", "job_id": job_id}
