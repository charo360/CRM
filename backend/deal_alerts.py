"""
Deal Alerts — when someone asks for a service you sell:
  1. Push notification + in-app queue with link
  2. Draft reply ready to approve
  3. On approve (or auto mode): reply via Composio when IDs are available
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Phrases that signal someone is looking to buy / hire
BUY_INTENT_PHRASES = (
    "looking for",
    "need a ",
    "need an ",
    "need ",
    "need someone",
    "anyone know",
    "anyone recommend",
    "can anyone recommend",
    "who can",
    "where can i find",
    "recommend a",
    "recommendation for",
    "hire a",
    "hiring a",
    "searching for",
    "want to buy",
    "want a ",
    "please recommend",
    "suggest a",
    "best place for",
    "how much for",
    "quote for",
)


def detect_buy_intent(
    text: str,
    keywords: Optional[List[str]] = None,
    business_type: str = "",
) -> bool:
    """True if the message looks like someone seeking a product/service."""
    if not text or len(text.strip()) < 8:
        return False
    lower = text.lower()

    if any(p in lower for p in BUY_INTENT_PHRASES):
        return True

    for kw in keywords or []:
        k = (kw or "").lower().strip()
        if k and k in lower:
            return True

    bt = (business_type or "").lower().strip()
    if bt and len(bt) > 2 and bt in lower:
        if any(w in lower for w in ("need", "want", "looking", "recommend", "hire", "find")):
            return True

    return False


async def _send_push(db, user_id: str, title: str, body: str, data: Optional[Dict] = None) -> None:
    user = await db.users.find_one({"_id": user_id})
    if not user:
        return
    tokens = [
        t for t in (user.get("push_tokens") or [])
        if t and (str(t).startswith("ExponentPushToken") or str(t).startswith("ExpoPushToken"))
    ]
    if not tokens:
        return
    messages = [
        {"to": t, "title": title, "body": body[:240], "data": data or {}, "sound": "default", "priority": "high"}
        for t in tokens
    ]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=messages,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
    except Exception as e:
        logger.warning("[deal_alerts] push failed user=%s: %s", user_id, e)


async def reply_composio_comment(
    db,
    user_id: str,
    post_id: str,
    account_id: str,
    comment_id: str,
    message: str,
    *,
    platform: str = "",
) -> bool:
    if not (post_id and account_id and comment_id and message):
        return False
    user = await db.users.find_one({"_id": user_id})
    if not user:
        return False
    try:
        from social_composio_engagement import reply_to_comment

        result = await reply_to_comment(
            db,
            user,
            post_id,
            account_id,
            comment_id,
            message[:900],
            platform=platform,
        )
        if result.get("error"):
            logger.warning("[deal_alerts] composio reply: %s", result["error"])
            return False
        return bool(result.get("success"))
    except Exception as e:
        logger.warning("[deal_alerts] composio reply error: %s", e)
    return False


async def reply_zernio_comment(
    post_id: str,
    account_id: str,
    comment_id: str,
    message: str,
) -> bool:
    """Deprecated — Zernio comment replies removed."""
    logger.warning("[deal_alerts] reply_zernio_comment is deprecated")
    return False


async def _get_deal_settings(db, user_id: str) -> Dict[str, Any]:
    social = await db.action_mode_social.find_one({"user_id": user_id}) or {}
    mode = social.get("deal_mode") or social.get("mode") or "review"
    # review = notify + approve before reply | auto = reply immediately | notify = link only
    if mode == "auto":
        deal_mode = "auto_reply"
    elif mode == "notify":
        deal_mode = "notify_only"
    else:
        deal_mode = "review"
    return {
        "deal_mode": deal_mode,
        "notify_push": social.get("notify_push", True),
        "keywords": social.get("keywords") or [],
        "location": social.get("location") or "",
    }


async def queue_deal_alert(
    db,
    user_id: str,
    *,
    text: str,
    author: str = "Someone",
    platform: str = "social",
    url: str = "",
    source: str = "monitor",
    group_name: str = "",
    post_id: str = "",
    comment_id: str = "",
    account_id: str = "",
    conversation_id: str = "",
    force: bool = False,
) -> bool:
    """
    Core deal alert pipeline. Returns True if an alert was created.
    """
    from action_mode_routes import _draft_contextual_comment, _log_activity

    cfg = await _get_deal_settings(db, user_id)
    biz = await db.users.find_one({"_id": user_id}) or {}
    biz_name = biz.get("business_name", "") or biz.get("name", "")
    biz_type = biz.get("business_type", "") or biz.get("industry", "")

    keywords = cfg["keywords"]
    if not keywords and biz_type:
        keywords = [biz_type]

    if not detect_buy_intent(text, keywords, biz_type):
        return False

    dedup_key = comment_id or conversation_id or url or text[:80]
    if dedup_key:
        existing = await db.action_mode_queue.find_one({
            "user_id": user_id,
            "metadata.dedup_key": dedup_key,
        })
        if existing:
            return False

    location = cfg["location"]
    matched_kw = next((k for k in keywords if k.lower() in text.lower()), biz_type or "service")
    draft = _draft_contextual_comment(biz_name, biz_type, text, matched_kw, location)

    deal_mode = cfg["deal_mode"]
    can_zernio_reply = bool(post_id and comment_id and account_id)
    auto_send = deal_mode == "auto_reply" and can_zernio_reply

    item_id = str(uuid.uuid4())
    meta: Dict[str, Any] = {
        "url": url,
        "platform": platform,
        "snippet": text[:300],
        "keyword": matched_kw,
        "author": author,
        "group_name": group_name or platform,
        "source": source,
        "dedup_key": dedup_key,
        "post_id": post_id,
        "comment_id": comment_id,
        "account_id": account_id,
        "conversation_id": conversation_id,
        "can_reply": can_zernio_reply,
    }

    status = "approved" if auto_send else "pending"
    if deal_mode == "notify_only":
        status = "skipped"

    await db.action_mode_queue.insert_one({
        "_id": item_id,
        "user_id": user_id,
        "agent": "deal_alert",
        "action_type": "post_comment",
        "title": f"🎯 {author}: {text[:55]}",
        "draft_content": draft,
        "metadata": meta,
        "status": status,
        "posted": False,
        "created_at": datetime.utcnow(),
    })

    opp_id = str(uuid.uuid4())
    await db.action_mode_opportunities.insert_one({
        "_id": opp_id,
        "user_id": user_id,
        "kind": "social",
        "agent": "deal_alert",
        "agent_name": "Deal Alert",
        "title": f"{author} needs {matched_kw}",
        "url": url,
        "snippet": text[:300],
        "score": 9,
        "queue_id": item_id,
        "created_at": datetime.utcnow(),
    })

    try:
        from delegate.service import notify_opportunity_created
        import asyncio
        opp_doc = {
            "_id": opp_id,
            "user_id": user_id,
            "url": url,
            "snippet": text[:300],
            "title": f"{author} needs {matched_kw}",
            "agent": "deal_alert",
            "created_at": datetime.utcnow(),
        }
        asyncio.create_task(notify_opportunity_created(db, user_id, opp_doc))
    except Exception as e:
        logger.warning(f"[deal_alerts] delegate opportunity hook failed: {e}")

    await db.action_mode_activity.insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "agent": "deal_alert",
        "title": f"🎯 New lead on {platform}",
        "detail": f"{author}: {text[:120]}",
        "kind": "opportunity",
        "created_at": datetime.utcnow(),
    })

    if cfg.get("notify_push", True):
        link_hint = "Open the link in Field Agents to respond."
        if url:
            link_hint = "Tap to open the conversation."
        await _send_push(
            db,
            user_id,
            title=f"🎯 Someone needs {matched_kw}",
            body=f"{author}: {text[:100]}",
            data={
                "type": "deal_alert",
                "queue_id": item_id,
                "url": url,
                "platform": platform,
            },
        )

    if auto_send:
        ok = await reply_composio_comment(
            db,
            user_id,
            post_id,
            account_id,
            comment_id,
            draft,
            platform=platform,
        )
        await db.action_mode_queue.update_one(
            {"_id": item_id},
            {"$set": {"posted": ok, "status": "approved" if ok else "pending"}},
        )
        await _log_activity(
            db, user_id, "deal_alert",
            f"✅ Auto-replied on {platform}" if ok else f"⚠️ Reply failed — check queue",
            draft[:200],
            kind="action",
        )
    else:
        await _log_activity(
            db, user_id, "deal_alert",
            f"🔔 Deal alert — review reply",
            f"{author} on {platform}: {text[:100]}",
            kind="opportunity",
        )

    logger.info("[deal_alerts] queued user=%s platform=%s author=%s", user_id, platform, author)

    # Fire workflow trigger
    try:
        from workflows.engine import fire_trigger
        from workflows.models import WorkflowEvent
        from whatsapp_service import get_whatsapp_service
        ws = get_whatsapp_service(db)
        event = WorkflowEvent(
            trigger_type="social_lead_discovered",
            user_id=user_id,
            from_number="",
            data={
                "lead_author": author,
                "lead_text": text,
                "platform": platform,
                "url": url,
                "keyword": matched_kw,
                "suggested_reply": draft,
            }
        )
        import asyncio
        asyncio.create_task(fire_trigger(db, event, ws))
    except Exception as e:
        logger.warning(f"[deal_alerts] fire_trigger social_lead failed: {e}")

    return True
