"""
Protocols for the orchestrator (Phase 5) to plug Sub-Agents and executors in.

Two seams:

    ActionProducer  — anything that *generates* Actions when invoked.
                      The existing backend Sub-Agents (Scout, Pulse, Sales,
                      etc.) will be adapted into producers in Phase 5.

    ActionExecutor  — anything that actually *carries out* an Action when
                      the time comes (after approval, or autonomously for
                      Sender+ rank). The existing action_mode_routes.py and
                      composio_service.py will be wrapped into executors.

These Protocols are intentionally narrow. Phase 4 ships zero implementations
of them — that's the point. Phase 5 brings real producers and executors
without touching anything we've built so far.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from rex.actions.primitives import Action, Outcome


@runtime_checkable
class ActionProducer(Protocol):
    """
    Generates Action manifests.

    A producer is bound to an actor (Rex or a Sub-Agent) and one or more
    Categories. It reads from external signals (inbox, CRM, social feeds,
    etc.) and returns Actions in the PROPOSED state — the Ledger handles
    storage + initial state recording.

    Implementations should NEVER mutate the Ledger directly; they only
    propose. The orchestrator wires the rest.
    """

    @property
    def actor_name(self) -> str: ...

    @property
    def categories(self) -> tuple[str, ...]: ...

    def produce(
        self,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> tuple[Action, ...]:
        """
        Return zero or more Actions to be proposed.

        `context` is an opaque hint bag the orchestrator may pass through
        (e.g. {"window_hours": 8} for the overnight loop). Implementations
        ignore keys they don't understand.
        """


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionResult:
    """
    Result returned by an ActionExecutor.

    success=True means the executor performed the work and any external
    side-effect succeeded. The Ledger should transition the Action to SENT
    and attach the outcome.

    success=False means the executor tried and failed (network, auth, etc.).
    The Ledger should transition the Action to FAILED with the outcome.
    """
    success: bool
    outcome: Outcome


@runtime_checkable
class ActionExecutor(Protocol):
    """
    Carries out an Action. The orchestrator picks an executor based on
    Action.kind and Action.category, then awaits its result.

    An executor that doesn't understand an Action raises NotImplementedError
    rather than returning success=False — the orchestrator routes elsewhere.
    """

    def supports(self, action: Action) -> bool: ...

    def execute(self, action: Action) -> ExecutionResult: ...
