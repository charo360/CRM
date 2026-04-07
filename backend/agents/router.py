import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from collections import defaultdict

from .intent_analyzer import analyze_intent, route_intent_to_agent, build_threaded_context, format_threaded_history
from .conversation_state import load_state, save_state, mark_escalated
from .reply_validator import validate_reply, validate_db_state, RESULT_APPROVE, RESULT_REJECT, RESULT_ESCALATE
from .sales_agent import SalesAgent
from .order_agent import OrderAgent
from .payment_agent import PaymentAgent
from .complaint_agent import ComplaintAgent
from .chat_agent import ChatAgent
from .booking_agent import BookingAgent
from .personal_agent import PersonalAgent
from .session_summarizer import maybe_summarize, format_summary_for_prompt

logger = logging.getLogger(__name__)

MAX_VALIDATOR_RETRIES = 1

# 12.1: Intents that benefit from a more capable model
_HIGH_COMPLEXITY_INTENTS = {
    "COMPLAINT", "LEGAL_THREAT", "FRAUD_CLAIM",
    "NEGOTIATION", "DAMAGED_ITEM", "WRONG_ITEM",
    "REFUND_REQUEST", "ESCALATION",
}

# 12.5: Simple in-memory rate limiter (per user+customer pair)
_rate_store: Dict[str, List[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60   # seconds
_RATE_LIMIT_MAX = 5       # max messages per window


def _is_rate_limited(user_id: str, customer_id: str) -> bool:
    """Return True if this customer has sent too many messages recently."""
    key = f"{user_id}:{customer_id}"
    now = datetime.now(timezone.utc).timestamp()
    _rate_store[key] = [t for t in _rate_store[key] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_store[key]) >= _RATE_LIMIT_MAX:
        return True
    _rate_store[key].append(now)
    return False


def _get_model_for_intent(intent: str, sentiment: str) -> str:
    """12.1: Select model tier based on intent complexity and sentiment."""
    if sentiment in ("angry", "frustrated") or intent in _HIGH_COMPLEXITY_INTENTS:
        return "advanced"
    return "standard"


# 17: Multilingual word-to-number map for menu selection normalization
_SELECTION_MAP = {
    # Digits — 0 triggers "view all images/gallery" in catalog/service menus
    "0": 0,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    # English words
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "the first": 1, "the second": 2, "the third": 3,
    "first one": 1, "second one": 2, "third one": 3,
    "option 1": 1, "option 2": 2, "option 3": 3, "option 4": 4, "option 5": 5,
    "number 1": 1, "number 2": 2, "number 3": 3,
    "no 1": 1, "no 2": 2, "no 3": 3, "no. 1": 1, "no. 2": 2, "no. 3": 3,
    "#1": 1, "#2": 2, "#3": 3, "#4": 4, "#5": 5,
    # Swahili
    "moja": 1, "mbili": 2, "tatu": 3, "nne": 4, "tano": 5,
    "ya kwanza": 1, "ya pili": 2, "ya tatu": 3,
    "chaguo 1": 1, "chaguo 2": 2, "chaguo 3": 3,
    # French
    "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    # Arabic-Indic digits
    "\u0661": 1, "\u0662": 2, "\u0663": 3, "\u0664": 4, "\u0665": 5,
}


def _normalize_selection(message: str):
    """17: Normalize a customer reply to a menu item number. Returns int or None.
    First tries exact match from the map, then falls back to extracting a digit
    from short natural phrases like 'I'll take 2', 'give me the third one'.
    """
    cleaned = message.strip().lower()
    exact = _SELECTION_MAP.get(cleaned)
    if exact is not None:
        return exact
    # Fallback: extract a single digit from short conversational messages (≤5 words)
    # Avoids false positives on longer sentences like "I want 2 kg of rice"
    if len(cleaned.split()) <= 5:
        import re as _re
        _dm = _re.search(r'\b([1-9])\b', cleaned)
        if _dm:
            return int(_dm.group(1))
    return None


# Escalation acknowledgment — customer always gets this when we hand off to a human.
# Never let the customer sit in silence wondering if their message was received.
_ESCALATION_ACK_MSGS = {
    "English":    "Thanks for your message! Someone from our team will be with you shortly. 😊",
    "Swahili":    "Asante kwa ujumbe wako! Mtu kutoka timu yetu atakujibu hivi karibuni. 😊",
    "Sheng":      "Sawa! Mtu wetu atakujibu hivi sasa. 😊",
    "French":     "Merci pour votre message ! Un membre de notre équipe vous répondra bientôt. 😊",
    "Spanish":    "¡Gracias por tu mensaje! Alguien de nuestro equipo te responderá pronto. 😊",
    "Portuguese": "Obrigado pela sua mensagem! Alguém da nossa equipe responderá em breve. 😊",
    "Arabic":     "شكراً لرسالتك! سيتواصل معك أحد أعضاء فريقنا قريباً. 😊",
    "Hausa":      "Na gode da saƙonka! Ɗan ƙungiyarmu zai amsa da sauri. 😊",
    "Yoruba":     "E dupe fun ifiranṣẹ rẹ! Ẹnikan lati ẹgbẹ wa yoo dahun laipẹ. 😊",
    "Igbo":       "Daalụ maka ozi gị! Onye n'otu anyị ga-azaghachi ngwa ngwa. 😊",
    "Somali":     "Mahadsanid fariintaada! Xubin ka tirsan kooxdeena ayaa kugu jawaabi doona dhawaan. 😊",
    "Luganda":    "Webale obubaka bwo! Omuntu ku ffe agenda kukuddamu amangu. 😊",
    "Pidgin":     "Thank you for your message! Our person go reply you soon. 😊",
    "Hinglish":   "Aapka message mila! Hamari team jald hi jawab degi. 😊",
    "Amharic":    "ለመልእክትዎ እናመሰግናለን! የቡድናችን አባል በቅርቡ ያገኝዎታል። 😊",
    "Hindi":      "आपका संदेश मिल गया! हमारी टीम का कोई सदस्य जल्द ही जवाब देगा। 😊",
}


def _escalation_ack(language: str = "English") -> str:
    """Return a human-handoff acknowledgment in the customer's language."""
    return _ESCALATION_ACK_MSGS.get(language, _ESCALATION_ACK_MSGS["English"])


# 16.3: Business-critical intents that warrant owner notification
_BUSINESS_CRITICAL_INTENTS = {
    "COMPLAINT", "LEGAL_THREAT", "FRAUD_CLAIM",
    "PAYMENT_ISSUE", "REFUND_REQUEST", "ESCALATION",
    "DAMAGED_ITEM", "WRONG_ITEM",
}


def should_notify_owner(contact_signal: dict, intent: str) -> bool:
    """16.3: Only notify for business-critical situations. Never for personal contacts."""
    if contact_signal.get("type") == "personal":
        return False
    if intent in _BUSINESS_CRITICAL_INTENTS:
        return True
    return False


def _infer_correct_agent(intent: str, message: str, business_type: str) -> Optional[str]:
    """
    When ChatAgent hallucinates a booking/order confirmation, figure out which agent
    should actually handle this message.

    Strategy:
      1. If intent already maps to a non-chat agent, use that.
      2. Otherwise scan the raw message for domain-specific keywords to infer.
      3. Return agent name string, or None if we genuinely can't tell.
    """
    from .intent_analyzer import (
        BOOKING_INTENTS, ORDER_INTENTS, PAYMENT_INTENTS,
        COMPLAINT_INTENTS, SALES_INTENTS, route_intent_to_agent,
    )

    # Step 1: intent-based routing (already computed, fast)
    routed = route_intent_to_agent(intent, business_type)
    if routed != "chat":
        logger.info(f"[InferAgent] intent={intent} → {routed}")
        return routed

    # Step 2: message-level keyword scan — intent was GENERAL_CHAT but content was business
    msg = message.lower()
    _btype = (business_type or "").lower()
    _is_service = any(k in _btype for k in (
        "salon", "spa", "clinic", "barber", "beauty", "fitness", "gym",
        "service", "rental", "airbnb", "restaurant", "hotel", "saloon",
    ))

    # Booking signals (services/rentals)
    _BOOKING_SIGNALS = [
        "book", "booking", "appointment", "schedule", "reserve", "slot",
        "checkin", "check-in", "checkout", "check-out", "available",
        "when can i", "can i come", "what time", "next week", "tomorrow",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        # Swahili
        "hifadhi", "nafasi", "miadi", "weka", "booking yangu",
        # French
        "réserver", "rendez-vous", "disponible",
    ]
    # Order/product signals
    _ORDER_SIGNALS = [
        "order", "delivery", "my order", "where is", "track", "shipped",
        "order yangu", "amri yangu", "commande",
    ]
    # Payment signals
    _PAYMENT_SIGNALS = [
        "pay", "paid", "payment", "mpesa", "transfer", "invoice",
        "receipt", "lipa", "pesa", "paiement",
    ]
    # Complaint signals
    _COMPLAINT_SIGNALS = [
        "wrong", "broken", "damaged", "unhappy", "complaint", "refund",
        "not what", "poor quality", "mbaya", "tatizo", "problème",
    ]
    # Sales/product signals
    _SALES_SIGNALS = [
        "price", "how much", "catalog", "buy", "purchase", "stock",
        "bei", "nunua", "order something", "i want to buy",
        "prix", "acheter",
    ]

    booking_hits = sum(1 for s in _BOOKING_SIGNALS if s in msg)
    order_hits = sum(1 for s in _ORDER_SIGNALS if s in msg)
    payment_hits = sum(1 for s in _PAYMENT_SIGNALS if s in msg)
    complaint_hits = sum(1 for s in _COMPLAINT_SIGNALS if s in msg)
    sales_hits = sum(1 for s in _SALES_SIGNALS if s in msg)

    scores = {
        "booking" if _is_service else "sales": booking_hits,
        "order": order_hits,
        "payment": payment_hits,
        "complaint": complaint_hits,
        "sales": sales_hits,
    }

    best_agent, best_score = max(scores.items(), key=lambda x: x[1])
    if best_score >= 1:
        logger.info(
            f"[InferAgent] Message-level inference: best={best_agent} (score={best_score}) "
            f"from scores={scores} for message='{message[:60]}'"
        )
        return best_agent

    # Can't determine — caller should escalate
    logger.info(f"[InferAgent] Could not infer agent for intent={intent} message='{message[:60]}'")
    return None


class Router:
    def __init__(self, db: Any):
        self.db = db

    async def _get_contact_state(self, customer_id: str, user_id: str) -> dict:
        """16.4: Load contact classification state from customer document."""
        if not customer_id or self.db is None:
            return {"contact_type": "UNKNOWN", "message_count": 0, "ai_enabled": True}
        try:
            doc = await self.db.customers.find_one(
                {"_id": customer_id, "user_id": user_id},
                {"contact_type": 1, "contact_type_source": 1, "message_count": 1, "ai_enabled": 1, "is_personal": 1}
            )
            if doc:
                return {
                    "contact_type": doc.get("contact_type", "UNKNOWN"),
                    "contact_type_source": doc.get("contact_type_source", "unknown"),
                    "message_count": doc.get("message_count", 0),
                    "ai_enabled": doc.get("ai_enabled", not doc.get("is_personal", False)),
                }
        except Exception as e:
            logger.error(f"[Router] _get_contact_state error: {e}")
        return {"contact_type": "UNKNOWN", "message_count": 0, "ai_enabled": True}

    async def _update_contact_state(self, customer_id: str, user_id: str, updates: dict) -> None:
        """16.4: Persist contact classification state on customer document."""
        if not customer_id or self.db is None:
            return
        try:
            updates["contact_state_updated_at"] = datetime.now(timezone.utc)
            await self.db.customers.update_one(
                {"_id": customer_id, "user_id": user_id},
                {"$set": updates}
            )
        except Exception as e:
            logger.error(f"[Router] _update_contact_state error: {e}")

    async def route_and_process(
        self, user_id: str, message: str, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Full pipeline:
          1. Build threaded context (relationship detection)
          2. Load conversation state (auto-resets if stale)
          3. Analyze intent (1 AI call, threaded context)
          4. Contact classification gate (16.2)
          5. Dispatch to correct agent
          6. Validate reply (fast rules, no LLM)
          7. Save state + flag for human if needed
        """
        customer_id = context.get("customer_id")
        is_personal = context.get("is_personal", False)
        history = context.get("history", [])
        business_knowledge = context.get("business_knowledge", "")
        customer_name = context.get("customer_name", "Customer")

        # ── 1. Build threaded context ─────────────────────────────────────
        threaded = build_threaded_context(history)
        context["_threaded"] = threaded
        context["_relationship"] = threaded.get("relationship", "new_conversation")
        context["_threaded_history_text"] = format_threaded_history(threaded)

        # ── 2. Load conversation state ────────────────────────────────────
        conv_state = await load_state(self.db, user_id, str(customer_id) if customer_id else "")
        context["conversation_state_data"] = conv_state

        # ── 2.5: Menu selection gate (17) ─────────────────────────────────
        # Check BEFORE intent analyzer — intercepts "One", "moja", "first", "ya kwanza" etc.
        if conv_state.get("waiting_for_selection") and conv_state.get("menu_items"):
            _sel = _normalize_selection(message)
            _menu_items = conv_state.get("menu_items", {})

            # "0" = view all images / gallery — special signal to server.py
            if _sel == 0:
                if customer_id:
                    await save_state(self.db, user_id, str(customer_id), {
                        "active_menu": False, "waiting_for_selection": False,
                        "menu_items": {}, "menu_type": None,
                    })
                return {
                    "handled": True, "escalated": False,
                    "messages": [],
                    "show_gallery": True,
                }

            if _sel is not None and str(_sel) in _menu_items:
                _selected = _menu_items[str(_sel)]
                _menu_type = conv_state.get("menu_type", "product_selection")
                _lang = conv_state.get("preferred_language", "English") or "English"
                logger.info(f"[Router] Menu selection intercepted: '{message}' → {_sel} = {_selected.get('name', 'see_more')} (type={_menu_type})")

                # ── "See more" — catalog pagination ────────────────────────
                if _selected.get("type") == "see_more":
                    _offset = int(_selected.get("offset", 8))
                    _all_ids = conv_state.get("catalog_all_ids", [])
                    _currency2 = context.get("currency", "")
                    try:
                        from bson import ObjectId as _ObjId
                        from .ui_strings import t as _t
                        _next_ids = _all_ids[_offset:_offset + 8]
                        _next_products = []
                        if _next_ids:
                            _raw = await self.db.products.find(
                                {"_id": {"$in": [_ObjId(pid) for pid in _next_ids]}}
                            ).to_list(8)
                            _id_map = {str(p["_id"]): p for p in _raw}
                            _next_products = [_id_map[pid] for pid in _next_ids if pid in _id_map]
                        _has_more_next = len(_all_ids) > _offset + 8
                        _lines2 = [_t("products_header", _lang) + "\n"]
                        for _j, _p2 in enumerate(_next_products, 1):
                            _price2 = _p2.get("price", 0)
                            _stock2 = "✅" if _p2.get("in_stock", True) else "❌"
                            _pstr2 = f"{_currency2} {_price2:,.0f}" if _price2 else "POA"
                            _lines2.append(f"{_j}️⃣  *{_p2['name']}* — {_pstr2} {_stock2}")
                        if _has_more_next:
                            _lines2.append(_t("see_more", _lang))
                        _lines2.append(_t("view_gallery", _lang))
                        _lines2.append("\n" + _t("select_number_instruction", _lang))
                        _new_menu2 = {
                            str(_j): {"name": _p2["name"], "price": _p2.get("price", 0), "id": str(_p2["_id"]), "type": "product"}
                            for _j, _p2 in enumerate(_next_products, 1)
                        }
                        if _has_more_next:
                            _new_menu2["9"] = {"type": "see_more", "offset": _offset + 8}
                        if customer_id:
                            await save_state(self.db, user_id, str(customer_id), {
                                "active_menu": bool(_next_products),
                                "waiting_for_selection": bool(_next_products),
                                "menu_type": "catalog_selection",
                                "menu_items": _new_menu2,
                                "catalog_page_offset": _offset + 8,
                                "preferred_language": _lang,
                            })
                        _page_msg = "\n".join(_lines2) if _next_products else "That's everything we have! Let me know if you'd like more details on any item. 😊"
                        return {"handled": True, "escalated": False, "messages": [{"text": _page_msg}]}
                    except Exception as _pe:
                        logger.error(f"[Router] See more pagination error: {_pe}")
                        return {"handled": True, "escalated": False, "messages": [{"text": "Couldn't load the next page right now — please try again! 😊"}]}

                # ── Normal selection: clear menu state ──────────────────────
                if customer_id:
                    await save_state(self.db, user_id, str(customer_id), {
                        "active_menu": False, "waiting_for_selection": False,
                        "menu_items": {}, "menu_type": None,
                        "last_discussed_product": _selected.get("name"),
                    })
                # Build confirmation response based on menu type
                _name = _selected.get("name", "")
                _price = _selected.get("price", 0)
                _currency = context.get("currency", "")
                _product_id = _selected.get("id") or _selected.get("_id")
                if _menu_type == "service_selection":
                    _dur = _selected.get("duration")
                    _dur_str = f" ({_dur} min)" if _dur else ""
                    _svc_cat = _selected.get("service_category", "appointment")

                    # Rental with known dates from availability check — create booking directly
                    _ci = conv_state.get("checkin_date")
                    _co = conv_state.get("checkout_date")
                    _is_rental_dates = _svc_cat == "rental" and _ci and _co
                    if _is_rental_dates:
                        _nights = conv_state.get("nights", 1)
                        _total = _price * _nights if _price else 0
                        _total_str = f" · Total: {_currency} {_total:,.0f}" if _total else ""
                        _reply = (
                            f"🏠 *{_name}*\n"
                            f"Check-in: *{_ci}* → Check-out: *{_co}* ({_nights} night{'s' if _nights != 1 else ''}){_total_str}\n\n"
                            f"Your reservation request has been received! We'll confirm shortly. 🙏"
                        )
                        _flag_reason = f"Rental reservation: {_name} — {_ci} to {_co} ({_nights} nights)"
                        if customer_id:
                            try:
                                import random as _rnd, string as _str2
                                _bk_num = "BK-" + "".join(_rnd.choices(_str2.digits, k=6))
                                await self.db.bookings.insert_one({
                                    "user_id": user_id,
                                    "customer_id": str(customer_id),
                                    "service_name": _name,
                                    "service_id": _product_id,
                                    "price": _price,
                                    "checkin_date": _ci,
                                    "checkout_date": _co,
                                    "nights": _nights,
                                    "status": "pending",
                                    "booking_number": _bk_num,
                                    "created_at": datetime.now(timezone.utc),
                                    "created_by": "customer",
                                })
                                await self.db.customers.update_one(
                                    {"_id": customer_id},
                                    {"$set": {
                                        "needs_human": True,
                                        "needs_human_reason": _flag_reason,
                                        "needs_human_at": datetime.now(timezone.utc),
                                    }}
                                )
                                await save_state(self.db, user_id, str(customer_id), {
                                    "checkin_date": None, "checkout_date": None, "nights": None,
                                })
                            except Exception as _bke:
                                logger.error(f"[Router] Rental booking create error: {_bke}")
                        return {"handled": True, "escalated": False, "messages": [{"text": _reply}]}

                    # Rental listing selected from calendar — need to collect check-in AND check-out dates
                    if _svc_cat == "rental":
                        _rental_ask = (
                            f"🏠 *{_name}*\n\n"
                            f"What are your *check-in* and *check-out* dates?\n"
                            f"_Reply with both, e.g. *15 April to 20 April* or *15/04 - 20/04*_ 📅"
                        )
                        if customer_id:
                            try:
                                await self.db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user_id},
                                    {"$set": {
                                        "action_context": "rental_dates_input",
                                        "booking_service_id": _product_id,
                                        "booking_service_name": _name,
                                        "booking_service_price": _price,
                                        "price_unit": _selected.get("price_unit", "night"),
                                        "updated_at": datetime.now(timezone.utc),
                                    }},
                                    upsert=True
                                )
                                await save_state(self.db, user_id, str(customer_id), {
                                    "pending_rental_dates_input": True,
                                })
                            except Exception as _rde:
                                logger.error(f"[Router] Rental dates context save error: {_rde}")
                        return {
                            "handled": True, "escalated": False,
                            "messages": [{"text": _rental_ask}],
                        }

                    # Regular service — ask for date in customer's language
                    try:
                        from ai_service import get_drafter as _gd
                        _ai = _gd()
                        _date_prompt = (
                            f"You are a business owner on WhatsApp. A customer just selected a service to book.\n"
                            f"Service: {_name}{_dur_str}\nPrice: {_currency} {_price:,.0f}\nLanguage: {_lang}\n\n"
                            f"Write a warm 2-sentence reply in {_lang}:\n"
                            f"1. Confirm their service choice warmly\n"
                            f"2. Ask what date AND time they'd like\n"
                            f"WhatsApp tone. Output only the customer-facing message."
                        )
                        _reply = await _ai._call_llm(_date_prompt, model_pref="standard")
                    except Exception as _de:
                        logger.error(f"[Router] Service selection date prompt error: {_de}")
                        _reply = (
                            f"Great choice! *{_name}*{_dur_str} — {_currency} {_price:,.0f}\n\n"
                            f"When would you like to book? Please reply with your preferred *date and time*. 📅"
                        )

                    # Save service details so the next message routes to BookingAgent for date handling
                    if customer_id:
                        try:
                            await self.db.pending_catalogs.update_one(
                                {"customer_id": customer_id, "user_id": user_id},
                                {"$set": {
                                    "action_context": "booking_date_input",
                                    "booking_service_id": _product_id,
                                    "booking_service_name": _name,
                                    "booking_service_price": _price,
                                    "booking_service_duration": _dur,
                                    "updated_at": datetime.now(timezone.utc),
                                }},
                                upsert=True
                            )
                            await save_state(self.db, user_id, str(customer_id), {
                                "pending_booking_date_input": True,
                            })
                        except Exception as _bpe:
                            logger.error(f"[Router] Booking date context save error: {_bpe}")
                    return {
                        "handled": True, "escalated": False,
                        "messages": [{"text": _reply}],
                    }
                elif _menu_type == "single_product_actions":
                    # Customer picked Order Now / Add to Cart / See Similar
                    _action = _selected.get("action", "order")
                    if _action == "similar":
                        # Re-dispatch to sales to find similar items
                        _sim_ctx = {**context, "intent": "CATALOG_REQUEST", "_similar_to": _name}
                        _sim_result = await self._dispatch("sales", user_id, f"show me products similar to {_name}", _sim_ctx)
                        return {
                            "handled": True, "escalated": False,
                            "messages": _sim_result.get("messages") if _sim_result and _sim_result.get("messages") else [{"text": f"Let me find you something similar to *{_name}*! 🛍️"}],
                        }
                    else:
                        # Order Now or Add to Cart — collect delivery details
                        _order_reply = (
                            f"*{_name}* — {_currency} {_price:,.0f} 🛒\n\n"
                            f"How many would you like, and what's your *delivery address*? "
                            f"(Or let me know if you prefer *pickup*.) 📦"
                        )
                        if customer_id:
                            await save_state(self.db, user_id, str(customer_id), {
                                "pending_order_creation": True,
                                "pending_order_product_id": _product_id,
                                "pending_order_product_name": _name,
                                "pending_order_price": _price,
                            })
                            try:
                                await self.db.customers.update_one(
                                    {"_id": customer_id},
                                    {"$set": {
                                        "needs_human": True,
                                        "needs_human_reason": f"Customer wants to order: {_name} ({_currency} {_price:,.0f})",
                                        "needs_human_at": datetime.now(timezone.utc),
                                    }}
                                )
                            except Exception as _fe:
                                logger.error(f"[Router] Order flag error: {_fe}")
                        return {
                            "handled": True, "escalated": False,
                            "messages": [{"text": _order_reply}],
                        }
                else:
                    # catalog_selection or product_selection → showcase with full images + action buttons
                    return {
                        "handled": True, "escalated": False,
                        "messages": [],  # server.py sends product showcase
                        "showcase_product_id": _product_id,
                    }
            elif _sel is None:
                # Unrelated text reply — clear menu state, continue to intent analyzer
                if customer_id:
                    await save_state(self.db, user_id, str(customer_id), {
                        "active_menu": False, "waiting_for_selection": False,
                        "menu_items": {}, "menu_type": None,
                    })
            else:
                # _sel is a number but not in menu_items (e.g. out-of-range) — clear and continue
                if customer_id:
                    await save_state(self.db, user_id, str(customer_id), {
                        "active_menu": False, "waiting_for_selection": False,
                        "menu_items": {}, "menu_type": None,
                    })

        # ── 2.6: Rate limiting ─────────────────────────────────────────────
        if customer_id and _is_rate_limited(user_id, str(customer_id)):
            logger.warning(f"[Router] Rate limited: user={user_id} customer={customer_id}")
            _rl_lang = conv_state.get("preferred_language", "English") or "English"
            _rl_msgs = {
                "English": "You're sending messages too fast — please wait a moment before trying again. 🙏",
                "Swahili": "Unatuma ujumbe haraka sana — tafadhali subiri kidogo. 🙏",
                "Sheng":   "Unatuma fast sana buda — ngoja kidogo. 🙏",
                "French":  "Vous envoyez des messages trop vite — veuillez patienter un moment. 🙏",
                "Spanish": "Estás enviando mensajes muy rápido — espera un momento por favor. 🙏",
                "Arabic":  "ترسل رسائل بسرعة كبيرة — يرجى الانتظار لحظة. 🙏",
                "Pidgin":  "You dey send message too fast — wait small abeg. 🙏",
                "Hindi":   "Aap bahut tezi se message bhej rahe hain — thoda ruko please. 🙏",
                "Hinglish": "Bahut fast message kar rahe ho — thoda wait karo. 🙏",
                "Hausa":   "Kana aika saƙo da sauri sosai — don Allah jira ɗan lokaci. 🙏",
            }
            return {
                "handled": True,
                "escalated": False,
                "messages": [{"text": _rl_msgs.get(_rl_lang, _rl_msgs["English"])}],
            }

        # ── 3. Analyze intent ─────────────────────────────────────────────
        classification = await analyze_intent(
            message=message,
            history=history,
            business_knowledge=business_knowledge,
            conversation_state=conv_state,
            customer_name=customer_name,
            is_personal=is_personal,
            business_type=context.get("business_type", ""),
        )

        intent = classification.get("intent", "UNKNOWN")
        sentiment = classification.get("sentiment", "neutral")
        language = classification.get("language", "English")
        confidence = float(classification.get("confidence", 0.5))
        needs_escalation = classification.get("needs_escalation", False)
        escalation_reason = classification.get("escalation_reason", "")
        relationship = classification.get("_relationship", "new_conversation")
        entities = classification.get("entities", {})
        alternative_intents = classification.get("alternative_intents", [])
        contact_signal = classification.get("contact_signal", {"type": "unclear", "confidence": 0.0, "reason": ""})

        # ── 3.5: Contact classification gate (16.2) ────────────────────────
        contact_state = await self._get_contact_state(str(customer_id) if customer_id else "", user_id)
        msg_count = contact_state.get("message_count", 0) + 1
        current_contact_type = contact_state.get("contact_type", "UNKNOWN")
        ai_enabled = contact_state.get("ai_enabled", True)

        # ── 3.6: History-based pre-classification (16.6) ─────────────────────
        # If contact is still UNKNOWN but we have previous message history,
        # scan it for business signals to classify immediately — no waiting for msg 3+.
        if current_contact_type == "UNKNOWN" and history:
            _BIZ_KEYWORDS = {
                # Products / catalog
                "price", "bei", "cost", "how much", "ngapi", "catalog", "menu", "stock",
                "available", "unapatikana", "do you have", "mnayo", "nataka", "i want",
                "buy", "order", "nunua", "purchase", "delivery", "shipping",
                # Payments
                "mpesa", "payment", "pay", "paid", "transfer", "invoice", "receipt",
                # Bookings
                "book", "appointment", "schedule", "reserve", "booking",
                "available", "slot", "checkin", "check-in", "checkout",
                # Negotiation
                "discount", "offer", "deal", "wholesale", "bulk",
                # Support
                "complaint", "wrong", "damaged", "refund", "exchange",
            }
            _biz_hits = 0
            _personal_hits = 0
            _PERSONAL_SIGNALS = {"call me", "it's me", "ni mimi", "tuongee", "talk later", "miss you", "love you"}
            for _hmsg in history[-20:]:  # scan up to last 20 messages
                _htext = (_hmsg.get("content") or _hmsg.get("text") or "").lower()
                _hdir = _hmsg.get("direction", "")
                if _hdir != "incoming":
                    continue  # only customer-sent messages count
                if any(_kw in _htext for _kw in _BIZ_KEYWORDS):
                    _biz_hits += 1
                if any(_ps in _htext for _ps in _PERSONAL_SIGNALS):
                    _personal_hits += 1
            if _biz_hits >= 2 and _biz_hits > _personal_hits:
                # Clear customer pattern from history — classify immediately
                logger.info(
                    f"[Router] History pre-classification: customer={customer_id} → KNOWN_CUSTOMER "
                    f"({_biz_hits} business signals in history)"
                )
                await self._update_contact_state(
                    str(customer_id) if customer_id else "", user_id,
                    {"contact_type": "KNOWN_CUSTOMER", "contact_type_source": "history_detected",
                     "auto_detected_at_message": msg_count, "message_count": msg_count,
                     "ai_enabled": True, "is_personal": False}
                )
                current_contact_type = "KNOWN_CUSTOMER"
                is_personal = False
                context["is_personal"] = False
                # Also upgrade the current contact_signal so downstream logic stays consistent
                contact_signal = {"type": "customer", "confidence": 0.9, "reason": "business history detected"}
            elif _personal_hits >= 2 and _personal_hits > _biz_hits and _biz_hits == 0:
                # Clearly personal pattern from history
                logger.info(
                    f"[Router] History pre-classification: customer={customer_id} → NEEDS_REVIEW "
                    f"({_personal_hits} personal signals in history)"
                )
                await self._update_contact_state(
                    str(customer_id) if customer_id else "", user_id,
                    {"contact_type": "NEEDS_REVIEW", "contact_type_source": "history_detected",
                     "auto_detected_at_message": msg_count, "message_count": msg_count,
                     "ai_enabled": True, "is_personal": False, "needs_owner_classification": True}
                )
                if customer_id:
                    try:
                        await self.db.customers.update_one(
                            {"_id": customer_id},
                            {"$set": {
                                "needs_human": True,
                                "needs_human_reason": "Unclassified contact — tap to mark as Customer or Personal",
                                "needs_human_at": datetime.now(timezone.utc),
                            }}
                        )
                    except Exception as _hpe:
                        logger.error(f"[Router] History personal flag error: {_hpe}")
                current_contact_type = "NEEDS_REVIEW"
                is_personal = False
                context["is_personal"] = False

        # 16.5: If ai_enabled is False (personal contact, owner toggled off) → complete silence
        # RECOVERY: if a contact that was auto-classified as personal now sends a clear
        # business intent (product/booking/order/payment), re-enable AI and re-classify.
        # This prevents legitimate customers from being permanently ghosted after misclassification.
        if not ai_enabled:
            _recovery_intents = {
                "PRODUCT_INQUIRY", "CATALOG_REQUEST", "PRICE_INQUIRY", "STOCK_CHECK",
                "BOOKING_REQUEST", "AVAILABILITY_CHECK", "ORDER_STATUS", "PAYMENT_CONFIRM",
                "PAYMENT_METHOD", "NEGOTIATION", "BULK_ORDER",
            }
            _source = contact_state.get("contact_type_source", "")
            _can_recover = _source in ("auto_detected", "auto_detected_timeout")  # never override owner-manual
            _sig_conf_early = float(contact_signal.get("confidence", 0.0))
            if _can_recover and intent in _recovery_intents and _sig_conf_early >= 0.75:
                logger.info(
                    f"[Router] RECOVERY: re-classifying customer={customer_id} "
                    f"from KNOWN_PERSONAL → KNOWN_CUSTOMER (intent={intent} conf={_sig_conf_early:.2f})"
                )
                await self._update_contact_state(
                    str(customer_id) if customer_id else "", user_id,
                    {"contact_type": "KNOWN_CUSTOMER", "contact_type_source": "auto_recovered",
                     "ai_enabled": True, "is_personal": False, "message_count": msg_count}
                )
                ai_enabled = True
                is_personal = False
                context["is_personal"] = False
            else:
                logger.info(f"[Router] AI disabled for customer={customer_id} (personal contact)")
                await self._update_contact_state(str(customer_id) if customer_id else "", user_id, {"message_count": msg_count})
                return None

        sig_type = contact_signal.get("type", "unclear")
        sig_conf = float(contact_signal.get("confidence", 0.0))

        if current_contact_type == "UNKNOWN":
            if sig_type == "customer" and sig_conf >= 0.65:
                # Auto-tag as customer, continue pipeline normally
                logger.info(f"[Router] Auto-tagged customer={customer_id} as KNOWN_CUSTOMER")
                await self._update_contact_state(
                    str(customer_id) if customer_id else "", user_id,
                    {"contact_type": "KNOWN_CUSTOMER", "contact_type_source": "auto_detected",
                     "auto_detected_at_message": msg_count, "message_count": msg_count, "ai_enabled": True}
                )
                is_personal = False
                context["is_personal"] = False
            elif sig_type == "personal" and sig_conf >= 0.65:
                # Looks personal — but don't ghost them. Flag for owner review, keep replying naturally.
                logger.info(f"[Router] Contact={customer_id} looks personal (conf={sig_conf:.2f}) — flagging for owner review")
                await self._update_contact_state(
                    str(customer_id) if customer_id else "", user_id,
                    {"contact_type": "NEEDS_REVIEW", "contact_type_source": "auto_detected",
                     "auto_detected_at_message": msg_count, "message_count": msg_count,
                     "ai_enabled": True, "is_personal": False,
                     "needs_owner_classification": True}
                )
                if customer_id:
                    try:
                        await self.db.customers.update_one(
                            {"_id": customer_id},
                            {"$set": {
                                "needs_human": True,
                                "needs_human_reason": "Unclassified contact — tap to mark as Customer or Personal",
                                "needs_human_at": datetime.now(timezone.utc),
                            }}
                        )
                    except Exception as _nre:
                        logger.error(f"[Router] NEEDS_REVIEW flag error: {_nre}")
                # Continue pipeline — ChatAgent will reply naturally
                is_personal = False
                context["is_personal"] = False
            else:
                # Still unclear or low confidence
                if msg_count > 5:
                    # After 5 messages still unclear — flag for owner, keep AI on, never ghost
                    logger.info(f"[Router] Unknown contact reached message {msg_count} — flagging for owner review")
                    await self._update_contact_state(
                        str(customer_id) if customer_id else "", user_id,
                        {"contact_type": "NEEDS_REVIEW", "contact_type_source": "auto_detected_timeout",
                         "auto_detected_at_message": msg_count, "message_count": msg_count,
                         "ai_enabled": True, "is_personal": False,
                         "needs_owner_classification": True}
                    )
                    if customer_id:
                        try:
                            await self.db.customers.update_one(
                                {"_id": customer_id},
                                {"$set": {
                                    "needs_human": True,
                                    "needs_human_reason": "Unclassified contact — tap to mark as Customer or Personal",
                                    "needs_human_at": datetime.now(timezone.utc),
                                }}
                            )
                        except Exception as _nre2:
                            logger.error(f"[Router] NEEDS_REVIEW timeout flag error: {_nre2}")
                else:
                    await self._update_contact_state(
                        str(customer_id) if customer_id else "", user_id,
                        {"message_count": msg_count}
                    )
                
                # At exactly 3 messages, still unclear — just reply naturally to what they said.
                # Never use a bot-sounding clarifying question. Sound like a real person texting back.
                if msg_count == 3 and sig_type == "unclear":
                    logger.info(f"[Router] Unknown contact at 3 msgs — replying naturally")
                    _unk_reply = None
                    try:
                        from ai_service import get_drafter as _gd3
                        _ai3 = _gd3()
                        _bk3 = (business_knowledge or "")[:200]
                        _prompt3 = (
                            f"Someone just texted you on WhatsApp: \"{message}\"\n"
                            f"Their name: {customer_name}\n"
                            f"Language they used: {language}\n"
                            f"Business context: {_bk3}\n\n"
                            f"Reply EXACTLY like a real person would reply to this specific message — "
                            f"not a bot, not a customer service agent. "
                            f"Match their language and energy completely. "
                            f"If they greeted, greet back naturally. "
                            f"If they said something casual, respond casually. "
                            f"Do NOT ask 'what are you looking for' or any structured question. "
                            f"Do NOT mention products, services, or business unless they did. "
                            f"1-2 sentences max. Sound human. Output only the reply."
                        )
                        _unk_reply = await _ai3._call_llm(_prompt3, model_pref="standard")
                    except Exception as _e3:
                        logger.error(f"[Router] Unknown contact natural reply error: {_e3}")
                    if not _unk_reply:
                        # Fallback: just echo their energy naturally — no bot phrasing
                        _fallbacks = {
                            "Swahili": "Sawa! 😊", "Sheng": "Sawa fam! 😄",
                            "French": "Bonjour ! 😊", "Arabic": "أهلاً! 😊",
                            "Hausa": "Sannu! 😊", "Yoruba": "Ẹ káàbọ̀! 😊",
                        }
                        _unk_reply = _fallbacks.get(language, "Hey! 😊")
                    return {
                        "handled": True,
                        "escalated": False,
                        "messages": [{"text": _unk_reply}],
                    }
                # Within first 2 messages or if sig_type is personal with low confidence — respond naturally, continue pipeline
        else:
            # Known contact type — just update message count
            await self._update_contact_state(
                str(customer_id) if customer_id else "", user_id,
                {"message_count": msg_count}
            )
            # KNOWN_PERSONAL with ai_enabled=False already caught above
            if current_contact_type == "KNOWN_PERSONAL":
                is_personal = True
                context["is_personal"] = True

        # Expose contact_signal to downstream agents
        context["contact_signal"] = contact_signal

        # 1.6: Careful mode for low-confidence classifications
        careful_instruction = ""
        if confidence < 0.65 and not needs_escalation:
            context["careful_mode"] = True
            careful_instruction = (
                "Intent confidence is low. Read the customer message "
                "very carefully. If unsure, ask ONE clarifying question "
                "instead of assuming."
            )
            context["careful_instruction"] = careful_instruction

        # 12.1: Select AI model based on complexity
        selected_model = _get_model_for_intent(intent, sentiment)
        context["ai_model"] = selected_model

        # 14: Build business_config and inject into context
        business_config = {
            "business_id": user_id,
            "name": context.get("business_name", ""),
            "type": context.get("business_type", ""),
            "country": context.get("country", ""),
            "currency": context.get("currency", "USD"),
            "currency_symbol": context.get("currency_symbol", "$"),
            "primary_language": language,
            "payment_methods": context.get("payment_methods", []),
            "discount_policy": context.get("discount_policy", ""),
            "timezone": context.get("timezone", "UTC"),
            "escalation_contact": context.get("escalation_contact", ""),
            "booking_or_catalog": "booking" if context.get("business_type", "") in {
                "salon", "spa", "clinic", "gym", "hotel", "rental", "service"
            } else "catalog",
        }
        context["business_config"] = business_config

        # 15: Session summary every 5 messages
        session_summary = await maybe_summarize(
            history=history,
            business_knowledge=business_knowledge,
            customer_name=customer_name,
            conv_state=conv_state,
            user_id=user_id,
        )
        session_summary_text = format_summary_for_prompt(session_summary)

        # Owner-was-handling instruction: owner replied but stepped away >15 min ago
        owner_was_handling = context.get("owner_was_handling", False)
        owner_handling_instruction = ""
        if owner_was_handling:
            owner_handling_instruction = (
                "NOTE: A staff member was handling this conversation earlier but has not responded "
                "in the last 15 minutes. The customer may still have an unresolved issue. "
                "Acknowledge warmly, let them know you are picking this up, and if the issue "
                "is unclear say something like: 'Let me check on that and get back to you shortly.' "
                "Do NOT pretend the previous staff reply did not happen."
            )

        # Append owner-handling note into careful_instruction so all agents pick it up
        if owner_handling_instruction:
            careful_instruction = (careful_instruction + "\n" + owner_handling_instruction).strip()

        # Enrich context with classification results
        context.update({
            "intent": intent,
            "sentiment": sentiment,
            "language": language,
            "confidence": confidence,
            "keywords": classification.get("keywords", []),
            "entities": entities,
            "alternative_intents": alternative_intents,
            "careful_instruction": careful_instruction,
            "session_summary": session_summary,
            "session_summary_text": session_summary_text,
        })

        logger.info(
            f"[Router] user={user_id} customer={customer_id} "
            f"intent={intent} alt={alternative_intents} sentiment={sentiment} "
            f"lang={language} conf={confidence:.2f} model={selected_model} "
            f"escalate={needs_escalation} relationship={relationship}"
        )

        # ── 4. Immediate escalation if analyzer says so ────────────────────
        if needs_escalation:
            await self._do_escalate(user_id, customer_id, escalation_reason or f"Intent {intent} flagged for escalation")
            return {
                "handled": True,
                "escalated": True,
                "messages": self._ack(language),
                "escalation_reason": escalation_reason,
            }

        # ── 5. Dispatch to agent ───────────────────────────────────────────
        agent_name = route_intent_to_agent(intent, context.get("business_type", ""), current_contact_type)
        
        # Override agent routing based on active multi-step flows
        if conv_state.get("pending_order_action") or conv_state.get("pending_order_list"):
            logger.info("[Router] Overriding agent to 'order' due to pending order state")
            agent_name = "order"
        elif conv_state.get("pending_order_creation"):
            # Customer is providing delivery details after selecting "Order Now"
            logger.info("[Router] Overriding agent to 'sales' due to pending order creation")
            agent_name = "sales"
        elif conv_state.get("pending_booking_action") or conv_state.get("pending_booking_list"):
            logger.info("[Router] Overriding agent to 'booking' due to pending booking state")
            agent_name = "booking"
        elif conv_state.get("pending_booking_date_input"):
            logger.info("[Router] Overriding agent to 'booking' due to pending_booking_date_input")
            agent_name = "booking"
        elif conv_state.get("pending_rental_dates_input"):
            logger.info("[Router] Overriding agent to 'booking' due to pending_rental_dates_input")
            agent_name = "booking"

        if is_personal:
            agent_name = "personal"

        # 12.3: BookingAgent handling a complaint → ComplaintAgent
        if agent_name == "booking" and sentiment in ("angry", "frustrated") and conv_state.get("complaint_count", 0) > 0:
            logger.info(f"[Router] Booking+complaint sentiment → routing to complaint agent")
            agent_name = "complaint"

        logger.info(f"[Router] dispatching to agent={agent_name} for intent={intent} btype={context.get('business_type','')}")
        agent_result = await self._dispatch(agent_name, user_id, message, context)
        logger.info(f"[Router] agent={agent_name} returned handled={agent_result.get('handled') if agent_result else None}")

        if not agent_result:
            agent_result = {"handled": False}

        # Note: If an agent returns handled=False, it will fall through to the fallback block below
        
        # If agent itself requested escalation
        if agent_result.get("escalate"):
            reason = agent_result.get("escalate_reason", f"Agent {agent_name} escalated")
            await self._do_escalate(user_id, customer_id, reason)
            # Preserve any messages the agent already prepared — add ack if agent sent nothing
            escalate_messages = agent_result.get("messages", [])
            if not escalate_messages:
                escalate_messages = self._ack(language)
            return {
                "handled": True,
                "escalated": True,
                "messages": escalate_messages,
                "escalation_reason": reason,
            }

        if not agent_result.get("handled"):
            # For service/retail businesses, try the business-specific agent before chat fallback
            # This ensures booking/catalog requests that slip through intent classification
            # still reach the correct agent instead of ChatAgent generating fake confirmations
            _btype_fb = context.get("business_type", "").lower()
            _is_svc_fb = any(k in _btype_fb for k in (
                "salon", "saloon", "barbershop", "spa", "clinic", "healthcare",
                "fitness", "gym", "services", "restaurant", "hotel", "beauty",
                "rental", "airbnb", "creator", "service",
            ))
            
            # If the primary attempt failed, and we haven't tried the domain-specific agent yet, do so.
            if _is_svc_fb and agent_name != "booking":
                logger.info(f"[Router] Service biz fallback: trying booking agent for intent={intent}")
                agent_result = await self._dispatch("booking", user_id, message, context)
            elif not _is_svc_fb and agent_name != "sales":
                logger.info(f"[Router] Retail biz fallback: trying sales agent for intent={intent}")
                agent_result = await self._dispatch("sales", user_id, message, context)
            
            # If domain-specific agents still didn't handle it, AND we haven't tried chat fallback yet, try chat.
            if (not agent_result or not agent_result.get("handled")) and agent_name != "chat":
                logger.warning(f"[Router] No agent handled intent={intent}, trying chat fallback")
                agent_result = await self._dispatch("chat", user_id, message, context)
                
            # If nothing handled it at all
            if not agent_result or not agent_result.get("handled"):
                logger.warning(f"[Router] ALL fallbacks failed. Escalating intent={intent}")
                await self._do_escalate(user_id, customer_id, f"No agent handled intent={intent}")
                return {"handled": True, "escalated": True, "messages": self._ack(language), "escalation_reason": f"Unhandled intent: {intent}"}

        # ── 6. Reply validation (fast rules, no LLM) ─────────────────────
        messages_out = agent_result.get("messages", [])
        if messages_out:
            reply_text = " ".join(m.get("text", "") for m in messages_out if m.get("text"))
            validation = await validate_reply(
                reply_text=reply_text,
                original_message=message,
                intent=intent,
                sentiment=sentiment,
                language=language,
                agent_name=agent_name,
                business_knowledge=business_knowledge,
                history=history,
            )

            if validation["result"] == RESULT_ESCALATE:
                reason = validation.get("reason", "Validator escalated reply")
                logger.warning(f"[Router] Validator ESCALATE: {reason}")
                await self._do_escalate(user_id, customer_id, reason)
                return {"handled": True, "escalated": True, "messages": self._ack(language), "escalation_reason": reason}

            if validation["result"] == RESULT_REJECT:
                reason = validation.get("reason", "")
                suggestion = validation.get("suggestion", "")
                # If ChatAgent produced something that looks like a booking/order confirmation,
                # do NOT retry ChatAgent — it cannot fix this.
                # Instead, infer the correct agent and dispatch to it.
                # Only escalate if we truly can't determine the right agent.
                _is_confirmation_hallucination = (
                    agent_name == "chat" and (
                        "fake booking" in reason.lower() or "confirmation" in reason.lower()
                    )
                ) or "fake booking" in reason.lower()
                if _is_confirmation_hallucination:
                    _correct_agent = _infer_correct_agent(intent, message, context.get("business_type", ""))
                    if _correct_agent and _correct_agent != "chat":
                        logger.info(f"[Router] ChatAgent hallucination caught — re-routing to {_correct_agent} (intent={intent})")
                        reroute_result = await self._dispatch(_correct_agent, user_id, message, context)
                        if reroute_result and reroute_result.get("handled") and not reroute_result.get("escalate"):
                            logger.info(f"[Router] Re-route to {_correct_agent} succeeded after ChatAgent hallucination")
                            messages_out = reroute_result.get("messages", [])
                            agent_result = reroute_result
                            agent_name = _correct_agent  # update so state saves correctly
                            # Skip further validation retry — the correct agent handled it properly
                            # (it has its own internal guardrails)
                        else:
                            logger.warning(f"[Router] Re-route to {_correct_agent} failed — escalating")
                            await self._do_escalate(user_id, customer_id, f"ChatAgent hallucinated, re-route to {_correct_agent} also failed")
                            return {"handled": True, "escalated": True, "messages": self._ack(language), "escalation_reason": reason}
                    else:
                        logger.warning(f"[Router] ChatAgent fake-confirmation — could not infer agent, escalating: {reason}")
                        await self._do_escalate(user_id, customer_id, f"AI attempted to fake-confirm booking/order — {reason}")
                        return {"handled": True, "escalated": True, "messages": self._ack(language), "escalation_reason": reason}

                # For all other REJECT reasons — one retry with the suggestion fed back
                logger.info(f"[Router] Validator REJECT — retrying. Reason: {reason} | Suggestion: {suggestion}")
                context["validator_suggestion"] = suggestion
                context["custom_instructions"] = suggestion

                retry_result = await self._dispatch(agent_name, user_id, message, context)
                if retry_result and retry_result.get("handled") and not retry_result.get("escalate"):
                    messages_out = retry_result.get("messages", [])
                    agent_result = retry_result
                else:
                    await self._do_escalate(user_id, customer_id, "Retry agent failed")
                    return {"handled": True, "escalated": True, "messages": self._ack(language), "escalation_reason": "Retry agent failed"}

        # ── 6.5. Post-action DB state validation ──────────────────────────
        # Checks that claims in the reply ("booked", "ordered", "cancelled")
        # actually match database records. Catches hallucinated confirmations
        # that slipped past the text validator.
        if messages_out:
            reply_text = " ".join(m.get("text", "") for m in messages_out if m.get("text"))
            db_validation = await validate_db_state(
                reply_text=reply_text,
                agent_name=agent_name,
                intent=intent,
                customer_id=str(customer_id) if customer_id else None,
                user_id=user_id,
                db=self.db,
            )
            if db_validation["result"] == RESULT_REJECT:
                db_reason = db_validation.get("reason", "")
                db_suggestion = db_validation.get("suggestion", "")
                # ChatAgent claiming a booking/order exists in DB when nothing is there
                # is a hallucination — infer the correct agent and re-route.
                if agent_name == "chat":
                    _correct_agent_db = _infer_correct_agent(intent, message, context.get("business_type", ""))
                    if _correct_agent_db and _correct_agent_db != "chat":
                        logger.info(f"[Router] ChatAgent DB hallucination — re-routing to {_correct_agent_db}")
                        reroute_db = await self._dispatch(_correct_agent_db, user_id, message, context)
                        if reroute_db and reroute_db.get("handled") and not reroute_db.get("escalate"):
                            messages_out = reroute_db.get("messages", [])
                            agent_result = reroute_db
                            agent_name = _correct_agent_db
                        else:
                            await self._do_escalate(user_id, customer_id, f"ChatAgent DB hallucination, re-route to {_correct_agent_db} failed")
                            return {"handled": True, "escalated": True, "messages": self._ack(language), "escalation_reason": db_reason}
                    else:
                        logger.warning(f"[Router] ChatAgent DB hallucination — could not infer agent, escalating: {db_reason}")
                        await self._do_escalate(user_id, customer_id, f"ChatAgent hallucinated DB state — {db_reason}")
                        return {"handled": True, "escalated": True, "messages": self._ack(language), "escalation_reason": db_reason}

                logger.warning(f"[Router] DB Validator REJECT: {db_reason} | Retrying with hint")
                context["validator_suggestion"] = db_suggestion
                context["custom_instructions"] = db_suggestion

                retry_result = await self._dispatch(agent_name, user_id, message, context)
                if retry_result and retry_result.get("handled") and not retry_result.get("escalate"):
                    messages_out = retry_result.get("messages", [])
                    agent_result = retry_result
                else:
                    await self._do_escalate(user_id, customer_id, "DB validation retry failed")
                    return {"handled": True, "escalated": True, "messages": self._ack(language), "escalation_reason": "DB validation retry failed"}

        # ── 7. Save conversation state ────────────────────────────────────
        state_updates = agent_result.get("context_update", {})
        state_updates["last_intent"] = intent
        # Clear waiting_for_service_request once the customer has responded with a real intent
        # (keeps the flag from persisting across unrelated messages)
        if intent not in ("GREETING", "GENERAL_CHAT", "SMALL_TALK", "PERSONAL_CHAT") and conv_state.get("waiting_for_service_request"):
            state_updates.setdefault("waiting_for_service_request", False)
        if customer_id:
            await save_state(self.db, user_id, str(customer_id), state_updates)

        # ── 8. Flag for human if agent requested soft flag ────────────────
        if agent_result.get("flag_for_human") and customer_id:
            try:
                await self.db.customers.update_one(
                    {"_id": customer_id},
                    {"$set": {
                        "needs_human": True,
                        "needs_human_reason": agent_result.get("flag_reason", "Agent flagged for review"),
                        "needs_human_at": datetime.now(timezone.utc),
                    }}
                )
            except Exception as e:
                logger.error(f"[Router] flag_for_human update error: {e}")

        return {
            "handled": True,
            "escalated": False,
            "messages": messages_out,
            "context_update": state_updates,
        }

    async def _dispatch(
        self, agent_name: str, user_id: str, message: str, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Instantiate and run the correct agent."""
        try:
            if agent_name == "sales":
                return await SalesAgent("sales", self.db).process(user_id, message, context)
            elif agent_name == "order":
                return await OrderAgent(self.db).process(user_id, message, context)
            elif agent_name == "payment":
                return await PaymentAgent(self.db).process(user_id, message, context)
            elif agent_name == "complaint":
                return await ComplaintAgent(self.db).process(user_id, message, context)
            elif agent_name == "booking":
                return await BookingAgent("booking", self.db).process(user_id, message, context)
            elif agent_name == "personal":
                return await PersonalAgent("personal", self.db).process(user_id, message, context)
            else:
                return await ChatAgent("chat", self.db).process(user_id, message, context)
        except Exception as e:
            logger.error(f"[Router] _dispatch error agent={agent_name}: {e}")
            return {"handled": False}

    async def _do_escalate(self, user_id: str, customer_id, reason: str) -> None:
        """Mark conversation as escalated in DB."""
        if customer_id:
            await mark_escalated(self.db, user_id, str(customer_id), reason)
        logger.info(f"[Router] ESCALATED customer={customer_id} reason={reason}")

    def _ack(self, language: str = "English") -> list:
        """Return a single-item message list with the escalation ack in the customer's language."""
        return [{"text": _escalation_ack(language)}]
