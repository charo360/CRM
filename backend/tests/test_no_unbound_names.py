"""No route may use a name it never binds.

DELETE /customers/{id} read `business_id` twice and never assigned it. There
is no module-level `business_id`, so every attempt to delete a customer
raised NameError and returned 500 — a guaranteed crash, not an intermittent
one, and invisible until someone tried it.

Nothing catches this: Python only raises at the moment the line runs, the
route had no test, and the name is spelled the same as the one every other
handler uses correctly.

This walks the syntax tree instead. A name loaded inside a function must be
a parameter, assigned somewhere in that function, bound by an enclosing
function, a module-level name, or a builtin.
"""
import ast
import builtins
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

BUILTINS = set(dir(builtins))


def _module_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.Try, ast.If)):
            for inner in ast.walk(node):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    for alias in inner.names:
                        names.add((alias.asname or alias.name).split(".")[0])
                elif isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
                    names.add(inner.id)
    return names


def _bound_in(fn):
    """Every name this function binds, by any means."""
    bound = {a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs}
    if fn.args.vararg:
        bound.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        bound.add(fn.args.kwarg.arg)
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)
    return bound


# The ids that carry a tenant. Getting one of these wrong either crashes or,
# worse, reads another business's data.
WATCHED = {"business_id", "user_id", "customer_id", "owner_id", "tenant_id", "tid"}


def _offenders(path: Path):
    # utf-8-sig: one routes.py carries a byte-order mark. Python itself
    # reads it fine; ast.parse chokes on the U+FEFF unless it is stripped.
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    module = _module_names(tree)
    scopes = {}  # function node -> names bound by it or any ancestor

    def walk(node, inherited):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bound = inherited | _bound_in(child)
                scopes[child] = bound
                walk(child, bound)
            else:
                walk(child, inherited)

    walk(tree, module | BUILTINS)

    bad = []
    for fn, bound in scopes.items():
        for node in ast.walk(fn):
            if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                    and node.id in WATCHED and node.id not in bound):
                bad.append(f"{path.name}:{node.lineno} {fn.name}() reads '{node.id}' unbound")
    return sorted(set(bad))


PY_FILES = [p for p in BACKEND.rglob("*.py")
            if "tests" not in p.parts and ".venv" not in p.parts and "__pycache__" not in p.parts]


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: p.name)
def test_no_handler_reads_a_tenant_id_it_never_bound(path):
    offenders = _offenders(path)
    assert not offenders, "\n".join(offenders)
