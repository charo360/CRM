"""What kind of shop each business type gets on the web.

"general" means the merchant said they sell both goods and services, and its
AI takes bookings in WhatsApp — but the storefront gave it a cart and no
booking path, so the same business behaved two different ways depending on
where the customer met it. Restaurants already did both, with tables.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storefront_routes import _shop_mode  # noqa: E402


def mode(btype):
    return _shop_mode({"business_knowledge": {"business_type": btype}})


def test_a_shop_selling_goods_only_has_no_booking_path():
    for btype in ("retail", "wholesale", "grocery", "creator"):
        m = mode(btype)
        assert m["mode"] == "shop", btype
        assert m["takes_bookings"] is False, btype


def test_a_booking_business_has_no_cart():
    for btype in ("salon", "spa", "repair", "healthcare", "hotel", "rental"):
        m = mode(btype)
        assert m["mode"] == "booking", btype
        assert m["takes_bookings"] is True, btype


def test_a_restaurant_keeps_its_cart_and_its_tables():
    m = mode("restaurant")
    assert m["mode"] == "shop"
    assert m["takes_bookings"] is True
    assert m["takes_table_bookings"] is True


def test_general_now_does_both():
    m = mode("general")
    assert m["mode"] == "shop", "it still sells goods from a cart"
    assert m["takes_bookings"] is True, "and can now be booked, like its AI already allows"
    assert m["takes_table_bookings"] is False, "but it books an item, not a table"


def test_stays_are_told_apart_from_appointments():
    assert mode("hotel")["booking_kind"] == "stay"
    assert mode("rental")["booking_kind"] == "stay"
    assert mode("salon")["booking_kind"] == "appointment"


def test_the_storefront_and_the_ai_agree_on_who_takes_bookings():
    # The mismatch this fixes: one of them booking while the other cannot.
    from autoreply.prompt_builder import build_system_prompt

    APP_TYPES = ["general", "retail", "wholesale", "restaurant", "food", "bakery",
                 "grocery", "salon", "spa", "services", "repair", "cleaning",
                 "fitness", "events", "healthcare", "rental", "hotel", "creator", "tech"]
    for btype in APP_TYPES:
        prompt = build_system_prompt(
            business_config={"name": "T", "owner_name": "S", "type": btype, "currency": "KES"},
            products=[{"id": "p", "name": "A", "price": 1}], services=[], mini_state={},
        )
        ai_books = "create_booking" in prompt
        shop_books = mode(btype)["takes_bookings"]
        if ai_books:
            assert shop_books, f"{btype}: the AI books but the storefront offers no way to"
