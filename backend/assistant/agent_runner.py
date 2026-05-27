"""Generic specialist agent runner for Zilo's v2 multi-agent system.

To add a new agent to the system:
    1. Add an entry to AGENT_REGISTRY in agents.py with:
           label, description, system_prompt, allowed_tools
    2. Done. No changes needed here or in the orchestrator.

The runner loads config at call-time so new agents are live on next restart.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_AGENT_STEPS = 6
DEFAULT_AGENT_MAX_STEPS = 6
DOCUMENT_AGENT_MAX_STEPS = 12

# Maps tool names → which result fields to surface as shared artifacts.
# When a specialist produces an artifact (image_url, post_id, etc.) it is
# returned in the `artifacts` dict so the orchestrator can pass it to the
# next specialist without any history parsing.
_ARTIFACT_FIELDS: Dict[str, List[str]] = {
    "generate_social_post":      ["image_url"],
    "generate_ad_creative":      ["image_url"],
    "generate_carousel_cover":   ["image_url"],
    "refine_design":             ["image_url"],
    "generate_creative_image":   ["image_url"],
    "edit_product_image":        ["image_url"],
    "create_scheduled_post":     ["post_id", "scheduled_at", "status", "channels"],
    "create_broadcast":          ["broadcast_id"],
    "create_customer":           ["customer_id"],
    "create_followup":           ["followup_id"],
    "create_invoice":            ["invoice_id"],
    "create_quote":              ["quote_id"],
    "create_business_document":  ["pdf_url", "preview_key", "preview_url"],
    "plan_business_document":    ["preview_key", "preview_url"],
    "generate_document":         ["pdf_url", "download_url", "preview_key"],
    "create_visual_presentation": ["presentation_url", "download_url"],
}

_DOCUMENT_EXPORT_TOOLS = frozenset({
    "create_business_document",
    "generate_document",
    "create_visual_presentation",
})

_CONTINUATION_HINT = (
    "Continue from the tool results above — do NOT repeat the same requirement checks "
    "or CRM fetches you already ran.\n"
    "- If check_document_requirements returned ready=true: write the full Markdown document "
    "and call plan_business_document (NOT create_business_document — user must review the draft first).\n"
    "- If check_presentation_requirements returned ready=true: call plan_visual_presentation.\n"
    "- If a tool returned chat_reply with ready=false: reply using that chat_reply verbatim "
    "and ask only the one missing field.\n"
    "- Never end with an empty message after only running tools."
)

_PLAN_TOOLS = frozenset({"plan_business_document", "plan_visual_presentation"})

_LLM_STRIP_TOOL_FIELDS = frozenset({"html_preview", "content_md", "body_markdown"})
_MAX_TOOL_RESULT_JSON_CHARS = 80_000


def _slim_tool_result_for_llm(result: Any) -> Any:
    """Drop huge HTML/markdown from tool JSON before sending back to the LLM."""
    if not isinstance(result, dict):
        return result
    slim = {k: v for k, v in result.items() if k not in _LLM_STRIP_TOOL_FIELDS}
    if result.get("html_preview") and not slim.get("preview_key"):
        try:
            from .document_generator import store_html_preview
            key = store_html_preview(str(result["html_preview"]))
            slim["preview_key"] = key
            slim["preview_url"] = f"/api/document-preview/{key}"
        except Exception:
            pass
    try:
        payload = json.dumps(slim, default=str)
    except (TypeError, ValueError):
        return {"error": "unserializable_tool_result"}
    if len(payload) <= _MAX_TOOL_RESULT_JSON_CHARS:
        return slim
    return {
        "_truncated": True,
        "original_json_chars": len(payload),
        "preview": payload[:8000] + "…",
    }


def _extract_text_from_steps(steps: List[Dict[str, Any]]) -> str:
    """Build a user-visible reply from tool results when the model returned no text."""
    for step in reversed(steps):
        result = step.get("result")
        tool = step.get("tool") or ""
        if not isinstance(result, dict):
            continue
        if result.get("error"):
            return f"I ran into an issue: {result['error']}"
        for key in ("markdown", "message"):
            val = (result.get(key) or "").strip()
            if val:
                return val
        if result.get("success") and result.get("pdf_url"):
            title = (result.get("filename") or "document").replace(".pdf", "")
            return f"📄 **[Download — {title}]({result['pdf_url']})**"
        if result.get("success") and result.get("plan_ready") and tool == "plan_business_document":
            title = (result.get("title") or "Document").strip()
            return (
                f"Here's your **{title}** draft — review it below. "
                "Edit anything inline, then tap **Approve & Export PDF** when you're ready."
            )
        chat = (result.get("chat_reply") or "").strip()
        if chat:
            return chat
    return ""


def _summarize_last_step(last_step: Dict[str, Any]) -> str:
    """Honest fallback summary when the LLM didn't emit a final reply but at
    least one tool ran successfully. Tries to surface concrete counts/IDs from
    the result instead of fabricating a generic apology."""
    tool = last_step.get("tool") or "the action"
    result = last_step.get("result") or {}
    if not isinstance(result, dict):
        return f"Done — `{tool}` completed."

    # Specific shapes we recognise (extend as more tools surface this issue).
    if "trashed_count" in result:
        n = result.get("trashed_count") or 0
        q = result.get("query")
        if q:
            return f"Done — moved **{n}** thread(s) matching `{q}` to Trash."
        return f"Done — moved **{n}** thread(s) to Trash."
    if result.get("status") == "sent" and result.get("message_id"):
        return "Done — email sent."
    if result.get("status") == "trashed":
        return "Done — moved to Trash."
    if result.get("status") == "created" and result.get("event_id"):
        return "Done — calendar event created."
    if result.get("status") == "updated" and result.get("event_id"):
        return "Done — calendar event updated."
    if result.get("status") == "deleted":
        return "Done — deleted."
    if result.get("status") == "draft_saved":
        return "Done — draft saved."
    if "count" in result and isinstance(result.get("count"), int):
        return f"Done — found {result['count']} item(s)."

    # Generic fall-through: name the tool and signal success.
    if result.get("success") or result.get("status"):
        return f"Done — `{tool}` completed."
    return f"`{tool}` finished but produced no message to show."


def _needs_continuation(steps: List[Dict[str, Any]], *, agent_id: str) -> bool:
    if not steps:
        return False
    tool_names = [s.get("tool") for s in steps]
    if any(t in _DOCUMENT_EXPORT_TOOLS for t in tool_names):
        return False
    if any(t in _PLAN_TOOLS for t in tool_names):
        return False
    for step in reversed(steps):
        result = step.get("result") or {}
        if not isinstance(result, dict):
            continue
        tool = step.get("tool") or ""
        if tool == "check_document_requirements" and result.get("ready"):
            return True
        if tool == "check_presentation_requirements" and result.get("ready"):
            return True
        if result.get("chat_reply") and not result.get("ready", True):
            return True
    return agent_id == "document" and len(steps) >= 3


async def run_agent_stream(
    *,
    agent_id: str,
    task: str,
    context: Optional[Dict[str, Any]] = None,
    db,
    user: Dict[str, Any],
    history: Optional[List[Dict[str, Any]]] = None,
    model_id: Optional[str] = None,
    stream_final: bool = False,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Streaming specialist runner.

    Yields:
        {"type": "tool_start", "tool": <name>}  each time a tool fires
        {"type": "agent_result", "result": {...}}  final structured result
    """
    from .agents import get_agent_config
    from .models import chat_with_tools, stream_reply
    from .tools import ToolContext, openai_tool_specs, openai_tool_specs_filtered, run_tool

    cfg = get_agent_config(agent_id)
    system = (cfg.get("system_prompt") or "").strip()
    if not system:
        # Fallback to the generic system prompt if no specialist prompt defined
        try:
            from .orchestrator import SYSTEM_PROMPT
            system = SYSTEM_PROMPT
        except Exception:
            system = "You are a helpful CRM assistant."

    allowed = cfg.get("allowed_tools")
    tool_specs = (
        openai_tool_specs_filtered(allowed) if allowed is not None else openai_tool_specs()
    )

    # ── Build context injection ───────────────────────────────────────────────
    ctx_lines: List[str] = [f"YOUR TASK: {task}"]
    if context:
        ctx_lines.append(
            "\nCONTEXT FROM PREVIOUS STEPS — use this data directly, do not re-fetch:"
        )
        for k, v in context.items():
            if v is not None:
                ctx_lines.append(f"  {k}: {v}")
    context_block = "\n".join(ctx_lines)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": f"{system}\n\n---\n{context_block}"},
    ]

    # Include recent history so the agent has conversational awareness
    hist = list((history or [])[-6:])
    while hist and hist[0].get("role") != "user":
        hist.pop(0)
    for m in hist:
        role = m.get("role", "user")
        if role in ("user", "assistant"):
            content = m.get("content", "")
            if isinstance(content, str):
                messages.append({"role": role, "content": content[:5000]})

    if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), str):
        messages[-1]["content"] = f"{messages[-1]['content']}\n\n{task}".strip()
    else:
        messages.append({"role": "user", "content": task})

    tool_ctx = ToolContext(db, user)
    from .orchestrator import _load_sidebar_features, _nudge_tool_result
    _sidebar_features = await _load_sidebar_features(db, tool_ctx.business_id)
    steps: List[Dict[str, Any]] = []
    artifacts: Dict[str, Any] = {}
    result_text = ""
    # Use a lightweight flash model for tool planning to minimise latency.
    # Final drafting still uses the heavier model for quality.
    _planning_model = "deepseek-v4-flash"
    # Document replies after tool runs are 1–2 sentences; keep on DeepSeek to avoid
    # Anthropic 400s from cross-provider message/tool payload mismatches.
    _final_model = _planning_model if agent_id == "document" else (model_id or cfg.get("model"))

    max_steps = int(cfg.get("max_steps") or DEFAULT_AGENT_MAX_STEPS)
    if agent_id == "document":
        max_steps = max(max_steps, DOCUMENT_AGENT_MAX_STEPS)

    async def _run_one_step(*, emit_planning: bool):
        """Run one planner turn (async generator — yields SSE events)."""
        nonlocal result_text
        if emit_planning:
            yield {"type": "tool_start", "tool": "planning_specialist"}
        try:
            resp = await chat_with_tools(
                messages=messages,
                tools=tool_specs,
                model_id=_planning_model,
            )
        except Exception as exc:
            logger.exception("[agent_runner] %s chat_with_tools failed: %s", agent_id, exc)
            result_text = (
                "I'm having trouble reaching the AI service right now. "
                "Please try again in a moment."
            )
            return
        raw_msg = resp.get("raw_assistant_message") or {
            "role": "assistant",
            "content": resp.get("content", ""),
        }
        messages.append(raw_msg)
        tool_calls = resp.get("tool_calls") or []

        if not tool_calls:
            draft = resp.get("content", "").strip()
            if stream_final and draft:
                yield {"type": "tool_start", "tool": "drafting_reply"}
                has_tool_results = any(m.get("role") == "tool" for m in messages)
                if has_tool_results:
                    messages.pop()
                    result_text = ""
                    try:
                        async for chunk in stream_reply(
                            messages=messages,
                            tools=[],
                            model_id=_final_model,
                        ):
                            result_text += chunk
                            yield {"type": "token", "text": chunk}
                    except Exception as exc:
                        logger.warning("[agent_runner] %s final stream failed: %s", agent_id, exc)
                        result_text = draft
                        yield {"type": "token", "text": draft}
                    messages.append({"role": "assistant", "content": result_text})
                else:
                    result_text = ""
                    for i in range(0, len(draft), 24):
                        token = draft[i:i + 24]
                        result_text += token
                        yield {"type": "token", "text": token}
            else:
                result_text = draft
            return

        for _tc in tool_calls:
            yield {"type": "tool_start", "tool": _tc.get("name", "")}

        async def _exec_tool(tc: Dict[str, Any]):
            name = tc.get("name", "")
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if agent_id == "document" and name == "create_business_document":
                name = "plan_business_document"
                logger.info("[agent_runner] document agent: redirect create_business_document → plan_business_document")
            try:
                result = await run_tool(name, tool_ctx, args)
                result = _nudge_tool_result(name, result, _sidebar_features)
            except Exception as exc:
                result = {"error": str(exc)}
            return tc, name, args, result

        exec_results = await asyncio.gather(*[_exec_tool(tc) for tc in tool_calls])

        for tc, name, args, result in exec_results:
            steps.append({"tool": name, "arguments": args, "result": result})

            if name in _ARTIFACT_FIELDS and isinstance(result, dict):
                for field in _ARTIFACT_FIELDS[name]:
                    if result.get(field):
                        artifacts[field] = result[field]

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(_slim_tool_result_for_llm(result), default=str),
            })

    # ── Tool-use loop ─────────────────────────────────────────────────────────
    for step_idx in range(max_steps):
        async for ev in _run_one_step(emit_planning=(step_idx == 0)):
            yield ev
        if result_text:
            break

    # Continue when we gathered requirements but never drafted/exported
    if not result_text and _needs_continuation(steps, agent_id=agent_id):
        messages.append({"role": "user", "content": _CONTINUATION_HINT})
        extra_steps = 4 if agent_id == "document" else 2
        for step_idx in range(extra_steps):
            async for ev in _run_one_step(emit_planning=False):
                yield ev
            if result_text:
                break

    # Safety net — synthesize a useful reply from tool results
    from .document_flow import (
        auto_plan_document_from_steps,
        looks_like_document_dump,
        recover_document_plan_from_dump,
    )
    from .models import _strip_dsml

    if result_text:
        result_text = _strip_dsml(result_text)

    if not result_text:
        result_text = _extract_text_from_steps(steps)

    has_plan = any(s.get("tool") == "plan_business_document" for s in steps)
    has_export = any(s.get("tool") in _DOCUMENT_EXPORT_TOOLS for s in steps)

    if agent_id == "document" and result_text and not has_plan and not has_export:
        if looks_like_document_dump(result_text):
            try:
                auto_reply, steps = await recover_document_plan_from_dump(
                    tool_ctx, steps, task, result_text,
                )
                if auto_reply:
                    result_text = auto_reply
                    has_plan = True
            except Exception as exc:
                logger.warning("[agent_runner] document dump recovery failed: %s", exc)

    if result_text and has_plan:
        if len(result_text) > 400:
            result_text = _extract_text_from_steps(steps) or (
                "Here's your draft — review it below. Edit anything inline, "
                "then hit **Approve & Export PDF** when you're ready."
            )

    if not result_text and agent_id == "document":
        if steps and not has_plan and not has_export:
            try:
                auto_reply, steps = await auto_plan_document_from_steps(tool_ctx, steps, task)
                if auto_reply:
                    result_text = auto_reply
            except Exception as exc:
                logger.warning("[agent_runner] document auto-plan failed: %s", exc)
    if not result_text:
        if steps:
            last_step = steps[-1]
            last_result = last_step.get("result") or {}
            if isinstance(last_result, dict) and last_result.get("error"):
                result_text = f"I ran into an issue: {last_result['error']}"
            elif agent_id == "document":
                # Document-agent-specific recovery: it really might be mid-draft.
                result_text = (
                    "I pulled your business data but didn't finish the document yet. "
                    "Say **continue** and I'll draft and export it now."
                )
            else:
                # Generic fallback for other agents: don't fabricate a
                # document-related message. Summarise the last tool's result
                # honestly so the user knows what actually happened.
                result_text = _summarize_last_step(last_step)
        else:
            result_text = "I couldn't complete that request — please try again or rephrase."

    logger.info(
        "[agent_runner] %s done | steps=%d artifacts=%s",
        agent_id, len(steps), list(artifacts.keys()),
    )
    yield {
        "type": "agent_result",
        "result": {
            "text": result_text,
            "artifacts": artifacts,
            "steps": steps,
            "agent_id": cfg["id"],
        },
    }


async def run_agent(
    *,
    agent_id: str,
    task: str,
    context: Optional[Dict[str, Any]] = None,
    db,
    user: Dict[str, Any],
    history: Optional[List[Dict[str, Any]]] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Backward-compatible blocking wrapper. Use run_agent_stream for live events."""
    result: Dict[str, Any] = {}
    async for ev in run_agent_stream(
        agent_id=agent_id, task=task, context=context, db=db,
        user=user, history=history, model_id=model_id,
    ):
        if ev.get("type") == "agent_result":
            result = ev["result"]
    return result or {
        "text": "I couldn't complete that request — please try again or rephrase.",
        "artifacts": {},
        "steps": [],
        "agent_id": agent_id,
    }
