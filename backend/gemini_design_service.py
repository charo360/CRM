"""Gemini-powered design generation for social media posts and ads.

Replaces Orshot template-based workflow with direct Gemini image generation
using carefully crafted prompts that produce professional, branded visuals.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Platform size presets ──────────────────────────────────────────────────

PLATFORM_FORMATS: Dict[str, Dict[str, str]] = {
    "instagram_post":  {"aspect": "1:1",   "label": "Instagram Feed (square)"},
    "instagram_story": {"aspect": "9:16",  "label": "Instagram Story (vertical)"},
    "facebook_post":   {"aspect": "1:1",   "label": "Facebook Post (square)"},
    "facebook_ad":     {"aspect": "1:1",   "label": "Facebook Ad (square)"},
    "tiktok":          {"aspect": "9:16",  "label": "TikTok (vertical)"},
    "youtube_thumb":   {"aspect": "16:9",  "label": "YouTube Thumbnail (landscape)"},
    "linkedin":        {"aspect": "1:1",   "label": "LinkedIn Post (square)"},
    "x_post":          {"aspect": "16:9",  "label": "X/Twitter Post (landscape)"},
    "general_square":  {"aspect": "1:1",   "label": "Square"},
    "general_story":   {"aspect": "9:16",  "label": "Story/Vertical"},
    "general_landscape": {"aspect": "16:9", "label": "Landscape"},
}

# ── Prompt templates ──────────────────────────────────────────────────────

_SOCIAL_POST_SYSTEM = (
    "You are a world-class social media graphic designer and creative director. "
    "You create stunning, professional social media post designs that look like they "
    "came from a top creative agency.\n\n"
    "DESIGN RULES — violating any of these produces a bad result:\n"
    "1. The image MUST look like a real, polished social media graphic — not a photo, "
    "not an illustration, not AI art. Think Canva/Figma-quality layout with clean typography.\n"
    "2. Include a clear VISUAL HIERARCHY: headline is the largest text, subtext is smaller, "
    "CTA or tagline is smallest. Use contrast and spacing to create this hierarchy.\n"
    "3. Use PROFESSIONAL TYPOGRAPHY: clean sans-serif fonts, proper letter-spacing, "
    "no stretched or distorted text. Text must be crisp and readable.\n"
    "4. Leave BREATHING ROOM: generous margins and padding. Do not cram text edge-to-edge.\n"
    "5. Use the brand color as the PRIMARY accent — for backgrounds, overlays, buttons, "
    "or key graphic elements. The design should feel ON-BRAND.\n"
    "6. If a product image is provided, it must be the HERO of the design — prominently "
    "placed, well-lit, unobstructed. The layout frames and supports the product.\n"
    "7. If a logo is provided, place it subtly — small, in a corner or bottom area. "
    "Do NOT make the logo the hero.\n"
    "8. NO watermarks, NO placeholder text, NO lorem ipsum. Every word must be real and intentional.\n"
    "9. The design must work at the specified aspect ratio — properly composed for that format.\n"
    "10. Background should complement the content — use gradients, subtle patterns, or clean "
    "solid colors. Never a flat boring white unless the style calls for it.\n"
)

_AD_DESIGN_SYSTEM = (
    "You are a world-class advertising creative director and graphic designer. "
    "You create high-converting ad creatives that stop the scroll and drive action.\n\n"
    "AD DESIGN RULES — violating any of these produces a bad result:\n"
    "1. The image MUST look like a real, polished ad creative — the kind you see from "
    "top brands on Facebook/Instagram. Professional layout, clean typography, strong CTA.\n"
    "2. SCROLL-STOPPING POWER: The headline must grab attention instantly. Use bold, "
    "contrasting colors for the headline against the background. Make it impossible to ignore.\n"
    "3. CLEAR VALUE PROPOSITION: The offer/benefit must be immediately visible. "
    "Use numbers, percentages, or power words (e.g. '50% OFF', 'FREE', 'NEW').\n"
    "4. STRONG CTA: Include a prominent call-to-action button or text (e.g. 'Shop Now', "
    "'Learn More', 'Get Started'). The CTA should use the brand color or a contrasting accent.\n"
    "5. PRODUCT IS HERO: If a product image is provided, it dominates the frame. "
    "The product should look premium — great lighting, clean background, professional staging.\n"
    "6. BRAND CONSISTENCY: Use the brand color as the primary accent throughout. "
    "The ad should feel unmistakably on-brand.\n"
    "7. If a logo is provided, place it small and subtle — corner or bottom. Not the hero.\n"
    "8. PROFESSIONAL TYPOGRAPHY: Clean sans-serif fonts, proper hierarchy. "
    "Headline > Offer > CTA > Fine print. No distorted or stretched text.\n"
    "9. NO watermarks, NO placeholder text, NO fake elements. Everything must be real.\n"
    "10. The design must work perfectly at the specified aspect ratio.\n"
    "11. Use urgency or scarcity cues when appropriate (limited time, while stocks last).\n"
)

_CAROUSEL_SYSTEM = (
    "You are a world-class social media carousel designer. You create multi-slide "
    "carousel posts that tell a story and keep viewers swiping.\n\n"
    "CAROUSEL DESIGN RULES:\n"
    "1. Generate ONE slide that represents the COVER/FIRST slide of the carousel. "
    "It must have a bold hook headline that makes people want to swipe.\n"
    "2. Include a visual cue that this is a carousel (e.g. 'Swipe →', '1/5', or a "
    "partial next-slide peek on the right edge).\n"
    "3. The cover slide sets the visual style — brand colors, typography, layout grid — "
    "that would carry through all slides.\n"
    "4. Follow all the same quality rules as social post design: professional typography, "
    "clean layout, brand consistency, visual hierarchy.\n"
)


def _build_post_prompt(
    *,
    headline: str,
    subtext: str = "",
    cta: str = "",
    brand_color: str = "",
    style: str = "",
    product_description: str = "",
    platform: str = "",
) -> str:
    """Build a detailed prompt for social media post generation."""
    parts = [
        "Create a professional social media post graphic with the following content:\n",
        f"HEADLINE (largest text, bold, eye-catching): \"{headline}\"",
    ]
    if subtext:
        parts.append(f"SUBTEXT (smaller, below headline): \"{subtext}\"")
    if cta:
        parts.append(f"CALL-TO-ACTION (button or emphasized text): \"{cta}\"")
    if brand_color:
        parts.append(
            f"BRAND COLOR: Use {brand_color} as the primary accent color throughout "
            f"the design — for backgrounds, overlays, buttons, graphic elements. "
            f"The design must feel on-brand with this color."
        )
    if product_description:
        parts.append(
            f"PRODUCT CONTEXT: This post promotes: {product_description}. "
            f"If a product image is provided, make it the hero of the design."
        )
    if platform:
        label = PLATFORM_FORMATS.get(platform, {}).get("label", platform)
        parts.append(f"FORMAT: Designed for {label}")
    if style:
        parts.append(f"STYLE DIRECTION: {style}")
    parts.append(
        "\nThe final image must be a polished, ready-to-post social media graphic "
        "with professional layout, clean typography, and strong visual hierarchy. "
        "No watermarks, no placeholder text."
    )
    return "\n".join(parts)


def _build_ad_prompt(
    *,
    headline: str,
    offer: str = "",
    cta: str = "Shop Now",
    brand_color: str = "",
    product_description: str = "",
    platform: str = "",
    urgency: str = "",
) -> str:
    """Build a detailed prompt for ad creative generation."""
    parts = [
        "Create a high-converting ad creative with the following content:\n",
        f"HEADLINE (bold, scroll-stopping, largest text): \"{headline}\"",
    ]
    if offer:
        parts.append(f"OFFER/VALUE PROP (prominent, eye-catching): \"{offer}\"")
    parts.append(f"CTA BUTTON (clear, actionable): \"{cta}\"")
    if urgency:
        parts.append(f"URGENCY CUE (small text, near CTA): \"{urgency}\"")
    if brand_color:
        parts.append(
            f"BRAND COLOR: Use {brand_color} as the primary accent color — "
            f"for the CTA button, headline highlights, background, and graphic elements. "
            f"The ad must feel unmistakably on-brand."
        )
    if product_description:
        parts.append(
            f"PRODUCT CONTEXT: This ad promotes: {product_description}. "
            f"If a product image is provided, it MUST be the hero — prominently displayed, "
            f"professional, well-lit. The layout frames and supports the product."
        )
    if platform:
        label = PLATFORM_FORMATS.get(platform, {}).get("label", platform)
        parts.append(f"FORMAT: Designed for {label}")
    parts.append(
        "\nThe final image must be a polished, ready-to-run ad creative with "
        "professional layout, strong visual hierarchy, scroll-stopping power, "
        "and a clear call-to-action. No watermarks, no placeholder text."
    )
    return "\n".join(parts)


def _build_carousel_prompt(
    *,
    headline: str,
    subtext: str = "",
    slide_count: int = 5,
    brand_color: str = "",
    topic: str = "",
    platform: str = "",
) -> str:
    """Build a detailed prompt for carousel cover slide generation."""
    parts = [
        "Create the COVER SLIDE (first slide) of a social media carousel post:\n",
        f"HOOK HEADLINE (bold, makes people want to swipe): \"{headline}\"",
    ]
    if subtext:
        parts.append(f"SUBTEXT: \"{subtext}\"")
    parts.append(
        f"CAROUSEL INFO: This is slide 1 of {slide_count}. "
        f"Include a visual swipe cue (e.g. 'Swipe →', '1/{slide_count}', "
        f"or a partial peek of the next slide on the right edge)."
    )
    if brand_color:
        parts.append(
            f"BRAND COLOR: Use {brand_color} as the primary accent throughout. "
            f"This cover sets the visual style for all slides."
        )
    if topic:
        parts.append(f"TOPIC: The carousel is about: {topic}")
    if platform:
        label = PLATFORM_FORMATS.get(platform, {}).get("label", platform)
        parts.append(f"FORMAT: Designed for {label}")
    parts.append(
        "\nThe final image must be a polished carousel cover slide with "
        "professional layout, bold typography, and a clear swipe cue."
    )
    return "\n".join(parts)


async def generate_social_post(
    *,
    headline: str,
    subtext: str = "",
    cta: str = "",
    brand_color: str = "",
    style: str = "",
    product_description: str = "",
    product_image_url: Optional[str] = None,
    logo_url: Optional[str] = None,
    platform: str = "instagram_post",
    quality: str = "pro",
) -> Dict[str, Any]:
    """Generate a social media post graphic using Gemini."""
    from nano_banana_service import generate_creative_image

    fmt_info = PLATFORM_FORMATS.get(platform, {"aspect": "1:1"})
    aspect_key = fmt_info["aspect"]

    # Map aspect ratio to format key used by nano_banana_service
    aspect_to_format = {"1:1": "square", "9:16": "story", "16:9": "landscape", "4:5": "portrait"}
    img_format = aspect_to_format.get(aspect_key, "square")

    prompt = _build_post_prompt(
        headline=headline,
        subtext=subtext,
        cta=cta,
        brand_color=brand_color,
        style=style,
        product_description=product_description,
        platform=platform,
    )

    system = _SOCIAL_POST_SYSTEM

    # If we have a product image, use edit_product_image for better results
    if product_image_url:
        full_prompt = f"{system}\n\n{prompt}"
        from nano_banana_service import edit_product_image
        result = await edit_product_image(
            product_image_url=product_image_url,
            scene_prompt=full_prompt,
            format=img_format,
            quality=quality,
        )
    else:
        # Text-to-image with optional logo reference
        full_prompt = f"{system}\n\n{prompt}"
        result = await generate_creative_image(
            prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
        )

    if result.get("error"):
        return result

    image_url = result["image_url"]
    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![Social Post]({image_url})",
        "platform": platform,
        "format": img_format,
    }


async def generate_ad_creative(
    *,
    headline: str,
    offer: str = "",
    cta: str = "Shop Now",
    brand_color: str = "",
    product_description: str = "",
    product_image_url: Optional[str] = None,
    logo_url: Optional[str] = None,
    platform: str = "facebook_ad",
    urgency: str = "",
    quality: str = "pro",
) -> Dict[str, Any]:
    """Generate an ad creative using Gemini."""
    from nano_banana_service import generate_creative_image

    fmt_info = PLATFORM_FORMATS.get(platform, {"aspect": "1:1"})
    aspect_key = fmt_info["aspect"]

    aspect_to_format = {"1:1": "square", "9:16": "story", "16:9": "landscape", "4:5": "portrait"}
    img_format = aspect_to_format.get(aspect_key, "square")

    prompt = _build_ad_prompt(
        headline=headline,
        offer=offer,
        cta=cta,
        brand_color=brand_color,
        product_description=product_description,
        platform=platform,
        urgency=urgency,
    )

    system = _AD_DESIGN_SYSTEM

    if product_image_url:
        full_prompt = f"{system}\n\n{prompt}"
        from nano_banana_service import edit_product_image
        result = await edit_product_image(
            product_image_url=product_image_url,
            scene_prompt=full_prompt,
            format=img_format,
            quality=quality,
        )
    else:
        full_prompt = f"{system}\n\n{prompt}"
        result = await generate_creative_image(
            prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
        )

    if result.get("error"):
        return result

    image_url = result["image_url"]
    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![Ad Creative]({image_url})",
        "platform": platform,
        "format": img_format,
    }


async def generate_carousel_cover(
    *,
    headline: str,
    subtext: str = "",
    slide_count: int = 5,
    brand_color: str = "",
    topic: str = "",
    product_image_url: Optional[str] = None,
    logo_url: Optional[str] = None,
    platform: str = "instagram_post",
    quality: str = "pro",
) -> Dict[str, Any]:
    """Generate a carousel cover slide using Gemini."""
    from nano_banana_service import generate_creative_image

    fmt_info = PLATFORM_FORMATS.get(platform, {"aspect": "1:1"})
    aspect_key = fmt_info["aspect"]

    aspect_to_format = {"1:1": "square", "9:16": "story", "16:9": "landscape", "4:5": "portrait"}
    img_format = aspect_to_format.get(aspect_key, "square")

    prompt = _build_carousel_prompt(
        headline=headline,
        subtext=subtext,
        slide_count=slide_count,
        brand_color=brand_color,
        topic=topic,
        platform=platform,
    )

    system = _CAROUSEL_SYSTEM

    if product_image_url:
        full_prompt = f"{system}\n\n{prompt}"
        from nano_banana_service import edit_product_image
        result = await edit_product_image(
            product_image_url=product_image_url,
            scene_prompt=full_prompt,
            format=img_format,
            quality=quality,
        )
    else:
        full_prompt = f"{system}\n\n{prompt}"
        result = await generate_creative_image(
            prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
        )

    if result.get("error"):
        return result

    image_url = result["image_url"]
    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![Carousel Cover]({image_url})",
        "platform": platform,
        "format": img_format,
    }


async def regenerate_with_feedback(
    *,
    original_image_url: str,
    feedback: str,
    headline: str = "",
    brand_color: str = "",
    product_image_url: Optional[str] = None,
    logo_url: Optional[str] = None,
    platform: str = "instagram_post",
    quality: str = "pro",
) -> Dict[str, Any]:
    """Regenerate a design based on user feedback, using the original as reference."""
    from nano_banana_service import recreate_design_from_reference

    fmt_info = PLATFORM_FORMATS.get(platform, {"aspect": "1:1"})
    aspect_key = fmt_info["aspect"]

    aspect_to_format = {"1:1": "square", "9:16": "story", "16:9": "landscape", "4:5": "portrait"}
    img_format = aspect_to_format.get(aspect_key, "square")

    prompt_parts = [
        "You are refining a social media design based on user feedback.\n",
        f"USER FEEDBACK: \"{feedback}\"\n",
        "Apply this feedback to improve the design. Keep everything that works, "
        "change only what the feedback asks for. Maintain professional quality, "
        "clean typography, and visual hierarchy.",
    ]
    if headline:
        prompt_parts.append(f"\nHEADLINE must remain: \"{headline}\"")
    if brand_color:
        prompt_parts.append(f"\nBRAND COLOR must remain: {brand_color}")

    result = await recreate_design_from_reference(
        reference_image_url=original_image_url,
        prompt="\n".join(prompt_parts),
        product_image_url=product_image_url,
        logo_url=logo_url,
        format=img_format,
        quality=quality,
    )

    if result.get("error"):
        return result

    image_url = result["image_url"]
    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![Updated Design]({image_url})",
        "platform": platform,
        "format": img_format,
    }
