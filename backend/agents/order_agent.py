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

# ── Minimal UI translations for order flow error prompts ──────────────────────
_ORDER_T = {
    "invalid_menu": {
        "English": "Please reply with *1* (Add Item), *2* (Remove Item), or *3* (Change Quantity).",
        "Swahili": "Tafadhali jibu na *1* (Ongeza Bidhaa), *2* (Ondoa Bidhaa), au *3* (Badilisha Idadi).",
        "Sheng":   "Jibu *1* (Ongeza), *2* (Toa), ama *3* (Badilisha idadi) tu fam.",
    },
    "invalid_product_pick": {
        "English": "Please reply with the product number from the list above.",
        "Swahili": "Tafadhali jibu na nambari ya bidhaa kutoka kwenye orodha hapo juu.",
        "Sheng":   "Jibu na namba ya bidhaa uliyoona hapo juu.",
    },
    "invalid_remove_pick": {
        "English": "Please choose an item number from the list:\n{item_list}\nReply with the number (e.g. *1*).",
        "Swahili": "Tafadhali chagua nambari ya bidhaa:\n{item_list}\nJibu na nambari (mfano *1*).",
        "Sheng":   "Chagua namba ya kitu:\n{item_list}\nJibu na namba (e.g. *1*).",
    },
    "invalid_change_pick": {
        "English": "Please choose an item number to change its quantity:\n{item_list}\nReply with the number (e.g. *1*).",
        "Swahili": "Tafadhali chagua nambari ya bidhaa kubadilisha idadi yake:\n{item_list}\nJibu na nambari (mfano *1*).",
        "Sheng":   "Chagua namba ya kitu ubadilishe idadi:\n{item_list}\nJibu na namba (e.g. *1*).",
    },
    "invalid_qty": {
        "English": "Please reply with the new quantity (number only, e.g. *3*).",
        "Swahili": "Tafadhali jibu na idadi mpya (nambari tu, mfano *3*).",
        "Sheng":   "Jibu na namba tu, e.g. *3*.",
    },
    "qty_too_low": {
        "English": "Quantity must be at least 1. Please try again.",
        "Swahili": "Idadi lazima iwe angalau 1. Jaribu tena.",
        "Sheng":   "Lazima uandike angalau 1. Jaribu tena.",
    },
    "cannot_remove_all": {
        "English": "You can't remove all items from an order. Reply *1* to cancel the whole order instead.",
        "Swahili": "Huwezi kuondoa vitu vyote kwenye agizo. Jibu *1* kukufuta agizo lote badala yake.",
        "Sheng":   "Huwezi kuondoa vitu vyote. Jibu *1* ukifuta agizo lote.",
    },
}

def _t_order(language: str, key: str, **fmt) -> str:
    """Get a translated UI string for the order flow. Falls back to English."""
    lang = language.strip().capitalize() if language else "English"
    strings = _ORDER_T.get(key, {})
    text = strings.get(lang) or strings.get("English", key)
    return text.format(**fmt) if fmt else text


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

        # ── Handle update sub-flow steps (add/remove/change qty) ──────────
        pending_update_step = conv_state.get("pending_update_step")
        pending_action_order_id = conv_state.get("pending_order_action")
        if pending_update_step and pending_action_order_id:
            order_being_updated = await self.db.orders.find_one({"_id": pending_action_order_id})
            if order_being_updated:
                return await self._handle_update_step(
                    step=pending_update_step,
                    order=order_being_updated,
                    message=message,
                    customer_name=customer_name,
                    currency=currency,
                    language=language,
                    user_id=user_id,
                    customer_id=customer_id,
                    conv_state=conv_state,
                )

        # ── Handle 1=Cancel / 2=Update reply for a focused order ────────────
        if pending_action_order_id:
            pick_match = PICK_NUMBER_RE.match(message.strip())
            if pick_match:
                choice = int(pick_match.group(1))
                focused_order = await self.db.orders.find_one({"_id": pending_action_order_id})
                if focused_order:
                    if choice == 1:
                        return await self._handle_cancel(focused_order, customer_name, currency, language, user_id, customer_id)
                    elif choice == 2:
                        return await self._handle_update(focused_order, customer_name, currency, language, user_id, customer_id)

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
                    return await self._handle_update(specific_order, customer_name, currency, language, user_id, customer_id)
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
                    return await self._handle_update(actionable[0], customer_name, currency, language, user_id, customer_id)
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

        # ── Check for unhandled override/fallback intent ────────
        # If the user is in a pending state but gave an invalid reply (e.g. "Thank you" instead of "1"),
        # and their intent is not related to orders, we should clear the state and pass to another agent.
        from agents.intent_analyzer import ORDER_INTENTS
        if intent not in ORDER_INTENTS:
            if conv_state.get("pending_order_action") or conv_state.get("pending_order_list") or conv_state.get("pending_update_step"):
                from agents.conversation_state import save_state
                await save_state(self.db, user_id, customer_id, {
                    "pending_order_list": None,
                    "pending_order_action": None,
                    "pending_update_step": None,
                    "pending_update_item_idx": None,
                    "pending_update_products": None,
                    "pending_update_selected_product": None,
                })
            return {"handled": False}

        # Catch simple acknowledgements that might have been misclassified as ORDER_STATUS due to context
        import string
        clean_msg = message.lower().translate(str.maketrans('', '', string.punctuation)).strip()
        if clean_msg in {
            "ok", "okay", "k", "kk", "thanks", "thank you", "thx", "tysm", "thank you so much", "thanks a lot",
            "cool", "perfect", "awesome", "great", "good", "done", "sweet", "sounds good",
            "yes", "yep", "yeah", "no", "nope", "nah"
        }:
            # Let it fall through to ChatAgent
            return {"handled": False}

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
            # 8.1: Friendly fallback + flag owner to follow up
            return {
                "handled": True,
                "messages": [{"text": self._no_orders_reply(language)}],
                "escalate": False,
                "flag_for_human": True,
                "flag_reason": f"Customer asked about orders but none found — owner should follow up with {customer_name}",
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
            if len(active_orders) == 1:
                # Single active order — show with action hints and save state for 1=Cancel / 2=Update
                return await self._interact_with_order(
                    active_orders[0], customer_name, currency, language, user_id, customer_id
                )
            else:
                # 2 active orders — show both without action hints to avoid ambiguity
                blocks = []
                for o in active_orders:
                    blocks.append(_format_order_block(o, currency))
                intro = f"Hi {customer_name}! Here are your active orders:\n\n"
                reply = intro + "\n\n---\n\n".join(blocks)
                reply += "\n\nSend the order number (e.g. *ORD-4B9D32*) to view details or make changes."
                if len(orders) > len(active_orders):
                    reply += " For older orders, send their order number too."
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
        await save_state(
            self.db,
            user_id,
            customer_id,
            {
                "pending_order_list": order_ids,
                "pending_order_action": None,
                # Clear any active product-selection menu so it doesn't conflict
                "active_menu": False,
                "waiting_for_selection": False,
                "menu_items": {},
                "menu_type": None,
            },
        )
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
        # Save order ID for 1=Cancel / 2=Update reply, clear any pending order list
        status = (order.get("status") or "").lower()
        payment = (order.get("payment_status") or "").lower()
        action_order_id = str(order["_id"]) if (status in CANCELLABLE_STATUSES or payment == "unpaid") else None
        await save_state(self.db, user_id, customer_id, {"pending_order_list": None, "pending_order_action": action_order_id})
        return {"handled": True, "messages": [{"text": reply}], "escalate": False}

    def _action_hint(self, order: dict) -> str:
        """Return a short action prompt based on order status."""
        status = (order.get("status") or "").lower()
        payment = (order.get("payment_status") or "").lower()
        if status in CANCELLABLE_STATUSES or payment == "unpaid":
            return (
                f"_Need to make changes?_\n"
                f"1️⃣ Cancel Order\n"
                f"2️⃣ Update Order"
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

        await save_state(self.db, user_id, customer_id, {"pending_order_list": None, "pending_order_action": None})
        product = order.get("product_name") or order.get("product") or "your item"
        total = order.get("total_amount") or order.get("total") or 0
        return {
            "handled": True,
            "messages": [{
                "text": (
                    f"✅ Order *#{order_num}* (*{product}*) has been cancelled successfully.\n\n"
                    f"If you change your mind or need help placing a new order, just let us know! 😊"
                )
            }],
            "escalate": False,
            "owner_notification": {
                "title": f"❌ Order #{order_num} Cancelled",
                "body": f"{customer_name} cancelled {product} — {currency} {total:,.0f}",
            },
        }

    async def _handle_update(
        self,
        order: dict,
        customer_name: str,
        currency: str,
        language: str,
        user_id: str,
        customer_id: str,
    ) -> Dict[str, Any]:
        """Show self-service update menu: add item, remove item, change quantity."""
        from agents.conversation_state import save_state
        order_num = order.get("order_number") or ("ORD-" + str(order.get("_id", ""))[:6].upper())
        items = order.get("items", [])
        item_preview = ""
        if items:
            item_preview = "\n".join(
                f"  • {it.get('product_name','Item')} × {it.get('quantity',1)}"
                for it in items
            ) + "\n\n"
        await save_state(self.db, user_id, customer_id, {
            "pending_update_step": "update_menu",
            "pending_order_action": str(order["_id"]),
        })
        return {
            "handled": True,
            "escalate": False,
            "messages": [{"text": (
                f"What would you like to change for order *#{order_num}*?\n\n"
                f"{item_preview}"
                f"1️⃣ Add Item\n"
                f"2️⃣ Remove Item\n"
                f"3️⃣ Change Quantity\n\n"
                f"Reply with *1*, *2*, or *3*."
            )}],
        }

    async def _handle_update_step(
        self,
        step: str,
        order: dict,
        message: str,
        customer_name: str,
        currency: str,
        language: str,
        user_id: str,
        customer_id: str,
        conv_state: dict,
    ) -> Dict[str, Any]:
        """Handle each step of the self-service order update conversation."""
        import re as _re
        from agents.conversation_state import save_state
        order_num = order.get("order_number") or ("ORD-" + str(order.get("_id", ""))[:6].upper())
        items = list(order.get("items", []))

        def _clear():
            return save_state(self.db, user_id, customer_id, {
                "pending_update_step": None,
                "pending_order_action": None,
                "pending_update_item_idx": None,
                "pending_update_products": None,
                "pending_update_selected_product": None,
            })

        if step == "update_menu":
            pick = PICK_NUMBER_RE.match(message.strip())
            if pick:
                choice = int(pick.group(1))
                if choice == 1:
                    # Fetch product catalog and show numbered list
                    try:
                        _biz_id = user_id  # OrderAgent already uses correct user_id
                        products = await self.db.products.find({
                            "user_id": _biz_id,
                            "in_stock": {"$ne": False},
                        }).to_list(50)
                        if not products:
                            await _clear()
                            return {"handled": True, "escalate": False, "messages": [{"text": (
                                "No products available to add. Please contact us for help."
                            )}]}
                        # Build numbered catalog
                        lines = [f"Which product would you like to add to order *#{order_num}*?\n"]
                        for i, p in enumerate(products[:20], 1):
                            price_str = f"{currency} {p.get('price', 0):,.0f}" if p.get('price') else "Contact for price"
                            lines.append(f"*{i}.* {p['name']} — {price_str}")
                        lines.append("\nReply with the product number (e.g. *1*).")
                        # Save product list in state
                        await save_state(self.db, user_id, customer_id, {
                            "pending_update_step": "add_item_select_product",
                            "pending_order_action": str(order["_id"]),
                            "pending_update_products": [{"id": str(p["_id"]), "name": p["name"], "price": p.get("price", 0)} for p in products[:20]],
                        })
                        return {"handled": True, "escalate": False, "messages": [{"text": "\n".join(lines)}]}
                    except Exception as e:
                        logger.error(f"[OrderAgent] product fetch error: {e}")
                        await _clear()
                        return {"handled": True, "escalate": False, "messages": [{"text": (
                            "Something went wrong loading products. Please try again or contact us."
                        )}]}
                elif choice == 2:
                    if not items:
                        await _clear()
                        return {"handled": True, "escalate": False, "messages": [{"text": (
                            "This order has no individual items to remove. "
                            "Please contact us for help."
                        )}]}
                    lines = [f"Which item would you like to *remove* from order *#{order_num}*?\n"]
                    for i, it in enumerate(items, 1):
                        lines.append(f"*{i}.* {it.get('product_name','Item')} × {it.get('quantity',1)} — {currency} {it.get('price',0):,.0f}")
                    lines.append("\nReply with the item number (e.g. *1*).")
                    await save_state(self.db, user_id, customer_id, {
                        "pending_update_step": "remove_item_await",
                        "pending_order_action": str(order["_id"]),
                    })
                    return {"handled": True, "escalate": False, "messages": [{"text": "\n".join(lines)}]}
                elif choice == 3:
                    if not items:
                        await _clear()
                        return {"handled": True, "escalate": False, "messages": [{"text": (
                            "This order has no individual items to change. "
                            "Please contact us for help."
                        )}]}
                    lines = [f"Which item's quantity would you like to change?\n"]
                    for i, it in enumerate(items, 1):
                        lines.append(f"*{i}.* {it.get('product_name','Item')} × {it.get('quantity',1)}")
                    lines.append("\nReply with the item number (e.g. *1*).")
                    await save_state(self.db, user_id, customer_id, {
                        "pending_update_step": "change_qty_item",
                        "pending_order_action": str(order["_id"]),
                    })
                    return {"handled": True, "escalate": False, "messages": [{"text": "\n".join(lines)}]}
            return {"handled": True, "escalate": False, "messages": [{"text": _t_order(language, "invalid_menu")}]}

        elif step == "add_item_select_product":
            # Customer picked a product number from the catalog
            pick = PICK_NUMBER_RE.match(message.strip())
            products_list = conv_state.get("pending_update_products") or []
            if not products_list:
                # Products list is empty/stale — clear state and fall through to normal routing
                await _clear()
                return {"handled": False, "escalate": False, "messages": []}
            if pick:
                idx = int(pick.group(1)) - 1
                if 0 <= idx < len(products_list):
                    selected = products_list[idx]
                    # Ask for quantity
                    await save_state(self.db, user_id, customer_id, {
                        "pending_update_step": "add_item_await_qty",
                        "pending_order_action": str(order["_id"]),
                        "pending_update_selected_product": selected,
                    })
                    return {"handled": True, "escalate": False, "messages": [{"text": (
                        f"How many *{selected['name']}* would you like to add?\n"
                        f"Reply with a number (e.g. *2*)."
                    )}]}
            # Not a valid product number — check if customer wants to do something else
            _msg_lower = message.strip().lower()
            _escape_kw = {
                "order", "orders", "my order", "my orders", "order status", "check order",
                "cancel", "nevermind", "never mind", "forget it", "stop", "exit", "quit",
                "back", "go back", "start over", "reset", "help", "menu",
                "booking", "book", "appointment", "payment", "pay",
            }
            _is_escape = any(kw in _msg_lower for kw in _escape_kw)
            _is_question = any(_msg_lower.startswith(q) for q in ["what", "which", "where", "when", "how", "why", "who"])
            if _is_escape or _is_question:
                await _clear()
                return {"handled": False, "escalate": False, "messages": []}
            return {"handled": True, "escalate": False, "messages": [{"text": _t_order(language, "invalid_product_pick")}]}

        elif step == "add_item_await_qty":
            # Customer entered quantity
            qty_match = _re.match(r'^\s*(\d+)\s*$', message.strip())
            if qty_match:
                qty = int(qty_match.group(1))
                if qty <= 0:
                    return {"handled": True, "escalate": False, "messages": [{"text": _t_order(language, "qty_too_low")}]}
                selected = conv_state.get("pending_update_selected_product", {})
                item_name = selected.get("name", "Item")
                unit_price = selected.get("price", 0)
                new_item = {"product_name": item_name, "quantity": qty, "price": unit_price * qty}
                new_items = items + [new_item]
                new_total = sum(it.get("price", 0) for it in new_items)
                await self.db.orders.update_one(
                    {"_id": order["_id"]},
                    {"$set": {"items": new_items, "total_amount": new_total, "total": new_total}}
                )
                await _clear()
                return {
                    "handled": True, "escalate": False,
                    "messages": [{"text": (
                        f"✅ Added *{item_name} × {qty}* to order *#{order_num}*.\n\n"
                        f"Updated total: {currency} {new_total:,.0f} 🎉"
                    )}],
                    "owner_notification": {
                        "title": f"📦 Order #{order_num} Updated",
                        "body": f"{customer_name} added {item_name} × {qty}",
                    },
                }
            return {"handled": True, "escalate": False, "messages": [{"text": _t_order(language, "invalid_qty")}]}

        elif step == "remove_item_await":
            pick = PICK_NUMBER_RE.match(message.strip())
            if pick:
                idx = int(pick.group(1)) - 1
                if 0 <= idx < len(items):
                    removed = items[idx]
                    new_items = [it for i, it in enumerate(items) if i != idx]
                    if not new_items:
                        return {"handled": True, "escalate": False, "messages": [{"text": _t_order(language, "cannot_remove_all")}]}
                    new_total = sum(it.get("price", 0) for it in new_items)
                    await self.db.orders.update_one(
                        {"_id": order["_id"]},
                        {"$set": {"items": new_items, "total_amount": new_total, "total": new_total}}
                    )
                    await _clear()
                    removed_name = removed.get("product_name", "Item")
                    return {
                        "handled": True, "escalate": False,
                        "messages": [{"text": (
                            f"✅ Removed *{removed_name}* from order *#{order_num}*.\n\n"
                            f"Updated total: {currency} {new_total:,.0f}"
                        )}],
                        "owner_notification": {
                            "title": f"📦 Order #{order_num} Updated",
                            "body": f"{customer_name} removed {removed_name}",
                        },
                    }
            item_list = "\n".join(f"*{i+1}.* {it.get('product_name','Item')} × {it.get('quantity',1)}" for i, it in enumerate(items))
            return {"handled": True, "escalate": False, "messages": [{"text": _t_order(language, "invalid_remove_pick", item_list=item_list)}]}

        elif step == "change_qty_item":
            pick = PICK_NUMBER_RE.match(message.strip())
            if pick:
                idx = int(pick.group(1)) - 1
                if 0 <= idx < len(items):
                    item_name = items[idx].get("product_name", "Item")
                    cur_qty = items[idx].get("quantity", 1)
                    await save_state(self.db, user_id, customer_id, {
                        "pending_update_step": "change_qty_value",
                        "pending_order_action": str(order["_id"]),
                        "pending_update_item_idx": idx,
                    })
                    return {"handled": True, "escalate": False, "messages": [{"text": (
                        f"What is the new quantity for *{item_name}*? "
                        f"(Current: {cur_qty})\n"
                        f"Reply with a number, e.g. *3*"
                    )}]}
            item_list = "\n".join(f"*{i+1}.* {it.get('product_name','Item')} × {it.get('quantity',1)}" for i, it in enumerate(items))
            return {"handled": True, "escalate": False, "messages": [{"text": _t_order(language, "invalid_change_pick", item_list=item_list)}]}

        elif step == "change_qty_value":
            item_idx = conv_state.get("pending_update_item_idx", 0)
            qty_match = _re.match(r'^\s*(\d+)\s*$', message.strip())
            if qty_match and items and 0 <= item_idx < len(items):
                new_qty = int(qty_match.group(1))
                if new_qty <= 0:
                    return {"handled": True, "escalate": False, "messages": [{"text": (
                        "Quantity must be at least 1. Please try again."
                    )}]}
                new_items = list(items)
                old_item = dict(new_items[item_idx])
                old_qty = max(old_item.get("quantity", 1), 1)
                unit_price = old_item.get("price", 0) / old_qty
                old_item["quantity"] = new_qty
                old_item["price"] = round(unit_price * new_qty, 2)
                new_items[item_idx] = old_item
                new_total = sum(it.get("price", 0) for it in new_items)
                await self.db.orders.update_one(
                    {"_id": order["_id"]},
                    {"$set": {"items": new_items, "total_amount": new_total, "total": new_total}}
                )
                await _clear()
                item_name = old_item.get("product_name", "Item")
                return {
                    "handled": True, "escalate": False,
                    "messages": [{"text": (
                        f"✅ Changed *{item_name}* quantity to {new_qty}.\n\n"
                        f"Updated total: {currency} {new_total:,.0f}"
                    )}],
                    "owner_notification": {
                        "title": f"📦 Order #{order_num} Updated",
                        "body": f"{customer_name} changed {item_name} qty to {new_qty}",
                    },
                }
            return {"handled": True, "escalate": False, "messages": [{"text": _t_order(language, "invalid_qty")}]}

        # Unknown step — clear state
        await _clear()
        return {"handled": False, "messages": [], "escalate": False}

    async def _build_status_reply(
        self,
        orders: list,
        message: str,
        intent: str,
        customer_name: str,
        language: str,
        business_knowledge: str,
        currency: str = "",
        confidence: float = 1.0,
        careful_instruction: str = "",
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

        intent_hint = (
            f"Intent classified as: {intent} ({confidence:.0%} confidence)\n"
            f"Customer message: \"{message}\"\n\n"
            f"Read the message yourself. If the classification seems off, address what the customer actually needs instead.\n"
        )
        if careful_instruction:
            intent_hint += f"\n{careful_instruction}\n"

        prompt = f"""You are a helpful order status assistant for a WhatsApp business.

{intent_hint}
Business info: {bk}

Customer name: {customer_name}

Their recent orders:
{orders_text}

Think one sentence about what this customer actually needs, then reply. Output only the customer-facing message.

Rules:
1. Directly answer what they asked about their order(s)
2. Always include the order number (e.g. #ORD-XXXXXX) when mentioning an order
3. State current status and payment status clearly
4. 8.3 DELIVERY RULE: ONLY state a delivery date if it is EXPLICITLY in the order data above. If not present, say \"our team will confirm delivery timing with you\" — NEVER estimate
5. Brief (2-4 sentences max), natural WhatsApp tone
6. CRITICAL: ONLY state facts from the order data above. NEVER invent delivery dates, tracking numbers, or order details."""

        return await ai._call_llm(prompt, model_pref="standard")

    def _no_record_reply(self, language: str) -> str:
        return "Let me look into that for you! Could you confirm the number or name you used when placing the order? I want to make sure I'm checking the right account. 😊"

    def _no_orders_reply(self, language: str) -> str:
        return "Let me check on that for you! I don't see any recent orders on your account just yet. If you've placed one recently, it may still be processing — I'll follow up shortly! 🙏"
