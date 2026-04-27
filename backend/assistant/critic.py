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
    "You are a quality reviewer for a business CRM AI assistant. "
    "Review the draft response and output ONLY valid JSON — no markdown, no preamble.\n\n"
    "Criteria:\n"
    "1. ACCURACY — does the draft match the retrieved knowledge chunks (if any)?\n"
    "2. TONE — calm, professional, appropriate for a Kenyan SME business context?\n"
    "3. COMPLETENESS — does it fully address the user's question?\n"
    "4. SAFETY — no hallucinated prices, policies, contact details, or commitments?\n\n"
    "Output format:\n"
    '{"pass": true | false, "issues": ["..."], "revised_response": "..." | null}\n\n'
    "If pass=true set revised_response to null. "
    "If pass=false rewrite the response in revised_response fixing all issues."
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
