"""The owner's phone replies are read from where NOWEB actually puts the chat.

With the session subscribed to message.any, the gateway delivered four replies
the owner typed on their phone -- from_me true, source "app" -- and every one
was dropped before it could be stored. The recorded payloads showed why: a
direct chat carries no ``to`` and no ``chatId``, only ``from``, and ``from`` is
the other person's chat in both directions. The parser read ``to`` for the
owner's messages, got nothing, and discarded them.
"""
import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from waha_service import _chat_of  # noqa: E402

OWN = "12026995029"
KIBE_LID = "264037577302174@lid"


def test_an_owner_message_with_no_to_uses_from():
    """The shape the live gateway sends for a reply typed on the phone."""
    data = {"fromMe": True, "from": KIBE_LID, "body": "Getting it for you", "source": "app"}
    assert _chat_of(data, True, OWN) == KIBE_LID


def test_to_is_still_preferred_when_an_engine_sends_it():
    data = {"fromMe": True, "from": f"{OWN}@c.us", "to": "254790904240@c.us"}
    assert _chat_of(data, True, OWN) == "254790904240@c.us"


def test_chat_id_wins_when_present():
    data = {"fromMe": True, "chatId": KIBE_LID, "from": f"{OWN}@c.us", "to": "x@c.us"}
    assert _chat_of(data, True, OWN) == KIBE_LID


def test_the_owners_own_number_is_never_the_conversation():
    data = {"fromMe": True, "to": f"{OWN}@c.us", "from": "254790904240@c.us"}
    assert _chat_of(data, True, OWN) == "254790904240@c.us"


def test_incoming_messages_are_read_exactly_as_before():
    assert _chat_of({"fromMe": False, "from": KIBE_LID, "to": f"{OWN}@c.us"}, False, OWN) == KIBE_LID
    assert _chat_of({"fromMe": False, "chatId": "c@c.us", "from": KIBE_LID}, False, OWN) == "c@c.us"


def test_nothing_to_read_is_an_empty_chat():
    assert _chat_of({"fromMe": True}, True, OWN) == ""


def _fn(path, name):
    src = (BACKEND / path).read_text(encoding="utf-8-sig", errors="replace")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found in {path}")


def test_the_parser_uses_it():
    body = _fn("waha_service.py", "handle_incoming_message")
    assert "_chat_of(data, from_me" in body
    assert 'data.get("to") if from_me else data.get("from")' not in body.split("_payload_phone")[0], (
        "the parser still reads the chat from `to` for the owner's messages"
    )


def test_the_pause_covers_every_id_the_customer_writes_from():
    """The owner's reply may resolve only to the LID; the customer's to the phone."""
    body = _fn("server.py", "evolution_webhook")
    block = body[body.index("_pause_ids = {str(from_number)}"):]
    block = block[:block.index("Auto-reply skipped for {from_number}")]
    assert '"phone_number"' in block and '"lid_jid"' in block
    assert "for _pid in _pause_ids" in block
