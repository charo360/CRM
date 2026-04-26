"""Orshot Studio — render images (and other formats) from templates via REST API."""
from __future__ import annotations

import base64
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)

ORSHOT_RENDER_URL = "https://api.orshot.com/v1/studio/render"
ORSHOT_TEMPLATE_GET_URL = "https://api.orshot.com/v1/studio/templates"


def _api_key() -> str:
    return (os.environ.get("ORSHOT_API_KEY") or "").strip()


def _coerce_template_id(template_id: Union[str, int]) -> Union[str, int]:
    if isinstance(template_id, int):
        return template_id
    s = str(template_id).strip()
    if s.isdigit():
        return int(s)
    return s


def _extract_output_urls(data: Any) -> List[str]:
    """Normalize Orshot response `data` into a list of image/file URLs or data URLs."""
    out: List[str] = []
    if data is None:
        return out
    if isinstance(data, dict):
        content = data.get("content")
        if isinstance(content, str) and content:
            out.append(content)
        return out
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            c = item.get("content")
            if isinstance(c, str) and c:
                out.append(c)
    return out


def _normalize_format(response_format: str) -> str:
    fmt = (response_format or "png").lower()
    if fmt == "jpeg":
        return "jpg"
    return fmt if fmt in ("png", "jpg", "webp", "pdf") else "png"


async def rehost_orshot_outputs_to_zilo_bucket(
    outputs: List[str],
    *,
    response_format: str,
) -> List[str]:
    """
    Orshot ``response.type=url`` often returns third-party S3 presigned links; those can be
    invalid (wrong signer, placeholder signature, etc.). We always persist bytes in **our**
    bucket and return boto3 presigned GET URLs the app trusts.
    """
    from image_handler import S3Handler

    ext = _normalize_format(response_format)
    hosted: List[str] = []

    for raw in outputs:
        s = (raw or "").strip()
        if not s:
            continue
        if s.startswith("data:"):
            fn = f"orshot-{uuid.uuid4()}.{ext}"
            hosted.append(await S3Handler.upload_file(s, fn))
            continue
        if s.startswith("http://") or s.startswith("https://"):
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.get(s, follow_redirects=True)
            if r.status_code != 200:
                raise ValueError(
                    f"Could not download Orshot output (HTTP {r.status_code}). "
                    "The render URL may be invalid or unsigned for this environment."
                )
            ct = (r.headers.get("content-type") or "").split(";")[0].strip() or (
                "application/pdf" if ext == "pdf" else ("image/jpeg" if ext == "jpg" else f"image/{ext}")
            )
            data_url = f"data:{ct};base64,{base64.b64encode(r.content).decode('ascii')}"
            fn = f"orshot-{uuid.uuid4()}.{ext}"
            hosted.append(await S3Handler.upload_file(data_url, fn))
            continue
        raise ValueError(f"Unexpected Orshot output (expected data: or https URL): {s[:120]!r}")

    return hosted


async def render_studio_template(
    template_id: Union[str, int],
    modifications: Dict[str, Any],
    *,
    response_type: str = "base64",
    response_format: str = "png",
    timeout_sec: float = 120.0,
) -> Dict[str, Any]:
    """
    POST /v1/studio/render. Returns ``{success, image_url, image_urls, raw}`` or ``{error}``.

    Defaults to ``response_type=base64`` so we never depend on Orshot-hosted S3 presigns;
    outputs are re-uploaded to this deployment's bucket with a fresh presigned GET URL.
    """
    key = _api_key()
    if not key:
        return {"error": "ORSHOT_API_KEY is not set in the server environment."}

    tid = _coerce_template_id(template_id)
    payload: Dict[str, Any] = {
        "templateId": tid,
        "modifications": modifications or {},
        "response": {
            "type": response_type,
            "format": response_format,
        },
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(ORSHOT_RENDER_URL, headers=headers, json=payload)
            text = r.text
            try:
                body = r.json()
            except Exception:
                body = {"raw": text[:2000]}
    except httpx.TimeoutException:
        return {"error": "Orshot request timed out — try again or simplify the template."}
    except Exception as e:
        logger.exception("[orshot] request failed")
        return {"error": str(e)}

    if r.status_code >= 400:
        err = body if isinstance(body, dict) else {}
        msg = err.get("message") or err.get("error") or text[:500]
        return {"error": f"Orshot HTTP {r.status_code}: {msg}"}

    if not isinstance(body, dict):
        return {"error": "Unexpected Orshot response shape."}

    data = body.get("data")
    urls = _extract_output_urls(data)
    if not urls:
        return {
            "error": "Orshot returned no image content. Check templateId and modification keys match Studio parameters.",
            "raw_keys": list(body.keys()),
        }

    try:
        hosted = await rehost_orshot_outputs_to_zilo_bucket(urls, response_format=response_format)
    except ValueError as ve:
        return {"error": str(ve)}
    except Exception as e:
        logger.exception("[orshot] rehost to Zilo S3 failed")
        return {"error": f"Orshot render succeeded but saving to your image bucket failed: {e}"}

    return {
        "success": True,
        "image_url": hosted[0],
        "image_urls": hosted,
        "raw": body,
    }


async def get_studio_template(
    template_id: Union[str, int],
    *,
    timeout_sec: float = 60.0,
) -> Dict[str, Any]:
    """
    GET /v1/studio/templates/:id — template metadata plus ``modifications`` (dynamic parameter defs).

    Returns ``{success, id, name, modifications, pages_data, ...}`` or ``{error}``.
    """
    key = _api_key()
    if not key:
        return {"error": "ORSHOT_API_KEY is not set in the server environment."}

    tid = _coerce_template_id(template_id)
    url = f"{ORSHOT_TEMPLATE_GET_URL}/{tid}"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.get(url, headers=headers)
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:2000]}
    except Exception as e:
        logger.exception("[orshot] get template failed")
        return {"error": str(e)}

    if r.status_code >= 400:
        msg = body.get("message") if isinstance(body, dict) else str(body)
        return {"error": f"Orshot HTTP {r.status_code}: {msg}"}

    if not isinstance(body, dict):
        return {"error": "Unexpected Orshot template response."}

    mods = body.get("modifications") or []
    return {
        "success": True,
        "id": body.get("id"),
        "name": body.get("name"),
        "description": body.get("description"),
        "canvas_width": body.get("canvas_width"),
        "canvas_height": body.get("canvas_height"),
        "thumbnail_url": body.get("thumbnail_url"),
        "modifications": mods,
        "pages_data": body.get("pages_data") or [],
        "raw": body,
    }


async def list_studio_templates(
    *,
    page: int = 1,
    limit: int = 20,
    timeout_sec: float = 60.0,
) -> Dict[str, Any]:
    """
    GET /v1/studio/templates/all — paginated catalog so the assistant can pick a template by intent.

    ``limit`` max 20 per Orshot docs.
    """
    key = _api_key()
    if not key:
        return {"error": "ORSHOT_API_KEY is not set in the server environment."}

    page = max(1, int(page))
    limit = min(20, max(1, int(limit)))
    url = f"{ORSHOT_TEMPLATE_GET_URL}/all"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    params = {"page": page, "limit": limit}

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.get(url, headers=headers, params=params)
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:2000]}
    except Exception as e:
        logger.exception("[orshot] list templates failed")
        return {"error": str(e)}

    if r.status_code >= 400:
        msg = body.get("message") if isinstance(body, dict) else str(body)
        return {"error": f"Orshot HTTP {r.status_code}: {msg}"}

    if not isinstance(body, dict):
        return {"error": "Unexpected Orshot list response."}

    rows = body.get("data") or []
    simplified: List[Dict[str, Any]] = []
    for t in rows if isinstance(rows, list) else []:
        if not isinstance(t, dict):
            continue
        pages = t.get("pages_data") or []
        simplified.append(
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "description": (t.get("description") or "")[:240],
                "canvas_width": t.get("canvas_width"),
                "canvas_height": t.get("canvas_height"),
                "thumbnail_url": t.get("thumbnail_url"),
                "page_count": len(pages) if isinstance(pages, list) else 0,
            }
        )

    return {
        "success": True,
        "templates": simplified,
        "pagination": body.get("pagination") or {},
    }
