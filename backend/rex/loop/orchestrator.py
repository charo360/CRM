"""
The Orchestrator — the single object that holds the whole running system.

It owns:
    - Ledger          (Phase 4)  — all Actions + state changes
    - EventStore      (Phase 2)  — trust events (drives ranks)
    - RankEngine      (Phase 2)  — replayed state of every (actor, category)
    - Notebook        (Phase 3)  — Rex's memory of the business
    - producers       (Phase 4 Protocol) — emit Actions
    - executors       (Phase 4 Protocol) — carry them out
    - policy          (Phase 5) — routing thresholds

It exposes the four user-facing verbs:
    approve(action_id)   — STAGED → APPROVED → SENT
    reject(action_id)    — STAGED → REJECTED
    dismiss(action_id)   — STAGED → DISMISSED
    undo(action_id)      — SENT   → UNDONE

Plus the system verbs:
    run_overnight()      — pull from every producer, route, optionally dispatch
    sweep_clean_sends()  — emit ACTION_CLEAN_SEND for past-window SENT actions

THIS MODULE STAYS PURE.
The Orchestrator imports only rex.* modules; it never reaches into
`backend/agents/*` or `action_mode_routes.py`. Real wiring is Phase 5b.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from rex.actions.ledger import Ledger
from rex.actions.primitives import (
    Action,
    ActionState,
    ActionStateChange,
    Outcome,
)
from rex.actions.protocols import ActionExecutor, ActionProducer, ExecutionResult
from rex.actions.transitions import clean_send_event
from rex.loop.routing import (
    DEFAULT_ROUTING_POLICY,
    Routing,
    RoutingDecision,
    RoutingPolicy,
    decide_route,
)
from rex.memory.notebook import Notebook
from rex.ranks.engine import RankEngine
from rex.ranks.events import TrustEvent
from rex.ranks.store import EventStore, InMemoryEventStore


# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OvernightReport:
    """Summary of one `run_overnight` invocation."""
    actions_proposed: int
    actions_staged: int
    actions_sent: int
    actions_dropped: int
    actions_failed: int
    actions_by_actor: Mapping[str, int]
    decisions: tuple[RoutingDecision, ...]


@dataclass(frozen=True)
class ApprovalResult:
    """Returned by `approve()`. Tells the caller what happened downstream."""
    action_id: str
    final_state: ActionState
    trust_events: tuple[TrustEvent, ...]
    executor_outcome: Outcome | None = None


@dataclass(frozen=True)
class ExecutionDispatch:
    """Returned by `dispatch_pending_executions()`."""
    action_id: str
    final_state: ActionState
    trust_events: tuple[TrustEvent, ...]
    outcome: Outcome | None


# ---------------------------------------------------------------------------
# The Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """
    Coordinates Ledger, EventStore, RankEngine, Notebook, producers, executors.
    """

    def __init__(
        self,
        *,
        ledger: Ledger | None = None,
        event_store: EventStore | None = None,
        notebook: Notebook | None = None,
        policy: RoutingPolicy = DEFAULT_ROUTING_POLICY,
    ) -> None:
        self.ledger: Ledger = ledger if ledger is not None else Ledger()
        self.event_store: EventStore = event_store if event_store is not None else InMemoryEventStore()
        self.notebook: Notebook = notebook if notebook is not None else Notebook()
        self.engine: RankEngine = RankEngine.from_events(self.event_store)
        self.policy: RoutingPolicy = policy

        self._producers: list[ActionProducer] = []
        self._executors: list[ActionExecutor] = []
        # Track which SENT actions have already had a CLEAN_SEND emitted —
        # the sweep must be idempotent across multiple sweep calls.
        self._swept_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_producer(self, producer: ActionProducer) -> None:
        self._producers.append(producer)

    def register_executor(self, executor: ActionExecutor) -> None:
        self._executors.append(executor)

    # ------------------------------------------------------------------
    # Internal: emit trust events through both store and engine
    # ------------------------------------------------------------------

    def _emit_trust_events(self, events: Iterable[TrustEvent]) -> None:
        for e in events:
            self.event_store.append(e)
            self.engine.apply(e)

    # ------------------------------------------------------------------
    # The overnight loop
    # ------------------------------------------------------------------

    def run_overnight(
        self,
        *,
        context: Mapping[str, Any] | None = None,
        auto_dispatch: bool = True,
    ) -> OvernightReport:
        """
        Pull from every producer, route each proposal, optionally dispatch
        the "SEND" routes through executors immediately.

        With `auto_dispatch=False`, autonomous-route actions sit in
        APPROVED state pending a later `dispatch_pending_executions()` call.
        Useful for tests + dry-runs.
        """
        proposed = staged = sent = dropped = failed = 0
        by_actor: dict[str, int] = {}
        decisions: list[RoutingDecision] = []

        for producer in self._producers:
            for action in producer.produce(context=context):
                proposed += 1
                by_actor[action.actor_name] = by_actor.get(action.actor_name, 0) + 1
                self.ledger.record_proposal(action)

                standing = self.engine.standing(
                    action.actor_name, action.category,
                )
                decision = decide_route(
                    action=action, standing=standing, policy=self.policy,
                )
                decisions.append(decision)

                if decision.routing is Routing.DROP:
                    dropped += 1
                    continue

                if decision.routing is Routing.STAGE:
                    self.ledger.transition(
                        action_id=action.id,
                        to_state=ActionState.STAGED,
                        actor_name="Rex",
                        reason=decision.reason,
                    )
                    staged += 1
                    continue

                # Routing.SEND — fast path: mark APPROVED then dispatch.
                self.ledger.transition(
                    action_id=action.id,
                    to_state=ActionState.APPROVED,
                    actor_name=action.actor_name,
                    reason=decision.reason,
                )
                if auto_dispatch:
                    dispatched = self._dispatch_action(action)
                    if dispatched.final_state is ActionState.SENT:
                        sent += 1
                    elif dispatched.final_state is ActionState.FAILED:
                        failed += 1

        return OvernightReport(
            actions_proposed=proposed,
            actions_staged=staged,
            actions_sent=sent,
            actions_dropped=dropped,
            actions_failed=failed,
            actions_by_actor=by_actor,
            decisions=tuple(decisions),
        )

    # ------------------------------------------------------------------
    # User verbs
    # ------------------------------------------------------------------

    def approve(self, action_id: str, *, reason: str | None = None) -> ApprovalResult:
        """User approves a STAGED action; dispatch immediately."""
        action = self._must_get(action_id)
        _, events = self.ledger.transition(
            action_id=action_id, to_state=ActionState.APPROVED,
            actor_name="User", reason=reason,
        )
        self._emit_trust_events(events)

        dispatched = self._dispatch_action(action)
        return ApprovalResult(
            action_id=action_id,
            final_state=dispatched.final_state,
            trust_events=tuple(events) + dispatched.trust_events,
            executor_outcome=dispatched.outcome,
        )

    def reject(self, action_id: str, *, reason: str | None = None) -> tuple[TrustEvent, ...]:
        """User rejects a STAGED action."""
        self._must_get(action_id)
        _, events = self.ledger.transition(
            action_id=action_id, to_state=ActionState.REJECTED,
            actor_name="User", reason=reason,
        )
        self._emit_trust_events(events)
        return events

    def dismiss(self, action_id: str, *, reason: str | None = None) -> tuple[TrustEvent, ...]:
        """User says 'handle manually'. No trust event."""
        self._must_get(action_id)
        _, events = self.ledger.transition(
            action_id=action_id, to_state=ActionState.DISMISSED,
            actor_name="User", reason=reason,
        )
        self._emit_trust_events(events)
        return events

    def undo(self, action_id: str, *, reason: str | None = None) -> tuple[TrustEvent, ...]:
        """User undoes a SENT action (only valid within the undo window)."""
        self._must_get(action_id)
        _, events = self.ledger.transition(
            action_id=action_id, to_state=ActionState.UNDONE,
            actor_name="User", reason=reason,
        )
        self._emit_trust_events(events)
        return events

    # ------------------------------------------------------------------
    # Executor dispatch
    # ------------------------------------------------------------------

    def dispatch_pending_executions(self) -> tuple[ExecutionDispatch, ...]:
        """
        Run every APPROVED action through its executor. Used when
        run_overnight was called with auto_dispatch=False, or when
        approvals were collected over the day and now need to run.
        """
        results: list[ExecutionDispatch] = []
        for a in self.ledger.actions_in_state(ActionState.APPROVED):
            results.append(self._dispatch_action(a))
        return tuple(results)

    def _dispatch_action(self, action: Action) -> ExecutionDispatch:
        """Find an executor that supports this action and run it."""
        executor = self._find_executor(action)
        if executor is None:
            # No executor available — leave action APPROVED. The caller
            # may dispatch later when an adapter has been registered.
            return ExecutionDispatch(
                action_id=action.id,
                final_state=ActionState.APPROVED,
                trust_events=(),
                outcome=None,
            )

        try:
            result: ExecutionResult = executor.execute(action)
        except Exception as exc:  # executor crashed — record as FAILED
            _, events = self.ledger.transition(
                action_id=action.id,
                to_state=ActionState.FAILED,
                actor_name=action.actor_name,
                reason=f"Executor exception: {type(exc).__name__}",
                outcome=Outcome(
                    error_class=type(exc).__name__,
                    error_message=str(exc),
                ),
            )
            self._emit_trust_events(events)
            return ExecutionDispatch(
                action_id=action.id,
                final_state=ActionState.FAILED,
                trust_events=events,
                outcome=Outcome(error_class=type(exc).__name__, error_message=str(exc)),
            )

        if result.success:
            _, events = self.ledger.transition(
                action_id=action.id,
                to_state=ActionState.SENT,
                actor_name=action.actor_name,
                outcome=result.outcome,
            )
            self._emit_trust_events(events)
            return ExecutionDispatch(
                action_id=action.id,
                final_state=ActionState.SENT,
                trust_events=events,
                outcome=result.outcome,
            )

        # Executor reported a clean failure.
        _, events = self.ledger.transition(
            action_id=action.id,
            to_state=ActionState.FAILED,
            actor_name=action.actor_name,
            reason="Executor reported failure",
            outcome=result.outcome,
        )
        self._emit_trust_events(events)
        return ExecutionDispatch(
            action_id=action.id,
            final_state=ActionState.FAILED,
            trust_events=events,
            outcome=result.outcome,
        )

    def _find_executor(self, action: Action) -> ActionExecutor | None:
        for ex in self._executors:
            try:
                if ex.supports(action):
                    return ex
            except NotImplementedError:
                continue
        return None

    # ------------------------------------------------------------------
    # Sweeps
    # ------------------------------------------------------------------

    def sweep_clean_sends(self, *, now: datetime | None = None) -> tuple[TrustEvent, ...]:
        """
        For every action currently in SENT state whose undo window has
        closed, emit ACTION_CLEAN_SEND (Phase 2). Idempotent per action:
        we use a private "swept" set keyed by action_id.
        """
        from rex.loop.sweeps import sweep_undo_window
        report = sweep_undo_window(
            ledger=self.ledger,
            already_swept=self._swept_ids,
            now=now,
        )
        self._emit_trust_events(report.events)
        for aid in report.swept_action_ids:
            self._swept_ids.add(aid)
        return report.events

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _must_get(self, action_id: str) -> Action:
        a = self.ledger.get(action_id)
        if a is None:
            raise KeyError(f"No action with id={action_id!r}")
        return a
