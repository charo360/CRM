"""
Journal Writer — Rex's relationship log.

The Journal is not a raw audit log. It converts important trust events into
short entries in Rex's evolving voice. The Action Ledger remains the source
of truth for every action; this module writes the story layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from rex.persona.templates import journal_day_anchor
from rex.persona.voice_evolution import JournalPhase, voice_for_day
from rex.persona.voice_rules import validate_voice
from rex.ranks.events import EventType, Rank, TrustEvent
from rex.principals.visibility import Visibility, visibility_founder_only


class JournalEventKind(str, Enum):
    PROMOTION = "promotion"
    DEMOTION = "demotion"
    RECOMMENDATION = "recommendation"
    RECOMMENDATION_RESOLVED = "recommendation_resolved"
    OPERATIONAL_WIN = "operational_win"
    OPERATIONAL_SETBACK = "operational_setback"
    PROBATION = "probation"
    TEAM = "team"  # Phase 8: Team Journal for founder (REX.md §4.6)


@dataclass(frozen=True)
class JournalEntry:
    id: str
    relationship_day: int
    kind: JournalEventKind
    body: str
    source_event_ids: tuple[str, ...]
    actor_name: str
    category: str
    phase: JournalPhase
    word_count: int
    visibility: Visibility = visibility_founder_only


class JournalWriter:
    def write_for_event(
        self,
        event: TrustEvent,
        *,
        relationship_day: int,
        context: Mapping[str, object] | None = None,
    ) -> JournalEntry | None:
        return write_entry_for_trust_event(
            event,
            relationship_day=relationship_day,
            context=context,
        )

    def write_for_events(
        self,
        events: Iterable[TrustEvent],
        *,
        relationship_day: int,
        context: Mapping[str, object] | None = None,
    ) -> tuple[JournalEntry, ...]:
        return write_entries_for_events(
            events,
            relationship_day=relationship_day,
            context=context,
        )


def write_entries_for_events(
    events: Iterable[TrustEvent],
    *,
    relationship_day: int,
    context: Mapping[str, object] | None = None,
) -> tuple[JournalEntry, ...]:
    entries: list[JournalEntry] = []
    for event in events:
        entry = write_entry_for_trust_event(
            event,
            relationship_day=relationship_day,
            context=context,
        )
        if entry is not None:
            entries.append(entry)
    return tuple(entries)


def write_entry_for_trust_event(
    event: TrustEvent,
    *,
    relationship_day: int,
    context: Mapping[str, object] | None = None,
) -> JournalEntry | None:
    if relationship_day < 1:
        raise ValueError("relationship_day must be >= 1")

    kind = _kind_for(event.type)
    if kind is None:
        return None

    calibration = voice_for_day(relationship_day)
    text = _body_for(event, relationship_day=relationship_day, phase=calibration.phase, context=context or {})
    body = f"{journal_day_anchor(relationship_day)}\n{text}"
    _validate(body, calibration.target_word_ceiling)

    # By default journal entries are founder-only, EXCEPT role-based subagent actions
    # and recommendations which can have custom visibility mapped later if needed.
    # We keep everything founder_only by default as per REX.md §4.6.
    return JournalEntry(
        id=f"journal-{event.id}",
        relationship_day=relationship_day,
        kind=kind,
        body=body,
        source_event_ids=(event.id,),
        actor_name=event.actor_name,
        category=event.category,
        phase=calibration.phase,
        word_count=_word_count(body),
        visibility=visibility_founder_only,
    )


def _kind_for(event_type: EventType) -> JournalEventKind | None:
    if event_type is EventType.USER_PROMOTED_REX:
        return JournalEventKind.PROMOTION
    if event_type in {EventType.USER_DEMOTED_REX, EventType.REX_DEMOTED_SUBAGENT}:
        return JournalEventKind.DEMOTION
    if event_type is EventType.REX_RECOMMENDED_SUBAGENT_PROMOTION:
        return JournalEventKind.RECOMMENDATION
    if event_type in {
        EventType.USER_APPROVED_RECOMMENDATION,
        EventType.USER_DENIED_RECOMMENDATION,
        EventType.USER_DEFERRED_RECOMMENDATION,
    }:
        return JournalEventKind.RECOMMENDATION_RESOLVED
    if event_type is EventType.REX_LIFTED_PROBATION:
        return JournalEventKind.PROBATION
    if event_type in {EventType.FOUNDER_INVITED_TEAM_MEMBER, EventType.FOUNDER_REVOKED_TEAM_MEMBER}:
        return JournalEventKind.TEAM
    if event_type in {EventType.ACTION_APPROVED, EventType.ACTION_CLEAN_SEND}:
        return JournalEventKind.OPERATIONAL_WIN
    if event_type in {
        EventType.ACTION_REJECTED,
        EventType.ACTION_UNDONE,
        EventType.ACTION_FLAGGED_MISTAKE,
    }:
        return JournalEventKind.OPERATIONAL_SETBACK
    return None


def _body_for(
    event: TrustEvent,
    *,
    relationship_day: int,
    phase: JournalPhase,
    context: Mapping[str, object],
) -> str:
    if event.type is EventType.USER_PROMOTED_REX:
        return _rex_promotion(event, phase)
    if event.type is EventType.USER_DEMOTED_REX:
        return _rex_demotion(event, phase)
    if event.type is EventType.REX_RECOMMENDED_SUBAGENT_PROMOTION:
        return _subagent_recommendation(event, phase)
    if event.type is EventType.USER_APPROVED_RECOMMENDATION:
        return _recommendation_approved(event, phase)
    if event.type is EventType.USER_DENIED_RECOMMENDATION:
        return _recommendation_denied(event, phase)
    if event.type is EventType.USER_DEFERRED_RECOMMENDATION:
        return _recommendation_deferred(event, phase)
    if event.type is EventType.REX_DEMOTED_SUBAGENT:
        return _subagent_demoted(event, phase)
    if event.type is EventType.REX_LIFTED_PROBATION:
        return _probation_lifted(event, phase)
    if event.type is EventType.FOUNDER_INVITED_TEAM_MEMBER:
        return _team_invited(event, phase)
    if event.type is EventType.FOUNDER_REVOKED_TEAM_MEMBER:
        return _team_revoked(event, phase)
    if event.type is EventType.ACTION_APPROVED:
        return _action_approved(event, phase, context)
    if event.type is EventType.ACTION_CLEAN_SEND:
        return _clean_send(event, phase, context)
    if event.type is EventType.ACTION_REJECTED:
        return _action_rejected(event, phase, context)
    if event.type is EventType.ACTION_UNDONE:
        return _action_undone(event, phase, context)
    if event.type is EventType.ACTION_FLAGGED_MISTAKE:
        return _mistake(event, phase, context)
    raise ValueError(f"Unsupported journal event: {event.type}")


def _rank(r: Rank | None) -> str:
    return r.display if r is not None else "Observer"


def _cat(category: str) -> str:
    return category.replace("_", " ")


def _reason(event: TrustEvent) -> str:
    return event.reason.strip() if event.reason else ""


def _subject(context: Mapping[str, object], fallback: str) -> str:
    raw = context.get("subject") or context.get("target_subject") or fallback
    return str(raw).strip() or fallback


def _metric(context: Mapping[str, object], key: str, default: object) -> object:
    return context.get(key, default)


def _rex_promotion(event: TrustEvent, phase: JournalPhase) -> str:
    first = f"Earned {_rank(event.to_rank)} on {_cat(event.category)}."
    if phase is JournalPhase.OBSERVING:
        return first
    if phase is JournalPhase.SHIFTING:
        return f"{first} They made the call. Filed."
    if phase is JournalPhase.BLENDED:
        return f"{first} They moved me from {_rank(event.from_rank)}. Earned."
    if phase is JournalPhase.EARNED:
        return f"{first} More room to act. Same standard. I won't forget that."
    return f"{first} Different from Day 1. Still earned one category at a time."


def _rex_demotion(event: TrustEvent, phase: JournalPhase) -> str:
    first = f"Demoted to {_rank(event.to_rank)} on {_cat(event.category)}."
    reason = _reason(event)
    if phase in {JournalPhase.OBSERVING, JournalPhase.SHIFTING}:
        return f"{first} Rebuilding."
    if reason:
        return f"{first} {reason}. Fair. Rebuilding."
    return f"{first} Fair. Rebuilding."


def _subagent_recommendation(event: TrustEvent, phase: JournalPhase) -> str:
    first = f"Recommended {event.actor_name} for {_rank(event.to_rank)} on {_cat(event.category)}."
    reason = _reason(event)
    if phase is JournalPhase.OBSERVING:
        return first
    if reason:
        return f"{first} {reason}. Your call."
    return f"{first} Your call."


def _recommendation_approved(event: TrustEvent, phase: JournalPhase) -> str:
    first = f"{event.actor_name} earned {_rank(event.to_rank)} on {_cat(event.category)}."
    if phase is JournalPhase.OBSERVING:
        return first
    if phase is JournalPhase.SHIFTING:
        return f"{first} You approved it. Noted."
    if phase is JournalPhase.BLENDED:
        return f"{first} You approved it. Trust moved one step down the chain."
    return f"{first} You approved it. That's trust moving in the right direction."


def _team_invited(event: TrustEvent, phase: JournalPhase) -> str:
    # event.actor_name is the invitee name.
    # event.reason has the metadata: "role:sales;cats:outreach,replies;id:sarah-1"
    parts = dict(pair.split(":", 1) for pair in event.reason.split(";"))
    role_str = parts.get("role", "sales").capitalize()
    return f"Added {event.actor_name} to the team as {role_str}. Set up their briefing."


def _team_revoked(event: TrustEvent, phase: JournalPhase) -> str:
    return f"Revoked access for {event.actor_name}. Closed their briefing stream."


def _recommendation_denied(event: TrustEvent, phase: JournalPhase) -> str:
    first = f"Denied promotion for {event.actor_name} on {_cat(event.category)}."
    if phase is JournalPhase.OBSERVING:
        return first
    return f"{first} More proof needed. Fair."


def _recommendation_deferred(event: TrustEvent, phase: JournalPhase) -> str:
    first = f"Deferred promotion for {event.actor_name} on {_cat(event.category)}."
    if phase is JournalPhase.OBSERVING:
        return first
    return f"{first} Not no. Not yet. Filed."


def _subagent_demoted(event: TrustEvent, phase: JournalPhase) -> str:
    first = f"Pulled {event.actor_name} back to {_rank(event.to_rank)} on {_cat(event.category)}."
    reason = _reason(event)
    if reason:
        return f"{first} {reason}. Rebuilding."
    return f"{first} Rebuilding."


def _probation_lifted(event: TrustEvent, phase: JournalPhase) -> str:
    first = f"Lifted probation for {event.actor_name} on {_cat(event.category)}."
    if phase in {JournalPhase.OBSERVING, JournalPhase.SHIFTING}:
        return first
    return f"{first} The pattern held. Filed."


def _action_approved(event: TrustEvent, phase: JournalPhase, context: Mapping[str, object]) -> str:
    subject = _subject(context, _cat(event.category))
    first = f"{subject} approved."
    if phase is JournalPhase.OBSERVING:
        return first
    return f"{first} Confidence {int(round((event.confidence or 0) * 100))}%. Noted."


def _clean_send(event: TrustEvent, phase: JournalPhase, context: Mapping[str, object]) -> str:
    subject = _subject(context, _cat(event.category))
    hours = _metric(context, "reply_hours", None)
    if hours is not None:
        first = f"{subject} sent. Replied in {hours} hours."
    else:
        first = f"{subject} sent clean."
    if phase is JournalPhase.OBSERVING:
        return first
    if phase is JournalPhase.EARNED:
        return f"{first} Directness worked again. I won't forget that."
    if phase is JournalPhase.PERSPECTIVE:
        return f"{first} That's the pattern now."
    return f"{first} Noted."


def _action_rejected(event: TrustEvent, phase: JournalPhase, context: Mapping[str, object]) -> str:
    subject = _subject(context, _cat(event.category))
    if phase is JournalPhase.OBSERVING:
        return f"{subject} rejected."
    return f"{subject} rejected. Pattern not strong enough. Noted."


def _action_undone(event: TrustEvent, phase: JournalPhase, context: Mapping[str, object]) -> str:
    subject = _subject(context, _cat(event.category))
    if phase in {JournalPhase.OBSERVING, JournalPhase.SHIFTING}:
        return f"{subject} undone. Rebuilding."
    return f"{subject} undone before it settled. Fair. Rebuilding."


def _mistake(event: TrustEvent, phase: JournalPhase, context: Mapping[str, object]) -> str:
    subject = _subject(context, _cat(event.category))
    reason = _reason(event)
    if reason:
        first = f"{subject} flagged. {reason}."
    else:
        first = f"{subject} flagged."
    if phase in {JournalPhase.OBSERVING, JournalPhase.SHIFTING}:
        return f"{first} Rebuilding."
    return f"{first} Fair. Rebuilding."


def _word_count(text: str) -> int:
    return len([w for w in text.replace("\n", " ").split(" ") if w.strip()])


def _validate(body: str, ceiling: int) -> None:
    if _word_count(body) > ceiling + 5:
        raise ValueError("Journal entry exceeded voice phase word ceiling")
    report = validate_voice(body)
    hard = [v for v in report.violations if v.severity.value == "hard"]
    if hard:
        raise ValueError(
            "Journal entry failed voice validation: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in hard)
        )
