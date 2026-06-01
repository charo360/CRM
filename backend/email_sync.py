"""
email_sync.py — Store emails in MongoDB for instant loading and full control.

Collections:
  email_threads  — one doc per conversation thread per user
  email_messages — one doc per email message per user

Sync flow:
  1. Fetch from Gmail (Composio) or Outlook (Nango)
  2. Strip quoted replies, upsert into MongoDB
  3. Frontend reads from DB (instant) instead of hitting Gmail every time
"""
from __future__ import annotations

import html as _html
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ACTIVE_SYNCS: set[str] = set()

# ── Quote stripping ────────────────────────────────────────────────────────────

def strip_quoted_reply(text: str) -> str:
    """Strip Gmail/Outlook quoted reply chains from a plain-text email body."""
    if not text:
        return text

    # Gmail inline quote: "On Mon, Jan 1, 2026, 9:00 PM Name wrote:"
    cleaned = re.sub(
        r"\s*On [A-Za-z]{2,9},?\s+[A-Za-z]{2,9}\.?\s+\d{1,2},?\s+\d{4}[\s\S]*?wrote:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    # Outlook: "-----Original Message-----"
    cleaned = re.sub(r"\s*-{3,}\s*original message\s*-{3,}[\s\S]*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*_{5,}[\s\S]*", "", cleaned).strip()

    # Strip "> " quoted lines
    lines = [l for l in cleaned.split("\n") if not l.strip().startswith(">")]
    cleaned = "\n".join(lines).strip()

    # Fallback: if everything stripped, return first line of original
    return cleaned if cleaned else text.split("\n")[0].strip()


def strip_quoted_html(html_body: str) -> str:
    """Strip quoted content from an HTML email body."""
    if not html_body:
        return html_body
    cleaned = re.sub(r"<blockquote[^>]*>[\s\S]*?</blockquote>", "", html_body, flags=re.IGNORECASE)
    cleaned = re.sub(r'<div[^>]*class="[^"]*gmail_quote[^"]*"[^>]*>[\s\S]*', "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<div[^>]*id="[^"]*appendonsend[^"]*"[^>]*>[\s\S]*', "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(<br\s*/?>[\s]*)+$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or html_body


def clean_body(body: str) -> str:
    """Return a clean version of an email body with quoted replies removed."""
    if "<" in body and ">" in body:
        return strip_quoted_html(body)
    return strip_quoted_reply(body)


# ── Shape helpers ──────────────────────────────────────────────────────────────

def _shape_outlook_message(m: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Convert a Microsoft Graph message into our standard format."""
    from_email = (m.get("from") or {}).get("emailAddress", {})
    to_list    = m.get("toRecipients") or []
    to_email   = (to_list[0] if to_list else {}).get("emailAddress", {})
    body_raw   = (m.get("body") or {}).get("content") or m.get("bodyPreview") or ""
    # Strip HTML tags from Outlook HTML bodies for plain text storage
    import re as _re
    body_plain = _re.sub(r"<[^>]+>", " ", body_raw).strip() if "<" in body_raw else body_raw
    thread_id  = m.get("conversationId") or m.get("id", "")
    return {
        "_id":        m.get("id", ""),
        "thread_id":  thread_id,
        "user_id":    user_id,
        "from_addr":  f"{from_email.get('name', '')} <{from_email.get('address', '')}>".strip(" <>"),
        "to_addr":    f"{to_email.get('name', '')} <{to_email.get('address', '')}>".strip(" <>"),
        "subject":    m.get("subject") or "(no subject)",
        "body_raw":   body_raw,
        "body_clean": clean_body(body_plain),
        "date":       m.get("receivedDateTime") or m.get("sentDateTime") or "",
        "is_read":    m.get("isRead", True),
        "provider":   "microsoft",
        "synced_at":  datetime.now(timezone.utc),
    }


def _shape_composio_message(m: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Convert a raw Composio Gmail message into our standard format."""
    raw_body = _html.unescape(str(m.get("messageText") or m.get("preview") or ""))
    return {
        "_id":        m.get("messageId", ""),
        "thread_id":  m.get("threadId") or m.get("messageId", ""),
        "user_id":    user_id,
        "from_addr":  _html.unescape(str(m.get("sender") or "")),
        "to_addr":    _html.unescape(str(m.get("to") or "")),
        "subject":    _html.unescape(str(m.get("subject") or "(no subject)")),
        "body_raw":   raw_body,
        "body_clean": clean_body(raw_body),
        "date":       str(m.get("messageTimestamp") or ""),
        "is_read":    "UNREAD" not in (m.get("labelIds") or []),
        "provider":   "gmail",
        "synced_at":  datetime.now(timezone.utc),
    }


def _shape_thread_from_messages(msgs: list[dict[str, Any]], user_id: str) -> dict[str, Any]:
    """Build a thread summary from a list of messages."""
    first = msgs[0]
    last  = msgs[-1]
    unread_count = sum(1 for m in msgs if not m.get("is_read", True))
    return {
        "_id":             first["thread_id"],
        "user_id":         user_id,
        "subject":         first.get("subject", "(no subject)"),
        "participants":    list({m.get("from_addr", "") for m in msgs} | {m.get("to_addr", "") for m in msgs}),
        "last_message_at": last.get("date", ""),
        "snippet":         last.get("body_clean", "")[:200],
        "unread_count":    unread_count,
        "message_count":   len(msgs),
        "provider":        "gmail",
        "synced_at":       datetime.now(timezone.utc),
    }


# ── Core sync ──────────────────────────────────────────────────────────────────

async def _store_messages(user_id: str, db: Any, raw_msgs: list[dict[str, Any]], pre_shaped: bool = False) -> dict[str, Any]:
    """Upsert a list of messages into MongoDB. Pass pre_shaped=True if already formatted."""
    thread_map: dict[str, list[dict[str, Any]]] = {}
    for m in raw_msgs:
        shaped = m if pre_shaped else _shape_composio_message(m, user_id)
        if not shaped["_id"]:
            continue
        thread_map.setdefault(shaped["thread_id"], []).append(shaped)

    threads_saved = 0
    messages_saved = 0

    for tid, msgs in thread_map.items():
        msgs.sort(key=lambda x: x.get("date") or "")
        for msg in msgs:
            await db.email_messages.update_one(
                {"_id": msg["_id"], "user_id": user_id},
                {"$set": msg},
                upsert=True,
            )
            messages_saved += 1
        thread_doc = _shape_thread_from_messages(msgs, user_id)
        await db.email_threads.update_one(
            {"_id": tid, "user_id": user_id},
            {"$set": thread_doc},
            upsert=True,
        )
        threads_saved += 1

    return {"synced_threads": threads_saved, "synced_messages": messages_saved}


async def _fetch_and_store_batch(
    user_id: str,
    db: Any,
    query: str = "",
    max_results: int = 10,
    max_pages: int = 50,
) -> dict[str, Any]:
    """
    Fetch emails matching the query by paginating through results up to max_pages.
    Each page requests max_results (default 10) to stay under Composio's payload limit.
    Keeps fetching next pages until no more results.
    """
    try:
        from composio_service import execute_action, ACTION_GMAIL_FETCH
    except ImportError:
        return {"error": "composio_service not available"}

    import asyncio as _asyncio

    total_threads = 0
    total_messages = 0
    page_token: Optional[str] = None
    page = 0

    while page < max_pages:
        params: dict[str, Any] = {"max_results": max_results}
        if query:
            params["query"] = query
        if page_token:
            params["page_token"] = page_token

        result = await execute_action(user_id, ACTION_GMAIL_FETCH, params)

        if "error" in result:
            # If first page fails, report error; otherwise stop gracefully
            if page == 0:
                return {"error": result["error"]}
            break

        data = result.get("data", {})
        raw_msgs = data.get("messages", [])

        if not raw_msgs:
            break  # no more emails

        saved = await _store_messages(user_id, db, raw_msgs)
        total_threads  += saved["synced_threads"]
        total_messages += saved["synced_messages"]

        # Check for next page token (Composio may return it under different keys)
        next_token = (
            data.get("next_page_token")
            or data.get("nextPageToken")
            or data.get("next_token")
            or result.get("data", {}).get("next_page_token")
        )

        if not next_token or len(raw_msgs) < max_results:
            # No more pages or last page was partial
            break

        page_token = next_token
        page += 1
        await _asyncio.sleep(0.5)  # brief pause between pages

    return {"synced_threads": total_threads, "synced_messages": total_messages}


async def sync_emails_for_user(
    user_id: str,
    db: Any,
    max_results: int = 10,
    trigger_briefing_ingest: bool = False,
) -> dict[str, Any]:
    """
    Quick sync — fetch the most recent inbox/important emails from ALL connected providers.
    Gmail: via Composio. Outlook: via Composio.
    """
    if user_id in _ACTIVE_SYNCS:
        logger.info("[email_sync] Sync already in progress for user %s, skipping", user_id)
        return {"synced_threads": 0, "synced_messages": 0, "status": "already_syncing"}

    _ACTIVE_SYNCS.add(user_id)
    try:
        total_threads = 0
        total_messages = 0

        # Gmail sync (quick sync limited to 1 page)
        gmail_query = "in:inbox -category:promotions -category:social -category:updates -category:forums"
        gmail_result = await _fetch_and_store_batch(user_id, db, query=gmail_query, max_results=max_results, max_pages=1)
        if "error" not in gmail_result:
            total_threads  += gmail_result.get("synced_threads", 0)
            total_messages += gmail_result.get("synced_messages", 0)

        # Outlook sync via Composio
        outlook_result = await _fetch_and_store_outlook_batch(user_id, db, max_results=max_results)
        if "error" not in outlook_result:
            total_threads  += outlook_result.get("synced_threads", 0)
            total_messages += outlook_result.get("synced_messages", 0)

        result = {"synced_threads": total_threads, "synced_messages": total_messages}
        logger.info("[email_sync] quick sync user=%s → %s", user_id, result)

        if total_messages > 0 and trigger_briefing_ingest:
            try:
                import asyncio as _asyncio
                from rex.integrations.briefing_refresh import ingest_crm_signals_for_user_id
                _asyncio.create_task(ingest_crm_signals_for_user_id(db, user_id))
            except Exception as e:
                logger.warning("[zilo] schedule briefing ingest after sync: %s", e)

        # Auto-classify new email contacts after sync
        if total_messages > 0:
            try:
                from email_classifier import get_email_classifier
                classifier = get_email_classifier(db)
                classify_result = await classifier.classify_new_emails(user_id)
                result["contacts_classified"] = classify_result.get("classified", 0)
                result["contacts_created"] = classify_result.get("created", 0)
                result["contacts_updated"] = classify_result.get("updated", 0)
            except Exception as e:
                logger.warning("[email_sync] classification failed for user %s: %s", user_id, e)

        return result
    finally:
        _ACTIVE_SYNCS.discard(user_id)


async def _fetch_and_store_outlook_batch(
    user_id: str,
    db: Any,
    max_results: int = 10,
    received_after: str = "",
    received_before: str = "",
) -> dict[str, Any]:
    """Fetch Outlook inbox emails via Composio and store in MongoDB."""
    try:
        from composio_service import execute_action, ACTION_OUTLOOK_FETCH, get_connection_status, TOOLKIT_OUTLOOK
    except ImportError:
        return {"error": "composio_service not available"}

    status = await get_connection_status(user_id, TOOLKIT_OUTLOOK)
    if not status.get("connected"):
        return {"synced_threads": 0, "synced_messages": 0}

    params: dict[str, Any] = {
        "top":     max_results,
        "orderby": "receivedDateTime desc",
    }
    if received_after:
        params["received_date_time_ge"] = received_after
    if received_before:
        params["received_date_time_le"] = received_before

    result = await execute_action(user_id, ACTION_OUTLOOK_FETCH, params)
    if "error" in result:
        logger.warning("[email_sync] Outlook fetch error for user %s: %s", user_id, result["error"])
        return {"synced_threads": 0, "synced_messages": 0}

    data = result.get("data", {})
    # Composio wraps Graph API response under response_data
    response_data = data.get("response_data", data)
    raw_msgs = (
        response_data.get("value")
        or data.get("messages")
        or data.get("emails")
        or (data if isinstance(data, list) else [])
    )
    if not raw_msgs:
        return {"synced_threads": 0, "synced_messages": 0}

    shaped = [_shape_outlook_message(m, user_id) for m in raw_msgs if m.get("id")]
    return await _store_messages(user_id, db, shaped, pre_shaped=True)


async def deep_sync_user(user_id: str, db: Any) -> None:
    """
    Full historical sync — fetches inbox + important emails DAY BY DAY for the last 1 year.
    Excludes: promotions, social, updates, forums (noise categories).
    Each day = 1 API call, max 10 emails/day, 2s pause → ~12 min for 1 year.
    """
    import asyncio as _asyncio
    from datetime import date, timedelta

    # Gmail filter: only real inbox/important, skip promotional noise
    BASE_FILTER = "in:inbox -category:promotions -category:social -category:updates -category:forums"

    await ensure_indexes(db)
    total_threads = 0
    total_messages = 0

    today = date.today()
    one_year_ago = today - timedelta(days=365)

    # Build list of daily windows (newest first)
    days: list[date] = []
    d = today
    while d >= one_year_ago:
        days.append(d)
        d -= timedelta(days=1)

    total_days = len(days)
    for i, day in enumerate(days):
        tomorrow = day + timedelta(days=1)
        after  = f"{day.year}/{day.month}/{day.day}"
        before = f"{tomorrow.year}/{tomorrow.month}/{tomorrow.day}"
        query  = f"{BASE_FILTER} after:{after} before:{before}"

        result = await _fetch_and_store_batch(user_id, db, query=query, max_results=10)
        if "error" in result:
            # Silently skip days with errors (network blip, etc.)
            await _asyncio.sleep(3)
            continue

        batch_threads = result.get("synced_threads", 0)
        total_threads  += batch_threads
        total_messages += result.get("synced_messages", 0)

        # Update progress every 7 days
        if i % 7 == 0 or i == total_days - 1:
            await db.email_sync_status.update_one(
                {"user_id": user_id},
                {"$set": {
                    "last_week_synced": after,
                    "total_threads":    total_threads,
                    "total_messages":   total_messages,
                    "status":           "running",
                    "progress_pct":     round((i + 1) / total_days * 100),
                    "updated_at":       datetime.now(timezone.utc),
                }},
                upsert=True,
            )

        await _asyncio.sleep(4)  # gentle rate limiting — 4s keeps backend responsive

    await db.email_sync_status.update_one(
        {"user_id": user_id},
        {"$set": {
            "status":       "complete",
            "completed_at": datetime.now(timezone.utc),
            "progress_pct": 100,
        }},
        upsert=True,
    )
    logger.info("[email_sync] deep_sync COMPLETE user=%s %d threads %d messages", user_id, total_threads, total_messages)

    # Auto-classify historical email contacts after deep sync complete
    if total_messages > 0:
        try:
            from email_classifier import get_email_classifier
            classifier = get_email_classifier(db)
            classify_result = await classifier.classify_new_emails(user_id)
            logger.info("[email_sync] deep_sync contact classification complete user=%s: %s", user_id, classify_result)
        except Exception as e:
            logger.warning("[email_sync] classification failed after deep sync for user %s: %s", user_id, e)



# ── DB read helpers ────────────────────────────────────────────────────────────

async def get_threads_from_db(
    user_id: str,
    db: Any,
    q: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List email threads from MongoDB, newest first."""
    flt: dict[str, Any] = {"user_id": user_id}
    if q:
        flt["$or"] = [
            {"subject":    {"$regex": q, "$options": "i"}},
            {"snippet":    {"$regex": q, "$options": "i"}},
            {"participants": {"$regex": q, "$options": "i"}},
        ]
    cursor = db.email_threads.find(flt).sort("last_message_at", -1).skip(offset).limit(limit)
    threads = await cursor.to_list(limit)
    return [_fmt_thread(t) for t in threads]


async def get_messages_from_db(
    user_id: str,
    thread_id: str,
    db: Any,
) -> list[dict[str, Any]]:
    """Get all messages for a thread from MongoDB, oldest-first."""
    cursor = db.email_messages.find({"user_id": user_id, "thread_id": thread_id}).sort("date", 1)
    msgs = await cursor.to_list(200)
    return [_fmt_message(m) for m in msgs]


async def mark_thread_read(user_id: str, thread_id: str, db: Any) -> None:
    """Mark all messages in a thread as read."""
    await db.email_messages.update_many(
        {"user_id": user_id, "thread_id": thread_id},
        {"$set": {"is_read": True}},
    )
    await db.email_threads.update_one(
        {"_id": thread_id, "user_id": user_id},
        {"$set": {"unread_count": 0}},
    )


async def save_sent_message(
    user_id: str,
    thread_id: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    db: Any,
) -> None:
    """Save a sent email to the DB immediately so it appears in the thread."""
    import uuid
    msg_id = f"sent_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc).isoformat()
    msg: dict[str, Any] = {
        "_id":        msg_id,
        "thread_id":  thread_id,
        "user_id":    user_id,
        "from_addr":  from_addr,
        "to_addr":    to_addr,
        "subject":    subject,
        "body_raw":   body,
        "body_clean": body,
        "date":       now,
        "is_read":    True,
        "is_outgoing": True,
        "provider":   "gmail",
        "synced_at":  datetime.now(timezone.utc),
    }
    await db.email_messages.insert_one(msg)
    # Update thread's last message
    await db.email_threads.update_one(
        {"_id": thread_id, "user_id": user_id},
        {"$set": {"last_message_at": now, "snippet": body[:200]}, "$inc": {"message_count": 1}},
    )


async def ensure_indexes(db: Any) -> None:
    """Create indexes for the email collections."""
    try:
        await db.email_threads.create_index([("user_id", 1), ("last_message_at", -1)])
        await db.email_threads.create_index([("user_id", 1), ("subject", "text"), ("snippet", "text")])
        await db.email_messages.create_index([("user_id", 1), ("thread_id", 1), ("date", 1)])
        await db.email_messages.create_index([("user_id", 1), ("contact_classified", 1)])
        await db.email_messages.create_index([("user_id", 1), ("contact_classified", 1), ("date", -1)])
        await db.customers.create_index([("user_id", 1), ("email", 1)])
        await db.pending_email_classifications.create_index([("user_id", 1), ("status", 1)])
    except Exception as e:
        logger.warning("[email_sync] index creation failed: %s", e)


# ── Format for API response ────────────────────────────────────────────────────

def _fmt_thread(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "id":              t["_id"],
        "subject":         t.get("subject", "(no subject)"),
        "from":            (t.get("participants") or [""])[0],
        "date":            t.get("last_message_at", ""),
        "snippet":         t.get("snippet", ""),
        "unread":          (t.get("unread_count") or 0) > 0,
        "messageCount":    t.get("message_count", 1),
        "provider":        t.get("provider", "gmail"),
        "synced_at":       t.get("synced_at", "").isoformat() if isinstance(t.get("synced_at"), datetime) else str(t.get("synced_at", "")),
    }


def _fmt_message(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id":         m["_id"],
        "from":       m.get("from_addr", ""),
        "to":         m.get("to_addr", ""),
        "subject":    m.get("subject", ""),
        "date":       m.get("date", ""),
        "body":       m.get("body_clean") or m.get("body_raw", ""),
        "body_raw":   m.get("body_raw", ""),
        "unread":     not m.get("is_read", True),
        "is_outgoing": m.get("is_outgoing", False),
    }
