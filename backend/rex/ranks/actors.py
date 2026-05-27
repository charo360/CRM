"""
Actors — Rex and his Sub-Agents.

Per REX.md §4.5, Rex is the single relationship the user maintains; his
Sub-Agents are invisible in operational copy. This module registers the
existing platform agents as Rex's deputies. Their *implementation* still
lives in `backend/agents/*` and the various worker files — this is just
the registry.

Pure module. The `backend_module` field is a hint for Phase 4 wiring;
nothing in Phase 2 imports those modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActorKind(str, Enum):
    REX = "rex"
    SUB_AGENT = "sub_agent"


@dataclass(frozen=True)
class Actor:
    """
    An entity whose Rank we track per Category.

    Equality is by (kind, name) — `display` is presentation only.
    """
    kind: ActorKind
    name: str               # canonical name; "Rex" for the singleton
    display: str            # user-facing label
    backend_module: str | None = None  # Phase 4 hint, never imported here

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Rex — the singleton
# ---------------------------------------------------------------------------

REX: Actor = Actor(
    kind=ActorKind.REX,
    name="Rex",
    display="Rex",
    backend_module=None,
)


# ---------------------------------------------------------------------------
# Sub-Agent specifications
# ---------------------------------------------------------------------------
#
# Maps the existing platform agents to Rex's team. The `categories` tuple
# declares which Categories this Sub-Agent operates in. A Sub-Agent's Rank
# is tracked PER CATEGORY just like Rex's — Scout might be Sender on Leads
# and Drafter on Suppliers.
#
# `team`:
#   "operations"        — autonomous workers (Scout, Pulse, Radar, ...)
#   "customer_service"  — talks to the user's customers (Sales, Orders, ...)

@dataclass(frozen=True)
class SubAgentSpec:
    name: str
    display: str
    team: str
    backend_module: str
    categories: tuple[str, ...]
    description: str

    def to_actor(self) -> Actor:
        return Actor(
            kind=ActorKind.SUB_AGENT,
            name=self.name,
            display=self.display,
            backend_module=self.backend_module,
        )


# Operations team — work on the user's behalf.
_OPERATIONS_TEAM: tuple[SubAgentSpec, ...] = (
    SubAgentSpec(
        name="Scout",
        display="Scout",
        team="operations",
        backend_module="scout_service",
        categories=("leads", "outreach"),
        description="Finds leads. Watches social, web, signal feeds.",
    ),
    SubAgentSpec(
        name="Pulse",
        display="Pulse",
        team="operations",
        backend_module="daily_analyzer",
        categories=("follow_ups", "leads"),
        description="Monitors pipeline health and cold deals.",
    ),
    SubAgentSpec(
        name="Radar",
        display="Radar",
        team="operations",
        backend_module="market_intelligence",
        categories=("analytics",),
        description="Tracks competitors and market signals.",
    ),
    SubAgentSpec(
        name="Funding",
        display="Funding",
        team="operations",
        backend_module="funding_finder",
        categories=("investors",),
        description="Watches funding opportunities and investor moves.",
    ),
    SubAgentSpec(
        name="Ad-watch",
        display="Ad-watch",
        team="operations",
        backend_module="ad_health_monitor",
        categories=("meta_ads", "google_ads"),
        description="Monitors ad health and surfaces alerts.",
    ),
    SubAgentSpec(
        name="Smart-Notes",
        display="Smart Notes",
        team="operations",
        backend_module="smart_notes",
        categories=("meeting_follow_through",),
        description="Captures meetings and generates follow-through.",
    ),
)


# Customer-service team — talks to the user's customers.
_CUSTOMER_SERVICE_TEAM: tuple[SubAgentSpec, ...] = (
    SubAgentSpec(
        name="Sales",
        display="Sales",
        team="customer_service",
        backend_module="agents.sales_agent",
        categories=("outreach", "leads"),
        description="Handles inbound sales conversations.",
    ),
    SubAgentSpec(
        name="Orders",
        display="Orders",
        team="customer_service",
        backend_module="agents.order_agent",
        categories=("orders",),
        description="Confirms and tracks customer orders.",
    ),
    SubAgentSpec(
        name="Payments",
        display="Payments",
        team="customer_service",
        backend_module="agents.payment_agent",
        categories=("payments",),
        description="Reconciles and confirms customer payments.",
    ),
    SubAgentSpec(
        name="Bookings",
        display="Bookings",
        team="customer_service",
        backend_module="agents.booking_agent",
        categories=("bookings", "calendar"),
        description="Manages reservations and appointments.",
    ),
    SubAgentSpec(
        name="Complaints",
        display="Complaints",
        team="customer_service",
        backend_module="agents.complaint_agent",
        categories=("replies",),
        description="Triages and de-escalates customer complaints.",
    ),
    SubAgentSpec(
        name="Support",
        display="Support",
        team="customer_service",
        backend_module="agents.support_agent",
        categories=("replies",),
        description="Handles general customer support replies.",
    ),
    SubAgentSpec(
        name="Personal",
        display="Personal",
        team="customer_service",
        backend_module="agents.personal_agent",
        categories=("replies",),
        description="Handles personal-style 1:1 conversations.",
    ),
    SubAgentSpec(
        name="Gmail-Filter",
        display="Gmail Filter",
        team="customer_service",
        backend_module="agents.gmail_filter_agent",
        categories=("replies",),
        description="Filters and routes inbound Gmail messages.",
    ),
)


SUB_AGENTS: tuple[SubAgentSpec, ...] = _OPERATIONS_TEAM + _CUSTOMER_SERVICE_TEAM


# Lookup index built once.
_BY_NAME: dict[str, Actor] = {REX.name: REX}
for _s in SUB_AGENTS:
    _BY_NAME[_s.name] = _s.to_actor()


def actor_by_name(name: str) -> Actor:
    """Lookup an Actor (Rex or a Sub-Agent) by canonical name."""
    return _BY_NAME[name]


def is_actor(name: str) -> bool:
    """True iff the given name identifies a registered Actor."""
    return name in _BY_NAME


def operations_team() -> tuple[SubAgentSpec, ...]:
    return _OPERATIONS_TEAM


def customer_service_team() -> tuple[SubAgentSpec, ...]:
    return _CUSTOMER_SERVICE_TEAM
