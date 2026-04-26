"""Nano Banana (Google Gemini image generation) via OpenRouter → S3 upload."""
import os
import uuid
import base64
import logging
import httpx
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Model IDs on OpenRouter
NANO_BANANA_2   = "google/gemini-3.1-flash-image-preview"   # fastest, best quality/speed
NANO_BANANA_PRO = "google/gemini-3-pro-image-preview"        # highest quality, slower

# Aspect ratio → OpenRouter image_config value
_ASPECT_MAP: Dict[str, str] = {
    "square":    "1:1",
    "story":     "9:16",
    "landscape": "16:9",
    "portrait":  "4:5",
}


async def _fetch_as_b64(url: str) -> tuple[str, str]:
    """Download a URL and return (base64_string, mime_type)."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        mime = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return base64.b64encode(r.content).decode(), mime


async def edit_product_image(
    product_image_url: str,
    scene_prompt: str,
    format: str = "square",
    quality: str = "fast",
) -> Dict[str, Any]:
    """
    Use Gemini to EDIT an existing product photo — places the real product in a new
    scene/environment with professional lighting without replacing or reinventing it.

    product_image_url : publicly accessible URL of the product photo
    scene_prompt      : description of the desired scene, lighting, mood
                        e.g. "on a marble table, golden-hour sunlight from the left, moody shadows"
    """
    if not OPENROUTER_KEY:
        return {"error": "OPENROUTER_KEY not configured in .env"}

    try:
        prod_b64, prod_mime = await _fetch_as_b64(product_image_url)
    except Exception as e:
        logger.warning("[nano_banana] Could not fetch product image for editing: %s", e)
        return {"error": f"Could not fetch product image: {e}"}

    model = NANO_BANANA_PRO if quality == "pro" else NANO_BANANA_2
    aspect_ratio = _ASPECT_MAP.get(format, "1:1")

    edit_instruction = (
        f"You are a world-class commercial photographer and creative director.\n\n"
        f"STEP 1 — ANALYZE: Study this product carefully. What is it? What are its key visual "
        f"strengths — shape, texture, color, branding, scale? Who buys it and why?\n\n"
        f"STEP 2 — DECIDE STAGING: Choose the single most compelling way to present this product "
        f"for an advertisement. Think like a creative director:\n"
        f"- For footwear: worn on a foot in motion, angled hero shot on a surface, flat lay from above, "
        f"or floating dramatic shot?\n"
        f"- For a bottle/drink: poured mid-action, condensation on ice, held in hand, or pristine on surface?\n"
        f"- For clothing: worn on a model, folded editorial, or dramatic close-up of fabric?\n"
        f"- For electronics: in use, angled product shot, detail close-up, or lifestyle context?\n"
        f"Pick what makes THIS specific product look most irresistible to a buyer.\n\n"
        f"STEP 3 — CREATE THE SCENE: {scene_prompt}\n\n"
        f"ABSOLUTE RULES — violating any of these ruins the image:\n"
        f"1. The product itself must remain 100% identical to the original photo — same shape, every color, "
        f"all branding, every texture and detail. Do NOT redesign, stylize, or reimagine the product.\n"
        f"2. The final image must look like a REAL PHOTOGRAPH taken by a human photographer — "
        f"photorealistic, natural lighting, genuine depth of field. Not AI art, not CGI, not illustration.\n"
        f"3. No text, no words, no letters, no watermarks anywhere in the image.\n"
        f"4. No other products or competing objects in the scene.\n"
        f"5. The scene and background must feel real — real surfaces, real light, real environment."
    )

    message_content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{prod_mime};base64,{prod_b64}"},
        },
        {"type": "text", "text": edit_instruction},
    ]

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message_content}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio},
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("FRONTEND_URL", "https://charo360.com"),
        "X-Title": "Zilo CRM Design Agent",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.error("[nano_banana] edit_product_image request failed: %s", e)
        return {"error": str(e)}

    try:
        choices = data.get("choices", [])
        if not choices:
            return {"error": "No choices returned from Gemini image edit"}
        message = choices[0].get("message", {})
        images = message.get("images") or []
        if not images:
            content = message.get("content", "")
            if isinstance(content, str) and content.startswith("data:image"):
                b64_data = content
            else:
                logger.warning("[nano_banana] edit_product_image unexpected shape: %s", str(data)[:400])
                return {"error": "No image data in edit response"}
        else:
            b64_data = images[0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError) as e:
        return {"error": f"Failed to parse edit response: {e}"}

    try:
        from image_handler import S3Handler
        filename = f"edited-product-{uuid.uuid4()}.png"
        public_url = await S3Handler.upload_file(b64_data, filename, content_type="image/png")
        if not public_url:
            return {"error": "S3 upload returned empty URL"}
        return {"success": True, "image_url": public_url, "source": "gemini_edit"}
    except Exception as e:
        logger.error("[nano_banana] S3 upload failed after edit: %s", e)
        return {"error": f"S3 upload failed: {e}"}


async def generate_creative_image(
    prompt: str,
    format: str = "square",
    quality: str = "fast",
    logo_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call Nano Banana via OpenRouter to generate a creative/lifestyle image.
    Returns {"success": True, "image_url": <s3_url>} or {"error": ...}

    quality: "fast" uses Nano Banana 2 (Flash), "pro" uses Nano Banana Pro.
    logo_url: optional brand logo — passed as a multimodal reference so Gemini
              can incorporate the brand's colour palette and aesthetic.
    """
    if not OPENROUTER_KEY:
        return {"error": "OPENROUTER_KEY not configured in .env"}

    model = NANO_BANANA_PRO if quality == "pro" else NANO_BANANA_2
    aspect_ratio = _ASPECT_MAP.get(format, "1:1")

    # Build multimodal content: if a logo is provided, include it as an image
    # reference so Gemini can pick up brand colours / aesthetic.
    if logo_url:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                logo_resp = await client.get(logo_url)
                logo_resp.raise_for_status()
                logo_b64 = base64.b64encode(logo_resp.content).decode()
                content_type = logo_resp.headers.get("content-type", "image/png").split(";")[0]
                message_content = [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{logo_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ]
        except Exception as e:
            logger.warning("[nano_banana] Logo fetch failed, falling back to text-only: %s", e)
            message_content = prompt
    else:
        message_content = prompt

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": message_content,
            }
        ],
        "modalities": ["image", "text"],
        "image_config": {
            "aspect_ratio": aspect_ratio,
        },
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("FRONTEND_URL", "https://charo360.com"),
        "X-Title": "Zilo CRM Design Agent",
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.error("[nano_banana] OpenRouter request failed: %s", e)
        return {"error": str(e)}

    # Extract base64 image from response
    try:
        choices = data.get("choices", [])
        if not choices:
            return {"error": "No choices returned from Nano Banana"}

        message = choices[0].get("message", {})

        # Images come back in message["images"] as list of {image_url: {url: "data:image/png;base64,..."}}
        images = message.get("images") or []
        if not images:
            # Fallback: sometimes content contains the data URL inline
            content = message.get("content", "")
            if isinstance(content, str) and content.startswith("data:image"):
                b64_data = content
            else:
                logger.warning("[nano_banana] Unexpected response shape: %s", str(data)[:400])
                return {"error": "No image data in response"}
        else:
            b64_data = images[0]["image_url"]["url"]

    except (KeyError, IndexError, TypeError) as e:
        logger.error("[nano_banana] Failed to parse response: %s | data: %s", e, str(data)[:400])
        return {"error": f"Failed to parse Nano Banana response: {e}"}

    # Upload base64 image to S3
    try:
        from image_handler import S3Handler
        filename = f"creative-{uuid.uuid4()}.png"
        public_url = await S3Handler.upload_file(b64_data, filename, content_type="image/png")
        if not public_url:
            return {"error": "S3 upload returned empty URL"}
        return {"success": True, "image_url": public_url}
    except Exception as e:
        logger.error("[nano_banana] S3 upload failed: %s", e)
        return {"error": f"S3 upload failed: {e}"}


async def recreate_design_from_reference(
    *,
    reference_image_url: str,
    prompt: str,
    product_image_url: Optional[str] = None,
    logo_url: Optional[str] = None,
    format: str = "square",
    quality: str = "pro",
) -> Dict[str, Any]:
    """
    Recreate a marketing design using a reference layout image plus optional
    product / logo references and a strict text prompt.

    The reference image is sent first so the model treats it as the primary
    layout/style cue. ``prompt`` carries the strict-rules text (allowed facts,
    no fabrication, leave empty when no fact). Returns
    ``{success, image_url}`` on success, or ``{error}`` otherwise.
    """
    if not OPENROUTER_KEY:
        return {"error": "OPENROUTER_KEY not configured in .env"}
    if not reference_image_url:
        return {"error": "reference_image_url is required"}

    model = NANO_BANANA_PRO if quality == "pro" else NANO_BANANA_2
    aspect_ratio = _ASPECT_MAP.get(format, "1:1")

    message_content: list = []
    try:
        ref_b64, ref_mime = await _fetch_as_b64(reference_image_url)
        message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{ref_mime};base64,{ref_b64}"},
        })
    except Exception as e:
        logger.warning("[nano_banana] reference fetch failed: %s", e)
        return {"error": f"Could not fetch reference image: {e}"}

    if product_image_url:
        try:
            p_b64, p_mime = await _fetch_as_b64(product_image_url)
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{p_mime};base64,{p_b64}"},
            })
        except Exception as e:
            logger.warning("[nano_banana] product fetch failed (continuing without): %s", e)

    if logo_url:
        try:
            l_b64, l_mime = await _fetch_as_b64(logo_url)
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{l_mime};base64,{l_b64}"},
            })
        except Exception as e:
            logger.warning("[nano_banana] logo fetch failed (continuing without): %s", e)

    message_content.append({"type": "text", "text": prompt})

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message_content}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio},
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("FRONTEND_URL", "https://charo360.com"),
        "X-Title": "Zilo CRM Design Agent",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.error("[nano_banana] recreate request failed: %s", e)
        return {"error": str(e)}

    try:
        choices = data.get("choices", [])
        if not choices:
            return {"error": "No choices returned from recreate"}
        message = choices[0].get("message", {})
        images = message.get("images") or []
        if not images:
            content = message.get("content", "")
            if isinstance(content, str) and content.startswith("data:image"):
                b64_data = content
            else:
                logger.warning("[nano_banana] recreate unexpected shape: %s", str(data)[:400])
                return {"error": "No image data in recreate response"}
        else:
            b64_data = images[0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError) as e:
        return {"error": f"Failed to parse recreate response: {e}"}

    try:
        from image_handler import S3Handler
        filename = f"recreate-{uuid.uuid4()}.png"
        public_url = await S3Handler.upload_file(b64_data, filename, content_type="image/png")
        if not public_url:
            return {"error": "S3 upload returned empty URL"}
        return {"success": True, "image_url": public_url}
    except Exception as e:
        logger.error("[nano_banana] S3 upload failed after recreate: %s", e)
        return {"error": f"S3 upload failed: {e}"}
