"""
AI Message Drafter Service
Generates personalized follow-up messages using OpenAI API
"""
import os
import logging
from typing import List, Dict
from datetime import datetime
from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

class AIMessageDrafter:
    """Service for drafting personalized follow-up messages using AI"""
    
    def __init__(self, api_key: str = None):
        raw_key = api_key or os.environ.get('OPENAI_API_KEY')
        # Sanitize API key to avoid issues with accidental newlines/spaces from copy-paste
        self.api_key = (raw_key or '').strip().replace('\r', '').replace('\n', '').replace(' ', '')
        if not self.api_key or self.api_key == 'your_openai_api_key_here':
            logger.warning("OPENAI_API_KEY not set - using mock mode")
            logger.warning("To fix: Set OPENAI_API_KEY in backend/.env file")
            self.client = None
            self.mock_mode = True
        else:
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.model_name = 'gpt-4o-mini'
                self.mock_mode = False
                logger.info(f"✓ OpenAI client initialized successfully (key ends: ...{self.api_key[-10:]})")
            except Exception as e:
                logger.error(f"❌ Failed to configure OpenAI client: {e}")
                logger.error(f"   API key ends with: ...{self.api_key[-10:]}")
                logger.error(f"   Check if key is valid at: https://platform.openai.com/account/api-keys")
                self.client = None
                self.mock_mode = True
    
    async def draft_followup_message(
        self,
        customer_name: str,
        customer_data: Dict,
        messages: List[Dict],
        business_name: str = "Your Business",
        tone: str = "friendly",
        business_knowledge: str = None,
        user_id: str = None,
        db = None
    ) -> Dict[str, any]:
        """
        Draft a personalized follow-up message for a customer using learned user writing style
        """
        if not self.api_key or not self.client:
            return {
                "drafted_message": f"Hi {customer_name}, just checking in! How can we help you today?",
                "confidence": 0.5,
                "ai_reason": "Default message (AI not configured)"
            }
        
        # Build context from customer data
        context = self._build_customer_context(customer_name, customer_data, messages)
        
        # Learn user's writing style if user_id and db are provided
        user_style = {"style": tone, "patterns": []}
        if user_id and db:
            user_style = await self._analyze_user_writing_style(user_id, db)
            # Override tone with learned style
            tone = user_style["style"]
        
        # Create AI prompt with personalized style
        prompt = self._create_personalized_prompt(context, business_name, tone, business_knowledge, user_style)
        
        # Call OpenAI API
        try:
            drafted_message = await self._call_openai(prompt)
            return {
                "drafted_message": drafted_message,
                "confidence": 0.85,
                "ai_reason": self._extract_reason(context)
            }
        except Exception as e:
            logger.error(f"AI drafting failed: {e}")
            return {
                "drafted_message": f"Hi {customer_name}, hope you're doing well! Just wanted to check in and see if there's anything we can help you with.",
                "confidence": 0.5,
                "ai_reason": f"Fallback message (AI error: {str(e)[:50]})"
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
                try:
                    last_contacted = datetime.fromisoformat(last_contacted.replace('Z', '+00:00'))
                except ValueError:
                    pass # Keep as None if parsing fails
            if isinstance(last_contacted, datetime):
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
        """Create prompt for OpenAI with business knowledge and language detection"""
        
        # Build context description
        context_parts = []
        
        if context['days_since_contact'] is not None:
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
    
    def _create_personalized_prompt(self, context: Dict, business_name: str, tone: str, business_knowledge: str = None, user_style: Dict = None) -> str:
        """Create personalized prompt using learned user writing style"""
        
        # Start with the base prompt
        base_prompt = self._create_prompt(context, business_name, tone, business_knowledge)
        
        # If we have user style information, enhance the prompt
        if user_style and user_style.get("patterns"):
            patterns = user_style["patterns"]
            
            # Add style-specific instructions
            style_instructions = []
            
            if patterns.get("uses_emojis"):
                style_instructions.append("- Use 1-2 emojis naturally (like the business owner usually does)")
            
            if patterns.get("uses_swahili"):
                style_instructions.append("- Mix English and Swahili naturally (Sheng style)")
            
            if patterns.get("avg_length", 0) < 10:
                style_instructions.append("- Keep it very brief (under 10 words if possible)")
            elif patterns.get("avg_length", 0) > 20:
                style_instructions.append("- You can be a bit more detailed than usual")
            
            if patterns.get("common_greetings"):
                greeting_examples = list(set(patterns["common_greetings"]))[:2]
                style_instructions.append(f"- Start with greetings like: {', '.join(greeting_examples)}")
            
            if patterns.get("common_closings"):
                closing_examples = list(set(patterns["common_closings"]))[:2]
                style_instructions.append(f"- End with closings like: {', '.join(closing_examples)}")
            
            # Add style instructions to the prompt
            if style_instructions:
                style_section = "\n\nPERSONALIZED STYLE (match the business owner's usual writing):\n" + "\n".join(style_instructions)
                base_prompt = base_prompt + style_section
        
        return base_prompt
    
    async def _analyze_user_writing_style(self, user_id: str, db) -> Dict:
        """Analyze user's writing style from their outgoing messages"""
        try:
            # Get recent outgoing messages from this user
            outgoing_messages = await db.messages.find({
                "user_id": user_id,
                "direction": "outgoing"
            }).sort("created_at", -1).limit(20).to_list(20)
            
            if not outgoing_messages:
                return {"style": "friendly", "patterns": []}
            
            # Extract message content
            message_texts = [msg.get("content", "") for msg in outgoing_messages if msg.get("content")]
            
            if not message_texts:
                return {"style": "friendly", "patterns": []}
            
            # Analyze patterns
            combined_text = " ".join(message_texts)
            
            patterns = {
                "avg_length": sum(len(msg.split()) for msg in message_texts) / len(message_texts),
                "uses_emojis": "😊" in combined_text or "😄" in combined_text or "👍" in combined_text,
                "uses_swahili": any(word in combined_text.lower() for word in ["habari", "sawa", "asante", "bei", "vipi", "poa"]),
                "formal_tone": any(phrase in combined_text.lower() for phrase in ["dear", "thank you", "please", "kindly"]),
                "casual_tone": any(phrase in combined_text.lower() for phrase in ["hey", "hi", "what's up", "how are you"]),
                "uses_questions": "?" in combined_text,
                "uses_exclamations": "!" in combined_text,
                "common_greetings": [],
                "common_closings": []
            }
            
            # Extract common greetings and closings
            for msg in message_texts:
                words = msg.split()
                if len(words) > 0:
                    first_words = " ".join(words[:3]).lower()
                    if any(greeting in first_words for greeting in ["hi", "hello", "hey", "habari", "mambo"]):
                        patterns["common_greetings"].append(first_words)
                
                if len(words) > 2:
                    last_words = " ".join(words[-3:]).lower()
                    if any(closing in last_words for closing in ["thanks", "asante", "regards", "cheers"]):
                        patterns["common_closings"].append(last_words)
            
            # Determine overall style
            if patterns["formal_tone"] and not patterns["casual_tone"]:
                style = "professional"
            elif patterns["casual_tone"] and patterns["uses_emojis"]:
                style = "casual"
            else:
                style = "friendly"
            
            return {"style": style, "patterns": patterns}
            
        except Exception as e:
            logger.error(f"Error analyzing user writing style: {e}")
            return {"style": "friendly", "patterns": []}

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
    
    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API to generate message"""
        if not self.client:
            raise Exception("OpenAI client not initialized")
            
        try:
            import asyncio
            # Run synchronous OpenAI call in thread pool
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=150,
                top_p=0.8
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise Exception(f"OpenAI API error: {str(e)}")


    async def analyze_conversation_for_notes(
        self,
        messages: List[Dict]
    ) -> str:
        """
        Analyze conversation to generate CRM notes
        """
        if not self.api_key or not self.client:
            return "Unable to generate notes (AI unavailable)"
            
        try:
            # Prepare conversation text
            conversation_text = ""
            for msg in messages[-30:]:
                direction = "Customer" if msg.get("direction") == "incoming" else "Business"
                conversation_text += f"{direction}: {msg.get('content', '')}\n"
            
            prompt = f"""Analyze this WhatsApp business conversation and extract key information as CRM notes.

CONVERSATION:
{conversation_text}

Create brief, useful CRM notes that include:
- What products/services the customer is interested in
- Any specific requirements or preferences mentioned
- Price points discussed
- Any commitments or next steps agreed
- Customer's tone/attitude

Keep it concise (max 3-4 bullet points). Use simple language."""

            import asyncio
            # Run synchronous OpenAI call in thread pool
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200,
                top_p=0.8
            )
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Notes generation failed: {e}")
            return "Error generating notes"

# Singleton instance
_drafter_instance = None
_cached_api_key = None

def get_drafter() -> AIMessageDrafter:
    """Get singleton instance of AIMessageDrafter"""
    global _drafter_instance, _cached_api_key
    current_key = os.environ.get('OPENAI_API_KEY', '')
    
    # Recreate instance if key changed or instance doesn't exist
    if _drafter_instance is None or _cached_api_key != current_key:
        logger.info(f"Creating new AIMessageDrafter instance (key changed: {_cached_api_key != current_key})")
        _drafter_instance = AIMessageDrafter()
        _cached_api_key = current_key
    
    return _drafter_instance
