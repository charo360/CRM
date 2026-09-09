"""A customer's profile must show that customer's bookings.

GET /bookings declared only `status` and `limit`. The customer profile has
always called /bookings?customer_id=..., and FastAPI drops a query parameter
the handler does not declare — silently, with no error. So every customer's
profile showed the whole business's booking count as if it were theirs.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def get_bookings_params():
    from server import app
    spec = app.openapi()
    path = next(p for p in spec["paths"] if p.endswith("/bookings"))
    op = spec["paths"][path]["get"]
    return {p["name"] for p in (op.get("parameters") or []) if p.get("in") == "query"}


def test_bookings_can_be_filtered_to_one_customer(get_bookings_params):
    assert "customer_id" in get_bookings_params, (
        "the customer profile sends it; if it is not declared, FastAPI drops it "
        "and the profile shows every booking in the business"
    )


def test_the_existing_filters_are_still_there(get_bookings_params):
    assert {"status", "limit"} <= get_bookings_params
