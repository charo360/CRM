"""Critic agent — reviews the Executor's draft before it is returned to the user.

Checks for: accuracy vs. retrieved knowledge, appropriate tone, completeness,
and safety (no hallucinated prices, policies, or commitments).

Scoped to Zilo Chat only. Gated by the CRITIC_ENABLED env flag (default: false)
so it can be rolled out gradually after latency profiling.

On any failure, the original draft is returned unchanged — the Critic never
blocks the response path.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

CRITIC_SYSTEM = (
    "You are a safety reviewer for a business CRM AI assistant. "
    "Review the draft response and output ONLY valid JSON — no markdown, no preamble.\n\n"
    "IMPORTANT RULES:\n"
    "1. CRM data (revenue figures, order counts, customer names, follow-up dates, analytics) "
    "comes from live database queries and is ALWAYS accurate. Never challenge it, never add "
    "uncertainty language, never say it is 'being processed' or 'check back later'.\n"
    "2. If no knowledge chunks are provided, ONLY check for SAFETY issues — do not assess accuracy.\n"
    "3. SAFETY — the ONLY valid reason to fail: the draft contains a fabricated external URL, "
    "phone number, email address, or specific policy/price/commitment that was NOT in the "
    "knowledge chunks and was NOT in the user's message. Do NOT flag zero values, empty results, "
    "or standard business language.\n"
    "4. TONE — calm, professional, appropriate for a Kenyan SME context. No emoji, no exclamation marks.\n"
    "5. When in doubt, pass=true. The Critic must not make responses worse.\n\n"
    "Output format:\n"
    '{"pass": true | false, "issues": ["..."], "revised_response": "..." | null}\n\n'
    "If pass=true set revised_response to null. "
    "If pass=false, rewrite ONLY to fix the specific safety issue — keep everything else identical."
)


async def critique(
    draft: str,
    user_message: str,
    knowledge_chunks: list,
) -> str:
    """Review `draft` and return either the original or a rewritten version.

    Always returns a non-empty string. Never raises.
    """
    if os.getenv("CRITIC_ENABLED", "false").lower() != "true":
        return draft
    if not draft or not draft.strip():
        return draft

    try:
        from .models import chat_with_tools

        knowledge_text = "\n".join(f"- {c}" for c in (knowledge_chunks or []))
        user_content = (
            f"Draft response:\n{draft}\n\n"
            f"User's original message:\n{user_message}\n\n"
        )
        if knowledge_text:
            user_content += f"Retrieved knowledge chunks:\n{knowledge_text}"

        resp = await chat_with_tools(
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            tools=[],
            temperature=0.1,
        )
        raw = (resp.get("content") or "").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)

        if parsed.get("pass"):
            return draft

        revised = parsed.get("revised_response")
        if revised and revised.strip():
            logger.info(
                "[critic] rewrote response (issues: %s)", parsed.get("issues", [])
            )
            return revised.strip()

        return draft
    except Exception as exc:
        logger.warning("[critic] failed, returning original draft: %s", exc)
        return draft
