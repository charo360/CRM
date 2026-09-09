"""Coverage for reading Anthropic's reply out of the API response.

Claude 4.7 and later return a thinking block before the answer, so the
response content is ``[{"type": "thinking", ...}, {"type": "text", ...}]``.
Both callers took ``content[0]["text"]``, which raised KeyError on every
single reply. The auto-reply engine caught that and sent the customer
"Sorry, I'm having a little trouble right now" instead, while the API call
itself had succeeded with HTTP 200 and a perfectly good answer.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeAsyncClient:
    """Stands in for httpx.AsyncClient, returning a canned Anthropic reply."""

    payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        return FakeResponse(FakeAsyncClient.payload)


THINKING_FIRST = {
    "content": [
        {"type": "thinking", "thinking": "The customer asked for a price."},
        {"type": "text", "text": "Niaje! T-shirt ni KES 1,200."},
    ]
}
TEXT_ONLY = {"content": [{"type": "text", "text": "Niaje! T-shirt ni KES 1,200."}]}


@pytest.fixture
def fake_httpx(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


@pytest.mark.asyncio
async def test_engine_reads_past_a_thinking_block(fake_httpx):
    from autoreply.engine import _call_claude_http

    fake_httpx.payload = THINKING_FIRST
    reply = await _call_claude_http(
        {"key": "k", "endpoint": "https://example.invalid"},
        "claude-sonnet-5",
        "system",
        [{"role": "user", "content": "bei ya tshirt?"}],
    )
    assert reply == "Niaje! T-shirt ni KES 1,200."


@pytest.mark.asyncio
async def test_engine_still_reads_a_plain_text_reply(fake_httpx):
    from autoreply.engine import _call_claude_http

    fake_httpx.payload = TEXT_ONLY
    reply = await _call_claude_http(
        {"key": "k", "endpoint": "https://example.invalid"},
        "claude-sonnet-5",
        "system",
        [{"role": "user", "content": "hi"}],
    )
    assert reply == "Niaje! T-shirt ni KES 1,200."


@pytest.mark.asyncio
async def test_ai_service_reads_past_a_thinking_block(fake_httpx):
    from ai_service import AIMessageDrafter

    fake_httpx.payload = THINKING_FIRST
    drafter = AIMessageDrafter.__new__(AIMessageDrafter)
    reply = await drafter._call_claude(
        {"key": "k", "endpoint": "https://example.invalid"},
        "claude-sonnet-5",
        "what is the price?",
    )
    assert reply == "Niaje! T-shirt ni KES 1,200."
