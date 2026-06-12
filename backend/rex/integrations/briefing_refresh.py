"""
Live Zilo Briefing ingest — pull signals from the whole CRM into staged actions.

Used on:
  - GET /api/rex/home (light refresh)
  - Email webhooks / sync after new messages land
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from rex.crm.adapters import _business_id
from rex.crm.sync import fetch_metrics, sync_from_crm
from rex.integrations.action_mode_bridge import (
    import_pending_queue,
    import_scout_opportunities,
    wire_action_mode_executor,
)
from rex.integrations.email_bridge import sync_and_draft_inbox
from rex.integrations.messages_bridge import draft_whatsapp_inbox
from rex.integrations.platform_sweep import _biz_context
from rex.loop import Orchestrator

logger = logging.getLogger(__name__)


async def _safe(coro, *, label: str):
    """Await `coro`, return its result, or capture the exception as a report dict."""
    try:
        return await coro
    except Exception as e:
        logger.warning("[zilo] briefing %s: %s", label, e)
        return {"error": str(e)}


def _auto_dismiss_promotional_staged(orch: Orchestrator, whitelist: set[str] | None = None) -> int:
    """Walk staged email actions and dismiss any that look promotional.

    Why: the email_bridge + queue-import filters block new newsletter drafts,
    but accumulated staged items from before the filter shipped still pollute
    the count. We dismiss them here with an audit reason so the user can
    inspect the trail in the journal / ledger.
    """
    from rex.actions.primitives import ActionState
    from rex.integrations.email_bridge import _is_promotional

    dismissed = 0
    for action in orch.ledger.staged_actions():
        payload = action.payload or {}
        if payload.get("channel") not in (None, "email"):
            continue
        meta_msg = {
            "from_addr": payload.get("from_addr"),
            "subject": payload.get("subject"),
            "body_clean": payload.get("snippet") or payload.get("draft_preview"),
            "headers": payload.get("headers"),
        }
        promo, reason = _is_promotional(meta_msg, whitelist)
        if not promo:
            continue
        try:
            orch.ledger.transition(
                action_id=action.id,
                to_state=ActionState.DISMISSED,
                actor_name="Zilo",
                reason=f"Auto-dismissed: {reason}",
            )
            dismissed += 1
        except Exception as e:
            logger.debug("[zilo] auto-dismiss skip %s: %s", action.id, e)
    if dismissed:
        logger.info("[zilo] auto-dismissed %d promotional staged actions", dismissed)
    return dismissed


# Reasons we used to dismiss with that turned out to be too aggressive. Actions
# dismissed under these reasons get re-proposed (the original action stays in
# the audit trail; a new proposal is created so the item resurfaces).
_REVIVABLE_DISMISS_REASONS = (
    "Auto-dismissed: no_conversation_signal",
)


def _revive_overzealously_dismissed(orch: Orchestrator) -> int:
    """Re-propose actions that an earlier (too-aggressive) filter dismissed.

    DISMISSED is a terminal state in the ledger, so we can't move them back to
    STAGED directly. Instead we create a fresh Action with the same payload and
    stage that. The original DISMISSED record remains for auditability.
    """
    from rex.actions.primitives import Action, ActionState
    from rex.identity import CHIEF_OF_STAFF_NAME

    revived = 0
    seen_refs: set[str] = set()

    # Build the set of CRM refs that are currently live (any non-terminal state)
    # so we don't re-stage something the user already acted on.
    for a in orch.ledger.all_actions():
        st = orch.ledger.current_state(a.id)
        if st not in (ActionState.DISMISSED, ActionState.REJECTED, ActionState.FAILED):
            ref = (a.payload or {}).get("crm_ref")
            if ref:
                seen_refs.add(ref)

    for action in orch.ledger.all_actions():
        if orch.ledger.current_state(action.id) is not ActionState.DISMISSED:
            continue
        changes = orch.ledger.changes(action.id)
        if not changes:
            continue
        latest = changes[-1]
        if (latest.reason or "") not in _REVIVABLE_DISMISS_REASONS:
            continue

        ref = (action.payload or {}).get("crm_ref")
        if ref and ref in seen_refs:
            continue  # already revived or user already acted

        standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, action.category)
        new_action = Action.propose(
            actor_name=action.actor_name,
            rank_at_time=standing.rank,
            category=action.category,
            kind=action.kind,
            summary=action.summary,
            reasoning=action.reasoning,
            confidence=action.confidence,
            target_subject=action.target_subject,
            payload=dict(action.payload or {}),
        )
        orch.ledger.record_proposal(new_action)
        orch.ledger.transition(
            action_id=new_action.id,
            to_state=ActionState.STAGED,
            actor_name="Zilo",
            reason=f"Revived from over-aggressive auto-dismiss (orig={action.id})",
        )
        if ref:
            seen_refs.add(ref)
        revived += 1

    if revived:
        logger.info("[zilo] revived %d over-dismissed actions", revived)
    return revived


async def light_briefing_refresh(
    db: Any,
    user: dict,
    orch: Orchestrator,
    *,
    email_limit: int = 8,
    queue_limit: int = 40,
) -> dict[str, Any]:
    """
    Fast pass: new email drafts, WhatsApp drafts, Action Mode queue, CRM metrics.
    Does not run heavy scouts/agents (use platform_sweep for that).

    The four CRM-side ingests don't share state (each mutates a different slice
    of `orch` or returns a value), so they run concurrently. `sync_from_crm`
    and `fetch_metrics` still run after — they read the resulting orch.
    """
    uid = _business_id(user)
    ctx = await _biz_context(db, uid)
    biz_name = ctx.get("business_name", "") or ""

    report: dict[str, Any] = {"user_id": uid}

    email_res, whatsapp_res, queue_res, opps_res = await asyncio.gather(
        _safe(
            sync_and_draft_inbox(db, uid, max_messages=email_limit, biz_name=biz_name),
            label="email ingest",
        ),
        _safe(
            draft_whatsapp_inbox(db, uid, max_threads=6, biz_name=biz_name),
            label="whatsapp ingest",
        ),
        _safe(
            import_pending_queue(db, uid, orch, limit=queue_limit),
            label="queue import",
        ),
        _safe(
            import_scout_opportunities(db, uid, orch, limit=6),
            label="scout opps",
        ),
    )
    report["email"] = email_res
    report["whatsapp"] = whatsapp_res
    report["queue_imported"] = queue_res
    report["opps_imported"] = opps_res

    await sync_from_crm(db, user, orch, skip_heavy_staging=True)

    try:
        from rex.decisions.bridge import (
            sync_open_decisions_to_briefing,
            sync_outcome_reports_to_briefing,
        )
        from rex.decisions.outcomes import process_due_outcomes

        report["outcomes_processed"] = len(await process_due_outcomes(db, user))
        report["decisions_staged"] = await sync_open_decisions_to_briefing(db, user, orch)
        report["outcomes_staged"] = await sync_outcome_reports_to_briefing(db, user, orch)
    except Exception as e:
        logger.warning("[zilo] decision briefing sync: %s", e)
        report["decisions_staged"] = 0
        report["outcomes_staged"] = 0
        report["outcomes_processed"] = 0

    # Batch-fetch customer email addresses for fast whitelist lookup
    whitelist: set[str] = set()
    try:
        customers = await db.customers.find({"user_id": uid}, {"email": 1}).to_list(1000)
        for c in customers:
            e = c.get("email")
            if e:
                whitelist.add(e.lower().strip())
    except Exception as e:
        logger.warning("[zilo] failed to build customer email whitelist: %s", e)

    # Order matters: revive first (recovers items wrongly killed by an old
    # over-aggressive rule), then run the current promo-dismiss pass.
    report["revived"] = _revive_overzealously_dismissed(orch)
    report["auto_dismissed_promo"] = _auto_dismiss_promotional_staged(orch, whitelist)

    # Emit ACTION_CLEAN_SEND for SENT actions whose undo window has closed.
    # This is the only live call site — it feeds the journal ("sent cleanly")
    # and the rank engine's clean-send credit. Idempotent via orch._swept_ids.
    try:
        report["clean_sends"] = len(orch.sweep_clean_sends())
    except Exception as e:
        logger.warning("[zilo] clean-send sweep: %s", e)
        report["clean_sends"] = 0

    metrics = await fetch_metrics(db, uid)
    metrics["followups_zilo"] = sum(
        1 for a in orch.ledger.all_actions()
        if orch.ledger.current_state(a.id).value == "staged"
    )
    metrics["followups_rex"] = metrics["followups_zilo"]
    orch._metrics = metrics  # type: ignore[attr-defined]
    report["staged"] = metrics["followups_zilo"]
    return report


async def ingest_crm_signals_into_briefing(db: Any, user: dict) -> dict[str, Any]:
    """
    Persist new CRM signals onto the user's Zilo session (e.g. after inbound email).
    Safe to call from webhooks — failures are logged, not raised.
    """
    from rex.persistence.session import ZiloSessionStore

    uid = str(user.get("_id") or user.get("id") or "")
    bid = _business_id(user)
    if not uid:
        return {"skipped": "no_user_id"}

    try:
        store = ZiloSessionStore(db)
        await store.ensure_indexes()
        orch = await store.load(uid, business_id=bid)
        wire_action_mode_executor(orch, db, bid)
        report = await light_briefing_refresh(db, user, orch, email_limit=6, queue_limit=20)
        await store.save(uid, business_id=bid, orch=orch)
        logger.info("[zilo] briefing ingest uid=%s staged=%s", bid, report.get("staged"))
        return report
    except Exception as e:
        logger.exception("[zilo] briefing ingest failed uid=%s: %s", bid, e)
        return {"error": str(e)}


async def ingest_crm_signals_for_user_id(db: Any, user_id: str) -> None:
    """Resolve user doc and ingest (for email_sync / PubSub callbacks)."""
    from bson import ObjectId

    clauses: list[dict] = [{"business_id": user_id}]
    try:
        clauses.append({"_id": ObjectId(user_id)})
    except Exception:
        clauses.append({"_id": user_id})

    user = await db.users.find_one({"$or": clauses})
    if not user:
        logger.warning("[zilo] briefing ingest: user not found %s", user_id)
        return
    await ingest_crm_signals_into_briefing(db, user)
