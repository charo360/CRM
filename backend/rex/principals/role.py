"""
Role — the team-shaped identity of a Principal.

Roles map to default category bundles (Layer 2 in REX.md §4.6). The founder
can override the default mapping at invite time; this module just declares
what 'support', 'sales', etc. mean by default.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    FOUNDER = "founder"
    SALES = "sales"
    SUPPORT = "support"
    OPS = "ops"
    MARKETING = "marketing"
    FINANCE = "finance"

    @property
    def display(self) -> str:
        return {
            Role.FOUNDER: "Founder",
            Role.SALES: "Sales",
            Role.SUPPORT: "Support",
            Role.OPS: "Ops",
            Role.MARKETING: "Marketing",
            Role.FINANCE: "Finance",
        }[self]


# Default Tier-1 / Tier-2 categories each role gets at invite time.
# References the canonical Category names in rex.ranks.categories.
# A founder always overrides this if they want — Rex enforces whatever
# the founder declared at invite, not these defaults blindly.
ROLE_DEFAULT_CATEGORIES: dict[Role, tuple[str, ...]] = {
    Role.FOUNDER: (),  # founder = ALL; empty tuple is sentinel for "all"
    Role.SALES: ("outreach", "replies", "leads", "follow_ups", "meeting_follow_through"),
    Role.SUPPORT: ("replies", "follow_ups"),
    Role.OPS: ("follow_ups", "meeting_follow_through"),
    Role.MARKETING: ("broadcast", "social_post"),
    Role.FINANCE: ("invoices", "payments", "quotes"),
}
