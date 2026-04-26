"""Invoice management — create, send, track payment."""
from __future__ import annotations
import logging, uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

ALLOWED_STATUS = frozenset({"draft", "sent", "paid", "overdue", "cancelled"})

def _tid(user): return user.get("business_id", user["_id"])

def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at", "due_date"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"): doc[f] = v.isoformat()
    return doc

def _next_number(existing: int) -> str:
    return f"INV-{existing + 1:04d}"

class InvoiceItem(BaseModel):
    name: str
    qty: float = 1
    unit_price: float = 0
    amount: float = 0

class InvoiceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    customer_id: Optional[str] = None
    customer_name: str = ""
    customer_phone: str = ""
    items: List[InvoiceItem] = []
    tax_rate: float = 0
    currency: str = "KES"
    due_date: Optional[str] = None
    notes: str = ""
    status: str = "draft"

class InvoiceUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items: Optional[List[InvoiceItem]] = None
    tax_rate: Optional[float] = None
    currency: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

def _calc(items: List[InvoiceItem], tax_rate: float):
    subtotal = sum(i.qty * i.unit_price for i in items)
    tax = round(subtotal * (tax_rate / 100), 2)
    return round(subtotal, 2), tax, round(subtotal + tax, 2)

def make_invoices_router(db, user_dep):
    router = APIRouter(prefix="/invoices", tags=["invoices"])

    @router.get("")
    async def list_invoices(status: Optional[str] = None, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if status: q["status"] = status
        docs = await db.invoices.find(q, sort=[("created_at", -1)]).to_list(200)
        return [_ser(d) for d in docs]

    @router.post("")
    async def create_invoice(payload: InvoiceCreate, user=user_dep):
        tid = _tid(user)
        count = await db.invoices.count_documents({"user_id": tid})
        subtotal, tax, total = _calc(payload.items, payload.tax_rate)
        now = datetime.utcnow()
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "number": _next_number(count),
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name,
            "customer_phone": payload.customer_phone,
            "items": [i.model_dump() for i in payload.items],
            "subtotal": subtotal, "tax_rate": payload.tax_rate,
            "tax_amount": tax, "total": total,
            "currency": payload.currency.upper()[:6],
            "due_date": payload.due_date,
            "notes": payload.notes,
            "status": payload.status if payload.status in ALLOWED_STATUS else "draft",
            "created_at": now, "updated_at": now,
        }
        await db.invoices.insert_one(doc)
        return _ser(doc)

    @router.get("/{invoice_id}")
    async def get_invoice(invoice_id: str, user=user_dep):
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Invoice not found")
        return _ser(doc)

    @router.put("/{invoice_id}")
    async def update_invoice(invoice_id: str, payload: InvoiceUpdate, user=user_dep):
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Invoice not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for f in ("customer_name","customer_phone","currency","due_date","notes"):
            v = getattr(payload, f, None)
            if v is not None: upd[f] = v
        if payload.status and payload.status in ALLOWED_STATUS: upd["status"] = payload.status
        if payload.items is not None:
            tr = payload.tax_rate if payload.tax_rate is not None else doc.get("tax_rate", 0)
            sub, tax, total = _calc(payload.items, tr)
            upd.update({"items": [i.model_dump() for i in payload.items],
                         "subtotal": sub, "tax_amount": tax, "total": total})
        if payload.tax_rate is not None:
            items = payload.items or [InvoiceItem(**i) for i in doc.get("items", [])]
            sub, tax, total = _calc(items, payload.tax_rate)
            upd.update({"tax_rate": payload.tax_rate, "subtotal": sub, "tax_amount": tax, "total": total})
        await db.invoices.update_one({"_id": invoice_id}, {"$set": upd})
        updated = await db.invoices.find_one({"_id": invoice_id})
        return _ser(updated)

    @router.patch("/{invoice_id}/status")
    async def set_status(invoice_id: str, body: Dict[str, Any], user=user_dep):
        st = body.get("status")
        if st not in ALLOWED_STATUS: raise HTTPException(400, f"Invalid status: {st}")
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Invoice not found")
        await db.invoices.update_one({"_id": invoice_id}, {"$set": {"status": st, "updated_at": datetime.utcnow()}})
        return {"status": st}

    @router.delete("/{invoice_id}")
    async def delete_invoice(invoice_id: str, user=user_dep):
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Invoice not found")
        await db.invoices.delete_one({"_id": invoice_id})
        return {"deleted": True}

    @router.get("/meta/summary")
    async def invoice_summary(user=user_dep):
        tid = _tid(user)
        pipeline = [
            {"$match": {"user_id": tid}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}, "total": {"$sum": "$total"}}}
        ]
        rows = await db.invoices.aggregate(pipeline).to_list(20)
        summary = {r["_id"]: {"count": r["count"], "total": r["total"]} for r in rows}
        all_total = sum(r["total"] for r in rows)
        return {"by_status": summary, "total_invoiced": all_total}

    return router
