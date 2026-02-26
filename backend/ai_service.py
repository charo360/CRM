"""
AI Message Drafter Service
Generates personalized follow-up messages using OpenAI API
"""
import os
import re
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
        # Default provider config (can be overridden per request)
        self.provider = os.environ.get('AI_PROVIDER', 'openai').strip().lower()
        self.api_key = api_key
        
        # Initialize clients map
        self.clients = {}
        self._init_clients()
        self._validate_provider()

    def _init_clients(self):
        """Initialize available AI clients based on env vars"""
        import httpx
        
        # 1. OpenAI (Default)
        openai_key = self.api_key or os.environ.get('OPENAI_API_KEY')
        if openai_key and openai_key not in ('your_openai_api_key_here',):
            try:
                self.clients['openai'] = OpenAI(api_key=openai_key)
                logging.info("[OK] OpenAI client initialized")
            except Exception as e:
                logging.error(f"[FAIL] OpenAI init failed: {e}")
        else:
            logging.warning("[WARN] OpenAI key not found or placeholder")
        
        # 2. DeepSeek
        ds_key = os.environ.get('DEEPSEEK_API_KEY')
        if ds_key and ds_key not in ('your_deepseek_api_key_here',):
            try:
                self.clients['deepseek'] = OpenAI(
                    api_key=ds_key, 
                    base_url='https://api.deepseek.com'
                )
                logging.info("[OK] DeepSeek client initialized")
            except Exception as e:
                logging.error(f"[FAIL] DeepSeek init failed: {e}")

        # 3. Grok (xAI) - Uses OpenAI client compatibility
        grok_key = os.environ.get('XS_API_KEY') or os.environ.get('GROK_API_KEY')
        if grok_key:
            try:
                self.clients['grok'] = OpenAI(
                    api_key=grok_key,
                    base_url='https://api.x.ai/v1'
                )
                logging.info("[OK] Grok client initialized")
            except Exception as e:
                logging.error(f"[FAIL] Grok init failed: {e}")
        
        # 4. Claude (Anthropic) - Uses raw HTTP to avoid new dependency
        claude_key = os.environ.get('ANTHROPIC_API_KEY')
        if claude_key:
            self.clients['claude'] = {
                'key': claude_key,
                'endpoint': 'https://api.anthropic.com/v1/messages'
            }
            logging.info("[OK] Claude client configured")

    def _validate_provider(self):
        """Warn loudly if the configured AI provider isn't available"""
        if not self.clients:
            logging.error("=" * 60)
            logging.error("[CRITICAL] NO AI PROVIDERS INITIALIZED - AI replies will NOT work!")
            logging.error("Check your .env file for API keys (OPENAI_API_KEY, DEEPSEEK_API_KEY, etc)")
            logging.error("=" * 60)
            return
        
        if self.provider not in self.clients:
            available = list(self.clients.keys())
            logging.warning(f"[WARN] AI_PROVIDER={self.provider} but that client failed to init. Falling back to: {available[0]}")
            logging.warning(f"[WARN] Check your .env - is the API key for '{self.provider}' correct?")
        else:
            logging.info(f"[OK] AI ready: provider={self.provider}, all clients={list(self.clients.keys())}")

    def get_status(self) -> dict:
        """Return AI provider status for health checks"""
        default_type, default_model, default_client = self._get_default_client_and_model()
        return {
            "configured_provider": self.provider,
            "active_provider": default_type,
            "active_model": default_model,
            "available_clients": list(self.clients.keys()),
            "ready": bool(self.clients),
        }

    async def self_test(self) -> dict:
        """Make a real AI call to verify the service works end-to-end"""
        try:
            result = await self._call_llm("Reply with exactly: OK", "standard")
            return {"status": "ok", "response": result.strip()[:50]}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _get_default_client_and_model(self):
        """Get the default client based on configured provider, with fallback to any available client"""
        # Provider-specific defaults
        provider_defaults = {
            'deepseek': ('deepseek', 'deepseek-chat'),
            'openai': ('openai', 'gpt-4o-mini'),
            'grok': ('grok', 'grok-4'),
            'claude': ('claude', 'claude-3-5-sonnet-latest'),
        }
        
        # Try configured provider first
        if self.provider in provider_defaults and self.provider in self.clients:
            ct, mn = provider_defaults[self.provider]
            return ct, mn, self.clients[ct]
        
        # Fallback: pick the first available client (cheapest first)
        fallback_order = ['openai', 'deepseek', 'grok', 'claude']
        for fb in fallback_order:
            if fb in self.clients:
                ct, mn = provider_defaults.get(fb, (fb, 'unknown'))
                return ct, mn, self.clients[fb]
        
        return 'openai', 'gpt-4o-mini', None

    def _get_client_and_model(self, model_pref: str = None):
        """Determine which client and model name to use based on preference"""
        if not model_pref:
            model_pref = 'standard'
            
        model_pref = model_pref.lower()
        
        if model_pref in ('premium', 'gpt-4o'):
            client_type = 'openai'
            model_name = 'gpt-4o'
        elif model_pref == 'gpt-5':
            client_type = 'openai'
            model_name = 'gpt-5'
        elif 'claude' in model_pref or 'sonnet' in model_pref:
            client_type = 'claude'
            if '4.5' in model_pref or 'sonnet-4.5' == model_pref:
                model_name = 'claude-sonnet-4-5-20250929'
            else:
                model_name = 'claude-3-5-sonnet-latest'
        elif 'grok' in model_pref:
            client_type = 'grok'
            model_name = 'grok-4' 
        elif 'deepseek' in model_pref:
            client_type = 'deepseek'
            model_name = 'deepseek-chat'
        else:
            # Standard/Default — use configured provider
            return self._get_default_client_and_model()
        
        # If the requested client isn't available, fall back to default
        client = self.clients.get(client_type)
        if not client:
            logging.warning(f"Provider {client_type} not configured, falling back to default")
            return self._get_default_client_and_model()
            
        return client_type, model_name, client

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
        customer_phone: str = None,
        model_pref: str = 'standard'
    ) -> Dict[str, any]:
        """
        Draft a personalized follow-up message for a customer using learned user writing style
        """
        if not self.clients:
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
            mem_query = {"customer_id": cid}
            if user_id:
                mem_query["user_id"] = user_id
            mem_doc = await db.conversation_memory.find_one(mem_query)
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
        
        # Call LLM Provider
        try:
            print(f"DEBUG: Calling LLM ({model_pref}) now with prompt len={len(prompt)}")
            drafted_message = await self._call_llm(prompt, model_pref)
            print(f"DEBUG: API call successful. Response len={len(drafted_message)}")
            
            # Update conversation memory after successful reply
            if db is not None and cid and drafted_message:
                try:
                    await self._update_conversation_memory(
                        db, cid, customer_name, messages, drafted_message, incoming_msg, user_id=user_id
                    )
                except Exception as mem_err:
                    logger.debug(f"Conversation memory update failed (non-critical): {mem_err}")
            
            return {
                "drafted_message": drafted_message,
                "confidence": 0.85,
                "ai_reason": self._extract_reason(context)
            }
        except Exception as e:
            print(f"CRITICAL AI ERROR: {e}") # Direct print to bypass logging error
            import traceback
            traceback.print_exc()
            logger.error(f"AI drafting failed: {e}")
            # Return None to indicate failure - webhook should NOT send auto-reply
            return {
                "drafted_message": None,
                "confidence": 0.0,
                "ai_reason": f"AI service failed: {str(e)[:100]}"
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
        """Learn business patterns from past answers (pricing, product info, tone).
        Extracts anonymized guidelines — never injects raw conversations or customer details.
        The output trains the model on HOW the business owner responds, not WHAT other customers said."""
        if db is None or not incoming_message:
            return ""
        
        try:
            # Only activate for substantive messages (skip greetings/casual)
            if len(incoming_message.split()) <= 3:
                return ""
            
            stop_words = {
                'the', 'a', 'an', 'is', 'are', 'was', 'do', 'does', 'i', 'me',
                'my', 'you', 'your', 'we', 'ok', 'yes', 'no', 'please', 'thanks',
                'thank', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
                'with', 'how', 'what', 'when', 'where', 'who', 'which', 'can',
                'will', 'have', 'has', 'had', 'this', 'that', 'it', 'be', 'been',
                'am', 'not', 'so', 'if', 'hi', 'hello', 'hey', 'habari', 'mambo',
                'sawa', 'poa', 'ndiyo', 'hapana',
            }
            words = [w.lower().strip('?!.,') for w in incoming_message.split() if len(w) > 2]
            keywords = [w for w in words if w not in stop_words]
            
            if not keywords:
                return ""
            
            # Search for the business owner's past OUTGOING replies that contain
            # similar keywords — we only look at what the OWNER said, not customers
            search_regex = "|".join(keywords[:5])
            past_replies = await db.messages.find({
                "user_id": user_id,
                "direction": "outgoing",
                "customer_id": {"$ne": current_customer_id},
                "content": {"$regex": search_regex, "$options": "i"}
            }).sort("created_at", -1).limit(10).to_list(10)
            
            if not past_replies:
                return ""
            
            # Extract ONLY business patterns — no customer names or personal info
            prices_quoted = []
            product_mentions = []
            reply_lengths = []
            
            price_pattern = re.compile(r'(\d[\d,]*\.?\d*)\s*(ksh|kes|usd|\$|shillings?)?', re.IGNORECASE)
            
            for reply in past_replies:
                content = reply.get("content", "")
                if not content:
                    continue
                
                reply_lengths.append(len(content.split()))
                
                # Extract prices mentioned
                for match in price_pattern.finditer(content):
                    price_str = match.group(0).strip()
                    if len(price_str) > 2:  # Skip single digits
                        prices_quoted.append(price_str)
            
            # Build anonymized business guidelines
            guidelines = []
            
            if prices_quoted:
                unique_prices = list(set(prices_quoted))[:5]
                guidelines.append(f"Prices you've quoted before: {', '.join(unique_prices)}")
            
            if reply_lengths:
                avg_len = sum(reply_lengths) / len(reply_lengths)
                if avg_len < 15:
                    guidelines.append("You typically give short, direct answers to these types of questions.")
                elif avg_len > 40:
                    guidelines.append("You typically give detailed explanations for these types of questions.")
            
            if not guidelines:
                return ""
            
            return "YOUR PAST BUSINESS PATTERNS (stay consistent):\n- " + "\n- ".join(guidelines)
            
        except Exception as e:
            logger.error(f"Error extracting business patterns: {e}")
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
            first_words = ' '.join(last_msg.split()[:3])
            repetition_warning = f"\n⚠️ IMPORTANT: Your last reply started with '{first_words}' - DO NOT start with those same words again. Use completely different opening words."
        
        # If there are multiple messages, this is mid-conversation — no greetings
        if context.get('conversation_log') and len(context['conversation_log']) > 2:
            repetition_warning += "\n⚠️ This is a mid-conversation reply. Do NOT open with any greeting (Hey, Hi, Hello, etc). Get straight to the point."
        
        prompt = f"""You are the person behind {business_name}, chatting with {context['name']} on WhatsApp. Write like a real human — not a bot, not a customer service agent. Think of how you'd actually text a customer you know.

Context: {context_str}
{business_context}{memory_section}
Recent chat:
{conversation_history}
{repetition_warning}

STEP 1 — What is the customer talking about RIGHT NOW?
Read their LAST message carefully. That is what you are replying to. The chat history above is just background — if the customer changed topic, you change with them. Do NOT continue an old topic if they moved on.
- If they were asking about shoes and now ask about laptops → answer about laptops. Forget the shoes.
- If they were negotiating a price and now say "hi" → treat it as a fresh greeting.
- If their message IS a direct follow-up to the previous topic (e.g. "ok send it", "how much?", "yes") → continue that topic naturally.
- When in doubt, answer exactly what their last message says. Nothing more.

STEP 2 — How to reply:
- Text like a real person. Short, natural, no filler. No "I'd be happy to help" or "Feel free to ask" type phrases.
- NEVER start with "Hey", "Hi", "Hello", or any greeting if the conversation already has messages above. Only greet if this is the very first message OR they just greeted you. Mid-conversation, jump straight into your answer.
- Reply in whatever language the customer used. If they wrote in English, reply in English. If Swahili, reply in Swahili. If they mix (e.g. "niaje, do you have laptops?"), you mix too within the SAME sentence — that's how real people text. NEVER translate: don't say something in English then repeat it in another language below. One message, one natural flow.
- Only use an emoji when it genuinely adds something (e.g. confirming an order ✅, or something exciting 🔥). Most normal replies do NOT need emojis. If the message is just answering a simple question, skip the emoji entirely. Never force emojis.
- Keep it 1-3 sentences. Don't over-explain.
- NEVER repeat the same opening as your last message.
- Don't use phrases like "Sure thing!", "Absolutely!", "Of course!", "Great choice!" — those sound robotic.
- Be direct. If they ask a question, answer it. If they say yes, move forward. If they want to see something, show it.
- If a product catalog or business information is provided above, you ALREADY KNOW your products. Answer product questions directly from that catalog — give the name, price, availability. NEVER say "let me check", "I'll look into it", or "let me get back to you" when the answer is right there in your catalog. If the product isn't in your catalog, just say you don't have it.
- CRITICAL: ONLY use information from the chat history and business information shown above. NEVER invent facts, names, events, or personal details that are not provided. If you don't know something, say so honestly.
- If the customer asks something you genuinely CANNOT answer from the business information or chat history (e.g. specific pricing not in catalog, custom requests, complaints, technical questions you have no info on), start your reply with [NEEDS_HUMAN] then give a natural holding reply like "Let me confirm that for you" or "Give me a moment, I'll get back to you on that". Do NOT use [NEEDS_HUMAN] for general greetings, simple questions you CAN answer, or casual chat.

Tone: {tone_desc}

Reply:"""

        return prompt
    
    def _create_personalized_prompt(self, context: Dict, business_name: str, tone: str, business_knowledge: str = None, user_style: Dict = None, custom_instructions: str = None, past_answers_context: str = None, language_context: str = None) -> str:
        """Create personalized prompt using learned user writing style and custom instructions"""
        
        # Start with the base prompt
        base_prompt = self._create_prompt(context, business_name, tone, business_knowledge)
        
        # Add language awareness context
        if language_context:
            lang_section = f"\n\nCustomer context:{language_context}"
            lang_section += "\nLANGUAGE RULES:"
            lang_section += "\n- Reply in the SAME language the customer used. Do NOT translate or repeat in a second language."
            lang_section += "\n- If they mix languages, you can mix too — but within the SAME sentence, not as separate lines."
            lang_section += "\n- WRONG: 'It's in Nairobi, we deliver countrywide' then 'Iko Nairobi, tunadeliver countrywide' — this is translating, never do this."
            lang_section += "\n- RIGHT: 'Iko Nairobi but tunadeliver countrywide' — one natural sentence mixing both."
            lang_section += "\n- RIGHT: 'It's in Nairobi, we deliver countrywide' — pure English if they asked in English."
            lang_section += "\n- Match the customer's actual language choice, don't force a language they didn't use."
            base_prompt = base_prompt + lang_section
        
        # Add past similar answers context
        if past_answers_context:
            base_prompt = base_prompt + f"\n\n{past_answers_context}"
        
        # If we have custom instructions, treat them as a writing directive, not something to reply to
        if custom_instructions:
            custom_section = (
                f"\n\nWRITING DIRECTIVE (override default intent):\n"
                f"Ignore what the last message was about. Instead, write a message that: {custom_instructions}\n"
                f"Output ONLY the message text to send. Do NOT explain, do NOT answer the directive as a question, do NOT add commentary. Just write the message."
            )
            base_prompt = base_prompt + custom_section
        
        # If we have user style information, enhance the prompt
        if user_style and user_style.get("patterns"):
            patterns = user_style["patterns"]
            
            # Add style-specific instructions
            style_instructions = []
            
            if patterns.get("uses_emojis"):
                style_instructions.append("- The business owner sometimes uses emojis — only add one when it genuinely fits (e.g. ✅ for confirmations, 🔥 for something exciting). Skip emojis on plain answers.")
            
            if patterns.get("uses_local_language"):
                style_instructions.append("- Mix languages naturally as the business owner usually does")
            
            if patterns.get("avg_length", 0) < 10:
                style_instructions.append("- Keep it very brief (under 10 words if possible)")
            elif patterns.get("avg_length", 0) > 20:
                style_instructions.append("- You can be a bit more detailed than usual")
            
            # NOTE: common_greetings intentionally NOT injected here.
            # It was causing the AI to always open with "Hey!" even mid-conversation.
            # Greetings are handled by the base prompt rule: "Only greet if THEY greeted first."
            
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
                "uses_emojis": bool(re.search(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF\U0000200D\U00002764]', combined_text)),
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
    
    async def _call_llm(self, prompt: str, model_pref: str = 'standard') -> str:
        """Route the prompt to the correct LLM provider with fallback"""
        client_type, model_name, client = self._get_client_and_model(model_pref)
        
        # If client not configured, fallback to default provider
        if not client:
            logger.warning(f"Provider {client_type} not configured, falling back to default")
            client_type, model_name, client = self._get_default_client_and_model()
            
            if not client:
                error_msg = f"No AI Provider configured. Please add an API key (OPENAI_API_KEY, DEEPSEEK_API_KEY, etc)."
                logger.error(error_msg)
                raise Exception(error_msg)
            
        print(f"DEBUG: Routing to {client_type} (model: {model_name})...", flush=True)
        logging.info(f"DEBUG: Routing to {client_type} (model: {model_name})...")
        
        try:
            if client_type == 'claude':
                return await self._call_claude(client, model_name, prompt)
            else:
                # works for OpenAI, DeepSeek, Grok (all use OpenAI client)
                return await self._call_openai_compatible(client, model_name, prompt)
        except Exception as e:
            logger.error(f"Primary model {model_name} failed: {e}")
            print(f"ERROR: {model_name} failed, trying fallback...", flush=True)
            
            # Fallback to default provider (skip if already using it)
            fb_type, fb_model, fb_client = self._get_default_client_and_model()
            if fb_client and (fb_type != client_type or fb_model != model_name):
                logger.info(f"Falling back to {fb_type} ({fb_model})")
                if fb_type == 'claude':
                    return await self._call_claude(fb_client, fb_model, prompt)
                else:
                    return await self._call_openai_compatible(fb_client, fb_model, prompt)
            raise

    async def _call_openai_compatible(self, client: OpenAI, model_name: str, prompt: str) -> str:
        """Generic handler for OpenAI-compatible APIs (DeepSeek, Grok, OpenAI)"""
        try:
            import asyncio
            separator = 'Recent chat:'
            if separator in prompt:
                parts = prompt.split(separator, 1)
                system_msg = parts[0].strip()
                user_msg = separator + parts[1]
                messages = [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ]
            else:
                messages = [{"role": "user", "content": prompt}]
            
            # Grok 4 uses max_completion_tokens (reasoning model)
            # GPT-5 appears to reject both max_tokens and max_completion_tokens (manages own output?)
            is_grok_reasoning = model_name.startswith('grok-4')
            
            kwargs = {
                "model": model_name,
                "messages": messages,
            }
            
            if is_grok_reasoning:
                kwargs["max_completion_tokens"] = 400
            elif model_name.startswith('gpt-5'):
                # GPT-5: Do NOT send max_tokens or max_completion_tokens
                pass
            else:
                kwargs["max_tokens"] = 400
                kwargs["temperature"] = 0.7
            
            response = await asyncio.to_thread(
                client.chat.completions.create,
                **kwargs,
            )
            content = response.choices[0].message.content
            if not content:
                logger.warning(f"Empty content from {model_name}. Full response: {response}")
                return ""
            return content.strip()
        except Exception as e:
            logger.error(f"LLM Call Failed ({model_name}): {e}")
            raise e

    async def _call_claude(self, client_config: Dict, model_name: str, prompt: str) -> str:
        """Direct HTTP call to Anthropic API"""
        import httpx
        
        api_key = client_config['key']
        endpoint = client_config['endpoint']
        
        system_msg = "You are a helpful AI assistant for a business."
        user_msg = prompt
        
        separator = 'Recent chat:'
        if separator in prompt:
            parts = prompt.split(separator, 1)
            system_msg = parts[0].strip()
            user_msg = separator + parts[1]

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": model_name,
            "max_tokens": 400,
            "system": system_msg,
            "messages": [
                {"role": "user", "content": user_msg}
            ]
        }
        
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(endpoint, json=payload, headers=headers, timeout=30.0)
                
                if response.status_code != 200:
                    raise Exception(f"Claude API Error {response.status_code}: {response.text}")
                    
                data = response.json()
                # Claude response format: content[0].text
                return data['content'][0]['text']
        except Exception as e:
            logger.error(f"Claude Call Failed: {e}")
            raise e


    async def draft_broadcast_message(self, prompt: str, business_type: str = None) -> str:
        """Draft a broadcast message based on a prompt"""
        if not self.clients:
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
            return await self._call_llm(full_prompt, model_pref='standard')
        except Exception as e:
            logger.error(f"Broadcast drafting failed: {e}")
            return f"Error drafting message: {str(e)}"


    async def recommend_product_with_discount(
        self,
        customer_name: str,
        products: List[Dict],
        customer_message: str,
        business_name: str = "Your Business",
        user_id: str = None,
        db = None,
        customer_phone: str = None,
        model_pref: str = 'standard'
    ) -> Dict[str, any]:
        """
        Recommend products with smart discount negotiation
        Only mentions discounts when customer asks about them or tries to negotiate
        """
        if not self.clients:
            return {
                "message": f"Hi {customer_name}, I have several options available. Which would you like to know more about?",
                "mentions_discount": False,
                "confidence": 0.5
            }
        
        # Check if customer is asking about discounts or negotiating
        discount_keywords = ['discount', 'cheaper', 'lower price', 'deal', 'offer', 'reduce', 'negotiate', 'better price', 'can you do', 'any discount']
        is_asking_discount = any(keyword.lower() in customer_message.lower() for keyword in discount_keywords)
        
        # Format products with pricing info
        product_list = ""
        for i, product in enumerate(products[:5], 1):  # Limit to 5 products
            price_text = f"${product['price']}"
            if product.get('discount_price') and is_asking_discount:
                savings = product['price'] - product['discount_price']
                price_text = f"${product['discount_price']} (was ${product['price']}, save ${savings})"
            elif product.get('discount_price'):
                price_text = f"${product['price']}"
            product_list += f"{i}. {product['name']} - {price_text}\n"
        
        # Build prompt
        if is_asking_discount:
            prompt = f"""You are a helpful sales assistant for {business_name}. The customer {customer_name} is asking about discounts or negotiating price.

Available products:
{product_list}

Customer message: "{customer_message}"

Guidelines:
- You CAN offer discounts since the customer is asking
- Focus on the best value (highest savings)
- Be friendly but professional
- Don't give unrealistic discounts
- End with a clear call to action

Respond with a natural message that mentions the discount and encourages purchase."""
        else:
            prompt = f"""You are a helpful sales assistant for {business_name}. The customer {customer_name} is interested in products.

Available products:
{product_list}

Customer message: "{customer_message}"

Guidelines:
- DO NOT mention discounts unless asked
- Focus on product features and benefits
- Be helpful and professional
- Ask which product they'd like more details about

Respond with a natural message recommending products without mentioning discounts."""
        
        try:
            response = await self._call_llm(prompt, model_pref)
            return {
                "message": response,
                "mentions_discount": is_asking_discount,
                "confidence": 0.8
            }
        except Exception as e:
            logger.error(f"Product recommendation failed: {e}")
            return {
                "message": f"Hi {customer_name}, I have several options available. Which would you like to know more about?",
                "mentions_discount": False,
                "confidence": 0.5
            }


    async def _update_conversation_memory(self, db, customer_id: str, customer_name: str, messages: List[Dict], last_reply: str, last_incoming: str, user_id: str = None):
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
            mem_query = {"customer_id": customer_id}
            if user_id:
                mem_query["user_id"] = user_id
            existing = await db.conversation_memory.find_one(mem_query)
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

            new_summary = await self._call_llm(summary_prompt, model_pref='standard')
            
            # Upsert the memory
            mem_filter = {"customer_id": customer_id}
            if user_id:
                mem_filter["user_id"] = user_id
            await db.conversation_memory.update_one(
                mem_filter,
                {"$set": {
                    "customer_id": customer_id,
                    "user_id": user_id,
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
        if not self.clients:
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

            return await self._call_llm(prompt, model_pref='standard')
            
        except Exception as e:
            logger.error(f"Notes generation failed: {e}")
            return "Error generating notes"

# Singleton instance
_drafter_instance = None
_cached_api_key = None

def get_drafter() -> AIMessageDrafter:
    """Get singleton instance of AIMessageDrafter"""
    global _drafter_instance, _cached_api_key
    provider = os.environ.get('AI_PROVIDER', 'openai').strip().lower()
    if provider == 'deepseek':
        current_key = os.environ.get('DEEPSEEK_API_KEY', '')
    else:
        current_key = os.environ.get('OPENAI_API_KEY', '')
    cache_key = f"{provider}:{current_key}"
    
    # Recreate instance if key/provider changed or instance doesn't exist
    if _drafter_instance is None or _cached_api_key != cache_key:
        logger.info(f"Creating new AIMessageDrafter instance (provider: {provider})")
        _drafter_instance = AIMessageDrafter()
        _cached_api_key = cache_key
    
    return _drafter_instance
