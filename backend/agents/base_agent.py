from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseAgent(ABC):
    def __init__(self, name: str, db: Any):
        self.name = name
        self.db = db
        
    @abstractmethod
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the user message and return a response.
        
        Args:
            user_id: The user's ID definition.
            message: The user's message text.
            context: Conversation context (e.g. history, user settings).
            
        Returns dict with keys:
            - messages: List[Dict] (Each dict has 'text', optional 'media_url')
            - context_update: Dict (New context variables to save)
            - handled: bool (Did this agent handle it?)
        """
        pass
