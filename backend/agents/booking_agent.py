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
        business_type = (context.get("business_type") or "").lower().strip()
        is_rental = business_type == "rental"  # will also check services below after fetch
        confidence = context.get("confidence", 1.0)
        careful_instruction = context.get("careful_instruction", "")

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

        # Fetch services - exclude only explicitly physical/retail products
        # Safety net: also include any product with duration set (bookable service)
        # even if wrongly tagged as offering_type=product by the startup migration
        try:
            services = await self.db.products.find({
                "user_id": user_id,
                "in_stock": {"$ne": False},
                "$or": [
                    {"offering_type": {"$nin": ["physical", "retail", "product"]}},
                    {"offering_type": "product", "duration": {"$exists": True, "$ne": None}},
                ],
            }).to_list(50)
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

        # Upgrade is_rental if any fetched service is a rental listing
        if not is_rental and any(s.get("service_category") == "rental" for s in services):
            is_rental = True

        if intent == "AVAILABILITY_CHECK":
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

        # Default: BOOKING_REQUEST
        return await self._handle_booking_request(
            services, business_hours, booking_settings, customer_name, language, currency,
            message, business_knowledge, history, customer_id, user_id, is_rental,
            intent=intent, confidence=confidence, careful_instruction=careful_instruction,
        )

    # ── Booking Request ────────────────────────────────────────────────────────

    async def _handle_booking_request(
        self, services, business_hours, booking_settings,
        customer_name, language, currency, message,
        business_knowledge, history, customer_id, user_id, is_rental=False,
        intent="BOOKING_REQUEST", confidence=1.0, careful_instruction="",
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

        # Build numbered listing/services list
        if is_rental:
            lines = ["🏠 *Our Listings*\n"]
            for i, s in enumerate(first_page, 1):
                price = s.get("price", 0)
                unit = s.get("price_unit", "night")
                unit_label = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(unit, "night")
                price_str = f"{currency} {price:,.0f}/" + unit_label if price else "Contact for price"
                desc = s.get("description", "")
                desc_str = f" · {desc[:50]}" if desc else ""
                lines.append(f"{i}️⃣  *{s['name']}* — {price_str}{desc_str}")
            if has_more:
                lines.append(f"9️⃣  ➡️ *See more listings*")
            lines.append("\n_Reply with the number of the listing you'd like to book_")
        else:
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
        intro = await self._ai_intro(
            message, customer_name, language, business_knowledge, history, is_rental,
            intent=intent, confidence=confidence, careful_instruction=careful_instruction,
        )
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

                    return {
                        "handled": True,
                        "messages": messages_out,
                        "escalate": False,
                        "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
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

            return {
                "handled": True,
                "messages": messages_out,
                "escalate": False,
                "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
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

        return {
            "handled": True,
            "messages": messages_out,
            "escalate": False,
            "context_update": {"state": "ongoing", "last_intent": "AVAILABILITY_CHECK"},
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
            }).sort("date", 1).to_list(5)
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

    async def _ai_intro(
        self, message, customer_name, language, business_knowledge, history,
        is_rental=False, intent="BOOKING_REQUEST", confidence=1.0, careful_instruction="",
    ) -> Optional[str]:
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
            if is_rental:
                prompt = (
                    f"{intent_hint}"
                    f"Customer is looking to book a rental/property. Business: {bk}. "
                    f"Think one sentence about what this customer actually needs, then write 1 warm short line in {language} "
                    f"welcoming them to browse listings (WhatsApp tone, no bullet points). Output only the customer-facing message."
                )
            else:
                prompt = (
                    f"{intent_hint}"
                    f"Customer wants to book a service. Business: {bk}. "
                    f"Think one sentence about what this customer actually needs, then write 1 warm short line in {language} "
                    f"(WhatsApp tone, no bullet points). Output only the customer-facing message."
                )
            intro = await ai._call_llm(prompt, model_pref="standard")
            if intro and len(intro.strip()) < 120:
                return intro.strip()
        except Exception as e:
            logger.error(f"[BookingAgent] AI intro error: {e}")
        return None
