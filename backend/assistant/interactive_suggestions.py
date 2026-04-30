"""Generate tap-to-send follow-up suggestions for interactive assistant turns.

Used for advertising specialists so users get step-by-step chips instead of only long prose.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List

logger = logging.getLogger(__name__)

AGENTS_WITH_SUGGESTION_CHIPS = frozenset({"meta_ads", "google_ads", "x_ads", "social_media", "design", "creative"})

_META_FALLBACK = [
    "Build the full ad end-to-end from my catalog (one package)",
    "Recommend which products I should advertise for my business type",
    "I'll pick the products — help me turn them into the ad",
    "Image or carousel ad — walk me through copy and structure",
    "Video or Reels-style ad — I need a script and shot ideas",
    "I have creative files — I'll attach them; align copy to them",
    "Show me a text preview of the ad, then I'll say what to tweak",
    "Create a square promo graphic for Instagram (Design agent — AI)",
    "Generate a simple slide deck outline then build the .pptx",
]

_SOCIAL_FALLBACK = [
    "Instagram Feed — square",
    "Instagram Story — full-screen vertical",
    "Facebook Post — square",
    "LinkedIn Post — square",
    "Feature a product from my catalog",
    "It's a promotion or offer",
]

_GOOGLE_FALLBACK = [
    "Next: Pick campaign type — Search, Performance Max, or Display",
    "Next: Keyword themes and negative keywords for my business",
    "Next: Budget and bidding strategy recommendation",
    "Next: Write responsive search ad headlines and descriptions",
]

_X_ADS_FALLBACK = [
    "Pick objective: reach, engagements, website clicks, or followers",
    "Suggest audience and geo for my business type",
    "Draft post copy + CTA for a single-image promoted post",
    "Image vs video — what fits this offer?",
    "Budget band and what to watch in the first week",
    "Save this plan as a draft when we agree",
]

_DESIGN_FALLBACK = [
    "Instagram Feed — square",
    "Instagram Story — full-screen vertical",
    "Facebook Post — square",
    "Show me templates to pick from",
    "You design it — surprise me",
    "Use my catalog image for this design",
]


def _ads_specialist_label(agent_id: str) -> str:
    if agent_id == "meta_ads":
        return "Meta Ads"
    if agent_id == "x_ads":
        return "X Ads"
    if agent_id in ("social_media", "creative"):
        return "Creative Director"
    if agent_id == "design":
        return "Creative Director"
    return "Google Ads"


def _fallback_chips(agent_id: str, n: int) -> List[str]:
    if agent_id == "meta_ads":
        return _META_FALLBACK[:n]
    if agent_id == "x_ads":
        return _X_ADS_FALLBACK[:n]
    if agent_id in ("social_media", "creative", "design"):
        return _DESIGN_FALLBACK[:n]
    return _GOOGLE_FALLBACK[:n]


_BLOCKED_CHIP_PATTERNS = (
    "download", "pdf", "word", "docx", "export", "save as",
    "send via", "whatsapp", "share", "email this", "print",
)

# Keywords that indicate the reply is informational/research — not an actionable step.
# When these appear, skip suggestion chips entirely so the UI stays clean.
_RESEARCH_REPLY_PATTERNS = (
    "competitor", "competitors", "competitor analysis",
    "market research", "market data", "market trends",
    "industry benchmark", "industry overview",
    "strengths", "weaknesses", "swot",
    "pricing strategy", "key observations",
    "regulations", "compliance", "tax rate",
    "exchange rate", "market share",
)


def _is_research_reply(reply: str) -> bool:
    """Return True when the assistant reply is an informational/research report."""
    lower = reply.lower()
    hits = sum(1 for p in _RESEARCH_REPLY_PATTERNS if p in lower)
    # Also treat long Markdown tables as informational
    table_rows = lower.count("| ---") + lower.count("|---")
    return hits >= 2 or table_rows >= 3


def _is_blocked_chip(text: str) -> bool:
    t = text.lower()
    if any(p in t for p in _BLOCKED_CHIP_PATTERNS):
        return True
    # Block chips containing unfilled placeholder syntax like [yourwebsite.com] or [Name]
    if re.search(r"\[.{1,60}\]", text):
        return True
    return False


def _parse_chips_json(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return []
    try:
        data = json.loads(m.group())
        chips = data.get("chips") or data.get("suggestions")
        if not isinstance(chips, list):
            return []
        out: List[str] = []
        for c in chips:
            if isinstance(c, str):
                t = c.strip()
                if t and len(t) <= 200 and not _is_blocked_chip(t):
                    out.append(t)
        return out[:6]
    except (json.JSONDecodeError, TypeError):
        return []


async def build_reply_suggestions(
    agent_id: str,
    user_message: str,
    assistant_reply: str,
) -> List[str]:
    """Return 3–5 short follow-up messages the UI can show as tap chips."""
    if agent_id not in AGENTS_WITH_SUGGESTION_CHIPS:
        return []
    reply = (assistant_reply or "").strip()
    # Never show action chips on research / analysis / competitor reports
    if _is_research_reply(reply):
        return []
    if not reply:
        return _fallback_chips(agent_id, 6 if agent_id != "google_ads" else 4)

    try:
        import os, httpx
        label = _ads_specialist_label(agent_id)

        # Phase-detection context injected per agent
        phase_guidance = ""
        if agent_id == "meta_ads":
            phase_guidance = """
READ THE CONVERSATION STATE and generate chips that ADVANCE it — never reset it.

Detect the current phase:
- Product selection shown → chips = exact product names listed + "Recommend the best one" + "Test two at once"
- Concept/scene options shown (A, B, C or more) → chips = one "Go with [option name]" chip per option listed (e.g. "Go with A — The desk moment", "Go with B — The before/after", "Go with C — The phone-in-hand") + "Mix two together" + "Describe my own"
- Concept A/B pitch shown (only 2 options) → chips = "Go with Concept A", "Go with Concept B", "Mix both", "Show a third direction"
- Concept approved, refining copy → chips = "Looks good, generate it", "Punchier headline", "Different CTA", "Try Story format"
- Design image just shown → chips = "Love it", "Headline needs work", "Try darker background", "Second version", "Write Meta Ads copy"
- Open strategy talk → chips = "Let's build the creative", "What audience to target?", "Suggest a budget"

CRITICAL: Count the EXACT number of options (A, B, C...) in the reply and produce one chip per option. Never drop an option.
NEVER show "Build the full ad end-to-end" or "Recommend which products" once the conversation has started — those are reset chips, not progression chips.
"""
        elif agent_id in ("social_media", "creative", "design"):
            phase_guidance = """
Chips must match the CURRENT conversation phase:
- Asking platform/format → chips = the format options ("Instagram Feed", "Story", "Facebook Post", etc.)
- Scene/concept options shown (A, B, C or more) → chips = one chip per option listed (e.g. "Go with A — The desk moment") — include ALL options shown, never skip one
- Concept A/B pitch shown (only 2 options) → "Go with Concept A", "Go with Concept B", "Mix both", "Third direction"
- Copy proposed → "Looks good, generate it", "Change headline", "Different tone", "Punchier hook"
- Design just shown → "Love it", "Headline needs work", "Try darker colours", "Different layout", "Story version"
"""
        elif agent_id == "x_ads":
            phase_guidance = "Chips should advance: objective → audience/geo → copy+CTA → image vs video → budget → save draft."
        elif agent_id == "google_ads":
            phase_guidance = "Chips should advance: campaign type → keywords → budget/bidding → RSA copy → extensions."

        prompt = f"""You are generating tap-to-send reply chips for a user chatting with the {label} specialist in Zilo Chat.

User's last message:
{user_message[:600]}

Assistant's reply:
{reply[:3000]}

{phase_guidance}

Output 4 to 6 short chips the user can tap to continue. Rules:
- Each chip ≤ 90 characters, written in first person as if the user is speaking
- Chips must advance the conversation to the NEXT step — never offer what was just answered
- No numbering inside chip text
- No file/download/share actions
- Do NOT repeat options already listed as bullets in the assistant reply
- JSON only, one line: {{"chips": ["...", "...", "..."]}}"""

        # Use DeepSeek (same provider the assistant uses) — fast model for chips
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        openrouter_key = os.environ.get("OPENROUTER_KEY", "").strip()

        raw = None
        if deepseek_key:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {deepseek_key}"},
                    json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.4, "max_tokens": 200},
                )
                r.raise_for_status()
                raw = r.json()["choices"][0]["message"]["content"]
        elif openai_key:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.4, "max_tokens": 200},
                )
                r.raise_for_status()
                raw = r.json()["choices"][0]["message"]["content"]
        elif openrouter_key:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openrouter_key}"},
                    json={"model": "google/gemini-flash-1.5", "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.4, "max_tokens": 200},
                )
                r.raise_for_status()
                raw = r.json()["choices"][0]["message"]["content"]

        if raw:
            chips = _parse_chips_json(raw)
            if len(chips) >= 3:
                return chips[:6]
            logger.warning("[interactive_suggestions] parsed < 3 chips from: %s", raw[:200])

    except Exception as exc:
        logger.warning("[interactive_suggestions] LLM chips failed: %s", exc)

    return _fallback_chips(agent_id, 6)
