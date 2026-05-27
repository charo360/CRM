"""
Tests for rex.journal — Phase 7 Journal Writer.
"""

from __future__ import annotations

import pytest

from rex.journal import (
    JournalEntry,
    JournalEventKind,
    JournalWriter,
    write_entries_for_events,
    write_entry_for_trust_event,
)
from rex.persona.voice_evolution import JournalPhase
from rex.persona.voice_rules import validate_voice
from rex.ranks.events import EventType, Rank, TrustEvent


class TestJournalWriterPromotionEvents:
    def test_user_promoted_rex_day_one(self):
        event = TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
        )
        entry = write_entry_for_trust_event(event, relationship_day=1)

        assert isinstance(entry, JournalEntry)
        assert entry.kind is JournalEventKind.PROMOTION
        assert entry.phase is JournalPhase.OBSERVING
        assert entry.body.startswith("Day 1.\n")
        assert "Earned Drafter on outreach." in entry.body
        assert entry.source_event_ids == (event.id,)

    def test_user_promoted_rex_evolved_voice(self):
        event = TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.DRAFTER,
            to_rank=Rank.SENDER,
        )
        entry = write_entry_for_trust_event(event, relationship_day=75)

        assert entry.phase is JournalPhase.EARNED
        assert "Same standard" in entry.body
        assert "I won't forget that." in entry.body

    def test_user_demoted_rex(self):
        event = TrustEvent.user_demoted_rex(
            category="invoices",
            from_rank=Rank.SENDER,
            to_rank=Rank.DRAFTER,
            reason="Wrong vendor flagged",
        )
        entry = write_entry_for_trust_event(event, relationship_day=47)

        assert entry.kind is JournalEventKind.DEMOTION
        assert "Demoted to Drafter on invoices." in entry.body
        assert "Wrong vendor flagged." in entry.body
        assert "Fair. Rebuilding." in entry.body


class TestJournalWriterSubagentEvents:
    def test_rex_recommended_subagent_promotion(self):
        event = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout",
            category="leads",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            reason="14 leads found, 11 acted on",
            confidence=0.91,
        )
        entry = write_entry_for_trust_event(event, relationship_day=34)

        assert entry.kind is JournalEventKind.RECOMMENDATION
        assert "Recommended Scout for Drafter on leads." in entry.body
        assert "14 leads found, 11 acted on." in entry.body
        assert "Your call." in entry.body

    def test_user_approved_recommendation(self):
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout",
            category="leads",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            reason="Good work",
            confidence=0.9,
        )
        event = TrustEvent.user_approved_recommendation(
            subagent="Scout",
            category="leads",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            recommendation_id=rec.id,
        )
        entry = write_entry_for_trust_event(event, relationship_day=91)

        assert entry.kind is JournalEventKind.RECOMMENDATION_RESOLVED
        assert entry.phase is JournalPhase.PERSPECTIVE
        assert "Scout earned Drafter on leads." in entry.body
        assert "trust moving in the right direction" in entry.body

    def test_user_denied_recommendation(self):
        event = TrustEvent.user_denied_recommendation(
            subagent="Scout",
            category="leads",
            recommendation_id="rec-1",
        )
        entry = write_entry_for_trust_event(event, relationship_day=45)

        assert "Denied promotion for Scout on leads." in entry.body
        assert "More proof needed. Fair." in entry.body

    def test_user_deferred_recommendation(self):
        event = TrustEvent.user_deferred_recommendation(
            subagent="Scout",
            category="leads",
            recommendation_id="rec-1",
        )
        entry = write_entry_for_trust_event(event, relationship_day=45)

        assert "Deferred promotion for Scout on leads." in entry.body
        assert "Not no. Not yet. Filed." in entry.body

    def test_rex_demoted_subagent(self):
        event = TrustEvent.rex_demoted_subagent(
            subagent="Scout",
            category="leads",
            from_rank=Rank.SENDER,
            to_rank=Rank.DRAFTER,
            reason="Two bad matches",
        )
        entry = write_entry_for_trust_event(event, relationship_day=60)

        assert entry.kind is JournalEventKind.DEMOTION
        assert "Pulled Scout back to Drafter on leads." in entry.body
        assert "Two bad matches. Rebuilding." in entry.body

    def test_rex_lifted_probation(self):
        event = TrustEvent.rex_lifted_probation(
            actor_name="Scout",
            category="leads",
            reason="Recovered",
        )
        entry = write_entry_for_trust_event(event, relationship_day=62)

        assert entry.kind is JournalEventKind.PROBATION
        assert "Lifted probation for Scout on leads." in entry.body
        assert "The pattern held. Filed." in entry.body


class TestJournalWriterOperationalEvents:
    def test_action_approved(self):
        event = TrustEvent.operational(
            type=EventType.ACTION_APPROVED,
            actor_name="Rex",
            category="outreach",
            confidence=0.88,
        )
        entry = write_entry_for_trust_event(
            event,
            relationship_day=20,
            context={"subject": "Acme follow-up"},
        )

        assert entry.kind is JournalEventKind.OPERATIONAL_WIN
        assert "Acme follow-up approved." in entry.body
        assert "Confidence 88%. Noted." in entry.body

    def test_action_clean_send_with_reply_hours(self):
        event = TrustEvent.operational(
            type=EventType.ACTION_CLEAN_SEND,
            actor_name="Rex",
            category="outreach",
            confidence=0.93,
        )
        entry = write_entry_for_trust_event(
            event,
            relationship_day=75,
            context={"subject": "Acme follow-up", "reply_hours": 4},
        )

        assert "Acme follow-up sent. Replied in 4 hours." in entry.body
        assert "Directness worked again." in entry.body
        assert "I won't forget that." in entry.body

    def test_action_rejected(self):
        event = TrustEvent.operational(
            type=EventType.ACTION_REJECTED,
            actor_name="Rex",
            category="outreach",
            confidence=0.55,
        )
        entry = write_entry_for_trust_event(
            event,
            relationship_day=33,
            context={"subject": "Henderson reply"},
        )

        assert entry.kind is JournalEventKind.OPERATIONAL_SETBACK
        assert "Henderson reply rejected." in entry.body
        assert "Pattern not strong enough. Noted." in entry.body

    def test_action_undone(self):
        event = TrustEvent.operational(
            type=EventType.ACTION_UNDONE,
            actor_name="Rex",
            category="outreach",
            confidence=0.77,
        )
        entry = write_entry_for_trust_event(
            event,
            relationship_day=47,
            context={"subject": "Henson follow-up"},
        )

        assert "Henson follow-up undone before it settled." in entry.body
        assert "Fair. Rebuilding." in entry.body

    def test_action_flagged_mistake(self):
        event = TrustEvent.operational(
            type=EventType.ACTION_FLAGGED_MISTAKE,
            actor_name="Rex",
            category="invoices",
            confidence=0.64,
            reason="Flagged Henderson when I meant Henson",
        )
        entry = write_entry_for_trust_event(
            event,
            relationship_day=47,
            context={"subject": "Invoice chase"},
        )

        assert "Invoice chase flagged." in entry.body
        assert "Flagged Henderson when I meant Henson." in entry.body
        assert "Fair. Rebuilding." in entry.body


class TestJournalWriterBatchAndValidation:
    def test_batch_skips_none_never_happens_for_known_events(self):
        events = [
            TrustEvent.user_promoted_rex(
                category="outreach",
                from_rank=Rank.OBSERVER,
                to_rank=Rank.DRAFTER,
            ),
            TrustEvent.operational(
                type=EventType.ACTION_CLEAN_SEND,
                actor_name="Rex",
                category="outreach",
                confidence=0.9,
            ),
        ]
        entries = write_entries_for_events(events, relationship_day=10)

        assert len(entries) == 2
        assert entries[0].source_event_ids == (events[0].id,)
        assert entries[1].source_event_ids == (events[1].id,)

    def test_class_wrapper(self):
        writer = JournalWriter()
        event = TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
        )
        entry = writer.write_for_event(event, relationship_day=1)

        assert entry.kind is JournalEventKind.PROMOTION

    def test_invalid_day_raises(self):
        event = TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
        )
        with pytest.raises(ValueError):
            write_entry_for_trust_event(event, relationship_day=0)

    def test_all_entries_pass_voice_validator(self):
        events = [
            TrustEvent.user_promoted_rex(
                category="outreach",
                from_rank=Rank.OBSERVER,
                to_rank=Rank.DRAFTER,
            ),
            TrustEvent.user_demoted_rex(
                category="invoices",
                from_rank=Rank.SENDER,
                to_rank=Rank.DRAFTER,
            ),
            TrustEvent.rex_recommended_subagent_promotion(
                subagent="Scout",
                category="leads",
                from_rank=Rank.OBSERVER,
                to_rank=Rank.DRAFTER,
                reason="14 leads found",
                confidence=0.9,
            ),
            TrustEvent.operational(
                type=EventType.ACTION_FLAGGED_MISTAKE,
                actor_name="Rex",
                category="invoices",
                reason="Wrong vendor",
            ),
        ]
        entries = write_entries_for_events(events, relationship_day=47)

        for entry in entries:
            report = validate_voice(entry.body)
            assert not [v for v in report.violations if v.severity.value == "hard"]

    def test_word_count_stored(self):
        event = TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
        )
        entry = write_entry_for_trust_event(event, relationship_day=1)

        assert entry.word_count == len(entry.body.replace("\n", " ").split())
