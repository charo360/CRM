"""Coverage for deciding whether the auto-reply answers a contact at all.

The V2 engine answers everyone as a shop. On one account that meant 6,313
contacts imported from the owner's own phone book — family included — would
each get sold to if they ever messaged.

The two mistakes are not equally bad, and these tests hold that line: going
quiet on a real customer loses a sale silently, so silence needs confidence,
while a greeting that could come from either gets answered.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contact_qualifier import (  # noqa: E402
    LOOKS_PERSONAL,
    OWNER_MARKED_PERSONAL,
    qualify,
)


def incoming(*texts):
    return [{"direction": "incoming", "content": t} for t in texts]


# ── the owner's own decision wins ────────────────────────────────────────

def test_the_owner_marking_someone_personal_stops_the_ai():
    reply, verdict, reason = qualify({"is_personal": True}, "how much is the hoodie?")
    assert reply is False
    assert verdict == "personal"
    assert reason == OWNER_MARKED_PERSONAL


def test_a_known_customer_is_always_answered():
    reply, verdict, _ = qualify(
        {"is_personal": False, "contact_type": "KNOWN_CUSTOMER"},
        "habari yako, long time",
    )
    assert reply is True
    assert verdict == "customer"


# ── a customer must never be met with silence ────────────────────────────

def test_business_talk_is_answered_however_it_is_written():
    for text in (
        "how much is the hoodie?",
        "Bei ya tshirt ni ngapi?",
        "uko na size 40?",
        "nataka kuorder mbili",
        "can I pay on delivery?",
        "nitumie hiyo picha ya hoodie",
    ):
        reply, verdict, _ = qualify(None, text)
        assert reply is True, text
        assert verdict == "customer", text


def test_a_bare_greeting_is_answered_because_it_could_be_either():
    # "Niaje" is identical from a customer and a cousin. Answering is the
    # recoverable mistake; silence is not.
    for text in ("Niaje", "Hi", "sasa", "Vipi", "Hello", "?"):
        reply, verdict, _ = qualify(None, text)
        assert reply is True, text
        assert verdict == "unclear", text


def test_one_friendly_line_alone_is_not_enough_to_go_quiet():
    reply, verdict, _ = qualify(None, "how are you")
    assert reply is True
    assert verdict == "unclear"


def test_business_talk_anywhere_in_the_history_keeps_the_ai_on():
    # A customer who bought last week and now sends "how are you" is still a
    # customer, not a friend.
    reply, verdict, _ = qualify(
        None, "how are you", incoming("Niaje", "bei ya hoodie ni ngapi?")
    )
    assert reply is True
    assert verdict == "customer"


# ── a friend must not be sold to ─────────────────────────────────────────

def test_clearly_personal_talk_stops_the_ai():
    reply, verdict, reason = qualify(
        None, "tuonane later", incoming("habari yako", "long time bro")
    )
    assert reply is False
    assert verdict == "personal"
    assert reason == LOOKS_PERSONAL


def test_two_personal_signals_in_one_message_are_enough():
    reply, verdict, _ = qualify(None, "habari yako my brother, long time")
    assert reply is False
    assert verdict == "personal"


def test_family_and_occasions_read_as_personal():
    reply, _, _ = qualify(None, "happy birthday mama, love you")
    assert reply is False


# ── the awkward middle ───────────────────────────────────────────────────

def test_a_personal_opener_that_turns_commercial_is_answered():
    # Plenty of real customers open with small talk before getting to it.
    reply, verdict, _ = qualify(
        None, "anyway how much for the cap?", incoming("habari yako", "long time")
    )
    assert reply is True
    assert verdict == "customer"


def test_missing_customer_and_empty_history_do_not_crash():
    for hist in (None, []):
        reply, verdict, _ = qualify(None, "", hist)
        assert reply is True
        assert verdict == "unclear"


def test_a_pattern_of_endearment_reads_personal():
    # Real conversations on this account: "Hello bb" then "Thx bb".
    reply, verdict, _ = qualify(None, "Thx bb", incoming("Hello bb"))
    assert reply is False
    assert verdict == "personal"


def test_one_endearment_alone_still_gets_answered():
    reply, verdict, _ = qualify(None, "Hello bb")
    assert reply is True
    assert verdict == "unclear"


def test_baby_clothes_are_not_mistaken_for_an_endearment():
    # A clothes shop sells baby clothes; silence here would cost a sale.
    reply, verdict, _ = qualify(None, "do you have baby clothes?")
    assert reply is True
    assert verdict == "customer"
