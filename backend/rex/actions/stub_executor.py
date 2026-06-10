"""Stub executor — marks approved actions SENT without external integrations."""

from __future__ import annotations

from rex.actions.primitives import Action, Outcome
from rex.actions.protocols import ActionExecutor, ExecutionResult


class StubExecutor(ActionExecutor):
    """Local testing: approve/dismiss updates ledger only."""

    def supports(self, action: Action) -> bool:
        return True

    def execute(self, action: Action) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            outcome=Outcome(external_ref="local-stub", rows_affected=1),
        )


def ensure_stub_executor(orch) -> None:
    if not getattr(orch, "_stub_executor_registered", False):
        orch.register_executor(StubExecutor())
        orch._stub_executor_registered = True  # type: ignore[attr-defined]
