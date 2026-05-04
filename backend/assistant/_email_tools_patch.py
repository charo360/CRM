"""Email tools patch — appended to tools.py during build.
This file is not imported directly; its contents are appended to tools.py.
"""

# ── Email helpers ─────────────────────────────────────────────────────────────

import base64
import os as _os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_GMAIL_KEY     = _os.getenv("NEXT_PUBLIC_NANGO_ID_EMAIL",     "google-mail")
_MICROSOFT_KEY = _os.getenv("NEXT_PUBLIC_NANGO_ID_MICROSOFT", "microsoft")


def _gmail_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _gmail_decode_part(payload: dict, prefer: str = "text/plain") -> str:
    body_data = (payload.get("body") or {}).get("data", "")
    if body_data and payload.get("mimeType", "") == prefer:
        try:
            return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        except Exception:
            return ""
    for part in payload.get("parts") or []:
        text = _gmail_decode_part(part, prefer)
        if text:
            return text
    if prefer == "text/plain":
        return _gmail_decode_part(payload, "text/html")
    return ""


def _gmail_build_raw(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    in_reply_to: str = "",
    references: str = "",
) -> str:
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _email_trunc(text: str, n: int = 3000) -> str:
    return text[:n] + ("..." if len(text) > n else "")


# ── Gmail tools ───────────────────────────────────────────────────────────────

@tool(
    name="gmail_list_threads",
    description=(
        "List Gmail inbox threads. Supports search queries like "
        "'from:someone@email.com', 'is:unread', 'subject:invoice'. "
        "Returns thread summaries: id, subject, snippet, sender, date, unread flag."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query":       {"type": "string", "description": "Gmail search query. Default: 'in:inbox'"},
            "max_results": {"type": "integer", "description": "Max threads (1-50, default 15)"},
            "unread_only": {"type": "boolean", "description": "Add 'is:unread' to query if true"},
        },
    },
)
async def gmail_list_threads(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    q = (args.get("query") or "in:inbox").strip()
    if args.get("unread_only"):
        q = "is:unread " + q
    limit = min(int(args.get("max_results") or 15), 50)
    try:
        data = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "GET",
            "gmail/v1/users/me/threads",
            params={"q": q, "maxResults": limit},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    threads = []
    for t in (data.get("threads") or [])[:limit]:
        try:
            td = await nango_proxy(
                ctx.business_id, _GMAIL_KEY, "GET",
                f"gmail/v1/users/me/threads/{t['id']}",
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            msgs = td.get("messages") or []
            if not msgs:
                continue
            first = msgs[0]
            hdrs = (first.get("payload") or {}).get("headers") or []
            threads.append({
                "thread_id":     t["id"],
                "message_count": len(msgs),
                "subject":       _gmail_header(hdrs, "Subject") or "(no subject)",
                "from":          _gmail_header(hdrs, "From"),
                "date":          _gmail_header(hdrs, "Date"),
                "snippet":       _email_trunc(td.get("snippet") or "", 200),
                "unread":        "UNREAD" in (first.get("labelIds") or []),
            })
        except Exception:
            continue
    return {"threads": threads, "total": len(threads), "query": q}


@tool(
    name="gmail_read_thread",
    description=(
        "Read a full Gmail thread by thread_id. Returns all messages "
        "with decoded body, sender, date, and subject."
    ),
    parameters={
        "type": "object",
        "properties": {
            "thread_id": {"type": "string", "description": "Gmail thread ID"},
        },
        "required": ["thread_id"],
    },
)
async def gmail_read_thread(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    thread_id = (args.get("thread_id") or "").strip()
    if not thread_id:
        return {"error": "thread_id is required"}
    try:
        data = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "GET",
            f"gmail/v1/users/me/threads/{thread_id}",
            params={"format": "full"},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    messages = []
    for msg in data.get("messages") or []:
        payload = msg.get("payload") or {}
        hdrs = payload.get("headers") or []
        messages.append({
            "message_id":         msg["id"],
            "from":               _gmail_header(hdrs, "From"),
            "to":                 _gmail_header(hdrs, "To"),
            "subject":            _gmail_header(hdrs, "Subject"),
            "date":               _gmail_header(hdrs, "Date"),
            "message_id_header":  _gmail_header(hdrs, "Message-ID"),
            "references":         _gmail_header(hdrs, "References"),
            "body":               _email_trunc(_gmail_decode_part(payload), 4000),
            "unread":             "UNREAD" in (msg.get("labelIds") or []),
        })
    return {"thread_id": thread_id, "message_count": len(messages), "messages": messages}


@tool(
    name="gmail_send",
    description="Send a new email via Gmail. Requires to, subject, and body. cc and bcc are optional.",
    parameters={
        "type": "object",
        "properties": {
            "to":      {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Subject line"},
            "body":    {"type": "string", "description": "Plain text email body"},
            "cc":      {"type": "string"},
            "bcc":     {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    destructive=True,
)
async def gmail_send(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject or not body:
        return {"error": "to, subject, and body are required"}
    raw = _gmail_build_raw(to, subject, body, cc=args.get("cc") or "", bcc=args.get("bcc") or "")
    try:
        result = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "POST",
            "gmail/v1/users/me/messages/send",
            json={"raw": raw},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "sent", "message_id": result.get("id"), "thread_id": result.get("threadId")}


@tool(
    name="gmail_reply",
    description=(
        "Reply to an existing Gmail thread. Automatically threads correctly. "
        "Set reply_all=true to include all original recipients."
    ),
    parameters={
        "type": "object",
        "properties": {
            "thread_id": {"type": "string", "description": "Gmail thread ID to reply to"},
            "body":      {"type": "string", "description": "Reply body text"},
            "reply_all": {"type": "boolean", "description": "Reply all. Default false."},
        },
        "required": ["thread_id", "body"],
    },
    destructive=True,
)
async def gmail_reply(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    thread_id = (args.get("thread_id") or "").strip()
    body = (args.get("body") or "").strip()
    if not thread_id or not body:
        return {"error": "thread_id and body are required"}
    try:
        td = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "GET",
            f"gmail/v1/users/me/threads/{thread_id}",
            params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Message-ID", "References"]},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    msgs = td.get("messages") or []
    if not msgs:
        return {"error": "Thread not found or empty"}
    last = msgs[-1]
    hdrs = (last.get("payload") or {}).get("headers") or []
    orig_from   = _gmail_header(hdrs, "From")
    orig_to     = _gmail_header(hdrs, "To")
    subject     = _gmail_header(hdrs, "Subject")
    msg_id_hdr  = _gmail_header(hdrs, "Message-ID")
    existing_refs = _gmail_header(hdrs, "References")
    reply_to = orig_from
    if args.get("reply_all") and orig_to:
        reply_to = f"{orig_from}, {orig_to}"
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    refs = (existing_refs + " " + msg_id_hdr).strip() if existing_refs else msg_id_hdr
    raw = _gmail_build_raw(reply_to, subject, body, in_reply_to=msg_id_hdr, references=refs)
    try:
        result = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "POST",
            "gmail/v1/users/me/messages/send",
            json={"raw": raw, "threadId": thread_id},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "sent", "message_id": result.get("id"), "thread_id": result.get("threadId")}


@tool(
    name="gmail_draft",
    description="Save a Gmail draft without sending. Returns the draft ID.",
    parameters={
        "type": "object",
        "properties": {
            "to":      {"type": "string"},
            "subject": {"type": "string"},
            "body":    {"type": "string"},
            "cc":      {"type": "string"},
            "bcc":     {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
)
async def gmail_draft(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject or not body:
        return {"error": "to, subject, and body are required"}
    raw = _gmail_build_raw(to, subject, body, cc=args.get("cc") or "", bcc=args.get("bcc") or "")
    try:
        result = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "POST",
            "gmail/v1/users/me/drafts",
            json={"message": {"raw": raw}},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "draft_saved", "draft_id": result.get("id")}


# ── Outlook / Microsoft 365 tools ─────────────────────────────────────────────

_OUTLOOK_SELECT      = "id,subject,from,toRecipients,ccRecipients,bodyPreview,receivedDateTime,isRead,conversationId,internetMessageId"
_OUTLOOK_FULL_SELECT = "id,subject,from,toRecipients,ccRecipients,body,receivedDateTime,isRead,conversationId,internetMessageId"


def _ms_addr_list(val: str) -> list:
    return [{"emailAddress": {"address": a.strip()}} for a in (val or "").split(",") if a.strip()]


@tool(
    name="outlook_list_messages",
    description=(
        "List Outlook / Microsoft 365 inbox messages. "
        "Filter by folder, unread status, or search term. "
        "Returns: id, subject, from, preview, date, read status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "folder":      {"type": "string", "description": "inbox (default), sentItems, drafts, deletedItems"},
            "search":      {"type": "string", "description": "Search subject or body"},
            "unread_only": {"type": "boolean"},
            "max_results": {"type": "integer", "description": "1-50, default 15"},
        },
    },
)
async def outlook_list_messages(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    folder = (args.get("folder") or "inbox").strip()
    limit  = min(int(args.get("max_results") or 15), 50)
    params: Dict[str, Any] = {
        "$top":     limit,
        "$select":  _OUTLOOK_SELECT,
        "$orderby": "receivedDateTime desc",
    }
    if args.get("unread_only"):
        params["$filter"] = "isRead eq false"
    if args.get("search"):
        params["$search"] = f'"{args["search"]}"'
    try:
        data = await nango_proxy(
            ctx.business_id, _MICROSOFT_KEY, "GET",
            f"v1.0/me/mailFolders/{folder}/messages",
            params=params,
        )
    except RuntimeError as e:
        return {"error": str(e)}
    messages = []
    for m in (data.get("value") or []):
        sender = (m.get("from") or {}).get("emailAddress") or {}
        messages.append({
            "message_id":    m.get("id"),
            "subject":       m.get("subject") or "(no subject)",
            "from_name":     sender.get("name"),
            "from_email":    sender.get("address"),
            "preview":       _email_trunc(m.get("bodyPreview") or "", 200),
            "date":          m.get("receivedDateTime"),
            "is_read":       m.get("isRead", True),
            "conversation_id": m.get("conversationId"),
        })
    return {"messages": messages, "total": len(messages)}


@tool(
    name="outlook_read_message",
    description="Read the full body and details of an Outlook message by message_id.",
    parameters={
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "Outlook message ID"},
        },
        "required": ["message_id"],
    },
)
async def outlook_read_message(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    msg_id = (args.get("message_id") or "").strip()
    if not msg_id:
        return {"error": "message_id is required"}
    try:
        m = await nango_proxy(
            ctx.business_id, _MICROSOFT_KEY, "GET",
            f"v1.0/me/messages/{msg_id}",
            params={"$select": _OUTLOOK_FULL_SELECT},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    sender = (m.get("from") or {}).get("emailAddress") or {}
    to_list = [(r.get("emailAddress") or {}).get("address") for r in (m.get("toRecipients") or [])]
    body_content = _email_trunc((m.get("body") or {}).get("content") or m.get("bodyPreview") or "", 4000)
    return {
        "message_id":    m.get("id"),
        "subject":       m.get("subject") or "(no subject)",
        "from_name":     sender.get("name"),
        "from_email":    sender.get("address"),
        "to":            ", ".join(filter(None, to_list)),
        "date":          m.get("receivedDateTime"),
        "is_read":       m.get("isRead", True),
        "body":          body_content,
        "internet_message_id": m.get("internetMessageId"),
        "conversation_id": m.get("conversationId"),
    }


@tool(
    name="outlook_send",
    description="Send a new email via Outlook / Microsoft 365. to, subject, body required. cc and bcc optional.",
    parameters={
        "type": "object",
        "properties": {
            "to":      {"type": "string", "description": "Recipient(s), comma-separated"},
            "subject": {"type": "string"},
            "body":    {"type": "string", "description": "Plain text body"},
            "cc":      {"type": "string"},
            "bcc":     {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    destructive=True,
)
async def outlook_send(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject or not body:
        return {"error": "to, subject, and body are required"}
    payload: Dict[str, Any] = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": _ms_addr_list(to),
        },
        "saveToSentItems": True,
    }
    if args.get("cc"):
        payload["message"]["ccRecipients"] = _ms_addr_list(args["cc"])
    if args.get("bcc"):
        payload["message"]["bccRecipients"] = _ms_addr_list(args["bcc"])
    try:
        await nango_proxy(ctx.business_id, _MICROSOFT_KEY, "POST", "v1.0/me/sendMail", json=payload)
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "sent"}


@tool(
    name="outlook_reply",
    description="Reply to an Outlook message. Set reply_all=true to reply to all recipients.",
    parameters={
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "Outlook message ID to reply to"},
            "body":       {"type": "string", "description": "Reply body text"},
            "reply_all":  {"type": "boolean", "description": "Reply all. Default false."},
        },
        "required": ["message_id", "body"],
    },
    destructive=True,
)
async def outlook_reply(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    msg_id    = (args.get("message_id") or "").strip()
    body      = (args.get("body") or "").strip()
    reply_all = bool(args.get("reply_all"))
    if not msg_id or not body:
        return {"error": "message_id and body are required"}
    endpoint = f"v1.0/me/messages/{msg_id}/{'replyAll' if reply_all else 'reply'}"
    try:
        await nango_proxy(ctx.business_id, _MICROSOFT_KEY, "POST", endpoint, json={"comment": body})
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "replied"}


@tool(
    name="outlook_draft",
    description="Save a draft email in Outlook without sending. Returns the draft message_id.",
    parameters={
        "type": "object",
        "properties": {
            "to":      {"type": "string"},
            "subject": {"type": "string"},
            "body":    {"type": "string"},
            "cc":      {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
)
async def outlook_draft(ctx: ToolContext, args: Dict[str, Any]):
    from .composio_helper import composio_proxy as nango_proxy
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject or not body:
        return {"error": "to, subject, and body are required"}
    payload: Dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": _ms_addr_list(to),
    }
    if args.get("cc"):
        payload["ccRecipients"] = _ms_addr_list(args["cc"])
    try:
        result = await nango_proxy(ctx.business_id, _MICROSOFT_KEY, "POST", "v1.0/me/messages", json=payload)
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "draft_saved", "message_id": result.get("id")}
