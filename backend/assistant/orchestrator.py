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
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .agents import get_agent_config
from .context_builder import build_context, format_context_block
from .critic import critique
from .documents import build_context_preamble, load_full
from .interactive_suggestions import build_reply_suggestions
from .models import chat_with_tools, resolve_model
from .planner import format_plan_hint, plan
from .tools import REGISTRY, ToolContext, openai_tool_specs, openai_tool_specs_filtered, run_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are **Zilo Chat**, the in-app AI business intelligence operator for a CRM platform.
You help the business owner manage customers, orders, follow-ups, broadcasts, integrations, and reference documents with deep analytical insight.

When documents are attached (PDF, DOCX, TXT, CSV, image), the relevant text or image is placed in a system preamble or attached natively. You can read, summarize, extract data, cross-reference with CRM data, and answer questions. Always cite the filename when quoting or paraphrasing.

---

# Intelligence Rules
- **Always use tools first. Never ask the user for information you can fetch yourself.**
  - Business name, owner name, phone, country, currency → `get_owner_info`
  - Products and services → `list_products`
  - Revenue and sales data → `get_analytics_summary` + `get_revenue_trends`
  - Customers → `list_customers` or `get_top_customers`
  - Orders → `list_orders` or `get_sales_pipeline`
  - Follow-ups → `list_followups`
  - Team → `list_team`
  - If you need something and there's a tool for it, **call the tool — do not ask the user**.
- **Think in layers.** When the user asks a broad question or requests a document, chain multiple tools to build a complete picture. E.g. "business proposal" → call `get_owner_info` + `list_products` + `get_analytics_summary` + `get_revenue_trends` + `get_top_customers` before writing a single word.
- **Spot patterns.** After retrieving data, note trends: revenue direction, dormant customers, overdue follow-ups, stalled orders. Flag what the owner should act on without being asked.
- **Cross-reference.** If revenue is dropping, check follow-ups. If a top customer hasn't ordered recently, flag the risk.
- Before any destructive action (sending a WhatsApp, broadcasting, creating or deleting records), restate what you will do and wait for confirmation unless the user already said "yes / do it / send / confirm".
- If a tool returns an error, explain it plainly and suggest the fix. Do not retry the same call blindly.
- **When to ask the user:** Only ask if a piece of information (a) cannot be fetched from any tool AND (b) is truly required to complete the task. Examples: recipient name for a proposal, a specific date range the user wants to cover, a custom message body. Keep it to ONE focused question. Never ask for anything that's already in the CRM.

---

# Document Generation
When the user asks for a report, proposal, analysis, contract draft, invoice, or any formal document:

1. **Collect all data from tools first — without asking the user.** For a business proposal: call `get_owner_info`, `list_products`, `get_analytics_summary`, `get_revenue_trends`, `get_top_customers`. For a customer report: call `get_customer`. For a sales report: call `get_revenue_trends` + `get_sales_pipeline`. Use whatever tools are relevant. Pull everything you need in the tool loop, then write.
2. **Write the full document in rich Markdown** — headings, tables, bullets, summaries. Quality matters: it should look like it came from a professional consultant. Fill every section with real data from the tools. Never use placeholder text like "[Your business name]" or "[Insert revenue here]".
3. **After writing the document, immediately call `generate_document`** with the full markdown content to produce a downloadable file. Pass the format the user requested (default: pdf). Include the returned `download_url` in your reply as a Markdown link so the user can download instantly — e.g. `[Download PDF](download_url)`. Do NOT say "Reply pdf or docx" if you have already generated the file.
4. Structure every formal document with:
   - H1 title + H2 subtitle/date
   - Executive Summary paragraph (most important insights up front)
   - Clearly delineated sections using H2/H3
   - All data in well-formatted Markdown tables
   - Key callout points using blockquotes (`> key insight here`) for important facts, warnings, or highlights
   - "Key Findings" or "Recommendations" section near the end
   - Professional closing statement
5. For financial documents: include period covered, currency (from owner settings), and data source note.
6. For proposals and pitches: lead with the business's strengths and real metrics.
7. **Images**: If you include an image reference `![caption](url)`, it will be rendered in the document at the correct size with the caption below. Only include real, accessible image URLs — never invent or guess URLs.
- **Design library:** A system block may list **brand assets** (logos, images, reference PDFs) the owner saved under Dashboard → Design library. Prefer those URLs in creative and document advice. After they say they uploaded new files, call `list_design_library_assets` so you have fresh URLs.

---

# Automations
When the user wants to automate something — follow-ups, notifications, tagging, routing, sequences, or any repeating task — use the automation tools.

- **Detecting intent:** Phrases like "automate", "every time", "whenever", "when a customer does X", "set up a rule", "create a workflow", "remind me automatically", "tag leads who", "send a follow-up if they don't reply" all signal automation intent.
- **Always call `list_automations` first** to avoid creating duplicates and to show what already exists.
- **To create:** Call `create_automation` with the full plain-English description. You do NOT need to manually construct the trigger/steps JSON — the builder handles that. Write a clear, complete description including trigger, condition, timing, and action.
- **After creating:** Confirm with the name, trigger, and steps summary. Tell the user the automation is now live.
- **Format automation lists as a table:**
  | # | Name | Trigger | Steps | Status | Runs |
  |---|------|---------|-------|--------|------|
- Keep automation names short and clear. If the user is vague, ask ONE clarifying question (e.g. what message to send, or what tag to apply).
- Available trigger types: `incoming_message`, `intent_detected` (order/booking/inquiry/complaint), `tag_added`, `customer_created`, `pipeline_stage_changed`.
- Available actions: send message, tag contact, assign owner, notify owner, create follow-up, move pipeline stage, escalate, wait, if_no_reply.

---

# Design & Creative Generation
- **Static graphics and carousels** use **Orshot** when your tools include `list_orshot_templates`, `get_orshot_template_fields`, and `render_orshot_template`: list or pick a template, learn field keys once, then `render_orshot_template`. There are no HTML or screenshot-based image tools.
- If you **lack** Orshot tools but the user wants a visual, say briefly to switch to **Design / Creative** or **Meta Ads** / **Social** (those specialists carry Orshot).
- For product ads and graphics, the Design agent runs a **3-phase conversational flow**: (1) **Plan** — agree on product, concept, copy, and platform before generating anything; (2) **Product shot preview** — generate and approve the AI-enhanced product photo first; (3) **Full ad** — pick Orshot template, render two options, refine until done. Never generate in phase 1.

---

# Response Format — write like a senior business analyst, not a chatbot
Every reply must read like a polished document an executive would skim.

**Structure for data responses:**
1. `### Headline` — one line summarizing what you are reporting, e.g. `### Revenue Overview — April 2025` or `### 7 Follow-ups Pending`.
2. **Lead sentence** — the single most important takeaway.
3. **Data section** — Markdown tables. Required columns by entity:
   - Follow-ups: `#`, `Customer`, `Phone`, `Due`, `Channel`, `Note`
   - Orders: `#`, `Customer`, `Items`, `Total`, `Status`, `Placed`
   - Customers: `#`, `Name`, `Phone`, `Last Contact`, `Tags`
   - Broadcasts: `#`, `Name`, `Audience`, `Sent`, `Delivered`, `Created`
   - Revenue: `Period`, `Revenue`, `Orders`, `Avg Order`, `vs Prior`
   - Products: `#`, `Product`, `Price`, `Stock`
4. **Key Observations** (if useful) — 2–4 bullets, only if there is something the owner should act on.
5. **Suggested Actions** — close with 1–2 concrete next steps written as clickable replies, e.g. `_Reply **send followups** to message all overdue customers, or tell me which one to contact._`

**Formatting rules:**
- **Never show raw UUIDs.** Use `name` from tool output. If only ID is present, use the first 8 chars: `#a97bccb5`.
- Dates: human-friendly only — `today`, `yesterday`, `Apr 19`, `3 days ago`, `Mon Apr 21`. Never ISO strings.
- Money: use the currency from owner settings; format with thousands separator (e.g. `KES 12,500`).
- Long text in table cells: first ~60 chars + `…`.
- Lists over 10 items: show 10, then `_… and N more — ask to see the rest._`
- Empty results: one clear sentence; no empty table.
- Never show: `_id`, `user_id`, `tool_call_id`, internal tokens, raw DB fields.
- Tone: calm, precise, confident. No emoji. No exclamation marks. No "Sure!" / "Great question!" openers. Lead with the answer.
"""

MAX_STEPS = 14
AFFIRMATIVE = {"yes", "y", "ok", "okay", "sure", "go", "do it", "send", "confirm", "confirmed", "yep", "yeah"}

# Tool results go to the LLM and to Mongo on assistant messages — cap JSON size both places.
_MAX_TOOL_RESULT_JSON_CHARS = 80_000


def _limit_tool_result_size(result: Any) -> Any:
    """Replace oversized tool JSON with a short preview (Orshot template payloads, etc.)."""
    try:
        s = json.dumps(result, default=str)
    except (TypeError, ValueError):
        return {"error": "unserializable_tool_result"}
    if len(s) <= _MAX_TOOL_RESULT_JSON_CHARS:
        return result
    return {
        "_truncated": True,
        "original_json_chars": len(s),
        "preview": s[:8000] + "…",
    }


async def _finalize_turn(payload: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    """Attach tap-to-send suggestion chips for interactive specialists (e.g. Meta Ads)."""
    if payload.get("needs_confirmation"):
        payload.setdefault("reply_suggestions", [])
        return payload
    reply = payload.get("reply") or ""
    ag = payload.get("active_agent") or ""
    try:
        sugs = await build_reply_suggestions(ag, user_message, reply)
    except Exception as exc:
        logger.warning("[orchestrator] build_reply_suggestions failed: %s", exc)
        sugs = []
    payload["reply_suggestions"] = sugs
    if sugs and payload.get("messages_to_append"):
        last = payload["messages_to_append"][-1]
        if last.get("role") == "assistant":
            last["suggestions"] = sugs
    return payload


async def run_turn(
    *,
    db,
    user: Dict[str, Any],
    history: List[Dict[str, Any]],
    user_message: str,
    model_id: Optional[str] = None,
    auto_approve_destructive: bool = False,
    conversation_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a single conversational turn."""
    # Stash the conversation id on the user dict so tools (e.g. search_documents)
    # can scope their queries without an extra plumbing channel.
    user = {**user, "_active_conversation_id": conversation_id}
    ctx = ToolContext(db, user)

    ag_cfg = get_agent_config(agent_id)
    active_agent_id = ag_cfg["id"]
    allowed = ag_cfg.get("allowed_tools")
    tool_specs = openai_tool_specs_filtered(allowed) if allowed is not None else openai_tool_specs()
    if ag_cfg.get("use_default_system_prompt"):
        system_text = SYSTEM_PROMPT
    else:
        system_text = (ag_cfg.get("system_prompt") or SYSTEM_PROMPT).strip()
    # Agent-level model override takes priority over the request/conversation model
    if ag_cfg.get("model"):
        model_id = ag_cfg["model"]

    # Planner: decompose complex multi-step requests before the ReAct loop.
    # Runs a fast LLM call only when the message looks multi-intent; skips instantly otherwise.
    _execution_plan = await plan(user_message, list(allowed or []))

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

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_text}]

    # Mirror AutoReply v2's mini-state pattern: when running the design agent,
    # inject a compact snapshot of locked template / platform / staged image so
    # the model can't silently drift onto a different template across turns.
    if active_agent_id in ("design", "creative", "social_media") and conversation_id:
        try:
            from .design_state import (
                load_design_state,
                format_design_state_for_prompt,
                update_design_state,
                _STEP_NEXT_ACTION,
            )

            ds = await load_design_state(db, conversation_id, ctx.business_id)
            # Bootstrap flow_step on the very first design-agent turn
            if not ds.get("flow_step"):
                await update_design_state(
                    db, conversation_id, ctx.business_id,
                    flow_step="awaiting_product",
                )
                ds["flow_step"] = "awaiting_product"
            ds_block = format_design_state_for_prompt(ds)
            if ds_block:
                messages.append({"role": "system", "content": ds_block})
        except Exception:
            logger.exception("[orchestrator] design state injection skipped")

    try:
        from saved_designs import build_design_library_context_message

        lib_ctx = await build_design_library_context_message(db, ctx.business_id)
        if lib_ctx:
            messages.append({"role": "system", "content": lib_ctx})
    except Exception:
        logger.exception("[orchestrator] design library context skipped")
    # Append document context (text) as a second system message.
    # For LONG docs we also note that the `search_documents` tool is available so
    # the model can pull additional excerpts instead of relying on the truncated preamble.
    if attached_docs:
        preamble = build_context_preamble(attached_docs)
        if preamble:
            has_long_doc = any(
                (d.get("text_len") or len(d.get("text") or "")) >= 6000 for d in attached_docs
            )
            if has_long_doc:
                preamble += (
                    "\n\nNote: at least one document is long and has been chunked. "
                    "Call the `search_documents` tool with a natural-language query whenever "
                    "you need passages that aren't in the excerpt above."
                )
            messages.append({"role": "system", "content": preamble})
    # Context builder: inject long-term memory + RAG knowledge chunks (parallel fetch).
    # Gracefully no-ops if QDRANT_URL or OPENAI_API_KEY is not configured.
    _rag_ctx = await build_context(
        user_id=str(user.get("_id", "")),
        business_id=str(user.get("business_id") or user.get("_id", "")),
        user_message=user_message,
    )
    _ctx_block = format_context_block(_rag_ctx)
    if _ctx_block:
        messages.append({"role": "system", "content": _ctx_block})

    # Inject Planner hint for complex multi-step requests
    _plan_hint = format_plan_hint(_execution_plan)
    if _plan_hint:
        messages.append({"role": "system", "content": _plan_hint})

    # Trim history to last 50 messages
    messages.extend(history[-50:])
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
            tools=tool_specs,
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
            # Critic: review the draft before returning. No-ops unless CRITIC_ENABLED=true.
            final = await critique(
                draft=final,
                user_message=user_message,
                knowledge_chunks=_rag_ctx.get("knowledge_chunks", []),
            )
            messages_to_append.append({"role": "assistant", "content": final})
            # Memory flush: every MEMORY_FLUSH_EVERY turns, summarize + embed async.
            _flush_every = int(os.getenv("MEMORY_FLUSH_EVERY", "10"))
            if len(history) > 0 and (len(history) + 1) % _flush_every == 0:
                import asyncio as _asyncio
                from memory.flush import flush_to_long_term
                _asyncio.create_task(flush_to_long_term(
                    customer_id=str(user.get("_id", "")),
                    business_id=str(user.get("business_id") or user.get("_id", "")),
                    turns=history[-_flush_every:],
                ))
            return await _finalize_turn(
                {
                    "reply": final,
                    "steps": steps,
                    "messages_to_append": messages_to_append,
                    "model": model_used,
                    "needs_confirmation": pending_confirmation,
                    "active_agent": active_agent_id,
                },
                user_message,
            )

        # Execute tool calls (OpenAI may return multiple in one shot)
        for tc in tool_calls:
            tc_id = tc.get("id") or str(uuid.uuid4())
            name = tc.get("name")
            if not name:
                logger.error("[orchestrator] tool_call missing name: %s", tc)
                steps.append({"tool": "(invalid)", "arguments": tc, "result": {"error": "Model returned a tool call without a name — retry the message."}})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": json.dumps({"error": "Malformed tool call (missing name)."}, default=str),
                })
                continue
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except Exception:
                    args = {}
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
                return await _finalize_turn(
                    {
                        "reply": preview_text,
                        "steps": steps,
                        "messages_to_append": messages_to_append,
                        "model": model_used,
                        "needs_confirmation": pending_confirmation,
                        "active_agent": active_agent_id,
                    },
                    user_message,
                )

            result = await run_tool(name, ctx, args)
            capped = _limit_tool_result_size(result)
            steps.append({
                "tool": name,
                "arguments": args,
                "result": capped,
            })

            # Structured ERROR logging — mirrors AutoReply v2's failure-trace pattern.
            # When a tool returns an `error` field (or raises a swallowed exception
            # surfaced as such), log the full context so we can diagnose silent drift
            # (wrong template_id, missing field key, vendor 4xx, etc.) without grepping.
            if isinstance(result, dict) and result.get("error"):
                try:
                    logger.error(
                        "[assistant.tool_error] tool=%s agent=%s conv=%s user=%s args=%s error=%r",
                        name,
                        active_agent_id,
                        conversation_id,
                        ctx.user_id,
                        json.dumps(args, default=str)[:1500],
                        result.get("error"),
                    )
                except Exception:
                    logger.exception("[assistant.tool_error] log emission failed (tool=%s)", name)

            # Audit log for destructive actions
            if spec and spec.get("destructive"):
                try:
                    await ctx.db.assistant_audit_log.insert_one({
                        "_id": str(uuid.uuid4()),
                        "user_id": ctx.business_id,
                        "actor_id": ctx.user_id,
                        "tool": name,
                        "arguments": args,
                        "result": capped,
                        "success": not (isinstance(result, dict) and "error" in result),
                        "agent": active_agent_id,
                        "created_at": datetime.utcnow(),
                    })
                except Exception as e:
                    logger.warning(f"[assistant.audit] failed to write log: {e}")

            try:
                tool_payload = json.dumps(capped, default=str)
            except (TypeError, ValueError) as ser_err:
                logger.exception("[orchestrator] tool result not JSON-serializable (tool=%s)", name)
                tool_payload = json.dumps(
                    {
                        "error": "Tool output could not be serialized for the chat session",
                        "tool": name,
                        "detail": str(ser_err),
                    },
                    default=str,
                )
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or tc_id,
                "content": tool_payload,
            })

    # Hit step limit without a final answer
    fallback = "I've gathered a lot of info but couldn't finish the task in one go. Ask me to narrow it down or try again."
    messages_to_append.append({"role": "assistant", "content": fallback})
    return await _finalize_turn(
        {
            "reply": fallback,
            "steps": steps,
            "messages_to_append": messages_to_append,
            "model": model_used,
            "needs_confirmation": pending_confirmation,
            "active_agent": active_agent_id,
        },
        user_message,
    )


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
