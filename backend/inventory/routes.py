"""Inventory / stock management — products, stock levels, movements."""
from __future__ import annotations
import logging, uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

def _tid(user): return user.get("business_id", user["_id"])

def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"): doc[f] = v.isoformat()
    return doc

class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str
    sku: str = ""
    category: str = ""
    unit: str = "pcs"
    cost_price: float = 0
    selling_price: float = 0
    quantity: float = 0
    reorder_level: float = 0
    description: str = ""

class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    reorder_level: Optional[float] = None
    description: Optional[str] = None

class StockMovement(BaseModel):
    product_id: str
    type: str  # "in" | "out" | "adjustment"
    quantity: float
    reason: str = ""
    reference: str = ""

def make_inventory_router(db, user_dep):
    router = APIRouter(prefix="/inventory", tags=["inventory"])

    @router.get("/products")
    async def list_products(category: Optional[str] = None, low_stock: bool = False, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if category: q["category"] = category
        docs = await db.inventory_products.find(q, sort=[("name", 1)]).to_list(500)
        items = [_ser(d) for d in docs]
        if low_stock:
            items = [i for i in items if i.get("quantity", 0) <= i.get("reorder_level", 0)]
        return items

    @router.post("/products")
    async def create_product(payload: ProductCreate, user=user_dep):
        tid = _tid(user)
        now = datetime.utcnow()
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            **payload.model_dump(),
            "created_at": now, "updated_at": now,
        }
        await db.inventory_products.insert_one(doc)
        return _ser(doc)

    @router.get("/products/{product_id}")
    async def get_product(product_id: str, user=user_dep):
        doc = await db.inventory_products.find_one({"_id": product_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Product not found")
        return _ser(doc)

    @router.put("/products/{product_id}")
    async def update_product(product_id: str, payload: ProductUpdate, user=user_dep):
        doc = await db.inventory_products.find_one({"_id": product_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Product not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for f, v in payload.model_dump(exclude_none=True).items():
            upd[f] = v
        await db.inventory_products.update_one({"_id": product_id}, {"$set": upd})
        updated = await db.inventory_products.find_one({"_id": product_id})
        return _ser(updated)

    @router.delete("/products/{product_id}")
    async def delete_product(product_id: str, user=user_dep):
        doc = await db.inventory_products.find_one({"_id": product_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Product not found")
        await db.inventory_products.delete_one({"_id": product_id})
        return {"deleted": True}

    @router.post("/movements")
    async def record_movement(payload: StockMovement, user=user_dep):
        tid = _tid(user)
        product = await db.inventory_products.find_one({"_id": payload.product_id, "user_id": tid})
        if not product: raise HTTPException(404, "Product not found")
        delta = payload.quantity if payload.type == "in" else (-payload.quantity if payload.type == "out" else payload.quantity - product.get("quantity", 0))
        new_qty = max(0, product.get("quantity", 0) + delta)
        await db.inventory_products.update_one(
            {"_id": payload.product_id},
            {"$set": {"quantity": new_qty, "updated_at": datetime.utcnow()}}
        )
        now = datetime.utcnow()
        movement = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "product_id": payload.product_id,
            "product_name": product.get("name", ""),
            "type": payload.type,
            "quantity": payload.quantity,
            "balance_after": new_qty,
            "reason": payload.reason,
            "reference": payload.reference,
            "created_at": now,
        }
        await db.inventory_movements.insert_one(movement)
        return {"balance": new_qty, "movement": _ser(movement)}

    @router.get("/movements")
    async def list_movements(product_id: Optional[str] = None, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if product_id: q["product_id"] = product_id
        docs = await db.inventory_movements.find(q, sort=[("created_at", -1)]).to_list(200)
        return [_ser(d) for d in docs]

    @router.get("/summary")
    async def inventory_summary(user=user_dep):
        tid = _tid(user)
        docs = await db.inventory_products.find({"user_id": tid}).to_list(1000)
        total_items = len(docs)
        total_value = sum(d.get("quantity", 0) * d.get("cost_price", 0) for d in docs)
        low_stock = [_ser(d) for d in docs if d.get("quantity", 0) <= d.get("reorder_level", 0) and d.get("reorder_level", 0) > 0]
        out_of_stock = [_ser(d) for d in docs if d.get("quantity", 0) == 0]
        return {
            "total_items": total_items,
            "total_value": round(total_value, 2),
            "low_stock_count": len(low_stock),
            "out_of_stock_count": len(out_of_stock),
            "low_stock_items": low_stock[:10],
        }

    return router
