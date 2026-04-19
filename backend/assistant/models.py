"""Pluggable LLM adapter for the assistant.

Exposes a single `chat_with_tools` entry point that:
- Accepts OpenAI-style messages + tools
- Dispatches to the correct provider (openai, deepseek, grok, anthropic)
- Returns a normalized response: {content, tool_calls, finish_reason, raw}

Keys picked up from env: OPENAI_API_KEY, DEEPSEEK_API_KEY, GROK_API_KEY, ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Model registry ────────────────────────────────────────────────────────────
# id ↔ provider + upstream model name. id is what the UI passes.
MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
    "gpt-4o-mini":             {"provider": "openai",    "model": "gpt-4o-mini",               "label": "GPT-4o mini (fast)"},
    "gpt-4o":                  {"provider": "openai",    "model": "gpt-4o",                    "label": "GPT-4o (smart)"},
    "claude-sonnet-4.5":       {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929","label": "Claude Sonnet 4.5"},
    "claude-3.5-sonnet":       {"provider": "anthropic", "model": "claude-3-5-sonnet-latest",  "label": "Claude 3.5 Sonnet"},
    "deepseek-chat":           {"provider": "deepseek",  "model": "deepseek-chat",             "label": "DeepSeek Chat"},
    "grok-4":                  {"provider": "grok",      "model": "grok-4",                    "label": "Grok 4"},
}

DEFAULT_MODEL = os.environ.get("ASSISTANT_DEFAULT_MODEL", "gpt-4o-mini")


def _provider_available(provider: str) -> bool:
    key_map = {
        "openai":    "OPENAI_API_KEY",
        "deepseek":  "DEEPSEEK_API_KEY",
        "grok":      "GROK_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    return bool(os.environ.get(key_map.get(provider, ""), "").strip())


def list_available_models() -> List[Dict[str, str]]:
    out = []
    for mid, cfg in MODEL_REGISTRY.items():
        if _provider_available(cfg["provider"]):
            out.append({"id": mid, "label": cfg["label"], "provider": cfg["provider"]})
    return out


def resolve_model(model_id: Optional[str]) -> Dict[str, str]:
    if model_id and model_id in MODEL_REGISTRY and _provider_available(MODEL_REGISTRY[model_id]["provider"]):
        return {**MODEL_REGISTRY[model_id], "id": model_id}
    # Fallback to first available
    for mid, cfg in MODEL_REGISTRY.items():
        if _provider_available(cfg["provider"]):
            return {**cfg, "id": mid}
    raise RuntimeError("No LLM provider is configured. Set at least one API key (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc).")


# ── Chat entrypoint ───────────────────────────────────────────────────────────
async def chat_with_tools(
    *,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model_id: Optional[str] = None,
    temperature: float = 0.2,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Run one round of chat completion with tool-calling enabled.

    `messages` follow OpenAI format: {role, content, tool_calls?, tool_call_id?}.
    `tools` is a list of OpenAI tool specs: {type:"function", function:{name, description, parameters}}.
    Returns: {content, tool_calls:[{id,name,arguments}], finish_reason, model, raw}.
    """
    cfg = resolve_model(model_id)
    provider = cfg["provider"]

    if provider in ("openai", "deepseek", "grok"):
        return await _call_openai_compatible(cfg, messages, tools, temperature, timeout)
    if provider == "anthropic":
        return await _call_anthropic(cfg, messages, tools, temperature, timeout)
    raise RuntimeError(f"Unsupported provider: {provider}")


# ── OpenAI / DeepSeek / Grok (OpenAI-compatible) ─────────────────────────────
_OAI_COMPATIBLE_BASE = {
    "openai":   "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "grok":     "https://api.x.ai/v1",
}
_OAI_KEY_ENV = {
    "openai":   "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "grok":     "GROK_API_KEY",
}


async def _call_openai_compatible(
    cfg: Dict[str, str],
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    temperature: float,
    timeout: float,
) -> Dict[str, Any]:
    provider = cfg["provider"]
    base = _OAI_COMPATIBLE_BASE[provider]
    key = os.environ[_OAI_KEY_ENV[provider]]

    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    choice = data["choices"][0]
    msg = choice["message"]
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        try:
            args = json.loads(tc["function"]["arguments"] or "{}")
        except Exception:
            args = {}
        tool_calls.append({
            "id": tc.get("id") or f"call_{len(tool_calls)}",
            "name": tc["function"]["name"],
            "arguments": args,
        })

    return {
        "content": msg.get("content") or "",
        "tool_calls": tool_calls,
        "finish_reason": choice.get("finish_reason", "stop"),
        "model": cfg["id"],
        "raw_assistant_message": msg,  # kept so we can echo exact tool_calls back into history
    }


# ── Anthropic ─────────────────────────────────────────────────────────────────
async def _call_anthropic(
    cfg: Dict[str, str],
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    temperature: float,
    timeout: float,
) -> Dict[str, Any]:
    key = os.environ["ANTHROPIC_API_KEY"]

    # Anthropic wants system separate + content blocks.
    system_text = ""
    a_messages: List[Dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_text = (system_text + "\n\n" + (m.get("content") or "")).strip()
            continue
        if role == "tool":
            # Tool result → user message with tool_result block
            a_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m["tool_call_id"],
                    "content": m.get("content") or "",
                }],
            })
            continue
        if role == "assistant" and m.get("tool_calls"):
            blocks: List[Dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                })
            a_messages.append({"role": "assistant", "content": blocks})
            continue
        a_messages.append({"role": role, "content": m.get("content") or ""})

    # Convert OpenAI tool spec → Anthropic tool spec
    a_tools = [{
        "name": t["function"]["name"],
        "description": t["function"].get("description", ""),
        "input_schema": t["function"]["parameters"],
    } for t in tools]

    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": a_messages,
        "max_tokens": 4096,
        "temperature": temperature,
    }
    if system_text:
        payload["system"] = system_text
    if a_tools:
        payload["tools"] = a_tools

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    content_text = ""
    tool_calls = []
    raw_blocks: List[Dict[str, Any]] = []
    for blk in data.get("content") or []:
        raw_blocks.append(blk)
        if blk.get("type") == "text":
            content_text += blk.get("text", "")
        elif blk.get("type") == "tool_use":
            tool_calls.append({
                "id": blk["id"],
                "name": blk["name"],
                "arguments": blk.get("input") or {},
            })

    return {
        "content": content_text,
        "tool_calls": tool_calls,
        "finish_reason": data.get("stop_reason", "stop"),
        "model": cfg["id"],
        "raw_assistant_message": {
            "role": "assistant",
            "content": content_text,
            "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                for tc in tool_calls
            ] or None,
            "_anthropic_blocks": raw_blocks,
        },
    }
