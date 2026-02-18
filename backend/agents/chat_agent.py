from .base_agent import BaseAgent
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ChatAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles general conversation and casual chat.
        This is typically the fallback agent.
        """
        # For now, we'll use a simple keyword check to see if it's "just a chat"
        # Or we can just have it always handle the message if others failed.
        # Given the Chain of Responsibility, being the last agent means it handles everything left.
        
        # We'll use the ai_service to generate a friendly response.
        # We need to import it here to avoid circular dependencies if any.
        try:
            from ai_service import get_drafter
            ai_service = get_drafter()
            
            # Prepare context for AI
            # In a real scenario, we'd fetch recent messages from DB.
            # For now, we'll pass the current message and some basic context.
            
            customer_name = context.get("customer_name", "Customer")
            business_name = context.get("business_name", "Our Business")
            tone = context.get("tone", "friendly")
            
            # If the user just said "hello" or "hi", we can have a fast path, 
            # but let's see if the AI can do it better.
            
            instructions = (
                f"You are a friendly and helpful assistant. "
                "The customer/person is just chatting with you. Be natural, polite, and human-like. "
                "MATCH THE USER'S LANGUAGE AND STYLE. If they use a mix of languages (e.g. Sheng, Spanglish), reply using a similar mix to sound natural and relatable. "
                "Do NOT mention 'the store', 'products', or 'buying' UNLESS those topics are already present in the recent conversation history. "
                "If the user is praising something just sent (like 'they look beautiful'), acknowledge it warmly based on what was just discussed. "
                "Keep the conversation simple and respond directly to what they said."
            )
            
            custom_req = context.get("custom_instructions")
            if custom_req:
                instructions += f"\n\nUSER'S SPECIFIC REQUEST: {custom_req}\nFollow this request strictly while maintaining your persona."
            
            # Get history from context or fall back to just the current message
            history = context.get("history", [])
            if not history:
                history = [{"direction": "incoming", "content": message}]
            
            result = await ai_service.draft_followup_message(
                customer_name=customer_name,
                customer_data={},
                messages=history,
                business_name=business_name,
                tone=tone,
                business_knowledge=context.get("business_knowledge"),
                custom_instructions=instructions,
                user_id=user_id,
                model_pref=context.get("ai_model", "standard")
            )
            
            reply_text = result.get("drafted_message", "")
            
            if reply_text:
                return {
                    "messages": [{"text": reply_text}],
                    "handled": True
                }
                
        except Exception as e:
            logger.error(f"ChatAgent error: {e}")
            
        return {"handled": False}
