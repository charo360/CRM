"""Coverage for where a notification to the business owner is delivered.

A business can sign up with one number and run WhatsApp on another. Sending to
the sign-up number still succeeds - it lands in a chat nobody opens - so
getting this wrong fails silently, which is how daily messages were being
delivered to a test number instead of the owner.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whatsapp_service import owner_whatsapp_number  # noqa: E402


def test_the_linked_whatsapp_number_wins():
    """The real case: signed up with a test number, WhatsApp on a real one."""
    user = {
        "phone_number": "+16505553434",                      # sign-up / OTP
        "whatsapp": {"phone_number": "12026995029"},          # actually linked
    }
    assert owner_whatsapp_number(user) == "12026995029"


def test_the_signup_number_is_used_when_nothing_is_linked():
    assert owner_whatsapp_number({"phone_number": "+254712345678"}) == "+254712345678"
    assert owner_whatsapp_number(
        {"phone_number": "+254712345678", "whatsapp": {}}
    ) == "+254712345678"


def test_a_blank_linked_number_does_not_beat_a_real_one():
    user = {"phone_number": "+254712345678", "whatsapp": {"phone_number": ""}}
    assert owner_whatsapp_number(user) == "+254712345678"


def test_no_number_at_all_is_empty_rather_than_a_crash():
    assert owner_whatsapp_number({}) == ""
    assert owner_whatsapp_number({"whatsapp": {"phone_number": None}}) == ""
