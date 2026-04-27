import logging
from datetime import datetime, date as _date, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from whatsapp_service import get_whatsapp_service

logger = logging.getLogger(__name__)

async def process_reminders(db: AsyncIOMotorDatabase):
    """
    Scans for upcoming confirmed/pending bookings and sends WhatsApp reminders.
    Regular bookings: 24h and 2h before appointment.
    Hotel/rental (checkin_date): 24h before check-in and on check-in day morning.
    """
    now = datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    ws = get_whatsapp_service(db)

    upcoming = await db.bookings.find({
        "status": {"$in": ["confirmed", "pending"]},
        "$or": [
            {"reminder_sent_24h": {"$ne": True}},
            {"reminder_sent_2h": {"$ne": True}},
            {"reminder_sent_checkin_day": {"$ne": True}},
        ]
    }).to_list(200)

    for booking in upcoming:
        try:
            user_id = booking.get("user_id")
            customer_phone = booking.get("customer_phone")
            customer_name = booking.get("customer_name", "there")
            service_name = booking.get("service_name", "appointment")
            booking_number = booking.get("booking_number", "")

            if not user_id or not customer_phone:
                continue

            checkin_str = booking.get("checkin_date", "")
            checkout_str = booking.get("checkout_date", "")
            is_stay = bool(checkin_str and checkout_str)

            # ── HOTEL / RENTAL (check-in / check-out) ────────────────────────
            if is_stay:
                try:
                    checkin_dt = datetime.strptime(checkin_str, "%Y-%m-%d")
                except ValueError:
                    continue

                diff_hours = (checkin_dt - now).total_seconds() / 3600

                # 24h before check-in (23–25 h window)
                if not booking.get("reminder_sent_24h") and 23.0 <= diff_hours <= 25.5:
                    msg = (
                        f"Hi {customer_name}! 👋 Just a reminder — your *{service_name}* "
                        f"check-in is *tomorrow* 📅\n\n"
                        f"📥 Check-in: *{checkin_str}*\n"
                        f"📤 Check-out: *{checkout_str}*\n"
                        f"Ref: *{booking_number}*\n\n"
                        f"_Reply to reschedule or cancel_"
                    )
                    if await ws.send_message(user_id=user_id, to_number=customer_phone, message=msg,
                                             customer_name=customer_name, send_context="booking_reminder"):
                        await db.bookings.update_one(
                            {"_id": booking["_id"]},
                            {"$set": {"reminder_sent_24h": True, "reminder_sent_24h_at": now}}
                        )
                        logger.info(f"[Reminders] Sent 24h check-in reminder to {customer_phone}")

                # Check-in day morning (0–10 h window, i.e. same day before 10 AM)
                elif not booking.get("reminder_sent_checkin_day") and 0 <= diff_hours < 10:
                    msg = (
                        f"Hi {customer_name}! 🏨 Today is your check-in day for *{service_name}*! 🎉\n\n"
                        f"📥 Check-in: *{checkin_str}*\n"
                        f"📤 Check-out: *{checkout_str}*\n"
                        f"Ref: *{booking_number}*\n\n"
                        f"We look forward to welcoming you! 😊"
                    )
                    if await ws.send_message(user_id=user_id, to_number=customer_phone, message=msg,
                                             customer_name=customer_name, send_context="booking_reminder"):
                        await db.bookings.update_one(
                            {"_id": booking["_id"]},
                            {"$set": {"reminder_sent_checkin_day": True, "reminder_sent_checkin_day_at": now}}
                        )
                        logger.info(f"[Reminders] Sent check-in day reminder to {customer_phone}")
                continue  # skip regular-booking logic for stays

            # ── REGULAR BOOKINGS (date + time) ────────────────────────────────
            date_str = booking.get("date", "")
            time_str = booking.get("time", "")
            if not date_str or not time_str:
                continue

            # Normalise time — skip unparseable values
            time_str = time_str.strip()
            if not time_str or ":" not in time_str:
                continue

            try:
                booking_dt = datetime.strptime(f"{date_str} {time_str[:5]}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue

            diff_hours = (booking_dt - now).total_seconds() / 3600

            # 24h reminder (23–25.5 h window)
            if not booking.get("reminder_sent_24h") and 23.0 <= diff_hours <= 25.5:
                msg = (
                    f"Hi {customer_name}! 👋 Just a reminder that your *{service_name}* "
                    f"is scheduled for *tomorrow at {time_str[:5]}* 📅\n\n"
                    f"Ref: *{booking_number}*\n"
                    f"_Reply to reschedule or cancel_"
                )
                if await ws.send_message(user_id=user_id, to_number=customer_phone, message=msg,
                                         customer_name=customer_name, send_context="booking_reminder"):
                    await db.bookings.update_one(
                        {"_id": booking["_id"]},
                        {"$set": {"reminder_sent_24h": True, "reminder_sent_24h_at": now}}
                    )
                    logger.info(f"[Reminders] Sent 24h reminder to {customer_phone}")

            # 2h reminder (1.5–3 h window)
            elif (not booking.get("reminder_sent_2h") and not booking.get("reminder_sent_1h")
                  and 1.5 <= diff_hours <= 3.0):
                msg = (
                    f"Hi {customer_name}! ⏰ Your *{service_name}* starts in *about 2 hours* "
                    f"({time_str[:5]}) today 📅\n\n"
                    f"Ref: *{booking_number}*\n"
                    f"See you soon! 😊"
                )
                if await ws.send_message(user_id=user_id, to_number=customer_phone, message=msg,
                                         customer_name=customer_name, send_context="booking_reminder"):
                    await db.bookings.update_one(
                        {"_id": booking["_id"]},
                        {"$set": {"reminder_sent_2h": True, "reminder_sent_2h_at": now}}
                    )
                    logger.info(f"[Reminders] Sent 2h reminder to {customer_phone}")

        except Exception as e:
            logger.error(f"[Reminders] Error processing booking {booking.get('_id')}: {e}")
