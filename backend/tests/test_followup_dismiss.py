"""A Needs Attention suggestion can be removed without inventing an outcome.

Clearing an entry used to mean pressing Done and choosing from called, replied,
converted, no_answer, rescheduled or not_interested -- and that also wrote
last_owner_reply as though the owner had answered. For a suggestion that is
simply noise (a contact who is not really a customer, somebody already dealt
with in person) every one of those answers is untrue, and the untruth lands in
the field that decides who looks neglected and feeds the follow-up analytics.

So dismissing records nothing about the customer except that the owner does not
want to be prompted about them, and it lasts until they get in touch again.
"""
import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SRC = (BACKEND / "server.py").read_text(encoding="utf-8-sig", errors="replace")


def _fn(name, code_only=False):
    """The function's source. code_only drops the docstring.

    A docstring that explains what the code deliberately does not do will
    otherwise match a search for exactly that thing.
    """
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            if code_only:
                body = [n for n in node.body
                        if not (isinstance(n, ast.Expr)
                                and isinstance(n.value, ast.Constant)
                                and isinstance(n.value.value, str))]
                return "\n".join(ast.get_source_segment(SRC, n) or "" for n in body)
            return ast.get_source_segment(SRC, node) or ""
    raise AssertionError(f"{name} not found in server.py")


def test_the_endpoints_exist():
    assert '"/customers/{customer_id}/dismiss-followup"' in SRC, (
        "there is no way to take a suggestion off the list"
    )
    assert '"/customers/{customer_id}/undismiss-followup"' in SRC, (
        "a mistaken tap must be undoable"
    )


def test_dismissing_does_not_fake_a_reply():
    """Writing last_owner_reply would claim the owner answered them."""
    body = _fn("dismiss_followup_suggestion", code_only=True)
    for invented in ("last_owner_reply", "last_contacted", "followup_events"):
        assert invented not in body, (
            f"dismissing writes {invented}, which claims something about the "
            "customer that did not happen"
        )
    assert "followup_dismissed_at" in body


def test_dismissing_is_scoped_to_the_business():
    """One business must not be able to dismiss another's customer."""
    for name in ("dismiss_followup_suggestion", "undismiss_followup_suggestion"):
        body = _fn(name)
        assert "business_id" in body, f"{name} does not scope by business"
        assert "404" in body, f"{name} does not reject an unknown customer"


def test_the_suggestion_list_actually_filters_them_out():
    body = _fn("get_cold_customers")
    assert "_drop_dismissed_suggestions" in body, (
        "the list does not exclude dismissed suggestions, so they come back on "
        "the next refresh and the button looks broken"
    )
    # Order matters: filtering after the trim would let a dismissed row hold
    # one of the thirty slots and push a real suggestion off the end.
    filt = body.index("_drop_dismissed_suggestions")
    trim = body.index("result[:30]")
    assert filt < trim, "dismissed rows are filtered after the top-30 trim"


def test_a_dismissal_lifts_when_the_customer_writes_again():
    body = _fn("_effective_dismissed_ids")
    assert '"direction": "incoming"' in body, (
        "nothing brings a dismissed customer back, so somebody who messages "
        "after being waved away is never surfaced again"
    )


def test_the_filter_does_not_query_once_per_row():
    """The list holds thirty; a query each would be sixty round trips."""
    body = _fn("_effective_dismissed_ids")
    # One find for the dismissal times, one aggregate for the replies,
    # regardless of how many customers are being checked.
    assert body.count("db.customers.find") == 1
    assert body.count("db.messages.aggregate") == 1
    assert "for r in rows" in _fn("_drop_dismissed_suggestions"), (
        "expected a single pass over the rows"
    )


# ------------------------------ the list and the numbers above it agree

def test_the_counters_exclude_dismissed_customers_too():
    """Removing a row must move the figures sitting directly above it.

    The first version of this filtered the list only. The "7+ days" and
    "30+ days" chips carried on counting the dismissed customer, so removing a
    row changed nothing visible at the top of the screen and the button looked
    broken.
    """
    body = _fn("get_followup_suggestions")
    assert "_effective_dismissed_ids" in body, (
        "the header counts do not exclude dismissed customers, so they will "
        "disagree with the list they sit above"
    )
    # Every figure on that header, not just the first one.
    for figure in ("neglected_week", "neglected_month", "vip_neglected",
                   "new_no_followup"):
        assert figure in body, f"{figure} is no longer computed here"
    assert body.count("_not_hidden") >= 4, (
        "at least one of the four figures still counts dismissed customers"
    )


def test_there_is_one_definition_of_dismissed():
    """The list and the counts must not grow separate rules."""
    helper = _fn("_effective_dismissed_ids")
    assert '"direction": "incoming"' in helper

    consumer = _fn("_drop_dismissed_suggestions")
    assert "_effective_dismissed_ids" in consumer
    # The rule itself must live in one place, not be re-implemented.
    assert "followup_dismissed_at" not in consumer, (
        "the list has its own copy of the dismissal rule; it will drift from "
        "the counters' copy"
    )
