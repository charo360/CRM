"""
Tests for the four intelligence innovations:
  1. save_notebook_observation / search_notebook tools (Innovation 1)
  2. save_agent_hint / read_agent_hints tools (Innovation 2)
  3. retrieve_knowledge unified tool (Innovation 3)
  4. _score_relationship_health background loop (Innovation 4)

Run from repo root:
    $env:PYTHONPATH="backend"
    python -m pytest backend/tests/test_intelligence_innovations.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── ToolContext stub ──────────────────────────────────────────────────────────
def _make_ctx(db=None):
    from assistant.tools import ToolContext
    user = {"_id": "user-1", "business_id": "biz-1"}
    ctx = ToolContext(db=db or MagicMock(), user=user)
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# INNOVATION 1 — save_notebook_observation
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveNotebookObservation:
    """save_notebook_observation tool validation."""

    @pytest.mark.anyio
    async def test_missing_text_returns_error(self):
        from assistant.tools import save_notebook_observation
        ctx = _make_ctx()
        result = await save_notebook_observation(ctx, {"bucket": "patterns", "text": ""})
        assert "error" in result

    @pytest.mark.anyio
    async def test_invalid_bucket_returns_error(self):
        from assistant.tools import save_notebook_observation
        ctx = _make_ctx()
        result = await save_notebook_observation(ctx, {"bucket": "bogus", "text": "Something."})
        assert "error" in result

    @pytest.mark.anyio
    async def test_voice_violation_returns_friendly_error(self):
        """Field-style text should be rejected by voice validation."""
        from assistant.tools import save_notebook_observation
        from rex.memory.buckets import Bucket
        from rex.memory.notebook import Notebook
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()  # in-memory orchestrator

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch), \
             patch.object(ZiloSessionStore, "save", new_callable=AsyncMock):
            ctx = _make_ctx()
            result = await save_notebook_observation(ctx, {
                "bucket": "people",
                "subject": "Patel",
                "text": "Contact: Patel | Preference: Direct | Notes: price-sensitive",
            })
        assert "error" in result
        assert "Voice validation" in result["error"] or "voice" in result.get("error", "").lower()

    @pytest.mark.anyio
    async def test_valid_people_entry_saved(self):
        from assistant.tools import save_notebook_observation
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch), \
             patch.object(ZiloSessionStore, "save", new_callable=AsyncMock) as mock_save:
            ctx = _make_ctx()
            result = await save_notebook_observation(ctx, {
                "bucket": "people",
                "subject": "Patel",
                "text": "Patel — responds to directness, not warmth. Warm approach failed twice.",
                "tags": ["outreach"],
            })

        assert result.get("ok") is True
        assert result["bucket"] == "people"
        assert result["subject"] == "Patel"
        assert mock_save.called

    @pytest.mark.anyio
    async def test_valid_patterns_entry_saved(self):
        from assistant.tools import save_notebook_observation
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch), \
             patch.object(ZiloSessionStore, "save", new_callable=AsyncMock):
            ctx = _make_ctx()
            result = await save_notebook_observation(ctx, {
                "bucket": "patterns",
                "text": "Reply rates drop 60% on Tuesdays across all outreach campaigns.",
            })

        assert result.get("ok") is True
        assert result["bucket"] == "patterns"

    @pytest.mark.anyio
    async def test_valid_lanes_entry_saved(self):
        from assistant.tools import save_notebook_observation
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch), \
             patch.object(ZiloSessionStore, "save", new_callable=AsyncMock):
            ctx = _make_ctx()
            result = await save_notebook_observation(ctx, {
                "bucket": "lanes",
                "subject": "payments",
                "text": "Payments — Observer only. Their call, not mine. Yet.",
            })

        assert result.get("ok") is True
        assert result["bucket"] == "lanes"


# ─────────────────────────────────────────────────────────────────────────────
# INNOVATION 1 — search_notebook
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchNotebook:
    """search_notebook tool."""

    @pytest.mark.anyio
    async def test_empty_notebook_returns_empty(self):
        from assistant.tools import search_notebook
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch):
            ctx = _make_ctx()
            result = await search_notebook(ctx, {"query": "Patel pricing"})

        assert result["count"] == 0
        assert result["entries"] == []

    @pytest.mark.anyio
    async def test_subject_search_returns_hit(self):
        from assistant.tools import search_notebook
        from rex.memory.buckets import Bucket
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()
        mock_orch.notebook.add(
            bucket=Bucket.PEOPLE,
            subject="Patel",
            text="Patel — responds to directness, not warmth. Tried warm twice.",
        )

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch):
            ctx = _make_ctx()
            result = await search_notebook(ctx, {"subject": "Patel"})

        assert result["count"] >= 1
        assert any(e["subject"] == "Patel" for e in result["entries"])

    @pytest.mark.anyio
    async def test_bucket_filter_limits_results(self):
        from assistant.tools import search_notebook
        from rex.memory.buckets import Bucket
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()
        mock_orch.notebook.add(bucket=Bucket.PEOPLE, subject="Alice", text="Alice — direct communicator.")
        mock_orch.notebook.add(bucket=Bucket.PATTERNS, text="Reply rates drop on Tuesdays.")

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch):
            ctx = _make_ctx()
            result = await search_notebook(ctx, {"query": "reply rates", "bucket": "people"})

        # Should not return the patterns entry when filtering for people only
        for entry in result.get("entries", []):
            assert entry["bucket"] == "people"


# ─────────────────────────────────────────────────────────────────────────────
# INNOVATION 2 — save_agent_hint / read_agent_hints
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentHints:
    """Cross-agent shared scratchpad tools."""

    @pytest.mark.anyio
    async def test_save_hint_missing_fields_returns_error(self):
        from assistant.tools import save_agent_hint
        ctx = _make_ctx()
        result = await save_agent_hint(ctx, {"category": "", "hint": ""})
        assert "error" in result

    @pytest.mark.anyio
    async def test_save_hint_too_long_returns_error(self):
        from assistant.tools import save_agent_hint
        ctx = _make_ctx()
        result = await save_agent_hint(ctx, {
            "category": "social",
            "hint": "x" * 501,
        })
        assert "error" in result

    @pytest.mark.anyio
    async def test_save_hint_writes_to_db(self):
        from assistant.tools import save_agent_hint

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "abc123"
        mock_db.agent_hints.insert_one = AsyncMock(return_value=mock_result)

        ctx = _make_ctx(db=mock_db)
        result = await save_agent_hint(ctx, {
            "category": "social",
            "hint": "Instagram Reels performing 3× better than static posts this month.",
            "agent": "social_media",
        })

        assert result.get("ok") is True
        assert result["category"] == "social"
        mock_db.agent_hints.insert_one.assert_called_once()

    @pytest.mark.anyio
    async def test_read_hints_returns_list(self):
        from assistant.tools import read_agent_hints

        mock_row = {
            "_id": "id1",
            "category": "social",
            "hint": "Reels outperform static 3×.",
            "agent": "social_media",
            "created_at": datetime.utcnow(),
        }

        mock_db = MagicMock()
        mock_find = MagicMock()
        mock_find.sort.return_value = mock_find
        mock_find.to_list = AsyncMock(return_value=[mock_row])
        mock_db.agent_hints.find.return_value = mock_find

        ctx = _make_ctx(db=mock_db)
        result = await read_agent_hints(ctx, {"category": "social"})

        assert result["count"] == 1
        assert result["hints"][0]["category"] == "social"
        assert "Reels" in result["hints"][0]["hint"]

    @pytest.mark.anyio
    async def test_read_hints_empty_returns_message(self):
        from assistant.tools import read_agent_hints

        mock_db = MagicMock()
        mock_find = MagicMock()
        mock_find.sort.return_value = mock_find
        mock_find.to_list = AsyncMock(return_value=[])
        mock_db.agent_hints.find.return_value = mock_find

        ctx = _make_ctx(db=mock_db)
        result = await read_agent_hints(ctx, {})

        assert result["count"] == 0
        assert "message" in result


# ─────────────────────────────────────────────────────────────────────────────
# INNOVATION 3 — retrieve_knowledge (unified retrieval)
# ─────────────────────────────────────────────────────────────────────────────

class TestRetrieveKnowledge:
    """Unified knowledge retrieval tool."""

    @pytest.mark.anyio
    async def test_missing_query_returns_error(self):
        from assistant.tools import retrieve_knowledge
        ctx = _make_ctx()
        result = await retrieve_knowledge(ctx, {"query": ""})
        assert "error" in result

    @pytest.mark.anyio
    async def test_notebook_source_included(self):
        from assistant.tools import retrieve_knowledge
        from rex.memory.buckets import Bucket
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()
        mock_orch.notebook.add(
            bucket=Bucket.PEOPLE,
            subject="Patel",
            text="Patel — responds to directness, not warmth.",
        )

        async def mock_search_knowledge(db, biz_id, query, top_k=4):
            return []

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch), \
             patch("smart_notes.knowledge.search_knowledge", side_effect=mock_search_knowledge):
            ctx = _make_ctx()
            result = await retrieve_knowledge(ctx, {"query": "Patel", "subject": "Patel"})

        assert result["count"] >= 1
        sources = [r["source"] for r in result["results"]]
        assert "notebook" in sources

    @pytest.mark.anyio
    async def test_smart_notes_source_included(self):
        from assistant.tools import retrieve_knowledge
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()  # empty notebook

        async def mock_search_knowledge(db, biz_id, query, top_k=4):
            return [{"title": "Q1 Review", "date": "2025-03-01",
                     "summary": "Discussed pricing strategy with Patel.", "score": 0.92}]

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch), \
             patch("smart_notes.knowledge.search_knowledge", side_effect=mock_search_knowledge):
            ctx = _make_ctx()
            result = await retrieve_knowledge(ctx, {"query": "Patel pricing"})

        sources = [r["source"] for r in result.get("results", [])]
        assert "smart_notes" in sources

    @pytest.mark.anyio
    async def test_empty_both_sources_returns_no_results(self):
        from assistant.tools import retrieve_knowledge
        from rex.loop import Orchestrator
        from rex.persistence.session import ZiloSessionStore

        mock_orch = Orchestrator()

        async def mock_search_knowledge(db, biz_id, query, top_k=4):
            return []

        with patch.object(ZiloSessionStore, "load", new_callable=AsyncMock, return_value=mock_orch), \
             patch("smart_notes.knowledge.search_knowledge", side_effect=mock_search_knowledge):
            ctx = _make_ctx()
            result = await retrieve_knowledge(ctx, {"query": "completely unknown topic xyz"})

        assert result["count"] == 0
        assert "message" in result


# ─────────────────────────────────────────────────────────────────────────────
# INNOVATION 4 — Relationship health scoring in platform sweep
# ─────────────────────────────────────────────────────────────────────────────

class TestRelationshipHealthScoring:
    """_score_relationship_health background function."""

    @pytest.mark.anyio
    async def test_no_cold_customers_returns_zero(self):
        from rex.integrations.platform_sweep import _score_relationship_health
        from rex.loop import Orchestrator

        mock_db = MagicMock()
        # No cold customers
        mock_find = MagicMock()
        mock_find.sort.return_value = mock_find
        mock_find.limit.return_value = mock_find
        mock_find.to_list = AsyncMock(return_value=[])
        mock_db.customers.find.return_value = mock_find
        mock_db.invoices.find.return_value = mock_find
        mock_db.customers.count_documents = AsyncMock(return_value=0)

        orch = Orchestrator()
        result = await _score_relationship_health(mock_db, "user-1", orch)

        assert result["cold_customers"] == 0
        assert result["notebook_writes"] == 0

    @pytest.mark.anyio
    async def test_cold_customer_writes_notebook(self):
        from rex.integrations.platform_sweep import _score_relationship_health
        from rex.loop import Orchestrator

        mock_db = MagicMock()
        cold_cust = {
            "_id": "cust-1",
            "name": "Johnson",
            "last_interaction": datetime.utcnow() - timedelta(days=45),
            "total_orders": 3,
        }
        mock_find_cold = MagicMock()
        mock_find_cold.sort.return_value = mock_find_cold
        mock_find_cold.limit.return_value = mock_find_cold
        mock_find_cold.to_list = AsyncMock(return_value=[cold_cust])

        mock_find_empty = MagicMock()
        mock_find_empty.sort.return_value = mock_find_empty
        mock_find_empty.limit.return_value = mock_find_empty
        mock_find_empty.to_list = AsyncMock(return_value=[])

        # first call = cold customers, second = overdue invoices
        mock_db.customers.find.side_effect = [mock_find_cold, mock_find_empty]
        mock_db.invoices.find.return_value = mock_find_empty
        mock_db.customers.count_documents = AsyncMock(return_value=0)

        orch = Orchestrator()
        result = await _score_relationship_health(mock_db, "user-1", orch)

        assert result["cold_customers"] == 1
        assert result["notebook_writes"] >= 1
        # Verify notebook has entry for Johnson
        entries = orch.notebook.by_subject("Johnson")
        assert len(entries) >= 1
        assert "johnson" in entries[0].text.lower() or "Johnson" in entries[0].text

    @pytest.mark.anyio
    async def test_already_noted_customer_not_duplicated(self):
        from rex.integrations.platform_sweep import _score_relationship_health
        from rex.memory.buckets import Bucket
        from rex.loop import Orchestrator

        mock_db = MagicMock()
        cold_cust = {
            "_id": "cust-2",
            "name": "Martinez",
            "last_interaction": datetime.utcnow() - timedelta(days=50),
            "total_orders": 2,
        }
        mock_find_cold = MagicMock()
        mock_find_cold.sort.return_value = mock_find_cold
        mock_find_cold.limit.return_value = mock_find_cold
        mock_find_cold.to_list = AsyncMock(return_value=[cold_cust])

        mock_find_empty = MagicMock()
        mock_find_empty.sort.return_value = mock_find_empty
        mock_find_empty.limit.return_value = mock_find_empty
        mock_find_empty.to_list = AsyncMock(return_value=[])

        mock_db.customers.find.side_effect = [mock_find_cold, mock_find_empty]
        mock_db.invoices.find.return_value = mock_find_empty
        mock_db.customers.count_documents = AsyncMock(return_value=0)

        orch = Orchestrator()
        # Pre-seed notebook with existing entry for Martinez
        orch.notebook.add(
            bucket=Bucket.PEOPLE,
            subject="Martinez",
            text="Martinez — price-sensitive but won't say it directly.",
        )
        initial_count = len(orch.notebook.all())

        await _score_relationship_health(mock_db, "user-1", orch)

        # Should NOT have added a duplicate — existing entry guards this
        assert len(orch.notebook.all()) == initial_count

    @pytest.mark.anyio
    async def test_broad_pattern_written_when_20pct_cold(self):
        from rex.integrations.platform_sweep import _score_relationship_health
        from rex.loop import Orchestrator

        mock_db = MagicMock()

        mock_find_empty = MagicMock()
        mock_find_empty.sort.return_value = mock_find_empty
        mock_find_empty.limit.return_value = mock_find_empty
        mock_find_empty.to_list = AsyncMock(return_value=[])

        mock_db.customers.find.return_value = mock_find_empty
        mock_db.invoices.find.return_value = mock_find_empty
        # 40% of customers are very cold (>60 days)
        mock_db.customers.count_documents = AsyncMock(side_effect=[100, 40])

        orch = Orchestrator()
        result = await _score_relationship_health(mock_db, "user-1", orch)

        pattern_entries = orch.notebook.by_bucket(
            __import__("rex.memory.buckets", fromlist=["Bucket"]).Bucket.PATTERNS
        )
        assert len(pattern_entries) >= 1
        assert any("contact" in e.text.lower() or "%" in e.text for e in pattern_entries)


# ─────────────────────────────────────────────────────────────────────────────
# INNOVATION 1 — Tool allowlist: verify new tools are registered in GENERAL_TOOLS
# ─────────────────────────────────────────────────────────────────────────────

class TestToolAllowlists:
    """Verify new tools are wired into the correct agent allowlists."""

    def test_retrieve_knowledge_in_general_tools(self):
        from assistant.agents import GENERAL_TOOLS
        assert "retrieve_knowledge" in GENERAL_TOOLS

    def test_search_notebook_in_general_tools(self):
        from assistant.agents import GENERAL_TOOLS
        assert "search_notebook" in GENERAL_TOOLS

    def test_save_notebook_observation_in_general_tools(self):
        from assistant.agents import GENERAL_TOOLS
        assert "save_notebook_observation" in GENERAL_TOOLS

    def test_save_agent_hint_in_general_tools(self):
        from assistant.agents import GENERAL_TOOLS
        assert "save_agent_hint" in GENERAL_TOOLS

    def test_read_agent_hints_in_general_tools(self):
        from assistant.agents import GENERAL_TOOLS
        assert "read_agent_hints" in GENERAL_TOOLS

    def test_retrieve_knowledge_in_document_tools(self):
        from assistant.agents import DOCUMENT_TOOLS
        assert "retrieve_knowledge" in DOCUMENT_TOOLS

    def test_search_notebook_in_document_tools(self):
        from assistant.agents import DOCUMENT_TOOLS
        assert "search_notebook" in DOCUMENT_TOOLS

    def test_retrieve_knowledge_in_google_calendar_tools(self):
        from assistant.agents import GOOGLE_CALENDAR_TOOLS
        assert "retrieve_knowledge" in GOOGLE_CALENDAR_TOOLS

    def test_retrieve_knowledge_in_microsoft_tools(self):
        from assistant.agents import MICROSOFT_TOOLS
        assert "retrieve_knowledge" in MICROSOFT_TOOLS

    def test_all_new_tools_registered_in_tool_registry(self):
        """All five new tools must be importable from the REGISTRY."""
        from assistant.tools import REGISTRY
        new_tools = [
            "save_notebook_observation",
            "search_notebook",
            "retrieve_knowledge",
            "save_agent_hint",
            "read_agent_hints",
        ]
        for tool_name in new_tools:
            assert tool_name in REGISTRY, f"Missing from REGISTRY: {tool_name}"

    def test_memory_protocol_in_expert_shell(self):
        """PLUGGABLE_EXPERT_SHELL must contain the Unified Memory Protocol."""
        from assistant.agent_contract import PLUGGABLE_EXPERT_SHELL
        assert "UNIFIED MEMORY PROTOCOL" in PLUGGABLE_EXPERT_SHELL
        assert "retrieve_knowledge" in PLUGGABLE_EXPERT_SHELL
        assert "save_notebook_observation" in PLUGGABLE_EXPERT_SHELL
        assert "save_agent_hint" in PLUGGABLE_EXPERT_SHELL
