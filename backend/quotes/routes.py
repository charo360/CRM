"""Quotes / Proposals — create, send, convert to invoice."""
from __future__ import annotations
import logging, uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

ALLOWED_STATUS = frozenset({"draft", "sent", "accepted", "rejected", "expired"})

def _tid(user): return user.get("business_id", user["_id"])

def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at", "valid_until"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"): doc[f] = v.isoformat()
    return doc

def _next_number(existing: int) -> str:
    return f"QUO-{existing + 1:04d}"

class QuoteItem(BaseModel):
    name: str
    qty: float = 1
    unit_price: float = 0
    amount: float = 0

class QuoteCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    customer_id: Optional[str] = None
    customer_name: str = ""
    customer_phone: str = ""
    customer_email: str = ""
    items: List[QuoteItem] = []
    tax_rate: float = 0
    currency: str = "KES"
    valid_until: Optional[str] = None
    notes: str = ""
    terms: str = ""
    subject: str = ""
    status: str = "draft"

class QuoteUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    items: Optional[List[QuoteItem]] = None
    tax_rate: Optional[float] = None
    currency: Optional[str] = None
    valid_until: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    subject: Optional[str] = None
    status: Optional[str] = None

def _calc(items: List[QuoteItem], tax_rate: float):
    subtotal = sum(i.qty * i.unit_price for i in items)
    tax = round(subtotal * (tax_rate / 100), 2)
    return round(subtotal, 2), tax, round(subtotal + tax, 2)

def make_quotes_router(db, user_dep):
    router = APIRouter(prefix="/quotes", tags=["quotes"])

    @router.get("")
    async def list_quotes(status: Optional[str] = None, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if status: q["status"] = status
        docs = await db.quotes.find(q, sort=[("created_at", -1)]).to_list(200)
        return [_ser(d) for d in docs]

    @router.post("")
    async def create_quote(payload: QuoteCreate, user=user_dep):
        tid = _tid(user)
        count = await db.quotes.count_documents({"user_id": tid})
        subtotal, tax, total = _calc(payload.items, payload.tax_rate)
        now = datetime.utcnow()
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "number": _next_number(count),
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name,
            "customer_phone": payload.customer_phone,
            "customer_email": payload.customer_email,
            "subject": payload.subject,
            "items": [i.model_dump() for i in payload.items],
            "subtotal": subtotal, "tax_rate": payload.tax_rate,
            "tax_amount": tax, "total": total,
            "currency": payload.currency.upper()[:6],
            "valid_until": payload.valid_until,
            "notes": payload.notes,
            "terms": payload.terms,
            "status": payload.status if payload.status in ALLOWED_STATUS else "draft",
            "created_at": now, "updated_at": now,
        }
        await db.quotes.insert_one(doc)
        return _ser(doc)

    @router.get("/{quote_id}")
    async def get_quote(quote_id: str, user=user_dep):
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Quote not found")
        return _ser(doc)

    @router.put("/{quote_id}")
    async def update_quote(quote_id: str, payload: QuoteUpdate, user=user_dep):
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Quote not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for f in ("customer_name", "customer_phone", "customer_email", "currency", "valid_until", "notes", "terms", "subject"):
            v = getattr(payload, f, None)
            if v is not None: upd[f] = v
        if payload.status and payload.status in ALLOWED_STATUS: upd["status"] = payload.status
        if payload.items is not None:
            tr = payload.tax_rate if payload.tax_rate is not None else doc.get("tax_rate", 0)
            sub, tax, total = _calc(payload.items, tr)
            upd.update({"items": [i.model_dump() for i in payload.items], "subtotal": sub, "tax_amount": tax, "total": total})
        if payload.tax_rate is not None:
            items = payload.items or [QuoteItem(**i) for i in doc.get("items", [])]
            sub, tax, total = _calc(items, payload.tax_rate)
            upd.update({"tax_rate": payload.tax_rate, "subtotal": sub, "tax_amount": tax, "total": total})
        await db.quotes.update_one({"_id": quote_id}, {"$set": upd})
        updated = await db.quotes.find_one({"_id": quote_id})
        return _ser(updated)

    @router.patch("/{quote_id}/status")
    async def set_status(quote_id: str, body: Dict[str, Any], user=user_dep):
        st = body.get("status")
        if st not in ALLOWED_STATUS: raise HTTPException(400, f"Invalid status: {st}")
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Quote not found")
        await db.quotes.update_one({"_id": quote_id}, {"$set": {"status": st, "updated_at": datetime.utcnow()}})
        return {"status": st}

    @router.post("/{quote_id}/convert-to-invoice")
    async def convert_to_invoice(quote_id: str, user=user_dep):
        """Convert an accepted quote into an invoice."""
        tid = _tid(user)
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": tid})
        if not doc: raise HTTPException(404, "Quote not found")
        count = await db.invoices.count_documents({"user_id": tid})
        now = datetime.utcnow()
        invoice = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "number": f"INV-{count + 1:04d}",
            "quote_id": quote_id,
            "customer_id": doc.get("customer_id"),
            "customer_name": doc.get("customer_name", ""),
            "customer_phone": doc.get("customer_phone", ""),
            "items": doc.get("items", []),
            "subtotal": doc.get("subtotal", 0),
            "tax_rate": doc.get("tax_rate", 0),
            "tax_amount": doc.get("tax_amount", 0),
            "total": doc.get("total", 0),
            "currency": doc.get("currency", "KES"),
            "due_date": None,
            "notes": doc.get("notes", ""),
            "status": "draft",
            "created_at": now, "updated_at": now,
        }
        await db.invoices.insert_one(invoice)
        await db.quotes.update_one({"_id": quote_id}, {"$set": {"status": "accepted", "updated_at": now}})
        return {"invoice": _ser(invoice)}

    @router.delete("/{quote_id}")
    async def delete_quote(quote_id: str, user=user_dep):
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Quote not found")
        await db.quotes.delete_one({"_id": quote_id})
        return {"deleted": True}

    @router.get("/meta/summary")
    async def quote_summary(user=user_dep):
        tid = _tid(user)
        pipeline = [
            {"$match": {"user_id": tid}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}, "total": {"$sum": "$total"}}}
        ]
        rows = await db.quotes.aggregate(pipeline).to_list(20)
        summary = {r["_id"]: {"count": r["count"], "total": r["total"]} for r in rows}
        return {"by_status": summary, "total_quoted": sum(r["total"] for r in rows)}

    return router
