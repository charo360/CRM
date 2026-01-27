"""
AI Message Drafter Service
Generates personalized follow-up messages using Gemini AI
"""
import os
import httpx
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"


class AIMessageDrafter:
    """Service for drafting personalized follow-up messages using AI"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set - AI drafting will not work")
    
    async def draft_followup_message(
        self,
        customer_name: str,
        customer_data: Dict,
        messages: List[Dict],
        business_name: str = "Your Business",
        tone: str = "friendly"
    ) -> Dict[str, any]:
        """
        Draft a personalized follow-up message for a customer
        
        Args:
            customer_name: Name of the customer
            customer_data: Customer info (tags, notes, purchase history)
            messages: List of recent messages with the customer
            business_name: Name of the business
            tone: Message tone (professional, friendly, casual)
        
        Returns:
            Dict with 'message', 'confidence', and 'reason'
        """
        if not self.api_key:
            return {
                "message": f"Hi {customer_name}, just checking in! How can we help you today?",
                "confidence": 0.5,
                "reason": "Default message (AI not configured)"
            }
        
        # Build context from customer data
        context = self._build_customer_context(customer_name, customer_data, messages)
        
        # Create AI prompt
        prompt = self._create_prompt(context, business_name, tone)
        
        # Call Gemini API
        try:
            drafted_message = await self._call_gemini(prompt)
            return {
                "message": drafted_message,
                "confidence": 0.85,
                "reason": self._extract_reason(context)
            }
        except Exception as e:
            logger.error(f"AI drafting failed: {e}")
            return {
                "message": f"Hi {customer_name}, hope you're doing well! Just wanted to check in and see if there's anything we can help you with.",
                "confidence": 0.5,
                "reason": f"Fallback message (AI error: {str(e)[:50]})"
            }
    
    def _build_customer_context(
        self,
        customer_name: str,
        customer_data: Dict,
        messages: List[Dict]
    ) -> Dict:
        """Build context from customer data and messages"""
        
        # Calculate days since last contact
        last_contacted = customer_data.get('last_contacted')
        days_since = None
        if last_contacted:
            if isinstance(last_contacted, str):
                last_contacted = datetime.fromisoformat(last_contacted.replace('Z', '+00:00'))
            days_since = (datetime.utcnow() - last_contacted).days
        
        # Get last message content
        last_message = messages[-1]['content'] if messages else None
        last_message_direction = messages[-1]['direction'] if messages else None
        
        # Extract conversation topics
        topics = self._extract_topics(messages)
        
        # Get customer tags
        tags = customer_data.get('tags', [])
        is_vip = 'VIP' in tags
        is_new = 'New' in tags
        
        return {
            'name': customer_name,
            'days_since_contact': days_since,
            'last_message': last_message,
            'last_message_direction': last_message_direction,
            'topics': topics,
            'is_vip': is_vip,
            'is_new': is_new,
            'purchase_count': customer_data.get('purchase_count', 0),
            'total_spent': customer_data.get('total_spent', 0),
            'notes': customer_data.get('notes', '')
        }
    
    def _extract_topics(self, messages: List[Dict]) -> List[str]:
        """Extract conversation topics from messages"""
        topics = []
        
        # Look for common keywords in recent messages
        keywords = {
            'pricing': ['price', 'cost', 'how much', 'bei', 'ksh'],
            'product_inquiry': ['product', 'item', 'stock', 'available'],
            'delivery': ['deliver', 'shipping', 'send', 'location'],
            'complaint': ['problem', 'issue', 'not working', 'broken'],
            'thanks': ['thank', 'asante', 'appreciate']
        }
        
        recent_messages = messages[-5:] if len(messages) > 5 else messages
        
        for msg in recent_messages:
            content = msg.get('content', '').lower()
            for topic, words in keywords.items():
                if any(word in content for word in words):
                    if topic not in topics:
                        topics.append(topic)
        
        return topics
    
    def _create_prompt(self, context: Dict, business_name: str, tone: str) -> str:
        """Create prompt for Gemini AI"""
        
        # Build context description
        context_parts = []
        
        if context['days_since_contact']:
            context_parts.append(f"Last contacted {context['days_since_contact']} days ago")
        else:
            context_parts.append("Never contacted before")
        
        if context['is_vip']:
            context_parts.append("VIP customer")
        elif context['is_new']:
            context_parts.append("New customer")
        
        if context['purchase_count'] > 0:
            context_parts.append(f"Made {context['purchase_count']} purchases (KES {context['total_spent']:.0f} total)")
        
        if context['last_message']:
            context_parts.append(f"Last message from {'them' if context['last_message_direction'] == 'incoming' else 'us'}: \"{context['last_message'][:100]}\"")
        
        if context['topics']:
            context_parts.append(f"Discussed: {', '.join(context['topics'])}")
        
        if context['notes']:
            context_parts.append(f"Notes: {context['notes'][:100]}")
        
        context_str = "\n- ".join(context_parts)
        
        # Tone instructions
        tone_instructions = {
            'professional': 'professional and respectful',
            'friendly': 'warm and friendly',
            'casual': 'casual and conversational'
        }
        tone_desc = tone_instructions.get(tone, 'friendly')
        
        prompt = f"""You are a helpful business assistant for {business_name}, a Kenyan business. 
Draft a personalized WhatsApp follow-up message for customer {context['name']}.

Customer Context:
- {context_str}

Instructions:
1. Write a {tone_desc} message in English (you can use Swahili greetings if appropriate)
2. Reference their last interaction naturally if relevant
3. Keep it SHORT (1-3 sentences max)
4. Make it personal and contextual, not generic
5. Include a clear call-to-action or question
6. DO NOT use emojis excessively (max 1-2)
7. Sound natural, like a real person texting

Write ONLY the message text, nothing else. No quotes, no explanations."""

        return prompt
    
    def _extract_reason(self, context: Dict) -> str:
        """Extract a short reason for the follow-up"""
        
        if context['is_new'] and not context['days_since_contact']:
            return "New customer - never contacted"
        
        if context['days_since_contact']:
            if context['days_since_contact'] > 30:
                return f"Inactive for {context['days_since_contact']} days"
            elif context['days_since_contact'] > 14:
                return f"No contact in {context['days_since_contact']} days"
        
        if 'pricing' in context['topics']:
            return "Asked about pricing - follow up on quote"
        
        if 'product_inquiry' in context['topics']:
            return "Product inquiry - check if still interested"
        
        if 'complaint' in context['topics']:
            return "Had an issue - check if resolved"
        
        if context['is_vip']:
            return "VIP customer - maintain relationship"
        
        return "Due for follow-up"
    
    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API to generate message"""
        
        url = f"{GEMINI_API_URL}?key={self.api_key}"
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 150,
                "topP": 0.8,
                "topK": 40
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract generated text
            if 'candidates' in data and len(data['candidates']) > 0:
                candidate = data['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    text = candidate['content']['parts'][0]['text']
                    return text.strip()
            
            raise Exception("No content in Gemini response")


# Singleton instance
_drafter_instance = None

def get_drafter() -> AIMessageDrafter:
    """Get singleton instance of AIMessageDrafter"""
    global _drafter_instance
    if _drafter_instance is None:
        _drafter_instance = AIMessageDrafter()
    return _drafter_instance
