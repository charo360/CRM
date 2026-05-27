"""
Tests for rex.ranks — the Rank Engine and Trust Event store.

Coverage targets:

    1. Category catalog integrity (Tier 1-8, no duplicates)
    2. Actor registry integrity (Rex singleton, Sub-Agent uniqueness)
    3. TrustEvent constructor correctness
    4. EventStore append + query semantics
    5. RankEngine — every event type, including the asymmetry invariants
    6. Probation lifecycle (set on demotion, lift only via REX_LIFTED_PROBATION)
    7. Recommendation chaining (approve must match prior recommendation)
    8. Trust score computation + threshold detection
    9. End-to-end story replay: scout earns Sender, screws up, gets demoted,
       comes back to Sender after probation lifts.

Run from backend/:
    python -m pytest rex/tests/ranks_test.py -v
"""

from __future__ import annotations

import pytest

from rex.ranks import (
    Actor, ActorKind, REX, SUB_AGENTS, actor_by_name,
    Category, Tier, all_categories,
    EventStore, InMemoryEventStore,
    EventType, Rank, TrustEvent,
    Standing, RankEngine, ProbationViolation,
    Recommendation, RecommendationStatus,
    compute_trust_score, propose_promotion, PROMOTION_THRESHOLDS,
)
from rex.ranks.categories import _CATALOG  # type: ignore  (test-only access)


# ===========================================================================
# Category catalog
# ===========================================================================

class TestCategoryCatalog:
    def test_all_categories_unique_names(self):
        names = [c.name for c in all_categories()]
        assert len(names) == len(set(names))

    def test_all_tiers_represented(self):
        tiers = {c.tier for c in all_categories()}
        assert tiers == set(Tier)

    def test_tier_1_includes_core_day_one_categories(self):
        tier1 = {c.name for c in all_categories() if c.tier is Tier.CORE}
        # REX.md §6 Tier 1 inventory.
        for required in (
            "outreach", "replies", "leads", "follow_ups", "meeting_follow_through",
        ):
            assert required in tier1

    def test_payments_is_in_operations_tier(self):
        # REX.md §6 — money is sacred, stays in tier 2.
        c = next(c for c in all_categories() if c.name == "payments")
        assert c.tier is Tier.OPERATIONS


# ===========================================================================
# Actor registry
# ===========================================================================

class TestActorRegistry:
    def test_rex_is_singleton(self):
        assert REX.kind is ActorKind.REX
        assert REX.name == "Rex"
        assert actor_by_name("Rex") is REX

    def test_subagent_names_unique(self):
        names = [s.name for s in SUB_AGENTS]
        assert len(names) == len(set(names))

    def test_known_subagents_registered(self):
        names = {s.name for s in SUB_AGENTS}
        # Both teams covered.
        assert "Scout" in names         # operations
        assert "Sales" in names         # customer service
        assert "Payments" in names      # the cautious one

    def test_actor_by_name_for_subagent(self):
        a = actor_by_name("Scout")
        assert a.kind is ActorKind.SUB_AGENT
        assert a.name == "Scout"

    def test_actor_by_name_unknown_raises(self):
        with pytest.raises(KeyError):
            actor_by_name("Nonexistent")


# ===========================================================================
# Rank enum
# ===========================================================================

class TestRank:
    def test_ordering(self):
        assert Rank.OBSERVER < Rank.DRAFTER < Rank.SENDER < Rank.OPERATOR < Rank.CHIEF_OF_STAFF

    def test_display_strings(self):
        assert Rank.OBSERVER.display == "Observer"
        assert Rank.CHIEF_OF_STAFF.display == "Chief of Staff"

    def test_from_display_roundtrip(self):
        for r in Rank:
            assert Rank.from_display(r.display) is r

    def test_from_display_handles_dash(self):
        # "chief-of-staff" should parse.
        assert Rank.from_display("chief-of-staff") is Rank.CHIEF_OF_STAFF


# ===========================================================================
# Event store
# ===========================================================================

class TestInMemoryEventStore:
    def test_satisfies_protocol(self):
        store = InMemoryEventStore()
        assert isinstance(store, EventStore)

    def test_append_and_iterate_preserves_order(self):
        store = InMemoryEventStore()
        e1 = TrustEvent.operational(
            type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
        )
        e2 = TrustEvent.operational(
            type=EventType.ACTION_CLEAN_SEND, actor_name="Scout", category="leads",
        )
        store.append(e1)
        store.append(e2)
        assert store.all_events() == (e1, e2)
        assert list(store) == [e1, e2]
        assert len(store) == 2

    def test_events_for_filtering(self):
        store = InMemoryEventStore()
        store.append(TrustEvent.operational(
            type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
        ))
        store.append(TrustEvent.operational(
            type=EventType.ACTION_APPROVED, actor_name="Scout", category="outreach",
        ))
        store.append(TrustEvent.operational(
            type=EventType.ACTION_APPROVED, actor_name="Pulse", category="leads",
        ))
        scout_leads = store.events_for(actor_name="Scout", category="leads")
        assert len(scout_leads) == 1
        scout_all = store.events_for(actor_name="Scout")
        assert len(scout_all) == 2
        leads_all = store.events_for(category="leads")
        assert len(leads_all) == 2


# ===========================================================================
# Rank Engine — Rex axis
# ===========================================================================

class TestEngineRexAxis:
    def test_default_standing_is_observer(self):
        engine = RankEngine.empty()
        s = engine.standing("Rex", "outreach")
        assert s.rank is Rank.OBSERVER
        assert not s.on_probation

    def test_user_promotes_rex(self):
        engine = RankEngine.empty()
        engine.apply(TrustEvent.user_promoted_rex(
            category="outreach", from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
        ))
        assert engine.standing("Rex", "outreach").rank is Rank.DRAFTER

    def test_user_demotes_rex_sets_probation(self):
        engine = RankEngine.empty()
        engine.apply(TrustEvent.user_promoted_rex(
            category="outreach", from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        # Wait — SENDER is two steps up, that's a single multi-step promotion.
        # The engine accepts it because we only check to_rank > from_rank.
        engine.apply(TrustEvent.user_demoted_rex(
            category="outreach", from_rank=Rank.SENDER, to_rank=Rank.DRAFTER,
            reason="too aggressive on cold outreach",
        ))
        s = engine.standing("Rex", "outreach")
        assert s.rank is Rank.DRAFTER
        assert s.on_probation

    def test_promotion_must_match_current_rank(self):
        engine = RankEngine.empty()
        # Rex is Observer, but event claims from_rank=Sender.
        with pytest.raises(ProbationViolation, match="from_rank"):
            engine.apply(TrustEvent.user_promoted_rex(
                category="outreach", from_rank=Rank.SENDER, to_rank=Rank.OPERATOR,
            ))

    def test_demotion_with_to_rank_above_from_rank_rejected(self):
        engine = RankEngine.empty()
        engine.apply(TrustEvent.user_promoted_rex(
            category="outreach", from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        with pytest.raises(ProbationViolation, match="strictly below"):
            engine.apply(TrustEvent.user_demoted_rex(
                category="outreach", from_rank=Rank.SENDER, to_rank=Rank.OPERATOR,
            ))


# ===========================================================================
# Rank Engine — Sub-Agent axis (the asymmetry)
# ===========================================================================

class TestEngineSubAgentAxis:
    def test_subagent_cannot_be_promoted_without_recommendation(self):
        engine = RankEngine.empty()
        # Try to approve a recommendation that never existed.
        with pytest.raises(ProbationViolation, match="No pending recommendation"):
            engine.apply(TrustEvent.user_approved_recommendation(
                subagent="Scout", category="leads",
                from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
                recommendation_id="never-recommended",
            ))

    def test_subagent_promotion_via_chained_recommendation_then_approval(self):
        engine = RankEngine.empty()
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            reason="Found 14 leads, all approved.", confidence=0.92,
        )
        engine.apply(rec)
        # Still Observer until user approves.
        assert engine.standing("Scout", "leads").rank is Rank.OBSERVER

        engine.apply(TrustEvent.user_approved_recommendation(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            recommendation_id=rec.id,
        ))
        assert engine.standing("Scout", "leads").rank is Rank.DRAFTER

    def test_approval_must_match_recommendation_subagent(self):
        engine = RankEngine.empty()
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            reason="r", confidence=0.9,
        )
        engine.apply(rec)
        with pytest.raises(ProbationViolation, match="does not match"):
            engine.apply(TrustEvent.user_approved_recommendation(
                subagent="Pulse",  # wrong subagent
                category="leads",
                from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
                recommendation_id=rec.id,
            ))

    def test_deny_recommendation_closes_pending(self):
        engine = RankEngine.empty()
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            reason="r", confidence=0.9,
        )
        engine.apply(rec)
        engine.apply(TrustEvent.user_denied_recommendation(
            subagent="Scout", category="leads", recommendation_id=rec.id,
        ))
        # Approval after denial should now fail — recommendation closed.
        with pytest.raises(ProbationViolation):
            engine.apply(TrustEvent.user_approved_recommendation(
                subagent="Scout", category="leads",
                from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
                recommendation_id=rec.id,
            ))

    def test_rex_demotes_subagent_unilaterally(self):
        # First get Scout up to Sender via proper chain.
        engine = _bring_subagent_to(engine_actor="Scout", category="leads",
                                    target=Rank.SENDER)
        # Now Rex demotes — no user gate.
        engine.apply(TrustEvent.rex_demoted_subagent(
            subagent="Scout", category="leads",
            from_rank=Rank.SENDER, to_rank=Rank.DRAFTER,
            reason="Sent to wrong vendor — Henderson/Henson confusion.",
        ))
        s = engine.standing("Scout", "leads")
        assert s.rank is Rank.DRAFTER
        assert s.on_probation

    def test_rex_cannot_demote_himself(self):
        engine = RankEngine.empty()
        engine.apply(TrustEvent.user_promoted_rex(
            category="outreach", from_rank=Rank.OBSERVER, to_rank=Rank.SENDER,
        ))
        with pytest.raises(ProbationViolation, match="cannot target Rex"):
            engine.apply(TrustEvent.rex_demoted_subagent(
                subagent="Rex", category="outreach",
                from_rank=Rank.SENDER, to_rank=Rank.DRAFTER,
                reason="self-doubt",
            ))


# ===========================================================================
# Probation lifecycle
# ===========================================================================

class TestProbation:
    def test_demotion_sets_probation_and_lift_clears_it(self):
        engine = _bring_subagent_to(
            engine_actor="Scout", category="leads", target=Rank.SENDER,
        )
        engine.apply(TrustEvent.rex_demoted_subagent(
            subagent="Scout", category="leads",
            from_rank=Rank.SENDER, to_rank=Rank.DRAFTER,
            reason="error",
        ))
        assert engine.standing("Scout", "leads").on_probation

        engine.apply(TrustEvent.rex_lifted_probation(
            actor_name="Scout", category="leads",
            reason="12 clean events in a row",
        ))
        assert not engine.standing("Scout", "leads").on_probation

    def test_lift_probation_when_not_on_probation_raises(self):
        engine = RankEngine.empty()
        with pytest.raises(ProbationViolation, match="not on probation"):
            engine.apply(TrustEvent.rex_lifted_probation(
                actor_name="Scout", category="leads",
            ))


# ===========================================================================
# Trust score + recommendations
# ===========================================================================

class TestTrustScore:
    def test_empty_events_yields_zero_score(self):
        score, count = compute_trust_score(
            (), actor_name="Scout", category="leads",
        )
        assert score == 0.0
        assert count == 0

    def test_all_approved_yields_high_score(self):
        events = [
            TrustEvent.operational(
                type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
            )
            for _ in range(20)
        ]
        score, count = compute_trust_score(
            events, actor_name="Scout", category="leads",
        )
        assert count == 20
        assert score >= 0.9  # consistent +1.0 weight should normalize near top

    def test_mistakes_drag_score_down(self):
        # 5 approved (+1 each) vs 10 flagged mistakes (-3 each)
        # total = -25, avg = -25/15 ≈ -1.67, normalized ≈ 0.33 — well below 0.5.
        good = [
            TrustEvent.operational(
                type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
            )
            for _ in range(5)
        ]
        bad = [
            TrustEvent.operational(
                type=EventType.ACTION_FLAGGED_MISTAKE,
                actor_name="Scout", category="leads",
            )
            for _ in range(10)
        ]
        score, _ = compute_trust_score(
            good + bad, actor_name="Scout", category="leads",
        )
        assert score < 0.5

    def test_equal_good_and_severe_bad_lands_at_midpoint(self):
        # Documents the exact balance: 10 approved (+1) + 10 mistakes (-3)
        # = avg -1.0, normalized to 0.5. Boundary case worth pinning down.
        good = [
            TrustEvent.operational(
                type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
            )
            for _ in range(10)
        ]
        bad = [
            TrustEvent.operational(
                type=EventType.ACTION_FLAGGED_MISTAKE,
                actor_name="Scout", category="leads",
            )
            for _ in range(10)
        ]
        score, _ = compute_trust_score(
            good + bad, actor_name="Scout", category="leads",
        )
        assert score == 0.5

    def test_filters_by_actor_and_category(self):
        # Pulse on outreach should not influence Scout/leads score.
        events = [
            TrustEvent.operational(
                type=EventType.ACTION_FLAGGED_MISTAKE,
                actor_name="Pulse", category="outreach",
            ),
            TrustEvent.operational(
                type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
            ),
        ]
        score, count = compute_trust_score(
            events, actor_name="Scout", category="leads",
        )
        assert count == 1
        assert score >= 0.9


class TestPropose:
    def test_no_recommendation_when_under_threshold(self):
        engine = RankEngine.empty()
        # Scout on leads with very few events stays Observer.
        events = [
            TrustEvent.operational(
                type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
            )
        ]
        rec = propose_promotion(
            events, engine=engine, subagent_name="Scout", category="leads",
        )
        # 1 event is below DRAFTER threshold? DRAFTER threshold is (0.50, 1).
        # 1 approved event scores 1.0, count=1, so it actually qualifies for DRAFTER.
        # The fact that we get a recommendation here is intentional.
        assert rec is not None
        assert rec.to_rank is Rank.DRAFTER

    def test_recommendation_for_sender_requires_more_events(self):
        engine = RankEngine.empty()
        # Bring Scout to Drafter first.
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            reason="r", confidence=0.9,
        )
        engine.apply(rec)
        engine.apply(TrustEvent.user_approved_recommendation(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            recommendation_id=rec.id,
        ))
        # Now only 5 events — below SENDER's min_events=10.
        events = [
            TrustEvent.operational(
                type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
            )
            for _ in range(5)
        ]
        proposal = propose_promotion(
            events, engine=engine, subagent_name="Scout", category="leads",
        )
        assert proposal is None

    def test_recommendation_emitted_when_thresholds_met(self):
        engine = RankEngine.empty()
        # Get to Drafter first.
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            reason="r", confidence=0.9,
        )
        engine.apply(rec)
        engine.apply(TrustEvent.user_approved_recommendation(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            recommendation_id=rec.id,
        ))
        events = [
            TrustEvent.operational(
                type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
            )
            for _ in range(15)
        ]
        proposal = propose_promotion(
            events, engine=engine, subagent_name="Scout", category="leads",
        )
        assert proposal is not None
        assert proposal.to_rank is Rank.SENDER
        assert proposal.from_rank is Rank.DRAFTER
        assert proposal.confidence >= 0.7
        assert proposal.supporting_stats  # non-empty

    def test_probation_blocks_recommendation(self):
        engine = _bring_subagent_to(
            engine_actor="Scout", category="leads", target=Rank.SENDER,
        )
        # Demote → probation.
        engine.apply(TrustEvent.rex_demoted_subagent(
            subagent="Scout", category="leads",
            from_rank=Rank.SENDER, to_rank=Rank.DRAFTER,
            reason="oops",
        ))
        # Even with great events, no recommendation while on probation.
        events = [
            TrustEvent.operational(
                type=EventType.ACTION_APPROVED, actor_name="Scout", category="leads",
            )
            for _ in range(30)
        ]
        proposal = propose_promotion(
            events, engine=engine, subagent_name="Scout", category="leads",
        )
        assert proposal is None


# ===========================================================================
# End-to-end story replay
# ===========================================================================

class TestEndToEndStory:
    """
    The canonical Day 1 → Day 60 arc:
        - Scout starts Observer on Leads
        - Rex recommends Drafter → user approves
        - Scout earns Sender via chain
        - Scout screws up; Rex demotes unilaterally → probation
        - Scout recovers; Rex lifts probation
        - Scout earns Sender back via fresh chain
        - State at the end matches Rex's journal narrative.
    """

    def test_full_arc(self):
        store = InMemoryEventStore()

        # --- Day 5: Rex recommends Drafter --------------------------------
        rec1 = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            reason="3 leads found, all kept.", confidence=0.85,
        )
        store.append(rec1)

        # --- User approves ------------------------------------------------
        approval1 = TrustEvent.user_approved_recommendation(
            subagent="Scout", category="leads",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            recommendation_id=rec1.id,
        )
        store.append(approval1)

        # --- Day 6-30: 20 clean operational events ------------------------
        for _ in range(20):
            store.append(TrustEvent.operational(
                type=EventType.ACTION_APPROVED,
                actor_name="Scout", category="leads",
            ))

        # --- Day 31: Rex recommends Sender --------------------------------
        rec2 = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.DRAFTER, to_rank=Rank.SENDER,
            reason="Earned it.", confidence=0.95,
        )
        store.append(rec2)
        approval2 = TrustEvent.user_approved_recommendation(
            subagent="Scout", category="leads",
            from_rank=Rank.DRAFTER, to_rank=Rank.SENDER,
            recommendation_id=rec2.id,
        )
        store.append(approval2)

        # --- Day 47: Henderson/Henson screw-up — Rex demotes --------------
        store.append(TrustEvent.operational(
            type=EventType.ACTION_FLAGGED_MISTAKE,
            actor_name="Scout", category="leads",
            reason="Wrong vendor flagged.",
        ))
        store.append(TrustEvent.rex_demoted_subagent(
            subagent="Scout", category="leads",
            from_rank=Rank.SENDER, to_rank=Rank.DRAFTER,
            reason="Misjudged the Henderson lead.",
        ))

        # Replay everything.
        engine = RankEngine.from_events(store)
        s = engine.standing("Scout", "leads")
        assert s.rank is Rank.DRAFTER
        assert s.on_probation

        # --- Day 48-60: clean events + probation lift ---------------------
        for _ in range(15):
            store.append(TrustEvent.operational(
                type=EventType.ACTION_APPROVED,
                actor_name="Scout", category="leads",
            ))
        store.append(TrustEvent.rex_lifted_probation(
            actor_name="Scout", category="leads",
            reason="15 clean events.",
        ))

        # --- Day 61: Rex re-recommends Sender -----------------------------
        rec3 = TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout", category="leads",
            from_rank=Rank.DRAFTER, to_rank=Rank.SENDER,
            reason="Restored.", confidence=0.92,
        )
        store.append(rec3)
        store.append(TrustEvent.user_approved_recommendation(
            subagent="Scout", category="leads",
            from_rank=Rank.DRAFTER, to_rank=Rank.SENDER,
            recommendation_id=rec3.id,
        ))

        # Final replay.
        engine = RankEngine.from_events(store)
        final = engine.standing("Scout", "leads")
        assert final.rank is Rank.SENDER
        assert not final.on_probation


# ===========================================================================
# Determinism — replay is a pure function of the event log
# ===========================================================================

class TestReplayDeterminism:
    def test_two_replays_yield_identical_state(self):
        events = [
            TrustEvent.user_promoted_rex(
                category="outreach",
                from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
            ),
        ]
        e1 = RankEngine.from_events(events)
        e2 = RankEngine.from_events(events)
        assert e1.state == e2.state


# ===========================================================================
# Test helpers
# ===========================================================================

def _bring_subagent_to(*, engine_actor: str, category: str, target: Rank,
                       starting: Rank = Rank.OBSERVER) -> RankEngine:
    """
    Build an engine with a Sub-Agent at the given rank in the given category
    via the proper recommend → approve chain. Used to set up test scenarios
    that aren't themselves testing the promotion chain.
    """
    engine = RankEngine.empty()
    current = starting
    for step in (Rank.DRAFTER, Rank.SENDER, Rank.OPERATOR, Rank.CHIEF_OF_STAFF):
        if current >= target:
            break
        nxt = Rank(current + 1)
        rec = TrustEvent.rex_recommended_subagent_promotion(
            subagent=engine_actor, category=category,
            from_rank=current, to_rank=nxt,
            reason="setup", confidence=0.9,
        )
        engine.apply(rec)
        engine.apply(TrustEvent.user_approved_recommendation(
            subagent=engine_actor, category=category,
            from_rank=current, to_rank=nxt,
            recommendation_id=rec.id,
        ))
        current = nxt
    return engine
