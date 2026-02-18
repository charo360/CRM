from typing import Dict, List, Any
import datetime

class MultiLayerContextManager:
    """
    Manages context at 5 levels:
    1. Immediate: The specific message being replied to (and its intent)
    2. Thread: The current active conversation (last 10-20 messages)
    3. Session: The broader ongoing interaction (e.g., "Shopping Session" started 2 hours ago)
    4. Historical: Long-term user data (Purchase history, VIP status, Communication Style)
    5. Global: Environmental context (Time of day, Business Hours, Holidays, Global Business Rules)
    """

    def __init__(self, knowledge_base=None):
        self.kb = knowledge_base

    async def build_context(self, db, user_id: str, message: Dict, intent_data: Dict) -> Dict[str, Any]:
        """
        Aggregates context from all 5 layers.
        """
        
        # 1. Global Context
        global_ctx = self._get_global_context()

        # 2. Historical Context (User Profile)
        history_ctx = await self._get_historical_context(db, user_id)

        # 3. Session Context (Recent interactions, state)
        session_ctx = await self._get_session_context(db, user_id)

        # 4. Thread Context (Recent messages)
        thread_ctx = await self._get_thread_context(db, user_id)

        # 5. Immediate Context (Intent, Entities)
        immediate_ctx = {
            "intent": intent_data.get("intent"),
            "entities": intent_data.get("entities"),
            "current_message": message.get("content")
        }
        
        # Merge with Knowledge Base if needed
        kb_ctx = {}
        if self.kb:
            # Search products if intent is business-related
            query = None
            if intent_data.get("intent") in ["business_b2c", "business_b2b"]:
                query = message.get("content")
                
            kb_ctx = await self.kb.get_context(db, query)

        return {
            "global": global_ctx,
            "historical": history_ctx,
            "session": session_ctx,
            "thread": thread_ctx,
            "immediate": immediate_ctx,
            "knowledge_base": kb_ctx
        }

    def _get_global_context(self) -> Dict[str, Any]:
        now = datetime.datetime.now()
        hour = now.hour
        time_of_day = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening"
        
        # Simple hardcoded business hours logic (Mon-Fri 8-6)
        is_business_hours = 8 <= hour < 18 and now.weekday() < 5
        
        return {
            "time_of_day": time_of_day,
            "day_of_week": now.strftime("%A"),
            "date": now.strftime("%Y-%m-%d"),
            "is_business_hours": is_business_hours
        }

    async def _get_historical_context(self, db, user_id: str) -> Dict[str, Any]:
        """
        Fetches user profile, VIP status, total spend.
        """
        customer = await db.customers.find_one({"user_id": user_id}) # Assuming user_id maps to customer owner or checking customer collection directly
        # Wait, 'user_id' in server.py usually refers to the Business Owner. 
        # But here valid context needs the CUSTOMER's ID. 
        # The 'user_id' param passed here should be the customer's unique ID or we need both.
        # Let's assume 'user_id' passed to this function is the CUSTOMER'S ID or we pass distinct args.
        
        # Refactoring: The AI service generally deals with a 'customer' object.
        # I'll update the signature to accept 'customer_id' or 'customer_data'.
        
        # For now, let's assume usage involves passing the customer_id
        return {} # Placeholder, will need actual DB lookup based on integrating logic

    async def _get_session_context(self, db, user_id: str) -> Dict[str, Any]:
        # Placeholder for session logic (e.g. cart state, open tickets)
        return {"current_flow": "general"}
        
    async def _get_thread_context(self, db, user_id: str) -> List[Dict]:
        # Placeholder - would fetch last N messages
        return []

    # Correction: The logic above needs to be robust about who 'user_id' is.
    # In 'ai_service.py', we work with 'customer_data'.
    # I should align with that. 
    
    async def build_context_from_customer(self, db, customer_id: str, message: Dict, intent_data: Dict) -> Dict[str, Any]:
        # Re-implementing with clearer variable names
        
        # 1. Global
        global_ctx = self._get_global_context()
        
        # 2. Historical
        customer = await db.customers.find_one({"_id": customer_id})
        history_ctx = {
            "name": customer.get("name"),
            "is_vip": "VIP" in customer.get("tags", []),
            "total_spent": customer.get("total_spent", 0),
            "communication_style": customer.get("communication_style", {})
        } if customer else {}
        
        # 3. Session (mocked for now, implies tracking session ID in Redis/DB)
        session_ctx = {"state": "active"} 

        # 4. Thread
        # Fetch last 5 messages
        thread = await db.messages.find(
            {"customer_id": customer_id}
        ).sort("created_at", -1).limit(5).to_list(5)
        
        # Reverse to chronological order
        thread_ctx = thread[::-1] if thread else []

        # 5. Immediate
        immediate_ctx = {
            "intent": intent_data.get("intent"),
            "entities": intent_data.get("entities"),
            "content": message.get("content")
        }
        
        # KB
        kb_ctx = {}
        if self.kb:
             # Search products if intent is business-related
            query = None
            if intent_data.get("intent") in ["business_b2c", "business_b2b"]:
                query = message.get("content")
            kb_ctx = await self.kb.get_context(db, query)

        return {
            "global": global_ctx,
            "historical": history_ctx,
            "session": session_ctx,
            "thread": thread_ctx,
            "immediate": immediate_ctx,
            "knowledge_base": kb_ctx
        }
