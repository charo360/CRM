"""Customer Loyalty / Points — earn, redeem, tier management."""
from __future__ import annotations
import logging, uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# Default tier thresholds
DEFAULT_TIERS = [
    {"name": "Bronze", "min_points": 0, "color": "#cd7f32"},
    {"name": "Silver", "min_points": 500, "color": "#9ca3af"},
    {"name": "Gold", "min_points": 1500, "color": "#f59e0b"},
    {"name": "Platinum", "min_points": 5000, "color": "#6366f1"},
]

def _tid(user): return user.get("business_id", user["_id"])

def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"): doc[f] = v.isoformat()
    return doc

def _get_tier(points: float, tiers: list) -> str:
    tier = tiers[0]["name"]
    for t in tiers:
        if points >= t["min_points"]:
            tier = t["name"]
    return tier

class PointsTransaction(BaseModel):
    customer_id: str
    type: str  # "earn" | "redeem" | "adjustment" | "expire"
    points: float
    reason: str = ""
    reference: str = ""

class LoyaltySettingsUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    points_per_kes: Optional[float] = None   # e.g. 1 point per 100 KES spent
    kes_per_point: Optional[float] = None    # redemption: 1 point = X KES
    tiers: Optional[List[Dict]] = None
    enabled: Optional[bool] = None


class ManualPointsAdd(BaseModel):
    points: Optional[float] = None
    # Keep existing installed app builds working while they receive the update.
    amount: Optional[float] = None
    reason: str = "manual"

def make_loyalty_router(db, user_dep):
    router = APIRouter(prefix="/loyalty", tags=["loyalty"])

    async def _get_settings(tid: str) -> dict:
        s = await db.loyalty_settings.find_one({"user_id": tid})
        if not s:
            s = {
                "_id": str(uuid.uuid4()),
                "user_id": tid,
                "points_per_kes": 0.01,   # 1 point per 100 KES
                "kes_per_point": 0.5,     # 1 point = 0.5 KES
                "tiers": DEFAULT_TIERS,
                "enabled": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            await db.loyalty_settings.insert_one(s)
        return s

    @router.get("/settings")
    async def get_settings(user=user_dep):
        s = await _get_settings(_tid(user))
        return _ser(s)

    @router.put("/settings")
    async def update_settings(payload: LoyaltySettingsUpdate, user=user_dep):
        tid = _tid(user)
        await _get_settings(tid)  # ensure exists
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for f, v in payload.model_dump(exclude_none=True).items():
            upd[f] = v
        await db.loyalty_settings.update_one({"user_id": tid}, {"$set": upd})
        updated = await db.loyalty_settings.find_one({"user_id": tid})
        return _ser(updated)

    @router.get("/members")
    async def list_members(tier: Optional[str] = None, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if tier: q["tier"] = tier
        docs = await db.loyalty_members.find(q, sort=[("points", -1)]).to_list(500)
        return [_ser(d) for d in docs]

    @router.get("/members/{customer_id}")
    async def get_member(customer_id: str, user=user_dep):
        doc = await db.loyalty_members.find_one({"customer_id": customer_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Loyalty member not found")
        return _ser(doc)

    @router.post("/transactions")
    async def add_transaction(payload: PointsTransaction, user=user_dep):
        tid = _tid(user)
        settings = await _get_settings(tid)
        tiers = settings.get("tiers", DEFAULT_TIERS)

        # Get or create a member. Customer Profile passes an id from the
        # `customers` collection; older web flows may still pass a contact id.
        customer = await db.customers.find_one({"_id": payload.customer_id, "user_id": tid})
        if not customer:
            customer = await db.contacts.find_one({"_id": payload.customer_id, "user_id": tid})
        if not customer:
            raise HTTPException(404, "Customer not found")

        member = await db.loyalty_members.find_one({"customer_id": payload.customer_id, "user_id": tid})
        if not member:
            member = {
                "_id": str(uuid.uuid4()),
                "user_id": tid,
                "customer_id": payload.customer_id,
                "customer_name": customer.get("name", ""),
                "points": 0,
                "lifetime_points": 0,
                "tier": tiers[0]["name"] if tiers else "Bronze",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            await db.loyalty_members.insert_one(member)

        current_points = member.get("points", 0)
        lifetime = member.get("lifetime_points", 0)

        if payload.type == "earn":
            new_points = current_points + payload.points
            new_lifetime = lifetime + payload.points
        elif payload.type == "redeem":
            if payload.points > current_points:
                raise HTTPException(400, f"Insufficient points: {current_points} available")
            new_points = current_points - payload.points
            new_lifetime = lifetime
        else:  # adjustment or expire
            new_points = max(0, current_points + payload.points)
            new_lifetime = lifetime

        new_tier = _get_tier(new_points, tiers)
        now = datetime.utcnow()

        await db.loyalty_members.update_one(
            {"customer_id": payload.customer_id, "user_id": tid},
            {"$set": {"points": new_points, "lifetime_points": new_lifetime, "tier": new_tier, "updated_at": now}}
        )

        txn = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "customer_id": payload.customer_id,
            "type": payload.type,
            "points": payload.points,
            "balance_after": new_points,
            "reason": payload.reason,
            "reference": payload.reference,
            "created_at": now,
        }
        await db.loyalty_transactions.insert_one(txn)
        return {"balance": new_points, "tier": new_tier, "transaction": _ser(txn)}

    @router.get("/transactions")
    async def list_transactions(customer_id: Optional[str] = None, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if customer_id: q["customer_id"] = customer_id
        docs = await db.loyalty_transactions.find(q, sort=[("created_at", -1)]).to_list(200)
        return [_ser(d) for d in docs]

    @router.get("/summary")
    async def loyalty_summary(user=user_dep):
        tid = _tid(user)
        members = await db.loyalty_members.find({"user_id": tid}).to_list(1000)
        total_members = len(members)
        total_points = sum(m.get("points", 0) for m in members)
        by_tier: Dict[str, int] = {}
        for m in members:
            t = m.get("tier", "Bronze")
            by_tier[t] = by_tier.get(t, 0) + 1
        return {
            "total_members": total_members,
            "total_active_points": round(total_points, 0),
            "members_by_tier": by_tier,
        }

    # Mobile Customer Profile convenience endpoints.  These keep the mobile
    # app deliberately small while reusing the same ledger used by the web.
    # They must be registered after the named routes above, so `/settings`,
    # `/members`, and `/transactions` are never captured as customer ids.
    @router.get("/{customer_id}")
    async def get_customer_points(customer_id: str, user=user_dep):
        tid = _tid(user)
        customer = await db.customers.find_one({"_id": customer_id, "user_id": tid})
        if not customer:
            customer = await db.contacts.find_one({"_id": customer_id, "user_id": tid})
        if not customer:
            raise HTTPException(404, "Customer not found")

        settings = await _get_settings(tid)
        member = await db.loyalty_members.find_one({"customer_id": customer_id, "user_id": tid})
        if not member:
            tiers = settings.get("tiers", DEFAULT_TIERS)
            return {
                "customer_id": customer_id,
                "customer_name": customer.get("name", ""),
                "points": 0,
                "lifetime_points": 0,
                "tier": tiers[0]["name"] if tiers else "Bronze",
                "tiers": tiers,
            }

        result = _ser(member)
        result["tiers"] = settings.get("tiers", DEFAULT_TIERS)
        return result

    @router.get("/{customer_id}/history")
    async def get_customer_history(customer_id: str, user=user_dep):
        tid = _tid(user)
        docs = await db.loyalty_transactions.find(
            {"customer_id": customer_id, "user_id": tid},
            sort=[("created_at", -1)],
        ).to_list(100)
        return [_ser(d) for d in docs]

    @router.post("/{customer_id}/add")
    async def add_customer_points(customer_id: str, payload: ManualPointsAdd, user=user_dep):
        points = payload.points if payload.points is not None else payload.amount
        if points is None or points <= 0 or points > 1_000_000:
            raise HTTPException(400, "Points must be between 1 and 1,000,000")
        return await add_transaction(
            PointsTransaction(
                customer_id=customer_id,
                type="adjustment",
                points=points,
                reason=payload.reason.strip() or "manual",
            ),
            user,
        )

    return router
