"""
Per-user Zilo session — load/save Orchestrator state in MongoDB.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from rex.actions.ledger import Ledger, InMemoryLedgerStore
from rex.actions.stub_executor import ensure_stub_executor  # demo + fallback
from rex.demo_seed import build_demo_orchestrator
from rex.loop import Orchestrator
from rex.memory.notebook import Notebook
from rex.memory.store import InMemoryNotebookStore
from rex.persistence import codec
from rex.ranks.store import InMemoryEventStore

logger = logging.getLogger(__name__)

COLLECTION = "zilo_sessions"
_INDEX_ENSURED = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _relationship_day(created_at: datetime) -> int:
    start = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    delta = _utc_now() - start
    return max(1, delta.days + 1)


class ZiloSessionStore:
    """Mongo-backed orchestrator sessions keyed by CRM user id."""

    _cache: dict[str, Orchestrator] = {}

    def __init__(self, db: Any) -> None:
        self._db = db
        self._col = db[COLLECTION]

    async def ensure_indexes(self) -> None:
        global _INDEX_ENSURED
        if _INDEX_ENSURED:
            return
        try:
            await self._col.create_index("user_id", unique=True)
            _INDEX_ENSURED = True
        except Exception as e:
            logger.warning("[zilo] index create: %s", e)

    def _orch_from_doc(self, doc: dict[str, Any]) -> Orchestrator:
        store = InMemoryLedgerStore()
        actions = tuple(codec.action_from_dict(a) for a in doc.get("actions") or [])
        changes = tuple(codec.change_from_dict(c) for c in doc.get("changes") or [])
        store.load_snapshot(actions, changes)
        ledger = Ledger(store=store)

        events = tuple(codec.trust_event_from_dict(e) for e in doc.get("events") or [])
        event_store = InMemoryEventStore(events)

        entries = tuple(codec.notebook_entry_from_dict(n) for n in doc.get("notebook") or [])
        notebook = Notebook(store=InMemoryNotebookStore(entries))

        orch = Orchestrator(ledger=ledger, event_store=event_store, notebook=notebook)
        ensure_stub_executor(orch)
        orch._swept_ids = set(doc.get("swept_ids") or [])
        orch._disabled_categories = set(doc.get("disabled_categories") or [])
        orch._lead_scout_interval = doc.get("lead_scout_interval", "24h")
        orch._open_scout_interval = doc.get("open_scout_interval", "12h")
        orch._fb_group_interval = doc.get("fb_group_interval", "6h")
        created = doc.get("created_at")
        if created:
            orch._relationship_day = _relationship_day(codec._parse_dt(created))  # type: ignore[attr-defined]
        else:
            orch._relationship_day = int(doc.get("relationship_day") or 1)  # type: ignore[attr-defined]
        orch._metrics = dict(doc.get("metrics") or {})  # type: ignore[attr-defined]
        orch._live_mode = not doc.get("demo_mode", False)  # type: ignore[attr-defined]
        # Journal engagement state
        orch._journal_last_visit_day = doc.get("journal_last_visit_day")  # type: ignore[attr-defined]
        orch._journal_streak = int(doc.get("journal_streak") or 0)  # type: ignore[attr-defined]
        orch._journal_shown_milestones = list(doc.get("journal_shown_milestones") or [])  # type: ignore[attr-defined]
        return orch

    async def load(self, user_id: str, *, business_id: str) -> Orchestrator:
        cached = self._cache.get(user_id)
        if cached is not None:
            return cached

        doc = await self._col.find_one({"user_id": user_id})
        if doc:
            orch = self._orch_from_doc(doc)
            self._cache[user_id] = orch
            return orch

        orch = Orchestrator()
        ensure_stub_executor(orch)
        orch._relationship_day = 1  # type: ignore[attr-defined]
        orch._disabled_categories = set()
        orch._lead_scout_interval = "24h"
        orch._open_scout_interval = "12h"
        orch._fb_group_interval = "6h"
        orch._metrics = {}  # type: ignore[attr-defined]
        orch._live_mode = True  # type: ignore[attr-defined]
        await self.save(user_id, business_id=business_id, orch=orch)
        return orch

    async def load_demo(self, user_id: str, *, business_id: str) -> Orchestrator:
        orch = build_demo_orchestrator()
        orch._live_mode = False  # type: ignore[attr-defined]
        orch._metrics = {}  # type: ignore[attr-defined]
        self._cache[user_id] = orch
        await self._save_doc(
            user_id,
            business_id=business_id,
            orch=orch,
            demo_mode=True,
        )
        return orch

    async def save(
        self,
        user_id: str,
        *,
        business_id: str,
        orch: Orchestrator,
        demo_mode: bool | None = None,
    ) -> None:
        await self._save_doc(
            user_id,
            business_id=business_id,
            orch=orch,
            demo_mode=demo_mode,
        )
        self._cache[user_id] = orch

    def _compact_orchestrator(self, orch: Orchestrator) -> None:
        """Prune resolved actions and changes in ledger to limit document size in DB."""
        try:
            from datetime import timedelta
            from rex.actions.primitives import ActionState

            ledger = orch.ledger
            swept_ids = set(orch._swept_ids)

            all_actions = ledger.all_actions()
            active_actions = []
            resolved_actions = []

            for action in all_actions:
                try:
                    state = ledger.current_state(action.id)
                except KeyError:
                    continue

                is_active = False
                if state in (ActionState.PROPOSED, ActionState.STAGED, ActionState.APPROVED):
                    is_active = True
                elif state == ActionState.SENT:
                    if action.id not in swept_ids:
                        is_active = True
                    elif action.proposed_at:
                        now_val = datetime.now(action.proposed_at.tzinfo or timezone.utc)
                        if now_val - action.proposed_at < timedelta(minutes=45):
                            is_active = True

                if is_active:
                    active_actions.append(action)
                else:
                    resolved_actions.append(action)

            # Sort resolved by proposed_at descending, keep 50
            tz_min = datetime.min.replace(tzinfo=timezone.utc)
            def get_sort_key(act):
                dt = act.proposed_at
                if not dt:
                    return tz_min
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

            resolved_actions.sort(key=get_sort_key, reverse=True)
            max_resolved = 50
            keep_resolved = resolved_actions[:max_resolved]

            keep_ids = {a.id for a in active_actions} | {a.id for a in keep_resolved}

            keep_actions_list = [a for a in all_actions if a.id in keep_ids]
            all_changes = ledger.all_changes()
            keep_changes_list = [c for c in all_changes if c.action_id in keep_ids]

            ledger._store.load_snapshot(keep_actions_list, keep_changes_list)
            orch._swept_ids = swept_ids & keep_ids
            logger.info(
                "[zilo] compacted session ledger: actions count %d -> %d, changes %d -> %d",
                len(all_actions), len(keep_actions_list),
                len(all_changes), len(keep_changes_list)
            )
        except Exception as e:
            logger.exception("[zilo] failed to compact session ledger: %s", e)

    async def _save_doc(
        self,
        user_id: str,
        *,
        business_id: str,
        orch: Orchestrator,
        demo_mode: bool | None = None,
    ) -> None:
        self._compact_orchestrator(orch)
        existing = await self._col.find_one({"user_id": user_id})
        created_at = (existing or {}).get("created_at") or _utc_now()
        rel_day = getattr(orch, "_relationship_day", None) or _relationship_day(
            codec._parse_dt(created_at) if isinstance(created_at, str) else created_at
        )
        metrics = getattr(orch, "_metrics", None) or {}
        is_demo = demo_mode if demo_mode is not None else (existing or {}).get("demo_mode", False)

        doc: dict[str, Any] = {
            "user_id": user_id,
            "business_id": business_id,
            "created_at": created_at,
            "updated_at": _utc_now(),
            "relationship_day": rel_day,
            "last_sync_at": getattr(orch, "_last_sync_at", None),
            "demo_mode": is_demo,
            "metrics": metrics,
            "events": [codec.trust_event_to_dict(e) for e in orch.event_store.all_events()],
            "actions": [codec.action_to_dict(a) for a in orch.ledger.all_actions()],
            "changes": [codec.change_to_dict(c) for c in orch.ledger._store.all_changes()],  # noqa: SLF001
            "notebook": [codec.notebook_entry_to_dict(e) for e in orch.notebook.all()],
            "swept_ids": list(orch._swept_ids),
            "disabled_categories": list(getattr(orch, "_disabled_categories", set())),
            "lead_scout_interval": getattr(orch, "_lead_scout_interval", "24h"),
            "open_scout_interval": getattr(orch, "_open_scout_interval", "12h"),
            "fb_group_interval": getattr(orch, "_fb_group_interval", "6h"),
            "journal_last_visit_day": getattr(orch, "_journal_last_visit_day", None),
            "journal_streak": int(getattr(orch, "_journal_streak", 0) or 0),
            "journal_shown_milestones": list(getattr(orch, "_journal_shown_milestones", []) or []),
        }
        await self._col.update_one({"user_id": user_id}, {"$set": doc}, upsert=True)

    def invalidate_cache(self, user_id: str) -> None:
        self._cache.pop(user_id, None)

    async def reset(self, user_id: str, *, business_id: str, demo: bool = False) -> Orchestrator:
        await self._col.delete_one({"user_id": user_id})
        self.invalidate_cache(user_id)
        if demo:
            return await self.load_demo(user_id, business_id=business_id)
        return await self.load(user_id, business_id=business_id)
