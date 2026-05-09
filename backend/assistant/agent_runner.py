"""Generic specialist agent runner for Zilo's v2 multi-agent system.

To add a new agent to the system:
    1. Add an entry to AGENT_REGISTRY in agents.py with:
           label, description, system_prompt, allowed_tools
    2. Done. No changes needed here or in the orchestrator.

The runner loads config at call-time so new agents are live on next restart.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_AGENT_STEPS = 12

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
    """Run a specialist agent and return a structured result.

    Args:
        agent_id:  Any key in AGENT_REGISTRY  e.g. 'social_scheduler'.
        task:      Plain-language description of what the agent must do.
        context:   Structured data from prior agent calls (image_url, caption …).
                   Injected at the top of the system prompt so the agent has it
                   directly — no history parsing required.
        db:        Motor AsyncIOMotorDatabase instance.
        user:      Authenticated user dict (same shape the tools expect).
        history:   Recent conversation turns; last 12 used for context.
        model_id:  Override model; falls back to agent config then global default.

    Returns:
        {
            "text":      str,   # Agent's final reply text
            "artifacts": dict,  # Structured outputs: image_url, post_id, …
            "steps":     list,  # Tool calls the agent made
            "agent_id":  str,
        }
    """
    from .agents import get_agent_config
    from .models import chat_with_tools
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
    for m in (history or [])[-12:]:
        role = m.get("role", "user")
        if role in ("user", "assistant"):
            content = m.get("content", "")
            if isinstance(content, str):
                messages.append({"role": role, "content": content[:5000]})

    messages.append({"role": "user", "content": task})

    tool_ctx = ToolContext(db, user)
    steps: List[Dict[str, Any]] = []
    artifacts: Dict[str, Any] = {}
    result_text = ""
    _model = model_id or cfg.get("model")

    # ── Tool-use loop ─────────────────────────────────────────────────────────
    for _ in range(MAX_AGENT_STEPS):
        resp = await chat_with_tools(
            messages=messages,
            tools=tool_specs,
            model_id=_model,
        )
        raw_msg = resp.get("raw_assistant_message") or {
            "role": "assistant",
            "content": resp.get("content", ""),
        }
        messages.append(raw_msg)
        tool_calls = resp.get("tool_calls") or []

        if not tool_calls:
            result_text = resp.get("content", "").strip()
            break

        # ── Execute each tool call and feed results back into messages ────────
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            try:
                result = await run_tool(name, tool_ctx, args)
            except Exception as exc:
                result = {"error": str(exc)}

            steps.append({"tool": name, "arguments": args, "result": result})

            # Auto-extract artifacts
            if name in _ARTIFACT_FIELDS and isinstance(result, dict):
                for field in _ARTIFACT_FIELDS[name]:
                    if result.get(field):
                        artifacts[field] = result[field]

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(result, default=str),
            })

    # Safety net — if MAX_AGENT_STEPS exhausted without a text reply
    if not result_text:
        if steps:
            last_result = steps[-1].get("result") or {}
            if isinstance(last_result, dict) and last_result.get("message"):
                result_text = last_result["message"]
            elif isinstance(last_result, dict) and last_result.get("error"):
                result_text = f"I ran into an issue: {last_result['error']}"
            else:
                result_text = "I've completed the requested actions."
        else:
            result_text = "I've completed the requested actions."

    logger.info(
        "[agent_runner] %s done | steps=%d artifacts=%s",
        agent_id, len(steps), list(artifacts.keys()),
    )
    return {
        "text": result_text,
        "artifacts": artifacts,
        "steps": steps,
        "agent_id": cfg["id"],
    }
