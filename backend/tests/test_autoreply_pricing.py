"""An order's price comes from the catalog, never from the model.

The AI writes real orders. If the figure in its JSON were trusted, a
mistyped price — or a customer who talks the model into one — would become a
real order at that amount. The public shop already refuses to trust a price
sent by a browser; the same rule has to hold here.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from autoreply.action_handler import _create_order  # noqa: E402

CATALOG = [
    {"_id": "p1", "user_id": "biz-1", "name": "Latte", "price": 500.0},
    {"_id": "p2", "user_id": "biz-1", "name": "Beans 1kg", "price": 2400.0, "discount_price": 1900.0},
]


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()
    def sort(self, *a, **k): return self
    async def to_list(self, n=None): return self._docs


class _Products:
    def find(self, query, *a, **k):
        wanted = (query.get("_id") or {}).get("$in") or []
        return _Cursor([d for d in CATALOG if d["_id"] in wanted and d["user_id"] == query.get("user_id")])
    async def find_one(self, *a, **k): return None


class _Inserted:
    def __init__(self, doc_id): self.inserted_id = doc_id


class _Orders:
    def __init__(self): self.docs = []
    async def insert_one(self, doc):
        self.docs.append(doc)
        return _Inserted(doc.get("_id", f"o{len(self.docs)}"))
    async def find_one(self, *a, **k): return None
    async def update_one(self, *a, **k): return None
    async def count_documents(self, *a, **k): return 0


class _DB:
    def __init__(self):
        self.products = _Products()
        self.orders = _Orders()
    def __getattr__(self, name): return _Orders()


def _order(items):
    db = _DB()
    asyncio.run(_create_order(db, {"items": items}, "biz-1", "cust-1", "KES"))
    return db.orders.docs[0]


def test_a_price_the_model_invented_is_ignored():
    # The model claims a 2,400 bag of beans costs 1.
    order = _order([{"product_name": "Beans 1kg", "product_id": "p2", "quantity": 1, "unit_price": 1}])
    line = order["items"][0]
    assert line["unit_price"] == 1900.0, "the catalog's discounted price must win"
    assert order["total_amount"] == 1900.0


def test_the_catalog_price_is_used_even_when_the_model_omits_one():
    order = _order([{"product_name": "Latte", "product_id": "p1", "quantity": 2}])
    assert order["items"][0]["unit_price"] == 500.0
    assert order["total_amount"] == 1000.0


def test_a_custom_item_keeps_the_agreed_figure():
    # Nothing in the catalog to check against — a genuine quote stands.
    order = _order([{"product_name": "Custom cake", "quantity": 1, "unit_price": 4500}])
    assert order["items"][0]["unit_price"] == 4500.0


def test_another_business_catalog_cannot_be_used_for_pricing():
    db = _DB()
    asyncio.run(_create_order(db, {"items": [
        {"product_name": "Latte", "product_id": "p1", "quantity": 1, "unit_price": 9}
    ]}, "someone-else", "cust-1", "KES"))
    # p1 belongs to biz-1, so it is not found and the quoted figure stands.
    assert db.orders.docs[0]["items"][0]["unit_price"] == 9.0
