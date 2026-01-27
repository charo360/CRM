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
        tone: str = "friendly",
        business_knowledge: str = None
    ) -> Dict[str, any]:
        """
        Draft a personalized follow-up message for a customer
        
        Args:
            customer_name: Name of the customer
            customer_data: Customer info (tags, notes, purchase history)
            messages: List of recent messages with the customer
            business_name: Name of the business
            tone: Message tone (professional, friendly, casual)
            business_knowledge: Business context (products, services, FAQs)
        
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
        prompt = self._create_prompt(context, business_name, tone, business_knowledge)
        
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
    
    def _create_prompt(self, context: Dict, business_name: str, tone: str, business_knowledge: str = None) -> str:
        """Create prompt for Gemini AI with business knowledge and language detection"""
        
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
        
        # Detect language from last message
        language_hint = ""
        if context['last_message']:
            msg = context['last_message'].lower()
            # Check for Swahili keywords
            swahili_words = ['habari', 'sawa', 'asante', 'tafadhali', 'bei', 'ngapi', 'nini', 'vipi', 'poa', 'mambo']
            if any(word in msg for word in swahili_words):
                language_hint = "\n- Customer seems to prefer Swahili - respond in Swahili if you're confident"
            else:
                language_hint = "\n- Respond in the same language as the customer (English or Swahili)"
        
        # Tone instructions
        tone_instructions = {
            'professional': 'professional but warm, like a trusted business advisor',
            'friendly': 'warm and friendly, like talking to a regular customer you know well',
            'casual': 'casual and conversational, like chatting with a friend'
        }
        tone_desc = tone_instructions.get(tone, 'friendly')
        
        # Business knowledge section
        business_context = ""
        if business_knowledge:
            business_context = f"""
Business Information:
{business_knowledge}

Use this information to answer questions and provide relevant details about products/services.
"""
        
        prompt = f"""You are the owner of {business_name}, a Kenyan business. You're reaching out to your customer {context['name']} via WhatsApp.

Customer Context:
- {context_str}{language_hint}

{business_context}

CRITICAL INSTRUCTIONS:
1. Write as if YOU are the business owner - use "I" and "we", be personal
2. Sound NATURAL - like you're texting a customer, not writing a formal email
3. Be BRIEF - 1-3 sentences maximum (WhatsApp style)
4. Reference their last interaction if relevant
5. If they asked a question, ANSWER it directly
6. Detect the language they used and respond in the SAME language
7. For Swahili, use natural Kenyan Swahili (mix with English is fine - "Sheng")
8. Be {tone_desc}
9. Include a clear next step or question
10. NO emojis unless it fits naturally (max 1-2)
11. If you don't have enough information to answer their question, say you'll check and get back to them

Examples of GOOD messages:
- "Hi John! Saw you were asking about the price last week. It's KES 2,500. Still interested?"
- "Habari Mary! That product is back in stock. Unataka nikudelivery?"
- "Hey! Been a while 😊 We have a new offer - 20% off this week. Want details?"

Examples of BAD messages (too formal/generic):
- "Dear valued customer, we hope this message finds you well..."
- "Thank you for your interest in our products and services..."
- "We would like to follow up on your previous inquiry..."

Write ONLY the message text. No quotes, no explanations, no subject lines."""

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
