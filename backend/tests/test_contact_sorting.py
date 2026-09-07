"""Coverage for how the Contacts tab orders its rows.

The sort keys are read out of server.py's source and executed in isolation:
importing the module itself would start schedulers against the shared
database, which a test must never do.
"""
import io
import re
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _load_sort_keys():
    """Execute just the two sort helpers from server.py, nothing else."""
    source = io.open(BACKEND / "server.py", encoding="utf-8").read()
    wanted = []
    for name in ("_contact_name_key", "_contact_activity_key"):
        match = re.search(
            rf"^def {name}\(.*?(?=^def |^class |^@)", source, re.S | re.M
        )
        assert match, f"{name} not found in server.py"
        wanted.append(match.group(0))
    namespace = {"datetime": datetime}
    exec("\n\n".join(wanted), namespace)
    return namespace["_contact_name_key"], namespace["_contact_activity_key"]


NAME_KEY, ACTIVITY_KEY = _load_sort_keys()


def test_names_sort_alphabetically_with_symbols_last():
    contacts = [
        {"name": "+254712345678"},
        {"name": "zoe"},
        {"name": "Adam"},
        {"name": "1st Supplier"},
        {"name": "brenda"},
    ]
    ordered = [c["name"] for c in sorted(contacts, key=NAME_KEY)]
    assert ordered == ["Adam", "brenda", "zoe", "+254712345678", "1st Supplier"]


def test_a_nameless_contact_does_not_break_the_sort():
    contacts = [{"name": ""}, {"name": None}, {"name": "Ada"}, {}]
    ordered = sorted(contacts, key=NAME_KEY)
    assert ordered[0]["name"] == "Ada"      # real names come first
    assert len(ordered) == 4                # and nothing is lost


def test_recent_orders_by_last_contact_then_by_when_added():
    contacts = [
        {"name": "old chat", "last_contacted": datetime(2026, 1, 1),
         "created_at": datetime(2025, 1, 1)},
        {"name": "new chat", "last_contacted": datetime(2026, 9, 6),
         "created_at": datetime(2025, 1, 1)},
        # Never spoken to, but added recently - it should not sink to the
        # bottom below a contact last spoken to years ago.
        {"name": "just added", "created_at": datetime(2026, 5, 1)},
    ]
    ordered = [c["name"] for c in sorted(contacts, key=ACTIVITY_KEY, reverse=True)]
    assert ordered == ["new chat", "just added", "old chat"]


def test_a_contact_with_no_dates_sorts_last_rather_than_crashing():
    contacts = [
        {"name": "has date", "last_contacted": datetime(2026, 1, 1)},
        {"name": "no dates"},
        {"name": "bad date", "last_contacted": "not-a-datetime"},
    ]
    ordered = [c["name"] for c in sorted(contacts, key=ACTIVITY_KEY, reverse=True)]
    assert ordered[0] == "has date"
    assert set(ordered[1:]) == {"no dates", "bad date"}
