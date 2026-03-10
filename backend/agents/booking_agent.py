from .base_agent import BaseAgent
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


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

        # Fetch services (offering_type = service, class, etc.)
        try:
            services = await self.db.products.find({
                "user_id": user_id,
                "in_stock": True,
                "offering_type": {"$in": ["service", "class", "appointment", "consultation"]},
            }).to_list(50)

            # If no typed services, fall back to all products (retail business trying to book)
            if not services:
                services = await self.db.products.find(
                    {"user_id": user_id, "in_stock": True}
                ).to_list(50)
        except Exception as e:
            logger.error(f"[BookingAgent] DB error fetching services: {e}")
            return {"handled": False}

        # Fetch user settings for business_hours and booking_settings
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
                services, business_hours, booking_settings, customer_name, language, currency, message
            )

        if intent == "BOOKING_STATUS":
            return await self._handle_booking_status(
                customer_id, user_id, customer_name, language, currency
            )

        if intent == "BOOKING_CANCEL":
            return await self._handle_booking_cancel(
                customer_id, user_id, customer_name, language, message
            )

        # Default: BOOKING_REQUEST — show services and prompt to book
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

        # Build services list
        lines = ["📋 *Our Services*\n"]
        for i, s in enumerate(services[:8], 1):
            price = s.get("price", 0)
            duration = s.get("duration")
            price_str = f"{currency} {price:,.0f}" if price else "Contact for price"
            dur_str = f" · {duration} min" if duration else ""
            lines.append(f"{i}. *{s['name']}* — {price_str}{dur_str}")

        lines.append("\n_Reply with the number of the service you'd like to book_")
        services_text = "\n".join(lines)

        # AI intro
        intro = await self._ai_intro(message, customer_name, language, business_knowledge, history)
        messages_out = []
        if intro:
            messages_out.append({"text": intro})
        messages_out.append({"text": services_text})

        # Store services in pending_catalogs for numbered reply
        if customer_id and services:
            try:
                await self.db.pending_catalogs.update_one(
                    {"customer_id": customer_id, "user_id": user_id},
                    {"$set": {
                        "products": [
                            {"id": str(s["_id"]), "name": s["name"], "price": s.get("price", 0), "index": idx}
                            for idx, s in enumerate(services[:8], 1)
                        ],
                        "action_context": "booking_service_select",
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

    # ── Availability Check ─────────────────────────────────────────────────────

    async def _handle_availability(
        self, services, business_hours, booking_settings,
        customer_name, language, currency, message
    ) -> Dict[str, Any]:
        if not business_hours:
            return {
                "handled": True,
                "messages": [{"text": "Please contact us directly to check available times — we'll be happy to help!"}],
                "escalate": False,
            }

        weekday_map = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        day_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        lines = ["🗓️ *Our Availability*\n"]
        today = date.today()
        for i in range(7):
            d = today + timedelta(days=i)
            key = weekday_map[d.weekday()]
            day_info = business_hours.get(key, {})
            label = d.strftime("%A %d %b")
            if day_info.get("closed", False) or not day_info:
                lines.append(f"• {label}: Closed")
            else:
                open_t = day_info.get("open", "09:00")
                close_t = day_info.get("close", "17:00")
                lines.append(f"• {label}: {open_t} – {close_t}")

        lines.append("\n_Reply with the service you'd like to book and preferred date/time_")

        if services:
            lines.append("\n*Services available:*")
            for s in services[:5]:
                dur = f" ({s['duration']} min)" if s.get("duration") else ""
                lines.append(f"  • {s['name']}{dur}")

        return {
            "handled": True,
            "messages": [{"text": "\n".join(lines)}],
            "escalate": False,
            "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
        }

    # ── Booking Status ──────────────────────────────────────────────────────────

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
                "messages": [{"text": f"Hi {customer_name}! You don't have any upcoming bookings with us. Would you like to book a service?"}],
                "escalate": False,
            }

        lines = [f"📅 *Your Upcoming Bookings*\n"]
        for b in bookings:
            status_emoji = "✅" if b.get("status") == "confirmed" else "⏳"
            lines.append(
                f"{status_emoji} *{b.get('service_name', 'Service')}*\n"
                f"   📆 {b.get('date', '')} at {b.get('time', '')}\n"
                f"   Ref: {b.get('booking_number', '')}\n"
                f"   Status: {b.get('status', '').title()}"
            )

        lines.append("\n_Reply with your booking reference to cancel or reschedule_")

        return {
            "handled": True,
            "messages": [{"text": "\n".join(lines)}],
            "escalate": False,
            "context_update": {"state": "ongoing", "last_intent": "BOOKING_STATUS"},
        }

    # ── Booking Cancel / Reschedule ─────────────────────────────────────────────

    async def _handle_booking_cancel(
        self, customer_id, user_id, customer_name, language, message
    ) -> Dict[str, Any]:
        return {
            "handled": True,
            "messages": [{
                "text": (
                    f"To cancel or reschedule your booking, please share your booking reference number "
                    f"(starts with BK-) and we'll take care of it right away. 😊"
                )
            }],
            "escalate": False,
            "flag_for_human": True,
            "flag_reason": "Customer wants to cancel/reschedule a booking",
            "context_update": {"state": "ongoing", "last_intent": "BOOKING_CANCEL"},
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
