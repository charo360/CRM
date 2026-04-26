from .base_agent import BaseAgent
from .tools import find_product_matches, find_product_matches_ai, normalize_url, format_product_catalog
from .ui_strings import t
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def _payment_methods_to_bullets(raw_pm: list) -> List[str]:
    """Turn user.payment_methods (strings or {name,details}) into WhatsApp bullet lines."""
    lines: List[str] = []
    if not raw_pm:
        return lines
    for pm in raw_pm:
        if isinstance(pm, dict):
            n = (pm.get("name") or "").strip()
            d = (pm.get("details") or "").strip()
            if n and d:
                lines.append(f"  • {n}: {d}")
            elif n:
                lines.append(f"  • {n}")
        elif isinstance(pm, str) and pm.strip():
            lines.append(f"  • {pm.strip()}")
    return lines


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

        # Use business_id from context (authoritative for product queries)
        biz_id = context.get("business_id", user_id)

        # --- PENDING ORDER CREATION (WhatsApp retail) ---
        # After "How many?": create order with ORD-XXXXXX, payment bullets from account settings,
        # and instructions for proof + delivery (same workflow as manual / legacy flows).
        logger.info(f"[SalesAgent] Checking pending_order_creation: {conv_state.get('pending_order_creation')}, step: {conv_state.get('pending_order_step')}, product: {conv_state.get('pending_order_product_name')}")
        if conv_state.get("pending_order_creation"):
            product_name = conv_state.get("pending_order_product_name", "your item")
            product_price = conv_state.get("pending_order_price", 0)
            product_id = conv_state.get("pending_order_product_id", "")
            # FIX: Handle None as "quantity" - dict.get() returns None if key exists with None value
            order_step = conv_state.get("pending_order_step") or "quantity"
            import re as _re2
            import uuid as _uuid2
            from datetime import datetime as _dt2

            def _cleared_order_context() -> Dict[str, Any]:
                return {
                    "pending_order_creation": False,
                    "pending_order_step": None,
                    "pending_order_quantity": None,
                    "pending_order_total": None,
                    "pending_order_delivery": None,
                    "pending_order_product_id": None,
                    "pending_order_product_name": None,
                    "pending_order_price": None,
                    "pending_order_list": None,
                    "pending_order_action": None,
                    "state": "ongoing",
                    "last_intent": intent,
                }

            async def _insert_order_and_reply(
                quantity: int,
                total: float,
                delivery_address: str,
                payment_method: str,
            ) -> Dict[str, Any]:
                _cid = context.get("customer_id")
                oid = str(_uuid2.uuid4())
                order_number = "ORD-" + oid[:6].upper()
                product_summary = f"{quantity}x {product_name}" if quantity != 1 else product_name
                product_line = f"{quantity}x {product_name}" if quantity != 1 else product_name

                raw_pm = context.get("payment_methods") or []
                if not raw_pm:
                    try:
                        _owner = await self.db.users.find_one({"_id": user_id}, {"payment_methods": 1})
                        raw_pm = (_owner or {}).get("payment_methods") or []
                    except Exception as _e_pm:
                        logger.warning(f"[SalesAgent] Could not load payment_methods: {_e_pm}")
                        raw_pm = []
                pay_bullets = _payment_methods_to_bullets(raw_pm)

                order_doc = {
                    "_id": oid,
                    "order_number": order_number,
                    "user_id": user_id,
                    "customer_name": customer_name,
                    "product": product_summary,
                    "items": [
                        {
                            "product_id": product_id,
                            "name": product_name,
                            "product_name": product_name,
                            "quantity": quantity,
                            "price": product_price,
                        }
                    ],
                    "total_amount": total,
                    "delivery_address": delivery_address or "— (confirm on chat)",
                    "payment_method": payment_method or "— (confirm on chat)",
                    "delivery_status": "Pending",
                    "payment_status": "Pending",
                    "status": "pending",
                    "created_at": _dt2.utcnow(),
                }
                if _cid:
                    order_doc["customer_id"] = str(_cid)
                try:
                    await self.db.orders.insert_one(order_doc)
                    logger.info(f"[SalesAgent] Order created: {order_number} id={order_doc['_id']} for {customer_name}")
                except Exception as e:
                    logger.error(f"[SalesAgent] Order DB insert failed: {e}")

                if pay_bullets:
                    pay_block = (
                        "\n\nTo complete your order, please make payment using the details below.\n\n"
                        "💳 *Payment Details:*\n" + "\n".join(pay_bullets)
                    )
                else:
                    pay_block = (
                        "\n\n💳 *Payment:* We'll confirm payment options with you on WhatsApp shortly."
                    )

                reply = (
                    f"*Order Received!*\n\n"
                    f"🔖 Order No: *#{order_number}*\n"
                    f"📦 {product_line}\n"
                    f"💰 {currency} {total:,.0f}\n"
                    f"Status: 🔴 Unpaid"
                    f"{pay_block}\n\n"
                    f"📸 Once you have paid, send us a screenshot of your payment confirmation.\n\n"
                    f"Also send your delivery details:\n"
                    f"• Full name\n"
                    f"• Delivery address\n"
                    f"• Phone number\n\n"
                    f"Your order *#{order_number}* will be processed once payment is confirmed. 🙏"
                )
                return {
                    "handled": True,
                    "messages": [{"text": reply}],
                    "flag_for_human": True,
                    "flag_reason": (
                        f"New order #{order_number}: {quantity}x {product_name} — {currency} {total:,.0f}"
                    ),
                    "context_update": _cleared_order_context(),
                }

            if order_step == "quantity":
                qty_match = _re2.search(r"\d+", message)
                if not qty_match:
                    return {
                        "handled": True,
                        "escalate": False,
                        "messages": [{
                            "text": (
                                f"Please send a *number only* for how many *{product_name}* you want "
                                f"(e.g. *1*, *2*, *3*). 🔢"
                            ),
                        }],
                    }
                quantity = int(qty_match.group())
                if quantity < 1:
                    quantity = 1
                total = float(product_price) * quantity
                return await _insert_order_and_reply(
                    quantity, total, "", "",
                )

            elif order_step == "delivery":
                # Legacy mid-flow: customer already gave qty; this message is the address
                delivery_address = message.strip()
                quantity = int(conv_state.get("pending_order_quantity") or 1)
                total = float(conv_state.get("pending_order_total") or (product_price * quantity))
                return await _insert_order_and_reply(quantity, total, delivery_address, "")

            elif order_step == "payment":
                # Legacy mid-flow: finalize with payment preference
                payment_method = message.strip()
                quantity = int(conv_state.get("pending_order_quantity") or 1)
                total = float(conv_state.get("pending_order_total") or (product_price * quantity))
                delivery_address = str(conv_state.get("pending_order_delivery") or "")
                return await _insert_order_and_reply(quantity, total, delivery_address, payment_method)

        # Fetch products - physical/digital products first
        try:
            products = await self.db.products.find({
                "user_id": biz_id,
                "offering_type": {"$in": ["product", "digital", "menu_item", "physical", "retail"]}
            }).to_list(100)
            # Fallback: if no physical products found (e.g. service business with empty/wrong
            # business_type routed here), show ALL products so catalog is never empty
            if not products:
                products = await self.db.products.find({"user_id": biz_id}).to_list(100)
        except Exception as e:
            logger.error(f"[SalesAgent] DB error fetching products: {e}")
            return {"handled": False}

        # --- CONTACT-AWARE SMALL TALK (KNOWN_CUSTOMER) ---
        if intent in ["GREETING", "GENERAL_CHAT", "UNKNOWN", "SMALL_TALK"]:
            relationship = context.get("_relationship", "new_conversation")
            return await self._handle_customer_chat(
                message, intent, customer_name, language,
                business_knowledge, history, currency, relationship, products, context
            )

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
                customer_name, language, currency, business_knowledge, history, products,
                confidence=confidence, careful_instruction=careful_instruction,
                discount_policy=discount_policy,
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
                message, intent, customer_name, language, business_knowledge, history, products, relationship,
                confidence=confidence, careful_instruction=careful_instruction,
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
            price_raw = p.get("price", 0)
            try:
                price = float(price_raw)
            except (ValueError, TypeError):
                price = 0.0
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

            # Provide the primary image with the caption
            msg = {"text": caption}
            if all_imgs:
                msg["media_url"] = all_imgs[0]
            messages_out.append(msg)
        
        # Add instruction text for how to select/order — labels in customer's language
        lang = context.get("language") or "English"
        if len(to_send) > 1:
            instruction = f"\n{t('view_gallery', lang)}\n{t('select_number_instruction', lang)}"
            messages_out.append({"text": instruction})
        elif len(to_send) == 1:
            # For single product, send action buttons immediately
            instruction = (
                "*What would you like to do?*\n\n"
                "1️⃣  Order Now\n"
                "2️⃣  Add to Cart\n"
                "3️⃣  See Similar Products\n"
                f"{t('view_gallery', lang)}\n\n"
                f"{t('select_number_instruction', lang)}"
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
        from datetime import timezone as _tz
        context_update["active_menu"] = True
        context_update["waiting_for_selection"] = True
        context_update["menu_sent_at"] = datetime.utcnow().isoformat()
        
        if len(to_send) > 1:
            context_update["menu_type"] = "product_selection"
            context_update["menu_items"] = {
                str(i): {"name": p["name"], "price": p.get("price", 0), "id": str(p["_id"]), "type": "product"}
                for i, p in enumerate(to_send, 1)
            }
        else:
            # Single product also uses a numbered list: 1. Order, 2. Add, 3. Similar
            context_update["menu_type"] = "single_product_actions"
            p = to_send[0]
            context_update["menu_items"] = {
                "1": {"name": "Order Now", "price": p.get("price", 0), "id": str(p["_id"]), "type": "product_action", "action": "order"},
                "2": {"name": "Add to Cart", "price": p.get("price", 0), "id": str(p["_id"]), "type": "product_action", "action": "add_cart"},
                "3": {"name": "See Similar", "price": p.get("price", 0), "id": str(p["_id"]), "type": "product_action", "action": "similar"}
            }

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

        # Single AI call: get intro + localised list header + footer instruction
        # No extra latency — one call returns all three pieces
        import json as _json, re as _re
        lang = language or "English"
        list_header = None
        list_footer = None
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            bk = (business_knowledge or "")[:300]
            if relationship in ("follow_up", "continuation"):
                tone_note = "Mid-conversation — NO greeting. Jump straight in with 1 short natural line."
            else:
                tone_note = "New conversation — brief, warm 1-sentence intro."
            prompt = (
                f"You are a business owner on WhatsApp. A customer asked to see your products.\n"
                f"Business info: {bk}\n"
                f"Customer language: {lang}\n"
                f"Tone note: {tone_note}\n\n"
                f"Return ONLY valid JSON with exactly these 3 keys:\n"
                f'{{\n'
                f'  "intro": "1 short warm sentence in {lang} introducing the catalog. {tone_note} Think: what would a real shopkeeper say?",\n'
                f'  "header": "A short bold title for the products list — in {lang}. With a shopping emoji. E.g. in English: \'🛍️ *Our Products*\'. Adapt naturally.",\n'
                f'  "footer": "A short instruction in {lang} telling them to reply with a number to select. In italics (_underscores_). Natural, informal."\n'
                f'}}\n\nJSON only. No markdown fences.'
            )
            raw = await ai._call_llm(prompt, model_pref="standard")
            match = _re.search(r'\{.*\}', raw, _re.DOTALL)
            if match:
                data = _json.loads(match.group())
                intro_text = (data.get("intro") or "").strip()
                list_header = (data.get("header") or "").strip()
                list_footer = (data.get("footer") or "").strip()
                if intro_text and len(intro_text) < 120:
                    messages_out.append({"text": intro_text})
        except Exception as e:
            logger.error(f"[SalesAgent] catalog intro error: {e}")

        # Fallback to ui_strings if AI didn't return labels
        if not list_header:
            list_header = t("products_header", lang)
        if not list_footer:
            list_footer = t("select_number_instruction", lang)

        # Build numbered list — header and footer are now in the customer's language
        lines = [list_header + "\n"]
        for i, p in enumerate(first_page, 1):
            price = p.get('price', 0)
            stock = "✅" if p.get('in_stock', True) else "❌"
            price_str = f"{currency} {price:,.0f}" if price else "POA"
            lines.append(f"{i}️⃣  *{p['name']}* — {price_str} {stock}")
        if has_more:
            lines.append(t("see_more", lang))
        lines.append(t("view_gallery", lang))
        lines.append("\n" + list_footer)

        messages_out.append({"text": "\n".join(lines)})

        from datetime import datetime as _dt
        _menu_items_catalog = {
            str(i): {"name": p["name"], "price": p.get("price", 0), "id": str(p["_id"]), "type": "product"}
            for i, p in enumerate(first_page, 1)
        }
        if has_more:
            _menu_items_catalog["9"] = {"type": "see_more", "offset": PAGE_SIZE}

        return {
            "handled": True,
            "messages": messages_out,
            "escalate": False,
            "context_update": {
                "state": "ongoing",
                "last_intent": "CATALOG_REQUEST",
                "catalog_all_ids": [str(p["_id"]) for p in all_products],
                "catalog_has_more": has_more,
                # Menu state — enables numbered selection + "9 = see more" pagination
                "active_menu": True,
                "waiting_for_selection": True,
                "menu_type": "catalog_selection",
                "menu_sent_at": _dt.utcnow().isoformat(),
                "preferred_language": language,
                "menu_items": _menu_items_catalog,
                # Clear any stale order-list state so routing stays on the catalog flow
                "pending_order_list": None,
                "pending_order_action": None,
            },
        }

    async def _handle_negotiation(
        self, message, last_product_name, last_product_id, last_price,
        customer_name, language, currency, business_knowledge, history, products,
        confidence=1.0, careful_instruction="", discount_policy="",
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
        self, message, intent, customer_name, language, business_knowledge, history, products,
        relationship="new_conversation", confidence=1.0, careful_instruction="",
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

    async def _handle_customer_chat(
        self, message, intent, customer_name, language,
        business_knowledge, history, currency, relationship, products, context
    ) -> Dict[str, Any]:
        """Contact-Aware Routing: Handles small talk from KNOWN_CUSTOMERs by pivoting to sales."""
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            bk = (business_knowledge or "")[:300]
            
            prompt = f"""You are a business owner replying on WhatsApp to a known customer: {customer_name}.
They just sent a casual message or greeting: "{message}"

Business info: {bk}

Output only the customer-facing message. Think: what would a real shopkeeper say back when a regular customer walks in and says hi?

Rules:
- Be warm and genuinely human — match their energy and language exactly.
- Acknowledge their greeting naturally first (1 short line).
- Then ask ONE simple open question: what brings them in today, or if they need anything.
- Do NOT immediately list products or push the catalog — let them respond first.
- Max 2 sentences. Pure WhatsApp tone — contractions, informal phrasing is fine.
- Language: {language}
- CRITICAL: NEVER confirm or imply any order, booking, or appointment has been made."""

            reply = await ai._call_llm(prompt, model_pref="standard")
            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": False,
                "context_update": {
                    "state": "ongoing",
                    "last_intent": intent,
                    # If customer replies "yes/sure/ok", route them to catalog instead of ChatAgent
                    "waiting_for_service_request": True,
                    "preferred_language": language,
                },
            }
        except Exception as e:
            logger.error(f"[SalesAgent] customer_chat handler error: {e}")
            return {"handled": False}
