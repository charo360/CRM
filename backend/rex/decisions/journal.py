"""
Decision journal + notebook hooks when a founder records a choice.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from rex.journal.writer import JournalEntry, JournalEventKind
from rex.memory import Bucket
from rex.persona.voice_evolution import voice_for_day
from rex.decisions.models import STRATEGY_CATEGORY

logger = logging.getLogger(__name__)


def build_decision_journal_body(
    *,
    question: str,
    decision: str,
    notes: str = "",
    relationship_day: int = 1,
) -> str:
    """Template journal entry in Zilo voice — no LLM required."""
    q = _one_line(question, 120)
    d = _one_line(decision, 160)
    parts = [
        f"Founder decided.",
        f"Question: {q}",
        f"Call: {d}",
    ]
    if notes.strip():
        parts.append(f"Why: {_one_line(notes, 120)}")
    parts.append("Watching outcomes. Not my lane to override.")
    body = "\n\n".join(parts)
    phase = voice_for_day(relationship_day)
    return body


def journal_entry_from_decision(
    *,
    session_id: str,
    question: str,
    decision: str,
    notes: str = "",
    relationship_day: int = 1,
) -> JournalEntry:
    body = build_decision_journal_body(
        question=question,
        decision=decision,
        notes=notes,
        relationship_day=relationship_day,
    )
    phase = voice_for_day(relationship_day)
    return JournalEntry(
        id=f"decision-{session_id}",
        relationship_day=relationship_day,
        kind=JournalEventKind.STRATEGIC_DECISION,
        body=body,
        source_event_ids=(session_id,),
        actor_name="Zilo",
        category=STRATEGY_CATEGORY,
        phase=phase,
        word_count=len(body.split()),
        created_at=datetime.now(timezone.utc),
        details=(question[:200], decision[:200]),
    )


def _one_line(text: str, max_len: int) -> str:
    t = " ".join((text or "").split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


async def persist_decision_journal(
    db: Any,
    session_doc: dict,
    *,
    decision: str,
    notes: str = "",
    relationship_day: int = 1,
) -> str:
    """Save journal body on session; return body text."""
    sid = str(session_doc.get("_id") or "")
    body = build_decision_journal_body(
        question=session_doc.get("question") or "",
        decision=decision,
        notes=notes,
        relationship_day=relationship_day,
    )
    await db.decision_sessions.update_one(
        {"_id": sid},
        {"$set": {"journal_body": body, "journal_recorded_at": datetime.utcnow()}},
    )
    return body


def add_decision_notebook_pattern(
    orch: Any,
    *,
    question: str,
    decision: str,
) -> None:
    """Record decision pattern in notebook for future spars."""
    from rex.memory.notebook import NotebookVoiceError

    q = _one_line(question, 80)
    d = _one_line(decision, 100)
    text = f"Founder chose: {d}. Context: {q}. Track whether this held up."
    try:
        orch.notebook.add(
            bucket=Bucket.PATTERNS,
            subject="Strategic decisions",
            text=text,
            tags=("decision", "strategy"),
            strict_voice=False,
        )
    except NotebookVoiceError as e:
        logger.warning("[decision-journal] notebook voice: %s", e)
    except Exception as e:
        logger.warning("[decision-journal] notebook add: %s", e)


async def fetch_decision_journal_entries(
    db: Any,
    user_id: str,
    *,
    relationship_day: int = 1,
    limit: int = 30,
) -> list[JournalEntry]:
    """Load decided sessions that have journal_body into JournalEntry objects."""
    try:
        cursor = (
            db.decision_sessions.find(
                {
                    "user_id": user_id,
                    "status": "decided",
                    "journal_body": {"$exists": True, "$ne": ""},
                }
            )
            .sort("decided_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(limit)
    except Exception as e:
        logger.warning("[decision-journal] fetch: %s", e)
        return []

    entries: list[JournalEntry] = []
    for doc in docs or []:
        sid = str(doc.get("_id") or uuid.uuid4())
        decided_at = doc.get("decided_at") or doc.get("updated_at")
        if hasattr(decided_at, "replace") and getattr(decided_at, "tzinfo", None) is None:
            decided_at = decided_at.replace(tzinfo=timezone.utc)
        body = (doc.get("journal_body") or "").strip()
        if not body:
            continue
        phase = voice_for_day(relationship_day)
        entries.append(
            JournalEntry(
                id=f"decision-{sid}",
                relationship_day=relationship_day,
                kind=JournalEventKind.STRATEGIC_DECISION,
                body=body,
                source_event_ids=(sid,),
                actor_name="Zilo",
                category=STRATEGY_CATEGORY,
                phase=phase,
                word_count=len(body.split()),
                created_at=decided_at if isinstance(decided_at, datetime) else datetime.now(timezone.utc),
                details=(
                    _one_line(doc.get("question") or "", 200),
                    _one_line(doc.get("founder_decision") or "", 200),
                ),
            )
        )
    return entries
