"""
Sync open Decision Room sessions into the morning briefing ledger.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from rex.actions import Action, ActionKind, ActionState
from rex.identity import CHIEF_OF_STAFF_NAME
from rex.loop import Orchestrator
from rex.decisions.models import STRATEGY_CATEGORY

logger = logging.getLogger(__name__)


def _decision_ref(session_id: str) -> str:
    return f"decision:{session_id}"


def _outcome_ref(session_id: str, day: int) -> str:
    return f"outcome:{session_id}:{day}"


def _has_ref(orch: Orchestrator, ref: str) -> bool:
    for act in orch.ledger.all_actions():
        if (act.payload or {}).get("crm_ref") == ref:
            return True
    return False


def _truncate(text: str, n: int = 72) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1].rstrip() + "…"


async def sync_open_decisions_to_briefing(
    db: Any,
    user: dict,
    orch: Orchestrator,
    *,
    limit: int = 1,
) -> int:
    """
    Stage at most `limit` open decision sessions as strategy DATA_FLAG actions
    so they can surface in the morning letter (max 3 slots globally).
    """
    uid = str(user.get("_id") or "")
    if not uid:
        return 0

    try:
        cursor = db.decision_sessions.find(
            {"user_id": uid, "status": "open"},
        ).sort("updated_at", -1).limit(limit)
        sessions = await cursor.to_list(limit)
    except Exception as e:
        logger.warning("[decision-bridge] list open: %s", e)
        return 0

    staged = 0
    for doc in sessions or []:
        sid = str(doc.get("_id") or "")
        if not sid:
            continue
        ref = _decision_ref(sid)
        if _has_ref(orch, ref):
            continue

        question = _truncate(doc.get("question") or "Strategic decision")
        lean = (doc.get("founder_lean") or doc.get("spar", {}).get("founder_lean_detected") or "").strip()
        summary = f"Decision pending — {question}"
        reasoning = (
            f"Spar complete. Your data is loaded."
            + (f" Lean: {lean}." if lean else "")
            + " Open Decision Room to pressure-test before you commit."
        )

        standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, STRATEGY_CATEGORY)
        action = Action.propose(
            actor_name="Zilo",
            rank_at_time=standing.rank,
            category=STRATEGY_CATEGORY,
            kind=ActionKind.DATA_FLAG,
            summary=summary,
            reasoning=reasoning,
            confidence=0.92,
            target_subject="Strategic decision",
            payload={
                "crm_ref": ref,
                "decision_session_id": sid,
                "action_mode_type": "decision_room",
                "is_informational": True,
                "review_only": True,
                "urgency": "high",
                "href": f"/dashboard/rex/decisions?session={sid}",
            },
            memory_citation_ids=(),
        )
        orch.ledger.record_proposal(action)
        orch.ledger.transition(
            action_id=action.id,
            to_state=ActionState.STAGED,
            actor_name="Zilo",
            reason="Open decision needs your judgment.",
        )
        staged += 1

    return staged


def dismiss_decision_briefing_actions(orch: Orchestrator, session_id: str) -> int:
    """Dismiss staged briefing items for a decided/archived session."""
    ref = _decision_ref(session_id)
    dismissed = 0
    for act in orch.ledger.staged_actions():
        if (act.payload or {}).get("crm_ref") != ref:
            continue
        try:
            orch.dismiss(act.id, reason="Decision recorded by founder.")
            dismissed += 1
        except Exception as e:
            logger.debug("[decision-bridge] dismiss %s: %s", act.id, e)
    return dismissed


async def sync_outcome_reports_to_briefing(
    db: Any,
    user: dict,
    orch: Orchestrator,
    *,
    limit: int = 1,
) -> int:
    """Stage unacknowledged 30/60/90-day outcome reports for the morning letter."""
    uid = str(user.get("_id") or "")
    if not uid:
        return 0

    try:
        cursor = (
            db.decision_sessions.find(
                {"user_id": uid, "status": "decided", "outcome_reports": {"$exists": True, "$ne": []}},
            )
            .sort("updated_at", -1)
            .limit(20)
        )
        sessions = await cursor.to_list(20)
    except Exception as e:
        logger.warning("[decision-bridge] outcome list: %s", e)
        return 0

    staged = 0
    for doc in sessions or []:
        if staged >= limit:
            break
        sid = str(doc.get("_id") or "")
        for report in doc.get("outcome_reports") or []:
            if staged >= limit:
                break
            if report.get("briefing_ack"):
                continue
            day = int(report.get("day") or 0)
            if not day:
                continue
            ref = _outcome_ref(sid, day)
            if _has_ref(orch, ref):
                continue

            review = _truncate(report.get("summary") or f"Day {day} outcome check", 220)
            decided_on = ""
            decided_at = doc.get("decided_at")
            if hasattr(decided_at, "strftime"):
                decided_on = decided_at.strftime("%b %d")
            decision_recap = _truncate(doc.get("founder_decision") or "", 80)
            recap = (
                f"On {decided_on} you decided: {decision_recap} " if decided_on and decision_recap else ""
            )
            reasoning = f"{recap}{review} What actually happened? Open to log it — your call still stands."
            standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, STRATEGY_CATEGORY)
            action = Action.propose(
                actor_name="Zilo",
                rank_at_time=standing.rank,
                category=STRATEGY_CATEGORY,
                kind=ActionKind.DATA_FLAG,
                summary=f"Decision Room · Day {day} check — {_truncate(doc.get('question') or 'your decision', 44)}",
                reasoning=reasoning,
                confidence=0.88,
                target_subject="Decision outcome",
                payload={
                    "crm_ref": ref,
                    "decision_session_id": sid,
                    "outcome_day": day,
                    "action_mode_type": "decision_outcome",
                    "is_informational": True,
                    "review_only": True,
                    "urgency": "medium",
                    "href": f"/dashboard/rex/decisions?session={sid}&tab=outcomes",
                },
                memory_citation_ids=(),
            )
            orch.ledger.record_proposal(action)
            orch.ledger.transition(
                action_id=action.id,
                to_state=ActionState.STAGED,
                actor_name="Zilo",
                reason=f"Day {day} outcome check ready.",
            )
            staged += 1

    return staged


async def ack_outcome_briefing(db: Any, user_id: str, session_id: str, day: int) -> bool:
    """Mark an outcome report as acknowledged (briefing dismissed)."""
    try:
        doc = await db.decision_sessions.find_one({"_id": session_id, "user_id": user_id})
        if not doc:
            return False
        reports = list(doc.get("outcome_reports") or [])
        changed = False
        for r in reports:
            if int(r.get("day") or 0) == day:
                r["briefing_ack"] = True
                changed = True
        if not changed:
            return False
        await db.decision_sessions.update_one(
            {"_id": session_id},
            {"$set": {"outcome_reports": reports, "updated_at": datetime.now(timezone.utc)}},
        )
        return True
    except Exception as e:
        logger.warning("[decision-bridge] ack outcome: %s", e)
        return False
