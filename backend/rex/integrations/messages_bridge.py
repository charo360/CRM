"""
Draft WhatsApp replies from unread CRM messages — review before send.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def draft_whatsapp_inbox(
    db: Any,
    uid: str,
    *,
    max_threads: int = 10,
    biz_name: str = "",
) -> dict[str, Any]:
    from action_mode_routes import _add_to_queue

    drafted = 0
    # Latest unread incoming per customer
    pipeline = [
        {"$match": {
            "user_id": uid,
            "direction": "incoming",
            "read": {"$ne": True},
        }},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$customer_id",
            "last_body": {"$first": "$body"},
            "last_at": {"$first": "$created_at"},
            "message_id": {"$first": "$_id"},
        }},
        {"$limit": max_threads},
    ]
    try:
        groups = await db.messages.aggregate(pipeline).to_list(max_threads)
    except Exception as e:
        logger.warning("[zilo] WA draft aggregate failed: %s", e)
        return {"drafts_queued": 0, "error": str(e)}

    sign = biz_name or "the team"
    for g in groups:
        cid = g.get("_id")
        if not cid:
            continue
        cust = await db.customers.find_one({"_id": cid, "user_id": uid})
        if not cust:
            continue
        phone = cust.get("phone") or cust.get("phone_number")
        if not phone:
            continue
        cid_s = str(cid)
        existing = await db.action_mode_queue.find_one({
            "user_id": uid,
            "status": "pending",
            "metadata.customer_id": cid_s,
            "action_type": "send_whatsapp",
        })
        if existing:
            continue
        name = cust.get("name") or "there"
        first = name.split()[0] if name else "there"
        snippet = (g.get("last_body") or "")[:200]
        draft = (
            f"Hi {first}! Thanks for your message.\n\n"
        )
        if snippet:
            draft += f'You wrote: "{snippet[:120]}..."\n\n'
        draft += (
            "[Edit this draft before sending — Zilo does not auto-send without your approval.]\n\n"
            f"— {sign}"
        )
        await _add_to_queue(
            db,
            uid,
            "zilo_inbox",
            "send_whatsapp",
            f"WhatsApp reply: {name}",
            draft,
            {
                "customer_id": cid_s,
                "phone": phone,
                "message_id": str(g.get("message_id", "")),
                "snippet": snippet,
                "channel": "whatsapp",
                "review_only": False,
            },
        )
        drafted += 1

    logger.info("[zilo] WA drafts uid=%s count=%d", uid, drafted)
    return {"drafts_queued": drafted}
