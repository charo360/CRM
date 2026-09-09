"""A broadcast must reach the audience the owner was shown, and no one else.

GET /customers leaves out contacts synced off the phone. Every broadcast sender
queried {"user_id": business_id} with no such filter, so the count on screen and
the people who got the message came from different populations. On live data one
account's screen said 0 recipients while a send to "all customers" would have
dialled 5,025 numbers; another showed 1 and would have sent 820.

These tests pin the shared definition, and then check statically that no sender
grows its own copy of the query again -- which is how the four copies that
diverged got there in the first place.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from customer_audience import (  # noqa: E402
    VISIBLE_CUSTOMER,
    audience_query,
    visible_customer_query,
)


# ---------------------------------------------------------------- the rule

def _matches(query, doc):
    """Evaluate the small subset of Mongo these queries actually use."""
    for key, cond in query.items():
        if key == "$and":
            if not all(_matches(c, doc) for c in cond):
                return False
        elif key == "$or":
            if not any(_matches(c, doc) for c in cond):
                return False
        elif isinstance(cond, dict):
            if "$in" in cond and doc.get(key) not in cond["$in"]:
                return False
            if "$ne" in cond and doc.get(key) == cond["$ne"]:
                return False
            if "$exists" in cond and (key in doc) != cond["$exists"]:
                return False
        else:
            value = doc.get(key)
            if isinstance(value, list):
                if cond not in value:
                    return False
            elif value != cond:
                return False
    return True


SYNCED_CONTACT = {"_id": "c1", "user_id": "b", "is_customer": False,
                  "auto_created": True, "tags": ["New"]}
REAL_CUSTOMER = {"_id": "c2", "user_id": "b", "is_customer": True,
                 "tags": ["New", "VIP"]}
LEGACY_CUSTOMER = {"_id": "c3", "user_id": "b", "tags": ["New"]}  # predates the flag


def test_a_broadcast_to_all_skips_contacts_synced_off_the_phone():
    q = audience_query("b", "all")
    assert not _matches(q, SYNCED_CONTACT), "would message a non-customer contact"
    assert _matches(q, REAL_CUSTOMER)
    assert _matches(q, LEGACY_CUSTOMER), "records predating is_customer must survive"


def test_tag_filters_also_skip_synced_contacts():
    # Every synced contact carries the "New" tag, so this is the filter that
    # leaked the most: "New Customers" was really "everyone in the phone".
    q = audience_query("b", "new")
    assert not _matches(q, SYNCED_CONTACT)
    assert _matches(q, REAL_CUSTOMER)

    vip = audience_query("b", "vip")
    assert _matches(vip, REAL_CUSTOMER)
    assert not _matches(vip, LEGACY_CUSTOMER), "not tagged VIP"


def test_explicitly_chosen_people_are_honoured_as_chosen():
    """Picking names by hand is the consent; do not second-guess it."""
    q = audience_query("b", "custom", ["c1"])
    assert _matches(q, SYNCED_CONTACT)
    assert not _matches(q, REAL_CUSTOMER)


def test_an_empty_custom_selection_reaches_nobody():
    """Fail closed. The catalog sender used to fall through to everyone."""
    q = audience_query("b", "custom", [])
    for doc in (SYNCED_CONTACT, REAL_CUSTOMER, LEGACY_CUSTOMER):
        assert not _matches(q, doc)


def test_the_audience_is_a_subset_of_the_list_the_owner_sees():
    """The whole point: never send to someone the customer list omits."""
    shown = visible_customer_query("b")
    for filt in ("all", "new", "returning", "vip"):
        q = audience_query("b", filt)
        for doc in (SYNCED_CONTACT, REAL_CUSTOMER, LEGACY_CUSTOMER):
            if _matches(q, doc):
                assert _matches(shown, doc), (
                    f"filter {filt!r} would message {doc['_id']}, "
                    "who never appears in the owner's customer list"
                )


def test_the_query_survives_a_caller_adding_its_own_or():
    """Composed under $and so a sibling $or cannot displace it."""
    q = audience_query("b", "all")
    q["$or"] = [{"tags": "Returning"}, {"tags": "VIP"}]
    assert not _matches(q, SYNCED_CONTACT)


def test_server_get_customers_agrees_with_the_shared_predicate():
    """One definition. get_customers had its own copy; digest_service a third."""
    src = (BACKEND / "server.py").read_text(encoding="utf-8-sig", errors="replace")
    handler = src[src.index('@api_router.get("/customers"'):][:2000]
    assert '"is_customer": True' in handler and '"auto_created"' in handler, (
        "get_customers no longer filters on is_customer/auto_created -- if its "
        "definition of a customer changed, customer_audience must change with it"
    )


# ------------------------------------------------------- no fifth copy

# Every place that picks who receives a message. Listed by name on purpose: a
# rename must fail here loudly rather than quietly stop being checked.
SENDERS = {
    "create_broadcast",
    "resend_broadcast",
    "execute_broadcast_automations",
    "broadcast_catalog",
}


def _functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


@pytest.mark.parametrize("name", sorted(SENDERS))
def test_each_sender_builds_its_audience_from_the_shared_helper(name):
    src = (BACKEND / "server.py").read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(src)
    fns = [f for f in _functions(tree) if f.name == name]
    assert fns, (
        f"{name} no longer exists in server.py. If it was renamed, rename it "
        "in SENDERS too -- otherwise this check silently stops running."
    )
    for fn in fns:
        body = ast.get_source_segment(src, fn) or ""
        if "db.customers.find" not in body and "db.customers.count" not in body:
            continue
        assert "audience_query" in body, (
            f"{name} queries customers without customer_audience.audience_query; "
            "it will drift from the count the owner is shown"
        )
        assert not re.search(r'query\s*=\s*\{\s*["\']user_id["\']\s*:', body), (
            f"{name} builds a raw {{'user_id': ...}} audience again"
        )
