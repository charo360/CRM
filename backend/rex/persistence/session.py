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


class OptimisticLockError(Exception):
    """Raised when an update fails because the document was modified concurrently."""
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _relationship_day(created_at: datetime) -> int:
    start = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    delta = _utc_now() - start
    return max(1, delta.days + 1)


class ZiloSessionStore:
    """Mongo-backed orchestrator sessions keyed by CRM user id."""

    def __init__(self, db: Any) -> None:
        self._db = db
        self._col = db[COLLECTION]
        self._cache: dict[str, Orchestrator] = {}

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
        override_day = doc.get("relationship_day_override")
        created = doc.get("created_at")
        if override_day is not None:
            orch._relationship_day = int(override_day)  # type: ignore[attr-defined]
            orch._relationship_day_override = int(override_day)  # type: ignore[attr-defined]
        elif created:
            orch._relationship_day = _relationship_day(codec._parse_dt(created))  # type: ignore[attr-defined]
        else:
            orch._relationship_day = int(doc.get("relationship_day") or 1)  # type: ignore[attr-defined]
        orch._metrics = dict(doc.get("metrics") or {})  # type: ignore[attr-defined]
        orch._live_mode = not doc.get("demo_mode", False)  # type: ignore[attr-defined]
        # Journal engagement state
        orch._journal_last_visit_day = doc.get("journal_last_visit_day")  # type: ignore[attr-defined]
        orch._journal_streak = int(doc.get("journal_streak") or 0)  # type: ignore[attr-defined]
        orch._companies = doc.get("companies") or []
        return orch

    async def load(self, user_id: str, *, business_id: str) -> Orchestrator:
        cached = self._cache.get(user_id)
        if cached is not None:
            return cached

        doc = await self._col.find_one({"user_id": user_id})
        if doc:
            orch = self._orch_from_doc(doc)
            # Track the DB timestamp at load-time for optimistic-locking on save
            orch._loaded_updated_at = doc.get("updated_at")  # type: ignore[attr-defined]
            self._cache[user_id] = orch
            
            # ONLY seed mock data if we are in demo mode (live_mode is False)
            if not getattr(orch, "_live_mode", True):
                notebook_seeded = False
                if len(orch.notebook.all()) == 0:
                    from rex.demo_seed import seed_notebook_history
                    seed_notebook_history(orch)
                    notebook_seeded = True
                    
                if not getattr(orch, "_companies", None):
                    from rex.demo_seed import seed_companies_history
                    seed_companies_history(orch)
                    await self.save(user_id, business_id=business_id, orch=orch)
                elif notebook_seeded:
                    await self.save(user_id, business_id=business_id, orch=orch)
            else:
                # For live mode, extract notebook if:
                #   a) it's completely empty, OR
                #   b) companies are missing, OR
                #   c) the notebook entries are stale (oldest entry > 7 days)
                #      — ensures new emails/contacts are picked up weekly
                notebook_entries = orch.notebook.all()
                is_empty = len(notebook_entries) == 0
                no_companies = not getattr(orch, "_companies", None)
                is_stale = False
                if not is_empty and not no_companies:
                    oldest = min((e.created_at for e in notebook_entries), default=None)
                    if oldest:
                        age_days = (_utc_now() - (oldest if oldest.tzinfo else oldest.replace(tzinfo=timezone.utc))).days
                        is_stale = age_days >= 7

                if is_empty or no_companies or is_stale:
                    try:
                        from rex.persistence.extractor import extract_and_populate_notebook
                        if not is_empty:
                            # Clear stale entries before re-extraction
                            # Keep user-edited entries — they contain real knowledge
                            for entry in list(notebook_entries):
                                if not entry.edited_by_user:
                                    orch.notebook.delete(entry.id)
                            orch._companies = []
                        await extract_and_populate_notebook(self._db, user_id, orch)
                        await self.save(user_id, business_id=business_id, orch=orch)
                        logger.info("[zilo-session] notebook re-extracted uid=%s stale=%s", user_id, is_stale)
                    except Exception as e:
                        logger.exception("[zilo-session] failed during dynamic extraction: %s", e)

                # Sync any trust events that happened since last session into notebook
                try:
                    from rex.memory.notebook_sync import sync_events_to_notebook
                    synced = sync_events_to_notebook(
                        events=orch.event_store.all_events(),
                        ledger=orch.ledger,
                        notebook=orch.notebook,
                    )
                    if synced:
                        logger.info("[zilo-session] notebook synced %d events on load uid=%s", synced, user_id)
                        await self.save(user_id, business_id=business_id, orch=orch)
                except Exception as e:
                    logger.warning("[zilo-session] notebook sync on load failed: %s", e)
                
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
        
        # Try to extract and populate notebook from connected accounts on creation
        try:
            from rex.persistence.extractor import extract_and_populate_notebook
            await extract_and_populate_notebook(self._db, user_id, orch)
        except Exception as e:
            logger.exception("[zilo-session] failed during fresh dynamic extraction: %s", e)

        await self.save(user_id, business_id=business_id, orch=orch)
        return orch

    async def load_demo(self, user_id: str, *, business_id: str) -> Orchestrator:
        orch = build_demo_orchestrator()
        orch._live_mode = False  # type: ignore[attr-defined]
        orch._metrics = {}  # type: ignore[attr-defined]
        
        # Seed companies for demo mode
        from rex.demo_seed import seed_companies_history
        seed_companies_history(orch)
        
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
        rel_day = getattr(orch, "_relationship_day", 1)
        metrics = getattr(orch, "_metrics", None) or {}
        is_demo = demo_mode if demo_mode is not None else False

        doc: dict[str, Any] = {
            "business_id": business_id,
            # updated_at is set below after now_ts is computed for the lock filter
            "relationship_day": rel_day,
            "last_sync_at": getattr(orch, "_last_sync_at", None),
            "metrics": metrics,
            "events": [codec.trust_event_to_dict(e) for e in orch.event_store.all_events()],
            "actions": [codec.action_to_dict(a) for a in orch.ledger.all_actions()],
            "changes": [codec.change_to_dict(c) for c in orch.ledger._store.all_changes()],  # noqa: SLF001
            "notebook": [codec.notebook_entry_to_dict(e) for e in orch.notebook.all()],
            "companies": getattr(orch, "_companies", []),
            "swept_ids": list(orch._swept_ids),
            "disabled_categories": list(getattr(orch, "_disabled_categories", set())),
            "lead_scout_interval": getattr(orch, "_lead_scout_interval", "24h"),
            "open_scout_interval": getattr(orch, "_open_scout_interval", "12h"),
            "fb_group_interval": getattr(orch, "_fb_group_interval", "6h"),
            "journal_last_visit_day": getattr(orch, "_journal_last_visit_day", None),
            "journal_streak": int(getattr(orch, "_journal_streak", 0) or 0),
            "journal_shown_milestones": list(getattr(orch, "_journal_shown_milestones", []) or []),
            "relationship_day_override": getattr(orch, "_relationship_day_override", None),
        }

        set_on_insert = {
            "user_id": user_id,
            "created_at": _utc_now(),
            "demo_mode": is_demo,
        }

        now_ts = _utc_now()
        # Optimistic-locking filter: match the exact updated_at we loaded from DB.
        # On a new document (upsert) there is no prior timestamp, so use user_id only.
        loaded_ts = getattr(orch, "_loaded_updated_at", None)
        if loaded_ts is not None:
            filter_doc: dict[str, Any] = {"user_id": user_id, "updated_at": loaded_ts}
        else:
            filter_doc = {"user_id": user_id}

        doc["updated_at"] = now_ts

        result = await self._col.update_one(
            filter_doc,
            {
                "$set": doc,
                "$setOnInsert": set_on_insert,
            },
            upsert=(loaded_ts is None),  # only upsert when creating for the first time
        )

        if loaded_ts is not None and result.matched_count == 0:
            logger.warning(
                "[zilo-session] optimistic lock miss for user_id=%s — "
                "another writer saved first; in-memory state may be stale.",
                user_id,
            )
            raise OptimisticLockError(
                f"Optimistic lock collision: session for user_id={user_id} was modified concurrently."
            )
        else:
            # Update the tracked timestamp so subsequent saves use the new value
            orch._loaded_updated_at = now_ts  # type: ignore[attr-defined]

    def invalidate_cache(self, user_id: str) -> None:
        self._cache.pop(user_id, None)

    async def reset(self, user_id: str, *, business_id: str, demo: bool = False) -> Orchestrator:
        await self._col.delete_one({"user_id": user_id})
        self.invalidate_cache(user_id)
        if demo:
            return await self.load_demo(user_id, business_id=business_id)
        return await self.load(user_id, business_id=business_id)
