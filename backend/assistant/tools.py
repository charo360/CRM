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

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

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


def openai_tool_specs_filtered(allowed: Optional[Set[str]]) -> List[Dict[str, Any]]:
    """If allowed is None, return all tools; otherwise only named tools (must exist in REGISTRY)."""
    if not allowed:
        return openai_tool_specs()
    out: List[Dict[str, Any]] = []
    for name in sorted(allowed):
        t = REGISTRY.get(name)
        if not t:
            continue
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        })
    return out


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
    description="List products in the catalog with full details including images.",
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
    
    products = []
    for p in rows:
        # Handle images like the backend API does
        imgs = list(p.get("images", []))
        orig = p.get("image_url")
        if orig and orig not in imgs:
            imgs.insert(0, orig)
            
        product = {
            "id": str(p["_id"]),
            "name": p.get("name", "Unnamed Product"),
            "price": p.get("price") or 0.0,
            "discount_price": p.get("discount_price"),
            "category": p.get("category") or "Other",
            "sub_category": p.get("sub_category"),
            "image_url": orig,
            "images": imgs,
            "description": p.get("description"),
            "in_stock": p.get("in_stock", True),
            "stock_quantity": p.get("stock_quantity"),
            "unit": p.get("unit"),
            "moq": p.get("moq"),
            "pricing_tiers": p.get("pricing_tiers") or None,
            "variants": p.get("variants") or None,
            "modifier_groups": p.get("modifier_groups") or None,
            "created_at": p.get("created_at")
        }
        products.append(product)
    
    return {"count": len(products), "products": products}


@tool(
    name="get_product_images",
    description="Get all available images for a specific product including the main image and additional photos.",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "string", "description": "Product ID to get images for"},
        },
        "required": ["product_id"],
    },
)
async def get_product_images(ctx: ToolContext, args: Dict[str, Any]):
    product_id = args["product_id"]
    product = await ctx.db.products.find_one({"_id": product_id, "user_id": ctx.business_id})
    if not product:
        return {"error": "Product not found"}
    
    # Handle images like the backend API does
    imgs = list(product.get("images", []))
    orig = product.get("image_url")
    if orig and orig not in imgs:
        imgs.insert(0, orig)
    
    return {
        "product_id": product_id,
        "product_name": product.get("name", "Unnamed Product"),
        "image_url": orig,
        "images": imgs,
        "image_count": len(imgs)
    }


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
    description=(
        "Return the business owner's name, phone, business name, currency, country, "
        "business_type (industry), and short hints from business knowledge. "
        "Use for Meta/Google ads, proposals, and any time industry-aware advice is needed."
    ),
    parameters={"type": "object", "properties": {}},
    destructive=False,
)
async def get_owner_info(ctx: ToolContext, args: Dict[str, Any]):
    user = await ctx.db.users.find_one({"_id": ctx.business_id})
    if not user:
        return {"error": "Owner record not found"}
    settings = user.get("settings", {}) or {}
    bk = user.get("business_knowledge") or {}
    return {
        "owner_name":    user.get("owner_name") or user.get("name", ""),
        "business_name": user.get("business_name", ""),
        "phone_number":  user.get("phone_number") or settings.get("phone_number", ""),
        "email":         user.get("email", ""),
        "country":       settings.get("country", ""),
        "currency":      settings.get("currency", ""),
        "whatsapp_number": (user.get("whatsapp") or {}).get("number", ""),
        "business_type":   (settings.get("business_type") or "").strip(),
        "business_description_hint": (bk.get("business_description") or "")[:400],
        "products_services_hint":    (bk.get("products_services") or "")[:400],
    }


@tool(
    name="list_design_library_assets",
    description=(
        "List entries from the **Design library** for this business: uploaded brand kit files (logos, images, reference PDFs), "
        "chat-generated graphics/PDFs/decks, and optional manual template rows. "
        "Use the returned `file_url_public` when you need a browser-reachable URL. "
        "Call this after the user says they uploaded new brand files, or when planning creatives."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sources": {
                "type": "string",
                "description": "Optional filter: `all` (default), or comma-separated: `brand_kit`, `assistant_generated`, `manual`.",
            },
        },
    },
    destructive=False,
)
async def list_design_library_assets(ctx: ToolContext, args: Dict[str, Any]):
    from saved_designs import list_library_for_tool

    src = (args.get("sources") or "all") if isinstance(args.get("sources"), str) else "all"
    items = await list_library_for_tool(ctx.db, ctx.business_id, sources_filter=src, limit=60)
    return {"count": len(items), "assets": items}


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
    description="Add a product to the Zilo CRM catalog (WhatsApp/catalog/broadcasts). This is not the same as creating a product in Shopify Admin — use shopify_add_product only when the user wants it on their connected Shopify store.",
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
    description=(
        "Return the connection state of every integration: WhatsApp, Telegram, Meta, "
        "and all Nango-connected apps (Shopify, Stripe, Klaviyo, Mailchimp, Brevo, "
        "Slack, Gmail, Microsoft, Google Calendar)."
    ),
    parameters={"type": "object", "properties": {}},
)
async def integrations_status(ctx: ToolContext, args: Dict[str, Any]):
    import os
    out: Dict[str, Any] = {}

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    try:
        from whatsapp_service import get_whatsapp_service
        wa = get_whatsapp_service(ctx.db)
        status = await wa.get_instance_status(ctx.business_id)
        out["whatsapp"] = {"connected": bool(status.get("connected")), "state": status.get("state")}
    except Exception as e:
        out["whatsapp"] = {"connected": False, "error": str(e)}

    # ── Telegram ──────────────────────────────────────────────────────────────
    tg = await ctx.db.telegram_connections.find_one({"user_id": ctx.business_id})
    out["telegram"] = {"connected": bool(tg), "bot_username": (tg or {}).get("bot_username")}

    # ── Meta (Facebook/Instagram) ─────────────────────────────────────────────
    meta_rows = await ctx.db.meta_connections.find({"user_id": ctx.business_id}).to_list(10)
    out["meta"] = [
        {"channel": r.get("channel"), "page_id": r.get("page_id"), "connected": True}
        for r in meta_rows
    ]

    # ── Nango-connected apps ──────────────────────────────────────────────────
    # Maps human-readable key → Nango provider_config_key
    _NANGO_INTEGRATIONS = {
        "shopify":         os.getenv("NEXT_PUBLIC_NANGO_ID_SHOPIFY",   "shopify"),
        "stripe":          os.getenv("NEXT_PUBLIC_NANGO_ID_STRIPE",    "stripe"),
        "klaviyo":         os.getenv("NEXT_PUBLIC_NANGO_ID_KLAVIYO",   "klaviyo"),
        "mailchimp":       os.getenv("NEXT_PUBLIC_NANGO_ID_MAILCHIMP", "mailchimp"),
        "brevo":           os.getenv("NEXT_PUBLIC_NANGO_ID_BREVO",     "brevo"),
        "slack":           os.getenv("NEXT_PUBLIC_NANGO_ID_SLACK",     "slack"),
        "gmail":           os.getenv("NEXT_PUBLIC_NANGO_ID_EMAIL",     "google-mail"),
        "microsoft":       os.getenv("NEXT_PUBLIC_NANGO_ID_MICROSOFT", "microsoft"),
        "google_calendar": os.getenv("NEXT_PUBLIC_NANGO_ID_CALENDAR",  "google-calendar"),
    }
    nango_secret = os.getenv("NANGO_SECRET_KEY")
    nango_api    = os.getenv("NANGO_API_URL", "https://api.nango.dev")
    nango_status: Dict[str, bool] = {k: False for k in _NANGO_INTEGRATIONS}

    if nango_secret:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    f"{nango_api}/connection",
                    params={"end_user_id": ctx.business_id},
                    headers={"Authorization": f"Bearer {nango_secret}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    connected_keys = {
                        c["provider_config_key"]
                        for c in data.get("connections", [])
                    }
                    for key, nango_id in _NANGO_INTEGRATIONS.items():
                        nango_status[key] = nango_id in connected_keys
        except Exception as e:
            logger.warning(f"[integrations_status] Nango lookup failed: {e}")

    out["nango"] = {k: {"connected": v} for k, v in nango_status.items()}

    # Flat convenience summary for the agent
    out["summary"] = (
        "Connected: "
        + ", ".join(
            k for k, v in {
                "WhatsApp": out["whatsapp"]["connected"],
                "Telegram": out["telegram"]["connected"],
                **{k.replace("_", " ").title(): v for k, v in nango_status.items()},
            }.items()
            if v
        )
        or "none"
    )
    return out


# ═════════════════════════════════════════════════════════════════════════════
# SHOPIFY TOOLS (via Nango proxy)
# ═════════════════════════════════════════════════════════════════════════════

@tool(
    name="list_shopify_orders",
    description=(
        "Fetch orders from the connected Shopify store. "
        "Returns order number, customer, items, status, total, and fulfilment info. "
        "Requires Shopify to be connected in Integrations."
    ),
    parameters={
        "type": "object",
        "properties": {
            "status":    {"type": "string", "default": "any",  "description": "any | open | closed | cancelled"},
            "limit":     {"type": "integer", "default": 25,    "description": "Max orders to return (1-250)"},
            "since_days":{"type": "integer", "default": 7,     "description": "Only orders from the last N days"},
        },
    },
)
async def list_shopify_orders(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    from datetime import timezone
    status = args.get("status", "any")
    limit  = min(int(args.get("limit", 25)), 250)
    days   = int(args.get("since_days", 7))
    since  = (datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        data = await nango_proxy(
            ctx.business_id, "shopify", "GET",
            "/admin/api/2024-01/orders.json",
            params={"status": status, "limit": limit, "created_at_min": since},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    orders = data.get("orders", [])
    out = []
    for o in orders:
        out.append({
            "order_number":      o.get("order_number"),
            "name":              o.get("name"),
            "customer":          ((o.get("customer") or {}).get("first_name", "") + " " +
                                  (o.get("customer") or {}).get("last_name", "")).strip() or "Guest",
            "email":             o.get("email"),
            "total_price":       o.get("total_price"),
            "currency":          o.get("currency"),
            "financial_status":  o.get("financial_status"),
            "fulfillment_status":o.get("fulfillment_status") or "unfulfilled",
            "item_count":        len(o.get("line_items", [])),
            "items":             [{"title": i["title"], "qty": i["quantity"], "price": i["price"]}
                                  for i in o.get("line_items", [])[:5]],
            "created_at":        (o.get("created_at") or "")[:10],
        })
    return {"count": len(out), "orders": out, "status_filter": status}


@tool(
    name="list_shopify_products",
    description=(
        "Fetch products from the connected Shopify store including inventory levels. "
        "Requires Shopify to be connected in Integrations."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit":  {"type": "integer", "default": 50, "description": "Max products (1-250)"},
            "status": {"type": "string",  "default": "active", "description": "active | draft | archived"},
        },
    },
)
async def list_shopify_products(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    limit  = min(int(args.get("limit", 50)), 250)
    status = args.get("status", "active")
    try:
        data = await nango_proxy(
            ctx.business_id, "shopify", "GET",
            "/admin/api/2024-01/products.json",
            params={"limit": limit, "status": status},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    products = data.get("products", [])
    out = []
    for p in products:
        variants = p.get("variants", [])
        total_inventory = sum(v.get("inventory_quantity", 0) for v in variants)
        out.append({
            "id":            p.get("id"),
            "title":         p.get("title"),
            "status":        p.get("status"),
            "product_type":  p.get("product_type"),
            "vendor":        p.get("vendor"),
            "variant_count": len(variants),
            "price_range":   f"{min(v.get('price','0') for v in variants)} – {max(v.get('price','0') for v in variants)}" if variants else "N/A",
            "total_inventory": total_inventory,
            "tags":          p.get("tags"),
        })
    return {"count": len(out), "products": out}


@tool(
    name="get_shopify_analytics",
    description=(
        "Get sales analytics from the connected Shopify store: total revenue, order count, "
        "average order value, top products. Requires Shopify to be connected."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "default": 30, "description": "Period in days (e.g. 7, 30, 90)"},
        },
    },
)
async def get_shopify_analytics(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    from datetime import timezone
    days  = int(args.get("days", 30))
    since = (datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        data = await nango_proxy(
            ctx.business_id, "shopify", "GET",
            "/admin/api/2024-01/orders.json",
            params={"status": "any", "financial_status": "paid", "limit": 250, "created_at_min": since},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    orders = data.get("orders", [])
    if not orders:
        return {"period_days": days, "order_count": 0, "revenue": 0, "aov": 0, "top_products": []}
    revenue = sum(float(o.get("total_price", 0)) for o in orders)
    aov     = revenue / len(orders) if orders else 0
    # Top products by revenue
    product_rev: Dict[str, float] = {}
    for o in orders:
        for item in o.get("line_items", []):
            name = item.get("title", "Unknown")
            product_rev[name] = product_rev.get(name, 0) + float(item.get("price", 0)) * item.get("quantity", 1)
    top = sorted(product_rev.items(), key=lambda x: x[1], reverse=True)[:5]
    currency = orders[0].get("currency", "") if orders else ""
    return {
        "period_days":  days,
        "order_count":  len(orders),
        "revenue":      round(revenue, 2),
        "currency":     currency,
        "aov":          round(aov, 2),
        "top_products": [{"product": k, "revenue": round(v, 2)} for k, v in top],
    }


# ── Shopify action tools (autopilot / write) ──────────────────────────────────

@tool(
    name="shopify_fulfill_order",
    description=(
        "Fulfill a Shopify order — marks it as fulfilled and optionally sets a tracking number. "
        "Requires Shopify to be connected. This is a destructive action that mutates Shopify data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "order_id":       {"type": "string",  "description": "Shopify order ID (numeric string)"},
            "tracking_number":{"type": "string",  "description": "Optional tracking number"},
            "tracking_company":{"type": "string", "description": "Optional carrier name, e.g. 'DHL', 'FedEx'"},
            "notify_customer":{"type": "boolean", "default": True, "description": "Send fulfillment notification email to customer"},
        },
        "required": ["order_id"],
    },
    destructive=True,
)
async def shopify_fulfill_order(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    order_id = str(args["order_id"])
    try:
        # Get fulfillment orders
        fo_data = await nango_proxy(
            ctx.business_id, "shopify", "GET",
            f"/admin/api/2024-01/orders/{order_id}/fulfillment_orders.json",
        )
        fo_list = fo_data.get("fulfillment_orders", [])
        open_fos = [fo for fo in fo_list if fo.get("status") == "open"]
        if not open_fos:
            return {"error": "No open fulfillment orders found for this order"}

        line_items_by_fo = [
            {"fulfillment_order_id": fo["id"], "fulfillment_order_line_items": [
                {"id": li["id"], "quantity": li["fulfillable_quantity"]}
                for li in fo.get("line_items", [])
            ]}
            for fo in open_fos
        ]
        payload: Dict[str, Any] = {
            "fulfillment": {
                "line_items_by_fulfillment_order": line_items_by_fo,
                "notify_customer": args.get("notify_customer", True),
            }
        }
        if args.get("tracking_number"):
            payload["fulfillment"]["tracking_info"] = {
                "number": args["tracking_number"],
                "company": args.get("tracking_company", ""),
            }
        result = await nango_proxy(
            ctx.business_id, "shopify", "POST",
            "/admin/api/2024-01/fulfillments.json",
            json=payload,
        )
        return {"success": True, "fulfillment_id": result.get("fulfillment", {}).get("id"), "order_id": order_id}
    except RuntimeError as e:
        return {"error": str(e)}


@tool(
    name="shopify_cancel_order",
    description=(
        "Cancel a Shopify order with an optional reason and refund flag. "
        "Requires Shopify to be connected. This is a destructive action."
    ),
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "string",  "description": "Shopify order ID (numeric string)"},
            "reason":   {"type": "string",  "default": "other", "description": "customer | inventory | fraud | declined | other"},
            "refund":   {"type": "boolean", "default": False,   "description": "Issue a full refund on cancellation"},
            "email":    {"type": "boolean", "default": True,    "description": "Notify customer by email"},
        },
        "required": ["order_id"],
    },
    destructive=True,
)
async def shopify_cancel_order(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    order_id = str(args["order_id"])
    try:
        result = await nango_proxy(
            ctx.business_id, "shopify", "POST",
            f"/admin/api/2024-01/orders/{order_id}/cancel.json",
            json={
                "reason": args.get("reason", "other"),
                "refund":  args.get("refund", False),
                "email":   args.get("email", True),
            },
        )
        return {"success": True, "order_id": order_id, "status": result.get("order", {}).get("financial_status")}
    except RuntimeError as e:
        return {"error": str(e)}


@tool(
    name="shopify_create_discount",
    description=(
        "Create a Shopify discount code — percentage or fixed amount. "
        "Great for win-back campaigns, abandoned cart recovery, loyalty rewards. "
        "Requires Shopify to be connected. Destructive action."
    ),
    parameters={
        "type": "object",
        "properties": {
            "code":            {"type": "string",  "description": "Discount code, e.g. 'SAVE20'. Leave blank to auto-generate."},
            "type":            {"type": "string",  "default": "percentage", "description": "percentage | fixed_amount"},
            "value":           {"type": "number",  "description": "Discount value. For percentage: 10 means 10%. For fixed: 10 means $10 off."},
            "min_order_amount":{"type": "number",  "default": 0,   "description": "Minimum order subtotal to qualify"},
            "usage_limit":     {"type": "integer", "default": 1,   "description": "Max total redemptions (1 = single-use)"},
            "expiry_days":     {"type": "integer", "default": 30,  "description": "Days until the code expires"},
        },
        "required": ["value"],
    },
    destructive=True,
)
async def shopify_create_discount(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    import random, string
    from datetime import timezone
    code = (args.get("code") or "").strip().upper() or "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    value = float(args["value"])
    discount_type = args.get("type", "percentage")
    expiry_days   = int(args.get("expiry_days", 30))
    ends_at = (datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(days=expiry_days)).isoformat()
    try:
        # Create price rule
        pr_payload: Dict[str, Any] = {
            "price_rule": {
                "title": code,
                "target_type": "line_item",
                "target_selection": "all",
                "allocation_method": "across",
                "value_type": "percentage" if discount_type == "percentage" else "fixed_amount",
                "value": f"-{value}" if discount_type == "percentage" else f"-{value}",
                "customer_selection": "all",
                "starts_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
                "ends_at": ends_at,
                "usage_limit": int(args.get("usage_limit", 1)),
            }
        }
        if args.get("min_order_amount", 0) > 0:
            pr_payload["price_rule"]["prerequisite_subtotal_range"] = {"greater_than_or_equal_to": str(args["min_order_amount"])}
        pr = await nango_proxy(ctx.business_id, "shopify", "POST", "/admin/api/2024-01/price_rules.json", json=pr_payload)
        pr_id = pr.get("price_rule", {}).get("id")
        if not pr_id:
            return {"error": "Failed to create price rule"}
        # Create discount code under the rule
        dc = await nango_proxy(
            ctx.business_id, "shopify", "POST",
            f"/admin/api/2024-01/price_rules/{pr_id}/discount_codes.json",
            json={"discount_code": {"code": code}},
        )
        return {
            "success": True, "code": code,
            "type": discount_type, "value": value,
            "expires": ends_at[:10],
            "discount_code_id": dc.get("discount_code", {}).get("id"),
        }
    except RuntimeError as e:
        return {"error": str(e)}


@tool(
    name="shopify_get_abandoned_carts",
    description=(
        "Fetch abandoned checkouts from Shopify — carts with items that were never purchased. "
        "Returns cart value, email, items, and time since abandonment. "
        "Requires Shopify to be connected."
    ),
    parameters={
        "type": "object",
        "properties": {
            "since_hours": {"type": "integer", "default": 1,   "description": "Only carts abandoned at least this many hours ago"},
            "limit":       {"type": "integer", "default": 25,  "description": "Max results (1-250)"},
        },
    },
)
async def shopify_get_abandoned_carts(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    from datetime import timezone
    hours = int(args.get("since_hours", 1))
    limit = min(int(args.get("limit", 25)), 250)
    since = (datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=24 * 7)).isoformat()
    try:
        data = await nango_proxy(
            ctx.business_id, "shopify", "GET",
            "/admin/api/2024-01/checkouts.json",
            params={"limit": limit, "created_at_min": since},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    carts = data.get("checkouts", [])
    cutoff = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=hours)
    out = []
    for c in carts:
        updated = c.get("updated_at", "")
        if updated:
            from datetime import datetime as dt
            try:
                ts = dt.fromisoformat(updated.replace("Z", "+00:00"))
                if ts > cutoff:
                    continue  # Too recent — still might convert
            except Exception:
                pass
        out.append({
            "token":       c.get("token"),
            "email":       c.get("email") or "Guest",
            "total_price": c.get("total_price"),
            "currency":    c.get("currency"),
            "item_count":  len(c.get("line_items", [])),
            "items":       [{"title": i.get("title"), "qty": i.get("quantity"), "price": i.get("price")} for i in c.get("line_items", [])[:5]],
            "abandoned_at": updated[:16],
            "recovery_url": c.get("abandoned_checkout_url"),
        })
    return {"count": len(out), "carts": out, "total_recoverable": sum(float(c.get("total_price", 0)) for c in carts if c.get("total_price"))}


@tool(
    name="shopify_get_growth_metrics",
    description=(
        "Get Shopify growth intelligence metrics: repeat purchase rate, revenue at risk from "
        "at-risk customers, average LTV, new vs returning buyer split, CAC context, "
        "and channel attribution from order tags. Use this to power growth analysis and autopilot decisions. "
        "Requires Shopify to be connected."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "default": 90, "description": "Lookback period in days"},
        },
    },
)
async def shopify_get_growth_metrics(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    from datetime import timezone
    days  = int(args.get("days", 90))
    since = (datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        data = await nango_proxy(
            ctx.business_id, "shopify", "GET",
            "/admin/api/2024-01/orders.json",
            params={"status": "any", "financial_status": "paid", "limit": 250, "created_at_min": since},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    orders = data.get("orders", [])
    if not orders:
        return {"period_days": days, "order_count": 0, "message": "No paid orders in this period"}

    # Customer order counts
    cust_orders: Dict[str, list] = {}
    for o in orders:
        cid = str((o.get("customer") or {}).get("id", "guest"))
        cust_orders.setdefault(cid, []).append(o)

    repeat_customers = sum(1 for orders_list in cust_orders.values() if len(orders_list) > 1)
    total_customers  = len(cust_orders)
    repeat_rate      = round(repeat_customers / total_customers * 100, 1) if total_customers else 0

    # LTV
    ltv_values = [sum(float(o.get("total_price", 0)) for o in ol) for ol in cust_orders.values()]
    avg_ltv    = round(sum(ltv_values) / len(ltv_values), 2) if ltv_values else 0

    # At-risk: customers who haven't ordered in 60+ days within the window
    from datetime import timezone as tz_mod
    sixty_ago = datetime.utcnow().replace(tzinfo=tz_mod.utc) - timedelta(days=60)
    at_risk_count   = 0
    at_risk_revenue = 0.0
    for cid, cust_order_list in cust_orders.items():
        latest_ts = max(
            (o.get("created_at", "") for o in cust_order_list),
            default=""
        )
        try:
            from datetime import datetime as dt
            ts = dt.fromisoformat(latest_ts.replace("Z", "+00:00"))
            if ts < sixty_ago:
                at_risk_count += 1
                at_risk_revenue += sum(float(o.get("total_price", 0)) for o in cust_order_list)
        except Exception:
            pass

    # Channel attribution via tags
    channels = {"meta": 0.0, "google": 0.0, "email": 0.0, "whatsapp": 0.0, "organic": 0.0, "direct": 0.0}
    for o in orders:
        tags  = (o.get("tags") or "").lower()
        price = float(o.get("total_price", 0))
        if "facebook" in tags or "meta" in tags or "instagram" in tags:
            channels["meta"] += price
        elif "google" in tags:
            channels["google"] += price
        elif "email" in tags or "klaviyo" in tags or "mailchimp" in tags:
            channels["email"] += price
        elif "whatsapp" in tags or "wa" in tags:
            channels["whatsapp"] += price
        elif "organic" in tags or "seo" in tags:
            channels["organic"] += price
        else:
            channels["direct"] += price

    total_revenue = sum(float(o.get("total_price", 0)) for o in orders)
    aov           = round(total_revenue / len(orders), 2) if orders else 0
    currency      = orders[0].get("currency", "") if orders else ""

    return {
        "period_days":        days,
        "currency":           currency,
        "total_revenue":      round(total_revenue, 2),
        "order_count":        len(orders),
        "aov":                aov,
        "total_customers":    total_customers,
        "repeat_customers":   repeat_customers,
        "repeat_rate_pct":    repeat_rate,
        "avg_ltv":            avg_ltv,
        "at_risk_customers":  at_risk_count,
        "at_risk_revenue":    round(at_risk_revenue, 2),
        "channel_attribution": {k: round(v, 2) for k, v in channels.items()},
    }


@tool(
    name="shopify_add_product",
    description=(
        "Add a new product to the connected Shopify store. "
        "Use this when the user asks to add, create, or import a product. "
        "The AI can research and suggest product details; this tool creates it in Shopify. "
        "Requires Shopify to be connected. Destructive action."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title":            {"type": "string", "description": "Product title / name"},
            "description":      {"type": "string", "description": "Product description (2-4 sentences)"},
            "product_type":     {"type": "string", "description": "Category / product type"},
            "price":            {"type": "string", "description": "Selling price, e.g. '29.99'"},
            "compare_at_price": {"type": "string", "description": "Original price (shows as crossed-out), e.g. '39.99'"},
            "vendor":           {"type": "string", "description": "Brand or supplier name"},
            "tags":             {"type": "string", "description": "Comma-separated tags"},
            "variants": {
                "type": "array",
                "description": "Optional variants (sizes, colors, etc.). Leave empty for a single-variant product.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title":              {"type": "string"},
                        "price":              {"type": "string"},
                        "compare_at_price":   {"type": "string"},
                        "inventory_quantity": {"type": "integer"},
                    },
                },
            },
        },
        "required": ["title", "price"],
    },
    destructive=True,
)
async def shopify_add_product(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    title   = args["title"]
    price   = str(args["price"])
    raw_variants = args.get("variants") or []
    variants = [
        {
            "title": v.get("title", "Default Title"),
            "price": str(v.get("price", price)),
            **({"compare_at_price": str(v["compare_at_price"])} if v.get("compare_at_price") else {}),
            "inventory_management": "shopify",
            "inventory_quantity": int(v.get("inventory_quantity", 10)),
        }
        for v in raw_variants
    ] if raw_variants else [{
        "title": "Default Title",
        "price": price,
        **({"compare_at_price": str(args["compare_at_price"])} if args.get("compare_at_price") else {}),
        "inventory_management": "shopify",
        "inventory_quantity": 10,
    }]

    payload: Dict[str, Any] = {
        "product": {
            "title": title,
            "body_html": f"<p>{args.get('description', '')}</p>" if args.get("description") else "",
            "vendor": args.get("vendor", ""),
            "product_type": args.get("product_type", ""),
            "status": "active",
            "tags": args.get("tags", ""),
            "variants": variants,
        }
    }
    try:
        result = await nango_proxy(ctx.business_id, "shopify", "POST", "/admin/api/2024-01/products.json", json=payload)
        product = result.get("product", {})
        return {
            "success": True,
            "product_id": product.get("id"),
            "title": product.get("title"),
            "handle": product.get("handle"),
            "status": product.get("status"),
            "variant_count": len(product.get("variants", [])),
        }
    except RuntimeError as e:
        return {"error": str(e)}


@tool(
    name="shopify_adjust_inventory",
    description=(
        "Adjust the inventory quantity of a Shopify product variant at a location. "
        "Use a positive delta to increase stock, negative to decrease. "
        "Requires Shopify to be connected. Destructive action."
    ),
    parameters={
        "type": "object",
        "properties": {
            "inventory_item_id": {"type": "string",  "description": "Shopify inventory_item_id from list_shopify_products"},
            "location_id":       {"type": "string",  "description": "Shopify location ID. Omit to use the primary location."},
            "delta":             {"type": "integer",  "description": "Quantity change. Positive = add stock, negative = remove."},
        },
        "required": ["inventory_item_id", "delta"],
    },
    destructive=True,
)
async def shopify_adjust_inventory(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    inv_item_id = str(args["inventory_item_id"])
    delta = int(args["delta"])
    location_id = args.get("location_id")
    try:
        if not location_id:
            locs = await nango_proxy(ctx.business_id, "shopify", "GET", "/admin/api/2024-01/locations.json")
            loc_list = locs.get("locations", [])
            if not loc_list:
                return {"error": "No locations found in Shopify store"}
            location_id = str(loc_list[0]["id"])
        result = await nango_proxy(
            ctx.business_id, "shopify", "POST",
            "/admin/api/2024-01/inventory_levels/adjust.json",
            json={
                "location_id":       location_id,
                "inventory_item_id": inv_item_id,
                "available_adjustment": delta,
            },
        )
        level = result.get("inventory_level", {})
        return {
            "success": True,
            "inventory_item_id": inv_item_id,
            "location_id":       location_id,
            "new_quantity":      level.get("available"),
        }
    except RuntimeError as e:
        return {"error": str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# STRIPE TOOLS (via Nango proxy)
# ═════════════════════════════════════════════════════════════════════════════

@tool(
    name="list_stripe_payments",
    description=(
        "Fetch recent payments/charges from the connected Stripe account. "
        "Requires Stripe to be connected in Integrations."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit":  {"type": "integer", "default": 20, "description": "Number of payments (1-100)"},
            "status": {"type": "string",  "default": "succeeded", "description": "succeeded | pending | failed | all"},
        },
    },
)
async def list_stripe_payments(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    limit  = min(int(args.get("limit", 20)), 100)
    status = args.get("status", "succeeded")
    params: Dict[str, Any] = {"limit": limit}
    try:
        data = await nango_proxy(
            ctx.business_id, "stripe", "GET",
            "/v1/payment_intents",
            params=params,
        )
    except RuntimeError as e:
        return {"error": str(e)}
    items = data.get("data", [])
    if status != "all":
        items = [p for p in items if p.get("status") == status]
    out = []
    for p in items:
        out.append({
            "id":          p.get("id"),
            "amount":      round(p.get("amount", 0) / 100, 2),
            "currency":    (p.get("currency") or "").upper(),
            "status":      p.get("status"),
            "description": p.get("description"),
            "customer":    p.get("customer"),
            "created":     p.get("created"),
        })
    return {"count": len(out), "payments": out, "total": round(sum(p["amount"] for p in out), 2)}


@tool(
    name="list_stripe_invoices",
    description=(
        "Fetch invoices from the connected Stripe account: paid, open, and overdue. "
        "Requires Stripe to be connected in Integrations."
    ),
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "default": "open", "description": "open | paid | uncollectible | void | all"},
            "limit":  {"type": "integer", "default": 20},
        },
    },
)
async def list_stripe_invoices(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    status = args.get("status", "open")
    limit  = min(int(args.get("limit", 20)), 100)
    params: Dict[str, Any] = {"limit": limit}
    if status != "all":
        params["status"] = status
    try:
        data = await nango_proxy(
            ctx.business_id, "stripe", "GET",
            "/v1/invoices",
            params=params,
        )
    except RuntimeError as e:
        return {"error": str(e)}
    items = data.get("data", [])
    out = []
    for inv in items:
        out.append({
            "id":            inv.get("id"),
            "number":        inv.get("number"),
            "customer_email":inv.get("customer_email"),
            "amount_due":    round((inv.get("amount_due") or 0) / 100, 2),
            "amount_paid":   round((inv.get("amount_paid") or 0) / 100, 2),
            "currency":      (inv.get("currency") or "").upper(),
            "status":        inv.get("status"),
            "due_date":      inv.get("due_date"),
            "description":   inv.get("description"),
        })
    return {"count": len(out), "invoices": out}


# ═════════════════════════════════════════════════════════════════════════════
# KLAVIYO TOOLS (via Nango proxy)
# ═════════════════════════════════════════════════════════════════════════════

@tool(
    name="list_klaviyo_flows",
    description=(
        "Fetch automation flows from the connected Klaviyo account: welcome series, "
        "abandoned cart, post-purchase, win-back, etc. Requires Klaviyo to be connected."
    ),
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "default": "all", "description": "live | draft | archived | all"},
        },
    },
)
async def list_klaviyo_flows(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    status = args.get("status", "all")
    params: Dict[str, Any] = {"page[size]": 50}
    if status != "all":
        params["filter"] = f"equals(status,'{status}')"
    try:
        data = await nango_proxy(
            ctx.business_id, "klaviyo", "GET",
            "/api/flows/",
            params=params,
        )
    except RuntimeError as e:
        return {"error": str(e)}
    flows = data.get("data", [])
    out = []
    for f in flows:
        attrs = f.get("attributes", {})
        out.append({
            "id":      f.get("id"),
            "name":    attrs.get("name"),
            "status":  attrs.get("status"),
            "trigger": attrs.get("trigger_type"),
            "created": (attrs.get("created") or "")[:10],
            "updated": (attrs.get("updated") or "")[:10],
        })
    return {"count": len(out), "flows": out}


@tool(
    name="get_klaviyo_metrics",
    description=(
        "Get Klaviyo performance metrics: open rates, click rates, revenue attributed. "
        "Requires Klaviyo to be connected in Integrations."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 20, "description": "Number of metrics to return"},
        },
    },
)
async def get_klaviyo_metrics(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    limit = min(int(args.get("limit", 20)), 100)
    try:
        data = await nango_proxy(
            ctx.business_id, "klaviyo", "GET",
            "/api/metrics/",
            params={"page[size]": limit},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    metrics = data.get("data", [])
    out = [
        {
            "id":          m.get("id"),
            "name":        (m.get("attributes") or {}).get("name"),
            "integration": ((m.get("attributes") or {}).get("integration") or {}).get("name"),
            "created":     ((m.get("attributes") or {}).get("created") or "")[:10],
        }
        for m in metrics
    ]
    return {"count": len(out), "metrics": out}


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


# ═════════════════════════════════════════════════════════════════════════════
# ANALYTICS TOOLS
# ═════════════════════════════════════════════════════════════════════════════
@tool(
    name="get_revenue_trends",
    description=(
        "Return revenue totals grouped by period (day/week/month) for the last N periods. "
        "Use this to show revenue trends, growth rates, and patterns over time."
    ),
    parameters={
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["day", "week", "month"], "default": "day"},
            "periods_back": {"type": "integer", "default": 14, "minimum": 1, "maximum": 90,
                             "description": "How many periods to look back (e.g. 14 days, 8 weeks, 6 months)."},
        },
    },
)
async def get_revenue_trends(ctx: ToolContext, args: Dict[str, Any]):
    period = args.get("period") or "day"
    periods_back = min(max(int(args.get("periods_back") or 14), 1), 90)
    now = datetime.utcnow()

    if period == "day":
        delta = timedelta(days=1)
        fmt = "%Y-%m-%d"
    elif period == "week":
        delta = timedelta(weeks=1)
        fmt = "week of %b %d"
    else:
        delta = timedelta(days=30)
        fmt = "%b %Y"

    start = now - delta * periods_back
    sales = await ctx.db.sales.find(
        {"user_id": ctx.business_id, "sale_date": {"$gte": start}}
    ).to_list(5000)

    # Bucket by period
    buckets: Dict[str, Dict[str, Any]] = {}
    for i in range(periods_back):
        bucket_start = now - delta * (periods_back - i)
        key = bucket_start.strftime(fmt)
        buckets[key] = {"period": key, "revenue": 0.0, "orders": 0}

    for s in sales:
        sale_date = s.get("sale_date") or s.get("created_at")
        if not isinstance(sale_date, datetime):
            continue
        key = sale_date.strftime(fmt)
        if key not in buckets:
            buckets[key] = {"period": key, "revenue": 0.0, "orders": 0}
        buckets[key]["revenue"] += float(s.get("amount") or 0)
        buckets[key]["orders"] += 1

    trend_list = list(buckets.values())
    total_revenue = sum(b["revenue"] for b in trend_list)
    total_orders = sum(b["orders"] for b in trend_list)

    # Compare first half vs second half for trend direction
    mid = len(trend_list) // 2
    first_half = sum(b["revenue"] for b in trend_list[:mid]) if mid else 0
    second_half = sum(b["revenue"] for b in trend_list[mid:]) if mid else total_revenue
    trend_pct = ((second_half - first_half) / first_half * 100) if first_half > 0 else 0

    return {
        "period_type": period,
        "periods": periods_back,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "trend_direction": "up" if trend_pct > 2 else "down" if trend_pct < -2 else "flat",
        "trend_percent": round(trend_pct, 1),
        "data": trend_list,
    }


@tool(
    name="get_top_customers",
    description=(
        "Return the top customers ranked by total revenue or order count. "
        "Use this to identify VIPs, loyal buyers, or high-value targets for follow-up."
    ),
    parameters={
        "type": "object",
        "properties": {
            "by": {"type": "string", "enum": ["revenue", "orders"], "default": "revenue"},
            "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            "days_back": {"type": "integer", "default": 90, "minimum": 7, "maximum": 365,
                          "description": "Only count sales within this many days."},
        },
    },
)
async def get_top_customers(ctx: ToolContext, args: Dict[str, Any]):
    limit = min(int(args.get("limit") or 10), 50)
    days_back = min(max(int(args.get("days_back") or 90), 7), 365)
    by = args.get("by") or "revenue"
    since = datetime.utcnow() - timedelta(days=days_back)

    sales = await ctx.db.sales.find(
        {"user_id": ctx.business_id, "sale_date": {"$gte": since}}
    ).to_list(10000)

    agg: Dict[str, Dict[str, Any]] = {}
    for s in sales:
        cid = s.get("customer_id") or ""
        if not cid:
            continue
        if cid not in agg:
            agg[cid] = {"customer_id": cid, "name": s.get("customer_name") or "", "revenue": 0.0, "orders": 0}
        agg[cid]["revenue"] += float(s.get("amount") or 0)
        agg[cid]["orders"] += 1

    # Enrich missing names
    missing_ids = [cid for cid, v in agg.items() if not v["name"]]
    if missing_ids:
        custs = await ctx.db.customers.find(
            {"_id": {"$in": missing_ids}, "user_id": ctx.business_id}
        ).to_list(len(missing_ids))
        name_map = {c["_id"]: c.get("name", "") for c in custs}
        for cid in missing_ids:
            if cid in name_map:
                agg[cid]["name"] = name_map[cid]

    # Also get phone numbers
    all_ids = list(agg.keys())
    if all_ids:
        custs_all = await ctx.db.customers.find(
            {"_id": {"$in": all_ids}, "user_id": ctx.business_id},
            {"_id": 1, "phone_number": 1, "tags": 1, "last_interaction": 1}
        ).to_list(len(all_ids))
        for c in custs_all:
            if c["_id"] in agg:
                agg[c["_id"]]["phone_number"] = c.get("phone_number", "")
                agg[c["_id"]]["tags"] = c.get("tags", [])
                li = c.get("last_interaction")
                agg[c["_id"]]["last_interaction"] = li.isoformat() if isinstance(li, datetime) else None

    sorted_list = sorted(agg.values(), key=lambda x: x[by], reverse=True)[:limit]
    return {
        "ranked_by": by,
        "days_back": days_back,
        "count": len(sorted_list),
        "customers": sorted_list,
    }


@tool(
    name="get_customer_health",
    description=(
        "Score and segment customers by engagement health: active (recent purchase/contact), "
        "at_risk (no contact for 30+ days), dormant (60+ days), and never_bought. "
        "Use this for retention strategy and follow-up prioritization."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 30, "minimum": 5, "maximum": 100},
        },
    },
)
async def get_customer_health(ctx: ToolContext, args: Dict[str, Any]):
    limit = min(int(args.get("limit") or 30), 100)
    now = datetime.utcnow()
    customers = await ctx.db.customers.find(
        {"user_id": ctx.business_id, "is_customer": True}
    ).sort("last_interaction", -1).to_list(500)

    active = []
    at_risk = []
    dormant = []
    never_bought = []

    for c in customers:
        li = c.get("last_interaction")
        if not isinstance(li, datetime):
            li = c.get("created_at")
        days_since = (now - li).days if isinstance(li, datetime) else 9999

        row = {
            "name": c.get("name", ""),
            "phone_number": c.get("phone_number", ""),
            "days_since_contact": days_since,
            "tags": c.get("tags", []),
            "customer_id": str(c["_id"]),
        }
        if days_since <= 14:
            active.append(row)
        elif days_since <= 30:
            at_risk.append(row)
        elif days_since <= 9998:
            dormant.append(row)
        else:
            never_bought.append(row)

    return {
        "summary": {
            "active": len(active),
            "at_risk": len(at_risk),
            "dormant": len(dormant),
            "total": len(customers),
        },
        "active": active[:limit],
        "at_risk": at_risk[:limit],
        "dormant": dormant[:limit],
    }


@tool(
    name="get_sales_pipeline",
    description=(
        "Return current orders grouped by fulfillment status with revenue totals. "
        "Shows where orders are stuck and the total value in each stage. "
        "Use this for operations overview and bottleneck detection."
    ),
    parameters={"type": "object", "properties": {}},
)
async def get_sales_pipeline(ctx: ToolContext, args: Dict[str, Any]):
    orders = await ctx.db.orders.find({"user_id": ctx.business_id}).to_list(2000)

    stages: Dict[str, Dict[str, Any]] = {}
    for o in orders:
        status = o.get("fulfillment_status") or "Unknown"
        if status not in stages:
            stages[status] = {"status": status, "count": 0, "revenue": 0.0, "orders": []}
        stages[status]["count"] += 1
        total = float(o.get("total") or o.get("total_amount") or 0)
        stages[status]["revenue"] += total
        if len(stages[status]["orders"]) < 5:
            stages[status]["orders"].append({
                "order_id": str(o.get("_id", ""))[:8],
                "customer_id": str(o.get("customer_id", "")),
                "total": total,
                "created_at": o.get("created_at").isoformat() if isinstance(o.get("created_at"), datetime) else None,
            })

    pipeline = sorted(stages.values(), key=lambda x: x["count"], reverse=True)
    total_active_revenue = sum(
        s["revenue"] for s in pipeline
        if s["status"] not in ("Done", "Delivered", "Cancelled")
    )
    return {
        "total_orders": len(orders),
        "total_active_revenue": total_active_revenue,
        "pipeline": pipeline,
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


# ═════════════════════════════════════════════════════════════════════════════
# AUTOMATION / WORKFLOW TOOLS
# ═════════════════════════════════════════════════════════════════════════════

@tool(
    name="list_automations",
    description=(
        "List all automations (workflows) the user has created. "
        "Shows name, trigger, number of steps, enabled state, and run count. "
        "Call this before creating or modifying automations so you know what already exists."
    ),
    parameters={"type": "object", "properties": {}},
)
async def list_automations(ctx: ToolContext, args: Dict[str, Any]):
    docs = await ctx.db.workflows.find(
        {"user_id": ctx.business_id},
        sort=[("created_at", -1)],
    ).to_list(100)

    result = []
    for d in docs:
        trigger = d.get("trigger", {})
        steps = d.get("steps", [])
        result.append({
            "id": str(d["_id"]),
            "name": d.get("name", ""),
            "description": d.get("description", ""),
            "trigger_type": trigger.get("type", ""),
            "trigger_condition": trigger.get("condition", "always"),
            "step_count": len(steps),
            "steps_summary": [s.get("action", "") for s in steps],
            "enabled": d.get("enabled", True),
            "run_count": d.get("run_count", 0),
            "last_run_at": d.get("last_run_at").isoformat() if isinstance(d.get("last_run_at"), datetime) else None,
            "created_at": d.get("created_at").isoformat() if isinstance(d.get("created_at"), datetime) else None,
        })
    return {"count": len(result), "automations": result}


@tool(
    name="create_automation",
    description=(
        "Create a new automation from a plain English description. "
        "The AI builder will convert the description into a structured workflow and save it. "
        "Use this when the user wants to automate something — follow-ups, tagging, notifications, sequences, routing, etc. "
        "Pass the full description of what the automation should do. Be specific and include timing if relevant. "
        "Examples: "
        "'When a customer asks about price, wait 2 hours, if they haven't replied, send a follow-up message', "
        "'When a new customer contacts us, tag them as new_lead and notify me', "
        "'When an order intent is detected, create a follow-up reminder for tomorrow'."
    ),
    parameters={
        "type": "object",
        "required": ["description"],
        "properties": {
            "description": {
                "type": "string",
                "description": (
                    "Natural language description of the automation. "
                    "Include: the trigger event, any condition, the steps, and delays if any."
                ),
            },
        },
    },
    destructive=True,
)
async def create_automation(ctx: ToolContext, args: Dict[str, Any]):
    description = (args.get("description") or "").strip()
    if not description or len(description) < 10:
        return {"error": "Description is too short. Describe what the automation should do."}

    try:
        from workflows.ai_builder import build_workflow_from_description
        wf_dict = await build_workflow_from_description(
            description=description,
            user=ctx.user,
        )
    except ValueError as exc:
        return {"error": f"Could not generate automation: {exc}"}
    except Exception as exc:
        logger.exception("[create_automation] AI builder failed")
        return {"error": f"Automation builder error: {exc}"}

    # Save to DB
    wf_id = str(uuid.uuid4())
    now = datetime.utcnow()
    doc = {
        "_id": wf_id,
        "user_id": ctx.business_id,
        "name": wf_dict.get("name", "New Automation"),
        "description": wf_dict.get("description", ""),
        "trigger": wf_dict.get("trigger", {}),
        "steps": wf_dict.get("steps", []),
        "enabled": True,
        "run_count": 0,
        "last_run_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await ctx.db.workflows.insert_one(doc)

    steps_summary = [s.get("action", "") for s in doc["steps"]]
    return {
        "status": "created",
        "automation_id": wf_id,
        "name": doc["name"],
        "description": doc["description"],
        "trigger": doc["trigger"],
        "steps": steps_summary,
        "step_count": len(steps_summary),
        "enabled": True,
    }


@tool(
    name="toggle_automation",
    description="Enable or disable an automation by ID. Use list_automations first to find the ID.",
    parameters={
        "type": "object",
        "required": ["automation_id"],
        "properties": {
            "automation_id": {"type": "string", "description": "The automation's ID from list_automations"},
            "enabled": {"type": "boolean", "description": "True to enable, False to disable. If omitted, toggles the current state."},
        },
    },
    destructive=True,
)
async def toggle_automation(ctx: ToolContext, args: Dict[str, Any]):
    wf_id = (args.get("automation_id") or "").strip()
    if not wf_id:
        return {"error": "automation_id is required"}
    doc = await ctx.db.workflows.find_one({"_id": wf_id, "user_id": ctx.business_id})
    if not doc:
        return {"error": f"Automation '{wf_id}' not found"}

    if "enabled" in args and args["enabled"] is not None:
        new_state = bool(args["enabled"])
    else:
        new_state = not doc.get("enabled", True)

    await ctx.db.workflows.update_one(
        {"_id": wf_id},
        {"$set": {"enabled": new_state, "updated_at": datetime.utcnow()}},
    )
    action = "enabled" if new_state else "disabled"
    return {"status": action, "automation_id": wf_id, "name": doc.get("name", ""), "enabled": new_state}


@tool(
    name="delete_automation",
    description="Permanently delete an automation by ID. Use list_automations first to find the ID. This cannot be undone.",
    parameters={
        "type": "object",
        "required": ["automation_id"],
        "properties": {
            "automation_id": {"type": "string"},
        },
    },
    destructive=True,
)
async def delete_automation(ctx: ToolContext, args: Dict[str, Any]):
    wf_id = (args.get("automation_id") or "").strip()
    if not wf_id:
        return {"error": "automation_id is required"}
    doc = await ctx.db.workflows.find_one({"_id": wf_id, "user_id": ctx.business_id})
    if not doc:
        return {"error": f"Automation '{wf_id}' not found"}
    await ctx.db.workflows.delete_one({"_id": wf_id})
    await ctx.db.workflow_pending_steps.delete_many({"workflow_id": wf_id})
    return {"status": "deleted", "automation_id": wf_id, "name": doc.get("name", "")}


# ═════════════════════════════════════════════════════════════════════════════
# DOCUMENT GENERATION
# ═════════════════════════════════════════════════════════════════════════════
# In-memory store: key → filepath (survives the request, cleaned up lazily)
_doc_store: Dict[str, str] = {}


@tool(
    name="generate_document",
    description=(
        "Convert markdown content into a downloadable PDF or DOCX file and return a download link. "
        "Call this after writing a full document (proposal, report, invoice, contract) so the user can download it immediately. "
        "Pass the complete markdown as `content`. Set `format` to 'pdf' or 'docx'. "
        "Set `filename` to a short descriptive name without extension (e.g. 'business-proposal')."
    ),
    parameters={
        "type": "object",
        "properties": {
            "content":  {"type": "string", "description": "The full Markdown content to export."},
            "format":   {"type": "string", "enum": ["pdf", "docx"], "default": "pdf"},
            "filename": {"type": "string", "description": "Base filename without extension, e.g. 'q1-report'."},
        },
        "required": ["content"],
    },
)
async def generate_document(ctx: ToolContext, args: Dict[str, Any]):
    import re as _re
    import uuid as _uuid
    content = (args.get("content") or "").strip()
    if not content:
        return {"error": "content is required"}
    fmt = (args.get("format") or "pdf").lower()
    if fmt not in ("pdf", "docx"):
        fmt = "pdf"

    raw_name = (args.get("filename") or "document").strip()
    safe = _re.sub(r"[^\w\-]", "_", raw_name)[:60] or "document"
    filename = f"{safe}.{fmt}"

    try:
        from .document_generator import generate_pdf, generate_docx
        if fmt == "pdf":
            filepath = generate_pdf(content, filename)
        else:
            filepath = generate_docx(content, filename)
    except Exception as e:
        logger.exception("[generate_document] generation failed")
        return {"error": f"Document generation failed: {e}"}

    key = str(_uuid.uuid4())
    _doc_store[key] = filepath

    return {
        "status": "ready",
        "download_url": f"/proxy/assistant/download/{key}",
        "filename": filename,
        "format": fmt,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Ad trend intelligence — Meta Ads Library + TikTok Creative Center

@tool(
    name="get_meta_ad_trends",
    description=(
        "Search Meta Ads Library (Facebook & Instagram) for active ads in a given category or niche. "
        "Use this BEFORE proposing a creative concept to see what's actually working in the market — "
        "which headlines, copy hooks, and formats proven competitors are running and for how long. "
        "Ads running 21+ days are proven winners (brands don't waste budget on what doesn't convert)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "search_terms": {
                "type": "string",
                "description": "What to search for — product type, niche, or brand keyword. E.g. 'skincare serum', 'gym wear', 'online course'.",
            },
            "countries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Country codes to search in. E.g. ['KE', 'NG', 'ZA'] for East/West/South Africa, ['US', 'GB'] for Western markets.",
                "default": ["KE"],
            },
            "active_only": {
                "type": "boolean",
                "description": "True = only currently running ads (default). False = include recently stopped ads.",
                "default": True,
            },
            "days_back": {
                "type": "integer",
                "description": "How far back to look in days. Default 90.",
                "default": 90,
            },
        },
        "required": ["search_terms"],
    },
)
async def get_meta_ad_trends(ctx: ToolContext, args: Dict[str, Any]):
    from trend_service import search_meta_ads
    result = await search_meta_ads(
        search_terms=args.get("search_terms", ""),
        countries=args.get("countries", ["KE"]),
        active_only=args.get("active_only", True),
        days_back=args.get("days_back", 90),
        db=ctx.db,
    )
    return result


@tool(
    name="get_tiktok_ad_trends",
    description=(
        "Fetch top-performing TikTok ads for a product category from TikTok Creative Center. "
        "Shows what's getting the most engagement and CTR on TikTok right now — "
        "use this to understand trending video ad styles, hooks, and brand messaging for TikTok content. "
        "Requires TIKTOK_ACCESS_TOKEN configured in .env (apply at developers.tiktok.com)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Product/industry category. E.g. 'skincare', 'fashion', 'food', 'fitness', 'tech', 'ecommerce'.",
            },
            "country_code": {
                "type": "string",
                "description": "2-letter country code. E.g. 'KE', 'NG', 'US', 'GB', 'ZA'.",
                "default": "US",
            },
            "period": {
                "type": "integer",
                "description": "Time window in days: 7, 30, or 180.",
                "enum": [7, 30, 180],
                "default": 30,
            },
        },
        "required": ["category"],
    },
)
async def get_tiktok_ad_trends(ctx: ToolContext, args: Dict[str, Any]):
    from trend_service import search_tiktok_top_ads
    result = await search_tiktok_top_ads(
        category=args.get("category", ""),
        country_code=args.get("country_code", "US"),
        period=args.get("period", 30),
        db=ctx.db,
    )
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Visual assets — Nano Banana / Gemini AI images; Orshot for template graphics; .pptx via python-pptx

@tool(
    name="generate_creative_image",
    description=(
        "Generate a creative, conceptual, or lifestyle image using Google's Nano Banana AI model (via OpenRouter). "
        "Use this for standalone AI image generation — product lifestyle shots, mood scenes, conceptual backgrounds, "
        "people with products, brand imagery. "
        "For branded layouts, pass the returned image_url as the image field value in `render_orshot_template` — "
        "the AI picks a matching Orshot template and places this image into it."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Detailed visual description of the image to generate. Be specific: lighting, mood, setting, "
                    "subject, colours, style. E.g. 'A confident woman in her 30s holding a brown glass skincare serum bottle "
                    "in a minimalist bathroom, golden hour light, soft shadows, editorial photography style, clean white background'."
                )
            },
            "format": {
                "type": "string",
                "description": "Canvas format — controls aspect ratio of the generated image.",
                "enum": ["square", "story", "landscape", "portrait"],
                "default": "square"
            },
            "quality": {
                "type": "string",
                "description": "fast = Nano Banana 2 (quick, great quality). pro = Nano Banana Pro (best quality, slower). Use fast by default.",
                "enum": ["fast", "pro"],
                "default": "fast"
            },
        },
        "required": ["prompt"],
    },
)
async def generate_creative_image(ctx: ToolContext, args: Dict[str, Any]):
    from nano_banana_service import generate_creative_image as _generate
    prompt  = args.get("prompt", "")
    fmt     = args.get("format", "square")
    quality = args.get("quality", "fast")

    result = await _generate(prompt=prompt, format=fmt, quality=quality)

    if result.get("error"):
        return {"error": result["error"]}

    image_url = result["image_url"]
    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![Generated image]({image_url})",
        "note": "Use this URL as an image field value in `render_orshot_template.modifications` when your Orshot template expects a photo URL.",
    }


@tool(
    name="list_orshot_templates",
    description=(
        "List Orshot Studio templates in the workspace. Each template includes id, name, canvas size, "
        "and thumbnail_url — a preview image of what the template looks like. "
        "When presenting options to the user, show the thumbnail images using markdown "
        "![Template Name](thumbnail_url) so they can see the actual design and pick visually "
        "instead of guessing from a name. Show 2–4 of the best fits for the brief, not the full list."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page": {"type": "integer", "default": 1, "description": "Pagination page (1-based)."},
            "limit": {
                "type": "integer",
                "default": 20,
                "description": "Page size (max 20).",
            },
        },
        "required": [],
    },
)
async def list_orshot_templates(ctx: ToolContext, args: Dict[str, Any]):
    from orshot_service import list_studio_templates

    page = int(args.get("page") or 1)
    limit = int(args.get("limit") or 20)
    return await list_studio_templates(page=page, limit=limit)


@tool(
    name="get_orshot_template_fields",
    description=(
        "Fetch the **modification keys** for one Orshot template (for mapping user feedback to fields). "
        "Call **once** after you pick `template_id` — use internally to know which keys to change on edits; "
        "do **not** dump the full list to the user unless they ask. Same schema as GET /api/orshot/templates/{id}."
    ),
    parameters={
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Orshot template id. Omit to use ORSHOT_DEFAULT_TEMPLATE_ID env.",
            },
        },
        "required": [],
    },
)
async def get_orshot_template_fields(ctx: ToolContext, args: Dict[str, Any]):
    import os as _os

    from orshot_service import get_studio_template

    tid = (args.get("template_id") or "").strip() or (_os.environ.get("ORSHOT_DEFAULT_TEMPLATE_ID") or "").strip()
    if not tid:
        return {"error": "Pass template_id or set ORSHOT_DEFAULT_TEMPLATE_ID on the server."}

    data = await get_studio_template(tid)
    if data.get("error"):
        return data

    mods = data.get("modifications") or []
    fields: list = []
    for m in mods if isinstance(mods, list) else []:
        if not isinstance(m, dict):
            continue
        ex = m.get("example")
        if isinstance(ex, str) and len(ex) > 800:
            ex = ex[:800] + "…"
        fields.append(
            {
                "key": m.get("key") or m.get("id"),
                "type": m.get("type"),
                "help_text": m.get("helpText") or m.get("help_text") or m.get("description"),
                "example": ex,
                "page_number": m.get("page_number"),
                "page_id": m.get("page_id"),
            }
        )

    pages_raw = data.get("pages_data") or []
    page_count = len(pages_raw) if isinstance(pages_raw, list) else 0

    return {
        "success": True,
        "template_id": data.get("id"),
        "name": data.get("name"),
        "canvas_width": data.get("canvas_width"),
        "canvas_height": data.get("canvas_height"),
        "thumbnail_url": data.get("thumbnail_url"),
        "page_count": page_count,
        "fields": fields,
        "note": "Use `key` in `render_orshot_template.modifications`. Full `pages_data` is omitted here to keep chat storage small — use `page_count` and `fields` only.",
    }


@tool(
    name="render_orshot_template",
    description=(
        "Render a graphic from an **Orshot Studio** template (hosted layouts — import from Canva/Figma supported in Orshot). "
        "Requires server env **ORSHOT_API_KEY**. Optional **ORSHOT_DEFAULT_TEMPLATE_ID** supplies a default when `template_id` is omitted. "
        "**modifications** keys must match Orshot Studio dynamic parameters (often `pageN@field_name` on carousels). "
        "Use `get_orshot_template_fields` once to learn keys, then keep them in mind for refinements. "
        "Optional **`presentation_label`** (e.g. 'Option A', 'Final') helps you show two variants or a final pass. "
        "Default response_type is **base64**; the server re-uploads to your S3 so image links always work."
    ),
    parameters={
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Orshot template ID from Workspaces / Template Playground. Omit to use ORSHOT_DEFAULT_TEMPLATE_ID env.",
            },
            "modifications": {
                "type": "object",
                "description": "Dynamic field values for the template (Studio parameter names → strings or image URLs).",
                "additionalProperties": True,
            },
            "response_type": {
                "type": "string",
                "enum": ["url", "base64", "binary"],
                "default": "base64",
                "description": "How Orshot returns the asset; default base64 avoids broken third-party S3 presigns — server saves to your bucket.",
            },
            "response_format": {
                "type": "string",
                "enum": ["png", "jpg", "jpeg", "webp", "pdf"],
                "default": "png",
            },
            "platform": {
                "type": "string",
                "enum": ["instagram", "facebook", "tiktok", "youtube", "linkedin", "x", "general"],
                "default": "general",
            },
            "content_type": {
                "type": "string",
                "enum": ["ad", "post", "story", "carousel", "general"],
                "default": "general",
            },
            "format": {
                "type": "string",
                "enum": ["square", "story", "landscape", "portrait", "general"],
                "default": "general",
            },
            "name": {
                "type": "string",
                "description": "Label for Design library + image caption (e.g. 'Spring drop — Option A').",
            },
            "presentation_label": {
                "type": "string",
                "description": "Short label echoed in the tool result for chat, e.g. 'Option A', 'Option B', 'Final'.",
            },
        },
        "required": ["modifications"],
    },
)
async def _presign_s3_url(url: str) -> str:
    """Return a publicly accessible URL for a private S3 object.

    Strategy (in order):
    1. If BACKEND_PUBLIC_URL is set, return a proxy URL through our own server
       (/api/images/s3/<key>) — most reliable, avoids S3 direct-access issues.
    2. Otherwise generate an S3 presigned URL (GET, 1-hour TTL).
    3. On any error, return the original URL unchanged (safe degradation).
    """
    if not url or "amazonaws.com" not in url:
        return url
    # Already presigned — skip
    if "X-Amz-Signature" in url or "x-amz-signature" in url:
        return url
    try:
        import os as _os
        from image_handler import S3Handler

        bucket, key = S3Handler.parse_s3_source_to_bucket_key(url)
        if not bucket:
            bucket = (_os.environ.get("AWS_BUCKET_NAME") or "").strip()

        # Prefer backend proxy — Orshot's servers can call our own endpoint
        backend_url = (
            _os.environ.get("BACKEND_PUBLIC_URL")
            or _os.environ.get("PUBLIC_BASE_URL")
            or ""
        ).rstrip("/")
        if backend_url and key:
            proxy = f"{backend_url}/api/images/s3/{key}"
            logger.debug("[render_orshot] Using proxy URL for %s → %s", key[:60], proxy[:80])
            return proxy

        # Fallback: presign directly against S3
        import asyncio as _asyncio
        presigned = await _asyncio.get_event_loop().run_in_executor(
            None,
            lambda: S3Handler.generate_presigned_get_url(bucket, key, expires_in=3600),
        )
        return presigned
    except Exception as _e:
        logger.warning("[render_orshot] Could not build accessible URL for %s: %s", url[:80], _e)
        return url


async def _presign_modifications(mods: dict) -> dict:
    """Replace any private S3 image URLs in modifications with fresh presigned URLs."""
    import asyncio as _asyncio
    out = {}
    for k, v in mods.items():
        if isinstance(v, str) and v.startswith("http") and "amazonaws.com" in v:
            out[k] = await _presign_s3_url(v)
        else:
            out[k] = v
    return out


async def render_orshot_template(ctx: ToolContext, args: Dict[str, Any]):
    import os as _os

    from orshot_service import render_studio_template

    tid = (args.get("template_id") or "").strip() or (_os.environ.get("ORSHOT_DEFAULT_TEMPLATE_ID") or "").strip()
    if not tid:
        return {
            "error": "No template_id: pass template_id in the tool call or set ORSHOT_DEFAULT_TEMPLATE_ID on the server.",
        }
    template_id_used = str(tid)

    mods = args.get("modifications")
    if not isinstance(mods, dict):
        mods = {}

    # Auto-presign any private S3 image URLs so Orshot's server can fetch them
    mods = await _presign_modifications(mods)

    response_type = args.get("response_type") or "base64"
    response_format = args.get("response_format") or "png"
    if response_format == "jpeg":
        response_format = "jpg"

    platform = args.get("platform", "general")
    content_type = args.get("content_type", "general")
    fmt = args.get("format", "general")
    pres = (args.get("presentation_label") or "").strip()
    name = (args.get("name") or pres or "Orshot graphic")[:200]

    result = await render_studio_template(
        tid,
        mods,
        response_type=response_type,
        response_format=response_format,
    )
    if result.get("error"):
        return result

    image_url = result.get("image_url")
    if image_url:
        try:
            from saved_designs import insert_saved_design

            await insert_saved_design(
                ctx.db,
                ctx.business_id,
                name=name,
                asset_kind="image",
                file_url=image_url,
                thumbnail_url=image_url,
                source_tool="render_orshot_template",
                conversation_id=ctx.user.get("_active_conversation_id"),
                platform=platform,
                content_type=content_type,
                format=fmt,
            )
        except Exception:
            logger.exception("[render_orshot_template] saved_designs insert skipped")

    return {
        "success": True,
        "template_id_used": template_id_used,
        "image_url": image_url,
        "image_urls": result.get("image_urls"),
        "presentation_label": pres or None,
        "markdown": f"![{name}]({image_url})" if image_url else "",
        "note": "Carousel templates may return multiple URLs in image_urls.",
    }


@tool(
    name="generate_design_background",
    description=(
        "Enhances a product photo into a professional advertising image using Gemini AI. "
        "Two modes — always prefer (A) when you have the real product photo: "
        "(A) product_image_url provided → Gemini places the product into a styled scene with professional "
        "lighting and environment. THE PRODUCT IS NEVER ALTERED — not the shape, color, label, or texture. "
        "Only the background and scene around it are created. "
        "(B) no product_image_url → Gemini generates a pure lifestyle/concept scene from scratch. "
        "Pass format to match the Orshot template you chose (square / story / landscape / portrait). "
        "The returned background_url is the enhanced product photo — place it into the Orshot template's "
        "image field via render_orshot_template to produce the final branded graphic."
    ),
    parameters={
        "type": "object",
        "properties": {
            "concept": {
                "type": "string",
                "description": (
                    "The advertising goal and product context — what this product is, who it's for, "
                    "and what feeling the ad should create. Gemini uses this to decide the best staging. "
                    "Example: 'Premium running shoe targeting serious athletes — should feel fast, powerful, and aspirational.' "
                    "Do NOT describe a specific scene — let Gemini choose the staging based on the product."
                ),
            },
            "product_image_url": {
                "type": "string",
                "description": (
                    "URL of the real product photo (from list_products or get_product_images). "
                    "When provided, Gemini edits this photo — placing the product in the scene "
                    "described in `concept` while keeping the product itself identical. "
                    "Always provide this when the business has product images."
                ),
            },
            "style": {
                "type": "string",
                "description": (
                    "bold=cinematic high-contrast (Nike/Supreme), "
                    "minimal=clean airy soft light (Apple/Notion), "
                    "editorial=magazine sophisticated (Vogue/NYT), "
                    "luxury=premium dark gold (Rolex/Chanel), "
                    "vibrant=electric gradient DTC (Glossier)."
                ),
                "enum": ["bold", "minimal", "editorial", "luxury", "vibrant"],
                "default": "bold",
            },
            "format": {
                "type": "string",
                "enum": ["square", "story", "landscape", "portrait"],
                "default": "square",
            },
            "logo_url": {
                "type": "string",
                "description": "Brand logo URL — passed to Gemini as colour/aesthetic reference when generating from scratch.",
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "pro"],
                "default": "pro",
                "description": "pro=Gemini Pro (highest quality, most photorealistic — default for product ads). fast=Gemini Flash (quicker previews).",
            },
        },
        "required": ["concept"],
    },
)
async def generate_design_background(ctx: ToolContext, args: Dict[str, Any]):
    from nano_banana_service import generate_creative_image, edit_product_image

    import random as _random
    _BG_STYLES = ["bold", "minimal", "editorial", "luxury", "vibrant"]

    concept           = args.get("concept", "")
    product_image_url = args.get("product_image_url")
    style             = args.get("style") or _random.choice(_BG_STYLES)
    fmt               = args.get("format", "square")
    logo_url          = args.get("logo_url")
    quality           = args.get("quality", "fast")

    style_scene_hints = {
        "bold":      "dramatic cinematic lighting, deep shadows, high contrast, moody atmosphere — think Nike or Supreme campaign",
        "minimal":   "clean studio lighting, soft diffused shadows, airy and spacious feel, neutral tones — think Apple or Muji",
        "editorial": "magazine-quality lighting, sophisticated real-world setting, editorial photography — think Vogue or NYT Magazine",
        "luxury":    "low-key premium lighting, deep dark background, subtle warm gold or amber accents — think Rolex or Chanel",
        "vibrant":   "vibrant colourful real environment, energetic natural or neon-accented lighting, electric atmosphere — think Glossier or Red Bull",
    }
    style_hint = style_scene_hints.get(style, "professional commercial photography, natural lighting, real environment")

    # ── Route A: edit the real product photo ──────────────────────────────────
    if product_image_url:
        scene_prompt = (
            f"Goal: {concept}. "
            f"Visual mood and style: {style_hint}. "
            f"The scene must feel completely real and photographic — "
            f"genuine surfaces, natural or studio light, real depth of field. "
            f"The result must look like it was shot by a professional photographer on location or in a studio, "
            f"not generated by AI."
        )
        result = await edit_product_image(
            product_image_url=product_image_url,
            scene_prompt=scene_prompt,
            format=fmt,
            quality=quality,
        )
        if result.get("success"):
            bg_url = result["image_url"]
            return {
                "success": True,
                "background_url": bg_url,
                "source": "gemini_product_edit",
                "format": fmt,
                "style": style,
                "markdown": f"![Edited product background]({bg_url})",
                "next_step": "Call list_orshot_templates, pick the best template, call get_orshot_template_fields, then render_orshot_template placing this background_url into the template's image field.",
            }
        # Fallback to raw product image if editing fails
        logger.warning("[generate_design_background] Gemini edit failed (%s), using raw product image", result.get("error"))
        return {
            "success": True,
            "background_url": product_image_url,
            "source": "product_image_fallback",
            "format": fmt,
            "style": style,
            "markdown": f"![Product background]({product_image_url})",
            "next_step": "Call list_orshot_templates, pick the best template, call get_orshot_template_fields, then render_orshot_template placing this background_url into the template's image field.",
        }

    # ── Route B: generate a scene from scratch ────────────────────────────────
    nb_prompt = (
        f"{concept}. "
        f"Style: {style_hint}. "
        f"NO text, no words, no letters anywhere in the image — pure visual only. "
        f"Professional marketing background, high quality photography."
    )
    result = await generate_creative_image(
        prompt=nb_prompt,
        format=fmt,
        quality=quality,
        logo_url=logo_url,
    )
    if not result.get("success"):
        return {"error": result.get("error", "Gemini generation failed")}

    bg_url = result["image_url"]
    return {
        "success": True,
        "background_url": bg_url,
        "source": "gemini_generated",
        "format": fmt,
        "style": style,
        "markdown": f"![AI Background]({bg_url})",
        "next_step": "Call list_orshot_templates, pick the best template, call get_orshot_template_fields, then render_orshot_template placing this background_url into the template's image field.",
    }


@tool(
    name="create_business_document",
    description=(
        "Create a professional PDF document like an invoice, quote, proposal, or report."
    ),
    parameters={
        "type": "object",
        "required": ["title", "content"],
        "properties": {
            "title": {
                "type": "string",
                "description": "Document title (e.g. 'Invoice INV-001' or 'Marketing Proposal').",
            },
            "content": {
                "type": "string",
                "description": "The main body of the document. Use \\n for new paragraphs.",
            }
        },
    },
)
async def create_business_document(ctx: ToolContext, args: Dict[str, Any]):
    import asyncio
    import base64
    import uuid as _uuid
    title = args.get("title", "Document")
    content = args.get("content", "")

    owner = await ctx.db.users.find_one({"_id": ctx.business_id})
    business_name = (owner.get("business_name") or owner.get("owner_name") or "My Business") if owner else "My Business"

    md = f"# {title}\n\n{content}"
    try:
        from .document_generator import generate_pdf as _gen_pdf
        filepath = await asyncio.get_event_loop().run_in_executor(
            None, _gen_pdf, md, None, business_name
        )
    except Exception as e:
        logger.exception("[create_business_document] PDF generation failed")
        return {"error": f"PDF generation failed: {e}"}

    try:
        from image_handler import S3Handler
        pdf_bytes = filepath.read_bytes()
        b64 = base64.b64encode(pdf_bytes).decode()
        filename = f"doc-{_uuid.uuid4().hex[:8]}.pdf"
        pdf_url = await S3Handler.upload_file(b64, filename, content_type="application/pdf")
    except Exception as e:
        logger.exception("[create_business_document] S3 upload failed")
        return {"error": f"PDF upload failed: {e}"}
    finally:
        try:
            filepath.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        from saved_designs import insert_saved_design
        await insert_saved_design(
            ctx.db,
            ctx.business_id,
            name=(title or "PDF document")[:200],
            asset_kind="pdf",
            file_url=pdf_url,
            thumbnail_url=None,
            source_tool="create_business_document",
            conversation_id=ctx.user.get("_active_conversation_id"),
        )
    except Exception:
        logger.exception("[create_business_document] saved_designs insert skipped")

    return {
        "success": True,
        "pdf_url": pdf_url,
        "markdown": f"📄 **[Download {title}]({pdf_url})**" if pdf_url else "",
    }

@tool(
    name="create_presentation",
    description=(
        "Create an editable PowerPoint presentation (.pptx) slide deck. "
        "Provide a title and a list of slides with bullet points."
    ),
    parameters={
        "type": "object",
        "required": ["title", "slides_data"],
        "properties": {
            "title": {
                "type": "string",
                "description": "The main title of the presentation.",
            },
            "slides_data": {
                "type": "array",
                "description": "A list of slide objects. Each object should have a 'title' string and a 'content' array of bullet point strings.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "array", "items": {"type": "string"}}
                    }
                }
            }
        },
    },
)
async def create_presentation(ctx: ToolContext, args: Dict[str, Any]):
    from presentation_service import generate_presentation
    title = args.get("title", "Presentation")
    slides_data = args.get("slides_data", [])
    
    owner = await ctx.db.users.find_one({"_id": ctx.business_id})
    business_name = owner.get("business_name") or owner.get("owner_name") or "My Business" if owner else "My Business"

    result = generate_presentation(title, slides_data, business_name)
    
    if result.get("error"):
        return {"error": result["error"]}
        
    url = result.get("url")
    if url:
        try:
            from saved_designs import insert_saved_design

            await insert_saved_design(
                ctx.db,
                ctx.business_id,
                name=(title or "Presentation")[:200],
                asset_kind="pptx",
                file_url=url,
                thumbnail_url=None,
                source_tool="create_presentation",
                conversation_id=ctx.user.get("_active_conversation_id"),
            )
        except Exception:
            logger.exception("[create_presentation] saved_designs insert skipped")
    return {
        "success": True,
        "pptx_url": url,
        "markdown": f"📊 **[Download Presentation: {title}]({url})**" if url else "",
    }


# ═════════════════════════════════════════════════════════════════════════════
# META ADS AGENT — drafts persisted for Marketing → Meta Ads sync later
# ═════════════════════════════════════════════════════════════════════════════


def _meta_draft_notes_payload(args: Dict[str, Any]) -> str:
    """Merge freeform notes with structured fields for Marketing → Meta Ads UI."""
    raw_notes = (args.get("notes") or "").strip()
    base: Dict[str, Any] = {
        "audience": "",
        "strategy": "",
        "start_date": "",
        "end_date": "",
        "creative_format": "",
        "products_advertised": "",
        "creative_assets_plan": "",
        "ad_preview": "",
    }
    if raw_notes.startswith("{"):
        try:
            parsed = json.loads(raw_notes)
            if isinstance(parsed, dict):
                for k in base:
                    if k in parsed and parsed[k] is not None:
                        base[k] = str(parsed[k])
        except Exception:
            base["strategy"] = raw_notes
    else:
        base["strategy"] = raw_notes
    for key in (
        "audience",
        "strategy",
        "start_date",
        "end_date",
        "creative_format",
        "products_advertised",
        "creative_assets_plan",
        "ad_preview",
    ):
        val = args.get(key)
        if val is not None and str(val).strip():
            base[key] = str(val).strip()
    return json.dumps(base, ensure_ascii=False)


@tool(
    name="save_meta_ads_campaign_draft",
    description=(
        "Save a Meta (Facebook/Instagram) Ads campaign draft for this business. "
        "Call when the user wants to persist a planned campaign from chat. "
        "Objectives should be plain strings e.g. awareness, traffic, leads, sales. "
        "Pass creative_format, products_advertised, creative_assets_plan, ad_preview when known — they merge into notes JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Campaign name"},
            "objective": {"type": "string", "description": "Primary objective keyword"},
            "daily_budget": {"type": "number", "description": "Suggested daily budget"},
            "currency": {"type": "string", "description": "ISO currency e.g. USD"},
            "notes": {"type": "string", "description": "Optional: plain strategy text or full JSON string"},
            "audience": {"type": "string", "description": "Targeting summary"},
            "strategy": {"type": "string", "description": "Strategy / angles"},
            "start_date": {"type": "string", "description": "Optional start YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "Optional end YYYY-MM-DD"},
            "creative_format": {
                "type": "string",
                "description": "One of: image, video, carousel, reels, mixed, undecided",
            },
            "products_advertised": {
                "type": "string",
                "description": "Which catalog products this ad focuses on",
            },
            "creative_assets_plan": {
                "type": "string",
                "description": "owner_will_upload | zilo_generated_copy_only | need_both | tbd",
            },
            "ad_preview": {
                "type": "string",
                "description": "Text preview: headlines, primary text, CTA — Markdown ok",
            },
        },
        "required": ["name"],
    },
    destructive=False,
)
async def save_meta_ads_campaign_draft(ctx: ToolContext, args: Dict[str, Any]):
    name = (args.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    notes_out = _meta_draft_notes_payload(args)
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": ctx.business_id,
        "name": name,
        "objective": (args.get("objective") or "awareness").strip(),
        "daily_budget": float(args.get("daily_budget") or 0),
        "currency": (args.get("currency") or "USD").strip().upper()[:8],
        "notes": notes_out,
        "status": "draft",
        "created_at": datetime.utcnow(),
        "source": "meta_ads_agent",
    }
    await ctx.db.meta_ads_campaign_drafts.insert_one(doc)
    return {"status": "saved", "draft_id": doc["_id"], "name": doc["name"]}


@tool(
    name="list_meta_ads_campaign_drafts",
    description="List Meta Ads campaign drafts saved from Zilo Chat for this business (newest first).",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 15, "minimum": 1, "maximum": 50},
        },
    },
)
async def list_meta_ads_campaign_drafts(ctx: ToolContext, args: Dict[str, Any]):
    limit = min(int(args.get("limit") or 15), 50)
    rows = await ctx.db.meta_ads_campaign_drafts.find(
        {"user_id": ctx.business_id}
    ).sort("created_at", -1).to_list(limit)
    return {
        "count": len(rows),
        "drafts": [
            {
                "id": str(r["_id"]),
                "name": r.get("name"),
                "objective": r.get("objective"),
                "daily_budget": r.get("daily_budget"),
                "currency": r.get("currency"),
                "notes": (r.get("notes") or "")[:4000],
                "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ],
    }


# ═════════════════════════════════════════════════════════════════════════════
# X ADS AGENT — drafts in Mongo `x_ads_campaign_drafts`
# ═════════════════════════════════════════════════════════════════════════════


@tool(
    name="save_x_ads_campaign_draft",
    description=(
        "Save an X (Twitter) Ads campaign draft for this business. "
        "Call when the user wants to persist a planned X campaign from chat. "
        "Objectives: reach, engagements, website_clicks, followers, video_views, app_installs, or plain-language equivalents. "
        "Merge audience, strategy, creative_format, products_advertised, creative_assets_plan, ad_preview into notes (same shape as Meta drafts)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Campaign name"},
            "objective": {"type": "string", "description": "Primary objective keyword"},
            "daily_budget": {"type": "number", "description": "Suggested daily budget"},
            "currency": {"type": "string", "description": "ISO currency e.g. USD"},
            "notes": {"type": "string", "description": "Optional: plain strategy text or full JSON string"},
            "audience": {"type": "string", "description": "Targeting summary"},
            "strategy": {"type": "string", "description": "Strategy / angles"},
            "start_date": {"type": "string", "description": "Optional start YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "Optional end YYYY-MM-DD"},
            "creative_format": {
                "type": "string",
                "description": "One of: image, video, carousel, mixed, undecided",
            },
            "products_advertised": {
                "type": "string",
                "description": "Which catalog products this ad focuses on",
            },
            "creative_assets_plan": {
                "type": "string",
                "description": "owner_will_upload | zilo_generated_copy_only | need_both | tbd",
            },
            "ad_preview": {
                "type": "string",
                "description": "Post copy, headline ideas, CTA — Markdown ok",
            },
        },
        "required": ["name"],
    },
    destructive=False,
)
async def save_x_ads_campaign_draft(ctx: ToolContext, args: Dict[str, Any]):
    name = (args.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    notes_out = _meta_draft_notes_payload(args)
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": ctx.business_id,
        "name": name,
        "objective": (args.get("objective") or "reach").strip(),
        "daily_budget": float(args.get("daily_budget") or 0),
        "currency": (args.get("currency") or "USD").strip().upper()[:8],
        "notes": notes_out,
        "status": "draft",
        "created_at": datetime.utcnow(),
        "source": "x_ads_agent",
    }
    await ctx.db.x_ads_campaign_drafts.insert_one(doc)
    return {"status": "saved", "draft_id": doc["_id"], "name": doc["name"]}


@tool(
    name="list_x_ads_campaign_drafts",
    description="List X Ads campaign drafts saved from Zilo Chat for this business (newest first).",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 15, "minimum": 1, "maximum": 50},
        },
    },
)
async def list_x_ads_campaign_drafts(ctx: ToolContext, args: Dict[str, Any]):
    limit = min(int(args.get("limit") or 15), 50)
    rows = await ctx.db.x_ads_campaign_drafts.find(
        {"user_id": ctx.business_id}
    ).sort("created_at", -1).to_list(limit)
    return {
        "count": len(rows),
        "drafts": [
            {
                "id": str(r["_id"]),
                "name": r.get("name"),
                "objective": r.get("objective"),
                "daily_budget": r.get("daily_budget"),
                "currency": r.get("currency"),
                "notes": (r.get("notes") or "")[:4000],
                "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ],
    }
