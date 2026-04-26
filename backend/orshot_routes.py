"""HTTP API for Orshot: template field schema + render (for dashboard forms and integrations)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


def _simplify_modifications(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in raw or []:
        if not isinstance(m, dict):
            continue
        out.append({
            "key": m.get("key") or m.get("id"),
            "type": m.get("type"),
            "help_text": m.get("helpText") or m.get("help_text") or m.get("description"),
            "example": m.get("example"),
            "page_number": m.get("page_number"),
            "page_id": m.get("page_id"),
        })
    return out


class OrshotRenderBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    template_id: int = Field(..., gt=0, description="Orshot studio template id")
    modifications: Dict[str, Any] = Field(default_factory=dict)
    response_type: Literal["url", "base64", "binary"] = "base64"
    response_format: Literal["png", "jpg", "jpeg", "webp", "pdf"] = "png"


def make_orshot_router(user_dep):
    router = APIRouter(prefix="/orshot", tags=["orshot"])

    @router.get("/templates/{template_id}")
    async def get_template_schema(template_id: int, user=user_dep):
        """Return editable field definitions for building a manual form (or for the AI to list)."""
        _ = user
        if not (os.environ.get("ORSHOT_API_KEY") or "").strip():
            raise HTTPException(status_code=503, detail="Orshot is not configured (ORSHOT_API_KEY missing)")
        from orshot_service import get_studio_template

        data = await get_studio_template(template_id)
        if data.get("error"):
            raise HTTPException(status_code=400, detail=data["error"])
        mods = data.get("modifications") or []
        return {
            "success": True,
            "template_id": data.get("id"),
            "name": data.get("name"),
            "description": data.get("description"),
            "canvas_width": data.get("canvas_width"),
            "canvas_height": data.get("canvas_height"),
            "thumbnail_url": data.get("thumbnail_url"),
            "pages": data.get("pages_data") or [],
            "fields": _simplify_modifications(mods if isinstance(mods, list) else []),
        }

    @router.post("/render")
    async def render_template(body: OrshotRenderBody, user=user_dep):
        """Render from template + modifications; same contract as assistant tool (for UI submit)."""
        _ = user
        if not (os.environ.get("ORSHOT_API_KEY") or "").strip():
            raise HTTPException(status_code=503, detail="Orshot is not configured (ORSHOT_API_KEY missing)")
        from orshot_service import render_studio_template

        fmt = body.response_format
        if fmt == "jpeg":
            fmt = "jpg"
        result = await render_studio_template(
            body.template_id,
            body.modifications,
            response_type=body.response_type,
            response_format=fmt,
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {
            "success": True,
            "image_url": result.get("image_url"),
            "image_urls": result.get("image_urls"),
        }

    return router
