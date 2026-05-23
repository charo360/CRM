"""
deck_content_engine.py
──────────────────────
AI Content Engine — takes a plain-English brief and produces
fully structured slide content JSON ready for deck_engine.build_deck().

Supports both Western and Africa-first business contexts.
Uses Claude (via OpenRouter) for high-quality, tightly scoped output.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

# ── OpenRouter config ─────────────────────────────────────────────────────────

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_CLAUDE_MODEL   = "anthropic/claude-sonnet-4-5"

def _get_key() -> Optional[str]:
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_KEY")


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a presentation content strategist who specialises in investor pitch decks, sales decks, and corporate presentations for both Western markets and African markets (Kenya, Nigeria, Ghana, South Africa, East/West Africa).

Given a company brief, output ONLY valid JSON matching the deck content schema below. No prose, no markdown fences, no extra text — raw JSON only.

RULES:
- If an APPROVED PLAN is provided, it is AUTHORITATIVE — follow it exactly. Use the exact slide titles, bullet points, headlines, stats, and structure the user already reviewed and approved. Do NOT invent different content or reorder anything. Only enrich with supporting detail (real numbers, one-line descriptions) while keeping every user-approved point intact.
- bullets: max 4 per slide, max 12 words each — punchy, specific, no filler
- stats: use REAL numbers only — never "X%", "TBD", or vague ranges. If unknown, use credible industry estimates and note them
- tone: match deck_type — investor = bold claims + market size; sales = client pain + ROI; corporate = data + process
- Africa-first: if region is Africa/Kenya/Nigeria/Ghana/East Africa/West Africa, use:
    * local currency context (KES, NGN, GHS, USD) where relevant  
    * Africa-specific market data (e.g. "560M mobile money users in Sub-Saharan Africa")
    * WhatsApp-first, mobile-first framing
    * local platforms (M-Pesa, Flutterwave, Paystack, etc.) where relevant
    * avoid Western-centric comparisons unless explicitly asked
- Western: if region is US/Europe/global, use standard market benchmarks

OUTPUT SCHEMA (produce exactly this structure):
{
  "title": {
    "name": "Company Name",
    "tagline": "One-line tagline",
    "website": "company.com",
    "founder": "Founder Name, Founder Title"
  },
  "problem": {
    "bullets": ["Pain point 1", "Pain point 2", "Pain point 3"],
    "stat": { "number": "XX%", "label": "Short label", "sub": "One-line context" },
    "sub": "One-line market-size hook"
  },
  "solution": {
    "items": [
      { "label": "Feature Name", "description": "One line explaining the feature" },
      { "label": "Feature Name", "description": "One line explaining the feature" },
      { "label": "Feature Name", "description": "One line explaining the feature" },
      { "label": "Feature Name", "description": "One line explaining the feature" }
    ]
  },
  "market": {
    "cards": [
      { "number": "$12B",   "label": "TAM", "sub": "Total addressable market description" },
      { "number": "$2.24B", "label": "SAM", "sub": "Serviceable addressable market description" },
      { "number": "$180M",  "label": "SOM", "sub": "Serviceable obtainable market description" }
    ]
  },
  "how_it_works": {
    "steps": [
      { "label": "Step Name", "description": "One-line explanation" },
      { "label": "Step Name", "description": "One-line explanation" },
      { "label": "Step Name", "description": "One-line explanation" },
      { "label": "Step Name", "description": "One-line explanation" }
    ]
  },
  "pricing": {
    "columns": ["Starter", "Growth", "Enterprise"],
    "features": [
      { "feature": "Feature name", "values": ["Free", "$49/mo", "Custom"] },
      { "feature": "Feature name", "values": ["5 users", "Unlimited", "Unlimited"] },
      { "feature": "Feature name", "values": ["—", "✓", "✓"] }
    ],
    "highlight_column": 1
  },
  "why_now": {
    "items": ["Traction point with real number", "Market shift or timing catalyst", "Competitive window or regulatory tailwind"],
    "stat": { "number": "3x", "label": "YoY growth", "sub": "Last 6 months" }
  },
  "team": {
    "members": [
      { "name": "Full Name", "title": "CEO & Co-Founder", "credential": "Previously X at Y company" },
      { "name": "Full Name", "title": "CTO", "credential": "Built X product at Y" }
    ]
  },
  "ask": {
    "amount": "$500K",
    "use_of_funds": ["40% — Product engineering", "35% — Sales & marketing", "25% — Operations & team"],
    "milestones": [
      { "number": "$50K", "label": "MRR target in 12 months" },
      { "number": "500",  "label": "Paying customers by Month 12" }
    ]
  },
  "closing": {
    "title": "Company Name",
    "tagline": "Tagline here",
    "cta": "Let's talk.",
    "contact": "founder@company.com  ·  +254 700 000 000"
  }
}

Omit any slides not requested. Fill every requested slide fully."""


# ── Main generation function ───────────────────────────────────────────────────

async def generate_content(
    brief: str,
    deck_type: str = "investor_pitch",
    slide_list: Optional[List[str]] = None,
    region: str = "global",
    extra_context: str = "",
    approved_plan: str = "",
) -> Dict[str, Any]:
    """
    Generate structured slide content JSON from a plain-English brief.

    Args:
        brief:         Free-text company description / brief
        deck_type:     "investor_pitch" | "sales" | "corporate" | "product_launch"
        slide_list:    Which slides to generate content for (defaults to full investor deck)
        region:        "africa" | "kenya" | "nigeria" | "west_africa" | "us" | "europe" | "global"
        extra_context: Any extra instructions (tone, style, language hints)
        approved_plan: The full slide-by-slide outline the user reviewed and approved — treated as authoritative

    Returns:
        dict with structured content per slide type, plus meta keys
    """
    key = _get_key()
    if not key:
        log.error("[deck_content] No OpenRouter API key found")
        return {"error": "OpenRouter API key not configured", "content": {}}

    if slide_list is None:
        slide_list = ["title", "problem", "solution", "market",
                      "how_it_works", "pricing", "why_now", "team", "ask", "closing"]

    region_note = _region_note(region)

    approved_section = (
        f"\n\nAPPROVED PLAN (follow this exactly — do not deviate from the structure or key points):\n{approved_plan.strip()}"
        if approved_plan.strip() else ""
    )
    extra_section = (
        f"\nAdditional context: {extra_context.strip()}"
        if extra_context.strip() else ""
    )

    user_prompt = f"""Company brief:
{brief.strip()}

Deck type: {deck_type}
Target region: {region} {region_note}
Slides needed: {", ".join(slide_list)}
{extra_section}{approved_section}

Generate the full content JSON for every slide in the list above.
"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": _CLAUDE_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                    "max_tokens": 4000,
                    "temperature": 0.4,
                },
            )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        content = _parse_json(raw)
        return {"success": True, "content": content, "region": region, "deck_type": deck_type}

    except httpx.HTTPStatusError as e:
        log.error("[deck_content] HTTP error: %s — %s", e.response.status_code, e.response.text[:300])
        return {"error": f"API error {e.response.status_code}", "content": {}}
    except Exception as e:
        log.error("[deck_content] generation failed: %s", e)
        return {"error": str(e), "content": {}}


# ── Full pipeline helper ───────────────────────────────────────────────────────

async def generate_and_build(
    brief: str,
    brand: Dict[str, Any],
    deck_type: str = "investor_pitch",
    pack: str = "bold",
    slide_list: Optional[List[str]] = None,
    region: str = "global",
    extra_context: str = "",
    approved_plan: str = "",
    export_pdf: bool = False,
    export_png: bool = False,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full pipeline: brief → AI content → PPTX (+ optional PDF/PNG).

    Returns the build_deck result dict augmented with content + any errors.
    """
    from deck_engine import build_deck_async

    # 1. Generate content
    gen = await generate_content(
        brief=brief,
        deck_type=deck_type,
        slide_list=slide_list,
        region=region,
        extra_context=extra_context,
        approved_plan=approved_plan,
    )
    if not gen.get("success"):
        return {"success": False, "error": gen.get("error", "Content generation failed")}

    content = gen["content"]

    # 2. Build deck
    config = {
        "brand":   brand,
        "deck":    {"type": deck_type, "pack": pack, "slides": slide_list or list(content.keys())},
        "content": content,
        "export_pdf": export_pdf,
        "export_png": export_png,
    }
    result = await build_deck_async(config, output_dir=output_dir)
    result["content"] = content
    return result


# ── Utilities ──────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> Dict[str, Any]:
    """Extract and parse JSON from model output — strips markdown fences."""
    text = raw.strip()
    # Strip ```json ... ``` fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find first { ... } block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        log.error("[deck_content] JSON parse failed on output:\n%s", text[:500])
        return {}


def _region_note(region: str) -> str:
    region_lower = (region or "").lower()
    africa_regions = {"africa", "kenya", "nigeria", "ghana", "south africa",
                      "east africa", "west africa", "sub-saharan africa", "nairobi", "lagos"}
    if any(r in region_lower for r in africa_regions):
        return ("— USE Africa-first framing: mobile money, WhatsApp-native, local platforms, "
                "Sub-Saharan market data, local currency where relevant.")
    if region_lower in {"us", "usa", "united states", "north america"}:
        return "— Use US market benchmarks and USD throughout."
    if region_lower in {"europe", "uk", "eu"}:
        return "— Use European market context, EUR/GBP where relevant."
    return ""
