"""
notebook_sync — event-driven write-back from TrustEvents into the Notebook.

Every time the founder interacts with an action (approve, reject, undo) or
a sweep completes cleanly, this module updates the Notebook so the next
action proposal gets a smarter citation.

The loop that was previously broken:
    Event fires
        ↓
    notebook_sync.on_trust_event(event, action, notebook)
        ↓
    Notebook entry updated/created for that subject
        ↓
    Next time same subject appears → better citation → smarter briefing

Design rules:
  - Never overwrites user-edited entries (edited_by_user=True)
  - Capped at 3 approved / 3 rejected signals per entry to avoid runaway confidence
  - Uses strict_voice=False because sync observations are data-derived, not creative
  - All writes are idempotent — safe to call multiple times with the same event
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from rex.actions.primitives import Action
from rex.memory.buckets import Bucket
from rex.memory.notebook import Notebook
from rex.ranks.events import EventType, TrustEvent

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# How many approval/rejection signals before we stop updating a People entry.
# Prevents the notebook from becoming stale overconfident assertions.
_MAX_SIGNALS_PER_ENTRY = 5


def _subject_from_action(action: Action) -> str | None:
    """Extract the best human-readable subject from an action."""
    subj = getattr(action, "target_subject", None)
    if subj and subj.strip():
        return subj.strip()
    # Fall back to actor_name if it looks like a name, not a system
    actor = getattr(action, "actor_name", None) or ""
    if actor and actor.lower() not in ("zilo", "rex", "system", ""):
        return actor.strip()
    return None


def _count_signals(text: str, signal: str) -> int:
    """Count how many times a signal marker appears in an entry's text."""
    return text.lower().count(signal.lower())


def on_trust_event(
    event: TrustEvent,
    action: Action | None,
    notebook: Notebook,
) -> None:
    """
    Called after every user verb (approve, reject, undo) and after
    ACTION_CLEAN_SEND. Updates or creates a Notebook entry for the
    action's subject to reflect what the founder just taught Zilo.

    Safe to call with action=None — will be a no-op in that case.
    """
    if action is None:
        return

    subject = _subject_from_action(action)
    category = getattr(action, "category", None) or "general"
    summary = getattr(action, "summary", None) or ""

    try:
        if event.type is EventType.ACTION_APPROVED:
            _handle_approved(event, action, subject, category, summary, notebook)

        elif event.type is EventType.ACTION_REJECTED:
            _handle_rejected(event, action, subject, category, summary, notebook)

        elif event.type is EventType.ACTION_UNDONE:
            _handle_undone(event, action, subject, category, summary, notebook)

        elif event.type is EventType.ACTION_CLEAN_SEND:
            _handle_clean_send(event, action, subject, category, summary, notebook)

    except Exception as e:
        logger.warning("[notebook-sync] failed to sync event=%s subject=%s: %s", event.type, subject, e)


# ---------------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------------

def _handle_approved(
    event: TrustEvent,
    action: Action,
    subject: str | None,
    category: str,
    summary: str,
    notebook: Notebook,
) -> None:
    """Founder approved this draft. Reinforce what worked."""
    if not subject:
        # No subject — write a Patterns entry about approval behaviour
        _upsert_pattern(
            notebook=notebook,
            tag=f"approved:{category}",
            signal_text=f"Approved {category} action. {_short_summary(summary)}",
            source_event_ids=(event.id,),
        )
        return

    existing = notebook.by_subject(subject)

    if existing:
        # Find the first non-user-edited entry for this subject
        entry = _first_rex_entry(existing)
        if entry is None:
            return
        if _count_signals(entry.text, "approved") >= _MAX_SIGNALS_PER_ENTRY:
            return
        appended = entry.text.rstrip()
        appended += f" Approved {category} draft: {_short_summary(summary)}."
        updated = entry.with_text(appended, by_user=False)
        updated = replace(
            updated,
            source_event_ids=updated.source_event_ids + (event.id,),
        )
        notebook._store.put(updated)
        logger.info("[notebook-sync] updated People entry for %s (approved)", subject)
    else:
        # New contact — create their first entry
        text = (
            f"{subject} — {category} draft approved. "
            f"{_short_summary(summary)}. "
            f"First approval on record."
        )
        notebook.add(
            bucket=Bucket.PEOPLE,
            subject=subject,
            text=text,
            source_event_ids=(event.id,),
            tags=(category, "approved"),
            strict_voice=False,
        )
        logger.info("[notebook-sync] created People entry for %s (approved)", subject)


def _handle_rejected(
    event: TrustEvent,
    action: Action,
    subject: str | None,
    category: str,
    summary: str,
    notebook: Notebook,
) -> None:
    """Founder rejected this draft. Record what didn't land."""
    reason = event.reason or ""

    if not subject:
        _upsert_pattern(
            notebook=notebook,
            tag=f"rejected:{category}",
            signal_text=f"Rejected {category} draft. {_short_summary(summary)}. Reason: {reason[:80]}",
            source_event_ids=(event.id,),
        )
        return

    existing = notebook.by_subject(subject)

    if existing:
        entry = _first_rex_entry(existing)
        if entry is None:
            return
        if _count_signals(entry.text, "rejected") >= _MAX_SIGNALS_PER_ENTRY:
            return
        note = f" Rejected {category} draft"
        if reason:
            note += f" — {reason[:80]}"
        note += "."
        updated = entry.with_text(entry.text.rstrip() + note, by_user=False)
        updated = replace(
            updated,
            source_event_ids=updated.source_event_ids + (event.id,),
        )
        notebook._store.put(updated)
        logger.info("[notebook-sync] updated People entry for %s (rejected)", subject)
    else:
        text = (
            f"{subject} — {category} draft rejected. "
            f"{_short_summary(summary)}. "
            + (f"Reason: {reason[:80]}." if reason else "No reason given.")
        )
        notebook.add(
            bucket=Bucket.PEOPLE,
            subject=subject,
            text=text,
            source_event_ids=(event.id,),
            tags=(category, "rejected"),
            strict_voice=False,
        )
        logger.info("[notebook-sync] created People entry for %s (rejected)", subject)


def _handle_undone(
    event: TrustEvent,
    action: Action,
    subject: str | None,
    category: str,
    summary: str,
    notebook: Notebook,
) -> None:
    """Founder undid a sent message. That's a strong signal."""
    reason = event.reason or ""

    if not subject:
        _upsert_pattern(
            notebook=notebook,
            tag=f"undone:{category}",
            signal_text=f"Sent {category} action undone. {_short_summary(summary)}.",
            source_event_ids=(event.id,),
        )
        return

    existing = notebook.by_subject(subject)

    if existing:
        entry = _first_rex_entry(existing)
        if entry is None:
            return
        note = f" Message undone after send — {category}"
        if reason:
            note += f": {reason[:80]}"
        note += ". Check approach for this contact."
        updated = entry.with_text(entry.text.rstrip() + note, by_user=False)
        updated = replace(
            updated,
            source_event_ids=updated.source_event_ids + (event.id,),
        )
        notebook._store.put(updated)
        logger.info("[notebook-sync] updated People entry for %s (undone)", subject)
    else:
        text = (
            f"{subject} — message sent then undone ({category}). "
            f"{_short_summary(summary)}. Approach needs review."
        )
        notebook.add(
            bucket=Bucket.PEOPLE,
            subject=subject,
            text=text,
            source_event_ids=(event.id,),
            tags=(category, "undone"),
            strict_voice=False,
        )
        logger.info("[notebook-sync] created People entry for %s (undone)", subject)


def _handle_clean_send(
    event: TrustEvent,
    action: Action,
    subject: str | None,
    category: str,
    summary: str,
    notebook: Notebook,
) -> None:
    """Message sent cleanly past undo window. Confidence builder."""
    if not subject:
        return  # Pattern-level clean send is low signal, skip

    existing = notebook.by_subject(subject)
    if not existing:
        return  # Only reinforce existing entries, don't create for clean sends

    entry = _first_rex_entry(existing)
    if entry is None:
        return
    if _count_signals(entry.text, "sent cleanly") >= 3:
        return

    updated = entry.with_text(
        entry.text.rstrip() + f" {category} message sent cleanly — no recall.",
        by_user=False,
    )
    updated = replace(
        updated,
        source_event_ids=updated.source_event_ids + (event.id,),
    )
    notebook._store.put(updated)
    logger.info("[notebook-sync] reinforced People entry for %s (clean send)", subject)


# ---------------------------------------------------------------------------
# Batch sync — call this after a full platform sweep to sync all events
# ---------------------------------------------------------------------------

def sync_events_to_notebook(
    events: tuple[TrustEvent, ...],
    ledger,
    notebook: Notebook,
) -> int:
    """
    Replay all OPERATIONAL trust events that are not yet synced to the notebook.
    Returns number of entries updated/created.

    Called by the nightly sweep and on session load to ensure the notebook
    is always current even if on_trust_event was missed in a previous session.
    """
    _SYNCABLE = {
        EventType.ACTION_APPROVED,
        EventType.ACTION_REJECTED,
        EventType.ACTION_UNDONE,
        EventType.ACTION_CLEAN_SEND,
    }

    # Track which event IDs are already referenced in any entry
    already_synced: set[str] = set()
    for entry in notebook.all():
        already_synced.update(entry.source_event_ids)

    # Build a map: event_id → action by scanning all state changes
    # Each state change carries actor_name + action_id; TrustEvents are
    # derived from those changes so they share category and actor.
    action_by_category_actor: dict[tuple[str, str], Action] = {}
    for action in ledger.all_actions():
        key = (getattr(action, "category", ""), getattr(action, "actor_name", ""))
        action_by_category_actor[key] = action

    synced = 0
    for event in events:
        if event.type not in _SYNCABLE:
            continue
        if event.id in already_synced:
            continue

        # Best-effort action lookup by category + actor name
        action: Action | None = action_by_category_actor.get(
            (event.category or "", event.actor_name or "")
        )

        on_trust_event(event, action, notebook)
        synced += 1

    return synced


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_rex_entry(entries: tuple) -> object | None:
    """Return the first entry that hasn't been user-edited."""
    for e in entries:
        if not e.edited_by_user:
            return e
    return None


def _short_summary(summary: str, max_chars: int = 60) -> str:
    s = summary.strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rsplit(" ", 1)[0] + "..."


def _upsert_pattern(
    notebook: Notebook,
    tag: str,
    signal_text: str,
    source_event_ids: tuple[str, ...],
) -> None:
    """
    Find an existing Patterns entry with matching tag and append to it,
    or create a new one. Used for subject-less events.
    """
    for entry in notebook.by_bucket(Bucket.PATTERNS):
        if tag in entry.tags and not entry.edited_by_user:
            appended = entry.text.rstrip() + f" {signal_text}"
            updated = entry.with_text(appended, by_user=False)
            updated = replace(
                updated,
                source_event_ids=updated.source_event_ids + source_event_ids,
            )
            notebook._store.put(updated)
            return

    notebook.add(
        bucket=Bucket.PATTERNS,
        text=signal_text,
        source_event_ids=source_event_ids,
        tags=(tag,),
        strict_voice=False,
    )
