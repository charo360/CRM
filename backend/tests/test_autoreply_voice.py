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
