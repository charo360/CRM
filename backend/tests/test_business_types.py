"""Every business type the app offers must be fully wired.

The app's picker lists 20 types. Each one needs menu rules, greeting rules,
and a response format that only offers actions its catalog can support —
offering a booking to a type whose services are never loaded asks the model
to invent the thing being booked.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoreply.context_loader import _supports_bookings  # noqa: E402
from autoreply.prompt_builder import build_system_prompt  # noqa: E402

# Exactly the list in frontend/components/BusinessKnowledgeModal.tsx
APP_TYPES = [
    "general", "retail", "wholesale", "restaurant", "food", "bakery", "grocery",
    "salon", "spa", "services", "repair", "cleaning", "fitness", "events",
    "healthcare", "rental", "hotel", "support", "creator", "tech",
]

PRODUCTS = [{"id": "p1", "name": "Item", "price": 1000}]
SERVICES = [{"id": "s1", "name": "Service", "price": 500}]


def prompt(btype):
    return build_system_prompt(
        business_config={"name": "T", "owner_name": "S", "type": btype, "currency": "KES"},
        products=PRODUCTS, services=SERVICES, mini_state={},
    )


def test_every_type_the_app_offers_builds_a_prompt():
    for btype in APP_TYPES:
        text = prompt(btype)
        assert len(text) > 2000, f"{btype} produced a suspiciously short prompt"


def test_no_type_is_offered_a_booking_without_its_services():
    # "support" was in the response-format booking set but not in the
    # context loader's booking types, so services were never loaded and the
    # model was asked to book something it could not see.
    for btype in APP_TYPES:
        if "create_booking" in prompt(btype):
            assert _supports_bookings(btype), (
                f"{btype} is offered create_booking but its services never load"
            )


def test_support_is_inquiry_only():
    text = prompt("support")
    assert "create_booking" not in text
    assert "create_order" not in text
    assert "tag_customer" in text, "it must still be able to tag and escalate"
    assert "notify_owner" in text


def test_an_unset_business_type_can_do_both():
    # 22 of 27 live accounts have never set a type. Defaulting them to retail
    # left a salon unable to take a booking at all.
    text = build_system_prompt(
        business_config={"name": "T", "owner_name": "S", "currency": "KES"},
        products=PRODUCTS, services=SERVICES, mini_state={},
    )
    assert "create_order" in text
    assert "create_booking" in text
