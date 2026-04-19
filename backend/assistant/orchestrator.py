"""Agent orchestrator — runs the tool-use loop for one user turn.

High-level flow per turn:
1. Prepend system prompt + conversation history
2. Call the LLM with the tool registry attached
3. If the model returns tool_calls, execute each one (unless destructive and
   not yet user-approved), append tool results as messages, loop.
4. Stop when the model returns a plain content message, or `max_steps` is hit.

Returned shape:
    {
        "reply": "<final assistant text>",
        "steps": [{"tool": str, "arguments": {...}, "result": {...}}],
        "messages_to_append": [...],   # OpenAI-format messages to store in history
        "model": "<model id>",
        "needs_confirmation": None | {"tool": str, "arguments": {...}, "reason": str},
    }
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .documents import build_context_preamble, load_full
from .models import chat_with_tools, resolve_model
from .tools import REGISTRY, ToolContext, openai_tool_specs, run_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are **Zilo Chat**, the in-app AI operator for a small-business CRM.
You help the logged-in business owner manage customers, orders, follow-ups, broadcasts, integrations, and **reference documents** they upload to the conversation.

When documents are attached (PDF, DOCX, TXT, CSV, image), the relevant text or image is placed in a system preamble or attached natively as a content block. You can read, summarize, extract data from, or answer questions about them. Always cite the filename when quoting or paraphrasing.

# How to work
- Prefer calling tools over guessing. Never invent customer names, phone numbers, order IDs, or stats.
- If the user asks a question whose answer requires data, call the relevant `list_*` / `get_*` tool first.
- Before any destructive action (sending a WhatsApp message, broadcasting, creating records, disconnecting a channel), briefly restate what you will do in plain English and wait for the user to confirm unless they already said "yes / do it / send".
- If a tool returns an error, explain it plainly and suggest a next step. Do not keep retrying the same call.

# How to present results — write like a business briefing, not a chat
Every reply must read like a short, polished document an executive would skim. Structure:

1. **Headline (H3)** — one line summarizing what you're reporting, e.g. `### Follow-ups due this week (3)` or `### Today's snapshot`.
2. **Lead sentence** — one short sentence giving the takeaway ("Three customers are waiting on a check-in. Two are overdue.").
3. **Data section** — render lists as a compact Markdown table. Required columns depend on the entity:
   - Follow-ups: `#`, `Customer`, `Phone`, `Due`, `Channel`, `Message`
   - Orders: `#`, `Order`, `Customer`, `Total`, `Status`, `Placed`
   - Customers: `#`, `Name`, `Phone`, `Last contact`, `Tags`
   - Broadcasts: `#`, `Name`, `Audience`, `Sent`, `Delivered`, `Created`
4. **Key observations** (only if useful) — 1–3 bullets calling out anything the user should notice (overdue count, large order, top customer).
5. **Suggested actions** — close with a short line offering 1–2 concrete next steps the user can reply with, e.g. `_Reply **send all** to message every customer in this list, or tell me which row to act on._`

Formatting rules:
- **Never show raw UUIDs** (e.g. `a97bccb5-…`). Always use `customer_name` / `name` from the tool output. If only an ID exists, write "(customer #a97bccb5)" using the first 8 chars.
- Dates must be human-friendly: `today`, `tomorrow`, `Apr 19`, `2 days ago`. Never ISO strings.
- Money: use the currency symbol the tool provides; otherwise just the number with a thousands separator.
- Long message text inside a table cell: show the first ~60 chars followed by `…`.
- If the list has more than 8 items, show the first 8 and finish with `_… and N more — ask to see the rest._`
- If the list is empty, say so in one sentence; do not show an empty table.
- Never include internal fields like `_id`, `user_id`, `tool_call_id`, or bot tokens.
- Tone: calm, concise, professional. No emoji. No exclamation marks. No "Sure!" / "Absolutely!" openers.
"""

MAX_STEPS = 6
AFFIRMATIVE = {"yes", "y", "ok", "okay", "sure", "go", "do it", "send", "confirm", "confirmed", "yep", "yeah"}


async def run_turn(
    *,
    db,
    user: Dict[str, Any],
    history: List[Dict[str, Any]],
    user_message: str,
    model_id: Optional[str] = None,
    auto_approve_destructive: bool = False,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a single conversational turn."""
    ctx = ToolContext(db, user)

    # Load attached documents for this conversation
    attached_docs: List[Dict[str, Any]] = []
    native_attachments: List[Dict[str, Any]] = []
    if conversation_id:
        attached_docs = await load_full(db, ctx.business_id, conversation_id)
        provider = resolve_model(model_id)["provider"]
        if provider == "anthropic":
            for d in attached_docs:
                if d.get("b64") and d.get("kind") in ("image", "pdf"):
                    native_attachments.append({
                        "kind": d["kind"],
                        "mime_type": d.get("mime_type"),
                        "filename": d.get("filename"),
                        "b64": d["b64"],
                    })

    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Append document context (text) as a second system message
    if attached_docs:
        preamble = build_context_preamble(attached_docs)
        if preamble:
            messages.append({"role": "system", "content": preamble})
    # Trim history to last 30 messages
    messages.extend(history[-30:])
    messages.append({"role": "user", "content": user_message})

    steps: List[Dict[str, Any]] = []
    messages_to_append: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]

    # Simple heuristic: if the user's latest message reads as an affirmative confirmation,
    # treat this turn as implicitly approving the *next* destructive tool call.
    is_confirmation_reply = user_message.strip().lower() in AFFIRMATIVE
    approved_destructive = auto_approve_destructive or is_confirmation_reply

    pending_confirmation: Optional[Dict[str, Any]] = None
    model_used = model_id or ""

    for step_idx in range(MAX_STEPS):
        resp = await chat_with_tools(
            messages=messages,
            tools=openai_tool_specs(),
            model_id=model_id,
            # Attach on the first LLM call only — subsequent tool-loop rounds
            # already have the system context and should not re-upload the files.
            attachments=native_attachments if step_idx == 0 else None,
        )
        model_used = resp.get("model", model_used)

        tool_calls = resp.get("tool_calls") or []
        # Echo the assistant message (with any tool_calls) back into the running
        # messages list so the subsequent tool role messages reference the right ids.
        asst_msg = resp.get("raw_assistant_message") or {
            "role": "assistant",
            "content": resp.get("content", ""),
        }
        messages.append(asst_msg)

        if not tool_calls:
            final = resp.get("content", "")
            messages_to_append.append({"role": "assistant", "content": final})
            return {
                "reply": final,
                "steps": steps,
                "messages_to_append": messages_to_append,
                "model": model_used,
                "needs_confirmation": pending_confirmation,
            }

        # Execute tool calls (OpenAI may return multiple in one shot)
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("arguments") or {}
            spec = REGISTRY.get(name)
            if spec and spec.get("destructive") and not approved_destructive:
                pending_confirmation = {
                    "tool": name,
                    "arguments": args,
                    "reason": f"Destructive action `{name}` requires confirmation.",
                }
                # Don't run it — return the plan as assistant text instead.
                preview_text = _describe_destructive(name, args)
                messages_to_append.append({"role": "assistant", "content": preview_text})
                return {
                    "reply": preview_text,
                    "steps": steps,
                    "messages_to_append": messages_to_append,
                    "model": model_used,
                    "needs_confirmation": pending_confirmation,
                }

            result = await run_tool(name, ctx, args)
            steps.append({"tool": name, "arguments": args, "result": result})

            # Audit log for destructive actions
            if spec and spec.get("destructive"):
                try:
                    await ctx.db.assistant_audit_log.insert_one({
                        "_id": str(uuid.uuid4()),
                        "user_id": ctx.business_id,
                        "actor_id": ctx.user_id,
                        "tool": name,
                        "arguments": args,
                        "result": result,
                        "success": not (isinstance(result, dict) and "error" in result),
                        "created_at": datetime.utcnow(),
                    })
                except Exception as e:
                    logger.warning(f"[assistant.audit] failed to write log: {e}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, default=str),
            })

    # Hit step limit without a final answer
    fallback = "I've gathered a lot of info but couldn't finish the task in one go. Ask me to narrow it down or try again."
    messages_to_append.append({"role": "assistant", "content": fallback})
    return {
        "reply": fallback,
        "steps": steps,
        "messages_to_append": messages_to_append,
        "model": model_used,
        "needs_confirmation": pending_confirmation,
    }


def _describe_destructive(name: str, args: Dict[str, Any]) -> str:
    blurbs = {
        "create_customer":        lambda a: f"Add new customer **{a.get('name')}** ({a.get('phone_number')})?",
        "create_followup":        lambda a: f"Set a follow-up on customer `{a.get('customer_id')}` for `{a.get('when')}`?",
        "send_whatsapp_message":  lambda a: f"Send this WhatsApp message to customer `{a.get('customer_id')}`?\n\n> {a.get('message')}",
        "create_broadcast":       lambda a: f"Broadcast this message to audience `{a.get('filter_type','all')}`?\n\n> {a.get('message')}",
        "disconnect_telegram":    lambda a: "Disconnect the Telegram bot? Incoming Telegram messages will stop.",
    }
    blurb = blurbs.get(name, lambda a: f"Run `{name}` with {a}?")(args)
    return f"{blurb}\n\nReply **yes** to confirm, or tell me what to change."
