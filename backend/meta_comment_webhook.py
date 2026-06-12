"""Parse Meta (Facebook Page) comment webhooks and run comment auto-reply."""
from __future__ import annotations

import logging
from typing import Any, Dict

from composio_service import get_connection_status
from social_comment_autoreply import handle_comment_event

logger = logging.getLogger(__name__)


async def _user_for_page(db, page_id: str) -> Dict[str, Any] | None:
    if not page_id:
        return None
    user = await db.users.find_one({"meta_connections.page_id": page_id})
    if user:
        return user
    user = await db.meta_connections.find_one({"page_id": page_id})
    if user and user.get("user_id"):
        return await db.users.find_one({"_id": user["user_id"]})
    return await db.users.find_one({"settings.facebook_page_id": page_id})


async def process_meta_page_comment_webhook(db, body: dict) -> int:
    """
    Meta Page webhook: entry[].changes[] where field=feed and value.item=comment.

    Configure in Meta Developer Console → Webhooks → Page → feed.
    Uses the same auto-reply settings as Social Inbox → Comments.
    """
    if body.get("object") != "page":
        return 0

    handled = 0
    for entry in body.get("entry") or []:
        page_id = str(entry.get("id") or "")
        user = await _user_for_page(db, page_id)
        if not user:
            logger.warning("[MetaComments] no user for page %s", page_id)
            continue

        business_id = str(user.get("business_id") or user["_id"])
        status = await get_connection_status(business_id, "facebook")
        account_id = str(status.get("connection_id") or "")

        for change in entry.get("changes") or []:
            if str(change.get("field") or "") != "feed":
                continue
            value = change.get("value") or {}
            if str(value.get("item") or "") != "comment":
                continue
            if str(value.get("verb") or "add") != "add":
                continue

            comment_id = str(value.get("comment_id") or value.get("id") or "")
            post_id = str(value.get("post_id") or value.get("parent_id") or "")
            text = str(value.get("message") or "").strip()
            from_obj = value.get("from") or {}
            author = str(from_obj.get("name") or from_obj.get("id") or "")
            if from_obj.get("id") == page_id:
                continue
            if not comment_id or not post_id or not text:
                continue

            event = {
                "post_id": post_id,
                "comment_id": comment_id,
                "comment_text": text,
                "account_id": account_id,
                "author_name": author,
                "reply_count": 0,
                "platform": "facebook",
                "post_caption": "",
            }
            try:
                if await handle_comment_event(db, user, event):
                    handled += 1
            except Exception as exc:
                logger.warning("[MetaComments] handle failed: %s", exc)

    return handled
