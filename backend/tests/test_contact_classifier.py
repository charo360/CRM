"""Coverage for what the contact classifier is allowed to treat as evidence.

The auto-reply answers "Hello" with "What are you looking for today? Browse our
products". Reading that back turned every greeting into a shopping
conversation - the classifier being persuaded by its own output.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contact_classifier import _is_owner_authored  # noqa: E402


def test_an_auto_reply_is_not_the_business_speaking():
    assert _is_owner_authored(
        {"direction": "outgoing", "send_context": "auto_reply"}
    ) is False


def test_zilos_own_notifications_are_not_evidence_either():
    """Digests and motivational notes are Zilo writing to the owner."""
    for context in ("digest", "motivation", "broadcast"):
        assert _is_owner_authored(
            {"direction": "outgoing", "send_context": context}
        ) is False, context


def test_a_message_the_owner_typed_counts():
    assert _is_owner_authored(
        {"direction": "outgoing", "send_context": "manual"}
    ) is True
    assert _is_owner_authored(
        {"direction": "outgoing", "send_context": "product_send"}
    ) is True


def test_older_sends_without_a_context_are_treated_as_the_owners():
    """Manual sends predate send_context; excluding them would lose real signal."""
    assert _is_owner_authored({"direction": "outgoing"}) is True


def test_what_the_contact_said_is_always_evidence():
    assert _is_owner_authored({"direction": "incoming"}) is True
    assert _is_owner_authored(
        {"direction": "incoming", "send_context": "auto_reply"}
    ) is True


def test_the_real_conversation_leaves_almost_nothing_to_judge():
    """The flagged thread: one greeting, then Zilo talking to itself."""
    thread = [
        {"direction": "incoming", "content": "Hello"},
        {"direction": "outgoing", "send_context": "auto_reply",
         "content": "Hi there! What are you looking for today? Browse our products"},
        {"direction": "outgoing", "send_context": "auto_reply",
         "content": "Which category would you like to explore? Electronics, Clothing"},
    ]
    kept = [m for m in thread if _is_owner_authored(m)]
    assert kept == [{"direction": "incoming", "content": "Hello"}]

    # And a lone greeting is not enough to classify anyone.
    incoming = [m for m in kept if m["direction"] == "incoming"]
    assert not any(len(str(m["content"]).split()) >= 3 for m in incoming)
