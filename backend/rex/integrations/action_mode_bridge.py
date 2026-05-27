"""
Bridge Zilo ledger ↔ Action Mode queue (drafts, approve → real sends).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from rex.actions import Action, ActionKind, ActionState
from rex.actions.primitives import Outcome
from rex.actions.protocols import ActionExecutor, ExecutionResult
from rex.crm.sync import _has_crm_ref, _stage_action
from rex.identity import CHIEF_OF_STAFF_NAME
from rex.loop import Orchestrator
from rex.onboarding.scanner import _run_async
logger = logging.getLogger(__name__)

QUEUE_REF_PREFIX = "queue:"

ACTION_TYPE_TO_KIND: dict[str, ActionKind] = {
    "send_whatsapp": ActionKind.OUTREACH,
    "send_email": ActionKind.REPLY,
    "post_comment": ActionKind.SOCIAL_DM,
    "join_group": ActionKind.OUTREACH,
    "submit_application": ActionKind.QUOTE,
    "review_result": ActionKind.DATA_FLAG,
}

def _channel_for_action_type(action_type: str) -> str:
    return {
        "send_email": "email",
        "send_whatsapp": "whatsapp",
        "post_comment": "social",
        "join_group": "social",
    }.get(action_type, "crm")


ACTION_TYPE_TO_CATEGORY: dict[str, str] = {
    "send_whatsapp": "replies",
    "send_email": "replies",
    "post_comment": "leads",
    "join_group": "leads",
    "submit_application": "quotes",
    "review_result": "leads",
}


def queue_ref(queue_id: str) -> str:
    return f"{QUEUE_REF_PREFIX}{queue_id}"


def _category_for_item(item: dict[str, Any]) -> str:
    agent = (item.get("agent") or "").lower()
    at = item.get("action_type", "")
    if "scout" in agent or at == "post_comment":
        return "leads"
    if at == "send_email":
        return "replies"
    if at in ("send_whatsapp",):
        return "outreach"
    return ACTION_TYPE_TO_CATEGORY.get(at, "outreach")


async def import_pending_queue(
    db: Any,
    uid: str,
    orch: Orchestrator,
    *,
    limit: int = 15,
) -> int:
    """Mirror Action Mode pending queue into Zilo staged actions."""
    items = await db.action_mode_queue.find(
        {"user_id": uid, "status": "pending"},
    ).sort("created_at", -1).to_list(limit)

    imported = 0
    for item in items:
        qid = str(item["_id"])
        ref = queue_ref(qid)
        if _has_crm_ref(orch, ref):
            continue

        action_type = item.get("action_type") or "review_result"
        kind = ACTION_TYPE_TO_KIND.get(action_type, ActionKind.DATA_FLAG)
        category = _category_for_item(item)
        meta = dict(item.get("metadata") or {})
        meta["queue_id"] = qid
        meta["action_mode_type"] = action_type
        meta["agent"] = item.get("agent", "")

        draft = (item.get("draft_content") or "").strip()
        reasoning_parts = []
        if meta.get("snippet"):
            reasoning_parts.append(str(meta["snippet"])[:200])
        if meta.get("url"):
            reasoning_parts.append(f"Source: {meta['url']}")
        if not reasoning_parts and draft:
            reasoning_parts.append(draft[:200])
        reasoning = " · ".join(reasoning_parts) or "From Action Mode queue — review draft before sending."

        channel = meta.get("channel") or _channel_for_action_type(action_type)
        review_only = action_type == "send_email" or meta.get("review_only") is True

        standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, category)
        action = Action.propose(
            actor_name="Zilo",
            rank_at_time=standing.rank,
            category=category,
            kind=kind,
            summary=(item.get("title") or "Queued action")[:120],
            reasoning=reasoning,
            confidence=0.86,
            target_subject=meta.get("customer_name") or meta.get("contact_name"),
            payload={
                "crm_ref": ref,
                "queue_id": qid,
                "action_mode_type": action_type,
                "channel": channel,
                "review_only": review_only,
                "draft_preview": draft[:2000] if draft else None,
                **{k: v for k, v in meta.items() if k not in ("crm_ref", "channel", "review_only")},
            },
        )
        orch.ledger.record_proposal(action)
        orch.ledger.transition(
            action_id=action.id,
            to_state=ActionState.STAGED,
            actor_name="Zilo",
            reason="Imported from Action Mode queue.",
        )
        imported += 1

    if imported:
        logger.info("[zilo] imported %d queue items for uid=%s", imported, uid)
    return imported


async def import_scout_opportunities(db: Any, uid: str, orch: Orchestrator, *, limit: int = 8) -> int:
    """Stage high-score Scout hits not already in the queue."""
    cutoff = datetime.utcnow() - timedelta(days=3)
    opps = await db.action_mode_opportunities.find({
        "user_id": uid,
        "created_at": {"$gte": cutoff},
        "score": {"$gte": 6},
    }).sort([("score", -1), ("created_at", -1)]).to_list(limit)

    imported = 0
    for opp in opps:
        oid = str(opp["_id"])
        ref = f"opp:{oid}"
        if _has_crm_ref(orch, ref):
            continue
        url = opp.get("url", "")
        if url:
            pending = await db.action_mode_queue.find_one({
                "user_id": uid,
                "status": "pending",
                "metadata.url": url,
            })
            if pending:
                continue

        kind = ActionKind.SOCIAL_POST if opp.get("kind") == "social" else ActionKind.DATA_FLAG
        if opp.get("kind") == "funding":
            kind = ActionKind.QUOTE

        _stage_action(
            orch,
            kind=kind,
            category="leads",
            summary=f"Lead: {(opp.get('title') or 'Opportunity')[:100]}",
            reasoning=(opp.get("snippet") or "Scout found this — approve to engage or add to pipeline.")[:300],
            confidence=min(0.95, 0.7 + (opp.get("score", 7) * 0.03)),
            crm_ref=ref,
            target_subject=opp.get("contact_name"),
            payload={
                "opportunity_id": oid,
                "url": url,
                "score": opp.get("score"),
                "scout_id": opp.get("scout_id"),
                "draft_preview": (opp.get("snippet") or "")[:500],
            },
        )
        imported += 1
    return imported


class ActionModeExecutor(ActionExecutor):
    """On approve, runs the same path as Action Mode (WhatsApp, social, etc.)."""

    def __init__(self, db: Any, uid: str) -> None:
        self._db = db
        self._uid = uid

    def supports(self, action: Action) -> bool:
        return bool((action.payload or {}).get("queue_id"))

    def execute(self, action: Action) -> ExecutionResult:
        try:
            return _run_async(self._execute_async(action)) or ExecutionResult(
                success=False,
                outcome=Outcome(error_message="Executor timed out"),
            )
        except Exception as e:
            logger.exception("[zilo] ActionModeExecutor failed: %s", e)
            return ExecutionResult(
                success=False,
                outcome=Outcome(error_class=type(e).__name__, error_message=str(e)),
            )

    async def _execute_async(self, action: Action) -> ExecutionResult:
        from action_mode_routes import _execute_approved_action

        payload = action.payload or {}
        qid = payload.get("queue_id")
        if not qid:
            return ExecutionResult(
                success=False,
                outcome=Outcome(error_message="Missing queue_id"),
            )

        item = await self._db.action_mode_queue.find_one(
            {"_id": qid, "user_id": self._uid},
        )
        if not item:
            return ExecutionResult(
                success=False,
                outcome=Outcome(error_message="Queue item not found"),
            )

        if item.get("user_edited") and item.get("draft_content"):
            content = item["draft_content"]
        else:
            content = payload.get("draft_preview") or item.get("draft_content") or ""
        await self._db.action_mode_queue.update_one(
            {"_id": qid},
            {"$set": {"status": "approved", "approved_at": datetime.utcnow()}},
        )
        await _execute_approved_action(self._db, self._uid, item, content)

        return ExecutionResult(
            success=True,
            outcome=Outcome(external_ref=f"action-mode:{qid}", rows_affected=1),
        )


def wire_action_mode_executor(orch: Orchestrator, db: Any, uid: str) -> None:
    """Register real executor; keep stub as fallback for non-queue actions."""
    from rex.actions.stub_executor import StubExecutor

    orch.register_executor(ActionModeExecutor(db, uid))
    orch.register_executor(StubExecutor())
