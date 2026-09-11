"""What the owner types on their own phone reaches the app.

The session subscribed to the gateway's "message" event, which is incoming
only. A reply the owner sent from the phone therefore never reached Zilo: on
the live account not one such message had ever been stored, and a chat like
Kibe's showed the customer's eight messages and nothing in between. The
webhook handler already knew how to store the owner's messages; they simply
never arrived.

Arriving is not enough on its own. A phone-typed reply also has to step the AI
back, the way a manual reply from the app already did, or the AI keeps
answering on top of the owner. And the switch makes the gateway echo Zilo's
own sends back too, which must never be stored a second time.
"""
import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SERVER = (BACKEND / "server.py").read_text(encoding="utf-8-sig", errors="replace")
WAHA = (BACKEND / "waha_service.py").read_text(encoding="utf-8-sig", errors="replace")


def _fn(src, name):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found")


def test_new_sessions_subscribe_to_every_message(monkeypatch):
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://example.test")
    import waha_service

    events = waha_service.WahaWhatsAppService._webhook_config(None)["webhooks"][0]["events"]
    assert "message.any" in events, "the owner's own phone messages are never delivered"
    # Both together would deliver every incoming message twice.
    assert "message" not in events


def test_the_route_accepts_message_any():
    body = _fn(SERVER, "waha_webhook")
    assert 'event in ("message", "message.any")' in body, (
        "message.any would fall into the ignored branch and be dropped"
    )


def test_a_phone_typed_reply_pauses_the_ai():
    handler = _fn(SERVER, "evolution_webhook")
    block = handler[handler.index("Auto-reply skipped for {from_number}") - 900:]
    block = block[:block.index('return {"status": "ok"}')]
    assert "_redis_set_ts(" in block and "owner_reply" in block, (
        "the owner's phone reply is stored but the AI keeps answering over them"
    )


def test_the_ai_can_never_answer_the_owner_themselves():
    """An owner message must return before the auto-reply section."""
    handler = _fn(SERVER, "evolution_webhook")
    own = handler.index("Auto-reply skipped for {from_number}")
    ret = handler.index('return {"status": "ok"}', own)
    engine = handler.index("from autoreply.engine import process_message")
    assert ret < engine, "an owner message could reach the auto-reply engine"


def test_an_unmatched_echo_of_our_own_send_is_not_stored():
    handler = _fn(SERVER, "evolution_webhook")
    assert 'parsed.get("source") == "api"' in handler
    guard = handler.index('parsed.get("source") == "api"')
    store = handler.index("await db.messages.insert_one(msg_doc)")
    assert guard < store, "the echo guard must come before the message is stored"


def test_the_parser_carries_the_source():
    assert '"source": str(data.get("source") or "")' in _fn(WAHA, "handle_incoming_message")


def test_an_already_linked_session_can_be_updated_one_at_a_time():
    refresh = _fn(WAHA, "refresh_session_webhooks")
    assert "client.put(" in refresh
    assert "_session_config_for_user" in refresh, (
        "the update must reuse the same config as linking, egress proxy included"
    )
    endpoint = _fn(SERVER, "whatsapp_refresh_events")
    assert '("owner", "manager")' in endpoint, "anyone could restart the business's WhatsApp"
    assert "refresh_session_webhooks" in endpoint
