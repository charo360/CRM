"""
Expert AI rubric grader — Opinion + Options + minimal questions.

Used when ``ASSISTANT_EXPERT_RUBRIC=1`` (see ``assistant.rubric_guard``).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from ..models import chat_with_tools, resolve_model

logger = logging.getLogger(__name__)

_RUBRIC_MODEL_ENV = "ASSISTANT_RUBRIC_MODEL"


def _grader_model(preferred: Optional[str]) -> str:
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


def _truncate(s: str, max_chars: int) -> str:
    s = s or ""
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


EXPERT_RUBRICS: Dict[str, List[Dict[str, Any]]] = {
    "must_have": [
        {
            "id": "MH1",
            "question": (
                "Did the AI state a clear recommendation using 'recommend', 'suggest', "
                "'opinion', or similar wording?"
            ),
            "weight": 10,
            "pass_example": "I recommend Product A because it's your top seller",
            "fail_example": "You can choose Product A, B, or C",
        },
        {
            "id": "MH2",
            "question": (
                "Did the AI provide a data-driven reason for its recommendation "
                "(sales, margin, engagement, or past performance)?"
            ),
            "weight": 10,
            "pass_example": "because it sold 1,247 units last month",
            "fail_example": "because I think it's good",
        },
        {
            "id": "MH3",
            "question": (
                "Did the AI offer at least 2 distinct alternative options after giving "
                "its recommendation?"
            ),
            "weight": 10,
            "pass_example": "Your options: Product A, Product B, or Product C",
            "fail_example": "Just use Product A",
        },
        {
            "id": "MH4",
            "question": (
                "Did the AI explicitly include 'something else' or 'not in your store' "
                "as an option?"
            ),
            "weight": 10,
            "pass_example": "Or something not in your store",
            "fail_example": "Only store products mentioned",
        },
        {
            "id": "MH5",
            "question": (
                "Did the AI leave the final decision to the user (e.g. 'What feels right?', "
                "'Your call:', 'Which one?')?"
            ),
            "weight": 10,
            "pass_example": "What feels right to you?",
            "fail_example": "I'll proceed with Product A",
        },
    ],
    "should_have": [
        {
            "id": "SH1",
            "question": (
                "Did the AI ask no more than 2 clarifying questions before offering a "
                "draft or recommendation?"
            ),
            "weight": 5,
            "pass_example": '"What is this? What\'s the main message?" (2 questions)',
            "fail_example": '"Please provide name, category, reason, image, goal, platform" (6 questions)',
        },
        {
            "id": "SH2",
            "question": "Did the AI demonstrate it saw/understood any user-provided image content?",
            "weight": 5,
            "pass_example": '"I see a coffee mug with \'Best Dad\' on it"',
            "fail_example": '"I see you uploaded an image" (no description)',
        },
        {
            "id": "SH3",
            "question": "Did the AI avoid asking 'why' unnecessarily?",
            "weight": 5,
            "pass_example": '"What\'s the main message?"',
            "fail_example": '"Why do you want to feature this product?"',
        },
    ],
    "nice_to_have": [
        {
            "id": "NH1",
            "question": "Did the AI use conversational, human-like language (not form-style)?",
            "weight": 1,
            "pass_example": '"Nice shot. Cool sneakers."',
            "fail_example": '"Please provide the required information"',
        },
        {
            "id": "NH2",
            "question": "Did the AI offer to adjust or tweak the response?",
            "weight": 1,
            "pass_example": '"Want me to change anything?"',
            "fail_example": "No adjustment option offered",
        },
    ],
}


_LINE_RE = re.compile(
    r"^([A-Z]{2}\d+):\s*(YES|NO|N/A)\s*(?:\(([^)]*)\))?\s*$",
    re.IGNORECASE,
)


def parse_grader_output(raw: str) -> Dict[str, str]:
    """Parse MH1: YES / SH2: N/A (no image) lines into id -> YES|NO|N/A."""
    out: Dict[str, str] = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        rid, status, _reason = m.group(1).upper(), m.group(2).upper(), (m.group(3) or "").strip()
        out[rid] = status
        if _reason:
            out[f"{rid}_reason"] = _reason
    return out


def _build_grader_user_block(
    *,
    response: str,
    user_query: str,
    has_image: bool,
) -> str:
    must = EXPERT_RUBRICS["must_have"]
    should = EXPERT_RUBRICS["should_have"]
    nice = EXPERT_RUBRICS["nice_to_have"]

    def _block(items: List[Dict[str, Any]], label: str) -> str:
        lines = []
        for r in items:
            lines.append(
                f"{r['id']}: {r['question']}\n"
                f"  Pass example: {r.get('pass_example', '')}\n"
                f"  Fail example: {r.get('fail_example', '')}"
            )
        return f"{label}\n" + "\n\n".join(lines)

    return f"""USER QUERY (truncated):
{_truncate(user_query, 2500)}

HAS USER IMAGE IN THIS TURN: {has_image}

AI RESPONSE TO GRADE (truncated):
{_truncate(response, 12000)}

--- RUBRICS ---

{_block(must, "MUST-HAVE (10 points each — failing any means defective for expert-choice replies)")}

{_block(should, "SHOULD-HAVE (5 points each)")}

{_block(nice, "NICE-TO-HAVE (1 point each)")}

--- INSTRUCTIONS ---
If the AI response is ONLY a data table, export, or direct factual answer with **no**
strategic choices for the owner, answer **YES** to every MUST item (not applicable).

If there is NO image in this turn, SH2 must be **N/A** with reason "(no image provided)".

For each rubric id, output exactly one line:
MH1: YES
MH2: NO (missing data-backed reason)
SH1: YES
SH2: N/A (no image provided)
NH1: YES

Rules:
- YES / NO / N/A only (N/A only when truly not applicable).
- Be strict when expert choices ARE offered: "almost" = NO.
- No markdown fences, no extra commentary outside these lines."""


async def grade_expert_response(
    response: str,
    *,
    user_query: str = "",
    has_image: bool = False,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Grade ``response`` against ``EXPERT_RUBRICS`` using a small LLM call.

    Returns:
        passed, score (0-100), per-tier percents, failed_items, details (id -> status).
    """
    sys = "You are a strict rubric grader for a business CRM assistant. Follow output format exactly."

    user = _build_grader_user_block(
        response=response,
        user_query=user_query,
        has_image=has_image,
    )

    judge = _grader_model(model_id)
    try:
        resp = await chat_with_tools(
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            tools=[],
            model_id=judge,
            temperature=0.0,
            timeout=60.0,
        )
        raw = (resp.get("content") or "").strip()
    except Exception as exc:
        logger.warning("[expert_grader] LLM call failed: %s — treating as pass", exc)
        return {
            "passed": True,
            "score": 100.0,
            "must_have_score": 100.0,
            "should_have_score": 100.0,
            "nice_to_have_score": 100.0,
            "failed_items": [],
            "details": {},
            "error": str(exc),
        }

    parsed = parse_grader_output(raw)
    if not parsed:
        logger.warning("[expert_grader] unparseable grader output — treating as pass")
        return {
            "passed": True,
            "score": 100.0,
            "must_have_score": 100.0,
            "should_have_score": 100.0,
            "nice_to_have_score": 100.0,
            "failed_items": [],
            "details": parsed,
            "raw_grader": raw[:800],
        }

    failed_items: List[Dict[str, str]] = []
    must_pts = 0
    must_max = 0
    for r in EXPERT_RUBRICS["must_have"]:
        rid = r["id"]
        w = int(r.get("weight", 10))
        must_max += w
        st = parsed.get(rid, "YES").upper()
        if st == "YES":
            must_pts += w
        elif st == "NO":
            failed_items.append(
                {
                    "id": rid,
                    "question": r["question"],
                    "reason": parsed.get(f"{rid}_reason", "Failed"),
                }
            )
        else:
            # N/A counts as full credit for must (treated as not applicable)
            must_pts += w

    should_pts = 0
    should_max = 0
    for r in EXPERT_RUBRICS["should_have"]:
        rid = r["id"]
        w = int(r.get("weight", 5))
        st = parsed.get(rid, "YES").upper()
        if st == "N/A":
            continue
        should_max += w
        if st == "YES":
            should_pts += w

    nice_pts = 0
    nice_max = 0
    for r in EXPERT_RUBRICS["nice_to_have"]:
        rid = r["id"]
        w = int(r.get("weight", 1))
        st = parsed.get(rid, "YES").upper()
        if st == "N/A":
            continue
        nice_max += w
        if st == "YES":
            nice_pts += w

    must_pct = (must_pts / must_max * 100.0) if must_max else 100.0
    should_pct = (should_pts / should_max * 100.0) if should_max else 100.0
    nice_pct = (nice_pts / nice_max * 100.0) if nice_max else 100.0

    overall = (must_pct * 0.6) + (should_pct * 0.3) + (nice_pct * 0.1)

    passed = (must_pct >= 99.99) and (should_pct >= 70.0 or should_max == 0)

    return {
        "passed": passed,
        "score": round(overall, 2),
        "must_have_score": round(must_pct, 2),
        "should_have_score": round(should_pct, 2),
        "nice_to_have_score": round(nice_pct, 2),
        "failed_items": failed_items,
        "details": parsed,
    }
