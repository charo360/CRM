"""The line under a product the owner sends a customer.

Every product sent from the app ended "Reply *Yes* or *Order* to buy!",
identical for all 20 business types — so a salon asked a customer to buy a
haircut, a hotel to buy a room, and a repair shop to buy a callout.

The ProductActionsModal was built to make these buttons configurable per
business, but its endpoint was never written and nothing renders it. This is
the smaller fix that removes the actual damage: the verb follows the trade.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoreply.prompt_builder import get_action_verb, product_call_to_action  # noqa: E402


def test_shops_order():
    for btype in ("retail", "wholesale", "restaurant", "food", "bakery", "grocery"):
        assert get_action_verb(btype) == "order", btype


def test_services_are_booked_not_bought():
    for btype in ("salon", "spa", "services", "repair", "cleaning",
                  "fitness", "events", "healthcare", "tech"):
        assert get_action_verb(btype) == "book", btype


def test_rooms_and_rentals_are_reserved():
    for btype in ("hotel", "rental"):
        assert get_action_verb(btype) == "reserve", btype


def test_an_unknown_type_still_says_something_sensible():
    for btype in ("", None, "something-new"):
        assert get_action_verb(btype) == "order"


def test_the_line_reads_as_an_instruction():
    line = product_call_to_action("salon")
    assert "Reply" in line and "book" in line
    assert "buy" not in line


def test_every_app_business_type_has_a_verb():
    # The app's picker, from BusinessKnowledgeModal.tsx.
    for btype in ("general", "retail", "wholesale", "restaurant", "food", "bakery",
                  "grocery", "salon", "spa", "services", "repair", "cleaning",
                  "fitness", "events", "healthcare", "rental", "hotel", "support",
                  "creator", "tech"):
        assert get_action_verb(btype) in ("order", "book", "reserve", "get"), btype
