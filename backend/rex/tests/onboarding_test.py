"""
Phase 11 Tests: Day 0 Onboarding

Tests the 5-question interview flow, background data scanning,
and the "I see it" moment generation.
"""

import pytest

from rex.onboarding import (
    OnboardingEngine,
    OnboardingState,
    CommunicationChannel,
    DirectnessLevel,
    MockDataScanner,
    BackgroundScan,
    WebsiteInsights,
    ISeeItMoment,
)


class TestOnboardingFlow:
    """Test the basic 6-question interview flow."""
    
    def test_start_onboarding(self):
        """Test starting the onboarding interview."""
        engine = OnboardingEngine()
        welcome = engine.start()
        
        assert engine.state == OnboardingState.QUESTION_1
        assert "Before I start" in welcome
        assert "Five quick questions" in welcome
    
    def test_question_1_business_type(self):
        """Test answering Q1: What kind of business?"""
        engine = OnboardingEngine()
        engine.start()
        
        q2 = engine.answer_question_1("Marketing agency")
        
        assert engine.state == OnboardingState.QUESTION_2
        assert engine.answers.business_type == "Marketing agency"
        assert "website" in q2.lower()
    
    def test_question_2_website(self):
        """Test answering Q2: Do you have a website?"""
        engine = OnboardingEngine()
        engine.start()
        engine.answer_question_1("E-commerce store")
        
        q3 = engine.answer_question_2("mystore.com")
        
        assert engine.state == OnboardingState.QUESTION_3
        assert engine.answers.website_url == "mystore.com"
        assert "falling through" in q3.lower()
    
    def test_question_3_pain_point(self):
        """Test answering Q3: What's falling through?"""
        engine = OnboardingEngine()
        engine.start()
        engine.answer_question_1("Consulting")
        engine.answer_question_2("consulting.com")
        
        q4 = engine.answer_question_3("Invoices not getting paid")
        
        assert engine.state == OnboardingState.QUESTION_4
        assert engine.answers.pain_point == "Invoices not getting paid"
        assert "communicate" in q4.lower()
    
    def test_question_4_channel(self):
        """Test answering Q4: How should Rex communicate?"""
        engine = OnboardingEngine()
        engine.start()
        engine.answer_question_1("Agency")
        engine.answer_question_2("agency.com")
        engine.answer_question_3("Deals going cold")
        
        q5 = engine.answer_question_4(CommunicationChannel.EMAIL)
        
        assert engine.state == OnboardingState.QUESTION_5
        assert engine.answers.channel == CommunicationChannel.EMAIL
        assert "direct" in q5.lower()
    
    def test_question_5_directness(self):
        """Test answering Q5: How direct should Rex be?"""
        engine = OnboardingEngine()
        engine.start()
        engine.answer_question_1("SaaS startup")
        engine.answer_question_2("saas.com")
        engine.answer_question_3("Pipeline visibility")
        engine.answer_question_4(CommunicationChannel.IN_APP)
        
        q6 = engine.answer_question_5(DirectnessLevel.CONTEXT_FIRST)
        
        assert engine.state == OnboardingState.QUESTION_6
        assert engine.answers.directness == DirectnessLevel.CONTEXT_FIRST
        assert "good week" in q6.lower()
    
    def test_question_6_completes_onboarding(self):
        """Test answering Q6: What's a good week?"""
        engine = OnboardingEngine()
        engine.start()
        engine.answer_question_1("SaaS startup")
        engine.answer_question_2("")
        engine.answer_question_3("Pipeline visibility")
        engine.answer_question_4(CommunicationChannel.IN_APP)
        engine.answer_question_5(DirectnessLevel.CONTEXT_FIRST)
        
        response = engine.answer_question_6("3 deals closed, inbox clear")
        
        assert engine.state in [OnboardingState.I_SEE_IT, OnboardingState.COMPLETE]
        assert engine.answers.good_week == "3 deals closed, inbox clear"
        assert "I'm in" in response or "Got it" in response


class TestBackgroundScanning:
    """Test the background data scanning during onboarding."""
    
    def test_scanner_finds_overdue_invoices(self):
        """Test scanner detecting overdue invoices."""
        scanner = MockDataScanner(
            overdue_invoices=3,
            cold_conversations=0,
            stalled_deals=0,
        )
        
        assert scanner.scan_invoices() == 3
        assert scanner.scan_conversations() == 0
        assert scanner.scan_deals() == 0
    
    def test_scanner_finds_cold_conversations(self):
        """Test scanner detecting cold conversations."""
        scanner = MockDataScanner(
            overdue_invoices=0,
            cold_conversations=7,
            stalled_deals=0,
        )
        
        assert scanner.scan_conversations() == 7
    
    def test_scanner_finds_stalled_deals(self):
        """Test scanner detecting stalled deals."""
        scanner = MockDataScanner(
            overdue_invoices=0,
            cold_conversations=0,
            stalled_deals=2,
        )
        
        assert scanner.scan_deals() == 2
    
    def test_scan_triggers_after_question_3(self):
        """Test that background scan starts after Q3 (pain point)."""
        scanner = MockDataScanner(
            overdue_invoices=3,
            cold_conversations=7,
            stalled_deals=2,
        )
        engine = OnboardingEngine(scanner=scanner)
        
        engine.start()
        engine.answer_question_1("Agency")
        engine.answer_question_2("agency.com")
        
        # Scan should not have run yet
        assert engine.scan is None
        
        engine.answer_question_3("Follow-ups falling through")
        
        # Scan should have run after Q3
        assert engine.scan is not None
        assert engine.scan.overdue_invoices == 3
        assert engine.scan.cold_conversations == 7
        assert engine.scan.stalled_deals == 2


class TestISeeItMoment:
    """Test the 'I see it' moment generation."""
    
    def test_i_see_it_matches_invoice_pain_point(self):
        """Test matching invoice pain point to scan findings."""
        scan = BackgroundScan(
            overdue_invoices=3,
            cold_conversations=0,
            stalled_deals=0,
        )
        
        moment = ISeeItMoment.generate(
            pain_point="Invoices not getting paid on time",
            scan=scan,
        )
        
        assert moment is not None
        assert "3 overdue invoice" in moment.rex_response
        assert "I see it" in moment.rex_response
    
    def test_i_see_it_matches_conversation_pain_point(self):
        """Test matching conversation pain point to scan findings."""
        scan = BackgroundScan(
            overdue_invoices=0,
            cold_conversations=7,
            stalled_deals=0,
        )
        
        moment = ISeeItMoment.generate(
            pain_point="Follow-ups with clients falling through",
            scan=scan,
        )
        
        assert moment is not None
        assert "7 conversation" in moment.rex_response
        assert "gone quiet" in moment.rex_response
    
    def test_i_see_it_matches_deal_pain_point(self):
        """Test matching deal pain point to scan findings."""
        scan = BackgroundScan(
            overdue_invoices=0,
            cold_conversations=0,
            stalled_deals=2,
        )
        
        moment = ISeeItMoment.generate(
            pain_point="Deals sitting in pipeline too long",
            scan=scan,
        )
        
        assert moment is not None
        assert "2 deal" in moment.rex_response
        assert "stalled" in moment.rex_response or "sitting" in moment.rex_response
    
    def test_i_see_it_fallback_when_no_match(self):
        """Test fallback when pain point doesn't match findings."""
        scan = BackgroundScan(
            overdue_invoices=3,
            cold_conversations=0,
            stalled_deals=0,
        )
        
        moment = ISeeItMoment.generate(
            pain_point="Social media engagement is low",
            scan=scan,
        )
        
        # Should still generate a moment showing what Rex found
        assert moment is not None
        assert "3 overdue invoice" in moment.rex_response
    
    def test_no_i_see_it_when_scan_empty(self):
        """Test no moment generated when scan finds nothing."""
        scan = BackgroundScan(
            overdue_invoices=0,
            cold_conversations=0,
            stalled_deals=0,
        )
        
        moment = ISeeItMoment.generate(
            pain_point="Everything is falling apart",
            scan=scan,
        )
        
        assert moment is None


class TestFullOnboardingFlow:
    """Test the complete end-to-end onboarding flow."""
    
    def test_complete_flow_with_i_see_it_moment(self):
        """Test full flow with successful 'I see it' moment."""
        scanner = MockDataScanner(
            overdue_invoices=3,
            cold_conversations=7,
            stalled_deals=2,
        )
        engine = OnboardingEngine(scanner=scanner)
        
        # Start
        welcome = engine.start()
        assert "Five quick questions" in welcome
        
        # Q1
        q2 = engine.answer_question_1("Marketing agency")
        assert "website" in q2.lower()
        
        # Q2
        q3 = engine.answer_question_2("agency.com")
        assert "falling through" in q3.lower()
        
        # Q3 (triggers scan)
        q4 = engine.answer_question_3("Follow-ups with clients")
        assert "communicate" in q4.lower()
        assert engine.scan is not None
        
        # Q4
        q5 = engine.answer_question_4(CommunicationChannel.WHATSAPP)
        assert "direct" in q5.lower()
        
        # Q5
        q6 = engine.answer_question_5(DirectnessLevel.STRAIGHT)
        assert "good week" in q6.lower()
        
        # Q6 (generates I see it moment)
        final = engine.answer_question_6("3 deals closed, inbox clear")
        assert "I see it" in final or "conversation" in final
        assert engine.i_see_it is not None
        
        # Export preferences
        prefs = engine.get_preferences()
        assert prefs["business_type"] == "Marketing agency"
        assert prefs["website_url"] == "agency.com"
        assert prefs["pain_point"] == "Follow-ups with clients"
        assert prefs["channel"] == "whatsapp"
        assert prefs["directness"] == "straight"
        assert prefs["scan_findings"]["cold_conversations"] == 7
        assert prefs["i_see_it_moment"] is not None
    
    def test_complete_flow_without_scanner(self):
        """Test full flow without data scanner (demo mode)."""
        engine = OnboardingEngine(scanner=None)
        
        engine.start()
        engine.answer_question_1("E-commerce")
        engine.answer_question_2("")
        engine.answer_question_3("Inventory management")
        engine.answer_question_4(CommunicationChannel.EMAIL)
        engine.answer_question_5(DirectnessLevel.CONTEXT_FIRST)
        final = engine.answer_question_6("10 orders shipped")
        
        assert "I'm in" in final or "Got it" in final
        assert engine.scan is not None  # Empty scan created
        assert engine.i_see_it is None  # No moment without findings
    
    def test_preferences_export_structure(self):
        """Test the structure of exported preferences."""
        scanner = MockDataScanner(overdue_invoices=2)
        engine = OnboardingEngine(scanner=scanner)
        
        engine.start()
        engine.answer_question_1("Consulting")
        engine.answer_question_2("consulting.com")
        engine.answer_question_3("Invoices not paid")
        engine.answer_question_4(CommunicationChannel.TELEGRAM)
        engine.answer_question_5(DirectnessLevel.STRAIGHT)
        engine.answer_question_6("All invoices paid on time")
        
        prefs = engine.get_preferences()
        
        # Check structure
        assert "business_type" in prefs
        assert "pain_point" in prefs
        assert "channel" in prefs
        assert "directness" in prefs
        assert "good_week" in prefs
        assert "scan_findings" in prefs
        assert "i_see_it_moment" in prefs
        
        # Check values
        assert prefs["channel"] == "telegram"
        assert prefs["directness"] == "straight"
        assert prefs["scan_findings"]["overdue_invoices"] == 2


class TestOnboardingStateValidation:
    """Test state machine validation and error handling."""
    
    def test_cannot_answer_before_start(self):
        """Test that answering questions before start raises error."""
        engine = OnboardingEngine()
        
        with pytest.raises(ValueError):
            engine.answer_question_1("Business")
    
    def test_cannot_skip_questions(self):
        """Test that skipping questions raises error."""
        engine = OnboardingEngine()
        engine.start()
        
        with pytest.raises(ValueError):
            engine.answer_question_2("Pain point")
    
    def test_cannot_answer_same_question_twice(self):
        """Test that answering same question twice raises error."""
        engine = OnboardingEngine()
        engine.start()
        engine.answer_question_1("Business")
        
        with pytest.raises(ValueError):
            engine.answer_question_1("Different business")
    
    def test_get_current_question_text(self):
        """Test getting current question text."""
        engine = OnboardingEngine()
        
        assert engine.get_current_question() is None
        
        engine.start()
        q1 = engine.get_current_question()
        assert "kind of business" in q1.lower()
        
        engine.answer_question_1("Agency")
        q2 = engine.get_current_question()
        assert "website" in q2.lower()
        
        engine.answer_question_2("agency.com")
        q3 = engine.get_current_question()
        assert "falling through" in q3.lower()
