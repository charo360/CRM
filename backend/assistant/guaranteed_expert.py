"""
Guaranteed expert loop — rubric grade + auto-repair + gather fallback.

This is a **reference / reusable** wrapper for flows that can inject an LLM
caller. Zilo Chat’s main path uses ``rubric_guard.guard_reply_with_rubric`` +
``run_turn`` instead of this class, but you can reuse the same repair/fallback
helpers or call ``GuaranteedExpertAgent`` from jobs/tests.

Example::

    async def call_llm(q: str, attempt: int) -> str:
        ...

    agent = GuaranteedExpertAgent(max_retries=2)
    text = await agent.arespond("Create an Instagram post", call_llm, has_image=False)
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .rubric.expert_grader import grade_expert_response

logger = logging.getLogger(__name__)


def build_repair_user_message(
    *,
    original_query: str,
    failed_response: str,
    failed_items: List[Dict[str, str]],
) -> str:
    failed_descriptions = "\n".join(
        f"- [{x.get('id', '')}] {x.get('question', '')}"
        for x in failed_items
    )
    return f"""Your previous response FAILED these critical checks:

{failed_descriptions}

Your failed response was:
{failed_response[:14000]}

Provide a CORRECTED full reply that:
1. Gives a clear recommendation with a data-driven reason (or states data is missing).
2. Offers at least 2 distinct options plus something else / not in your store.
3. Asks at most 2 clarifying questions only if needed.
4. Ends with the user choosing (e.g. "What feels right to you?").

Original request:
{original_query[:3000]}

Corrected reply only (no preamble):"""


def fallback_gather_mode(original_query: str, failed_items: List[Dict[str, str]]) -> str:
    if not failed_items:
        return (
            f'I want to help with: "{original_query[:500]}"\n\n'
            "To give you a solid recommendation with options, I need:\n"
            "1. What you want to accomplish\n"
            "2. Any product or image you have in mind\n\n"
            "Reply with those and I will continue."
        )

    missing_fields: List[str] = []
    for item in failed_items:
        q = (item.get("question") or "").lower()
        if "recommend" in q or "opinion" in q:
            missing_fields.append("Your goal or preference")
        elif "option" in q or "alternative" in q:
            missing_fields.append("What alternatives you would consider")
        elif "something else" in q or "not in your store" in q:
            missing_fields.append("Whether you want something outside the catalog")

    fields_text = "\n".join(f"• {f}" for f in missing_fields) if missing_fields else "• What you are trying to do"

    return (
        "### Let me get this right\n\n"
        f"I need a bit more before I recommend with options:\n\n{fields_text}\n\n"
        "Also tell me if you have an image or product in mind.\n\n"
        f"_Your request:_ {original_query[:500]}"
    )


class GuaranteedExpertAgent:
    """Rubric-guarded loop with injectable async LLM caller."""

    def __init__(self, *, max_retries: int = 2):
        self.max_retries = max(0, min(5, int(max_retries)))

    async def arespond(
        self,
        user_input: str,
        call_agent: Callable[[str, int], Awaitable[str]],
        *,
        context: Optional[Dict[str, Any]] = None,
        model_id: Optional[str] = None,
    ) -> str:
        """
        ``call_agent(full_prompt, attempt_index)`` must return the assistant text
        for that attempt (your system prompt + user should already be inside the
        string you pass to the model — this class only adds repair wrappers).
        """
        context = context or {}
        has_image = bool(context.get("has_image"))
        full_query = user_input
        last_response = ""

        for attempt in range(self.max_retries + 1):
            last_response = await call_agent(full_query, attempt)
            grade = await grade_expert_response(
                last_response,
                user_query=user_input,
                has_image=has_image,
                model_id=model_id,
            )
            if grade.get("passed"):
                return last_response

            if attempt < self.max_retries:
                fails = grade.get("failed_items") or []
                full_query = build_repair_user_message(
                    original_query=user_input,
                    failed_response=last_response,
                    failed_items=fails,
                )
            else:
                return fallback_gather_mode(user_input, grade.get("failed_items") or [])

        return fallback_gather_mode(user_input, [])
