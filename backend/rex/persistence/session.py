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
        try:
            await self._col.create_index("user_id", unique=True)
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
        created = doc.get("created_at")
        if created:
            orch._relationship_day = _relationship_day(codec._parse_dt(created))  # type: ignore[attr-defined]
        else:
            orch._relationship_day = int(doc.get("relationship_day") or 1)  # type: ignore[attr-defined]
        orch._metrics = dict(doc.get("metrics") or {})  # type: ignore[attr-defined]
        orch._live_mode = not doc.get("demo_mode", False)  # type: ignore[attr-defined]
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

    async def _save_doc(
        self,
        user_id: str,
        *,
        business_id: str,
        orch: Orchestrator,
        demo_mode: bool | None = None,
    ) -> None:
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
