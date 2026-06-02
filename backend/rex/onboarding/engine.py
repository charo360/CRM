"""
Phase 11: Day 0 Onboarding — Engine

The state machine that runs the 5-question interview,
triggers background scanning, and generates the "I see it" moment.
"""

from typing import Optional, Protocol
from .primitives import (
    OnboardingState,
    OnboardingAnswers,
    BackgroundScan,
    ISeeItMoment,
    CommunicationChannel,
    DirectnessLevel,
    ONBOARDING_QUESTIONS,
)


class DataScanner(Protocol):
    """
    Protocol for scanning the founder's existing data
    while they're answering onboarding questions.
    """
    def scan_invoices(self) -> int:
        """Return count of overdue invoices."""
        ...
    
    def scan_conversations(self) -> int:
        """Return count of cold conversations (>7 days no reply)."""
        ...
    
    def scan_deals(self) -> int:
        """Return count of stalled deals (>7 days no movement)."""
        ...
    
    def scan_emails(self) -> int:
        """Return count of unread emails."""
        ...
    
    def scan_opportunities(self) -> int:
        """Return count of new opportunities found by Scout."""
        ...


class OnboardingEngine:
    """
    Manages the Day 0 onboarding interview flow.
    
    The engine:
    1. Presents 5 questions in sequence
    2. Triggers background data scanning after Q2
    3. Generates the "I see it" moment at the end
    4. Stores answers and preferences
    """
    
    def __init__(self, scanner: Optional[DataScanner] = None):
        self.state = OnboardingState.NOT_STARTED
        self.answers = OnboardingAnswers()
        self.scan: Optional[BackgroundScan] = None
        self.i_see_it: Optional[ISeeItMoment] = None
        self._scanner = scanner
    
    def start(self) -> str:
        """
        Begin the onboarding interview.
        Returns Rex's welcome message.
        """
        self.state = OnboardingState.QUESTION_1
        return (
            "Before I start — give me a minute.\n\n"
            "Six quick questions. I'm not building a profile. "
            "I'm trying to figure out what you actually need from me."
        )
    
    def get_current_question(self) -> Optional[str]:
        """Get the current question text."""
        if self.state == OnboardingState.NOT_STARTED:
            return None
        if self.state == OnboardingState.COMPLETE:
            return None
        if self.state == OnboardingState.SCANNING:
            return "Reading your data..."
        if self.state == OnboardingState.I_SEE_IT:
            return None
        
        for q in ONBOARDING_QUESTIONS:
            if q.state == self.state:
                return q.text
        
        return None
    
    def answer_question_1(self, business_type: str) -> str:
        """Answer: What kind of business?"""
        if self.state != OnboardingState.QUESTION_1:
            raise ValueError(f"Cannot answer Q1 in state {self.state}")
        
        self.answers.business_type = business_type.strip()
        self.state = OnboardingState.QUESTION_2
        
        return ONBOARDING_QUESTIONS[1].text
    
    def answer_question_2(self, website_url: str) -> str:
        """Answer: Do you have a website?"""
        if self.state != OnboardingState.QUESTION_2:
            raise ValueError(f"Cannot answer Q2 in state {self.state}")
        
        self.answers.website_url = website_url.strip()
        self.state = OnboardingState.QUESTION_3
        
        return ONBOARDING_QUESTIONS[2].text
    
    def answer_question_3(self, pain_point: str) -> str:
        """
        Answer: What's falling through the cracks?
        
        This is the critical question. After they answer,
        Rex starts scanning their data in the background.
        """
        if self.state != OnboardingState.QUESTION_3:
            raise ValueError(f"Cannot answer Q3 in state {self.state}")
        
        self.answers.pain_point = pain_point.strip()
        
        # Trigger background scan (always, even if no scanner provided)
        self._trigger_background_scan()
        
        self.state = OnboardingState.QUESTION_4
        return ONBOARDING_QUESTIONS[3].text
    
    def answer_question_4(self, channel: CommunicationChannel) -> str:
        """Answer: How should Rex communicate?"""
        if self.state != OnboardingState.QUESTION_4:
            raise ValueError(f"Cannot answer Q4 in state {self.state}")
        
        self.answers.channel = channel
        self.state = OnboardingState.QUESTION_5
        
        return ONBOARDING_QUESTIONS[4].text
    
    def answer_question_5(self, directness: DirectnessLevel) -> str:
        """Answer: How direct should Rex be?"""
        if self.state != OnboardingState.QUESTION_5:
            raise ValueError(f"Cannot answer Q5 in state {self.state}")
        
        self.answers.directness = directness
        self.state = OnboardingState.QUESTION_6
        
        return ONBOARDING_QUESTIONS[5].text
    
    def answer_question_6(self, good_week: str) -> str:
        """
        Answer: What does a good week look like?
        
        This is the final question. After this, Rex generates
        the "I see it" moment if he found anything in the scan.
        """
        if self.state != OnboardingState.QUESTION_6:
            raise ValueError(f"Cannot answer Q6 in state {self.state}")
        
        self.answers.good_week = good_week.strip()
        
        # Generate the "I see it" moment
        return self._generate_i_see_it_moment()
    
    def _trigger_background_scan(self) -> None:
        """
        Scan the founder's data in the background.
        This runs while they're answering Q4-Q6.
        Also scrapes their website if they provided a URL.
        """
        if not self._scanner:
            # No scanner provided — create empty scan
            self.scan = BackgroundScan()
            return
        
        # Scan website if URL was provided
        website_insights = None
        if self.answers.website_url:
            website_insights = self._scanner.scan_website(self.answers.website_url)
        
        # Scanner provided — run actual scan
        self.scan = BackgroundScan(
            overdue_invoices=self._scanner.scan_invoices(),
            cold_conversations=self._scanner.scan_conversations(),
            stalled_deals=self._scanner.scan_deals(),
            unread_emails=self._scanner.scan_emails(),
            opportunities_found=self._scanner.scan_opportunities(),
            website_insights=website_insights,
        )
    
    def _generate_i_see_it_moment(self) -> str:
        """
        Generate the "I see it" moment by connecting
        what they said in Q3 to what Rex found in their data.
        """
        if not self.scan:
            # No scan at all — shouldn't happen in practice, but handle it.
            self.state = OnboardingState.COMPLETE
            return f"You said {self.answers.pain_point}. That's enough to start. Briefing at 7."

        self.i_see_it = ISeeItMoment.generate(
            pain_point=self.answers.pain_point,
            scan=self.scan,
        )

        self.state = OnboardingState.I_SEE_IT

        if self.i_see_it:
            return self.i_see_it.rex_response

        # Scan ran but found nothing. Don't fake it — be honest.
        return (
            f"Haven't been let into your data yet. So no magic trick today.\n\n"
            f"You said {self.answers.pain_point}. That's enough to start. Briefing at 7."
        )
    
    def complete(self) -> None:
        """Mark onboarding as complete."""
        self.state = OnboardingState.COMPLETE
    
    def is_complete(self) -> bool:
        """Check if onboarding is finished."""
        return self.state == OnboardingState.COMPLETE
    
    def get_preferences(self) -> dict:
        """
        Export the founder's preferences for storage.
        This gets saved to the Notebook and used by Rex going forward.
        """
        return {
            "business_type": self.answers.business_type,
            "website_url": self.answers.website_url,
            "pain_point": self.answers.pain_point,
            "channel": self.answers.channel.value if self.answers.channel else "in_app",
            "directness": self.answers.directness.value if self.answers.directness else "context",
            "good_week": self.answers.good_week,
            "scan_findings": {
                "overdue_invoices": self.scan.overdue_invoices if self.scan else 0,
                "cold_conversations": self.scan.cold_conversations if self.scan else 0,
                "stalled_deals": self.scan.stalled_deals if self.scan else 0,
                "unread_emails": self.scan.unread_emails if self.scan else 0,
                "opportunities_found": self.scan.opportunities_found if self.scan else 0,
            } if self.scan else {},
            "website_insights": {
                "company_name": self.scan.website_insights.company_name,
                "industry": self.scan.website_insights.industry,
                "business_model": self.scan.website_insights.business_model,
                "target_market": self.scan.website_insights.target_market,
                "tech_stack": self.scan.website_insights.tech_stack,
                "has_blog": self.scan.website_insights.has_blog,
                "social_links": self.scan.website_insights.social_links,
                "contact_email": self.scan.website_insights.contact_email,
            } if self.scan and self.scan.website_insights else {},
            "i_see_it_moment": {
                "pain_point": self.i_see_it.pain_point_mentioned,
                "data_found": self.i_see_it.data_found,
                "response": self.i_see_it.rex_response,
            } if self.i_see_it else None,
        }
