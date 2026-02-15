"""
Follow-up Analytics
Automatically tracks outcomes and calculates success metrics
"""
from datetime import datetime, timedelta
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class FollowUpAnalytics:
    """Analyzes follow-up effectiveness automatically"""
    
    def __init__(self, db):
        self.db = db
    
    async def analyze_followup_outcome(self, followup_id: str) -> Dict:
        """
        Automatically determine follow-up outcome based on data
        
        Outcomes:
        - "converted": Sale created after follow-up
        - "responded": Customer replied
        - "no_response": No reply within 7 days
        - "pending": Still within response window
        """
        followup = await self.db.followups.find_one({"_id": followup_id})
        if not followup:
            return {"outcome": "unknown"}
        
        customer_id = followup["customer_id"]
        user_id = followup.get("user_id")
        reminder_date = followup["reminder_date"]
        
        # Check if completed
        if followup.get("status") != "completed":
            return {"outcome": "pending", "reason": "Not yet completed"}
        
        # Look for activity after follow-up date
        seven_days_after = reminder_date + timedelta(days=7)
        
        # 1. Check for sale (CONVERTED)
        sale_query = {
            "customer_id": customer_id,
            "created_at": {"$gte": reminder_date, "$lte": seven_days_after}
        }
        if user_id:
            sale_query["user_id"] = user_id
        sale = await self.db.sales.find_one(sale_query)
        
        if sale:
            return {
                "outcome": "converted",
                "reason": f"Sale of {sale['amount']} made",
                "sale_id": sale["_id"],
                "sale_amount": sale["amount"]
            }
        
        # 2. Check for customer response (RESPONDED)
        msg_query_base = {"customer_id": customer_id}
        if user_id:
            msg_query_base["user_id"] = user_id
        incoming_message = await self.db.messages.find_one({
            **msg_query_base,
            "direction": "incoming",
            "created_at": {"$gte": reminder_date, "$lte": seven_days_after}
        })
        
        if incoming_message:
            return {
                "outcome": "responded",
                "reason": "Customer replied",
                "response_time_hours": (incoming_message["created_at"] - reminder_date).total_seconds() / 3600
            }
        
        # 3. Check if we sent message (CONTACTED)
        outgoing_message = await self.db.messages.find_one({
            **msg_query_base,
            "direction": "outgoing",
            "created_at": {"$gte": reminder_date, "$lte": seven_days_after}
        })
        
        if outgoing_message and not incoming_message:
            return {
                "outcome": "no_response",
                "reason": "Contacted but no reply within 7 days"
            }
        
        # 4. No activity
        return {
            "outcome": "not_contacted",
            "reason": "Follow-up marked complete but no message sent"
        }
    
    async def get_followup_stats(self, user_id: str, days: int = 30) -> Dict:
        """
        Get follow-up statistics for a user
        
        Returns:
        - Total follow-ups
        - Conversion rate
        - Response rate
        - Average response time
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get all completed follow-ups in period
        followups = await self.db.followups.find({
            "user_id": user_id,
            "status": "completed",
            "reminder_date": {"$gte": cutoff_date}
        }).to_list(1000)
        
        if not followups:
            return {
                "total_followups": 0,
                "conversion_rate": 0,
                "response_rate": 0,
                "avg_response_time_hours": 0
            }
        
        # Analyze each follow-up
        outcomes = {
            "converted": 0,
            "responded": 0,
            "no_response": 0,
            "not_contacted": 0
        }
        
        response_times = []
        total_revenue = 0
        
        for followup in followups:
            outcome = await self.analyze_followup_outcome(followup["_id"])
            outcome_type = outcome.get("outcome")
            
            if outcome_type in outcomes:
                outcomes[outcome_type] += 1
            
            if outcome_type == "converted":
                total_revenue += outcome.get("sale_amount", 0)
            
            if outcome_type == "responded":
                response_times.append(outcome.get("response_time_hours", 0))
        
        total = len(followups)
        contacted = total - outcomes["not_contacted"]
        
        return {
            "period_days": days,
            "total_followups": total,
            "contacted": contacted,
            "converted": outcomes["converted"],
            "responded": outcomes["responded"],
            "no_response": outcomes["no_response"],
            "not_contacted": outcomes["not_contacted"],
            
            # Rates
            "conversion_rate": (outcomes["converted"] / contacted * 100) if contacted > 0 else 0,
            "response_rate": ((outcomes["converted"] + outcomes["responded"]) / contacted * 100) if contacted > 0 else 0,
            
            # Timing
            "avg_response_time_hours": sum(response_times) / len(response_times) if response_times else 0,
            
            # Revenue
            "total_revenue": total_revenue,
            "revenue_per_followup": total_revenue / total if total > 0 else 0
        }
    
    async def get_best_followup_times(self, user_id: str) -> Dict:
        """
        Analyze which follow-up timings work best
        
        Returns best:
        - Day of week
        - Time of day
        - Days after first contact
        """
        # Get all successful follow-ups (converted or responded)
        followups = await self.db.followups.find({
            "user_id": user_id,
            "status": "completed"
        }).to_list(1000)
        
        successful_times = []
        
        for followup in followups:
            outcome = await self.analyze_followup_outcome(followup["_id"])
            if outcome.get("outcome") in ["converted", "responded"]:
                reminder_date = followup["reminder_date"]
                successful_times.append({
                    "day_of_week": reminder_date.weekday(),  # 0=Monday, 6=Sunday
                    "hour": reminder_date.hour
                })
        
        if not successful_times:
            return {
                "best_day": "Monday",
                "best_hour": 10,
                "sample_size": 0
            }
        
        # Find most common day
        day_counts = {}
        hour_counts = {}
        
        for time in successful_times:
            day = time["day_of_week"]
            hour = time["hour"]
            day_counts[day] = day_counts.get(day, 0) + 1
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        
        best_day_num = max(day_counts, key=day_counts.get)
        best_hour = max(hour_counts, key=hour_counts.get)
        
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        return {
            "best_day": days[best_day_num],
            "best_hour": best_hour,
            "sample_size": len(successful_times),
            "day_distribution": {days[k]: v for k, v in day_counts.items()},
            "hour_distribution": hour_counts
        }

# Singleton
_analytics = None

def get_analytics(db):
    """Get singleton instance"""
    global _analytics
    if _analytics is None:
        _analytics = FollowUpAnalytics(db)
    return _analytics
