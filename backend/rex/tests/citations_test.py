"""
Tests for rex.memory.citations — Phase 10: Auto-Citations (REX.md §3.13).

Coverage:
    1. Scan and attach matching logic (subject match, category match, keyword match).
    2. Minimum relevancy thresholds / flooring to prevent noise.
    3. Truncation and flattening to single-line observations.
    4. Orchestrator integration matching automatically during `run_overnight()`.
"""

from __future__ import annotations

import pytest

from rex.actions import Action, ActionKind, ActionState
from rex.loop import Orchestrator
from rex.memory import Bucket, Notebook
from rex.memory.citations import (
    entry_to_citation,
    _flatten_to_single_line,
    scan_and_attach_citations,
)
from rex.ranks.events import Rank, TrustEvent
from rex.tests.fakes import FakeProducer, make_action


class TestAutoCitationsScanner:
    def test_single_line_flattening_and_truncation(self):
        text = "This is line one.\nThis is line two. This is line three. This is line four."
        flat = _flatten_to_single_line(text, max_chars=40)
        assert "\n" not in flat
        assert flat.endswith("…") or flat.endswith(".")
        assert len(flat) <= 40

    def test_scanner_subject_match_wins(self):
        notebook = Notebook()
        # Add two entries
        e1 = notebook.add(
            bucket=Bucket.PEOPLE,
            subject="Patel",
            text="Patel responds better to directness, not warmth.",
        )
        e2 = notebook.add(
            bucket=Bucket.PATTERNS,
            text="General cold leads template matches.",
        )

        matches = scan_and_attach_citations(
            summary="Draft outreach to Patel.",
            category="outreach",
            target_subject="Patel",
            notebook=notebook,
        )

        assert len(matches) == 1
        assert matches[0] == e1.id

    def test_scanner_keyword_intersection_match(self):
        notebook = Notebook()
        e1 = notebook.add(
            bucket=Bucket.PATTERNS,
            text="When dealing with cold leads, keep the prose ex-McKinsey style.",
        )

        matches = scan_and_attach_citations(
            summary="Drafting cold outreach for leads.",
            category="outreach",
            target_subject=None,
            notebook=notebook,
        )

        assert len(matches) == 1
        assert matches[0] == e1.id

    def test_scanner_flooring_prevents_noise(self):
        notebook = Notebook()
        notebook.add(
            bucket=Bucket.PEOPLE,
            subject="Patel",
            text="Patel responds better to directness, not warmth.",
        )

        matches = scan_and_attach_citations(
            summary="Chasing unpaid invoices for Henderson.",
            category="invoices",
            target_subject="Henderson",
            notebook=notebook,
        )

        # No Patel references should hit Henderson's invoice actions
        assert len(matches) == 0


class TestOrchestratorAutoCitations:
    def test_overnight_auto_attaches_citations(self):
        orch = Orchestrator()
        # Seed Notebook
        entry = orch.notebook.add(
            bucket=Bucket.PEOPLE,
            subject="Acme",
            text="Acme is sensitive about billing cycles.",
        )

        # Promote Rex so drafts are staged
        orch.event_store.append(TrustEvent.user_promoted_rex(
            category="invoices",
            from_rank=Rank.OBSERVER, to_rank=Rank.DRAFTER,
        ))
        orch.engine = RankEngine = orch.engine.from_events(orch.event_store)

        # Produce a raw invoice proposal with NO pre-filled citations
        a = make_action(
            actor="Rex",
            rank=Rank.DRAFTER,
            category="invoices",
            kind=ActionKind.INVOICE,
            summary="Chase Acme invoice.",
            target="Acme",
        )
        assert len(a.memory_citation_ids) == 0

        orch.register_producer(FakeProducer(
            actor_name_value="Rex",
            categories_value=("invoices",),
            actions=[a],
        ))

        # Run loop
        orch.run_overnight()

        # Retrieve action from ledger
        staged_actions = list(orch.ledger.staged_actions())
        assert len(staged_actions) == 1
        staged_action = staged_actions[0]

        # Verified: Citation automatically attached by loop scanning
        assert len(staged_action.memory_citation_ids) == 1
        assert staged_action.memory_citation_ids[0] == entry.id
