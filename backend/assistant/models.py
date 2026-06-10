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
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False

_retry_decorator = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)


# ── DeepSeek DSML tool-call parser ───────────────────────────────────────────
# DeepSeek sometimes outputs tool calls in its native <｜DSML｜> format
# inside the content field instead of the standard tool_calls JSON field.
# This parser extracts them and converts to OpenAI-compatible format.

_DSML_BLOCK_RE = re.compile(
    r"<[｜|]+DSML[｜|]+\s*tool_calls>(.*?)</[｜|]+DSML[｜|]+\s*tool_calls>",
    re.DOTALL,
)
_DSML_INVOKE_RE = re.compile(
    r'<[｜|]+DSML[｜|]+\s*invoke\s+name=["\']([^"\']+)["\'][^>]*>(.*?)</[｜|]+DSML[｜|]+\s*invoke>',
    re.DOTALL,
)
_DSML_PARAM_RE = re.compile(
    r'<[｜|]+DSML[｜|]+\s*parameter\s+name=["\']([^"\']+)["\'][^>]*>(.*?)</[｜|]+DSML[｜|]+\s*parameter>',
    re.DOTALL,
)


def _parse_dsml_tool_calls(content: str) -> tuple[str, list]:
    """Extract DSML tool calls from content. Returns (clean_content, tool_calls)."""
    tool_calls = []
    block_match = _DSML_BLOCK_RE.search(content)
    search_text = block_match.group(1) if block_match else content

    for invoke in _DSML_INVOKE_RE.finditer(search_text):
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

    clean = _DSML_BLOCK_RE.sub("", content)
    clean = _DSML_INVOKE_RE.sub("", clean)
    clean = _strip_dsml(clean)
    return clean, tool_calls


def _strip_dsml(text: str) -> str:
    """Strip any DSML markup from a text chunk (for streaming)."""
    text = _DSML_BLOCK_RE.sub("", text)
    text = _DSML_INVOKE_RE.sub("", text)
    # ASCII-pipe variants sometimes leak through
    text = re.sub(r"<\|+\s*DSML\s*\|+[^>]*>.*?(?:</\|+\s*DSML\s*\|+[^>]*>|$)", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()

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


# ── Persistent HTTP client (shared across all non-streaming LLM calls) ────────
# Creating a new httpx.AsyncClient per request incurs TCP + TLS setup overhead
# (~50-200ms). A shared client with connection keepalive eliminates that.
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(
            timeout=120.0,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )
    return _HTTP_CLIENT


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
        {"provider": p, "model": m, "id": m}
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


@_retry_decorator
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

    client = _get_http_client()
    start_time = time.perf_counter()
    r = await client.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if r.status_code >= 400:
        logger.error("[models] %s chat/completions %s: %s", provider, r.status_code, r.text[:500])
    r.raise_for_status()
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    data = r.json()

    # Log per-provider latency span to llm_call_log for SLA analysis
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    llm_call_logger = logging.getLogger("llm_call_log")
    llm_call_logger.info(json.dumps({
        "provider": provider,
        "model": cfg.get("model"),
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }))

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
    if not tool_calls and "DSML" in raw_content and ("tool_calls" in raw_content or "invoke" in raw_content):
        raw_content, dsml_calls = _parse_dsml_tool_calls(raw_content)
        if dsml_calls:
            logger.debug("[models] promoted %d DSML tool call(s) from content", len(dsml_calls))
            tool_calls = dsml_calls
            msg = {**msg, "content": raw_content}

    raw_content = _strip_dsml(raw_content)

    return {
        "content": raw_content,
        "tool_calls": tool_calls,
        "finish_reason": choice.get("finish_reason", "stop"),
        "model": cfg.get("id") or cfg.get("model", ""),
        "raw_assistant_message": msg,
    }


# ── Anthropic ─────────────────────────────────────────────────────────────────
def _merge_user_anthropic_content(prev: Any, cur: Any) -> Any:
    """Merge two user message contents (Anthropic rejects consecutive user turns)."""
    if isinstance(prev, str) and isinstance(cur, str):
        return f"{prev}\n\n{cur}".strip()
    if isinstance(prev, list) and isinstance(cur, str):
        return prev + [{"type": "text", "text": cur}]
    if isinstance(prev, str) and isinstance(cur, list):
        return [{"type": "text", "text": prev}] + cur
    if isinstance(prev, list) and isinstance(cur, list):
        return prev + cur
    return cur or prev


def _merge_assistant_anthropic_content(prev: Any, cur: Any) -> Any:
    if isinstance(prev, list) and isinstance(cur, list):
        return prev + cur
    if isinstance(prev, str) and isinstance(cur, str):
        return prev + "\n\n" + cur
    if isinstance(prev, str):
        return [{"type": "text", "text": prev}] + (cur if isinstance(cur, list) else [{"type": "text", "text": cur}])
    if isinstance(cur, str):
        return (prev if isinstance(prev, list) else [{"type": "text", "text": prev}]) + [{"type": "text", "text": cur}]
    return cur or prev


def _merge_consecutive_anthropic_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Anthropic requires alternating roles — merge consecutive user/assistant messages."""
    if not messages:
        return messages
    merged: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if merged and merged[-1].get("role") == role:
            prev_content = merged[-1].get("content")
            cur_content = m.get("content")
            if role == "user":
                merged[-1]["content"] = _merge_user_anthropic_content(prev_content, cur_content)
            elif role == "assistant":
                merged[-1]["content"] = _merge_assistant_anthropic_content(prev_content, cur_content)
            continue
        merged.append(dict(m))
    # First message must be user (Anthropic API rule).
    while merged and merged[0].get("role") != "user":
        merged.pop(0)
    return merged


@_retry_decorator
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

    a_messages = _merge_consecutive_anthropic_messages(a_messages)

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

    _LONG_FORM_SIGNALS = (
        "business plan", "proposal", "contract", "press release",
        "pitch deck", "presentation", "executive summary", "investment memo",
        "brochure", "slide deck", "powerpoint",
    )
    _recent_text = " ".join(str(m.get("content", "")) for m in messages[-4:]).lower()
    _max_tok = 4096 if any(s in _recent_text for s in _LONG_FORM_SIGNALS) else 2048
    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": a_messages,
        "max_tokens": _max_tok,
        "temperature": temperature,
    }
    if system_text:
        payload["system"] = system_text
    if a_tools:
        payload["tools"] = a_tools

    client = _get_http_client()
    start_time = time.perf_counter()
    r = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if r.status_code >= 400:
        logger.error("[models] anthropic messages %s: %s", r.status_code, r.text[:1000])
    r.raise_for_status()
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    data = r.json()

    # Log per-provider latency span to llm_call_log for SLA analysis
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    llm_call_logger = logging.getLogger("llm_call_log")
    llm_call_logger.info(json.dumps({
        "provider": "anthropic",
        "model": cfg.get("model"),
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }))

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
        "model": cfg.get("id") or cfg.get("model", ""),
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

    _FALLBACK_CHAIN = [
        ("deepseek", "deepseek-chat"),
        ("openai",   "gpt-4o-mini"),
        ("grok",     "grok-3-mini"),
        ("anthropic", "claude-haiku-4-5-20251001"),
    ]
    providers_to_try = [cfg] + [
        {"provider": p, "model": m, "id": m}
        for p, m in _FALLBACK_CHAIN
        if p != provider and os.environ.get({"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY",
                                              "grok": "GROK_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(p, ""))
    ]

    last_exc = None
    for attempt_cfg in providers_to_try:
        try:
            p = attempt_cfg["provider"]
            if attempt_cfg is providers_to_try[0]:
                try:
                    if p in ("openai", "deepseek", "grok"):
                        async for chunk in _stream_openai_compatible(attempt_cfg, messages, tools, temperature, timeout):
                            yield chunk
                    elif p == "anthropic":
                        async for chunk in _stream_anthropic(attempt_cfg, messages, tools, temperature, timeout):
                            yield chunk
                    return
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                    logger.warning("[models] stream primary provider %s failed (%s), using fallback non-stream", p, e)
                    last_exc = e
            else:
                resp = await chat_with_tools(
                    messages=messages, tools=tools,
                    model_id=attempt_cfg.get("id") or attempt_cfg.get("model"),
                    temperature=temperature, timeout=timeout
                )
                content = resp.get("content", "")
                if content:
                    yield content
                return
        except Exception as e:
            logger.warning("[models] stream fallback provider %s failed (%s)", attempt_cfg.get("provider"), e)
            last_exc = e
            continue

    if last_exc:
        raise last_exc


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

    a_messages = _merge_consecutive_anthropic_messages(a_messages)

    _LONG_FORM_SIGNALS = (
        "business plan", "proposal", "contract", "press release",
        "pitch deck", "presentation", "executive summary", "investment memo",
        "brochure", "slide deck", "powerpoint",
    )
    _recent_text = " ".join(str(m.get("content", "")) for m in messages[-4:]).lower()
    _max_tok = 4096 if any(s in _recent_text for s in _LONG_FORM_SIGNALS) else 2048
    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": a_messages,
        "max_tokens": _max_tok,
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
            if resp.status_code >= 400:
                body = (await resp.aread())[:1000]
                logger.error("[models] anthropic stream %s: %s", resp.status_code, body)
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
