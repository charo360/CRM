"""Serialize Zilo's team for the dashboard team page."""

from __future__ import annotations

from typing import Any

from rex.identity import CHIEF_OF_STAFF_DISPLAY, CHIEF_OF_STAFF_NAME
from rex.loop import Orchestrator
from rex.ranks.actors import (
    customer_service_team,
    operations_team,
)


ACTION_MODE_AGENTS: tuple[dict[str, str], ...] = (
    {
        "id": "zilo_scout",
        "label": "Zilo Scout",
        "description": "Autonomous web scouts — finds leads, funding, and buy-intent signals.",
        "href": "/dashboard/action-mode",
    },
    {
        "id": "funding_hunter",
        "label": "Funding Hunter",
        "description": "VCs, grants, accelerators, and funding opportunities.",
        "href": "/dashboard/action-mode",
    },
    {
        "id": "lead_gen",
        "label": "Lead Generation",
        "description": "Potential customers, groups, and outbound opportunities.",
        "href": "/dashboard/action-mode",
    },
    {
        "id": "social_scout",
        "label": "Social Scout",
        "description": "Social conversations with purchase intent.",
        "href": "/dashboard/action-mode",
    },
    {
        "id": "admin_autopilot",
        "label": "Admin Autopilot",
        "description": "Invoice reminders and cold-customer re-engagement.",
        "href": "/dashboard/action-mode",
    },
)

CHAT_GROUP_DEFS: tuple[tuple[str, str, frozenset[str]], ...] = (
    (
        "advertising",
        "Advertising & growth",
        frozenset({"meta_ads", "google_ads", "x_ads", "seo", "social_media", "creative"}),
    ),
    (
        "crm",
        "CRM & revenue",
        frozenset({
            "sales", "customers", "orders", "follow_ups", "bookings", "broadcasts",
            "messages", "contacts", "suppliers", "payments", "invoices", "quotes",
            "finance", "follow_ups", "forms",
        }),
    ),
    (
        "commerce",
        "Commerce platforms",
        frozenset({
            "shopify", "shopify_orders", "shopify_products", "shopify_analytics",
            "shopify_customers", "stripe", "shop", "inventory", "loyalty",
        }),
    ),
    (
        "email_comms",
        "Email & messaging",
        frozenset({
            "gmail", "microsoft", "email_marketing", "klaviyo", "mailchimp", "brevo",
            "whatsapp", "telegram", "slack",
        }),
    ),
    (
        "social_ops",
        "Social inbox & scheduling",
        frozenset({"social_inbox", "social_scheduler", "social_monitor"}),
    ),
    (
        "analytics",
        "Analytics & team",
        frozenset({"analytics", "team_analytics", "team", "automations", "nps"}),
    ),
    (
        "productivity",
        "Calendar, docs & productivity",
        frozenset({
            "google_calendar", "google_sheets", "notion", "document", "documents",
        }),
    ),
    (
        "support",
        "Platform support",
        frozenset({"zilo_support"}),
    ),
)


def _chat_group_id(agent_id: str) -> str:
    for gid, _label, ids in CHAT_GROUP_DEFS:
        if agent_id in ids:
            return gid
    return "other"


def _sub_agent_row(spec: Any, orch: Orchestrator) -> dict[str, Any]:
    cat = spec.categories[0]
    try:
        st = orch.engine.standing(spec.name, cat)
        rank = st.rank.display
        probation = st.on_probation
    except Exception:
        rank = "Observer"
        probation = False
    return {
        "id": spec.name.lower().replace(" ", "-").replace("_", "-"),
        "name": spec.name,
        "label": spec.display,
        "team": spec.team,
        "description": spec.description,
        "categories": list(spec.categories),
        "rank": rank,
        "on_probation": probation,
        "chat_agent_id": _name_to_chat_id(spec.name),
    }


def _name_to_chat_id(name: str) -> str | None:
    """Best-effort map Rex sub-agent name → Zilo Chat agent id."""
    m = {
        "Scout": None,  # Action Mode / scouts
        "Sales": "sales",
        "Orders": "orders",
        "Payments": "payments",
        "Bookings": "bookings",
        "Gmail-Filter": "gmail",
        "Support": "zilo_support",
        "Personal": "messages",
    }
    return m.get(name)


def serialize_team(orch: Orchestrator | None = None) -> dict[str, Any]:
    from assistant.agents import list_agents_public

    orch = orch  # may be None for standings skip

    def standing(spec: Any) -> dict[str, Any]:
        if orch is None:
            return {
                "id": spec.name.lower().replace(" ", "-"),
                "name": spec.name,
                "label": spec.display,
                "team": spec.team,
                "description": spec.description,
                "categories": list(spec.categories),
                "rank": "—",
                "on_probation": False,
                "chat_agent_id": _name_to_chat_id(spec.name),
            }
        return _sub_agent_row(spec, orch)

    chat_all = list_agents_public()
    specialists = [a for a in chat_all if a["id"] != "general"]

    grouped: dict[str, list[dict[str, str]]] = {gid: [] for gid, _, _ in CHAT_GROUP_DEFS}
    grouped["other"] = []

    for a in specialists:
        gid = _chat_group_id(a["id"])
        grouped.setdefault(gid, []).append(a)

    chat_groups = []
    for gid, label, _ in CHAT_GROUP_DEFS:
        items = sorted(grouped.get(gid, []), key=lambda x: x["label"].lower())
        if items:
            chat_groups.append({"id": gid, "label": label, "agents": items})
    other = sorted(grouped.get("other", []), key=lambda x: x["label"].lower())
    if other:
        chat_groups.append({"id": "other", "label": "More specialists", "agents": other})

    zilo_standing = None
    if orch is not None:
        try:
            st = orch.engine.standing(CHIEF_OF_STAFF_NAME, "outreach")
            zilo_standing = {"rank": st.rank.display, "on_probation": st.on_probation}
        except Exception:
            pass

    return {
        "chief": {
            "name": CHIEF_OF_STAFF_NAME,
            "label": CHIEF_OF_STAFF_DISPLAY,
            "description": "Chief of Staff — briefings, trust, and coordination. Speaks for the whole team.",
            "chat_agent_id": "general",
            "standing": zilo_standing,
        },
        "operations": [standing(s) for s in operations_team()],
        "customer_service": [standing(s) for s in customer_service_team()],
        "action_mode": list(ACTION_MODE_AGENTS),
        "chat_groups": chat_groups,
        "chat_total": len(specialists),
    }
