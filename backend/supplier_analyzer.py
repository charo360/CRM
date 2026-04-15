"""
Supplier Analyzer
Identifies suppliers from chat history and suggests restocking
"""
import logging
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from ai_service import get_drafter

logger = logging.getLogger(__name__)

# Strong keyword signals — fast pre-filter before AI call
SUPPLIER_KEYWORDS = [
    "invoice", "delivery note", "stock", "supply", "shipment", "tracking",
    "restock", "wholesale", "bulk", "proforma", "purchase order", "po ",
    "consignment", "dispatch", "goods", "price list", "quotation", "quote",
    "minimum order", "moq", "payment terms", "net 30", "net 60",
    "bei", "nipe bei", "stock yako", "delivery", "nimepeleka", "nimesend",
]

class SupplierAnalyzer:
    """Analyzes chats to find suppliers and sourcing opportunities"""
    
    def __init__(self, db):
        self.db = db
        self.drafter = get_drafter()

    async def identify_potential_suppliers(self, user_id: str) -> List[Dict]:
        """
        Scan recent active contacts and find potential suppliers using
        a two-stage approach: fast keyword pre-filter → AI confirmation.
        Only contacts with at least one keyword signal are sent to AI,
        keeping API costs low.
        """
        try:
            contacts = await self.db.customers.find({
                "user_id": user_id
            }).sort("last_contacted", -1).limit(60).to_list(60)

            eligible = [c for c in contacts if "Supplier" not in c.get("tags", [])]
            if not eligible:
                return []

            # One query for recent messages across all eligible contacts (avoids N sequential round-trips)
            ids = [c["_id"] for c in eligible]
            raw_msgs = await self.db.messages.find({
                "user_id": user_id,
                "customer_id": {"$in": ids},
            }).sort("created_at", -1).limit(2500).to_list(2500)

            by_customer: Dict[str, List[Dict]] = {}
            for m in raw_msgs:
                cid = m.get("customer_id")
                if not cid:
                    continue
                key = str(cid)
                if key not in by_customer:
                    by_customer[key] = []
                if len(by_customer[key]) < 15:
                    by_customer[key].append(m)

            id_to_contact = {str(c["_id"]): c for c in eligible}

            # Stage 1: keyword pre-filter (free, instant)
            candidates = []
            for cid_str, messages in by_customer.items():
                contact = id_to_contact.get(cid_str)
                if not contact or not messages:
                    continue
                full_text = " ".join([m.get("content", "").lower() for m in messages])
                if any(kw in full_text for kw in SUPPLIER_KEYWORDS):
                    candidates.append((contact, messages))

            if not candidates:
                return []

            # Stage 2: batch AI confirmation — send all candidates in one call
            potential_suppliers = await self._batch_ai_classify(candidates)
            return potential_suppliers

        except Exception as e:
            logger.error(f"Error identifying suppliers: {e}")
            return []

    async def _batch_ai_classify(self, candidates: List[tuple]) -> List[Dict]:
        """
        Send all keyword-matched candidates to AI in a single prompt.
        Returns list of contact dicts that AI confirmed as likely suppliers.
        """
        try:
            entries = []
            for i, (contact, messages) in enumerate(candidates):
                snippet = " | ".join([
                    m.get("content", "")[:120] for m in messages[:8]
                ])
                entries.append(f'{i}. Name: {contact.get("name","?")} | Chat: {snippet}')

            prompt = (
                "You are analyzing business WhatsApp chats to identify which contacts are SUPPLIERS "
                "(people/companies that SELL goods or materials TO the business owner).\n\n"
                "For each contact below, reply with just the index numbers (comma-separated) "
                "of those who are likely suppliers. If none qualify, reply with an empty list [].\n\n"
                "Contacts:\n" + "\n".join(entries) + "\n\n"
                "Reply with JSON only, e.g.: {\"suppliers\": [0, 2, 5]}"
            )

            result_str = await self.drafter._call_llm(prompt, model_pref="standard")

            json_match = re.search(r'\{.*\}', result_str, re.DOTALL)
            if not json_match:
                return []

            data = json.loads(json_match.group())
            confirmed_indices = data.get("suppliers", [])

            return [candidates[i][0] for i in confirmed_indices if i < len(candidates)]

        except Exception as e:
            logger.error(f"Batch AI supplier classification error: {e}")
            return []

    async def get_restock_suggestions(self, user_id: str) -> List[Dict]:
        """
        Generate restocking suggestions based on stock level and sales velocity.
        Prioritises products that are selling fast AND running low.
        """
        suggestions = []
        try:
            products = await self.db.products.find({
                "user_id": user_id,
                "in_stock": True
            }).to_list(50)

            if not products:
                return []

            # Get sales from the last 30 days to compute velocity
            since = datetime.utcnow() - timedelta(days=30)
            sales = await self.db.sales.find({
                "user_id": user_id,
                "created_at": {"$gte": since}
            }).to_list(500)

            # Count units sold per product name (sales store product name not id)
            sales_counts: Dict[str, int] = {}
            for sale in sales:
                name = (sale.get("product_name") or sale.get("product") or "").strip().lower()
                if name:
                    sales_counts[name] = sales_counts.get(name, 0) + sale.get("quantity", 1)

            for product in products:
                stock = product.get("stock_quantity")
                if stock is None:
                    stock = product.get("stock_count")
                if stock is None:
                    continue

                p_name = product.get("name", "")
                velocity = sales_counts.get(p_name.lower(), 0)

                # High: out of stock or stock < 3 and selling
                # Medium: stock < 10 and some sales, or stock < 5 regardless
                if stock == 0:
                    priority = "High"
                    action = "Out of stock — reorder immediately"
                elif stock < 3 and velocity > 0:
                    priority = "High"
                    action = f"Only {stock} left and {velocity} sold this month — reorder soon"
                elif stock < 5:
                    priority = "Medium"
                    action = f"Low stock ({stock} remaining) — consider restocking"
                elif stock < 10 and velocity >= 5:
                    priority = "Medium"
                    action = f"{velocity} units sold this month — stock may run out soon"
                else:
                    continue

                # Find linked supplier if any
                supplier_hint = ""
                if product.get("products_supplied"):
                    supplier_hint = f" Contact your supplier for {p_name}."

                suggestions.append({
                    "type": "restock",
                    "product_name": p_name,
                    "current_stock": stock,
                    "monthly_sales": velocity,
                    "suggested_action": action + supplier_hint,
                    "priority": priority,
                })

            # Sort: High first, then by lowest stock
            suggestions.sort(key=lambda x: (0 if x["priority"] == "High" else 1, x["current_stock"]))

        except Exception as e:
            logger.error(f"Error getting restock suggestions: {e}")

        return suggestions
