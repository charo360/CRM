"""
OrderAgent — Handles order status, delivery, tracking, order changes.
Reads real order data from DB. Escalates when order not found or issue unresolvable.
"""
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class OrderAgent:
    def __init__(self, db: Any):
        self.db = db

    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        customer_id = context.get("customer_id")
        intent = context.get("intent", "ORDER_STATUS")
        customer_name = context.get("customer_name", "there")
        language = context.get("language", "English")
        business_knowledge = context.get("business_knowledge", "")

        if not customer_id:
            return {
                "handled": True,
                "messages": [{"text": self._no_record_reply(language)}],
                "escalate": False,
            }

        # Fetch last 5 orders for this customer
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

        # Handle specific intents
        if intent in ("ORDER_CANCEL", "ORDER_MODIFY"):
            # Can't do this automatically — escalate to human
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"Customer requested {intent} — needs human action",
                "messages": [],
            }

        # Build order status reply using AI for natural language
        try:
            reply = await self._build_status_reply(
                orders, message, intent, customer_name, language, business_knowledge, user_id
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

    async def _build_status_reply(
        self,
        orders: list,
        message: str,
        intent: str,
        customer_name: str,
        language: str,
        business_knowledge: str,
        user_id: str,
    ) -> str:
        from ai_service import get_drafter
        ai = get_drafter()

        # Format orders for the prompt
        order_lines = []
        for o in orders:
            status = o.get("status", "pending").capitalize()
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
            line = f"- {product} (qty: {qty}) | Status: {status}"
            if total:
                line += f" | Amount: {total}"
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
2. States the current status clearly
3. If delivery info is available, mention it
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
