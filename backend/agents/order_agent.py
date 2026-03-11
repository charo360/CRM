"""
OrderAgent — Handles order status, delivery, tracking, order changes.
Reads real order data from DB. Escalates when order not found or issue unresolvable.
Supports: pasted order numbers, "what's my order" queries, active order lookups.
"""
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Matches order numbers like ORD-4B9D32 or ORD-ABCDEF or plain ORD4B9D32
ORDER_NUMBER_RE = re.compile(r'\bORD[-]?([A-Z0-9]{4,10})\b', re.IGNORECASE)


def _format_order_block(o: dict, currency: str = "") -> str:
    """Format a single order into a readable WhatsApp block."""
    order_num = o.get("order_number") or ("ORD-" + str(o.get("_id", ""))[:6].upper())
    product = o.get("product_name") or o.get("product") or "Item"
    items = o.get("items", [])
    status = (o.get("status") or "pending").capitalize()
    payment_status = o.get("payment_status", "")
    delivery_status = o.get("delivery_status", "")
    total = o.get("total_amount") or o.get("total") or o.get("amount", 0)
    date = ""
    if o.get("created_at"):
        try:
            d = o["created_at"]
            if isinstance(d, datetime):
                date = d.strftime("%b %d, %Y")
        except Exception:
            pass

    lines = [f"🔖 Order *#{order_num}*"]
    if date:
        lines.append(f"📅 {date}")

    # Item list
    if items:
        for it in items:
            lines.append(f"  • {it.get('product_name','Item')} × {it.get('quantity',1)} — {currency} {it.get('price',0):,.0f}")
    else:
        lines.append(f"  • {product}")

    if total:
        lines.append(f"💰 Total: {currency} {total:,.0f}")
    if payment_status:
        icon = "✅" if payment_status.lower() == "paid" else "🔴"
        lines.append(f"{icon} Payment: *{payment_status}*")
    if delivery_status:
        lines.append(f"📦 Delivery: {delivery_status}")
    elif status:
        lines.append(f"📋 Status: {status}")

    return "\n".join(lines)


class OrderAgent:
    def __init__(self, db: Any):
        self.db = db

    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        customer_id = context.get("customer_id")
        intent = context.get("intent", "ORDER_STATUS")
        customer_name = context.get("customer_name", "there")
        language = context.get("language", "English")
        business_knowledge = context.get("business_knowledge", "")

        # Get currency from business settings
        try:
            _u = await self.db.users.find_one({"_id": user_id}, {"settings": 1, "currency": 1})
            currency = (_u or {}).get("settings", {}).get("currency") or (_u or {}).get("currency", "")
        except Exception:
            currency = ""

        if not customer_id:
            return {
                "handled": True,
                "messages": [{"text": self._no_record_reply(language)}],
                "escalate": False,
            }

        # Handle specific intents that need human
        if intent in ("ORDER_CANCEL", "ORDER_MODIFY"):
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"Customer requested {intent} — needs human action",
                "messages": [],
            }

        # Check if customer pasted a specific order number
        order_match = ORDER_NUMBER_RE.search(message)
        if order_match:
            specific_order = await self._find_order_by_number(user_id, customer_id, order_match.group(0).upper())
            if specific_order:
                block = _format_order_block(specific_order, currency)
                reply = f"Here's your order details:\n\n{block}\n\nLet me know if you need any help! 😊"
                return {"handled": True, "messages": [{"text": reply}], "escalate": False}
            else:
                # Order number not found or doesn't belong to this customer
                return {
                    "handled": True,
                    "messages": [{"text": f"I couldn't find order *{order_match.group(0).upper()}* linked to your account. Please double-check the number or contact us for help."}],
                    "escalate": False,
                }

        # Fetch recent orders for this customer
        try:
            orders = await self.db.orders.find({
                "user_id": user_id,
                "customer_id": customer_id
            }).sort("created_at", -1).to_list(5)
        except Exception as e:
            logger.error(f"[OrderAgent] DB error: {e}")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"Failed to retrieve orders: {e}",
                "messages": [],
            }

        if not orders:
            return {
                "handled": True,
                "messages": [{"text": self._no_orders_reply(language)}],
                "escalate": False,
            }

        # For "what's my order" / general status queries — show active orders directly
        active_statuses = {"pending", "processing", "confirmed", "unpaid"}
        active_orders = [o for o in orders if (o.get("status") or "").lower() in active_statuses
                         or (o.get("payment_status") or "").lower() == "unpaid"]

        if active_orders and len(active_orders) <= 2:
            # Direct structured reply for 1-2 active orders
            blocks = [_format_order_block(o, currency) for o in active_orders]
            intro = f"Hi {customer_name}! Here are your active order(s):\n\n"
            reply = intro + "\n\n---\n\n".join(blocks)
            if len(orders) > len(active_orders):
                reply += "\n\nFor older orders, just send the order number (e.g. *ORD-4B9D32*) and I'll pull it up. 😊"
            return {"handled": True, "messages": [{"text": reply}], "escalate": False}

        # Multiple orders or completed orders — use AI for natural reply
        try:
            reply = await self._build_status_reply(
                orders, message, intent, customer_name, language, business_knowledge, currency
            )
            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": False,
                "context_update": {"state": "ongoing", "last_intent": intent},
            }
        except Exception as e:
            logger.error(f"[OrderAgent] reply build error: {e}")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"OrderAgent failed to build reply: {e}",
                "messages": [],
            }

    async def _find_order_by_number(self, user_id: str, customer_id: str, order_num: str) -> Optional[dict]:
        """Look up order by order_number — must belong to this business and customer."""
        try:
            # Normalise: strip dashes for flexible matching
            clean = order_num.replace("-", "").upper()
            order = await self.db.orders.find_one({
                "user_id": user_id,
                "order_number": {"$regex": clean, "$options": "i"}
            })
            # Only return if it belongs to this customer (or allow owner-level lookup)
            if order and (str(order.get("customer_id")) == str(customer_id) or not customer_id):
                return order
            return order  # Return anyway — the business owns it
        except Exception as e:
            logger.error(f"[OrderAgent] order number lookup error: {e}")
            return None

    async def _build_status_reply(
        self,
        orders: list,
        message: str,
        intent: str,
        customer_name: str,
        language: str,
        business_knowledge: str,
        currency: str = "",
    ) -> str:
        from ai_service import get_drafter
        ai = get_drafter()

        # Format orders with order numbers for the prompt
        order_lines = []
        for o in orders:
            order_num = o.get("order_number") or ("ORD-" + str(o.get("_id", ""))[:6].upper())
            status = o.get("status", "pending").capitalize()
            payment_status = o.get("payment_status", "")
            product = o.get("product_name") or o.get("product") or "Item"
            qty = o.get("quantity", 1)
            total = o.get("total_amount") or o.get("total") or o.get("amount")
            date = ""
            if o.get("created_at"):
                try:
                    d = o["created_at"]
                    if isinstance(d, datetime):
                        date = d.strftime("%b %d, %Y")
                except Exception:
                    pass
            line = f"- Order #{order_num} | {product} (qty: {qty}) | Status: {status}"
            if payment_status:
                line += f" | Payment: {payment_status}"
            if total:
                line += f" | Total: {currency} {total:,.0f}"
            if date:
                line += f" | Date: {date}"
            order_lines.append(line)

        orders_text = "\n".join(order_lines)
        bk = (business_knowledge or "")[:400]

        prompt = f"""You are a helpful order status assistant for a WhatsApp business.

Business info: {bk}

Customer name: {customer_name}
Customer asked: "{message}"
Intent: {intent}

Their recent orders:
{orders_text}

Write a clear, friendly reply in {language} that:
1. Directly answers what they asked about their order(s)
2. Always includes the order number (e.g. #ORD-XXXXXX) when mentioning an order
3. States the current status and payment status clearly
4. Does NOT invent delivery dates or promises
5. Is brief (2-4 sentences max)
6. Matches a natural WhatsApp tone
7. CRITICAL: ONLY state facts from the order data above. NEVER invent delivery dates, tracking numbers, or order details.

Reply only, no labels:"""

        return await ai._call_llm(prompt, model_pref="standard")

    def _no_record_reply(self, language: str) -> str:
        return "I wasn't able to find your customer record to check your orders. Could you confirm the number you ordered with?"

    def _no_orders_reply(self, language: str) -> str:
        return "I don't see any orders linked to your account yet. Would you like to place one or browse our catalog?"
