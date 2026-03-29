import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from whatsapp_service import get_whatsapp_service

logger = logging.getLogger(__name__)

async def process_reminders(db: AsyncIOMotorDatabase):
    """
    Scans for upcoming confirmed bookings and sends reminders via WhatsApp.
    Intervals: 24h and 2h before the appointment.
    """
    now = datetime.utcnow()
    ws = get_whatsapp_service(db)
    
    # 1. FETCH UPCOMING BOOKINGS
    # We fetch bookings that are coming up and missing at least one reminder
    upcoming = await db.bookings.find({
        "status": {"$in": ["confirmed", "pending"]},
        "$or": [
            {"reminder_sent_24h": {"$ne": True}},
            {"reminder_sent_1h": {"$ne": True}}, # Support old 1h field
            {"reminder_sent_2h": {"$ne": True}},
        ]
    }).to_list(100)

    for booking in upcoming:
        try:
            date_str = booking.get("date", "")
            time_str = booking.get("time", "")
            if not date_str or not time_str:
                continue
            
            # Skip rental/creator logic for now or handle appropriately
            if time_str in ("check-in", "check-out"):
                continue

            # Parse booking datetime
            try:
                booking_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue

            diff_hours = (booking_dt - now).total_seconds() / 3600
            
            user_id = booking.get("user_id")
            customer_phone = booking.get("customer_phone")
            customer_name = booking.get("customer_name", "there")
            service_name = booking.get("service_name", "appointment")
            booking_number = booking.get("booking_number", "")

            if not user_id or not customer_phone:
                continue

            # 24h REMINDER: 23-25 hours before
            if not booking.get("reminder_sent_24h") and 23.0 <= diff_hours <= 25.5:
                msg = (
                    f"Hi {customer_name}! \U0001f44b Just a reminder that your *{service_name}* "
                    f"is scheduled for *tomorrow at {time_str}* \U0001f4c5\n\n"
                    f"Ref: *{booking_number}*\n"
                    f"_Reply to reschedule or cancel_"
                )
                if await ws.send_message(user_id=user_id, to_number=customer_phone, message=msg, customer_name=customer_name, send_context="booking_reminder"):
                    await db.bookings.update_one(
                        {"_id": booking["_id"]},
                        {"$set": {"reminder_sent_24h": True, "reminder_sent_24h_at": now}}
                    )
                    logger.info(f"[Reminders] Sent 24h reminder to {customer_phone}")

            # 2h REMINDER: 1.5-3.0 hours before
            elif not booking.get("reminder_sent_2h") and not booking.get("reminder_sent_1h") and 1.5 <= diff_hours <= 3.0:
                msg = (
                    f"Hi {customer_name}! \u23f0 Your *{service_name}* starts in *about 2 hours* "
                    f"({time_str}) today \U0001f4c5\n\n"
                    f"Ref: *{booking_number}*\n"
                    f"See you soon! \U0001f60a"
                )
                if await ws.send_message(user_id=user_id, to_number=customer_phone, message=msg, customer_name=customer_name, send_context="booking_reminder"):
                    await db.bookings.update_one(
                        {"_id": booking["_id"]},
                        {"$set": {"reminder_sent_2h": True, "reminder_sent_2h_at": now}}
                    )
                    logger.info(f"[Reminders] Sent 2h reminder to {customer_phone}")

        except Exception as e:
            logger.error(f"Error processing booking {booking.get('_id')}: {e}")
