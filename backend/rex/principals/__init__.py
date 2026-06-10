"""
rex.principals — Phase 8: Two-Sided Loyalty Model (REX.md §4.6).

Pure module. No I/O. Owns three primitives every other rex.* phase consumes
once it is multi-user aware:

    Role         The team-shaped identity (FOUNDER, SALES, SUPPORT, ...)
    Visibility   The audience scope of an Action / Notebook / Journal item
    Principal    A single person Rex is serving (founder OR team member)

INVARIANTS (REX.md §4.6)
========================
    1. A solo founder is the default. `Principal.founder()` returns a
       principal that sees everything — Phases 1-7 keep working unchanged.
    2. Layer 1 (financials, full pipeline, full notebook, Rex's journal,
       team journal) is FOUNDER_ONLY. No role grants it.
    3. Team members see their lane and only their lane unless the founder
       explicitly grants more.
    4. Rex never reveals to a team member anything the founder hasn't
       cleared (`can_see` enforces the floor).
    5. Visibility is a property of the OBJECT, not of the channel. The
       channel layer (Phase 9) renders. This layer decides what exists
       for each principal.
"""

from rex.principals.role import Role, ROLE_DEFAULT_CATEGORIES
from rex.principals.visibility import (
    Visibility,
    VisibilityScope,
    can_see,
    visibility_founder_only,
    visibility_team_shared,
    visibility_role_scoped,
    visibility_principal,
)
from rex.principals.principal import (
    Principal,
    PrincipalRegistry,
)

__all__ = [
    "Role", "ROLE_DEFAULT_CATEGORIES",
    "Visibility", "VisibilityScope", "can_see",
    "visibility_founder_only",
    "visibility_team_shared",
    "visibility_role_scoped",
    "visibility_principal",
    "Principal", "PrincipalRegistry",
]
