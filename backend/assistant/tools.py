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
import os
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
    # the AI can share them with users and pass them to design tools without
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
        "primary colour into Gemini design tools (brand_color, logo_url) and `generate_design_background.logo_url`."
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
        # Brand kit — pass these straight into Gemini design tools
        # (brand_color, logo_url) and generate_design_background.logo_url.
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
    description="Update a product in the catalog. Can update name, price, discount price, description, category, sub-category, stock status, and stock quantity.",
    parameters={
        "type": "object",
        "required": ["product_id"],
        "properties": {
            "product_id": {"type": "string", "description": "Product ID from list_products"},
            "name": {"type": "string"},
            "price": {"type": "number"},
            "discount_price": {"type": "number", "description": "Sale/discounted price (set to 0 to remove)"},
            "description": {"type": "string"},
            "category": {"type": "string", "description": "Product category e.g. 'AI Design', 'Image Generation', 'AI Infrastructure'"},
            "sub_category": {"type": "string"},
            "in_stock": {"type": "boolean"},
            "stock_quantity": {"type": "integer", "description": "Inventory count (set to track stock levels)"},
        },
    },
    destructive=True,
)
async def update_product(ctx: ToolContext, args: Dict[str, Any]):
    from bson import ObjectId
    pid = args["product_id"]
    # Support both ObjectId and string _id
    try:
        oid = ObjectId(pid)
        query = {"$or": [{"_id": oid}, {"_id": pid}], "user_id": ctx.business_id}
    except Exception:
        query = {"_id": pid, "user_id": ctx.business_id}

    updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    for k in ("name", "description", "category", "sub_category"):
        if k in args and args[k] is not None:
            updates[k] = args[k]
    if "price" in args and args["price"] is not None:
        updates["price"] = float(args["price"])
    if "discount_price" in args and args["discount_price"] is not None:
        updates["discount_price"] = float(args["discount_price"]) or None
    if "in_stock" in args and args["in_stock"] is not None:
        updates["in_stock"] = bool(args["in_stock"])
    if "stock_quantity" in args and args["stock_quantity"] is not None:
        updates["stock_quantity"] = int(args["stock_quantity"])

    res = await ctx.db.products.update_one(query, {"$set": updates})
    if res.matched_count == 0:
        return {"error": "Product not found — double-check the product_id from list_products"}
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
        "Nango-connected apps (Shopify, Stripe, Klaviyo, Mailchimp, Brevo, Slack, "
        "Microsoft, Google Sheets, Notion), and Composio-connected apps (Gmail, Google Calendar)."
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

    # ── Social channels (Zernio-backed accounts) ─────────────────────────────
    social_accounts: list[Dict[str, Any]] = []
    social_activity: Dict[str, Any] = {
        "accounts_count": 0,
        "platforms": [],
        "accounts_by_platform": {},
        "window_days": None,
        "recent_inbox_conversations": 0,
        "recent_comments": 0,
        "comments_by_platform_recent": {},
        "recent_posts": 0,
        "recent_unread_conversations": 0,
        "total_inbox_conversations_fetched": 0,
        "total_comments_fetched": 0,
        "total_posts_fetched": 0,
        "inbox_by_platform_recent": {},
        "posts_by_platform_recent": {},
        "latest_messages_sample": [],
        "latest_messages_by_conversation": {},
        "brand_voice_signals": {
            "outgoing_messages_analyzed": 0,
            "avg_outgoing_length": 0,
            "uses_emoji_ratio": 0.0,
            "uses_question_ratio": 0.0,
            "common_openers": [],
        },
        "performance_totals": {
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "reach": 0,
            "clicks": 0,
        },
        "top_post": None,
        "latest_conversations": [],
        "latest_posts": [],
        "last_message_at": None,
        "last_comment_at": None,
        "last_post_at": None,
        "post_data_source": "zernio_posts",
        "fetch_diagnostics": {
            "accounts": {"status_code": None, "ok": False, "error": None},
            "inbox": {"status_code": None, "ok": False, "error": None},
            "comments": {"status_code": None, "ok": False, "error": None},
            "posts": {"status_code": None, "ok": False, "error": None},
            "analytics": {"status_code": None, "ok": False, "error": None},
        },
        "checked_at": datetime.utcnow().isoformat(),
    }
    try:
        import httpx
        user_doc = await ctx.db.users.find_one(
            {"_id": ctx.business_id},
            {"zernio_profile_id": 1},
        )
        zernio_profile_id = (user_doc or {}).get("zernio_profile_id")
        zernio_api_key = (os.getenv("ZERNIO_API_KEY") or "").strip()
        configured_base = (os.getenv("ZERNIO_API_BASE") or "https://zernio.com/api/v1").rstrip("/")
        zernio_api_bases = list(dict.fromkeys([configured_base, "https://zernio.com/api/v1"]))
        if zernio_profile_id and zernio_api_key:
            # Bumped timeout (was 6s) — the social block makes ~10 sequential message-detail
            # fetches per conversation; with a 6s per-request budget, a slow Zernio response
            # in the middle of the loop would cause the subsequent /posts or /analytics call
            # to time out, leaving recent_posts=0 and performance_totals all zero. The AI then
            # incorrectly tells the owner they "have only one post" or no likes/shares data.
            async with httpx.AsyncClient(timeout=15.0) as client:
                async def _get_first_ok(paths: list[str], *, params: Optional[Dict[str, Any]] = None) -> tuple[Optional[httpx.Response], Optional[str]]:
                    last_resp: Optional[httpx.Response] = None
                    for base in zernio_api_bases:
                        for path in paths:
                            url = f"{base}{path}"
                            try:
                                r = await client.get(url, params=params, headers={"Authorization": f"Bearer {zernio_api_key}"})
                            except Exception:
                                # Network/timeout on one base+path shouldn't kill the whole social block.
                                # Try the next candidate; if all fail, return whatever last_resp we have (may be None).
                                continue
                            last_resp = r
                            if r.status_code == 200:
                                return r, path
                    return last_resp, None

                resp, _ = await _get_first_ok(["/accounts"], params={"profileId": zernio_profile_id})
                if resp is None:
                    return out
                social_activity["fetch_diagnostics"]["accounts"]["status_code"] = resp.status_code
                if resp.status_code == 200:
                    social_activity["fetch_diagnostics"]["accounts"]["ok"] = True
                    data = resp.json()
                    rows = data.get("accounts") or data.get("data") or []
                    if isinstance(rows, list):
                        social_accounts = [
                            {
                                "id": str((a or {}).get("id") or (a or {}).get("_id") or (a or {}).get("accountId") or ""),
                                "platform": str((a or {}).get("platform") or "").lower(),
                                "username": (a or {}).get("username"),
                                "name": (a or {}).get("name") or (a or {}).get("displayName") or (a or {}).get("pageName"),
                                "page_name": (a or {}).get("pageName") or (a or {}).get("name") or (a or {}).get("displayName"),
                                "connected": True,
                            }
                            for a in rows
                            if isinstance(a, dict)
                        ]
                        social_activity["accounts_count"] = len(social_accounts)
                        platforms = {
                            str(a.get("platform") or "").lower()
                            for a in social_accounts
                            if a.get("platform")
                        }
                        social_activity["platforms"] = sorted(platforms)
                        social_activity["accounts_by_platform"] = {
                            p: sum(1 for a in social_accounts if str(a.get("platform") or "").lower() == p)
                            for p in sorted(platforms)
                        }

                    # Pull lightweight inbox + posts snapshots so the assistant has
                    # immediate context about what is happening on connected pages.
                    conv_resp, conv_path = await _get_first_ok(
                        ["/inbox/conversations", "/conversations"],
                        params={"profileId": zernio_profile_id, "limit": 50},
                    )
                    if conv_resp is None:
                        conv_resp = resp
                    social_activity["fetch_diagnostics"]["inbox"]["status_code"] = conv_resp.status_code
                    # Defaults so the deferred message-detail loop below is always safe to reference,
                    # even when the inbox call returns no usable payload.
                    recent_conversations_for_messages: list[Dict[str, Any]] = []
                    inbox_message_loop_pending = False
                    if conv_resp.status_code == 200:
                        social_activity["fetch_diagnostics"]["inbox"]["ok"] = True
                        conv_data = conv_resp.json()
                        conversations = conv_data.get("conversations") or conv_data.get("data") or []
                        if isinstance(conversations, list):
                            social_activity["total_inbox_conversations_fetched"] = len(conversations)
                            recent_conversations = [c for c in conversations if isinstance(c, dict)]
                            social_activity["recent_inbox_conversations"] = len(recent_conversations)
                            social_activity["recent_unread_conversations"] = sum(
                                1
                                for c in recent_conversations
                                if isinstance(c, dict) and bool(
                                    (c.get("unread") is True)
                                    or ((c.get("unreadCount") or c.get("unread_count") or 0) > 0)
                                )
                            )
                            inbox_by_platform: Dict[str, int] = {}
                            for c in recent_conversations:
                                platform = str((c or {}).get("platform") or "").lower() or "unknown"
                                inbox_by_platform[platform] = inbox_by_platform.get(platform, 0) + 1
                            social_activity["inbox_by_platform_recent"] = inbox_by_platform
                            social_activity["latest_conversations"] = [
                                {
                                    "platform": str((c or {}).get("platform") or "").lower(),
                                    "conversation_id": (c or {}).get("id") or (c or {}).get("_id") or (c or {}).get("conversationId"),
                                    "username": (c or {}).get("username") or (c or {}).get("senderName"),
                                    "last_message": (c or {}).get("lastMessage") or (c or {}).get("last_message"),
                                    "unread_count": (c or {}).get("unreadCount") or (c or {}).get("unread_count") or (1 if (c or {}).get("unread") else 0),
                                    "updated_at": (c or {}).get("updatedAt") or (c or {}).get("updated_at"),
                                }
                                for c in recent_conversations[:10]
                                if isinstance(c, dict)
                            ]
                            conv_times = [
                                str(item.get("updated_at"))
                                for item in social_activity["latest_conversations"]
                                if item.get("updated_at")
                            ]
                            if conv_times:
                                social_activity["last_message_at"] = conv_times[0]

                            # NOTE: Per-conversation message-detail fetching (for brand-voice signals)
                            # used to live here — but it is the slowest part of the social block
                            # (10 sequential requests). Running it before /posts and /analytics caused
                            # those later fetches to time out, so the assistant ended up reporting
                            # "0 posts" and "no likes/shares". The loop has been moved to run AFTER
                            # the posts/comments/analytics snapshots so high-value engagement data is
                            # always populated even if message sampling later degrades.
                            recent_conversations_for_messages = recent_conversations
                            inbox_message_loop_pending = True

                    elif conv_resp.status_code >= 400:
                        social_activity["fetch_diagnostics"]["inbox"]["error"] = conv_resp.text[:300]

                    post_resp, _ = await _get_first_ok(
                        ["/posts"],
                        params={"profileId": zernio_profile_id, "limit": 50},
                    )
                    if post_resp is None:
                        post_resp = resp
                    social_activity["fetch_diagnostics"]["posts"]["status_code"] = post_resp.status_code
                    if post_resp.status_code == 200:
                        social_activity["fetch_diagnostics"]["posts"]["ok"] = True
                        post_data = post_resp.json()
                        posts = post_data.get("posts") or post_data.get("data") or []
                        if isinstance(posts, list):
                            social_activity["total_posts_fetched"] = len(posts)
                            latest_posts = [p for p in posts if isinstance(p, dict)]
                            social_activity["recent_posts"] = len(latest_posts)
                            posts_by_platform: Dict[str, int] = {}
                            for p in latest_posts:
                                platform = str((p or {}).get("platform") or "").lower() or "unknown"
                                posts_by_platform[platform] = posts_by_platform.get(platform, 0) + 1
                            social_activity["posts_by_platform_recent"] = posts_by_platform
                            top_score = -1
                            social_activity["latest_posts"] = [
                                {
                                    "platform": str((p or {}).get("platform") or "").lower(),
                                    "post_id": (p or {}).get("id") or (p or {}).get("_id"),
                                    "status": (p or {}).get("status"),
                                    "title": (p or {}).get("title") or (p or {}).get("caption"),
                                    "scheduled_at": (p or {}).get("scheduledAt") or (p or {}).get("scheduled_at"),
                                    "published_at": (p or {}).get("publishedAt") or (p or {}).get("published_at"),
                                }
                                for p in latest_posts[:20]
                                if isinstance(p, dict)
                            ]
                            post_times = [
                                str(item.get("published_at") or item.get("scheduled_at"))
                                for item in social_activity["latest_posts"]
                                if item.get("published_at") or item.get("scheduled_at")
                            ]
                            if post_times:
                                social_activity["last_post_at"] = post_times[0]
                            for p in latest_posts:
                                if not isinstance(p, dict):
                                    continue
                                metrics = p.get("metrics") if isinstance(p.get("metrics"), dict) else {}
                                likes = int(metrics.get("likes") or p.get("likes") or 0)
                                comments = int(metrics.get("comments") or p.get("comments") or 0)
                                shares = int(metrics.get("shares") or p.get("share_count") or 0)
                                reach = int(metrics.get("reach") or p.get("impressions") or 0)
                                clicks = int(metrics.get("clicks") or p.get("link_clicks") or 0)
                                social_activity["performance_totals"]["likes"] += likes
                                social_activity["performance_totals"]["comments"] += comments
                                social_activity["performance_totals"]["shares"] += shares
                                social_activity["performance_totals"]["reach"] += reach
                                social_activity["performance_totals"]["clicks"] += clicks
                                score = likes + comments * 2 + shares * 3 + clicks
                                if score > top_score:
                                    top_score = score
                                    social_activity["top_post"] = {
                                        "post_id": p.get("id") or p.get("_id"),
                                        "platform": str(p.get("platform") or "").lower(),
                                        "title": p.get("title") or p.get("caption"),
                                        "likes": likes,
                                        "comments": comments,
                                        "shares": shares,
                                        "reach": reach,
                                        "clicks": clicks,
                                        "engagement_score": score,
                                    }
                    elif post_resp.status_code >= 400:
                        social_activity["fetch_diagnostics"]["posts"]["error"] = post_resp.text[:300]

                    # Pull comments snapshot so we always report comment activity.
                    comments_resp, _ = await _get_first_ok(
                        ["/inbox/comments", "/comments"],
                        params={"profileId": zernio_profile_id, "limit": 100},
                    )
                    if comments_resp is not None:
                        social_activity["fetch_diagnostics"]["comments"]["status_code"] = comments_resp.status_code
                        if comments_resp.status_code == 200:
                            social_activity["fetch_diagnostics"]["comments"]["ok"] = True
                            comments_data = comments_resp.json()
                            comments_rows = comments_data.get("comments") or comments_data.get("data") or []
                            if isinstance(comments_rows, list):
                                social_activity["total_comments_fetched"] = len(comments_rows)
                                recent_comments = [c for c in comments_rows if isinstance(c, dict)]
                                social_activity["recent_comments"] = len(recent_comments)
                                comments_by_platform: Dict[str, int] = {}
                                for c in recent_comments:
                                    platform = str((c or {}).get("platform") or "").lower() or "unknown"
                                    comments_by_platform[platform] = comments_by_platform.get(platform, 0) + 1
                                social_activity["comments_by_platform_recent"] = comments_by_platform
                                comment_times = [
                                    str((c or {}).get("createdAt") or (c or {}).get("created_at"))
                                    for c in recent_comments
                                    if (c or {}).get("createdAt") or (c or {}).get("created_at")
                                ]
                                if comment_times:
                                    social_activity["last_comment_at"] = comment_times[0]
                        elif comments_resp.status_code >= 400:
                            social_activity["fetch_diagnostics"]["comments"]["error"] = comments_resp.text[:300]

                    # Pull analytics snapshot for likes/shares/comments/reach/clicks with endpoint fallback.
                    analytics_resp, _ = await _get_first_ok(
                        ["/analytics"],
                        params={"profileId": zernio_profile_id, "limit": 100},
                    )
                    if analytics_resp is not None:
                        social_activity["fetch_diagnostics"]["analytics"]["status_code"] = analytics_resp.status_code
                        if analytics_resp.status_code == 200:
                            social_activity["fetch_diagnostics"]["analytics"]["ok"] = True
                            analytics_data = analytics_resp.json()
                            analytics_rows = analytics_data.get("analytics") or analytics_data.get("data") or []
                            if isinstance(analytics_rows, list) and analytics_rows:
                                # Keep additive behavior but avoid double counting if posts already had rich metrics.
                                if not any(int((social_activity.get("performance_totals") or {}).get(k) or 0) > 0 for k in ("likes", "comments", "shares", "reach", "clicks")):
                                    for a in analytics_rows:
                                        if not isinstance(a, dict):
                                            continue
                                        social_activity["performance_totals"]["likes"] += int(
                                            a.get("likes") or a.get("likeCount") or a.get("like_count") or 0
                                        )
                                        social_activity["performance_totals"]["comments"] += int(
                                            a.get("comments") or a.get("commentCount") or a.get("comments_count") or 0
                                        )
                                        social_activity["performance_totals"]["shares"] += int(
                                            a.get("shares") or a.get("shareCount") or a.get("share_count") or 0
                                        )
                                        social_activity["performance_totals"]["reach"] += int(
                                            a.get("reach") or a.get("impressions") or 0
                                        )
                                        social_activity["performance_totals"]["clicks"] += int(
                                            a.get("clicks") or a.get("clickCount") or a.get("click_count") or 0
                                        )
                        elif analytics_resp.status_code >= 400:
                            social_activity["fetch_diagnostics"]["analytics"]["error"] = analytics_resp.text[:300]

                    # Fallback 1: derive active post IDs from comment streams.
                    if social_activity["recent_posts"] == 0:
                        comments_resp, _ = await _get_first_ok(
                            ["/inbox/comments", "/comments"],
                            params={"profileId": zernio_profile_id, "limit": 100},
                        )
                        if comments_resp is not None and comments_resp.status_code == 200:
                            comments_data = comments_resp.json()
                            comments_rows = comments_data.get("comments") or comments_data.get("data") or []
                            if isinstance(comments_rows, list) and comments_rows:
                                def _comment_post_id(row: Dict[str, Any]) -> str:
                                    post_obj = row.get("post") if isinstance(row.get("post"), dict) else {}
                                    media_obj = row.get("media") if isinstance(row.get("media"), dict) else {}
                                    parent_obj = row.get("parent") if isinstance(row.get("parent"), dict) else {}
                                    candidates = (
                                        row.get("postId"),
                                        row.get("post_id"),
                                        row.get("postID"),
                                        row.get("latePostId"),
                                        row.get("late_post_id"),
                                        row.get("external_post_id"),
                                        row.get("zernio_post_id"),
                                        row.get("object_id"),
                                        row.get("objectId"),
                                        row.get("parentId"),
                                        row.get("parent_id"),
                                        row.get("mediaId"),
                                        row.get("media_id"),
                                        post_obj.get("id"),
                                        post_obj.get("postId"),
                                        post_obj.get("post_id"),
                                        media_obj.get("id"),
                                        media_obj.get("postId"),
                                        media_obj.get("post_id"),
                                        parent_obj.get("id"),
                                    )
                                    for c in candidates:
                                        if c is None:
                                            continue
                                        s = str(c).strip()
                                        if s:
                                            return s
                                    return ""

                                by_post: Dict[str, Dict[str, Any]] = {}
                                for c in comments_rows:
                                    if not isinstance(c, dict):
                                        continue
                                    post_id = _comment_post_id(c)
                                    if not post_id:
                                        continue
                                    if post_id not in by_post:
                                        by_post[post_id] = {
                                            "platform": str(c.get("platform") or "").lower(),
                                            "post_id": post_id,
                                            "status": "active_via_comments",
                                            "title": c.get("postTitle") or c.get("caption") or None,
                                            "scheduled_at": None,
                                            "published_at": c.get("createdAt") or c.get("created_at"),
                                        }
                                if by_post:
                                    social_activity["total_posts_fetched"] = len(by_post)
                                    social_activity["recent_posts"] = len(by_post)
                                    social_activity["latest_posts"] = list(by_post.values())[:20]
                                    social_activity["post_data_source"] = "comments_fallback"
                                    post_times = [
                                        str(item.get("published_at") or item.get("scheduled_at"))
                                        for item in social_activity["latest_posts"]
                                        if item.get("published_at") or item.get("scheduled_at")
                                    ]
                                    if post_times:
                                        social_activity["last_post_at"] = post_times[0]

                    # Fallback 2: use internal scheduled/published posts saved in CRM.
                    if social_activity["recent_posts"] == 0:
                        internal_rows = await ctx.db.scheduled_posts.find(
                            {"user_id": ctx.business_id, "status": {"$in": ["published", "scheduled"]}}
                        ).sort("scheduled_at", -1).to_list(100)
                        if internal_rows:
                            latest_internal = [p for p in internal_rows if isinstance(p, dict)]
                            social_activity["total_posts_fetched"] = len(latest_internal)
                            social_activity["recent_posts"] = len(latest_internal)
                            social_activity["latest_posts"] = [
                                {
                                    "platform": str((p or {}).get("platform") or "").lower(),
                                    "post_id": (p or {}).get("_id") or (p or {}).get("id"),
                                    "status": (p or {}).get("status"),
                                    "title": (p or {}).get("title") or (p or {}).get("caption") or (p or {}).get("content"),
                                    "scheduled_at": (p or {}).get("scheduled_at"),
                                    "published_at": (p or {}).get("published_at"),
                                }
                                for p in latest_internal[:20]
                            ]
                            social_activity["post_data_source"] = "internal_scheduled_posts"
                            post_times = [
                                str(item.get("published_at") or item.get("scheduled_at"))
                                for item in social_activity["latest_posts"]
                                if item.get("published_at") or item.get("scheduled_at")
                            ]
                            if post_times:
                                social_activity["last_post_at"] = post_times[0]

                    # Deferred message-detail sampling for brand-voice signals. Runs LAST and is
                    # wrapped so any timeout/network hiccup here cannot wipe the post / analytics
                    # data we already populated above. Previously this loop ran before the
                    # /posts and /analytics fetches, and a slow run here used to time out the
                    # subsequent calls — leaving recent_posts=0 and performance_totals all zero.
                    if inbox_message_loop_pending and recent_conversations_for_messages:
                        try:
                            collected_messages: list[Dict[str, Any]] = []
                            for c in recent_conversations_for_messages[:10]:
                                conv_id = (c or {}).get("id") or (c or {}).get("_id") or (c or {}).get("conversationId")
                                if not conv_id:
                                    continue
                                try:
                                    account_id = (c or {}).get("accountId") or (c or {}).get("account_id")
                                    detail_params = {
                                        "limit": 50,
                                        "sortOrder": "asc",
                                        **({"accountId": account_id} if account_id else {}),
                                    }
                                    detail_paths = [f"/inbox/conversations/{conv_id}/messages", f"/conversations/{conv_id}"]
                                    if conv_path == "/conversations":
                                        detail_paths = [f"/conversations/{conv_id}", f"/inbox/conversations/{conv_id}/messages"]
                                    conv_detail_resp, _ = await _get_first_ok(detail_paths, params=detail_params)
                                    if conv_detail_resp is None:
                                        continue
                                    if conv_detail_resp.status_code != 200:
                                        # Backward-compat fallback for connectors that still expose conversation detail.
                                        conv_detail_resp, _ = await _get_first_ok(
                                            [f"/inbox/conversations/{conv_id}", f"/conversations/{conv_id}"],
                                            params=None,
                                        )
                                        if conv_detail_resp is None:
                                            continue
                                        if conv_detail_resp.status_code != 200:
                                            continue
                                    conv_detail = conv_detail_resp.json()
                                    msgs = conv_detail.get("messages") or conv_detail.get("data") or []
                                    if not isinstance(msgs, list):
                                        continue
                                    convo_bucket: list[Dict[str, Any]] = []
                                    for m in msgs[-10:]:
                                        if not isinstance(m, dict):
                                            continue
                                        text = (
                                            (m.get("message") if isinstance(m.get("message"), str) else None)
                                            or (m.get("text") if isinstance(m.get("text"), str) else None)
                                            or (m.get("content") if isinstance(m.get("content"), str) else None)
                                            or ""
                                        ).strip()
                                        if not text:
                                            continue
                                        direction = str(
                                            m.get("direction")
                                            or m.get("type")
                                            or ("outgoing" if m.get("fromMe") else "incoming")
                                        ).lower()
                                        row = {
                                            "conversation_id": str(conv_id),
                                            "platform": str((c or {}).get("platform") or "").lower(),
                                            "username": (c or {}).get("username") or (c or {}).get("senderName"),
                                            "direction": direction,
                                            "text": text[:280],
                                            "created_at": m.get("createdAt") or m.get("created_at") or m.get("timestamp"),
                                        }
                                        convo_bucket.append(row)
                                        collected_messages.append(row)
                                    if convo_bucket:
                                        social_activity["latest_messages_by_conversation"][str(conv_id)] = convo_bucket[-10:]
                                except Exception:
                                    continue
                                if len(collected_messages) >= 50:
                                    break

                            social_activity["latest_messages_sample"] = collected_messages[-50:]

                            outgoing = [
                                m for m in social_activity["latest_messages_sample"]
                                if isinstance(m, dict) and "out" in str(m.get("direction") or "").lower()
                            ]
                            if outgoing:
                                total_len = sum(len(str(m.get("text") or "")) for m in outgoing)
                                emoji_hits = sum(
                                    1 for m in outgoing
                                    if any(ord(ch) > 10000 for ch in str(m.get("text") or ""))
                                )
                                question_hits = sum(
                                    1 for m in outgoing if "?" in str(m.get("text") or "")
                                )
                                openers: Dict[str, int] = {}
                                for m in outgoing:
                                    txt = str(m.get("text") or "").strip().lower()
                                    first = txt.split(" ")[0] if txt else ""
                                    if first:
                                        openers[first] = openers.get(first, 0) + 1
                                top_openers = [k for k, _ in sorted(openers.items(), key=lambda kv: kv[1], reverse=True)[:5]]
                                social_activity["brand_voice_signals"] = {
                                    "outgoing_messages_analyzed": len(outgoing),
                                    "avg_outgoing_length": int(round(total_len / max(len(outgoing), 1))),
                                    "uses_emoji_ratio": round(emoji_hits / max(len(outgoing), 1), 3),
                                    "uses_question_ratio": round(question_hits / max(len(outgoing), 1), 3),
                                    "common_openers": top_openers,
                                }
                        except Exception as e:
                            logger.warning(f"[integrations_status] message-detail sampling failed (non-fatal): {e}")
                elif resp.status_code >= 400:
                    social_activity["fetch_diagnostics"]["accounts"]["error"] = resp.text[:300]
    except Exception as e:
        logger.warning(f"[integrations_status] Zernio social lookup failed: {e}")
    out["social"] = social_accounts
    out["social_activity"] = social_activity

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
                    f"{nango_api}/connections",
                    params={"tags[end_user_id]": ctx.business_id},
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

    # ── Composio (Gmail + Google Calendar) ────────────────────────────────────
    try:
        from composio_service import get_all_connection_statuses
        composio_statuses = await get_all_connection_statuses(ctx.business_id)
        out["composio"] = {k: {"connected": v} for k, v in composio_statuses.items()}
    except Exception as e:
        logger.warning(f"[integrations_status] Composio lookup failed: {e}")
        out["composio"] = {}

    # Human-friendly social account labels so the assistant can reference exact pages.
    social_labels: list[str] = []
    for acc in social_accounts:
        if not acc.get("connected"):
            continue
        platform = str(acc.get("platform") or "").title()
        page = (acc.get("page_name") or acc.get("name") or "").strip() if isinstance(acc.get("page_name") or acc.get("name"), str) else ""
        username = (acc.get("username") or "").strip() if isinstance(acc.get("username"), str) else ""
        if page and username:
            social_labels.append(f"{platform} ({page} / @{username})")
        elif page:
            social_labels.append(f"{platform} ({page})")
        elif username:
            social_labels.append(f"{platform} (@{username})")
        elif platform:
            social_labels.append(platform)
    out["social_overview"] = social_labels
    social_gaps: list[str] = []
    social_actions: list[str] = []
    fetch_diag = social_activity.get("fetch_diagnostics") or {}
    inbox_diag = fetch_diag.get("inbox") or {}
    posts_diag = fetch_diag.get("posts") or {}
    inbox_status = int(inbox_diag.get("status_code") or 0) if str(inbox_diag.get("status_code") or "").isdigit() else None
    posts_status = int(posts_diag.get("status_code") or 0) if str(posts_diag.get("status_code") or "").isdigit() else None
    inbox_error_txt = str(inbox_diag.get("error") or "").lower()
    posts_error_txt = str(posts_diag.get("error") or "").lower()
    inbox_perm_denied = inbox_status in (401, 403) or ("permission" in inbox_error_txt)
    posts_perm_denied = posts_status in (401, 403) or ("permission" in posts_error_txt)

    if social_activity["accounts_count"] > 0 and social_activity["recent_inbox_conversations"] == 0:
        if inbox_perm_denied:
            social_gaps.append("Connected social channels cannot read inbox data due to platform permission denial.")
            social_actions.append("Reconnect affected channels and grant inbox/message read permissions, then run a fresh inbox sync.")
        elif inbox_status == 404:
            social_gaps.append("Connected social channels returned 404 on inbox fetch (likely connector path or sync mismatch).")
            social_actions.append("Run a full Social Inbox refresh first; if still failing, contact Zilo support with this diagnostic.")
        else:
            social_gaps.append("No recent inbox conversations returned for connected social channels.")
            social_actions.append("Send a new test DM to a connected page/account and trigger inbox refresh to verify live sync.")
    if social_activity["accounts_count"] > 0 and social_activity["recent_posts"] == 0:
        if posts_perm_denied:
            social_gaps.append("Connected social channels cannot read post history due to platform permission denial.")
            social_actions.append("Reconnect affected channels and grant post/page read permissions, then run a social refresh.")
        elif posts_status == 404:
            social_gaps.append("Connected social channels returned 404 on post fetch (likely connector path or sync mismatch).")
            social_actions.append("Run a social data refresh; if it persists, contact Zilo support with diagnostics.")
        else:
            social_gaps.append("No recent posts returned for connected social channels.")
            social_actions.append("Confirm posting history exists and run a refresh to pull latest posts.")
    if social_activity["accounts_count"] == 0:
        social_gaps.append("No connected social accounts were found.")
        social_actions.append("Connect at least one social account in Integrations to unlock social insights.")
    out["social_diagnostics"] = {
        "status": "healthy" if not social_gaps else "attention_needed",
        "gaps": social_gaps,
        "recommended_actions": social_actions,
        # Keep normal responses conversational: only expose technical evidence when attention is needed.
        **(
            {
                "evidence": {
                    "accounts_fetch_status": (fetch_diag.get("accounts") or {}).get("status_code"),
                    "inbox_fetch_status": (fetch_diag.get("inbox") or {}).get("status_code"),
                    "comments_fetch_status": (fetch_diag.get("comments") or {}).get("status_code"),
                    "posts_fetch_status": (fetch_diag.get("posts") or {}).get("status_code"),
                    "analytics_fetch_status": (fetch_diag.get("analytics") or {}).get("status_code"),
                    "post_data_source": social_activity.get("post_data_source"),
                }
            }
            if social_gaps
            else {}
        ),
        "checked_at": social_activity.get("checked_at"),
        "last_message_at": social_activity.get("last_message_at"),
        "last_comment_at": social_activity.get("last_comment_at"),
        "last_post_at": social_activity.get("last_post_at"),
    }

    # Flat convenience summary for the agent — list every connected social
    # platform (not just FB/IG), so newly-added platforms like TikTok/Twitter/
    # YouTube/LinkedIn show up in the agent's view.
    connected_social_platforms: Dict[str, bool] = {}
    for acc in social_accounts:
        if not isinstance(acc, dict) or not acc.get("connected"):
            continue
        plat_raw = str(acc.get("platform") or "").strip().lower()
        if not plat_raw:
            continue
        # Map platform ids to display names (twitter → "Twitter / X", googlebusiness → "Google Business")
        display = {
            "facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn",
            "twitter": "Twitter / X", "x": "Twitter / X", "tiktok": "TikTok",
            "youtube": "YouTube", "pinterest": "Pinterest", "reddit": "Reddit",
            "bluesky": "Bluesky", "threads": "Threads", "snapchat": "Snapchat",
            "discord": "Discord", "googlebusiness": "Google Business",
        }.get(plat_raw, plat_raw.title())
        connected_social_platforms[display] = True

    out["summary"] = (
        "Connected: "
        + ", ".join(
            k for k, v in {
                "WhatsApp": out["whatsapp"]["connected"],
                "Telegram": out["telegram"]["connected"],
                **connected_social_platforms,
                **{k.replace("_", " ").title(): v for k, v in nango_status.items()},
            }.items()
            if v
        )
        or "none"
    )
    if social_labels:
        out["summary"] += f" | Social pages: {', '.join(social_labels)}"
    if social_activity["accounts_count"]:
        out["summary"] += (
            f" | Social activity: {social_activity['recent_inbox_conversations']} inbox threads "
            f"({social_activity['recent_unread_conversations']} unread), "
            f"{social_activity['recent_comments']} comments, "
            f"{social_activity['recent_posts']} recent posts"
        )
        perf = social_activity.get("performance_totals") or {}
        if any(int(perf.get(k) or 0) > 0 for k in ("likes", "comments", "shares", "reach", "clicks")):
            out["summary"] += (
                f" | Social performance: {int(perf.get('likes') or 0)} likes, "
                f"{int(perf.get('comments') or 0)} comments, "
                f"{int(perf.get('shares') or 0)} shares, "
                f"{int(perf.get('reach') or 0)} reach, "
                f"{int(perf.get('clicks') or 0)} clicks"
            )
    if social_gaps:
        out["summary"] += f" | Social diagnostics: {social_gaps[0]}"
    return out


@tool(
    name="get_social_conversation_history",
    description=(
        "Fetch recent social inbox conversations and message snippets from connected channels. "
        "Use this to answer who the business talked to and what they discussed."
    ),
    parameters={
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "Optional platform filter (facebook, instagram, twitter, etc).",
            },
            "query": {
                "type": "string",
                "description": "Optional keyword/person search in username or message text.",
            },
            "limit": {
                "type": "integer",
                "description": "How many conversations to return (default 20, max 50).",
            },
        },
    },
)
async def get_social_conversation_history(ctx: ToolContext, args: Dict[str, Any]):
    import os
    import httpx

    platform_filter = str(args.get("platform") or "").strip().lower()
    query = str(args.get("query") or "").strip().lower()
    limit = max(1, min(int(args.get("limit") or 20), 50))

    user_doc = await ctx.db.users.find_one({"_id": ctx.business_id}, {"zernio_profile_id": 1})
    zernio_profile_id = (user_doc or {}).get("zernio_profile_id")
    if not zernio_profile_id:
        return {"error": "No social profile linked yet. Connect a social account first."}

    zernio_api_key = (os.getenv("ZERNIO_API_KEY") or "").strip()
    configured_base = (os.getenv("ZERNIO_API_BASE") or "https://zernio.com/api/v1").rstrip("/")
    zernio_api_bases = list(dict.fromkeys([configured_base, "https://zernio.com/v1", "https://zernio.com/api/v1"]))
    if not zernio_api_key:
        return {"error": "ZERNIO_API_KEY is not configured on the server."}

    headers = {"Authorization": f"Bearer {zernio_api_key}"}
    conversations: list[Dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            async def _get_with_base_fallback(path: str, *, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
                last_exc: Optional[httpx.HTTPStatusError] = None
                for base in zernio_api_bases:
                    url = f"{base}{path}"
                    try:
                        resp = await client.get(url, params=params, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        return data if isinstance(data, dict) else {}
                    except httpx.HTTPStatusError as e:
                        last_exc = e
                        # 404 on one base/path can mean wrong connector path; try next candidate.
                        if e.response.status_code == 404:
                            continue
                        raise
                if last_exc is not None and last_exc.response.status_code == 404:
                    return None
                if last_exc is not None:
                    raise last_exc
                return None

            params: Dict[str, Any] = {"profileId": zernio_profile_id, "limit": 50}
            if platform_filter:
                params["platform"] = platform_filter
            conv_data = await _get_with_base_fallback("/inbox/conversations", params=params)
            if conv_data is None:
                # No synced conversation endpoint for this account/base yet: return empty state.
                return {
                    "count": 0,
                    "platform_filter": platform_filter or None,
                    "query": query or None,
                    "conversations": [],
                    "notice": "No social conversations available yet (account connected, inbox not synced or endpoint unavailable).",
                }
            rows = conv_data.get("conversations") or conv_data.get("data") or []
            if not isinstance(rows, list):
                rows = []

            for c in rows:
                if not isinstance(c, dict):
                    continue
                conv_id = c.get("id") or c.get("_id") or c.get("conversationId")
                if not conv_id:
                    continue
                platform = str(c.get("platform") or "").lower()
                username = c.get("username") or c.get("senderName") or c.get("name")
                account_id = str(c.get("accountId") or c.get("account_id") or "").strip()
                try:
                    detail_params: Dict[str, Any] = {"limit": 100, "sortOrder": "asc"}
                    if account_id:
                        detail_params["accountId"] = account_id
                    detail = await _get_with_base_fallback(
                        f"/inbox/conversations/{conv_id}/messages",
                        params=detail_params,
                    )
                    if detail is None:
                        # Backward compatibility path if message endpoint is unavailable.
                        detail = await _get_with_base_fallback(f"/inbox/conversations/{conv_id}")
                    if detail is None:
                        continue
                    msgs = detail.get("messages") or detail.get("data") or []
                    if not isinstance(msgs, list):
                        msgs = []
                    parsed_msgs: list[Dict[str, Any]] = []
                    for m in msgs[-12:]:
                        if not isinstance(m, dict):
                            continue
                        text = (
                            (m.get("message") if isinstance(m.get("message"), str) else None)
                            or (m.get("text") if isinstance(m.get("text"), str) else None)
                            or (m.get("content") if isinstance(m.get("content"), str) else None)
                            or ""
                        ).strip()
                        if not text:
                            continue
                        parsed_msgs.append({
                            "direction": str(
                                m.get("direction")
                                or m.get("type")
                                or ("outgoing" if m.get("fromMe") else "incoming")
                            ).lower(),
                            "text": text[:320],
                            "created_at": m.get("createdAt") or m.get("created_at") or m.get("timestamp"),
                        })

                    if query:
                        hay = " ".join([
                            str(username or "").lower(),
                            str((c.get("lastMessage") or c.get("last_message") or "")).lower(),
                            " ".join(str(m.get("text") or "").lower() for m in parsed_msgs),
                        ])
                        if query not in hay:
                            continue

                    conversations.append({
                        "conversation_id": str(conv_id),
                        "account_id": account_id or None,
                        "platform": platform,
                        "username": username,
                        "unread_count": c.get("unreadCount") or c.get("unread_count") or (1 if c.get("unread") else 0),
                        "updated_at": c.get("updatedAt") or c.get("updated_at"),
                        "last_message": c.get("lastMessage") or c.get("last_message"),
                        "messages": parsed_msgs,
                    })
                except Exception:
                    continue

    except httpx.HTTPStatusError as e:
        return {"error": f"Social inbox API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Failed to fetch social history: {e}"}

    return {
        "count": len(conversations[:limit]),
        "platform_filter": platform_filter or None,
        "query": query or None,
        "conversations": conversations[:limit],
    }


@tool(
    name="get_social_conversation_insights",
    description=(
        "Analyze recent social conversations to summarize who contacted the business and what they talked about. "
        "Returns top topics/intents, frequent contacts, and representative message snippets."
    ),
    parameters={
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "Optional platform filter (facebook, instagram, twitter, etc).",
            },
            "limit": {
                "type": "integer",
                "description": "How many conversations to analyze (default 30, max 50).",
            },
        },
    },
)
async def get_social_conversation_insights(ctx: ToolContext, args: Dict[str, Any]):
    limit = max(1, min(int(args.get("limit") or 30), 50))
    platform = str(args.get("platform") or "").strip().lower()

    history = await get_social_conversation_history(
        ctx,
        {"limit": limit, "platform": platform or None},
    )
    if history.get("error"):
        return history

    conversations = history.get("conversations") or []
    if not isinstance(conversations, list) or not conversations:
        return {
            "count": 0,
            "platform_filter": platform or None,
            "top_topics": [],
            "top_contacts": [],
            "message_snippets": [],
        }

    topic_rules = {
        "pricing": ("price", "pricing", "cost", "how much", "quote", "rate"),
        "availability": ("available", "stock", "in stock", "out of stock", "when can"),
        "delivery": ("deliver", "shipping", "pickup", "drop off", "dispatch"),
        "payment": ("pay", "payment", "invoice", "mpesa", "card", "bank"),
        "order_status": ("order", "tracking", "status", "eta", "received"),
        "support_issue": ("issue", "problem", "error", "not working", "failed"),
        "complaint": ("bad", "late", "angry", "refund", "disappointed", "complain"),
        "greeting_or_general": ("hello", "hi", "hey", "thanks", "thank you"),
    }

    topic_counts: Dict[str, int] = {k: 0 for k in topic_rules}
    contact_counts: Dict[str, int] = {}
    snippets: list[Dict[str, Any]] = []

    for conv in conversations:
        if not isinstance(conv, dict):
            continue
        uname = str(conv.get("username") or "unknown")
        contact_counts[uname] = contact_counts.get(uname, 0) + 1
        msgs = conv.get("messages") or []
        if not isinstance(msgs, list):
            continue
        for m in msgs:
            if not isinstance(m, dict):
                continue
            # Weight customer-side messages slightly more for intent discovery.
            direction = str(m.get("direction") or "").lower()
            text = str(m.get("text") or "").strip().lower()
            if not text:
                continue
            weight = 2 if "in" in direction else 1
            for topic, needles in topic_rules.items():
                if any(n in text for n in needles):
                    topic_counts[topic] += weight
            if len(snippets) < 20:
                snippets.append({
                    "platform": conv.get("platform"),
                    "username": conv.get("username"),
                    "direction": direction,
                    "text": str(m.get("text") or "")[:200],
                    "created_at": m.get("created_at"),
                })

    top_topics = [
        {"topic": t, "count": c}
        for t, c in sorted(topic_counts.items(), key=lambda kv: kv[1], reverse=True)
        if c > 0
    ][:6]
    top_contacts = [
        {"username": u, "conversation_count": c}
        for u, c in sorted(contact_counts.items(), key=lambda kv: kv[1], reverse=True)
    ][:10]

    return {
        "count": len(conversations),
        "platform_filter": platform or None,
        "top_topics": top_topics,
        "top_contacts": top_contacts,
        "message_snippets": snippets,
    }


@tool(
    name="configure_social_comment_autoreply",
    description=(
        "Create or update Social Inbox comment auto-reply setup. "
        "Supports Native AI all-post mode, ManyChat per-post mode, and hybrid mode "
        "with keyword rules and chained media/text steps."
    ),
    parameters={
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "description": "Turn comment auto-reply on/off."},
            "engine_mode": {
                "type": "string",
                "description": "native_ai_all_posts | manychat_per_post | hybrid",
            },
            "apply_all_posts": {"type": "boolean", "description": "Whether rules apply to all posts."},
            "manychat_post_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Post IDs to run ManyChat-style flows on when not using all posts.",
            },
            "default_message": {
                "type": "string",
                "description": "Fallback ManyChat text reply. Supports {name}.",
            },
            "reply_only_unreplied": {
                "type": "boolean",
                "description": "Only auto-reply when post/comment has no existing replies.",
            },
            "keyword_rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string"},
                        "message": {"type": "string"},
                    },
                },
                "description": "Ordered keyword->message rules.",
            },
            "chain_steps": {
                "type": "array",
                "description": "ManyChat-style chained replies. Supports text/image/video/file.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "message": {"type": "string"},
                        "media_url": {"type": "string"},
                        "delay_seconds": {"type": "integer"},
                    },
                },
            },
        },
    },
)
async def configure_social_comment_autoreply(ctx: ToolContext, args: Dict[str, Any]):
    user_doc = await ctx.db.users.find_one({"_id": ctx.business_id}, {"settings.zernio_comment_autoreply": 1})
    saved = (((user_doc or {}).get("settings") or {}).get("zernio_comment_autoreply") or {})

    def _clean_mode(v: Any) -> str:
        mode = str(v or saved.get("engine_mode") or "hybrid").strip().lower()
        return mode if mode in ("native_ai_all_posts", "manychat_per_post", "hybrid") else "hybrid"

    def _clean_rules(value: Any) -> list[dict]:
        out: list[dict] = []
        for item in (value if value is not None else saved.get("keyword_rules") or []):
            if not isinstance(item, dict):
                continue
            keyword = str(item.get("keyword") or "").strip()
            message = str(item.get("message") or "").strip()
            if keyword and message:
                out.append({"keyword": keyword, "message": message})
        return out[:25]

    def _clean_steps(value: Any) -> list[dict]:
        out: list[dict] = []
        for item in (value if value is not None else saved.get("chain_steps") or []):
            if not isinstance(item, dict):
                continue
            stype = str(item.get("type") or "text").strip().lower()
            if stype not in {"text", "image", "video", "file"}:
                stype = "text"
            message = str(item.get("message") or "").strip()
            media_url = str(item.get("media_url") or "").strip()
            delay_seconds = max(0, min(int(item.get("delay_seconds") or 0), 120))
            if stype == "text" and not message:
                continue
            if stype != "text" and not media_url and not message:
                continue
            out.append(
                {
                    "type": stype,
                    "message": message or None,
                    "media_url": media_url or None,
                    "delay_seconds": delay_seconds,
                }
            )
        return out[:12]

    settings = {
        "enabled": bool(args.get("enabled", saved.get("enabled", False))),
        "engine_mode": _clean_mode(args.get("engine_mode")),
        "apply_all_posts": bool(args.get("apply_all_posts", saved.get("apply_all_posts", True))),
        "post_ids": [str(x).strip() for x in (saved.get("post_ids") or []) if str(x).strip()],
        "manychat_post_ids": [
            str(x).strip()
            for x in (args.get("manychat_post_ids") if "manychat_post_ids" in args else saved.get("manychat_post_ids", []) or [])
            if str(x).strip()
        ],
        "default_message": str(
            args.get(
                "default_message",
                saved.get("default_message", "Thanks for your comment. We have seen it and will follow up shortly."),
            )
            or ""
        ).strip() or "Thanks for your comment. We have seen it and will follow up shortly.",
        "keyword_rules": _clean_rules(args.get("keyword_rules") if "keyword_rules" in args else None),
        "chain_steps": _clean_steps(args.get("chain_steps") if "chain_steps" in args else None),
        "reply_only_unreplied": bool(args.get("reply_only_unreplied", saved.get("reply_only_unreplied", True))),
    }

    await ctx.db.users.update_one(
        {"_id": ctx.business_id},
        {"$set": {"settings.zernio_comment_autoreply": settings}},
        upsert=False,
    )
    return {
        "status": "ok",
        "settings": settings,
        "summary": (
            f"Comment auto-reply {'enabled' if settings['enabled'] else 'disabled'} | "
            f"mode={settings['engine_mode']} | "
            f"manychat_posts={len(settings['manychat_post_ids'])} | "
            f"keywords={len(settings['keyword_rules'])} | "
            f"steps={len(settings['chain_steps'])}"
        ),
    }


@tool(
    name="audit_social_integrations",
    description=(
        "Run a health audit for connected social integrations and report data freshness, gaps, and fixes."
    ),
    parameters={"type": "object", "properties": {}},
)
async def audit_social_integrations(ctx: ToolContext, args: Dict[str, Any]):
    status = await integrations_status(ctx, {})
    diagnostics = status.get("social_diagnostics") if isinstance(status, dict) else None
    activity = status.get("social_activity") if isinstance(status, dict) else None
    overview = status.get("social_overview") if isinstance(status, dict) else None
    diag_status = (diagnostics or {}).get("status", "unknown")
    is_healthy = diag_status == "healthy"
    conversational_summary = (
        "Social channels are connected and syncing normally."
        if is_healthy
        else "Social channels are connected, but some data checks need attention."
    )
    return {
        "status": diag_status,
        "summary": conversational_summary,
        "connected_pages": overview or [],
        "activity": activity or {},
        "gaps": (diagnostics or {}).get("gaps", []),
        "recommended_actions": (diagnostics or {}).get("recommended_actions", []),
        # Technical details only when there's an issue.
        **({"technical_evidence": (diagnostics or {}).get("evidence", {})} if not is_healthy else {}),
        "checked_at": (diagnostics or {}).get("checked_at"),
    }


@tool(
    name="run_brand_audit",
    description=(
        "Run a practical brand and growth audit using CRM profile + social signals. "
        "Returns messaging scorecard, About Us rewrites, and prioritized 30-day actions."
    ),
    parameters={"type": "object", "properties": {}},
)
async def run_brand_audit(ctx: ToolContext, args: Dict[str, Any]):
    owner = await get_owner_info(ctx, {})
    integrations = await integrations_status(ctx, {})
    insights = await get_social_conversation_insights(ctx, {"limit": 30})

    business_name = str(owner.get("business_name") or "Your business").strip()
    business_type = str(owner.get("business_type") or "").strip() or "general business"
    country = str(owner.get("country") or "").strip()
    owner_name = str(owner.get("owner_name") or "").strip()
    products = owner.get("products_preview") or []
    social_pages = integrations.get("social_overview") or []
    social_diag = integrations.get("social_diagnostics") or {}
    social_activity = integrations.get("social_activity") or {}
    top_topics = insights.get("top_topics") or []

    has_social = bool(social_pages)
    has_inbox = int(social_activity.get("recent_inbox_conversations") or 0) > 0
    has_posts = int(social_activity.get("recent_posts") or 0) > 0
    products_count = len(products) if isinstance(products, list) else 0

    # Simple actionable scorecard
    scorecard = {
        "positioning_clarity": 80 if business_type and products_count > 0 else 55,
        "social_proof_signals": 75 if has_social and has_posts else 45,
        "customer_voice_signal": 80 if has_inbox else 50,
        "offer_specificity": 78 if products_count >= 3 else 58,
        "overall_readiness": 0,
    }
    scorecard["overall_readiness"] = int(round(
        (scorecard["positioning_clarity"]
         + scorecard["social_proof_signals"]
         + scorecard["customer_voice_signal"]
         + scorecard["offer_specificity"]) / 4
    ))

    # Topic-derived hooks
    topic_labels = [str(t.get("topic") or "") for t in top_topics if isinstance(t, dict)]
    primary_topic = topic_labels[0] if topic_labels else "customer outcomes"
    secondary_topic = topic_labels[1] if len(topic_labels) > 1 else "service reliability"

    about_us_base = (
        f"{business_name} helps customers with {business_type.lower()} solutions"
        + (f" in {country}" if country else "")
        + "."
    )
    about_us_rewrites = {
        "formal": (
            f"{about_us_base} We focus on consistent quality, transparent communication, and measurable results. "
            f"Our team{f', led by {owner_name},' if owner_name else ''} prioritizes {primary_topic.replace('_', ' ')} "
            f"and long-term client trust."
        ),
        "warm": (
            f"At {business_name}, we keep things simple: we listen, we respond fast, and we deliver real value. "
            f"Our customers choose us for dependable support, honest guidance, and better outcomes around {primary_topic.replace('_', ' ')}."
        ),
        "premium": (
            f"{business_name} is a premium {business_type.lower()} brand built around precision, responsiveness, and trust. "
            f"We combine proven execution with clear communication so clients see results in {primary_topic.replace('_', ' ')} and {secondary_topic.replace('_', ' ')}."
        ),
    }

    actions_30d = [
        {
            "priority": 1,
            "action": "Update About Us across website + social bios",
            "why": "Current brand story is not consistently reinforced across channels.",
            "expected_impact": "Higher trust and better conversion from profile visits.",
        },
        {
            "priority": 2,
            "action": "Publish 3 authority posts focused on top customer topics",
            "why": f"Recent conversations indicate interest in {primary_topic.replace('_', ' ')}.",
            "expected_impact": "Improved engagement quality and more qualified inquiries.",
        },
        {
            "priority": 3,
            "action": "Standardize first-response script for inbox leads",
            "why": "Consistent response style improves close rate and brand perception.",
            "expected_impact": "Faster response times and stronger lead conversion.",
        },
        {
            "priority": 4,
            "action": "Create one clear signature offer with CTA",
            "why": "Offer specificity is a key conversion lever.",
            "expected_impact": "More direct inquiries and fewer low-intent chats.",
        },
    ]

    return {
        "business": {
            "name": business_name,
            "type": business_type,
            "country": country or None,
            "connected_social_pages": social_pages,
        },
        "scorecard": scorecard,
        "social_health": {
            "status": social_diag.get("status"),
            "gaps": social_diag.get("gaps") or [],
            "checked_at": social_diag.get("checked_at"),
        },
        "top_customer_topics": top_topics,
        "about_us_rewrites": about_us_rewrites,
        "recommended_30_day_actions": actions_30d,
    }


@tool(
    name="run_competitor_benchmark",
    description=(
        "Benchmark competitors using web search + business context. "
        "Returns a focused competitor list, positioning gaps, and concrete actions."
    ),
    parameters={"type": "object", "properties": {}},
)
async def run_competitor_benchmark(ctx: ToolContext, args: Dict[str, Any]):
    from urllib.parse import urlparse

    owner = await get_owner_info(ctx, {})
    business_name = str(owner.get("business_name") or "Your business").strip()
    business_type = str(owner.get("business_type") or "").strip() or "business"
    country = str(owner.get("country") or "").strip()
    products = owner.get("products_preview") or []

    product_hints = ", ".join(str(p.get("name") or "") for p in (products[:3] if isinstance(products, list) else []))
    market_hint = f"{business_type} in {country}" if country else business_type
    query_seed = (
        f"Top {market_hint} competitors pricing features customer reviews "
        f"{product_hints}".strip()
    )

    # Multiple targeted pulls for better quality than one broad search.
    search_a = await web_search(ctx, {"query": query_seed, "max_results": 8})
    search_b = await web_search(ctx, {"query": f"{market_hint} alternatives to {business_name}", "max_results": 8})
    search_c = await web_search(ctx, {"query": f"{market_hint} best companies comparison", "max_results": 8})

    merged: list[Dict[str, Any]] = []
    for pack in (search_a, search_b, search_c):
        rows = pack.get("results") if isinstance(pack, dict) else []
        if not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict):
                merged.append(r)

    # Dedupe by domain and keep top unique results.
    seen_domains: set[str] = set()
    competitors: list[Dict[str, Any]] = []
    for r in merged:
        url = str(r.get("url") or "").strip()
        title = str(r.get("title") or "").strip()
        snippet = str(r.get("snippet") or "").strip()
        if not url:
            continue
        try:
            domain = (urlparse(url).netloc or "").lower().replace("www.", "")
        except Exception:
            domain = ""
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        if business_name.lower().replace(" ", "") in domain.replace("-", ""):
            continue
        competitors.append({
            "company": title[:100] or domain,
            "website": url,
            "notes": snippet[:240],
        })
        if len(competitors) >= 8:
            break

    # Heuristic opportunities based on search snippets.
    snippets_blob = " ".join(c.get("notes", "").lower() for c in competitors)
    opportunities: list[str] = []
    if "price" in snippets_blob or "afford" in snippets_blob:
        opportunities.append("Clarify pricing tiers and value outcomes on your About/offer pages.")
    if "delivery" in snippets_blob or "support" in snippets_blob:
        opportunities.append("Prominently position response speed, delivery reliability, and support quality.")
    if "review" in snippets_blob or "testimonial" in snippets_blob:
        opportunities.append("Add stronger social proof (testimonials/case outcomes) to trust surfaces.")
    if "free" in snippets_blob or "trial" in snippets_blob:
        opportunities.append("Test a low-friction entry offer (trial, starter package, or free consult).")
    if not opportunities:
        opportunities = [
            "Sharpen homepage/About positioning around a single clear value promise.",
            "Publish weekly authority content answering the top customer buying questions.",
            "Create one signature offer with a direct CTA and expected outcome."
        ]

    actions = [
        {"priority": 1, "action": "Differentiate core offer messaging", "detail": opportunities[0]},
        {"priority": 2, "action": "Strengthen trust and proof elements", "detail": opportunities[1] if len(opportunities) > 1 else opportunities[0]},
        {"priority": 3, "action": "Run 14-day competitor-informed campaign test", "detail": opportunities[2] if len(opportunities) > 2 else opportunities[-1]},
    ]

    return {
        "business": {
            "name": business_name,
            "type": business_type,
            "country": country or None,
        },
        "query_seed": query_seed,
        "competitors": competitors,
        "opportunities": opportunities,
        "recommended_actions": actions,
    }


@tool(
    name="run_weekly_operator_digest",
    description=(
        "Generate a weekly execution digest: key metrics, integration health, market context, "
        "and a concrete 3-item action plan with owners and success metrics."
    ),
    parameters={"type": "object", "properties": {}},
)
async def run_weekly_operator_digest(ctx: ToolContext, args: Dict[str, Any]):
    owner = await get_owner_info(ctx, {})
    analytics = await get_analytics_summary(ctx, {})
    trends = await get_revenue_trends(ctx, {"months": 3})
    social_audit = await audit_social_integrations(ctx, {})
    brand_audit = await run_brand_audit(ctx, {})
    benchmark = await run_competitor_benchmark(ctx, {})
    team_data = await list_team(ctx, {})

    team_members = team_data.get("members") if isinstance(team_data, dict) else []
    if not isinstance(team_members, list):
        team_members = []

    owner_name = str(owner.get("owner_name") or owner.get("business_name") or "Owner")
    sales_owner = owner_name
    marketing_owner = owner_name
    ops_owner = owner_name

    for m in team_members:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").lower()
        name = str(m.get("name") or "").strip() or owner_name
        if any(k in role for k in ("sales", "bd", "account")):
            sales_owner = name
        if any(k in role for k in ("marketing", "social", "growth")):
            marketing_owner = name
        if any(k in role for k in ("ops", "operation", "support")):
            ops_owner = name

    total_customers = int(analytics.get("total_customers") or 0) if isinstance(analytics, dict) else 0
    sales_today = float(analytics.get("sales_today") or 0) if isinstance(analytics, dict) else 0.0
    revenue_trend = trends.get("trend") if isinstance(trends, dict) else None
    trend_label = str((revenue_trend or {}).get("direction") or "unknown") if isinstance(revenue_trend, dict) else "unknown"

    social_status = str(social_audit.get("status") or "unknown") if isinstance(social_audit, dict) else "unknown"
    social_gaps = social_audit.get("gaps") if isinstance(social_audit, dict) else []
    if not isinstance(social_gaps, list):
        social_gaps = []

    competitor_actions = benchmark.get("recommended_actions") if isinstance(benchmark, dict) else []
    if not isinstance(competitor_actions, list):
        competitor_actions = []

    # Confidence and freshness scoring (simple, transparent heuristics).
    freshness_points = 0
    if isinstance(social_audit, dict) and social_audit.get("checked_at"):
        freshness_points += 1
    if isinstance(brand_audit, dict) and (brand_audit.get("social_health") or {}).get("checked_at"):
        freshness_points += 1
    if isinstance(analytics, dict):
        freshness_points += 1
    confidence = "high" if freshness_points >= 3 else ("medium" if freshness_points == 2 else "low")

    top_actions = [
        {
            "priority": 1,
            "owner": ops_owner,
            "task": "Close social data gaps and verify channel health",
            "why": social_gaps[0] if social_gaps else "Maintain healthy social signal quality for AI decisions.",
            "success_metric": "Social audit status is healthy and at least one active inbox thread is visible.",
        },
        {
            "priority": 2,
            "owner": marketing_owner,
            "task": "Ship one offer/positioning update and 3 social posts this week",
            "why": "Improve trust and conversion from profile/traffic touchpoints.",
            "success_metric": "3 posts published and measurable uplift in engagement vs prior week.",
        },
        {
            "priority": 3,
            "owner": sales_owner,
            "task": "Follow up top opportunities from recent conversations",
            "why": "Turn active demand signals into revenue quickly.",
            "success_metric": "At least 10 high-intent follow-ups sent and conversion outcomes tracked.",
        },
    ]

    if competitor_actions:
        ca = competitor_actions[0]
        if isinstance(ca, dict):
            top_actions[1]["why"] = str(ca.get("detail") or top_actions[1]["why"])

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "data_freshness": {
            "confidence": confidence,
            "sources": {
                "analytics": bool(isinstance(analytics, dict) and analytics),
                "social_audit_checked_at": (social_audit.get("checked_at") if isinstance(social_audit, dict) else None),
                "brand_audit_checked_at": ((brand_audit.get("social_health") or {}).get("checked_at") if isinstance(brand_audit, dict) else None),
            },
        },
        "snapshot": {
            "business": owner.get("business_name") or owner.get("owner_name"),
            "total_customers": total_customers,
            "sales_today": sales_today,
            "revenue_trend_direction": trend_label,
            "social_status": social_status,
            "team_count": len(team_members),
        },
        "top_actions": top_actions,
        "supporting_context": {
            "social_gaps": social_gaps,
            "competitor_opportunities": benchmark.get("opportunities") if isinstance(benchmark, dict) else [],
            "brand_scorecard": brand_audit.get("scorecard") if isinstance(brand_audit, dict) else {},
        },
    }


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
    from composio_service import shopify_orders_via_composio_or_proxy
    from datetime import timezone
    status = args.get("status", "any")
    limit  = min(int(args.get("limit", 25)), 250)
    days   = int(args.get("since_days", 7))
    since  = (datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        data = await shopify_orders_via_composio_or_proxy(
            ctx.business_id,
            status=str(status),
            limit=limit,
            created_at_min=since,
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
    from composio_service import shopify_products_via_composio_or_proxy
    limit  = min(int(args.get("limit", 50)), 250)
    status = args.get("status", "active")
    try:
        data = await shopify_products_via_composio_or_proxy(
            ctx.business_id,
            limit=limit,
            product_status=str(status),
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
    from composio_service import shopify_orders_via_composio_or_proxy
    from datetime import timezone
    days  = int(args.get("days", 30))
    since = (datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        data = await shopify_orders_via_composio_or_proxy(
            ctx.business_id,
            status="any",
            limit=250,
            created_at_min=since,
            financial_status="paid",
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
# STRIPE TOOLS (Composio packaged actions, REST proxy fallback)
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
    from composio_service import stripe_payment_intents_via_composio_or_proxy
    limit  = min(int(args.get("limit", 20)), 100)
    status = args.get("status", "succeeded")
    try:
        data = await stripe_payment_intents_via_composio_or_proxy(
            ctx.business_id,
            limit=limit,
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
    from composio_service import stripe_invoices_via_composio_or_proxy
    status = args.get("status", "open")
    limit  = min(int(args.get("limit", 20)), 100)
    try:
        data = await stripe_invoices_via_composio_or_proxy(
            ctx.business_id,
            limit=limit,
            status=str(status),
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
# KLAVIYO TOOLS (Composio packaged actions, REST proxy fallback)
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
    from composio_service import klaviyo_flows_via_composio_or_proxy
    status = args.get("status", "all")
    try:
        data = await klaviyo_flows_via_composio_or_proxy(
            ctx.business_id,
            status=str(status),
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
    from composio_service import klaviyo_metrics_via_composio_or_proxy
    limit = min(int(args.get("limit", 20)), 100)
    try:
        data = await klaviyo_metrics_via_composio_or_proxy(
            ctx.business_id,
            limit=limit,
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

    build_warning: Optional[str] = None
    try:
        from workflows.ai_builder import build_workflow_from_description
        wf_dict = await build_workflow_from_description(
            description=description,
            user=ctx.user,
        )
    except ValueError as exc:
        # Do not fail the user flow when the AI parser/output is imperfect.
        # Create a valid starter automation they can run/edit immediately.
        from workflows.ai_builder import fallback_workflow_create
        wf_dict = fallback_workflow_create(description)
        build_warning = f"AI builder fallback used: {exc}"
    except Exception as exc:
        logger.exception("[create_automation] AI builder failed")
        from workflows.ai_builder import fallback_workflow_create
        wf_dict = fallback_workflow_create(description)
        build_warning = "AI builder error; starter automation created instead."

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
        **({"warning": build_warning} if build_warning else {}),
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
# Visual assets — Gemini AI images for social posts/ads/carousels; .pptx via python-pptx

@tool(
    name="generate_creative_image",
    description=(
        "Generate a creative, conceptual, or lifestyle image using Google's Nano Banana AI model (via OpenRouter). "
        "Use this for standalone AI image generation — product lifestyle shots, mood scenes, conceptual backgrounds, "
        "people with products, brand imagery. "
        "For branded layouts, pass the returned image_url as product_image_url to `generate_ad_creative` or "
        "`generate_social_post` — the AI creates a professional branded design with this image."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Detailed visual description of the image. ALWAYS include: (1) camera angle — e.g. "
                    "'3/4 angle from slightly below' or 'eye-level editorial shot' or 'low-angle hero shot'; "
                    "(2) lighting — e.g. 'soft side-lit studio light with a subtle fill light'; "
                    "(3) composition — e.g. 'subject at left Rule-of-Thirds intersection, 50% negative space right'; "
                    "(4) style — e.g. 'clean editorial photography, Canva Pro aesthetic, minimal, premium'; "
                    "(5) what NOT to include — e.g. 'no text overlays, no busy backgrounds, no watermarks'. "
                    "Example: 'A premium dark glass perfume bottle at a 3/4 angle from slightly below, "
                    "soft studio side-lighting with a gradient shadow, placed at left Rule-of-Thirds, "
                    "deep navy background, 50% negative space, editorial photography, no text, no artifacts'."
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
        "note": "Use this URL as product_image_url in `generate_ad_creative` or `generate_social_post` when creating branded designs.",
    }


# ═════════════════════════════════════════════════════════════════════════════
# GEMINI DESIGN TOOLS — direct AI image generation for social posts & ads
# ═════════════════════════════════════════════════════════════════════════════


@tool(
    name="generate_social_post",
    description=(
        "Generate a professional social media post graphic using Gemini AI. "
        "Creates a polished, ready-to-post image with headline, subtext, CTA, and brand colors. "
        "Supports all major platforms (Instagram, Facebook, TikTok, LinkedIn, X). "
        "If a product image URL is available, the product becomes the hero of the design. "
        "Use this for any social media post — product launches, announcements, promotions, brand awareness."
    ),
    parameters={
        "type": "object",
        "required": ["headline"],
        "properties": {
            "headline": {
                "type": "string",
                "description": "Main headline text — bold, eye-catching, largest text on the design.",
            },
            "subtext": {
                "type": "string",
                "description": "Secondary text below the headline — smaller, supporting message.",
            },
            "cta": {
                "type": "string",
                "description": "Call-to-action text — e.g. 'Shop Now', 'Learn More', 'Link in Bio'.",
            },
            "brand_color": {
                "type": "string",
                "description": "Primary brand color as hex (e.g. '#4CD137'). Used as accent throughout the design. Get from get_owner_info.brand_primary_color.",
            },
            "style": {
                "type": "string",
                "description": "Optional style direction — e.g. 'minimalist', 'bold and vibrant', 'elegant', 'playful', 'corporate'.",
            },
            "product_image_url": {
                "type": "string",
                "description": "URL of a product photo to feature as the hero image. Get from get_product_images or list_products.",
            },
            "logo_url": {
                "type": "string",
                "description": "Brand logo URL — placed subtly in corner. Get from get_owner_info.default_logo_url.",
            },
            "platform": {
                "type": "string",
                "enum": [
                    "instagram_post", "instagram_story", "facebook_post",
                    "tiktok", "youtube_thumb", "linkedin", "x_post",
                    "general_square", "general_story", "general_landscape",
                ],
                "default": "instagram_post",
                "description": "Target platform — controls aspect ratio and format.",
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "pro"],
                "default": "pro",
                "description": "pro = best quality (slower), fast = quick generation. Use pro by default for posts.",
            },
            "trend_context": {
                "type": "string",
                "description": (
                    "2-3 sentence summary of current design trends or high-performing ad styles "
                    "researched via web_search BEFORE calling this tool. E.g. 'Bold typographic ads with "
                    "minimal product shots are dominating AI tool promotions in 2025. Dark backgrounds "
                    "with a single neon accent outperform light designs 3:1 in this category.' "
                    "This context shapes the design to feel current and scroll-stopping."
                ),
            },
        },
    },
)
async def generate_social_post(ctx: ToolContext, args: Dict[str, Any]):
    from gemini_design_service import generate_social_post as _gen

    # Auto-fetch brand kit if not provided
    brand_color = args.get("brand_color", "")
    logo_url = args.get("logo_url", "")
    if not brand_color or not logo_url:
        brand = await _load_brand_kit(ctx)
        if not brand_color:
            brand_color = brand.get("brand_primary_color", "")
        if not logo_url:
            logo_url = brand.get("default_logo_url", "")

    result = await _gen(
        headline=args.get("headline", ""),
        subtext=args.get("subtext", ""),
        cta=args.get("cta", ""),
        brand_color=brand_color,
        style=args.get("style", ""),
        product_description="",
        product_image_url=args.get("product_image_url"),
        logo_url=logo_url or None,
        platform=args.get("platform", "instagram_post"),
        quality=args.get("quality", "pro"),
        trend_context=args.get("trend_context", ""),
    )

    if result.get("error"):
        return {"error": result["error"]}

    image_url = result["image_url"]
    platform = args.get("platform", "instagram_post")
    name = (args.get("headline") or "Social Post")[:200]

    # Save to design library
    try:
        from saved_designs import insert_saved_design
        await insert_saved_design(
            ctx.db, ctx.business_id,
            name=name,
            asset_kind="image",
            file_url=image_url,
            thumbnail_url=image_url,
            source_tool="generate_social_post",
            conversation_id=ctx.user.get("_active_conversation_id"),
            platform=platform,
            content_type="post",
        )
    except Exception:
        logger.exception("[generate_social_post] saved_designs insert skipped")

    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![{name}]({image_url})" if image_url else "",
        "platform": platform,
    }


@tool(
    name="generate_ad_creative",
    description=(
        "Generate a high-converting ad creative using Gemini AI. Creates a scroll-stopping "
        "ad image with headline, offer, CTA button, and brand colors. Optimized for Facebook/Instagram ads "
        "but supports all platforms. If a product image is available, it becomes the hero. "
        "Use this for paid ad creatives — conversion ads, awareness ads, promotional ads."
    ),
    parameters={
        "type": "object",
        "required": ["headline"],
        "properties": {
            "headline": {
                "type": "string",
                "description": "Ad headline — bold, scroll-stopping, largest text. E.g. 'Summer Sale Is Here!'",
            },
            "offer": {
                "type": "string",
                "description": "Offer or value proposition — prominent, eye-catching. E.g. '50% OFF Everything', 'Buy 2 Get 1 Free'.",
            },
            "cta": {
                "type": "string",
                "description": "Call-to-action button text. E.g. 'Shop Now', 'Get Offer', 'Learn More'.",
                "default": "Shop Now",
            },
            "urgency": {
                "type": "string",
                "description": "Urgency cue — small text near CTA. E.g. 'Limited time only', 'While stocks last', 'Ends Sunday'.",
            },
            "brand_color": {
                "type": "string",
                "description": "Primary brand color as hex. Get from get_owner_info.brand_primary_color.",
            },
            "product_image_url": {
                "type": "string",
                "description": "Product photo URL — becomes the hero of the ad. Get from get_product_images.",
            },
            "logo_url": {
                "type": "string",
                "description": "Brand logo URL. Get from get_owner_info.default_logo_url.",
            },
            "platform": {
                "type": "string",
                "enum": [
                    "facebook_ad", "instagram_post", "instagram_story",
                    "tiktok", "youtube_thumb", "linkedin", "x_post",
                    "general_square", "general_story", "general_landscape",
                ],
                "default": "facebook_ad",
                "description": "Target platform — controls aspect ratio.",
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "pro"],
                "default": "pro",
                "description": "pro = best quality, fast = quicker. Use pro for ads.",
            },
            "trend_context": {
                "type": "string",
                "description": (
                    "2-3 sentence summary of current ad design trends researched via web_search "
                    "BEFORE calling this tool. Include what visual styles, hooks, or formats are "
                    "performing in this product niche right now. This is injected into the design "
                    "prompt to produce a current, scroll-stopping result."
                ),
            },
        },
    },
)
async def generate_ad_creative(ctx: ToolContext, args: Dict[str, Any]):
    from gemini_design_service import generate_ad_creative as _gen

    brand_color = args.get("brand_color", "")
    logo_url = args.get("logo_url", "")
    if not brand_color or not logo_url:
        brand = await _load_brand_kit(ctx)
        if not brand_color:
            brand_color = brand.get("brand_primary_color", "")
        if not logo_url:
            logo_url = brand.get("default_logo_url", "")

    result = await _gen(
        headline=args.get("headline", ""),
        offer=args.get("offer", ""),
        cta=args.get("cta", "Shop Now"),
        brand_color=brand_color,
        product_description="",
        product_image_url=args.get("product_image_url"),
        logo_url=logo_url or None,
        platform=args.get("platform", "facebook_ad"),
        urgency=args.get("urgency", ""),
        quality=args.get("quality", "pro"),
        trend_context=args.get("trend_context", ""),
    )

    if result.get("error"):
        return {"error": result["error"]}

    image_url = result["image_url"]
    platform = args.get("platform", "facebook_ad")
    name = (args.get("headline") or "Ad Creative")[:200]

    try:
        from saved_designs import insert_saved_design
        await insert_saved_design(
            ctx.db, ctx.business_id,
            name=name,
            asset_kind="image",
            file_url=image_url,
            thumbnail_url=image_url,
            source_tool="generate_ad_creative",
            conversation_id=ctx.user.get("_active_conversation_id"),
            platform=platform,
            content_type="ad",
        )
    except Exception:
        logger.exception("[generate_ad_creative] saved_designs insert skipped")

    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![{name}]({image_url})" if image_url else "",
        "platform": platform,
    }


@tool(
    name="generate_carousel_cover",
    description=(
        "Generate the cover slide (first slide) of a social media carousel post using Gemini AI. "
        "Creates a bold hook slide with a swipe cue that makes viewers want to swipe through. "
        "Sets the visual style (colors, typography, layout) for the full carousel."
    ),
    parameters={
        "type": "object",
        "required": ["headline"],
        "properties": {
            "headline": {
                "type": "string",
                "description": "Carousel hook headline — bold, makes people want to swipe. E.g. '5 Ways to...', 'The Secret to...', 'Before & After'",
            },
            "subtext": {
                "type": "string",
                "description": "Supporting text on the cover slide.",
            },
            "slide_count": {
                "type": "integer",
                "default": 5,
                "description": "Total number of slides in the carousel — shown as '1/N' on the cover.",
            },
            "brand_color": {
                "type": "string",
                "description": "Primary brand color as hex. Get from get_owner_info.brand_primary_color.",
            },
            "topic": {
                "type": "string",
                "description": "What the carousel is about — helps the AI set the right visual tone.",
            },
            "product_image_url": {
                "type": "string",
                "description": "Product photo URL to feature on the cover slide.",
            },
            "logo_url": {
                "type": "string",
                "description": "Brand logo URL.",
            },
            "platform": {
                "type": "string",
                "enum": [
                    "instagram_post", "facebook_post", "linkedin",
                    "general_square", "general_landscape",
                ],
                "default": "instagram_post",
                "description": "Target platform — carousels are typically square.",
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "pro"],
                "default": "pro",
            },
        },
    },
)
async def generate_carousel_cover(ctx: ToolContext, args: Dict[str, Any]):
    from gemini_design_service import generate_carousel_cover as _gen

    brand_color = args.get("brand_color", "")
    logo_url = args.get("logo_url", "")
    if not brand_color or not logo_url:
        brand = await _load_brand_kit(ctx)
        if not brand_color:
            brand_color = brand.get("brand_primary_color", "")
        if not logo_url:
            logo_url = brand.get("default_logo_url", "")

    result = await _gen(
        headline=args.get("headline", ""),
        subtext=args.get("subtext", ""),
        slide_count=int(args.get("slide_count", 5)),
        brand_color=brand_color,
        topic=args.get("topic", ""),
        product_image_url=args.get("product_image_url"),
        logo_url=logo_url or None,
        platform=args.get("platform", "instagram_post"),
        quality=args.get("quality", "pro"),
    )

    if result.get("error"):
        return {"error": result["error"]}

    image_url = result["image_url"]
    platform = args.get("platform", "instagram_post")
    name = (args.get("headline") or "Carousel")[:200]

    try:
        from saved_designs import insert_saved_design
        await insert_saved_design(
            ctx.db, ctx.business_id,
            name=name,
            asset_kind="image",
            file_url=image_url,
            thumbnail_url=image_url,
            source_tool="generate_carousel_cover",
            conversation_id=ctx.user.get("_active_conversation_id"),
            platform=platform,
            content_type="carousel",
        )
    except Exception:
        logger.exception("[generate_carousel_cover] saved_designs insert skipped")

    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![{name}]({image_url})" if image_url else "",
        "platform": platform,
    }


@tool(
    name="refine_design",
    description=(
        "Refine an existing AI-generated design based on user feedback. Uses the current design "
        "as a reference and applies the requested changes while keeping what works. "
        "Use this when the user wants to tweak a generated post/ad — change colors, adjust text, "
        "try a different style, or fix something they don't like."
    ),
    parameters={
        "type": "object",
        "required": ["original_image_url", "feedback"],
        "properties": {
            "original_image_url": {
                "type": "string",
                "description": "URL of the current design image to refine.",
            },
            "feedback": {
                "type": "string",
                "description": "What the user wants changed. E.g. 'Make the background darker', 'Change the headline to X', 'Make it more vibrant'.",
            },
            "headline": {
                "type": "string",
                "description": "Headline text to preserve/apply on the refined design.",
            },
            "brand_color": {
                "type": "string",
                "description": "Brand color to maintain in the refined design.",
            },
            "product_image_url": {
                "type": "string",
                "description": "Product photo URL — re-inject if the product was lost.",
            },
            "logo_url": {
                "type": "string",
                "description": "Brand logo URL.",
            },
            "platform": {
                "type": "string",
                "enum": [
                    "instagram_post", "instagram_story", "facebook_post", "facebook_ad",
                    "tiktok", "youtube_thumb", "linkedin", "x_post",
                    "general_square", "general_story", "general_landscape",
                ],
                "default": "instagram_post",
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "pro"],
                "default": "pro",
            },
        },
    },
)
async def refine_design(ctx: ToolContext, args: Dict[str, Any]):
    from gemini_design_service import regenerate_with_feedback

    brand_color = args.get("brand_color", "")
    logo_url = args.get("logo_url", "")
    if not brand_color or not logo_url:
        brand = await _load_brand_kit(ctx)
        if not brand_color:
            brand_color = brand.get("brand_primary_color", "")
        if not logo_url:
            logo_url = brand.get("default_logo_url", "")

    result = await regenerate_with_feedback(
        original_image_url=args.get("original_image_url", ""),
        feedback=args.get("feedback", ""),
        headline=args.get("headline", ""),
        brand_color=brand_color,
        product_image_url=args.get("product_image_url"),
        logo_url=logo_url or None,
        platform=args.get("platform", "instagram_post"),
        quality=args.get("quality", "pro"),
    )

    if result.get("error"):
        return {"error": result["error"]}

    image_url = result["image_url"]
    name = "Refined design"

    try:
        from saved_designs import insert_saved_design
        await insert_saved_design(
            ctx.db, ctx.business_id,
            name=name,
            asset_kind="image",
            file_url=image_url,
            thumbnail_url=image_url,
            source_tool="refine_design",
            conversation_id=ctx.user.get("_active_conversation_id"),
        )
    except Exception:
        logger.exception("[refine_design] saved_designs insert skipped")

    return {
        "success": True,
        "image_url": image_url,
        "markdown": f"![{name}]({image_url})" if image_url else "",
    }


@tool(
    name="plan_visual_presentation",
    description=(
        "STEP 1 of 2 — Plan a visual presentation deck and present the full outline to the user "
        "for review and approval BEFORE any images are generated. "
        "This avoids wasting Gemini image credits on a deck the user hasn't approved. "
        "Call this first whenever a user asks for a presentation, pitch deck, or slideshow. "
        "It returns a structured slide-by-slide plan showing: slide title, bullet points, "
        "and the image concept for each slide. "
        "After showing the plan, ask the user: 'Does this look good, or would you like to change anything?' "
        "Only call create_visual_presentation once the user explicitly approves."
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Main subject of the presentation.",
            },
            "audience": {
                "type": "string",
                "description": "Who this deck is for (e.g. 'investors', 'clients', 'internal team').",
            },
            "slides": {
                "type": "array",
                "description": (
                    "The complete planned slide list. Each object must have: "
                    "title (str), body (list of 3-5 punchy bullet strings — no filler), "
                    "image_concept (str — vivid 1-sentence description of the background visual), "
                    "is_title (bool — True only for the first cover slide). "
                    "Plan 6-10 slides. Start with a cover, end with a strong CTA or summary."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "title":         {"type": "string"},
                        "body":          {"type": "array", "items": {"type": "string"}},
                        "image_concept": {"type": "string"},
                        "is_title":      {"type": "boolean"},
                    },
                    "required": ["title", "body", "image_concept"],
                },
            },
            "style_note": {
                "type": "string",
                "description": "Visual tone for all images (e.g. 'dark cinematic', 'bright modern', 'luxury minimal').",
            },
        },
        "required": ["topic", "slides"],
    },
)
async def plan_visual_presentation(ctx: ToolContext, args: Dict[str, Any]):
    topic      = (args.get("topic") or "Presentation").strip()
    audience   = (args.get("audience") or "").strip()
    slides     = args.get("slides") or []
    style_note = (args.get("style_note") or "cinematic dark professional").strip()

    if not slides:
        return {"error": "slides list is required."}

    return {
        "success": True,
        "plan_ready": True,
        "topic": topic,
        "audience": audience,
        "style_note": style_note,
        "slide_count": len(slides),
        "slides": slides,
        "awaiting_approval": True,
        "note": (
            f"Deck plan ready — {len(slides)} slides. "
            "Show this plan to the user and ask for approval or changes. "
            "Do NOT call create_visual_presentation until the user confirms."
        ),
    }


@tool(
    name="create_visual_presentation",
    description=(
        "STEP 2 of 2 — Generate the actual visual PowerPoint (.pptx) ONLY after the user has "
        "approved the plan from plan_visual_presentation. "
        "Each slide gets a unique Gemini AI-generated full-bleed background image (award-winning, "
        "cinematic quality), with the slide title and bullets overlaid on a semi-transparent panel. "
        "Never call this tool speculatively — only after explicit user approval of the slide plan. "
        "Pass the exact slides array from the approved plan, enriched with a detailed image_prompt "
        "per slide (expand image_concept into a rich, specific generation prompt)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Main subject of the presentation.",
            },
            "slides": {
                "type": "array",
                "description": (
                    "The APPROVED slide list from plan_visual_presentation, with image_prompt "
                    "added to each slide (expand the image_concept into a rich, specific, "
                    "award-winning image generation prompt — include lighting, mood, composition, "
                    "color palette, no text, no people unless essential). "
                    "Each slide: title, body (list[str]), image_prompt (str), is_title (bool)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "title":        {"type": "string"},
                        "body":         {"type": "array", "items": {"type": "string"}},
                        "image_prompt": {"type": "string"},
                        "is_title":     {"type": "boolean"},
                    },
                    "required": ["title", "image_prompt"],
                },
            },
            "brand_color": {
                "type": "string",
                "description": "Hex colour code for the accent bar (e.g. '#4CD137'). From get_owner_info.",
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "pro"],
                "description": "'pro' for final delivery (recommended), 'fast' for draft preview.",
            },
        },
        "required": ["topic", "slides"],
    },
)
async def create_visual_presentation(ctx: ToolContext, args: Dict[str, Any]):
    from presentation_service import create_visual_presentation_async

    topic       = (args.get("topic") or "Presentation").strip()
    slides_plan = args.get("slides") or []
    brand_color = (args.get("brand_color") or "").strip()
    quality     = (args.get("quality") or "pro").strip()

    if not slides_plan:
        return {"error": "slides list is required — pass the approved plan from plan_visual_presentation."}
    if len(slides_plan) > 15:
        slides_plan = slides_plan[:15]

    # Auto-fetch brand color + business name from owner info
    try:
        owner = await get_owner_info(ctx, {})
        if not brand_color:
            brand_color = owner.get("brand_primary_color") or ""
        business_name = str(owner.get("business_name") or "My Business").strip()
    except Exception:
        business_name = "My Business"

    result = await create_visual_presentation_async(
        topic=topic,
        slides_plan=slides_plan,
        business_name=business_name,
        brand_color=brand_color,
        quality=quality,
    )

    if not result.get("success"):
        return {"error": result.get("error", "Presentation generation failed.")}

    return {
        "success": True,
        "url": result["url"],
        "slide_count": result["slide_count"],
        "images_generated": result["images_generated"],
        "topic": topic,
        "slides": result.get("slides", slides_plan),
        "image_urls": result.get("image_urls", []),
    }


@tool(
    name="regenerate_slide",
    description=(
        "Regenerate a SINGLE slide's background image in an existing visual presentation, "
        "based on the user's feedback/instruction for that specific slide. "
        "Only ONE new Gemini image is generated (cheap). The full .pptx is rebuilt with "
        "that one slide swapped and re-uploaded. "
        "Use this when the user says things like 'redo slide 3', 'change slide 2 to show a sunset', "
        "'make slide 4 more dramatic', etc. "
        "You need the slides array and image_urls array from the previous create_visual_presentation result."
    ),
    parameters={
        "type": "object",
        "properties": {
            "slide_index": {
                "type": "integer",
                "description": (
                    "0-based index of the slide to regenerate. "
                    "If user says 'slide 3', use index 2. If 'slide 1', use 0."
                ),
            },
            "instruction": {
                "type": "string",
                "description": (
                    "The user's instruction for what to change on this slide's background image. "
                    "E.g. 'make it more dramatic with stormy weather', 'use a forest background', "
                    "'change to a luxury hotel lobby'. Be descriptive."
                ),
            },
            "slides": {
                "type": "array",
                "description": "The full slides array from the previous create_visual_presentation result.",
                "items": {"type": "object"},
            },
            "image_urls": {
                "type": "array",
                "description": "The image_urls array from the previous create_visual_presentation result.",
                "items": {"type": "string"},
            },
            "topic": {
                "type": "string",
                "description": "The presentation topic (from the previous result).",
            },
            "brand_color": {
                "type": "string",
                "description": "Hex brand colour (from get_owner_info or previous result).",
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "pro"],
                "description": "'pro' for final quality (default), 'fast' for quick preview.",
            },
        },
        "required": ["slide_index", "instruction", "slides", "image_urls"],
    },
)
async def regenerate_slide(ctx: ToolContext, args: Dict[str, Any]):
    from presentation_service import regenerate_single_slide_async

    slide_index  = int(args.get("slide_index", 0))
    instruction  = (args.get("instruction") or "").strip()
    slides_plan  = args.get("slides") or []
    image_urls   = args.get("image_urls") or []
    topic        = (args.get("topic") or "Presentation").strip()
    brand_color  = (args.get("brand_color") or "").strip()
    quality      = (args.get("quality") or "pro").strip()

    if not slides_plan:
        return {"error": "slides array is required — pass it from the previous create_visual_presentation result."}
    if not image_urls:
        return {"error": "image_urls array is required — pass it from the previous create_visual_presentation result."}
    if not instruction:
        return {"error": "instruction is required — describe what to change on this slide."}

    if not brand_color:
        try:
            owner = await get_owner_info(ctx, {})
            brand_color = owner.get("brand_primary_color") or ""
        except Exception:
            pass

    result = await regenerate_single_slide_async(
        slides_plan=slides_plan,
        image_urls=image_urls,
        slide_index=slide_index,
        instruction=instruction,
        brand_color=brand_color,
        quality=quality,
        topic=topic,
    )

    if not result.get("success"):
        return {"error": result.get("error", "Slide regeneration failed.")}

    return {
        "success": True,
        "url": result["url"],
        "slide_count": result["slide_count"],
        "images_generated": result["images_generated"],
        "regenerated_slide_index": result["regenerated_slide_index"],
        "regenerated_slide_title": result["regenerated_slide_title"],
        "topic": topic,
        "slides": result["slides"],
        "image_urls": result["image_urls"],
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
        "(if present) is the real product to feature.\n\n"
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
        "6. Do NOT draw, invent, or place any logo, brand mark, icon, or watermark. "
        "The real brand logo will be composited on top afterwards. "
        "Leave a visually clean, uncluttered zone in the bottom-right corner "
        "(roughly 15% of canvas width) — no text, no pattern, no dark imagery there.\n\n"
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

    reference_url = ""
    template_name = fact_pack.get("locked_template_name") or ""

    prompt = _compose_recreate_prompt(
        fact_pack,
        headline=headline, tagline=tagline, cta=cta,
        offer=offer, website=website, extra_notes=extra_notes,
    )

    result = await recreate_design_from_reference(
        reference_image_url=reference_url,
        prompt=prompt,
        product_image_url=product_image_url,
        logo_url=None,  # don't send — Gemini redraws logos; PIL composites the real one below
        format=fmt,
        quality=quality,
    )
    if result.get("error"):
        return {"error": result["error"]}

    image_url = result.get("image_url") or ""
    if not image_url:
        return {"error": "Renderer returned no image URL."}

    # PIL-composite the real pixel-perfect brand logo onto the finished design.
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
    width_pct: float = 0.13,
    margin_pct: float = 0.04,
) -> Optional[str]:
    """Paste the brand logo onto a rendered design and upload the result.

    Adds a smart background pill behind the logo so it stays readable on any
    background colour. Both inputs are fetched over HTTP; the composite is
    re-uploaded to S3 via ``S3Handler.upload_file``.

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
        from PIL import Image as _Image, ImageDraw as _ImageDraw
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
            pad = max(6, int(base.width * 0.015))  # inner padding around logo

            if position == "top-left":
                lx, ly = margin + pad, margin + pad
            elif position == "top-right":
                lx = base.width - logo.width - margin - pad
                ly = margin + pad
            elif position == "bottom-left":
                lx = margin + pad
                ly = base.height - logo.height - margin - pad
            else:  # bottom-right (default)
                lx = base.width - logo.width - margin - pad
                ly = base.height - logo.height - margin - pad

            # Sample the average brightness of the region where the logo will sit.
            sample_box = (
                max(0, lx - pad), max(0, ly - pad),
                min(base.width,  lx + logo.width  + pad),
                min(base.height, ly + logo.height + pad),
            )
            region = base.crop(sample_box).convert("RGB")
            pixels = list(region.getdata())
            avg_brightness = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels) / max(1, len(pixels))

            # Choose a contrasting pill background (semi-transparent)
            if avg_brightness > 140:
                pill_color = (0, 0, 0, 130)       # dark pill on light bg
            else:
                pill_color = (255, 255, 255, 130)  # light pill on dark bg

            # Draw the rounded-rectangle background pill
            pill_w = logo.width + pad * 2
            pill_h = logo.height + pad * 2
            pill_x = lx - pad
            pill_y = ly - pad
            radius = max(4, pad)

            pill = _Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = _ImageDraw.Draw(pill)
            draw.rounded_rectangle(
                [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
                radius=radius,
                fill=pill_color,
            )
            base = _Image.alpha_composite(base, pill)

            # Composite logo on top of the pill
            base.alpha_composite(logo, dest=(lx, ly))

            buf = _io.BytesIO()
            base.convert("RGB").save(buf, format="PNG", optimize=True)
            return buf.getvalue()

        composed = await _asyncio.get_event_loop().run_in_executor(None, _do_composite)
        b64 = _b64.b64encode(composed).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"
        fn = f"logo-composite-{uuid.uuid4()}.png"
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
    name="_presign_s3_url",
    description="Return a publicly accessible URL for a private S3 object.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The S3 URL to presign"}
        },
        "required": ["url"],
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

        # Prefer backend proxy — external services can call our own endpoint
        backend_url = (
            _os.environ.get("BACKEND_PUBLIC_URL")
            or _os.environ.get("PUBLIC_BASE_URL")
            or ""
        ).rstrip("/")
        if backend_url and key:
            proxy = f"{backend_url}/api/images/s3/{key}"
            logger.debug("[_make_accessible_url] Using proxy URL for %s → %s", key[:60], proxy[:80])
            return proxy

        # Fallback: presign directly against S3
        import asyncio as _asyncio
        presigned = await _asyncio.get_event_loop().run_in_executor(
            None,
            lambda: S3Handler.generate_presigned_get_url(bucket, key, expires_in=3600),
        )
        return presigned
    except Exception as _e:
        logger.warning("[_make_accessible_url] Could not build accessible URL for %s: %s", url[:80], _e)
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
        "Pass format to match the platform canvas you chose (square / story / landscape / portrait). "
        "The returned background_url is the enhanced product photo — pass it as product_image_url "
        "to generate_ad_creative or generate_social_post to produce the final branded graphic."
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
                "next_step": "Pass this background_url as product_image_url to generate_ad_creative or generate_social_post to create the final branded design.",
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
            "next_step": "Pass this background_url as product_image_url to generate_ad_creative or generate_social_post to create the final branded design.",
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
        "next_step": "Pass this background_url as product_image_url to generate_ad_creative or generate_social_post to create the final branded design.",
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
        "Create a professional PowerPoint presentation (.pptx). "
        "Slide layouts: title, content, two_column, quote, key_points, section, image_text, ending. "
        "Color themes: dark (deep green), light (white), navy (blue), warm (amber). "
        "Deck styles change the actual geometry, fonts, and structural layout — not just colour: "
        "ribbon, minimal, magazine, split, spotlight. "
        "IMPORTANT: Do NOT pass deck_style or theme unless the user explicitly asks for a specific look. "
        "When omitted, the system automatically pairs a random layout+colour preset so every deck looks unique. "
        "First slide becomes title; last slide gets an ending unless already specified."
    ),
    parameters={
        "type": "object",
        "required": ["title", "slides_data"],
        "properties": {
            "title": {
                "type": "string",
                "description": "The main title of the presentation.",
            },
            "deck_style": {
                "type": "string",
                "description": (
                    "Visual layout family — changes shapes, alignment, fonts, geometry. "
                    "Omit (or pass \"auto\") unless user asks for a specific style. "
                    "ribbon: bar + decorative shapes. minimal: whitespace + centered. "
                    "magazine: editorial serif + side panel. split: big colour block hero. spotlight: framed card."
                ),
                "enum": ["auto", "ribbon", "minimal", "magazine", "split", "spotlight"],
            },
            "theme": {
                "type": "string",
                "description": (
                    "Colour palette. Omit (or pass \"auto\") unless user specifies a colour. "
                    "dark: deep forest green. light: white/cream. navy: dark blue. warm: amber/brown."
                ),
                "enum": ["auto", "dark", "light", "navy", "warm"],
            },
            "tagline": {
                "type": "string",
                "description": "Optional closing tagline shown on the ending slide (e.g. 'Let\'s grow together').",
            },
            "slides_data": {
                "type": "array",
                "description": (
                    "List of slide objects. Each has a 'layout' key plus layout-specific keys. "
                    "Layouts: 'title' (title, subtitle), 'content' (title, content[]), 'section' (title), "
                    "'two_column' (title, left_items[], right_items[], left_header?, right_header?), "
                    "'quote' (quote, attribution?), 'key_points' (title, points[{title, description}]), "
                    "'image_text' (title, content[], image_url?), 'ending' (auto-generated). "
                    "Default layout is 'content'. First slide auto-becomes 'title', last auto-gets 'ending'."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "layout": {
                            "type": "string",
                            "enum": ["title", "section", "content", "two_column", "quote", "image_text", "key_points", "ending"],
                        },
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "content": {"type": "array", "items": {"type": "string"}},
                        "left_items": {"type": "array", "items": {"type": "string"}},
                        "right_items": {"type": "array", "items": {"type": "string"}},
                        "left_header": {"type": "string"},
                        "right_header": {"type": "string"},
                        "quote": {"type": "string"},
                        "attribution": {"type": "string"},
                        "points": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                        "image_url": {"type": "string"},
                    },
                },
            },
        },
    },
)
async def create_presentation(ctx: ToolContext, args: Dict[str, Any]):
    from presentation_service import (
        generate_presentation_with_upload,
        normalize_deck_style,
        pick_deck_preset,
        pick_deck_style_random,
    )
    title = args.get("title", "Presentation")
    slides_data = args.get("slides_data", [])
    tagline = args.get("tagline", "")

    raw_style = args.get("deck_style")
    raw_theme = args.get("theme")

    _auto_style = not raw_style or str(raw_style).strip().lower() in ("", "auto", "automatic", "random")
    _auto_theme = not raw_theme or str(raw_theme).strip().lower() in ("", "auto", "automatic", "random")

    if _auto_style and _auto_theme:
        # Pick a fully-curated preset: BOTH layout AND colour differ each time
        deck_style, theme_name = pick_deck_preset()
    elif _auto_style:
        theme_name = str(raw_theme).strip().lower()
        deck_style = pick_deck_style_random()
    elif _auto_theme:
        deck_style = normalize_deck_style(str(raw_style))
        theme_name = "dark"
    else:
        deck_style = normalize_deck_style(str(raw_style))
        theme_name = str(raw_theme).strip().lower()

    owner = await ctx.db.users.find_one({"_id": ctx.business_id})
    business_name = owner.get("business_name") or owner.get("owner_name") or "My Business" if owner else "My Business"

    result = await generate_presentation_with_upload(
        title,
        slides_data,
        business_name,
        theme_name=theme_name,
        tagline=tagline,
        deck_style=deck_style,
    )

    if result.get("error"):
        return {"error": result["error"]}

    url = result.get("url")
    thumb_url = result.get("thumbnail_url")
    if url:
        try:
            from saved_designs import insert_saved_design

            await insert_saved_design(
                ctx.db,
                ctx.business_id,
                name=(title or "Presentation")[:200],
                asset_kind="pptx",
                file_url=url,
                thumbnail_url=thumb_url,
                source_tool="create_presentation",
                conversation_id=ctx.user.get("_active_conversation_id"),
            )
        except Exception:
            logger.exception("[create_presentation] saved_designs insert skipped")

    # Build markdown with image preview (chat renders ![...](...) as visual card with download)
    md_parts = []
    if thumb_url:
        md_parts.append(f"![{title}]({thumb_url})")
    if url:
        md_parts.append(f"📊 **[Download Presentation: {title}]({url})**")
    markdown = "\n\n".join(md_parts)

    return {
        "success": True,
        "pptx_url": url,
        "thumbnail_url": thumb_url,
        "deck_style": result.get("deck_style") or deck_style,
        "markdown": markdown,
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
# META ADS — LIVE CAMPAIGN MANAGEMENT (Marketing API)
# ═════════════════════════════════════════════════════════════════════════════


@tool(
    name="list_meta_campaigns",
    description=(
        "List live Meta (Facebook/Instagram) ad campaigns in the connected ad account. "
        "Returns id, name, status, objective, daily_budget, start/stop times. "
        "Use status_filter=ACTIVE to see only running campaigns, PAUSED for paused ones, ALL for everything."
    ),
    parameters={
        "type": "object",
        "properties": {
            "status_filter": {
                "type": "string",
                "description": "ACTIVE | PAUSED | ARCHIVED | DELETED | ALL (default ALL)",
            },
            "limit": {"type": "integer", "description": "Max campaigns to return (default 50)"},
        },
    },
)
async def list_meta_campaigns(ctx: ToolContext, args: Dict[str, Any]):
    from meta_ads_service import list_campaigns, _is_configured
    if not _is_configured():
        return {
            "error": "Meta Ads not configured. Set META_ADS_ACCESS_TOKEN and META_ADS_ACCOUNT_ID env vars.",
            "configured": False,
        }
    campaigns = await list_campaigns(
        status_filter=args.get("status_filter"),
        limit=min(int(args.get("limit") or 50), 100),
    )
    return {"count": len(campaigns), "campaigns": campaigns}


@tool(
    name="get_meta_campaign_performance",
    description=(
        "Get real engagement and spend metrics for Meta ad campaigns from the Marketing API. "
        "Returns spend, impressions, clicks, CTR, CPC, CPM, reach, and ROAS for each campaign. "
        "Leave campaign_id empty to get performance across ALL campaigns in the account. "
        "Use days=7 for last week, days=30 for last month."
    ),
    parameters={
        "type": "object",
        "properties": {
            "campaign_id": {
                "type": "string",
                "description": "Specific campaign ID to fetch. Leave empty for all campaigns.",
            },
            "days": {
                "type": "integer",
                "description": "Lookback window in days: 1, 3, 7, 14, 30, or 90. Default 7.",
            },
        },
    },
)
async def get_meta_campaign_performance(ctx: ToolContext, args: Dict[str, Any]):
    from meta_ads_service import get_campaign_insights, get_account_insights, _is_configured
    if not _is_configured():
        return {
            "error": "Meta Ads not configured. Set META_ADS_ACCESS_TOKEN and META_ADS_ACCOUNT_ID env vars.",
            "configured": False,
        }
    days = int(args.get("days") or 7)
    campaign_id = (args.get("campaign_id") or "").strip()
    if campaign_id:
        result = await get_campaign_insights(campaign_id, days=days)
        if not result:
            return {"error": f"No insights found for campaign {campaign_id} in the last {days} days."}
        return result
    else:
        rows = await get_account_insights(days=days)
        total_spend = sum(r["spend"] for r in rows)
        total_clicks = sum(r["clicks"] for r in rows)
        total_impressions = sum(r["impressions"] for r in rows)
        avg_roas = round(
            sum(r["roas"] * r["spend"] for r in rows) / total_spend, 2
        ) if total_spend > 0 else 0.0
        rows_sorted = sorted(rows, key=lambda x: x["spend"], reverse=True)
        return {
            "period_days": days,
            "campaign_count": len(rows),
            "totals": {
                "spend": round(total_spend, 2),
                "clicks": total_clicks,
                "impressions": total_impressions,
                "avg_roas": avg_roas,
            },
            "campaigns": rows_sorted,
        }


@tool(
    name="update_meta_campaign_status",
    description=(
        "Pause, reactivate, or delete a Meta (Facebook/Instagram) ad campaign via the Marketing API. "
        "Use status=PAUSED to stop a campaign that is underperforming or overspending. "
        "Use status=ACTIVE to re-enable a paused campaign. "
        "Use status=DELETED to permanently remove it (irreversible). "
        "Always confirm the campaign name and reason before calling this. This is a destructive action."
    ),
    parameters={
        "type": "object",
        "properties": {
            "campaign_id": {"type": "string", "description": "The Meta campaign ID to update"},
            "status": {
                "type": "string",
                "description": "New status: ACTIVE | PAUSED | DELETED",
            },
            "reason": {
                "type": "string",
                "description": "Brief reason for the status change (for audit log)",
            },
        },
        "required": ["campaign_id", "status"],
    },
    destructive=True,
)
async def update_meta_campaign_status(ctx: ToolContext, args: Dict[str, Any]):
    from meta_ads_service import update_campaign_status, _is_configured
    if not _is_configured():
        return {
            "error": "Meta Ads not configured. Set META_ADS_ACCESS_TOKEN and META_ADS_ACCOUNT_ID env vars.",
            "configured": False,
        }
    campaign_id = (args.get("campaign_id") or "").strip()
    status = (args.get("status") or "").strip()
    if not campaign_id or not status:
        return {"error": "campaign_id and status are required"}

    result = await update_campaign_status(campaign_id, status)

    if result.get("success"):
        await ctx.db.meta_ads_campaign_drafts.update_one(
            {"user_id": ctx.business_id, "meta_campaign_id": campaign_id},
            {"$set": {"status": status.lower(), "updated_at": datetime.utcnow()}},
        )
        logger.info(
            "[meta_ads] Campaign %s set to %s by agent. Reason: %s",
            campaign_id, status, args.get("reason", "not provided"),
        )
    return result


@tool(
    name="update_meta_campaign_budget",
    description=(
        "Update the daily budget of a live Meta (Facebook/Instagram) ad campaign. "
        "Provide new_daily_budget as a dollar amount (e.g. 25.00 means $25/day). "
        "Use this to scale up a well-performing campaign or reduce spend on a costly one. "
        "Always state the reason and current performance before adjusting."
    ),
    parameters={
        "type": "object",
        "properties": {
            "campaign_id": {"type": "string", "description": "The Meta campaign ID to update"},
            "new_daily_budget": {
                "type": "number",
                "description": "New daily budget in dollars (e.g. 25.00 = $25/day)",
            },
            "reason": {
                "type": "string",
                "description": "Brief reason for the budget change (for audit log)",
            },
        },
        "required": ["campaign_id", "new_daily_budget"],
    },
    destructive=True,
)
async def update_meta_campaign_budget(ctx: ToolContext, args: Dict[str, Any]):
    from meta_ads_service import update_campaign_budget, _is_configured
    if not _is_configured():
        return {
            "error": "Meta Ads not configured. Set META_ADS_ACCESS_TOKEN and META_ADS_ACCOUNT_ID env vars.",
            "configured": False,
        }
    campaign_id = (args.get("campaign_id") or "").strip()
    dollars = float(args.get("new_daily_budget") or 0)
    if not campaign_id or dollars <= 0:
        return {"error": "campaign_id and a positive new_daily_budget (dollars) are required"}

    cents = int(dollars * 100)
    result = await update_campaign_budget(campaign_id, cents)
    if result.get("success"):
        logger.info(
            "[meta_ads] Campaign %s budget set to $%.2f by agent. Reason: %s",
            campaign_id, dollars, args.get("reason", "not provided"),
        )
    return result


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

_GMAIL_KEY     = "gmail"       # Composio toolkit slug (was: google-mail via Nango)
_MICROSOFT_KEY = "outlook"     # Composio toolkit slug (was: microsoft via Nango)
_SLACK_KEY     = "slack"       # Composio toolkit slug (same as Nango)


def _slack_api_error(data: Dict[str, Any]) -> Optional[str]:
    """Slack returns HTTP 200 with {\"ok\": false, \"error\": \"...\"} on failures."""
    if data.get("ok") is True:
        return None
    return str(data.get("error") or "slack_api_error")


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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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


# ── Slack tools (Composio packaged actions, Slack Web API proxy fallback) ────


@tool(
    name="slack_workspace_info",
    description=(
        "Verify the Slack connection and show workspace identity. Calls auth.test — "
        "returns team name, team_id, workspace URL, and the authenticated bot/user. "
        "Use this before posting to confirm Slack is linked."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
)
async def slack_workspace_info(ctx: ToolContext, args: Dict[str, Any]):
    from composio_service import slack_auth_test_via_composio_or_proxy
    try:
        data = await slack_auth_test_via_composio_or_proxy(ctx.business_id)
    except RuntimeError as e:
        return {"error": str(e)}
    err = _slack_api_error(data)
    if err:
        return {"error": err, "slack_response": data}
    return {
        "ok": True,
        "team": data.get("team"),
        "team_id": data.get("team_id"),
        "url": data.get("url"),
        "user": data.get("user"),
        "user_id": data.get("user_id"),
        "bot_id": data.get("bot_id"),
    }


@tool(
    name="slack_list_channels",
    description=(
        "List Slack channels the token can see (public and, if permitted, private). "
        "Returns id, name, is_private, is_archived, num_members. Use channel `id` "
        "with slack_post_message (e.g. C123…). Paginates automatically up to ~2000 rows."
    ),
    parameters={
        "type": "object",
        "properties": {
            "include_private": {
                "type": "boolean",
                "description": "Include private channels (default true). Set false for public only.",
            },
            "include_archived": {
                "type": "boolean",
                "description": "Include archived channels (default false).",
            },
            "page_limit": {
                "type": "integer",
                "description": "Max Slack API pages to fetch (1–15, default 10). Each page up to 200 channels.",
            },
        },
    },
)
async def slack_list_channels(ctx: ToolContext, args: Dict[str, Any]):
    from composio_service import slack_conversations_list_via_composio_or_proxy
    include_private = args.get("include_private", True)
    include_archived = bool(args.get("include_archived", False))
    max_pages = min(max(int(args.get("page_limit") or 10), 1), 15)
    types = "public_channel,private_channel" if include_private else "public_channel"

    channels: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    for _ in range(max_pages):
        try:
            data = await slack_conversations_list_via_composio_or_proxy(
                ctx.business_id,
                types=types,
                limit=200,
                exclude_archived=not include_archived,
                cursor=cursor,
            )
        except RuntimeError as e:
            return {"error": str(e), "channels_partial": channels}
        err = _slack_api_error(data)
        if err:
            return {"error": err, "slack_response": data, "channels_partial": channels}
        for ch in data.get("channels") or []:
            if not isinstance(ch, dict):
                continue
            channels.append({
                "id": ch.get("id"),
                "name": ch.get("name"),
                "is_private": ch.get("is_private"),
                "is_archived": ch.get("is_archived"),
                "num_members": ch.get("num_members"),
            })
        cursor = (data.get("response_metadata") or {}).get("next_cursor") or None
        if not cursor:
            break
    return {"channels": channels, "total": len(channels)}


@tool(
    name="slack_post_message",
    description=(
        "Post a message to a Slack channel or DM. `channel` must be a channel ID "
        "(from slack_list_channels, e.g. C…) or a user/DM id the app can message. "
        "Requires the Slack app to be invited to the channel for public channels. "
        "Use thread_ts to reply in a thread."
    ),
    parameters={
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel ID (e.g. C1234567890) or conversation ID for DMs.",
            },
            "text": {
                "type": "string",
                "description": "Message text (Slack mrkdwn supported for simple formatting).",
            },
            "thread_ts": {
                "type": "string",
                "description": "Optional: parent message ts to reply in thread (e.g. 1234567890.123456).",
            },
        },
        "required": ["channel", "text"],
    },
    destructive=True,
)
async def slack_post_message(ctx: ToolContext, args: Dict[str, Any]):
    from composio_service import slack_post_message_via_composio_or_proxy
    channel = (args.get("channel") or "").strip()
    text = (args.get("text") or "").strip()
    if not channel or not text:
        return {"error": "channel and text are required"}
    ts = (args.get("thread_ts") or "").strip() or None
    try:
        data = await slack_post_message_via_composio_or_proxy(
            ctx.business_id,
            channel=channel,
            text=text,
            thread_ts=ts,
        )
    except RuntimeError as e:
        return {"error": str(e)}
    err = _slack_api_error(data)
    if err:
        return {"error": err, "slack_response": data}
    return {
        "ok": True,
        "channel": data.get("channel"),
        "ts": data.get("ts"),
        "message_ts": (data.get("message") or {}).get("ts") if isinstance(data.get("message"), dict) else data.get("ts"),
    }


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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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


def _public_http_url(url: str) -> Optional[str]:
    """Return normalized https? URL or None if not a safe public fetch target (SSRF guard)."""
    from urllib.parse import urlparse

    raw = (url or "").strip()
    if not raw:
        return None
    try:
        p = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return None
    if p.scheme not in ("http", "https"):
        return None
    host = (p.hostname or "").lower()
    if not host:
        return None
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return None
    if host.endswith(".localhost") or host.endswith(".local"):
        return None
    if host in ("metadata.google.internal", "metadata", "169.254.169.254"):
        return None
    if host.startswith("169.254."):
        return None
    if host.startswith("10.") or host.startswith("192.168."):
        return None
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2 and parts[0] == "172":
            try:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return None
            except ValueError:
                pass
    if "[" in host:
        return None
    netloc = p.netloc
    path = p.path or "/"
    query = f"?{p.query}" if p.query else ""
    frag = f"#{p.fragment}" if p.fragment else ""
    return f"{p.scheme}://{netloc}{path}{query}{frag}"


def _html_to_plain_text(html: str, max_chars: int = 120_000) -> str:
    import html as html_module

    s = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", s)
    s = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = html_module.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_chars]


@tool(
    name="fetch_url",
    description=(
        "Fetch and read the main text content of a specific web page the user linked or pasted "
        "(full https URL). Use when the user provides a URL and wants a summary, facts, or "
        "content from that exact page. Do NOT use this for open-ended research — use `web_search` "
        "for keyword searches. Returns extracted markdown or plain text (truncated if very long)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full page URL (https://...) exactly as the user shared or from a cited link.",
            },
        },
        "required": ["url"],
    },
)
async def fetch_url(ctx: ToolContext, args: Dict[str, Any]):
    import os
    import httpx

    normalized = _public_http_url((args.get("url") or "").strip())
    if not normalized:
        return {"error": "Invalid or non-public URL — provide an http(s) link to a public page."}

    tavily_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if tavily_key:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    "https://api.tavily.com/extract",
                    json={
                        "api_key": tavily_key,
                        "urls": [normalized],
                        "format": "markdown",
                        "extract_depth": "basic",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results") or []
                    failed = data.get("failed_results") or []
                    if results:
                        r0 = results[0]
                        content = (r0.get("raw_content") or "").strip()
                        if content:
                            return {
                                "url": normalized,
                                "title": r0.get("title") or "",
                                "content": content[:120_000],
                                "source": "tavily_extract",
                            }
                    if failed:
                        err = (failed[0].get("error") or "extraction failed")[:500]
                        logger.warning("[fetch_url] Tavily extract failed for %s: %s", normalized, err)
                else:
                    logger.warning(
                        "[fetch_url] Tavily HTTP %s: %s",
                        resp.status_code,
                        resp.text[:300],
                    )
        except Exception as e:
            logger.warning("[fetch_url] Tavily extract error: %s — falling back to direct fetch", e)

    max_bytes = 2_000_000
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "ZiloAI/1.0 (assistant; +https://zilo.pro)"},
        ) as client:
            resp = await client.get(normalized)
            resp.raise_for_status()
            body = resp.content
            if len(body) > max_bytes:
                body = body[:max_bytes]
            ctype = (resp.headers.get("content-type") or "").lower()
            text = body.decode("utf-8", errors="replace")
            if "html" in ctype or text.lstrip().lower().startswith("<!doctype") or "<html" in text[:2000].lower():
                plain = _html_to_plain_text(text)
            else:
                plain = text.strip()[:120_000]
            if not plain:
                return {"error": "Page returned no readable text (may require JavaScript or login).", "url": normalized}
            return {
                "url": str(resp.url),
                "content": plain,
                "source": "direct_http",
                "note": "Raw fetch; for heavy JS sites set TAVILY_API_KEY for better extraction." if not tavily_key else None,
            }
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "url": normalized}
    except Exception as e:
        logger.warning("[fetch_url] direct fetch failed: %s", e)
        return {"error": str(e)[:500], "url": normalized}


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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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
    from .composio_helper import composio_proxy as nango_proxy
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


# ── Shotstack Video Generation ─────────────────────────────────────────────────
# Default base URLs — overridden by SHOTSTACK_ENV if set to a full URL.
_SHOTSTACK_PROD_BASE = "https://api.shotstack.io/edit/v1"
_SHOTSTACK_STAGE_BASE = "https://api.shotstack.io/edit/stage"


def _shotstack_headers() -> dict:
    import os
    key = os.getenv("SHOTSTACK_API_KEY", "")
    if not key:
        raise RuntimeError("SHOTSTACK_API_KEY is not configured")
    return {"x-api-key": key, "Content-Type": "application/json"}


def _shotstack_render_url() -> str:
    """Return the full POST render endpoint URL.

    Handles three formats for SHOTSTACK_ENV:
      - Full render URL  : https://api.shotstack.io/edit/stage/render  (what the user set)
      - Base URL         : https://api.shotstack.io/edit/stage  -> appends /render
      - Short label      : 'stage' or 'production'
    """
    import os
    val = os.getenv("SHOTSTACK_ENV", "stage").strip()
    if val.startswith("http"):
        if val.endswith("/render"):
            return val  # already the full render endpoint
        return val.rstrip("/") + "/render"
    if val == "production":
        return _SHOTSTACK_PROD_BASE + "/render"
    return _SHOTSTACK_STAGE_BASE + "/render"


def _shotstack_status_url(render_id: str) -> str:
    """Return the GET render status endpoint URL for a given render_id."""
    import os
    val = os.getenv("SHOTSTACK_ENV", "stage").strip()
    if val.startswith("http"):
        base = val.rstrip("/").split("/render")[0]
        return f"{base}/render/{render_id}"
    if val == "production":
        return f"{_SHOTSTACK_PROD_BASE}/render/{render_id}"
    return f"{_SHOTSTACK_STAGE_BASE}/render/{render_id}"


@tool(
    name="create_video",
    description=(
        "Create a short promotional video using Shotstack. "
        "Assembles a video from a title, subtitle, background color or image URL, "
        "optional product image URL, and a voiceover or background music track. "
        "Returns a render_id — use get_video_status to poll until ready, then share the URL. "
        "Best for: product promos, event announcements, sale countdowns, social media reels."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Main headline text shown on the video (e.g. 'Summer Sale — 30% Off')",
            },
            "subtitle": {
                "type": "string",
                "description": "Supporting text shown below the title (e.g. 'Shop now at zilocrm.com')",
            },
            "background_color": {
                "type": "string",
                "description": "Hex background color when no background image is used (e.g. '#1a1a2e'). Defaults to #000000.",
            },
            "background_image_url": {
                "type": "string",
                "description": "Optional URL of a full-bleed background image or product image to use as the video background.",
            },
            "product_image_url": {
                "type": "string",
                "description": "Optional URL of a product image to overlay in the center of the video.",
            },
            "duration": {
                "type": "number",
                "description": "Video duration in seconds (5–30). Defaults to 10.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["square", "portrait", "landscape"],
                "description": "Output format. square=1080x1080 (Instagram), portrait=1080x1920 (Reels/TikTok), landscape=1920x1080 (YouTube/Facebook). Defaults to square.",
            },
            "music_url": {
                "type": "string",
                "description": "Optional URL of a background music/audio track (.mp3). Leave empty for silent video.",
            },
            "title_color": {
                "type": "string",
                "description": "Hex color for the title text. Defaults to #ffffff.",
            },
            "voiceover_text": {
                "type": "string",
                "description": "Optional spoken voiceover script read aloud over the video using text-to-speech. E.g. 'Shop our summer sale — 30 percent off all items this weekend only.' Leave empty for no voiceover.",
            },
            "voiceover_voice": {
                "type": "string",
                "enum": ["male", "female"],
                "description": "Voice gender for TTS voiceover. Defaults to female.",
            },
        },
        "required": ["title"],
    },
)
async def create_video(ctx: ToolContext, args: Dict[str, Any]):
    import os
    import httpx

    title = (args.get("title") or "").strip()
    subtitle = (args.get("subtitle") or "").strip()
    bg_color = (args.get("background_color") or "#000000").strip()
    bg_image = (args.get("background_image_url") or "").strip()
    product_image = (args.get("product_image_url") or "").strip()
    duration = float(args.get("duration") or 10)
    duration = max(5.0, min(30.0, duration))
    aspect = (args.get("aspect_ratio") or "square").lower()
    music_url = (args.get("music_url") or "").strip()
    title_color = (args.get("title_color") or "#ffffff").strip()
    voiceover_text = (args.get("voiceover_text") or "").strip()
    voiceover_voice = (args.get("voiceover_voice") or "female").strip().lower()

    # Resolve dimensions
    size_map = {
        "square": {"width": 1080, "height": 1080},
        "portrait": {"width": 1080, "height": 1920},
        "landscape": {"width": 1920, "height": 1080},
    }
    size = size_map.get(aspect, size_map["square"])

    # Build clips list
    clips = []

    # Background layer (color fill or image)
    if bg_image:
        clips.append({
            "asset": {"type": "image", "src": bg_image},
            "start": 0, "length": duration,
            "fit": "cover", "scale": 1.0,
            "position": "center",
        })
    else:
        # Derive a darker shade for the gradient by blending bg_color toward black
        import colorsys as _cs
        def _darken(hex_col: str, factor: float = 0.45) -> str:
            hex_col = hex_col.lstrip("#")
            if len(hex_col) != 6:
                return "#0a0a1a"
            r, g, b = (int(hex_col[i:i+2], 16) for i in (0, 2, 4))
            h, s, v = _cs.rgb_to_hsv(r/255, g/255, b/255)
            v2 = max(0.0, v * factor)
            r2, g2, b2 = _cs.hsv_to_rgb(h, min(1.0, s * 1.2), v2)
            return f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"
        dark = _darken(bg_color)
        grad_html = (
            f"<div style='width:{size['width']}px;height:{size['height']}px;"
            f"background:linear-gradient(145deg,{bg_color} 0%,{dark} 100%)'></div>"
        )
        clips.append({
            "asset": {
                "type": "html",
                "html": grad_html,
                "width": size["width"],
                "height": size["height"],
            },
            "start": 0, "length": duration,
            "position": "center",
        })

    # Optional product image overlay
    if product_image:
        clips.append({
            "asset": {"type": "image", "src": product_image},
            "start": 0.5, "length": duration - 1,
            "fit": "contain", "scale": 0.55,
            "position": "center",
            "opacity": 0.95,
        })

    # Title text — positioned at top to avoid overlap with subtitle
    clips.append({
        "asset": {
            "type": "title",
            "text": title,
            "style": "minimal",
            "color": title_color,
            "size": "large",
        },
        "start": 0.5,
        "length": duration - 0.5,
        "position": "top",
        "offset": {"y": 0.15},
        "transition": {"in": "fade", "out": "fade"},
    })

    # Subtitle text — positioned at bottom with clear separation
    if subtitle:
        clips.append({
            "asset": {
                "type": "title",
                "text": subtitle,
                "style": "minimal",
                "color": "#dddddd",
                "size": "small",
            },
            "start": 1.5,
            "length": duration - 1.5,
            "position": "bottom",
            "offset": {"y": 0.15},
            "transition": {"in": "fade"},
        })

    # Logo overlay — top-left corner, small and subtle
    logo_url = None
    try:
        owner = await ctx.db.businesses.find_one({"_id": ctx.business_id})
        if owner:
            logo_url = owner.get("logo_url") or owner.get("brand_logo_url")
    except Exception:
        pass

    if logo_url:
        clips.append({
            "asset": {"type": "image", "src": logo_url},
            "start": 0,
            "length": duration,
            "fit": "contain",
            "scale": 0.12,
            "position": "topLeft",
            "offset": {"x": 0.05, "y": 0.05},
            "opacity": 0.85,
        })

    track = {"clips": clips}

    # Voiceover TTS track — only supported in Shotstack v1 (production), not stage/sandbox
    import os as _os
    _env_val = _os.getenv("SHOTSTACK_ENV", "stage").strip()
    _is_production = _env_val == "production" or (
        _env_val.startswith("http") and "/v1/" in _env_val
    )
    tracks = [track]
    if voiceover_text and _is_production:
        # Shotstack text-to-speech asset — voice IDs: Brian (male), Joanna (female)
        tts_voice = "Brian" if voiceover_voice == "male" else "Joanna"
        tts_clip: Dict[str, Any] = {
            "asset": {
                "type": "text-to-speech",
                "text": voiceover_text[:300],
                "voice": tts_voice,
            },
            "start": 0.3,
            "length": "auto",
        }
        tracks.append({"clips": [tts_clip]})

    timeline: Dict[str, Any] = {"tracks": tracks}

    # Background music (lower volume when voiceover is present)
    if music_url:
        timeline["soundtrack"] = {
            "src": music_url,
            "effect": "fadeInFadeOut",
            "volume": 0.25 if voiceover_text else 0.6,
        }

    payload = {
        "timeline": timeline,
        "output": {
            "format": "mp4",
            "resolution": "hd",
            "size": size,
            "fps": 25,
        },
    }

    try:
        headers = _shotstack_headers()
        render_url = _shotstack_render_url()
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(render_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except RuntimeError as e:
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"error": f"Shotstack API error: {e.response.status_code} — {e.response.text[:300]}"}
    except Exception as e:
        return {"error": f"Video render request failed: {e}"}

    render_id = (data.get("response") or {}).get("id") or data.get("id")
    if not render_id:
        return {"error": "Shotstack did not return a render ID", "raw": str(data)[:300]}

    # Persist render record in DB for tracking
    try:
        await ctx.db.video_renders.insert_one({
            "_id": render_id,
            "business_id": ctx.business_id,
            "title": title,
            "aspect_ratio": aspect,
            "status": "queued",
            "created_at": datetime.utcnow(),
        })
    except Exception:
        pass

    return {
        "status": "queued",
        "render_id": render_id,
        "message": f"Video '{title}' is rendering. Use get_video_status('{render_id}') to check when it's ready.",
        "estimated_wait": "15–45 seconds",
        "aspect_ratio": aspect,
        "dimensions": f"{size['width']}x{size['height']}",
    }


@tool(
    name="get_video_status",
    description=(
        "Check the rendering status of a Shotstack video by its render_id. "
        "Returns status (queued / rendering / done / failed) and the video URL when done. "
        "Poll every 5–10 seconds until status is 'done' or 'failed'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "render_id": {
                "type": "string",
                "description": "The render ID returned by create_video.",
            },
        },
        "required": ["render_id"],
    },
)
async def get_video_status(ctx: ToolContext, args: Dict[str, Any]):
    import httpx

    render_id = (args.get("render_id") or "").strip()
    if not render_id:
        return {"error": "render_id is required"}

    try:
        headers = _shotstack_headers()
        status_url = _shotstack_status_url(render_id)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(status_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except RuntimeError as e:
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"error": f"Shotstack API error: {e.response.status_code} — {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Status check failed: {e}"}

    r = data.get("response") or data
    status = (r.get("status") or "unknown").lower()
    url = r.get("url") or ""

    # Update DB record and read aspect_ratio + title
    db_record: Dict[str, Any] = {}
    try:
        update: Dict[str, Any] = {"status": status}
        if url:
            update["url"] = url
        await ctx.db.video_renders.update_one(
            {"_id": render_id},
            {"$set": update},
        )
        db_record = await ctx.db.video_renders.find_one({"_id": render_id}) or {}
    except Exception:
        pass

    # Map stored aspect_ratio key to display string the frontend expects
    _ratio_map = {"square": "1:1", "portrait": "9:16", "landscape": "16:9"}
    stored_ratio = db_record.get("aspect_ratio", "square")
    display_ratio = _ratio_map.get(stored_ratio, "1:1")

    result: Dict[str, Any] = {
        "render_id": render_id,
        "status": status,
        "aspect_ratio": display_ratio,
        "title": db_record.get("title", ""),
    }
    if status == "done" and url:
        result["url"] = url
        result["message"] = f"Your video is ready! [Watch / Download]({url})"
    elif status == "failed":
        result["message"] = "Render failed. Try create_video again with slightly different settings."
        result["error_detail"] = r.get("error") or ""
    else:
        result["message"] = f"Still rendering ({status}). Check again in a few seconds."

    return result


@tool(
    name="list_videos",
    description=(
        "List all videos previously created for this business, with their status and URLs. "
        "Use this to show the owner their video history or find a specific render."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max number of videos to return (default 10, max 30).",
            },
        },
        "required": [],
    },
)
async def list_videos(ctx: ToolContext, args: Dict[str, Any]):
    limit = min(int(args.get("limit") or 10), 30)
    try:
        rows = await ctx.db.video_renders.find(
            {"business_id": ctx.business_id}
        ).sort("created_at", -1).to_list(limit)
    except Exception as e:
        return {"error": f"Could not fetch video history: {e}"}

    videos = []
    for r in rows:
        videos.append({
            "render_id": str(r["_id"]),
            "title": r.get("title", ""),
            "status": r.get("status", "unknown"),
            "aspect_ratio": r.get("aspect_ratio", ""),
            "url": r.get("url", ""),
            "created_at": r.get("created_at", "").isoformat() if hasattr(r.get("created_at", ""), "isoformat") else str(r.get("created_at", "")),
        })

    return {"videos": videos, "total": len(videos)}


# ── Kling AI Video Generation ───────────────────────────────────────────────
_KLING_API_BASE = "https://api.kie.ai/api/v1"


def _kling_headers() -> dict:
    import os
    key = os.getenv("KLING_API_KEY", "")
    if not key:
        raise RuntimeError("KLING_API_KEY is not configured")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@tool(
    name="create_kling_video",
    description=(
        "Generate a realistic AI video using Kling 2.6 — turns a text prompt (and optionally a "
        "reference image URL) into a real video with cinematic motion. Use this when the user wants "
        "a video with actual visual footage, product scenes, lifestyle shots, or animated scenes. "
        "Returns a task_id — use get_kling_video_status to poll until ready."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Detailed scene description. Be cinematic and specific: describe lighting, "
                    "motion, camera angle, subject, mood. E.g. 'A sleek black smartphone rotating "
                    "slowly on a white marble surface, dramatic studio lighting, product ad style, "
                    "ultra HD.'"
                ),
            },
            "image_url": {
                "type": "string",
                "description": "Optional reference image URL to use as the starting frame (image-to-video). Great for animating product photos.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1"],
                "description": "16:9 = landscape (YouTube/Facebook), 9:16 = portrait (Reels/TikTok), 1:1 = square (Instagram). Defaults to 9:16.",
            },
            "duration": {
                "type": "string",
                "enum": ["5", "10"],
                "description": "Video duration in seconds. Defaults to 5.",
            },
            "mode": {
                "type": "string",
                "enum": ["standard", "pro"],
                "description": "standard = faster and cheaper, pro = higher quality. Defaults to standard.",
            },
            "sound": {
                "type": "boolean",
                "description": "Enable AI-generated ambient sound/audio that matches the video scene. Defaults to true.",
            },
        },
        "required": ["prompt"],
    },
)
async def create_kling_video(ctx: ToolContext, args: Dict[str, Any]):
    import httpx

    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return {"error": "prompt is required"}

    image_url = (args.get("image_url") or "").strip()
    aspect_ratio = args.get("aspect_ratio") or "9:16"
    duration = str(args.get("duration") or "5")
    mode = args.get("mode") or "standard"
    sound = args.get("sound", True)

    # Use image-to-video model if a reference image is provided
    model = "kling-2.6/image-to-video" if image_url else "kling-2.6/text-to-video"

    payload: Dict[str, Any] = {
        "model": model,
        "input": {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "mode": mode,
            "sound": sound,
        },
    }
    if image_url:
        payload["input"]["image_url"] = image_url

    try:
        headers = _kling_headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_KLING_API_BASE}/jobs/createTask",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except RuntimeError as e:
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"error": f"Kling API error: {e.response.status_code} — {e.response.text[:300]}"}
    except Exception as e:
        return {"error": f"Kling video request failed: {e}"}

    task_id = (data.get("data") or {}).get("taskId") or data.get("taskId")
    if not task_id:
        return {"error": f"No task_id returned: {data}"}

    # Persist to DB
    try:
        await ctx.db.kling_renders.insert_one({
            "business_id": ctx.business_id,
            "task_id": task_id,
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "status": "queued",
            "url": None,
            "created_at": datetime.utcnow(),
        })
    except Exception:
        pass

    return {
        "task_id": task_id,
        "model": model,
        "status": "queued",
        "message": "Kling video is generating. Call get_kling_video_status to poll progress.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# SOCIAL MEDIA MONITORING TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="list_scheduled_posts",
    description=(
        "List social media posts for the current business. "
        "Filter by status (draft/scheduled/published/failed) or channel (facebook/instagram/linkedin/x/tiktok). "
        "Returns post titles, channels, status, scheduled time, and engagement metrics for published posts."
    ),
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter by post status: draft, scheduled, published, failed. Omit for all.",
            },
            "channel": {
                "type": "string",
                "description": "Filter by platform: facebook, instagram, linkedin, x, tiktok.",
            },
            "limit": {"type": "integer", "default": 30, "minimum": 1, "maximum": 100},
        },
    },
)
async def list_scheduled_posts(ctx: ToolContext, args: Dict[str, Any]):
    q: Dict[str, Any] = {"user_id": ctx.business_id}
    if st := (args.get("status") or "").strip().lower():
        q["status"] = st
    if ch := (args.get("channel") or "").strip().lower():
        q["channels"] = {"$in": [ch]}
    limit = min(int(args.get("limit") or 30), 100)
    rows = await ctx.db.scheduled_posts.find(q).sort("scheduled_at", -1).to_list(limit)

    def _fmt(r: Dict[str, Any]) -> Dict[str, Any]:
        sa = r.get("scheduled_at")
        return {
            "id":           str(r["_id"]),
            "title":        r.get("title") or "",
            "channels":     r.get("channels") or [],
            "status":       r.get("status") or "draft",
            "scheduled_at": sa.isoformat() if hasattr(sa, "isoformat") else str(sa or ""),
            "engagement":   r.get("engagement") or {},
            "zernio_post_id": r.get("zernio_post_id"),
            "engagement_synced_at": (
                r["engagement_synced_at"].isoformat()
                if hasattr(r.get("engagement_synced_at"), "isoformat")
                else None
            ),
        }

    return {"count": len(rows), "posts": [_fmt(r) for r in rows]}


@tool(
    name="get_social_post_analytics",
    description=(
        "Get a detailed engagement analytics summary across all published social posts. "
        "Returns per-platform breakdowns, top-performing posts by likes/reach/clicks, "
        "overall totals, and trend observations the monitoring agent can use to advise strategy."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "default": 30,
                "description": "Look-back window in days (default 30).",
            },
            "channel": {
                "type": "string",
                "description": "Narrow to a single platform: facebook, instagram, linkedin, x/twitter, tiktok, youtube.",
            },
        },
    },
)
async def get_social_post_analytics(ctx: ToolContext, args: Dict[str, Any]):
    days = int(args.get("days") or 30)
    channel_filter = (args.get("channel") or "").strip().lower()
    since = datetime.utcnow() - timedelta(days=days)

    q: Dict[str, Any] = {
        "user_id": ctx.business_id,
        "status": "published",
        "scheduled_at": {"$gte": since},
    }
    if channel_filter:
        q["channels"] = {"$in": [channel_filter]}

    posts = await ctx.db.scheduled_posts.find(q).sort("scheduled_at", -1).to_list(200)

    totals = {"likes": 0, "comments": 0, "shares": 0, "reach": 0, "clicks": 0, "saves": 0}
    by_channel: Dict[str, Dict[str, int]] = {}
    post_summaries = []

    for p in posts:
        eng = p.get("engagement") or {}
        likes    = int(eng.get("likes", 0))
        comments = int(eng.get("comments", 0))
        shares   = int(eng.get("shares", 0))
        reach    = int(eng.get("reach", 0))
        clicks   = int(eng.get("clicks", 0))
        saves    = int(eng.get("saves", 0))

        totals["likes"]    += likes
        totals["comments"] += comments
        totals["shares"]   += shares
        totals["reach"]    += reach
        totals["clicks"]   += clicks
        totals["saves"]    += saves

        for ch in (p.get("channels") or []):
            bc = by_channel.setdefault(ch, {"likes": 0, "comments": 0, "shares": 0,
                                            "reach": 0, "clicks": 0, "posts": 0})
            bc["likes"]    += likes
            bc["comments"] += comments
            bc["shares"]   += shares
            bc["reach"]    += reach
            bc["clicks"]   += clicks
            bc["posts"]    += 1

        sa = p.get("scheduled_at")
        post_summaries.append({
            "id":       str(p["_id"]),
            "title":    p.get("title") or "",
            "channels": p.get("channels") or [],
            "date":     sa.isoformat() if hasattr(sa, "isoformat") else str(sa or ""),
            "likes": likes, "comments": comments, "shares": shares,
            "reach": reach, "clicks": clicks, "saves": saves,
            "engagement_score": likes + comments * 2 + shares * 3 + clicks,
        })

    # Top 5 posts by engagement score
    top_posts = sorted(post_summaries, key=lambda x: x["engagement_score"], reverse=True)[:5]

    # Posts with zero engagement (no metrics synced yet)
    unsynced = sum(1 for p in posts if not p.get("engagement"))

    return {
        "period_days":       days,
        "total_posts":       len(posts),
        "unsynced_posts":    unsynced,
        "totals":            totals,
        "by_channel":        by_channel,
        "top_posts":         top_posts,
        "avg_reach_per_post": round(totals["reach"] / len(posts), 1) if posts else 0,
        "avg_engagement_rate": (
            round((totals["likes"] + totals["comments"] + totals["shares"]) / totals["reach"] * 100, 2)
            if totals["reach"] > 0 else 0
        ),
    }


@tool(
    name="get_live_social_posts",
    description=(
        "Fetch live posts and real-time engagement metrics (likes, comments, shares, reach, clicks) "
        "directly from connected social media accounts. "
        "Unlike get_social_post_analytics (which only shows CRM-scheduled posts), this returns ALL posts "
        "from connected accounts — including posts published directly on Facebook, Instagram, etc. "
        "Use this whenever the user asks about their latest posts, current engagement, or says they "
        "can't see a post. Also returns posts that have received comments in the social inbox.\n\n"
        "IMPORTANT — read `metric_coverage` and `low_coverage_metrics` before quoting any total. "
        "Each metric total is summed only across posts where the platform returned that metric, so "
        "`totals.reach: 19` with `metric_coverage.reach: 1` means only 1 post out of `total_posts` "
        "reported reach. In that case, do NOT quote the total bare — qualify it (e.g. \"reach data is "
        "only available for 1 of your 50 posts; the rest are organic Instagram/older Facebook posts "
        "that don't expose reach via the Graph API\"). Also surface any strings in `metric_notes`.\n\n"
        "Returns pre-computed strategy signals in `derived_insights` (engagement rate per platform, "
        "best publish hour & day from the owner's own posts, media-type performance, posting cadence, "
        "top 3 posts, and recommended actions) and audience-size context in `accounts_summary` + "
        "`total_followers_by_platform`. `follower_growth_by_platform` accumulates daily snapshots so "
        "growth deltas (`delta_7d`, `delta_30d`) become available after a few days of usage.\n\n"
        "CONNECTION HEALTH: every account in `accounts_summary` carries a `sync_status` "
        "(synced / sync_in_progress / pending_first_sync / no_posts_published) and a plain-English "
        "`sync_message`. `platform_diagnostics` aggregates this per platform. Use these to honestly "
        "explain why a freshly-connected platform (e.g. LinkedIn just added) shows 0 posts — that "
        "typically means our first sync hasn't completed yet (takes 30–60 min), NOT that the "
        "integration failed. The follower count is real even when post-level data is still pending.\n\n"
        "Audience demographics (age, gender, geography, industry, seniority) are NOT returned by THIS tool. "
        "If the user asks for demographic data, you MUST call the `get_audience_insights` tool instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "Filter by platform: facebook, instagram, twitter, linkedin, tiktok, youtube. Omit for all.",
            },
            "limit": {
                "type": "integer",
                "default": 50,
                "description": "Max number of posts to return (1–100). Request more when the user wants every post.",
            },
        },
    },
)
@tool(
    name="get_audience_insights",
    description=(
        "Fetch real audience demographics for connected social pages — age ranges, gender split, "
        "top countries, and top cities. Use this when the user asks: who follows me, who engages "
        "with my content, who should I target for ads, what's my audience profile. "
        "Returns structured data per platform (facebook, linkedin)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "refresh": {
                "type": "boolean",
                "description": "Pass true to bypass the 24-hour cache and fetch fresh data.",
                "default": False,
            },
        },
    },
)
async def get_audience_insights(ctx: ToolContext, args: Dict[str, Any]):
    refresh = bool(args.get("refresh", False))
    try:
        from audience_insights_service import get_audience_insights_for_user
        db = ctx.db
        user_id = ctx.user_id

        if refresh:
            # bust the 24-hour cache so fresh data is pulled
            await db.audience_insights_cache.delete_one({"user_id": user_id})

        insights = await get_audience_insights_for_user(db, user_id)

        if not insights:
            # Provide a specific, helpful message rather than a generic Facebook one
            return {
                "has_data": False,
                "message": (
                    "No audience demographics could be fetched right now. "
                    "Make sure your LinkedIn and/or Facebook Page are connected under Integrations. "
                    "If you just connected them, try again with refresh=true."
                ),
            }

        # Summarise what platforms returned data so the AI knows what it has
        platforms_with_data = list(insights.keys())
        return {
            "has_data": True,
            "platforms": platforms_with_data,
            "insights": insights,
        }
    except Exception as exc:
        return {"error": str(exc)}


async def get_live_social_posts(ctx: ToolContext, args: Dict[str, Any]):
    import httpx as _httpx

    zernio_base = os.environ.get("ZERNIO_API_BASE", "https://zernio.com/api/v1").rstrip("/")
    zernio_bases = list(dict.fromkeys([zernio_base, "https://zernio.com/api/v1"]))

    api_key = os.environ.get("ZERNIO_API_KEY", "").strip()
    if not api_key:
        return {"error": "Social sync service is not configured. Please contact support."}

    platform_filter = (args.get("platform") or "").strip().lower()
    limit = max(1, min(int(args.get("limit") or 50), 100))
    # Fetch wide from Zernio; return only `limit` rows after merge/sort (matches Social Inbox behaviour).
    posts_inbox_fetch_limit = 100

    hdrs = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def _zernio_get(path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Try each Zernio base URL until one succeeds."""
        async with _httpx.AsyncClient(timeout=20.0) as client:
            for base in zernio_bases:
                try:
                    r = await client.get(f"{base}{path}", headers=hdrs, params=params)
                    if r.status_code == 404 and "text/html" in (r.headers.get("content-type") or ""):
                        continue
                    r.raise_for_status()
                    return r.json()
                except _httpx.HTTPStatusError:
                    continue
                except Exception:
                    continue
        return None

    async def _zernio_accounts_count(pid: str) -> int:
        data = await _zernio_get("/accounts", {"profileId": pid})
        if not isinstance(data, dict):
            return 0
        acc_list = data.get("accounts") or data.get("data") or []
        return len(acc_list) if isinstance(acc_list, list) else 0

    async def _zernio_first_profile_id_with_accounts() -> str:
        """Scan Zernio profiles under this API key — same idea as zernio.routes._pick_profile_with_accounts."""
        pdata = await _zernio_get("/profiles", {})
        if not isinstance(pdata, dict):
            return ""
        profiles = pdata.get("profiles") or pdata.get("data") or []
        if not isinstance(profiles, list):
            return ""
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            raw_pid = (
                profile.get("_id") or profile.get("id")
                or profile.get("profileId") or profile.get("profile_id")
            )
            cand = str(raw_pid).strip() if raw_pid else ""
            if cand and await _zernio_accounts_count(cand) > 0:
                return cand
        return ""

    # ── 1. Resolve profile ID from DB + heal stale profile (matches Social Inbox) ─
    # Web `/zernio/*` calls _get_or_create_profile(), which updates MongoDB when the stored
    # profile has zero connected accounts but another profile on the key has pages.
    # Without this, the assistant keeps querying an empty/stale profile while the UI shows data.
    user_doc = await ctx.db.users.find_one(
        {"_id": ctx.business_id}, {"zernio_profile_id": 1}
    )
    profile_id = str((user_doc or {}).get("zernio_profile_id") or "").strip()
    if not profile_id:
        return {
            "error": "No social profile found for this account. Connect a social account first.",
            "posts": [],
        }

    profile_healed = False
    if await _zernio_accounts_count(profile_id) == 0:
        healed = await _zernio_first_profile_id_with_accounts()
        if healed and healed != profile_id:
            await ctx.db.users.update_one(
                {"_id": ctx.business_id},
                {"$set": {"zernio_profile_id": healed}},
            )
            profile_id = healed
            profile_healed = True

    params_base: Dict[str, Any] = {"profileId": profile_id, "limit": posts_inbox_fetch_limit}
    if platform_filter:
        params_base["platform"] = platform_filter

    METRICS = "likes,comments,shares,reach,clicks,saves,impressions"
    ANALYTICS_PAGE_SIZE = 100
    MAX_ANALYTICS_PAGES = 10
    PER_POST_FALLBACK_CAP = 40

    # ── helpers (defined early so they can be used in async fetch steps) ────────
    def _all_ids(row: Dict[str, Any]) -> List[str]:
        candidates: List[Any] = [
            row.get("id"), row.get("_id"), row.get("postId"), row.get("post_id"),
            row.get("platformPostId"), row.get("externalPostId"),
            row.get("latePostId"), row.get("late_post_id"),
            row.get("zernio_post_id"), row.get("external_post_id"), row.get("cid"),
        ]
        pa = row.get("platformAnalytics")
        if isinstance(pa, list) and pa and isinstance(pa[0], dict):
            p0 = pa[0]
            candidates.extend([
                p0.get("platformPostId"), p0.get("postId"), p0.get("post_id"), p0.get("id"),
            ])
        analytics_obj = row.get("analytics")
        if isinstance(analytics_obj, dict):
            candidates.extend([
                analytics_obj.get("postId"), analytics_obj.get("post_id"),
            ])
        out: List[str] = []
        for c in candidates:
            if c and str(c).strip():
                s = str(c).strip()
                if s not in out:
                    out.append(s)
        return out

    def _extract_analytics_row_list(data: Any) -> List[Dict[str, Any]]:
        """Same shapes as Social Inbox `pickAnalyticsRows`."""
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("data", "posts", "results"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return [r for r in candidate if isinstance(r, dict)]
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in ("posts", "data"):
                c2 = nested.get(key)
                if isinstance(c2, list):
                    return [r for r in c2 if isinstance(r, dict)]
            if nested.get("postId") or nested.get("latePostId") or nested.get("analytics"):
                return [nested]
        if data.get("postId") or data.get("latePostId") or data.get("analytics"):
            return [data]
        return []

    def _extract_int(*values) -> int:
        for v in values:
            # Facebook Graph API returns several engagement fields as nested objects:
            # shares -> {"count": 5}, reactions -> {"total_count": 12}. Without
            # unwrapping these, posts that were actually shared were reported as 0.
            if isinstance(v, dict):
                for key in ("count", "total_count", "totalCount", "total", "value"):
                    inner = v.get(key)
                    if inner is None:
                        continue
                    try:
                        n = int(inner)
                        if n >= 0:
                            return n
                    except (TypeError, ValueError):
                        continue
                continue
            try:
                n = int(v)
                if n >= 0:
                    return n
            except (TypeError, ValueError):
                pass
        return 0

    def _get_account_id(row: Dict[str, Any]) -> str:
        for key in ("accountId", "account_id", "accountID", "pageId", "page_id"):
            v = row.get(key)
            if v and str(v).strip():
                return str(v).strip()
        return ""

    # ── 2. Fetch live posts + accounts (mirror Social Inbox `page.tsx` loading) ──
    import asyncio as _asyncio

    def _rows_from_zernio_list_payload(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ("posts", "data", "results"):
                candidate = payload.get(key)
                if isinstance(candidate, list):
                    return [r for r in candidate if isinstance(r, dict)]
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        return []

    def _merge_unique_post_dicts(row_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        seen_alias: set = set()
        out: List[Dict[str, Any]] = []
        for rows in row_lists:
            for row in rows:
                ids = _all_ids(row)
                if ids and any(i in seen_alias for i in ids):
                    continue
                if ids:
                    for i in ids:
                        seen_alias.add(i)
                out.append(row)
        return out

    # UI: `commentedPosts` omits min_comments; analytics uses `platform: filter || "facebook"`.
    # Zernio often returns a sparse list without `platform=facebook` — merge explicit FB-scoped fetches.
    comments_params_ui = dict(params_base)
    posts_params_ui = dict(params_base)

    fetch_tasks: List[Any] = [
        _zernio_get("/posts", posts_params_ui),
        _zernio_get("/accounts", {"profileId": profile_id}),
        _zernio_get("/inbox/comments", comments_params_ui),
        # Account-level snapshot: returns each account's followersCount and a global
        # overview block. Useful as cross-platform context (e.g. "1010 FB followers,
        # 124 IG followers") even when per-post share/reach data is unavailable.
        _zernio_get("/analytics", {"profileId": profile_id, "period": "30d"}),
    ]
    if not platform_filter:
        fetch_tasks.append(_zernio_get("/posts", {**params_base, "platform": "facebook"}))
        fetch_tasks.append(_zernio_get("/inbox/comments", {**params_base, "platform": "facebook"}))

    fetch_results = await _asyncio.gather(*fetch_tasks, return_exceptions=True)

    posts_data = fetch_results[0]
    accounts_data = fetch_results[1]
    comments_data = fetch_results[2]
    account_snapshot_data = fetch_results[3]
    posts_fb_data = fetch_results[4] if len(fetch_results) > 4 else None
    comments_fb_data = fetch_results[5] if len(fetch_results) > 5 else None

    post_row_lists: List[List[Dict[str, Any]]] = []
    if not isinstance(posts_data, Exception):
        post_row_lists.append(_rows_from_zernio_list_payload(posts_data))
    if posts_fb_data is not None and not isinstance(posts_fb_data, Exception):
        post_row_lists.append(_rows_from_zernio_list_payload(posts_fb_data))
    raw_posts = _merge_unique_post_dicts(post_row_lists)

    comment_row_lists: List[List[Dict[str, Any]]] = []
    if not isinstance(comments_data, Exception):
        comment_row_lists.append(_rows_from_zernio_list_payload(comments_data))
    if comments_fb_data is not None and not isinstance(comments_fb_data, Exception):
        comment_row_lists.append(_rows_from_zernio_list_payload(comments_fb_data))
    commented_posts = _merge_unique_post_dicts(comment_row_lists)

    # Collect all account IDs as fallback when a post doesn't carry its own.
    # Also remember the platform per account so per-account post fetches can tag
    # the rows correctly (LinkedIn /accounts/{id}/posts doesn't include `platform`).
    fallback_account_ids: List[str] = []
    account_platform_by_id: Dict[str, str] = {}
    if isinstance(accounts_data, dict):
        acc_list = accounts_data.get("accounts") or accounts_data.get("data") or []
        if isinstance(acc_list, list):
            for acc in acc_list:
                if isinstance(acc, dict):
                    aid = _get_account_id(acc)
                    if aid:
                        fallback_account_ids.append(aid)
                        # Zernio may return platform as 'platform', 'type', 'channelType', 'network', or 'channel'
                        plat = str(
                            acc.get("platform")
                            or acc.get("type")
                            or acc.get("channelType")
                            or acc.get("network")
                            or acc.get("channel")
                            or ""
                        ).strip().lower()
                        if plat:
                            account_platform_by_id[aid] = plat

    # ── Per-account /accounts/{id}/posts fallback ─────────────────────────────
    # Zernio's bulk /posts and /analytics endpoints often miss LinkedIn and other
    # newer-integration platforms (the bulk endpoints favour Facebook/Instagram).
    # /accounts/{id}/posts is the canonical per-account list and includes
    # platforms that the bulk endpoints silently drop. Run it for any connected
    # account whose platform isn't already represented in raw_posts.
    represented_platforms: Set[str] = {
        str(p.get("platform") or "").lower() for p in raw_posts if isinstance(p, dict)
    }
    represented_platforms.discard("")
    per_account_post_tasks: List[Any] = []
    per_account_post_meta: List[Dict[str, str]] = []
    for aid, plat in account_platform_by_id.items():
        if platform_filter and plat != platform_filter.strip().lower():
            continue
        if plat in represented_platforms:
            continue  # bulk endpoints already have this platform covered
        per_account_post_tasks.append(_zernio_get(f"/accounts/{aid}/posts", {}))
        per_account_post_meta.append({"account_id": aid, "platform": plat})

    if per_account_post_tasks:
        per_account_results = await _asyncio.gather(*per_account_post_tasks, return_exceptions=True)
        for meta, res in zip(per_account_post_meta, per_account_results):
            if isinstance(res, Exception) or not isinstance(res, dict):
                continue
            extra_rows = _rows_from_zernio_list_payload(res)
            if not extra_rows:
                continue
            # Stamp platform/account so downstream merging treats them correctly
            for row in extra_rows:
                if isinstance(row, dict):
                    row.setdefault("platform", meta["platform"])
                    row.setdefault("accountId", meta["account_id"])
            raw_posts = _merge_unique_post_dicts([raw_posts, extra_rows])

    def _extract_engagement(row: Dict[str, Any]) -> Dict[str, int]:
        # Zernio nests engagement under several possible keys depending on endpoint
        a = row.get("analytics") or row.get("metrics") or row.get("insights") or row.get("engagement") or {}
        if not isinstance(a, dict):
            a = {}
        pa_list = row.get("platformAnalytics") or []
        pa = (pa_list[0] if isinstance(pa_list, list) and pa_list and isinstance(pa_list[0], dict) else {})

        def _best(*sources) -> int:
            return _extract_int(*sources)

        def _reactions_total(obj: Any) -> int:
            if isinstance(obj, dict):
                return _extract_int(obj.get("total"), obj.get("total_count"), obj.get("like_count"))
            return _extract_int(obj)

        likes = _best(
            row.get("likes"), row.get("likeCount"), row.get("like_count"),
            row.get("reactions"), row.get("reactionCount"), row.get("reaction_count"),
            _reactions_total(row.get("reactions")),
            a.get("likes"), a.get("likeCount"), a.get("like_count"),
            a.get("reactions"), a.get("reactionCount"), a.get("reaction_count"), a.get("reactions_count"),
            _reactions_total(a.get("reactions")),
            pa.get("likes"), pa.get("likeCount"), pa.get("like_count"),
            pa.get("reactions"), pa.get("reactionCount"), pa.get("reaction_count"),
            _reactions_total(pa.get("reactions")),
        )
        # Shares come in many shapes:
        #   - Facebook /posts:        shares: {"count": N}   (handled by _extract_int unwrap)
        #   - Facebook /analytics:    shareCount / share_count
        #   - Instagram Reels:        reshares / reshare_count
        #   - Threads/X-style:        repost_count / repostCount
        #   - Story shares:           forwards / forward_count
        # Without this expanded list, posts that were actually shared show as 0.
        shares = _best(
            row.get("shares"), row.get("share"),
            row.get("shareCount"), row.get("share_count"), row.get("sharesCount"),
            row.get("reshares"), row.get("reshareCount"), row.get("reshare_count"),
            row.get("reposts"), row.get("repostCount"), row.get("repost_count"),
            row.get("forwards"), row.get("forwardCount"), row.get("forward_count"),
            a.get("shares"), a.get("share"),
            a.get("shareCount"), a.get("share_count"), a.get("sharesCount"), a.get("shares_count"),
            a.get("reshares"), a.get("reshareCount"), a.get("reshare_count"),
            a.get("reposts"), a.get("repostCount"), a.get("repost_count"),
            a.get("forwards"), a.get("forwardCount"), a.get("forward_count"),
            pa.get("shares"), pa.get("share"),
            pa.get("shareCount"), pa.get("share_count"), pa.get("sharesCount"),
            pa.get("reshares"), pa.get("reshareCount"), pa.get("reshare_count"),
            pa.get("reposts"), pa.get("repostCount"), pa.get("repost_count"),
        )
        comments = _best(
            row.get("commentCount"), row.get("comments_count"), row.get("comments"), row.get("total_comments"),
            a.get("comments"), a.get("commentCount"), a.get("comment_count"), a.get("comments_count"),
            pa.get("comments"), pa.get("commentCount"), pa.get("comment_count"),
        )
        # Reach has many platform-specific names: Instagram organic insights expose
        # `reach`/`impressions`; Reels expose `plays`/`video_views`; Facebook video
        # posts expose `viewCount`/`views`; some Zernio bulk rows nest under
        # `unique_impressions` or `total_impressions`. Without this expanded list,
        # most posts return reach=0 and the assistant reports an implausibly low
        # total (e.g. 19 reach against 134 likes).
        reach = _best(
            row.get("reach"), row.get("impressions"),
            row.get("uniqueImpressions"), row.get("unique_impressions"),
            row.get("totalImpressions"), row.get("total_impressions"),
            row.get("views"), row.get("viewCount"), row.get("view_count"),
            row.get("videoViews"), row.get("video_views"), row.get("videoViewCount"),
            row.get("plays"), row.get("playCount"), row.get("play_count"),
            row.get("uniqueViews"), row.get("unique_views"),
            a.get("reach"), a.get("impressions"),
            a.get("uniqueImpressions"), a.get("unique_impressions"),
            a.get("totalImpressions"), a.get("total_impressions"),
            a.get("views"), a.get("viewCount"), a.get("view_count"),
            a.get("videoViews"), a.get("video_views"),
            a.get("plays"), a.get("playCount"), a.get("play_count"),
            a.get("uniqueViews"), a.get("unique_views"),
            pa.get("reach"), pa.get("impressions"),
            pa.get("uniqueImpressions"), pa.get("unique_impressions"),
            pa.get("views"), pa.get("viewCount"),
            pa.get("videoViews"), pa.get("video_views"),
            pa.get("plays"), pa.get("playCount"),
        )
        clicks = _best(
            row.get("clicks"), row.get("clickCount"), row.get("click_count"),
            row.get("linkClicks"), row.get("link_clicks"),
            a.get("clicks"), a.get("clickCount"), a.get("click_count"),
            a.get("linkClicks"), a.get("link_clicks"),
            pa.get("clicks"), pa.get("clickCount"),
        )
        saves = _best(
            row.get("saves"), row.get("saveCount"), row.get("save_count"),
            a.get("saves"), a.get("saveCount"), a.get("save_count"),
            pa.get("saves"), pa.get("saveCount"),
        )
        return {
            "likes": likes, "comments": comments, "shares": shares,
            "reach": reach, "clicks": clicks, "saves": saves,
        }

    # ── 3. Bulk analytics (paginated) — must include accountId per Page (Facebook insights). ──
    async def _fetch_bulk_analytics_pages(extra: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows_acc: List[Dict[str, Any]] = []
        for page in range(1, MAX_ANALYTICS_PAGES + 1):
            bulk_params: Dict[str, Any] = {
                "profileId": profile_id,
                "metrics": METRICS,
                "limit": ANALYTICS_PAGE_SIZE,
                "page": page,
                **extra,
            }
            page_data = await _zernio_get("/analytics", bulk_params)
            chunk = _extract_analytics_row_list(page_data)
            if not chunk:
                break
            rows_acc.extend(chunk)
            if len(chunk) < ANALYTICS_PAGE_SIZE:
                break
        return rows_acc

    acc_list_full: List[Dict[str, Any]] = []
    if isinstance(accounts_data, dict):
        raw_acc = accounts_data.get("accounts") or accounts_data.get("data") or []
        if isinstance(raw_acc, list):
            acc_list_full = [a for a in raw_acc if isinstance(a, dict)]

    def _accounts_for_bulk() -> List[Dict[str, Any]]:
        if not acc_list_full:
            return []
        if platform_filter:
            pf = platform_filter.strip().lower()
            return [a for a in acc_list_full if str(a.get("platform") or "").strip().lower() == pf]
        return acc_list_full

    bulk_rows: List[Dict[str, Any]] = []
    for acc in _accounts_for_bulk():
        aid = _get_account_id(acc)
        if not aid:
            continue
        plat = str(acc.get("platform") or "").strip().lower()
        extra_acc: Dict[str, Any] = {"accountId": aid}
        if plat:
            extra_acc["platform"] = plat
        elif platform_filter:
            extra_acc["platform"] = platform_filter
        bulk_rows.extend(await _fetch_bulk_analytics_pages(extra_acc))

    if not bulk_rows:
        extra_fb: Dict[str, Any] = {}
        if platform_filter:
            extra_fb["platform"] = platform_filter
        else:
            # Same default as Social Inbox analytics when no platform filter is selected.
            extra_fb["platform"] = "facebook"
        bulk_rows = await _fetch_bulk_analytics_pages(extra_fb)

    engagement_keys = ("likes", "comments", "shares", "reach", "clicks", "saves")

    def _merge_eng(a: Dict[str, int], b: Dict[str, int]) -> Dict[str, int]:
        return {k: max(a.get(k, 0), b.get(k, 0)) for k in engagement_keys}

    engagement_by_id: Dict[str, Dict[str, int]] = {}
    for brow in bulk_rows:
        eng_b = _extract_engagement(brow)
        for pid in _all_ids(brow):
            if pid in engagement_by_id:
                engagement_by_id[pid] = _merge_eng(engagement_by_id[pid], eng_b)
            else:
                engagement_by_id[pid] = dict(eng_b)

    async def _fetch_post_engagement(post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch engagement for one post; try every connected Page until insights non-empty."""
        post_ids = _all_ids(post)
        if not post_ids:
            return None
        plat = str(post.get("platform") or platform_filter or "").lower()
        account_candidates: List[str] = []
        pa = _get_account_id(post)
        if pa:
            account_candidates.append(pa)
        for x in fallback_account_ids:
            if x and x not in account_candidates:
                account_candidates.append(x)
        if not account_candidates:
            account_candidates = [""]

        best_row: Optional[Dict[str, Any]] = None
        best_score = -1

        for account_id in account_candidates:
            params: Dict[str, Any] = {
                "profileId": profile_id,
                "metrics": METRICS,
                "postId": post_ids[0],
            }
            if account_id:
                params["accountId"] = account_id
            if plat:
                params["platform"] = plat

            data = await _zernio_get("/analytics", params)
            if not data:
                continue

            row: Optional[Dict[str, Any]] = None
            for key in ("data", "posts", "analytics", "results"):
                candidate = data.get(key)
                if isinstance(candidate, list) and candidate:
                    row = candidate[0]
                    break
                if isinstance(candidate, dict):
                    row = candidate
                    break
            if row is None:
                if any(k in data for k in ("likes", "like_count", "reactions", "shares", "share_count")):
                    row = data
            if not isinstance(row, dict):
                continue

            eng_try = _extract_engagement(row)
            score = sum(eng_try.values())
            if score > best_score:
                best_score = score
                best_row = row

        return best_row

    # Combine raw_posts + commented_posts; per-post Zernio calls only when bulk analytics has no row for that id.
    _seen_for_analytics: set = set()
    _posts_for_analytics: List[Dict[str, Any]] = []
    for _p in raw_posts + commented_posts:
        if not isinstance(_p, dict):
            continue
        _ids = _all_ids(_p)
        _canon = _ids[0] if _ids else None
        if _canon and _canon not in _seen_for_analytics:
            _posts_for_analytics.append(_p)
            _seen_for_analytics.add(_canon)

    def _needs_per_post_fetch(post: Dict[str, Any]) -> bool:
        """Bulk rows often carry comment counts but omit likes/reach without accountId-scoped insights.

        Also re-fetch when reach is missing specifically: Instagram organic posts and
        Facebook posts older than ~28 days routinely return likes from the bulk endpoint
        but no reach, which silently skews engagement-rate calculations toward zero.
        """
        eng: Dict[str, int] = {}
        for pid in _all_ids(post):
            if pid in engagement_by_id:
                eng = engagement_by_id[pid]
                break
        if not eng:
            return True
        insight_sum = (
            eng.get("likes", 0) + eng.get("shares", 0) + eng.get("reach", 0)
            + eng.get("clicks", 0) + eng.get("saves", 0)
        )
        if insight_sum == 0:
            return True
        # Reach is the most commonly-missing metric; if the bulk row had likes but
        # zero reach, give the per-post endpoint a chance to fill it in.
        return eng.get("likes", 0) > 0 and eng.get("reach", 0) == 0

    posts_needing_per_post: List[Dict[str, Any]] = [
        p for p in _posts_for_analytics if _needs_per_post_fetch(p)
    ][:PER_POST_FALLBACK_CAP]

    per_post_results = await _asyncio.gather(
        *[_fetch_post_engagement(p) for p in posts_needing_per_post],
        return_exceptions=True,
    )

    for i, result in enumerate(per_post_results):
        if not isinstance(result, dict):
            continue
        original_post = posts_needing_per_post[i] if i < len(posts_needing_per_post) else None
        if not original_post:
            continue
        eng_pp = _extract_engagement(result)
        for pid in _all_ids(original_post):
            engagement_by_id[pid] = eng_pp
        for pid in _all_ids(result):
            engagement_by_id.setdefault(pid, eng_pp)

    comment_count_by_id: Dict[str, int] = {}
    for row in commented_posts:
        if not isinstance(row, dict):
            continue
        cnt = _extract_int(row.get("commentCount"), row.get("comments_count"), row.get("comments"))
        for pid in _all_ids(row):
            comment_count_by_id[pid] = cnt

    # ── 6. Merge and format output ────────────────────────────────────────────
    def _post_text(row: Dict[str, Any]) -> str:
        for key in ("content", "caption", "message", "text", "title"):
            v = row.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:300]
        return "(no caption)"

    def _post_media_type(row: Dict[str, Any]) -> str:
        """Normalise Zernio media-type variants into image/video/carousel/text."""
        raw_mt = (row.get("mediaType") or row.get("media_type") or row.get("type") or "").strip().lower()
        if raw_mt in ("image", "photo"):
            return "image"
        if raw_mt in ("video", "reel", "reels"):
            return "video"
        if raw_mt in ("carousel", "carousel_album", "album"):
            return "carousel"
        # Fall back to inspecting media items list
        items = row.get("mediaItems") or row.get("media") or []
        if isinstance(items, list) and items:
            if len(items) > 1:
                return "carousel"
            first = items[0] if isinstance(items[0], dict) else {}
            t = str(first.get("type") or "").lower()
            if t in ("video", "reel"):
                return "video"
            if t in ("image", "photo"):
                return "image"
        # Has thumbnail/picture but no other signal → assume image
        if row.get("thumbnailUrl") or row.get("picture") or row.get("imageUrl"):
            return "image"
        return "text"

    def _build_post(row: Dict[str, Any], canonical: str, eng: Dict[str, int]) -> Dict[str, Any]:
        created = row.get("createdTime") or row.get("created_at") or row.get("createdAt") or row.get("publishedAt") or ""
        return {
            "id":        canonical,
            "platform":  str(row.get("platform") or platform_filter or "unknown").lower(),
            "text":      _post_text(row),
            "permalink": row.get("permalink") or row.get("url") or row.get("platformPostUrl") or "",
            "created_at": created,
            "media_type": _post_media_type(row),
            "engagement": eng,
            "engagement_score": eng.get("likes", 0) + eng.get("comments", 0) * 2 + eng.get("shares", 0) * 3 + eng.get("clicks", 0),
        }

    seen_ids: set = set()
    result_posts: List[Dict[str, Any]] = []

    for row in raw_posts:
        if not isinstance(row, dict):
            continue
        ids = _all_ids(row)
        canonical = ids[0] if ids else None
        if not canonical or any(i in seen_ids for i in ids):
            continue
        for i in ids:
            seen_ids.add(i)

        eng: Dict[str, int] = {}
        for pid in ids:
            if pid in engagement_by_id:
                eng = engagement_by_id[pid]
                break
        if not eng:
            eng = _extract_engagement(row)

        for pid in ids:
            if pid in comment_count_by_id:
                eng["comments"] = max(eng.get("comments", 0), comment_count_by_id[pid])
                break

        result_posts.append(_build_post(row, canonical, eng))

    # Also surface commented posts not already in the list
    for row in commented_posts:
        if not isinstance(row, dict):
            continue
        ids = _all_ids(row)
        canonical = ids[0] if ids else None
        if not canonical or any(i in seen_ids for i in ids):
            continue
        for i in ids:
            seen_ids.add(i)
        eng: Dict[str, int] = {}
        for pid in ids:
            if pid in engagement_by_id:
                eng = engagement_by_id[pid]
                break
        if not eng:
            eng = _extract_engagement(row)
        cnt = max(
            eng.get("comments", 0),
            *[comment_count_by_id.get(pid, 0) for pid in ids],
        )
        eng["comments"] = cnt
        result_posts.append(_build_post(row, canonical, eng))

    # Posts that appear in bulk analytics but not in /posts or inbox/comments.
    for row in bulk_rows:
        if not isinstance(row, dict):
            continue
        ids = _all_ids(row)
        canonical = ids[0] if ids else None
        if not canonical or any(i in seen_ids for i in ids):
            continue
        for i in ids:
            seen_ids.add(i)
        eng = {}
        for pid in ids:
            if pid in engagement_by_id:
                eng = dict(engagement_by_id[pid])
                break
        if not eng:
            eng = _extract_engagement(row)
        cnt = max(
            eng.get("comments", 0),
            *[comment_count_by_id.get(pid, 0) for pid in ids],
        )
        eng["comments"] = cnt
        result_posts.append(_build_post(row, canonical, eng))

    result_posts.sort(key=lambda x: x["engagement_score"], reverse=True)

    totals = {"likes": 0, "comments": 0, "shares": 0, "reach": 0, "clicks": 0, "saves": 0}
    # Per-metric coverage: how many posts contributed a non-zero value to each total.
    # The assistant uses this to avoid quoting misleading sums (e.g. "19 reach across
    # 50 posts" when really only 1 post returned a reach number).
    metric_coverage = {"likes": 0, "comments": 0, "shares": 0, "reach": 0, "clicks": 0, "saves": 0}
    for p in result_posts:
        for k in totals:
            v = p["engagement"].get(k, 0) or 0
            totals[k] += v
            if v > 0:
                metric_coverage[k] += 1

    total_posts = len(result_posts)

    def _coverage_pct(metric: str) -> float:
        return round((metric_coverage[metric] / total_posts) * 100, 1) if total_posts else 0.0

    coverage_pct = {k: _coverage_pct(k) for k in metric_coverage}
    # Flag metrics where fewer than 30% of posts reported a value — these totals are
    # not representative of the full post set and should be qualified, not quoted bare.
    low_coverage_metrics = [k for k, pct in coverage_pct.items() if pct < 30.0 and total_posts > 0]
    metric_notes: List[str] = []
    if "reach" in low_coverage_metrics:
        metric_notes.append(
            f"reach data only available for {metric_coverage['reach']}/{total_posts} posts "
            f"({coverage_pct['reach']}%) — Instagram organic posts and older Facebook posts often "
            "do not return reach via the Graph API. Do not quote total reach as a complete number."
        )
    if "clicks" in low_coverage_metrics:
        metric_notes.append(
            f"clicks data only available for {metric_coverage['clicks']}/{total_posts} posts — "
            "click-through is typically only tracked for posts with link attachments or boosted posts."
        )
    if "shares" in low_coverage_metrics and metric_coverage["shares"] > 0:
        metric_notes.append(
            f"shares data only available for {metric_coverage['shares']}/{total_posts} posts."
        )
    # Special case: Facebook + Instagram organic share counts are essentially never
    # available via Zernio. Facebook's Graph API exposes shares as `shares.count` on the
    # post object, but Zernio's analytics sync only pulls /insights metrics (which omit
    # shares), so almost every Facebook post returns shares=0 even when the post was
    # actually shared. Instagram doesn't expose organic share counts at all. Always
    # warn about this when there are Facebook or Instagram posts with no shares.
    fb_ig_post_count = sum(
        1 for p in result_posts if str(p.get("platform") or "").lower() in ("facebook", "instagram")
    )
    if fb_ig_post_count > 0 and metric_coverage["shares"] == 0:
        metric_notes.append(
            "share counts for Facebook and Instagram posts are NOT reliably reported by the social "
            "API: Facebook's Graph insights endpoint omits shares (you'd need to query the post's "
            "shares.count field directly), and Instagram does not expose organic shares at all. "
            "If a Facebook post shows 0 shares here but you can see it was shared on Facebook, "
            "trust Facebook — direct the owner to the post's permalink to see the real share count."
        )

    # ── Upstream sync health (from /analytics overview) ──────────────────────
    # The upstream response carries `overview.dataStaleness.syncTriggered` and
    # `overview.lastSync`. We surface them so the AI can explain "we are
    # actively syncing right now" vs "no sync queued, data is the latest"
    # without having to guess.
    sync_health: Dict[str, Any] = {}
    if isinstance(account_snapshot_data, dict):
        overview = account_snapshot_data.get("overview") or {}
        if isinstance(overview, dict):
            stale = overview.get("dataStaleness") or {}
            sync_health = {
                "last_sync_at": overview.get("lastSync"),
                "sync_triggered": bool(stale.get("syncTriggered")) if isinstance(stale, dict) else None,
                "stale_account_count": stale.get("staleAccountCount") if isinstance(stale, dict) else None,
                "has_analytics_access": account_snapshot_data.get("hasAnalyticsAccess"),
            }

    # ── Account-level snapshot (followers etc.) from /analytics?period=30d ────
    # This complements per-post engagement with audience-size context the AI can use
    # to triangulate ("18 reach against 1010 FB followers = 1.8% reach rate").
    accounts_summary: List[Dict[str, Any]] = []
    total_followers_by_platform: Dict[str, int] = {}

    # Cross-reference: how many posts did the merged result include per platform?
    posts_per_platform_count: Dict[str, int] = {}
    for p in result_posts:
        pp = str(p.get("platform") or "").lower()
        if pp:
            posts_per_platform_count[pp] = posts_per_platform_count.get(pp, 0) + 1

    # Pull external_post_count + lastSyncedAt straight from the /accounts payload
    # (the sync_state we stored earlier). Lets us derive a meaningful sync_status.
    accounts_meta_by_id: Dict[str, Dict[str, Any]] = {}
    if isinstance(accounts_data, dict):
        for a in (accounts_data.get("accounts") or accounts_data.get("data") or []):
            if isinstance(a, dict):
                aid = _get_account_id(a)
                if aid:
                    accounts_meta_by_id[aid] = a

    if isinstance(account_snapshot_data, dict):
        snapshot_accounts = account_snapshot_data.get("accounts") or []
        if isinstance(snapshot_accounts, list):
            for acc in snapshot_accounts:
                if not isinstance(acc, dict):
                    continue
                plat = str(acc.get("platform") or "").lower()
                aid = acc.get("_id") or acc.get("id")
                followers = _extract_int(
                    acc.get("followersCount"),
                    acc.get("followers_count"),
                    acc.get("followers"),
                    acc.get("fan_count"),
                    acc.get("fanCount"),
                )

                # Pull sync state from the /accounts payload (richer than /analytics)
                meta = accounts_meta_by_id.get(str(aid) if aid else "", {}) or {}
                external_post_count = _extract_int(
                    meta.get("externalPostCount"),
                    meta.get("external_post_count"),
                    acc.get("externalPostCount"),
                )
                last_synced_at = (
                    meta.get("lastSyncedAt")
                    or meta.get("last_synced_at")
                    or meta.get("analyticsLastSyncedAt")
                    or acc.get("lastSyncedAt")
                )
                merged_post_count = posts_per_platform_count.get(plat, 0)

                # Derive a status the AI can act on without doing the math itself.
                if merged_post_count > 0:
                    sync_status = "synced"
                    sync_message = None
                elif external_post_count > 0:
                    # Posts exist on the platform but they haven't arrived in
                    # /posts/analytics yet — sync is still in progress.
                    sync_status = "sync_in_progress"
                    sync_message = (
                        f"We can see {external_post_count} {plat} posts on this account but "
                        "they haven't fully synced yet. Try again in 30–60 minutes."
                    )
                elif not last_synced_at:
                    # Fresh connection, sync hasn't run yet at all.
                    sync_status = "pending_first_sync"
                    sync_message = (
                        f"{plat.title()} account connected, but the first post sync hasn't completed yet. "
                        "Initial sync usually finishes within 30–60 minutes of connecting."
                    )
                else:
                    # Synced but the platform genuinely has no posts published.
                    sync_status = "no_posts_published"
                    sync_message = (
                        f"{plat.title()} account is synced, but no posts have been published from it."
                    )

                accounts_summary.append({
                    "account_id": aid,
                    "platform": plat,
                    "username": acc.get("username"),
                    "display_name": acc.get("displayName") or acc.get("name"),
                    "followers": followers,
                    "followers_last_updated": acc.get("followersLastUpdated") or acc.get("followers_last_updated"),
                    "external_post_count": external_post_count,
                    "last_synced_at": last_synced_at,
                    "merged_post_count": merged_post_count,
                    "sync_status": sync_status,
                    "sync_message": sync_message,
                })
                if plat:
                    total_followers_by_platform[plat] = total_followers_by_platform.get(plat, 0) + followers

    # Surface a top-level diagnostics block so the AI doesn't have to scan the
    # accounts_summary list to figure out which platforms are healthy.
    platform_diagnostics: Dict[str, Dict[str, Any]] = {}
    for acc in accounts_summary:
        plat = acc.get("platform")
        if not plat:
            continue
        entry = platform_diagnostics.setdefault(plat, {
            "accounts_connected": 0,
            "total_posts_in_response": 0,
            "total_external_post_count": 0,
            "sync_statuses": [],
            "messages": [],
        })
        entry["accounts_connected"] += 1
        entry["total_posts_in_response"] += acc.get("merged_post_count") or 0
        entry["total_external_post_count"] += acc.get("external_post_count") or 0
        entry["sync_statuses"].append(acc.get("sync_status"))
        if acc.get("sync_message"):
            entry["messages"].append(acc["sync_message"])

    # ── Persist + read follower history for growth tracking ──────────────────
    # We snapshot once per UTC day per account, so calling this tool repeatedly
    # in a single day is cheap. After ≥2 days of data, the assistant can quote
    # "+X followers since last week" — without that history the answer is just
    # "we don't have a comparison point yet, ask again tomorrow".
    follower_growth_by_platform = await _record_and_read_follower_history(
        ctx, accounts_summary
    )

    # ── Derived insights ──────────────────────────────────────────────────────
    # Everything below is computed locally from data we already have, so the
    # assistant gets concrete strategy signals without needing data Zernio
    # doesn't expose (audience demographics, etc.). Each block carries a
    # `sample_size` so the LLM can decide whether the signal is trustworthy.
    derived_insights = _compute_derived_insights(result_posts, total_followers_by_platform)

    return {
        "source": "social_live",
        "note": (
            "Paginated bulk analytics per connected Page (accountId), same as Social Inbox; "
            "per-post analytics fills missing likes/reach when bulk only had comment counts. "
            "`accounts_summary` carries audience-size context (followers per Page) so totals can be "
            "interpreted against the actual audience reached. `derived_insights` carries computed "
            "strategy signals (engagement rate, best publish hour/day, media-type performance, "
            "posting cadence, top posts) — the assistant should prefer these over re-deriving them."
        ),
        "total_posts": total_posts,
        "totals": totals,
        # ↓ The assistant should ALWAYS check `metric_coverage` before quoting a total.
        "metric_coverage": metric_coverage,
        "metric_coverage_pct": coverage_pct,
        "low_coverage_metrics": low_coverage_metrics,
        "metric_notes": metric_notes,
        "accounts_summary": accounts_summary,
        "platform_diagnostics": platform_diagnostics,
        "sync_health": sync_health,
        "total_followers_by_platform": total_followers_by_platform,
        "follower_growth_by_platform": follower_growth_by_platform,
        "derived_insights": derived_insights,
        "posts": result_posts[:limit],
        "bulk_analytics_rows_loaded": len(bulk_rows),
        "profile_auto_repaired": profile_healed,
        "diagnostics": {
            "connected_accounts": len(fallback_account_ids),
            "posts_from_posts_endpoint": len(raw_posts),
            "posts_from_inbox_comments": len(commented_posts),
            "analytics_rows_merged": len(bulk_rows),
            "posts_after_merge": total_posts,
        },
    }


# ── Derived-insights helper (used by get_live_social_posts) ──────────────────
def _compute_derived_insights(
    posts: List[Dict[str, Any]],
    followers_by_platform: Dict[str, int],
) -> Dict[str, Any]:
    """Compute strategy signals from the owner's own post history.

    All numbers come from data we already have on hand. Each section carries a
    `sample_size` (or `posts_considered`) so the assistant can refuse to make
    sweeping claims off a tiny sample.
    """
    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    MIN_SAMPLE_FOR_PATTERN = 5  # need at least this many posts before we trust a "best hour" claim

    def _parse_dt(s: Any) -> Optional[datetime]:
        if not s or not isinstance(s, str):
            return None
        try:
            # Zernio returns ISO 8601 with trailing Z
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    # Group posts by platform
    by_platform: Dict[str, List[Dict[str, Any]]] = {}
    for p in posts:
        plat = (p.get("platform") or "unknown").lower()
        by_platform.setdefault(plat, []).append(p)

    # 1) Engagement rate per platform = (likes + comments + shares) / followers × 100.
    #    This is the most-cited cross-platform health metric and only requires
    #    follower counts (which we now pull via /analytics?period=30d).
    engagement_rate_by_platform: Dict[str, Dict[str, Any]] = {}
    for plat, plist in by_platform.items():
        followers = followers_by_platform.get(plat, 0) or 0
        if followers <= 0:
            continue
        # Per-post rates so we can also report a representative average rather
        # than just total-engagement / followers (which conflates frequency).
        per_post_rates: List[float] = []
        for p in plist:
            eng = p.get("engagement", {}) or {}
            interactions = (eng.get("likes", 0) or 0) + (eng.get("comments", 0) or 0) + (eng.get("shares", 0) or 0)
            per_post_rates.append((interactions / followers) * 100)
        if not per_post_rates:
            continue
        engagement_rate_by_platform[plat] = {
            "avg_engagement_rate_pct": round(sum(per_post_rates) / len(per_post_rates), 3),
            "best_post_engagement_rate_pct": round(max(per_post_rates), 3),
            "followers": followers,
            "sample_size": len(per_post_rates),
            "formula": "(likes + comments + shares) / followers × 100, averaged across posts",
        }

    # 2) Best publish hour per platform — group posts into hour-of-day buckets
    #    and pick the one with the highest mean engagement_score.
    def _best_bucket(plist: List[Dict[str, Any]], key_fn) -> Optional[Dict[str, Any]]:
        buckets: Dict[Any, List[float]] = {}
        for p in plist:
            dt = _parse_dt(p.get("created_at"))
            if dt is None:
                continue
            k = key_fn(dt)
            buckets.setdefault(k, []).append(float(p.get("engagement_score", 0) or 0))
        if not buckets:
            return None
        ranked = sorted(
            ((k, sum(v) / len(v), len(v)) for k, v in buckets.items()),
            key=lambda x: x[1],
            reverse=True,
        )
        best_k, best_avg, best_n = ranked[0]
        return {
            "bucket": best_k,
            "avg_engagement_score": round(best_avg, 2),
            "posts_in_bucket": best_n,
            "all_buckets": [
                {"bucket": k, "avg_engagement_score": round(avg, 2), "posts": n}
                for k, avg, n in ranked
            ],
        }

    best_publish_hour_by_platform: Dict[str, Dict[str, Any]] = {}
    best_publish_day_by_platform: Dict[str, Dict[str, Any]] = {}
    for plat, plist in by_platform.items():
        if len(plist) < MIN_SAMPLE_FOR_PATTERN:
            continue
        hour = _best_bucket(plist, lambda d: d.hour)
        if hour:
            best_publish_hour_by_platform[plat] = {
                "hour_utc": hour["bucket"],
                "avg_engagement_score": hour["avg_engagement_score"],
                "posts_in_bucket": hour["posts_in_bucket"],
                "sample_size": len(plist),
                "note": "Hour is in UTC. Times derived from the owner's own posts on this platform.",
            }
        day = _best_bucket(plist, lambda d: d.weekday())
        if day:
            best_publish_day_by_platform[plat] = {
                "day_of_week": DAY_NAMES[day["bucket"]] if 0 <= day["bucket"] < 7 else str(day["bucket"]),
                "avg_engagement_score": day["avg_engagement_score"],
                "posts_in_bucket": day["posts_in_bucket"],
                "sample_size": len(plist),
            }

    # 3) Media-type performance — image vs video vs carousel vs text.
    media_type_performance: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for plat, plist in by_platform.items():
        type_groups: Dict[str, List[float]] = {}
        for p in plist:
            mt = p.get("media_type") or "unknown"
            type_groups.setdefault(mt, []).append(float(p.get("engagement_score", 0) or 0))
        if not type_groups:
            continue
        media_type_performance[plat] = {
            mt: {
                "avg_engagement_score": round(sum(scores) / len(scores), 2),
                "post_count": len(scores),
            }
            for mt, scores in type_groups.items()
        }

    # 4) Posting cadence — posts/week, longest gap, days since last post.
    posting_cadence: Dict[str, Dict[str, Any]] = {}
    now = datetime.utcnow().replace(tzinfo=None)
    for plat, plist in by_platform.items():
        dts = sorted(
            [d for d in (_parse_dt(p.get("created_at")) for p in plist) if d is not None]
        )
        if not dts:
            continue
        # Strip tz to keep arithmetic simple (treat all as UTC)
        dts = [d.replace(tzinfo=None) for d in dts]
        gaps = [(dts[i + 1] - dts[i]).total_seconds() / 86400 for i in range(len(dts) - 1)]
        span_days = (dts[-1] - dts[0]).total_seconds() / 86400 if len(dts) > 1 else 0
        days_since_last = (now - dts[-1]).total_seconds() / 86400
        posting_cadence[plat] = {
            "posts_per_week": round((len(dts) / span_days) * 7, 2) if span_days > 0 else None,
            "longest_gap_days": round(max(gaps), 1) if gaps else None,
            "avg_gap_days": round(sum(gaps) / len(gaps), 1) if gaps else None,
            "days_since_last_post": round(days_since_last, 1),
            "first_post_at": dts[0].isoformat(),
            "last_post_at": dts[-1].isoformat(),
            "post_count": len(dts),
        }

    # 5) Top 3 posts overall (already sorted by engagement_score upstream).
    top_3_posts = [
        {
            "id": p["id"],
            "platform": p["platform"],
            "permalink": p.get("permalink"),
            "media_type": p.get("media_type"),
            "engagement": p.get("engagement"),
            "engagement_score": p.get("engagement_score"),
            "text_preview": (p.get("text") or "")[:140],
        }
        for p in posts[:3]
    ]

    # 6) Heuristic recommended actions — turn the above into 1–3 plain-English nudges.
    recommended_actions: List[str] = []
    for plat, cad in posting_cadence.items():
        if cad.get("days_since_last_post") and cad["days_since_last_post"] > 7:
            recommended_actions.append(
                f"You haven't posted on {plat} in {cad['days_since_last_post']:.0f} days — "
                "your posting cadence has dropped, consider scheduling something this week."
            )
    for plat, perf in media_type_performance.items():
        if len(perf) < 2:
            continue
        ranked = sorted(perf.items(), key=lambda x: x[1]["avg_engagement_score"], reverse=True)
        top_type, top_data = ranked[0]
        bottom_type, bottom_data = ranked[-1]
        if top_data["post_count"] >= 2 and top_data["avg_engagement_score"] > bottom_data["avg_engagement_score"] * 1.5:
            recommended_actions.append(
                f"On {plat}, your {top_type} posts average "
                f"{top_data['avg_engagement_score']:.0f} engagement vs {bottom_data['avg_engagement_score']:.0f} "
                f"for {bottom_type} — lean into more {top_type} content."
            )
    for plat, hr in best_publish_hour_by_platform.items():
        recommended_actions.append(
            f"On {plat}, posts published around {hr['hour_utc']:02d}:00 UTC perform best "
            f"(avg engagement {hr['avg_engagement_score']:.0f} across {hr['posts_in_bucket']} posts)."
        )

    return {
        "engagement_rate_by_platform": engagement_rate_by_platform,
        "best_publish_hour_by_platform": best_publish_hour_by_platform,
        "best_publish_day_by_platform": best_publish_day_by_platform,
        "media_type_performance": media_type_performance,
        "posting_cadence": posting_cadence,
        "top_3_posts": top_3_posts,
        "recommended_actions": recommended_actions[:5],
        "methodology_note": (
            "All signals derived locally from the owner's own posts. "
            f"Patterns require ≥{MIN_SAMPLE_FOR_PATTERN} posts on a platform to be reported. "
            "Hours are UTC. Audience demographic data (age, gender, geography) is not available "
            "from the current API and is intentionally excluded."
        ),
    }


async def _record_and_read_follower_history(
    ctx: ToolContext,
    accounts_summary: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Snapshot today's follower counts (idempotent per UTC day) and read history.

    Stores rows in `social_follower_snapshots` with a unique key on
    (business_id, account_id, date) so calling the parent tool repeatedly in
    a single day overwrites the same row instead of bloating the collection.

    Returns a per-platform growth payload the assistant can quote directly:
        {
          "facebook": {
            "current": 1010,
            "delta_7d": 12,
            "delta_30d": 47,
            "history_start": "2026-04-15T00:00:00Z",
            "history_points": 17
          },
          ...
        }
    """
    if not accounts_summary:
        return {}

    coll = ctx.db.social_follower_snapshots
    today_utc = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    now_utc = datetime.utcnow()

    # ── Persist today's snapshot per account (upsert keyed on the UTC date) ──
    for acc in accounts_summary:
        if not acc.get("account_id") or not acc.get("followers"):
            continue
        try:
            await coll.update_one(
                {
                    "business_id": ctx.business_id,
                    "account_id": str(acc["account_id"]),
                    "date": today_utc,
                },
                {
                    "$set": {
                        "business_id": ctx.business_id,
                        "account_id": str(acc["account_id"]),
                        "platform": acc.get("platform"),
                        "username": acc.get("username"),
                        "followers": int(acc["followers"]),
                        "date": today_utc,
                        "updated_at": now_utc,
                    },
                    "$setOnInsert": {"created_at": now_utc},
                },
                upsert=True,
            )
        except Exception as exc:
            logger.warning("follower-snapshot upsert failed for account %s: %s", acc.get("account_id"), exc)

    # ── Read back history for each platform we just snapshotted ──────────────
    platforms_today: Set[str] = {
        str(a.get("platform")) for a in accounts_summary if a.get("platform")
    }
    growth: Dict[str, Any] = {}

    for plat in platforms_today:
        try:
            cursor = coll.find(
                {"business_id": ctx.business_id, "platform": plat},
                {"date": 1, "followers": 1, "account_id": 1, "_id": 0},
            ).sort("date", 1)
            rows = await cursor.to_list(length=400)
        except Exception as exc:
            logger.warning("follower-snapshot read failed for platform %s: %s", plat, exc)
            continue

        if not rows:
            continue

        # Sum across accounts within the same UTC day (a business can have multiple
        # Pages on the same platform).
        by_date: Dict[datetime, int] = {}
        for r in rows:
            d = r.get("date")
            if not isinstance(d, datetime):
                continue
            by_date[d] = by_date.get(d, 0) + int(r.get("followers") or 0)

        if not by_date:
            continue

        sorted_dates = sorted(by_date.keys())
        latest = sorted_dates[-1]
        current = by_date[latest]

        def _delta_for(days: int) -> Optional[int]:
            cutoff = latest - timedelta(days=days)
            past = [by_date[d] for d in sorted_dates if d <= cutoff]
            if not past:
                return None
            return current - past[-1]

        growth[plat] = {
            "current": current,
            "delta_7d": _delta_for(7),
            "delta_30d": _delta_for(30),
            "history_start": sorted_dates[0].isoformat() + "Z",
            "history_points": len(sorted_dates),
            "note": (
                "Tracking starts the first time this tool runs. Deltas require enough "
                "history to span the requested window — `null` means we don't yet have a "
                "data point that far back."
            ),
        }

    return growth


@tool(
    name="get_business_context",
    description=(
        "Pulls unified business context across all modules so Zilo can remember everything. "
        "Use this before drafting personalized messages, follow-ups, or posts. "
        "Returns recent customers, orders, social engagement, broadcasts, follow-ups, and top products. "
        "If a customer name/email is provided, returns that customer's full history."
    ),
    parameters={
        "type": "object",
        "properties": {
            "customer_name_or_email": {
                "type": "string",
                "description": "Optional: name or email of a specific customer to fetch their full history. Omit for business-wide snapshot.",
            },
            "days": {
                "type": "integer",
                "default": 7,
                "description": "How many days of recent activity to include (1–30).",
            },
        },
    },
)
async def get_business_context(ctx: ToolContext, args: Dict[str, Any]):
    days = max(1, min(int(args.get("days") or 7), 30))
    customer_query = (args.get("customer_name_or_email") or "").strip()
    limit = 20

    # ── Helper: match customer by name/email ─────────────────────────────────────
    async def _find_customer(query: str):
        if not query:
            return None
        # Try email exact match first
        email_match = await ctx.db.customers.find_one({
            "business_id": ctx.business_id,
            "email": {"$regex": f"^{query}$", "$options": "i"},
        })
        if email_match:
            return email_match
        # Try name contains
        name_match = await ctx.db.customers.find_one({
            "business_id": ctx.business_id,
            "name": {"$regex": query, "$options": "i"},
        })
        return name_match

    # ── 1. Customer snapshot (or specific customer) ───────────────────────────────
    target_customer = await _find_customer(customer_query)
    if target_customer:
        # Full history for this customer
        customer_id = str(target_customer["_id"])
        orders = await ctx.db.orders.find({
            "business_id": ctx.business_id,
            "customer_id": customer_id,
            "created_at": {"$gte": f"{datetime.utcnow() - timedelta(days=days):.0f}"}
        }).to_list(length=limit)
        followups = await ctx.db.followups.find({
            "business_id": ctx.business_id,
            "customer_id": customer_id,
            "created_at": {"$gte": f"{datetime.utcnow() - timedelta(days=days):.0f}"}
        }).to_list(length=limit)
        # Social inbox mentions (via Zernio conversations)
        social_refs = []
        # Note: would need to index Zernio conversations by customer name/email for true cross-ref
        customers = [target_customer]
    else:
        # Recent customers
        customers = await ctx.db.customers.find({
            "business_id": ctx.business_id,
            "created_at": {"$gte": f"{datetime.utcnow() - timedelta(days=days):.0f}"}
        }).sort("created_at", -1).to_list(length=limit)
        orders = await ctx.db.orders.find({
            "business_id": ctx.business_id,
            "created_at": {"$gte": f"{datetime.utcnow() - timedelta(days=days):.0f}"}
        }).sort("created_at", -1).to_list(length=limit)
        followups = await ctx.db.followups.find({
            "business_id": ctx.business_id,
            "created_at": {"$gte": f"{datetime.utcnow() - timedelta(days=days):.0f}"}
        }).sort("created_at", -1).to_list(length=limit)
        social_refs = []

    # ── 2. Recent broadcasts ─────────────────────────────────────────────────────
    broadcasts = await ctx.db.broadcasts.find({
        "business_id": ctx.business_id,
        "created_at": {"$gte": f"{datetime.utcnow() - timedelta(days=days):.0f}"}
    }).sort("created_at", -1).to_list(length=limit)

    # ── 3. Top products (by order count in window) ────────────────────────────────
    product_counts = {}
    for o in orders:
        for item in o.get("items", []):
            pid = item.get("product_id")
            if pid:
                product_counts[pid] = product_counts.get(pid, 0) + (item.get("quantity") or 1)
    top_product_ids = sorted(product_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_products = []
    if top_product_ids:
        product_docs = await ctx.db.products.find({
            "_id": {"$in": [ObjectId(pid) for pid, _ in top_product_ids]}
        }).to_list(length=None)
        product_map = {str(doc["_id"]): doc for doc in product_docs}
        top_products = [
            {
                "product": product_map.get(pid),
                "order_count": cnt,
            }
            for pid, cnt in top_product_ids
            if pid in product_map
        ]

    # ── 4. Social engagement summary ─────────────────────────────────────────────
    # Reuse existing tools for consistency
    from . import get_live_social_posts, get_social_post_analytics
    social_live = await get_live_social_posts(ctx, {"platform": None, "limit": 50})
    social_analytics = await get_social_post_analytics(ctx, {"days": days})

    # ── 5. Business quick stats ───────────────────────────────────────────────────
    quick_stats = {
        "new_customers": len(customers),
        "orders": len(orders),
        "broadcasts": len(broadcasts),
        "followups": len(followups),
        "top_product": top_products[0]["product"]["name"] if top_products else None,
        "total_revenue_window": sum(o.get("total", 0) for o in orders),
    }

    # ── 6. Assemble response ─────────────────────────────────────────────────────
    return {
        "scope": "customer" if target_customer else "business",
        "customer": target_customer,
        "customers": customers,
        "orders": orders,
        "followups": followups,
        "broadcasts": broadcasts,
        "top_products": top_products,
        "social_live": social_live.get("posts", [])[:25],
        "social_analytics": social_analytics,
        "quick_stats": quick_stats,
        "window_days": days,
    }


@tool(
    name="get_kling_video_status",
    description=(
        "Poll the status of a Kling AI video generation task. "
        "Returns status ('generating', 'success', 'failed') and the video URL when done. "
        "Keep polling every 8–10s until status is 'success' or 'failed' (max 10 attempts)."
    ),
    parameters={
        "type": "object",
        "required": ["task_id"],
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task_id returned by create_kling_video.",
            },
        },
    },
)
async def get_kling_video_status(ctx: ToolContext, args: Dict[str, Any]):
    import httpx
    import json as _json

    task_id = (args.get("task_id") or "").strip()
    if not task_id:
        return {"error": "task_id is required"}

    try:
        headers = _kling_headers()
        async with httpx.AsyncClient(timeout=20.0) as client:
            # KIE uses recordInfo endpoint with taskId query param
            resp = await client.get(
                f"{_KLING_API_BASE}/jobs/recordInfo?taskId={task_id}",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except RuntimeError as e:
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"error": f"Kling API error: {e.response.status_code} — {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Status check failed: {e}"}

    job = data.get("data") or {}
    state = job.get("state", "unknown")

    # Extract video URL — KIE returns it inside resultJson as a JSON string
    url = ""
    result_json_str = job.get("resultJson", "")
    if result_json_str:
        try:
            result = _json.loads(result_json_str)
            urls = result.get("resultUrls", [])
            if urls:
                url = urls[0]
        except Exception:
            pass

    # Update DB record
    if url and state == "success":
        try:
            await ctx.db.kling_renders.update_one(
                {"task_id": task_id, "business_id": ctx.business_id},
                {"$set": {"status": state, "url": url, "updated_at": datetime.utcnow()}},
            )
        except Exception:
            pass

    return {
        "task_id": task_id,
        "status": state,
        "url": url,
        "done": state in ("success", "failed"),
    }


# ── Shotstack Image & Voice Generation (complements Kling video) ─────────────────

_SHOTSTACK_API_KEY = os.getenv("SHOTSTACK_API_KEY")
_SHOTSTACK_API_URL = os.getenv("SHOTSTACK_API_URL", "https://api.shotstack.io/v1")


def _shotstack_headers() -> dict:
    if not _SHOTSTACK_API_KEY:
        raise RuntimeError("SHOTSTACK_API_KEY is not configured")
    return {"x-api-key": _SHOTSTACK_API_KEY, "content-type": "application/json"}


@tool(
    name="create_shotstack_image",
    description=(
        "Generate a high-quality image using Shotstack templates. "
        "Perfect for creating posters, thumbnails, social media graphics, and marketing visuals. "
        "Supports text overlays, backgrounds, and design assets. Returns a render_id to track progress."
    ),
    parameters={
        "type": "object",
        "properties": {
            "template_name": {
                "type": "string",
                "description": "Name for this image template (e.g., 'Product Poster', 'Event Thumbnail')",
            },
            "text_content": {
                "type": "string", 
                "description": "Main text to display on the image",
            },
            "background": {
                "type": "string",
                "description": "Background color (hex) or image URL",
                "default": "#1a1a1a",
            },
            "format": {
                "type": "string",
                "enum": ["jpg", "png"],
                "description": "Output format",
                "default": "png",
            },
            "width": {
                "type": "integer",
                "description": "Image width in pixels",
                "default": 1920,
            },
            "height": {
                "type": "integer", 
                "description": "Image height in pixels",
                "default": 1080,
            },
        },
        "required": ["template_name", "text_content"],
    },
)
async def create_shotstack_image(ctx: ToolContext, args: Dict[str, Any]):
    import httpx
    
    template_name = args["template_name"].strip()
    text_content = args["text_content"].strip()
    background = args.get("background", "#1a1a1a")
    format = args.get("format", "png")
    width = int(args.get("width", 1920))
    height = int(args.get("height", 1080))
    
    # Build Shotstack timeline for image
    timeline = {
        "output": {
            "format": format,
            "resolution": {"width": width, "height": height},
            "quality": "high"
        },
        "timeline": {
            "tracks": [{
                "clips": [{
                    "asset": {
                        "type": "title",
                        "text": text_content,
                        "style": {
                            "fontSize": f"{max(48, min(120, width // 16))}px",
                            "fontFamily": "Montserrat",
                            "backgroundColor": "#00000000",
                            "color": "#ffffff",
                            "textAlign": "center",
                            "fontWeight": "bold"
                        }
                    },
                    "start": 0,
                    "length": 5,
                    "position": "center"
                }]
            }]
        }
    }
    
    # Add background
    if background.startswith("#"):
        timeline["timeline"]["tracks"][0]["clips"][0]["asset"]["type"] = "title"
        timeline["timeline"]["tracks"][0]["clips"][0]["asset"]["style"]["backgroundColor"] = background
    elif background.startswith(("http", "/")):
        timeline["timeline"]["tracks"].insert(0, {
            "clips": [{
                "asset": {
                    "type": "image",
                    "src": background
                },
                "start": 0,
                "length": 5,
                "fit": "cover"
            }]
        })
    
    try:
        headers = _shotstack_headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_SHOTSTACK_API_URL}/render",
                headers=headers,
                json=timeline
            )
            resp.raise_for_status()
            data = resp.json()
            
    except RuntimeError as e:
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"error": f"Shotstack API error: {e.response.status_code} — {e.response.text[:300]}"}
    except Exception as e:
        return {"error": f"Shotstack image request failed: {e}"}
    
    render_id = data.get("response", {}).get("id")
    if not render_id:
        return {"error": "Shotstack did not return a render ID"}
    
    # Store in database
    try:
        await ctx.db.shotstack_renders.insert_one({
            "business_id": ctx.business_id,
            "render_id": render_id,
            "type": "image",
            "template_name": template_name,
            "text_content": text_content,
            "background": background,
            "format": format,
            "dimensions": {"width": width, "height": height},
            "status": "queued",
            "created_at": datetime.utcnow(),
        })
    except Exception as e:
        logging.warning(f"[shotstack] Failed to save render record: {e}")
    
    return {
        "render_id": render_id,
        "type": "image",
        "status": "queued",
        "message": "Shotstack image is generating. Use get_shotstack_render_status to track progress.",
    }


@tool(
    name="create_shotstack_voice",
    description=(
        "Generate high-quality voice audio using Shotstack text-to-speech. "
        "Perfect for voiceovers, narration, and audio content. Supports multiple voices and languages. "
        "Returns a render_id to track progress."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to convert to speech",
            },
            "voice": {
                "type": "string",
                "description": "Voice name (samantha, matthew, joanna, joseph, lisa, brian, camila, penelope, chantal, hans, zoe)",
                "default": "samantha",
            },
            "format": {
                "type": "string",
                "enum": ["mp3", "wav"],
                "description": "Audio format",
                "default": "mp3",
            },
        },
        "required": ["text"],
    },
)
async def create_shotstack_voice(ctx: ToolContext, args: Dict[str, Any]):
    import httpx
    
    text = args["text"].strip()
    voice = args.get("voice", "samantha")
    format = args.get("format", "mp3")
    
    # Build Shotstack timeline for voice
    timeline = {
        "output": {
            "format": format,
            "resolution": {"width": 1920, "height": 1080},  # Required even for audio
            "quality": "medium"
        },
        "timeline": {
            "soundtrack": {
                "tracks": [{
                    "clips": [{
                        "asset": {
                            "type": "audio",
                            "src": f"tts:{voice}",
                            "text": text,
                            "effect": "volume:0.8"
                        },
                        "start": 0,
                        "length": max(5, len(text) * 0.08)  # Estimate duration
                    }]
                }]
            }
        }
    }
    
    try:
        headers = _shotstack_headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_SHOTSTACK_API_URL}/render",
                headers=headers,
                json=timeline
            )
            resp.raise_for_status()
            data = resp.json()
            
    except RuntimeError as e:
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"error": f"Shotstack API error: {e.response.status_code} — {e.response.text[:300]}"}
    except Exception as e:
        return {"error": f"Shotstack voice request failed: {e}"}
    
    render_id = data.get("response", {}).get("id")
    if not render_id:
        return {"error": "Shotstack did not return a render ID"}
    
    # Store in database
    try:
        await ctx.db.shotstack_renders.insert_one({
            "business_id": ctx.business_id,
            "render_id": render_id,
            "type": "voice",
            "text": text,
            "voice": voice,
            "format": format,
            "status": "queued",
            "created_at": datetime.utcnow(),
        })
    except Exception as e:
        logging.warning(f"[shotstack] Failed to save render record: {e}")
    
    return {
        "render_id": render_id,
        "type": "voice",
        "status": "queued",
        "message": "Shotstack voice is generating. Use get_shotstack_render_status to track progress.",
    }


@tool(
    name="get_shotstack_render_status",
    description=(
        "Check the status of a Shotstack render (image or voice). "
        "Returns status ('queued', 'rendering', 'done', 'failed') and download URL when ready. "
        "Keep polling every 5-8s until status is 'done' or 'failed'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "render_id": {
                "type": "string",
                "description": "The render_id returned by create_shotstack_image or create_shotstack_voice",
            },
        },
        "required": ["render_id"],
    },
)
async def get_shotstack_render_status(ctx: ToolContext, args: Dict[str, Any]):
    import httpx
    
    render_id = args["render_id"].strip()
    if not render_id:
        return {"error": "render_id is required"}
    
    try:
        headers = _shotstack_headers()
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{_SHOTSTACK_API_URL}/render/{render_id}",
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
            
    except RuntimeError as e:
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"error": f"Shotstack API error: {e.response.status_code} — {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Status check failed: {e}"}
    
    response = data.get("response", {})
    status = response.get("status", "unknown")
    url = response.get("url")
    expires_at = response.get("expires")
    
    # Update database record
    try:
        update_data = {"status": status, "updated_at": datetime.utcnow()}
        if url:
            update_data["url"] = url
            update_data["expires_at"] = expires_at
            
        await ctx.db.shotstack_renders.update_one(
            {"render_id": render_id, "business_id": ctx.business_id},
            {"$set": update_data}
        )
    except Exception as e:
        logging.warning(f"[shotstack] Failed to update render record: {e}")
    
    result = {
        "render_id": render_id,
        "status": status,
        "url": url,
        "expires_at": expires_at,
    }
    
    if status == "done":
        result["message"] = f"Shotstack render completed! Download URL: {url}"
    elif status == "failed":
        result["message"] = "Shotstack render failed. Please try again."
    else:
        result["message"] = f"Shotstack render is {status}. Keep polling..."
    
    return result


# ── Ad Health & Alert Rules ───────────────────────────────────────────────────

@tool(
    name="get_ads_health_report",
    description=(
        "Get a health report for all live ad campaigns. Returns health scores (0-100), "
        "zone (healthy/warning/critical), key issues, and recent auto-pause actions. "
        "Use this when the user asks how their ads are performing, or to check ROI."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Lookback window in days (default 7)",
                "default": 7,
            },
            "zone_filter": {
                "type": "string",
                "enum": ["all", "healthy", "warning", "critical"],
                "description": "Filter by health zone",
                "default": "all",
            },
        },
        "required": [],
    },
)
async def get_ads_health_report(ctx: ToolContext, args: Dict[str, Any]):
    from zernio_ads_service import list_campaigns
    from ad_health_monitor import score_campaign, ensure_default_rules

    days = int(args.get("days", 7))
    zone_filter = args.get("zone_filter", "all")

    await ensure_default_rules(ctx.db, ctx.user_id)

    result = await list_campaigns(days=days)
    campaigns = result.get("campaigns") or result.get("data") or []

    if result.get("error") and not campaigns:
        return {"error": result["error"], "campaigns": []}

    scored = []
    for c in campaigns:
        metrics = c.get("metrics") or c.get("insights") or c
        health_score, issues, zone = score_campaign(metrics)
        if zone_filter != "all" and zone != zone_filter:
            continue
        scored.append({
            "campaign_id":   str(c.get("id") or c.get("campaignId") or ""),
            "name":          c.get("name") or c.get("campaignName") or "Unknown",
            "status":        c.get("status", ""),
            "platform":      c.get("platform", ""),
            "health_score":  health_score,
            "zone":          zone,
            "issues":        issues[:4],
            "spend":         float(metrics.get("spend", 0) or 0),
            "impressions":   int(metrics.get("impressions", 0) or 0),
            "clicks":        int(metrics.get("clicks", 0) or 0),
            "ctr":           float(metrics.get("ctr", 0) or 0),
            "roas":          float(metrics.get("roas", 0) or 0),
        })

    scored.sort(key=lambda x: x["health_score"])

    # Recent auto-pause actions
    from datetime import timedelta
    recent_actions = await ctx.db.ad_alert_history.find(
        {"user_id": ctx.user_id, "fired_at": {"$gte": datetime.utcnow() - timedelta(days=7)}}
    ).sort("fired_at", -1).to_list(20)
    actions = [{
        "campaign_name": a.get("campaign_name"),
        "rule_name":     a.get("rule_name"),
        "action":        a.get("action"),
        "health_score":  a.get("health_score"),
        "zone":          a.get("zone"),
        "fired_at":      a["fired_at"].isoformat() if hasattr(a.get("fired_at"), "isoformat") else str(a.get("fired_at", "")),
    } for a in recent_actions]

    critical = [c for c in scored if c["zone"] == "critical"]
    warning  = [c for c in scored if c["zone"] == "warning"]
    healthy  = [c for c in scored if c["zone"] == "healthy"]

    return {
        "total_campaigns": len(scored),
        "summary": {
            "critical": len(critical),
            "warning":  len(warning),
            "healthy":  len(healthy),
        },
        "campaigns":       scored,
        "recent_actions":  actions,
        "days":            days,
    }


@tool(
    name="set_ad_alert_rule",
    description=(
        "Create or update an ad alert rule. Rules define when to auto-pause a campaign or send "
        "an alert based on performance metrics (CTR, ROAS, CPC, health score, spend). "
        "Use this when the user wants to configure performance thresholds or auto-pause rules."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Descriptive name for the rule, e.g. 'Pause if ROAS below 1.5'",
            },
            "condition": {
                "type": "string",
                "enum": ["health_score", "ctr", "roas", "cpc", "cpm", "spend", "clicks"],
                "description": "Metric to evaluate",
            },
            "operator": {
                "type": "string",
                "enum": ["lt", "gt", "lte", "gte"],
                "description": "Comparison operator: lt=less than, gt=greater than",
            },
            "value": {
                "type": "number",
                "description": "Threshold value (e.g. 1.5 for ROAS, 0.5 for CTR%)",
            },
            "action": {
                "type": "string",
                "enum": ["auto_pause", "alert_only"],
                "description": "auto_pause = pause the campaign automatically; alert_only = WhatsApp notification only",
            },
            "min_spend": {
                "type": "number",
                "description": "Minimum $ spend before rule fires (avoid false positives on new campaigns)",
                "default": 5.0,
            },
            "min_impressions": {
                "type": "integer",
                "description": "Minimum impressions before rule fires",
                "default": 300,
            },
            "notify_whatsapp": {
                "type": "boolean",
                "description": "Send WhatsApp alert to owner when rule fires",
                "default": True,
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether this rule is active",
                "default": True,
            },
            "rule_id": {
                "type": "string",
                "description": "Existing rule ID to update (omit to create new)",
            },
        },
        "required": ["name", "condition", "operator", "value", "action"],
    },
    destructive=False,
)
async def set_ad_alert_rule(ctx: ToolContext, args: Dict[str, Any]):
    rule_id = (args.get("rule_id") or "").strip()

    doc = {
        "user_id":        ctx.user_id,
        "name":           args["name"].strip(),
        "condition":      args["condition"],
        "operator":       args["operator"],
        "value":          float(args["value"]),
        "action":         args["action"],
        "min_spend":      float(args.get("min_spend", 5.0)),
        "min_impressions": int(args.get("min_impressions", 300)),
        "notify_whatsapp": bool(args.get("notify_whatsapp", True)),
        "enabled":        bool(args.get("enabled", True)),
        "updated_at":     datetime.utcnow(),
    }

    if rule_id:
        existing = await ctx.db.ad_alert_rules.find_one({"_id": rule_id, "user_id": ctx.user_id})
        if not existing:
            return {"error": "Rule not found"}
        await ctx.db.ad_alert_rules.update_one({"_id": rule_id}, {"$set": doc})
        doc["_id"] = rule_id
        action_taken = "updated"
    else:
        import uuid as _uuid
        doc["_id"] = str(_uuid.uuid4())
        doc["created_at"] = datetime.utcnow()
        await ctx.db.ad_alert_rules.insert_one(doc)
        action_taken = "created"

    operator_label = {"lt": "below", "lte": "≤", "gt": "above", "gte": "≥"}.get(doc["operator"], doc["operator"])
    action_label = "auto-pause campaign" if doc["action"] == "auto_pause" else "send WhatsApp alert"

    return {
        "status": action_taken,
        "rule_id": doc["_id"],
        "name": doc["name"],
        "description": f"When {doc['condition']} is {operator_label} {doc['value']} (with ≥${doc['min_spend']} spend): {action_label}",
    }


# ── Smart agent handoff ────────────────────────────────────────────────────────
@tool(
    name="switch_to_agent",
    description=(
        "Hand off this conversation to a specialist agent when the user's request is outside your scope. "
        "Call this IMMEDIATELY — do NOT apologise or explain first, just switch. "
        "The handoff is transparent: the target agent will handle the same message as if it was always theirs."
    ),
    parameters={
        "type": "object",
        "required": ["target_agent"],
        "properties": {
            "target_agent": {
                "type": "string",
                "enum": [
                    "creative", "general", "document", "meta_ads",
                    "social_scheduler", "social_monitor", "social_inbox",
                    "sales", "customers", "orders", "finance",
                ],
                "description": "Agent to hand off to.",
            },
            "reason": {
                "type": "string",
                "description": "One-line reason for the handoff (logged only, never shown to user).",
            },
        },
    },
)
async def switch_to_agent(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Signal the orchestrator to re-run this turn with a different agent."""
    target = (args.get("target_agent") or "general").strip()
    reason = (args.get("reason") or "").strip()
    logger.info("[switch_to_agent] handoff → %s (reason: %s)", target, reason or "(none)")
    return {"__handoff__": target, "reason": reason}


# ── Composio: Gmail & Google Calendar ─────────────────────────────────────────

@tool(
    name="read_emails",
    description=(
        "Fetch recent emails from the user's connected Gmail inbox. "
        "Use to check unread messages, find a specific email, or summarise recent correspondence."
    ),
    parameters={
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "description": "Maximum number of emails to return (default 10, max 50).",
            },
            "query": {
                "type": "string",
                "description": "Optional Gmail search query e.g. 'is:unread', 'from:john@example.com', 'subject:invoice'.",
            },
            "label": {
                "type": "string",
                "description": "Optional label filter e.g. 'INBOX', 'SENT', 'UNREAD'.",
            },
        },
    },
)
async def read_emails(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from composio_service import execute_action, get_connection_status, TOOLKIT_GMAIL, ACTION_GMAIL_FETCH
    status = await get_connection_status(ctx.business_id, TOOLKIT_GMAIL)
    if not status.get("connected"):
        return {
            "error": "Gmail is not connected.",
            "action_required": "Connect Gmail in the Integrations page first.",
        }
    params: Dict[str, Any] = {
        "max_results": min(int(args.get("max_results") or 10), 50),
    }
    if args.get("query"):
        params["query"] = args["query"]
    if args.get("label"):
        params["label_ids"] = [args["label"].upper()]
    result = await execute_action(ctx.business_id, ACTION_GMAIL_FETCH, params)
    return result


@tool(
    name="send_email",
    description="Send an email from the user's connected Gmail account.",
    parameters={
        "type": "object",
        "required": ["to", "subject", "body"],
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address.",
            },
            "subject": {"type": "string", "description": "Email subject line."},
            "body": {"type": "string", "description": "Email body text (plain text or HTML)."},
            "cc": {"type": "string", "description": "Optional CC email address(es), comma-separated."},
            "reply_to_message_id": {
                "type": "string",
                "description": "Optional message ID to reply to (keeps thread context).",
            },
        },
    },
    destructive=True,
)
async def send_email(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from composio_service import execute_action, get_connection_status, TOOLKIT_GMAIL, ACTION_GMAIL_SEND
    status = await get_connection_status(ctx.business_id, TOOLKIT_GMAIL)
    if not status.get("connected"):
        return {
            "error": "Gmail is not connected.",
            "action_required": "Connect Gmail in the Integrations page first.",
        }
    params: Dict[str, Any] = {
        "recipient_email": args["to"],
        "subject": args["subject"],
        "body": args["body"],
    }
    if args.get("cc"):
        params["cc"] = args["cc"]
    if args.get("reply_to_message_id"):
        params["message_id"] = args["reply_to_message_id"]
    result = await execute_action(ctx.business_id, ACTION_GMAIL_SEND, params)
    return result


@tool(
    name="create_email_draft",
    description="Create a draft email in the user's Gmail account without sending it.",
    parameters={
        "type": "object",
        "required": ["to", "subject", "body"],
        "properties": {
            "to": {"type": "string", "description": "Recipient email address."},
            "subject": {"type": "string", "description": "Email subject line."},
            "body": {"type": "string", "description": "Draft body text."},
        },
    },
)
async def create_email_draft(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from composio_service import execute_action, get_connection_status, TOOLKIT_GMAIL, ACTION_GMAIL_DRAFT
    status = await get_connection_status(ctx.business_id, TOOLKIT_GMAIL)
    if not status.get("connected"):
        return {
            "error": "Gmail is not connected.",
            "action_required": "Connect Gmail in the Integrations page first.",
        }
    result = await execute_action(ctx.business_id, ACTION_GMAIL_DRAFT, {
        "recipient_email": args["to"],
        "subject": args["subject"],
        "body": args["body"],
    })
    return result


@tool(
    name="list_calendar_events",
    description=(
        "List upcoming events from the user's connected Google Calendar. "
        "Use to check schedule, find free slots, or summarise upcoming meetings."
    ),
    parameters={
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to return (default 10).",
            },
            "time_min": {
                "type": "string",
                "description": "Start of time range in ISO 8601 format e.g. '2025-05-01T00:00:00Z'. Defaults to now.",
            },
            "time_max": {
                "type": "string",
                "description": "End of time range in ISO 8601 format e.g. '2025-05-31T23:59:59Z'.",
            },
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID to query (defaults to primary).",
            },
        },
    },
)
async def list_calendar_events(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from composio_service import execute_action, get_connection_status, TOOLKIT_CALENDAR, ACTION_CALENDAR_LIST
    status = await get_connection_status(ctx.business_id, TOOLKIT_CALENDAR)
    if not status.get("connected"):
        return {
            "error": "Google Calendar is not connected.",
            "action_required": "Connect Google Calendar in the Integrations page first.",
        }
    params: Dict[str, Any] = {
        "max_results": min(int(args.get("max_results") or 10), 50),
        "calendar_id": args.get("calendar_id") or "primary",
    }
    if args.get("time_min"):
        params["time_min"] = args["time_min"]
    if args.get("time_max"):
        params["time_max"] = args["time_max"]
    result = await execute_action(ctx.business_id, ACTION_CALENDAR_LIST, params)
    return result


@tool(
    name="create_calendar_event",
    description="Create a new event in the user's Google Calendar.",
    parameters={
        "type": "object",
        "required": ["title", "start_datetime", "end_datetime"],
        "properties": {
            "title": {"type": "string", "description": "Event title/summary."},
            "start_datetime": {
                "type": "string",
                "description": "Start time in ISO 8601 format e.g. '2025-05-10T14:00:00Z'.",
            },
            "end_datetime": {
                "type": "string",
                "description": "End time in ISO 8601 format e.g. '2025-05-10T15:00:00Z'.",
            },
            "description": {"type": "string", "description": "Optional event description/notes."},
            "location": {"type": "string", "description": "Optional event location."},
            "attendees": {
                "type": "string",
                "description": "Optional comma-separated attendee email addresses.",
            },
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID to create the event in (defaults to primary).",
            },
        },
    },
    destructive=True,
)
async def create_calendar_event(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from composio_service import execute_action, get_connection_status, TOOLKIT_CALENDAR, ACTION_CALENDAR_CREATE
    status = await get_connection_status(ctx.business_id, TOOLKIT_CALENDAR)
    if not status.get("connected"):
        return {
            "error": "Google Calendar is not connected.",
            "action_required": "Connect Google Calendar in the Integrations page first.",
        }
    params: Dict[str, Any] = {
        "summary": args["title"],
        "start": {"dateTime": args["start_datetime"]},
        "end": {"dateTime": args["end_datetime"]},
        "calendar_id": args.get("calendar_id") or "primary",
    }
    if args.get("description"):
        params["description"] = args["description"]
    if args.get("location"):
        params["location"] = args["location"]
    if args.get("attendees"):
        emails = [e.strip() for e in args["attendees"].split(",") if e.strip()]
        params["attendees"] = [{"email": e} for e in emails]
    result = await execute_action(ctx.business_id, ACTION_CALENDAR_CREATE, params)
    return result


@tool(
    name="delete_calendar_event",
    description="Delete an event from the user's Google Calendar by event ID.",
    parameters={
        "type": "object",
        "required": ["event_id"],
        "properties": {
            "event_id": {"type": "string", "description": "The Google Calendar event ID to delete."},
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID (defaults to primary).",
            },
        },
    },
    destructive=True,
)
async def delete_calendar_event(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from composio_service import execute_action, get_connection_status, TOOLKIT_CALENDAR, ACTION_CALENDAR_DELETE
    status = await get_connection_status(ctx.business_id, TOOLKIT_CALENDAR)
    if not status.get("connected"):
        return {
            "error": "Google Calendar is not connected.",
            "action_required": "Connect Google Calendar in the Integrations page first.",
        }
    result = await execute_action(ctx.business_id, ACTION_CALENDAR_DELETE, {
        "event_id": args["event_id"],
        "calendar_id": args.get("calendar_id") or "primary",
    })
    return result


@tool(
    name="switch_to_agent",
    description=(
        "Hand off this conversation to a specialist agent immediately. "
        "Call this the INSTANT you detect the user's request is outside your area — "
        "do NOT apologise, do NOT explain, do NOT attempt to help first. Just switch. "
        "The handoff is invisible to the user — they see the correct agent's response directly."
    ),
    parameters={
        "type": "object",
        "required": ["target_agent"],
        "properties": {
            "target_agent": {
                "type": "string",
                "enum": ["creative", "general", "meta_ads", "social_monitor", "document", "social_scheduler"],
                "description": (
                    "Agent to hand off to. "
                    "creative=visuals/graphics/social post images. "
                    "document=proposals/reports/presentations/PDFs. "
                    "meta_ads=Facebook/Instagram ad campaigns. "
                    "social_monitor=analytics/follower data/post performance. "
                    "social_scheduler=scheduling posts. "
                    "general=everything else."
                ),
            },
            "reason": {
                "type": "string",
                "description": "One-line reason for the handoff (logged only, not shown to user).",
            },
        },
    },
)
async def switch_to_agent(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    target = args.get("target_agent", "")
    reason = args.get("reason", "")
    logger.info("[switch_to_agent] handoff → %s | reason: %s", target, reason)
    return {"__handoff__": target, "reason": reason}
