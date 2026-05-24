"""Field Agents — task assignment, check-ins, activity, and performance."""
from __future__ import annotations
import logging, uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

TASK_TYPES    = ["visit", "call", "demo", "collect_payment", "delivery", "survey", "other"]
TASK_STATUSES = ["pending", "in_progress", "completed", "missed", "cancelled"]
PRIORITIES    = ["low", "medium", "high"]

def _tid(user): return user.get("business_id", user["_id"])

def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at", "checked_in_at", "checked_out_at", "due_date"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"): doc[f] = v.isoformat()
    return doc

# ── Pydantic models ────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    assigned_to: str          # team member _id
    title: str
    task_type: str = "visit"
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    notes: str = ""
    due_date: Optional[str] = None   # ISO date string
    priority: str = "medium"
    location: str = ""

class TaskUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: Optional[str] = None
    task_type: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    location: Optional[str] = None
    outcome: Optional[str] = None

class CheckIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    location_note: str = ""
    notes: str = ""

class CommissionSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    commission_type: str = "none"   # none | percentage | per_lead
    commission_rate: float = 0.0

class CheckOut(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    outcome: str = ""
    notes: str = ""
    status: str = "completed"   # completed | missed
    amount_collected: Optional[float] = None   # for collect_payment tasks
    payment_method: str = "cash"               # cash | card | bank_transfer | mobile_money | other

# ── Router factory ─────────────────────────────────────────────────────────────

def make_field_agents_router(db, user_dep):
    router = APIRouter(prefix="/field-agents", tags=["field-agents"])

    # ── Agents (team members) ────────────────────────────────────────────────

    @router.get("/agents")
    async def list_agents(user=user_dep):
        tid = _tid(user)
        members = await db.team_members.find(
            {"business_id": tid, "status": {"$ne": "suspended"}}
        ).to_list(200)

        today_str = date.today().isoformat()

        # Single aggregation to get all task counts per agent in one round-trip
        pipeline = [
            {"$match": {"user_id": tid}},
            {"$group": {
                "_id": "$assigned_to",
                "total":     {"$sum": 1},
                "pending":   {"$sum": {"$cond": [{"$eq": ["$status", "pending"]},   1, 0]}},
                "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "overdue":   {"$sum": {"$cond": [
                    {"$and": [
                        {"$in": ["$status", ["pending", "in_progress"]]},
                        {"$gt": ["$due_date", ""]},          # exclude empty due_date
                        {"$lt": ["$due_date", today_str]},
                    ]}, 1, 0
                ]}},
            }},
        ]
        rows = await db.field_agent_tasks.aggregate(pipeline).to_list(200)
        counts = {r["_id"]: r for r in rows}

        # Per-agent collection totals from finance_entries
        fin_pipeline = [
            {"$match": {"user_id": tid, "source": "field_agent", "type": "income"}},
            {"$group": {
                "_id": "$agent_id",
                "total_collected":  {"$sum": "$amount"},
                "collection_count": {"$sum": 1},
            }},
        ]
        fin_rows = await db.finance_entries.aggregate(fin_pipeline).to_list(200)
        collections = {r["_id"]: r for r in fin_rows}

        result = []
        for m in members:
            agent_id       = str(m["_id"])
            c              = counts.get(agent_id, {"total": 0, "pending": 0, "completed": 0, "overdue": 0})
            fc             = collections.get(agent_id, {"total_collected": 0.0, "collection_count": 0})
            total_collected = round(fc["total_collected"], 2)
            comm_type  = m.get("commission_type", "none")
            comm_rate  = float(m.get("commission_rate", 0) or 0)
            leads_done = c["completed"]
            if comm_type == "percentage":
                commission_earned = round(total_collected * comm_rate / 100, 2)
            elif comm_type == "per_lead":
                commission_earned = round(leads_done * comm_rate, 2)
            else:
                commission_earned = 0.0
            result.append({
                "id": agent_id,
                "name": m.get("name", ""),
                "email": m.get("email", ""),
                "phone_number": m.get("phone_number", ""),
                "role": m.get("role", "employee"),
                "status": m.get("status", "active"),
                "tasks_total": c["total"],
                "tasks_pending": c["pending"],
                "tasks_completed": c["completed"],
                "tasks_overdue": c["overdue"],
                "total_collected":  total_collected,
                "collection_count": fc["collection_count"],
                "commission_type":  comm_type,
                "commission_rate":  comm_rate,
                "commission_earned": commission_earned,
            })
        return result

    @router.get("/agents/{agent_id}")
    async def get_agent(agent_id: str, user=user_dep):
        tid = _tid(user)
        m = await db.team_members.find_one({"_id": agent_id, "business_id": tid})
        if not m:
            raise HTTPException(404, "Agent not found")
        tasks = await db.field_agent_tasks.find(
            {"user_id": tid, "assigned_to": agent_id},
            sort=[("due_date", 1), ("created_at", -1)]
        ).to_list(100)
        checkins = await db.field_agent_checkins.find(
            {"user_id": tid, "agent_id": agent_id},
            sort=[("checked_in_at", -1)]
        ).to_list(50)
        fin_rows = await db.finance_entries.aggregate([
            {"$match": {"user_id": tid, "agent_id": agent_id, "source": "field_agent", "type": "income"}},
            {"$group": {"_id": None, "total_collected": {"$sum": "$amount"}, "collection_count": {"$sum": 1}}},
        ]).to_list(1)
        fc = fin_rows[0] if fin_rows else {"total_collected": 0.0, "collection_count": 0}
        total_collected = round(fc["total_collected"], 2)
        comm_type = m.get("commission_type", "none")
        comm_rate = float(m.get("commission_rate", 0) or 0)
        completed_count = sum(1 for t in tasks if t.get("status") == "completed")
        if comm_type == "percentage":
            commission_earned = round(total_collected * comm_rate / 100, 2)
        elif comm_type == "per_lead":
            commission_earned = round(completed_count * comm_rate, 2)
        else:
            commission_earned = 0.0
        return {
            "id": agent_id,
            "name": m.get("name", ""),
            "email": m.get("email", ""),
            "phone_number": m.get("phone_number", ""),
            "role": m.get("role", "employee"),
            "status": m.get("status", "active"),
            "commission_type": comm_type,
            "commission_rate": comm_rate,
            "commission_earned": commission_earned,
            "total_collected": total_collected,
            "collection_count": fc["collection_count"],
            "tasks": [_ser(t) for t in tasks],
            "checkins": [_ser(c) for c in checkins],
        }

    @router.put("/agents/{agent_id}/commission")
    async def set_commission(agent_id: str, payload: CommissionSettings, user=user_dep):
        tid = _tid(user)
        m = await db.team_members.find_one({"_id": agent_id, "business_id": tid})
        if not m: raise HTTPException(404, "Agent not found")
        if payload.commission_type not in ("none", "percentage", "per_lead"):
            raise HTTPException(400, "commission_type must be none | percentage | per_lead")
        await db.team_members.update_one(
            {"_id": agent_id},
            {"$set": {"commission_type": payload.commission_type,
                      "commission_rate": round(payload.commission_rate, 4),
                      "updated_at": datetime.utcnow()}}
        )
        return {"commission_type": payload.commission_type, "commission_rate": payload.commission_rate}

    # ── Tasks ────────────────────────────────────────────────────────────────

    @router.get("/tasks")
    async def list_tasks(
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        user=user_dep,
    ):
        tid = _tid(user)
        q: Dict[str, Any] = {"user_id": tid}
        if agent_id: q["assigned_to"] = agent_id
        if status and status in TASK_STATUSES: q["status"] = status
        if priority and priority in PRIORITIES: q["priority"] = priority
        if from_date or to_date:
            q["due_date"] = {}
            if from_date: q["due_date"]["$gte"] = from_date
            if to_date:   q["due_date"]["$lte"] = to_date
            if not q["due_date"]: del q["due_date"]
        docs = await db.field_agent_tasks.find(q, sort=[("due_date", 1), ("created_at", -1)]).to_list(500)
        return [_ser(d) for d in docs]

    @router.post("/tasks")
    async def create_task(payload: TaskCreate, user=user_dep):
        if payload.task_type not in TASK_TYPES:
            raise HTTPException(400, f"task_type must be one of {TASK_TYPES}")
        if payload.priority not in PRIORITIES:
            raise HTTPException(400, f"priority must be one of {PRIORITIES}")
        tid = _tid(user)
        # Verify agent belongs to this business
        agent = await db.team_members.find_one({"_id": payload.assigned_to, "business_id": tid})
        if not agent:
            raise HTTPException(404, "Agent not found in your team")
        now = datetime.utcnow()
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "assigned_to": payload.assigned_to,
            "agent_name": agent.get("name", ""),
            "title": payload.title,
            "task_type": payload.task_type,
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name or "",
            "notes": payload.notes,
            "due_date": payload.due_date or "",
            "priority": payload.priority,
            "location": payload.location,
            "status": "pending",
            "outcome": "",
            "created_at": now,
            "updated_at": now,
        }
        await db.field_agent_tasks.insert_one(doc)
        await _log_activity(db, tid, payload.assigned_to, agent.get("name",""), doc["_id"],
                            "task_assigned", payload.title, payload.task_type)
        return _ser(doc)

    @router.put("/tasks/{task_id}")
    async def update_task(task_id: str, payload: TaskUpdate, user=user_dep):
        tid = _tid(user)
        doc = await db.field_agent_tasks.find_one({"_id": task_id, "user_id": tid})
        if not doc: raise HTTPException(404, "Task not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for f, v in payload.model_dump(exclude_none=True).items():
            upd[f] = v
        await db.field_agent_tasks.update_one({"_id": task_id}, {"$set": upd})
        if payload.status:
            await _log_activity(db, tid, doc["assigned_to"], doc.get("agent_name",""), task_id,
                                f"status_{payload.status}", doc["title"], doc.get("task_type", "other"))
        updated = await db.field_agent_tasks.find_one({"_id": task_id})
        return _ser(updated)

    @router.delete("/tasks/{task_id}")
    async def delete_task(task_id: str, user=user_dep):
        tid = _tid(user)
        doc = await db.field_agent_tasks.find_one({"_id": task_id, "user_id": tid})
        if not doc: raise HTTPException(404, "Task not found")
        await db.field_agent_tasks.delete_one({"_id": task_id})
        return {"deleted": True}

    # ── Check-in / Check-out ─────────────────────────────────────────────────

    @router.post("/tasks/{task_id}/checkin")
    async def checkin(task_id: str, payload: CheckIn, user=user_dep):
        tid = _tid(user)
        task = await db.field_agent_tasks.find_one({"_id": task_id, "user_id": tid})
        if not task: raise HTTPException(404, "Task not found")
        existing = await db.field_agent_checkins.find_one({"task_id": task_id, "checked_out_at": None})
        if existing: raise HTTPException(400, "Already checked in — check out first")
        now = datetime.utcnow()
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "task_id": task_id,
            "agent_id": task["assigned_to"],
            "agent_name": task.get("agent_name", ""),
            "customer_id": task.get("customer_id"),
            "customer_name": task.get("customer_name", ""),
            "location_note": payload.location_note,
            "notes": payload.notes,
            "checked_in_at": now,
            "checked_out_at": None,
            "outcome": "",
            "duration_mins": None,
        }
        await db.field_agent_checkins.insert_one(doc)
        await db.field_agent_tasks.update_one({"_id": task_id}, {"$set": {"status": "in_progress", "updated_at": now}})
        await _log_activity(db, tid, task["assigned_to"], task.get("agent_name",""), task_id,
                            "checked_in", task["title"], task.get("task_type", "other"))
        return _ser(doc)

    @router.put("/tasks/{task_id}/checkout")
    async def checkout(task_id: str, payload: CheckOut, user=user_dep):
        tid = _tid(user)
        task = await db.field_agent_tasks.find_one({"_id": task_id, "user_id": tid})
        if not task: raise HTTPException(404, "Task not found")
        checkin_doc = await db.field_agent_checkins.find_one({"task_id": task_id, "checked_out_at": None})
        if not checkin_doc: raise HTTPException(400, "Not currently checked in")
        now = datetime.utcnow()
        duration = int((now - checkin_doc["checked_in_at"]).total_seconds() / 60)
        await db.field_agent_checkins.update_one(
            {"_id": checkin_doc["_id"]},
            {"$set": {"checked_out_at": now, "outcome": payload.outcome,
                      "notes": payload.notes, "duration_mins": duration}}
        )
        final_status = payload.status if payload.status in TASK_STATUSES else "completed"
        await db.field_agent_tasks.update_one(
            {"_id": task_id},
            {"$set": {"status": final_status, "outcome": payload.outcome, "updated_at": now}}
        )
        await _log_activity(db, tid, task["assigned_to"], task.get("agent_name",""), task_id,
                            "checked_out", task["title"], task.get("task_type", "other"), duration)

        # ── Record payment if this was a collect_payment task ────────────────
        payment_entry_id = None
        if (task.get("task_type") == "collect_payment"
                and payload.amount_collected and payload.amount_collected > 0
                and final_status == "completed"):
            customer_id   = task.get("customer_id") or ""
            customer_name = task.get("customer_name") or ""
            amount        = round(payload.amount_collected, 2)
            payment_entry_id = str(uuid.uuid4())
            today_iso = date.today().isoformat()
            await db.finance_entries.insert_one({
                "_id": payment_entry_id,
                "user_id": tid,
                "type": "income",
                "category": "Sales",
                "amount": amount,
                "currency": "USD",
                "description": f"Field collection — {customer_name}",
                "reference": f"field-task:{task_id}",
                "payment_method": payload.payment_method,
                "customer_id": customer_id,
                "agent_id": task["assigned_to"],
                "agent_name": task.get("agent_name", ""),
                "date": today_iso,
                "source": "field_agent",
                "reconciliation_status": "unreconciled",
                "created_at": now,
                "updated_at": now,
            })
            if customer_id:
                await db.customers.update_one(
                    {"_id": customer_id, "user_id": tid},
                    {"$inc": {"purchase_count": 1, "total_spent": amount},
                     "$set":  {"last_contacted": now}},
                )
                # Auto-mark oldest matching open invoice as paid
                open_invoice = await db.invoices.find_one(
                    {"user_id": tid, "customer_id": customer_id,
                     "status": {"$in": ["sent", "viewed", "overdue", "partial"]},
                     "total": {"$lte": amount * 1.01, "$gte": amount * 0.99}},
                    sort=[("created_at", 1)]
                )
                if open_invoice:
                    await db.invoices.update_one(
                        {"_id": open_invoice["_id"]},
                        {"$set": {"status": "paid", "updated_at": now}}
                    )

        updated = await db.field_agent_checkins.find_one({"_id": checkin_doc["_id"]})
        result = _ser(updated)
        if payment_entry_id:
            result["payment_recorded"] = True
            result["amount_collected"] = payload.amount_collected
        return result

    # ── Activity feed ────────────────────────────────────────────────────────

    @router.get("/activity")
    async def list_activity(agent_id: Optional[str] = None, limit: int = 50, user=user_dep):
        tid = _tid(user)
        q: Dict[str, Any] = {"user_id": tid}
        if agent_id: q["agent_id"] = agent_id
        docs = await db.field_agent_activity.find(q, sort=[("created_at", -1)]).to_list(min(limit, 200))
        return [_ser(d) for d in docs]

    # ── Summary ──────────────────────────────────────────────────────────────

    @router.get("/summary")
    async def summary(user=user_dep):
        tid = _tid(user)
        today_str = date.today().isoformat()
        total_tasks    = await db.field_agent_tasks.count_documents({"user_id": tid})
        pending        = await db.field_agent_tasks.count_documents({"user_id": tid, "status": "pending"})
        in_progress    = await db.field_agent_tasks.count_documents({"user_id": tid, "status": "in_progress"})
        completed      = await db.field_agent_tasks.count_documents({"user_id": tid, "status": "completed"})
        overdue        = await db.field_agent_tasks.count_documents({
            "user_id": tid, "status": {"$in": ["pending", "in_progress"]},
            "due_date": {"$gt": "", "$lt": today_str},
        })
        total_agents   = await db.team_members.count_documents({"business_id": tid, "status": {"$ne": "suspended"}})
        active_today   = await db.field_agent_checkins.count_documents({
            "user_id": tid,
            "checked_in_at": {"$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)},
        })
        return {
            "total_agents": total_agents,
            "active_today": active_today,
            "tasks": {
                "total": total_tasks, "pending": pending,
                "in_progress": in_progress, "completed": completed, "overdue": overdue,
            },
        }

    # ── Collections (field-agent payments for reconciliation) ────────────────

    @router.get("/collections")
    async def list_collections(
        agent_id: Optional[str] = None,
        reconciliation_status: Optional[str] = None,  # unreconciled | reconciled
        user=user_dep,
    ):
        tid = _tid(user)
        q: Dict[str, Any] = {"user_id": tid, "source": "field_agent", "type": "income"}
        if agent_id: q["agent_id"] = agent_id
        if reconciliation_status: q["reconciliation_status"] = reconciliation_status
        docs = await db.finance_entries.find(q, sort=[("date", -1), ("created_at", -1)]).to_list(500)
        # Totals
        total_all          = sum(d["amount"] for d in docs)
        total_unreconciled = sum(d["amount"] for d in docs if d.get("reconciliation_status") != "reconciled")
        total_reconciled   = sum(d["amount"] for d in docs if d.get("reconciliation_status") == "reconciled")
        return {
            "entries": [_ser(d) for d in docs],
            "totals": {
                "all":          round(total_all, 2),
                "unreconciled": round(total_unreconciled, 2),
                "reconciled":   round(total_reconciled, 2),
                "count":        len(docs),
            },
        }

    @router.put("/collections/{entry_id}/reconcile")
    async def reconcile_collection(entry_id: str, user=user_dep):
        tid = _tid(user)
        doc = await db.finance_entries.find_one({"_id": entry_id, "user_id": tid, "source": "field_agent"})
        if not doc: raise HTTPException(404, "Collection entry not found")
        await db.finance_entries.update_one(
            {"_id": entry_id},
            {"$set": {"reconciliation_status": "reconciled", "updated_at": datetime.utcnow()}}
        )
        updated = await db.finance_entries.find_one({"_id": entry_id})
        return _ser(updated)

    @router.post("/collections/reconcile-all")
    async def reconcile_all_collections(user=user_dep):
        tid = _tid(user)
        result = await db.finance_entries.update_many(
            {"user_id": tid, "source": "field_agent", "reconciliation_status": "unreconciled"},
            {"$set": {"reconciliation_status": "reconciled", "updated_at": datetime.utcnow()}}
        )
        return {"reconciled": result.modified_count}

    return router


async def _log_activity(db, user_id, agent_id, agent_name, task_id, activity_type,
                        task_title: str = "", task_type: str = "other", duration_mins: Optional[int] = None):
    try:
        await db.field_agent_activity.insert_one({
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "task_id": task_id,
            "type": activity_type,
            "task_title": task_title,
            "task_type": task_type,
            "duration_mins": duration_mins,
            "created_at": datetime.utcnow(),
        })
    except Exception as e:
        logger.warning("field_agent activity log failed: %s", e)
