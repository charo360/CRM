"""
Phase 11: Day 0 Onboarding

The 5-question interview flow that Rex uses to understand
a new founder's business while scanning their data in the background.

Core components:
- OnboardingEngine: State machine managing the interview flow
- DataScanner: Scans existing data while founder answers questions
- ISeeItMoment: Connects founder's pain point to real data findings

Usage:
    from rex.onboarding import OnboardingEngine, MockDataScanner
    
    scanner = MockDataScanner(overdue_invoices=3, cold_conversations=7)
    engine = OnboardingEngine(scanner=scanner)
    
    # Start interview
    welcome = engine.start()
    
    # Answer questions
    q2 = engine.answer_question_1("Marketing agency")
    q3 = engine.answer_question_2("Follow-ups falling through")
    # ... etc
    
    # Get the "I see it" moment
    i_see_it = engine.answer_question_5("3 deals closed, inbox clear")
    
    # Export preferences
    prefs = engine.get_preferences()
"""

from .primitives import (
    OnboardingState,
    OnboardingAnswers,
    BackgroundScan,
    WebsiteInsights,
    ISeeItMoment,
    CommunicationChannel,
    DirectnessLevel,
    OnboardingQuestion,
    ONBOARDING_QUESTIONS,
)

from .engine import OnboardingEngine, DataScanner

from .scanner import (
    LiveDataScanner,
    MockDataScanner,
    HonestDemoScanner,
    InvoiceStore,
    ConversationStore,
    DealStore,
    EmailStore,
    ScoutStore,
)

__all__ = [
    # Primitives
    "OnboardingState",
    "OnboardingAnswers",
    "BackgroundScan",
    "WebsiteInsights",
    "ISeeItMoment",
    "CommunicationChannel",
    "DirectnessLevel",
    "OnboardingQuestion",
    "ONBOARDING_QUESTIONS",
    
    # Engine
    "OnboardingEngine",
    "DataScanner",
    
    # Scanner
    "LiveDataScanner",
    "MockDataScanner",
    "HonestDemoScanner",
    "InvoiceStore",
    "ConversationStore",
    "DealStore",
    "EmailStore",
    "ScoutStore",
]
