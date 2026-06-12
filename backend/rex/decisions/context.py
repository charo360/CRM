"""
Gather live business context for Decision Room sparring.

Read-only queries against Mongo collections the CRM already maintains.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _tid(user: dict) -> str:
    return str(user.get("business_id") or user.get("_id") or "")


def _uid(user: dict) -> str:
    return str(user.get("_id") or "")


async def gather_decision_context(db: Any, user: dict) -> dict[str, Any]:
    """Build a compact facts bundle for the sparring prompt."""
    business_id = _tid(user)
    user_id = _uid(user)
    now = datetime.utcnow()
    cutoff_30 = now - timedelta(days=30)
    cutoff_90 = now - timedelta(days=90)
    stall_cutoff = now - timedelta(days=7)

    ctx: dict[str, Any] = {
        "business_name": user.get("business_name") or "Your business",
        "currency": user.get("currency") or "USD",
        "relationship_day": (user.get("settings") or {}).get("zilo_relationship_day"),
        "business_knowledge": user.get("business_knowledge") if isinstance(user.get("business_knowledge"), dict) else {},
    }

    try:
        ctx["customer_count"] = await db.customers.count_documents(
            {"user_id": business_id, "is_customer": True}
        )
    except Exception as e:
        logger.warning("[decision-context] customers: %s", e)
        ctx["customer_count"] = 0

    try:
        ctx["contact_count"] = await db.customers.count_documents({"user_id": business_id})
    except Exception as e:
        logger.warning("[decision-context] contacts: %s", e)
        ctx["contact_count"] = 0

    try:
        stalled = await db.customers.count_documents({
            "user_id": business_id,
            "pipeline_stage": {"$in": ["negotiation", "proposal", "qualified", "contacted"]},
            "updated_at": {"$lt": stall_cutoff},
        })
        ctx["stalled_deals"] = stalled
    except Exception as e:
        logger.warning("[decision-context] stalled: %s", e)
        ctx["stalled_deals"] = 0

    try:
        pipeline = [
            {"$match": {"user_id": business_id, "created_at": {"$gte": cutoff_30}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        ]
        rows = await db.sales.aggregate(pipeline).to_list(1)
        if rows:
            ctx["revenue_30d"] = round(float(rows[0].get("total") or 0), 2)
            ctx["sales_count_30d"] = int(rows[0].get("count") or 0)
        else:
            ctx["revenue_30d"] = 0
            ctx["sales_count_30d"] = 0
    except Exception as e:
        logger.warning("[decision-context] sales 30d: %s", e)
        ctx["revenue_30d"] = None

    try:
        pipeline = [
            {"$match": {"user_id": business_id, "created_at": {"$gte": cutoff_90}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        rows = await db.sales.aggregate(pipeline).to_list(1)
        ctx["revenue_90d"] = round(float(rows[0]["total"]), 2) if rows else 0
    except Exception as e:
        logger.warning("[decision-context] sales 90d: %s", e)
        ctx["revenue_90d"] = None

    try:
        ctx["followups_due"] = await db.followups.count_documents({
            "user_id": user_id,
            "status": {"$ne": "completed"},
            "reminder_date": {"$lte": now},
        })
    except Exception as e:
        logger.warning("[decision-context] followups: %s", e)
        ctx["followups_due"] = 0

    try:
        from followup_analytics import get_analytics
        analytics = get_analytics(db)
        stats = await analytics.get_followup_stats(user_id, days=30)
        ctx["followup_conversion_30d"] = stats.get("conversion_rate")
        ctx["followup_response_rate_30d"] = stats.get("response_rate")
        ctx["followup_revenue_30d"] = stats.get("total_revenue")
    except Exception as e:
        logger.warning("[decision-context] followup stats: %s", e)

    try:
        ctx["open_orders"] = await db.orders.count_documents({
            "user_id": business_id,
            "status": {"$nin": ["completed", "cancelled", "delivered"]},
        })
        ctx["pending_payments"] = await db.orders.count_documents({
            "user_id": business_id,
            "payment_status": {"$in": ["pending", "unpaid", "partial"]},
        })
    except Exception as e:
        logger.warning("[decision-context] orders: %s", e)

    try:
        # Products may be stored under business_id OR the raw user_id depending on
        # which surface created them — query both so prices are never "missing".
        id_filter = {"$in": list({business_id, user_id})}
        products = await db.products.find(
            {"user_id": id_filter},
            {"name": 1, "price": 1, "discount_price": 1, "category": 1},
        ).to_list(100)
        if products:
            detail = []
            prices = []
            for p in products:
                price = p.get("discount_price") or p.get("price")
                try:
                    price = float(price) if price not in (None, "") else None
                except (TypeError, ValueError):
                    price = None
                if price is not None and price > 0:
                    prices.append(price)
                detail.append({"name": p.get("name"), "price": price, "category": p.get("category")})
            ctx["product_count"] = len(products)
            ctx["product_price_min"] = min(prices) if prices else None
            ctx["product_price_max"] = max(prices) if prices else None
            ctx["product_samples"] = [p.get("name") for p in products[:5] if p.get("name")]
            # Full priced list (capped) so the LLM sees actual prices, not just a range.
            ctx["products_detail"] = [d for d in detail if d.get("name")][:25]
    except Exception as e:
        logger.warning("[decision-context] products: %s", e)

    try:
        date_30 = cutoff_30.strftime("%Y-%m-%d")
        expense_pipeline = [
            {"$match": {"user_id": business_id, "type": "expense", "date": {"$gte": date_30}}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
            {"$sort": {"total": -1}},
            {"$limit": 5},
        ]
        expenses = await db.finance_entries.aggregate(expense_pipeline).to_list(5)
        ctx["top_expenses_30d"] = [
            {"category": r["_id"], "amount": round(float(r["total"]), 2)} for r in expenses
        ]
        # Monthly burn + net (income − expense) over the last 30 days.
        totals_pipeline = [
            {"$match": {"user_id": business_id, "date": {"$gte": date_30}}},
            {"$group": {"_id": "$type", "total": {"$sum": "$amount"}}},
        ]
        totals = await db.finance_entries.aggregate(totals_pipeline).to_list(10)
        by_type = {r["_id"]: round(float(r["total"] or 0), 2) for r in totals}
        burn = by_type.get("expense")
        income = by_type.get("income")
        if burn is not None:
            ctx["monthly_burn"] = burn
        if income is not None and burn is not None:
            ctx["net_30d"] = round(income - burn, 2)
    except Exception as e:
        logger.warning("[decision-context] finance: %s", e)

    try:
        id_filter = {"$in": list({business_id, user_id})}
        unpaid = await db.invoices.aggregate([
            {"$match": {"user_id": id_filter, "status": {"$in": ["sent", "overdue", "unpaid", "partial"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        if unpaid:
            ctx["invoices_outstanding"] = round(float(unpaid[0].get("total") or 0), 2)
            ctx["invoices_outstanding_count"] = int(unpaid[0].get("count") or 0)
    except Exception as e:
        logger.debug("[decision-context] invoices: %s", e)

    try:
        id_filter = {"$in": list({business_id, user_id})}
        ctx["quotes_pending"] = await db.quotes.count_documents({
            "user_id": id_filter,
            "status": {"$in": ["draft", "sent", "pending"]},
        })
    except Exception as e:
        logger.debug("[decision-context] quotes: %s", e)

    try:
        integrations = (user.get("settings") or {}).get("integrations") or {}
        ctx["connected"] = {
            "whatsapp": bool(user.get("whatsapp_connected") or user.get("wa_phone")),
            "stripe": bool(integrations.get("stripe") or user.get("stripe_connected")),
            "shopify": bool(integrations.get("shopify") or user.get("shopify_shop")),
            "email": bool(integrations.get("gmail") or integrations.get("outlook")),
        }
    except Exception:
        ctx["connected"] = {}

    return ctx


def format_context_for_prompt(ctx: dict[str, Any]) -> str:
    """Human-readable context block for the LLM."""
    lines = [
        f"Business: {ctx.get('business_name')}",
        f"Currency: {ctx.get('currency')}",
    ]
    if ctx.get("customer_count") is not None:
        lines.append(f"Customers: {ctx['customer_count']} (contacts total: {ctx.get('contact_count', '?')})")
    if ctx.get("stalled_deals"):
        lines.append(f"Stalled deals (>7d no movement): {ctx['stalled_deals']}")
    if ctx.get("revenue_30d") is not None:
        lines.append(f"Revenue last 30d: {ctx['currency']} {ctx['revenue_30d']} ({ctx.get('sales_count_30d', 0)} sales)")
    if ctx.get("revenue_90d") is not None:
        lines.append(f"Revenue last 90d: {ctx['currency']} {ctx['revenue_90d']}")
    if ctx.get("followups_due"):
        lines.append(f"Follow-ups overdue: {ctx['followups_due']}")
    if ctx.get("followup_conversion_30d") is not None:
        lines.append(
            f"Follow-up conversion (30d): {ctx['followup_conversion_30d']}% · "
            f"response rate: {ctx.get('followup_response_rate_30d')}%"
        )
    if ctx.get("open_orders"):
        lines.append(f"Open orders: {ctx['open_orders']} · pending payments: {ctx.get('pending_payments', 0)}")
    cur = ctx.get("currency")
    if ctx.get("product_count"):
        lines.append(
            f"Products: {ctx['product_count']} · price range {ctx.get('product_price_min')}–{ctx.get('product_price_max')} {cur}"
        )
    if ctx.get("products_detail"):
        items = []
        for d in ctx["products_detail"][:15]:
            price = d.get("price")
            price_str = f"{cur} {price:,.0f}" if isinstance(price, (int, float)) else "price not set"
            items.append(f"{d.get('name')} ({price_str})")
        lines.append("Product prices (live from catalog): " + "; ".join(items))
    if ctx.get("invoices_outstanding") is not None:
        lines.append(
            f"Outstanding invoices: {cur} {ctx['invoices_outstanding']:,.0f} "
            f"across {ctx.get('invoices_outstanding_count', 0)} unpaid"
        )
    if ctx.get("quotes_pending"):
        lines.append(f"Quotes pending: {ctx['quotes_pending']}")
    if ctx.get("monthly_burn") is not None:
        lines.append(f"Monthly burn (expenses 30d): {cur} {ctx['monthly_burn']:,.0f}")
    if ctx.get("net_30d") is not None:
        lines.append(f"Net last 30d (income − expense): {cur} {ctx['net_30d']:,.0f}")
    bk = ctx.get("business_knowledge") or {}
    if bk.get("pricing_info"):
        lines.append(f"Pricing notes (founder-provided): {str(bk['pricing_info'])[:400]}")
    if bk.get("products_services"):
        lines.append(f"Offerings: {str(bk['products_services'])[:300]}")
    if ctx.get("top_expenses_30d"):
        exp = ", ".join(f"{e['category']} {e['amount']}" for e in ctx["top_expenses_30d"][:3])
        lines.append(f"Top expenses (30d): {exp}")
    connected = ctx.get("connected") or {}
    missing = [k for k, v in connected.items() if not v]
    if missing:
        lines.append(f"Not connected: {', '.join(missing)}")

    # Tell the model what it definitively HAS, so it never lists present data as a gap.
    have: list[str] = []
    if ctx.get("products_detail") or ctx.get("product_count"):
        have.append("product prices")
    if ctx.get("revenue_30d") is not None:
        have.append("revenue")
    if ctx.get("customer_count") is not None:
        have.append("customer counts")
    if ctx.get("monthly_burn") is not None:
        have.append("expenses/burn")
    if have:
        lines.append(
            "DATA YOU ALREADY HAVE (do NOT list these as data gaps): " + ", ".join(have) + "."
        )
    return "\n".join(lines)
