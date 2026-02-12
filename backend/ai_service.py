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

# Map phone prefixes to country and common languages
PHONE_PREFIX_LANGUAGES = {
    '+254': {'country': 'Kenya', 'languages': ['English', 'Swahili (Kiswahili)', 'Sheng']},
    '+255': {'country': 'Tanzania', 'languages': ['Swahili', 'English']},
    '+256': {'country': 'Uganda', 'languages': ['English', 'Luganda', 'Swahili']},
    '+251': {'country': 'Ethiopia', 'languages': ['Amharic', 'English', 'Oromo']},
    '+234': {'country': 'Nigeria', 'languages': ['English', 'Pidgin English', 'Yoruba', 'Igbo', 'Hausa']},
    '+233': {'country': 'Ghana', 'languages': ['English', 'Twi', 'Pidgin English']},
    '+27': {'country': 'South Africa', 'languages': ['English', 'Zulu', 'Afrikaans', 'Xhosa']},
    '+237': {'country': 'Cameroon', 'languages': ['French', 'English', 'Pidgin English']},
    '+225': {'country': 'Ivory Coast', 'languages': ['French', 'Dioula']},
    '+221': {'country': 'Senegal', 'languages': ['French', 'Wolof']},
    '+243': {'country': 'DR Congo', 'languages': ['French', 'Lingala', 'Swahili']},
    '+250': {'country': 'Rwanda', 'languages': ['Kinyarwanda', 'English', 'French']},
    '+257': {'country': 'Burundi', 'languages': ['Kirundi', 'French']},
    '+252': {'country': 'Somalia', 'languages': ['Somali', 'Arabic', 'English']},
    '+91': {'country': 'India', 'languages': ['Hindi', 'English', 'Tamil', 'Telugu', 'Bengali']},
    '+92': {'country': 'Pakistan', 'languages': ['Urdu', 'English', 'Punjabi']},
    '+880': {'country': 'Bangladesh', 'languages': ['Bengali', 'English']},
    '+63': {'country': 'Philippines', 'languages': ['Filipino/Tagalog', 'English']},
    '+62': {'country': 'Indonesia', 'languages': ['Bahasa Indonesia', 'English']},
    '+60': {'country': 'Malaysia', 'languages': ['Malay', 'English', 'Mandarin']},
    '+66': {'country': 'Thailand', 'languages': ['Thai', 'English']},
    '+84': {'country': 'Vietnam', 'languages': ['Vietnamese', 'English']},
    '+86': {'country': 'China', 'languages': ['Mandarin Chinese', 'English']},
    '+81': {'country': 'Japan', 'languages': ['Japanese', 'English']},
    '+82': {'country': 'South Korea', 'languages': ['Korean', 'English']},
    '+971': {'country': 'UAE', 'languages': ['Arabic', 'English']},
    '+966': {'country': 'Saudi Arabia', 'languages': ['Arabic', 'English']},
    '+20': {'country': 'Egypt', 'languages': ['Arabic', 'English']},
    '+212': {'country': 'Morocco', 'languages': ['Arabic', 'French', 'Darija']},
    '+216': {'country': 'Tunisia', 'languages': ['Arabic', 'French']},
    '+1': {'country': 'USA/Canada', 'languages': ['English', 'Spanish', 'French']},
    '+44': {'country': 'UK', 'languages': ['English']},
    '+33': {'country': 'France', 'languages': ['French', 'English']},
    '+49': {'country': 'Germany', 'languages': ['German', 'English']},
    '+34': {'country': 'Spain', 'languages': ['Spanish', 'Catalan', 'English']},
    '+39': {'country': 'Italy', 'languages': ['Italian', 'English']},
    '+351': {'country': 'Portugal', 'languages': ['Portuguese', 'English']},
    '+55': {'country': 'Brazil', 'languages': ['Portuguese', 'English']},
    '+52': {'country': 'Mexico', 'languages': ['Spanish', 'English']},
    '+57': {'country': 'Colombia', 'languages': ['Spanish', 'English']},
    '+56': {'country': 'Chile', 'languages': ['Spanish', 'English']},
    '+54': {'country': 'Argentina', 'languages': ['Spanish', 'English']},
}

def detect_language_from_phone(phone: str) -> Dict:
    """Detect likely country and languages from phone number prefix"""
    if not phone:
        return {'country': None, 'languages': []}
    phone = phone.strip()
    # Try longest prefix first (4 digits, then 3, then 2)
    for length in [4, 3, 2]:
        prefix = phone[:length] if phone.startswith('+') else '+' + phone[:length-1]
        if prefix in PHONE_PREFIX_LANGUAGES:
            return PHONE_PREFIX_LANGUAGES[prefix]
    return {'country': None, 'languages': []}

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
        custom_instructions: str = None,
        user_id: str = None,
        db = None,
        customer_id: str = None,
        user_country: str = None,
        customer_phone: str = None
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
        
        # Load conversation memory for this customer
        conversation_memory = ""
        cid = customer_id or customer_data.get("_id", "")
        if db is not None and cid:
            mem_doc = await db.conversation_memory.find_one({"customer_id": cid})
            if mem_doc and mem_doc.get("summary"):
                conversation_memory = mem_doc["summary"]
                context['conversation_memory'] = conversation_memory
        
        # Learn user's writing style if user_id and db are provided
        user_style = {"style": tone, "patterns": []}
        if user_id and db is not None:
            user_style = await self._analyze_user_writing_style(user_id, db)
            # Override tone with learned style
            tone = user_style["style"]
        
        # Find similar past answers from other customers
        past_answers_context = ""
        incoming_msg = messages[-1].get("content", "") if messages and messages[-1].get("direction") == "incoming" else ""
        if user_id and db is not None and incoming_msg:
            past_answers_context = await self._find_similar_past_answers(user_id, incoming_msg, cid, db)
        
        # Detect customer language from phone number
        phone = customer_phone or customer_data.get('phone', '')
        customer_lang_info = detect_language_from_phone(phone)
        
        # Build language context string
        language_context = ""
        if customer_lang_info.get('country'):
            language_context += f"\nCustomer is from {customer_lang_info['country']}."
            language_context += f" Common languages: {', '.join(customer_lang_info['languages'])}."
        if user_country:
            language_context += f"\nBusiness is based in {user_country}."
        
        # Create AI prompt with personalized style
        prompt = self._create_personalized_prompt(context, business_name, tone, business_knowledge, user_style, custom_instructions, past_answers_context, language_context)
        
        # Call OpenAI API
        try:
            drafted_message = await self._call_openai(prompt)
            
            # Update conversation memory after successful reply
            if db is not None and cid and drafted_message:
                try:
                    await self._update_conversation_memory(
                        db, cid, customer_name, messages, drafted_message, incoming_msg
                    )
                except Exception as mem_err:
                    logger.debug(f"Conversation memory update failed (non-critical): {mem_err}")
            
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
        
        # Build full conversation history for AI context
        conversation_log = []
        last_outgoing_message = None
        for msg in messages:
            direction = msg.get('direction', 'incoming')
            content = msg.get('content', '').strip()
            if content:
                label = "Customer" if direction == "incoming" else "You"
                conversation_log.append(f"{label}: {content}")
                if direction == "outgoing":
                    last_outgoing_message = content
        
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
            'conversation_log': conversation_log,
            'last_outgoing_message': last_outgoing_message,
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
    
    async def _find_similar_past_answers(self, user_id: str, incoming_message: str, current_customer_id: str, db) -> str:
        """Find how the business owner previously answered similar questions from other customers"""
        if db is None or not incoming_message:
            return ""
        
        try:
            # Extract key words from the incoming message (skip very short/common words)
            # Skip past-answer search for very short messages (likely greetings/casual)
            if len(incoming_message.split()) <= 3:
                return ""
            stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'do', 'does', 'i', 'me', 'my', 'you', 'your', 'we', 'ok', 'yes', 'no', 'please', 'thanks', 'thank', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'how', 'what', 'when', 'where', 'who', 'which', 'can', 'will', 'have', 'has', 'had', 'this', 'that', 'it', 'be', 'been', 'am', 'not', 'so', 'if'}
            words = [w.lower().strip('?!.,') for w in incoming_message.split() if len(w) > 2]
            keywords = [w for w in words if w not in stop_words]
            
            if not keywords:
                return ""
            
            # Search for incoming messages from OTHER customers that contain similar keywords
            search_regex = "|".join(keywords[:5])  # Limit to 5 keywords
            similar_incoming = await db.messages.find({
                "user_id": user_id,
                "direction": "incoming",
                "customer_id": {"$ne": current_customer_id},
                "content": {"$regex": search_regex, "$options": "i"}
            }).sort("created_at", -1).limit(5).to_list(5)
            
            if not similar_incoming:
                return ""
            
            # For each similar incoming message, find the business owner's reply
            past_exchanges = []
            for msg in similar_incoming:
                # Find the next outgoing message to this customer after this incoming message
                reply = await db.messages.find_one({
                    "user_id": user_id,
                    "customer_id": msg["customer_id"],
                    "direction": "outgoing",
                    "created_at": {"$gt": msg["created_at"]}
                }, sort=[("created_at", 1)])
                
                if reply and reply.get("content"):
                    past_exchanges.append({
                        "question": msg.get("content", "")[:150],
                        "answer": reply.get("content", "")[:200]
                    })
            
            if not past_exchanges:
                return ""
            
            # Format as context for the AI
            lines = ["PAST SIMILAR CONVERSATIONS (how you answered similar questions from other customers):"]
            for i, ex in enumerate(past_exchanges[:3], 1):
                lines.append(f"  Customer asked: \"{ex['question']}\"")
                lines.append(f"  You replied: \"{ex['answer']}\"")
                lines.append("")
            
            lines.append("Use these past answers as reference for tone, pricing, and information accuracy. Stay consistent with how you've answered before.")
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Error finding similar past answers: {e}")
            return ""

    def _create_prompt(self, context: Dict, business_name: str, tone: str, business_knowledge: str = None) -> str:
        """Create prompt for OpenAI — clean, concise, AI-driven intent classification"""
        
        # Build context description
        context_parts = []
        
        if context['days_since_contact'] is not None:
            context_parts.append(f"Last contacted {context['days_since_contact']} days ago")
        
        if context['is_vip']:
            context_parts.append("VIP customer")
        elif context['is_new']:
            context_parts.append("New customer")
        
        if context['purchase_count'] > 0:
            context_parts.append(f"{context['purchase_count']} purchases ({context['total_spent']:.0f} total spent)")
        
        if context['notes']:
            context_parts.append(f"Notes: {context['notes'][:100]}")
        
        context_str = "\n- ".join(context_parts) if context_parts else "No prior context"
        
        # Tone instructions
        tone_instructions = {
            'professional': 'professional but warm',
            'friendly': 'warm and friendly',
            'casual': 'casual and conversational'
        }
        tone_desc = tone_instructions.get(tone, 'friendly')
        
        # Business knowledge section
        business_context = ""
        if business_knowledge:
            business_context = f"""
Business Information:
{business_knowledge}
"""
        
        # Format conversation history — limit to last 10 to reduce noise
        conversation_history = "(No previous messages)"
        if context.get('conversation_log'):
            conversation_history = "\n".join(context['conversation_log'][-10:])
        
        # Format conversation memory (long-term summary — stored in English)
        memory_section = ""
        if context.get('conversation_memory'):
            memory_section = f"""
Past interaction summary: {context['conversation_memory']}
"""
        
        # Add anti-repetition warning if we have a previous outgoing message
        repetition_warning = ""
        if context.get('last_outgoing_message'):
            last_msg = context['last_outgoing_message']
            # Extract first few words to identify the pattern
            first_words = ' '.join(last_msg.split()[:3])
            repetition_warning = f"\n⚠️ IMPORTANT: Your last reply started with '{first_words}' - DO NOT start with those same words again. Use completely different opening words."
        
        prompt = f"""You're {context['name']}'s business contact at {business_name}. You're texting them back on WhatsApp.

Context: {context_str}
{business_context}{memory_section}
Recent chat:
{conversation_history}
{repetition_warning}

Reply to their message naturally. Real people don't greet every single message:

ONLY greet if they ACTUALLY greeted you first (hi/hello/good morning/habari/sasa/hey/etc). If they greeted, vary your response (Morning/Hey/Sasa/Vipi/Yo/Sup).

For everything else, just respond directly:
- "Yes"/"OK" → Move forward (NO greeting, just continue)
- "I have send" → Acknowledge it (NO greeting, just confirm)
- Questions → Answer directly (NO greeting needed)
- Statements → Respond to what they said (NO greeting)

Rules:
- Match their language exactly (English, Swahili, mix)
- 1-3 sentences max
- NEVER start two messages in a row with the same words
- Don't add greetings where they don't belong

Tone: {tone_desc}

Reply:"""

        return prompt
    
    def _create_personalized_prompt(self, context: Dict, business_name: str, tone: str, business_knowledge: str = None, user_style: Dict = None, custom_instructions: str = None, past_answers_context: str = None, language_context: str = None) -> str:
        """Create personalized prompt using learned user writing style and custom instructions"""
        
        # Start with the base prompt
        base_prompt = self._create_prompt(context, business_name, tone, business_knowledge)
        
        # Add language awareness context (keep it minimal — the model handles language well)
        if language_context:
            lang_section = f"\n\nCustomer context:{language_context}\nMirror the customer's language and style exactly. If they mix languages, you mix too. Do not correct or translate."
            base_prompt = base_prompt + lang_section
        
        # Add past similar answers context
        if past_answers_context:
            base_prompt = base_prompt + f"\n\n{past_answers_context}"
        
        # If we have custom instructions, add them (but never override conversation progression rules)
        if custom_instructions:
            custom_section = f"\n\nADDITIONAL CONTEXT:\n{custom_instructions}\nIMPORTANT: Step 1 (classify intent) ALWAYS takes top priority. Only use the order flow if the customer is actively buying. For greetings and casual messages, just be natural."
            base_prompt = base_prompt + custom_section
        
        # If we have user style information, enhance the prompt
        if user_style and user_style.get("patterns"):
            patterns = user_style["patterns"]
            
            # Add style-specific instructions
            style_instructions = []
            
            if patterns.get("uses_emojis"):
                style_instructions.append("- Use 1-2 emojis naturally (like the business owner usually does)")
            
            if patterns.get("uses_local_language"):
                style_instructions.append("- Mix languages naturally as the business owner usually does")
            
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
                "uses_local_language": len(set(combined_text.lower().split()) - set('the a an is are was do does i me my you your we ok yes no please thanks thank and or but in on at to for of with how what when where who which can will have has had this that it be been am not so if'.split())) > len(combined_text.lower().split()) * 0.3,
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
            
            # Split prompt into system instructions and conversation context
            # Everything before "Recent chat:" is system-level, the rest is user context
            separator = 'Recent chat:'
            if separator in prompt:
                parts = prompt.split(separator, 1)
                system_msg = parts[0].strip()
                # The conversation history goes as user message
                user_msg = separator + parts[1]
                messages = [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ]
            else:
                messages = [
                    {"role": "user", "content": prompt}
                ]
            
            # Run synchronous OpenAI call in thread pool
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=150,
                top_p=0.9
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise Exception(f"OpenAI API error: {str(e)}")


    async def draft_broadcast_message(self, prompt: str, business_type: str = None) -> str:
        """Draft a broadcast message based on a prompt"""
        if not self.api_key or not self.client:
            return "AI Unavailable: Please set OPENAI_API_KEY in environment"

        # Build system prompt for WhatsApp-compliant messages
        system_prompt = """You are a marketing message generator for small businesses. 
Generate engaging WhatsApp-compliant promotional messages.

Rules:
1. Keep messages under 160 characters when possible
2. Use emojis sparingly (1-2 max)
3. Include a clear call-to-action
4. Be friendly and conversational
5. Follow WhatsApp Business API guidelines
6. You can use {{name}} to personalize with customer name
7. Make it suitable for SMS/WhatsApp broadcast

Format: Just return the message text, nothing else."""

        if business_type:
            system_prompt += f"\n\nBusiness type: {business_type}"
            
        full_prompt = f"{system_prompt}\n\nUser request: {prompt}"
        
        try:
            return await self._call_openai(full_prompt)
        except Exception as e:
            logger.error(f"Broadcast drafting failed: {e}")
            return f"Error drafting message: {str(e)}"


    async def _update_conversation_memory(self, db, customer_id: str, customer_name: str, messages: List[Dict], last_reply: str, last_incoming: str):
        """Update conversation memory/summary for a customer after each auto-reply.
        Stores a running summary so the AI always knows what was discussed."""
        try:
            # Build recent conversation snippet (last 10 messages + our new reply)
            recent = messages[-10:] if len(messages) > 10 else messages
            convo_text = ""
            for m in recent:
                label = "Customer" if m.get("direction") == "incoming" else "Business"
                convo_text += f"{label}: {m.get('content', '')}\n"
            convo_text += f"Business: {last_reply}\n"
            
            # Load existing memory
            existing = await db.conversation_memory.find_one({"customer_id": customer_id})
            old_summary = existing.get("summary", "") if existing else ""
            
            # Generate updated summary using AI — always in English for system use
            summary_prompt = f"""You are a CRM memory system. Update the conversation summary for customer "{customer_name}".

EXISTING MEMORY:
{old_summary if old_summary else "(None)"}

RECENT CONVERSATION:
{convo_text}

Write a concise updated summary (max 5 bullet points) covering:
- Products/services discussed and prices quoted
- Decisions made or orders placed
- Customer preferences or requirements
- Current conversation status (what's pending?)

IMPORTANT: Always write the summary in ENGLISH, even if the conversation was in another language. This is internal system data, not customer-facing.
Write ONLY the bullet points."""

            import asyncio
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model_name,
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            new_summary = response.choices[0].message.content.strip()
            
            # Upsert the memory
            await db.conversation_memory.update_one(
                {"customer_id": customer_id},
                {"$set": {
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "summary": new_summary,
                    "updated_at": datetime.utcnow(),
                    "message_count": len(messages) + 1,
                }},
                upsert=True
            )
            logger.info(f"Updated conversation memory for customer {customer_id}")
        except Exception as e:
            logger.debug(f"Memory update error (non-critical): {e}")

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
