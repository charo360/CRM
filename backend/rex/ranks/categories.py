"""
Category catalog — Tier 1 through Tier 8 from REX.md §6.

A Category is a domain Rex (and his Sub-Agents) operate in. Every Action,
TrustEvent, and Standing is keyed by Category. Categories never change once
declared; adding a new one is a code change, not a runtime config.

Pure module. No I/O, no DB, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Tier(IntEnum):
    """How early in the relationship a Category becomes available."""
    CORE = 1                # Day 1
    OPERATIONS = 2          # Weeks 2-4
    GROWTH = 3              # Month 1+
    ACQUISITION = 4         # slow earn — money on the line
    CUSTOMER = 5            # customer relationships
    PIPELINE = 6            # parallel to Outreach (suppliers, investors, partners)
    COMMERCE = 7            # inventory, orders, storefront
    TEAM_OPS = 8            # field, team, analytics, docs


@dataclass(frozen=True)
class _CategoryDef:
    """Internal — used to build the Category enum members below."""
    name: str          # canonical machine name (also enum value)
    display: str       # what Rex says ("outreach", "Meta Ads", etc.)
    tier: Tier


# ---------------------------------------------------------------------------
# The full catalog.
# Order matters only for human reading; lookups are by name.
# Keep names lowercase_with_underscores. Display strings are what Rex says.
# ---------------------------------------------------------------------------

_CATALOG: tuple[_CategoryDef, ...] = (
    # Tier 1 — Core (Day 1)
    _CategoryDef("outreach", "outreach", Tier.CORE),
    _CategoryDef("replies", "email replies", Tier.CORE),
    _CategoryDef("leads", "leads", Tier.CORE),
    _CategoryDef("follow_ups", "follow-ups", Tier.CORE),
    _CategoryDef("meeting_follow_through", "meeting follow-through", Tier.CORE),

    # Tier 2 — Operations
    _CategoryDef("quotes", "quotes & proposals", Tier.OPERATIONS),
    _CategoryDef("invoices", "invoices", Tier.OPERATIONS),
    _CategoryDef("bookings", "bookings", Tier.OPERATIONS),
    _CategoryDef("payments", "payments", Tier.OPERATIONS),
    _CategoryDef("calendar", "calendar", Tier.OPERATIONS),

    # Tier 3 — Growth
    _CategoryDef("broadcast", "broadcast campaigns", Tier.GROWTH),
    _CategoryDef("sms_marketing", "SMS marketing", Tier.GROWTH),
    _CategoryDef("social_scheduling", "social scheduling", Tier.GROWTH),
    _CategoryDef("social_dms", "social DMs", Tier.GROWTH),
    _CategoryDef("seo_content", "SEO content", Tier.GROWTH),
    _CategoryDef("behavior_offers", "behavior-triggered offers", Tier.GROWTH),

    # Tier 4 — Acquisition (money on the line — slow earn)
    _CategoryDef("meta_ads", "Meta Ads", Tier.ACQUISITION),
    _CategoryDef("google_ads", "Google Ads", Tier.ACQUISITION),
    _CategoryDef("x_ads", "X Ads", Tier.ACQUISITION),
    _CategoryDef("gbp", "Google Business Profile", Tier.ACQUISITION),

    # Tier 5 — Customer relationships
    _CategoryDef("loyalty", "loyalty", Tier.CUSTOMER),
    _CategoryDef("feedback", "feedback & NPS", Tier.CUSTOMER),
    _CategoryDef("client_portal", "client portal", Tier.CUSTOMER),

    # Tier 6 — Pipeline
    _CategoryDef("suppliers", "supplier relations", Tier.PIPELINE),
    _CategoryDef("investors", "investor relations", Tier.PIPELINE),
    _CategoryDef("partners", "partner relations", Tier.PIPELINE),

    # Tier 7 — Commerce
    _CategoryDef("inventory", "inventory", Tier.COMMERCE),
    _CategoryDef("orders", "orders", Tier.COMMERCE),
    _CategoryDef("storefront", "storefront", Tier.COMMERCE),

    # Tier 8 — Team operations
    _CategoryDef("field_ops", "field operations", Tier.TEAM_OPS),
    _CategoryDef("team_routing", "team routing", Tier.TEAM_OPS),
    _CategoryDef("analytics", "analytics", Tier.TEAM_OPS),
    _CategoryDef("documents", "documents", Tier.TEAM_OPS),
)


# Build the public Category enum dynamically from the catalog.
# Using a plain class rather than `enum.Enum` so we can attach `display`
# and `tier` properties cleanly.

@dataclass(frozen=True)
class Category:
    """A domain Rex and his team operate in. Equality is by `name`."""
    name: str
    display: str
    tier: Tier

    def __str__(self) -> str:
        return self.name


_BY_NAME: dict[str, Category] = {}
for _d in _CATALOG:
    _c = Category(name=_d.name, display=_d.display, tier=_d.tier)
    _BY_NAME[_d.name] = _c


def all_categories() -> tuple[Category, ...]:
    """Return every declared Category in catalog order."""
    return tuple(_BY_NAME.values())


def category_tier(name: str) -> Tier:
    """Lookup the tier for a category name. Raises KeyError if unknown."""
    return _BY_NAME[name].tier


def category(name: str) -> Category:
    """Lookup a Category by its canonical name. Raises KeyError if unknown."""
    return _BY_NAME[name]


def is_category(name: str) -> bool:
    """True iff the given string names a registered Category."""
    return name in _BY_NAME
