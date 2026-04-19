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

from .models import chat_with_tools
from .tools import REGISTRY, ToolContext, openai_tool_specs, run_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the in-app AI operator for a small-business CRM.
You help the logged-in business owner manage customers, orders, follow-ups, broadcasts, and integrations by calling the tools you have available.

Principles:
- Prefer calling tools over guessing. Never invent customer names, phone numbers, order IDs, or stats.
- If the user asks a question whose answer requires data, call the relevant `list_*` / `get_*` tool first.
- Before any destructive action (sending a WhatsApp message, broadcasting, creating records, disconnecting a channel), briefly restate what you'll do in plain English and wait for the user to confirm unless they already explicitly said "yes / do it / send".
- Keep replies short and business-like. Use bullet points for lists. Show money and times in the user's own units when provided by tools.
- If a tool returns an error, explain it plainly and suggest a next step. Do not keep retrying the same call.
- Never ask for or display API keys, tokens, or raw internal IDs unless the user specifically asks.
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
) -> Dict[str, Any]:
    """Run a single conversational turn."""
    ctx = ToolContext(db, user)

    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
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
