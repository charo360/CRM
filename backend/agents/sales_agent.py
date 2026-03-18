from .base_agent import BaseAgent
from .tools import find_product_matches, find_product_matches_ai, normalize_url, format_product_catalog
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
        confidence = context.get("confidence", 1.0)
        careful_instruction = context.get("careful_instruction", "")
        business_config = context.get("business_config", {})
        discount_policy = business_config.get("discount_policy") or context.get("discount_policy", "")

        # Fetch products - physical/digital products first
        try:
            products = await self.db.products.find({
                "user_id": user_id,
                "offering_type": {"$in": ["product", "digital", "menu_item"]}
            }).to_list(100)
            # Fallback: if no physical products found (e.g. service business with empty/wrong
            # business_type routed here), show ALL products so catalog is never empty
            if not products:
                products = await self.db.products.find({"user_id": user_id}).to_list(100)
        except Exception as e:
            logger.error(f"[SalesAgent] DB error fetching products: {e}")
            return {"handled": False}

        # --- CATALOG REQUEST ---
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
        # Use AI-powered semantic matching for superior product discovery
        matches = await find_product_matches_ai(message, products)

        # Fallback to keyword matching if AI returns nothing
        if not matches and keywords:
            kw_str = ", ".join(keywords) if isinstance(keywords, list) else keywords
            matches = await find_product_matches_ai(kw_str, products)

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
            relationship = context.get("_relationship", "new_conversation")
            return await self._handle_no_match(
                message, intent, customer_name, language, business_knowledge, history, products, relationship
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

        for i, p in enumerate(to_send, 1):
            price = p.get("price", 0)
            in_stock = p.get("in_stock", True)
            
            # Add product number for multi-product lists
            if len(to_send) > 1:
                caption = f"*{i}. {p['name']}*\n💰 {currency} {price:,.0f}"
            else:
                caption = f"*{p['name']}*\n💰 {currency} {price:,.0f}"

            if not in_stock:
                caption += "\n_(Out of stock)_"

            if p.get("description"):
                desc = p["description"]
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                caption += f"\n{desc}"

            # Collect ALL images (deduplicated)
            all_imgs = []
            if p.get("image_url"):
                all_imgs.append(p["image_url"])
            for _im in p.get("images", []):
                if _im and _im not in all_imgs:
                    all_imgs.append(_im)
            all_imgs = [normalize_url(u) for u in all_imgs if u]

            # Extra images first (no caption/text)
            for _extra_img in all_imgs[1:]:
                messages_out.append({"text": "", "media_url": _extra_img})

            msg = {"text": caption}
            if all_imgs:
                msg["media_url"] = all_imgs[0]
            messages_out.append(msg)
        
        # Add instruction text for how to select/order
        if len(to_send) > 1:
            instruction = f"\n_Reply with the number (1-{len(to_send)}) to see details and order options_"
            messages_out.append({"text": instruction})
        elif len(to_send) == 1:
            # For single product, send action buttons immediately
            instruction = (
                "*What would you like to do?*\n\n"
                "1️⃣  Order Now\n"
                "2️⃣  Add to Cart\n"
                "3️⃣  See Similar Products\n\n"
                "_Reply with 1, 2 or 3_"
            )
            messages_out.append({"text": instruction})

        # Store products in pending_catalogs so customer can reply with numbers to select/order
        # This enables the same numbered reply flow as manual catalog sends
        customer_id = context.get("customer_id")
        if customer_id and to_send:
            from datetime import datetime
            try:
                await self.db.pending_catalogs.update_one(
                    {"customer_id": customer_id, "user_id": user_id},
                    {"$set": {
                        "products": [
                            {
                                "id": str(p["_id"]),
                                "name": p["name"],
                                "price": p.get("price", 0),
                                "index": idx
                            }
                            for idx, p in enumerate(to_send, 1)
                        ],
                        "action_context": "catalog_select" if len(to_send) > 1 else "product",
                        "single_product": len(to_send) == 1,
                        "created_at": datetime.utcnow()
                    }},
                    upsert=True
                )
            except Exception as e:
                logger.error(f"[SalesAgent] Failed to create pending_catalogs: {e}")

        # Track last discussed product for follow-up conversation
        if len(to_send) == 1:
            context_update["last_discussed_product_id"] = str(to_send[0]["_id"])
            context_update["last_discussed_product"] = to_send[0]["name"]
            context_update["last_price_offered"] = to_send[0].get("price")

        context_update["state"] = "ongoing"
        context_update["last_intent"] = intent

        # 17: Save menu state so router can intercept "One", "moja", "first" etc.
        if len(to_send) > 1:
            from datetime import timezone as _tz
            context_update["active_menu"] = True
            context_update["menu_type"] = "product_selection"
            context_update["menu_items"] = {
                str(i): {"name": p["name"], "price": p.get("price", 0), "id": str(p["_id"]), "type": "product"}
                for i, p in enumerate(to_send, 1)
            }
            context_update["waiting_for_selection"] = True
            context_update["menu_sent_at"] = datetime.utcnow().isoformat()
        else:
            context_update["waiting_for_selection"] = False
            context_update["active_menu"] = False

        return {
            "messages": messages_out,
            "context_update": context_update,
            "handled": True,
            "escalate": False,
        }

    async def _handle_catalog_request(
        self, products, currency, customer_name, language, business_knowledge, history, relationship="new_conversation"
    ) -> Dict[str, Any]:
        """Send numbered catalog list with pagination (8 products per page, option 9 = more)."""
        if not products:
            # 3.1: Friendly empty catalog fallback — never say "no products"
            return {
                "handled": True,
                "messages": [{"text": f"Thanks for reaching out, {customer_name}! Our full catalog is being updated right now. I'll personally send you our latest items shortly — stay tuned! 😊"}],
                "escalate": False,
                "flag_for_human": True,
                "flag_reason": "Customer requested catalog but no products found — owner needs to follow up",
            }

        in_stock = [p for p in products if p.get("in_stock", True)]
        all_products = in_stock if in_stock else products
        
        PAGE_SIZE = 8
        first_page = all_products[:PAGE_SIZE]
        has_more = len(all_products) > PAGE_SIZE

        # Add currency to products
        products_with_currency = [{"currency": currency, **p} for p in first_page]

        messages_out = []
        
        # Optional AI intro (brief, context-aware)
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            bk = (business_knowledge or "")[:300]
            if relationship in ("follow_up", "continuation"):
                tone_instruction = "Mid-conversation — NO greetings. Just 1 short natural line like 'Sure, here's what we have:' or 'Here you go:'"
            else:
                tone_instruction = "Brief intro — 1 sentence max. Natural WhatsApp tone."
            prompt = f"""Customer asked for catalog. Business: {bk}. {tone_instruction} Reply:"""
            intro = await ai._call_llm(prompt, model_pref="standard")
            if intro and len(intro) < 100:
                messages_out.append({"text": intro.strip()})
        except Exception as e:
            logger.error(f"[SalesAgent] catalog intro error: {e}")

        # Build numbered list
        lines = ["🛍️ *Our Products*\n"]
        for i, p in enumerate(first_page, 1):
            price = p.get('price', 0)
            stock = "✅" if p.get('in_stock', True) else "❌"
            price_str = f"{currency} {price:,.0f}" if price else "POA"
            lines.append(f"{i}️⃣  *{p['name']}* — {price_str} {stock}")
        if has_more:
            lines.append(f"9️⃣  ➡️ *See more products*")
        lines.append("\n_Reply with a number to select_")
        
        messages_out.append({"text": "\n".join(lines)})

        return {
            "handled": True,
            "messages": messages_out,
            "escalate": False,
            "context_update": {
                "state": "ongoing",
                "last_intent": "CATALOG_REQUEST",
                "catalog_all_ids": [str(p["_id"]) for p in all_products],
                "catalog_page_offset": 0,
                "catalog_has_more": has_more
            },
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

            # 5.1: Extract discount policy
            discount_hint = f"\nDiscount policy: {discount_policy}" if discount_policy else "\nDiscount policy: None stated — do NOT invent discounts."

            # Intent hint injection
            intent_hint = (
                f"Intent classified as: NEGOTIATION ({confidence:.0%} confidence)\n"
                f"Customer message: \"{message}\"\n\n"
                f"Read the message yourself. If the classification seems off, address what the customer actually needs instead.\n"
            )
            if careful_instruction:
                intent_hint += f"\n{careful_instruction}\n"

            prompt = f"""You are a sales assistant handling a price negotiation.

{intent_hint}
Business info: {bk}{discount_hint}
Product: {product['name']} — {currency} {price:,.0f} {'(In stock)' if in_stock else '(Out of stock)'}
Customer: {customer_name}

Recent conversation:
{history_snippet}

Think one sentence about what this customer actually needs, then reply. Output only the customer-facing message.

Rules:
1. Acknowledge their request warmly
2. Hold firm on the price politely OR mention any genuine offer from the business info above
3. NEVER invent a lower price or discount not stated in the business info
4. 5.2: If customer makes a counter-offer, acknowledge it specifically (e.g. "I hear you on the {currency} X ask") then explain why the price is fair
5. If no flexibility exists, suggest value (quality, service, speed, etc.)
6. Conversational, WhatsApp-natural, 2-3 sentences max
7. CRITICAL: ONLY use facts above. NEVER invent prices, discounts, or offers."""

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
        self, message, intent, customer_name, language, business_knowledge, history, products, relationship="new_conversation"
    ) -> Dict[str, Any]:
        """No products found matching the query — honest reply, no hallucination."""
        has_products = len(products) > 0
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            bk = (business_knowledge or "")[:400]
            history_snippet = self._format_history(history)

            # Mid-conversation tone: no greeting
            if relationship in ("follow_up", "continuation"):
                tone_rule = "NO greeting (no 'Hi there', 'Hey', etc) — conversation is already going. Jump straight to the answer."
            else:
                tone_rule = "Keep it short. No corporate opener."

            # Intent hint injection
            intent_hint = (
                f"Intent classified as: {intent} ({confidence:.0%} confidence)\n"
                f"Customer message: \"{message}\"\n\n"
                f"Read the message yourself. If the classification seems off, address what the customer actually needs instead.\n"
            )
            if careful_instruction:
                intent_hint += f"\n{careful_instruction}\n"

            if has_products:
                # 4.1: No-match — show closest alternative specifically
                catalog_hint = format_product_catalog(products[:5], "")
                prompt = f"""You are a business owner replying on WhatsApp. A customer asked about something you don't carry.

{intent_hint}
Business info: {bk}
Available products:
{catalog_hint}

Recent conversation:
{history_snippet}

Think one sentence about what this customer actually needs, then reply. Output only the customer-facing message.

Rules:
- {tone_rule}
- Acknowledge what they asked for in 1 short sentence
- Then suggest the SINGLE most relevant product from your catalog by name — be specific (e.g. "We don't carry X but our Y might work for you")
- NEVER say "I don't have specific details" — just say what you DO have
- NEVER invent products or prices not in the catalog
- Max 2 sentences. WhatsApp tone.
- Language: {language}"""
            else:
                prompt = f"""You are a business owner on WhatsApp. Customer asked: "{message}"
You don't have a product catalog set up yet.
Write 1 short sentence in {language} saying you'll get back to them — sound like a real person, not a bot."""

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
        recent = history[-15:]
        lines = [
            f"{'Customer' if m.get('direction')=='incoming' else 'Business'}: {m.get('content','')}"
            for m in recent
        ]
        return "\n".join(lines)
