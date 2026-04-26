"""Finance / P&L — income, expenses, profit & loss reports."""
from __future__ import annotations
import logging, uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

ENTRY_TYPES = frozenset({"income", "expense"})
CATEGORIES_INCOME = ["Sales", "Service fees", "Consulting", "Rental income", "Interest", "Other income"]
CATEGORIES_EXPENSE = ["Cost of goods", "Rent", "Salaries", "Utilities", "Marketing", "Transport", "Taxes", "Equipment", "Software", "Other expense"]

def _tid(user): return user.get("business_id", user["_id"])

def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at", "date"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"): doc[f] = v.isoformat()
    return doc

class FinanceEntry(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    type: str  # income | expense
    category: str
    amount: float
    description: str = ""
    date: Optional[str] = None  # ISO date string, defaults to today
    reference: str = ""
    currency: str = "KES"

class FinanceEntryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    type: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    date: Optional[str] = None
    reference: Optional[str] = None

def make_finance_router(db, user_dep):
    router = APIRouter(prefix="/finance", tags=["finance"])

    @router.get("/entries")
    async def list_entries(
        type: Optional[str] = None,
        category: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        user=user_dep
    ):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if type and type in ENTRY_TYPES: q["type"] = type
        if category: q["category"] = category
        if from_date or to_date:
            q["date"] = {}
            if from_date: q["date"]["$gte"] = from_date
            if to_date: q["date"]["$lte"] = to_date
            if not q["date"]: del q["date"]
        docs = await db.finance_entries.find(q, sort=[("date", -1), ("created_at", -1)]).to_list(500)
        return [_ser(d) for d in docs]

    @router.post("/entries")
    async def create_entry(payload: FinanceEntry, user=user_dep):
        if payload.type not in ENTRY_TYPES:
            raise HTTPException(400, f"type must be one of {list(ENTRY_TYPES)}")
        tid = _tid(user)
        now = datetime.utcnow()
        entry_date = payload.date or date.today().isoformat()
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "type": payload.type,
            "category": payload.category,
            "amount": round(payload.amount, 2),
            "description": payload.description,
            "date": entry_date,
            "reference": payload.reference,
            "currency": payload.currency.upper()[:6],
            "created_at": now, "updated_at": now,
        }
        await db.finance_entries.insert_one(doc)
        return _ser(doc)

    @router.get("/entries/{entry_id}")
    async def get_entry(entry_id: str, user=user_dep):
        doc = await db.finance_entries.find_one({"_id": entry_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Entry not found")
        return _ser(doc)

    @router.put("/entries/{entry_id}")
    async def update_entry(entry_id: str, payload: FinanceEntryUpdate, user=user_dep):
        doc = await db.finance_entries.find_one({"_id": entry_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Entry not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for f, v in payload.model_dump(exclude_none=True).items():
            upd[f] = v
        if "amount" in upd: upd["amount"] = round(upd["amount"], 2)
        await db.finance_entries.update_one({"_id": entry_id}, {"$set": upd})
        updated = await db.finance_entries.find_one({"_id": entry_id})
        return _ser(updated)

    @router.delete("/entries/{entry_id}")
    async def delete_entry(entry_id: str, user=user_dep):
        doc = await db.finance_entries.find_one({"_id": entry_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Entry not found")
        await db.finance_entries.delete_one({"_id": entry_id})
        return {"deleted": True}

    @router.get("/summary")
    async def finance_summary(from_date: Optional[str] = None, to_date: Optional[str] = None, user=user_dep):
        tid = _tid(user)
        q: Dict[str, Any] = {"user_id": tid}
        if from_date or to_date:
            q["date"] = {}
            if from_date: q["date"]["$gte"] = from_date
            if to_date: q["date"]["$lte"] = to_date
            if not q["date"]: del q["date"]
        pipeline = [
            {"$match": q},
            {"$group": {"_id": {"type": "$type", "category": "$category"}, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
        ]
        rows = await db.finance_entries.aggregate(pipeline).to_list(100)
        income_total = 0.0
        expense_total = 0.0
        income_by_cat: Dict[str, float] = {}
        expense_by_cat: Dict[str, float] = {}
        for r in rows:
            t = r["_id"]["type"]
            cat = r["_id"]["category"]
            amt = r["total"]
            if t == "income":
                income_total += amt
                income_by_cat[cat] = income_by_cat.get(cat, 0) + amt
            else:
                expense_total += amt
                expense_by_cat[cat] = expense_by_cat.get(cat, 0) + amt
        return {
            "income": round(income_total, 2),
            "expenses": round(expense_total, 2),
            "profit": round(income_total - expense_total, 2),
            "income_by_category": income_by_cat,
            "expense_by_category": expense_by_cat,
        }

    @router.get("/categories")
    async def get_categories(user=user_dep):
        return {"income": CATEGORIES_INCOME, "expense": CATEGORIES_EXPENSE}

    return router
