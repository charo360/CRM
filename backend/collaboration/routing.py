"""Keyword-based inbound routing → conversation assignment."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def match_routing_rules(
    text: str,
    subject: Optional[str],
    channel: str,
    rules: List[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str]]:
    """Return (assignee_user_id, matched_rule_name) or (None, None)."""
    combined = f"{subject or ''}\n{text or ''}".lower()
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("enabled", True):
            continue
        assignee = rule.get("assignee_user_id")
        if not assignee:
            continue
        chans = rule.get("channels") or ["whatsapp", "social", "email"]
        if channel not in chans and "*" not in chans:
            continue
        keywords = rule.get("keywords") or []
        if not keywords:
            continue
        if any(str(kw).lower() in combined for kw in keywords):
            name = rule.get("name") or "rule"
            return str(assignee), name
    return None, None


async def resolve_assignee_name(db, business_id: str, assignee_user_id: str) -> Optional[str]:
    if assignee_user_id == business_id:
        owner = await db.users.find_one({"_id": business_id}, {"owner_name": 1, "business_name": 1})
        if owner:
            return owner.get("owner_name") or owner.get("business_name")
        return "Owner"
    tm = await db.team_members.find_one(
        {"business_id": business_id, "user_id": assignee_user_id},
        {"name": 1},
    )
    if tm:
        return tm.get("name")
    u = await db.users.find_one({"_id": assignee_user_id}, {"owner_name": 1})
    return u.get("owner_name") if u else None


async def apply_inbound_routing(
    db,
    *,
    business_user_id: str,
    customer_id: str,
    text: str,
    subject: Optional[str],
    channel: str,
) -> None:
    """If routing is enabled, assign conversation from keyword rules (default: only when unassigned)."""
    try:
        doc = await db.business_inbound_routing.find_one({"business_id": business_user_id})
        if not doc or not doc.get("enabled"):
            return

        replace_existing = bool(doc.get("replace_existing"))

        if not replace_existing:
            existing = await db.conversation_assignments.find_one(
                {"business_id": business_user_id, "customer_id": customer_id}
            )
            if existing and existing.get("assigned_to"):
                return

        rules = doc.get("rules") or []
        assignee, rule_name = match_routing_rules(text, subject, channel, rules)

        if not assignee:
            default_assignee = doc.get("default_assignee")
            if default_assignee in (None, "", "owner"):
                assignee = business_user_id
            else:
                assignee = str(default_assignee)

        if not assignee:
            return

        aname = await resolve_assignee_name(db, business_user_id, assignee)

        assignment_doc = {
            "customer_id": customer_id,
            "business_id": business_user_id,
            "assigned_to": assignee,
            "assigned_by": "inbound_routing",
            "assigned_at": datetime.utcnow(),
            "notes": f"auto: {rule_name}" if rule_name else "auto: default",
        }
        await db.conversation_assignments.update_one(
            {"business_id": business_user_id, "customer_id": customer_id},
            {"$set": assignment_doc},
            upsert=True,
        )
        await db.customers.update_one(
            {"_id": customer_id, "user_id": business_user_id},
            {"$set": {"assigned_to": assignee, "assigned_to_name": aname}},
        )
    except Exception as e:
        logger.warning("[inbound_routing] skipped: %s", e)
