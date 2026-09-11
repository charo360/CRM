"""The app is told whether a business can take payments before it asks.

Zilo's own Paystack pays out to Kenyan banks and M-Pesa, so a business
registered elsewhere is refused. The app used to check only whether the
platform was switched on at all -- a server-wide yes -- and so showed every
business the full M-Pesa and bank form. A business registered in the United
States filled it in, pressed save, and was refused with a message telling it to
"connect your own Paystack account", which the app has no way to do.

Nor was the refusal written down: it happened above the failure recorder, so
the attempt left no trace anywhere.
"""
import ast
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import paystack_routes  # noqa: E402

SRC = (BACKEND / "paystack_routes.py").read_text(encoding="utf-8-sig", errors="replace")


@pytest.fixture
def platform_on(monkeypatch):
    monkeypatch.setattr(paystack_routes, "platform_configured", lambda: True)


# ------------------------------------------------------------- the rule

@pytest.mark.parametrize("user", [
    {"country_code": "KE"},
    {"country_code": "ke"},
    {"country_code": "Kenya"},
    {"settings": {"country_code": "KE"}},
    {},  # nothing recorded: treated as Kenyan, as it always has been
])
def test_a_kenyan_business_is_eligible(platform_on, user):
    got = paystack_routes._platform_eligibility(user)
    assert got["eligible"] is True
    assert got["reason"] is None


@pytest.mark.parametrize("code,named", [
    ("US", "the United States"),
    ("KR", "South Korea"),
    ("NG", "Nigeria"),
    ("ZZ", "ZZ"),  # an unknown code still reads as a code, not as nothing
])
def test_a_business_elsewhere_is_told_where_it_is_registered(platform_on, code, named):
    got = paystack_routes._platform_eligibility({"country_code": code})
    assert got["eligible"] is False
    assert named in got["reason"], got["reason"]
    assert got["country_code"] == code


def test_the_reason_never_points_at_an_option_the_app_lacks(platform_on):
    """There is no "own Paystack account" in the app to connect."""
    reason = paystack_routes._platform_eligibility({"country_code": "US"})["reason"]
    assert "own Paystack" not in reason
    assert "secret key" not in reason


def test_nothing_is_eligible_while_the_platform_is_off(monkeypatch):
    monkeypatch.setattr(paystack_routes, "platform_configured", lambda: False)
    got = paystack_routes._platform_eligibility({"country_code": "KE"})
    assert got["eligible"] is False
    assert got["reason"]


# ------------------------------------------ the app is told, and it's used

def _fn(name):
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SRC, node) or ""
    raise AssertionError(f"{name} not found")


def test_the_connection_endpoint_tells_the_app_per_business():
    body = _fn("paystack_get_connection")
    assert "_platform_eligibility(user)" in body
    for field in ("platform_eligible", "eligibility_reason", "country_code"):
        assert f'"{field}"' in body, f"/paystack/connection no longer returns {field}"


def test_the_refusal_is_recorded():
    """It used to happen above the recorder and leave no trace at all."""
    body = _fn("paystack_connect")
    refusal = body.index("if not secret_in_body and not use_platform:")
    try_block = body.index("        try:\n", refusal)
    between = body[refusal:try_block]
    assert "_record_connect_failure" in between, (
        "a business refused on eligibility leaves nothing behind to diagnose"
    )


def test_deliberate_refusals_inside_the_try_are_recorded_too():
    body = _fn("paystack_connect")
    assert "except HTTPException" in body, (
        "an unrecognised provider code is raised inside the try and escapes "
        "the recorder, since it is neither a ValueError nor a PaystackApiError"
    )


def test_the_app_checks_eligibility_before_showing_the_form():
    modal = (BACKEND.parent / "frontend" / "components" /
             "PaymentSetupModal.tsx").read_text(encoding="utf-8", errors="replace")
    assert "platform_eligible === false" in modal, (
        "the payout form is shown to businesses the server will refuse"
    )
    assert "platform_eligible !== false" in modal, (
        "the bank list is still loaded for a business that cannot connect"
    )


def test_an_ineligible_business_is_sent_to_the_manual_route():
    """Not a dead end: the notice says where manual payment details go,
    and offers a way there."""
    modal = (BACKEND.parent / "frontend" / "components" /
             "PaymentSetupModal.tsx").read_text(encoding="utf-8", errors="replace")
    notice = modal[modal.index("platform_eligible === false ?"):]
    notice = notice[:notice.index(") : (")]
    assert "Business Knowledge" in notice and "Payment Methods" in notice
    assert "onOpenBusinessKnowledge" in notice, "no way to get there from the notice"

    account = (BACKEND.parent / "frontend" / "app" / "(tabs)" /
               "account.tsx").read_text(encoding="utf-8", errors="replace")
    assert "onOpenBusinessKnowledge=" in account, (
        "the account screen never passes the callback, so the button never shows"
    )
