"""Generate a short, smart title for a new conversation.

Called in the background after the first reply so the conversation list
shows something meaningful instead of a raw 60-char message truncation.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_PROMPT = (
    "Given the user's first message and the assistant's first reply, "
    "produce a short conversation title of 4-7 words. "
    "No punctuation at the end. No quotes. Just the title.\n\n"
    "User: {user_msg}\n"
    "Assistant: {reply}\n\n"
    "Title:"
)


async def generate_title(user_msg: str, reply: str, timeout: float = 6.0) -> Optional[str]:
    """Return a short title or None if generation fails / key missing."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return _fallback(user_msg)

    prompt = _PROMPT.format(
        user_msg=user_msg[:300],
        reply=reply[:400],
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20,
                    "temperature": 0.4,
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()
            # Strip surrounding quotes if the model added them
            title = raw.strip('"\'').strip()
            return title[:100] if title else _fallback(user_msg)
    except Exception as e:
        logger.debug(f"[titler] generate_title failed: {e}")
        return _fallback(user_msg)


def _fallback(user_msg: str) -> str:
    """Truncate to the first natural break ≤ 60 chars."""
    s = (user_msg or "New chat").strip()
    for delim in ("?", "!", ".", "\n"):
        idx = s.find(delim)
        if 8 <= idx <= 60:
            return s[: idx + 1]
    return s[:60] if len(s) > 60 else s
