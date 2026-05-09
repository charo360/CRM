"""Gemini-powered design generation for social media posts and ads.

Produces Canva/Apple-level professional designs: minimal, focused, artifact-free.
Every prompt goes through a 3-phase design brief: Analyse → Compose → Render.
Variety system ensures no two designs ever look the same.
"""
from __future__ import annotations

import logging
import random
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Layout archetypes — rotated randomly to guarantee variety ─────────────
# Each archetype defines a fundamentally different visual structure.
# The AI must follow the chosen archetype precisely.

_LAYOUT_ARCHETYPES = [
    {
        "name": "Split Horizon",
        "description": (
            "Canvas split horizontally 50/50. Top half: bold headline in large type, "
            "high contrast against a deep background. Bottom half: product image or lifestyle visual "
            "bleeding edge-to-edge. CTA floats at the horizontal split line as an overlapping button. "
            "Logo top-left, very small."
        ),
    },
    {
        "name": "Cinematic Frame",
        "description": (
            "Full-bleed dramatic background (deep colour or lifestyle scene) with a thin "
            "letterbox-style semi-transparent bar at the bottom third. Headline text sits inside "
            "this bar — clean, wide-spaced. Product image centred in the upper two-thirds, "
            "large and unobstructed. Feels like a movie poster."
        ),
    },
    {
        "name": "Asymmetric Bold",
        "description": (
            "Product or hero image anchored hard to the LEFT edge, cut off slightly, "
            "taking 55% of canvas width. Right side: clean light or brand-colour panel with "
            "vertically stacked headline (large) → subtext (small) → CTA button. "
            "Strong contrast between image side and text side. No centre alignment."
        ),
    },
    {
        "name": "Typographic Dominance",
        "description": (
            "NO product image visible — the headline IS the visual. Oversized bold type "
            "fills 70% of the canvas. A single power word or number is treated in the brand colour "
            "while the rest is white or black. Background is one deep solid or dramatic gradient. "
            "Subtext and CTA in small, quiet type at bottom. "
            "Inspired by Apple launch slides and NY Times ads."
        ),
    },
    {
        "name": "Hero Float",
        "description": (
            "Pure white or very light neutral background. Product image centred and large, "
            "slightly above vertical centre, with a clean drop shadow for depth. "
            "Headline above product in dark bold type. CTA pill-button below product. "
            "Generous white space surrounds everything. Clean, premium, Apple store feel."
        ),
    },
    {
        "name": "Diagonal Energy",
        "description": (
            "A bold diagonal stripe or colour block cuts across the canvas at 30–40 degrees. "
            "Brand colour dominates one triangle, neutral/white the other. "
            "Headline sits in the brand-colour zone in white or light type. "
            "Product image in the neutral zone at a 3/4 angle. Dynamic, energetic, stops the scroll."
        ),
    },
    {
        "name": "Immersive Scene",
        "description": (
            "Full-bleed lifestyle or studio photography as the background (or AI-generated scene). "
            "Headline text overlaid in the top third with a subtle dark scrim behind it for readability. "
            "CTA button bottom centre. Product integrated naturally into the scene — not pasted on top. "
            "Feels editorial, like a magazine double-page spread condensed to a square."
        ),
    },
    {
        "name": "Minimal Badge",
        "description": (
            "Mostly negative space — 65%+ of canvas is clean background. "
            "A single centred circular or rounded-square 'badge' shape in brand colour "
            "contains the offer or key number (e.g. '$20', '50% OFF', 'FREE'). "
            "Headline above badge. CTA below badge. Product image is a small, sharp thumbnail "
            "inside or beside the badge. Quiet confidence — zero clutter."
        ),
    },
]

# ── Scroll-stopping psychological triggers ────────────────────────────────
# One is injected per generation to create pattern interrupts.

_SCROLL_STOP_TRIGGERS = [
    "Pattern interrupt: include one unexpected visual element — an unusual crop, "
    "an oversized single character, or a stark colour contrast that breaks the viewer's visual rhythm.",

    "Contrast shock: make the dominant colour pairing extremely high contrast — "
    "e.g. pitch black background with electric brand-colour text, or pure white with deep navy. "
    "No soft pastels. Make the viewer's eye snap to it.",

    "Scale surprise: make the headline text dramatically larger than expected — "
    "so large it crops slightly at the canvas edges. The oversized type IS the scroll-stopper.",

    "Negative space tension: leave so much breathing room that the single central element "
    "feels isolated and powerful. The emptiness creates curiosity and draws the eye to what IS there.",

    "Bold number: if there is a price, discount, or stat — make it the single largest element "
    "on the canvas, rendered in the brand colour, minimum 3× the size of the headline. "
    "Numbers stop scrollers instantly.",

    "Unexpected angle: render the product from an unusual but intentional camera angle — "
    "extreme low angle looking up (dominating, premium), or a dramatic overhead flat-lay "
    "with intentional shadow play. Avoid the predictable 3/4 front view.",

    "Colour field: use one single solid colour field that occupies 70%+ of the canvas. "
    "Choose a colour that is unusual for this product category — it creates curiosity. "
    "The rest of the design is minimal on top of this field.",
]

# ── Platform size presets ──────────────────────────────────────────────────

PLATFORM_FORMATS: Dict[str, Dict[str, str]] = {
    "instagram_post":    {"aspect": "1:1",   "label": "Instagram Feed (square)"},
    "instagram_story":   {"aspect": "9:16",  "label": "Instagram Story (vertical)"},
    "facebook_post":     {"aspect": "1:1",   "label": "Facebook Post (square)"},
    "facebook_ad":       {"aspect": "1:1",   "label": "Facebook Ad (square)"},
    "tiktok":            {"aspect": "9:16",  "label": "TikTok (vertical)"},
    "youtube_thumb":     {"aspect": "16:9",  "label": "YouTube Thumbnail (landscape)"},
    "linkedin":          {"aspect": "1:1",   "label": "LinkedIn Post (square)"},
    "x_post":            {"aspect": "16:9",  "label": "X/Twitter Post (landscape)"},
    "general_square":    {"aspect": "1:1",   "label": "Square"},
    "general_story":     {"aspect": "9:16",  "label": "Story/Vertical"},
    "general_landscape": {"aspect": "16:9",  "label": "Landscape"},
}

# ── Master design philosophy injected into every prompt ──────────────────

_MASTER_RULES = """
UNIVERSAL DESIGN LAWS — break any of these and the output is rejected:

SIMPLICITY (most important rule):
• ONE message per design. One hero, one headline, one action. Nothing more.
• Maximum 3 text elements total on the entire canvas (headline + subtext + CTA).
• At least 55% of the canvas must be negative space — breathing room is power.
• If it doesn't need to be there, remove it. Every element must earn its place.
• FORBIDDEN: decorative dividers, unnecessary icons, filler shapes, busy patterns,
  drop shadows on everything, multiple competing focal points, text walls.

COMPOSITION & CAMERA ANGLES:
• Apply the Rule of Thirds — place the subject at a grid intersection, not dead-center.
• For product shots: use a 3/4 angle (45°) to show depth and dimension.
  Alternatively use a low camera angle (looking slightly up) for a premium, powerful feel.
  Use flat-lay / overhead ONLY for lifestyle or food contexts.
• For lifestyle scenes: use an eye-level angle that feels natural and relatable.
• Visual flow must guide the eye: large element → medium element → CTA. Left-to-right or
  top-to-bottom. Never random placement.
• Frame the subject with intentional negative space — let it breathe.

TYPOGRAPHY (non-negotiable):
• Maximum 2 typefaces. One display font for the headline, one clean sans-serif for body.
• Font size hierarchy: headline is 3× the size of subtext. Subtext is 2× the CTA label.
• Text must contrast at WCAG AA minimum (4.5:1 ratio) against its background.
• Never stretch, skew, or distort type. Proper letter-spacing. Crisp edges.
• Zero lorem ipsum. Zero placeholder text. Every word is real.

COLOUR (60-30-10 rule):
• 60% dominant neutral or background tone.
• 30% brand colour used intentionally (headline, key shape, overlay).
• 10% accent — white, black, or a complementary pop colour — for CTA or highlight.
• Maximum 3 colours total on the canvas.

TECHNICAL QUALITY:
• Photorealistic product renders: no blurring, no haloing, no AI smearing around edges.
• Typography: pixel-perfect edges, no anti-aliasing artifacts, no ghosting.
• Colour banding: none. Gradients must be smooth.
• The canvas must reach all four edges — no white borders, no vignette bleed,
  no unintended transparent areas.
• Logo (if present): placed bottom-left or bottom-right, small (≤12% canvas width),
  never competing with the headline.
"""

# ── System prompts per design type ────────────────────────────────────────

_SOCIAL_POST_SYSTEM = (
    "You are the creative director at a world-class design studio — think Apple, Nike, Airbnb. "
    "You produce scroll-stopping social media graphics that look indistinguishable from "
    "professional Canva Pro or Figma designs made by a senior designer.\n\n"
    "Before rendering anything, silently run this 3-phase brief:\n"
    "  PHASE 1 — ANALYSE: What is the single core message? Who is the audience? "
    "What emotion should they feel in the first 0.3 seconds?\n"
    "  PHASE 2 — COMPOSE: Choose the layout (Z-pattern, F-pattern, or centred focal). "
    "Decide the camera angle for any product. Set the colour palette. "
    "Pick the dominant typographic style. Define negative space zones.\n"
    "  PHASE 3 — RENDER: Produce the final image following every rule below.\n\n"
    + _MASTER_RULES
    + "\nSOCIAL POST SPECIFIC RULES:\n"
    "• The design must feel native to social media — not like a flyer or a PowerPoint slide.\n"
    "• Mood and aesthetic consistency: every element (colour, type, imagery) speaks the same visual language.\n"
    "• Background must be intentional: deep solid, soft gradient, subtle texture, or full bleed lifestyle photo.\n"
    "  Never a flat plain white unless explicitly part of a clean minimalist concept.\n"
    "• If a product image is provided: it occupies 40–60% of the canvas, sharply rendered, "
    "  no background bleed, placed at a Rule-of-Thirds intersection.\n"
)

_AD_DESIGN_SYSTEM = (
    "You are the lead creative director at a performance-marketing agency. "
    "Your ads have generated millions in revenue because they follow one rule: "
    "CLARITY converts. Complexity kills.\n\n"
    "Before rendering, silently run this 3-phase brief:\n"
    "  PHASE 1 — ANALYSE: What is the single, undeniable value to the customer? "
    "What objection does this ad pre-empt? What action do we want in 1 second?\n"
    "  PHASE 2 — COMPOSE: Choose the dominant visual (product hero or bold typographic). "
    "Select the camera angle that makes the product look premium. "
    "Define where the eye lands first, second, third. Lock the colour palette.\n"
    "  PHASE 3 — RENDER: Produce the final ad following every rule below.\n\n"
    + _MASTER_RULES
    + "\nAD-SPECIFIC RULES:\n"
    "• The headline must be readable in 1 second by someone scrolling fast — large, bold, high contrast.\n"
    "• The CTA must look like a real button: rounded rectangle, brand colour fill, white label text, "
    "  subtle depth. Placed in the bottom third of the canvas.\n"
    "• Facebook/Instagram 20% text rule: text elements combined cover less than 20% of the canvas area.\n"
    "• Product photography style: studio-quality lighting, clean shadow, premium staging. "
    "  Use a 3/4 camera angle (45°) or a low-angle hero shot. Never a flat top-down unless it's food/flat-lay.\n"
    "• One single offer. Not two. Not three. One. Make it big, make it clear.\n"
    "• Urgency cue (if used): small text, max 2 words, placed directly below the CTA button.\n"
    "• The ad must look like it belongs on the feed of a premium brand — not a local print shop flyer.\n"
)

_CAROUSEL_SYSTEM = (
    "You are a world-class carousel designer for Instagram and LinkedIn. "
    "Your carousel covers make people stop mid-scroll and swipe.\n\n"
    "Before rendering, silently run this 3-phase brief:\n"
    "  PHASE 1 — ANALYSE: What bold promise or intriguing question does this cover make? "
    "Why would someone swipe? What visual style carries across all slides?\n"
    "  PHASE 2 — COMPOSE: Layout the hook headline for maximum impact. "
    "Choose a background that sets the tone for the whole series. "
    "Place a subtle swipe cue that doesn't clutter.\n"
    "  PHASE 3 — RENDER: Produce the cover following every rule below.\n\n"
    + _MASTER_RULES
    + "\nCAROUSEL COVER SPECIFIC RULES:\n"
    "• The hook headline is the ONLY hero — it takes 50–60% of vertical space, centre-aligned or "
    "  slightly above centre.\n"
    "• Swipe cue: a single subtle arrow '›' or 'Swipe' label in the bottom-right corner only. "
    "  Small. Understated. It doesn't compete with the headline.\n"
    "• Slide counter (e.g. '1/5'): top-right corner, very small, secondary colour. Optional.\n"
    "• The visual style established here (colours, type, layout rhythm) must be repeatable "
    "  across all subsequent slides — think of this as the design system cover.\n"
)


# ── Prompt builders ────────────────────────────────────────────────────────

def _pick_archetype(exclude_name: str = "") -> dict:
    """Pick a random layout archetype, optionally avoiding the last used one."""
    choices = [a for a in _LAYOUT_ARCHETYPES if a["name"] != exclude_name]
    return random.choice(choices)


def _build_post_prompt(
    *,
    headline: str,
    subtext: str = "",
    cta: str = "",
    brand_color: str = "",
    style: str = "",
    product_description: str = "",
    platform: str = "",
    trend_context: str = "",
    archetype: Optional[dict] = None,
) -> str:
    label = PLATFORM_FORMATS.get(platform, {}).get("label", platform or "square")
    arch = archetype or _pick_archetype()
    scroll_trigger = random.choice(_SCROLL_STOP_TRIGGERS)

    parts = [
        f"FORMAT: {label}",
        "",
        "CONTENT (use exactly as written — no paraphrasing, no additions):",
        f"  HEADLINE → \"{headline}\"",
    ]
    if subtext:
        parts.append(f"  SUBTEXT  → \"{subtext}\"")
    if cta:
        parts.append(f"  CTA      → \"{cta}\"")

    parts.append("")
    parts.append("DESIGN BRIEF:")
    if brand_color:
        parts.append(
            f"  Brand colour: {brand_color}  "
            f"(30% of canvas — apply to headline, key shape, or overlay; "
            f"background should be a deep/light variant or neutral that complements it)"
        )
    if style:
        parts.append(f"  Style direction: {style}")
    if product_description:
        parts.append(
            f"  Product context: {product_description} — if a product image is attached, "
            f"it is the hero at a 3/4 camera angle, occupying 40-55% of canvas, "
            f"placed at a Rule-of-Thirds intersection."
        )
    if trend_context:
        parts.append(f"  Trend context (incorporate these insights naturally): {trend_context}")

    parts += [
        "",
        f"LAYOUT ARCHETYPE — you MUST use this exact layout structure:",
        f"  Name: {arch['name']}",
        f"  Structure: {arch['description']}",
        "",
        "SCROLL-STOP REQUIREMENT — this design must be impossible to scroll past:",
        f"  {scroll_trigger}",
        "",
        "UNIQUENESS MANDATE:",
        "  This design must look completely different from a standard social media post template.",
        "  Do not use: centred text on a plain gradient background, basic card layouts, ",
        "  or anything that looks like a Canva starter template. Be bold and unexpected.",
        "",
        "  • Logo (if provided): bottom corner, ≤10% canvas width, subtle.",
        "",
        "OUTPUT: a single polished social media graphic — pixel-perfect, no artifacts, "
        "no AI smearing, no borders, no watermarks.",
    ]
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
    trend_context: str = "",
    archetype: Optional[dict] = None,
) -> str:
    label = PLATFORM_FORMATS.get(platform, {}).get("label", platform or "square")
    arch = archetype or _pick_archetype()
    scroll_trigger = random.choice(_SCROLL_STOP_TRIGGERS)

    parts = [
        f"FORMAT: {label}",
        "",
        "AD CONTENT (exact — do not alter or add words):",
        f"  HEADLINE → \"{headline}\"",
    ]
    if offer:
        parts.append(f"  OFFER    → \"{offer}\"  (large, bold, high contrast — second most prominent element)")
    parts.append(f"  CTA      → \"{cta}\"  (inside a rounded-rectangle button, bottom third of canvas)")
    if urgency:
        parts.append(f"  URGENCY  → \"{urgency}\"  (tiny text, directly below CTA button)")

    parts.append("")
    parts.append("DESIGN BRIEF:")
    if brand_color:
        parts.append(
            f"  Brand colour: {brand_color}  "
            f"(CTA button fill + one accent zone; rest of canvas is neutral/deep background "
            f"that makes this colour pop)"
        )
    if product_description:
        parts.append(
            f"  Product: {product_description}  "
            f"→ if product image attached: place it as the visual hero, 3/4 angle (45°) "
            f"or low-angle hero shot, sharp edges, studio lighting, "
            f"occupying 45-60% of canvas at a Rule-of-Thirds intersection."
        )
    if trend_context:
        parts.append(f"  Trend context (use these insights to make the ad feel current): {trend_context}")

    parts += [
        "",
        f"LAYOUT ARCHETYPE — you MUST build this ad using this exact layout structure:",
        f"  Name: {arch['name']}",
        f"  Structure: {arch['description']}",
        "",
        "SCROLL-STOP REQUIREMENT — this ad must make someone stop mid-scroll:",
        f"  {scroll_trigger}",
        "",
        "UNIQUENESS MANDATE:",
        "  This must look like an ad from a top-tier brand with an in-house creative team.",
        "  Not a Canva template. Not a generic Facebook ad. Something that makes the viewer think",
        "  'who made this?' because it looks so distinctive and intentional.",
        "",
        "  • Text covers < 20% of total canvas area (Meta ad guideline).",
        "  • ONE focal point only. Remove anything that doesn't serve the single message.",
        "",
        "OUTPUT: a single high-converting ad creative — indistinguishable from a top-brand Meta ad. "
        "No artifacts, no AI smearing, no fake elements, no watermarks.",
    ]
    return "\n".join(parts)


def _build_carousel_prompt(
    *,
    headline: str,
    subtext: str = "",
    slide_count: int = 5,
    brand_color: str = "",
    topic: str = "",
    platform: str = "",
    trend_context: str = "",
    archetype: Optional[dict] = None,
) -> str:
    label = PLATFORM_FORMATS.get(platform, {}).get("label", platform or "square")
    arch = archetype or _pick_archetype()
    scroll_trigger = random.choice(_SCROLL_STOP_TRIGGERS)

    parts = [
        f"FORMAT: {label}  — COVER SLIDE (slide 1 of {slide_count})",
        "",
        "CONTENT:",
        f"  HOOK HEADLINE → \"{headline}\"",
    ]
    if subtext:
        parts.append(f"  SUBTEXT       → \"{subtext}\"")
    if topic:
        parts.append(f"  TOPIC         → {topic}")

    parts.append("")
    parts.append("DESIGN BRIEF:")
    if brand_color:
        parts.append(
            f"  Brand colour: {brand_color}  "
            f"(headline accent or background — this colour defines the entire series)"
        )
    if trend_context:
        parts.append(f"  Trend context: {trend_context}")

    parts += [
        "",
        f"LAYOUT ARCHETYPE — build this cover using this structure:",
        f"  Name: {arch['name']}",
        f"  Structure: {arch['description']}",
        "",
        "SCROLL-STOP REQUIREMENT:",
        f"  {scroll_trigger}",
        "",
        f"  • Swipe cue: a single '›' arrow or 'Swipe' — bottom-right only, very small.",
        f"  • Slide counter '1/{slide_count}': top-right, tiny, secondary colour. Optional.",
        "  • No clutter. Hook headline must hit in under 1 second.",
        "",
        "OUTPUT: a single cover slide — minimal, bold, unmistakably unique. No watermarks, no artifacts.",
    ]
    return "\n".join(parts)


# ── Generation functions ───────────────────────────────────────────────────

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
    quality: str = "fast",
    trend_context: str = "",
) -> Dict[str, Any]:
    """Generate a social media post graphic using Gemini."""
    from nano_banana_service import generate_creative_image, edit_product_image

    fmt_info = PLATFORM_FORMATS.get(platform, {"aspect": "1:1"})
    aspect_key = fmt_info["aspect"]
    aspect_to_format = {"1:1": "square", "9:16": "story", "16:9": "landscape", "4:5": "portrait"}
    img_format = aspect_to_format.get(aspect_key, "square")

    arch = _pick_archetype()
    logger.info("[design] social post archetype: %s", arch["name"])
    prompt = _build_post_prompt(
        headline=headline,
        subtext=subtext,
        cta=cta,
        brand_color=brand_color,
        style=style,
        product_description=product_description,
        platform=platform,
        trend_context=trend_context,
        archetype=arch,
    )
    full_prompt = f"{_SOCIAL_POST_SYSTEM}\n\n{prompt}"

    if product_image_url:
        result = await edit_product_image(
            product_image_url=product_image_url,
            scene_prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
            brand_color=brand_color,
        )
    else:
        result = await generate_creative_image(
            prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
            brand_color=brand_color,
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
    quality: str = "fast",
    trend_context: str = "",
) -> Dict[str, Any]:
    """Generate an ad creative using Gemini."""
    from nano_banana_service import generate_creative_image, edit_product_image

    fmt_info = PLATFORM_FORMATS.get(platform, {"aspect": "1:1"})
    aspect_key = fmt_info["aspect"]
    aspect_to_format = {"1:1": "square", "9:16": "story", "16:9": "landscape", "4:5": "portrait"}
    img_format = aspect_to_format.get(aspect_key, "square")

    arch = _pick_archetype()
    logger.info("[design] ad creative archetype: %s", arch["name"])
    prompt = _build_ad_prompt(
        headline=headline,
        offer=offer,
        cta=cta,
        brand_color=brand_color,
        product_description=product_description,
        platform=platform,
        urgency=urgency,
        trend_context=trend_context,
        archetype=arch,
    )
    full_prompt = f"{_AD_DESIGN_SYSTEM}\n\n{prompt}"

    if product_image_url:
        result = await edit_product_image(
            product_image_url=product_image_url,
            scene_prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
            brand_color=brand_color,
        )
    else:
        result = await generate_creative_image(
            prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
            brand_color=brand_color,
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
    quality: str = "fast",
) -> Dict[str, Any]:
    """Generate a carousel cover slide using Gemini."""
    from nano_banana_service import generate_creative_image, edit_product_image

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
    full_prompt = f"{_CAROUSEL_SYSTEM}\n\n{prompt}"

    if product_image_url:
        result = await edit_product_image(
            product_image_url=product_image_url,
            scene_prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
            brand_color=brand_color,
        )
    else:
        result = await generate_creative_image(
            prompt=full_prompt,
            format=img_format,
            quality=quality,
            logo_url=logo_url,
            brand_color=brand_color,
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
    quality: str = "fast",
) -> Dict[str, Any]:
    """Regenerate a design based on user feedback, using the original as reference."""
    from nano_banana_service import recreate_design_from_reference

    fmt_info = PLATFORM_FORMATS.get(platform, {"aspect": "1:1"})
    aspect_key = fmt_info["aspect"]
    aspect_to_format = {"1:1": "square", "9:16": "story", "16:9": "landscape", "4:5": "portrait"}
    img_format = aspect_to_format.get(aspect_key, "square")

    prompt_parts = [
        "You are refining a professional social media design based on user feedback.\n",
        "Apply ONLY the changes the feedback requests. Keep everything else exactly as it is.",
        f"\nUSER FEEDBACK: \"{feedback}\"\n",
        "Maintain: professional typography, clean layout, visual hierarchy, breathing room, "
        "no clutter, no artifacts. The result must match or exceed the original quality.",
    ]
    if headline:
        prompt_parts.append(f"\nHEADLINE must stay exactly: \"{headline}\"")
    if brand_color:
        prompt_parts.append(f"\nBRAND COLOUR must stay: {brand_color}")

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
