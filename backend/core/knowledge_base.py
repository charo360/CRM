from typing import Dict, List, Any, Optional
import datetime

class CentralizedKnowledgeBase:
    """
    Single source of truth for:
    1. Products (from DB)
    2. Business Rules (Opening hours, policies)
    3. FAQs (Common answers)
    """

    def __init__(self):
        # Hardcoded business rules for now, can be moved to DB settings later
        self.business_rules = {
            "opening_hours": "Mon-Fri: 8am - 6pm, Sat: 9am - 4pm, Sun: Closed",
            "delivery_policy": "Delivery within Nairobi is 200 KES. Countrywide delivery available via Fargo/G4S.",
            "payment_methods": "M-Pesa (Till Number 123456), Bank Transfer, Cash on Delivery (within CBD only).",
            "return_policy": "Returns accepted within 3 days if item is unused and in original packaging."
        }
        
        # Common FAQs
        self.faqs = {
            "location": "We are located at CBD, Moi Avenue, Bazaar Plaza, 3rd Floor.",
            "contacts": "Call or WhatsApp us on 0712345678."
        }

    async def get_context(self, db, query=None) -> Dict[str, Any]:
        """
        Retrieves relevant context based on a query or general context.
        """
        context = {
            "business_rules": self.business_rules,
            "faqs": self.faqs,
            "products": []
        }
        
        if query and db:
            context["products"] = await self._search_products(db, query)
            
        return context

    async def _search_products(self, db, query: str) -> List[Dict[str, Any]]:
        """
        Search products in the database based on the query.
        """
        if not query:
            return []
            
        try:
            # Basic text search on 'name' and 'description'
            # Check if text index exists, otherwise use regex (slower but works for small DBs)
            
            # Simple keyword matching for now
            keywords = query.lower().split()
            search_regex = "|".join([re.escape(k) for k in keywords if len(k) > 2])
            
            if not search_regex:
                return []

            products = await db.products.find({
                "$or": [
                    {"name": {"$regex": search_regex, "$options": "i"}},
                    {"description": {"$regex": search_regex, "$options": "i"}},
                    {"category": {"$regex": search_regex, "$options": "i"}}
                ]
            }).limit(5).to_list(5)
            
            # Format product info
            formatted_products = []
            for p in products:
                formatted_products.append({
                    "name": p.get("name"),
                    "price": p.get("price"),
                    "stock": p.get("stock_quantity", "Unknown"),
                    "description": p.get("description", "")
                })
                
            return formatted_products
            
        except Exception as e:
            print(f"Error searching products: {e}")
            return []

import re
