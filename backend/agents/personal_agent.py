from .base_agent import BaseAgent
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class PersonalAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles personal contacts (friends, family) and fan DMs for creator accounts.

        Two modes:
        1. Fan DM — creator business type + non-collab message → use fan_dm_response
           template as style guide, reply naturally as the creator
        2. Personal contact — friend/family → warm, casual, match their energy exactly
        """
        if not context.get("is_personal"):
            return {"handled": False}

        try:
            from ai_service import get_drafter
            ai_service = get_drafter()

            customer_name = context.get("customer_name", "there")
            language = context.get("language", "English")
            business_type = context.get("business_type", "").lower()
            business_knowledge = context.get("business_knowledge", "")
            history = context.get("history", [])
            if not history:
                history = [{"direction": "incoming", "content": message}]

            # Build recent thread for AI context
            thread_lines = []
            for m in history[-12:]:
                role = "Them" if m.get("direction") == "incoming" else "You"
                thread_lines.append(f"{role}: {m.get('content', '')}")
            thread_text = "\n".join(thread_lines) if thread_lines else "(No prior messages)"

            is_creator = business_type == "creator"

            # Extract fan_dm_response template if creator has one set
            fan_dm_template = ""
            if is_creator and business_knowledge:
                for line in business_knowledge.split("\n"):
                    if line.lower().startswith("fan dm response"):
                        fan_dm_template = line.split(":", 1)[-1].strip()
                        break

            if is_creator and fan_dm_template:
                instructions = (
                    f"You are a content creator replying to a message from {customer_name} on WhatsApp.\n\n"
                    f"Their message: \"{message}\"\n\n"
                    f"Recent thread:\n{thread_text}\n\n"
                    f"Your typical response style for fan/personal messages:\n\"{fan_dm_template}\"\n\n"
                    "Use that as a style guide — not a template to copy word-for-word. Adapt it naturally to this specific message.\n"
                    "Rules:\n"
                    f"- Reply in {language} — match their language exactly\n"
                    "- Warm, genuine, real — the way a creator actually talks to fans\n"
                    "- If it's praise or support, be appreciative without being over-the-top\n"
                    "- If it's a question, answer it briefly and directly\n"
                    "- If they're asking about collabs or paid work, say to DM for collab inquiries (keep it brief)\n"
                    "- 1-3 sentences max. Never corporate, never robotic.\n"
                    "- NEVER reveal you are AI or a bot\n"
                    "Output ONLY the reply text."
                )
            elif is_creator:
                instructions = (
                    f"You are a content creator replying to {customer_name} on WhatsApp.\n\n"
                    f"Their message: \"{message}\"\n\n"
                    f"Recent thread:\n{thread_text}\n\n"
                    "Rules:\n"
                    f"- Reply in {language} — match their exact language and tone\n"
                    "- Warm and genuine — the way a real creator talks, not a PR statement\n"
                    "- If it's a fan message, appreciate it naturally without being fake\n"
                    "- If it's a collab inquiry, briefly direct them to proper channels\n"
                    "- If it's a friend or personal message, just talk normally\n"
                    "- 1-2 sentences. Never use: 'I hope this finds you well', 'Thank you for reaching out', 'I'd be happy to'\n"
                    "- NEVER reveal you are AI\n"
                    "Output ONLY the reply text."
                )
            else:
                # Regular personal contact — friend or family of the business owner
                instructions = (
                    f"You are replying on WhatsApp to {customer_name} — a personal contact (friend or family), NOT a customer.\n\n"
                    f"Their message: \"{message}\"\n\n"
                    f"Recent thread:\n{thread_text}\n\n"
                    "Reply the way a real person texts someone they actually know:\n"
                    f"- Match their exact language and energy — {language}, mixed, Sheng, whatever they used\n"
                    "- If they said something funny, be funny back. If they're venting, be warm. If they asked something, answer it directly.\n"
                    "- Do NOT mention the business, products, or anything sales-related\n"
                    "- Do NOT use: 'Sure thing', 'Absolutely', 'I hope this helps', 'I understand your concern'\n"
                    "- 1-2 sentences unless they asked something that needs more\n"
                    "- NEVER invent facts or personal details about them\n"
                    "- NEVER share sensitive info (passwords, bank details, IDs)\n"
                    "Output ONLY the reply text."
                )

            custom_req = context.get("custom_instructions")
            if custom_req:
                instructions += f"\n\nExtra direction: {custom_req}"

            result = await ai_service.draft_followup_message(
                customer_name=customer_name,
                customer_data={},
                messages=history,
                business_name="Personal",
                tone="casual",
                business_knowledge=None,  # Never inject business context for personal chats
                custom_instructions=instructions,
                user_id=user_id,
                model_pref=context.get("ai_model", "standard"),
            )

            reply_text = result.get("drafted_message", "")
            if reply_text:
                return {
                    "messages": [{"text": reply_text}],
                    "handled": True,
                    "escalate": False,
                    "context_update": {"state": "ongoing", "last_intent": context.get("intent", "PERSONAL_CHAT")},
                }

        except Exception as e:
            logger.error(f"[PersonalAgent] error: {e}")

        return {"handled": False}
