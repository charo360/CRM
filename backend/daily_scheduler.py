"""
Daily Notification Scheduler
Runs AI analysis and sends push notifications at scheduled times
"""
import asyncio
import logging
import uuid
from datetime import datetime, time
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient
from daily_analyzer import DailyCustomerAnalyzer
from notification_service import get_notification_service
import os

logger = logging.getLogger(__name__)


class DailyScheduler:
    """Scheduler for daily customer analysis and notifications"""
    
    def __init__(self, db):
        self.db = db
        self.notification_service = get_notification_service()
        self.analyzer = DailyCustomerAnalyzer(db)
        self.running = False
    
    async def send_daily_notifications(self):
        """Send daily notifications to all users"""
        logger.info("Starting daily notification send...")
        
        # Get all users with push tokens and notifications enabled
        users = await self.db.users.find({
            "push_token": {"$exists": True, "$ne": None},
            "settings.notification_enabled": {"$ne": False}  # Default to enabled
        }).to_list(1000)
        
        logger.info(f"Found {len(users)} users with push notifications enabled")
        
        sent_count = 0
        for user in users:
            try:
                user_id = user["_id"]
                push_token = user.get("push_token")
                
                if not push_token or not push_token.startswith('ExponentPushToken'):
                    continue
                
                # Get user's timezone (default to UTC if not set)
                settings = user.get("settings", {})
                user_timezone = settings.get("timezone", "UTC")
                daily_alert_count = settings.get("daily_alert_count", 5)
                
                # Check if it's time to send notification for this user's timezone
                from datetime import timezone as tz
                import pytz
                
                try:
                    user_tz = pytz.timezone(user_timezone)
                    user_now = datetime.now(user_tz)
                    user_hour = user_now.hour
                    
                    # Check if current hour matches any notification time (with 1-hour window)
                    notification_hours = settings.get("notification_times", [8, 13, 18])
                    should_notify = user_hour in notification_hours
                    
                    if not should_notify:
                        continue  # Skip this user, not their notification time
                        
                except Exception as e:
                    logger.warning(f"Invalid timezone {user_timezone} for user {user_id}, using UTC")
                    user_tz = pytz.UTC
                
                # Run analysis for this user if not already done today
                today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                existing_analysis = await self.db.customer_analysis.find_one({
                    "user_id": user_id,
                    "analysis_date": {"$gte": today}
                })
                
                if not existing_analysis:
                    logger.info(f"Running analysis for user {user_id}")
                    await self.analyzer.analyze_all_customers(user_id)
                
                # Get today's insights
                insights = await self.analyzer.get_todays_insights(user_id, limit=daily_alert_count)
                
                if not insights:
                    logger.info(f"No insights for user {user_id}")
                    continue
                
                # Send notification
                success = await self.notification_service.send_daily_insights_notification(
                    push_token=push_token,
                    insights=insights,
                    count=min(3, len(insights))  # Show top 3 in notification
                )
                
                if success:
                    # Mark insights as notified
                    customer_ids = [i['customer_id'] for i in insights]
                    await self.db.customer_analysis.update_many(
                        {
                            "user_id": user_id,
                            "customer_id": {"$in": customer_ids},
                            "analysis_date": {"$gte": today}
                        },
                        {"$set": {"notification_sent": True}}
                    )
                    sent_count += 1
                    logger.info(f"Sent notification to user {user_id}")
                
            except Exception as e:
                logger.error(f"Error sending notification to user {user.get('_id')}: {e}")
                continue
        
        logger.info(f"Daily notifications complete. Sent to {sent_count}/{len(users)} users")
        return sent_count
    
    
    async def check_due_followups(self):
        """Check for follow-up reminders that are due and notify the owner"""
        try:
            now = datetime.utcnow()
            from datetime import timedelta
            # Fire from 5 minutes before to 5 minutes after the reminder time
            window_start = now - timedelta(minutes=5)
            window_end = now + timedelta(minutes=5)

            due_followups = await self.db.followups.find({
                "status": "pending",
                "reminder_date": {"$gte": window_start, "$lt": window_end},
                "notified": {"$ne": True},
            }).to_list(500)

            if not due_followups:
                return

            logger.info(f"Found {len(due_followups)} due follow-up reminders")

            from whatsapp_service import WhatsAppService
            import os
            wa_service = WhatsAppService(
                self.db,
                base_url=os.environ.get("EVOLUTION_API_URL", "http://localhost:8080"),
                api_key=os.environ.get("EVOLUTION_API_KEY", ""),
            )

            for followup in due_followups:
                try:
                    user_id = followup["user_id"]
                    user = await self.db.users.find_one({"_id": user_id})
                    if not user:
                        continue

                    customer_name = followup.get("customer_name", "a contact")
                    customer_phone = followup.get("customer_phone", "")
                    note = followup.get("message") or ""
                    ftype = followup.get("type", "call")

                    type_emoji = {"call": "📞", "whatsapp": "💬", "meeting": "🤝", "email": "📧"}.get(ftype, "🔔")

                    msg = (
                        f"{type_emoji} *Follow-up Reminder*\n\n"
                        f"👤 *{customer_name}*"
                        + (f"\n📱 {customer_phone}" if customer_phone else "")
                        + (f"\n\n📝 _{note}_" if note else "")
                        + f"\n\nOpen your CRM app to take action."
                    )

                    # 1. WhatsApp notification to owner
                    owner_phone = user.get("phone_number") or user.get("whatsapp", {}).get("phone_number")
                    if owner_phone:
                        try:
                            await wa_service.send_message(
                                user_id=user_id,
                                to_number=owner_phone,
                                message=msg,
                                send_context="auto_reply",
                            )
                            logger.info(f"Follow-up WhatsApp sent to owner for {customer_name}")
                        except Exception as e:
                            logger.warning(f"Follow-up WhatsApp failed: {e}")

                    # 2. Expo push notification
                    push_tokens = user.get("push_tokens", [])
                    if not push_tokens and user.get("push_token"):
                        push_tokens = [user["push_token"]]
                    if push_tokens:
                        try:
                            import httpx
                            messages = [
                                {
                                    "to": token,
                                    "title": f"{type_emoji} Follow-up: {customer_name}",
                                    "body": note or f"Time to {ftype} {customer_name}",
                                    "data": {"type": "followup", "customer_name": customer_name},
                                    "sound": "default",
                                    "priority": "high",
                                }
                                for token in push_tokens
                                if token.startswith("ExponentPushToken") or token.startswith("ExpoPushToken")
                            ]
                            if messages:
                                async with httpx.AsyncClient(timeout=10) as client:
                                    await client.post(
                                        "https://exp.host/--/api/v2/push/send",
                                        json=messages,
                                        headers={"Content-Type": "application/json"},
                                    )
                                logger.info(f"Follow-up push sent for {customer_name}")
                        except Exception as e:
                            logger.warning(f"Follow-up push failed: {e}")

                    # Mark as notified so it doesn't fire again
                    await self.db.followups.update_one(
                        {"_id": followup["_id"]},
                        {"$set": {"notified": True, "notified_at": now}}
                    )

                except Exception as e:
                    logger.error(f"Error processing follow-up {followup.get('_id')}: {e}")

        except Exception as e:
            logger.error(f"Error in check_due_followups: {e}")

    async def run_auto_sequences(self):
        """
        Auto-sequence: at day 3 and day 7 after a customer's first contact,
        create a pending follow-up with an AI-drafted WhatsApp message.
        Owner reviews and edits in the Follow-ups screen before sending.
        """
        import uuid as _uuid
        from datetime import timedelta

        now = datetime.utcnow()

        for sequence_day in [3, 7]:
            # Window: customers who joined between (day-0.25) and (day+0.25) days ago
            # This gives a 6-hour window so we catch them even if the scheduler runs hourly
            window_start = now - timedelta(days=sequence_day, hours=6)
            window_end = now - timedelta(days=sequence_day) + timedelta(hours=6)

            try:
                # Find real customers (not just contacts) created in this window
                candidates = await self.db.customers.find({
                    "is_customer": True,
                    "created_at": {"$gte": window_start, "$lte": window_end},
                }).to_list(200)

                logger.info(f"[AutoSequence] Day {sequence_day}: found {len(candidates)} candidates")

                for customer in candidates:
                    try:
                        user_id = customer["user_id"]
                        customer_id = str(customer["_id"])

                        # Skip if auto-sequence already created for this customer at this day
                        existing = await self.db.followups.find_one({
                            "user_id": user_id,
                            "customer_id": customer_id,
                            "is_auto_sequence": True,
                            "sequence_day": sequence_day,
                        })
                        if existing:
                            continue

                        # Get business owner settings
                        user = await self.db.users.find_one({"_id": user_id})
                        if not user:
                            continue

                        # Draft message via AI
                        draft_msg = await self._draft_sequence_message(
                            user, customer, sequence_day
                        )

                        # Create follow-up due in 1 hour (appears as "today" for the owner)
                        followup_id = str(_uuid.uuid4())
                        reminder_date = now + timedelta(hours=1)

                        await self.db.followups.insert_one({
                            "_id": followup_id,
                            "user_id": user_id,
                            "customer_id": customer_id,
                            "reminder_date": reminder_date,
                            "message": draft_msg,
                            "status": "pending",
                            "type": "whatsapp",
                            "is_auto_sequence": True,
                            "sequence_day": sequence_day,
                            "created_at": now,
                        })

                        logger.info(
                            f"[AutoSequence] Created day-{sequence_day} draft for "
                            f"customer {customer_id} (user {user_id})"
                        )

                        # Push notification to owner
                        try:
                            push_tokens = user.get("push_tokens", [])
                            if not push_tokens and user.get("push_token"):
                                push_tokens = [user["push_token"]]
                            if push_tokens:
                                import httpx
                                messages = [
                                    {
                                        "to": token,
                                        "title": f"💬 Day-{sequence_day} follow-up ready — {customer.get('name', 'Customer')}",
                                        "body": "AI drafted a message. Tap to review and send.",
                                        "data": {
                                            "type": "auto_sequence",
                                            "followup_id": followup_id,
                                            "customer_id": customer_id,
                                        },
                                        "sound": "default",
                                    }
                                    for token in push_tokens
                                    if token.startswith("ExponentPushToken") or token.startswith("ExpoPushToken")
                                ]
                                if messages:
                                    async with httpx.AsyncClient(timeout=10) as client:
                                        await client.post(
                                            "https://exp.host/--/api/v2/push/send",
                                            json=messages,
                                            headers={"Content-Type": "application/json"},
                                        )
                        except Exception as e:
                            logger.warning(f"[AutoSequence] Push notification failed: {e}")

                    except Exception as e:
                        logger.error(
                            f"[AutoSequence] Error processing customer "
                            f"{customer.get('_id')}: {e}"
                        )

            except Exception as e:
                logger.error(f"[AutoSequence] Day {sequence_day} batch failed: {e}")

    async def _draft_sequence_message(self, user: dict, customer: dict, day: int) -> str:
        """
        Draft a follow-up message for the customer.
        - If no business knowledge is configured, returns a safe generic template (no AI call).
        - If business knowledge exists, uses AI but with strict no-hallucination rules.
        """
        customer_name = customer.get("name", "there")
        business_name = user.get("business_name") or user.get("name") or ""

        bk = user.get("business_knowledge", {})
        business_desc = (bk.get("business_description", "") if isinstance(bk, dict) else "").strip()
        products = (bk.get("products_services", "") if isinstance(bk, dict) else "").strip()
        last_message = (customer.get("last_message") or "").strip()

        has_business_context = bool(business_desc or products)

        # No business knowledge configured — use safe generic templates, no AI
        if not has_business_context:
            if day == 3:
                return (
                    f"Hi {customer_name}! 👋 Just checking in — did you have any questions "
                    f"from when we last spoke? Happy to help anytime!"
                )
            else:
                return (
                    f"Hi {customer_name}! 😊 Just a quick follow-up — we're still here "
                    f"whenever you're ready. Feel free to reach out!"
                )

        # Business knowledge exists — call AI with strict constraints
        try:
            context_lines = []
            if business_name:
                context_lines.append(f"Business name: {business_name}")
            if business_desc:
                context_lines.append(f"What we do: {business_desc}")
            if products:
                context_lines.append(f"Products/Services: {products}")
            if last_message:
                context_lines.append(f"Customer's last message: {last_message[:200]}")
            context = "\n".join(context_lines)

            if day == 3:
                goal = (
                    "Write a short, warm WhatsApp check-in for a customer who contacted us 3 days ago. "
                    "Ask if they have any questions and keep it friendly. Max 2 sentences."
                )
            else:
                goal = (
                    "Write a short, friendly WhatsApp follow-up for a customer who contacted us 7 days ago. "
                    "Gently let them know we're still available. Max 2 sentences."
                )

            prompt = f"""You are writing a WhatsApp follow-up message on behalf of a business.

{context}

Customer name: {customer_name}

Task: {goal}

STRICT RULES — failure to follow these ruins the message:
- ONLY use the business details listed above. NEVER invent products, prices, offers, or services.
- If no products/offers are listed above, do NOT mention any products or offers.
- Do NOT make up discounts, promotions, or deals unless explicitly listed above.
- Keep it short, human, and WhatsApp-friendly.

Output only the message text. No explanation."""

            from ai_service import get_drafter
            ai = get_drafter()
            reply = await ai._call_llm(prompt, model_pref="standard")
            return reply.strip()

        except Exception as e:
            logger.error(f"[AutoSequence] AI draft failed: {e}")
            # Safe fallback — no invented details
            if day == 3:
                return (
                    f"Hi {customer_name}! 👋 Just checking in — did you have any questions "
                    f"from when we last spoke? Happy to help anytime!"
                )
            else:
                return (
                    f"Hi {customer_name}! 😊 Just a quick follow-up — we're still here "
                    f"whenever you're ready. Feel free to reach out!"
                )

    async def run_scheduler(self, check_interval_minutes: int = 60):
        """
        Run the scheduler in a loop, checking every hour for users who need notifications.
        Follow-up reminders are checked every 15 minutes.
        """
        self.running = True
        logger.info(f"Scheduler started. Will check for notifications every {check_interval_minutes} minutes")
        logger.info("Notifications will be sent based on each user's local timezone")

        followup_check_interval = 15 * 60  # 15 minutes in seconds
        seconds_since_followup_check = followup_check_interval  # check immediately on start

        while self.running:
            try:
                # Check due follow-ups every 15 minutes
                if seconds_since_followup_check >= followup_check_interval:
                    await self.check_due_followups()
                    seconds_since_followup_check = 0

                # Run auto-sequences every scheduler cycle
                try:
                    await self.run_auto_sequences()
                except Exception as e:
                    logger.error(f"Error in auto sequences: {e}")

                # Run hourly tasks
                await self.send_daily_notifications()

                # Run order payment reminders
                try:
                    from server import send_order_payment_reminders
                    await send_order_payment_reminders()
                except Exception as e:
                    logger.error(f"Error sending order reminders: {e}")

                # Wait for next check
                wait_seconds = check_interval_minutes * 60
                logger.info(f"Next check in {check_interval_minutes} minutes")
                await asyncio.sleep(wait_seconds)
                seconds_since_followup_check += wait_seconds

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(600)
                seconds_since_followup_check += 600
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Scheduler stopped")


# Global scheduler instance
_scheduler = None

async def get_scheduler(db) -> DailyScheduler:
    """Get or create scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = DailyScheduler(db)
    return _scheduler


async def start_daily_scheduler(db, check_interval_minutes: int = 60):
    """
    Start the daily scheduler in the background
    
    Args:
        db: MongoDB database instance
        check_interval_minutes: How often to check for notifications (default: 60 minutes)
    """
    scheduler = await get_scheduler(db)
    
    # Run in background task
    asyncio.create_task(scheduler.run_scheduler(check_interval_minutes))
    logger.info(f"Timezone-aware scheduler started - checking every {check_interval_minutes} minutes")
