"""
rex.loop — The Orchestrator and the Overnight Loop (REX.md §7 phase 5).

Phase 5 of the Rex build. This is where the previous four phases finally
meet: the Orchestrator holds a Ledger (Phase 4), an EventStore + RankEngine
(Phase 2), and a Notebook (Phase 3), and coordinates them as Actions move
through their lifecycle.

THIS PHASE STAYS PURE.
======================
No real Sub-Agent code is imported. No external sends. No LLM calls.
Phase 5 ships against `rex.tests.fakes` (FakeProducer / FakeExecutor),
which satisfy the Phase-4 Protocols deterministically.

Phase 5b — a future swap-only commit — will replace the fakes with real
adapters around the existing backend modules (`scout_service.py`,
`action_mode_routes.py`, the agents in `backend/agents/*`). At that point
zero orchestration code should change. That's the entire point of the
Protocol seams added in Phase 4.

PUBLIC API
==========
    Routing             Pure decision: PROPOSED → STAGED vs PROPOSED → SENT
    RoutingDecision     Result enum with reason string
    Orchestrator        The coordinator. Holds + mutates the system state.
    OvernightReport     Summary of one loop run.
    sweep_undo_window   Emits ACTION_CLEAN_SEND for SENT actions past the window.
    DEFAULT_ROUTING_POLICY  Shipped policy; tunable via the orchestrator.
"""

from rex.loop.routing import (
    DEFAULT_ROUTING_POLICY,
    Routing,
    RoutingDecision,
    RoutingPolicy,
    decide_route,
)
from rex.loop.orchestrator import (
    Orchestrator,
    OvernightReport,
    ApprovalResult,
    ExecutionDispatch,
)
from rex.loop.sweeps import sweep_undo_window, SweepReport

__all__ = [
    "Routing", "RoutingDecision", "RoutingPolicy",
    "DEFAULT_ROUTING_POLICY", "decide_route",
    "Orchestrator", "OvernightReport",
    "ApprovalResult", "ExecutionDispatch",
    "sweep_undo_window", "SweepReport",
]
