"""Delegate ↔ specialist agent bridge.

Zilo Delegate can invoke any registered assistant agent in the background
when a task needs inbox, CRM, ads, or other system access beyond hardcoded gatherers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Default specialist for each delegate category (emails resolved dynamically).
CATEGORY_SPECIALIST: dict[str, str] = {
    "follow_ups": "follow_ups",
    "invoices": "invoices",
    "leads": "customers",
    "outreach": "customers",
    "replies": "messages",
    "broadcast": "broadcasts",
    "social_scheduling": "social_scheduler",
    "bookings": "bookings",
}

_AGENT_GATHER_TIMEOUT_SEC = 120.0


async def resolve_delegate_specialist(
    db: Any,
    user_id: Any,
    task: str,
    category: str,
) -> str | None:
    """Pick the best specialist agent for this delegation."""
    from assistant.agents import resolve_agent_id

    if category == "emails":
        try:
            from composio_service import get_connection_status, TOOLKIT_GMAIL, TOOLKIT_OUTLOOK

            uid = str(user_id)
            if (await get_connection_status(uid, TOOLKIT_GMAIL)).get("connected"):
                return "gmail"
            if (await get_connection_status(uid, TOOLKIT_OUTLOOK)).get("connected"):
                return "microsoft"
        except Exception as e:  # noqa: BLE001
            logger.debug("[delegate] integration check failed: %s", e)
        return "gmail"

    mapped = CATEGORY_SPECIALIST.get(category)
    if mapped:
        return resolve_agent_id(mapped)

    low = (task or "").lower()
    if any(k in low for k in ("proposal", "business plan", "document", "pdf", "presentation")):
        return resolve_agent_id("document")
    if any(k in low for k in ("meta ad", "facebook ad", "instagram ad", "campaign")):
        return resolve_agent_id("meta_ads")
    if any(k in low for k in ("schedule post", "social post", "instagram post")):
        return resolve_agent_id("social_scheduler")
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_work_items_from_agent(result: dict[str, Any]) -> list[dict[str, Any]]:
    text = (result.get("text") or "").strip()
    parsed = _extract_json_object(text)
    if parsed and isinstance(parsed.get("work_items"), list):
        return [x for x in parsed["work_items"] if isinstance(x, dict)]

    # Some agents return structured steps
    for step in reversed(result.get("steps") or []):
        res = step.get("result")
        if isinstance(res, dict) and isinstance(res.get("work_items"), list):
            return [x for x in res["work_items"] if isinstance(x, dict)]
        if isinstance(res, dict) and isinstance(res.get("emails"), list):
            return _emails_list_to_work_items(res["emails"])
    return []


def _emails_list_to_work_items(emails: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in emails:
        if not isinstance(row, dict):
            continue
        from_addr = row.get("from") or row.get("from_addr") or row.get("sender") or ""
        subject = row.get("subject") or "(no subject)"
        body = row.get("body") or row.get("snippet") or row.get("preview") or ""
        label = str(from_addr).split("<")[0].strip() or str(from_addr) or "Sender"
        items.append(
            {
                "label": label[:120],
                "parent_label": str(subject)[:120],
                "email": _clean_email(from_addr),
                "context": f"Subject: {subject}\n\n{body}"[:3000],
                "source": "email",
                "lead_group": "email",
                "reply_channel": "email",
                "reply_to_subject": subject,
            }
        )
    return items


def _clean_email(addr: str) -> str:
    text = (addr or "").strip().lower()
    if "<" in text and ">" in text:
        return text.split("<")[-1].split(">")[0].strip()
    return text


def normalize_agent_work_items(
    items: list[dict[str, Any]],
    *,
    category: str,
    limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in items[:limit]:
        label = str(raw.get("label") or raw.get("name") or "Contact")[:120]
        ctx = str(raw.get("context") or raw.get("snippet") or raw.get("message") or "")[:4000]
        source = (raw.get("source") or ("email" if category == "emails" else "crm")).strip().lower()
        reply_ch = (raw.get("reply_channel") or ("email" if source == "email" else "")).strip().lower()
        item: dict[str, Any] = {
            "label": label,
            "parent_label": (raw.get("parent_label") or raw.get("subject") or "")[:120] or None,
            "context": ctx,
            "contact_id": raw.get("contact_id"),
            "source": source,
            "lead_group": raw.get("lead_group") or ("email" if source == "email" else "crm"),
            "phone": raw.get("phone"),
            "email": raw.get("email") or (_clean_email(label) if "@" in label else None),
            "reply_channel": reply_ch or None,
            "reply_to_subject": raw.get("reply_to_subject") or raw.get("subject"),
            "email_thread_id": raw.get("email_thread_id") or raw.get("thread_id"),
            "email_message_id": raw.get("email_message_id") or raw.get("message_id"),
        }
        if source == "email" or category == "emails":
            item["source"] = "email"
            item["lead_group"] = "email"
            item["reply_channel"] = "email"
        if item.get("context") or item.get("email") or item.get("phone"):
            out.append(item)
    return out


async def gather_work_items_via_agent(
    db: Any,
    user: dict[str, Any],
    doc: dict[str, Any],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Run a specialist agent in the background to discover real targets via tools."""
    from .service import map_category

    task = (doc.get("task") or "").strip()
    category = doc.get("category") or map_category(task)
    interpreted = doc.get("interpreted") or {}
    agent_id = interpreted.get("specialist_agent") or await resolve_delegate_specialist(
        db, user.get("_id"), task, category
    )
    if not agent_id:
        return []

    from assistant.agent_runner import run_agent

    agent_task = f"""BACKGROUND DELEGATE (founder approves every draft before send).

Founder task: {task}
Interpreted target: {interpreted.get('interpreted_task') or task}
Action per item: {interpreted.get('action') or 'Draft a reply'}

You MUST use your specialist tools first (inbox, CRM, orders, etc.) — never invent contacts.
Do NOT reply with meta summaries like "I reviewed emails" — return structured targets only.

Return ONLY valid JSON:
{{"work_items": [
  {{
    "label": "Sender or contact name",
    "email": "optional",
    "phone": "optional",
    "context": "The actual inbound message or email body to reply to",
    "reply_channel": "email|whatsapp|slack|instagram|linkedin|...",
    "reply_to_subject": "for emails",
    "source": "email|crm",
    "thread_id": "optional email thread id"
  }}
]}}

Max {limit} items. Skip newsletters and automated mail."""

    logger.info("[delegate] invoking specialist agent=%s category=%s", agent_id, category)
    try:
        result = await asyncio.wait_for(
            run_agent(
                agent_id=agent_id,
                task=agent_task,
                db=db,
                user=user,
                context={"delegate": True, "category": category, "mode": "gather"},
            ),
            timeout=_AGENT_GATHER_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning("[delegate] specialist agent timed out agent=%s", agent_id)
        return []
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] specialist agent failed agent=%s: %s", agent_id, e)
        return []

    raw_items = _parse_work_items_from_agent(result or {})
    normalized = normalize_agent_work_items(raw_items, category=category, limit=limit)
    logger.info(
        "[delegate] specialist agent=%s returned %d work item(s)",
        agent_id,
        len(normalized),
    )
    return normalized
