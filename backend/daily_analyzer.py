"""
Daily Customer Analyzer
Analyzes all customers daily and identifies who needs attention
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from ai_message_drafter import get_drafter

logger = logging.getLogger(__name__)


class DailyCustomerAnalyzer:
    """Analyzes customers daily and generates insights"""
    
    def __init__(self, db):
        self.db = db
        self.drafter = get_drafter()
    
    async def analyze_all_customers(self, user_id: str) -> List[Dict]:
        """
        Analyze all customers for a user and generate insights
        
        Returns:
            List of customer analyses sorted by urgency (highest first)
        """
        logger.info(f"Starting daily analysis for user {user_id}")
        
        # Get all customers for this user
        customers = await self.db.customers.find({"user_id": user_id}).to_list(1000)
        
        if not customers:
            logger.info(f"No customers found for user {user_id}")
            return []
        
        # Get user info for business name
        user = await self.db.users.find_one({"_id": user_id})
        business_name = user.get('business_name', 'Your Business') if user else 'Your Business'
        
        analyses = []
        
        for customer in customers:
            try:
                analysis = await self._analyze_customer(customer, business_name)
                if analysis:
                    analyses.append(analysis)
            except Exception as e:
                logger.error(f"Error analyzing customer {customer['_id']}: {e}")
                continue
        
        # Sort by urgency score (highest first)
        analyses.sort(key=lambda x: x['urgency_score'], reverse=True)
        
        # Store analyses in database
        await self._store_analyses(analyses)
        
        logger.info(f"Completed analysis for {len(analyses)} customers")
        return analyses
    
    async def _analyze_customer(self, customer: Dict, business_name: str) -> Dict:
        """Analyze a single customer and generate urgency score"""
        
        customer_id = customer['_id']
        
        # Get message history for this customer
        messages = await self.db.messages.find({
            "customer_id": customer_id
        }).sort("timestamp", -1).limit(10).to_list(10)
        
        # Reverse to get chronological order
        messages = list(reversed(messages))
        
        # Check if customer already has a pending follow-up
        has_pending_followup = await self.db.followups.find_one({
            "customer_id": customer_id,
            "status": "pending"
        }) is not None
        
        # Calculate urgency score
        urgency_score = self._calculate_urgency_score(customer, messages, has_pending_followup)
        
        # Skip if urgency is too low (less than 30)
        if urgency_score < 30:
            return None
        
        # Generate AI reason and draft message
        ai_result = await self.drafter.draft_followup_message(
            customer_name=customer['name'],
            customer_data=customer,
            messages=messages,
            business_name=business_name,
            tone='friendly'
        )
        
        # Create analysis record
        analysis = {
            "user_id": customer['user_id'],
            "customer_id": customer_id,
            "customer_name": customer['name'],
            "customer_phone": customer['phone_number'],
            "analysis_date": datetime.utcnow(),
            "urgency_score": urgency_score,
            "urgency_level": self._get_urgency_level(urgency_score),
            "ai_reason": ai_result['reason'],
            "suggested_action": self._get_suggested_action(customer, messages),
            "drafted_message": ai_result['message'],
            "conversation_summary": self._summarize_conversation(messages),
            "last_topic": self._get_last_topic(messages),
            "has_pending_followup": has_pending_followup,
            "notification_sent": False,
            "days_since_contact": self._get_days_since_contact(customer)
        }
        
        return analysis
    
    def _calculate_urgency_score(
        self,
        customer: Dict,
        messages: List[Dict],
        has_pending_followup: bool
    ) -> int:
        """
        Calculate urgency score (0-100) for a customer
        Higher score = more urgent to follow up
        """
        score = 0
        
        # Factor 1: Days since last contact (max 40 points)
        days_since = self._get_days_since_contact(customer)
        if days_since is None:
            score += 40  # Never contacted - high priority
        elif days_since > 60:
            score += 40
        elif days_since > 30:
            score += 35
        elif days_since > 14:
            score += 25
        elif days_since > 7:
            score += 15
        else:
            score += 5
        
        # Factor 2: Customer value (max 25 points)
        tags = customer.get('tags', [])
        if 'VIP' in tags:
            score += 25
        elif 'Returning' in tags:
            score += 15
        elif 'New' in tags:
            score += 20  # New customers need attention
        
        purchase_count = customer.get('purchase_count', 0)
        if purchase_count > 10:
            score += 10
        elif purchase_count > 5:
            score += 5
        
        # Factor 3: Conversation context (max 20 points)
        if messages:
            last_message = messages[-1]
            
            # If last message was from customer (incoming), higher priority
            if last_message.get('direction') == 'incoming':
                score += 15
            
            # Check for question keywords
            content = last_message.get('content', '').lower()
            question_words = ['?', 'how much', 'price', 'cost', 'when', 'where', 'can you']
            if any(word in content for word in question_words):
                score += 10
        
        # Factor 4: Pending follow-up (max 15 points)
        if has_pending_followup:
            score -= 30  # Reduce urgency if already has a reminder
        else:
            score += 15  # Increase if no reminder set
        
        # Ensure score is between 0 and 100
        return max(0, min(100, score))
    
    def _get_urgency_level(self, score: int) -> str:
        """Convert urgency score to level"""
        if score >= 70:
            return "high"
        elif score >= 50:
            return "medium"
        else:
            return "low"
    
    def _get_days_since_contact(self, customer: Dict) -> int:
        """Get days since last contact"""
        last_contacted = customer.get('last_contacted')
        if not last_contacted:
            return None
        
        if isinstance(last_contacted, str):
            last_contacted = datetime.fromisoformat(last_contacted.replace('Z', '+00:00'))
        
        return (datetime.utcnow() - last_contacted).days
    
    def _get_suggested_action(self, customer: Dict, messages: List[Dict]) -> str:
        """Get suggested action for this customer"""
        
        days_since = self._get_days_since_contact(customer)
        
        if days_since is None:
            return "Send welcome message"
        
        if days_since > 30:
            return "Re-engage with special offer"
        
        if messages and messages[-1].get('direction') == 'incoming':
            return "Respond to their message"
        
        tags = customer.get('tags', [])
        if 'VIP' in tags:
            return "Check in and maintain relationship"
        
        return "Send follow-up message"
    
    def _summarize_conversation(self, messages: List[Dict]) -> str:
        """Create a brief summary of the conversation"""
        if not messages:
            return "No previous conversation"
        
        message_count = len(messages)
        last_message = messages[-1]
        
        direction = "They" if last_message.get('direction') == 'incoming' else "You"
        last_content = last_message.get('content', '')[:50]
        
        return f"{message_count} messages. Last: {direction} said \"{last_content}...\""
    
    def _get_last_topic(self, messages: List[Dict]) -> str:
        """Extract the last topic discussed"""
        if not messages:
            return "No conversation"
        
        # Check last few messages for topics
        recent_messages = messages[-3:] if len(messages) > 3 else messages
        
        topics = {
            'pricing': ['price', 'cost', 'how much', 'bei'],
            'product': ['product', 'item', 'stock'],
            'delivery': ['deliver', 'shipping', 'send'],
            'complaint': ['problem', 'issue', 'not working']
        }
        
        for msg in reversed(recent_messages):
            content = msg.get('content', '').lower()
            for topic, keywords in topics.items():
                if any(kw in content for kw in keywords):
                    return topic.capitalize()
        
        return "General inquiry"
    
    async def _store_analyses(self, analyses: List[Dict]):
        """Store analyses in database"""
        if not analyses:
            return
        
        # Get today's date (start of day)
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Delete old analyses for today
        user_id = analyses[0]['user_id']
        await self.db.customer_analysis.delete_many({
            "user_id": user_id,
            "analysis_date": {"$gte": today}
        })
        
        # Insert new analyses
        await self.db.customer_analysis.insert_many(analyses)
    
    async def get_todays_insights(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get today's customer insights for a user"""
        
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        analyses = await self.db.customer_analysis.find({
            "user_id": user_id,
            "analysis_date": {"$gte": today}
        }).sort("urgency_score", -1).limit(limit).to_list(limit)
        
        return analyses


async def run_daily_analysis_for_all_users(db):
    """Run daily analysis for all users (called by scheduler)"""
    logger.info("Starting daily analysis for all users")
    
    users = await db.users.find({}).to_list(1000)
    analyzer = DailyCustomerAnalyzer(db)
    
    for user in users:
        try:
            user_id = user['_id']
            logger.info(f"Analyzing customers for user {user_id}")
            await analyzer.analyze_all_customers(user_id)
        except Exception as e:
            logger.error(f"Error analyzing user {user['_id']}: {e}")
            continue
    
    logger.info("Completed daily analysis for all users")
