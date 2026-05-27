"""
Tests for rex.principals — Phase 8: Two-Sided Loyalty Model.

Coverage:
    1. Principal / Role registry and category access permissions.
    2. Visibility matching (can_see): Founder, Team Member role-scoped, principal-scoped.
    3. Replay EventStore to recreate PrincipalRegistry.
    4. Scoped home screen snapshots for founder vs team member.
    5. Team Journal entries (founder only, team scoped).
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from rex.actions import Action, ActionKind, ActionState
from rex.briefing.home_screen import build_home_screen
from rex.journal.writer import JournalEntry, JournalEventKind, write_entry_for_trust_event
from rex.loop import Orchestrator
from rex.principals import (
    Principal,
    PrincipalRegistry,
    Role,
    Visibility,
    can_see,
    visibility_founder_only,
    visibility_role_scoped,
    visibility_team_shared,
)
from rex.ranks.events import Rank, TrustEvent
from rex.tests.fakes import make_action


def _utc(year=2026, month=6, day=2, hour=7, minute=2) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestPrincipalsVisibility:
    def test_founder_sees_everything(self):
        v1 = Visibility.founder_only()
        v2 = Visibility.role_scoped("sales")
        v3 = Visibility.principal("sarah-1")

        assert can_see(v1, principal_id="f-1", role="founder", is_founder=True) is True
        assert can_see(v2, principal_id="f-1", role="founder", is_founder=True) is True
        assert can_see(v3, principal_id="f-1", role="founder", is_founder=True) is True

    def test_team_member_cannot_see_founder_only(self):
        v = Visibility.founder_only()
        assert can_see(v, principal_id="sarah-1", role="support", is_founder=False) is False

    def test_team_member_sees_role_scoped(self):
        v = Visibility.role_scoped("sales")
        assert can_see(v, principal_id="sarah-1", role="sales", is_founder=False) is True
        assert can_see(v, principal_id="sarah-1", role="support", is_founder=False) is False

    def test_team_member_sees_principal_scoped(self):
        v = Visibility.principal("sarah-1")
        assert can_see(v, principal_id="sarah-1", role="support", is_founder=False) is True
        assert can_see(v, principal_id="tom-1", role="support", is_founder=False) is False

    def test_category_permission(self):
        p = Principal.team_member(
            id="sarah-1",
            name="Sarah",
            role=Role.SUPPORT,
            allowed_categories=["replies", "follow_ups"],
        )
        assert p.can_access_category("replies") is True
        assert p.can_access_category("outreach") is False


class TestRegistryEventSourceReplay:
    def test_event_driven_registry(self):
        orch = Orchestrator()
        assert len(orch.registry.all()) == 1  # Just founder initially

        # Invite Sarah
        evt1 = TrustEvent.founder_invited_team_member(
            principal_id="sarah-1",
            name="Sarah",
            role="support",
            allowed_categories=("replies", "follow_ups"),
        )
        orch._emit_trust_events((evt1,))

        assert len(orch.registry.all()) == 2
        p = orch.registry.get("sarah-1")
        assert p is not None
        assert p.name == "Sarah"
        assert p.role is Role.SUPPORT
        assert p.allowed_categories == ("replies", "follow_ups")

        # Revoke Sarah
        evt2 = TrustEvent.founder_revoked_team_member(
            principal_id="sarah-1",
            name="Sarah",
        )
        orch._emit_trust_events((evt2,))

        assert len(orch.registry.all()) == 1
        assert orch.registry.get("sarah-1") is None


class TestScopedHomeScreen:
    def test_founder_vs_member_briefing_filtering(self):
        orch = Orchestrator()
        # Invite Tom (Sales Rep)
        evt = TrustEvent.founder_invited_team_member(
            principal_id="tom-1",
            name="Tom",
            role="sales",
            allowed_categories=("outreach", "replies"),
        )
        orch._emit_trust_events((evt,))

        # Staged Action 1: Outreach (Sales allowed)
        a1 = make_action(
            actor="Zilo",
            category="outreach",
            summary="Nudge Meridian",
            confidence=0.9,
        )
        a1 = a1.propose(
            actor_name="Zilo",
            rank_at_time=Rank.DRAFTER,
            category="outreach",
            kind=ActionKind.OUTREACH,
            summary="Nudge Meridian",
            confidence=0.9,
            visibility=visibility_team_shared,
        )
        orch.ledger.record_proposal(a1)
        orch.ledger.transition(action_id=a1.id, to_state=ActionState.STAGED, actor_name="Zilo")

        # Staged Action 2: Invoices (Finance/Founder only, Sales cannot see)
        a2 = make_action(
            actor="Zilo",
            category="invoices",
            summary="Chasing unpaid invoice",
            confidence=0.85,
        )
        a2 = a2.propose(
            actor_name="Zilo",
            rank_at_time=Rank.DRAFTER,
            category="invoices",
            kind=ActionKind.INVOICE,
            summary="Chasing unpaid invoice",
            confidence=0.85,
            visibility=visibility_founder_only,
        )
        orch.ledger.record_proposal(a2)
        orch.ledger.transition(action_id=a2.id, to_state=ActionState.STAGED, actor_name="Zilo")

        # Build screen for Tom (Sales)
        tom_p = orch.registry.get("tom-1")
        tom_home = build_home_screen(orch, now=_utc(), relationship_day=5, principal=tom_p)

        assert tom_home.counts.staged == 1
        assert len(tom_home.letter.actions) == 1
        assert tom_home.letter.actions[0].summary == "Nudge Meridian"

        # Build screen for Founder
        founder_home = build_home_screen(orch, now=_utc(), relationship_day=5)
        assert founder_home.counts.staged == 2
        assert len(founder_home.letter.actions) == 2


class TestTeamJournalWriter:
    def test_journal_entry_for_team_invite(self):
        event = TrustEvent.founder_invited_team_member(
            principal_id="sarah-1",
            name="Sarah",
            role="support",
            allowed_categories=("replies", "follow_ups"),
        )
        entry = write_entry_for_trust_event(event, relationship_day=34)

        assert isinstance(entry, JournalEntry)
        assert entry.kind is JournalEventKind.TEAM
        assert "Added Sarah to the team as Support." in entry.body
        assert "briefing" in entry.body

    def test_journal_entry_for_team_revoke(self):
        event = TrustEvent.founder_revoked_team_member(
            principal_id="sarah-1",
            name="Sarah",
        )
        entry = write_entry_for_trust_event(event, relationship_day=41)

        assert isinstance(entry, JournalEntry)
        assert entry.kind is JournalEventKind.TEAM
        assert "Revoked access for Sarah." in entry.body
