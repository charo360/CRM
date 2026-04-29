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
        from ai_service import get_drafter

        ai = get_drafter()
        label = _ads_specialist_label(agent_id)
        extra_x = ""
        if agent_id == "x_ads":
            extra_x = """
For X Ads, chips should cover: objective choice, audience/geo, post copy + CTA, image vs video, budget/metrics, save draft.
"""
        extra_meta = ""
        if agent_id == "meta_ads":
            extra_meta = """
For Meta Ads, mix **step-by-step** options with **branch** options when relevant, e.g.:
- full campaign from catalog in one go
- "suggest which products to advertise" using business type
- user picks products themselves
- image vs video / creative upload vs generate copy
- "show preview then I'll tweak"
- save draft when a plan exists
- **Visuals:** Suggest "Create a graphic" (Design agent — `generate_ad_creative` / `generate_social_post`, or `create_business_document` for PDF).
"""
        extra_social = ""
        if agent_id in ("social_media", "creative"):
            extra_social = """
For Social Media, chips must match what the assistant is CURRENTLY asking — not generic social topics.
- If the assistant is asking about **platform or format** (e.g. "square or landscape?", "Feed or Story?"): chips = the format options themselves ("Square", "Landscape", "Feed", "Story — vertical", etc.)
- If the assistant is asking **what the post is about** (product, promo, announcement): chips = the real options listed in the reply, or "Feature a product", "Announce a promotion", "Share an update"
- If the assistant just **showed templates**: chips = template names from the reply, plus "See more options"
- If the assistant just **proposed copy**: chips = "Looks good, let's render", "Change the headline", "Different tone", "Add a CTA"
- If the assistant just **showed the final design**: chips = "Love it", "Try a different template", "Tweak the copy", "Post this now"
- Only fall back to brainstorming/hashtag/caption chips when the conversation is truly open-ended (no specific question pending).
"""
        extra_google = ""
        if agent_id == "google_ads":
            extra_google = """
For Google Ads, chips should move the user toward: campaign type, keywords/negatives, bidding/budget, RSA copy, or extensions.
"""
        extra_design = ""
        if agent_id in ("design", "creative"):
            extra_design = """
For the Creative Director (Design), chips must match the current phase of the conversation:
- Phase 1a (no product picked yet): offer real product names from the reply if listed, or "Show my catalog".
- Phase 1b (product picked, asking platform): offer platform+format options — "Instagram Feed", "Instagram Story", "Facebook Post", "TikTok", "Pinterest".
- Phase 1c (platform locked, choose path): "Show me templates", "You design it — surprise me".
- Phase 1d (template locked, copy): "Love it, let's go", "Try a different angle", "Change the headline", "Skip the offer line".
- Phase 1e (brief shown, awaiting green-light): "Yes, let's render it", "Change the platform", "Swap the template".
- Phase 3 (design shown): "Love it — finalise", "Try a different headline", "Two variants please", "Different template".
Keep chips ≤ 80 characters. Sound like a human tapping a quick reply, not a menu label.
"""
        prompt = f"""The user is in Zilo Chat with the {label} specialist.

User said (last message):
{user_message[:800]}

Assistant just replied (excerpt):
{reply[:3500]}

Produce **4 to 6** **very short** follow-up messages the user can **tap to send**. Sound natural (first person), not robotic.
{extra_meta}{extra_google}{extra_x}{extra_social}{extra_design}
Rules:
- Each chip ≤ 100 characters if possible.
- No "1." numbering inside chip text.
- Chips are conversation replies ONLY — things the user would say to continue the chat.
- NEVER suggest file or sharing actions: no "Download as", "PDF", "Word", "DOCX", "Send via WhatsApp", "Export", "Save as", "Share", or any variation. Those are UI buttons, not conversation replies.
- NEVER repeat a chip that is already a bullet option in the assistant reply — the UI already renders those as tappable chips. Only add chips for paths NOT already listed.
- If the assistant reply lists product names as options, echo the product names as chips (so they match exactly what the user sees).
- JSON only, one line:
{{"chips": ["...", "...", "...", "...", "..."]}}
"""
        raw = await ai._call_llm(prompt, model_pref="standard")
        chips = _parse_chips_json(raw)
        if len(chips) >= 3:
            return chips[:6]
    except Exception as exc:
        logger.warning("[interactive_suggestions] LLM chips failed: %s", exc)

    return _fallback_chips(agent_id, 6)
