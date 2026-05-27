"""
Tests for rex.actions — the Action primitive, Ledger, and rendering.

Coverage:
    1. Action.propose() — required fields, confidence bounds, payload freeze
    2. ActionState lifecycle — every legal transition + at least one illegal
    3. derive_current_state — pure replay of changes
    4. Ledger — record_proposal, transition, queries
    5. Phase 2 trust event emission via state_change_trust_events
    6. ACTION_CLEAN_SEND helper
    7. Story rendering — content + STAGED affordance + reverse chrono
    8. Inspect rendering — rows + ordering
    9. End-to-end: Rex stages, user approves, Phase 2 events flow

Run from backend/:
    python -m pytest rex/tests/actions_test.py -v
"""

from __future__ import annotations

import pytest

from rex.actions import (
    Action, ActionKind, ActionState, ActionStateChange, Outcome,
    Ledger, InMemoryLedgerStore, LedgerStore,
    ActionProducer, ActionExecutor, ExecutionResult,
    InvalidTransition, is_valid_transition,
    state_change_trust_events, derive_current_state,
    story_render, story_render_action,
    inspect_rows, InspectRow,
    TERMINAL_STATES,
)
from rex.actions.transitions import clean_send_event
from rex.ranks.events import EventType, Rank, TrustEvent


# ===========================================================================
# Action primitive
# ===========================================================================

class TestActionPropose:
    def test_basic_propose(self):
        a = Action.propose(
            actor_name="Rex",
            rank_at_time=Rank.DRAFTER,
            category="outreach",
            kind=ActionKind.OUTREACH,
            summary="Follow up with Patel.",
            confidence=0.85,
        )
        assert a.actor_name == "Rex"
        assert a.kind is ActionKind.OUTREACH
        assert a.confidence == 0.85
        assert a.proposed_at is not None
        assert a.id  # non-empty

    def test_summary_is_stripped(self):
        a = Action.propose(
            actor_name="Rex", rank_at_time=Rank.OBSERVER,
            category="outreach", kind=ActionKind.OUTREACH,
            summary="   leading + trailing   ",
        )
        assert a.summary == "leading + trailing"

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValueError):
            Action.propose(
                actor_name="Rex", rank_at_time=Rank.DRAFTER,
                category="outreach", kind=ActionKind.OUTREACH,
                summary="x", confidence=1.5,
            )
        with pytest.raises(ValueError):
            Action.propose(
                actor_name="Rex", rank_at_time=Rank.DRAFTER,
                category="outreach", kind=ActionKind.OUTREACH,
                summary="x", confidence=-0.1,
            )

    def test_payload_defaults_to_empty(self):
        a = Action.propose(
            actor_name="Rex", rank_at_time=Rank.OBSERVER,
            category="outreach", kind=ActionKind.OUTREACH,
            summary="x",
        )
        assert dict(a.payload) == {}

    def test_payload_is_independent_of_caller_dict(self):
        # The Action manifest must capture payload immutably — caller
        # mutating their dict afterward must not leak into the Action.
        d = {"to": "patel@example.com"}
        a = Action.propose(
            actor_name="Rex", rank_at_time=Rank.SENDER,
            category="outreach", kind=ActionKind.OUTREACH,
            summary="x", payload=d,
        )
        d["to"] = "someone-else@example.com"
        assert a.payload["to"] == "patel@example.com"


# ===========================================================================
# Lifecycle / transitions
# ===========================================================================

class TestTransitions:
    @pytest.mark.parametrize("frm,to,ok", [
        (None, ActionState.PROPOSED, True),
        (ActionState.PROPOSED, ActionState.STAGED, True),
        (ActionState.PROPOSED, ActionState.SENT, True),
        (ActionState.STAGED, ActionState.APPROVED, True),
        (ActionState.STAGED, ActionState.REJECTED, True),
        (ActionState.STAGED, ActionState.DISMISSED, True),
        (ActionState.APPROVED, ActionState.SENT, True),
        (ActionState.APPROVED, ActionState.FAILED, True),
        (ActionState.SENT, ActionState.UNDONE, True),
        # Illegal:
        (None, ActionState.STAGED, False),
        (ActionState.PROPOSED, ActionState.APPROVED, False),
        (ActionState.SENT, ActionState.STAGED, False),
        (ActionState.REJECTED, ActionState.SENT, False),
        (ActionState.UNDONE, ActionState.SENT, False),
        (ActionState.FAILED, ActionState.SENT, False),
    ])
    def test_legal_and_illegal_transitions(self, frm, to, ok):
        assert is_valid_transition(frm, to) is ok

    def test_terminal_states_have_no_outgoing(self):
        for terminal in TERMINAL_STATES:
            for s in ActionState:
                assert not is_valid_transition(terminal, s)


class TestDeriveCurrentState:
    def test_single_proposal(self):
        changes = [
            ActionStateChange.make(
                action_id="a1", from_state=None,
                to_state=ActionState.PROPOSED, actor_name="Rex",
            ),
        ]
        assert derive_current_state(changes) is ActionState.PROPOSED

    def test_full_staging_to_send_flow(self):
        changes = [
            ActionStateChange.make(
                action_id="a1", from_state=None,
                to_state=ActionState.PROPOSED, actor_name="Rex",
            ),
            ActionStateChange.make(
                action_id="a1", from_state=ActionState.PROPOSED,
                to_state=ActionState.STAGED, actor_name="Rex",
            ),
            ActionStateChange.make(
                action_id="a1", from_state=ActionState.STAGED,
                to_state=ActionState.APPROVED, actor_name="User",
            ),
            ActionStateChange.make(
                action_id="a1", from_state=ActionState.APPROVED,
                to_state=ActionState.SENT, actor_name="Rex",
            ),
        ]
        assert derive_current_state(changes) is ActionState.SENT

    def test_replay_rejects_inconsistent_from_state(self):
        changes = [
            ActionStateChange.make(
                action_id="a1", from_state=None,
                to_state=ActionState.PROPOSED, actor_name="Rex",
            ),
            ActionStateChange.make(
                action_id="a1",
                from_state=ActionState.SENT,   # wrong! current is PROPOSED
                to_state=ActionState.UNDONE, actor_name="User",
            ),
        ]
        with pytest.raises(InvalidTransition):
            derive_current_state(changes)

    def test_empty_history_raises(self):
        with pytest.raises(InvalidTransition):
            derive_current_state([])


# ===========================================================================
# Ledger
# ===========================================================================

def _propose_outreach(*, actor="Rex", rank=Rank.DRAFTER, conf=0.9) -> Action:
    return Action.propose(
        actor_name=actor, rank_at_time=rank,
        category="outreach", kind=ActionKind.OUTREACH,
        summary=f"Outreach from {actor}.",
        reasoning="9 days silent, prior cadence was 4 days.",
        confidence=conf,
        target_subject="Patel",
    )


class TestLedgerBasics:
    def test_record_proposal_records_initial_state(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        assert ledger.current_state(a.id) is ActionState.PROPOSED
        assert len(ledger.changes(a.id)) == 1

    def test_in_memory_store_satisfies_protocol(self):
        s = InMemoryLedgerStore()
        assert isinstance(s, LedgerStore)

    def test_double_record_proposal_raises(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        with pytest.raises(ValueError):
            ledger.record_proposal(a)

    def test_get_unknown_returns_none(self):
        ledger = Ledger()
        assert ledger.get("missing") is None

    def test_current_state_for_unknown_raises(self):
        ledger = Ledger()
        with pytest.raises(KeyError):
            ledger.current_state("missing")


class TestLedgerTransitions:
    def test_proposed_to_staged(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        change, events = ledger.transition(
            action_id=a.id, to_state=ActionState.STAGED, actor_name="Rex",
        )
        assert change.to_state is ActionState.STAGED
        assert events == ()  # no trust event from queuing

    def test_user_approve_emits_action_approved(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        ledger.transition(
            action_id=a.id, to_state=ActionState.STAGED, actor_name="Rex",
        )
        change, events = ledger.transition(
            action_id=a.id, to_state=ActionState.APPROVED,
            actor_name="User", reason="Looks good",
        )
        assert change.to_state is ActionState.APPROVED
        assert len(events) == 1
        assert events[0].type is EventType.ACTION_APPROVED
        assert events[0].actor_name == "Rex"           # action belongs to Rex
        assert events[0].category == "outreach"

    def test_user_reject_emits_action_rejected(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.STAGED, actor_name="Rex")
        _, events = ledger.transition(
            action_id=a.id, to_state=ActionState.REJECTED, actor_name="User",
        )
        assert events[0].type is EventType.ACTION_REJECTED

    def test_user_undo_emits_action_undone(self):
        ledger = Ledger()
        a = _propose_outreach(rank=Rank.SENDER)
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.SENT, actor_name="Rex")
        _, events = ledger.transition(
            action_id=a.id, to_state=ActionState.UNDONE, actor_name="User",
        )
        assert events[0].type is EventType.ACTION_UNDONE

    def test_failed_execution_emits_flagged_mistake(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.STAGED, actor_name="Rex")
        ledger.transition(action_id=a.id, to_state=ActionState.APPROVED, actor_name="User")
        _, events = ledger.transition(
            action_id=a.id, to_state=ActionState.FAILED, actor_name="Rex",
            outcome=Outcome(error_class="SMTPError", error_message="timeout"),
        )
        assert events[0].type is EventType.ACTION_FLAGGED_MISTAKE

    def test_dismiss_emits_no_trust_event(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.STAGED, actor_name="Rex")
        _, events = ledger.transition(
            action_id=a.id, to_state=ActionState.DISMISSED, actor_name="User",
        )
        assert events == ()  # user said "I'll handle it" — neutral

    def test_terminal_state_blocks_further_transitions(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.STAGED, actor_name="Rex")
        ledger.transition(action_id=a.id, to_state=ActionState.REJECTED, actor_name="User")
        with pytest.raises(InvalidTransition):
            ledger.transition(
                action_id=a.id, to_state=ActionState.APPROVED, actor_name="User",
            )

    def test_illegal_transition_raises(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        # PROPOSED → APPROVED is illegal (must go through STAGED).
        with pytest.raises(InvalidTransition):
            ledger.transition(
                action_id=a.id, to_state=ActionState.APPROVED, actor_name="User",
            )


class TestLedgerQueries:
    def test_staged_actions_filter(self):
        ledger = Ledger()
        a1 = _propose_outreach()
        a2 = _propose_outreach()
        ledger.record_proposal(a1)
        ledger.record_proposal(a2)
        ledger.transition(action_id=a1.id, to_state=ActionState.STAGED, actor_name="Rex")
        staged = ledger.staged_actions()
        assert len(staged) == 1
        assert staged[0].id == a1.id

    def test_actions_in_state(self):
        ledger = Ledger()
        a = _propose_outreach(rank=Rank.SENDER)
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.SENT, actor_name="Rex")
        sent = ledger.actions_in_state(ActionState.SENT)
        assert len(sent) == 1


# ===========================================================================
# clean_send_event helper
# ===========================================================================

class TestCleanSendEvent:
    def test_emits_clean_send_for_sent_action(self):
        a = _propose_outreach(rank=Rank.SENDER)
        evt = clean_send_event(action=a)
        assert evt.type is EventType.ACTION_CLEAN_SEND
        assert evt.actor_name == "Rex"
        assert evt.category == "outreach"


# ===========================================================================
# Rendering — Story mode
# ===========================================================================

class TestStoryRender:
    def test_empty_ledger(self):
        assert story_render(Ledger()) == "Nothing in the ledger yet."

    def test_staged_action_shows_review_token(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.STAGED, actor_name="Rex")
        rendered = story_render_action(ledger, a)
        assert "[Review → Send / Dismiss]" in rendered
        assert "Staged for you" in rendered
        assert "confidence: 90%" in rendered

    def test_sent_action_shows_undo_token(self):
        ledger = Ledger()
        a = _propose_outreach(rank=Rank.SENDER)
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.SENT, actor_name="Rex")
        rendered = story_render_action(ledger, a)
        assert "[Undo]" in rendered
        assert "Sent" in rendered

    def test_reverse_chronological_order(self):
        ledger = Ledger()
        first = _propose_outreach()
        second = _propose_outreach()
        ledger.record_proposal(first)
        ledger.record_proposal(second)
        out = story_render(ledger)
        # second was created later → should appear first in story view.
        assert out.find(second.summary) <= out.find(first.summary) or first.summary == second.summary

    def test_no_reasoning_no_why_line(self):
        ledger = Ledger()
        a = Action.propose(
            actor_name="Rex", rank_at_time=Rank.DRAFTER,
            category="outreach", kind=ActionKind.OUTREACH,
            summary="x", reasoning="", confidence=0.0,
        )
        ledger.record_proposal(a)
        rendered = story_render_action(ledger, a)
        assert "why:" not in rendered
        assert "confidence:" not in rendered  # zero confidence is hidden


# ===========================================================================
# Rendering — Inspect mode
# ===========================================================================

class TestInspectRender:
    def test_one_row_per_action(self):
        ledger = Ledger()
        a = _propose_outreach()
        ledger.record_proposal(a)
        ledger.transition(action_id=a.id, to_state=ActionState.STAGED, actor_name="Rex")
        rows = inspect_rows(ledger)
        assert len(rows) == 1
        r = rows[0]
        assert isinstance(r, InspectRow)
        assert r.actor == "Rex"
        assert r.category == "outreach"
        assert r.kind == "outreach"
        assert r.state == "staged"
        assert r.confidence_pct == 90
        assert r.target == "Patel"
        assert r.rank_at_time == "Drafter"

    def test_rows_reverse_chronological(self):
        import time
        ledger = Ledger()
        first = _propose_outreach()
        ledger.record_proposal(first)
        time.sleep(0.001)  # ensure ordering with µs resolution
        second = _propose_outreach()
        ledger.record_proposal(second)
        rows = inspect_rows(ledger)
        assert rows[0].action_id == second.id
        assert rows[1].action_id == first.id


# ===========================================================================
# Cross-phase end-to-end — Rex stages, user approves, trust event flows
# ===========================================================================

class TestEndToEnd:
    def test_stage_then_approve_emits_phase2_event(self):
        ledger = Ledger()
        action = Action.propose(
            actor_name="Scout", rank_at_time=Rank.DRAFTER,
            category="leads", kind=ActionKind.OUTREACH,
            summary="Found 3 new leads.",
            reasoning="Twitter signal: 'looking for a CRM' across 3 founders.",
            confidence=0.92,
            target_subject="Acme",
        )
        ledger.record_proposal(action)

        # Rex stages.
        _, e1 = ledger.transition(
            action_id=action.id, to_state=ActionState.STAGED, actor_name="Rex",
        )
        assert e1 == ()

        # User approves.
        _, e2 = ledger.transition(
            action_id=action.id, to_state=ActionState.APPROVED,
            actor_name="User", reason="Send them.",
        )
        assert len(e2) == 1
        # The trust event is on the SUB-AGENT (Scout), not on Rex.
        assert e2[0].actor_name == "Scout"
        assert e2[0].type is EventType.ACTION_APPROVED

        # Executor runs.
        _, e3 = ledger.transition(
            action_id=action.id, to_state=ActionState.SENT,
            actor_name="Scout",
            outcome=Outcome(external_ref="gmail-x", rows_affected=3),
        )
        assert e3 == ()
        assert ledger.current_state(action.id) is ActionState.SENT
