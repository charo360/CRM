"""Coverage for what a customer gets when the chosen provider is broken.

Picking Claude while Anthropic was out of credit sent every customer
"Sorry, I'm having a little trouble right now". The engine retried the
same dead model twice and then gave up: it only ever used the default
provider when the chosen one had no client configured at all, never when
a configured one started failing.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import autoreply.engine as engine  # noqa: E402

GOOD_JSON = (
    '{"reply": "Niaje! T-shirt ni KES 1,200.", "intent": "inquiry",'
    ' "sentiment": "neutral", "escalate": false, "escalate_reason": "",'
    ' "actions": [], "new_menu": null, "flow_update": null}'
)
MESSAGES = [{"role": "user", "content": "bei ya tshirt?"}]


class FakeDrafter:
    """Routes 'claude' to a Claude client and everything else to the default."""

    def _get_client_and_model(self, pref):
        if pref == "claude":
            return "claude", "claude-sonnet-5", {"key": "k"}
        return self._get_default_client_and_model()

    def _get_default_client_and_model(self):
        return "openai", "gpt-5.6-luna", object()


@pytest.fixture
def engine_with_fake_drafter(monkeypatch):
    monkeypatch.setattr(engine, "_get_drafter", lambda: FakeDrafter())
    return engine


@pytest.mark.asyncio
async def test_a_dead_provider_falls_back_instead_of_apologising(
    engine_with_fake_drafter, monkeypatch
):
    tried = []

    async def provider(client_type, client, model_name, system_prompt, messages):
        tried.append(model_name)
        if model_name.startswith("claude"):
            raise RuntimeError("Anthropic credit balance is too low")
        return GOOD_JSON

    monkeypatch.setattr(engine, "_call_provider", provider)
    out = await engine._call_ai_with_retry("system", MESSAGES, "claude")

    assert out["reply"] != engine.FALLBACK_REPLY
    assert out["reply"] == "Niaje! T-shirt ni KES 1,200."
    assert tried[-1] == "gpt-5.6-luna", tried


@pytest.mark.asyncio
async def test_unreadable_json_also_falls_back_to_the_default(
    engine_with_fake_drafter, monkeypatch
):
    tried = []

    async def provider(client_type, client, model_name, system_prompt, messages):
        tried.append(model_name)
        return "not json at all" if model_name.startswith("claude") else GOOD_JSON

    monkeypatch.setattr(engine, "_call_provider", provider)
    out = await engine._call_ai_with_retry("system", MESSAGES, "claude")

    assert out["reply"] == "Niaje! T-shirt ni KES 1,200."
    assert "gpt-5.6-luna" in tried


@pytest.mark.asyncio
async def test_the_default_failing_still_ends_in_the_safe_reply(
    engine_with_fake_drafter, monkeypatch
):
    # Nothing left to switch to, so the customer gets the apology rather
    # than an exception escaping into the webhook.
    tried = []

    async def provider(client_type, client, model_name, system_prompt, messages):
        tried.append(model_name)
        raise RuntimeError("everything is down")

    monkeypatch.setattr(engine, "_call_provider", provider)
    out = await engine._call_ai_with_retry("system", MESSAGES, "standard")

    assert out["reply"] == engine.FALLBACK_REPLY
    assert set(tried) == {"gpt-5.6-luna"}, tried


@pytest.mark.asyncio
async def test_it_does_not_switch_away_from_a_working_provider(
    engine_with_fake_drafter, monkeypatch
):
    tried = []

    async def provider(client_type, client, model_name, system_prompt, messages):
        tried.append(model_name)
        return GOOD_JSON

    monkeypatch.setattr(engine, "_call_provider", provider)
    out = await engine._call_ai_with_retry("system", MESSAGES, "claude")

    assert out["reply"] == "Niaje! T-shirt ni KES 1,200."
    assert tried == ["claude-sonnet-5"], tried
