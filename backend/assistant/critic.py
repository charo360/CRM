"""Critic agent — reviews the Executor's draft before it is returned to the user.

Has full awareness of: the system prompt, every tool result from the turn,
the user's message, and any RAG knowledge chunks. This means it can properly
verify accuracy (draft matches tool data), not guess.

Gated by the CRITIC_ENABLED env flag (default: false).
On any failure the original draft is returned unchanged — the Critic never
blocks the response path.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

CRITIC_SYSTEM = """You are the quality guardian for Zilo Chat, a business CRM AI assistant.

Each review provides you with:
1. The system instructions Zilo follows
2. All tool results retrieved this turn (ground truth — live CRM data)
3. The user's original message
4. The draft response to review
5. Any retrieved knowledge chunks (RAG business knowledge)

Your job is to verify the draft is accurate, safe, and well-toned.

## Rules

ACCURACY:
- Tool results are ground truth. If the draft contradicts what tools returned, fail it and correct it.
- If no tools were called, treat the draft as unverified — apply stricter safety review.
- If tools returned zero/empty results, the draft must say so clearly. It must NOT say "being processed", "check back later", or add false uncertainty. Zero is a valid, accurate result.

SAFETY:
- Fail if the draft contains a specific price, phone number, URL, email, or policy commitment that does NOT appear in the tool results, user message, or knowledge chunks.
- Do not fail for standard business language, zero values, or empty result statements.

TONE:
- Calm, precise, professional. Appropriate for a Kenyan SME business context.
- No emoji. No exclamation marks. No "Sure!" or "Great question!" openers.

CONSERVATISM:
- When in doubt, pass=true. The Critic must not make responses worse.
- Only rewrite to fix a specific, clearly identified issue. Keep everything else identical.
- Never add content that wasn't in the tool results or user message.

Output ONLY valid JSON — no markdown, no preamble:
{"pass": true | false, "issues": ["..."], "revised_response": "..." | null}

If pass=true → set revised_response to null.
If pass=false → rewrite only to fix the identified issue; revised_response must be the full corrected reply."""


def _summarise_steps(steps: list, max_chars: int = 6000) -> str:
    """Render tool steps as compact JSON, truncated to stay within token budget."""
    if not steps:
        return "(no tools called this turn)"
    try:
        text = json.dumps(steps, default=str, ensure_ascii=False)
    except Exception:
        return "(could not serialise tool results)"
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (truncated)"


async def critique(
    draft: str,
    user_message: str,
    knowledge_chunks: list,
    tool_steps: list | None = None,
    system_prompt: str = "",
) -> str:
    """Review `draft` using full turn context and return the original or a rewritten version.

    Args:
        draft:            The assistant's draft response.
        user_message:     The user's message that triggered this turn.
        knowledge_chunks: RAG business knowledge chunks (may be empty).
        tool_steps:       All tool calls + results from this turn (ground truth).
        system_prompt:    The active system prompt so the Critic knows the rules.

    Always returns a non-empty string. Never raises.
    """
    if os.getenv("CRITIC_ENABLED", "false").lower() != "true":
        return draft
    if not draft or not draft.strip():
        return draft

    try:
        from .models import chat_with_tools

        # Build the review payload
        sections: list[str] = []

        if system_prompt:
            # Cap system prompt to first 2000 chars — enough for rules without bloating
            sp_excerpt = system_prompt[:2000] + ("..." if len(system_prompt) > 2000 else "")
            sections.append(f"## System instructions (excerpt)\n{sp_excerpt}")

        sections.append(f"## Tool results this turn (ground truth)\n{_summarise_steps(tool_steps or [])}")
        sections.append(f"## User message\n{user_message}")
        sections.append(f"## Draft response\n{draft}")

        if knowledge_chunks:
            kc_text = "\n".join(f"- {c}" for c in knowledge_chunks)
            sections.append(f"## Retrieved knowledge chunks\n{kc_text}")

        user_content = "\n\n".join(sections)

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
            logger.info("[critic] rewrote response (issues: %s)", parsed.get("issues", []))
            return revised.strip()

        return draft
    except Exception as exc:
        logger.warning("[critic] failed, returning original draft: %s", exc)
        return draft
