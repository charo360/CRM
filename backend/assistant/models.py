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
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ── DeepSeek DSML tool-call parser ───────────────────────────────────────────
# DeepSeek sometimes outputs tool calls in its native <｜DSML｜> format
# inside the content field instead of the standard tool_calls JSON field.
# This parser extracts them and converts to OpenAI-compatible format.

_DSML_BLOCK_RE = re.compile(
    r"<｜+DSML｜+tool_calls>(.*?)</｜+DSML｜+tool_calls>",
    re.DOTALL,
)
_DSML_INVOKE_RE = re.compile(
    r'<｜+DSML｜+invoke\s+name=["\']([^"\']+)["\']>(.*?)</｜+DSML｜+invoke>',
    re.DOTALL,
)
_DSML_PARAM_RE = re.compile(
    r'<｜+DSML｜+parameter\s+name=["\']([^"\']+)["\'][^>]*>(.*?)</｜+DSML｜+parameter>',
    re.DOTALL,
)


def _parse_dsml_tool_calls(content: str) -> tuple[str, list]:
    """Extract DSML tool calls from content. Returns (clean_content, tool_calls)."""
    match = _DSML_BLOCK_RE.search(content)
    if not match:
        return content, []

    tool_calls = []
    block = match.group(1)
    for invoke in _DSML_INVOKE_RE.finditer(block):
        name = invoke.group(1).strip()
        params_text = invoke.group(2)
        args = {}
        for param in _DSML_PARAM_RE.finditer(params_text):
            args[param.group(1).strip()] = param.group(2).strip()
        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "name": name,
            "arguments": args,
        })

    # Remove the entire DSML block from content
    clean = _DSML_BLOCK_RE.sub("", content).strip()
    return clean, tool_calls


def _strip_dsml(text: str) -> str:
    """Strip any DSML markup from a text chunk (for streaming)."""
    return _DSML_BLOCK_RE.sub("", text).strip()

# ── Model registry ────────────────────────────────────────────────────────────
# id ↔ provider + upstream model name. id is what the UI passes.
MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
    "deepseek-v4-pro":         {"provider": "deepseek",  "model": "deepseek-v4-pro",           "label": "DeepSeek V4 Pro"},
    "deepseek-v4-flash":       {"provider": "deepseek",  "model": "deepseek-v4-flash",         "label": "DeepSeek V4 Flash (fast)"},
    "claude-sonnet-4.6":       {"provider": "anthropic", "model": "claude-sonnet-4-6",         "label": "Claude Sonnet 4.6"},
    "claude-3.5-sonnet":       {"provider": "anthropic", "model": "claude-3-5-sonnet-latest",  "label": "Claude 3.5 Sonnet"},
    "grok-4.3":                {"provider": "grok",      "model": "grok-4.3",                  "label": "Grok 4.3"},
    "grok-4-0709":             {"provider": "grok",      "model": "grok-4-0709",               "label": "Grok 4 (0709)"},
}

DEFAULT_MODEL = os.environ.get("ASSISTANT_DEFAULT_MODEL", "deepseek-v4-pro")


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
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run one round of chat completion with tool-calling enabled.

    `messages` follow OpenAI format: {role, content, tool_calls?, tool_call_id?}.
    `tools` is a list of OpenAI tool specs: {type:"function", function:{name, description, parameters}}.
    `attachments` (optional) is a list of documents to pass natively when the
        provider supports it (Anthropic). Each item: {kind, mime_type, filename, b64}.
    Returns: {content, tool_calls:[{id,name,arguments}], finish_reason, model, raw}.

    Fallback chain: if the primary provider times out or returns 5xx, automatically
    retries on the next available provider so a single vendor outage doesn't take
    down the whole assistant.
    """
    cfg = resolve_model(model_id)
    provider = cfg["provider"]

    # Build fallback chain: primary first, then alternatives in priority order
    _FALLBACK_CHAIN = [
        ("deepseek", "deepseek-chat"),
        ("openai",   "gpt-4o-mini"),
        ("grok",     "grok-3-mini"),
        ("anthropic","claude-haiku-4-5-20251001"),
    ]
    providers_to_try = [cfg] + [
        {"provider": p, "model": m}
        for p, m in _FALLBACK_CHAIN
        if p != provider and os.environ.get({"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY",
                                              "grok": "GROK_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(p, ""))
    ]

    last_exc: Exception = RuntimeError("No providers available")
    for attempt_cfg in providers_to_try:
        try:
            p = attempt_cfg["provider"]
            if p in ("openai", "deepseek", "grok"):
                return await _call_openai_compatible(attempt_cfg, messages, tools, temperature, timeout)
            if p == "anthropic":
                return await _call_anthropic(attempt_cfg, messages, tools, temperature, timeout, attachments=attachments)
        except (httpx.TimeoutException, httpx.HTTPStatusError, KeyError, ValueError, RuntimeError) as exc:
            if attempt_cfg is not providers_to_try[-1]:
                logger.warning("[models] provider %s failed (%s), trying fallback", attempt_cfg["provider"], exc)
                last_exc = exc
                continue
            raise
        except Exception as exc:
            logger.warning("[models] provider %s unexpected error (%s), trying fallback", attempt_cfg.get("provider"), exc)
            if attempt_cfg is not providers_to_try[-1]:
                last_exc = exc
                continue
            raise

    raise last_exc


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
        if r.status_code >= 400:
            logger.error("[models] %s chat/completions %s: %s", provider, r.status_code, r.text[:500])
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

    # DeepSeek sometimes puts tool calls in DSML format inside content instead
    # of the standard tool_calls field — parse and promote them.
    raw_content = msg.get("content") or ""
    if not tool_calls and "<｜" in raw_content and "DSML" in raw_content and "tool_calls" in raw_content:
        raw_content, dsml_calls = _parse_dsml_tool_calls(raw_content)
        if dsml_calls:
            logger.debug("[models] promoted %d DSML tool call(s) from content", len(dsml_calls))
            tool_calls = dsml_calls

    return {
        "content": raw_content,
        "tool_calls": tool_calls,
        "finish_reason": choice.get("finish_reason", "stop"),
        "model": cfg["id"],
        "raw_assistant_message": msg,
    }


# ── Anthropic ─────────────────────────────────────────────────────────────────
async def _call_anthropic(
    cfg: Dict[str, str],
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    temperature: float,
    timeout: float,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    key = os.environ["ANTHROPIC_API_KEY"]

    # Anthropic wants system separate + content blocks.
    system_text = ""
    a_messages: List[Dict[str, Any]] = []
    i = 0
    while i < len(messages):
        m = messages[i]
        role = m["role"]
        if role == "system":
            system_text = (system_text + "\n\n" + (m.get("content") or "")).strip()
            i += 1
            continue
        if role == "tool":
            # Batch ALL consecutive tool results into one user message —
            # Anthropic forbids consecutive user messages.
            tool_results: List[Dict[str, Any]] = []
            while i < len(messages) and messages[i]["role"] == "tool":
                tm = messages[i]
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tm["tool_call_id"],
                    "content": tm.get("content") or "",
                })
                i += 1
            a_messages.append({"role": "user", "content": tool_results})
            continue
        if role == "assistant" and m.get("tool_calls"):
            i += 1
            blocks: List[Dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                # Support both OpenAI-format ({id, function:{name, arguments}})
                # and the internal flat format ({id, name, arguments}).
                if "function" in tc:
                    fn = tc["function"] or {}
                    tc_name = fn.get("name", "")
                    raw_args = fn.get("arguments")
                    if isinstance(raw_args, str):
                        try:
                            tc_input = json.loads(raw_args) if raw_args else {}
                        except Exception:
                            tc_input = {}
                    else:
                        tc_input = raw_args or {}
                else:
                    tc_name = tc.get("name", "")
                    tc_input = tc.get("arguments") or {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id") or f"call_{len(blocks)}",
                    "name": tc_name,
                    "input": tc_input,
                })
            a_messages.append({"role": "assistant", "content": blocks})
            continue
        a_messages.append({"role": role, "content": m.get("content") or ""})
        i += 1

    # Attach documents/images natively to the FIRST user message (one-shot).
    # Only done on the fresh turn; subsequent tool-use loops don't re-attach.
    if attachments:
        attach_blocks: List[Dict[str, Any]] = []
        for a in attachments:
            if not a.get("b64"):
                continue
            if a.get("kind") == "image":
                attach_blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": a["mime_type"], "data": a["b64"]},
                })
            elif a.get("kind") == "pdf":
                attach_blocks.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": a["b64"]},
                    "title": a.get("filename") or "document.pdf",
                })
        if attach_blocks:
            # Find last user message and prepend attachment blocks
            for i in range(len(a_messages) - 1, -1, -1):
                if a_messages[i]["role"] == "user":
                    existing = a_messages[i].get("content")
                    text_block = (
                        [{"type": "text", "text": existing}] if isinstance(existing, str) else list(existing)
                    )
                    a_messages[i] = {"role": "user", "content": attach_blocks + text_block}
                    break

    # Convert OpenAI tool spec → Anthropic tool spec
    a_tools = [{
        "name": t["function"]["name"],
        "description": t["function"].get("description", ""),
        "input_schema": t["function"]["parameters"],
    } for t in tools]

    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": a_messages,
        "max_tokens": 8192,
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


# ── Streaming entrypoint ───────────────────────────────────────────────────────
async def stream_reply(
    *,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model_id: Optional[str] = None,
    temperature: float = 0.2,
    timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
    """Stream the final reply tokens from the LLM after all tool calls are done.

    Yields raw text chunks as they arrive from the provider.
    This should be called only for the *final* assistant reply (no tool calls expected).
    """
    cfg = resolve_model(model_id)
    provider = cfg["provider"]

    if provider in ("openai", "deepseek", "grok"):
        async for chunk in _stream_openai_compatible(cfg, messages, tools, temperature, timeout):
            yield chunk
    elif provider == "anthropic":
        async for chunk in _stream_anthropic(cfg, messages, tools, temperature, timeout):
            yield chunk
    else:
        raise RuntimeError(f"Unsupported provider for streaming: {provider}")


async def _stream_openai_compatible(
    cfg: Dict[str, str],
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    temperature: float,
    timeout: float,
) -> AsyncGenerator[str, None]:
    provider = cfg["provider"]
    base = _OAI_COMPATIBLE_BASE[provider]
    key = os.environ[_OAI_KEY_ENV[provider]]

    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "none"  # final reply only — no more tool calls

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        ) as resp:
            resp.raise_for_status()
            # Buffer for DSML blocks that span multiple chunks.
            # DSML blocks start with <｜ and end with </｜+DSML｜+tool_calls>.
            # We accumulate from the first <｜ and only yield once the closing
            # tag has arrived (or the buffer is suspiciously large).
            _dsml_buf = ""
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})
                    text = delta.get("content") or ""
                    if not text:
                        continue

                    _dsml_buf += text

                    # Fast path: no DSML start character in buffer → yield all
                    if "<｜" not in _dsml_buf:
                        yield _dsml_buf
                        _dsml_buf = ""
                        continue

                    # There's a <｜ in the buffer — could be DSML
                    start = _dsml_buf.find("<｜")
                    # Yield everything before the potential DSML start
                    if start > 0:
                        yield _dsml_buf[:start]
                        _dsml_buf = _dsml_buf[start:]

                    # Check if we have a complete DSML block
                    if _DSML_BLOCK_RE.search(_dsml_buf):
                        cleaned = _DSML_BLOCK_RE.sub("", _dsml_buf).strip()
                        if cleaned:
                            yield cleaned
                        _dsml_buf = ""
                    elif len(_dsml_buf) > 4000:
                        # Safety: buffer too large, give up and emit stripped
                        cleaned = _DSML_BLOCK_RE.sub("", _dsml_buf).strip()
                        if cleaned:
                            yield cleaned
                        _dsml_buf = ""
                    # else: keep accumulating — block not yet complete
                except Exception:
                    continue

            # Flush any remaining buffer (e.g. partial DSML or trailing text)
            if _dsml_buf:
                cleaned = _DSML_BLOCK_RE.sub("", _dsml_buf).strip()
                if cleaned:
                    yield cleaned


async def _stream_anthropic(
    cfg: Dict[str, str],
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    temperature: float,
    timeout: float,
) -> AsyncGenerator[str, None]:
    key = os.environ["ANTHROPIC_API_KEY"]

    system_text = ""
    a_messages: List[Dict[str, Any]] = []
    j = 0
    while j < len(messages):
        m = messages[j]
        role = m["role"]
        if role == "system":
            system_text = (system_text + "\n\n" + (m.get("content") or "")).strip()
            j += 1
            continue
        if role == "tool":
            tool_results: List[Dict[str, Any]] = []
            while j < len(messages) and messages[j]["role"] == "tool":
                tm = messages[j]
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tm["tool_call_id"],
                    "content": tm.get("content") or "",
                })
                j += 1
            a_messages.append({"role": "user", "content": tool_results})
            continue
        if role == "assistant" and m.get("tool_calls"):
            j += 1
            blocks: List[Dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                if "function" in tc:
                    fn = tc["function"] or {}
                    raw_args = fn.get("arguments")
                    tc_input = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else (raw_args or {})
                    blocks.append({"type": "tool_use", "id": tc.get("id") or "call_0", "name": fn.get("name", ""), "input": tc_input})
                else:
                    blocks.append({"type": "tool_use", "id": tc.get("id") or "call_0", "name": tc.get("name", ""), "input": tc.get("arguments") or {}})
            a_messages.append({"role": "assistant", "content": blocks})
            continue
        a_messages.append({"role": role, "content": m.get("content") or ""})
        j += 1

    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": a_messages,
        "max_tokens": 8192,
        "temperature": temperature,
        "stream": True,
    }
    if system_text:
        payload["system"] = system_text

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        text = (data.get("delta") or {}).get("text") or ""
                        if text:
                            yield text
                except Exception:
                    continue
