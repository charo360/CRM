"""Rubric-guarded reply quality loop (grade → repair → fallback).

Enabled by default; set ``ASSISTANT_RUBRIC_GUARD=0`` to disable.

New agents: add an entry to ``AGENT_RUBRICS`` keyed by the same ``agent_id`` used
in ``AGENT_REGISTRY`` (e.g. ``\"seo\"`` when you ship an SEO specialist).
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .models import chat_with_tools, resolve_model

logger = logging.getLogger(__name__)

MUST_PASS_RATIO = float(os.environ.get("ASSISTANT_RUBRIC_MUST_RATIO", "0.9"))
OVERALL_PASS = float(os.environ.get("ASSISTANT_RUBRIC_OVERALL", "0.7"))
MAX_REPAIR = max(0, min(5, int(os.environ.get("ASSISTANT_RUBRIC_MAX_REPAIR", "2"))))

# Prefer a small fast model for grading/repair to limit cost vs the user's chosen chat model.
_RUBRIC_MODEL_ENV = "ASSISTANT_RUBRIC_MODEL"

# Structured MH1–NH2 expert rubric (see assistant.rubric.expert_grader)
_EXPERT_RUBRIC_AGENTS = frozenset({"creative", "general", "meta_ads", "google_ads", "x_ads"})


def _use_expert_rubric() -> bool:
    return (os.environ.get("ASSISTANT_EXPERT_RUBRIC") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _rubric_model_id(preferred: Optional[str]) -> str:
    explicit = (os.environ.get(_RUBRIC_MODEL_ENV) or "").strip()
    if explicit:
        return explicit
    try:
        resolve_model("gpt-4o-mini")
        return "gpt-4o-mini"
    except Exception:
        pass
    try:
        resolve_model(preferred)
        return preferred or "gpt-4o-mini"
    except Exception:
        return preferred or "gpt-4o-mini"


AGENT_RUBRICS: Dict[str, Dict[str, List[str]]] = {
    "creative": {
        "must_have": [
            "If this reply asks the owner to pick among products, platforms, angles, or goals: does it lead with an explicit recommendation using I recommend or My opinion is or I'd lean toward (or an equivalent clear expert lead-in) plus a reason tied to real data or an honest statement that data is missing? (If the reply does NOT ask them to pick among strategic paths, answer YES.)",
            "If this reply asks them to pick among strategic paths: does it include at least two distinct meaningful options AND a Something else line? (If no strategic choice set is offered, answer YES.)",
            "If the user asked to create or render a visual in this turn: does the reply avoid delivering a finished rendered asset while key choices are still unresolved, unless the user already gave explicit go-ahead? (If not a visual-create request, answer YES.)",
        ],
        "should_have": [
            "If strategic choices are offered: does the reply end with one clear decision prompt (e.g. what feels right)? (If not applicable, answer YES.)",
            "Does the response avoid a form-like wall of many unrelated questions at once?",
        ],
        "nice_to_have": [
            "Does the response use scannable structure (headings or bullet lists) when giving multiple points?",
            "Does the response mention timing, hashtags, or format specifics where relevant?",
        ],
    },
    "meta_ads": {
        "must_have": [
            "If this reply asks the owner to pick among campaign directions: does it lead with I recommend or My opinion is or equivalent plus a data-grounded reason or honest gap? (If no strategic choice set, answer YES.)",
            "If strategic paths are offered: at least two distinct options plus Something else? (If not applicable, answer YES.)",
            "Did the assistant avoid claiming a live campaign was already launched or fully executed without the owner's explicit confirmation?",
        ],
        "should_have": [
            "If choices are offered: one clear decision prompt at the end? (If not applicable, answer YES.)",
            "Does the response mention budget, bid strategy, or measurement (even directionally) when discussing campaigns?",
        ],
        "nice_to_have": [
            "Does the response reference creative formats available in this product (e.g. design studio) where relevant?",
        ],
    },
    "general": {
        "must_have": [
            "Does the response address the owner's actual question or task (not an unrelated topic)?",
            "Does the response either lean on concrete CRM-style facts (numbers, lists, next actions grounded in data), OR clearly ask for one specific missing input, OR (when the user only greets or is very vague) offer a brief welcome and invite them to name their priority?",
            "Does the response avoid fabricating CRM outcomes (fake order IDs, payments sent, integrations completed) that are not supported by the text?",
            "If this reply asks the owner to pick among strategic CRM paths (which segment, product, campaign, report scope): does it include an expert lead-in (I recommend / My opinion is / equivalent) with reason before the options, and Something else among the choices? (If not applicable, answer YES.)",
        ],
        "should_have": [
            "Does the response lead with the most important takeaway before detail?",
            "Does the response suggest a clear next action where appropriate?",
        ],
        "nice_to_have": [
            "Does the response use Markdown structure (headings/tables) when presenting multi-row data?",
        ],
    },
}

# Ads specialists share the same quality bar until you split per-platform rubrics.
for _ads_id in ("google_ads", "x_ads"):
    AGENT_RUBRICS[_ads_id] = copy.deepcopy(AGENT_RUBRICS["meta_ads"])


def _enabled() -> bool:
    v = (os.environ.get("ASSISTANT_RUBRIC_GUARD") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _truncate(s: str, max_chars: int) -> str:
    s = s or ""
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


def _parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    t = (raw or "").strip()
    if not t:
        return None
    m = re.search(r"\{[\s\S]*\}\s*$", t)
    if m:
        t = m.group(0)
    if t.startswith("```"):
        t = re.sub(r"^```\w*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


async def _grade_once(
    *,
    user_message: str,
    reply: str,
    rubric: Dict[str, List[str]],
    model_id: str,
) -> Dict[str, Any]:
    must_q = rubric.get("must_have") or []
    should_q = rubric.get("should_have") or []
    nice_q = rubric.get("nice_to_have") or []

    spec = {
        "must": [True] * len(must_q),
        "should": [True] * len(should_q),
        "nice": [True] * len(nice_q),
    }
    grader_system = """You are a strict rubric judge for a business CRM assistant.
Output ONLY a single JSON object, no markdown fences, no prose.
Schema:
{"must":[...],"should":[...],"nice":[...]}
Each value is a boolean true/false: true ONLY if the assistant reply FULLY satisfies that criterion; false if missing, partial, or unclear.
The arrays MUST have exactly the lengths given in the user message."""

    user_block = f"""USER REQUEST (truncated):
{_truncate(user_message, 2500)}

ASSISTANT REPLY (truncated):
{_truncate(reply, 12000)}

must_have ({len(must_q)} items) — booleans in order:
{json.dumps(must_q, ensure_ascii=False)}

should_have ({len(should_q)} items):
{json.dumps(should_q, ensure_ascii=False)}

nice_to_have ({len(nice_q)} items):
{json.dumps(nice_q, ensure_ascii=False)}

Return: {json.dumps(spec)} with only true/false replaced."""

    resp = await chat_with_tools(
        messages=[
            {"role": "system", "content": grader_system},
            {"role": "user", "content": user_block},
        ],
        tools=[],
        model_id=model_id,
        temperature=0.0,
        timeout=60.0,
    )
    parsed = _parse_json_object(resp.get("content") or "")
    if not parsed:
        logger.warning("[rubric_guard] grader returned unparseable JSON; treating as pass")
        return {
            "pass": True,
            "overall_score": 1.0,
            "must_ratio": 1.0,
            "failed_items": [],
            "raw_grader": (resp.get("content") or "")[:500],
            "parse_error": True,
        }

    def _bools(key: str, n: int) -> List[bool]:
        arr = parsed.get(key)
        if not isinstance(arr, list):
            return [False] * n
        out: List[bool] = []
        for i in range(n):
            v = arr[i] if i < len(arr) else False
            out.append(bool(v))
        return out

    must_b = _bools("must", len(must_q))
    should_b = _bools("should", len(should_q))
    nice_b = _bools("nice", len(nice_q))

    w_must = 10
    w_should = 5
    w_nice = 1
    earned = sum(w_must for b in must_b if b) + sum(w_should for b in should_b if b) + sum(w_nice for b in nice_b if b)
    max_pts = len(must_q) * w_must + len(should_q) * w_should + len(nice_q) * w_nice
    overall = (earned / max_pts) if max_pts else 1.0

    n_m = len(must_q)
    must_passed = sum(1 for b in must_b if b)
    must_ratio = (must_passed / n_m) if n_m else 1.0
    need_must = math.ceil(MUST_PASS_RATIO * n_m) if n_m else 0
    must_ok = must_passed >= need_must if n_m else True
    overall_ok = overall >= OVERALL_PASS
    pass_all = must_ok and overall_ok

    failed: List[str] = []
    for i, b in enumerate(must_b):
        if not b and i < len(must_q):
            failed.append(must_q[i])

    return {
        "pass": pass_all,
        "overall_score": overall,
        "must_ratio": must_ratio,
        "failed_items": failed,
        "must_bools": must_b,
        "should_bools": should_b,
        "nice_bools": nice_b,
    }


async def _repair_reply(
    *,
    user_message: str,
    reply: str,
    failed_items: List[str],
    model_id: str,
) -> str:
    sys = """You revise assistant replies for a CRM product. Keep the same language as the user's request.
Output ONLY the improved assistant message — no preamble, no markdown code fences."""
    user = f"""ORIGINAL USER REQUEST:
{_truncate(user_message, 3000)}

PREVIOUS ASSISTANT REPLY:
{_truncate(reply, 14000)}

These quality checks FAILED (your new reply must fix ALL of them; do not skip any):
{chr(10).join(f"- {x}" for x in failed_items)}

Rewrite the full reply: be specific, grounded, and follow the failed checks exactly."""
    resp = await chat_with_tools(
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ],
        tools=[],
        model_id=model_id,
        temperature=0.2,
        timeout=90.0,
    )
    return (resp.get("content") or "").strip() or reply


def _fallback_gather(user_message: str, failed_items: List[str]) -> str:
    lines = "\n".join(f"- {x}" for x in failed_items[:6])
    return (
        "### Let's get this right\n\n"
        "I want to give you a complete, accurate answer. A quick quality pass flagged "
        "that some important checkpoints were not met.\n\n"
        "**Please clarify or provide:**\n"
        f"{lines}\n\n"
        "Once you share that, I will continue from your original request.\n\n"
        f"_Your request was:_ {_truncate(user_message, 400)}"
    )


async def _guard_with_expert_rubric(
    *,
    reply: str,
    user_message: str,
    agent_id: str,
    model_id: Optional[str],
    has_image: bool,
) -> Tuple[str, List[Dict[str, Any]]]:
    """MH1–NH2 line grader + same repair/fallback loop as legacy rubric."""
    from .rubric.expert_grader import grade_expert_response

    extra: List[Dict[str, Any]] = []
    judge_model = _rubric_model_id(model_id)
    current = reply

    for attempt in range(MAX_REPAIR + 1):
        grade = await grade_expert_response(
            current,
            user_query=user_message,
            has_image=has_image,
            model_id=judge_model,
        )
        extra.append(
            {
                "tool": "_expert_rubric_grade",
                "arguments": {"agent_id": agent_id, "attempt": attempt},
                "result": {
                    "passed": grade.get("passed"),
                    "score": grade.get("score"),
                    "must_have_score": grade.get("must_have_score"),
                    "should_have_score": grade.get("should_have_score"),
                },
            }
        )
        if grade.get("passed"):
            return current, extra

        fails = grade.get("failed_items") or []
        failed_lines = [
            f"{x.get('id', '')}: {x.get('question', '')}"
            + (f" — {x.get('reason')}" if x.get("reason") else "")
            for x in fails
        ]

        if attempt >= MAX_REPAIR:
            from .guaranteed_expert import fallback_gather_mode

            fb = fallback_gather_mode(user_message, fails)
            extra.append(
                {
                    "tool": "_expert_rubric_fallback",
                    "arguments": {"agent_id": agent_id},
                    "result": {"reason": "max_repair_exceeded"},
                }
            )
            return fb, extra

        if not failed_lines:
            return current, extra

        repaired = await _repair_reply(
            user_message=user_message,
            reply=current,
            failed_items=failed_lines,
            model_id=judge_model,
        )
        extra.append(
            {
                "tool": "_expert_rubric_repair",
                "arguments": {"agent_id": agent_id, "attempt": attempt + 1},
                "result": {"chars": len(repaired)},
            }
        )
        current = repaired

    return current, extra


async def guard_reply_with_rubric(
    *,
    reply: str,
    user_message: str,
    agent_id: str,
    model_id: Optional[str],
    has_image: bool = False,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Optionally grade and repair the final assistant reply. Returns (reply, extra_steps)."""
    extra: List[Dict[str, Any]] = []
    if not _enabled() or not reply or not agent_id:
        return reply, extra
    if len(reply.strip()) < 24:
        return reply, extra

    if _use_expert_rubric() and agent_id in _EXPERT_RUBRIC_AGENTS:
        return await _guard_with_expert_rubric(
            reply=reply,
            user_message=user_message,
            agent_id=agent_id,
            model_id=model_id,
            has_image=has_image,
        )

    rubric = AGENT_RUBRICS.get(agent_id)
    if not rubric:
        return reply, extra

    judge_model = _rubric_model_id(model_id)
    current = reply

    for attempt in range(MAX_REPAIR + 1):
        grade = await _grade_once(
            user_message=user_message,
            reply=current,
            rubric=rubric,
            model_id=judge_model,
        )
        extra.append({
            "tool": "_rubric_grade",
            "arguments": {"agent_id": agent_id, "attempt": attempt},
            "result": {k: v for k, v in grade.items() if k != "raw_grader"},
        })
        if grade.get("pass"):
            return current, extra

        if attempt >= MAX_REPAIR:
            fb = _fallback_gather(user_message, grade.get("failed_items") or [])
            extra.append({
                "tool": "_rubric_fallback",
                "arguments": {"agent_id": agent_id},
                "result": {"reason": "max_repair_exceeded"},
            })
            return fb, extra

        failed = grade.get("failed_items") or []
        if not failed:
            return current, extra

        repaired = await _repair_reply(
            user_message=user_message,
            reply=current,
            failed_items=failed,
            model_id=judge_model,
        )
        extra.append({
            "tool": "_rubric_repair",
            "arguments": {"agent_id": agent_id, "attempt": attempt + 1},
            "result": {"chars": len(repaired)},
        })
        current = repaired

    return current, extra
