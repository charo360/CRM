"""See what the WhatsApp gateway actually sends, without reading anyone's messages.

After switching a session to "message.any", an owner's phone reply still did
not appear, and nothing anywhere said why. The gateway's payloads do not match
its documentation, and a message it never sends -- or one the parser drops --
left only a log line on the server. These two diagnostics answer the question
from the database instead: what is the session really subscribed to, and what
has the gateway really been sending.
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


def test_every_authenticated_webhook_leaves_a_record():
    body = _fn(SERVER, "waha_webhook")
    assert "db.waha_webhook_seen.update_one" in body
    # After the signature check, so a forged request cannot write it.
    assert body.index("compare_digest") < body.index("waha_webhook_seen")
    assert '"$slice": -40' in body, "the record must stay bounded"


def test_the_record_holds_no_message_text_or_numbers():
    body = _fn(SERVER, "waha_webhook")
    record = body[body.index("waha_webhook_seen"):body.index("upsert=True")]
    assert '"has_body": bool(provider_data.get("body"))' in record
    assert '"body":' not in record, "message text must not be stored in the diagnostic"
    assert "chat_kind" in record and '"chat":' not in record, (
        "only the kind of chat, never the number or id"
    )


def test_a_failed_record_never_breaks_delivery():
    body = _fn(SERVER, "waha_webhook")
    record = body[body.index("waha_webhook_seen") - 400:body.index("upsert=True") + 60]
    assert "except Exception:" in record


def test_the_subscription_can_be_read_without_a_restart():
    reader = _fn(WAHA, "session_webhook_events")
    assert "client.get(" in reader
    assert "client.put(" not in reader and "client.post(" not in reader, (
        "reading the subscription must never change or restart the session"
    )
    endpoint = _fn(SERVER, "whatsapp_session_events")
    assert '("owner", "manager")' in endpoint
    assert "session_webhook_events" in endpoint
    assert "refresh_session_webhooks" not in endpoint
