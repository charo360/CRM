"""HTTP serializers for Zilo read APIs."""

from __future__ import annotations

from typing import Any

from rex.actions.rendering import inspect_rows, story_render
from rex.journal.writer import write_entries_for_events
from rex.loop import Orchestrator
from rex.memory.buckets import Bucket
from rex.persistence.codec import _dt_iso


def serialize_notebook(orch: Orchestrator) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "people": [],
        "patterns": [],
        "lanes": [],
    }
    for entry in orch.notebook.all():
        item = {
            "id": entry.id,
            "subject": entry.subject,
            "text": entry.text,
            "created_at": _dt_iso(entry.created_at),
            "updated_at": _dt_iso(entry.updated_at),
            "edited_by_user": entry.edited_by_user,
            "tags": list(entry.tags),
        }
        if entry.bucket is Bucket.PEOPLE:
            buckets["people"].append(item)
        elif entry.bucket is Bucket.PATTERNS:
            buckets["patterns"].append(item)
        else:
            buckets["lanes"].append(item)
    return {"buckets": buckets, "total": len(orch.notebook.all())}


def serialize_ledger(orch: Orchestrator) -> dict[str, Any]:
    story = story_render(orch.ledger, limit=80)
    rows = inspect_rows(orch.ledger)[:80]
    return {
        "story": story,
        "inspect": [
            {
                "action_id": r.action_id,
                "at": _dt_iso(r.time),
                "summary": r.summary,
                "state": r.state,
                "category": r.category,
                "kind": r.kind,
                "actor": r.actor,
                "confidence_pct": r.confidence_pct,
            }
            for r in rows
        ],
        "total_actions": len(orch.ledger.all_actions()),
    }


def serialize_journal(orch: Orchestrator) -> dict[str, Any]:
    day = getattr(orch, "_relationship_day", 1)
    entries = write_entries_for_events(
        orch.event_store.all_events(),
        relationship_day=day,
    )
    return {
        "relationship_day": day,
        "entries": [
            {
                "id": e.id,
                "kind": e.kind.value,
                "body": e.body,
                "actor_name": e.actor_name,
                "category": e.category,
                "phase": e.phase.value,
                "word_count": e.word_count,
                "source_event_ids": list(e.source_event_ids),
            }
            for e in entries
        ],
    }
