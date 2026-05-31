"""
Tests for rex.briefing — Selector + Opener + Letter + HomeScreen.

Coverage:
    1. Opener: phase boundaries (NEW / EARNING / EARNED), weekday + time format
    2. Selector: limit cap-3, confidence × freshness × tier ordering, ties
    3. Letter: quiet-night, single-action, multi-action, voice + shape gates,
       cap-3 enforcement, citation surfacing
    4. HomeScreen: end-to-end snapshot from a populated Orchestrator
       (uses Phase 5 fakes; no I/O)
    5. JSON-roundtrip stability — important for the future Phase 9 frontend

Run from backend/:
    python -m pytest rex/tests/briefing_test.py -v
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from rex.actions import Action, ActionKind
from rex.briefing import (
    BriefingPhase,
    HomeScreen,
    Letter,
    LetterAction,
    LetterShapeError,
    PendingPromotion,
    StandingSummary,
    briefing_phase_for_day,
    build_home_screen,
    compose_letter,
    opener_for,
    pick_top_actions,
)
from rex.briefing.selector import score_action
from rex.loop import Orchestrator
from rex.memory import Bucket, Notebook
from rex.persona.templates import (
    ACTION_TOKEN_REVIEW_SEND,
    BRIEFING_SIGN_OFF,
)
from rex.ranks.engine import RankEngine
from rex.ranks.events import EventType, Rank, TrustEvent
from rex.tests.fakes import FakeExecutor, FakeProducer, make_action


# ===========================================================================
# Helpers
# ===========================================================================

def _utc(year=2026, month=6, day=2, hour=6, minute=47) -> datetime:
    """A fixed Tuesday 06:47 UTC for deterministic tests."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _action_with_proposed_at(when: datetime, **kwargs) -> Action:
    a = make_action(**kwargs)
    return replace(a, proposed_at=when)


# ===========================================================================
# Opener
# ===========================================================================

class TestOpener:
    def test_phase_boundaries(self):
        assert briefing_phase_for_day(1) is BriefingPhase.NEW
        assert briefing_phase_for_day(14) is BriefingPhase.NEW
        assert briefing_phase_for_day(15) is BriefingPhase.EARNING
        assert briefing_phase_for_day(60) is BriefingPhase.EARNING
        assert briefing_phase_for_day(61) is BriefingPhase.EARNED
        assert briefing_phase_for_day(365) is BriefingPhase.EARNED

    def test_invalid_day_raises(self):
        with pytest.raises(ValueError):
            briefing_phase_for_day(0)

    def test_new_phase_format(self):
        # Tuesday 6:47am
        opener = opener_for(now=_utc(), relationship_day=3)
        assert opener == "Tuesday. 6:47am."

    def test_earning_phase_format(self):
        opener = opener_for(now=_utc(hour=14, minute=0), relationship_day=30)
        assert opener == "Tuesday afternoon."

    def test_earned_phase_drops_weekday(self):
        opener = opener_for(now=_utc(hour=8, minute=0), relationship_day=120)
        assert opener == "Morning."

    def test_evening_phrasing(self):
        opener = opener_for(now=_utc(hour=19, minute=0), relationship_day=120)
        assert opener == "Evening."


# ===========================================================================
# Selector
# ===========================================================================

class TestSelector:
    def test_empty_returns_empty(self):
        assert pick_top_actions([], limit=3) == ()

    def test_zero_limit_returns_empty(self):
        a = make_action()
        assert pick_top_actions([a], limit=0) == ()

    def test_limit_caps_three(self):
        now = _utc()
        actions = [
            _action_with_proposed_at(now - timedelta(minutes=i),
                                     summary=f"action {i}")
            for i in range(5)
        ]
        top = pick_top_actions(actions, limit=3, now=now)
        assert len(top) == 3

    def test_higher_confidence_ranks_first(self):
        now = _utc()
        low = _action_with_proposed_at(now, summary="low", confidence=0.3)
        high = _action_with_proposed_at(now, summary="high", confidence=0.95)
        top = pick_top_actions([low, high], limit=2, now=now)
        assert top[0].id == high.id

    def test_freshness_breaks_confidence_tie(self):
        now = _utc()
        old = _action_with_proposed_at(
            now - timedelta(hours=20), summary="old", confidence=0.8,
        )
        fresh = _action_with_proposed_at(
            now, summary="fresh", confidence=0.8,
        )
        top = pick_top_actions([old, fresh], limit=2, now=now)
        assert top[0].id == fresh.id

    def test_tier1_category_gets_bias(self):
        now = _utc()
        # Both at 0.8 conf, both fresh — Tier-1 'outreach' should beat
        # Tier-3 'broadcast'.
        outreach = _action_with_proposed_at(
            now, summary="outreach", confidence=0.8, category="outreach",
        )
        broadcast = _action_with_proposed_at(
            now, summary="broadcast", confidence=0.8, category="broadcast",
        )
        top = pick_top_actions([outreach, broadcast], limit=2, now=now)
        assert top[0].id == outreach.id

    def test_score_breakdown_is_stable(self):
        now = _utc()
        a = _action_with_proposed_at(now, confidence=0.9, category="outreach")
        s = score_action(a, now=now)
        assert s.confidence_term == round(0.20 * 0.9, 4)
        assert s.freshness_term == 0.10
        assert s.tier_term == 0.10
        assert s.urgency_term == round(0.35 * 0.4, 4)
        assert s.importance_term == round(0.35 * 0.8, 4)


# ===========================================================================
# Letter — quiet night
# ===========================================================================

class TestQuietNightLetter:
    def test_no_actions_yields_quiet_night(self):
        letter = compose_letter(
            opener="Tuesday. 6:47am.",
            staged_actions=(),
            now=_utc(hour=23),
        )
        assert letter.quiet_night is True
        assert "Quiet night" in letter.body
        assert letter.body.rstrip().endswith(BRIEFING_SIGN_OFF)
        assert letter.actions == ()

    def test_quiet_night_passes_voice_check(self):
        # Should not raise.
        compose_letter(opener="Tuesday. 6:47am.", staged_actions=(), now=_utc(hour=23))


# ===========================================================================
# Letter — with actions
# ===========================================================================

class TestLetterWithActions:
    def test_single_action_uses_singular_intro(self):
        a = make_action(confidence=0.9)
        letter = compose_letter(
            opener="Tuesday. 6:47am.",
            staged_actions=(a,),
            now=_utc(hour=23),
        )
        assert "one thing needs you" in letter.body
        assert ACTION_TOKEN_REVIEW_SEND in letter.body
        assert len(letter.actions) == 1
        assert letter.actions[0].confidence_pct == 90

    def test_three_actions_uses_three(self):
        actions = tuple(make_action(summary=f"thing {i}") for i in range(3))
        letter = compose_letter(opener="Tuesday. 6:47am.", staged_actions=actions, now=_utc(hour=23))
        assert "three things need you" in letter.body
        assert letter.body.count(ACTION_TOKEN_REVIEW_SEND) == 3

    def test_letter_ends_with_sign_off(self):
        a = make_action()
        letter = compose_letter(opener="Tuesday. 6:47am.", staged_actions=(a,), now=_utc(hour=23))
        assert letter.body.rstrip().endswith(BRIEFING_SIGN_OFF)

    def test_action_with_reasoning_is_rendered(self):
        a = make_action(reasoning="9 days silent, prior cadence was 4 days.")
        letter = compose_letter(opener="x.", staged_actions=(a,), now=_utc(hour=23))
        assert "9 days silent" in letter.body

    def test_long_imported_reasoning_passes_voice(self):
        long_reasoning = " ".join(["snippet"] * 81)
        a = make_action(reasoning=long_reasoning)
        letter = compose_letter(opener="Tuesday. 6:47am.", staged_actions=(a,), now=_utc(hour=23))
        assert "snippet" in letter.body

    def test_voice_violation_raises(self):
        # Action with sycophantic summary should be caught by voice gate.
        a = make_action(summary="Absolutely! I'd love to help!", confidence=0.9)
        with pytest.raises(LetterShapeError):
            compose_letter(opener="x.", staged_actions=(a,), now=_utc(hour=23))


# ===========================================================================
# Letter — citations
# ===========================================================================

class TestLetterCitations:
    def test_citation_surfaces_when_notebook_entry_referenced(self):
        nb = Notebook()
        entry = nb.add(
            bucket=Bucket.PEOPLE,
            subject="Patel",
            text="Patel — responds to directness, not warmth.",
        )
        a = make_action()
        a = replace(a, memory_citation_ids=(entry.id,))
        letter = compose_letter(
            opener="x.", staged_actions=(a,), notebook=nb, now=_utc(hour=23),
        )
        assert letter.actions[0].has_citation is True
        assert "directness" in letter.body

    def test_no_citation_when_no_notebook_provided(self):
        a = make_action()
        a = replace(a, memory_citation_ids=("any-id",))
        letter = compose_letter(opener="x.", staged_actions=(a,), notebook=None, now=_utc(hour=23))
        assert letter.actions[0].has_citation is False


# ===========================================================================
# HomeScreen — end-to-end snapshot
# ===========================================================================

class TestHomeScreen:
    def _orch_with_two_staged(self) -> Orchestrator:
        orch = Orchestrator()
        # Bump Rex to Drafter on outreach so actions stage instead of drop.
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
        ))
        orch.engine = RankEngine.from_events(orch.event_store)
        orch.register_producer(FakeProducer(
            actor_name_value="Zilo",
            categories_value=("outreach",),
            actions=[
                _action_with_proposed_at(_utc(), rank=Rank.DRAFTER, confidence=0.9, summary="A."),
                _action_with_proposed_at(_utc(), rank=Rank.DRAFTER, confidence=0.7, summary="B."),
            ],
        ))
        orch.run_overnight()
        return orch

    def test_basic_snapshot(self):
        orch = self._orch_with_two_staged()
        home = build_home_screen(orch, now=_utc(), relationship_day=5)

        assert isinstance(home, HomeScreen)
        assert home.relationship_day == 5
        assert home.counts.staged == 2
        assert home.counts.sent_today == 0
        assert home.letter.quiet_night is False
        assert len(home.letter.actions) == 2
        # Higher-confidence action appears first.
        assert home.letter.actions[0].confidence_pct == 90

    def test_quiet_morning_when_nothing_staged(self):
        orch = Orchestrator()
        home = build_home_screen(orch, now=_utc(), relationship_day=1)
        assert home.letter.quiet_night is True
        assert home.counts.staged == 0

    def test_pending_promotion_surfaces(self):
        orch = Orchestrator()
        # Rex recommends Scout for Drafter on leads.
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            reason="3 leads found, 3 kept.", confidence=0.9,
        )
        orch.event_store.append(rec)
        orch.engine = RankEngine.from_events(orch.event_store)

        home = build_home_screen(orch, now=_utc(), relationship_day=5)
        assert len(home.pending_promotions) == 1
        p = home.pending_promotions[0]
        assert p.subagent_name == "Scout"
        assert p.category == "leads"
        assert p.to_rank == "Drafter"
        assert p.confidence_pct == 90

    def test_tier1_standings_listed(self):
        orch = Orchestrator()
        home = build_home_screen(orch, now=_utc(), relationship_day=1)
        # All Tier-1 categories represented.
        cats = {s.category for s in home.rex_standings}
        for required in ("outreach", "replies", "leads",
                         "follow_ups", "meeting_follow_through"):
            assert required in cats
        # Rex starts as Observer everywhere.
        assert all(s.rank == "Observer" for s in home.rex_standings)

    def test_invalid_relationship_day_raises(self):
        with pytest.raises(ValueError):
            build_home_screen(Orchestrator(), now=_utc(), relationship_day=0)

    def test_snapshot_is_pure(self):
        """Calling build_home_screen twice yields equivalent snapshots."""
        orch = self._orch_with_two_staged()
        moment = _utc()
        h1 = build_home_screen(orch, now=moment, relationship_day=5)
        h2 = build_home_screen(orch, now=moment, relationship_day=5)
        assert h1.letter.body == h2.letter.body
        assert h1.counts == h2.counts


# ===========================================================================
# Determinism — same orchestrator state → same letter
# ===========================================================================

class TestDeterminism:
    def test_letter_body_stable_across_renders(self):
        a1 = _action_with_proposed_at(_utc(), summary="A", confidence=0.9)
        a2 = _action_with_proposed_at(_utc(), summary="B", confidence=0.7)
        letter1 = compose_letter(
            opener="Tuesday. 6:47am.", staged_actions=(a1, a2), now=_utc(hour=23),
        )
        letter2 = compose_letter(
            opener="Tuesday. 6:47am.", staged_actions=(a1, a2), now=_utc(hour=23),
        )
        assert letter1.body == letter2.body


# ===========================================================================
# Live Feed — Importance, Urgency, Anti-Starvation & Filtering
# ===========================================================================

class TestLiveFeedImportanceUrgency:
    def test_urgency_calculation(self):
        from rex.briefing.selector import calculate_action_urgency
        now = _utc()

        # Inbound reply: highly urgent
        reply = make_action(kind=ActionKind.REPLY, category="replies")
        assert calculate_action_urgency(reply, reply.proposed_at) == 0.9

        # Scout lead: lower urgency
        lead = make_action(kind=ActionKind.SOCIAL_POST, category="leads")
        assert calculate_action_urgency(lead, lead.proposed_at) == 0.4

        # Urgency override
        high_urg = make_action()
        high_urg = replace(high_urg, payload={"urgency": "high"})
        assert calculate_action_urgency(high_urg, high_urg.proposed_at) == 1.0

        # Keyword triggers
        urgent_kw = make_action(summary="Urgent invoice issue", category="outreach")
        assert calculate_action_urgency(urgent_kw, urgent_kw.proposed_at) == 0.4 + 0.15 # 0.55

    def test_importance_calculation(self):
        from rex.briefing.selector import calculate_action_importance

        # VIP Modifier
        vip_action = make_action(category="outreach")
        vip_action = replace(vip_action, payload={"tags": ["VIP"]})
        assert calculate_action_importance(vip_action) == 0.8 + 0.20 # 1.0

        # High value transaction
        high_val = make_action(category="invoices")
        high_val = replace(high_val, payload={"amount": 1500.0})
        assert calculate_action_importance(high_val) == 0.7 + 0.20 # 0.90

    def test_anti_starvation_decay(self):
        from rex.briefing.selector import calculate_action_urgency
        now = _utc()

        # Proposed 3 days ago (should lose 0.3 urgency)
        old_action = _action_with_proposed_at(now - timedelta(days=3), kind=ActionKind.REPLY, category="replies")
        assert round(calculate_action_urgency(old_action, now), 2) == round(0.9 - 0.3, 2)

    def test_time_of_day_phrasing(self):
        a = make_action()

        # Morning (hour 8)
        letter_morning = compose_letter(opener="x", staged_actions=(a,), now=_utc(hour=8))
        assert "Quiet morning overall" in letter_morning.body

        # Afternoon (hour 14)
        letter_afternoon = compose_letter(opener="x", staged_actions=(a,), now=_utc(hour=14))
        assert "Quiet afternoon overall" in letter_afternoon.body

        # Evening (hour 19)
        letter_evening = compose_letter(opener="x", staged_actions=(a,), now=_utc(hour=19))
        assert "Quiet evening overall" in letter_evening.body

        # Night (hour 23)
        letter_night = compose_letter(opener="x", staged_actions=(a,), now=_utc(hour=23))
        assert "Quiet night overall" in letter_night.body

    def test_promo_filtering_with_whitelist(self):
        from rex.integrations.email_bridge import _is_promotional

        # Newsletters should be blocked by default
        newsletter = {
            "from_addr": "newsletter@spam.com",
            "subject": "Weekly gains are 200%",
            "body_clean": "This is a weekly update containing list-manage links. Click here to unsubscribe.",
        }
        is_promo, reason = _is_promotional(newsletter)
        assert is_promo is True

        # But if whitelisted, it passes!
        whitelist = {"newsletter@spam.com"}
        is_promo_wl, reason_wl = _is_promotional(newsletter, whitelist)
        assert is_promo_wl is False

        # Normal conversation email passes
        convo = {
            "from_addr": "customer@company.com",
            "subject": "Question about Q3 billing",
            "body_clean": "Hi, please check when my billing cycle restarts. Thanks!",
        }
        is_promo_convo, reason_convo = _is_promotional(convo)
        assert is_promo_convo is False

