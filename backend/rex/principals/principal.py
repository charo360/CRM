"""
Principal — a single person Rex is serving (Founder or Team Member).

Includes registry management for team membership (driven by invite trust events).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from rex.principals.role import Role, ROLE_DEFAULT_CATEGORIES


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    role: Role
    is_founder: bool
    allowed_categories: tuple[str, ...]  # Empty means "all" (founder default)

    @classmethod
    def founder(cls, *, id: str = "founder-01", name: str = "Founder") -> Principal:
        return cls(
            id=id,
            name=name,
            role=Role.FOUNDER,
            is_founder=True,
            allowed_categories=(),  # sees all
        )

    @classmethod
    def team_member(
        cls,
        *,
        id: str,
        name: str,
        role: Role,
        allowed_categories: Sequence[str] | None = None,
    ) -> Principal:
        if role is Role.FOUNDER:
            raise ValueError("Team members cannot have the FOUNDER role")
        cats = tuple(allowed_categories) if allowed_categories is not None else ROLE_DEFAULT_CATEGORIES.get(role, ())
        return cls(
            id=id,
            name=name,
            role=role,
            is_founder=False,
            allowed_categories=cats,
        )

    def can_access_category(self, category: str) -> bool:
        if self.is_founder:
            return True
        return category in self.allowed_categories


class PrincipalRegistry:
    """
    In-memory list of principals. Reconstructed by the RankEngine or Orchestrator
    on reload using TrustEvents (keeping our event-sourced promise).
    """

    def __init__(self, founder_id: str = "founder-01", founder_name: str = "Founder") -> None:
        self._principals: dict[str, Principal] = {}
        # Seed the founder
        founder = Principal.founder(id=founder_id, name=founder_name)
        self._principals[founder.id] = founder

    @property
    def founder(self) -> Principal:
        for p in self._principals.values():
            if p.is_founder:
                return p
        raise RuntimeError("No founder registered")

    def register(self, principal: Principal) -> None:
        self._principals[principal.id] = principal

    def remove(self, principal_id: str) -> None:
        if principal_id in self._principals and self._principals[principal_id].is_founder:
            raise ValueError("Cannot remove the founder")
        self._principals.pop(principal_id, None)

    def get(self, principal_id: str) -> Principal | None:
        return self._principals.get(principal_id)

    def all(self) -> tuple[Principal, ...]:
        return tuple(self._principals.values())
