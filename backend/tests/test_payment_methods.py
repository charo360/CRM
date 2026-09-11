"""Customers are only offered ways to pay that they can actually use.

Signup pre-fills "Bank Transfer" and "Card" with nothing attached, and owners
add "Airtel Money" without the number. All of those were offered to customers
as payment options, so a customer could be told "you can pay by Bank Transfer"
with no account to pay into. On the live accounts: StocksIntels offered Airtel
Money with no number, and two more offered Bank Transfer and Card with nothing.
"""
import ast
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from payment_methods import (  # noqa: E402
    is_payable, payment_method_line, payment_method_lines, usable_payment_methods,
)


# ------------------------------------------------------------- the rule

def test_a_method_with_details_is_kept():
    assert payment_method_lines([{"name": "M-Pesa", "details": "0796148903"}]) == [
        "M-Pesa: 0796148903"]


@pytest.mark.parametrize("name", ["Bank Transfer", "Card", "Airtel Money",
                                  "M-Pesa", "PayPal", "Visa/Card", "Stripe"])
def test_a_method_with_nothing_attached_is_dropped(name):
    assert not is_payable({"name": name, "details": ""})
    assert not is_payable({"name": name, "details": "   "})


@pytest.mark.parametrize("name", ["Cash", "cash", " Cash ", "Cash on Delivery",
                                  "Pay on delivery", "COD", "Pay on pickup"])
def test_cash_needs_no_details(name):
    assert is_payable({"name": name, "details": ""})


def test_chipper_cash_is_not_cash():
    """The word "cash" in a name does not make it cash."""
    assert not is_payable({"name": "Chipper Cash", "details": ""})
    assert is_payable({"name": "Chipper Cash", "details": "@lexshop"})


def test_a_multi_field_method_counts_its_fields():
    """A Paybill keeps its numbers in fields, not in details."""
    paybill = {"name": "Paybill", "details": "",
               "fields": [{"label": "Business No", "value": "400200"},
                          {"label": "Account", "value": "LEX"}]}
    assert is_payable(paybill)
    assert payment_method_line(paybill) == "Paybill: Business No: 400200, Account: LEX"

    empty = {"name": "Paybill", "fields": [{"label": "Business No", "value": ""}]}
    assert not is_payable(empty)


def test_legacy_plain_strings_follow_the_same_rule():
    """Older accounts store names as bare strings, which carry no details."""
    assert payment_method_lines(["Cash", "Mobile Money", "Bank Transfer"]) == ["Cash"]


def test_the_owners_order_is_kept():
    raw = [{"name": "PayPal", "details": "a@b.com"}, {"name": "Card", "details": ""},
           {"name": "M-Pesa", "details": "0711"}]
    assert [m["name"] for m in usable_payment_methods(raw)] == ["PayPal", "M-Pesa"]


@pytest.mark.parametrize("raw", [None, [], "", {"name": "Card"}])
def test_nothing_usable_is_an_empty_list(raw):
    """Empty means the reply prompt says the owner will share details."""
    assert payment_method_lines(raw) == []


def test_a_single_method_not_in_a_list_still_works():
    assert payment_method_lines({"name": "M-Pesa", "details": "0711"}) == ["M-Pesa: 0711"]


# ------------------------------------- every customer-facing path uses it

def _source(path):
    return (BACKEND / path).read_text(encoding="utf-8-sig", errors="replace")


def _fn(path, name):
    src = _source(path)
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found in {path}")


@pytest.mark.parametrize("path,fn", [
    ("autoreply/context_loader.py", "_build_business_config"),
    ("agents/sales_agent.py", "_payment_methods_to_bullets"),
    ("agents/payment_agent.py", None),
])
def test_each_customer_facing_formatter_filters(path, fn):
    body = _fn(path, fn) if fn else _source(path)
    assert "payment_method_lines" in body or "usable_payment_methods" in body, (
        f"{path} builds payment options for customers without the filter, so "
        "a method with no details is still offered as a way to pay"
    )


def test_both_server_paths_filter():
    src = _source("server.py")
    assert "Payment methods accepted:" in src
    block = src[src.index("Payment methods accepted:") - 700:src.index("Payment methods accepted:")]
    assert "payment_method_lines" in block, (
        "the knowledge text given to the agents still lists methods with no details"
    )
    assert "_payment_methods_ctx = _usable_pm(" in src, (
        "the structured list handed to the payment and sales agents is unfiltered"
    )


def test_the_owners_own_screen_keeps_empty_entries():
    """Business Knowledge is where they fill the details in; hiding the
    empty ones there would make them impossible to complete."""
    body = _fn("server.py", "get_business_knowledge")
    assert "usable_payment_methods" not in body
    assert "payment_method_lines" not in body
