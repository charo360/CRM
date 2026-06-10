"""
ai_builder.py — convert plain English descriptions into workflow JSON.

Takes a natural language description like:
  "When a customer asks about price, wait 2 hours, then if they haven't replied,
   send a follow-up message"

Returns a validated WorkflowCreate-compatible dict.

Uses the existing AIMessageDrafter infrastructure so it respects the user's
configured AI provider.
"""
from __future__ import annotations

import json
import logging
import re
from difflib import get_close_matches
from typing import Any, Dict

from .capabilities import CAPABILITIES, TRIGGER_TYPES

# Common LLM mistakes → exact capability keys
_ACTION_ALIASES: Dict[str, str] = {
    "send_message": "send_message",
    "send_whatsapp_message": "send_message",
    "send_whatsapp": "send_message",
    "whatsapp_message": "send_message",
    "message": "send_message",
    "reply": "send_message",
    "auto_reply": "send_message",
    "tag_contact": "tag_contact",
    "add_tag": "tag_contact",
    "tag": "tag_contact",
    "set_tag": "tag_contact",
    "assign_owner": "assign_owner",
    "assign": "assign_owner",
    "notify_owner": "notify_owner",
    "notify": "notify_owner",
    "push_notify": "notify_owner",
    "create_followup": "create_followup",
    "followup": "create_followup",
    "follow_up": "create_followup",
    "reminder": "create_followup",
    "move_pipeline_stage": "move_pipeline_stage",
    "set_stage": "move_pipeline_stage",
    "change_stage": "move_pipeline_stage",
    "escalate_to_human": "escalate_to_human",
    "escalate": "escalate_to_human",
    "wait": "wait",
    "delay": "wait",
    "sleep": "wait",
    "pause": "wait",
    "if_no_reply": "if_no_reply",
    "check_no_reply": "if_no_reply",
    "no_reply": "if_no_reply",
}


def _normalize_action(raw: Any) -> str:
    if raw is None:
        return ""
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if key in _ACTION_ALIASES:
        return _ACTION_ALIASES[key]
    if key in CAPABILITIES:
        return key
    matches = get_close_matches(key, list(CAPABILITIES.keys()), n=1, cutoff=0.55)
    return matches[0] if matches else ""


def _stringify_condition(cond: Any) -> str:
    """WorkflowTrigger.condition must be Optional[str]; LLMs often return lists/objects."""
    if cond is None:
        return "always"
    if isinstance(cond, str):
        s = cond.strip()
        return s if s else "always"
    if isinstance(cond, (list, dict)):
        try:
            return json.dumps(cond, ensure_ascii=False)
        except (TypeError, ValueError):
            return "always"
    return str(cond)


def _normalize_trigger(tr: Any) -> Dict[str, Any]:
    if not isinstance(tr, dict):
        return {"type": "incoming_message", "condition": "always"}
    raw_type = tr.get("type") or "incoming_message"
    if isinstance(raw_type, list) and raw_type:
        raw_type = raw_type[0]
    raw_type = str(raw_type).strip().lower().replace(" ", "_").replace("-", "_")
    valid = list(TRIGGER_TYPES.keys())
    if raw_type in valid:
        t = raw_type
    else:
        m = get_close_matches(raw_type, valid, n=1, cutoff=0.5)
        t = m[0] if m else "incoming_message"
    return {"type": t, "condition": _stringify_condition(tr.get("condition"))}

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    caps_list = "\n".join(
        f"  - {name}: {info['description']}"
        for name, info in CAPABILITIES.items()
    )
    trigger_list = "\n".join(
        f"  - {name}: {info['description']}"
        for name, info in TRIGGER_TYPES.items()
    )
    allowed_actions = ", ".join(CAPABILITIES.keys())
    return f"""You are a workflow builder for a WhatsApp CRM system.

Your job: convert a natural language automation description into a structured JSON workflow.

## Available trigger types:
{trigger_list}

## Available action capabilities:
{caps_list}

## Output format:
Return ONLY a valid JSON object with this exact structure:
{{
  "name": "Short descriptive name",
  "description": "One sentence explaining what it does",
  "trigger": {{
    "type": "one of the trigger types above",
    "condition": "condition string or 'always'"
  }},
  "steps": [
    {{
      "id": "step_1",
      "action": "capability name",
      "params": {{ ... }},
      "delay_minutes": 0
    }}
  ],
  "enabled": true
}}

## Rules:
- Only use trigger types and action capabilities from the lists above
- Use these EXACT action strings (copy verbatim): {allowed_actions}
- For delays, use "wait" action with param "hours" (e.g. 2.0 for 2 hours). Set delay_minutes = 0 for wait steps.
- After a wait, use "if_no_reply" if you want to check if the customer replied
- Use placeholders like {{customer_name}}, {{business_name}}, {{first_name}}, {{phone}}, and any event fields or {{extracted_text}} for browser extractions in message texts or text parameters
- For send_message, optional params "destination": "customer_whatsapp" (default, message to contact on WhatsApp) or "owner_push" (message as mobile push to the business owner only); optional "title" when using owner_push
- Conditions for incoming_message: "always" or "message_contains('word')"
- Conditions for intent_detected: "intent == 'order'" etc.
- Keep step IDs sequential: step_1, step_2, ...
- No markdown, no explanation — ONLY the JSON object"""


# ── AI call ────────────────────────────────────────────────────────────────────

async def build_workflow_from_description(
    description: str,
    user: dict,
) -> Dict[str, Any]:
    """
    Convert a natural language description into a workflow dict.
    Returns the workflow dict or raises ValueError on failure.
    """
    from ai_service import AIMessageDrafter

    drafter = AIMessageDrafter()
    model_pref = (user.get("settings") or {}).get("ai_model", "standard") or "standard"
    client_type, model_name, client = drafter._get_client_and_model(model_pref)

    if not client:
        client_type, model_name, client = drafter._get_default_client_and_model()

    if not client:
        raise ValueError("No AI provider configured — add an API key to environment")

    system = _build_system_prompt()
    messages = [{"role": "user", "content": description}]

    raw = ""
    for attempt in range(2):
        try:
            if client_type == "claude":
                import httpx
                headers = {
                    "x-api-key": client["key"],
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                payload = {
                    "model": model_name,
                    "max_tokens": 1200,
                    "system": system,
                    "messages": messages,
                }
                async with httpx.AsyncClient() as http:
                    resp = await http.post(client["endpoint"], json=payload, headers=headers, timeout=30)
                    if resp.status_code != 200:
                        raise RuntimeError(f"Claude API {resp.status_code}: {resp.text[:200]}")
                    raw = resp.json()["content"][0]["text"]
            else:
                import asyncio
                kwargs: dict = {
                    "model": model_name,
                    "messages": [{"role": "system", "content": system}] + messages,
                    "max_tokens": 1200,
                    "temperature": 0.3,
                }
                # Force JSON output on supporting models
                if any(model_name.startswith(p) for p in ("gpt-", "deepseek")):
                    kwargs["response_format"] = {"type": "json_object"}
                resp = await asyncio.to_thread(client.chat.completions.create, **kwargs)
                raw = resp.choices[0].message.content or ""

            return _parse_workflow_json(raw)

        except Exception as exc:
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Return ONLY valid JSON with no markdown or extra text."},
                ]
                continue
            raise ValueError(f"Could not generate workflow: {exc}") from exc

    raise ValueError("Could not generate workflow after retries")


def _parse_workflow_json(raw: str) -> Dict[str, Any]:
    """Extract and validate the JSON from the AI response."""
    text = raw.strip()
    # Strip markdown code fences
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI returned invalid JSON: {exc}") from exc

    data = _unwrap_workflow_root(data)

    # Validate required fields
    if not isinstance(data.get("steps"), list) or not data["steps"]:
        raise ValueError("Missing 'steps' in workflow")

    raw_name = data.get("name")
    if raw_name is None:
        nm = "New Automation"
    else:
        nm = str(raw_name).strip()[:100]
    if not nm:
        nm = "New Automation"
    data["name"] = nm

    raw_desc = data.get("description")
    data["description"] = (str(raw_desc).strip()[:500] if raw_desc is not None else "")[:500]

    en = data.get("enabled", True)
    if isinstance(en, str):
        data["enabled"] = en.strip().lower() in ("1", "true", "yes", "on")
    else:
        data["enabled"] = bool(en)

    data["trigger"] = _normalize_trigger(data.get("trigger"))

    safe_steps: list = []
    for i, step in enumerate(data["steps"]):
        if not isinstance(step, dict):
            continue
        raw_action = step.get("action") or step.get("type") or step.get("capability")
        action = _normalize_action(raw_action)
        if not action or action not in CAPABILITIES:
            logger.warning(f"[AIBuilder] Dropping unknown capability '{raw_action}' → '{action}'")
            continue
        raw_params = step.get("params")
        if isinstance(raw_params, dict):
            params = raw_params
        elif raw_params is None:
            params = {}
        else:
            params = {"value": raw_params}
        try:
            dm = int(float(step.get("delay_minutes") or 0))
        except (TypeError, ValueError):
            dm = 0
        safe_steps.append(
            {
                "id": str(step.get("id") or f"step_{i + 1}"),
                "action": action,
                "params": params,
                "delay_minutes": max(0, dm),
            }
        )

    if not safe_steps:
        raise ValueError(
            "No valid capabilities in generated workflow — try describing send_message, tag_contact, wait, or create_followup"
        )

    data["steps"] = safe_steps
    return data


def _unwrap_workflow_root(data: Any) -> Dict[str, Any]:
    """LLMs often wrap the payload in a key or return an array of one object."""
    if isinstance(data, str):
        try:
            data = json.loads(data.strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"AI returned a string that is not JSON: {exc}") from exc
        return _unwrap_workflow_root(data)
    if isinstance(data, list):
        if not data:
            raise ValueError("AI returned an empty JSON array")
        return _unwrap_workflow_root(data[0])
    if not isinstance(data, dict):
        raise ValueError("AI returned JSON that is not an object")
    for key in ("workflow", "automation", "result", "data", "output", "response"):
        inner = data.get(key)
        if isinstance(inner, dict) and ("steps" in inner or "trigger" in inner):
            return inner
    return data


def fallback_workflow_create(description: str) -> Dict[str, Any]:
    """
    Minimal valid WorkflowCreate dict — used when AI output fails parse/validation
    so the user still gets an editable starter workflow (no 422).
    """
    desc = (description or "").strip()
    desc = desc.replace("\r", " ").replace("\n", " ")[:500]
    return {
        "name": "Starter automation",
        "description": desc,
        "trigger": {"type": "incoming_message", "condition": "always"},
        "steps": [
            {
                "id": "step_1",
                "action": "send_message",
                "params": {
                    "message": "Hi {customer_name}, thanks for your message — we will get back to you shortly.",
                },
                "delay_minutes": 0,
            }
        ],
        "enabled": True,
    }
