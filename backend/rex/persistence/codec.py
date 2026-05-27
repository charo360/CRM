"""
Serialize / deserialize Zilo orchestrator state for MongoDB.

BSON-friendly dicts only (no dataclass objects in the DB).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rex.actions.primitives import (
    Action,
    ActionKind,
    ActionState,
    ActionStateChange,
    Outcome,
)
from rex.memory.buckets import Bucket
from rex.memory.entries import NotebookEntry
from rex.principals.visibility import Visibility, VisibilityScope
from rex.ranks.events import EventType, Rank, TrustEvent


def _parse_dt(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        s = v.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise TypeError(f"expected datetime or iso str, got {type(v)}")


def _dt_iso(v: datetime) -> str:
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


# ── Visibility ────────────────────────────────────────────────────────────

def visibility_to_dict(v: Visibility) -> dict[str, Any]:
    return {
        "scope": v.scope.value,
        "target_role": v.target_role,
        "target_principal_id": v.target_principal_id,
    }


def visibility_from_dict(d: dict[str, Any] | None) -> Visibility:
    if not d:
        from rex.principals.visibility import visibility_founder_only
        return visibility_founder_only
    return Visibility(
        scope=VisibilityScope(d["scope"]),
        target_role=d.get("target_role"),
        target_principal_id=d.get("target_principal_id"),
    )


# ── Trust events ──────────────────────────────────────────────────────────

def trust_event_to_dict(e: TrustEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "timestamp": _dt_iso(e.timestamp),
        "type": e.type.value,
        "actor_name": e.actor_name,
        "category": e.category,
        "to_rank": e.to_rank.value if e.to_rank is not None else None,
        "from_rank": e.from_rank.value if e.from_rank is not None else None,
        "recommendation_id": e.recommendation_id,
        "reason": e.reason,
        "confidence": e.confidence,
    }


def trust_event_from_dict(d: dict[str, Any]) -> TrustEvent:
    return TrustEvent(
        id=d["id"],
        timestamp=_parse_dt(d["timestamp"]),
        type=EventType(d["type"]),
        actor_name=d["actor_name"],
        category=d["category"],
        to_rank=Rank(d["to_rank"]) if d.get("to_rank") is not None else None,
        from_rank=Rank(d["from_rank"]) if d.get("from_rank") is not None else None,
        recommendation_id=d.get("recommendation_id"),
        reason=d.get("reason"),
        confidence=d.get("confidence"),
    )


# ── Actions + ledger changes ──────────────────────────────────────────────

def outcome_to_dict(o: Outcome | None) -> dict[str, Any] | None:
    if o is None:
        return None
    return {
        "external_ref": o.external_ref,
        "rows_affected": o.rows_affected,
        "cost_cents": o.cost_cents,
        "error_class": o.error_class,
        "error_message": o.error_message,
    }


def outcome_from_dict(d: dict[str, Any] | None) -> Outcome | None:
    if not d:
        return None
    return Outcome(
        external_ref=d.get("external_ref"),
        rows_affected=d.get("rows_affected"),
        cost_cents=d.get("cost_cents"),
        error_class=d.get("error_class"),
        error_message=d.get("error_message"),
    )


def action_to_dict(a: Action) -> dict[str, Any]:
    return {
        "id": a.id,
        "proposed_at": _dt_iso(a.proposed_at),
        "actor_name": a.actor_name,
        "rank_at_time": a.rank_at_time.value,
        "category": a.category,
        "kind": a.kind.value,
        "summary": a.summary,
        "payload": dict(a.payload),
        "reasoning": a.reasoning,
        "confidence": a.confidence,
        "target_subject": a.target_subject,
        "memory_citation_ids": list(a.memory_citation_ids),
        "source_event_ids": list(a.source_event_ids),
        "visibility": visibility_to_dict(a.visibility),
    }


def action_from_dict(d: dict[str, Any]) -> Action:
    return Action(
        id=d["id"],
        proposed_at=_parse_dt(d["proposed_at"]),
        actor_name=d["actor_name"],
        rank_at_time=Rank(d["rank_at_time"]),
        category=d["category"],
        kind=ActionKind(d["kind"]),
        summary=d["summary"],
        payload=dict(d.get("payload") or {}),
        reasoning=d.get("reasoning", ""),
        confidence=float(d.get("confidence", 0)),
        target_subject=d.get("target_subject"),
        memory_citation_ids=tuple(d.get("memory_citation_ids") or []),
        source_event_ids=tuple(d.get("source_event_ids") or []),
        visibility=visibility_from_dict(d.get("visibility")),
    )


def change_to_dict(c: ActionStateChange) -> dict[str, Any]:
    return {
        "id": c.id,
        "action_id": c.action_id,
        "at": _dt_iso(c.at),
        "from_state": c.from_state.value if c.from_state is not None else None,
        "to_state": c.to_state.value,
        "actor_name": c.actor_name,
        "reason": c.reason,
        "outcome": outcome_to_dict(c.outcome),
    }


def change_from_dict(d: dict[str, Any]) -> ActionStateChange:
    return ActionStateChange(
        id=d["id"],
        action_id=d["action_id"],
        at=_parse_dt(d["at"]),
        from_state=ActionState(d["from_state"]) if d.get("from_state") else None,
        to_state=ActionState(d["to_state"]),
        actor_name=d["actor_name"],
        reason=d.get("reason"),
        outcome=outcome_from_dict(d.get("outcome")),
    )


# ── Notebook ──────────────────────────────────────────────────────────────

def notebook_entry_to_dict(e: NotebookEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "bucket": e.bucket.name,
        "subject": e.subject,
        "text": e.text,
        "created_at": _dt_iso(e.created_at),
        "updated_at": _dt_iso(e.updated_at),
        "edited_by_user": e.edited_by_user,
        "source_event_ids": list(e.source_event_ids),
        "tags": list(e.tags),
        "visibility": visibility_to_dict(e.visibility),
    }


def notebook_entry_from_dict(d: dict[str, Any]) -> NotebookEntry:
    return NotebookEntry(
        id=d["id"],
        bucket=Bucket[d["bucket"]],
        subject=d.get("subject"),
        text=d["text"],
        created_at=_parse_dt(d["created_at"]),
        updated_at=_parse_dt(d["updated_at"]),
        edited_by_user=bool(d.get("edited_by_user")),
        source_event_ids=tuple(d.get("source_event_ids") or []),
        tags=tuple(d.get("tags") or []),
        visibility=visibility_from_dict(d.get("visibility")),
    )
