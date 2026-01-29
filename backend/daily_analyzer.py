"""
Daily Customer Analyzer
Analyzes all customers daily and identifies who needs attention
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from ai_service import get_drafter

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
        try:
            logger.info(f"Starting optimized daily analysis for user {user_id}")
            
            # Optimization: Only analyze customers who might actually need a follow-up
            # (e.g., haven't been contacted in 3+ days or have no contact history)
            three_days_ago = datetime.utcnow() - timedelta(days=3)
            customers = await self.db.customers.find({
                "user_id": user_id,
                "$or": [
                    {"last_contacted": {"$lt": three_days_ago}},
                    {"last_contacted": None}
                ]
            }).sort("last_contacted", 1).to_list(100) # Limit candidates to top 100 cold ones
            
            if not customers:
                logger.info(f"No candidates for follow-up found for user {user_id}")
                return []
            
            # Get user info for business name
            user = await self.db.users.find_one({"_id": user_id})
            business_name = user.get('business_name', 'Your Business') if user else 'Your Business'
            
            analyses = []
            
            # Process in small chunks to avoid overwhelming the system
            for customer in customers:
                try:
                    analysis = await self._analyze_customer(customer, business_name)
                    if analysis:
                        analyses.append(analysis)
                    
                    # Optional: Add a small delay if needed to respect AI rate limits
                    # await asyncio.sleep(0.1) 
                except Exception as e:
                    logger.error(f"Error analyzing customer {customer['_id']}: {e}")
                    continue
            
            # Sort by urgency score (highest first)
            analyses.sort(key=lambda x: x['urgency_score'], reverse=True)
            
            # Apply Daily Quota (Small/Medium/Power tiers)
            daily_quota = self._get_daily_quota(len(customers))
            analyses = analyses[:daily_quota]
            
            # Store analyses in database
            if analyses:
                await self._store_analyses(analyses)
            
            logger.info(f"Completed analysis for {len(analyses)} customers")
            return analyses
        except Exception as e:
            logger.error(f"Failed to run all-customer analysis: {e}")
            return []
    
    def _get_daily_quota(self, total_customers: int) -> int:
        """Get daily suggestion limit based on business size"""
        if total_customers < 100:
            return 10  # Small Shop
        elif total_customers < 500:
            return 20  # Medium Shop
        else:
            return 30  # Power User (Hard Max)

    async def analyze_single_customer(self, customer_id: str, user_id: str) -> Dict:
        """Analyze a single customer on demand"""
        customer = await self.db.customers.find_one({"_id": customer_id, "user_id": user_id})
        if not customer:
            return None
            
        # Get business name
        user = await self.db.users.find_one({"_id": user_id})
        business_name = user.get('business_name', 'Your Business') if user else 'Your Business'
        
        return await self._analyze_customer(customer, business_name)

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
            "ai_reason": ai_result['ai_reason'],
            "suggested_action": self._get_suggested_action(customer, messages),
            "drafted_message": ai_result['drafted_message'],
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
        
        PRIORITY LOGIC:
        1. Customers who messaged YOU (they initiated contact)
        2. Customers with active conversations (24h, 3-day windows)
        3. VIP/Returning customers going cold
        4. New customers with no conversation (lowest priority - likely imports)
        """
        score = 0
        
        # Check if this is a real customer (has messages) or just an import
        has_conversation = len(messages) > 0
        customer_initiated = any(m.get('direction') == 'incoming' for m in messages)
        auto_created = customer.get('auto_created', False)
        
        # Check if this is a recently added contact (within 7 days)
        from datetime import datetime as dt
        created_at = customer.get('created_at')
        days_since_created = None
        if created_at:
            if isinstance(created_at, str):
                created_at = dt.fromisoformat(created_at.replace('Z', '+00:00'))
            days_since_created = (dt.utcnow() - created_at).days
        
        # Factor 1: Conversation Quality (MOST IMPORTANT)
        if customer_initiated:
            # Customer reached out to YOU - highest priority
            score += 50
        elif has_conversation:
            # You initiated but there's a conversation
            score += 30
        elif auto_created:
            # Auto-created from WhatsApp (real customer)
            score += 25
        elif days_since_created is not None and days_since_created <= 7:
            # Recently added manually (within 7 days) - reminder to reach out
            score += 35
        else:
            # Old imported contact, never engaged - LOWEST priority
            score += 5
        
        # Factor 2: Smart Cadence (24h & 3 Days) - Only if there's a conversation
        days_since = self._get_days_since_contact(customer)
        
        if has_conversation:
            if days_since == 1:
                score += 40  # 24-hour follow-up - Critical
            elif days_since == 3:
                score += 30  # 3-day follow-up - Important
            elif days_since > 30:
                score += 20  # Re-engagement needed
            elif days_since > 14:
                score += 15
            elif days_since > 7:
                score += 10
        else:
            # No conversation yet
            if days_since_created is not None and days_since_created <= 7:
                # Recently added, no contact yet - reminder to reach out
                score += 15
            elif days_since is None or days_since > 30:
                score += 5  # Old import, very low priority
        
        # Factor 3: Customer Value
        tags = customer.get('tags', [])
        if 'VIP' in tags:
            score += 25
        elif 'Returning' in tags:
            score += 15
        elif 'New' in tags and has_conversation:
            score += 15  # New with conversation = good
        
        purchase_count = customer.get('purchase_count', 0)
        if purchase_count > 10:
            score += 10
        elif purchase_count > 5:
            score += 5
        
        # Factor 4: Unanswered Questions (URGENT)
        if messages:
            last_message = messages[-1]
            if last_message.get('direction') == 'incoming':
                score += 20  # They messaged us last!
            
            # Check for question words
            content = last_message.get('content', '').lower()
            question_words = ['?', 'how much', 'price', 'cost', 'when', 'where', 'can you', 'bei', 'available']
            if any(word in content for word in question_words):
                score += 20  # Unanswered question = very urgent
        
        # Factor 5: Pending follow-up (Downgrade if exists)
        if has_pending_followup:
            score -= 50  # Already handled
        
        # Ensure score is between 0 and 100
        return max(0, min(100, score))
    
    def _get_urgency_level(self, score: int) -> str:
        """Convert urgency score to level"""
        if score >= 80:
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
        
        # Return exact days (0 for today, 1 for yesterday)
        delta = datetime.utcnow() - last_contacted
        return delta.days
    
    def _get_suggested_action(self, customer: Dict, messages: List[Dict]) -> str:
        """Get suggested action for this customer"""
        
        days_since = self._get_days_since_contact(customer)
        
        if days_since is None:
            return "Send welcome message"
        
        if days_since == 1:
            return "24h check-in"
        
        if days_since == 3:
            return "3-day follow-up"
        
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
