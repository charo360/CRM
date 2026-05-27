"""
Pull inbox via email_sync and queue reply drafts (Action Mode).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def sync_and_draft_inbox(
    db: Any,
    uid: str,
    *,
    max_messages: int = 12,
    biz_name: str = "",
) -> dict[str, Any]:
    """
    1) Sync Gmail/Outlook into email_messages
    2) Queue send_email drafts for unread threads
    """
    from email_sync import sync_emails_for_user
    from action_mode_routes import _add_to_queue

    sync_result = await sync_emails_for_user(uid, db, max_results=max_messages)
    drafted = 0

    # Avoid large in-memory sorts (Atlas 32MB limit) — take recent unread without sort.
    unread = await db.email_messages.find(
        {"user_id": uid, "is_read": False},
        limit=max_messages * 3,
    ).to_list(max_messages * 3)
    unread = unread[-max_messages:] if len(unread) > max_messages else unread

    seen_threads: set[str] = set()
    for msg in unread:
        thread_id = str(msg.get("thread_id") or msg.get("_id") or "")
        if not thread_id or thread_id in seen_threads:
            continue
        seen_threads.add(thread_id)

        existing = await db.action_mode_queue.find_one({
            "user_id": uid,
            "status": "pending",
            "metadata.thread_id": thread_id,
        })
        if existing:
            continue

        subject = (msg.get("subject") or "(no subject)")[:80]
        from_addr = msg.get("from_addr") or "sender"
        snippet = (msg.get("body_clean") or msg.get("body_raw") or "")[:400]
        name = from_addr.split("<")[0].strip() or "there"
        sign = biz_name or "the team"

        draft = (
            f"Hi {name.split()[0] if name else 'there'},\n\n"
            f"Thank you for your email about \"{subject}\".\n\n"
        )
        if snippet:
            draft += f"I read your note: \"{snippet[:180]}...\"\n\n"
        draft += (
            "[Personalize this reply before sending.]\n\n"
            f"Best regards,\n{sign}"
        )

        await _add_to_queue(
            db,
            uid,
            "zilo_email",
            "send_email",
            f"Email reply: {subject[:50]}",
            draft,
            {
                "thread_id": thread_id,
                "message_id": str(msg.get("_id", "")),
                "from_addr": from_addr,
                "subject": subject,
                "snippet": snippet[:300],
                "channel": "email",
                "review_only": True,
            },
        )
        drafted += 1

    logger.info("[zilo] email sync uid=%s drafted=%d sync=%s", uid, drafted, sync_result)
    return {"sync": sync_result, "drafts_queued": drafted}
