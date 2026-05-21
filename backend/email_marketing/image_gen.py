"""
email_marketing/image_gen.py
Email image generation via OpenRouter (nano_banana_service).

- generate_email_image   → creates a new image from a text prompt
- enhance_product_image  → places an existing product photo in a marketing scene
Both upload to S3 and return a public URL.
"""
from __future__ import annotations

import logging
import sys
import os

logger = logging.getLogger(__name__)

# nano_banana_service lives one level up in the backend root
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


async def generate_email_image(
    prompt: str,
    image_type: str = "hero",          # hero | product
    logo_url: str = "",
    accent_color: str = "",
    quality: str = "fast",             # fast | pro
) -> str:
    """
    Generate a brand-new marketing image via OpenRouter (Gemini Nano Banana).
    Returns a public S3 URL.
    Raises RuntimeError on failure.
    """
    from nano_banana_service import generate_creative_image

    fmt = "landscape" if image_type == "hero" else "square"
    result = await generate_creative_image(
        prompt=prompt,
        format=fmt,
        quality=quality,
        logo_url=logo_url or None,
        brand_color=accent_color,
    )
    if result.get("error"):
        raise RuntimeError(result["error"])
    url = result.get("image_url") or result.get("url", "")
    if not url:
        raise RuntimeError("Image generation returned no URL")
    return url


async def enhance_product_image(
    product_image_url: str,
    scene_prompt: str,
    logo_url: str = "",
    accent_color: str = "",
    quality: str = "fast",
) -> str:
    """
    Place an existing product photo in a compelling marketing scene.
    Returns a public S3 URL.
    Raises RuntimeError on failure.
    """
    from nano_banana_service import edit_product_image

    result = await edit_product_image(
        product_image_url=product_image_url,
        scene_prompt=scene_prompt,
        format="square",
        quality=quality,
        logo_url=logo_url or None,
        brand_color=accent_color,
    )
    if result.get("error"):
        raise RuntimeError(result["error"])
    url = result.get("image_url") or result.get("url", "")
    if not url:
        raise RuntimeError("Image enhancement returned no URL")
    return url


def hero_prompt(email_type: str, description: str, brand: str, accent: str) -> str:
    moods = {
        "Flash sale":           "Dynamic urgency. Vibrant saturated colors. Shopping excitement.",
        "Seasonal campaign":    "Festive warm atmosphere. Celebratory. Rich seasonal colors.",
        "Event invitation":     "Elegant atmospheric venue. Upscale, premium. Soft bokeh.",
        "Product announcement": "Clean studio reveal. Minimalist. Exciting product focus.",
        "Welcome":              "Warm, friendly, optimistic. Soft natural daylight.",
        "Newsletter":           "Clean editorial lifestyle. Professional workspace.",
        "Promotional":          "Bold commercial photography. Eye-catching. Modern aspirational.",
    }
    mood = moods.get(email_type, "Professional, modern, aspirational commercial photography.")
    return (
        f"{mood} "
        f"Wide landscape hero banner for a {email_type} email. "
        f"Campaign: {description}. Brand: {brand}. Accent color: {accent}. "
        f"Photorealistic. No text, no watermarks, no logos."
    )


def product_scene_prompt(
    product_name: str,
    product_desc: str,
    email_type: str,
    accent: str,
) -> str:
    return (
        f"Professional marketing scene for product: {product_name}. "
        f"{f'Details: {product_desc}. ' if product_desc else ''}"
        f"Campaign type: {email_type}. Accent color: {accent}. "
        f"Clean studio or lifestyle background. Perfect lighting. Square format."
    )


def product_gen_prompt(
    product_name: str,
    product_desc: str,
    email_type: str,
    accent: str,
) -> str:
    return (
        f"Professional product photography. Clean white studio background. "
        f"Perfect studio lighting. Product: {product_name}. "
        f"{f'Details: {product_desc}. ' if product_desc else ''}"
        f"Style: modern commercial {email_type.lower()} campaign. "
        f"Color accent: {accent}. Photorealistic. No text, no watermarks, no logos."
    )
