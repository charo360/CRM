"""
Tests for rex.loop — the Orchestrator + routing + sweep.

Coverage:
    1. Routing matrix (OBSERVER drops, DRAFTER stages, SENDER conditional,
       OPERATOR conditional, CHIEF sends; probation always stages)
    2. Orchestrator.run_overnight pulls every producer, records every
       proposal, makes correct routing decisions
    3. User approve / reject / dismiss / undo paths
    4. Trust events emitted from approve land in event store AND update engine
    5. Executor failure → FAILED state + FLAGGED_MISTAKE
    6. Executor exception → FAILED state + FLAGGED_MISTAKE
    7. No executor available → action remains APPROVED (caller retries later)
    8. Sweep: SENT actions past undo window emit CLEAN_SEND; idempotent
    9. End-to-end: producer→stage→approve→execute→trust event→rank engine

Run from backend/:
    python -m pytest rex/tests/loop_test.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rex.actions import (
    Action, ActionKind, ActionState, Ledger, Outcome,
)
from rex.actions.primitives import UNDO_WINDOW_SECONDS
from rex.loop import (
    DEFAULT_ROUTING_POLICY,
    Orchestrator,
    OvernightReport,
    Routing,
    RoutingDecision,
    decide_route,
    sweep_undo_window,
)
from rex.ranks.engine import RankEngine, Standing
from rex.ranks.events import EventType, Rank, TrustEvent
from rex.ranks.store import InMemoryEventStore
from rex.tests.fakes import FakeExecutor, FakeProducer, make_action


# ===========================================================================
# Routing
# ===========================================================================

def _standing(rank: Rank, on_probation: bool = False, category: str = "outreach") -> Standing:
    return Standing(actor_name="Rex", category=category, rank=rank, on_probation=on_probation)


class TestRouting:
    def test_observer_drops(self):
        d = decide_route(
            action=make_action(rank=Rank.OBSERVER, confidence=1.0),
            standing=_standing(Rank.OBSERVER),
        )
        assert d.routing is Routing.DROP

    def test_drafter_always_stages(self):
        # Even at confidence 1.0, Drafter NEVER sends.
        d = decide_route(
            action=make_action(rank=Rank.DRAFTER, confidence=1.0),
            standing=_standing(Rank.DRAFTER),
        )
        assert d.routing is Routing.STAGE

    def test_sender_sends_above_threshold(self):
        d = decide_route(
            action=make_action(rank=Rank.SENDER, confidence=0.9),
            standing=_standing(Rank.SENDER),
        )
        assert d.routing is Routing.SEND

    def test_sender_stages_below_threshold(self):
        d = decide_route(
            action=make_action(rank=Rank.SENDER, confidence=0.6),
            standing=_standing(Rank.SENDER),
        )
        assert d.routing is Routing.STAGE

    def test_operator_sends_at_lower_threshold(self):
        d = decide_route(
            action=make_action(rank=Rank.OPERATOR, confidence=0.75),
            standing=_standing(Rank.OPERATOR),
        )
        assert d.routing is Routing.SEND

    def test_chief_sends_at_low_confidence(self):
        d = decide_route(
            action=make_action(rank=Rank.CHIEF_OF_STAFF, confidence=0.55),
            standing=_standing(Rank.CHIEF_OF_STAFF),
        )
        assert d.routing is Routing.SEND

    def test_probation_overrides_send(self):
        # Even Sender at 0.99 confidence stages when on probation.
        d = decide_route(
            action=make_action(rank=Rank.SENDER, confidence=0.99),
            standing=_standing(Rank.SENDER, on_probation=True),
        )
        assert d.routing is Routing.STAGE
        assert "probation" in d.reason.lower()

    def test_decisions_carry_human_reason(self):
        d = decide_route(
            action=make_action(rank=Rank.SENDER, confidence=0.95),
            standing=_standing(Rank.SENDER),
        )
        assert d.reason  # non-empty
        assert "Sender" in d.reason or "sender" in d.reason


# ===========================================================================
# Orchestrator — run_overnight
# ===========================================================================

class TestOvernight:
    def _orch_with_sender_rex(self) -> Orchestrator:
        # Pre-seed Rex to Sender on outreach via legitimate event chain.
        store = InMemoryEventStore()
        store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        return Orchestrator(event_store=store)

    def test_no_producers_no_actions(self):
        orch = Orchestrator()
        report = orch.run_overnight()
        assert report.actions_proposed == 0
        assert report.decisions == ()

    def test_drafter_action_stages(self):
        orch = Orchestrator()  # Rex is Observer everywhere by default
        # Bump Rex to Drafter on outreach so the action doesn't get DROPPED.
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)

        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.DRAFTER, confidence=0.99)],
        )
        orch.register_producer(producer)
        report = orch.run_overnight()
        assert report.actions_proposed == 1
        assert report.actions_staged == 1
        assert report.actions_sent == 0

    def test_observer_action_drops(self):
        # Rex is OBSERVER on outreach (default) → action drops.
        orch = Orchestrator()
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.OBSERVER, confidence=1.0)],
        )
        orch.register_producer(producer)
        report = orch.run_overnight()
        assert report.actions_dropped == 1
        assert report.actions_staged == 0

    def test_sender_high_conf_sends_via_executor(self):
        orch = self._orch_with_sender_rex()
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        executor = FakeExecutor()
        orch.register_producer(producer)
        orch.register_executor(executor)

        report = orch.run_overnight()
        assert report.actions_sent == 1
        assert len(executor.execute_calls) == 1

    def test_sender_low_conf_stages_instead(self):
        orch = self._orch_with_sender_rex()
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.55)],
        )
        orch.register_producer(producer)
        orch.register_executor(FakeExecutor())
        report = orch.run_overnight()
        assert report.actions_staged == 1
        assert report.actions_sent == 0

    def test_probation_forces_stage_even_at_sender(self):
        orch = Orchestrator()
        # Manually craft an on-probation Sender standing via events.
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        orch.event_store.append(TrustEvent.user_demoted_rex(
            category="outreach",
            from_rank=Rank.SENDER, to_rank=Rank.DRAFTER,
            reason="oops",
        ))
        # Now promote back to Sender — but probation flag persists.
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.DRAFTER, to_rank=Rank.SENDER,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)
        assert orch.engine.standing("Rex", "outreach").on_probation

        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.99)],
        )
        orch.register_producer(producer)
        orch.register_executor(FakeExecutor())
        report = orch.run_overnight()
        assert report.actions_staged == 1
        assert report.actions_sent == 0

    def test_auto_dispatch_false_leaves_approved(self):
        orch = self._orch_with_sender_rex()
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        orch.register_producer(producer)
        orch.register_executor(FakeExecutor())
        report = orch.run_overnight(auto_dispatch=False)
        # Routing.SEND took action through APPROVED but not SENT.
        assert report.actions_sent == 0
        approved = orch.ledger.actions_in_state(ActionState.APPROVED)
        assert len(approved) == 1


# ===========================================================================
# User verbs
# ===========================================================================

class TestUserVerbs:
    def _setup_staged(self) -> tuple[Orchestrator, str]:
        orch = Orchestrator()
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.DRAFTER, confidence=0.9)],
        )
        executor = FakeExecutor()
        orch.register_producer(producer)
        orch.register_executor(executor)
        orch.run_overnight()
        action_id = orch.ledger.staged_actions()[0].id
        return orch, action_id

    def test_approve_dispatches_and_emits_event(self):
        orch, action_id = self._setup_staged()
        result = orch.approve(action_id, reason="LGTM")
        assert result.final_state is ActionState.SENT
        # TrustEvent appeared in store AND was applied to engine.
        types = [e.type for e in orch.event_store.all_events()
                 if e.actor_name == "Rex" and e.category == "outreach"]
        assert EventType.ACTION_APPROVED in types

    def test_reject_emits_action_rejected(self):
        orch, action_id = self._setup_staged()
        events = orch.reject(action_id, reason="No thanks")
        assert events[0].type is EventType.ACTION_REJECTED
        assert orch.ledger.current_state(action_id) is ActionState.REJECTED

    def test_dismiss_emits_no_trust_event(self):
        orch, action_id = self._setup_staged()
        events = orch.dismiss(action_id)
        assert events == ()
        assert orch.ledger.current_state(action_id) is ActionState.DISMISSED

    def test_undo_emits_action_undone(self):
        orch, action_id = self._setup_staged()
        orch.approve(action_id)
        events = orch.undo(action_id, reason="thought twice")
        assert events[0].type is EventType.ACTION_UNDONE
        assert orch.ledger.current_state(action_id) is ActionState.UNDONE

    def test_approve_unknown_raises(self):
        orch = Orchestrator()
        with pytest.raises(KeyError):
            orch.approve("nope")


# ===========================================================================
# Executor failure paths
# ===========================================================================

class TestExecutorFailures:
    def _orch_with_sender(self) -> Orchestrator:
        orch = Orchestrator()
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)
        return orch

    def test_executor_clean_failure_marks_failed(self):
        orch = self._orch_with_sender()
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        executor = FakeExecutor(should_fail=True)
        orch.register_producer(producer)
        orch.register_executor(executor)

        report = orch.run_overnight()
        assert report.actions_failed == 1
        # Trust event flow.
        types = [e.type for e in orch.event_store.all_events()
                 if e.type is EventType.ACTION_FLAGGED_MISTAKE]
        assert len(types) == 1

    def test_executor_exception_marks_failed(self):
        orch = self._orch_with_sender()
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        executor = FakeExecutor(should_raise=RuntimeError)
        orch.register_producer(producer)
        orch.register_executor(executor)

        report = orch.run_overnight()
        assert report.actions_failed == 1
        # The action ended up FAILED, not SENT.
        all_actions = orch.ledger.all_actions()
        assert orch.ledger.current_state(all_actions[0].id) is ActionState.FAILED

    def test_no_executor_leaves_approved(self):
        orch = self._orch_with_sender()
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        orch.register_producer(producer)
        # No executor registered.
        report = orch.run_overnight()
        assert report.actions_sent == 0
        approved = orch.ledger.actions_in_state(ActionState.APPROVED)
        assert len(approved) == 1

    def test_no_executor_then_register_then_dispatch(self):
        orch = self._orch_with_sender()
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        orch.register_producer(producer)
        orch.run_overnight()
        orch.register_executor(FakeExecutor())
        results = orch.dispatch_pending_executions()
        assert len(results) == 1
        assert results[0].final_state is ActionState.SENT


# ===========================================================================
# Sweep — ACTION_CLEAN_SEND
# ===========================================================================

class TestSweep:
    def test_sweep_emits_clean_send_after_window(self):
        # Build a ledger with a SENT action whose `at` is far in the past.
        orch = Orchestrator()
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        orch.register_producer(producer)
        orch.register_executor(FakeExecutor())
        orch.run_overnight()

        # Pretend "now" is two hours after the SENT transition.
        future = datetime.now(timezone.utc) + timedelta(seconds=UNDO_WINDOW_SECONDS + 60)
        events = orch.sweep_clean_sends(now=future)
        assert len(events) == 1
        assert events[0].type is EventType.ACTION_CLEAN_SEND

    def test_sweep_is_idempotent(self):
        orch = Orchestrator()
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        orch.register_producer(producer)
        orch.register_executor(FakeExecutor())
        orch.run_overnight()

        future = datetime.now(timezone.utc) + timedelta(seconds=UNDO_WINDOW_SECONDS + 60)
        events1 = orch.sweep_clean_sends(now=future)
        events2 = orch.sweep_clean_sends(now=future)
        assert len(events1) == 1
        assert events2 == ()  # nothing new

    def test_sweep_skips_within_window(self):
        orch = Orchestrator()
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)
        producer = FakeProducer(
            actor_name_value="Rex",
            categories_value=("outreach",),
            actions=[make_action(rank=Rank.SENDER, confidence=0.95)],
        )
        orch.register_producer(producer)
        orch.register_executor(FakeExecutor())
        orch.run_overnight()

        events = orch.sweep_clean_sends()  # now = now → still within window
        assert events == ()


# ===========================================================================
# End-to-end — Phase 5 closes the loop
# ===========================================================================

class TestEndToEnd:
    def test_full_arc_producer_to_trust_score(self):
        """
        Scout proposes an action while Rex is Drafter; user approves;
        executor runs; trust event lands in store; engine updates.
        """
        orch = Orchestrator()
        # Routing reads the ACTION'S actor standing — Scout's, not Rex's.
        # Bring Scout to Drafter on outreach via the canonical chain
        # (recommend → user approve) so his action won't be DROPPED.
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            reason="setup", confidence=0.9,
        )
        orch.event_store.append(rec)
        orch.event_store.append(TrustEvent.user_approved_recommendation(
            subagent="Scout", category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            recommendation_id=rec.id,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)

        scout_action = make_action(
            actor="Scout", rank=Rank.DRAFTER,
            category="outreach", confidence=0.9,
        )
        orch.register_producer(FakeProducer(
            actor_name_value="Scout",
            categories_value=("outreach",),
            actions=[scout_action],
        ))
        orch.register_executor(FakeExecutor())

        report = orch.run_overnight()
        assert report.actions_staged == 1

        action_id = orch.ledger.staged_actions()[0].id
        result = orch.approve(action_id)
        assert result.final_state is ActionState.SENT

        # ACTION_APPROVED is recorded against Scout in outreach.
        scout_events = [
            e for e in orch.event_store.all_events()
            if e.actor_name == "Scout" and e.category == "outreach"
        ]
        approved = [e for e in scout_events if e.type is EventType.ACTION_APPROVED]
        assert len(approved) == 1

        # Trust score for Scout/outreach is now positive.
        from rex.ranks.recommendations import compute_trust_score
        score, count = compute_trust_score(
            orch.event_store.all_events(),
            actor_name="Scout", category="outreach",
        )
        assert count == 1
        assert score >= 0.9
