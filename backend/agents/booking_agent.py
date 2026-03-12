from .base_agent import BaseAgent
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
        intent = context.get("intent", "BOOKING_REQUEST")
        language = context.get("language", "English")
        currency = context.get("currency", "USD")
        customer_name = context.get("customer_name", "there")
        business_knowledge = context.get("business_knowledge", "")
        history = context.get("history", [])
        customer_id = context.get("customer_id")
        conv_state = context.get("conversation_state_data", {})

        # ── Handle pending_booking_action: 1=Cancel / 2=Reschedule pick ──────
        pending_booking_action_id = conv_state.get("pending_booking_action")
        if pending_booking_action_id:
            pick = PICK_NUMBER_RE.match(message.strip())
            if pick:
                choice = int(pick.group(1))
                bk = await self.db.bookings.find_one({"_id": pending_booking_action_id})
                if bk:
                    if choice == 1:
                        return await self._execute_cancel(
                            bk, customer_name, currency, language, user_id, customer_id
                        )
                    elif choice == 2:
                        return await self._start_reschedule(
                            bk, customer_name, currency, language, user_id, customer_id
                        )

        # ── Handle pending_booking_list: customer picking a booking by number ─
        pending_booking_ids = conv_state.get("pending_booking_list")
        if pending_booking_ids:
            pick = PICK_NUMBER_RE.match(message.strip())
            if pick:
                pick_idx = int(pick.group(1)) - 1
                if 0 <= pick_idx < len(pending_booking_ids):
                    bk = await self.db.bookings.find_one({"_id": pending_booking_ids[pick_idx]})
                    if bk:
                        return await self._show_booking_actions(bk, customer_name, language, user_id, customer_id)

        # Fetch services
        try:
            services = await self.db.products.find({
                "user_id": user_id,
                "in_stock": True,
                "offering_type": {"$in": ["service", "class", "appointment", "consultation"]},
            }).to_list(50)
            if not services:
                services = await self.db.products.find(
                    {"user_id": user_id, "in_stock": True}
                ).to_list(50)
        except Exception as e:
            logger.error(f"[BookingAgent] DB error fetching services: {e}")
            return {"handled": False}

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

        if intent == "AVAILABILITY_CHECK":
            return await self._handle_availability(
                services, business_hours, booking_settings, customer_name, language, currency, message, customer_id, user_id
            )

        if intent in ("BOOKING_STATUS", "RESCHEDULE"):
            return await self._handle_booking_status(
                customer_id, user_id, customer_name, language, currency
            )

        if intent == "BOOKING_CANCEL":
            return await self._handle_booking_cancel(
                customer_id, user_id, customer_name, language, message
            )

        # Default: BOOKING_REQUEST
        return await self._handle_booking_request(
            services, business_hours, booking_settings, customer_name, language, currency,
            message, business_knowledge, history, customer_id, user_id
        )

    # ── Booking Request ────────────────────────────────────────────────────────

    async def _handle_booking_request(
        self, services, business_hours, booking_settings,
        customer_name, language, currency, message,
        business_knowledge, history, customer_id, user_id
    ) -> Dict[str, Any]:
        if not services:
            return {
                "handled": True,
                "messages": [{"text": "We don't have any services listed yet. Please check back soon or contact us directly!"}],
                "escalate": False,
            }

        first_page = services[:PAGE_SIZE]
        has_more = len(services) > PAGE_SIZE

        # Build numbered services list
        lines = ["📋 *Our Services*\n"]
        for i, s in enumerate(first_page, 1):
            price = s.get("price", 0)
            duration = s.get("duration")
            price_str = f"{currency} {price:,.0f}" if price else "Contact for price"
            dur_str = f" · {duration} min" if duration else ""
            lines.append(f"{i}️⃣  *{s['name']}* — {price_str}{dur_str}")
        if has_more:
            lines.append(f"9️⃣  ➡️ *See more services*")
        lines.append("\n_Reply with the number of the service you'd like to book_")
        services_text = "\n".join(lines)

        # AI intro
        intro = await self._ai_intro(message, customer_name, language, business_knowledge, history)
        messages_out = []
        if intro:
            messages_out.append({"text": intro})
        messages_out.append({"text": services_text})

        # Store in pending_catalogs for numbered reply
        if customer_id and first_page:
            try:
                await self.db.pending_catalogs.update_one(
                    {"customer_id": customer_id, "user_id": user_id},
                    {"$set": {
                        "products": [
                            {"id": str(s["_id"]), "name": s["name"], "price": s.get("price", 0),
                             "duration": s.get("duration"), "index": idx}
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

        return {
            "handled": True,
            "messages": messages_out,
            "escalate": False,
            "context_update": {"state": "ongoing", "last_intent": "BOOKING_REQUEST"},
        }

    # ── Availability Check ────────────────────────────────────────────────────────

    async def _handle_availability(
        self, services, business_hours, booking_settings,
        customer_name, language, currency, message,
        customer_id=None, user_id=None
    ) -> Dict[str, Any]:
        weekday_map = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        messages_out = []

        # Schedule block
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

        # Numbered services list — customer can select to book immediately
        if services:
            first_page = services[:PAGE_SIZE]
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
                                 "duration": s.get("duration"), "index": idx}
                                for idx, s in enumerate(first_page, 1)
                            ],
                            "action_context": "booking_service_select",
                            "created_at": datetime.utcnow(),
                        }},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"[BookingAgent] availability catalog upsert: {e}")
        else:
            messages_out.append({"text": "_Reply with the service you'd like to book and we'll sort out a time!_ \U0001f4c5"})

        return {
            "handled": True,
            "messages": messages_out,
            "escalate": False,
            "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
        }

    # ── Booking Status ───────────────────────────────────────────────────────────

    async def _handle_booking_status(
        self, customer_id, user_id, customer_name, language, currency
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
            }).sort("date", 1).to_list(5)
        except Exception as e:
            logger.error(f"[BookingAgent] booking_status query error: {e}")
            bookings = []

        if not bookings:
            return {
                "handled": True,
                "messages": [{"text": f"Hi {customer_name}! \U0001f44b You don't have any upcoming bookings. Would you like to book a service?"}],
                "escalate": False,
            }

        lines = [f"\U0001f4c5 *Your Upcoming Bookings*\n"]
        for i, b in enumerate(bookings, 1):
            status_emoji = "\u2705" if b.get("status") == "confirmed" else "\u23f3"
            lines.append(
                f"*{i}.* {status_emoji} *{b.get('service_name', 'Service')}*\n"
                f"   \U0001f4c6 {b.get('date', '')} at {b.get('time', '')}\n"
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
        self, customer_id, user_id, customer_name, language, message
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
            return {
                "handled": True,
                "messages": [{"text": f"Hi {customer_name}! You don't have any active bookings to cancel. Would you like to book a new service?"}],
                "escalate": False,
            }

        lines = [f"Which booking would you like to change?\n"]
        for i, b in enumerate(bookings, 1):
            lines.append(
                f"*{i}.* \U0001f4cc *{b.get('service_name', 'Service')}*\n"
                f"   \U0001f4c6 {b.get('date', '')} at {b.get('time', '')}\n"
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
        date_str = booking.get("date", "")
        time_str = booking.get("time", "")
        await save_state(self.db, user_id, customer_id, {
            "pending_booking_action": str(booking["_id"]),
            "pending_booking_list": None,
        })
        return {
            "handled": True,
            "escalate": False,
            "messages": [{"text": (
                f"\U0001f4cc *{svc}* — {date_str} at {time_str}\n"
                f"Ref: *{bk_num}*\n\n"
                f"What would you like to do?\n"
                f"1\ufe0f\u20e3 Cancel this booking\n"
                f"2\ufe0f\u20e3 Reschedule to a new date/time\n\n"
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
        """Start reschedule flow — reuse booking_date_input context."""
        bk_num = booking.get("booking_number", "")
        svc = booking.get("service_name", "Service")
        svc_id = booking.get("service_id", "")
        price = booking.get("price", 0)
        from agents.conversation_state import save_state
        await save_state(self.db, user_id, customer_id, {
            "pending_booking_action": None,
            "pending_booking_list": None,
        })
        # Set pending_catalogs to booking_date_input so server.py date handler picks it up
        try:
            await self.db.pending_catalogs.update_one(
                {"customer_id": customer_id, "user_id": user_id},
                {"$set": {
                    "action_context": "booking_date_input",
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
            "messages": [{"text": (
                f"Let's reschedule *{svc}* (Ref: *{bk_num}*).\n\n"
                f"\U0001f4c5 *What new date would you like?*\n"
                f"_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*, or *2026-03-15*_"
            )}],
        }

    # ── Helpers ─────────────────────────────────────────────────────────────────

    async def _ai_intro(self, message, customer_name, language, business_knowledge, history) -> Optional[str]:
        try:
            from ai_service import get_drafter
            ai = get_drafter()
            bk = (business_knowledge or "")[:300]
            prompt = (
                f"Customer wants to book a service. Business: {bk}. "
                f"Write 1 warm short line in {language} (WhatsApp tone, no bullet points). Reply:"
            )
            intro = await ai._call_llm(prompt, model_pref="standard")
            if intro and len(intro.strip()) < 120:
                return intro.strip()
        except Exception as e:
            logger.error(f"[BookingAgent] AI intro error: {e}")
        return None
