"""
WOW Moment Enhancements for CRM
Additional intelligence features to delight users
"""
from datetime import datetime, timedelta
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class WowMomentGenerator:
    """Generate delightful insights and predictions for users"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_daily_wow_insights(self, user_id: str) -> Dict:
        """
        Generate daily 'wow moment' insights that show the system is working hard
        """
        insights = {
            "greeting": await self._get_personalized_greeting(user_id),
            "quick_wins": await self._get_quick_wins(user_id),
            "revenue_opportunity": await self._calculate_revenue_opportunity(user_id),
            "streak": await self._get_follow_up_streak(user_id),
            "ai_saved_time": await self._calculate_time_saved(user_id),
            "success_prediction": await self._predict_success_rate(user_id),
            "best_time_to_contact": await self._suggest_best_contact_time(user_id),
        }
        
        return insights
    
    async def _get_personalized_greeting(self, user_id: str) -> str:
        """Smart greeting based on time and user activity"""
        hour = datetime.now().hour
        
        # Check recent activity
        recent_messages = await self.db.messages.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": datetime.utcnow() - timedelta(hours=1)}
        })
        
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        
        if recent_messages > 0:
            return f"{greeting}! You're on fire today 🔥"
        
        return f"{greeting}! Ready to close some deals?"
    
    async def _get_quick_wins(self, user_id: str) -> List[Dict]:
        """
        Identify 'quick win' customers - high probability of conversion
        """
        quick_wins = []
        
        # Customers who asked about price in last 24h
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_price_inquiries = await self.db.messages.find({
            "user_id": user_id,
            "direction": "incoming",
            "created_at": {"$gte": yesterday},
            "$or": [
                {"content": {"$regex": "price", "$options": "i"}},
                {"content": {"$regex": "cost", "$options": "i"}},
                {"content": {"$regex": "bei", "$options": "i"}},
                {"content": {"$regex": "how much", "$options": "i"}},
            ]
        }).to_list(10)
        
        for msg in recent_price_inquiries:
            customer = await self.db.customers.find_one({"_id": msg["customer_id"]})
            if customer:
                quick_wins.append({
                    "customer_name": customer["name"],
                    "reason": "Asked about price in last 24h",
                    "probability": "85%",
                    "action": "Send price quote now"
                })
        
        return quick_wins[:3]  # Top 3 quick wins
    
    async def _calculate_revenue_opportunity(self, user_id: str) -> Dict:
        """
        Calculate potential revenue from pending follow-ups
        """
        # Get customers needing attention
        two_weeks_ago = datetime.utcnow() - timedelta(days=14)
        neglected_customers = await self.db.customers.count_documents({
            "user_id": user_id,
            "$or": [
                {"last_contacted": {"$lt": two_weeks_ago}},
                {"last_contacted": None}
            ]
        })
        
        # Get average order value
        user = await self.db.users.find_one({"_id": user_id})
        avg_order = user.get("avg_order_value", 5000) if user else 5000
        
        # Conservative conversion rate: 10% of follow-ups convert
        potential_revenue = neglected_customers * avg_order * 0.10
        
        return {
            "customers_at_risk": neglected_customers,
            "potential_revenue": potential_revenue,
            "avg_order_value": avg_order,
            "message": f"💰 KES {potential_revenue:,.0f} in potential revenue from {neglected_customers} customers"
        }
    
    async def _get_follow_up_streak(self, user_id: str) -> Dict:
        """
        Track user's follow-up consistency (gamification)
        """
        # Check last 7 days for follow-up activity
        streak_days = 0
        current_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        for i in range(7):
            check_date = current_date - timedelta(days=i)
            next_date = check_date + timedelta(days=1)
            
            # Check if user sent any messages that day
            messages_sent = await self.db.messages.count_documents({
                "user_id": user_id,
                "direction": "outgoing",
                "created_at": {"$gte": check_date, "$lt": next_date}
            })
            
            if messages_sent > 0:
                streak_days += 1
            else:
                break  # Streak broken
        
        emoji = "🔥" if streak_days >= 7 else "⭐" if streak_days >= 3 else "💪"
        
        return {
            "streak_days": streak_days,
            "emoji": emoji,
            "message": f"{emoji} {streak_days}-day follow-up streak!" if streak_days > 0 else "Start your streak today!"
        }
    
    async def _calculate_time_saved(self, user_id: str) -> Dict:
        """
        Calculate time saved by AI features
        """
        # Count AI-drafted messages used in last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        ai_drafts_used = await self.db.customer_analysis.count_documents({
            "user_id": user_id,
            "analysis_date": {"$gte": thirty_days_ago}
        })
        
        # Assume each AI draft saves 3 minutes (thinking + typing)
        minutes_saved = ai_drafts_used * 3
        hours_saved = minutes_saved / 60
        
        return {
            "ai_drafts_used": ai_drafts_used,
            "minutes_saved": minutes_saved,
            "hours_saved": hours_saved,
            "message": f"🤖 AI saved you {hours_saved:.1f} hours this month"
        }
    
    async def _predict_success_rate(self, user_id: str) -> Dict:
        """
        Predict success rate for today's follow-ups
        """
        # Get today's pending follow-ups
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        todays_followups = await self.db.followups.count_documents({
            "user_id": user_id,
            "reminder_date": {"$gte": today, "$lt": tomorrow},
            "status": "pending"
        })
        
        # Get high-urgency customers
        high_urgency = await self.db.customer_analysis.count_documents({
            "user_id": user_id,
            "urgency_level": "high",
            "analysis_date": {"$gte": today}
        })
        
        # Calculate predicted success
        if todays_followups == 0:
            success_rate = 0
        else:
            # Higher urgency = higher success rate
            base_rate = 30  # 30% base conversion
            urgency_boost = (high_urgency / max(todays_followups, 1)) * 20
            success_rate = min(base_rate + urgency_boost, 75)
        
        return {
            "todays_followups": todays_followups,
            "high_urgency_count": high_urgency,
            "predicted_success_rate": success_rate,
            "message": f"📈 {success_rate:.0f}% predicted success rate today"
        }
    
    async def _suggest_best_contact_time(self, user_id: str) -> Dict:
        """
        Analyze when customers are most responsive
        """
        # Analyze message response patterns
        incoming_messages = await self.db.messages.find({
            "user_id": user_id,
            "direction": "incoming"
        }).to_list(1000)
        
        # Count messages by hour
        hour_counts = {}
        for msg in incoming_messages:
            created_at = msg.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                hour = created_at.hour
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
        
        if not hour_counts:
            return {
                "best_hour": 10,
                "message": "📱 Best time: 10 AM - 12 PM (most businesses are active)"
            }
        
        # Find peak hour
        best_hour = max(hour_counts, key=hour_counts.get)
        
        # Convert to readable time
        if best_hour < 12:
            time_str = f"{best_hour} AM - {best_hour + 2} AM"
        elif best_hour == 12:
            time_str = "12 PM - 2 PM"
        else:
            time_str = f"{best_hour - 12} PM - {best_hour - 10} PM"
        
        return {
            "best_hour": best_hour,
            "message": f"📱 Your customers are most active: {time_str}"
        }

# Singleton instance
_wow_generator = None

def get_wow_generator(db):
    """Get singleton instance"""
    global _wow_generator
    if _wow_generator is None:
        _wow_generator = WowMomentGenerator(db)
    return _wow_generator
