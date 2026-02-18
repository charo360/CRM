from .base_agent import BaseAgent
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class PersonalAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles personal chats (friends, family).
        Triggered when the contact is marked as personal.
        """
        # We only handle this if 'is_personal' is True in context.
        # Actually, the Router will usually decide this, but we check just in case.
        if not context.get("is_personal"):
            return {"handled": False}

        try:
            from ai_service import get_drafter
            ai_service = get_drafter()
            
            customer_name = context.get("customer_name", "Customer")
            
            instructions = (
                "You are acting as a friendly personal assistant for the user. "
                f"The person you are talking to is {customer_name}, who is a personal connection (friend or family). "
                "Use a warm, casual, and very human tone. No formal business talk. "
                "MATCH THE USER'S LANGUAGE AND STYLE. If they use a mix of languages (e.g. Sheng, Spanglish), reply using a similar mix to sound natural and relatable. "
                "If they are asking a question, help the user answer it. "
                "Keep it brief and caring. Respond directly to the latest message."
            )
            
            custom_req = context.get("custom_instructions")
            if custom_req:
                instructions += f"\n\nUSER'S SPECIFIC REQUEST: {custom_req}\nFollow this request strictly while maintaining your persona."
            
            # Get history from context or fall back to current message
            history = context.get("history", [])
            if not history:
                history = [{"direction": "incoming", "content": message}]
            
            result = await ai_service.draft_followup_message(
                customer_name=customer_name,
                customer_data={},
                messages=history,
                business_name="Personal", # Don't use business name
                tone="casual",
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
            logger.error(f"PersonalAgent error: {e}")
            
        return {"handled": False}
