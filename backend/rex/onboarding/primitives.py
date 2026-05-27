"""
Phase 11: Day 0 Onboarding — Primitives

The 5-question interview flow that Rex uses to understand
a new founder's business while scanning their data in the background.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OnboardingState(Enum):
    """State machine for the onboarding interview."""
    NOT_STARTED = "not_started"
    QUESTION_1 = "question_1"  # What kind of business?
    QUESTION_2 = "question_2"  # Do you have a website?
    QUESTION_3 = "question_3"  # What's falling through the cracks?
    QUESTION_4 = "question_4"  # How should Rex communicate?
    QUESTION_5 = "question_5"  # How direct should Rex be?
    QUESTION_6 = "question_6"  # What does a good week look like?
    SCANNING = "scanning"       # Background data scan + website scrape in progress
    I_SEE_IT = "i_see_it"      # The magic moment
    COMPLETE = "complete"


class CommunicationChannel(Enum):
    """How the founder wants Rex to reach them."""
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    EMAIL = "email"
    IN_APP = "in_app"


class DirectnessLevel(Enum):
    """How direct Rex should be when flagging risks."""
    STRAIGHT = "straight"      # "Tell me straight — no softening"
    CONTEXT_FIRST = "context"  # "Give me context before the bad news"


@dataclass(frozen=True)
class OnboardingQuestion:
    """A single question in the interview flow."""
    state: OnboardingState
    text: str
    placeholder: Optional[str] = None


@dataclass
class OnboardingAnswers:
    """The founder's answers to the 6 questions."""
    business_type: str = ""
    website_url: str = ""
    pain_point: str = ""
    channel: Optional[CommunicationChannel] = None
    directness: Optional[DirectnessLevel] = None
    good_week: str = ""


@dataclass
class WebsiteInsights:
    """Data scraped from the founder's website."""
    company_name: str = ""
    industry: str = ""
    business_model: str = ""  # B2B, B2C, SaaS, ecommerce, etc.
    target_market: str = ""
    tech_stack: str = ""  # Shopify, WordPress, custom, etc.
    has_blog: bool = False
    social_links: list[str] = None
    contact_email: str = ""
    
    def __post_init__(self):
        if self.social_links is None:
            self.social_links = []
    
    def has_insights(self) -> bool:
        """Check if we learned anything from the website."""
        return any([
            self.company_name,
            self.industry,
            self.business_model,
            self.target_market,
        ])


@dataclass
class BackgroundScan:
    """What Rex discovered while the founder was answering questions."""
    overdue_invoices: int = 0
    cold_conversations: int = 0
    unread_emails: int = 0
    stalled_deals: int = 0
    opportunities_found: int = 0
    website_insights: Optional[WebsiteInsights] = None
    
    def has_findings(self) -> bool:
        """Check if Rex found anything worth mentioning."""
        return any([
            self.overdue_invoices > 0,
            self.cold_conversations > 0,
            self.stalled_deals > 0,
            self.opportunities_found > 0,
            self.website_insights and self.website_insights.has_insights(),
        ])


@dataclass
class ISeeItMoment:
    """The connection between what they said and what Rex found."""
    pain_point_mentioned: str
    data_found: str
    rex_response: str
    
    @staticmethod
    def generate(pain_point: str, scan: BackgroundScan) -> Optional["ISeeItMoment"]:
        """
        Generate the "I see it" moment by connecting the founder's
        pain point to what Rex found in their data.
        """
        if not scan.has_findings():
            return None
        
        # Match pain point keywords to scan findings
        pain_lower = pain_point.lower()
        
        if scan.overdue_invoices > 0 and any(kw in pain_lower for kw in ["payment", "invoice", "money", "cash", "paid"]):
            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found=f"{scan.overdue_invoices} overdue invoice{'s' if scan.overdue_invoices > 1 else ''}",
                rex_response=f"You mentioned {pain_point}. I see it.\n\n"
                            f"You've got {scan.overdue_invoices} overdue invoice{'s' if scan.overdue_invoices > 1 else ''}. "
                            f"I'll handle it tonight. You'll see it in tomorrow's briefing."
            )
        
        if scan.cold_conversations > 0 and any(kw in pain_lower for kw in ["follow", "reply", "respond", "conversation", "client", "customer"]):
            base_response = (
                f"You mentioned {pain_point}. I see it.\n\n"
                f"{scan.cold_conversations} conversation{'s' if scan.cold_conversations > 1 else ''} "
                f"{'have' if scan.cold_conversations > 1 else 'has'} gone quiet in the last 14 days."
            )
            
            # Add website insight if available
            if scan.website_insights and scan.website_insights.business_model:
                if "B2B" in scan.website_insights.business_model or "enterprise" in scan.website_insights.target_market.lower():
                    base_response += f" I checked your site — you're targeting {scan.website_insights.target_market or 'enterprise clients'}. Those deals need 3-5 touchpoints."
            
            base_response += " I'll draft follow-ups tonight."
            
            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found=f"{scan.cold_conversations} conversation{'s' if scan.cold_conversations > 1 else ''} gone cold",
                rex_response=base_response
            )
        
        if scan.stalled_deals > 0 and any(kw in pain_lower for kw in ["deal", "sale", "pipeline", "closing", "revenue"]):
            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found=f"{scan.stalled_deals} stalled deal{'s' if scan.stalled_deals > 1 else ''}",
                rex_response=f"You mentioned {pain_point}. I see it.\n\n"
                            f"{scan.stalled_deals} deal{'s' if scan.stalled_deals > 1 else ''} "
                            f"{'have' if scan.stalled_deals > 1 else 'has'} been sitting for over a week. "
                            f"I'll flag them in your first briefing."
            )
        
        # Fallback: just show what Rex found
        findings = []
        if scan.overdue_invoices > 0:
            findings.append(f"{scan.overdue_invoices} overdue invoice{'s' if scan.overdue_invoices > 1 else ''}")
        if scan.cold_conversations > 0:
            findings.append(f"{scan.cold_conversations} cold conversation{'s' if scan.cold_conversations > 1 else ''}")
        if scan.stalled_deals > 0:
            findings.append(f"{scan.stalled_deals} stalled deal{'s' if scan.stalled_deals > 1 else ''}")
        
        if findings:
            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found=", ".join(findings),
                rex_response=f"Got it.\n\nOne more thing —\n\n"
                            f"I see {findings[0]}. "
                            f"I'll handle it tonight. You'll see it in tomorrow's briefing.\n\n"
                            f"I'm in. We begin."
            )
        
        return None


# The 6 questions Rex asks
ONBOARDING_QUESTIONS = [
    OnboardingQuestion(
        state=OnboardingState.QUESTION_1,
        text="What kind of business are you running?",
        placeholder="e.g., Marketing agency, e-commerce store, consulting..."
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_2,
        text="Do you have a website or online presence I should check?",
        placeholder="e.g., mycompany.com or leave blank if none"
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_3,
        text="What's the one thing falling through the cracks right now? The thing that keeps you up?",
        placeholder="Be specific — this is where Rex learns what matters most"
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_4,
        text="How do you prefer I communicate with you — WhatsApp, email, or inside the app?",
        placeholder=None  # This will be buttons, not text input
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_5,
        text="How direct do you want me to be when something's at risk?",
        placeholder=None  # This will be buttons, not text input
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_6,
        text="What does a good week look like for you?",
        placeholder="e.g., 3 new deals closed, inbox at zero, no fires..."
    ),
]
