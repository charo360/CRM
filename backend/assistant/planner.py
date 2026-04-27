"""Planner agent — decomposes complex user requests before the ReAct executor runs.

For simple one-intent messages (most turns), the planner is skipped entirely
and returns a single-step passthrough. For multi-intent messages, it makes a
fast LLM call to produce an ordered execution plan.

The plan is injected as a system message so the Executor knows what steps to
execute in the ReAct loop.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Keywords that suggest a multi-step or multi-intent request
_COMPLEXITY_TRIGGERS = [" and ", " also ", " then ", " plus ", " as well", " after that"]
_MIN_COMPLEX_LEN = 60  # characters; short messages are rarely complex

PLANNER_SYSTEM = (
    "You are a task planner for a business CRM AI assistant. "
    "Given a user message and available tools, output a JSON execution plan. "
    "For simple single-step tasks: return one step. "
    "For complex multi-step tasks: return 2-4 ordered steps.\n\n"
    "Output ONLY valid JSON — no markdown fences, no preamble:\n"
    '{"complexity": "simple" | "complex", '
    '"steps": [{"goal": "...", "tools_needed": [...], "depends_on": []}]}'
)

_FALLBACK = lambda msg: {  # noqa: E731
    "complexity": "simple",
    "steps": [{"goal": msg, "tools_needed": [], "depends_on": []}],
}


def _is_complex(message: str) -> bool:
    """Quick heuristic: returns True only if the message looks multi-intent."""
    msg_lower = message.lower()
    return (
        len(message) > _MIN_COMPLEX_LEN
        and any(t in msg_lower for t in _COMPLEXITY_TRIGGERS)
    )


async def plan(user_message: str, available_tools: list) -> dict:
    """Return a plan dict for the user message.

    Always returns a valid dict — never raises. On any failure, returns a
    single-step fallback so the Executor proceeds normally.
    """
    if not _is_complex(user_message):
        return _FALLBACK(user_message)

    try:
        from .models import chat_with_tools

        resp = await chat_with_tools(
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Message: {user_message}\n"
                        f"Available tools (sample): {available_tools[:20]}"
                    ),
                },
            ],
            tools=[],
            temperature=0.1,
        )
        raw = (resp.get("content") or "").strip()
        # Strip accidental markdown fences
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        # Validate minimal shape
        if "steps" not in result or not isinstance(result["steps"], list):
            return _FALLBACK(user_message)
        return result
    except Exception as exc:
        logger.warning("[planner] failed, using fallback: %s", exc)
        return _FALLBACK(user_message)


def format_plan_hint(plan_dict: dict) -> str:
    """Format a complex plan into a system message hint for the Executor."""
    steps = plan_dict.get("steps") or []
    if len(steps) <= 1:
        return ""
    lines = ["Execute this plan step by step:"]
    for i, s in enumerate(steps, 1):
        tools = s.get("tools_needed") or []
        tool_note = f" (tools: {', '.join(tools[:4])})" if tools else ""
        lines.append(f"{i}. {s.get('goal', '')}{tool_note}")
    return "\n".join(lines)
