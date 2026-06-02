"""
Visibility — audience scopes on Actions, Notebook entries, and Journal items.

REX.md §4.6 establishes three visibility layers. We represent them as a simple
enum + a scope dataclass, and a pure 'can_see' predicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VisibilityScope(str, Enum):
    FOUNDER_ONLY = "founder_only"
    TEAM_SHARED = "team_shared"
    ROLE_SCOPED = "role_scoped"
    PRINCIPAL = "principal"


@dataclass(frozen=True)
class Visibility:
    scope: VisibilityScope
    target_role: str | None = None       # Populated for ROLE_SCOPED (e.g. "sales")
    target_principal_id: str | None = None  # Populated for PRINCIPAL (specific team member)

    @classmethod
    def founder_only(cls) -> Visibility:
        return cls(scope=VisibilityScope.FOUNDER_ONLY)

    @classmethod
    def team_shared(cls) -> Visibility:
        return cls(scope=VisibilityScope.TEAM_SHARED)

    @classmethod
    def role_scoped(cls, role: str) -> Visibility:
        return cls(scope=VisibilityScope.ROLE_SCOPED, target_role=role.lower())

    @classmethod
    def principal(cls, principal_id: str) -> Visibility:
        return cls(scope=VisibilityScope.PRINCIPAL, target_principal_id=principal_id)


# Helpers for quick import / mapping
visibility_founder_only = Visibility.founder_only()
visibility_team_shared = Visibility.team_shared()
visibility_role_scoped = Visibility.role_scoped
visibility_principal = Visibility.principal


def can_see(
    visibility: Visibility,
    *,
    principal_id: str,
    role: str,
    is_founder: bool,
) -> bool:
    """
    Check if a principal is allowed to see an item with the given visibility.

    Highly-tested pure gate. Ensures Layer 1 is never leaked, and Layer 2
    is strictly scoped.
    """
    if is_founder:
        return True

    # Layer 1 is founder-only
    if visibility.scope is VisibilityScope.FOUNDER_ONLY:
        return False

    if visibility.scope is VisibilityScope.TEAM_SHARED:
        return True

    if visibility.scope is VisibilityScope.ROLE_SCOPED:
        return visibility.target_role == role.lower()

    if visibility.scope is VisibilityScope.PRINCIPAL:
        return visibility.target_principal_id == principal_id

    return False
