from .base_agent import BaseAgent
from .ui_strings import t
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


PICK_NUMBER_RE = __import__('re').compile(r'^(\d+)$')
PAGE_SIZE = 8


class BookingAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles booking/appointment intents:
        - BOOKING_REQUEST   : Customer wants to book a service
        - AVAILABILITY_CHECK: Customer asks what times/days are free
        - BOOKING_STATUS    : Customer asks about an existing booking
        - BOOKING_CANCEL    : Customer wants to cancel/reschedule
        """
        # --- EXTRACT CONTEXT VARIABLES ---
        intent = context.get("intent", "BOOKING_REQUEST")
        language = context.get("language", "English")
        currency = context.get("currency", "USD")
        customer_name = context.get("customer_name", "there")
        business_knowledge = context.get("business_knowledge", "")
        history = context.get("history", [])
        customer_id = context.get("customer_id")
        conv_state = context.get("conversation_state_data", {})
        business_type = (context.get("business_type") or "").lower().strip()
        is_rental = business_type == "rental"  # will also check services below after fetch
        confidence = context.get("confidence", 1.0)
        careful_instruction = context.get("careful_instruction", "")

        # --- RESET/START OVER HANDLER ---
        # 17: Clears both pendings and context if user wants to start afresh
        if intent == "RESET_CONVERSATION":
            logger.info(f"[BookingAgent] User requested reset. Clearing states for customer_id={customer_id}")
            if customer_id:
                try:
                    await self.db.pending_catalogs.delete_one({"customer_id": customer_id, "user_id": user_id})
                    await self.db.conversation_states.delete_one({"customer_id": str(customer_id), "user_id": user_id})
                except Exception as e:
                    logger.error(f"[BookingAgent] Error during reset: {e}")
            
            # Start a brand new flow
            return await self._handle_booking_request(
                services=[], business_hours={}, booking_settings={}, customer_name=customer_name, 
                language=language, currency=currency, message=message, business_knowledge=business_knowledge, 
                history=history, customer_id=customer_id, user_id=user_id, is_rental=is_rental,
                intent="BOOKING_REQUEST", confidence=1.0, careful_instruction="User requested to start afresh. Welcome them back!"
            )

        # --- CONTEXT-AWARE SMALL TALK ---

        # ── Handle pending_booking_action: 1=Cancel / 2=Reschedule pick ──────
        pending_booking_action_id = conv_state.get("pending_booking_action")
        if pending_booking_action_id:
            _msg_ba = message.strip().lower()
            # Map both digit and natural language to choice
            _choice_ba = None
            if PICK_NUMBER_RE.match(message.strip()):
                _choice_ba = int(message.strip())
            elif _msg_ba in ("one", "1️⃣", "cancel", "cancel it", "yes cancel", "cancel booking", "cancel reservation"):
                _choice_ba = 1
            elif _msg_ba in ("two", "2️⃣", "reschedule", "change date", "new date", "move it"):
                _choice_ba = 2
            if _choice_ba in (1, 2):
                bk = await self.db.bookings.find_one({"_id": pending_booking_action_id})
                if bk:
                    if _choice_ba == 1:
                        return await self._execute_cancel(
                            bk, customer_name, currency, language, user_id, customer_id
                        )
                    elif _choice_ba == 2:
                        return await self._start_reschedule(
                            bk, customer_name, currency, language, user_id, customer_id
                        )
            elif _choice_ba is None and pending_booking_action_id:
                # Customer sent something unrecognised — re-prompt gently
                return {
                    "handled": True,
                    "messages": [{"text": "Just reply *1* to cancel or *2* to reschedule. 😊"}],
                    "escalate": False,
                }

        # ── Handle pending_booking_list: customer picking a booking by number ─
        pending_booking_ids = conv_state.get("pending_booking_list")
        if pending_booking_ids:
            _msg_bl = message.strip().lower()
            _pick_num = None
            if PICK_NUMBER_RE.match(message.strip()):
                _pick_num = int(message.strip())
            elif _msg_bl in ("one", "first", "1️⃣"):
                _pick_num = 1
            elif _msg_bl in ("two", "second", "2️⃣"):
                _pick_num = 2
            elif _msg_bl in ("three", "third", "3️⃣"):
                _pick_num = 3
            if _pick_num is not None:
                pick_idx = _pick_num - 1
                if 0 <= pick_idx < len(pending_booking_ids):
                    bk = await self.db.bookings.find_one({"_id": pending_booking_ids[pick_idx]})
                    if bk:
                        return await self._show_booking_actions(bk, customer_name, language, user_id, customer_id)
                else:
                    # Out of range — tell customer valid options
                    return {
                        "handled": True,
                        "messages": [{"text": f"Please reply with a number between *1* and *{len(pending_booking_ids)}* to select a booking. 😊"}],
                        "escalate": False,
                    }

        # ── Waitlist handler ──────────────────────────────────────────────────
        _msg_wl = message.strip().lower()
        if any(k in _msg_wl for k in ("waitlist", "wait list", "notify me", "let me know when")):
            return {
                "handled": True,
                "messages": [{"text": f"You're on the waitlist, {customer_name}! 🙌 We'll let you know as soon as a slot becomes available. 📩"}],
                "escalate": False,
                "flag_for_human": True,
                "flag_reason": f"Customer wants to join waitlist — add {customer_name} to waitlist",
            }

        # Use business_id from context (authoritative for product queries)
        # Falls back to user_id for backward compatibility
        biz_id = context.get("business_id", user_id)

        # Fetch services - exclude only explicitly physical/retail products
        # Safety net: also include any product with duration set (bookable service)
        # even if wrongly tagged as offering_type=product by the startup migration
        try:
            services = await self.db.products.find({
                "user_id": biz_id,
                "in_stock": {"$ne": False},
                "$or": [
                    {"offering_type": {"$nin": ["physical", "retail", "product"]}},
                    {"offering_type": "product", "duration": {"$exists": True, "$ne": None}},
                ],
            }).to_list(50)
            # Fallback: if no services found (e.g. products saved without offering_type/duration),
            # fetch ALL products so the booking flow always has something to show
            if not services:
                services = await self.db.products.find({
                    "user_id": biz_id,
                    "in_stock": {"$ne": False},
                }).to_list(50)
                if services:
                    logger.info(f"[BookingAgent] Fallback: found {len(services)} products via all-products query for biz_id={biz_id}")
        except Exception as e:
            logger.error(f"[BookingAgent] DB error fetching services: {e}")
            return {"handled": False}

        logger.info(f"[BookingAgent] biz_id={biz_id} user_id={user_id} services_found={len(services)} intent={context.get('intent')}")

        # Fetch user settings
        try:
            user_doc = await self.db.users.find_one({"_id": user_id})
            settings = (user_doc or {}).get("settings", {})
            business_hours = settings.get("business_hours", {})
            booking_settings = settings.get("booking_settings", {})
        except Exception as e:
            logger.error(f"[BookingAgent] DB error fetching user: {e}")
            business_hours = {}
            booking_settings = {}

        # Upgrade is_rental if any fetched service is a rental listing
        if not is_rental and any(s.get("service_category") == "rental" for s in services):
            is_rental = True

        # ── Greeting / small talk from a known customer ──────────────────────────
        # Respond warmly and ask what they need — don't dump the services list immediately.
        # The waiting_for_service_request state ensures their follow-up "yes/ok" routes back here.
        if intent in ("GREETING", "GENERAL_CHAT", "SMALL_TALK", "PERSONAL_CHAT"):
            return await self._handle_customer_chat(
                message, intent, customer_name, language, business_knowledge, history, currency, context
            )

        if intent == "AVAILABILITY_CHECK":
            # Creators don't have appointment calendars — they accept collabs based on budget/fit, not time slots
            if business_type == "creator":
                collab_packages = "\n".join(
                    f"• *{s['name']}* — {currency} {s.get('price', 0):,.0f}" if s.get("price") else f"• *{s['name']}*"
                    for s in services
                ) if services else ""
                pkg_block = f"\n\n*Collab packages:*\n{collab_packages}" if collab_packages else ""
                return {
                    "handled": True,
                    "messages": [{"text": (
                        f"I take on new collabs based on fit and current workload rather than fixed calendar slots.{pkg_block}\n\n"
                        f"Send over what you have in mind — brand, type of content, budget, and timeline — and I'll let you know if it works! 🙌"
                    )}],
                    "escalate": False,
                    "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
                }

            # Tech / SaaS — demo booking, not appointment calendar
            if business_type == "tech":
                _bk = business_knowledge or ""
                _demo_line = ""
                _trial_line = ""
                _plans_line = ""
                for _line in _bk.split("\n"):
                    _ll = _line.lower()
                    if _ll.startswith("demo booking:"):
                        _demo_line = _line.split(":", 1)[-1].strip()
                    elif _ll.startswith("free trial:"):
                        _trial_line = _line.split(":", 1)[-1].strip()
                    elif _ll.startswith("pricing plans:"):
                        _plans_line = _line.split(":", 1)[-1].strip()
                lines = ["🖥️ *Book a Demo*\n"]
                if _demo_line:
                    lines.append(f"{_demo_line}\n")
                else:
                    lines.append("We'd love to walk you through the platform — it takes about 30 minutes.\n")
                if _trial_line:
                    lines.append(f"🎁 *Free trial:* {_trial_line}")
                if _plans_line:
                    lines.append(f"💳 *Plans:* {_plans_line}")
                lines.append("\nWhat's a good time for you? Share your preferred day and time and we'll confirm shortly. 🙌")
                return {
                    "handled": True,
                    "messages": [{"text": "\n".join(lines)}],
                    "escalate": False,
                    "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
                }

            # Fitness — show class schedule instead of appointment calendar
            if business_type == "fitness":
                _bk = business_knowledge or ""
                _schedule_line = ""
                _pricing_line = ""
                for _line in _bk.split("\n"):
                    if _line.lower().startswith("class schedule:"):
                        _schedule_line = _line.split(":", 1)[-1].strip()
                    elif _line.lower().startswith("membership/pricing:"):
                        _pricing_line = _line.split(":", 1)[-1].strip()
                lines = ["📅 *Our Class Schedule*\n"]
                if _schedule_line:
                    lines.append(_schedule_line)
                elif services:
                    for s in services:
                        price_str = f" — {currency} {s.get('price', 0):,.0f}" if s.get("price") else ""
                        dur_str = f" ({s.get('duration')} min)" if s.get("duration") else ""
                        lines.append(f"• *{s['name']}*{price_str}{dur_str}")
                else:
                    lines.append("Contact us for our latest class schedule.")
                if _pricing_line:
                    lines.append(f"\n💳 *Membership/Pricing:* {_pricing_line}")
                if services:
                    lines.append("\n*Book a class — reply with the name or number:*")
                    for i, s in enumerate(services[:PAGE_SIZE], 1):
                        price_str = f" — {currency} {s.get('price', 0):,.0f}" if s.get("price") else ""
                        lines.append(f"{i}\ufe0f\u20e3  *{s['name']}*{price_str}")
                return {
                    "handled": True,
                    "messages": [{"text": "\n".join(lines)}],
                    "escalate": False,
                    "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
                }

            # Healthcare — show providers and appointment types instead of raw calendar
            if business_type == "healthcare":
                _bk = business_knowledge or ""
                _providers_line = ""
                _appt_types_line = ""
                _insurance_line = ""
                for _line in _bk.split("\n"):
                    _ll = _line.lower()
                    if _ll.startswith("providers/doctors:"):
                        _providers_line = _line.split(":", 1)[-1].strip()
                    elif _ll.startswith("appointment types:"):
                        _appt_types_line = _line.split(":", 1)[-1].strip()
                    elif _ll.startswith("insurance accepted:"):
                        _insurance_line = _line.split(":", 1)[-1].strip()
                lines = ["🏥 *Booking an Appointment*\n"]
                if _providers_line:
                    lines.append(f"*Our providers:* {_providers_line}\n")
                if _appt_types_line:
                    lines.append(f"*Appointment types:* {_appt_types_line}\n")
                elif services:
                    lines.append("*Services available:*")
                    for s in services[:PAGE_SIZE]:
                        price_str = f" — {currency} {s.get('price', 0):,.0f}" if s.get("price") else ""
                        lines.append(f"• *{s['name']}*{price_str}")
                if _insurance_line:
                    lines.append(f"\n*Insurance accepted:* {_insurance_line}")
                lines.append("\nWhich doctor/service would you like to book, and what date works for you?")
                return {
                    "handled": True,
                    "messages": [{"text": "\n".join(lines)}],
                    "escalate": False,
                    "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
                }

            return await self._handle_availability(
                services, business_hours, booking_settings, customer_name, language, currency, message, customer_id, user_id, is_rental
            )

        if intent in ("BOOKING_STATUS", "RESCHEDULE"):
            return await self._handle_booking_status(
                customer_id, user_id, customer_name, language, currency, is_rental
            )

        if intent == "BOOKING_CANCEL":
            return await self._handle_booking_cancel(
                customer_id, user_id, customer_name, language, message, is_rental
            )

        # ── Handle active booking step from pending_catalogs ─────────────────
        pending_doc = None
        try:
            pending_doc = await self.db.pending_catalogs.find_one({"customer_id": customer_id, "user_id": user_id})
            if pending_doc and pending_doc.get("action_context"):
                _ctx = pending_doc["action_context"]
                logger.info(f"[BookingAgent] Active action_context detected: {_ctx}")

                if _ctx == "booking_date_input":
                    _dates_ent = context.get("entities", {}).get("dates", [])
                    _date_keywords = ("tomorrow", "today", "monday", "tuesday", "wednesday",
                                      "thursday", "friday", "saturday", "sunday", "next",
                                      "morning", "afternoon", "evening", " am", " pm",
                                      "january", "february", "march", "april", "may", "june",
                                      "july", "august", "september", "october", "november", "december",
                                      "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
                    _msg_lower = message.lower()
                    _has_date = bool(_dates_ent) or any(k in _msg_lower for k in _date_keywords)
                    import re as _re_bk
                    if not _has_date and _re_bk.search(r'\b\d{1,2}[\/\-\.]\d{1,2}', _msg_lower):
                        _has_date = True

                    if _has_date:
                        return await self._handle_booking_date_received(
                            pending_doc, message, customer_name, language, currency,
                            customer_id, user_id, context
                        )
                    else:
                        # Customer asked something else mid-booking (price, availability, hours, anything).
                        # Answer naturally and guide back to the date step — no rigid gate.
                        _svc_name = pending_doc.get("booking_service_name", "your service")
                        return await self._handle_off_script(
                            message=message, customer_name=customer_name, language=language,
                            business_knowledge=business_knowledge, business_hours=business_hours,
                            history=history, services=services, currency=currency,
                            step="booking_date_input", step_hint=f"You already asked them which date they want to book *{_svc_name}*. After answering their question, naturally bring them back to that.",
                        )

                elif _ctx == "rental_dates_input":
                    _rdates = self._parse_dates_from_message(message)
                    if len(_rdates) >= 2:
                        return await self._handle_rental_dates_received(
                            pending_doc, _rdates[0], _rdates[1], message, customer_name,
                            language, currency, customer_id, user_id
                        )
                    else:
                        return await self._handle_off_script(
                            message=message, customer_name=customer_name, language=language,
                            business_knowledge=business_knowledge, business_hours=business_hours,
                            history=history, services=services, currency=currency,
                            step="rental_dates_input", step_hint="You need both a check-in AND check-out date from them. After answering their question, naturally ask for both dates.",
                        )

                elif _ctx == "booking_service_select" and not PICK_NUMBER_RE.match(message.strip()):
                    return await self._handle_off_script(
                        message=message, customer_name=customer_name, language=language,
                        business_knowledge=business_knowledge, business_hours=business_hours,
                        history=history, services=services, currency=currency,
                        step="booking_service_select", step_hint="They were picking a service from the list. After answering their question, naturally guide them back to choose.",
                    )

                elif _ctx == "booking_time_select":
                    # Server.py already handled numbers, "next", period words, and "3pm"-style time.
                    # Anything reaching here is a general question or context change — handle naturally.
                    _svc_name = pending_doc.get("booking_service_name", "your service")
                    _bk_date = pending_doc.get("booking_date", "")
                    return await self._handle_off_script(
                        message=message, customer_name=customer_name, language=language,
                        business_knowledge=business_knowledge, business_hours=business_hours,
                        history=history, services=services, currency=currency,
                        step="booking_time_select",
                        step_hint=f"They were choosing a time slot to book *{_svc_name}* on *{_bk_date}*. After answering their question, naturally bring them back to pick a time (they can reply with a number or say e.g. '3pm').",
                    )

                elif _ctx == "booking_confirm":
                    # They're at the YES/NO confirmation step — handle questions naturally
                    _svc_name = pending_doc.get("booking_service_name", "your service")
                    _bk_date = pending_doc.get("booking_date", "")
                    _bk_time = pending_doc.get("booking_time", "")
                    return await self._handle_off_script(
                        message=message, customer_name=customer_name, language=language,
                        business_knowledge=business_knowledge, business_hours=business_hours,
                        history=history, services=services, currency=currency,
                        step="booking_confirm",
                        step_hint=f"They have a pending booking for *{_svc_name}* on *{_bk_date}* at *{_bk_time}* awaiting confirmation. After answering their question, remind them to reply YES to confirm or NO to cancel.",
                    )

                elif _ctx == "restaurant_party_size_input":
                    _svc_name = pending_doc.get("booking_service_name", "your reservation")
                    _bk_date = pending_doc.get("booking_date", "")
                    _bk_time = pending_doc.get("booking_time", "")
                    return await self._handle_off_script(
                        message=message, customer_name=customer_name, language=language,
                        business_knowledge=business_knowledge, business_hours=business_hours,
                        history=history, services=services, currency=currency,
                        step="restaurant_party_size_input",
                        step_hint=f"They're booking *{_svc_name}* on *{_bk_date}* at *{_bk_time}* and you need to know how many people. After answering their question, naturally ask for the party size.",
                    )

                elif _ctx == "restaurant_requests_input":
                    _svc_name = pending_doc.get("booking_service_name", "your reservation")
                    _bk_date = pending_doc.get("booking_date", "")
                    _bk_time = pending_doc.get("booking_time", "")
                    _party = pending_doc.get("restaurant_party_size", "")
                    return await self._handle_off_script(
                        message=message, customer_name=customer_name, language=language,
                        business_knowledge=business_knowledge, business_hours=business_hours,
                        history=history, services=services, currency=currency,
                        step="restaurant_requests_input",
                        step_hint=f"They're booking *{_svc_name}* for {_party} people on *{_bk_date}* at *{_bk_time}*. After answering their question, ask if they have any special requests (or reply NONE if not).",
                    )

                elif _ctx == "creator_timeline_input":
                    _svc_name = pending_doc.get("booking_service_name", "the project")
                    return await self._handle_off_script(
                        message=message, customer_name=customer_name, language=language,
                        business_knowledge=business_knowledge, business_hours=business_hours,
                        history=history, services=services, currency=currency,
                        step="creator_timeline_input",
                        step_hint=f"You need a deadline/timeline for *{_svc_name}*. After answering their question, naturally ask when they need it completed.",
                    )

                elif _ctx == "creator_budget_input":
                    _svc_name = pending_doc.get("booking_service_name", "the project")
                    _deadline = pending_doc.get("creator_deadline", "")
                    return await self._handle_off_script(
                        message=message, customer_name=customer_name, language=language,
                        business_knowledge=business_knowledge, business_hours=business_hours,
                        history=history, services=services, currency=currency,
                        step="creator_budget_input",
                        step_hint=f"You need their budget for *{_svc_name}* (deadline: {_deadline}). After answering their question, naturally ask what their budget is or if it's flexible.",
                    )

                elif _ctx == "creator_details_input":
                    _svc_name = pending_doc.get("booking_service_name", "the project")
                    _deadline = pending_doc.get("creator_deadline", "")
                    _budget = pending_doc.get("creator_budget", "")
                    return await self._handle_off_script(
                        message=message, customer_name=customer_name, language=language,
                        business_knowledge=business_knowledge, business_hours=business_hours,
                        history=history, services=services, currency=currency,
                        step="creator_details_input",
                        step_hint=f"You need project details for *{_svc_name}* (deadline: {_deadline}, budget: {_budget}). After answering their question, ask them to describe what they need.",
                    )

        except Exception as e:
            logger.warning(f"[BookingAgent] Error fetching pending_doc: {e}")

        # Default: BOOKING_REQUEST
        return await self._handle_booking_request(
            services, business_hours, booking_settings, customer_name, language, currency,
            message, business_knowledge, history, customer_id, user_id, is_rental,
            intent=intent, confidence=confidence, careful_instruction=careful_instruction,
            active_context=pending_doc.get("action_context") if pending_doc else None
        )

    # ── Booking Request ────────────────────────────────────────────────────────

    async def _handle_booking_request(
        self, services, business_hours, booking_settings,
        customer_name, language, currency, message,
        business_knowledge, history, customer_id, user_id, is_rental=False,
        intent="BOOKING_REQUEST", confidence=1.0, careful_instruction="",
        active_context: Optional[str] = None
    ) -> Dict[str, Any]:
        if not services:
            no_listing_msg = (
                "We don't have any listings available yet. Please check back soon or contact us directly!"
                if is_rental else
                "We don't have any services listed yet. Please check back soon or contact us directly!"
            )
            return {
                "handled": True,
                "messages": [{"text": no_listing_msg}],
                "escalate": False,
            }

        first_page = services[:PAGE_SIZE]
        has_more = len(services) > PAGE_SIZE

        # AI intro — single call returns intro text + localised list header + footer instruction
        intro_data = await self._ai_intro(
            message, customer_name, language, business_knowledge, history, is_rental,
            intent=intent, confidence=confidence, careful_instruction=careful_instruction,
            active_context=active_context
        )
        intro_text  = intro_data.get("intro")
        list_header = intro_data.get("header", "")
        list_footer = intro_data.get("footer", "")

        # Build numbered listing/services list — header and footer come from the AI call above
        from .ui_strings import t as _t
        lang = language or "English"
        see_more_label = _t("see_more", lang)
        gallery_label  = _t("view_gallery", lang)

        if is_rental:
            lines = [list_header + "\n"]
            for i, s in enumerate(first_page, 1):
                price = s.get("price", 0)
                unit = s.get("price_unit", "night")
                unit_label = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(unit, "night")
                price_str = f"{currency} {price:,.0f}/" + unit_label if price else "Contact for price"
                desc = s.get("description", "")
                desc_str = f" · {desc[:50]}" if desc else ""
                lines.append(f"{i}️⃣  *{s['name']}* — {price_str}{desc_str}")
            if has_more:
                lines.append(see_more_label)
            lines.append("\n" + list_footer)
        else:
            lines = [list_header + "\n"]
            for i, s in enumerate(first_page, 1):
                price = s.get("price", 0)
                duration = s.get("duration")
                price_str = f"{currency} {price:,.0f}" if price else "Contact for price"
                dur_str = f" · {duration} min" if duration else ""
                lines.append(f"{i}️⃣  *{s['name']}* — {price_str}{dur_str}")
            if has_more:
                lines.append(see_more_label)
            lines.append(gallery_label)
            lines.append("\n" + list_footer)
        services_text = "\n".join(lines)

        messages_out = []
        if intro_text:
            messages_out.append({"text": intro_text})

        # Only send the services list if:
        # 1. No active booking context
        # 2. Or context is 'booking_service_select'
        # 3. Or user specifically asked for 'what do you offer' / 'catalog'
        _show_list = not active_context or active_context == "booking_service_select" or intent == "CATALOG_REQUEST"
        if _show_list:
            messages_out.append({"text": services_text})

        # Safety net: if we're in the middle of a booking step and somehow ended up here
        # with no message (AI failed + list suppressed), send a fallback so the bot never
        # goes completely silent.
        if not messages_out:
            if active_context == "booking_date_input":
                messages_out.append({"text": "What date works best for you? You can say something like *tomorrow*, *Monday*, or *15 April*. 😊"})
            else:
                messages_out.append({"text": services_text})

        # Store in pending_catalogs for numbered reply
        if customer_id and first_page:
            try:
                await self.db.pending_catalogs.update_one(
                    {"customer_id": customer_id, "user_id": user_id},
                    {"$set": {
                        "products": [
                            {"id": str(s["_id"]), "name": s["name"], "price": s.get("price", 0),
                             "duration": s.get("duration"), "index": idx,
                             "service_category": s.get("service_category", "appointment"),
                             "addons": s.get("addons", []),
                             "image_url": s.get("image_url", "")}
                            for idx, s in enumerate(first_page, 1)
                        ],
                        "action_context": "booking_service_select",
                        "catalog_all_ids": [str(s["_id"]) for s in services],
                        "catalog_page_offset": 0,
                        "catalog_has_more": has_more,
                        "created_at": datetime.utcnow(),
                    }},
                    upsert=True
                )
            except Exception as e:
                logger.error(f"[BookingAgent] pending_catalogs upsert error: {e}")

        # 17: Save menu state so router can intercept "One", "moja", "first" etc.
        _menu_items_bk = {
            str(i): {"name": s["name"], "price": s.get("price", 0), "id": str(s["_id"]), "type": "service",
                     "duration": s.get("duration"), "service_category": s.get("service_category", "appointment")}
            for i, s in enumerate(first_page, 1)
        }
        return {
            "handled": True,
            "messages": messages_out,
            "escalate": False,
            "context_update": {
                "state": "ongoing",
                "last_intent": "BOOKING_REQUEST",
                "active_menu": True,
                "menu_type": "service_selection",
                "menu_items": _menu_items_bk,
                "waiting_for_selection": True,
                "menu_sent_at": datetime.utcnow().isoformat(),
            },
        }

    # ── Booking Date Received ─────────────────────────────────────────────────────

    async def _handle_booking_date_received(
        self, pending_doc: dict, message: str, customer_name: str,
        language: str, currency: str, customer_id, user_id: str, context: dict
    ) -> Dict[str, Any]:
        """
        Customer has provided a date after selecting a service.
        Creates a PENDING booking record and acknowledges warmly — never confirms.
        Flags for human to finalize.
        """
        import random, string as _str
        svc_name = pending_doc.get("booking_service_name", "the service")
        svc_id = pending_doc.get("booking_service_id", "")
        svc_price = pending_doc.get("booking_service_price", 0)
        dates_ent = context.get("entities", {}).get("dates", [])
        date_str = str(dates_ent[0]) if dates_ent else message.strip()[:80]
        reschedule_id = pending_doc.get("reschedule_booking_id")
        reschedule_bk_num = pending_doc.get("reschedule_booking_number")

        bk_number = "BK-" + "".join(random.choices(_str.digits, k=6))
        try:
            if reschedule_id:
                from bson import ObjectId
                await self.db.bookings.update_one(
                    {"_id": ObjectId(reschedule_id)},
                    {"$set": {
                        "status": "reschedule_requested",
                        "new_date": date_str,
                        "reschedule_requested_at": datetime.utcnow(),
                    }}
                )
                bk_number = reschedule_bk_num or bk_number
            else:
                await self.db.bookings.insert_one({
                    "user_id": user_id,
                    "customer_id": str(customer_id),
                    "service_name": svc_name,
                    "service_id": svc_id,
                    "price": svc_price,
                    "date": date_str,
                    "status": "pending",
                    "booking_number": bk_number,
                    "created_at": datetime.utcnow(),
                    "created_by": "customer",
                })
        except Exception as e:
            logger.error(f"[BookingAgent] booking create error: {e}")

        # Clear the date-input context so it doesn't fire again
        try:
            await self.db.pending_catalogs.update_one(
                {"customer_id": customer_id, "user_id": user_id},
                {"$set": {"action_context": None}}
            )
        except Exception:
            pass

        try:
            from ai_service import get_drafter
            ai = get_drafter()
            action_word = "reschedule request" if reschedule_id else "booking request"
            prompt = (
                f"You are a business owner on WhatsApp. A customer just sent their preferred date for a booking.\n\n"
                f"Customer: {customer_name}\nService: {svc_name}\nDate/time they gave: {date_str}\n"
                f"Booking ref: {bk_number}\nLanguage: {language}\n"
                f"Action: {'Reschedule for ref ' + str(reschedule_bk_num) if reschedule_id else 'New booking'}\n\n"
                f"Write a warm reply in {language} (2-3 sentences max):\n"
                f"1. Acknowledge their {action_word} for *{svc_name}* on *{date_str}*\n"
                f"2. Tell them a team member will confirm shortly and share the ref: *{bk_number}*\n"
                f"3. CRITICAL: NEVER say the booking is 'confirmed' — it is PENDING human review\n"
                f"4. WhatsApp tone — casual, warm\n"
                f"Output only the customer-facing message."
            )
            reply = await ai._call_llm(prompt, model_pref="standard")
        except Exception as e:
            logger.error(f"[BookingAgent] booking ack AI error: {e}")
            action_word = "reschedule" if reschedule_id else "booking"
            reply = (
                f"Got it {customer_name}! 🙏 Your {action_word} request for *{svc_name}* "
                f"on *{date_str}* has been received (Ref: *{bk_number}*).\n\n"
                f"We'll confirm your appointment shortly! 📅"
            )

        flag_reason = (
            f"Reschedule request: {svc_name} → new date {date_str} (Ref: {bk_number})"
            if reschedule_id else
            f"New booking request: {svc_name} on {date_str} (Ref: {bk_number})"
        )
        return {
            "handled": True,
            "messages": [{"text": reply}],
            "escalate": False,
            "flag_for_human": True,
            "flag_reason": flag_reason,
            "context_update": {
                "state": "ongoing",
                "last_intent": "BOOKING_REQUEST",
                "pending_booking_date_input": False,
            },
        }

    async def _handle_rental_dates_received(
        self, pending_doc: dict, ci_date, co_date, message: str,
        customer_name: str, language: str, currency: str,
        customer_id, user_id: str
    ) -> Dict[str, Any]:
        """
        Customer has provided check-in and check-out dates for a rental.
        Creates/updates a PENDING rental booking — never auto-confirms.
        """
        import random, string as _str
        svc_name = pending_doc.get("booking_service_name", "the listing")
        svc_id = pending_doc.get("booking_service_id", "")
        svc_price = pending_doc.get("booking_service_price", 0)
        price_unit = pending_doc.get("price_unit", "night")
        reschedule_id = pending_doc.get("reschedule_booking_id")
        reschedule_bk_num = pending_doc.get("reschedule_booking_number")

        nights = (co_date - ci_date).days
        if price_unit == "week":
            total = svc_price * max(1, round(nights / 7))
        elif price_unit == "month":
            total = svc_price * max(1, round(nights / 30))
        else:
            total = svc_price * nights
        total_str = f"{currency} {total:,.0f}" if total else ""
        ci_str = ci_date.strftime("%d %b %Y")
        co_str = co_date.strftime("%d %b %Y")

        bk_number = "BK-" + "".join(random.choices(_str.digits, k=6))
        try:
            if reschedule_id:
                from bson import ObjectId
                await self.db.bookings.update_one(
                    {"_id": ObjectId(reschedule_id)},
                    {"$set": {
                        "status": "reschedule_requested",
                        "checkin_date": str(ci_date),
                        "checkout_date": str(co_date),
                        "nights": nights,
                        "total_price": total,
                        "reschedule_requested_at": datetime.utcnow(),
                    }}
                )
                bk_number = reschedule_bk_num or bk_number
            else:
                await self.db.bookings.insert_one({
                    "user_id": user_id,
                    "customer_id": str(customer_id),
                    "service_name": svc_name,
                    "service_id": svc_id,
                    "price": svc_price,
                    "price_unit": price_unit,
                    "checkin_date": str(ci_date),
                    "checkout_date": str(co_date),
                    "nights": nights,
                    "total_price": total,
                    "status": "pending",
                    "booking_number": bk_number,
                    "created_at": datetime.utcnow(),
                    "created_by": "customer",
                })
        except Exception as e:
            logger.error(f"[BookingAgent] rental booking create error: {e}")

        # Clear context
        try:
            await self.db.pending_catalogs.update_one(
                {"customer_id": customer_id, "user_id": user_id},
                {"$set": {"action_context": None}}
            )
        except Exception:
            pass

        try:
            from ai_service import get_drafter
            ai = get_drafter()
            action_word = "reschedule request" if reschedule_id else "reservation request"
            prompt = (
                f"You are a business owner on WhatsApp. A customer just sent their stay dates for a rental.\n\n"
                f"Customer: {customer_name}\nListing: {svc_name}\n"
                f"Check-in: {ci_str}\nCheck-out: {co_str} ({nights} night{'s' if nights != 1 else ''})\n"
                f"Total: {total_str}\nRef: {bk_number}\nLanguage: {language}\n\n"
                f"Write a warm reply in {language} (2-3 sentences max):\n"
                f"1. Acknowledge their {action_word} for *{svc_name}*\n"
                f"2. Confirm the dates: *{ci_str}* → *{co_str}* and total if available\n"
                f"3. Say a team member will confirm shortly, share ref *{bk_number}*\n"
                f"4. CRITICAL: NEVER say 'confirmed' — it is PENDING human review\n"
                f"Output only the customer-facing message."
            )
            reply = await ai._call_llm(prompt, model_pref="standard")
        except Exception as e:
            logger.error(f"[BookingAgent] rental ack AI error: {e}")
            action_word = "change" if reschedule_id else "reservation"
            total_line = f" · Total: {total_str}" if total_str else ""
            reply = (
                f"Got it {customer_name}! 🏠 Your {action_word} request for *{svc_name}* "
                f"(*{ci_str}* → *{co_str}*{total_line}) has been received (Ref: *{bk_number}*).\n\n"
                f"We'll confirm your reservation shortly! 🙏"
            )

        flag_reason = (
            f"Rental reschedule: {svc_name} → new dates {ci_str} to {co_str} (Ref: {bk_number})"
            if reschedule_id else
            f"Rental reservation: {svc_name} {ci_str} to {co_str}, {nights} nights (Ref: {bk_number})"
        )
        return {
            "handled": True,
            "messages": [{"text": reply}],
            "escalate": False,
            "flag_for_human": True,
            "flag_reason": flag_reason,
            "context_update": {
                "state": "ongoing",
                "last_intent": "BOOKING_REQUEST",
                "pending_rental_dates_input": False,
                "checkin_date": None,
                "checkout_date": None,
                "nights": None,
            },
        }

    # ── Availability Check ────────────────────────────────────────────────────────

    def _parse_month_from_message(self, message: str):
        """Extract (year, month) from message. Returns tuple or None."""
        import re
        msg = message.lower()
        today = date.today()
        month_names = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        }
        if "next month" in msg:
            d = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
            return (d.year, d.month)
        if "this month" in msg:
            return (today.year, today.month)
        for mname, mnum in month_names.items():
            if re.search(rf'\b{mname}\b', msg):
                yr_m = re.search(r'\b(202\d)\b', msg)
                yr = int(yr_m.group(1)) if yr_m else (today.year if mnum >= today.month else today.year + 1)
                return (yr, mnum)
        return None

    @staticmethod
    def _compress_to_ranges(days: list) -> str:
        """Convert sorted list of ints to compact range string e.g. '1–7, 10–14'."""
        if not days:
            return ""
        ranges, start, end = [], days[0], days[0]
        for d in days[1:]:
            if d == end + 1:
                end = d
            else:
                ranges.append(str(start) if start == end else f"{start}–{end}")
                start = end = d
        ranges.append(str(start) if start == end else f"{start}–{end}")
        return ", ".join(ranges)

    def _parse_dates_from_message(self, message: str):
        """Extract up to two dates from a free-text message. Returns list of date objects."""
        import re
        found = []
        today = date.today()
        msg = message.lower()

        # ISO / dd-mm-yyyy / dd/mm/yyyy patterns first
        iso_pat = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', msg)
        for s in iso_pat:
            try: found.append(date.fromisoformat(s))
            except: pass

        dmy_pat = re.findall(r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})\b', msg)
        for d, m, y in dmy_pat:
            try:
                yr = int(y) + 2000 if len(y) == 2 else int(y)
                found.append(date(yr, int(m), int(d)))
            except: pass

        # Month-name patterns e.g. "20 march", "march 20"
        month_names = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                       "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                       "january":1,"february":2,"march":3,"april":4,"june":6,
                       "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
        for mname, mnum in month_names.items():
            m1 = re.search(rf'\b(\d{{1,2}})\s+{mname}\b', msg)
            m2 = re.search(rf'\b{mname}\s+(\d{{1,2}})\b', msg)
            m3 = re.search(rf'\b{mname}\s+(\d{{1,2}}),?\s*(\d{{4}})\b', msg)
            for pat in [m1, m2]:
                if pat:
                    try:
                        yr = today.year if date(today.year, mnum, int(pat.group(1))) >= today else today.year + 1
                        found.append(date(yr, mnum, int(pat.group(1))))
                    except: pass
            if m3:
                try: found.append(date(int(m3.group(2)), mnum, int(m3.group(1))))
                except: pass

        # Relative words
        if "tomorrow" in msg: found.append(today + timedelta(days=1))
        if "today" in msg: found.append(today)
        for kw, delta in [("next week", 7), ("this weekend", (5 - today.weekday()) % 7 or 7)]:
            if kw in msg: found.append(today + timedelta(days=delta))

        # Deduplicate and sort
        seen = set()
        result = []
        for d in sorted(found):
            if d not in seen and d >= today:
                seen.add(d); result.append(d)
        return result[:2]

    async def _handle_availability(
        self, services, business_hours, booking_settings,
        customer_name, language, currency, message,
        customer_id=None, user_id=None, is_rental=False
    ) -> Dict[str, Any]:
        weekday_map = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        messages_out = []

        # ── Rental: date-specific availability check ──────────────────────────
        if is_rental and services:
            parsed_dates = self._parse_dates_from_message(message)
            if len(parsed_dates) >= 2:
                ci_date, co_date = parsed_dates[0], parsed_dates[1]
                if co_date > ci_date:
                    nights = (co_date - ci_date).days
                    stay_dates = [str(ci_date + timedelta(days=i)) for i in range(nights)]
                    # Fetch global blocked dates
                    user_doc = await self.db.users.find_one({"_id": user_id})
                    global_blocked = set((user_doc or {}).get("settings", {}).get("rental_availability", []))

                    avail_listings = []
                    unavail_listings = []
                    for s in services:
                        listing_blocked = set(s.get("listing_blocked_dates", []))
                        all_blocked = global_blocked | listing_blocked
                        conflict = [d for d in stay_dates if d in all_blocked]
                        price = s.get("price", 0)
                        unit = s.get("price_unit", "night")
                        unit_label = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(unit, "night")
                        price_str = f"{currency} {price:,.0f}/" + unit_label if price else "Contact for price"
                        if unit == "week":
                            period_total = price * max(1, round(nights / 7))
                        elif unit == "month":
                            period_total = price * max(1, round(nights / 30))
                        elif unit == "year":
                            period_total = price * max(1, round(nights / 365))
                        elif unit == "person":
                            period_total = price  # base of 1 person
                        else:  # night or day — use days count
                            period_total = price * nights
                        total_str = f" · Total: {currency} {period_total:,.0f}" if price else ""
                        if conflict:
                            unavail_listings.append(f"❌ *{s['name']}* — not available ({', '.join(conflict[:2])}{'...' if len(conflict) > 2 else ''})")
                        else:
                            avail_listings.append(f"✅ *{s['name']}* — {price_str}{total_str}")

                    # Build numbered list of available listings only
                    avail_services = []
                    for s in services:
                        listing_blocked = set(s.get("listing_blocked_dates", []))
                        all_blocked = global_blocked | listing_blocked
                        conflict = [d for d in stay_dates if d in all_blocked]
                        if not conflict:
                            avail_services.append(s)

                    ci_str = ci_date.strftime("%d %b %Y")
                    co_str = co_date.strftime("%d %b %Y")
                    lines = [f"📅 *Availability: {ci_str} → {co_str} ({nights} night{'s' if nights != 1 else ''})*\n"]
                    if avail_listings:
                        lines.append("✅ *Available — select one to book:*")
                        for idx, s in enumerate(avail_services, 1):
                            price = s.get("price", 0)
                            unit = s.get("price_unit", "night")
                            unit_label = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(unit, "night")
                            price_str = f"{currency} {price:,.0f}/" + unit_label if price else "Contact for price"
                            if unit == "week":
                                period_total = price * max(1, round(nights / 7))
                            elif unit == "month":
                                period_total = price * max(1, round(nights / 30))
                            elif unit == "year":
                                period_total = price * max(1, round(nights / 365))
                            elif unit == "person":
                                period_total = price
                            else:
                                period_total = price * nights
                            total_str = f" · Total: {currency} {period_total:,.0f}" if price else ""
                            lines.append(f"{idx}\ufe0f\u20e3  *{s['name']}* — {price_str}{total_str}")
                    if unavail_listings:
                        lines.append("\n❌ *Not available for these dates:*")
                        lines.extend(unavail_listings)
                    if avail_listings:
                        lines.append("\n_Reply with the number to book_ 🏠")
                    else:
                        # 11.1: Fully booked — offer waitlist and next-available suggestion
                        lines.append(
                            "\n👋 *No listings are available for those exact dates.*\n"
                            "You can:\n"
                            "\u2022 Try *different dates* — reply with new check-in and check-out\n"
                            "\u2022 *Join our waitlist* — reply with \"waitlist\" and we'll notify you if a slot opens\n"
                            "\u2022 *Contact us directly* and we'll do our best to accommodate you 🙏"
                        )
                    messages_out.append({"text": "\n".join(lines)})

                    # Pre-load AVAILABLE listings into pending_catalogs for immediate booking
                    if customer_id and user_id and avail_services:
                        try:
                            await self.db.pending_catalogs.update_one(
                                {"customer_id": customer_id, "user_id": user_id},
                                {"$set": {
                                    "products": [
                                        {"id": str(s["_id"]), "name": s["name"], "price": s.get("price", 0),
                                         "duration": None, "index": idx,
                                         "service_category": "rental",
                                         "price_unit": s.get("price_unit", "night"),
                                         "addons": s.get("addons", []),
                                         "image_url": s.get("image_url", "")}
                                        for idx, s in enumerate(avail_services, 1)
                                    ],
                                    "action_context": "booking_service_select",
                                    "catalog_all_ids": [str(s["_id"]) for s in avail_services],
                                    "catalog_page_offset": 0,
                                    "catalog_has_more": False,
                                    "created_at": datetime.utcnow(),
                                }},
                                upsert=True
                            )
                        except Exception as e:
                            logger.error(f"[BookingAgent] availability catalog upsert: {e}")

                    # Build menu gate so customer can pick a listing by number
                    _avail_menu = {
                        str(i): {"name": s["name"], "price": s.get("price", 0), "id": str(s["_id"]),
                                 "type": "service", "service_category": "rental",
                                 "price_unit": s.get("price_unit", "night")}
                        for i, s in enumerate(avail_services, 1)
                    } if avail_services else {}
                    _avail_ctx = {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"}
                    if _avail_menu:
                        _avail_ctx.update({
                            "active_menu": True, "menu_type": "service_selection",
                            "menu_items": _avail_menu, "waiting_for_selection": True,
                            "menu_sent_at": datetime.utcnow().isoformat(),
                            "checkin_date": str(ci_date), "checkout_date": str(co_date), "nights": nights,
                        })
                    return {
                        "handled": True,
                        "messages": messages_out,
                        "escalate": False,
                        "context_update": _avail_ctx,
                    }

            # ── Rental: month-calendar availability view ──────────────────────
            import calendar as _cal
            month_result = self._parse_month_from_message(message)
            today = date.today()
            yr, mo = month_result if month_result else (today.year, today.month)
            days_in_month = _cal.monthrange(yr, mo)[1]
            month_label = date(yr, mo, 1).strftime("%B %Y")
            user_doc = await self.db.users.find_one({"_id": user_id})
            global_blocked = set((user_doc or {}).get("settings", {}).get("rental_availability", []))

            cal_lines = [f"📅 *Available Days — {month_label}*\n"]
            for s in services:
                listing_blocked = set(s.get("listing_blocked_dates", []))
                all_blocked = global_blocked | listing_blocked
                price = s.get("price", 0)
                unit = s.get("price_unit", "night")
                unit_label = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(unit, "night")
                price_str = f"{currency} {price:,.0f}/{unit_label}" if price else "Contact for price"
                cal_lines.append(f"🏠 *{s['name']}* — {price_str}")
                blocked_days = [d for d in range(1, days_in_month + 1)
                                if f"{yr:04d}-{mo:02d}-{d:02d}" in all_blocked]
                free_days = [d for d in range(1, days_in_month + 1)
                             if d not in blocked_days and date(yr, mo, d) >= today]
                if not blocked_days:
                    cal_lines.append("✅ Fully available this month!")
                else:
                    if free_days:
                        cal_lines.append(f"✅ Free: {self._compress_to_ranges(free_days)}")
                    if blocked_days:
                        cal_lines.append(f"❌ Blocked: {self._compress_to_ranges(blocked_days)}")
                cal_lines.append("")

            # Also show numbered listings for direct booking
            cal_lines.append("*Select a listing to book:*")
            for idx, s in enumerate(services, 1):
                price = s.get("price", 0)
                unit = s.get("price_unit", "night")
                unit_label = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(unit, "night")
                price_str = f"{currency} {price:,.0f}/{unit_label}" if price else "Contact for price"
                cal_lines.append(f"{idx}\ufe0f\u20e3  *{s['name']}* — {price_str}")
            cal_lines.append("\n_Reply with a number to book, or send check-in & check-out dates to check a specific range_ 🏠")
            messages_out.append({"text": "\n".join(cal_lines)})

            # Pre-load all listings for direct booking after calendar view
            if customer_id and user_id:
                try:
                    await self.db.pending_catalogs.update_one(
                        {"customer_id": customer_id, "user_id": user_id},
                        {"$set": {
                            "products": [
                                {"id": str(s["_id"]), "name": s["name"], "price": s.get("price", 0),
                                 "duration": None, "index": idx,
                                 "service_category": "rental",
                                 "price_unit": s.get("price_unit", "night"),
                                 "addons": s.get("addons", []),
                                 "image_url": s.get("image_url", "")}
                                for idx, s in enumerate(services, 1)
                            ],
                            "action_context": "booking_service_select",
                            "catalog_all_ids": [str(s["_id"]) for s in services],
                            "catalog_page_offset": 0,
                            "catalog_has_more": False,
                            "created_at": datetime.utcnow(),
                        }},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"[BookingAgent] month-cal catalog upsert: {e}")

            _cal_menu = {
                str(i): {"name": s["name"], "price": s.get("price", 0), "id": str(s["_id"]),
                         "type": "service", "service_category": "rental",
                         "price_unit": s.get("price_unit", "night")}
                for i, s in enumerate(services, 1)
            } if services else {}
            _cal_ctx = {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"}
            if _cal_menu:
                _cal_ctx.update({
                    "active_menu": True, "menu_type": "service_selection",
                    "menu_items": _cal_menu, "waiting_for_selection": True,
                    "menu_sent_at": datetime.utcnow().isoformat(),
                })
            return {
                "handled": True,
                "messages": messages_out,
                "escalate": False,
                "context_update": _cal_ctx,
            }

        # Schedule block — skip for rental businesses (they don't have open/close hours)
        if not is_rental:
            if business_hours:
                lines = ["\U0001f5d3\ufe0f *Our Availability*\n"]
                today = date.today()
                for i in range(7):
                    d = today + timedelta(days=i)
                    key = weekday_map[d.weekday()]
                    day_info = business_hours.get(key, {})
                    label = d.strftime("%A %d %b")
                    if day_info.get("closed", False) or not day_info:
                        lines.append(f"\u2022 {label}: _Closed_")
                    else:
                        open_t = day_info.get("open", "09:00")
                        close_t = day_info.get("close", "17:00")
                        lines.append(f"\u2022 {label}: {open_t} \u2013 {close_t}")
                messages_out.append({"text": "\n".join(lines)})
            else:
                messages_out.append({"text": "We're available Monday to Saturday. Contact us to confirm exact times."})

        # Numbered listings/services list — customer can select to book immediately
        if services:
            first_page = services[:PAGE_SIZE]
            if is_rental:
                svc_lines = ["\n🏠 *Our Listings — select one to book:*\n"]
                for i, s in enumerate(first_page, 1):
                    price = s.get("price", 0)
                    unit = s.get("price_unit", "night")
                    unit_label = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(unit, "night")
                    price_str = f"{currency} {price:,.0f}/" + unit_label if price else "Contact for price"
                    svc_lines.append(f"{i}\ufe0f\u20e3  *{s['name']}* \u2014 {price_str}")
            else:
                svc_lines = ["\n\U0001f4cb *Select a service to book:*\n"]
                for i, s in enumerate(first_page, 1):
                    price = s.get("price", 0)
                    dur = s.get("duration")
                    price_str = f"{currency} {price:,.0f}" if price else "Contact for price"
                    dur_str = f" · {dur} min" if dur else ""
                    svc_lines.append(f"{i}\ufe0f\u20e3  *{s['name']}* \u2014 {price_str}{dur_str}")
            svc_lines.append("\n_Reply with the number to book_")
            messages_out.append({"text": "\n".join(svc_lines)})

            # Save to pending_catalogs so numbered reply routes to booking flow
            if customer_id and user_id:
                try:
                    await self.db.pending_catalogs.update_one(
                        {"customer_id": customer_id, "user_id": user_id},
                        {"$set": {
                            "products": [
                                {"id": str(s["_id"]), "name": s["name"], "price": s.get("price", 0),
                                 "duration": s.get("duration"), "index": idx,
                                 "service_category": s.get("service_category", "appointment"),
                                 "addons": s.get("addons", []),
                                 "image_url": s.get("image_url", "")}
                                for idx, s in enumerate(first_page, 1)
                            ],
                            "action_context": "booking_service_select",
                            "catalog_all_ids": [str(s["_id"]) for s in services],
                            "catalog_page_offset": 0,
                            "catalog_has_more": len(services) > PAGE_SIZE,
                            "created_at": datetime.utcnow(),
                        }},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"[BookingAgent] availability catalog upsert: {e}")
        else:
            # 11.1: No services but still responding — soft CTA to contact
            messages_out.append({"text": (
                "_No slots are showing right now. Reply with \"waitlist\" to get notified when one opens, or contact us directly and we'll help you find the right time! 🙏_ "
                if is_rental else
                "_Reply with the service you'd like to book and we'll sort out a time!_ \U0001f4c5"
            )})

        # Build menu gate state so customer can immediately select a service by number
        _sched_menu = {}
        if services:
            _fp = services[:PAGE_SIZE]
            _sched_menu = {
                str(i): {"name": s["name"], "price": s.get("price", 0), "id": str(s["_id"]),
                         "type": "service", "duration": s.get("duration"),
                         "service_category": s.get("service_category", "appointment")}
                for i, s in enumerate(_fp, 1)
            }
        _sched_ctx = {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"}
        if _sched_menu:
            _sched_ctx.update({
                "active_menu": True, "menu_type": "service_selection",
                "menu_items": _sched_menu, "waiting_for_selection": True,
                "menu_sent_at": datetime.utcnow().isoformat(),
            })
        return {
            "handled": True,
            "messages": messages_out,
            "escalate": False,
            "context_update": _sched_ctx,
        }

    # ── Booking Status ───────────────────────────────────────────────────────────

    async def _handle_booking_status(
        self, customer_id, user_id, customer_name, language, currency, is_rental=False
    ) -> Dict[str, Any]:
        if not customer_id:
            return {
                "handled": True,
                "messages": [{"text": "I couldn't find your booking details. Please share your booking reference number."}],
                "escalate": False,
            }
        try:
            bookings = await self.db.bookings.find({
                "user_id": user_id,
                "customer_id": str(customer_id),
                "status": {"$in": ["pending", "confirmed"]},
            }).sort([("checkin_date", 1), ("date", 1)]).to_list(5)
        except Exception as e:
            logger.error(f"[BookingAgent] booking_status query error: {e}")
            bookings = []

        if not bookings:
            no_bk_msg = (
                f"Hi {customer_name}! \U0001f44b You don't have any upcoming reservations. Would you like to book a listing?"
                if is_rental else
                f"Hi {customer_name}! \U0001f44b You don't have any upcoming bookings. Would you like to book a service?"
            )
            return {
                "handled": True,
                "messages": [{"text": no_bk_msg}],
                "escalate": False,
            }

        lines = [f"\U0001f4c5 *Your Upcoming {'Reservations' if is_rental else 'Bookings'}*\n"]
        for i, b in enumerate(bookings, 1):
            status_emoji = "\u2705" if b.get("status") == "confirmed" else "\u23f3"
            if is_rental and b.get("checkin_date"):
                date_str = f"Check-in: {b.get('checkin_date', '')}" + (f" → {b.get('checkout_date', '')}" if b.get('checkout_date') else "")
            else:
                date_str = f"{b.get('date', '')} at {b.get('time', '')}"
            lines.append(
                f"*{i}.* {status_emoji} *{b.get('service_name', 'Listing')}*\n"
                f"   \U0001f4c6 {date_str}\n"
                f"   Ref: *{b.get('booking_number', '')}*  |  Status: {b.get('status', '').title()}"
            )

        lines.append("\n_Reply with a number to manage that booking_")

        # Save booking IDs to conversation state for numbered pick
        booking_ids = [str(b["_id"]) for b in bookings]
        context_update = {
            "state": "ongoing",
            "last_intent": "BOOKING_STATUS",
            "pending_booking_list": booking_ids,
            "pending_booking_action": None,
        }

        return {
            "handled": True,
            "messages": [{"text": "\n".join(lines)}],
            "escalate": False,
            "context_update": context_update,
        }

    # ── Booking Cancel / Reschedule ─────────────────────────────────────────────────────

    async def _handle_booking_cancel(
        self, customer_id, user_id, customer_name, language, message, is_rental=False
    ) -> Dict[str, Any]:
        if not customer_id:
            return {
                "handled": True,
                "messages": [{"text": "Please share your booking reference number (starts with BK-) and we'll cancel it for you."}],
                "escalate": False,
            }
        try:
            bookings = await self.db.bookings.find({
                "user_id": user_id,
                "customer_id": str(customer_id),
                "status": {"$in": ["pending", "confirmed"]},
            }).sort("date", 1).to_list(5)
        except Exception as e:
            logger.error(f"[BookingAgent] booking_cancel query error: {e}")
            bookings = []

        if not bookings:
            no_cancel_msg = (
                f"Hi {customer_name}! You don't have any active reservations to cancel. Would you like to book a new listing?"
                if is_rental else
                f"Hi {customer_name}! You don't have any active bookings to cancel. Would you like to book a new service?"
            )
            return {
                "handled": True,
                "messages": [{"text": no_cancel_msg}],
                "escalate": False,
            }

        lines = [f"Which {'reservation' if is_rental else 'booking'} would you like to change?\n"]
        for i, b in enumerate(bookings, 1):
            if is_rental and b.get("checkin_date"):
                date_str = f"Check-in: {b.get('checkin_date', '')}" + (f" → {b.get('checkout_date', '')}" if b.get('checkout_date') else "")
            else:
                date_str = f"{b.get('date', '')} at {b.get('time', '')}"
            lines.append(
                f"*{i}.* \U0001f4cc *{b.get('service_name', 'Listing')}*\n"
                f"   \U0001f4c6 {date_str}\n"
                f"   Ref: *{b.get('booking_number', '')}*"
            )
        lines.append("\n_Reply with the number (e.g. *1*) to select_")

        booking_ids = [str(b["_id"]) for b in bookings]
        return {
            "handled": True,
            "messages": [{"text": "\n".join(lines)}],
            "escalate": False,
            "context_update": {
                "state": "ongoing",
                "last_intent": "BOOKING_CANCEL",
                "pending_booking_list": booking_ids,
                "pending_booking_action": None,
            },
        }

    async def _show_booking_actions(
        self, booking: dict, customer_name: str, language: str, user_id: str, customer_id: str
    ) -> Dict[str, Any]:
        """Show 1=Cancel / 2=Reschedule for a selected booking."""
        from agents.conversation_state import save_state
        bk_num = booking.get("booking_number", "")
        svc = booking.get("service_name", "Service")
        # Support both rental (checkin/checkout) and service (date/time)
        if booking.get("checkin_date"):
            ci = booking.get("checkin_date", "")
            co = booking.get("checkout_date", "")
            date_str = f"Check-in: {ci}" + (f" → {co}" if co else "")
            reschedule_label = "Change dates"
        else:
            date_str = booking.get("date", "")
            time_str = booking.get("time", "")
            if time_str:
                date_str = f"{date_str} at {time_str}"
            reschedule_label = "Reschedule to a new date/time"
        await save_state(self.db, user_id, customer_id, {
            "pending_booking_action": str(booking["_id"]),
            "pending_booking_list": None,
        })
        return {
            "handled": True,
            "escalate": False,
            "messages": [{"text": (
                f"\U0001f4cc *{svc}* — {date_str}\n"
                f"Ref: *{bk_num}*\n\n"
                f"What would you like to do?\n"
                f"1\ufe0f\u20e3 Cancel this booking\n"
                f"2\ufe0f\u20e3 {reschedule_label}\n\n"
                f"_Reply with *1* or *2*_"
            )}],
        }

    async def _execute_cancel(
        self, booking: dict, customer_name: str, currency: str,
        language: str, user_id: str, customer_id: str
    ) -> Dict[str, Any]:
        """Cancel a booking self-service."""
        from agents.conversation_state import save_state
        bk_num = booking.get("booking_number", "")
        svc = booking.get("service_name", "Service")
        price = booking.get("price", 0)
        await self.db.bookings.update_one(
            {"_id": booking["_id"]},
            {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow(), "cancelled_by": "customer"}}
        )
        await save_state(self.db, user_id, customer_id, {
            "pending_booking_action": None,
            "pending_booking_list": None,
        })
        return {
            "handled": True,
            "escalate": False,
            "messages": [{"text": (
                f"\u2705 Booking *{bk_num}* (*{svc}*) has been cancelled.\n\n"
                f"If you'd like to rebook, just say *book* and we'll help you out! \U0001f60a"
            )}],
            "owner_notification": {
                "title": f"\u274c Booking {bk_num} Cancelled",
                "body": f"{customer_name} cancelled {svc} — {currency} {price:,.0f}",
            },
        }

    async def _start_reschedule(
        self, booking: dict, customer_name: str, currency: str,
        language: str, user_id: str, customer_id: str
    ) -> Dict[str, Any]:
        """Start reschedule flow — handles both services (single date) and rentals (check-in + check-out)."""
        bk_num = booking.get("booking_number", "")
        svc = booking.get("service_name", "Service")
        svc_id = booking.get("service_id", "")
        price = booking.get("price", 0)
        is_rental_bk = bool(booking.get("checkin_date"))
        from agents.conversation_state import save_state

        if is_rental_bk:
            # Rental reschedule — need new check-in AND check-out
            action_context = "rental_dates_input"
            ask_msg = (
                f"Let's change your reservation for *{svc}* (Ref: *{bk_num}*).\n\n"
                f"🏠 *What are your new check-in and check-out dates?*\n"
                f"_Reply with both dates, e.g. *15 April to 20 April* or *15/04 - 20/04*_"
            )
        else:
            action_context = "booking_date_input"
            ask_msg = (
                f"Let's reschedule *{svc}* (Ref: *{bk_num}*).\n\n"
                f"📅 *What new date would you like?*\n"
                f"_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*, or *2026-03-15*_"
            )

        await save_state(self.db, user_id, customer_id, {
            "pending_booking_action": None,
            "pending_booking_list": None,
            # Set the right override flag so router sends next message to BookingAgent
            "pending_booking_date_input": not is_rental_bk,
            "pending_rental_dates_input": is_rental_bk,
        })
        try:
            await self.db.pending_catalogs.update_one(
                {"customer_id": customer_id, "user_id": user_id},
                {"$set": {
                    "action_context": action_context,
                    "booking_service_id": svc_id,
                    "booking_service_name": svc,
                    "booking_service_price": price,
                    "reschedule_booking_id": str(booking["_id"]),
                    "reschedule_booking_number": bk_num,
                    "updated_at": datetime.utcnow(),
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"[BookingAgent] reschedule context error: {e}")
        return {
            "handled": True,
            "escalate": False,
            "messages": [{"text": ask_msg}],
        }

    # ── Helpers ─────────────────────────────────────────────────────────────────

    async def _ai_intro(
        self, message, customer_name, language, business_knowledge, history,
        is_rental=False, intent="BOOKING_REQUEST", confidence=1.0, careful_instruction="",
        active_context: Optional[str] = None
    ) -> dict:
        """
        Single AI call that returns three pieces needed to build the services/listings message:
          - intro : 1-2 sentence warm human reply to the customer
          - header: the list header ("Our Services" / "Our Listings") in their language
          - footer: the instruction line ("Reply with a number to book") in their language

        Falls back to ui_strings.t() if the AI call fails — no English hardcoding.
        """
        from .ui_strings import t as _t
        import json as _json, re as _re

        fallback_header = _t("listings_header" if is_rental else "services_header", language)
        fallback_footer = _t("rental_select_instruction" if is_rental else "book_number_instruction", language)

        try:
            from ai_service import get_drafter
            ai = get_drafter()
            bk = (business_knowledge or "")[:300]
            intent_hint = (
                f"Intent classified as: {intent} ({confidence:.0%} confidence)\n"
                f"Customer message: \"{message}\"\n\n"
                f"Read the message yourself. If the classification seems off, address what the customer actually needs instead.\n"
            )
            if careful_instruction:
                intent_hint += f"\n{careful_instruction}\n"
            context_note = ""
            if active_context:
                context_note = f"\n⚠️ CONTEXT: The user is currently in the middle of a booking, at the '{active_context}' step. "
                if active_context == "booking_date_input":
                    context_note += "They were just asked for a DATE. "
                elif active_context == "booking_service_select":
                    context_note += "They were just asked to SELECT A SERVICE from a list. "
                elif active_context == "booking_time_select":
                    context_note += "They were just asked to SELECT A TIME slot. "
                context_note += "Acknowledge their message naturally and, if they didn't provide the info needed, gently guide them back to this step."

            listing_type = "rental/property listings" if is_rental else "services/appointments"
            prompt = (
                f"{intent_hint}{context_note}"
                f"You are a business owner on WhatsApp. A customer wants to see your {listing_type}.\n"
                f"Business info: {bk}\n\n"
                f"Respond in: {language}\n\n"
                f"Return ONLY valid JSON with exactly these 3 keys:\n"
                f'{{\n'
                f'  "intro": "1-2 sentence warm human reply in {language}. Match their energy. '
                f'Never confirm a booking. No corporate tone. Think: what would a real business owner text back?",\n'
                f'  "header": "A short bold title for the {listing_type} list — in {language}. '
                f'With a relevant emoji. E.g. in English: \'📋 *Our Services*\'. In Swahili: \'📋 *Huduma Zetu*\'.",\n'
                f'  "footer": "A short instruction line in {language} telling the customer to reply with a number to select. '
                f'In italics (wrap in _underscores_). Natural, informal. E.g. \'_Jibu na namba kuchagua_\' or \'_Reply with a number_\'"\n'
                f'}}\n\n'
                f"JSON only. No markdown fences."
            )
            raw = await ai._call_llm(prompt, model_pref="standard")
            match = _re.search(r'\{.*\}', raw, _re.DOTALL)
            if match:
                data = _json.loads(match.group())
                return {
                    "intro": (data.get("intro") or "").strip(),
                    "header": (data.get("header") or fallback_header).strip(),
                    "footer": (data.get("footer") or fallback_footer).strip(),
                }
        except Exception as e:
            logger.error(f"[BookingAgent] AI intro error: {e}")

        return {"intro": None, "header": fallback_header, "footer": fallback_footer}

    async def _handle_off_script(
        self, message: str, customer_name: str, language: str,
        business_knowledge: str, business_hours: str,
        history, services, currency: str,
        step: str, step_hint: str,
    ) -> Dict[str, Any]:
        """
        A customer said something off-script during an active booking step
        (asked about price, hours, availability, anything).
        Answer their actual question naturally, then bring them back to where they were.
        Never go silent. Never be robotic.
        """
        try:
            from ai_service import get_drafter
            ai = get_drafter()

            _bk = (business_knowledge or "")[:600]
            _hrs = (business_hours or "")[:200]
            _hist = ""
            if history:
                _recent = history[-6:] if len(history) > 6 else history
                _hist = "\n".join(f"{'Customer' if m.get('role')=='user' else 'You'}: {m.get('content','')}" for m in _recent)

            _svc_list = ""
            if services:
                _svc_list = ", ".join(s.get("name","") for s in services[:6])

            prompt = f"""You are a business owner replying on WhatsApp to {customer_name}.
You're helping them book. Mid-booking, they asked: "{message}"

Business info: {_bk}
Hours: {_hrs}
Services/products: {_svc_list}
Currency: {currency}

Recent chat:
{_hist}

Instructions:
- Answer their question directly and honestly. Be natural, brief, warm.
- {step_hint}
- Do NOT repeat the full menu or list. Just answer + one soft nudge back.
- No bullet lists unless the question needs one. No corporate tone.
- Reply in: {language}
- 1-3 sentences max unless the question genuinely needs more.

Output only the WhatsApp reply. Nothing else."""

            reply = await ai._call_llm(prompt, model_pref="standard")
            reply = (reply or "").strip().strip('"').strip()
            if not reply:
                raise ValueError("Empty AI reply")

            logger.info(f"[BookingAgent] off-script reply (step={step}): {reply[:80]}")
            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": False,
                "context_update": {"state": "ongoing"},
            }
        except Exception as e:
            logger.error(f"[BookingAgent] _handle_off_script error: {e}")
            # Hard fallback — never go silent
            return {
                "handled": True,
                "messages": [{"text": f"Sorry, I didn't quite catch that — could you let me know what you'd like to book? 😊"}],
                "escalate": False,
            }

    async def _handle_customer_chat(
        self, message, intent, customer_name, language,
        business_knowledge, history, currency, context
    ) -> Dict[str, Any]:
        """Contact-Aware Routing: Handles small talk from KNOWN_CUSTOMERs by pivoting to a soft service offer."""
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            bk = (business_knowledge or "")[:300]
            
            prompt = f"""You are a business owner replying on WhatsApp to a known customer: {customer_name}.
They just sent a casual message or greeting: "{message}"

Business info: {bk}

Output only the customer-facing message. Think: what would a real salon/clinic owner say when a regular walks in and says hi?

Rules:
- Be warm and genuinely human — match their energy and language exactly.
- Acknowledge their greeting naturally first (1 short line).
- Then ask ONE open question: what can you help them with today, or are they looking to book something.
- Do NOT immediately list services or push the booking menu — wait for them to respond.
- Max 2 sentences. Pure WhatsApp tone — casual and real.
- Language: {language}
- CRITICAL: NEVER confirm or imply any booking or appointment has been made."""

            reply = await ai._call_llm(prompt, model_pref="standard")
            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": False,
                "context_update": {
                    "state": "ongoing",
                    "last_intent": intent,
                    # If customer replies "yes/sure/ok", route them to booking instead of ChatAgent
                    "waiting_for_service_request": True,
                    "preferred_language": language,
                },
            }
        except Exception as e:
            logger.error(f"[BookingAgent] customer_chat handler error: {e}")
            return {
                "handled": True,
                "messages": [{"text": f"Hi {customer_name}! 😊 How can I help you today? Are you looking to book something?"}],
                "escalate": False,
                "context_update": {
                    "state": "ongoing",
                    "last_intent": intent,
                    "waiting_for_service_request": True,
                    "preferred_language": language,
                },
            }

