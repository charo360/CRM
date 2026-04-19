"""Tool registry for the AI assistant.

Each tool:
- Has a JSON-schema spec the LLM sees
- Has an async implementation that operates on the CRM database
- Is tagged `destructive=True` when it mutates data — the orchestrator can require
  a confirmation turn before executing.

All tools are scoped to the authenticated user via the `ctx` (contains `db`, `user_id`,
`business_id`). Tools never return raw Mongo _id objects — always serialized strings.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Tool context ──────────────────────────────────────────────────────────────
class ToolContext:
    def __init__(self, db, user: Dict[str, Any]):
        self.db = db
        self.user = user
        self.user_id: str = user["_id"]
        self.business_id: str = user.get("business_id") or user["_id"]

# ── Registry types ────────────────────────────────────────────────────────────
ToolImpl = Callable[[ToolContext, Dict[str, Any]], Any]

REGISTRY: Dict[str, Dict[str, Any]] = {}


def tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    destructive: bool = False,
):
    def deco(fn: ToolImpl):
        REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "destructive": destructive,
            "impl": fn,
        }
        return fn
    return deco


def openai_tool_specs() -> List[Dict[str, Any]]:
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        },
    } for t in REGISTRY.values()]


async def run_tool(name: str, ctx: ToolContext, args: Dict[str, Any]) -> Any:
    if name not in REGISTRY:
        return {"error": f"Unknown tool: {name}"}
    try:
        res = await REGISTRY[name]["impl"](ctx, args or {})
        return res
    except Exception as e:
        logger.exception(f"[assistant.tool] {name} failed")
        return {"error": str(e)}


def _s(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (doc or {}).items():
        if k == "_id":
            out["id"] = str(v)
            continue
        if isinstance(v, dict):
            out[k] = _serialize(v)
        elif isinstance(v, list):
            out[k] = [_serialize(x) if isinstance(x, dict) else _s(x) for x in v]
        else:
            out[k] = _s(v)
    return out


# ═════════════════════════════════════════════════════════════════════════════
# READ TOOLS
# ═════════════════════════════════════════════════════════════════════════════
@tool(
    name="list_customers",
    description="List customers for the current business. Use `search` to filter by name/phone substring. Returns up to `limit` records (default 20, max 100).",
    parameters={
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "Optional name or phone substring"},
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            "only_customers": {"type": "boolean", "description": "If true, exclude raw WhatsApp contacts (default true)"},
        },
    },
)
async def list_customers(ctx: ToolContext, args: Dict[str, Any]):
    q: Dict[str, Any] = {"user_id": ctx.business_id}
    if args.get("only_customers", True):
        q["is_customer"] = True
    if s := (args.get("search") or "").strip():
        q["$or"] = [{"name": {"$regex": s, "$options": "i"}}, {"phone_number": {"$regex": s}}]
    limit = min(int(args.get("limit") or 20), 100)
    rows = await ctx.db.customers.find(q).sort("last_interaction", -1).to_list(limit)
    return {"count": len(rows), "customers": [_serialize(r) for r in rows]}


@tool(
    name="get_customer",
    description="Get one customer's full profile and recent activity by id or phone number.",
    parameters={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "phone_number": {"type": "string"},
        },
    },
)
async def get_customer(ctx: ToolContext, args: Dict[str, Any]):
    q: Dict[str, Any] = {"user_id": ctx.business_id}
    if cid := args.get("customer_id"):
        q["_id"] = cid
    elif ph := args.get("phone_number"):
        q["phone_number"] = ph
    else:
        return {"error": "Provide customer_id or phone_number"}
    doc = await ctx.db.customers.find_one(q)
    if not doc:
        return {"error": "Customer not found"}
    recent_msgs = await ctx.db.messages.find(
        {"user_id": ctx.business_id, "customer_id": doc["_id"]}
    ).sort("created_at", -1).limit(10).to_list(10)
    return {
        "customer": _serialize(doc),
        "recent_messages": [_serialize(m) for m in recent_msgs],
    }


@tool(
    name="list_orders",
    description="List recent orders. Filter by status (New/Confirmed/Preparing/Ready/Done) or customer_id.",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "customer_id": {"type": "string"},
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        },
    },
)
async def list_orders(ctx: ToolContext, args: Dict[str, Any]):
    q: Dict[str, Any] = {"user_id": ctx.business_id}
    if st := args.get("status"):
        q["fulfillment_status"] = st
    if cid := args.get("customer_id"):
        q["customer_id"] = cid
    limit = min(int(args.get("limit") or 20), 100)
    rows = await ctx.db.orders.find(q).sort("created_at", -1).to_list(limit)
    return {"count": len(rows), "orders": [_serialize(r) for r in rows]}


@tool(
    name="list_products",
    description="List products in the catalog.",
    parameters={
        "type": "object",
        "properties": {
            "search": {"type": "string"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 100},
        },
    },
)
async def list_products(ctx: ToolContext, args: Dict[str, Any]):
    q: Dict[str, Any] = {"user_id": ctx.business_id}
    if s := (args.get("search") or "").strip():
        q["name"] = {"$regex": s, "$options": "i"}
    limit = min(int(args.get("limit") or 50), 100)
    rows = await ctx.db.products.find(q).sort("created_at", -1).to_list(limit)
    return {"count": len(rows), "products": [_serialize(r) for r in rows]}


@tool(
    name="list_followups",
    description="List follow-up reminders. Filter by status (pending/completed/overdue) or assignee.",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        },
    },
)
async def list_followups(ctx: ToolContext, args: Dict[str, Any]):
    q: Dict[str, Any] = {"user_id": ctx.business_id}
    if st := args.get("status"):
        q["status"] = st
    limit = min(int(args.get("limit") or 20), 100)
    rows = await ctx.db.followups.find(q).sort("reminder_date", 1).to_list(limit)

    # Enrich with customer name/phone for any followups missing that snapshot
    missing_ids = {r["customer_id"] for r in rows if not r.get("customer_name") and r.get("customer_id")}
    name_by_id: Dict[str, Dict[str, str]] = {}
    if missing_ids:
        cust_rows = await ctx.db.customers.find(
            {"_id": {"$in": list(missing_ids)}, "user_id": ctx.business_id}
        ).to_list(len(missing_ids))
        for c in cust_rows:
            name_by_id[c["_id"]] = {
                "name": c.get("name") or "",
                "phone_number": c.get("phone_number") or "",
            }

    out = []
    for r in rows:
        s = _serialize(r)
        cid = r.get("customer_id")
        if (not s.get("customer_name")) and cid in name_by_id:
            s["customer_name"] = name_by_id[cid]["name"]
            s["customer_phone"] = name_by_id[cid].get("phone_number") or s.get("customer_phone")
        out.append(s)
    return {"count": len(out), "followups": out}


@tool(
    name="get_analytics_summary",
    description="High-level business stats: customer count, sales today, revenue, active orders, bookings today.",
    parameters={"type": "object", "properties": {}},
)
async def get_analytics_summary(ctx: ToolContext, args: Dict[str, Any]):
    now = datetime.utcnow()
    start = datetime(now.year, now.month, now.day)

    customers_count = await ctx.db.customers.count_documents({"user_id": ctx.business_id, "is_customer": True})
    active_orders = await ctx.db.orders.count_documents({
        "user_id": ctx.business_id,
        "fulfillment_status": {"$nin": ["Done", "Delivered", "Cancelled"]},
    })
    sales_today_cur = ctx.db.sales.find({"user_id": ctx.business_id, "sale_date": {"$gte": start}})
    sales_today = await sales_today_cur.to_list(500)
    sales_revenue_today = sum(float(s.get("amount") or 0) for s in sales_today)
    bookings_today = await ctx.db.bookings.count_documents({
        "user_id": ctx.business_id,
        "booking_date": {"$gte": start, "$lt": start + timedelta(days=1)},
    })
    return {
        "customers_count": customers_count,
        "active_orders": active_orders,
        "sales_count_today": len(sales_today),
        "sales_revenue_today": sales_revenue_today,
        "bookings_today": bookings_today,
    }


@tool(
    name="list_broadcasts",
    description="List recent broadcasts and their delivery stats.",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50}},
    },
)
async def list_broadcasts(ctx: ToolContext, args: Dict[str, Any]):
    limit = min(int(args.get("limit") or 10), 50)
    rows = await ctx.db.broadcasts.find({"user_id": ctx.business_id}).sort("created_at", -1).to_list(limit)
    return {"count": len(rows), "broadcasts": [_serialize(r) for r in rows]}


# ═════════════════════════════════════════════════════════════════════════════
# WRITE TOOLS (destructive=True → require user confirmation)
# ═════════════════════════════════════════════════════════════════════════════
@tool(
    name="create_customer",
    description="Create a new customer record. Phone number must be in international format (e.g. +254712345678).",
    parameters={
        "type": "object",
        "required": ["name", "phone_number"],
        "properties": {
            "name": {"type": "string"},
            "phone_number": {"type": "string"},
            "email": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
        },
    },
    destructive=True,
)
async def create_customer(ctx: ToolContext, args: Dict[str, Any]):
    phone = (args.get("phone_number") or "").strip()
    name = (args.get("name") or "").strip()
    if not phone or not name:
        return {"error": "name and phone_number are required"}
    existing = await ctx.db.customers.find_one({"user_id": ctx.business_id, "phone_number": phone})
    if existing:
        await ctx.db.customers.update_one(
            {"_id": existing["_id"]},
            {"$set": {"name": name, "is_customer": True, "updated_at": datetime.utcnow()}},
        )
        return {"status": "updated_existing", "customer_id": existing["_id"]}
    cid = str(uuid.uuid4())
    doc = {
        "_id": cid,
        "user_id": ctx.business_id,
        "name": name,
        "phone_number": phone,
        "email": (args.get("email") or "").strip() or None,
        "tags": args.get("tags") or [],
        "notes": (args.get("notes") or "").strip() or None,
        "is_customer": True,
        "auto_created": False,
        "created_at": datetime.utcnow(),
        "last_interaction": datetime.utcnow(),
    }
    await ctx.db.customers.insert_one(doc)
    return {"status": "created", "customer_id": cid}


@tool(
    name="create_followup",
    description="Create a follow-up reminder for a customer. `when` accepts an ISO datetime OR a natural phrase like 'tomorrow 10am', '+3 days', 'next monday'.",
    parameters={
        "type": "object",
        "required": ["customer_id", "when"],
        "properties": {
            "customer_id": {"type": "string"},
            "when": {"type": "string", "description": "ISO datetime or natural phrase"},
            "type": {"type": "string", "enum": ["call", "whatsapp", "email", "meeting"], "default": "whatsapp"},
            "message": {"type": "string", "description": "Note or draft message"},
        },
    },
    destructive=True,
)
async def create_followup(ctx: ToolContext, args: Dict[str, Any]):
    cust = await ctx.db.customers.find_one({"_id": args["customer_id"], "user_id": ctx.business_id})
    if not cust:
        return {"error": "Customer not found"}
    when_raw = (args.get("when") or "").strip()
    reminder = _parse_when(when_raw)
    if not reminder:
        return {"error": f"Could not parse 'when': {when_raw!r}"}
    fid = str(uuid.uuid4())
    await ctx.db.followups.insert_one({
        "_id": fid,
        "user_id": ctx.business_id,
        "customer_id": cust["_id"],
        "customer_name": cust.get("name", ""),
        "customer_phone": cust.get("phone_number", ""),
        "reminder_date": reminder,
        "type": args.get("type") or "whatsapp",
        "message": (args.get("message") or "").strip(),
        "status": "pending",
        "created_at": datetime.utcnow(),
    })
    return {"status": "created", "followup_id": fid, "reminder_date": reminder.isoformat()}


@tool(
    name="get_owner_info",
    description="Return the business owner's name, phone number, business name and settings. Use this when the user refers to 'owner', 'me', 'my number', or 'myself'.",
    parameters={"type": "object", "properties": {}},
    destructive=False,
)
async def get_owner_info(ctx: ToolContext, args: Dict[str, Any]):
    user = await ctx.db.users.find_one({"_id": ctx.business_id})
    if not user:
        return {"error": "Owner record not found"}
    settings = user.get("settings", {})
    return {
        "owner_name":    user.get("owner_name") or user.get("name", ""),
        "business_name": user.get("business_name", ""),
        "phone_number":  user.get("phone_number") or settings.get("phone_number", ""),
        "email":         user.get("email", ""),
        "country":       settings.get("country", ""),
        "currency":      settings.get("currency", ""),
        "whatsapp_number": (user.get("whatsapp") or {}).get("number", ""),
    }


@tool(
    name="send_whatsapp_message",
    description=(
        "Send a WhatsApp message. Accepts EITHER customer_id OR phone_number (international format). "
        "Use get_owner_info first if the user says 'send to me / owner / myself'."
    ),
    parameters={
        "type": "object",
        "required": ["message"],
        "properties": {
            "customer_id": {"type": "string", "description": "CRM customer ID (use if known)"},
            "phone_number": {"type": "string", "description": "Phone in international format e.g. +254712345678 (use when no customer_id)"},
            "message": {"type": "string"},
        },
    },
    destructive=True,
)
async def send_whatsapp_message(ctx: ToolContext, args: Dict[str, Any]):
    from whatsapp_service import get_whatsapp_service
    wa = get_whatsapp_service(ctx.db)

    to_number: str = ""
    customer_name: str = ""

    if args.get("customer_id"):
        cust = await ctx.db.customers.find_one({"_id": args["customer_id"], "user_id": ctx.business_id})
        if not cust:
            return {"error": f"Customer '{args['customer_id']}' not found. Use get_customers to look up the correct ID, or provide a phone_number directly."}
        to_number = cust.get("phone_number", "")
        customer_name = cust.get("name", "")
    elif args.get("phone_number"):
        to_number = args["phone_number"]
        # Try to find a matching customer name for context
        cust = await ctx.db.customers.find_one({"phone_number": to_number, "user_id": ctx.business_id})
        customer_name = cust.get("name", "") if cust else ""
    else:
        return {"error": "Provide either customer_id or phone_number."}

    if not to_number:
        return {"error": "No phone number available for this customer."}

    try:
        res = await wa.send_message(
            user_id=ctx.business_id,
            to_number=to_number,
            message=args["message"],
            customer_name=customer_name,
            send_context="assistant",
        )
        return {"status": "sent", "to": to_number, "provider_response": res}
    except Exception as e:
        return {"error": str(e)}


@tool(
    name="create_broadcast",
    description="Create and send a broadcast immediately to an audience. `filter_type` is one of: all, returning, vip, new, or 'custom' with explicit customer_ids.",
    parameters={
        "type": "object",
        "required": ["message"],
        "properties": {
            "message": {"type": "string"},
            "name": {"type": "string"},
            "filter_type": {"type": "string", "default": "all"},
            "customer_ids": {"type": "array", "items": {"type": "string"}},
        },
    },
    destructive=True,
)
async def create_broadcast(ctx: ToolContext, args: Dict[str, Any]):
    import httpx  # reuse HTTP to call our own endpoint is overkill; do it directly.
    # Instead: piggy-back on the existing broadcasts insert, then kick the sender.
    bid = str(uuid.uuid4())
    doc = {
        "_id": bid,
        "user_id": ctx.business_id,
        "name": (args.get("name") or "").strip() or None,
        "message": args["message"],
        "filter_type": args.get("filter_type") or "all",
        "customer_ids": args.get("customer_ids") or None,
        "status": "queued",
        "created_at": datetime.utcnow(),
    }
    await ctx.db.broadcasts.insert_one(doc)
    return {
        "status": "queued",
        "broadcast_id": bid,
        "note": "Broadcast created; it will be delivered by the broadcast worker on its next cycle.",
    }


# ═════════════════════════════════════════════════════════════════════════════
# CHANNEL ADMIN
# ═════════════════════════════════════════════════════════════════════════════
@tool(
    name="update_customer",
    description="Update fields on an existing customer. Only the provided fields are changed.",
    parameters={
        "type": "object",
        "required": ["customer_id"],
        "properties": {
            "customer_id": {"type": "string"},
            "name": {"type": "string"},
            "phone_number": {"type": "string"},
            "email": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
        },
    },
    destructive=True,
)
async def update_customer(ctx: ToolContext, args: Dict[str, Any]):
    cid = args["customer_id"]
    updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    for k in ("name", "phone_number", "email", "notes"):
        if k in args and args[k] is not None:
            updates[k] = args[k]
    if "tags" in args and isinstance(args["tags"], list):
        updates["tags"] = args["tags"]
    res = await ctx.db.customers.update_one(
        {"_id": cid, "user_id": ctx.business_id},
        {"$set": updates},
    )
    if res.matched_count == 0:
        return {"error": "Customer not found"}
    return {"status": "updated", "customer_id": cid, "changed": list(updates.keys())}


@tool(
    name="delete_customer",
    description="Delete a customer and all of their follow-ups. Messages are kept for audit. Irreversible.",
    parameters={
        "type": "object",
        "required": ["customer_id"],
        "properties": {"customer_id": {"type": "string"}},
    },
    destructive=True,
)
async def delete_customer(ctx: ToolContext, args: Dict[str, Any]):
    cid = args["customer_id"]
    cust = await ctx.db.customers.find_one({"_id": cid, "user_id": ctx.business_id})
    if not cust:
        return {"error": "Customer not found"}
    await ctx.db.customers.delete_one({"_id": cid, "user_id": ctx.business_id})
    await ctx.db.followups.delete_many({"customer_id": cid, "user_id": ctx.business_id})
    return {"status": "deleted", "customer_id": cid, "name": cust.get("name")}


@tool(
    name="create_product",
    description="Add a product to the catalog.",
    parameters={
        "type": "object",
        "required": ["name", "price"],
        "properties": {
            "name": {"type": "string"},
            "price": {"type": "number"},
            "description": {"type": "string"},
            "in_stock": {"type": "boolean", "default": True},
        },
    },
    destructive=True,
)
async def create_product(ctx: ToolContext, args: Dict[str, Any]):
    pid = str(uuid.uuid4())
    await ctx.db.products.insert_one({
        "_id": pid,
        "user_id": ctx.business_id,
        "name": (args.get("name") or "").strip(),
        "price": float(args.get("price") or 0),
        "description": (args.get("description") or "").strip() or None,
        "in_stock": bool(args.get("in_stock", True)),
        "images": [],
        "created_at": datetime.utcnow(),
    })
    return {"status": "created", "product_id": pid}


@tool(
    name="update_product",
    description="Update a product in the catalog (price, name, description, stock).",
    parameters={
        "type": "object",
        "required": ["product_id"],
        "properties": {
            "product_id": {"type": "string"},
            "name": {"type": "string"},
            "price": {"type": "number"},
            "description": {"type": "string"},
            "in_stock": {"type": "boolean"},
        },
    },
    destructive=True,
)
async def update_product(ctx: ToolContext, args: Dict[str, Any]):
    pid = args["product_id"]
    updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    for k in ("name", "description"):
        if k in args and args[k] is not None:
            updates[k] = args[k]
    if "price" in args and args["price"] is not None:
        updates["price"] = float(args["price"])
    if "in_stock" in args and args["in_stock"] is not None:
        updates["in_stock"] = bool(args["in_stock"])
    res = await ctx.db.products.update_one(
        {"_id": pid, "user_id": ctx.business_id},
        {"$set": updates},
    )
    if res.matched_count == 0:
        return {"error": "Product not found"}
    return {"status": "updated", "product_id": pid, "changed": list(updates.keys())}


@tool(
    name="delete_product",
    description="Remove a product from the catalog.",
    parameters={
        "type": "object",
        "required": ["product_id"],
        "properties": {"product_id": {"type": "string"}},
    },
    destructive=True,
)
async def delete_product(ctx: ToolContext, args: Dict[str, Any]):
    pid = args["product_id"]
    res = await ctx.db.products.delete_one({"_id": pid, "user_id": ctx.business_id})
    if res.deleted_count == 0:
        return {"error": "Product not found"}
    return {"status": "deleted", "product_id": pid}


@tool(
    name="update_order_status",
    description="Move an order through its fulfillment lifecycle. Allowed: New, Confirmed, Preparing, Ready, Done, Cancelled.",
    parameters={
        "type": "object",
        "required": ["order_id", "status"],
        "properties": {
            "order_id": {"type": "string"},
            "status": {"type": "string", "enum": ["New", "Confirmed", "Preparing", "Ready", "Done", "Cancelled"]},
        },
    },
    destructive=True,
)
async def update_order_status(ctx: ToolContext, args: Dict[str, Any]):
    oid = args["order_id"]
    res = await ctx.db.orders.update_one(
        {"_id": oid, "user_id": ctx.business_id},
        {"$set": {"fulfillment_status": args["status"], "updated_at": datetime.utcnow()}},
    )
    if res.matched_count == 0:
        return {"error": "Order not found"}
    return {"status": "updated", "order_id": oid, "new_status": args["status"]}


@tool(
    name="record_sale",
    description="Record a manual sale against a customer. Amount is in the business's default currency.",
    parameters={
        "type": "object",
        "required": ["customer_id", "amount"],
        "properties": {
            "customer_id": {"type": "string"},
            "amount": {"type": "number"},
            "description": {"type": "string"},
            "payment_method": {"type": "string"},
        },
    },
    destructive=True,
)
async def record_sale(ctx: ToolContext, args: Dict[str, Any]):
    cust = await ctx.db.customers.find_one({"_id": args["customer_id"], "user_id": ctx.business_id})
    if not cust:
        return {"error": "Customer not found"}
    sid = str(uuid.uuid4())
    await ctx.db.sales.insert_one({
        "_id": sid,
        "user_id": ctx.business_id,
        "customer_id": cust["_id"],
        "customer_name": cust.get("name", ""),
        "amount": float(args["amount"]),
        "description": (args.get("description") or "").strip() or None,
        "payment_method": (args.get("payment_method") or "").strip() or None,
        "source": "sale",
        "sale_date": datetime.utcnow(),
        "created_at": datetime.utcnow(),
    })
    return {"status": "recorded", "sale_id": sid, "amount": args["amount"]}


@tool(
    name="list_team",
    description="List team members on this business account and their roles.",
    parameters={"type": "object", "properties": {}},
)
async def list_team(ctx: ToolContext, args: Dict[str, Any]):
    rows = await ctx.db.team_members.find({"business_id": ctx.business_id}).to_list(100)
    return {"count": len(rows), "members": [_serialize(r) for r in rows]}


@tool(
    name="integrations_status",
    description="Return the connection state of every integrated channel (WhatsApp, Telegram, Meta Messenger/Instagram).",
    parameters={"type": "object", "properties": {}},
)
async def integrations_status(ctx: ToolContext, args: Dict[str, Any]):
    out: Dict[str, Any] = {}
    # WhatsApp
    try:
        from whatsapp_service import get_whatsapp_service
        wa = get_whatsapp_service(ctx.db)
        status = await wa.get_instance_status(ctx.business_id)
        out["whatsapp"] = {"connected": bool(status.get("connected")), "state": status.get("state")}
    except Exception as e:
        out["whatsapp"] = {"connected": False, "error": str(e)}
    # Telegram
    tg = await ctx.db.telegram_connections.find_one({"user_id": ctx.business_id})
    out["telegram"] = {"connected": bool(tg), "bot_username": (tg or {}).get("bot_username")}
    # Meta
    meta_rows = await ctx.db.meta_connections.find({"user_id": ctx.business_id}).to_list(10)
    out["meta"] = [
        {"channel": r.get("channel"), "page_id": r.get("page_id"), "connected": True}
        for r in meta_rows
    ]
    return out


@tool(
    name="telegram_status",
    description="Get the current Telegram bot connection state for this account.",
    parameters={"type": "object", "properties": {}},
)
async def telegram_status(ctx: ToolContext, args: Dict[str, Any]):
    conn = await ctx.db.telegram_connections.find_one({"user_id": ctx.business_id})
    if not conn:
        return {"connected": False}
    return {"connected": True, "bot_username": conn.get("bot_username", "")}


@tool(
    name="disconnect_telegram",
    description="Disconnect the Telegram bot from this account. Incoming Telegram messages will stop.",
    parameters={"type": "object", "properties": {}},
    destructive=True,
)
async def disconnect_telegram(ctx: ToolContext, args: Dict[str, Any]):
    conn = await ctx.db.telegram_connections.find_one({"user_id": ctx.business_id})
    if not conn:
        return {"status": "not_connected"}
    try:
        from telegram_service import delete_telegram_webhook
        await delete_telegram_webhook(conn["bot_token"])
    except Exception as e:
        logger.warning(f"telegram webhook delete failed: {e}")
    await ctx.db.telegram_connections.delete_one({"user_id": ctx.business_id})
    return {"status": "disconnected"}


# ═════════════════════════════════════════════════════════════════════════════
# DOCUMENT RETRIEVAL
# ═════════════════════════════════════════════════════════════════════════════
@tool(
    name="search_documents",
    description=(
        "Semantic search across the documents the user has attached to this conversation. "
        "Use this when a document is long and you need the specific passages that answer the user's question. "
        "Returns the top matching chunks with the originating filename."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural-language question or keywords to search for."},
            "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
)
async def search_documents(ctx: ToolContext, args: Dict[str, Any]):
    from .embeddings import search_chunks  # lazy import to avoid cycles
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    conv_id = (ctx.user or {}).get("_active_conversation_id")
    if not conv_id:
        return {"error": "No active conversation context — cannot search documents."}
    top_k = min(max(int(args.get("top_k") or 5), 1), 10)
    hits = await search_chunks(
        ctx.db,
        user_id=ctx.business_id,
        conversation_id=conv_id,
        query=query,
        top_k=top_k,
    )
    return {
        "query": query,
        "count": len(hits),
        "results": [
            {
                "filename": h["filename"],
                "chunk_index": h["chunk_index"],
                "score": round(h["score"], 4),
                "text": h["text"],
            }
            for h in hits
        ],
    }


# ─── helpers ──────────────────────────────────────────────────────────────────
def _parse_when(raw: str) -> Optional[datetime]:
    raw = raw.strip().lower()
    if not raw:
        return None
    # ISO 8601
    try:
        dt = datetime.fromisoformat(raw.replace("z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        pass
    now = datetime.utcnow()
    # +N days / +Nh
    if raw.startswith("+"):
        try:
            n = int("".join(c for c in raw if c.isdigit() or c == "-"))
            if raw.endswith("h"):
                return now + timedelta(hours=n)
            return now + timedelta(days=n)
        except Exception:
            pass
    if raw in ("tomorrow", "tmrw"):
        return (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    if raw == "today":
        return now + timedelta(hours=2)
    if "day" in raw and raw.split()[0].isdigit():
        try:
            n = int(raw.split()[0])
            return now + timedelta(days=n)
        except Exception:
            pass
    return None
