"""
Supplier Analyzer
Identifies suppliers from chat history and suggests restocking
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from ai_service import get_drafter

logger = logging.getLogger(__name__)

class SupplierAnalyzer:
    """Analyzes chats to find suppliers and sourcing opportunities"""
    
    def __init__(self, db):
        self.db = db
        self.drafter = get_drafter()
        
    async def identify_potential_suppliers(self, user_id: str) -> List[Dict]:
        """
        Scan all contacts to find potential suppliers based on chat history
        """
        try:
            # Get all customers/contacts
            # In a real app, we might filter by those NOT already tagged as suppliers
            # But here we'll just scan recent active chats
            
            # Find contacts with recent messages
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$sort": {"last_contacted": -1}},
                {"$limit": 50}  # Scan top 50 active chats
            ]
            
            contacts = await self.db.customers.find({
                "user_id": user_id
            }).sort("last_contacted", -1).limit(50).to_list(50)
            
            potential_suppliers = []
            
            for contact in contacts:
                # Skip if already tagged as supplier (assuming we add this tag)
                if "Supplier" in contact.get("tags", []):
                    continue
                    
                is_supplier = await self._analyze_contact_for_supplier_signals(contact)
                if is_supplier:
                    potential_suppliers.append(contact)
                    
            return potential_suppliers
            
        except Exception as e:
            logger.error(f"Error identifying suppliers: {e}")
            return []

    async def _analyze_contact_for_supplier_signals(self, contact: Dict) -> bool:
        """
        Analyze a single contact's messages for supplier signals
        Signals: "invoice", "delivery", "stock", "payment received", "order"
        """
        try:
            messages = await self.db.messages.find({
                "customer_id": contact["_id"],
                "user_id": contact.get("user_id")
            }).sort("timestamp", -1).limit(10).to_list(10)
            
            if not messages:
                return False
                
            # supplier_keywords = [
            #     "invoice", "receipt", "delivery", "stock", "supply", 
            #     "payment received", "order confirmed", "tracking", "shipment"
            # ]
            
            # Simple heuristic analysis
            # In production, use LLM for better accuracy
            full_text = " ".join([m.get("content", "").lower() for m in messages])
            
            # Check for strong supplier indicators
            if "invoice" in full_text or "delivery note" in full_text:
                return True
                
            # Check for context: You asking for price/stock usually means they are supplier
            # But let's assume we use AI for this to be smarter
            
            return False # Default to False for now to avoid false positives without AI
            
        except Exception as e:
            logger.error(f"Error analyzing contact {contact.get('_id')}: {e}")
            return False

    async def get_restock_suggestions(self, user_id: str) -> List[Dict]:
        """
        Generate restocking suggestions based on sales velocity
        """
        # This would require linking Products to Suppliers
        # For MVP, we'll return a mock suggestion if low stock
        
        suggestions = []
        try:
            # Get low stock products
            low_stock_products = await self.db.products.find({
                "user_id": user_id, 
                "stock_count": {"$lt": 5} # Threshold
            }).to_list(10)
            
            for product in low_stock_products:
                # Find distinct suppliers for this product (if linked)
                # Or just generic suggestion
                suggestions.append({
                    "type": "restock",
                    "product_name": product["name"],
                    "current_stock": product.get("stock_count", 0),
                    "suggested_action": "Reorder from supplier",
                    "priority": "High" if product.get("stock_count", 0) == 0 else "Medium"
                })
                
        except Exception as e:
            logger.error(f"Error getting restock suggestions: {e}")
            
        return suggestions
