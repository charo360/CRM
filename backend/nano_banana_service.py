"""Nano Banana (Google Gemini image generation) via OpenRouter → S3 upload."""
import os
import uuid
import base64
import logging
import httpx
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Dedicated file logger so errors are captured even in uvicorn worker subprocesses
_file_handler = logging.FileHandler(
    os.path.join(os.path.dirname(__file__), "nano_banana_errors.log"), encoding="utf-8"
)
_file_handler.setLevel(logging.WARNING)
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_file_handler)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Env: OPENROUTER_KEY (primary), OPENROUTER_API_KEY (common alias), OPENROUTER_KEY_2, ...
# Keys are read at call time so local .env matches Render after restart (not cached at import).
_OPENROUTER_KEY_MISSING = (
    "OpenRouter is not configured. Set OPENROUTER_KEY or OPENROUTER_API_KEY in "
    "CRM/backend/.env for local dev; on Render add the same variable in Environment."
)


def _load_openrouter_keys() -> list[str]:
    keys: list[str] = []
    primary = os.getenv("OPENROUTER_KEY", "").strip()
    if not primary:
        primary = os.getenv("OPENROUTER_API_KEY", "").strip()
    if primary:
        keys.append(primary)
    i = 2
    while True:
        k = os.getenv(f"OPENROUTER_KEY_{i}", "").strip()
        if not k:
            break
        keys.append(k)
        i += 1
    return keys


_MAX_RETRIES_PER_KEY = 2  # attempts per key before moving to the next

# Model IDs on OpenRouter — image generation (modalities: ["image","text"])
NANO_BANANA_2   = "google/gemini-3.1-flash-image-preview"   # Nano Banana 2 — fast
NANO_BANANA_PRO = "google/gemini-3.1-flash-image-preview"     # Switched to flash — same as NANO_BANANA_2

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
    logo_url: Optional[str] = None,
    brand_color: str = "",
) -> Dict[str, Any]:
    """
    Use Gemini to EDIT an existing product photo — places the real product in a new
    scene/environment with professional lighting without replacing or reinventing it.

    product_image_url : publicly accessible URL of the product photo
    scene_prompt      : description of the desired scene, lighting, mood
    logo_url          : optional brand logo — overlaid in a corner of the final design
    brand_color       : optional hex color — used as accent in the scene
    """
    keys = _load_openrouter_keys()
    if not keys:
        return {"error": _OPENROUTER_KEY_MISSING}

    try:
        prod_b64, prod_mime = await _fetch_as_b64(product_image_url)
        logger.info("[nano_banana] edit: product image fetched, b64_len=%d mime=%s", len(prod_b64), prod_mime)
    except Exception as e:
        logger.warning("[nano_banana] Could not fetch product image for editing: %s", e)
        return {"error": f"Could not fetch product image: {e}"}

    model = NANO_BANANA_PRO if quality == "pro" else NANO_BANANA_2
    aspect_ratio = _ASPECT_MAP.get(format, "1:1")

    color_note = f"\nBRAND ACCENT COLOUR: {brand_color} — use this as a subtle accent in the background, surface, or lighting." if brand_color else ""
    logo_note = (
        "\n\nBRAND LOGO PLACEMENT: The second image is the brand logo. You MUST include it in the final design.\n"
        "- Analyse the finished composition first — identify which corner or edge has the most visual breathing room (least subject matter, least focal weight).\n"
        "- Place the logo there. Size: ~12–16% of canvas width. Must be readable but not competing with the product.\n"
        "- Match contrast to local background: light logo on dark areas, dark/coloured logo on light areas.\n"
        "- It must look DESIGNED-IN, not pasted on top. Blend with the scene's lighting direction.\n"
        "- Do NOT distort, recolour, rotate, or reshape the logo."
    ) if logo_url else ""

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
        f"STEP 3 — CREATE THE SCENE: {scene_prompt}{color_note}{logo_note}\n\n"
        f"ABSOLUTE RULES — violating any of these ruins the image:\n"
        f"1. The product itself must remain 100% identical to the original photo — same shape, every color, "
        f"all branding, every texture and detail. Do NOT redesign, stylize, or reimagine the product.\n"
        f"2. The final image must look like a REAL PHOTOGRAPH taken by a human photographer — "
        f"photorealistic, natural lighting, genuine depth of field. Not AI art, not CGI, not illustration.\n"
        f"3. No text, no words, no letters, no watermarks anywhere in the image — except the brand logo if provided.\n"
        f"4. No other products or competing objects in the scene.\n"
        f"5. The scene and background must feel real — real surfaces, real light, real environment."
    )

    message_content: list = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{prod_mime};base64,{prod_b64}"},
        },
    ]
    if logo_url:
        try:
            logo_b64, logo_mime = await _fetch_as_b64(logo_url)
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{logo_mime};base64,{logo_b64}"},
            })
        except Exception as logo_err:
            logger.warning("[nano_banana] logo fetch failed (continuing without): %s", logo_err)
    message_content.append({"type": "text", "text": edit_instruction})

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message_content}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio},
    }

    import json as _json
    _payload_size = len(_json.dumps(payload, default=str))
    logger.info("[nano_banana:edit] payload_size=%d bytes model=%s aspect=%s", _payload_size, model, aspect_ratio)

    base_headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("FRONTEND_URL", "https://zilo.pro"),
        "X-Title": "Zilo CRM Design Agent",
    }
    last_error = "Unknown error"
    for key in keys:
        for attempt in range(_MAX_RETRIES_PER_KEY):
            try:
                headers = {**base_headers, "Authorization": f"Bearer {key}"}
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                b64_data = _extract_b64_from_message((data.get("choices") or [{}])[0].get("message", {}))
                if not b64_data:
                    last_error = "No image data in edit response"
                    logger.warning("[nano_banana] edit key=...%s attempt=%d no image: %s", key[-6:], attempt + 1, str(data)[:200])
                    continue
                from image_handler import S3Handler
                filename = f"edited-product-{uuid.uuid4()}.png"
                public_url = await S3Handler.upload_file(b64_data, filename, content_type="image/png")
                if not public_url:
                    last_error = "S3 upload returned empty URL"
                    continue
                logger.info("[nano_banana] edit_product_image ok key=...%s attempt=%d", key[-6:], attempt + 1)
                return {"success": True, "image_url": public_url, "source": "gemini_edit"}
            except httpx.HTTPStatusError as e:
                body = e.response.text[:800]
                last_error = f"HTTP {e.response.status_code}: {body}"
                logger.warning("[nano_banana:edit] key=...%s attempt=%d HTTP error: %s", key[-6:], attempt + 1, last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning("[nano_banana:edit] key=...%s attempt=%d error: %s", key[-6:], attempt + 1, last_error)

    logger.error("[nano_banana] edit_product_image exhausted all keys. last=%s", last_error)
    return {"error": f"Edit generation failed after trying all API keys. Last error: {last_error}"}


def _extract_b64_from_message(message: Dict[str, Any]) -> Optional[str]:
    """Parse image data from an OpenRouter/Gemini response message.

    Handles three response shapes:
      1. message.images[0].image_url.url  (OpenRouter native)
      2. message.content = "data:image/..."  (legacy string)
      3. message.content = [{"type": "image_url", "image_url": {"url": "..."}}]  (list blocks)
    """
    images = message.get("images") or []
    if images:
        try:
            return images[0]["image_url"]["url"]
        except (KeyError, IndexError):
            pass

    content = message.get("content", "")
    if isinstance(content, str) and content.startswith("data:image"):
        return content

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "image_url":
                    url = (item.get("image_url") or {}).get("url", "")
                    if url.startswith("data:image"):
                        return url
                # Some responses embed base64 directly under "data"
                if item.get("type") == "image" and item.get("data"):
                    mime = item.get("mimeType") or item.get("mime_type") or "image/png"
                    return f"data:{mime};base64,{item['data']}"

    return None


async def generate_creative_image(
    prompt: str,
    format: str = "square",
    quality: str = "fast",
    logo_url: Optional[str] = None,
    brand_color: str = "",
    brand_color_mode: str = "dominant",
) -> Dict[str, Any]:
    """Call Nano Banana via OpenRouter to generate a creative image.
    Auto-retries across all available OPENROUTER_KEY_* env vars."""
    keys = _load_openrouter_keys()
    if not keys:
        return {"error": _OPENROUTER_KEY_MISSING}

    model = NANO_BANANA_PRO if quality == "pro" else NANO_BANANA_2
    aspect_ratio = _ASPECT_MAP.get(format, "1:1")

    # Build multimodal content — include logo and brand color as references
    mode = (brand_color_mode or "dominant").strip().lower()
    if brand_color:
        if mode == "subtle":
            color_note = (
                f"\n\nBRAND COLOUR NOTE: {brand_color} — use this only as a subtle accent "
                f"(thin rules, small highlights). Keep it under ~5% of the canvas area. "
                f"Do NOT make large geometric shapes, big gradients, or full backgrounds using this colour."
            )
        else:
            color_note = (
                f"\n\nBRAND COLOUR MANDATE: {brand_color} — use this as the dominant accent colour: "
                f"headline text, CTA button fill, and key graphic shapes. ~30% of canvas area."
            )
    else:
        color_note = ""

    if logo_url:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                logo_resp = await client.get(logo_url)
                logo_resp.raise_for_status()
                logo_b64 = base64.b64encode(logo_resp.content).decode()
                content_type = logo_resp.headers.get("content-type", "image/png").split(";")[0]
                logo_instruction = (
                    "\n\nBRAND LOGO PLACEMENT:\n"
                    "The FIRST attached image is the brand logo. You MUST render it in the final design.\n"
                    "Rules:\n"
                    "1. Find the corner or edge with the most visual breathing room.\n"
                    "2. Size it at roughly 12-16% of the canvas width — readable but not competing.\n"
                    "3. Match contrast to local background: light logo on dark areas, dark logo on light.\n"
                    "4. It must look DESIGNED-IN — part of the composition, not stamped on top.\n"
                    "5. Do NOT distort, recolour, rotate, or crop the logo shape."
                )
                message_content = [
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{logo_b64}"}},
                    {"type": "text", "text": prompt + color_note + logo_instruction},
                ]
        except Exception as e:
            logger.warning("[nano_banana] Logo fetch failed, falling back to text-only: %s", e)
            message_content = [{"type": "text", "text": prompt + color_note}]
    else:
        message_content = [{"type": "text", "text": prompt + color_note}]

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message_content}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio},
        "max_tokens": 1024,
    }
    base_headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("FRONTEND_URL", "https://zilo.pro"),
        "X-Title": "Zilo CRM Design Agent",
    }

    last_error = "Unknown error"
    for key in keys:
        for attempt in range(_MAX_RETRIES_PER_KEY):
            try:
                headers = {**base_headers, "Authorization": f"Bearer {key}"}
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()

                choices = data.get("choices", [])
                if not choices:
                    last_error = "No choices returned"
                    logger.warning("[nano_banana] key=...%s attempt=%d no choices", key[-6:], attempt + 1)
                    continue
                b64_data = _extract_b64_from_message(choices[0].get("message", {}))
                if not b64_data:
                    last_error = "No image data in response"
                    logger.warning("[nano_banana] key=...%s attempt=%d no image: %s", key[-6:], attempt + 1, str(data)[:200])
                    continue

                from image_handler import S3Handler
                filename = f"creative-{uuid.uuid4()}.png"
                public_url = await S3Handler.upload_file(b64_data, filename, content_type="image/png")
                if not public_url:
                    last_error = "S3 upload returned empty URL"
                    continue
                logger.info("[nano_banana] generate_creative_image ok key=...%s attempt=%d", key[-6:], attempt + 1)
                return {"success": True, "image_url": public_url}

            except httpx.HTTPStatusError as e:
                body = e.response.text[:800]
                last_error = f"HTTP {e.response.status_code}: {body}"
                logger.warning("[nano_banana:generate] key=...%s attempt=%d HTTP error: %s", key[-6:], attempt + 1, last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning("[nano_banana:generate] key=...%s attempt=%d error: %s", key[-6:], attempt + 1, last_error)

    logger.error("[nano_banana] generate_creative_image exhausted all keys. last=%s", last_error)
    return {"error": f"Design generation failed after trying all API keys. Last error: {last_error}"}


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
    keys = _load_openrouter_keys()
    if not keys:
        return {"error": _OPENROUTER_KEY_MISSING}
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
        "max_tokens": 1024,
    }
    base_headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("FRONTEND_URL", "https://zilo.pro"),
        "X-Title": "Zilo CRM Design Agent",
    }
    last_error = "Unknown error"
    for key in keys:
        for attempt in range(_MAX_RETRIES_PER_KEY):
            try:
                headers = {**base_headers, "Authorization": f"Bearer {key}"}
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                b64_data = _extract_b64_from_message((data.get("choices") or [{}])[0].get("message", {}))
                if not b64_data:
                    last_error = "No image data in recreate response"
                    logger.warning("[nano_banana] recreate key=...%s attempt=%d no image: %s", key[-6:], attempt + 1, str(data)[:200])
                    continue
                from image_handler import S3Handler
                filename = f"recreate-{uuid.uuid4()}.png"
                public_url = await S3Handler.upload_file(b64_data, filename, content_type="image/png")
                if not public_url:
                    last_error = "S3 upload returned empty URL"
                    continue
                logger.info("[nano_banana] recreate_design_from_reference ok key=...%s attempt=%d", key[-6:], attempt + 1)
                return {"success": True, "image_url": public_url}
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}"
                logger.warning("[nano_banana] recreate key=...%s attempt=%d HTTP error: %s", key[-6:], attempt + 1, last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning("[nano_banana] recreate key=...%s attempt=%d error: %s", key[-6:], attempt + 1, last_error)

    logger.error("[nano_banana] recreate_design_from_reference exhausted all keys. last=%s", last_error)
    return {"error": f"Recreate failed after trying all API keys. Last error: {last_error}"}
