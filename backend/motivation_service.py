"""
Motivation Service
Sends inspiring business quotes with no-repeat tracking (100+ unique quotes)
"""
import random
from typing import Dict, List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase


class MotivationService:
    """Service for generating motivational messages with tracking to prevent repeats"""
    
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self.db = db
    
    # 100+ curated business quotes from famous leaders
    MOTIVATIONAL_QUOTES = [
        # Customer Service (15)
        {"quote": "Your most unhappy customers are your greatest source of learning.", "author": "Bill Gates"},
        {"quote": "The customer's perception is your reality.", "author": "Kate Zabriskie"},
        {"quote": "Every contact we have with a customer influences whether or not they'll come back.", "author": "Brian Tracy"},
        {"quote": "Make a customer, not a sale.", "author": "Katherine Barchetti"},
        {"quote": "A satisfied customer is the best business strategy of all.", "author": "Michael LeBoeuf"},
        {"quote": "Customers will never love a company until the employees love it first.", "author": "Simon Sinek"},
        {"quote": "There is only one boss: the customer.", "author": "Sam Walton"},
        {"quote": "Get closer than ever to your customers. So close that you tell them what they need before they realize it themselves.", "author": "Steve Jobs"},
        {"quote": "The purpose of business is to create and keep a customer.", "author": "Peter Drucker"},
        {"quote": "To keep a customer demands as much skill as to win one.", "author": "American Proverb"},
        {"quote": "If you're not serving the customer, your job is to serve someone who is.", "author": "Jan Carlzon"},
        {"quote": "Do what you do so well that they will want to see it again and bring their friends.", "author": "Walt Disney"},
        {"quote": "Customer service shouldn't just be a department, it should be the entire company.", "author": "Tony Hsieh"},
        {"quote": "We see our customers as invited guests to a party, and we are the hosts.", "author": "Jeff Bezos"},
        {"quote": "Right or wrong, the customer is always right.", "author": "Marshall Field"},
        
        # Success & Growth (15)
        {"quote": "The way to get started is to quit talking and begin doing.", "author": "Walt Disney"},
        {"quote": "Success is not final, failure is not fatal: it is the courage to continue that counts.", "author": "Winston Churchill"},
        {"quote": "Don't watch the clock; do what it does. Keep going.", "author": "Sam Levenson"},
        {"quote": "The only impossible journey is the one you never begin.", "author": "Tony Robbins"},
        {"quote": "Opportunities don't happen. You create them.", "author": "Chris Grosser"},
        {"quote": "Success usually comes to those who are too busy to be looking for it.", "author": "Henry David Thoreau"},
        {"quote": "The harder I work, the luckier I get.", "author": "Samuel Goldwyn"},
        {"quote": "Don't be afraid to give up the good to go for the great.", "author": "John D. Rockefeller"},
        {"quote": "Success is walking from failure to failure with no loss of enthusiasm.", "author": "Winston Churchill"},
        {"quote": "The only limit to our realization of tomorrow will be our doubts of today.", "author": "Franklin D. Roosevelt"},
        {"quote": "It's not about ideas. It's about making ideas happen.", "author": "Scott Belsky"},
        {"quote": "Your work is going to fill a large part of your life, and the only way to be truly satisfied is to do great work.", "author": "Steve Jobs"},
        {"quote": "Innovation distinguishes between a leader and a follower.", "author": "Steve Jobs"},
        {"quote": "The secret of getting ahead is getting started.", "author": "Mark Twain"},
        {"quote": "The best time to plant a tree was 20 years ago. The second best time is now.", "author": "Chinese Proverb"},
        
        # Leadership (15)
        {"quote": "Good business leaders create a vision, articulate the vision, passionately own the vision, and relentlessly drive it to completion.", "author": "Jack Welch"},
        {"quote": "People don't buy what you do; they buy why you do it.", "author": "Simon Sinek"},
        {"quote": "A leader is one who knows the way, goes the way, and shows the way.", "author": "John C. Maxwell"},
        {"quote": "The function of leadership is to produce more leaders, not more followers.", "author": "Ralph Nader"},
        {"quote": "Management is doing things right; leadership is doing the right things.", "author": "Peter Drucker"},
        {"quote": "Leadership is not about being in charge. It's about taking care of those in your charge.", "author": "Simon Sinek"},
        {"quote": "The greatest leader is not necessarily the one who does the greatest things. He is the one that gets the people to do the greatest things.", "author": "Ronald Reagan"},
        {"quote": "If your actions inspire others to dream more, learn more, do more and become more, you are a leader.", "author": "John Quincy Adams"},
        {"quote": "Vision without action is daydream. Action without vision is nightmare.", "author": "Japanese Proverb"},
        {"quote": "Before you are a leader, success is all about growing yourself. When you become a leader, success is all about growing others.", "author": "Jack Welch"},
        {"quote": "Outstanding leaders go out of their way to boost the self-esteem of their personnel.", "author": "Sam Walton"},
        {"quote": "Leadership is the capacity to translate vision into reality.", "author": "Warren Bennis"},
        {"quote": "The speed of the boss is the speed of the team.", "author": "Lee Iacocca"},
        {"quote": "Lead from the back and let others believe they are in front.", "author": "Nelson Mandela"},
        {"quote": "The art of communication is the language of leadership.", "author": "James Humes"},
        
        # Persistence (15)
        {"quote": "Every problem is a gift—without problems we would not grow.", "author": "Anthony Robbins"},
        {"quote": "Do not be embarrassed by your failures, learn from them and start again.", "author": "Richard Branson"},
        {"quote": "I have not failed. I've just found 10,000 ways that won't work.", "author": "Thomas Edison"},
        {"quote": "It does not matter how slowly you go as long as you do not stop.", "author": "Confucius"},
        {"quote": "Failure is simply the opportunity to begin again, this time more intelligently.", "author": "Henry Ford"},
        {"quote": "Persistence guarantees that results are inevitable.", "author": "Paramahansa Yogananda"},
        {"quote": "Many of life's failures are people who did not realize how close they were to success when they gave up.", "author": "Thomas Edison"},
        {"quote": "You just can't beat the person who won't give up.", "author": "Babe Ruth"},
        {"quote": "Never give in except to convictions of honor and good sense.", "author": "Winston Churchill"},
        {"quote": "Fall seven times, stand up eight.", "author": "Japanese Proverb"},
        {"quote": "The man who moves a mountain begins by carrying away small stones.", "author": "Confucius"},
        {"quote": "A river cuts through rock not because of its power, but because of its persistence.", "author": "Jim Watkins"},
        {"quote": "It's not that I'm so smart, it's just that I stay with problems longer.", "author": "Albert Einstein"},
        {"quote": "The difference between a successful person and others is not a lack of strength, not a lack of knowledge, but rather a lack in will.", "author": "Vince Lombardi"},
        {"quote": "Rock bottom became the solid foundation on which I rebuilt my life.", "author": "J.K. Rowling"},
        
        # Excellence (15)
        {"quote": "Quality is not an act, it is a habit.", "author": "Aristotle"},
        {"quote": "If you cannot do great things, do small things in a great way.", "author": "Napoleon Hill"},
        {"quote": "Excellence is not a destination; it is a continuous journey that never ends.", "author": "Brian Tracy"},
        {"quote": "We are what we repeatedly do. Excellence, then, is not an act but a habit.", "author": "Aristotle"},
        {"quote": "Strive not to be a success, but rather to be of value.", "author": "Albert Einstein"},
        {"quote": "Perfection is not attainable, but if we chase perfection we can catch excellence.", "author": "Vince Lombardi"},
        {"quote": "The secret of change is to focus all of your energy not on fighting the old, but on building the new.", "author": "Socrates"},
        {"quote": "The difference between ordinary and extraordinary is that little extra.", "author": "Jimmy Johnson"},
        {"quote": "Be a yardstick of quality. Some people aren't used to an environment where excellence is expected.", "author": "Steve Jobs"},
        {"quote": "Quality means doing it right when no one is looking.", "author": "Henry Ford"},
        {"quote": "Excellence is doing ordinary things extraordinarily well.", "author": "John W. Gardner"},
        {"quote": "Always deliver more than expected.", "author": "Larry Page"},
        {"quote": "There are no traffic jams along the extra mile.", "author": "Roger Staubach"},
        {"quote": "Your reputation is more important than your paycheck.", "author": "Mark Cuban"},
        {"quote": "Whatever you do, do it well. Do it so well that when people see you do it, they will want to come back and see you do it again.", "author": "Walt Disney"},
        
        # Entrepreneurship (15)
        {"quote": "The entrepreneur always searches for change, responds to it, and exploits it as an opportunity.", "author": "Peter Drucker"},
        {"quote": "An entrepreneur is someone who jumps off a cliff and builds a plane on the way down.", "author": "Reid Hoffman"},
        {"quote": "The critical ingredient is getting off your butt and doing something.", "author": "Nolan Bushnell"},
        {"quote": "Ideas are easy. Implementation is hard.", "author": "Guy Kawasaki"},
        {"quote": "Don't worry about failure; you only have to be right once.", "author": "Drew Houston"},
        {"quote": "Chase the vision, not the money; the money will end up following you.", "author": "Tony Hsieh"},
        {"quote": "Some people dream of success, while other people get up every morning and make it happen.", "author": "Wayne Huizenga"},
        {"quote": "Build your own dreams, or someone else will hire you to build theirs.", "author": "Farrah Gray"},
        {"quote": "The biggest risk is not taking any risk. In a world that's changing quickly, the only strategy that is guaranteed to fail is not taking risks.", "author": "Mark Zuckerberg"},
        {"quote": "Entrepreneurship is living a few years of your life like most people won't so you can spend the rest of your life like most people can't.", "author": "Unknown"},
        {"quote": "The only way to do great work is to love what you do.", "author": "Steve Jobs"},
        {"quote": "If you're not embarrassed by the first version of your product, you've launched too late.", "author": "Reid Hoffman"},
        {"quote": "Make every detail perfect and limit the number of details to perfect.", "author": "Jack Dorsey"},
        {"quote": "It's fine to celebrate success, but it is more important to heed the lessons of failure.", "author": "Bill Gates"},
        {"quote": "Life is too short to build something nobody wants.", "author": "Ash Maurya"},
        
        # Work Ethic & Discipline (15)
        {"quote": "I'm a greater believer in luck, and I find the harder I work the more I have of it.", "author": "Thomas Jefferson"},
        {"quote": "There is no substitute for hard work.", "author": "Thomas Edison"},
        {"quote": "Work hard in silence, let success make the noise.", "author": "Frank Ocean"},
        {"quote": "The only place success comes before work is in the dictionary.", "author": "Vidal Sassoon"},
        {"quote": "Without hustle, talent will only carry you so far.", "author": "Gary Vaynerchuk"},
        {"quote": "Don't wish it were easier. Wish you were better.", "author": "Jim Rohn"},
        {"quote": "The future depends on what you do today.", "author": "Mahatma Gandhi"},
        {"quote": "Do something today that your future self will thank you for.", "author": "Sean Patrick Flanery"},
        {"quote": "Discipline is the bridge between goals and accomplishment.", "author": "Jim Rohn"},
        {"quote": "Action is the foundational key to all success.", "author": "Pablo Picasso"},
        {"quote": "Well done is better than well said.", "author": "Benjamin Franklin"},
        {"quote": "The best way to predict the future is to create it.", "author": "Peter Drucker"},
        {"quote": "Stop chasing the money and start chasing the passion.", "author": "Tony Hsieh"},
        {"quote": "If you really look closely, most overnight successes took a long time.", "author": "Steve Jobs"},
        {"quote": "The only thing standing between you and your goal is the story you keep telling yourself.", "author": "Jordan Belfort"},
    ]
    
    MONDAY_QUOTES = [
        {"quote": "It's Monday—your chance to start fresh and make this week amazing!", "author": "Unknown"},
        {"quote": "Monday is a fresh start. It's never too late to dig in and begin a new journey of success.", "author": "Unknown"},
        {"quote": "Your Monday morning thoughts set the tone for your whole week.", "author": "Germany Kent"},
        {"quote": "Hey, I know it's Monday. But it's also a new day and a new week. And in that lies a new opportunity for something special to happen.", "author": "Michael Ely"},
        {"quote": "New Monday, new week, new goals.", "author": "Unknown"},
        {"quote": "Monday is for people with a mission.", "author": "Unknown"},
        {"quote": "Mondays are the start of the work week which offer new beginnings 52 times a year!", "author": "David Dweck"},
        {"quote": "Either you run the day or the day runs you.", "author": "Jim Rohn"},
        {"quote": "This is your Monday morning reminder that you can handle whatever this week throws at you.", "author": "Unknown"},
        {"quote": "Each Monday is a blank canvas. Paint a masterpiece.", "author": "Unknown"},
    ]
    
    async def get_monday_motivation(self, user_id: str) -> Dict[str, str]:
        """Get Monday motivation with no-repeat tracking"""
        if self.db is not None:
            quote_data = await self._get_next_quote(user_id, "monday")
        else:
            quote_data = random.choice(self.MONDAY_QUOTES)
        return self._format_message(quote_data, "Monday Motivation")
    
    async def get_midweek_motivation(self, user_id: str) -> Dict[str, str]:
        """Get weekday motivation with no-repeat tracking"""
        if self.db is not None:
            quote_data = await self._get_next_quote(user_id, "weekday")
        else:
            quote_data = random.choice(self.MOTIVATIONAL_QUOTES)
        return self._format_message(quote_data, "Daily Inspiration")
    
    async def _get_next_quote(self, user_id: str, quote_type: str) -> Dict:
        """Get next unseen quote for user, with tracking to prevent repeats"""
        # Get user's quote history
        history = await self.db.quote_history.find_one({"user_id": user_id, "type": quote_type})
        
        # Determine quote pool
        quote_pool = self.MONDAY_QUOTES if quote_type == "monday" else self.MOTIVATIONAL_QUOTES
        
        # Get quotes not yet seen
        seen_quotes = set(history.get("seen_quotes", [])) if history else set()
        
        # If all quotes seen, reset
        if len(seen_quotes) >= len(quote_pool):
            seen_quotes = set()
            await self.db.quote_history.update_one(
                {"user_id": user_id, "type": quote_type},
                {"$set": {"seen_quotes": []}},
                upsert=True
            )
        
        # Get unseen quotes
        unseen_quotes = [q for i, q in enumerate(quote_pool) if i not in seen_quotes]
        
        # Pick random from unseen
        selected_quote = random.choice(unseen_quotes)
        selected_index = quote_pool.index(selected_quote)
        
        # Mark as seen
        await self.db.quote_history.update_one(
            {"user_id": user_id, "type": quote_type},
            {
                "$addToSet": {"seen_quotes": selected_index},
                "$set": {"last_sent": datetime.utcnow()}
            },
            upsert=True
        )
        
        return selected_quote
    
    def _format_message(self, quote_data: Dict, title: str) -> Dict[str, str]:
        """Format quote as WhatsApp message"""
        whatsapp_message = f"""✨ *{title}* ✨

_{quote_data['quote']}_

— {quote_data['author']}

Keep pushing forward! Your customers are counting on you. 💪"""
        
        return {
            "title": title,
            "message": whatsapp_message,
            "quote": quote_data['quote'],
            "author": quote_data['author']
        }
    
    @staticmethod
    def get_random_weekdays(exclude_monday: bool = True) -> List[int]:
        """Get 2 random weekdays for motivation (consistent per week)"""
        week_num = datetime.utcnow().isocalendar()[1]
        random.seed(week_num)
        
        weekdays = [1, 2, 3, 4] if exclude_monday else [0, 1, 2, 3, 4]
        selected = random.sample(weekdays, 2)
        
        random.seed()
        return sorted(selected)


# Singleton instance
_motivation_service = None

def get_motivation_service(db: Optional[AsyncIOMotorDatabase] = None) -> MotivationService:
    """Get singleton instance of MotivationService"""
    global _motivation_service
    if _motivation_service is None:
        _motivation_service = MotivationService(db)
    elif db is not None and _motivation_service.db is None:
        _motivation_service.db = db
    return _motivation_service
