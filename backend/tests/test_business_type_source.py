"""The business type lives in settings, not at the top level of the user.

Every real account on this deployment has business_type: None on the user
document and the actual value -- retail, creator -- in settings.business_type.
Code that reads only the top-level field therefore gets nothing, silently:
there is no error, the prompt simply never mentions what the business sells.

That was true of both classifiers, which decide whether an inbound contact is
a customer, and of the broadcast drafter's fallback for the three composers
that send no type of their own.
"""
import ast
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Every place that resolves a business type from a user document.
READERS = [
    ("contact_classifier.py", None),
    ("email_classifier.py", None),
    ("server.py", "generate_broadcast_message"),
    ("autoreply/context_loader.py", None),
    ("social_draft_service.py", None),
]


def _source(path, fn=None):
    src = (BACKEND / path).read_text(encoding="utf-8-sig", errors="replace")
    if fn is None:
        return src
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{fn} not found in {path}")


@pytest.mark.parametrize("path,fn", READERS, ids=[r[0] for r in READERS])
def test_the_settings_type_is_consulted(path, fn):
    body = _source(path, fn)
    if 'user.get("business_type")' not in body:
        pytest.skip(f"{path} does not read business_type from a user document")
    assert 'settings' in body and 'business_type' in body, (
        f"{path} reads user['business_type'], which is None on every real "
        "account here, without consulting settings.business_type"
    )


def test_the_two_classifiers_no_longer_read_only_the_top_level():
    """These decide whether somebody is a customer; the trade is context."""
    for path in ("contact_classifier.py", "email_classifier.py"):
        src = _source(path)
        # The bare form, with nothing else on the line, is the bug.
        assert 'btype = user.get("business_type") or ""' not in src, (
            f"{path} still resolves the business type from the field that is "
            "always empty"
        )
