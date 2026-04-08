"""
Daily Customer Analyzer
Analyzes all customers daily and identifies who needs attention.

Urgency tiers:
  critical  (score 80-100) — unanswered message, asked a question, 24h-3d window
  high      (score 50-79)  — VIP/Returning going cold, 3-14 days no reply
  normal    (score 20-49)  — new customer never contacted, 14-30 days no reply
  low       (<20)          — old import, no conversation, skip

Daily cap (to avoid overwhelming the user):
  - ALL critical shown (never hide an unanswered message)
  - Up to 10 high shown today, rest queued for tomorrow
  - Up to 5 normal shown today, rest spread over next 3 days
  => Max ~20 per day for large accounts
"""
import asyncio
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
from ai_service import get_drafter

logger = logging.getLogger(__name__)


class DailyCustomerAnalyzer:
    """Analyzes customers daily and generates insights"""

    def __init__(self, db):
        self.db = db
        self.drafter = get_drafter()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def analyze_all_customers(self, user_id: str) -> List[Dict]:
        """
        Analyse all customers, score them, apply daily caps, queue overflow.
        Returns today's visible list sorted by urgency.
        """
        try:
            logger.info(f"[Analyzer] Starting analysis for user {user_id}")

            customers = await self.db.customers.find({
                "user_id": user_id,
                "$or": [
                    {"is_customer": True},
                    {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}
                ],
            }).sort("last_owner_reply", 1).to_list(500)

            if not customers:
                return []

            user = await self.db.users.find_one({"_id": user_id})
            business_name = user.get("business_name", "Your Business") if user else "Your Business"

            # Score every customer
            all_analyses = []
            for customer in customers:
                try:
                    analysis = await self._analyze_customer(customer, business_name)
                    if analysis:
                        all_analyses.append(analysis)
                except Exception as e:
                    logger.error(f"[Analyzer] Error on customer {customer['_id']}: {e}")

            all_analyses.sort(key=lambda x: x["urgency_score"], reverse=True)

            # Split into tiers
            critical = [a for a in all_analyses if a["urgency_score"] >= 80]
            high     = [a for a in all_analyses if 50 <= a["urgency_score"] < 80]
            normal   = [a for a in all_analyses if 20 <= a["urgency_score"] < 50]

            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            # Assign show_date — critical always today, others capped and queued
            MAX_HIGH   = 10
            MAX_NORMAL = 5

            to_store = []

            # All critical → today
            for a in critical:
                a["show_date"] = today
                to_store.append(a)

            # High — today's batch + queue overflow across next days
            for i, a in enumerate(high):
                day_offset = i // MAX_HIGH  # 0 today, 1 tomorrow, etc.
                a["show_date"] = today + timedelta(days=day_offset)
                to_store.append(a)

            # Normal — spread across days after high overflow
            high_days = math.ceil(len(high) / MAX_HIGH) if high else 0
            for i, a in enumerate(normal):
                day_offset = high_days + (i // MAX_NORMAL)
                a["show_date"] = today + timedelta(days=day_offset)
                to_store.append(a)

            if to_store:
                await self._store_analyses(user_id, to_store)

            today_visible = [a for a in to_store if a["show_date"] <= today]
            logger.info(
                f"[Analyzer] {user_id}: {len(critical)} critical, "
                f"{len(high)} high, {len(normal)} normal. "
                f"Showing {len(today_visible)} today."
            )
            return today_visible

        except Exception as e:
            logger.error(f"[Analyzer] Failed for user {user_id}: {e}")
            return []

    async def analyze_single_customer(self, customer_id: str, user_id: str) -> Dict:
        customer = await self.db.customers.find_one({"_id": customer_id, "user_id": user_id})
        if not customer:
            return None
        user = await self.db.users.find_one({"_id": user_id})
        business_name = user.get("business_name", "Your Business") if user else "Your Business"
        return await self._analyze_customer(customer, business_name)

    async def get_todays_insights(self, user_id: str, limit: int = 10) -> List[Dict]:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        analyses = await self.db.customer_analysis.find({
            "user_id": user_id,
            "show_date": {"$gte": today, "$lt": tomorrow},
        }).sort("urgency_score", -1).limit(limit).to_list(limit)
        return analyses

    # ------------------------------------------------------------------ #
    #  Scoring
    # ------------------------------------------------------------------ #

    async def _analyze_customer(self, customer: Dict, business_name: str) -> Optional[Dict]:
        customer_id = customer["_id"]

        messages = await self.db.messages.find({
            "customer_id": customer_id,
            "user_id": customer.get("user_id"),
        }).sort("created_at", -1).limit(10).to_list(10)
        messages = list(reversed(messages))

        has_pending_followup = await self.db.followups.find_one({
            "customer_id": customer_id,
            "status": "pending",
            "is_auto_sequence": {"$ne": True},
        }) is not None

        urgency_score = self._calculate_urgency_score(customer, messages, has_pending_followup)

        if urgency_score < 20:
            return None

        ai_result = await self.drafter.draft_followup_message(
            customer_name=customer["name"],
            customer_data=customer,
            messages=messages,
            business_name=business_name,
            tone="friendly",
        )

        return {
            "user_id": customer["user_id"],
            "customer_id": customer_id,
            "customer_name": customer["name"],
            "customer_phone": customer["phone_number"],
            "analysis_date": datetime.utcnow(),
            "show_date": None,  # filled by caller
            "urgency_score": urgency_score,
            "urgency_level": self._get_urgency_level(urgency_score),
            "ai_reason": ai_result["ai_reason"],
            "suggested_action": self._get_suggested_action(customer, messages),
            "drafted_message": ai_result["drafted_message"],
            "conversation_summary": self._summarize_conversation(messages),
            "last_topic": self._get_last_topic(messages),
            "has_pending_followup": has_pending_followup,
            "notification_sent": False,
            "days_since_contact": self._get_days_since_owner_reply(customer),
        }

    def _calculate_urgency_score(self, customer: Dict, messages: List[Dict], has_pending_followup: bool) -> int:
        score = 0
        has_conversation = len(messages) > 0
        customer_initiated = any(m.get("direction") == "incoming" for m in messages)
        auto_created = customer.get("auto_created", False)

        created_at = customer.get("created_at")
        days_since_created = None
        if created_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            days_since_created = (datetime.utcnow() - created_at).days

        # --- Factor 1: Conversation quality ---
        if customer_initiated:
            score += 50   # They reached out — highest priority
        elif has_conversation:
            score += 30
        elif auto_created:
            score += 20
        elif days_since_created is not None and days_since_created <= 7:
            score += 35   # Newly added, reach out soon
        else:
            score += 5    # Old import, never engaged

        # --- Factor 2: Time since OWNER last replied (uses hours for sub-day precision) ---
        hours_since = self._get_hours_since_owner_reply(customer)

        if has_conversation:
            if hours_since is None:
                score += 35   # Never replied to this customer
            elif hours_since <= 24:
                score += 45   # Within 24h — critical window
            elif hours_since <= 72:
                score += 35   # 3 days — important
            elif hours_since <= 168:
                score += 20   # 1 week
            elif hours_since <= 336:
                score += 12   # 2 weeks
            elif hours_since <= 720:
                score += 7    # 30 days
        else:
            if days_since_created is not None and days_since_created <= 7:
                score += 15
            else:
                score += 3

        # --- Factor 3: Customer value ---
        tags = customer.get("tags", [])
        if "VIP" in tags:
            score += 25
        elif "Returning" in tags:
            score += 15
        elif "New" in tags and has_conversation:
            score += 10

        purchase_count = customer.get("purchase_count", 0)
        if purchase_count > 10:
            score += 10
        elif purchase_count > 5:
            score += 5

        # --- Factor 4: Unanswered message / question ---
        if messages:
            last_msg = messages[-1]
            if last_msg.get("direction") == "incoming":
                score += 20   # They messaged last — needs reply
            content = last_msg.get("content", "").lower()
            question_words = ["?", "how much", "price", "cost", "when", "where", "can you", "bei", "available"]
            if any(w in content for w in question_words):
                score += 20   # Unanswered question

        # --- Factor 5: Already has reminder — de-prioritise ---
        if has_pending_followup:
            score -= 30

        # --- Factor 6: Hot lead — multiple unanswered incoming messages ---
        if messages:
            # Count consecutive incoming messages at the end (unanswered streak)
            unanswered_streak = 0
            for msg in reversed(messages):
                if msg.get("direction") == "incoming":
                    unanswered_streak += 1
                else:
                    break
            if unanswered_streak >= 3:
                score += 25   # Hot lead — messaged 3+ times with no reply
            elif unanswered_streak == 2:
                score += 10

        return max(0, min(100, score))

    def _get_days_since_owner_reply(self, customer: Dict) -> Optional[int]:
        """Days since the owner last sent a message. Uses last_owner_reply."""
        last_reply = customer.get("last_owner_reply")
        if not last_reply:
            return None
        if isinstance(last_reply, str):
            last_reply = datetime.fromisoformat(last_reply.replace("Z", "+00:00"))
        return (datetime.utcnow() - last_reply).days

    def _get_hours_since_owner_reply(self, customer: Dict) -> Optional[float]:
        """Hours since the owner last sent a message."""
        last_reply = customer.get("last_owner_reply")
        if not last_reply:
            return None
        if isinstance(last_reply, str):
            last_reply = datetime.fromisoformat(last_reply.replace("Z", "+00:00"))
        delta = datetime.utcnow() - last_reply
        return delta.total_seconds() / 3600

    def _get_urgency_level(self, score: int) -> str:
        if score >= 80:
            return "critical"
        elif score >= 50:
            return "high"
        elif score >= 20:
            return "normal"
        return "low"

    def _get_suggested_action(self, customer: Dict, messages: List[Dict]) -> str:
        days_since = self._get_days_since_owner_reply(customer)
        if messages and messages[-1].get("direction") == "incoming":
            return "Reply to their message"
        if days_since is None:
            return "Send first message"
        if days_since <= 1:
            return "24h check-in"
        if days_since <= 3:
            return "3-day follow-up"
        if days_since > 30:
            return "Re-engage with special offer"
        tags = customer.get("tags", [])
        if "VIP" in tags:
            return "Check in and maintain relationship"
        return "Send follow-up message"

    def _summarize_conversation(self, messages: List[Dict]) -> str:
        if not messages:
            return "No previous conversation"
        last = messages[-1]
        direction = "They" if last.get("direction") == "incoming" else "You"
        content = last.get("content", "")[:50]
        return f"{len(messages)} messages. Last: {direction} said \"{content}...\""

    def _get_last_topic(self, messages: List[Dict]) -> str:
        if not messages:
            return "No conversation"
        recent = messages[-3:] if len(messages) > 3 else messages
        topics = {
            "pricing": ["price", "cost", "how much", "bei"],
            "product": ["product", "item", "stock"],
            "delivery": ["deliver", "shipping", "send"],
            "complaint": ["problem", "issue", "not working"],
        }
        for msg in reversed(recent):
            content = msg.get("content", "").lower()
            for topic, keywords in topics.items():
                if any(kw in content for kw in keywords):
                    return topic.capitalize()
        return "General inquiry"

    # ------------------------------------------------------------------ #
    #  Storage
    # ------------------------------------------------------------------ #

    async def _store_analyses(self, user_id: str, analyses: List[Dict]):
        if not analyses:
            return
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        # Delete only today's existing analyses — keep future queued ones
        await self.db.customer_analysis.delete_many({
            "user_id": user_id,
            "analysis_date": {"$gte": today},
            "show_date": {"$lte": today},  # only wipe today's batch
        })
        await self.db.customer_analysis.insert_many(analyses)


async def run_daily_analysis_for_all_users(db):
    logger.info("[Analyzer] Running daily analysis for all users")
    users = await db.users.find({}).to_list(1000)
    analyzer = DailyCustomerAnalyzer(db)
    for user in users:
        try:
            await analyzer.analyze_all_customers(user["_id"])
        except Exception as e:
            logger.error(f"[Analyzer] Error for user {user['_id']}: {e}")
    logger.info("[Analyzer] Completed daily analysis for all users")
