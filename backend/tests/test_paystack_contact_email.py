"""Coverage for the optional payout-updates email on Paystack setup.

Owners sign up by phone: all 26 on this database have no email on file, so
nothing can fill this in for them. Without it Paystack has no way to reach
a business about its own settlements, and the business hears about its
money only through Zilo. It is asked for, and it stays optional.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paystack_routes import _parse_subaccount_payload as parse  # noqa: E402

BASE = {
    "payout_type": "mobile_money",
    "settlement_bank": "MPESA",
    "account_number": "0712345678",
    "business_name": "Mo apparel",
}


def test_setup_still_works_with_no_email():
    # The selling point of this screen is "no Paystack login required".
    # Adding a required field would undo that.
    assert parse(BASE)["contact_email"] == ""


def test_an_email_is_normalised():
    assert parse({**BASE, "primary_contact_email": "  Sam@Shop.CO.KE "})["contact_email"] == "sam@shop.co.ke"


def test_the_field_is_accepted_under_the_names_a_client_might_send():
    for key in ("primary_contact_email", "contact_email", "email"):
        assert parse({**BASE, key: "a@b.com"})["contact_email"] == "a@b.com"


def test_a_malformed_address_is_refused_rather_than_sent_on():
    # Paystack would take it and then silently never reach anyone.
    for bad in ("notanemail", "a@b", "@b.com", "a b@c.com", "a@@b.com"):
        with pytest.raises(ValueError):
            parse({**BASE, "email": bad})


def test_the_other_required_fields_are_unchanged():
    for missing in ("settlement_bank", "account_number", "business_name"):
        body = {k: v for k, v in BASE.items() if k != missing}
        with pytest.raises(ValueError):
            parse(body)
