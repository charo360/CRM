"""
email_marketing/image_gen.py
Gemini Imagen 3 image generation → ImgBB public URL.

Requires:
  GEMINI_API_KEY  — Google AI Studio key (https://aistudio.google.com/app/apikey)
  IMGBB_API_KEY   — already present in .env
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
IMGBB_API_KEY  = os.environ.get("IMGBB_API_KEY", "")

_IMAGEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict"
_IMGBB_URL  = "https://api.imgbb.com/1/upload"

# Aspect ratio map
ASPECT_RATIOS = {
    "hero":    "16:9",   # wide email banner
    "product": "1:1",    # square product card
    "portrait":"9:16",   # tall/portrait
}


async def generate_marketing_image(
    prompt: str,
    image_type: str = "hero",
    person_generation: str = "ALLOW_ADULT",
) -> str:
    """
    Generate a professional marketing image via Imagen 3.
    Uploads to ImgBB and returns a public URL.
    Falls back to data URI if ImgBB is unavailable.

    Raises RuntimeError if GEMINI_API_KEY is not set or generation fails.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY not configured. "
            "Get a key at https://aistudio.google.com/app/apikey and add it to backend/.env"
        )

    aspect = ASPECT_RATIOS.get(image_type, "16:9")

    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            f"{_IMAGEN_URL}?key={GEMINI_API_KEY}",
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": aspect,
                    "safetyFilterLevel": "BLOCK_SOME",
                    "personGeneration": person_generation,
                },
            },
        )

    data = r.json()
    if not r.is_success:
        err_msg = data.get("error", {}).get("message", r.text[:300])
        raise RuntimeError(f"Imagen 3 error {r.status_code}: {err_msg}")

    predictions = data.get("predictions") or []
    if not predictions:
        raise RuntimeError("Imagen 3 returned no predictions")

    b64 = predictions[0].get("bytesBase64Encoded", "")
    if not b64:
        raise RuntimeError("Imagen 3 returned empty image data")

    if IMGBB_API_KEY:
        try:
            return await _upload_imgbb(b64)
        except Exception as e:
            logger.warning("ImgBB upload failed, falling back to data URI: %s", e)

    return f"data:image/png;base64,{b64}"


async def _upload_imgbb(b64: str) -> str:
    """Upload base64 PNG to ImgBB, return direct URL."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            _IMGBB_URL,
            data={"key": IMGBB_API_KEY, "image": b64},
        )
    data = r.json()
    if not r.is_success or not data.get("success"):
        raise RuntimeError(
            f"ImgBB {r.status_code}: {data.get('error', {}).get('message', r.text[:200])}"
        )
    return data["data"]["url"]


def build_hero_prompt(
    email_type: str,
    description: str,
    brand: str,
    accent_color: str,
) -> str:
    """Build a prompt for a professional email hero/banner image."""
    style = (
        "Professional commercial photography. Photorealistic. High resolution. "
        "Clean composition. No text, no words, no logos, no watermarks. "
        "Suitable for email marketing header. Wide landscape format."
    )

    mood_map = {
        "Flash sale":           "Dynamic energy. Vibrant colors. Shopping excitement. Dramatic lighting.",
        "Seasonal campaign":    "Festive warm atmosphere. Seasonal decorations. Celebratory mood.",
        "Event invitation":     "Elegant venue. Atmospheric. Premium, upscale feel. Bokeh background.",
        "Product announcement": "Clean studio aesthetic. Exciting product reveal. Minimalist background.",
        "Welcome":              "Warm, friendly, inviting. Soft natural light. Optimistic.",
        "Newsletter":           "Clean editorial lifestyle. Minimal. Professional workspace or lifestyle.",
        "Promotional":          "Bold, eye-catching. Product showcase. Modern commercial style.",
    }
    mood = mood_map.get(email_type, "Professional, aspirational, modern commercial photography.")

    return (
        f"{style} {mood} "
        f"Campaign topic: {description}. Brand: {brand}. "
        f"Color palette inspired by {accent_color}."
    )


def build_product_prompt(
    product_name: str,
    product_description: str,
    email_type: str,
    accent_color: str,
) -> str:
    """Build a prompt for a professional product image."""
    return (
        f"Professional product photography. Photorealistic. High resolution. "
        f"Clean white or light studio background. Perfect lighting. "
        f"No text, no watermarks, no logos. Square format. "
        f"Product: {product_name}. "
        f"{f'Description: {product_description}. ' if product_description else ''}"
        f"Style: modern commercial {email_type.lower()} campaign. "
        f"Color accent: {accent_color}."
    )
