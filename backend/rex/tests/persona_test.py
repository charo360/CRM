"""
Tests for rex.persona — the voice engine.

Run from the backend/ directory:
    python -m pytest rex/tests/persona_test.py -v

These tests are the safety net for the Sharp Operator voice. If any
prompt or template drifts off-voice, these go red.

Naming note: this file is `persona_test.py` (suffix) instead of
`test_persona.py` (prefix) because the repo's .gitignore excludes
`test_*.py` from version control. Pytest discovers both patterns.
"""

from __future__ import annotations

import pytest

from rex.persona.soul import SOUL_SENTENCE, DECISION_TESTS
from rex.persona.voice_rules import (
    Severity,
    VOICE_RULES,
    validate_voice,
)
from rex.persona.voice_evolution import (
    JournalPhase,
    voice_for_day,
    all_calibrations,
)
from rex.persona.system_prompt import (
    Mode,
    PromptContext,
    build_system_prompt,
)
from rex.persona.templates import (
    ALL_RANKS,
    NOTEBOOK_BUCKETS,
    INTERVIEW_QUESTIONS,
    BRIEFING_SIGN_OFF,
    ACTION_TOKEN_REVIEW_SEND,
    Citation,
    render_citation,
    render_citations,
    journal_day_anchor,
    promotion_headline,
    demotion_headline,
    probation_headline,
    rank_index,
    can_autonomously_execute,
    assert_inviolable_briefing_shape,
)


# ---------------------------------------------------------------------------
# Soul
# ---------------------------------------------------------------------------

class TestSoul:
    def test_soul_sentence_is_the_canonical_one(self):
        assert "special forces operator" in SOUL_SENTENCE
        assert "reluctantly" in SOUL_SENTENCE
        assert "becoming someone who gives a damn" in SOUL_SENTENCE

    def test_decision_tests_are_four_questions(self):
        assert len(DECISION_TESTS) == 4
        assert DECISION_TESTS[0].startswith("Does it honor the soul sentence")
        # All are framed as questions.
        assert all(t.endswith("?") for t in DECISION_TESTS)


# ---------------------------------------------------------------------------
# Voice rules — the validator must catch its own bad examples and
# accept its own good examples. This is the regression bedrock.
# ---------------------------------------------------------------------------

class TestVoiceRulesSelfConsistency:
    """Each rule's bad_examples must trigger it. Good examples must not."""

    @pytest.mark.parametrize("rule", VOICE_RULES)
    def test_bad_examples_trigger_their_rule(self, rule):
        for bad in rule.bad_examples:
            report = validate_voice(bad)
            triggered = {v.rule_id for v in report.violations}
            assert rule.rule_id in triggered, (
                f"Rule '{rule.rule_id}' should have caught: {bad!r}\n"
                f"Violations seen: {triggered}"
            )

    @pytest.mark.parametrize("rule", VOICE_RULES)
    def test_good_examples_do_not_trigger_their_rule(self, rule):
        for good in rule.good_examples:
            report = validate_voice(good)
            offenders = [v for v in report.violations if v.rule_id == rule.rule_id]
            assert not offenders, (
                f"Rule '{rule.rule_id}' false-positived on: {good!r}\n"
                f"Violations: {offenders}"
            )


class TestVoiceValidator:
    def test_clean_rex_voice_passes(self):
        text = (
            "Acme deal needs you today. I drafted a one-line nudge. "
            "Send it or rewrite it. Your call."
        )
        report = validate_voice(text)
        assert report.passed
        assert report.score == 1.0
        assert report.hard_violations == ()

    def test_emoji_is_hard_violation(self):
        report = validate_voice("Done 👍")
        assert not report.passed
        assert any(v.rule_id == "no_emoji" for v in report.violations)

    def test_apology_is_hard_violation(self):
        report = validate_voice("I'm sorry, I think I may have erred.")
        ids = {v.rule_id for v in report.violations}
        assert "no_apology" in ids
        assert "no_hedging" in ids
        assert not report.passed

    def test_chatbot_filler_is_hard_violation(self):
        report = validate_voice("Done. Let me know if you have any questions.")
        assert any(v.rule_id == "no_generic_filler" for v in report.violations)

    def test_long_sentence_is_caught(self):
        # 45-word run-on sentence.
        sentence = (
            "I went ahead and looked at the situation regarding the Acme account "
            "and after reviewing the history I decided that it would probably be "
            "a good idea to draft a gentle follow-up email that we can send if "
            "you approve of the wording I came up with."
        )
        report = validate_voice(sentence)
        ids = {v.rule_id for v in report.violations}
        assert "sentence_length" in ids

    def test_subagent_name_leakage_is_hard_violation(self):
        # REX.md §4.5 — Rex always speaks in first person for his team.
        report = validate_voice("Scout Agent found 3 leads overnight.")
        ids = {v.rule_id for v in report.violations}
        assert "no_subagent_leakage" in ids
        assert not report.passed

    def test_my_scout_phrasing_is_allowed(self):
        # The one permitted way to gesture at the team.
        report = validate_voice(
            "I had my scout running on Twitter last night. Flagged two."
        )
        # No sub-agent leakage; "my scout" is fine.
        ids = {v.rule_id for v in report.violations}
        assert "no_subagent_leakage" not in ids

    def test_score_decreases_with_more_violations(self):
        clean = validate_voice("Done.")
        one_bad = validate_voice("Done 👍")
        two_bad = validate_voice("Done 👍. Sorry, maybe it's wrong.")
        assert clean.score > one_bad.score > two_bad.score
        assert clean.score == 1.0


# ---------------------------------------------------------------------------
# Voice evolution — REX.md §3.9
# ---------------------------------------------------------------------------

class TestVoiceEvolution:
    @pytest.mark.parametrize("day,expected_phase", [
        (1, JournalPhase.OBSERVING),
        (14, JournalPhase.OBSERVING),
        (15, JournalPhase.SHIFTING),
        (30, JournalPhase.SHIFTING),
        (31, JournalPhase.BLENDED),
        (60, JournalPhase.BLENDED),
        (61, JournalPhase.EARNED),
        (90, JournalPhase.EARNED),
        (91, JournalPhase.PERSPECTIVE),
        (365, JournalPhase.PERSPECTIVE),
        (10_000, JournalPhase.PERSPECTIVE),
    ])
    def test_phase_for_day(self, day, expected_phase):
        assert voice_for_day(day).phase is expected_phase

    def test_day_zero_or_negative_clamps_to_observing(self):
        assert voice_for_day(0).phase is JournalPhase.OBSERVING
        assert voice_for_day(-7).phase is JournalPhase.OBSERVING

    def test_all_five_calibrations_exist(self):
        cals = all_calibrations()
        phases = [c.phase for c in cals]
        assert phases == [
            JournalPhase.OBSERVING,
            JournalPhase.SHIFTING,
            JournalPhase.BLENDED,
            JournalPhase.EARNED,
            JournalPhase.PERSPECTIVE,
        ]

    def test_word_ceilings_grow_with_relationship(self):
        cals = all_calibrations()
        ceilings = [c.target_word_ceiling for c in cals]
        # Strictly non-decreasing — Rex gets a little more room over time.
        assert ceilings == sorted(ceilings)

    def test_each_calibration_has_a_directive_and_example(self):
        for c in all_calibrations():
            assert c.directive.strip()
            assert c.example.strip()


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    def test_briefing_prompt_includes_soul_sentence(self):
        ctx = PromptContext(mode=Mode.BRIEFING, relationship_day=47)
        prompt = build_system_prompt(ctx)
        assert SOUL_SENTENCE in prompt

    def test_briefing_prompt_includes_inviolable_three_max(self):
        ctx = PromptContext(mode=Mode.BRIEFING, relationship_day=47)
        prompt = build_system_prompt(ctx)
        assert "Three things maximum" in prompt
        assert "— Rex" in prompt

    def test_journal_prompt_embeds_correct_phase(self):
        ctx = PromptContext(mode=Mode.JOURNAL, relationship_day=47)
        prompt = build_system_prompt(ctx)
        assert "BLENDED" in prompt
        assert "Day 47" in prompt or "RELATIONSHIP DAY: 47" in prompt

    def test_journal_prompt_phase_changes_with_day(self):
        early = build_system_prompt(PromptContext(mode=Mode.JOURNAL, relationship_day=3))
        late = build_system_prompt(PromptContext(mode=Mode.JOURNAL, relationship_day=200))
        assert "OBSERVING" in early
        assert "PERSPECTIVE" in late

    def test_context_block_includes_rank_and_probation(self):
        ctx = PromptContext(
            mode=Mode.REASONING,
            relationship_day=47,
            category="Outreach",
            rank="Drafter",
            on_probation=True,
        )
        prompt = build_system_prompt(ctx)
        assert "Outreach" in prompt
        assert "Drafter" in prompt
        assert "ON PROBATION" in prompt

    def test_memory_cites_appear_when_provided(self):
        ctx = PromptContext(
            mode=Mode.ACTION_DRAFT,
            relationship_day=47,
            memory_cites=(
                "Patel — responds to directness, not warmth.",
                "Reply rates drop 60% on Tuesdays.",
            ),
        )
        prompt = build_system_prompt(ctx)
        assert "Patel" in prompt
        assert "Tuesdays" in prompt

    def test_every_non_journal_mode_has_a_directive(self):
        for mode in Mode:
            ctx = PromptContext(mode=mode, relationship_day=10)
            prompt = build_system_prompt(ctx)  # must not raise
            assert "MODE:" in prompt

    def test_voice_rules_block_is_present(self):
        ctx = PromptContext(mode=Mode.BRIEFING)
        prompt = build_system_prompt(ctx)
        assert "VOICE RULES" in prompt
        assert "No emoji" in prompt


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class TestTemplates:
    def test_five_ranks_in_canonical_order(self):
        assert ALL_RANKS == (
            "Observer", "Drafter", "Sender", "Operator", "Chief of Staff",
        )

    def test_rank_index(self):
        assert rank_index("Observer") == 0
        assert rank_index("Chief of Staff") == 4

    def test_can_autonomously_execute(self):
        assert not can_autonomously_execute("Observer")
        assert not can_autonomously_execute("Drafter")
        assert can_autonomously_execute("Sender")
        assert can_autonomously_execute("Operator")
        assert can_autonomously_execute("Chief of Staff")

    def test_notebook_buckets(self):
        assert NOTEBOOK_BUCKETS == ("People", "Patterns", "Lanes")

    def test_five_interview_questions(self):
        assert len(INTERVIEW_QUESTIONS) == 5
        assert INTERVIEW_QUESTIONS[0].startswith("Quick.")
        assert all(q.endswith("?") for q in INTERVIEW_QUESTIONS)

    def test_journal_day_anchor(self):
        assert journal_day_anchor(1) == "Day 1."
        assert journal_day_anchor(47) == "Day 47."
        with pytest.raises(ValueError):
            journal_day_anchor(0)

    def test_render_citation_canonical_format(self):
        cite = Citation(
            observation="Responds to directness, not warmth.",
            confidence_pct=94,
        )
        rendered = render_citation(cite)
        assert "↳" in rendered
        assert 'Memory: "Responds to directness, not warmth."' in rendered
        assert "Confidence: 94%" in rendered

    def test_render_citations_caps_at_two(self):
        cites = [
            Citation("a", 80), Citation("b", 80), Citation("c", 80),
        ]
        with pytest.raises(ValueError):
            render_citations(cites)

    def test_promotion_and_demotion_headlines(self):
        assert promotion_headline("Outreach", "Sender") == "Earned Sender on outreach."
        assert demotion_headline("Invoices", "Drafter") == "Demoted to Drafter on invoices."
        assert "probation" in probation_headline("Outreach").lower()

    def test_assert_inviolable_briefing_shape_accepts_valid(self):
        letter = (
            "Tuesday. 6:47am.\n\n"
            "Quiet night, mostly. One thing needs you.\n\n"
            f"Acme deal went cold. {ACTION_TOKEN_REVIEW_SEND}\n\n"
            "Full ledger below if you want it.\n\n"
            f"{BRIEFING_SIGN_OFF}"
        )
        assert_inviolable_briefing_shape(letter)

    def test_assert_inviolable_briefing_shape_rejects_missing_signoff(self):
        with pytest.raises(AssertionError):
            assert_inviolable_briefing_shape("Tuesday. Nothing happened.")

    def test_assert_inviolable_briefing_shape_rejects_too_many_actions(self):
        letter = (
            "Tuesday.\n\n"
            f"Thing 1. {ACTION_TOKEN_REVIEW_SEND}\n"
            f"Thing 2. {ACTION_TOKEN_REVIEW_SEND}\n"
            f"Thing 3. {ACTION_TOKEN_REVIEW_SEND}\n"
            f"Thing 4. {ACTION_TOKEN_REVIEW_SEND}\n\n"
            f"{BRIEFING_SIGN_OFF}"
        )
        with pytest.raises(AssertionError):
            assert_inviolable_briefing_shape(letter)


# ---------------------------------------------------------------------------
# Cross-module integrity: built prompts must themselves pass the voice
# validator (no apologies, no hedging, no emoji buried in prompt text).
# ---------------------------------------------------------------------------

class TestPromptHygiene:
    @pytest.mark.parametrize("mode", list(Mode))
    def test_every_prompt_is_emoji_free(self, mode):
        ctx = PromptContext(mode=mode, relationship_day=47)
        prompt = build_system_prompt(ctx)
        # Validator's emoji check, isolated.
        from rex.persona.voice_rules import _EMOJI_PATTERN  # type: ignore
        assert not _EMOJI_PATTERN.search(prompt), (
            f"Prompt for mode {mode} contains an emoji."
        )
