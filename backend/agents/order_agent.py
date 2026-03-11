"""
OrderAgent — Handles order status, delivery, tracking, order changes.
Reads real order data from DB. Escalates when order not found or issue unresolvable.
Supports: pasted order numbers, "what's my order" queries, active order lookups,
          multi-order selection list, self-service cancel/update.
"""
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Matches order numbers like ORD-4B9D32 or ORD-ABCDEF or plain ORD4B9D32
ORDER_NUMBER_RE = re.compile(r'\bORD[-]?([A-Z0-9]{4,10})\b', re.IGNORECASE)

# Matches a customer picking a number from a list (1, 2, 3 …)
PICK_NUMBER_RE = re.compile(r'^\s*(\d{1,2})\s*$')

# Cancellation keywords
CANCEL_KEYWORDS_RE = re.compile(
    r'\b(cancel|cancell?ed?|cancellation|remove order|delete order|don\'?t want|stop order)\b',
    re.IGNORECASE
)

# Update/change keywords
UPDATE_KEYWORDS_RE = re.compile(
    r'\b(update|change|modify|edit|different|wrong address|wrong item|adjust)\b',
    re.IGNORECASE
)

# Cancellable order statuses
CANCELLABLE_STATUSES = {"pending", "unpaid", "confirmed"}


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
        conv_state = context.get("conversation_state_data") or context.get("conversation_state") or {}

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

        # ── Handle customer picking from a previously sent order list ──────────
        pending_order_ids = conv_state.get("pending_order_list")
        if pending_order_ids:
            pick_match = PICK_NUMBER_RE.match(message.strip())
            if pick_match:
                pick_idx = int(pick_match.group(1)) - 1
                if 0 <= pick_idx < len(pending_order_ids):
                    selected_order = await self.db.orders.find_one({"_id": pending_order_ids[pick_idx]})
                    if selected_order:
                        return await self._interact_with_order(
                            selected_order, customer_name, currency, language, user_id, customer_id
                        )
            # If the number is out of range or non-numeric, fall through to normal handling

        # ── Check if message contains cancel/update intent for a specific order ─
        order_match = ORDER_NUMBER_RE.search(message)

        if order_match:
            found_order_num = order_match.group(0).upper()
            specific_order = await self._find_order_by_number(user_id, customer_id, found_order_num)
            if specific_order:
                # Check if they want to cancel or update this specific order
                if CANCEL_KEYWORDS_RE.search(message):
                    return await self._handle_cancel(specific_order, customer_name, currency, language, user_id, customer_id)
                if UPDATE_KEYWORDS_RE.search(message):
                    return await self._handle_update(specific_order, customer_name, currency, language)
                # Otherwise just show the order details with action options
                return await self._interact_with_order(
                    specific_order, customer_name, currency, language, user_id, customer_id
                )
            else:
                # Order number typed but not found — fetch all customer orders to help
                all_orders = await self._fetch_customer_orders(user_id, customer_id, limit=10)
                if all_orders:
                    order_nums = ", ".join(
                        "*#" + (o.get("order_number") or ("ORD-" + str(o.get("_id", ""))[:6].upper())) + "*"
                        for o in all_orders[:5]
                    )
                    return {
                        "handled": True,
                        "messages": [{
                            "text": (
                                f"I couldn't find order *{found_order_num}* on your account.\n\n"
                                f"Your orders are: {order_nums}\n\n"
                                f"Please check the number and try again, or send the correct order number."
                            )
                        }],
                        "escalate": False,
                    }
                return {
                    "handled": True,
                    "messages": [{"text": f"I couldn't find order *{found_order_num}* linked to your account. Please double-check the number or contact us for help."}],
                    "escalate": False,
                }

        # ── Detect cancel/update intent without an explicit order number ────────
        if CANCEL_KEYWORDS_RE.search(message) or UPDATE_KEYWORDS_RE.search(message):
            is_cancel = bool(CANCEL_KEYWORDS_RE.search(message))
            orders = await self._fetch_customer_orders(user_id, customer_id, limit=10)
            if not orders:
                return {"handled": True, "messages": [{"text": self._no_orders_reply(language)}], "escalate": False}
            actionable = [o for o in orders if (o.get("status") or "").lower() in CANCELLABLE_STATUSES
                          or (o.get("payment_status") or "").lower() == "unpaid"]
            if len(actionable) == 1:
                if is_cancel:
                    return await self._handle_cancel(actionable[0], customer_name, currency, language, user_id, customer_id)
                else:
                    return await self._handle_update(actionable[0], customer_name, currency, language)
            elif actionable:
                return await self._send_order_list(
                    actionable, customer_name, language, user_id, customer_id,
                    prompt="Which order would you like to " + ("cancel" if is_cancel else "update") + "?"
                )
            else:
                return {
                    "handled": True,
                    "messages": [{"text": "None of your orders can be modified at this stage. Please contact us if you need help."}],
                    "escalate": False,
                }

        # ── Fetch recent orders for general status queries ────────────────────
        orders = await self._fetch_customer_orders(user_id, customer_id, limit=10)
        if orders is None:
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "Failed to retrieve orders from DB",
                "messages": [],
            }

        if not orders:
            return {
                "handled": True,
                "messages": [{"text": self._no_orders_reply(language)}],
                "escalate": False,
            }

        # Single order — show it directly with action options
        if len(orders) == 1:
            return await self._interact_with_order(
                orders[0], customer_name, currency, language, user_id, customer_id
            )

        active_statuses = {"pending", "processing", "confirmed", "unpaid"}
        active_orders = [o for o in orders if (o.get("status") or "").lower() in active_statuses
                         or (o.get("payment_status") or "").lower() == "unpaid"]

        # 1-2 active orders — show directly with actions
        if active_orders and len(active_orders) <= 2:
            blocks = []
            for o in active_orders:
                blocks.append(_format_order_block(o, currency) + "\n" + self._action_hint(o))
            intro = f"Hi {customer_name}! Here are your active order(s):\n\n"
            reply = intro + "\n\n---\n\n".join(blocks)
            if len(orders) > len(active_orders):
                reply += "\n\nFor older orders just send the order number (e.g. *ORD-4B9D32*)."
            return {"handled": True, "messages": [{"text": reply}], "escalate": False}

        # Many orders — send a numbered pick list
        return await self._send_order_list(
            orders[:8], customer_name, language, user_id, customer_id,
            prompt="Which order would you like details on?"
        )

    async def _fetch_customer_orders(self, user_id: str, customer_id: str, limit: int = 10) -> Optional[list]:
        """Fetch orders for a customer, newest first. Returns None on DB error."""
        try:
            return await self.db.orders.find({
                "user_id": user_id,
                "customer_id": customer_id
            }).sort("created_at", -1).to_list(limit)
        except Exception as e:
            logger.error(f"[OrderAgent] DB error fetching orders: {e}")
            return None

    async def _find_order_by_number(self, user_id: str, customer_id: str, order_num: str) -> Optional[dict]:
        """Look up order by order_number — flexible match with/without dash."""
        try:
            # Try exact match first (ORD-98F4E7)
            normalized = order_num.upper().strip()
            # Also build version with dash inserted if missing (ORD98F4E7 → ORD-98F4E7)
            if normalized.startswith("ORD") and "-" not in normalized:
                normalized_dashed = "ORD-" + normalized[3:]
            else:
                normalized_dashed = normalized
            # Build regex that matches both ORD-98F4E7 and ORD98F4E7
            suffix = re.escape(normalized.replace("ORD-", "").replace("ORD", ""))
            pattern = f"ORD-?{suffix}"
            order = await self.db.orders.find_one({
                "user_id": user_id,
                "order_number": {"$regex": f"^{pattern}$", "$options": "i"}
            })
            if order:
                return order
            # Fallback: loose contains match
            order = await self.db.orders.find_one({
                "user_id": user_id,
                "order_number": {"$regex": suffix, "$options": "i"}
            })
            return order
        except Exception as e:
            logger.error(f"[OrderAgent] order number lookup error: {e}")
            return None

    async def _send_order_list(
        self,
        orders: list,
        customer_name: str,
        language: str,
        user_id: str,
        customer_id: str,
        prompt: str = "Which order would you like details on?",
    ) -> Dict[str, Any]:
        """Send a numbered pick list of orders and save the list in conversation state."""
        from agents.conversation_state import save_state
        lines = [f"Hi {customer_name}! You have {len(orders)} order(s):\n"]
        for i, o in enumerate(orders, 1):
            order_num = o.get("order_number") or ("ORD-" + str(o.get("_id", ""))[:6].upper())
            product = o.get("product_name") or o.get("product") or "Item"
            items = o.get("items", [])
            if items and len(items) > 1:
                product = ", ".join(it.get("product_name", "Item") for it in items[:2])
                if len(items) > 2:
                    product += f" +{len(items)-2} more"
            status = (o.get("status") or "pending").capitalize()
            payment = o.get("payment_status", "")
            status_str = status
            if payment and payment.lower() != status.lower():
                status_str = f"{status} / {payment}"
            lines.append(f"*{i}.* #{order_num} — {product} [{status_str}]")
        lines.append(f"\n{prompt} Reply with the number (e.g. *1*).")
        # Save order IDs so next message resolves the pick
        order_ids = [str(o.get("_id", "")) for o in orders]
        await save_state(self.db, user_id, customer_id, {"pending_order_list": order_ids})
        return {
            "handled": True,
            "messages": [{"text": "\n".join(lines)}],
            "escalate": False,
        }

    async def _interact_with_order(
        self,
        order: dict,
        customer_name: str,
        currency: str,
        language: str,
        user_id: str,
        customer_id: str,
    ) -> Dict[str, Any]:
        """Show full order details + available action options."""
        from agents.conversation_state import save_state
        block = _format_order_block(order, currency)
        hint = self._action_hint(order)
        reply = f"Here are your order details:\n\n{block}"
        if hint:
            reply += f"\n\n{hint}"
        # Clear any pending order list since we're now focused on a single order
        await save_state(self.db, user_id, customer_id, {"pending_order_list": None})
        return {"handled": True, "messages": [{"text": reply}], "escalate": False}

    def _action_hint(self, order: dict) -> str:
        """Return a short action prompt based on order status."""
        status = (order.get("status") or "").lower()
        payment = (order.get("payment_status") or "").lower()
        order_num = order.get("order_number") or ("ORD-" + str(order.get("_id", ""))[:6].upper())
        if status in CANCELLABLE_STATUSES or payment == "unpaid":
            return (
                f"_Need to make changes?_\n"
                f"• Reply *cancel {order_num}* to cancel this order\n"
                f"• Reply *update {order_num}* to change details"
            )
        return "Let me know if you need anything else! 😊"

    async def _handle_cancel(
        self,
        order: dict,
        customer_name: str,
        currency: str,
        language: str,
        user_id: str,
        customer_id: str,
    ) -> Dict[str, Any]:
        """Cancel an order if it's in a cancellable status, otherwise escalate."""
        from agents.conversation_state import save_state
        order_num = order.get("order_number") or ("ORD-" + str(order.get("_id", ""))[:6].upper())
        status = (order.get("status") or "").lower()
        payment = (order.get("payment_status") or "").lower()

        if status not in CANCELLABLE_STATUSES and payment == "paid":
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"Customer wants to cancel paid order {order_num} — requires human approval",
                "messages": [{
                    "text": (
                        f"Order *#{order_num}* has already been paid so cancellation needs to be reviewed by our team. "
                        f"I've flagged this for a team member — they'll reach out shortly. 🙏"
                    )
                }],
            }

        # Cancel the order in DB
        try:
            await self.db.orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow(),
                           "cancelled_by": "customer"}}
            )
        except Exception as e:
            logger.error(f"[OrderAgent] cancel DB error: {e}")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"Failed to cancel order {order_num}: {e}",
                "messages": [{"text": "Something went wrong cancelling your order. Our team will assist you shortly."}],
            }

        await save_state(self.db, user_id, customer_id, {"pending_order_list": None})
        product = order.get("product_name") or order.get("product") or "your item"
        return {
            "handled": True,
            "messages": [{
                "text": (
                    f"✅ Order *#{order_num}* (*{product}*) has been cancelled successfully.\n\n"
                    f"If you change your mind or need help placing a new order, just let us know! 😊"
                )
            }],
            "escalate": False,
        }

    async def _handle_update(
        self,
        order: dict,
        customer_name: str,
        currency: str,
        language: str,
    ) -> Dict[str, Any]:
        """Order update always escalates — too complex to automate. Show clear reason."""
        order_num = order.get("order_number") or ("ORD-" + str(order.get("_id", ""))[:6].upper())
        status = (order.get("status") or "pending").capitalize()
        return {
            "handled": True,
            "escalate": True,
            "escalate_reason": f"Customer wants to update order {order_num} (status: {status}) — needs human action",
            "messages": [{
                "text": (
                    f"I've flagged order *#{order_num}* for our team to update. "
                    f"Please let them know what you'd like to change (address, item, quantity, etc.) "
                    f"and they'll sort it out for you right away! 🙏"
                )
            }],
        }

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
