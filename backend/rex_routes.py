"""
Zilo Chief-of-Staff HTTP routes (API prefix /api/rex/* — rename to /api/zilo later).

Persists ledger, trust events, and notebook in Mongo when `db` is provided.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from rex.api_serializers import serialize_journal, serialize_ledger, serialize_notebook
from rex.crm.adapters import make_live_scanner
from rex.crm.sync import sync_from_crm
from rex.actions.stub_executor import ensure_stub_executor
from rex.demo_seed import build_demo_orchestrator, serialize_home
from rex.integrations.action_mode_bridge import wire_action_mode_executor
from rex.integrations.briefing_refresh import light_briefing_refresh
from rex.integrations.platform_sweep import run_platform_sweep
from rex.team_api import serialize_team
from rex.loop import Orchestrator
from rex.onboarding import (
    OnboardingEngine,
    OnboardingState,
    CommunicationChannel,
    DirectnessLevel,
    HonestDemoScanner,
)
from rex.persistence.session import ZiloSessionStore

logger = logging.getLogger(__name__)


def _uid(user: dict) -> str:
    return str(user.get("_id") or user.get("id") or "anonymous")


def _business_id(user: dict) -> str:
    return str(user.get("business_id") or user.get("_id") or "anonymous")


async def _persist_edited_draft(
    db: Any,
    orch: Orchestrator,
    action_id: str,
    draft_body: str,
    uid: str,
) -> None:
    """Save user-edited draft on the Action Mode queue item before send."""
    action = orch.ledger.get(action_id)
    if not action or not draft_body:
        return
    qid = (action.payload or {}).get("queue_id")
    if not qid:
        return
    await db.action_mode_queue.update_one(
        {"_id": qid, "user_id": uid},
        {"$set": {"draft_content": draft_body, "user_edited": True}},
    )


# ── In-memory fallback (no db) ────────────────────────────────────────────

_ENGINES: dict[str, OnboardingEngine] = {}
_ORCHESTRATORS: dict[str, Orchestrator] = {}
_SESSION: ZiloSessionStore | None = None


def _use_live_db(db: Any | None) -> bool:
    if db is None:
        return False
    if os.environ.get("ZILO_DEMO_ONLY", "").lower() in ("1", "true", "yes"):
        return False
    return True


def _get_engine(user: dict, db: Any | None = None) -> OnboardingEngine:
    user_id = _uid(user)
    engine = _ENGINES.get(user_id)
    if engine is None:
        scanner = make_live_scanner(db, user) if _use_live_db(db) else HonestDemoScanner()
        engine = OnboardingEngine(scanner=scanner)
        _ENGINES[user_id] = engine
    return engine


def _reset_engine(user: dict, db: Any | None = None) -> OnboardingEngine:
    user_id = _uid(user)
    scanner = make_live_scanner(db, user) if _use_live_db(db) else HonestDemoScanner()
    engine = OnboardingEngine(scanner=scanner)
    _ENGINES[user_id] = engine
    return engine


async def _get_orchestrator(
    user: dict,
    db: Any | None,
    *,
    light: bool = True,
    refresh: bool = True,
) -> Orchestrator:
    """Load persisted state.

    refresh=False  → just load persisted orch, no CRM/email ingest. Use for
                     read-only memory surfaces (journal, notebook, ledger).
    light=True    → load + run light briefing refresh (email, queue, metrics).
    light=False   → load + run full platform sweep (scouts, agents).
    """
    uid = _uid(user)
    bid = _business_id(user)

    if not _use_live_db(db):
        orch = _ORCHESTRATORS.get(uid)
        if orch is None:
            orch = build_demo_orchestrator()
            _ORCHESTRATORS[uid] = orch
        return orch

    store = ZiloSessionStore(db)
    global _SESSION
    _SESSION = store
    await store.ensure_indexes()
    orch = await store.load(uid, business_id=bid)
    wire_action_mode_executor(orch, db, uid)

    if not refresh:
        return orch

    if light:
        await light_briefing_refresh(db, user, orch)
        await store.save(uid, business_id=bid, orch=orch)
        return orch

    await run_platform_sweep(db, user, orch, force=True)
    await store.save(uid, business_id=bid, orch=orch)
    return orch


async def _persist(user: dict, db: Any | None, orch: Orchestrator) -> None:
    if not _use_live_db(db):
        _ORCHESTRATORS[_uid(user)] = orch
        return
    if _SESSION:
        await _SESSION.save(_uid(user), business_id=_business_id(user), orch=orch)


_BG_REFRESH_INFLIGHT: set[str] = set()


async def _background_briefing_refresh(user: dict, db: Any, uid: str, bid: str) -> None:
    """Fire-and-forget light refresh for the SWR /home path.

    Loads a fresh orch (the request's orch is already returned to the client),
    runs the light refresh, persists. Deduped per-user so rapid reloads don't
    stack refreshes on top of each other.
    """
    if uid in _BG_REFRESH_INFLIGHT:
        return
    _BG_REFRESH_INFLIGHT.add(uid)
    try:
        store = ZiloSessionStore(db)
        await store.ensure_indexes()
        orch = await store.load(uid, business_id=bid)
        wire_action_mode_executor(orch, db, uid)
        await light_briefing_refresh(db, user, orch)
        await store.save(uid, business_id=bid, orch=orch)
        logger.info("[zilo] background briefing refresh complete uid=%s", uid)
    except Exception as e:
        logger.warning("[zilo] background briefing refresh failed uid=%s: %s", uid, e)
    finally:
        _BG_REFRESH_INFLIGHT.discard(uid)


# ── Request/response models ───────────────────────────────────────────────

class StartResponse(BaseModel):
    welcome: str
    state: str
    question: Optional[str] = None


class AnswerRequest(BaseModel):
    value: str


class AnswerResponse(BaseModel):
    next_prompt: str
    state: str
    question: Optional[str] = None
    i_see_it: Optional[str] = None
    complete: bool = False


class StateResponse(BaseModel):
    state: str
    question: Optional[str] = None
    complete: bool


class PreferencesResponse(BaseModel):
    preferences: dict


class ActionVerbRequest(BaseModel):
    reason: Optional[str] = None
    draft_body: Optional[str] = None


class HomeResetRequest(BaseModel):
    demo: bool = False


class BriefingPreferencesRequest(BaseModel):
    enabled_categories: list[str]
    lead_scout_interval: Optional[str] = "24h"
    open_scout_interval: Optional[str] = "12h"
    fb_group_interval: Optional[str] = "6h"


class RankChangeRequest(BaseModel):
    category: str
    reason: Optional[str] = None
    to_rank: Optional[str] = None  # display name like "Sender"; defaults to one step up/down


class EditNotebookEntryRequest(BaseModel):
    text: str


class EditCompanyRequest(BaseModel):
    description: str



# ── Router factory ────────────────────────────────────────────────────────

def init_rex_routes(get_current_user, db: Any | None = None) -> APIRouter:
    """Build the Rex router with the host app's auth dependency."""
    router = APIRouter(prefix="/api/rex", tags=["rex"])

    async def _session_store() -> ZiloSessionStore:
        global _SESSION
        if _SESSION is None and _use_live_db(db):
            _SESSION = ZiloSessionStore(db)
            await _SESSION.ensure_indexes()
        if _SESSION is None:
            raise HTTPException(status_code=501, detail="Database not configured")
        return _SESSION

    # ── Zilo Briefing (live CRM feed) ────────────────────────────────────

    @router.get("/home")
    async def rex_home(
        user=Depends(get_current_user),
        refresh: bool = Query(False, description="Full platform sweep (slow, blocks)"),
        live: bool = Query(False, description="Block on light refresh before returning"),
        background: bool = Query(True, description="Kicks light refresh in background"),
    ):
        """Stale-while-revalidate by default.

        Returns the persisted briefing instantly and kicks the light refresh in
        the background — the next page load sees fresh data. Set ?live=true to
        block on the refresh (e.g. user-clicked "refresh now"), or ?refresh=true
        for a full platform sweep.
        """
        try:
            if refresh and _use_live_db(db):
                orch = await _get_orchestrator(user, db, light=False)
            elif live and _use_live_db(db):
                orch = await _get_orchestrator(user, db, light=True)
            else:
                orch = await _get_orchestrator(user, db, refresh=False)
                if background and _use_live_db(db):
                    asyncio.create_task(
                        _background_briefing_refresh(user, db, _uid(user), _business_id(user))
                    )
            return serialize_home(orch)
        except Exception as e:
            logger.exception("[zilo] /home failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e)[:500])

    @router.post("/home/reset")
    async def rex_home_reset(body: HomeResetRequest, user=Depends(get_current_user)):
        uid = _uid(user)
        bid = _business_id(user)
        if _use_live_db(db):
            store = await _session_store()
            orch = await store.reset(uid, business_id=bid, demo=body.demo)
            if not body.demo:
                wire_action_mode_executor(orch, db, uid)
                await run_platform_sweep(db, user, orch, force=True)
                await store.save(uid, business_id=bid, orch=orch)
            return {"ok": True, "demo": body.demo}
        if body.demo:
            _ORCHESTRATORS[uid] = build_demo_orchestrator()
        else:
            o = Orchestrator()
            ensure_stub_executor(o)
            _ORCHESTRATORS[uid] = o
        return {"ok": True, "demo": body.demo}

    @router.post("/actions/{action_id}/approve")
    async def rex_approve(action_id: str, body: ActionVerbRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        if body.draft_body and db is not None:
            await _persist_edited_draft(db, orch, action_id, body.draft_body.strip(), _uid(user))
        try:
            result = orch.approve(action_id, reason=body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {
            "ok": True,
            "action_id": result.action_id,
            "final_state": result.final_state.value,
            "home": serialize_home(orch),
        }

    @router.post("/actions/{action_id}/dismiss")
    async def rex_dismiss(action_id: str, body: ActionVerbRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            orch.dismiss(action_id, reason=body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.post("/actions/{action_id}/reject")
    async def rex_reject(action_id: str, body: ActionVerbRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            orch.reject(action_id, reason=body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.post("/actions/{action_id}/undo")
    async def rex_undo(action_id: str, body: ActionVerbRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            orch.undo(action_id, reason=body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.post("/actions/{action_id}/like")
    async def rex_like(action_id: str, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            action = orch.ledger.get(action_id)
            if not action:
                raise HTTPException(status_code=404, detail="Action not found")
            from dataclasses import replace
            payload = dict(action.payload or {})
            payload["feedback"] = "like"
            new_action = replace(action, payload=payload)
            orch.ledger._store._actions[action_id] = new_action
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.post("/actions/{action_id}/dislike")
    async def rex_dislike(action_id: str, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            action = orch.ledger.get(action_id)
            if not action:
                raise HTTPException(status_code=404, detail="Action not found")
            from dataclasses import replace
            payload = dict(action.payload or {})
            payload["feedback"] = "dislike"
            new_action = replace(action, payload=payload)
            orch.ledger._store._actions[action_id] = new_action
            orch.dismiss(action_id, reason="User disliked this item.")
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.get("/briefing/preferences")
    async def get_briefing_preferences(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        disabled = getattr(orch, "_disabled_categories", set())
        
        from rex.ranks.categories import all_categories
        categories_data = []
        for cat in all_categories():
            categories_data.append({
                "name": cat.name,
                "display": cat.display,
                "tier": cat.tier.value,
                "enabled": cat.name not in disabled
            })
        return {
            "categories": categories_data,
            "lead_scout_interval": getattr(orch, "_lead_scout_interval", "24h"),
            "open_scout_interval": getattr(orch, "_open_scout_interval", "12h"),
            "fb_group_interval": getattr(orch, "_fb_group_interval", "6h"),
        }

    @router.post("/briefing/preferences")
    async def save_briefing_preferences(body: BriefingPreferencesRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        uid = _uid(user)
        
        from rex.ranks.categories import all_categories
        all_names = {cat.name for cat in all_categories()}
        enabled_names = set(body.enabled_categories)
        disabled_names = all_names - enabled_names
        
        orch._disabled_categories = disabled_names
        orch._lead_scout_interval = body.lead_scout_interval or "24h"
        orch._open_scout_interval = body.open_scout_interval or "12h"
        orch._fb_group_interval = body.fb_group_interval or "6h"
        
        await _persist(user, db, orch)
        
        # Propagate custom intervals to the user's active database scouts
        try:
            from datetime import datetime, timedelta
            
            # 1. Update Lead Scouts (Lead Finder)
            delta_map = {
                "1h": timedelta(hours=1),
                "2h": timedelta(hours=2),
                "6h": timedelta(hours=6),
                "12h": timedelta(hours=12),
                "24h": timedelta(hours=24),
                "daily": timedelta(hours=24),
                "weekly": timedelta(days=7),
            }
            lead_delta = delta_map.get(body.lead_scout_interval)
            if lead_delta:
                await db["lead_scouts"].update_many(
                    {"user_id": uid, "enabled": True},
                    {"$set": {
                        "frequency": body.lead_scout_interval,
                        "next_run": datetime.utcnow() + lead_delta
                    }}
                )
            else:
                await db["lead_scouts"].update_many(
                    {"user_id": uid, "enabled": True},
                    {"$set": {
                        "frequency": "manual"
                    }, "$unset": {"next_run": ""}}
                )
                
            # 2. Update Open Scouts (Zilo Scouts / Web Finder)
            freq_hours_map = {
                "1h": 1,
                "2h": 2,
                "6h": 6,
                "12h": 12,
                "24h": 24,
                "daily": 24,
                "weekly": 168,
            }
            open_hours = freq_hours_map.get(body.open_scout_interval, 12)
            await db["zilo_scouts"].update_many(
                {"user_id": uid, "is_active": True},
                {"$set": {
                    "frequency": body.open_scout_interval,
                    "frequency_hours": open_hours,
                    "next_run_at": datetime.utcnow() + timedelta(hours=open_hours)
                }}
            )
            
            logger.info("[preferences] propagated scheduling changes to active scouts for user=%s", uid)
        except Exception as e:
            logger.error("[preferences] failed to propagate scheduling changes to scouts: %s", e)
            
        return {"ok": True, "home": serialize_home(orch)}

    # ── Memory surfaces (persisted) ─────────────────────────────────────

    @router.get("/notebook")
    async def rex_notebook(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        return serialize_notebook(orch)

    @router.post("/notebook/{entry_id}")
    async def edit_notebook_entry(
        entry_id: str,
        body: EditNotebookEntryRequest,
        user=Depends(get_current_user),
    ):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            orch.notebook.update_text(entry_id, body.text, by_user=True)
        except KeyError:
            raise HTTPException(status_code=404, detail="Notebook entry not found")
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.delete("/notebook/{entry_id}")
    async def delete_notebook_entry(
        entry_id: str,
        user=Depends(get_current_user),
    ):
        orch = await _get_orchestrator(user, db, refresh=False)
        deleted = orch.notebook.delete(entry_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Notebook entry not found")
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.post("/companies/{company_id}")
    async def edit_company(
        company_id: str,
        body: EditCompanyRequest,
        user=Depends(get_current_user),
    ):
        orch = await _get_orchestrator(user, db, refresh=False)
        companies = getattr(orch, "_companies", [])
        found = False
        for c in companies:
            if c.get("id") == company_id:
                c["description"] = body.description
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Company not found")
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.delete("/companies/{company_id}")
    async def delete_company(
        company_id: str,
        user=Depends(get_current_user),
    ):
        orch = await _get_orchestrator(user, db, refresh=False)
        companies = getattr(orch, "_companies", [])
        filtered = [c for c in companies if c.get("id") != company_id]
        if len(filtered) == len(companies):
            raise HTTPException(status_code=404, detail="Company not found")
        orch._companies = filtered
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}


    @router.post("/notebook/clear")
    async def clear_notebook(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        for entry in list(orch.notebook.all()):
            orch.notebook.delete(entry.id)
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.post("/notebook/refresh")
    async def refresh_notebook(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        for entry in list(orch.notebook.all()):
            orch.notebook.delete(entry.id)
        if hasattr(orch, "_companies"):
            orch._companies = []
        from rex.persistence.extractor import extract_and_populate_notebook
        uid = _uid(user)
        bid = _business_id(user)
        try:
            await extract_and_populate_notebook(db, uid, orch)
        except Exception as e:
            logger.exception("[zilo-session] failed during manual refresh: %s", e)
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.get("/notebook/export")
    async def export_notebook(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        data = serialize_notebook(orch)
        import json
        from fastapi import Response
        content = json.dumps(data, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=zilo_notebook_export.json"
            }
        )

    @router.get("/ledger")
    async def rex_ledger(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        return serialize_ledger(orch)

    @router.get("/journal")
    async def rex_journal(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        payload = await serialize_journal(orch)  # mutates streak + shown_milestones
        await _persist(user, db, orch)
        return payload

    @router.get("/standings")
    async def rex_standings(user=Depends(get_current_user)):
        """Per-category trust ladder for Zilo (Chief of Staff)."""
        from rex.identity import CHIEF_OF_STAFF_NAME
        from rex.ranks.categories import all_categories
        from rex.ranks.events import Rank

        orch = await _get_orchestrator(user, db, refresh=False)
        rows = []
        for cat in all_categories():
            s = orch.engine.standing(CHIEF_OF_STAFF_NAME, cat.name)
            rows.append({
                "category": cat.name,
                "display": cat.display,
                "tier": int(cat.tier),
                "rank": s.rank.display,
                "rank_value": int(s.rank),
                "on_probation": s.on_probation,
            })
        return {
            "standings": rows,
            "ranks": [r.display for r in Rank],
            "max_rank_value": int(Rank.CHIEF_OF_STAFF),
        }

    async def _apply_rank_change(
        user: dict,
        body: RankChangeRequest,
        *,
        direction: str,
    ) -> dict:
        from rex.identity import CHIEF_OF_STAFF_NAME
        from rex.ranks.categories import is_category
        from rex.ranks.engine import RankEngine
        from rex.ranks.events import Rank, TrustEvent

        if not is_category(body.category):
            raise HTTPException(status_code=400, detail=f"Unknown category: {body.category}")

        orch = await _get_orchestrator(user, db, refresh=False)
        standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, body.category)
        from_rank = standing.rank

        if body.to_rank:
            try:
                to_rank = Rank.from_display(body.to_rank)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Unknown rank: {body.to_rank}")
        else:
            step = 1 if direction == "promote" else -1
            new_value = int(from_rank) + step
            if new_value < int(Rank.OBSERVER) or new_value > int(Rank.CHIEF_OF_STAFF):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Already at Chief of Staff." if direction == "promote"
                        else "Already at Observer."
                    ),
                )
            to_rank = Rank(new_value)

        if direction == "promote" and int(to_rank) <= int(from_rank):
            raise HTTPException(status_code=409, detail="Target rank is not a promotion.")
        if direction == "demote" and int(to_rank) >= int(from_rank):
            raise HTTPException(status_code=409, detail="Target rank is not a demotion.")

        if direction == "promote":
            event = TrustEvent.user_promoted_rex(
                category=body.category,
                from_rank=from_rank,
                to_rank=to_rank,
                reason=body.reason,
            )
        else:
            event = TrustEvent.user_demoted_rex(
                category=body.category,
                from_rank=from_rank,
                to_rank=to_rank,
                reason=body.reason,
            )

        orch.event_store.append(event)
        orch.engine = RankEngine.from_events(orch.event_store)
        await _persist(user, db, orch)

        return {
            "ok": True,
            "category": body.category,
            "from_rank": from_rank.display,
            "to_rank": to_rank.display,
        }

    @router.post("/promote")
    async def rex_promote(body: RankChangeRequest, user=Depends(get_current_user)):
        return await _apply_rank_change(user, body, direction="promote")

    @router.post("/demote")
    async def rex_demote(body: RankChangeRequest, user=Depends(get_current_user)):
        return await _apply_rank_change(user, body, direction="demote")

    @router.get("/team")
    async def rex_team(user=Depends(get_current_user)):
        """All AI agents — Zilo Chat specialists, deputies, and Action Mode runners.

        Team roster is static; per-agent standings are skipped to keep this endpoint
        snappy. Loading the orchestrator + calling `engine.standing()` for each
        sub-agent triggered per-agent Mongo round-trips that could hang on slow links.
        """
        try:
            return serialize_team(None)
        except Exception as e:
            logger.exception("[zilo] /team failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e)[:500])

    async def _background_sync_task(db: Any, user: dict, uid: str, bid: str):
        try:
            store = ZiloSessionStore(db)
            orch = await store.load(uid, business_id=bid)
            wire_action_mode_executor(orch, db, uid)
            await run_platform_sweep(db, user, orch, force=True)
            await store.save(uid, business_id=bid, orch=orch)
            logger.info("[zilo] background /sync complete uid=%s", uid)
        except Exception as e:
            logger.warning("[zilo] background /sync failed uid=%s: %s", uid, e)

    @router.post("/sync")
    async def rex_sync(user=Depends(get_current_user)):
        """Email pull, scouts, Action Mode agents, queue import, metrics."""
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="CRM sync requires database")
        uid = _uid(user)
        bid = _business_id(user)
        store = await _session_store()
        orch = await store.load(uid, business_id=bid)
        
        # Run the heavy sync in the background to prevent 500 proxy timeouts
        asyncio.create_task(_background_sync_task(db, user, uid, bid))
        
        return {"ok": True, "report": {"status": "syncing in background"}, "home": serialize_home(orch)}

    # ── Onboarding ───────────────────────────────────────────────────────

    @router.post("/onboarding/start", response_model=StartResponse)
    async def onboarding_start(user=Depends(get_current_user)):
        engine = _reset_engine(user, db)
        welcome = engine.start()
        return StartResponse(
            welcome=welcome,
            state=engine.state.value,
            question=engine.get_current_question(),
        )

    @router.get("/onboarding/state", response_model=StateResponse)
    async def onboarding_state(user=Depends(get_current_user)):
        engine = _get_engine(user, db)
        return StateResponse(
            state=engine.state.value,
            question=engine.get_current_question(),
            complete=engine.state in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE),
        )

    @router.post("/onboarding/answer/{question_num}", response_model=AnswerResponse)
    async def onboarding_answer(question_num: int, body: AnswerRequest, user=Depends(get_current_user)):
        engine = _get_engine(user, db)
        value = (body.value or "").strip()

        try:
            if question_num == 1:
                prompt = engine.answer_question_1(value)
            elif question_num == 2:
                prompt = engine.answer_question_2(value)
            elif question_num == 3:
                prompt = engine.answer_question_3(value)
            elif question_num == 4:
                try:
                    channel = CommunicationChannel(value.lower())
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Unknown channel: {value}")
                prompt = engine.answer_question_4(channel)
            elif question_num == 5:
                try:
                    directness = DirectnessLevel(value.lower())
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Unknown directness: {value}")
                prompt = engine.answer_question_5(directness)
            elif question_num == 6:
                prompt = engine.answer_question_6(value)
            else:
                raise HTTPException(status_code=400, detail="question_num must be 1-6")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        complete = engine.state in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE)
        i_see_it = None
        if engine.i_see_it is not None:
            i_see_it = engine.i_see_it.rex_response

        return AnswerResponse(
            next_prompt=prompt,
            state=engine.state.value,
            question=engine.get_current_question(),
            i_see_it=i_see_it,
            complete=complete,
        )

    @router.get("/onboarding/preferences", response_model=PreferencesResponse)
    async def onboarding_preferences(user=Depends(get_current_user)):
        engine = _get_engine(user, db)
        if engine.state not in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE):
            raise HTTPException(status_code=409, detail="Onboarding not complete yet")
        return PreferencesResponse(preferences=engine.get_preferences())

    @router.post("/onboarding/reset")
    async def onboarding_reset(user=Depends(get_current_user)):
        engine = _reset_engine(user, db)
        return {"ok": True, "state": engine.state.value}

    return router
