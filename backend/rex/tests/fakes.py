"""
Test doubles for the Phase 4 Protocols.

Both fakes are deterministic, hold no external state, and depend only on
rex.* modules. Phase 6 / 7 tests can also use these.

DO NOT use these in production code paths. They live under rex/tests/
specifically so production imports cannot reach them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from rex.actions.primitives import Action, ActionKind, Outcome
from rex.actions.protocols import ActionProducer, ActionExecutor, ExecutionResult
from rex.ranks.events import Rank


# ---------------------------------------------------------------------------
# FakeProducer
# ---------------------------------------------------------------------------

@dataclass
class FakeProducer:
    """
    Deterministic ActionProducer.

    Configure with a fixed list of Actions to emit each time `produce` is
    called, or pass a callable for dynamic behavior.
    """
    actor_name_value: str
    categories_value: tuple[str, ...]
    actions: list[Action] = field(default_factory=list)
    # Optional callable: (context) -> tuple[Action, ...]. Overrides `actions`.
    factory: Callable[[Mapping[str, Any] | None], tuple[Action, ...]] | None = None
    call_count: int = 0

    @property
    def actor_name(self) -> str:
        return self.actor_name_value

    @property
    def categories(self) -> tuple[str, ...]:
        return self.categories_value

    def produce(
        self,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> tuple[Action, ...]:
        self.call_count += 1
        if self.factory is not None:
            return self.factory(context)
        return tuple(self.actions)


# ---------------------------------------------------------------------------
# FakeExecutor
# ---------------------------------------------------------------------------

@dataclass
class FakeExecutor:
    """
    Deterministic ActionExecutor.

    By default supports every Action and reports success. Pass:
      - `supported_kinds` to narrow what it claims to handle
      - `should_fail=True` to report ExecutionResult(success=False)
      - `should_raise=ExceptionClass` to raise from execute()
    """
    supported_kinds: tuple[ActionKind, ...] | None = None
    should_fail: bool = False
    should_raise: type[BaseException] | None = None
    external_ref: str = "fake-ref-001"
    rows_affected: int = 1
    error_class: str = "FakeError"
    error_message: str = "fake-failure"
    execute_calls: list[Action] = field(default_factory=list)

    def supports(self, action: Action) -> bool:
        if self.supported_kinds is None:
            return True
        return action.kind in self.supported_kinds

    def execute(self, action: Action) -> ExecutionResult:
        self.execute_calls.append(action)
        if self.should_raise is not None:
            raise self.should_raise("fake explosion")
        if self.should_fail:
            return ExecutionResult(
                success=False,
                outcome=Outcome(
                    error_class=self.error_class,
                    error_message=self.error_message,
                ),
            )
        return ExecutionResult(
            success=True,
            outcome=Outcome(
                external_ref=self.external_ref,
                rows_affected=self.rows_affected,
            ),
        )


# ---------------------------------------------------------------------------
# Convenience: build a propose-ready Action with sensible defaults
# ---------------------------------------------------------------------------

def make_action(
    *,
    actor: str = "Zilo",
    rank: Rank = Rank.DRAFTER,
    category: str = "outreach",
    kind: ActionKind = ActionKind.OUTREACH,
    summary: str = "Follow up with Patel.",
    reasoning: str = "9 days silent.",
    confidence: float = 0.9,
    target: str | None = "Patel",
) -> Action:
    """Quick Action builder for tests; matches the canonical example."""
    return Action.propose(
        actor_name=actor,
        rank_at_time=rank,
        category=category,
        kind=kind,
        summary=summary,
        reasoning=reasoning,
        confidence=confidence,
        target_subject=target,
    )
