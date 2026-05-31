"""
Full platform sweep — email, scouts, Action Mode agents, queue import.
"""

from __future__ import annotations

import logging
from typing import Any

from rex.crm.adapters import _business_id
from rex.crm.sync import fetch_metrics, sync_from_crm
from rex.integrations.action_mode_bridge import import_pending_queue, import_scout_opportunities
from rex.integrations.email_bridge import sync_and_draft_inbox
from rex.integrations.messages_bridge import draft_whatsapp_inbox
from rex.integrations.social_bridge import collect_social_drafts
from rex.integrations.sources import connected_sources_snapshot
from rex.loop import Orchestrator

logger = logging.getLogger(__name__)


async def _biz_context(db: Any, uid: str) -> dict[str, Any]:
    """Same rich context Action Mode agents use."""
    biz = await db.users.find_one({"_id": uid}) or {}
    bk = biz.get("business_knowledge") or {}
    settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
    country = (
        bk.get("country")
        or biz.get("country")
        or settings.get("country")
        or ""
    )
    return {
        "business_name": biz.get("business_name", "") or "",
        "business_type": bk.get("business_type", "") or biz.get("business_type", "") or "",
        "country": country,
        "goals": settings.get("goals", "") or "",
        "products_services": bk.get("products_services", "") or "",
        "business_description": bk.get("business_description", "") or "",
    }


async def _run_action_mode_agents(db: Any, uid: str, ctx: dict[str, Any]) -> dict[str, str]:
    """Run enabled Action Mode agents (foreground, capped)."""
    from action_mode_routes import (
        _default_agents,
        _run_admin_autopilot,
        _run_funding_hunter,
        _run_lead_gen,
        _run_social_scout,
    )

    settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
    agents_cfg = settings.get("agents", _default_agents())
    ran: dict[str, str] = {}

    async def _safe(name: str, coro):
        try:
            await coro
            ran[name] = "ok"
        except Exception as e:
            logger.warning("[zilo] agent %s failed uid=%s: %s", name, uid, e)
            ran[name] = str(e)[:120]

    tasks = []
    if agents_cfg.get("admin_autopilot", True):
        tasks.append(("admin_autopilot", _run_admin_autopilot(db, uid, ctx)))
    if agents_cfg.get("funding_hunter", False):
        tasks.append(("funding_hunter", _run_funding_hunter(db, uid, ctx)))
    if agents_cfg.get("lead_gen", False):
        tasks.append(("lead_gen", _run_lead_gen(db, uid, ctx)))
    if agents_cfg.get("social_scout", True):
        tasks.append(("social_scout", _run_social_scout(db, uid, ctx)))

    for name, coro in tasks:
        await _safe(name, coro)

    return ran


async def _run_due_scouts(db: Any, uid: str, *, max_scouts: int = 2) -> list[dict[str, Any]]:
    from scout_service import ensure_default_scouts, execute_scout, find_due_scouts, get_biz_context

    ctx = await get_biz_context(db, uid)
    await ensure_default_scouts(db, uid, ctx)
    due_all = await find_due_scouts(db, limit=20)
    scouts = [s for s in due_all if s.get("user_id") == uid][:max_scouts]

    results = []
    for scout in scouts:
        try:
            r = await execute_scout(db, scout, ctx)
            results.append(r)
        except Exception as e:
            logger.warning("[zilo] scout run failed %s: %s", scout.get("_id"), e)
    return results


async def run_platform_sweep(
    db: Any,
    user: dict,
    orch: Orchestrator,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    End-to-end Rex-style sweep:
      email pull → reply drafts → scouts → Action Mode agents → import queue → metrics
    """
    uid = _business_id(user)
    ctx = await _biz_context(db, uid)
    biz_name = ctx.get("business_name", "us")

    report: dict[str, Any] = {"user_id": uid}
    report["sources"] = await connected_sources_snapshot(db, uid)

    # 1) Email sync + draft queue
    try:
        report["email"] = await sync_and_draft_inbox(
            db, uid, biz_name=biz_name,
        )
    except Exception as e:
        logger.warning("[zilo] email bridge: %s", e)
        report["email"] = {"error": str(e)}

    # 1b) WhatsApp message drafts (review → approve to send)
    try:
        report["whatsapp"] = await draft_whatsapp_inbox(db, uid, biz_name=biz_name)
    except Exception as e:
        logger.warning("[zilo] whatsapp bridge: %s", e)
        report["whatsapp"] = {"error": str(e)}

    # 1c) Social inbox / groups (when configured)
    if force:
        try:
            report["social"] = await collect_social_drafts(db, uid, ctx)
        except Exception as e:
            report["social"] = {"error": str(e)}

    # 2) Scouts (find leads → opportunities + queue via scout_service)
    try:
        report["scouts"] = await _run_due_scouts(db, uid, max_scouts=2)
    except Exception as e:
        logger.warning("[zilo] scouts: %s", e)
        report["scouts"] = {"error": str(e)}

    # 3) Legacy Action Mode agents (WhatsApp reminders, funding, social)
    if force:
        try:
            report["agents"] = await _run_action_mode_agents(db, uid, ctx)
        except Exception as e:
            report["agents"] = {"error": str(e)}
    else:
        # Light path: admin only on routine sync
        try:
            from action_mode_routes import _run_admin_autopilot
            await _run_admin_autopilot(db, uid, ctx)
            report["agents"] = {"admin_autopilot": "ok"}
        except Exception as e:
            report["agents"] = {"error": str(e)}

    # 4) Import Action Mode queue + orphan opportunities into Zilo briefing
    report["queue_imported"] = await import_pending_queue(db, uid, orch, limit=30)
    report["opps_imported"] = await import_scout_opportunities(db, uid, orch)

    # 5) CRM metrics + light flags (no duplicate invoice staging)
    await sync_from_crm(db, user, orch, force=force, skip_heavy_staging=True)

    metrics = await fetch_metrics(db, uid)
    metrics["followups_zilo"] = sum(
        1 for a in orch.ledger.all_actions()
        if orch.ledger.current_state(a.id).value == "staged"
    )
    metrics["followups_rex"] = metrics["followups_zilo"]
    orch._metrics = metrics  # type: ignore[attr-defined]

    report["staged"] = metrics["followups_zilo"]
    return report
