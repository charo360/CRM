"""
Live Zilo Briefing ingest — pull signals from the whole CRM into staged actions.

Used on:
  - GET /api/rex/home (light refresh)
  - Email webhooks / sync after new messages land
"""

from __future__ import annotations

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
    """
    uid = _business_id(user)
    ctx = await _biz_context(db, uid)
    biz_name = ctx.get("business_name", "") or ""

    report: dict[str, Any] = {"user_id": uid}

    try:
        report["email"] = await sync_and_draft_inbox(
            db, uid, max_messages=email_limit, biz_name=biz_name,
        )
    except Exception as e:
        logger.warning("[zilo] briefing email ingest: %s", e)
        report["email"] = {"error": str(e)}

    try:
        report["whatsapp"] = await draft_whatsapp_inbox(
            db, uid, max_threads=6, biz_name=biz_name,
        )
    except Exception as e:
        logger.warning("[zilo] briefing whatsapp ingest: %s", e)
        report["whatsapp"] = {"error": str(e)}

    report["queue_imported"] = await import_pending_queue(db, uid, orch, limit=queue_limit)
    report["opps_imported"] = await import_scout_opportunities(db, uid, orch, limit=6)

    await sync_from_crm(db, user, orch, skip_heavy_staging=True)

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
