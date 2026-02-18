from .base_agent import BaseAgent
from typing import List, Dict, Any
import random
from datetime import datetime

class SupportAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles support inquiries like order status, return policy, etc.
        """
        body_lower = message.lower()
        customer_id = context.get("customer_id")
        
        # 1. Keyword check (Fast path)
        is_order = any(kw in body_lower for kw in ["order status", "where is my order", "track my order", "my order", "orders"])
        is_policy = any(kw in body_lower for kw in ["return", "refund", "exchange", "policy"])
        
        # 2. AI Intent extraction: Use intent from Router if available
        if not is_order and not is_policy:
            intent = context.get("intent")
            if intent == "ORDER_STATUS":
                is_order = True
            elif intent == "RETURN_POLICY":
                is_policy = True
            
            # Fallback (optional)
            if not is_order and not is_policy:
                # We skip doing an internal AI call to save time
                pass

        # Dispatch
        if is_order:
            return await self.handle_order_status(user_id, customer_id)
        if is_policy:
            return self.handle_return_policy()
            
        return {"handled": False}

    async def handle_order_status(self, user_id: str, customer_id: str) -> Dict[str, Any]:
        if not customer_id:
            return {
                "messages": [{"text": "I'm sorry, I couldn't find your customer record to check order status."}],
                "handled": True
            }
            
        # Fetch last 3 orders
        orders = await self.db.orders.find({
            "user_id": user_id,
            "customer_id": customer_id
        }).sort("created_at", -1).to_list(3)
        
        if not orders:
            return {
                "messages": [{"text": "I don't see any recent orders under your account. Would you like to see our catalog?"}],
                "handled": True
            }
            
        messages = []
        messages.append({"text": "Here are your recent orders:"})
        
        for o in orders:
            status = o.get("status", "Pending").capitalize()
            product = o.get("product", "Unknown item")
            date_str = ""
            if o.get("created_at"):
                date_str = f" ({o['created_at'].strftime('%b %d')})"
                
            messages.append({
                "text": f"📦 *{product}*\nStatus: {status}{date_str}"
            })
            
        return {
            "messages": messages,
            "handled": True
        }

    def handle_return_policy(self) -> Dict[str, Any]:
        policies = [
            "We offer a 7-day return policy for unused items in their original packaging.",
            "Items can be returned or exchanged within 7 days of purchase. Just keep the receipt!",
            "You have 7 days to return any item if you're not satisfied. We'll handle the rest!"
        ]
        return {
            "messages": [{"text": random.choice(policies)}],
            "handled": True
        }
