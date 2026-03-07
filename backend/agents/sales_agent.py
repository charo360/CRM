from .base_agent import BaseAgent
from .tools import find_product_matches, normalize_url, format_product_catalog
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SalesAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles product inquiries, catalog requests, stock checks, price questions,
        and negotiation. Uses conversation state to understand mid-conversation context.
        """
        intent = context.get("intent", "PRODUCT_INQUIRY")
        language = context.get("language", "English")
        currency = context.get("currency", "USD")
        customer_name = context.get("customer_name", "there")
        business_knowledge = context.get("business_knowledge", "")
        history = context.get("history", [])
        keywords = context.get("keywords", [])
        entities = context.get("entities", {})
        conv_state = context.get("conversation_state_data", {})

        # Fetch all active products for this user
        try:
            products = await self.db.products.find({"user_id": user_id}).to_list(100)
        except Exception as e:
            logger.error(f"[SalesAgent] DB error fetching products: {e}")
            return {"handled": False}

        # --- CATALOG REQUEST: send full catalog ---
        if intent == "CATALOG_REQUEST":
            relationship = context.get("_relationship", "new_conversation")
            return await self._handle_catalog_request(
                products, currency, customer_name, language, business_knowledge, history, relationship
            )

        # --- NEGOTIATION: customer is negotiating on a previously discussed product ---
        if intent == "NEGOTIATION":
            last_product_id = conv_state.get("last_discussed_product_id")
            last_product_name = conv_state.get("last_discussed_product")
            last_price = conv_state.get("last_price_offered")
            return await self._handle_negotiation(
                message, last_product_name, last_product_id, last_price,
                customer_name, language, currency, business_knowledge, history, products
            )

        # --- PRODUCT MATCH: find relevant products ---
        # Try message text first
        matches = find_product_matches(message, products)

        # Use AI-extracted keywords if no direct match
        if not matches and keywords:
            kw_str = ", ".join(keywords) if isinstance(keywords, list) else keywords
            matches = find_product_matches(kw_str, products)

        # Use entity product names if still no match
        if not matches:
            entity_products = entities.get("products", [])
            if entity_products:
                matches = find_product_matches(" ".join(entity_products), products)

        # Check if customer is asking about the last discussed product
        if not matches and conv_state.get("last_discussed_product"):
            matches = find_product_matches(conv_state["last_discussed_product"], products)

        if not matches:
            # We know it's a sales intent but couldn't find a product match
            return await self._handle_no_match(
                message, intent, customer_name, language, business_knowledge, history, products
            )

        # Limit to 5 matches
        to_send = matches[:5]

        # Build product messages
        messages_out = []
        context_update = {}

        if len(to_send) > 1:
            # AI-generated header for multi-product response
            header = await self._build_multi_product_header(
                message, customer_name, language, len(to_send)
            )
            messages_out.append({"text": header})

        for p in to_send:
            price = p.get("price", 0)
            in_stock = p.get("in_stock", True)
            caption = f"*{p['name']}*\n💰 {currency} {price:,.0f}"

            if not in_stock:
                caption += "\n_(Out of stock)_"

            if p.get("description"):
                desc = p["description"]
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                caption += f"\n{desc}"

            img_url = p.get("image_url")
            if not img_url and p.get("images"):
                img_url = p["images"][0]

            msg = {"text": caption}
            if img_url:
                msg["media_url"] = normalize_url(img_url)
            messages_out.append(msg)

        # Track last discussed product for follow-up conversation
        if len(to_send) == 1:
            context_update["last_discussed_product_id"] = str(to_send[0]["_id"])
            context_update["last_discussed_product"] = to_send[0]["name"]
            context_update["last_price_offered"] = to_send[0].get("price")

        context_update["state"] = "ongoing"
        context_update["last_intent"] = intent

        return {
            "messages": messages_out,
            "context_update": context_update,
            "handled": True,
            "escalate": False,
        }

    async def _handle_catalog_request(
        self, products, currency, customer_name, language, business_knowledge, history, relationship="new_conversation"
    ) -> Dict[str, Any]:
        """Send a concise catalog overview."""
        if not products:
            return {
                "handled": True,
                "messages": [{"text": "We don't have any products listed yet. Please check back soon!"}],
                "escalate": False,
            }

        in_stock = [p for p in products if p.get("in_stock", True)]
        display = in_stock[:8] if in_stock else products[:8]

        messages_out = []
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            catalog_text = format_product_catalog(display, currency)
            bk = (business_knowledge or "")[:300]

            # Adjust tone based on whether this is mid-conversation or a fresh start
            if relationship in ("follow_up", "continuation"):
                tone_instruction = "This is mid-conversation — NO greetings, NO 'Hey there!', NO 'Great to have you!'. Just send the catalog naturally as if continuing the chat. 1 short line intro max."
            else:
                tone_instruction = "Brief, natural intro — 1 sentence only. No corporate enthusiasm, no emojis overload."

            prompt = f"""You are a business owner replying on WhatsApp. A customer asked to see your catalog.

Business info: {bk}
Customer: {customer_name}
Language: {language}

{tone_instruction}

Product catalog:
{catalog_text}

Write the intro line then list the products. Keep it WhatsApp-natural. No fake enthusiasm. Reply:"""
            intro = await ai._call_llm(prompt, model_pref="standard")
            messages_out.append({"text": intro})
        except Exception as e:
            logger.error(f"[SalesAgent] catalog intro error: {e}")
            messages_out.append({"text": "Here's what we have available:"})

        # Send product cards for top 5
        for p in display[:5]:
            price = p.get("price", 0)
            caption = f"*{p['name']}*\n💰 {currency} {price:,.0f}"
            if p.get("description"):
                desc = p["description"][:100]
                caption += f"\n{desc}"
            img_url = p.get("image_url") or (p.get("images") or [None])[0]
            msg = {"text": caption}
            if img_url:
                msg["media_url"] = normalize_url(img_url)
            messages_out.append(msg)

        return {
            "handled": True,
            "messages": messages_out,
            "escalate": False,
            "context_update": {"state": "ongoing", "last_intent": "CATALOG_REQUEST"},
        }

    async def _handle_negotiation(
        self, message, last_product_name, last_product_id, last_price,
        customer_name, language, currency, business_knowledge, history, products
    ) -> Dict[str, Any]:
        """Handle price negotiation — never promise a lower price, escalate if needed."""
        # Find the product being negotiated
        product = None
        if last_product_id:
            product = next((p for p in products if str(p.get("_id")) == str(last_product_id)), None)
        if not product and last_product_name:
            matches = find_product_matches(last_product_name, products)
            if matches:
                product = matches[0]

        if not product:
            # No product context — escalate
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "Customer is negotiating but no prior product context found",
                "messages": [],
            }

        try:
            from ai_service import get_drafter
            ai = get_drafter()
            history_snippet = self._format_history(history)
            bk = (business_knowledge or "")[:400]
            price = product.get("price", 0)
            in_stock = product.get("in_stock", True)

            prompt = f"""You are a sales assistant handling a price negotiation.

Business info: {bk}
Product: {product['name']} — {currency} {price:,.0f} {'(In stock)' if in_stock else '(Out of stock)'}
Customer: {customer_name}
Customer message: "{message}"

Recent conversation:
{history_snippet}

Write a polite reply in {language} that:
1. Acknowledges their request warmly
2. Holds firm on the price politely OR mentions any genuine offer from the business info
3. NEVER invents a lower price or discount not in the business info
4. If no flexibility exists, suggest value (quality, service, etc.)
5. Is conversational and WhatsApp-natural (2-3 sentences)
6. CRITICAL: ONLY use facts from the business info and conversation above. NEVER invent details.

Reply only:"""

            reply = await ai._call_llm(prompt, model_pref="standard")
            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": False,
                "context_update": {
                    "state": "negotiating",
                    "last_discussed_product": product["name"],
                    "last_discussed_product_id": str(product["_id"]),
                    "last_price_offered": price,
                    "last_intent": "NEGOTIATION",
                },
            }
        except Exception as e:
            logger.error(f"[SalesAgent] negotiation error: {e}")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"Negotiation handler failed: {e}",
                "messages": [],
            }

    async def _handle_no_match(
        self, message, intent, customer_name, language, business_knowledge, history, products
    ) -> Dict[str, Any]:
        """No products found matching the query — honest reply, no hallucination."""
        has_products = len(products) > 0
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            bk = (business_knowledge or "")[:400]
            history_snippet = self._format_history(history)

            if has_products:
                catalog_hint = format_product_catalog(products[:5], "")
                prompt = f"""You are a sales assistant. A customer asked about a product but we couldn't find an exact match.

Business info: {bk}
Customer: {customer_name}
Customer asked: "{message}"
Available products (sample):
{catalog_hint}

Recent conversation:
{history_snippet}

Write a helpful reply in {language} that:
1. Honestly says we don't have that specific item (if it's not in the catalog)
2. Suggests the closest available products if any are relevant
3. Does NOT invent products or prices
4. Offers to help further
5. Is brief and WhatsApp-natural
6. CRITICAL: ONLY mention products from the catalog above. NEVER invent products, prices or details.

Reply only:"""
            else:
                prompt = f"""A customer asked about a product but the business has no catalog set up yet.
Customer: {customer_name}, asked: "{message}"
Write a short, apologetic reply in {language} saying we'll get back to them shortly. 1-2 sentences."""

            reply = await ai._call_llm(prompt, model_pref="standard")
            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": not has_products,
                "escalate_reason": "No products in catalog" if not has_products else None,
                "context_update": {"state": "ongoing", "last_intent": intent},
            }
        except Exception as e:
            logger.error(f"[SalesAgent] no_match handler error: {e}")
            return {"handled": False}

    async def _build_multi_product_header(
        self, message, customer_name, language, count
    ) -> str:
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            prompt = f"""Write a very short intro message (1 sentence) in {language} for a WhatsApp business reply where we are showing {count} products to {customer_name} who asked: "{message}". Be warm and natural. No markdown."""
            return await ai._call_llm(prompt, model_pref="standard")
        except Exception:
            return "Here's what we have for you:"

    def _format_history(self, history: list, context: dict = None) -> str:
        # Use threaded history if available (more accurate context)
        if context and context.get("_threaded_history_text"):
            return context["_threaded_history_text"]
        if not history:
            return "(no prior history)"
        recent = history[-6:]
        lines = [
            f"{'Customer' if m.get('direction')=='incoming' else 'Business'}: {m.get('content','')}"
            for m in recent
        ]
        return "\n".join(lines)
