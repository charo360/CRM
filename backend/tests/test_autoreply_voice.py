"""Coverage for how the auto-reply is told to speak.

Built from a real transcript. A customer said "Hello" and got:

    "Hi there! What are you looking for today? Feel free to browse our products"
    "Which category would you like to explore? 1 Electronics 2 Clothing"
    "Currently, we don't have any products set up in the Electronics category."

Invitation, menu, dead end — and the last line tells a customer the shop is
unfinished. The prompt was instructing all three.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoreply.prompt_builder import _SHARED_ALWAYS, _SHARED_ORDER_BLOCK  # noqa: E402


def test_the_owner_is_the_one_speaking():
    """"The assistant for X" produces assistant language."""
    assert "WRITE LIKE THE OWNER" in _SHARED_ALWAYS
    assert "not like software" in _SHARED_ALWAYS.lower()


def test_the_shops_own_admin_is_never_the_customers_problem():
    lowered = _SHARED_ALWAYS.lower()
    assert "never describe the state of the business's own setup" in lowered
    assert "unfinished" in lowered


def test_it_is_told_not_to_narrate_or_restart():
    lowered = _SHARED_ALWAYS.lower()
    assert "never announce what you are doing" in lowered
    assert "do not restart" in lowered


def test_worked_examples_are_present_for_tone():
    """Abstract adjectives move tone far less than examples do."""
    assert "HOW AN OWNER WOULD PUT IT" in _SHARED_ALWAYS
    # Both the wrong and the right version, so the contrast is visible.
    assert "✗" in _SHARED_ALWAYS and "✓" in _SHARED_ALWAYS
    # The exact opener from the transcript is named as the wrong one.
    assert "What are you looking for today?" in _SHARED_ALWAYS


def test_a_menu_is_for_choosing_not_for_talking():
    assert "A menu is for choosing between real things" in _SHARED_ORDER_BLOCK
    assert "Never open with a menu" in _SHARED_ORDER_BLOCK


def test_the_empty_catalog_instruction_no_longer_announces_an_empty_shop():
    """The old prompt said, in as many words, to tell the customer to come back
    later because nothing was set up. That instruction is gone."""
    import inspect

    from autoreply import prompt_builder

    source = inspect.getsource(prompt_builder)
    assert "No products or services have been set up yet" not in source
    assert "No menu items have been set up yet" not in source
    # Replaced by an instruction to take the enquiry instead.
    assert "NO CATALOG IS LOADED" in source
    assert "ask what they are looking for" in source
    assert "notify_owner" in source


def test_the_examples_cannot_be_copied_by_a_real_business():
    """Concrete examples get reproduced word for word by any business in the
    same trade — two different garages sent an identical greeting when the
    examples used a garage. The examples now come from trades no customer of
    this product is likely to be in, so copying one is obviously wrong.
    """
    assert "piano tuner" in _SHARED_ALWAYS
    assert "beekeeper" in _SHARED_ALWAYS
    # The trades that actually use this product must not appear as ready-made
    # greetings to lift.
    for trade in ("garage:", "salon:", "bakery:"):
        assert trade not in _SHARED_ALWAYS


def test_the_software_openers_are_named_and_banned():
    """Removing the examples once produced "How can I assist you today?" from
    every business — blandness is the other failure mode, so it is banned by
    name rather than left to taste."""
    assert "How can I assist you today?" in _SHARED_ALWAYS
    assert "What can I help you with today?" in _SHARED_ALWAYS
    assert "what software says" in _SHARED_ALWAYS


def test_two_shops_in_one_trade_are_told_to_differ():
    assert "same line of work should not open with the same sentence" in _SHARED_ALWAYS


# ── Learning the owner's voice ─────────────────────────────────────────────

def test_only_messages_the_owner_typed_are_learned_from():
    """The auto-reply must never learn from its own output.

    That loop is not hypothetical: the contact classifier read this system's
    auto-replies back as evidence and flagged people who had only said "Hello"
    as customers. Learning tone the same way would drift the voice toward
    whatever it already produces, and nobody would see it happening.
    """
    import inspect

    from autoreply import context_loader

    source = inspect.getsource(context_loader._load_owner_voice)
    assert '"send_context": "manual"' in source
    assert '"direction": "outgoing"' in source


def test_the_owners_replies_outrank_the_written_guidance():
    from autoreply.prompt_builder import build_system_prompt

    prompt = build_system_prompt(
        business_config={"name": "Mo apparel", "owner_name": "Sam", "type": "retail"},
        products=[], services=[], mini_state={},
        owner_voice=["Niaje boss, tshirt ni 1200 tu. Unataka size gani?"],
    )
    assert "HOW YOU WRITE" in prompt
    assert "Niaje boss" in prompt
    assert "follow these — they are" in prompt
    # And it must not simply parrot them back.
    assert "Do not reuse the sentences themselves" in prompt


def test_nothing_is_added_when_the_owner_has_not_written_anything_yet():
    """A new account has no manual replies; the prompt must not carry an empty
    section implying it does."""
    from autoreply.prompt_builder import build_system_prompt

    prompt = build_system_prompt(
        business_config={"name": "Mo apparel", "type": "retail"},
        products=[], services=[], mini_state={}, owner_voice=[],
    )
    assert "HOW YOU WRITE" not in prompt
