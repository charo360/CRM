from typing import List, Dict, Any, Optional
from .base_agent import BaseAgent
from .sales_agent import SalesAgent
from .support_agent import SupportAgent
from .chat_agent import ChatAgent
from .personal_agent import PersonalAgent

class Router:
    def __init__(self, db: Any):
        self.db = db
        self.agents: List[BaseAgent] = [
            PersonalAgent("personal", db),
            SupportAgent("support", db),
            SalesAgent("sales", db),
            ChatAgent("chat", db),
        ]
        
    async def classify_intent(self, message: str) -> Dict[str, Any]:
        """Classify message intent and extract keywords in one AI call."""
        try:
            from ai_service import get_drafter
            ai_service = get_drafter()
            
            prompt = (
                "Analyze the user message and identify the intent and relevant keywords. "
                "Return result as JSON with keys: 'intent', 'keywords'.\n"
                "Intents: 'PRODUCT_INQUIRY', 'ORDER_STATUS', 'RETURN_POLICY', 'PERSONAL_CHAT', 'GENERAL_CHAT'.\n"
                "Keywords: 1-3 English keywords if the intent is PRODUCT_INQUIRY.\n\n"
                f"Message: '{message}'\n"
                "JSON format:"
            )
            
            # Use faster model for classification
            result_str = await ai_service._call_llm(prompt, model_pref="standard")
            
            # Clean JSON from markdown if present
            import re
            json_match = re.search(r'\{.*\}', result_str, re.DOTALL)
            if json_match:
                import json
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Router classification error: {e}")
        return {"intent": "GENERAL_CHAT", "keywords": []}

    async def route_and_process(self, user_id: str, message: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Classifies the intent first, then delegates to the appropriate agent.
        """
        # 1. Personal override
        if context.get("is_personal"):
            agent = PersonalAgent("personal", self.db)
            return await agent.process(user_id, message, context)

        # 2. Classify intent (ONE AI call)
        classification = await self.classify_intent(message)
        context["intent"] = classification.get("intent")
        context["keywords"] = classification.get("keywords", [])
        
        # 3. Targeted Dispatch
        intent = context["intent"]
        
        if intent == "PRODUCT_INQUIRY" or context["keywords"]:
            agent = SalesAgent("sales", self.db)
            result = await agent.process(user_id, message, context)
            if result and result.get("handled"):
                return result

        if intent in ["ORDER_STATUS", "RETURN_POLICY"]:
            agent = SupportAgent("support", self.db)
            result = await agent.process(user_id, message, context)
            if result and result.get("handled"):
                return result

        # Fallback to Chat
        agent = ChatAgent("chat", self.db)
        return await agent.process(user_id, message, context)
