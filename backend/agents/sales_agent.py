from .base_agent import BaseAgent
from .tools import find_product_matches, normalize_url
from typing import List, Dict, Any
import random

class SalesAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles product inquiries using fuzzy matching and sends product images.
        """
        # Fetch products from DB
        # Note: In production, consider caching this or passing it in context
        products = await self.db.products.find({"user_id": user_id}).to_list(100)
        
        matches = find_product_matches(message, products)
        
        # 2. Multi-language Support: Use pre-extracted keywords if available
        if not matches:
            ai_keywords = context.get("keywords")
            if ai_keywords:
                if isinstance(ai_keywords, list):
                    ai_keywords = ", ".join(ai_keywords)
                print(f"DEBUG: Using pre-classified keywords: {ai_keywords}")
                matches = find_product_matches(ai_keywords, products)
            
            # Fallback (optional, keep it minimal)
            if not matches and context.get("intent") == "PRODUCT_INQUIRY":
                # Only if Router said PRODUCT_INQUIRY but extraction failed, try once more? 
                # Actually, let's trust the Router and skip it to save time.
                pass

        if not matches:
            return {"handled": False}
            
        messages = []
        context_update = {}
        
        # Limit to 5 matches
        limit = 5
        to_send = matches[:limit]

        # If multiple matches, use simpler language with variety
        if len(to_send) > 1:
            headers = [
                "Here is what we have available:",
                "Check these out:",
                "We have these in stock:",
                "Here are the ones match your request:",
                "Take a look at these:",
            ]
            messages.append({"text": random.choice(headers)})
            
        for p in to_send:
            price = p.get('price', 0)
            currency = context.get('currency', 'USD')
            caption = f"*{p['name']}*\n💰 {currency} {price:,.0f}"
            
            # Simple description
            if p.get('description'):
                desc = p['description']
                if len(desc) > 100: desc = desc[:97] + "..."
                caption += f"\n{desc}"
            
            # Get Image
            img_url = p.get("image_url")
            if not img_url and p.get("images"):
                img_url = p["images"][0]
                
            msg = {"text": caption}
            if img_url:
                msg["media_url"] = normalize_url(img_url)
                
            messages.append(msg)
            
            # Update context if single match
            if len(to_send) == 1:
                context_update["last_discussed_product_id"] = str(p["_id"])
        
        return {
            "messages": messages,
            "context_update": context_update,
            "handled": True
        }
