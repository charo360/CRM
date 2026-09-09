"""Every AI method a route calls must actually exist on the drafter.

POST /ai/generate-broadcast-message called drafter.draft_broadcast_message().
That method was never written. Python only looks an attribute up when the line
runs, so nothing failed at import, no route was missing, and the app's own
error handler turned the AttributeError into a tidy HTTP 500 "Failed to
generate message". Four screens were dead -- Broadcast's write-with-AI, its
follow-up and recurring composers, and the Follow-ups note composer -- and the
only symptom was a toast.

Static analysis catches it in the shape it actually takes: a name assigned
from get_drafter() or AIMessageDrafter(), then called with an attribute that
the class does not define.
"""
import ast
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from ai_service import AIMessageDrafter  # noqa: E402

# How a drafter enters a scope.
FACTORIES = {"get_drafter", "AIMessageDrafter", "get_ai_service"}

PY_FILES = [
    p for p in BACKEND.rglob("*.py")
    if "tests" not in p.parts and ".venv" not in p.parts and "__pycache__" not in p.parts
]


def _factory_name(node):
    """The factory being called, if this expression builds a drafter."""
    call = node
    if isinstance(call, ast.Await):
        call = call.value
    if not isinstance(call, ast.Call):
        return None
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id if fn.id in FACTORIES else None
    if isinstance(fn, ast.Attribute):
        return fn.attr if fn.attr in FACTORIES else None
    return None


def _drafter_vars(tree):
    """Names bound to a drafter anywhere in the module."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _factory_name(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if _factory_name(node.value) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def _called_attrs(tree, names):
    """(attribute, line) for every call made on a drafter name."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        target = fn.value
        # get_drafter().draft_x(...) -- called straight off the factory
        if _factory_name(target) or (isinstance(target, ast.Name) and target.id in names):
            out.append((fn.attr, node.lineno))
    return out


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: p.name)
def test_every_drafter_call_resolves(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    names = _drafter_vars(tree)
    missing = [
        f"{path.name}:{line} calls drafter.{attr}() but AIMessageDrafter has no such method"
        for attr, line in _called_attrs(tree, names)
        if not hasattr(AIMessageDrafter, attr)
    ]
    assert not missing, "\n".join(sorted(set(missing)))


def test_the_broadcast_drafter_is_present_and_callable():
    """The specific method four screens depend on."""
    assert hasattr(AIMessageDrafter, "draft_broadcast_message")
    import inspect
    sig = inspect.signature(AIMessageDrafter.draft_broadcast_message)
    # The endpoint passes all four by keyword.
    for param in ("prompt", "business_type", "business_name", "model_pref"):
        assert param in sig.parameters, f"draft_broadcast_message lost the {param} parameter"
    assert inspect.iscoroutinefunction(AIMessageDrafter.draft_broadcast_message)
