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
import re
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
    import os as _os

    q: Dict[str, Any] = {"user_id": ctx.business_id}
    if s := (args.get("search") or "").strip():
        q["name"] = {"$regex": s, "$options": "i"}
    limit = min(int(args.get("limit") or 50), 100)
    rows = await ctx.db.products.find(q).sort("created_at", -1).to_list(limit)

    backend_url = (
        _os.environ.get("BACKEND_PUBLIC_URL")
        or _os.environ.get("PUBLIC_BASE_URL")
        or ""
    ).rstrip("/")

    def _to_public(url: str) -> str:
        if not url or not backend_url or "amazonaws.com" not in url:
            return url
        try:
            from image_handler import S3Handler
            _, key = S3Handler.parse_s3_source_to_bucket_key(url)
            if key:
                return f"{backend_url}/api/images/s3/{key}"
        except Exception:
            pass
        return url

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
            "image_url": _to_public(orig),
            "images": [_to_public(u) for u in imgs],
            "description": p.get("description"),
            "in_stock": p.get("in_stock", True),
            "stock_quantity": p.get("stock_quantity"),
            "unit": p.get("unit"),
            "moq": p.get("moq"),
            "pricing_tiers": p.get("pricing_tiers") or None,
            "variants": p.get("variants") or None,
            "modifier_groups": p.get("modifier_groups") or None,
            "created_at": p.get("created_at"),
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
    import os as _os

    product_id = args["product_id"]
    product = await ctx.db.products.find_one({"_id": product_id, "user_id": ctx.business_id})
    if not product:
        # Fallback: agent may have passed a product name instead of a UUID.
        # Try a case-insensitive name lookup within the same business scope.
        product = await ctx.db.products.find_one({
            "name": {"$regex": f"^{re.escape(product_id)}$", "$options": "i"},
            "user_id": ctx.business_id,
        })
    if not product:
        return {"error": f"Product not found (tried id and name lookup for {product_id!r}). Call list_products to get valid product ids."}

    # Handle images like the backend API does
    imgs = list(product.get("images", []))
    orig = product.get("image_url")
    if orig and orig not in imgs:
        imgs.insert(0, orig)

    # Convert private S3 URLs to publicly accessible proxy URLs so that
    # the AI can share them with users and pass them to Orshot without
    # triggering S3 AccessDenied errors.
    backend_url = (
        _os.environ.get("BACKEND_PUBLIC_URL")
        or _os.environ.get("PUBLIC_BASE_URL")
        or ""
    ).rstrip("/")

    def _to_public(url: str) -> str:
        if not url:
            return url
        if not backend_url:
            return url
        if "amazonaws.com" not in url:
            return url
        try:
            from image_handler import S3Handler
            _, key = S3Handler.parse_s3_source_to_bucket_key(url)
            if key:
                return f"{backend_url}/api/images/s3/{key}"
        except Exception:
            pass
        return url

    public_imgs = [_to_public(u) for u in imgs]
    public_orig = _to_public(orig)

    # Advance design flow: product is now locked → ask for platform next
    try:
        from .design_state import load_design_state, update_design_state
        conv_id = ctx.user.get("_active_conversation_id")
        if conv_id:
            ds = await load_design_state(ctx.db, conv_id, ctx.business_id)
            if ds.get("flow_step") in ("awaiting_product", None):
                await update_design_state(
                    ctx.db, conv_id, ctx.business_id,
                    product_id=product_id,
                    product_name=product.get("name", "Unnamed Product"),
                    flow_step="awaiting_platform",
                )
    except Exception:
        logger.exception("[get_product_images] design_state update skipped")

    return {
        "product_id": product_id,
        "product_name": product.get("name", "Unnamed Product"),
        "image_url": public_orig,
        "images": public_imgs,
        "image_count": len(public_imgs),
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
        "business_type (industry), short hints from business knowledge, and the brand kit "
        "(`default_logo_url`, `brand_primary_color`, `brand_font`). "
        "Use for Meta/Google ads, proposals, and any time industry-aware advice is needed. "
        "For design work, **always call this first** so you can pass the brand logo URL and "
        "primary colour into `render_orshot_template.modifications` and `generate_design_background.logo_url`."
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

    # Brand assets — best-effort lookups so failures here don't break the tool.
    default_logo_url = ""
    brand_primary_color = ""
    brand_font = ""
    try:
        from saved_designs import get_primary_logo_url, get_brand_settings

        default_logo_url = (await get_primary_logo_url(ctx.db, ctx.business_id)) or ""
        brand = await get_brand_settings(ctx.db, ctx.business_id)
        brand_primary_color = (brand or {}).get("brand_primary_color", "") or ""
        brand_font = (brand or {}).get("brand_font", "") or ""
    except Exception:
        logger.exception("[get_owner_info] brand asset lookup skipped")

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
        # Brand kit — pass these straight into render_orshot_template.modifications
        # (logo image fields, brand colour fields) and generate_design_background.logo_url.
        "default_logo_url":    default_logo_url,
        "brand_primary_color": brand_primary_color,
        "brand_font":          brand_font,
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
        "gmail":           os.getenv("NEXT_PUBLIC_NANGO_ID_EMAIL",          "google-mail"),
        "microsoft":       os.getenv("NEXT_PUBLIC_NANGO_ID_MICROSOFT",       "microsoft"),
        "google_calendar": os.getenv("NEXT_PUBLIC_NANGO_ID_CALENDAR",        "google-calendar"),
        "google_sheets":   os.getenv("NEXT_PUBLIC_NANGO_ID_GOOGLE_SHEETS",   "google-sheet"),
        "notion":          os.getenv("NEXT_PUBLIC_NANGO_ID_NOTION",          "notion"),
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


@tool(
    name="generate_document",
    description=(
        "Convert markdown content into a downloadable PDF or DOCX file and return a download link. "
        "Call this after writing a full document (proposal, report, invoice, contract) so the user can download it immediately. "
        "Pass the complete markdown as `content`. Set `format` to 'pdf' or 'docx'. "
        "Set `filename` to a short descriptive name without extension (e.g. 'business-proposal'). "
        "Use `template` to control the visual design: "
        "'professional' (default) — branded header bar with accent colour, clean sans-serif; "
        "'minimal' — ultra-clean white layout, uppercase section headings, no coloured bars; "
        "'executive' — dark navy header, Playfair Display serif headings, dark table headers — ideal for proposals and contracts."
    ),
    parameters={
        "type": "object",
        "properties": {
            "content":  {"type": "string", "description": "The full Markdown content to export."},
            "format":   {"type": "string", "enum": ["pdf", "docx"], "default": "pdf"},
            "filename": {"type": "string", "description": "Base filename without extension, e.g. 'q1-report'."},
            "template": {
                "type": "string",
                "enum": ["professional", "minimal", "executive"],
                "default": "professional",
                "description": "Visual design template for the document.",
            },
            "image_prompt": {
                "type": "string",
                "description": (
                    "Optional. A prompt for a hero image that visually represents the document's actual subject matter. "
                    "Only include when an image genuinely elevates the document — e.g. a client proposal, marketing strategy, business plan, pitch deck. "
                    "Skip for invoices, receipts, payment requests, legal contracts, internal memos, or any document where an image would feel out of place. "
                    "Write the prompt as if briefing a real photographer — describe the scene, lighting, mood, and subject with specificity. "
                    "CRITICAL prompt rules to avoid AI-looking results: "
                    "(1) Describe a simple, uncluttered scene with ONE clear subject — not 'a boardroom with many elements'. "
                    "(2) Reference real photography styles: 'shot on Canon EOS R5', 'f/2.8 shallow depth of field', 'natural window light', 'golden hour'. "
                    "(3) Never use the words 'photorealistic', 'hyperrealistic', 'cinematic', 'digital art', 'render', '3D', or 'illustration'. "
                    "(4) Be specific to the document topic: for a resort proposal write 'A quiet infinity pool overlooking the ocean at dusk, warm ambient light, shot on 35mm'; "
                    "for a restaurant business plan write 'Empty upscale restaurant interior, warm pendant lighting, dark wood tables, soft bokeh background, shot at f/1.8'. "
                    "The more specific and grounded in real photography the prompt is, the less it will look AI-generated."
                ),
            },
        },
        "required": ["content"],
    },
)
async def generate_document(ctx: ToolContext, args: Dict[str, Any]):
    import asyncio
    import base64
    import re as _re
    import uuid as _uuid
    content = (args.get("content") or "").strip()
    if not content:
        return {"error": "content is required"}
    fmt = (args.get("format") or "pdf").lower()
    if fmt not in ("pdf", "docx"):
        fmt = "pdf"
    template = (args.get("template") or "professional").lower()
    if template not in ("professional", "minimal", "executive"):
        template = "professional"

    raw_name = (args.get("filename") or "document").strip()
    safe = _re.sub(r"[^\w\-]", "_", raw_name)[:60] or "document"
    filename = f"{safe}.{fmt}"

    # Fetch business name and document style for branded output
    owner = await ctx.db.users.find_one({"_id": ctx.business_id})
    business_name = (owner.get("business_name") or owner.get("owner_name") or "My Business") if owner else "My Business"
    doc_style: Dict[str, Any] = {}
    try:
        from saved_designs import get_document_style as _get_doc_style
        doc_style = await _get_doc_style(ctx.db, ctx.business_id) or {}
    except Exception:
        pass

    _title = raw_name.replace("-", " ").replace("_", " ").title()

    # Generate a hero image only when the AI explicitly provides an image_prompt
    # The AI decides based on document content whether an image adds value
    hero_image_url: str | None = None
    _image_prompt = (args.get("image_prompt") or "").strip()
    if _image_prompt:
        try:
            from nano_banana_service import generate_creative_image
            _hero_result = await generate_creative_image(
                prompt=_image_prompt + ", shot on full-frame camera, natural lighting, no text, no watermarks, no logos, clean composition",
                format="landscape",
                quality="pro",
            )
            if _hero_result.get("success"):
                hero_image_url = _hero_result["image_url"]
                logger.info("[generate_document] Hero image generated: %s", hero_image_url)
            else:
                logger.warning("[generate_document] Hero image failed: %s", _hero_result.get("error"))
        except Exception as _he:
            logger.warning("[generate_document] Hero image skipped: %s", _he)

    # Generate HTML preview (used for the in-chat iframe and, for PDF, as WeasyPrint source)
    preview_key: str | None = None
    html_doc: str | None = None
    try:
        from .document_generator import generate_html_document, store_html_preview
        html_doc = generate_html_document(
            content, title=_title, business_name=business_name,
            style=doc_style, template=template, hero_image_url=hero_image_url,
        )
        preview_key = store_html_preview(html_doc)
    except Exception:
        logger.warning("[generate_document] HTML preview generation failed")

    if fmt == "pdf":
        # Use Playwright (HTML→PDF) for polished, branded output
        try:
            from .document_generator import generate_pdf_from_html
            if html_doc is None:
                from .document_generator import generate_html_document
                html_doc = generate_html_document(
                    content, title=_title, business_name=business_name,
                    style=doc_style, template=template, hero_image_url=hero_image_url,
                )
            filepath = await asyncio.get_event_loop().run_in_executor(
                None, generate_pdf_from_html, html_doc, filename
            )
        except Exception as e:
            logger.exception("[generate_document] WeasyPrint PDF failed, falling back to ReportLab")
            try:
                from .document_generator import generate_pdf
                filepath = generate_pdf(content, filename, business_name=business_name, style=doc_style)
            except Exception as e2:
                return {"error": f"PDF generation failed: {e2}"}
    else:
        # DOCX with brand styling
        try:
            from .document_generator import generate_docx
            filepath = generate_docx(content, filename, business_name=business_name, style=doc_style)
        except Exception as e:
            logger.exception("[generate_document] DOCX generation failed")
            return {"error": f"DOCX generation failed: {e}"}

    # Upload to S3 so the file persists beyond the current process
    file_url = None
    try:
        from pathlib import Path as _Path
        from image_handler import S3Handler
        _filepath = _Path(filepath) if isinstance(filepath, str) else filepath
        file_bytes = _filepath.read_bytes()
        b64 = base64.b64encode(file_bytes).decode()
        ext = "pdf" if fmt == "pdf" else "docx"
        s3_name = f"doc-{_uuid.uuid4().hex[:8]}.{ext}"
        content_type = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        file_url = await S3Handler.upload_file(b64, s3_name, content_type=content_type)
    except Exception as e:
        logger.warning("[generate_document] S3 upload failed, serving from temp: %s", e)
    finally:
        try:
            _filepath = _Path(filepath) if isinstance(filepath, str) else filepath
            _filepath.unlink(missing_ok=True)
        except Exception:
            pass

    # Save to design library
    if file_url:
        try:
            from saved_designs import insert_saved_design
            await insert_saved_design(
                ctx.db,
                ctx.business_id,
                name=(raw_name or "Document")[:200],
                asset_kind=fmt,
                file_url=file_url,
                thumbnail_url=None,
                source_tool="generate_document",
                conversation_id=ctx.user.get("_active_conversation_id"),
            )
        except Exception:
            logger.exception("[generate_document] saved_designs insert skipped")

    if file_url:
        return {
            "status": "ready",
            "download_url": file_url,
            "filename": filename,
            "format": fmt,
            "template": template,
            "html_preview": html_doc or "",  # Stripped from LLM context by orchestrator
            "content_md": content,            # Stripped from LLM context by orchestrator
            "message": f"✅ **{raw_name}** is ready. See the document preview below.",
        }
    else:
        # Fallback: in-memory store (only if S3 failed)
        key = str(_uuid.uuid4())
        _fallback_doc_store[key] = str(filepath)
        return {
            "status": "ready",
            "download_url": f"/api/assistant/download/{key}",
            "filename": filename,
            "format": fmt,
            "template": template,
            "html_preview": html_doc or "",  # Stripped from LLM context by orchestrator
            "content_md": content,            # Stripped from LLM context by orchestrator
            "message": f"✅ **{raw_name}** is ready. See the document preview below.",
        }


# Fallback in-memory store for when S3 upload fails
_fallback_doc_store: Dict[str, str] = {}


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
        "List Orshot Studio templates in the workspace. Each template object has id, name, canvas size, "
        "and thumbnail_url. "
        "CRITICAL — URL RULE: When showing templates to the user, you MUST copy the thumbnail_url value "
        "character-for-character exactly as it appears in this tool's JSON response. Do not retype it, "
        "do not reconstruct it, do not shorten it. Select the value from the JSON, paste it. "
        "Every real thumbnail_url in this response starts with https://storage.orshot.com/ — "
        "if what you are about to write does NOT start with https://storage.orshot.com/, stop and "
        "fetch the value again from the tool result. "
        "NEVER invent, guess, or approximate a URL. Forbidden examples: https://example.com/..., "
        "template1.jpg, thumbnail_url_1, /images/..., or any string not present verbatim in the JSON. "
        "If a template object has a null or empty thumbnail_url, skip it entirely and pick the next one. "
        "Show 3 best fits for the brief, not the full list."
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
    from .design_state import update_design_state, load_design_state

    page = int(args.get("page") or 1)
    limit = int(args.get("limit") or 20)
    result = await list_studio_templates(page=page, limit=limit)

    # Persist which template ids were surfaced this turn so "See more options"
    # can skip them next time without the AI having to remember the full list.
    # Also advance flow_step to awaiting_template if we are currently at
    # awaiting_platform or awaiting_product (i.e. the first time templates are shown).
    try:
        templates = (result or {}).get("templates") or []
        ids = [t.get("id") for t in templates if isinstance(t, dict) and t.get("id") is not None]
        conv_id = ctx.user.get("_active_conversation_id")
        if ids and conv_id:
            existing = await load_design_state(ctx.db, conv_id, ctx.business_id)
            current_step = existing.get("flow_step") or ""
            advance = current_step in ("awaiting_product", "awaiting_platform", "")
            await update_design_state(
                ctx.db,
                conv_id,
                ctx.business_id,
                add_templates_shown=ids,
                **({"flow_step": "awaiting_template"} if advance else {}),
            )
    except Exception:
        logger.exception("[list_orshot_templates] design_state update skipped")

    # Annotate each template so the model can identify which thumbnail_url to use.
    # The model MUST copy the thumbnail_url value verbatim from this response into markdown.
    try:
        templates = (result or {}).get("templates") or []
        for t in templates:
            if isinstance(t, dict) and t.get("thumbnail_url"):
                t["_url_instruction"] = (
                    f"USE EXACTLY: {t['thumbnail_url']}"
                )
    except Exception:
        pass

    return result


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

    explicit_tid = (args.get("template_id") or "").strip()
    tid = explicit_tid or (_os.environ.get("ORSHOT_DEFAULT_TEMPLATE_ID") or "").strip()
    if not tid:
        return {"error": "Pass template_id or set ORSHOT_DEFAULT_TEMPLATE_ID on the server."}

    data = await get_studio_template(tid)
    if data.get("error"):
        # Only fall back to the env default when the caller did NOT explicitly pass a
        # template_id. If they did, surface the error so the AI doesn't silently end up
        # reading a different template's fields and rendering with mismatched modifications.
        default_tid = (_os.environ.get("ORSHOT_DEFAULT_TEMPLATE_ID") or "").strip()
        if not explicit_tid and default_tid and default_tid != tid:
            logger.warning("[get_orshot_template_fields] template %s failed (%s), retrying with default %s", tid, data["error"], default_tid)
            data = await get_studio_template(default_tid)
            if not data.get("error"):
                data["_fallback_used"] = True
                data["_original_template_id"] = tid
        if data.get("error"):
            err = data.get("error") or "unknown error"
            return {
                "error": f"Could not fetch fields for template {tid!r}: {err}. "
                         "Check that the template_id is correct and the Orshot API key is valid. "
                         "Call list_orshot_templates to get valid template ids.",
                "template_id": tid,
            }

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

    # Persist the field list so the render-time guard and `verify_design_ready`
    # can detect logo-incompatible templates without re-hitting Orshot.
    try:
        from .design_state import update_design_state, load_design_state

        conv_id = ctx.user.get("_active_conversation_id")
        if conv_id and fields:
            existing = await load_design_state(ctx.db, conv_id, ctx.business_id)
            current_step = existing.get("flow_step") or ""
            # Only advance to awaiting_copy_approval if we are currently at
            # awaiting_template (i.e. the user just picked a template and the
            # agent is now studying its fields). Do NOT advance the step if called
            # during template browsing or at any other phase.
            advance_step = current_step == "awaiting_template"
            await update_design_state(
                ctx.db,
                conv_id,
                ctx.business_id,
                locked_template_fields=fields,
                **({"flow_step": "awaiting_copy_approval"} if advance_step else {}),
            )
    except Exception:
        logger.exception("[get_orshot_template_fields] design_state update skipped")

    return {
        "success": True,
        "template_id": data.get("id"),
        "name": data.get("name"),
        "canvas_width": data.get("canvas_width"),
        "canvas_height": data.get("canvas_height"),
        "thumbnail_url": data.get("thumbnail_url"),
        "page_count": page_count,
        "fields": fields,
        "note": (
            "Use `key` in `render_orshot_template.modifications`. Any text field also accepts "
            "style overrides via `<key>.color`, `<key>.fontFamily`, `<key>.fontSize`, "
            "`<key>.backgroundColor`, `<key>.fontWeight`, `<key>.textAlign` — use these to "
            "apply the brand colour/font from `get_owner_info` to any headline/CTA/body field, "
            "even when the template has no dedicated brand-colour field. "
            "Full `pages_data` is omitted to keep chat storage small."
        ),
    }


@tool(
    name="render_orshot_template",
    description=(
        "Render a graphic from an **Orshot Studio** template (hosted layouts — import from Canva/Figma supported in Orshot). "
        "Requires server env **ORSHOT_API_KEY**. Optional **ORSHOT_DEFAULT_TEMPLATE_ID** supplies a default when `template_id` is omitted. "
        "**modifications** keys must match Orshot Studio dynamic parameters (often `pageN@field_name` on carousels). "
        "Use `get_orshot_template_fields` once to learn keys, then keep them in mind for refinements. "
        "**Style overrides:** any text/image field accepts dot-notation style parameters in `modifications` — "
        "e.g. `\"headline\": \"Big Sale\"` plus `\"headline.color\": \"#FF6600\"`, `\"headline.fontFamily\": \"Inter\"`, "
        "`\"headline.fontSize\": \"48px\"`, `\"cta.backgroundColor\": \"#FF6600\"`, `\"cta.fontWeight\": \"700\"`. "
        "This means brand colour/font from `get_owner_info` apply to *any* headline/CTA/body field even when the "
        "template has no dedicated brand-colour field — just append `.color` / `.fontFamily` to the field key. "
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
                "description": (
                    "Dynamic field values for the template (Studio parameter names → strings or image URLs). "
                    "Supports per-field style overrides via dot notation: `<key>.color`, `<key>.fontFamily`, "
                    "`<key>.fontSize`, `<key>.backgroundColor`, `<key>.fontWeight`, `<key>.textAlign`, "
                    "`<key>.letterSpacing`, `<key>.lineHeight`, `<key>.opacity`, `<key>.borderRadius` (image), "
                    "`<key>.borderColor` (image). Use these to apply brand colour/font to any field."
                ),
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
async def render_orshot_template(ctx: ToolContext, args: Dict[str, Any]):
    import os as _os

    from orshot_service import render_studio_template

    explicit_tid = (args.get("template_id") or "").strip()
    tid = explicit_tid or (_os.environ.get("ORSHOT_DEFAULT_TEMPLATE_ID") or "").strip()
    if not tid:
        return {
            "error": "No template_id: pass template_id in the tool call or set ORSHOT_DEFAULT_TEMPLATE_ID on the server.",
        }
    template_id_used = str(tid)

    mods = args.get("modifications")
    if not isinstance(mods, dict):
        mods = {}

    # ── Pre-render guard ─────────────────────────────────────────────────────
    # Verify that user-stated requirements (recorded via note_design_requirement)
    # are actually present in the modifications dict BEFORE we burn an Orshot
    # credit. Runs against the original `mods` — pre-presigning — so substring
    # matches against brand asset URLs are reliable. Best-effort: any failure
    # in the guard itself never blocks the render.
    original_mods = dict(mods)
    try:
        from .design_state import load_design_state

        conv_id = ctx.user.get("_active_conversation_id")
        if conv_id:
            state = await load_design_state(ctx.db, conv_id, ctx.business_id)
            pending = set(state.get("pending_requirements") or [])
            quotes = state.get("requirement_quotes") or {}
            staged_url = state.get("staged_image_url") or ""
            template_fields = state.get("locked_template_fields") or None
            brand = await _load_brand_kit(ctx) if pending else {}
            business_email = await _load_business_email(ctx)

            unmet: List[Dict[str, str]] = []
            if pending:
                unmet.extend(_evaluate_design_requirements(
                    pending, original_mods, brand, staged_url, template_fields,
                ))
            # Anti-fabrication scanner runs on every render, regardless of pending.
            unmet.extend(_detect_fabricated_facts(
                original_mods, quotes, business_email, template_fields,
            ))
            if unmet:
                logger.info(
                    "[render_orshot_template] blocked by guard (conv=%s, unmet=%s)",
                    conv_id, [u["code"] for u in unmet],
                )
                return {
                    "error": "render_blocked_by_requirements",
                    "reason": "One or more recorded user requirements are not satisfied by the modifications, "
                              "or the modifications contain fabricated facts (offers/URLs the user never stated). "
                              "Fix each item below, then call render_orshot_template again.",
                    "unmet": unmet,
                    "pending_requirements": sorted(pending),
                }
    except Exception:
        logger.exception("[render_orshot_template] pre-render guard skipped")

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
        # Only fall back to the env default when the caller did NOT explicitly pass a
        # template_id. If they did, the user/AI explicitly chose this template — silently
        # rendering with a different one would be a critical correctness bug (the design
        # would not match the locked template). Surface the error so the AI can re-fetch
        # fields with `get_orshot_template_fields` and retry with correct modifications.
        default_tid = (_os.environ.get("ORSHOT_DEFAULT_TEMPLATE_ID") or "").strip()
        if not explicit_tid and default_tid and default_tid != tid:
            logger.warning("[render_orshot_template] template %s failed (%s), retrying with default %s", tid, result["error"], default_tid)
            result = await render_studio_template(
                default_tid,
                mods,
                response_type=response_type,
                response_format=response_format,
            )
            if not result.get("error"):
                template_id_used = default_tid
        if result.get("error"):
            return result

    image_url = result.get("image_url")

    # ── Logo compositor ──────────────────────────────────────────────────────
    # When the user asked for their logo (`include_logo` in pending) and the
    # rendered modifications don't already contain the logo URL, paste the
    # brand logo onto the rendered image. This guarantees logo presence even
    # on templates that have no dedicated logo field. Best-effort: any
    # failure here falls back to the un-composited render.
    if image_url:
        try:
            from .design_state import load_design_state

            conv_id = ctx.user.get("_active_conversation_id")
            if conv_id:
                state = await load_design_state(ctx.db, conv_id, ctx.business_id)
                pending = set(state.get("pending_requirements") or [])
                if "include_logo" in pending:
                    brand = await _load_brand_kit(ctx)
                    logo = brand.get("default_logo_url") or ""
                    mod_blob = " ".join(_norm(v) for v in original_mods.values())
                    if logo and _norm(logo) not in mod_blob:
                        composited = await _composite_logo_on_image(image_url, logo)
                        if composited:
                            logger.info(
                                "[render_orshot_template] logo composited (conv=%s, tid=%s)",
                                conv_id, template_id_used,
                            )
                            image_url = composited
                            result["image_url"] = composited
                            urls = result.get("image_urls")
                            if isinstance(urls, list) and urls:
                                urls[0] = composited
        except Exception:
            logger.exception("[render_orshot_template] logo compositing skipped")

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

        # Persist the locked template + last render so the next turn's prompt
        # can show the AI exactly which template_id is in play (no silent swaps).
        try:
            from .design_state import update_design_state

            explicit_name = (args.get("name") or "").strip() or (args.get("presentation_label") or "").strip()
            await update_design_state(
                ctx.db,
                ctx.user.get("_active_conversation_id"),
                ctx.business_id,
                locked_template_id=str(template_id_used),
                locked_template_name=explicit_name or None,
                chosen_platform=(platform if platform and platform != "general" else None),
                chosen_format=(fmt if fmt and fmt != "general" else None),
                last_render_url=image_url,
                # Persist the original (pre-presigning) modifications so
                # verify_design_ready can audit logo / colour / copy presence
                # against the stable URLs the AI actually passed.
                last_render_modifications=original_mods,
                flow_step="refining",
            )
        except Exception:
            logger.exception("[render_orshot_template] design_state update skipped")

    return {
        "success": True,
        "template_id_used": template_id_used,
        "image_url": image_url,
        "image_urls": result.get("image_urls"),
        "presentation_label": pres or None,
        "markdown": f"![{name}]({image_url})" if image_url else "",
        "note": "Carousel templates may return multiple URLs in image_urls.",
    }


# ── AI-recreate design (Gemini-driven, template thumbnail as reference) ──────
# Combines staging + render in one call: Gemini receives the locked template's
# thumbnail (free) as a layout reference, the real product photo, the brand
# logo, and a strict fact pack — then produces the final design. The logo
# compositor still runs on top so the brand mark is pixel-identical, and an
# OCR pass scans the rendered text for any fabricated offers/URLs the model
# may have invented despite the prompt.


async def _build_design_fact_pack(ctx: "ToolContext") -> Dict[str, Any]:
    """Assemble the strict whitelist of facts the AI is allowed to render.

    Combines the business profile (name/phone/email), the brand kit
    (logo URL, primary colour, font), and any verbatim user quotes recorded
    via ``note_design_requirement`` (offers, websites). The recreate tool uses
    this both as prompt input *and* as the verification source for the OCR
    fabrication scanner — one source of truth.
    """
    pack: Dict[str, Any] = {
        "business_name": "",
        "business_phone": "",
        "business_email": "",
        "default_logo_url": "",
        "brand_primary_color": "",
        "brand_font": "",
        "requirement_quotes": {},
        "pending_requirements": [],
        "staged_image_url": "",
        "locked_template_name": "",
    }
    try:
        u = await ctx.db.users.find_one({"_id": ctx.business_id})
        if u:
            settings = u.get("settings", {}) or {}
            pack["business_name"] = (u.get("business_name") or "").strip()
            pack["business_phone"] = (u.get("phone_number") or settings.get("phone_number") or "").strip()
            pack["business_email"] = (u.get("email") or "").strip()
    except Exception:
        logger.exception("[fact_pack] business profile lookup failed")

    brand = await _load_brand_kit(ctx)
    pack["default_logo_url"] = brand.get("default_logo_url") or ""
    pack["brand_primary_color"] = brand.get("brand_primary_color") or ""
    pack["brand_font"] = brand.get("brand_font") or ""

    try:
        from .design_state import load_design_state

        conv_id = ctx.user.get("_active_conversation_id")
        if conv_id:
            state = await load_design_state(ctx.db, conv_id, ctx.business_id)
            pack["requirement_quotes"] = state.get("requirement_quotes") or {}
            pack["pending_requirements"] = list(state.get("pending_requirements") or [])
            pack["staged_image_url"] = state.get("staged_image_url") or ""
            pack["locked_template_name"] = state.get("locked_template_name") or ""
    except Exception:
        logger.exception("[fact_pack] design_state lookup failed")

    return pack


def _compose_recreate_prompt(
    fact_pack: Dict[str, Any],
    *,
    headline: str,
    tagline: str,
    cta: str,
    offer: str,
    website: str,
    extra_notes: str,
) -> str:
    """Build the strict instruction text Gemini sees alongside the reference image."""
    allowed: List[str] = []
    if fact_pack.get("business_name"):
        allowed.append(f"- Business name: {fact_pack['business_name']}")
    if fact_pack.get("business_phone"):
        allowed.append(f"- Phone: {fact_pack['business_phone']}")
    if fact_pack.get("business_email"):
        allowed.append(f"- Email: {fact_pack['business_email']}")
    if fact_pack.get("brand_primary_color"):
        allowed.append(f"- Brand colour (use as accent): {fact_pack['brand_primary_color']}")
    if fact_pack.get("brand_font"):
        allowed.append(f"- Brand font: {fact_pack['brand_font']}")
    if headline:
        allowed.append(f"- Headline (use exactly): {headline}")
    if tagline:
        allowed.append(f"- Tagline (use exactly): {tagline}")
    if cta:
        allowed.append(f"- Call to action (use exactly): {cta}")
    if offer:
        allowed.append(f"- Offer wording (use exactly): {offer}")
    if website:
        allowed.append(f"- Website (use exactly): {website}")

    allowed_block = "\n".join(allowed) if allowed else "- (none — leave all text slots empty)"

    return (
        "You are recreating a marketing design. The FIRST image is the layout reference — "
        "reproduce its composition, proportions, and visual style EXACTLY. The SECOND image "
        "(if present) is the real product to feature. The THIRD image (if present) is the "
        "brand logo for context only.\n\n"
        "STRICT RULES — read carefully, no exceptions:\n"
        "1. Reproduce the reference layout 100% as it is — same panels, same hierarchy, "
        "same shape and placement of headline, body text, image area, and call-to-action zone.\n"
        "2. Use ONLY the facts listed below. If a slot in the reference has no matching fact, "
        "LEAVE IT EMPTY — do not fill it with placeholder text, lorem ipsum, generic addresses, "
        "fake URLs, or invented contact details.\n"
        "3. NEVER invent prices, discounts, percentages, addresses, phone numbers, websites, "
        "social handles, dates, or any factual claim that is not in the allowed list below.\n"
        "4. Render text crisply and legibly. Spell every word EXACTLY as written below — "
        "no substitutions, no creative variants, no abbreviations.\n"
        "5. Replace the reference's product imagery with the supplied product photo when "
        "present. Do not redraw or stylise the product — keep its real shape, colour, and "
        "branding intact.\n"
        "6. Do not include any logo placeholder text like 'YOUR BRAND' or 'LOGO HERE' — the "
        "real brand logo is composited onto the output afterwards, leave clear space in the "
        "bottom-right corner for it.\n\n"
        "ALLOWED FACTS (the only text/data you may render):\n"
        f"{allowed_block}\n\n"
        + (f"ADDITIONAL DIRECTION:\n{extra_notes}\n\n" if extra_notes else "")
        + "Output: a single finished marketing image, ready to publish."
    )


async def _ocr_extract_text(image_url: str) -> Optional[str]:
    """Best-effort OCR via pytesseract. Returns the extracted text, or ``None``
    when pytesseract / the Tesseract binary isn't available — callers must
    treat ``None`` as "skip OCR check, don't block the render"."""
    if not image_url:
        return None
    try:
        import asyncio as _asyncio
        import io as _io
        import httpx as _httpx
        try:
            import pytesseract  # type: ignore[import]
        except Exception:
            logger.info("[ocr] pytesseract not installed — skipping OCR fabrication scan")
            return None
        from PIL import Image as _Image

        async with _httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(image_url)
            r.raise_for_status()
            img_bytes = r.content

        def _do_ocr() -> str:
            img = _Image.open(_io.BytesIO(img_bytes))
            try:
                return pytesseract.image_to_string(img) or ""
            except pytesseract.TesseractNotFoundError:  # type: ignore[attr-defined]
                return ""

        text = await _asyncio.get_event_loop().run_in_executor(None, _do_ocr)
        return text or ""
    except Exception:
        logger.exception("[ocr] extract failed for %s", (image_url or "")[:80])
        return None


def _detect_fabricated_pixels(
    ocr_text: str,
    fact_pack: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Scan OCR-extracted text for fabricated offers / URLs not traceable to
    the fact pack. Mirrors :func:`_detect_fabricated_facts` but operates on a
    single text blob (no template-field filtering)."""
    unmet: List[Dict[str, str]] = []
    text = (ocr_text or "").strip()
    if not text:
        return unmet

    quotes = fact_pack.get("requirement_quotes") or {}
    offer_quote = _norm(quotes.get("include_offer", ""))
    website_quote = _norm(quotes.get("include_website", ""))
    email_domain = _email_domain(fact_pack.get("business_email") or "")

    seen_offers: Set[str] = set()
    for pat in _OFFER_PATTERNS:
        for m in pat.finditer(text):
            matched = m.group(0)
            if not matched:
                continue
            allowed = bool(offer_quote) and _norm(matched) in offer_quote
            key = matched.lower()
            if not allowed and key not in seen_offers:
                seen_offers.add(key)
                unmet.append({
                    "code": "ocr_unverified_offer",
                    "fix": (
                        f"The recreated design contains '{matched}' which the user never stated. "
                        "Either confirm the exact offer wording with the user (then call "
                        "`note_design_requirement('include_offer', user_quote=<their words>)`) "
                        "and re-recreate, or re-recreate with the offer field empty."
                    ),
                })

    seen_urls: Set[str] = set()
    for pat in _URL_PATTERNS:
        for m in pat.finditer(text):
            url = m.group(0)
            if not url:
                continue
            url_norm = _norm(url)
            host = _url_host(url_norm)
            allowed_by_quote = bool(website_quote) and (
                url_norm in website_quote or (host and host in website_quote)
            )
            allowed_by_email = bool(email_domain) and email_domain in url_norm
            if not (allowed_by_quote or allowed_by_email) and url_norm not in seen_urls:
                seen_urls.add(url_norm)
                unmet.append({
                    "code": "ocr_unverified_url",
                    "fix": (
                        f"The recreated design contains URL '{url}' which the user never stated "
                        "and doesn't match the business email domain. Confirm the exact website "
                        "with the user (then call `note_design_requirement('include_website', "
                        "user_quote=<their URL>)`) and re-recreate, or re-recreate with the "
                        "website field empty."
                    ),
                })

    return unmet


@tool(
    name="recreate_design_with_ai",
    description=(
        "Recreate a marketing design from a chosen template layout in one step — combines "
        "product staging and final render. Pulls the locked template's preview as a layout "
        "reference (free), then uses the renderer to recreate the design while swapping all "
        "placeholder text for verified facts (business name, logo, brand colour, user-quoted "
        "headline/CTA/offer/website). Empty slots stay empty — never invents prices, "
        "addresses, URLs, or contact details. The brand logo is composited on top of the "
        "result so it's pixel-identical to the file. Use this for the **final design** in "
        "Phase 3 instead of staging + rendering separately."
    ),
    parameters={
        "type": "object",
        "required": ["template_id"],
        "properties": {
            "template_id": {
                "type": "string",
                "description": "The template_id locked in Phase 1c. Used as the layout reference (free preview fetch).",
            },
            "product_image_url": {
                "type": "string",
                "description": "Real product photo URL from `get_product_images`. Optional for non-product designs.",
            },
            "headline": {"type": "string"},
            "tagline": {"type": "string"},
            "cta": {"type": "string", "description": "Call-to-action button label (e.g. 'Shop Now')."},
            "offer": {
                "type": "string",
                "description": "Offer/discount wording — must match a `note_design_requirement('include_offer', user_quote=…)` you already recorded.",
            },
            "website": {
                "type": "string",
                "description": "Website/handle — must match a `note_design_requirement('include_website', user_quote=…)` you already recorded, or the business email domain on file.",
            },
            "extra_notes": {
                "type": "string",
                "description": "Optional extra direction for the renderer (e.g. 'leave the upper third clean for headline').",
            },
            "format": {
                "type": "string",
                "enum": ["square", "story", "landscape", "portrait"],
                "default": "square",
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "pro"],
                "default": "pro",
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
            "name": {"type": "string", "description": "Label for Design library (e.g. 'Spring drop — Final')."},
            "presentation_label": {"type": "string", "description": "Short echoed label e.g. 'Final', 'Option A'."},
        },
    },
)
async def recreate_design_with_ai(ctx: ToolContext, args: Dict[str, Any]):
    from orshot_service import get_studio_template
    from nano_banana_service import recreate_design_from_reference
    from .design_state import update_design_state

    tid = (args.get("template_id") or "").strip()
    if not tid:
        return {"error": "template_id is required — pass the locked template_id from Phase 1c."}

    headline = (args.get("headline") or "").strip()
    tagline = (args.get("tagline") or "").strip()
    cta = (args.get("cta") or "").strip()
    offer = (args.get("offer") or "").strip()
    website = (args.get("website") or "").strip()
    extra_notes = (args.get("extra_notes") or "").strip()
    product_image_url = (args.get("product_image_url") or "").strip() or None
    fmt = args.get("format", "square")
    quality = args.get("quality", "pro")
    platform = args.get("platform", "general")
    content_type = args.get("content_type", "general")
    pres = (args.get("presentation_label") or "").strip()
    name = (args.get("name") or pres or "AI design")[:200]

    fact_pack = await _build_design_fact_pack(ctx)

    # Pre-flight: scan the AI-supplied input args for fabricated offers/URLs
    # so we never burn a Gemini call when the inputs are obviously bad.
    business_email = fact_pack.get("business_email") or ""
    quotes = fact_pack.get("requirement_quotes") or {}
    pre_args_blob = {"headline": headline, "tagline": tagline, "cta": cta,
                     "offer": offer, "website": website}
    pre_unmet = _detect_fabricated_facts(pre_args_blob, quotes, business_email, None)
    if pre_unmet:
        logger.info("[recreate_design_with_ai] blocked pre-flight (codes=%s)",
                    [u["code"] for u in pre_unmet])
        return {
            "error": "recreate_blocked_by_requirements",
            "reason": "One or more inputs (offer / website) look fabricated — they don't match "
                      "any user quote on file. Fix each item below and retry.",
            "unmet": pre_unmet,
        }

    # Fetch template thumbnail (free GET) for use as layout reference.
    tpl = await get_studio_template(tid)
    if tpl.get("error"):
        return {"error": f"Could not load template preview: {tpl['error']}"}
    reference_url = tpl.get("thumbnail_url") or ""
    if not reference_url:
        return {"error": "Template has no thumbnail/preview to use as a layout reference."}
    template_name = tpl.get("name") or fact_pack.get("locked_template_name") or ""

    prompt = _compose_recreate_prompt(
        fact_pack,
        headline=headline, tagline=tagline, cta=cta,
        offer=offer, website=website, extra_notes=extra_notes,
    )

    result = await recreate_design_from_reference(
        reference_image_url=reference_url,
        prompt=prompt,
        product_image_url=product_image_url,
        logo_url=fact_pack.get("default_logo_url") or None,
        format=fmt,
        quality=quality,
    )
    if result.get("error"):
        return {"error": result["error"]}

    image_url = result.get("image_url") or ""
    if not image_url:
        return {"error": "Renderer returned no image URL."}

    # Composite the real brand logo on top so it's pixel-identical to the file.
    logo = fact_pack.get("default_logo_url") or ""
    if logo:
        try:
            composited = await _composite_logo_on_image(image_url, logo)
            if composited:
                logger.info("[recreate_design_with_ai] logo composited (tid=%s)", tid)
                image_url = composited
        except Exception:
            logger.exception("[recreate_design_with_ai] logo compositing skipped")

    # OCR fabrication check on the final pixels. Skipped silently when
    # pytesseract / Tesseract binary isn't available on this deployment.
    try:
        ocr_text = await _ocr_extract_text(image_url)
        if ocr_text is not None:
            ocr_unmet = _detect_fabricated_pixels(ocr_text, fact_pack)
            if ocr_unmet:
                logger.info("[recreate_design_with_ai] OCR flagged fabrication (codes=%s)",
                            [u["code"] for u in ocr_unmet])
                return {
                    "error": "recreate_blocked_by_pixel_fabrication",
                    "reason": "The renderer baked in text the user never stated. "
                              "Fix each item below and call recreate_design_with_ai again.",
                    "unmet": ocr_unmet,
                    "image_url": image_url,
                }
    except Exception:
        logger.exception("[recreate_design_with_ai] OCR check skipped")

    # Persist to design library.
    try:
        from saved_designs import insert_saved_design
        await insert_saved_design(
            ctx.db, ctx.business_id,
            name=name, asset_kind="image",
            file_url=image_url, thumbnail_url=image_url,
            source_tool="recreate_design_with_ai",
            conversation_id=ctx.user.get("_active_conversation_id"),
            platform=platform, content_type=content_type, format=fmt,
        )
    except Exception:
        logger.exception("[recreate_design_with_ai] saved_designs insert skipped")

    # Update design state. We set both staged_image_url and last_render_url
    # to the recreated design so the staging requirement is implicitly
    # satisfied (the product is in the design by construction) and the
    # next-turn prompt shows the AI exactly what was rendered.
    try:
        await update_design_state(
            ctx.db,
            ctx.user.get("_active_conversation_id"),
            ctx.business_id,
            locked_template_id=str(tid),
            locked_template_name=template_name or None,
            chosen_platform=(platform if platform and platform != "general" else None),
            chosen_format=(fmt if fmt and fmt != "general" else None),
            staged_image_url=image_url,
            last_render_url=image_url,
        )
    except Exception:
        logger.exception("[recreate_design_with_ai] design_state update skipped")

    return {
        "success": True,
        "template_id_used": str(tid),
        "image_url": image_url,
        "presentation_label": pres or None,
        "markdown": f"![{name}]({image_url})",
        "note": "Design produced via AI-recreate — staging + render combined. Logo composited deterministically.",
    }


# ── Design requirement tracking + pre-presentation verification ──────────────
# Allowed values for note_design_requirement / pending_requirements. Keep this
# list narrow on purpose — anything the deterministic guard cannot actually
# verify against modifications has no business being here.
_ALLOWED_DESIGN_REQUIREMENTS: Set[str] = {
    "include_logo",
    "use_brand_color",
    "use_brand_font",
    "stage_product",
    "include_cta",
    "include_headline",
    "include_price",
    "include_offer",
    "include_website",
}

# Requirements where the AI must pass `user_quote` (the user's verbatim wording).
# The fabrication scanner uses this to verify modification values weren't invented.
_REQUIREMENTS_NEEDING_QUOTE: Set[str] = {"include_offer", "include_website"}


def _norm(v: Any) -> str:
    """Lowercase a value for case-insensitive substring matching in modifications."""
    return str(v or "").lower()


async def _load_brand_kit(ctx: "ToolContext") -> Dict[str, str]:
    """Best-effort brand kit lookup shared by render guard and verify tool."""
    out = {"default_logo_url": "", "brand_primary_color": "", "brand_font": ""}
    try:
        from saved_designs import get_primary_logo_url, get_brand_settings

        out["default_logo_url"] = (await get_primary_logo_url(ctx.db, ctx.business_id)) or ""
        brand = await get_brand_settings(ctx.db, ctx.business_id)
        out["brand_primary_color"] = (brand or {}).get("brand_primary_color") or ""
        out["brand_font"]          = (brand or {}).get("brand_font") or ""
    except Exception:
        logger.exception("[design_guard] brand kit lookup failed")
    return out


async def _composite_logo_on_image(
    image_url: str,
    logo_url: str,
    *,
    position: str = "bottom-right",
    width_pct: float = 0.10,
    margin_pct: float = 0.04,
) -> Optional[str]:
    """Paste the brand logo onto a rendered design and upload the result.

    Used as a deterministic fallback when the locked Orshot template has no
    image field for the logo (or the AI didn't place it). Both inputs are
    fetched over HTTP; the composite is re-uploaded to this deployment's S3
    bucket via ``S3Handler.upload_file`` and the new presigned URL is returned.

    Returns ``None`` on any failure so the caller can fall back to the
    un-composited render — this helper must never break the render path.
    """
    if not image_url or not logo_url:
        return None
    try:
        import asyncio as _asyncio
        import base64 as _b64
        import io as _io
        import httpx as _httpx
        from PIL import Image as _Image
        from image_handler import S3Handler

        async with _httpx.AsyncClient(timeout=30.0) as client:
            r1 = await client.get(image_url)
            r1.raise_for_status()
            r2 = await client.get(logo_url)
            r2.raise_for_status()
            img_bytes = r1.content
            logo_bytes = r2.content

        def _do_composite() -> bytes:
            base = _Image.open(_io.BytesIO(img_bytes)).convert("RGBA")
            logo = _Image.open(_io.BytesIO(logo_bytes)).convert("RGBA")

            target_w = max(1, int(base.width * width_pct))
            ratio = target_w / max(1, logo.width)
            target_h = max(1, int(logo.height * ratio))
            logo = logo.resize((target_w, target_h), _Image.LANCZOS)

            margin = max(8, int(base.width * margin_pct))
            if position == "top-left":
                xy = (margin, margin)
            elif position == "top-right":
                xy = (base.width - logo.width - margin, margin)
            elif position == "bottom-left":
                xy = (margin, base.height - logo.height - margin)
            else:  # bottom-right (default)
                xy = (
                    base.width - logo.width - margin,
                    base.height - logo.height - margin,
                )

            base.alpha_composite(logo, dest=xy)

            buf = _io.BytesIO()
            base.convert("RGB").save(buf, format="PNG", optimize=True)
            return buf.getvalue()

        composed = await _asyncio.get_event_loop().run_in_executor(None, _do_composite)
        b64 = _b64.b64encode(composed).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"
        fn = f"orshot-logo-{uuid.uuid4()}.png"
        return await S3Handler.upload_file(data_url, fn)
    except Exception:
        logger.exception(
            "[_composite_logo_on_image] compositing failed (logo=%s)",
            (logo_url or "")[:80],
        )
        return None


def _image_fields(template_fields: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Return only the image-typed entries from a template's field list."""
    return [
        f for f in (template_fields or [])
        if isinstance(f, dict) and _norm(f.get("type")) == "image"
    ]


def _suggest_logo_field_key(image_fields: List[Dict[str, Any]]) -> Optional[str]:
    """Pick the field key most likely intended for a logo (key or help_text contains 'logo')."""
    for f in image_fields:
        if "logo" in _norm(f.get("key")) or "logo" in _norm(f.get("help_text")):
            return f.get("key")
    return image_fields[0].get("key") if image_fields else None


def _evaluate_design_requirements(
    pending: Set[str],
    mods: Dict[str, Any],
    brand: Dict[str, str],
    staged_image_url: str,
    template_fields: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """Run the deterministic checks. Returns a list of unmet items, each with
    a `code` and a human-readable `fix` string. Empty list = everything passes.

    The ``include_logo`` check only blocks when no default brand logo is
    configured at all — placement is handled deterministically by the
    post-render compositor (see ``_composite_logo_on_image``), so a missing
    logo field on the template or a logo absent from ``modifications`` is no
    longer a hard error. ``template_fields`` is still accepted for future
    template-aware checks but is no longer used for the logo branch.
    """
    unmet: List[Dict[str, str]] = []
    mod_blob = " ".join(_norm(v) for v in mods.values())

    if "include_logo" in pending:
        logo = brand.get("default_logo_url") or ""
        if not logo:
            unmet.append({
                "code": "logo_unavailable",
                "fix": "User asked for the logo, but no default brand logo is configured. "
                       "Tell them to add one in Settings → Brand or via the Design library, then retry.",
            })

    if "use_brand_color" in pending:
        color = brand.get("brand_primary_color") or ""
        if not color:
            unmet.append({
                "code": "brand_color_unavailable",
                "fix": "User asked for brand colour, but none is set. Ask them to set one in Settings → Brand.",
            })
        elif _norm(color) not in mod_blob:
            unmet.append({
                "code": "brand_color_not_applied",
                "fix": f"User asked for the brand colour ({color}). Place this hex value in the "
                       "template's colour/accent field, then re-render.",
            })

    if "use_brand_font" in pending:
        font = brand.get("brand_font") or ""
        if not font:
            unmet.append({
                "code": "brand_font_unavailable",
                "fix": "User asked for brand font, but none is set in Settings → Brand.",
            })
        elif _norm(font) not in mod_blob:
            unmet.append({
                "code": "brand_font_not_applied",
                "fix": f"User asked for brand font '{font}'. Place this in the template's font field, then re-render.",
            })

    if "stage_product" in pending and not staged_image_url:
        unmet.append({
            "code": "staging_skipped",
            "fix": "User asked for the product to be designed/staged, but staging was skipped. "
                   "Call generate_design_background with the product_image_url first, then re-render "
                   "using the returned background_url in the template's image field.",
        })

    # Copy presence checks — modifications must contain *some* non-empty value
    # under a key that looks like the relevant field. We don't enforce content,
    # only presence, because the AI/user picks the actual wording.
    def _has_field_match(needles: List[str]) -> bool:
        for k, v in mods.items():
            if not _norm(v):
                continue
            kl = _norm(k)
            if any(n in kl for n in needles):
                return True
        return False

    if "include_headline" in pending and not _has_field_match(["headline", "title", "heading"]):
        unmet.append({
            "code": "headline_missing",
            "fix": "User asked for a headline. Add a non-empty value to the template's headline/title field and re-render.",
        })
    if "include_cta" in pending and not _has_field_match(["cta", "button", "action"]):
        unmet.append({
            "code": "cta_missing",
            "fix": "User asked for a CTA. Add a non-empty value to the template's CTA/button field and re-render.",
        })
    if "include_price" in pending and not _has_field_match(["price", "offer", "discount"]):
        unmet.append({
            "code": "price_missing",
            "fix": "User asked for a price/offer. Add it to the template's price/offer field and re-render.",
        })

    return unmet


# ── Anti-fabrication scanner ─────────────────────────────────────────────────
# Detects discount/offer-shaped values and URLs in modifications that the AI
# may have invented. Runs on every render regardless of `pending_requirements`.
# Allow-list path: the AI must call note_design_requirement('include_offer'
# or 'include_website', user_quote=<user's verbatim words>) so the scanner can
# verify the modification value matches what the user actually said. URLs are
# also allowed when they match the business email's domain (real fact on file).

_OFFER_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b\d{1,3}\s*%(?:\s*(?:off|discount))?\b", re.IGNORECASE),
    re.compile(r"\bsave\s+(?:up\s+to\s+)?\$?\d", re.IGNORECASE),
    re.compile(r"\$\s?\d+(?:\.\d+)?\s*(?:off|discount)\b", re.IGNORECASE),
    re.compile(r"\bbuy\s+\d+\s+get\s+\d+", re.IGNORECASE),
    re.compile(r"\bfree\s+shipping\b", re.IGNORECASE),
    re.compile(r"\blimited\s+time\b", re.IGNORECASE),
    re.compile(r"\bflash\s+sale\b", re.IGNORECASE),
]

_URL_PATTERNS: List[re.Pattern] = [
    re.compile(r"https?://[^\s)]+", re.IGNORECASE),
    re.compile(r"\bwww\.[a-z0-9-]+\.[a-z]{2,}\b", re.IGNORECASE),
    re.compile(
        r"\b[a-z0-9][a-z0-9-]{1,62}\.(?:com|co|shop|io|net|org|app|store|biz|us|uk|in|me|dev|ai)\b",
        re.IGNORECASE,
    ),
]


def _email_domain(email: str) -> str:
    e = (email or "").strip().lower()
    if "@" not in e:
        return ""
    return e.split("@", 1)[1].split(">", 1)[0].strip()


def _url_host(url_norm: str) -> str:
    s = url_norm.strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s


async def _load_business_email(ctx: "ToolContext") -> str:
    """Best-effort owner email lookup so the scanner can allow-list URLs that
    match the business's real email domain."""
    try:
        u = await ctx.db.users.find_one(
            {"_id": ctx.business_id},
            {"email": 1, "_id": 0},
        )
        return ((u or {}).get("email") or "").strip()
    except Exception:
        logger.exception("[design_guard] business email lookup failed")
        return ""


def _detect_fabricated_facts(
    mods: Dict[str, Any],
    requirement_quotes: Dict[str, str],
    business_email: str = "",
    template_fields: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """Scan modification values for invented discounts/offers and URLs.

    Skips dot-notation style overrides (e.g. ``headline.color``) and
    image-typed template fields (logos / product shots are expected to contain
    URLs). Returns a list of ``{code, fix}`` entries; empty list = nothing to
    flag.
    """
    unmet: List[Dict[str, str]] = []
    if not isinstance(mods, dict) or not mods:
        return unmet

    image_keys: Set[str] = set()
    for f in (template_fields or []):
        if isinstance(f, dict) and _norm(f.get("type")) == "image":
            k = f.get("key")
            if k:
                image_keys.add(str(k))

    quotes = requirement_quotes or {}
    offer_quote = _norm(quotes.get("include_offer", ""))
    website_quote = _norm(quotes.get("include_website", ""))
    email_domain = _email_domain(business_email)

    seen_offers: Set[str] = set()
    seen_urls: Set[str] = set()

    for raw_key, raw_val in mods.items():
        key_str = str(raw_key)
        if "." in key_str:
            continue
        if key_str in image_keys:
            continue
        text = str(raw_val or "").strip()
        if not text:
            continue

        for pat in _OFFER_PATTERNS:
            m = pat.search(text)
            if not m:
                continue
            matched = m.group(0)
            allowed = bool(offer_quote) and _norm(matched) in offer_quote
            if not allowed and matched.lower() not in seen_offers:
                seen_offers.add(matched.lower())
                unmet.append({
                    "code": "unverified_offer_claim",
                    "fix": (
                        f"Field `{key_str}` contains '{matched}' which looks like an offer/discount the "
                        "user never explicitly stated. Either ask the user for the exact wording and "
                        "call `note_design_requirement('include_offer', user_quote=<their exact words>)` "
                        "first, or remove this field from `modifications` entirely. Do NOT retry with the "
                        "same fabricated claim."
                    ),
                })
            break

        for pat in _URL_PATTERNS:
            m = pat.search(text)
            if not m:
                continue
            url = m.group(0)
            url_norm = _norm(url)
            host = _url_host(url_norm)
            allowed_by_quote = bool(website_quote) and (
                url_norm in website_quote or (host and host in website_quote)
            )
            allowed_by_email = bool(email_domain) and email_domain in url_norm
            if not (allowed_by_quote or allowed_by_email) and url_norm not in seen_urls:
                seen_urls.add(url_norm)
                unmet.append({
                    "code": "unverified_url_claim",
                    "fix": (
                        f"Field `{key_str}` contains URL/website '{url}' which the user never stated and "
                        "doesn't match the business email domain on file. Either ask the user for their "
                        "exact website/handle and call `note_design_requirement('include_website', "
                        "user_quote=<their URL>)` first, or remove this field from `modifications`. "
                        "Do NOT retry with a fabricated URL."
                    ),
                })
            break

    return unmet


@tool(
    name="note_design_requirement",
    description=(
        "Record a design requirement the user has explicitly stated this turn so the "
        "server can verify it before any design is presented as final. Call this "
        "**immediately** when the user says things like 'include my logo', 'use my "
        "brand colours', 'design this product photo', 'add a CTA button', "
        "'show the price', 'mention 20% off', 'add my website'. The pre-render guard "
        "and `verify_design_ready` will block / flag any final design that doesn't "
        "satisfy these. Allowed `requirement` values: `include_logo`, `use_brand_color`, "
        "`use_brand_font`, `stage_product`, `include_cta`, `include_headline`, "
        "`include_price`, `include_offer`, `include_website`. "
        "**For `include_offer` and `include_website` you MUST pass `user_quote` "
        "containing the user's verbatim wording** (e.g. `user_quote='20% off until "
        "Friday'` or `user_quote='zilo.shop'`) — the anti-fabrication scanner uses it "
        "to verify the modification value matches what the user actually said."
    ),
    parameters={
        "type": "object",
        "properties": {
            "requirement": {
                "type": "string",
                "enum": sorted(_ALLOWED_DESIGN_REQUIREMENTS),
                "description": "The requirement code to record.",
            },
            "user_quote": {
                "type": "string",
                "description": (
                    "The user's verbatim wording for this requirement. Required for "
                    "`include_offer` and `include_website` (the scanner verifies the "
                    "modification value contains this quote). Optional but recommended "
                    "for other requirements as an audit trail."
                ),
            },
        },
        "required": ["requirement"],
    },
    destructive=False,
)
async def note_design_requirement(ctx: ToolContext, args: Dict[str, Any]):
    req = (args.get("requirement") or "").strip()
    if req not in _ALLOWED_DESIGN_REQUIREMENTS:
        return {
            "error": "unknown_requirement",
            "allowed": sorted(_ALLOWED_DESIGN_REQUIREMENTS),
        }

    quote = (args.get("user_quote") or "").strip()[:200]
    if req in _REQUIREMENTS_NEEDING_QUOTE and not quote:
        return {
            "error": "user_quote_required",
            "fix": (
                f"`{req}` requires `user_quote` containing the user's verbatim wording "
                "so the anti-fabrication scanner can verify the modification value "
                "matches what they actually said. Re-call this tool with `user_quote` set."
            ),
        }

    conv_id = ctx.user.get("_active_conversation_id")
    if not conv_id:
        return {"error": "No active conversation_id — requirement not persisted."}

    from .design_state import update_design_state

    update_kwargs: Dict[str, Any] = {"add_pending_requirements": [req]}
    if quote:
        # Persist as a nested field (`requirement_quotes.<req>`) so each requirement
        # keeps its own verbatim audit trail. update_design_state forwards arbitrary
        # `**fields` kwargs into a Mongo `$set`, and dotted keys are valid there.
        update_kwargs[f"requirement_quotes.{req}"] = quote

    try:
        await update_design_state(
            ctx.db,
            conv_id,
            ctx.business_id,
            **update_kwargs,
        )
    except Exception:
        logger.exception("[note_design_requirement] persist failed")
        return {"error": "persist_failed"}

    return {
        "success": True,
        "recorded": req,
        "user_quote": quote,
        "note": "This requirement will be verified by the render-time guard and `verify_design_ready`.",
    }


@tool(
    name="verify_design_ready",
    description=(
        "Run the deterministic pre-presentation check on the latest render. Returns "
        "`ready=true` when every recorded requirement (logo, brand colour, staging, "
        "headline, CTA, price) is satisfied by the most recent `render_orshot_template` "
        "call's `modifications`. Returns `ready=false` with `unmet` (list of "
        "`{code, fix}`) when something is missing — follow each `fix` exactly, "
        "re-render, then call this tool again. **Always call this before telling "
        "the user a design is final, ready, or done.**"
    ),
    parameters={"type": "object", "properties": {}},
    destructive=False,
)
async def verify_design_ready(ctx: ToolContext, args: Dict[str, Any]):
    conv_id = ctx.user.get("_active_conversation_id")
    if not conv_id:
        return {"ready": False, "error": "No active conversation_id."}

    from .design_state import load_design_state, update_design_state

    state = await load_design_state(ctx.db, conv_id, ctx.business_id)
    pending = set(state.get("pending_requirements") or [])
    quotes = state.get("requirement_quotes") or {}
    last_mods = state.get("last_render_modifications") or {}
    last_render_url = state.get("last_render_url") or ""
    staged_url = state.get("staged_image_url") or ""
    template_fields = state.get("locked_template_fields") or None

    if not last_render_url:
        return {
            "ready": False,
            "unmet": [{
                "code": "no_render",
                "fix": "No design has been rendered yet for this conversation. Walk through "
                       "Phase 2 (generate_design_background) and Phase 3 (render_orshot_template) first.",
            }],
            "checked": {"pending_requirements": sorted(pending)},
        }

    business_email = await _load_business_email(ctx)
    brand = await _load_brand_kit(ctx) if pending else {}

    unmet: List[Dict[str, str]] = []
    if pending:
        unmet.extend(_evaluate_design_requirements(
            pending, last_mods, brand, staged_url, template_fields,
        ))
    # Anti-fabrication scanner runs unconditionally so we never finalise a design
    # with an invented discount or URL — even when no requirements were recorded.
    unmet.extend(_detect_fabricated_facts(
        last_mods, quotes, business_email, template_fields,
    ))

    async def _mark_done() -> None:
        try:
            await update_design_state(
                ctx.db, conv_id, ctx.business_id, flow_step="done"
            )
        except Exception:
            logger.exception("[verify_design_ready] flow_step update skipped")

    if not pending and not unmet:
        await _mark_done()
        return {
            "ready": True,
            "unmet": [],
            "checked": {
                "pending_requirements": [],
                "has_last_render": True,
                "has_staged_image": bool(staged_url),
            },
            "note": "No explicit requirements were recorded for this conversation. "
                    "If the user mentioned logo / brand colour / specific copy, call "
                    "`note_design_requirement` first, then verify again.",
        }

    is_ready = len(unmet) == 0
    if is_ready:
        await _mark_done()

    return {
        "ready": is_ready,
        "unmet": unmet,
        "checked": {
            "pending_requirements": sorted(pending),
            "modification_keys": sorted(last_mods.keys()),
            "has_logo_in_brand_kit": bool(brand.get("default_logo_url")),
            "has_brand_color":       bool(brand.get("brand_primary_color")),
            "has_brand_font":        bool(brand.get("brand_font")),
            "has_staged_image":      bool(staged_url),
            "has_image_field_in_template": bool(_image_fields(template_fields)),
            "last_render_url":       last_render_url,
        },
    }






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
    from .design_state import update_design_state

    import random as _random
    _BG_STYLES = ["bold", "minimal", "editorial", "luxury", "vibrant"]

    concept           = args.get("concept", "")
    product_image_url = args.get("product_image_url")
    style             = args.get("style") or _random.choice(_BG_STYLES)
    fmt               = args.get("format", "square")
    logo_url          = args.get("logo_url")
    quality           = args.get("quality", "fast")

    async def _persist(bg_url: str) -> None:
        try:
            from .design_state import load_design_state
            conv_id = ctx.user.get("_active_conversation_id")
            if conv_id:
                existing = await load_design_state(ctx.db, conv_id, ctx.business_id)
                current_step = existing.get("flow_step") or ""
                # Only advance to awaiting_greenlight if copy has already been approved
                # (i.e. we are coming from awaiting_greenlight itself during a re-stage,
                # or from awaiting_copy_approval after copy was agreed). Never skip
                # copy-approval by jumping here from an earlier step.
                advance = current_step in ("awaiting_copy_approval", "awaiting_greenlight", "refining")
            else:
                advance = False
            await update_design_state(
                ctx.db,
                conv_id or ctx.user.get("_active_conversation_id"),
                ctx.business_id,
                staged_image_url=bg_url,
                staged_concept=(concept or None),
                staged_style=(style or None),
                staged_format=(fmt or None),
                **({"flow_step": "awaiting_greenlight"} if advance else {}),
            )
        except Exception:
            logger.exception("[generate_design_background] design_state update skipped")

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
            await _persist(bg_url)
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
        await _persist(product_image_url)
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
    await _persist(bg_url)
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

    # Fetch document style profile for branded output
    doc_style: Dict[str, Any] = {}
    try:
        from saved_designs import get_document_style as _get_doc_style
        doc_style = await _get_doc_style(ctx.db, ctx.business_id) or {}
    except Exception:
        pass

    md = f"# {title}\n\n{content}"
    preview_key: str | None = None
    html_preview: str | None = None
    try:
        from .document_generator import generate_html_document, generate_pdf_from_html, store_html_preview
        html_preview = generate_html_document(md, title=title, business_name=business_name, style=doc_style)
        preview_key = store_html_preview(html_preview)
        filepath = await asyncio.get_event_loop().run_in_executor(
            None, generate_pdf_from_html, html_preview, None
        )
    except Exception as e:
        logger.exception("[create_business_document] PDF generation failed")
        return {"error": f"PDF generation failed: {e}"}

    try:
        from pathlib import Path as _Path
        from image_handler import S3Handler
        _filepath = _Path(filepath) if isinstance(filepath, str) else filepath
        pdf_bytes = _filepath.read_bytes()
        b64 = base64.b64encode(pdf_bytes).decode()
        filename = f"doc-{_uuid.uuid4().hex[:8]}.pdf"
        pdf_url = await S3Handler.upload_file(b64, filename, content_type="application/pdf")
    except Exception as e:
        logger.exception("[create_business_document] S3 upload failed")
        return {"error": f"PDF upload failed: {e}"}
    finally:
        try:
            _filepath = _Path(filepath) if isinstance(filepath, str) else filepath
            _filepath.unlink(missing_ok=True)
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
        "download_url": pdf_url,
        "filename": f"{title}.pdf",
        "html_preview": html_preview or "",   # Stripped from LLM context by orchestrator
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
    from presentation_service import generate_presentation_with_upload
    title = args.get("title", "Presentation")
    slides_data = args.get("slides_data", [])

    owner = await ctx.db.users.find_one({"_id": ctx.business_id})
    business_name = owner.get("business_name") or owner.get("owner_name") or "My Business" if owner else "My Business"

    # Fetch document style for branded output
    doc_style: Dict[str, Any] = {}
    try:
        from saved_designs import get_document_style as _get_doc_style
        doc_style = await _get_doc_style(ctx.db, ctx.business_id) or {}
    except Exception:
        pass

    result = await generate_presentation_with_upload(title, slides_data, business_name, doc_style)

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



# ── Email helpers ─────────────────────────────────────────────────────────────

import base64
import os as _os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_GMAIL_KEY     = _os.getenv("NEXT_PUBLIC_NANGO_ID_EMAIL",     "google-mail")
_MICROSOFT_KEY = _os.getenv("NEXT_PUBLIC_NANGO_ID_MICROSOFT", "microsoft")


def _gmail_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _gmail_decode_part(payload: dict, prefer: str = "text/plain") -> str:
    body_data = (payload.get("body") or {}).get("data", "")
    if body_data and payload.get("mimeType", "") == prefer:
        try:
            return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        except Exception:
            return ""
    for part in payload.get("parts") or []:
        text = _gmail_decode_part(part, prefer)
        if text:
            return text
    if prefer == "text/plain":
        return _gmail_decode_part(payload, "text/html")
    return ""


def _gmail_build_raw(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    in_reply_to: str = "",
    references: str = "",
) -> str:
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _email_trunc(text: str, n: int = 3000) -> str:
    return text[:n] + ("..." if len(text) > n else "")


# ── Gmail tools ───────────────────────────────────────────────────────────────

@tool(
    name="gmail_list_threads",
    description=(
        "List Gmail inbox threads. Supports search queries like "
        "'from:someone@email.com', 'is:unread', 'subject:invoice'. "
        "Returns thread summaries: id, subject, snippet, sender, date, unread flag."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query":       {"type": "string", "description": "Gmail search query. Default: 'in:inbox'"},
            "max_results": {"type": "integer", "description": "Max threads (1-50, default 15)"},
            "unread_only": {"type": "boolean", "description": "Add 'is:unread' to query if true"},
        },
    },
)
async def gmail_list_threads(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    q = (args.get("query") or "in:inbox").strip()
    if args.get("unread_only"):
        q = "is:unread " + q
    limit = min(int(args.get("max_results") or 15), 50)
    try:
        data = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "GET",
            "gmail/v1/users/me/threads",
            params={"q": q, "maxResults": limit},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    threads = []
    for t in (data.get("threads") or [])[:limit]:
        try:
            td = await nango_proxy(
                ctx.business_id, _GMAIL_KEY, "GET",
                f"gmail/v1/users/me/threads/{t['id']}",
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            msgs = td.get("messages") or []
            if not msgs:
                continue
            first = msgs[0]
            hdrs = (first.get("payload") or {}).get("headers") or []
            threads.append({
                "thread_id":     t["id"],
                "message_count": len(msgs),
                "subject":       _gmail_header(hdrs, "Subject") or "(no subject)",
                "from":          _gmail_header(hdrs, "From"),
                "date":          _gmail_header(hdrs, "Date"),
                "snippet":       _email_trunc(td.get("snippet") or "", 200),
                "unread":        "UNREAD" in (first.get("labelIds") or []),
            })
        except Exception:
            continue
    return {"threads": threads, "total": len(threads), "query": q}


@tool(
    name="gmail_read_thread",
    description=(
        "Read a full Gmail thread by thread_id. Returns all messages "
        "with decoded body, sender, date, and subject."
    ),
    parameters={
        "type": "object",
        "properties": {
            "thread_id": {"type": "string", "description": "Gmail thread ID"},
        },
        "required": ["thread_id"],
    },
)
async def gmail_read_thread(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    thread_id = (args.get("thread_id") or "").strip()
    if not thread_id:
        return {"error": "thread_id is required"}
    try:
        data = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "GET",
            f"gmail/v1/users/me/threads/{thread_id}",
            params={"format": "full"},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    messages = []
    for msg in data.get("messages") or []:
        payload = msg.get("payload") or {}
        hdrs = payload.get("headers") or []
        messages.append({
            "message_id":         msg["id"],
            "from":               _gmail_header(hdrs, "From"),
            "to":                 _gmail_header(hdrs, "To"),
            "subject":            _gmail_header(hdrs, "Subject"),
            "date":               _gmail_header(hdrs, "Date"),
            "message_id_header":  _gmail_header(hdrs, "Message-ID"),
            "references":         _gmail_header(hdrs, "References"),
            "body":               _email_trunc(_gmail_decode_part(payload), 4000),
            "unread":             "UNREAD" in (msg.get("labelIds") or []),
        })
    return {"thread_id": thread_id, "message_count": len(messages), "messages": messages}


@tool(
    name="gmail_send",
    description="Send a new email via Gmail. Requires to, subject, and body. cc and bcc are optional.",
    parameters={
        "type": "object",
        "properties": {
            "to":      {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Subject line"},
            "body":    {"type": "string", "description": "Plain text email body"},
            "cc":      {"type": "string"},
            "bcc":     {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    destructive=True,
)
async def gmail_send(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject or not body:
        return {"error": "to, subject, and body are required"}
    raw = _gmail_build_raw(to, subject, body, cc=args.get("cc") or "", bcc=args.get("bcc") or "")
    try:
        result = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "POST",
            "gmail/v1/users/me/messages/send",
            json={"raw": raw},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "sent", "message_id": result.get("id"), "thread_id": result.get("threadId")}


@tool(
    name="gmail_reply",
    description=(
        "Reply to an existing Gmail thread. Automatically threads correctly. "
        "Set reply_all=true to include all original recipients."
    ),
    parameters={
        "type": "object",
        "properties": {
            "thread_id": {"type": "string", "description": "Gmail thread ID to reply to"},
            "body":      {"type": "string", "description": "Reply body text"},
            "reply_all": {"type": "boolean", "description": "Reply all. Default false."},
        },
        "required": ["thread_id", "body"],
    },
    destructive=True,
)
async def gmail_reply(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    thread_id = (args.get("thread_id") or "").strip()
    body = (args.get("body") or "").strip()
    if not thread_id or not body:
        return {"error": "thread_id and body are required"}
    try:
        td = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "GET",
            f"gmail/v1/users/me/threads/{thread_id}",
            params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Message-ID", "References"]},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    msgs = td.get("messages") or []
    if not msgs:
        return {"error": "Thread not found or empty"}
    last = msgs[-1]
    hdrs = (last.get("payload") or {}).get("headers") or []
    orig_from   = _gmail_header(hdrs, "From")
    orig_to     = _gmail_header(hdrs, "To")
    subject     = _gmail_header(hdrs, "Subject")
    msg_id_hdr  = _gmail_header(hdrs, "Message-ID")
    existing_refs = _gmail_header(hdrs, "References")
    reply_to = orig_from
    if args.get("reply_all") and orig_to:
        reply_to = f"{orig_from}, {orig_to}"
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    refs = (existing_refs + " " + msg_id_hdr).strip() if existing_refs else msg_id_hdr
    raw = _gmail_build_raw(reply_to, subject, body, in_reply_to=msg_id_hdr, references=refs)
    try:
        result = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "POST",
            "gmail/v1/users/me/messages/send",
            json={"raw": raw, "threadId": thread_id},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "sent", "message_id": result.get("id"), "thread_id": result.get("threadId")}


@tool(
    name="gmail_draft",
    description="Save a Gmail draft without sending. Returns the draft ID.",
    parameters={
        "type": "object",
        "properties": {
            "to":      {"type": "string"},
            "subject": {"type": "string"},
            "body":    {"type": "string"},
            "cc":      {"type": "string"},
            "bcc":     {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
)
async def gmail_draft(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject or not body:
        return {"error": "to, subject, and body are required"}
    raw = _gmail_build_raw(to, subject, body, cc=args.get("cc") or "", bcc=args.get("bcc") or "")
    try:
        result = await nango_proxy(
            ctx.business_id, _GMAIL_KEY, "POST",
            "gmail/v1/users/me/drafts",
            json={"message": {"raw": raw}},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "draft_saved", "draft_id": result.get("id")}


# ── Outlook / Microsoft 365 tools ─────────────────────────────────────────────

_OUTLOOK_SELECT      = "id,subject,from,toRecipients,ccRecipients,bodyPreview,receivedDateTime,isRead,conversationId,internetMessageId"
_OUTLOOK_FULL_SELECT = "id,subject,from,toRecipients,ccRecipients,body,receivedDateTime,isRead,conversationId,internetMessageId"


def _ms_addr_list(val: str) -> list:
    return [{"emailAddress": {"address": a.strip()}} for a in (val or "").split(",") if a.strip()]


@tool(
    name="outlook_list_messages",
    description=(
        "List Outlook / Microsoft 365 inbox messages. "
        "Filter by folder, unread status, or search term. "
        "Returns: id, subject, from, preview, date, read status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "folder":      {"type": "string", "description": "inbox (default), sentItems, drafts, deletedItems"},
            "search":      {"type": "string", "description": "Search subject or body"},
            "unread_only": {"type": "boolean"},
            "max_results": {"type": "integer", "description": "1-50, default 15"},
        },
    },
)
async def outlook_list_messages(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    folder = (args.get("folder") or "inbox").strip()
    limit  = min(int(args.get("max_results") or 15), 50)
    params: Dict[str, Any] = {
        "$top":     limit,
        "$select":  _OUTLOOK_SELECT,
        "$orderby": "receivedDateTime desc",
    }
    if args.get("unread_only"):
        params["$filter"] = "isRead eq false"
    if args.get("search"):
        params["$search"] = f'"{args["search"]}"'
    try:
        data = await nango_proxy(
            ctx.business_id, _MICROSOFT_KEY, "GET",
            f"v1.0/me/mailFolders/{folder}/messages",
            params=params,
        )
    except RuntimeError as e:
        return {"error": str(e)}
    messages = []
    for m in (data.get("value") or []):
        sender = (m.get("from") or {}).get("emailAddress") or {}
        messages.append({
            "message_id":    m.get("id"),
            "subject":       m.get("subject") or "(no subject)",
            "from_name":     sender.get("name"),
            "from_email":    sender.get("address"),
            "preview":       _email_trunc(m.get("bodyPreview") or "", 200),
            "date":          m.get("receivedDateTime"),
            "is_read":       m.get("isRead", True),
            "conversation_id": m.get("conversationId"),
        })
    return {"messages": messages, "total": len(messages)}


@tool(
    name="outlook_read_message",
    description="Read the full body and details of an Outlook message by message_id.",
    parameters={
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "Outlook message ID"},
        },
        "required": ["message_id"],
    },
)
async def outlook_read_message(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    msg_id = (args.get("message_id") or "").strip()
    if not msg_id:
        return {"error": "message_id is required"}
    try:
        m = await nango_proxy(
            ctx.business_id, _MICROSOFT_KEY, "GET",
            f"v1.0/me/messages/{msg_id}",
            params={"$select": _OUTLOOK_FULL_SELECT},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    sender = (m.get("from") or {}).get("emailAddress") or {}
    to_list = [(r.get("emailAddress") or {}).get("address") for r in (m.get("toRecipients") or [])]
    body_content = _email_trunc((m.get("body") or {}).get("content") or m.get("bodyPreview") or "", 4000)
    return {
        "message_id":    m.get("id"),
        "subject":       m.get("subject") or "(no subject)",
        "from_name":     sender.get("name"),
        "from_email":    sender.get("address"),
        "to":            ", ".join(filter(None, to_list)),
        "date":          m.get("receivedDateTime"),
        "is_read":       m.get("isRead", True),
        "body":          body_content,
        "internet_message_id": m.get("internetMessageId"),
        "conversation_id": m.get("conversationId"),
    }


@tool(
    name="outlook_send",
    description="Send a new email via Outlook / Microsoft 365. to, subject, body required. cc and bcc optional.",
    parameters={
        "type": "object",
        "properties": {
            "to":      {"type": "string", "description": "Recipient(s), comma-separated"},
            "subject": {"type": "string"},
            "body":    {"type": "string", "description": "Plain text body"},
            "cc":      {"type": "string"},
            "bcc":     {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    destructive=True,
)
async def outlook_send(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject or not body:
        return {"error": "to, subject, and body are required"}
    payload: Dict[str, Any] = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": _ms_addr_list(to),
        },
        "saveToSentItems": True,
    }
    if args.get("cc"):
        payload["message"]["ccRecipients"] = _ms_addr_list(args["cc"])
    if args.get("bcc"):
        payload["message"]["bccRecipients"] = _ms_addr_list(args["bcc"])
    try:
        await nango_proxy(ctx.business_id, _MICROSOFT_KEY, "POST", "v1.0/me/sendMail", json=payload)
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "sent"}


@tool(
    name="outlook_reply",
    description="Reply to an Outlook message. Set reply_all=true to reply to all recipients.",
    parameters={
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "Outlook message ID to reply to"},
            "body":       {"type": "string", "description": "Reply body text"},
            "reply_all":  {"type": "boolean", "description": "Reply all. Default false."},
        },
        "required": ["message_id", "body"],
    },
    destructive=True,
)
async def outlook_reply(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    msg_id    = (args.get("message_id") or "").strip()
    body      = (args.get("body") or "").strip()
    reply_all = bool(args.get("reply_all"))
    if not msg_id or not body:
        return {"error": "message_id and body are required"}
    endpoint = f"v1.0/me/messages/{msg_id}/{'replyAll' if reply_all else 'reply'}"
    try:
        await nango_proxy(ctx.business_id, _MICROSOFT_KEY, "POST", endpoint, json={"comment": body})
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "replied"}


@tool(
    name="web_search",
    description=(
        "Search the web for real-time information, news, market data, prices, competitor info, "
        "industry trends, regulations, or any topic not available in the CRM. "
        "Use whenever the user's question requires up-to-date external knowledge. "
        "Returns a list of results with title, url, and a short snippet."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query — be specific and targeted.",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10).",
            },
        },
        "required": ["query"],
    },
)
async def web_search(ctx: ToolContext, args: Dict[str, Any]):
    import os, httpx
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    max_results = min(int(args.get("max_results") or 5), 10)

    tavily_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    tavily_error: str = ""
    if tavily_key:
        # Tavily — purpose-built for AI agents, returns clean snippets
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                        "include_answer": True,
                    },
                )
                if resp.status_code != 200:
                    tavily_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                    logger.warning("[web_search] Tavily error %s — falling back to DuckDuckGo", tavily_error)
                else:
                    data = resp.json()
                    results = [
                        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                        for r in (data.get("results") or [])
                    ]
                    return {
                        "query": query,
                        "answer": data.get("answer") or "",
                        "results": results[:max_results],
                        "source": "tavily",
                    }
        except httpx.TimeoutException as e:
            tavily_error = f"Timeout connecting to Tavily: {e}"
            logger.warning("[web_search] %s — falling back to DuckDuckGo", tavily_error)
        except httpx.ConnectError as e:
            tavily_error = f"Connection error reaching Tavily: {e}"
            logger.warning("[web_search] %s — falling back to DuckDuckGo", tavily_error)
        except Exception as e:
            tavily_error = str(e)
            logger.warning("[web_search] Tavily failed: %s — falling back to DuckDuckGo", tavily_error)

    # DuckDuckGo full search — no key required, uses duckduckgo-search package
    try:
        from duckduckgo_search import AsyncDDGS
        async with AsyncDDGS() as ddgs:
            raw = await ddgs.text(query, max_results=max_results)
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in (raw or [])
        ]
        if results:
            return {
                "query": query,
                "answer": "",
                "results": results[:max_results],
                "source": "duckduckgo",
            }
        logger.warning("[web_search] DuckDuckGo returned no results for: %s", query)
    except Exception as e:
        logger.warning("[web_search] DuckDuckGo search failed: %s — trying instant answer", e)

    # DuckDuckGo Instant Answer API — last resort
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                headers={"User-Agent": "ZiloAI/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("Heading", query),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data["AbstractText"],
                })
            for topic in (data.get("RelatedTopics") or [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("Text", "")[:80],
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", ""),
                    })
            if results:
                return {
                    "query": query,
                    "answer": data.get("AbstractText") or "",
                    "results": results[:max_results],
                    "source": "duckduckgo",
                }
    except Exception as e:
        logger.error("[web_search] All fallbacks failed: %s", e)

    return {
        "query": query,
        "answer": "",
        "results": [],
        "source": "none",
        "note": "No results found. Set TAVILY_API_KEY in your deployment environment for reliable web search.",
        "tavily_error": tavily_error or None,
    }


@tool(
    name="get_document_style",
    description=(
        "Retrieve the business's Document Style Profile from the brand library. "
        "Call this at the start of every document creation task to apply the owner's preferred tone, "
        "signature, header/footer, colors, and standing instructions automatically."
    ),
    parameters={"type": "object", "properties": {}},
    destructive=False,
)
async def get_document_style(ctx: ToolContext, args: Dict[str, Any]):
    from saved_designs import get_document_style as _get
    profile = await _get(ctx.db, ctx.business_id)
    has_any = any(v for v in profile.values())
    return {"has_profile": has_any, "profile": profile}


@tool(
    name="save_document_style",
    description=(
        "Save or update the business's Document Style Profile in the brand library. "
        "Use this when the user explicitly defines how they want documents to look or sound — "
        "tone, signature, header/footer text, colors, logo placement, standing instructions, etc. "
        "Only pass fields the user actually specified; omit others."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tone":                 {"type": "string", "description": "e.g. formal, conversational, bold, friendly"},
            "font_style":           {"type": "string", "description": "e.g. serif, sans-serif, modern, classic"},
            "primary_color":        {"type": "string", "description": "Hex color e.g. #1E3A5F"},
            "secondary_color":      {"type": "string", "description": "Hex color e.g. #F5A623"},
            "logo_placement":       {"type": "string", "description": "top-left | top-center | top-right | none"},
            "header_text":          {"type": "string", "description": "Standing header line or company tagline"},
            "footer_text":          {"type": "string", "description": "Disclaimer, copyright, or standing footer"},
            "signature_name":       {"type": "string", "description": "Sign-off name e.g. James Kariuki"},
            "signature_title":      {"type": "string", "description": "e.g. Chief Executive Officer"},
            "signature_contact":    {"type": "string", "description": "e.g. james@company.co.ke | +254 712 345 678"},
            "date_format":          {"type": "string", "description": "e.g. DD Month YYYY"},
            "currency":             {"type": "string", "description": "e.g. KES, USD, EUR"},
            "standing_instructions":{"type": "string", "description": "Any standing writing rules e.g. always include payment terms"},
        },
    },
    destructive=False,
)
async def save_document_style(ctx: ToolContext, args: Dict[str, Any]):
    from saved_designs import upsert_document_style as _upsert
    updated = await _upsert(ctx.db, ctx.business_id, args)
    saved_fields = [k for k, v in updated.items() if v]
    return {"status": "saved", "saved_fields": saved_fields, "profile": updated}


@tool(
    name="outlook_draft",
    description="Save a draft email in Outlook without sending. Returns the draft message_id.",
    parameters={
        "type": "object",
        "properties": {
            "to":      {"type": "string"},
            "subject": {"type": "string"},
            "body":    {"type": "string"},
            "cc":      {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
)
async def outlook_draft(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject or not body:
        return {"error": "to, subject, and body are required"}
    payload: Dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": _ms_addr_list(to),
    }
    if args.get("cc"):
        payload["ccRecipients"] = _ms_addr_list(args["cc"])
    try:
        result = await nango_proxy(ctx.business_id, _MICROSOFT_KEY, "POST", "v1.0/me/messages", json=payload)
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "draft_saved", "message_id": result.get("id")}



_SHEETS_KEY = _os.getenv("NEXT_PUBLIC_NANGO_ID_GOOGLE_SHEETS", "google-sheet")
_NOTION_KEY = _os.getenv("NEXT_PUBLIC_NANGO_ID_NOTION", "notion")


# ── Google Sheets tools ───────────────────────────────────────────────────────

@tool(
    name="sheets_list",
    description=(
        "List Google Sheets spreadsheets the user has access to. "
        "Returns file name, spreadsheet ID, and last modified date."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query":       {"type": "string", "description": "Optional search term to filter by name"},
            "max_results": {"type": "integer", "description": "Max files to return (1-50, default 20)"},
        },
    },
)
async def sheets_list(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    limit = min(int(args.get("max_results") or 20), 50)
    q = "mimeType='application/vnd.google-apps.spreadsheet'"
    if args.get("query"):
        q += f" and name contains '{args['query']}'"
    try:
        data = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "GET",
            "drive/v3/files",
            params={"q": q, "pageSize": limit, "fields": "files(id,name,modifiedTime)"},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    files = data.get("files") or []
    return {
        "spreadsheets": [
            {"spreadsheet_id": f["id"], "name": f["name"], "modified": f.get("modifiedTime")}
            for f in files
        ],
        "total": len(files),
    }


@tool(
    name="sheets_read",
    description=(
        "Read data from a Google Sheets spreadsheet. "
        "Provide spreadsheet_id (from sheets_list) and optionally a range like 'Sheet1!A1:D20'. "
        "Returns rows as arrays of values."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Google Sheets spreadsheet ID"},
            "range":          {"type": "string", "description": "A1 notation range e.g. 'Sheet1!A1:E50'. Default: first sheet all data."},
        },
        "required": ["spreadsheet_id"],
    },
)
async def sheets_read(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    sid = (args.get("spreadsheet_id") or "").strip()
    if not sid:
        return {"error": "spreadsheet_id is required"}
    rng = (args.get("range") or "").strip() or "A1:Z1000"
    try:
        data = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "GET",
            f"sheets/v4/spreadsheets/{sid}/values/{rng}",
        )
    except RuntimeError as e:
        return {"error": str(e)}
    rows = data.get("values") or []
    return {
        "spreadsheet_id": sid,
        "range": data.get("range", rng),
        "row_count": len(rows),
        "rows": rows[:500],
    }


@tool(
    name="sheets_append",
    description=(
        "Append rows to a Google Sheets spreadsheet. "
        "Each row is an array of values. Adds after the last row of data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID"},
            "sheet_name":     {"type": "string", "description": "Sheet/tab name. Default: Sheet1"},
            "rows":           {
                "type": "array",
                "items": {"type": "array"},
                "description": "Rows to append, e.g. [[\"John\", \"KES 5000\", \"2024-01-01\"]]",
            },
        },
        "required": ["spreadsheet_id", "rows"],
    },
    destructive=True,
)
async def sheets_append(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    sid = (args.get("spreadsheet_id") or "").strip()
    rows = args.get("rows") or []
    if not sid or not rows:
        return {"error": "spreadsheet_id and rows are required"}
    sheet = (args.get("sheet_name") or "Sheet1").strip()
    try:
        result = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "POST",
            f"sheets/v4/spreadsheets/{sid}/values/{sheet}:append",
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            json={"values": rows},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    updates = result.get("updates") or {}
    return {
        "status": "appended",
        "rows_added": updates.get("updatedRows", len(rows)),
        "range": updates.get("updatedRange"),
    }


@tool(
    name="sheets_update",
    description=(
        "Update specific cells in a Google Sheets spreadsheet. "
        "Provide the A1 range and the values to write."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range":          {"type": "string", "description": "A1 notation range e.g. 'Sheet1!B2:D5'"},
            "rows":           {
                "type": "array",
                "items": {"type": "array"},
                "description": "Values to write into the range",
            },
        },
        "required": ["spreadsheet_id", "range", "rows"],
    },
    destructive=True,
)
async def sheets_update(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    sid = (args.get("spreadsheet_id") or "").strip()
    rng = (args.get("range") or "").strip()
    rows = args.get("rows") or []
    if not sid or not rng or not rows:
        return {"error": "spreadsheet_id, range, and rows are required"}
    try:
        result = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "PUT",
            f"sheets/v4/spreadsheets/{sid}/values/{rng}",
            params={"valueInputOption": "USER_ENTERED"},
            json={"range": rng, "values": rows},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {
        "status": "updated",
        "cells_updated": result.get("updatedCells"),
        "range": result.get("updatedRange"),
    }


@tool(
    name="sheets_create",
    description="Create a new Google Sheets spreadsheet with an optional title.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Spreadsheet title"},
        },
        "required": ["title"],
    },
    destructive=True,
)
async def sheets_create(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    title = (args.get("title") or "Untitled").strip()
    try:
        result = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "POST",
            "sheets/v4/spreadsheets",
            json={"properties": {"title": title}},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {
        "status": "created",
        "spreadsheet_id": result.get("spreadsheetId"),
        "title": result.get("properties", {}).get("title"),
        "url": result.get("spreadsheetUrl"),
    }


# ── Notion tools ──────────────────────────────────────────────────────────────

@tool(
    name="notion_search",
    description=(
        "Search Notion pages and databases. Returns titles, IDs, and types. "
        "Use to find a page or database before reading or writing."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query":    {"type": "string", "description": "Search term"},
            "filter":   {"type": "string", "description": "Filter by type: page or database. Default: both."},
            "max_results": {"type": "integer", "description": "Max results (1-20, default 10)"},
        },
    },
)
async def notion_search(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    limit = min(int(args.get("max_results") or 10), 20)
    body: Dict[str, Any] = {"page_size": limit}
    if args.get("query"):
        body["query"] = args["query"]
    if args.get("filter") in ("page", "database"):
        body["filter"] = {"value": args["filter"], "property": "object"}
    try:
        data = await nango_proxy(ctx.business_id, _NOTION_KEY, "POST", "v1/search", json=body)
    except RuntimeError as e:
        return {"error": str(e)}
    results = []
    for r in (data.get("results") or []):
        obj_type = r.get("object")
        title = ""
        if obj_type == "page":
            props = r.get("properties") or {}
            title_prop = props.get("title") or props.get("Name") or {}
            title_list = title_prop.get("title") or []
            title = "".join(t.get("plain_text", "") for t in title_list) if title_list else r.get("url", "")
        elif obj_type == "database":
            title_list = r.get("title") or []
            title = "".join(t.get("plain_text", "") for t in title_list)
        results.append({
            "id":       r["id"],
            "type":     obj_type,
            "title":    title or "(untitled)",
            "url":      r.get("url"),
            "created":  r.get("created_time"),
            "edited":   r.get("last_edited_time"),
        })
    return {"results": results, "total": len(results)}


@tool(
    name="notion_read_page",
    description=(
        "Read the content blocks of a Notion page by page_id. "
        "Returns the page title and all text blocks."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page_id": {"type": "string", "description": "Notion page ID (from notion_search)"},
        },
        "required": ["page_id"],
    },
)
async def notion_read_page(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    page_id = (args.get("page_id") or "").strip().replace("-", "")
    if not page_id:
        return {"error": "page_id is required"}
    try:
        page = await nango_proxy(ctx.business_id, _NOTION_KEY, "GET", f"v1/pages/{page_id}")
        blocks_data = await nango_proxy(ctx.business_id, _NOTION_KEY, "GET", f"v1/blocks/{page_id}/children", params={"page_size": 100})
    except RuntimeError as e:
        return {"error": str(e)}

    # Extract title
    props = page.get("properties") or {}
    title_prop = props.get("title") or props.get("Name") or {}
    title_list = title_prop.get("title") or []
    title = "".join(t.get("plain_text", "") for t in title_list) or "(untitled)"

    # Extract block text
    blocks = []
    for b in (blocks_data.get("results") or []):
        btype = b.get("type", "")
        block_content = b.get(btype) or {}
        rich = block_content.get("rich_text") or []
        text = "".join(t.get("plain_text", "") for t in rich)
        if text:
            blocks.append({"type": btype, "text": _email_trunc(text, 500)})

    return {"page_id": page_id, "title": title, "blocks": blocks, "block_count": len(blocks)}


@tool(
    name="notion_create_page",
    description=(
        "Create a new Notion page inside a parent page or database. "
        "Provide parent_id (page or database ID) and the page title. "
        "Optionally provide content as plain text."
    ),
    parameters={
        "type": "object",
        "properties": {
            "parent_id":   {"type": "string", "description": "Parent page or database ID"},
            "parent_type": {"type": "string", "description": "page or database (default: page)"},
            "title":       {"type": "string", "description": "Page title"},
            "content":     {"type": "string", "description": "Optional plain text body content"},
        },
        "required": ["parent_id", "title"],
    },
    destructive=True,
)
async def notion_create_page(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    parent_id   = (args.get("parent_id") or "").strip().replace("-", "")
    parent_type = (args.get("parent_type") or "page").strip()
    title       = (args.get("title") or "").strip()
    content     = (args.get("content") or "").strip()
    if not parent_id or not title:
        return {"error": "parent_id and title are required"}

    parent_key = "database_id" if parent_type == "database" else "page_id"
    payload: Dict[str, Any] = {
        "parent": {parent_key: parent_id},
        "properties": {
            "title": {"title": [{"text": {"content": title}}]}
        },
    }
    if content:
        payload["children"] = [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": content[:2000]}}]},
        }]
    try:
        result = await nango_proxy(ctx.business_id, _NOTION_KEY, "POST", "v1/pages", json=payload)
    except RuntimeError as e:
        return {"error": str(e)}
    return {
        "status": "created",
        "page_id": result.get("id"),
        "url": result.get("url"),
        "title": title,
    }


@tool(
    name="notion_append_blocks",
    description=(
        "Append text content to an existing Notion page. "
        "Content is added as paragraph blocks at the end of the page."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page_id": {"type": "string", "description": "Notion page ID"},
            "content": {"type": "string", "description": "Text to append"},
        },
        "required": ["page_id", "content"],
    },
    destructive=True,
)
async def notion_append_blocks(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    page_id = (args.get("page_id") or "").strip().replace("-", "")
    content = (args.get("content") or "").strip()
    if not page_id or not content:
        return {"error": "page_id and content are required"}
    # Split into 2000-char chunks (Notion block limit)
    chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]
    children = [
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": c}}]}}
        for c in chunks
    ]
    try:
        await nango_proxy(
            ctx.business_id, _NOTION_KEY, "PATCH",
            f"v1/blocks/{page_id}/children",
            json={"children": children},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "appended", "blocks_added": len(children)}


@tool(
    name="notion_query_database",
    description=(
        "Query a Notion database to retrieve its rows/entries. "
        "Returns up to 50 rows with all property values."
    ),
    parameters={
        "type": "object",
        "properties": {
            "database_id": {"type": "string", "description": "Notion database ID (from notion_search with filter=database)"},
            "max_results": {"type": "integer", "description": "Max rows to return (1-50, default 20)"},
        },
        "required": ["database_id"],
    },
)
async def notion_query_database(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    db_id = (args.get("database_id") or "").strip().replace("-", "")
    limit = min(int(args.get("max_results") or 20), 50)
    if not db_id:
        return {"error": "database_id is required"}
    try:
        data = await nango_proxy(
            ctx.business_id, _NOTION_KEY, "POST",
            f"v1/databases/{db_id}/query",
            json={"page_size": limit},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    rows = []
    for page in (data.get("results") or []):
        row: Dict[str, Any] = {"page_id": page["id"], "url": page.get("url")}
        for prop_name, prop_val in (page.get("properties") or {}).items():
            ptype = prop_val.get("type", "")
            val = prop_val.get(ptype)
            if ptype == "title":
                row[prop_name] = "".join(t.get("plain_text", "") for t in (val or []))
            elif ptype in ("rich_text", "email", "phone_number", "url"):
                if isinstance(val, list):
                    row[prop_name] = "".join(t.get("plain_text", "") for t in val)
                else:
                    row[prop_name] = val or ""
            elif ptype in ("number", "checkbox"):
                row[prop_name] = val
            elif ptype == "select":
                row[prop_name] = (val or {}).get("name")
            elif ptype == "multi_select":
                row[prop_name] = [s.get("name") for s in (val or [])]
            elif ptype == "date":
                row[prop_name] = (val or {}).get("start")
            else:
                row[prop_name] = str(val)[:100] if val else None
        rows.append(row)
    return {"database_id": db_id, "rows": rows, "total": len(rows)}
