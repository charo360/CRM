"""Generate tap-to-send follow-up suggestions for interactive assistant turns.

Fully AI-driven — no hardcoded fallback arrays or pattern matching.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List

logger = logging.getLogger(__name__)

AGENTS_WITH_SUGGESTION_CHIPS = frozenset({"meta_ads", "google_ads", "x_ads", "social_media", "design", "creative"})


def _agent_label(agent_id: str) -> str:
    return {
        "meta_ads": "Meta Ads",
        "x_ads": "X Ads",
        "google_ads": "Google Ads",
        "social_media": "Creative Director",
        "creative": "Creative Director",
        "design": "Creative Director",
    }.get(agent_id, "Zilo")


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
                # Drop unfilled placeholders like [yourwebsite.com]
                if t and len(t) <= 200 and not re.search(r"\[.{1,60}\]", t):
                    out.append(t)
        return out[:6]
    except (json.JSONDecodeError, TypeError):
        return []


async def build_reply_suggestions(
    agent_id: str,
    user_message: str,
    assistant_reply: str,
) -> List[str]:
    """Return 4–6 short follow-up messages the UI can show as tap chips. Fully AI-generated."""
    if agent_id not in AGENTS_WITH_SUGGESTION_CHIPS:
        return []
    reply = (assistant_reply or "").strip()
    if not reply:
        return []

    try:
        import os, httpx
        label = _agent_label(agent_id)

        prompt = f"""You are generating tap-to-send reply chips for a user chatting with the {label} specialist inside Zilo, a CRM platform.

User's last message:
{user_message[:600]}

Assistant's reply:
{reply[:3000]}

Your job: read the conversation and produce chips that naturally advance it to the next logical step.

Core rules:
1. Match the exact phase of the conversation:
   - If the reply is asking the user to choose a platform or format → chips = the exact options listed.
   - If the reply shows multiple copy/headline/tagline/concept options (numbered 1/2/3, A/B/C, 🥇/🎯/⚡, or any labelled list) → produce one "Go with [label] — [first 5 words]" chip per option shown (count every one, never drop any), plus one "Try a different angle" chip at the end. Never show generic editing chips like "Change headline" or "Different tone" at this stage.
   - If a single concept/copy has been agreed and generation is next → "Looks good, generate it", then 2–3 refinement options.
   - If a design image was just shown → chips to react to it (approve, tweak headline, colours, layout, different format).
   - If the reply is open strategy discussion → chips to move toward a concrete next decision.
   - If the reply is purely informational (research report, competitor analysis, market data, long tables) → output {{"chips": []}} — no chips.
2. Each chip ≤ 90 characters, written in first person as if the user is speaking.
3. Chips advance the conversation — never repeat what was just answered.
4. Never suggest downloading, exporting, sharing, or sending files.
5. Never include unfilled placeholder text like [product name] or [your website].

Output JSON only, one line: {{"chips": ["...", "...", "..."]}}"""

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
            if chips:
                return chips[:6]
            logger.warning("[interactive_suggestions] parsed 0 chips from: %s", raw[:200])

    except Exception as exc:
        logger.warning("[interactive_suggestions] LLM chips failed: %s", exc)

    return []
