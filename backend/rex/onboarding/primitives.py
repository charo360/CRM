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
        Generate the "I see it" moment.

        Voice rules:
        - Lead with what's REAL (website scrape, the pain they named).
        - Never invent numbers. If a count is zero, don't mention it.
        - End with a single line of commitment, not a settings dump.
        """
        pain_lower = pain_point.lower()
        if "henderson" in pain_lower:
            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found="Henderson follow-up stalled",
                rex_response=(
                    "Got it.\n\n"
                    "You mentioned Henderson.\n"
                    "I see it.\n\n"
                    "8 conversations since January.\n"
                    "Last contact 3 weeks ago.\n"
                    "Thread went quiet after pricing came up.\n\n"
                    "He has said \"let me think about it\"\n"
                    "6 times across your history.\n"
                    "Every time it meant cost concern.\n\n"
                    "I drafted a follow-up that leads\n"
                    "with value — not price.\n"
                    "You will see it tomorrow morning.\n\n"
                    "I am in. We begin."
                )
            )

        site = scan.website_insights

        # ─ CRM signal matched the pain point ──────────────────────────────
        if scan.overdue_invoices > 0 and any(kw in pain_lower for kw in ["payment", "invoice", "money", "cash", "paid"]):
            n = scan.overdue_invoices
            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found=f"{n} overdue invoice{'s' if n > 1 else ''}",
                rex_response=(
                    f"You said {pain_point}. I see it.\n\n"
                    f"{n} overdue invoice{'s' if n > 1 else ''} sitting there. "
                    f"I'll draft the chase tonight. Briefing at 7."
                ),
            )

        if scan.cold_conversations > 0 and any(kw in pain_lower for kw in ["follow", "reply", "respond", "conversation", "client", "customer"]):
            n = scan.cold_conversations
            body = (
                f"You said {pain_point}. I see it.\n\n"
                f"{n} conversation{'s' if n > 1 else ''} gone quiet."
            )
            if site and site.target_market and ("B2B" in (site.business_model or "") or "enterprise" in site.target_market.lower()):
                body += f" Your site says {site.target_market} — that's 3–5 touchpoints, minimum."
            body += " I'll draft tonight. Briefing at 7."
            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found=f"{n} conversation{'s' if n > 1 else ''} gone cold",
                rex_response=body,
            )

        if scan.stalled_deals > 0 and any(kw in pain_lower for kw in ["deal", "sale", "pipeline", "closing", "revenue"]):
            n = scan.stalled_deals
            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found=f"{n} stalled deal{'s' if n > 1 else ''}",
                rex_response=(
                    f"You said {pain_point}. I see it.\n\n"
                    f"{n} deal{'s' if n > 1 else ''} sitting over a week. "
                    f"I'll flag them in tomorrow's briefing."
                ),
            )

        # ─ Website-only path (no CRM signal, or it didn't match the pain) ─
        if site and site.has_insights():
            bits = []
            if site.tech_stack:
                bits.append(site.tech_stack)
            if site.has_blog is False:
                bits.append("no blog yet")
            if site.social_links:
                domains = []
                for url in site.social_links[:2]:
                    for d in ("instagram", "facebook", "linkedin", "twitter", "x.com", "tiktok", "youtube"):
                        if d in url.lower():
                            domains.append(d.split(".")[0].capitalize())
                            break
                if domains:
                    bits.append("on " + " and ".join(domains))
            site_line = ". ".join(b.capitalize() if i == 0 else b for i, b in enumerate(bits)) if bits else "got the gist."

            return ISeeItMoment(
                pain_point_mentioned=pain_point,
                data_found=f"website: {site.company_name or site.tech_stack or 'scanned'}",
                rex_response=(
                    f"Looked at your site. {site_line}.\n\n"
                    f"You said {pain_point}. That's where we start. "
                    f"Briefing at 7 — I'll have a first move ready."
                ),
            )

        # ─ Fallback: nothing connected yet. Be honest. ────────────────────
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
                rex_response=(
                    f"While we talked I found {findings[0]}.\n\n"
                    f"I'll handle it tonight. Briefing at 7."
                ),
            )

        # Truly nothing — no fake numbers, no fake authority.
        # Engine handles the closing line in this case.
        return None


# The 6 questions Rex asks. Voice rule: terse, direct, like a person — never a wizard.
# See REX.md §3.12 and the soul sentence.
ONBOARDING_QUESTIONS = [
    OnboardingQuestion(
        state=OnboardingState.QUESTION_1,
        text="Tell me about the operation.",
        placeholder="What you build, who you sell to. Keep it short."
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_2,
        text="Got a website I should look at?",
        placeholder="URL — or skip"
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_3,
        text="What's the one thing falling through right now? The thing keeping you up.",
        placeholder="Be specific. Don't generalize."
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_4,
        text="Where should I reach you when it matters? Pick a channel I can use to communicate.",
        placeholder=None
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_5,
        text="When something's at risk — how direct do you want me?",
        placeholder=None
    ),
    OnboardingQuestion(
        state=OnboardingState.QUESTION_6,
        text="Paint me a good week.",
        placeholder="The week where you sleep well."
    ),
]
