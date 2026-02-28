"""
Daily Digest Service
Generates and sends daily follow-up summaries via WhatsApp and Push Notifications
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class DigestService:
    """Service for generating and sending daily digests"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def generate_digest(self, user_id: str, digest_type: str = "morning") -> Dict:
        """
        Generate digest summary for a user
        
        Args:
            user_id: User/business ID
            digest_type: "morning" (8 AM) or "afternoon" (3 PM)
        
        Returns:
            Dict with counts and lists of items needing attention
        """
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Real customer filter
        is_customer = {"$or": [
            {"is_customer": True}, 
            {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}
        ]}
        
        # 1. Follow-ups due today
        followups_due_today = await self.db.followups.find({
            "user_id": user_id,
            "status": "pending",
            "reminder_date": {"$gte": today_start, "$lte": today_end}
        }).to_list(100)
        
        # Enrich with customer names
        for fu in followups_due_today:
            customer = await self.db.customers.find_one({"_id": fu["customer_id"]})
            fu["customer_name"] = customer.get("name", "Unknown") if customer else "Unknown"
        
        # 2. Overdue follow-ups (due before today, still pending)
        overdue_followups = await self.db.followups.find({
            "user_id": user_id,
            "status": "pending",
            "reminder_date": {"$lt": today_start}
        }).to_list(100)
        
        for fu in overdue_followups:
            customer = await self.db.customers.find_one({"_id": fu["customer_id"]})
            fu["customer_name"] = customer.get("name", "Unknown") if customer else "Unknown"
            fu["days_overdue"] = (now - fu["reminder_date"]).days
        
        # 3. New customers (added in last 48h) with no contact yet
        cutoff_48h = now - timedelta(hours=48)
        new_customers = await self.db.customers.find({
            "user_id": user_id,
            "$and": [
                is_customer,
                {"created_at": {"$gte": cutoff_48h}},
                {"$or": [
                    {"last_contacted": None}, 
                    {"last_contacted": {"$exists": False}}
                ]}
            ]
        }).to_list(50)
        
        # 4. Customers approaching cold threshold (5-6 days since contact)
        cutoff_5d = now - timedelta(days=5)
        cutoff_7d = now - timedelta(days=7)
        approaching_cold = await self.db.customers.find({
            "user_id": user_id,
            "$and": [
                is_customer,
                {"last_contacted": {"$gte": cutoff_7d, "$lt": cutoff_5d}}
            ]
        }).to_list(50)
        
        # 5. VIP customers not contacted in 3+ days
        cutoff_3d = now - timedelta(days=3)
        vip_neglected = await self.db.customers.find({
            "user_id": user_id,
            "tags": "VIP",
            "$and": [
                is_customer,
                {"$or": [
                    {"last_contacted": {"$lt": cutoff_3d}},
                    {"last_contacted": None},
                    {"last_contacted": {"$exists": False}}
                ]}
            ]
        }).to_list(50)
        
        # Build digest
        digest = {
            "type": digest_type,
            "generated_at": now,
            "followups_due_today": {
                "count": len(followups_due_today),
                "items": followups_due_today[:5]  # Top 5
            },
            "overdue_followups": {
                "count": len(overdue_followups),
                "items": sorted(overdue_followups, key=lambda x: x.get("days_overdue", 0), reverse=True)[:5]
            },
            "new_customers_waiting": {
                "count": len(new_customers),
                "items": new_customers[:5]
            },
            "approaching_cold": {
                "count": len(approaching_cold),
                "items": approaching_cold[:5]
            },
            "vip_neglected": {
                "count": len(vip_neglected),
                "items": vip_neglected[:5]
            }
        }
        
        # Add summary stats
        digest["total_action_items"] = (
            len(followups_due_today) + 
            len(overdue_followups) + 
            len(new_customers)
        )
        
        return digest
    
    def format_whatsapp_message(self, digest: Dict) -> str:
        """
        Format digest as WhatsApp message
        
        Args:
            digest: Digest data from generate_digest()
        
        Returns:
            Formatted message string
        """
        digest_type = digest["type"]
        time_emoji = "🌅" if digest_type == "morning" else "☀️"
        
        lines = []
        
        # Header
        if digest_type == "morning":
            lines.append(f"{time_emoji} *Good Morning! Daily Follow-up Digest*")
        else:
            lines.append(f"{time_emoji} *Afternoon Reminder*")
        
        lines.append("")
        
        # Total action items
        total = digest["total_action_items"]
        if total == 0:
            lines.append("✅ All caught up! No urgent items today.")
            return "\n".join(lines)
        
        lines.append(f"📋 *{total} items need your attention*")
        lines.append("")
        
        # Follow-ups due today
        due_today = digest["followups_due_today"]
        if due_today["count"] > 0:
            lines.append(f"📅 *Follow-ups Due Today ({due_today['count']})*")
            for fu in due_today["items"]:
                lines.append(f"  • {fu['customer_name']} - {fu.get('notes', 'Follow-up')}")
            lines.append("")
        
        # Overdue
        overdue = digest["overdue_followups"]
        if overdue["count"] > 0:
            lines.append(f"⚠️ *Overdue Follow-ups ({overdue['count']})*")
            for fu in overdue["items"]:
                days = fu.get("days_overdue", 0)
                lines.append(f"  • {fu['customer_name']} ({days}d overdue)")
            lines.append("")
        
        # New customers waiting
        new = digest["new_customers_waiting"]
        if new["count"] > 0:
            lines.append(f"🆕 *New Customers Waiting ({new['count']})*")
            for c in new["items"]:
                lines.append(f"  • {c.get('name', 'Unknown')}")
            lines.append("")
        
        # VIP neglected
        vip = digest["vip_neglected"]
        if vip["count"] > 0:
            lines.append(f"⭐ *VIP Customers ({vip['count']})*")
            for c in vip["items"]:
                lines.append(f"  • {c.get('name', 'Unknown')}")
            lines.append("")
        
        # Footer
        lines.append("_Open your CRM app to take action_ 📱")
        
        return "\n".join(lines)
    
    def format_push_notification(self, digest: Dict) -> Dict:
        """
        Format digest as push notification payload
        
        Args:
            digest: Digest data from generate_digest()
        
        Returns:
            Dict with title, body, and data
        """
        total = digest["total_action_items"]
        
        if total == 0:
            return {
                "title": "✅ All Caught Up!",
                "body": "No urgent follow-ups today. Great work!",
                "data": {"type": "digest", "action_count": 0}
            }
        
        # Build title
        title = f"📋 {total} Follow-up{'s' if total != 1 else ''}"
        
        # Build body summary
        parts = []
        if digest["followups_due_today"]["count"] > 0:
            parts.append(f"{digest['followups_due_today']['count']} due today")
        if digest["overdue_followups"]["count"] > 0:
            parts.append(f"{digest['overdue_followups']['count']} overdue")
        if digest["new_customers_waiting"]["count"] > 0:
            parts.append(f"{digest['new_customers_waiting']['count']} new waiting")
        
        body = ", ".join(parts)
        
        return {
            "title": title,
            "body": body,
            "data": {
                "type": "digest",
                "action_count": total,
                "due_today": digest["followups_due_today"]["count"],
                "overdue": digest["overdue_followups"]["count"]
            }
        }


# Singleton instance
_digest_service = None

def get_digest_service(db: AsyncIOMotorDatabase) -> DigestService:
    """Get singleton instance of DigestService"""
    global _digest_service
    if _digest_service is None:
        _digest_service = DigestService(db)
    return _digest_service
