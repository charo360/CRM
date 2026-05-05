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
_POLL_INTERVAL = 5  # seconds between status checks
_MAX_POLLS = 24     # 2 minutes max


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


async def search_themes(query: str = "professional") -> list:
    """Search available themes/templates by keyword."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/themes/search",
                headers=_headers(),
                params={"q": query},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("themes", [])
    except Exception as e:
        logger.warning("[2slides] theme search failed: %s", e)
        return []


async def generate_presentation(
    prompt: str,
    theme_id: Optional[str] = None,
    n_slides: int = 10,
    language: str = "en",
    resolution: str = "2K",
    reference_image_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a presentation via 2Slides API.
    Returns dict with: download_url, job_id, status, error
    """
    payload: Dict[str, Any] = {
        "userInput": prompt,
        "responseLanguage": language,
        "resolution": resolution,
        "mode": "async",
    }
    if theme_id:
        payload["themeId"] = theme_id
    if n_slides:
        payload["numSlides"] = n_slides

    # Use style-cloning endpoint if reference image provided
    endpoint = f"{_BASE}/slides/generate"
    if reference_image_url:
        endpoint = f"{_BASE}/slides/create-like-this"
        payload["referenceImageUrl"] = reference_image_url

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(endpoint, headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("[2slides] generate failed: %s — %s", e.response.status_code, e.response.text)
        return {"error": f"2Slides API error: {e.response.status_code} — {e.response.text}"}
    except Exception as e:
        logger.error("[2slides] generate request failed: %s", e)
        return {"error": str(e)}

    job_id = data.get("jobId") or data.get("id")
    if not job_id:
        # Synchronous response with direct download URL
        download_url = data.get("downloadUrl") or data.get("url")
        if download_url:
            return {"status": "success", "download_url": download_url, "job_id": None}
        return {"error": f"Unexpected response: {data}"}

    # Poll for result
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

        status = (data.get("status") or "").lower()
        logger.info("[2slides] job %s status: %s (attempt %d)", job_id, status, attempt + 1)

        if status in ("success", "completed", "done"):
            download_url = data.get("downloadUrl") or data.get("url")
            pages = data.get("pages", [])
            thumbnail = pages[0] if pages else None
            return {
                "status": "success",
                "download_url": download_url,
                "thumbnail_url": thumbnail,
                "job_id": job_id,
                "pages": pages,
            }
        elif status in ("failed", "error"):
            return {"error": data.get("message") or "2Slides render failed", "job_id": job_id}
        # Still processing — keep polling

    return {"error": "2Slides render timed out after 2 minutes", "job_id": job_id}
