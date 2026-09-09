"""The API must be able to describe itself.

/openapi.json returned 500 in production. The cause was a Pydantic model
defined inside the function that registers its route: FastAPI resolves
annotations against module globals, and with `from __future__ import
annotations` every annotation is a string, so the model became an
unresolvable ForwardRef. FastAPI then treated the body model as a query
parameter — so the endpoint rejected its own JSON — and building the schema
raised, which took /openapi.json down for all 842 paths.

Importing the app is safe here: schedulers start on FastAPI's startup
event, which importing does not fire.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def spec():
    from server import app
    return app.openapi()


def test_the_schema_builds_at_all(spec):
    assert spec["paths"], "no paths documented"


def test_every_route_is_documented(spec):
    # A single bad annotation takes the whole schema down, so this is really
    # a check that no route has one.
    assert len(spec["paths"]) > 500, f"only {len(spec['paths'])} paths — something dropped out"


def test_a_body_model_is_not_mistaken_for_query_parameters(spec):
    path = next((p for p in spec["paths"] if p.endswith("/email-marketing/generate-image")), None)
    assert path, "generate-image route is missing"
    post = spec["paths"][path]["post"]
    assert "requestBody" in post, "the model is being read as query params again"
    assert not post.get("parameters"), post.get("parameters")
