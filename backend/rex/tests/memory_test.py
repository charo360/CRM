"""
Tests for rex.memory — the Notebook.

Coverage:
    1. Bucket enum + subject-required rule
    2. NotebookEntry factory + immutable updates
    3. InMemoryNotebookStore semantics (put/get/delete/by_bucket/by_subject)
    4. Notebook facade — add/update/delete/queries
    5. Voice validation — field-style, reflection, advice rejection
    6. Notebook entries in Rex's voice from REX.md pass clean
    7. find_relevant retrieval (subject > tag > token-overlap)
    8. entry_to_citation bridge to Phase 1

Run from backend/:
    python -m pytest rex/tests/memory_test.py -v
"""

from __future__ import annotations

import pytest

from rex.memory import (
    Bucket,
    NotebookEntry,
    NotebookStore, InMemoryNotebookStore,
    Notebook, find_relevant,
    NotebookVoiceReport, NotebookVoiceIssue, validate_notebook_entry,
    entry_to_citation,
)
from rex.memory.notebook import NotebookVoiceError
from rex.persona.voice_rules import Severity


# ===========================================================================
# Bucket
# ===========================================================================

class TestBucket:
    def test_three_buckets(self):
        assert set(Bucket) == {Bucket.PEOPLE, Bucket.PATTERNS, Bucket.LANES}

    def test_display_names(self):
        assert Bucket.PEOPLE.display == "People"
        assert Bucket.PATTERNS.display == "Patterns"
        assert Bucket.LANES.display == "Lanes"

    def test_subject_required_rule(self):
        assert Bucket.PEOPLE.subject_required
        assert Bucket.LANES.subject_required
        assert not Bucket.PATTERNS.subject_required


# ===========================================================================
# NotebookEntry
# ===========================================================================

class TestNotebookEntry:
    def test_new_person_requires_subject(self):
        with pytest.raises(ValueError, match="People entries require"):
            NotebookEntry.new(
                bucket=Bucket.PEOPLE,
                text="Responds to directness.",
                subject=None,
            )

    def test_new_pattern_does_not_require_subject(self):
        e = NotebookEntry.new(
            bucket=Bucket.PATTERNS,
            text="Reply rates drop 60% on Tuesdays.",
        )
        assert e.subject is None

    def test_with_text_marks_user_edit(self):
        e = NotebookEntry.new(
            bucket=Bucket.PEOPLE,
            subject="Patel",
            text="Responds to directness.",
        )
        assert not e.edited_by_user
        e2 = e.with_text("Updated.", by_user=True)
        assert e2.edited_by_user
        assert e2.text == "Updated."
        # Original is untouched (frozen).
        assert e.text == "Responds to directness."

    def test_with_added_source_is_idempotent(self):
        e = NotebookEntry.new(
            bucket=Bucket.PEOPLE, subject="Patel", text="x",
        )
        e2 = e.with_added_source("evt-1")
        e3 = e2.with_added_source("evt-1")  # duplicate
        assert e2.source_event_ids == ("evt-1",)
        assert e3.source_event_ids == ("evt-1",)

    def test_text_is_stripped(self):
        e = NotebookEntry.new(
            bucket=Bucket.PATTERNS,
            text="   whitespace around me.   ",
        )
        assert e.text == "whitespace around me."


# ===========================================================================
# InMemoryNotebookStore
# ===========================================================================

class TestStore:
    def test_satisfies_protocol(self):
        s = InMemoryNotebookStore()
        assert isinstance(s, NotebookStore)

    def test_put_and_get(self):
        s = InMemoryNotebookStore()
        e = NotebookEntry.new(bucket=Bucket.PATTERNS, text="A.")
        s.put(e)
        assert s.get(e.id) == e

    def test_get_missing_returns_none(self):
        assert InMemoryNotebookStore().get("nope") is None

    def test_delete_returns_true_when_present(self):
        s = InMemoryNotebookStore()
        e = NotebookEntry.new(bucket=Bucket.PATTERNS, text="A.")
        s.put(e)
        assert s.delete(e.id) is True
        assert s.delete(e.id) is False

    def test_by_bucket(self):
        s = InMemoryNotebookStore()
        s.put(NotebookEntry.new(bucket=Bucket.PEOPLE, subject="A", text="x."))
        s.put(NotebookEntry.new(bucket=Bucket.PEOPLE, subject="B", text="y."))
        s.put(NotebookEntry.new(bucket=Bucket.PATTERNS, text="z."))
        assert len(s.by_bucket(Bucket.PEOPLE)) == 2
        assert len(s.by_bucket(Bucket.PATTERNS)) == 1
        assert len(s.by_bucket(Bucket.LANES)) == 0

    def test_by_subject_case_insensitive(self):
        s = InMemoryNotebookStore()
        s.put(NotebookEntry.new(bucket=Bucket.PEOPLE, subject="Patel", text="x."))
        assert len(s.by_subject("patel")) == 1
        assert len(s.by_subject("PATEL")) == 1
        assert len(s.by_subject("nobody")) == 0


# ===========================================================================
# Notebook facade
# ===========================================================================

class TestNotebookFacade:
    def test_add_valid_person_entry(self):
        nb = Notebook()
        e = nb.add(
            bucket=Bucket.PEOPLE, subject="Patel",
            text="Responds to directness, not warmth. Don't follow up on Fridays.",
        )
        assert e.id in {x.id for x in nb.all()}
        assert nb.get(e.id) == e

    def test_add_rejects_voice_violation(self):
        nb = Notebook()
        # Field-style format — should be rejected.
        with pytest.raises(NotebookVoiceError):
            nb.add(
                bucket=Bucket.PEOPLE, subject="Patel",
                text="Contact: Patel | Preference: Direct | Avoid: Fridays",
            )

    def test_add_rejects_first_person_reflection(self):
        nb = Notebook()
        with pytest.raises(NotebookVoiceError):
            nb.add(
                bucket=Bucket.PATTERNS,
                text="I noticed that Tuesdays produce low reply rates.",
            )

    def test_add_rejects_advice(self):
        nb = Notebook()
        with pytest.raises(NotebookVoiceError):
            nb.add(
                bucket=Bucket.PATTERNS,
                text="You should always send before 9am.",
            )

    def test_canonical_rex_md_examples_pass(self):
        """The example entries from REX.md §3.13 must all validate clean."""
        nb = Notebook()
        # People
        nb.add(
            bucket=Bucket.PEOPLE, subject="Patel",
            text=(
                "Patel — responds to directness, not warmth. "
                "Tried warm twice. Neither worked."
            ),
        )
        # Pattern
        nb.add(
            bucket=Bucket.PATTERNS,
            text="Reply rates drop 60% on Tuesdays.",
        )
        # Lane (the "self-awareness" example)
        nb.add(
            bucket=Bucket.LANES, subject="payments",
            text="Payments — Observer only. Their call, not mine. Yet.",
        )
        assert len(nb) == 3

    def test_user_edit_bypasses_voice_rules(self):
        """REX.md §3.13 — users can edit anything they want."""
        nb = Notebook()
        e = nb.add(
            bucket=Bucket.PATTERNS,
            text="Reply rates drop 60% on Tuesdays.",
        )
        # User writes whatever — should be accepted.
        edited = nb.update_text(e.id, "I think Tuesdays are slow.", by_user=True)
        assert edited.text == "I think Tuesdays are slow."
        assert edited.edited_by_user

    def test_update_missing_raises(self):
        nb = Notebook()
        with pytest.raises(KeyError):
            nb.update_text("missing", "anything")

    def test_delete(self):
        nb = Notebook()
        e = nb.add(bucket=Bucket.PATTERNS, text="Reply rates drop on Tuesdays.")
        assert nb.delete(e.id) is True
        assert nb.delete(e.id) is False
        assert nb.get(e.id) is None

    def test_count_by_bucket(self):
        nb = Notebook()
        nb.add(bucket=Bucket.PEOPLE, subject="A", text="One.")
        nb.add(bucket=Bucket.PEOPLE, subject="B", text="Two.")
        nb.add(bucket=Bucket.PATTERNS, text="Three.")
        counts = nb.count_by_bucket()
        assert counts[Bucket.PEOPLE] == 2
        assert counts[Bucket.PATTERNS] == 1
        assert counts[Bucket.LANES] == 0


# ===========================================================================
# Voice validation — direct
# ===========================================================================

class TestNotebookVoiceValidation:
    def test_clean_entry_passes(self):
        r = validate_notebook_entry(
            "Patel — responds to directness, not warmth.",
            Bucket.PEOPLE, subject="Patel",
        )
        assert r.passed
        assert r.score >= 0.95

    def test_missing_subject_for_people_flagged(self):
        r = validate_notebook_entry(
            "Some observation.", Bucket.PEOPLE, subject=None,
        )
        issues = {f.issue for f in r.flags}
        assert NotebookVoiceIssue.MISSING_SUBJECT in issues
        assert not r.passed

    def test_field_style_flagged(self):
        r = validate_notebook_entry(
            "Contact: Patel | Preference: Direct",
            Bucket.PEOPLE, subject="Patel",
        )
        issues = {f.issue for f in r.flags}
        assert NotebookVoiceIssue.FIELD_STYLE in issues

    def test_first_person_reflection_flagged(self):
        r = validate_notebook_entry(
            "I noticed Patel goes quiet on Fridays.",
            Bucket.PEOPLE, subject="Patel",
        )
        issues = {f.issue for f in r.flags}
        assert NotebookVoiceIssue.FIRST_PERSON_REFLECTION in issues

    def test_advice_flagged(self):
        r = validate_notebook_entry(
            "You should send before 9am.",
            Bucket.PATTERNS,
        )
        issues = {f.issue for f in r.flags}
        assert NotebookVoiceIssue.ADVICE_TO_READER in issues

    def test_long_entry_soft_flag(self):
        long = (
            "First sentence here. Second sentence here. "
            "Third sentence here. Fourth sentence here. "
            "Fifth sentence here."
        )
        r = validate_notebook_entry(long, Bucket.PATTERNS)
        issues = {f.issue for f in r.flags}
        assert NotebookVoiceIssue.TOO_MANY_SENTENCES in issues
        # SOFT only — still passes overall.
        assert r.passed

    def test_emoji_caught_via_generic_layer(self):
        r = validate_notebook_entry(
            "Patel replies fast 👍", Bucket.PEOPLE, subject="Patel",
        )
        assert not r.passed
        # Should appear under GENERIC_VOICE_VIOLATION.
        assert any(
            f.issue is NotebookVoiceIssue.GENERIC_VOICE_VIOLATION
            for f in r.flags
        )


# ===========================================================================
# Relevance retrieval
# ===========================================================================

class TestFindRelevant:
    def _populated(self) -> Notebook:
        nb = Notebook()
        nb.add(bucket=Bucket.PEOPLE, subject="Patel",
               text="Patel — responds to directness, not warmth.",
               tags=("outreach",))
        nb.add(bucket=Bucket.PEOPLE, subject="Henderson",
               text="Henderson — price-sensitive but won't say it directly.",
               tags=("outreach",))
        nb.add(bucket=Bucket.PATTERNS,
               text="Reply rates drop 60% on Tuesdays.",
               tags=("outreach",))
        nb.add(bucket=Bucket.LANES, subject="payments",
               text="Payments — Observer only. Their call, not mine. Yet.",
               tags=("payments",))
        return nb

    def test_exact_subject_match_ranks_first(self):
        nb = self._populated()
        results = find_relevant(nb, subject="Patel", limit=2)
        assert len(results) >= 1
        assert results[0].subject == "Patel"

    def test_tag_match_when_no_subject(self):
        nb = self._populated()
        results = find_relevant(nb, category="payments", limit=2)
        # Should pick up the lane entry tagged "payments".
        assert any(e.subject == "payments" for e in results)

    def test_token_overlap_query(self):
        nb = self._populated()
        results = find_relevant(nb, query="reply rates Tuesday", limit=2)
        assert results
        assert "tuesdays" in results[0].text.lower()

    def test_limit_is_respected(self):
        nb = self._populated()
        results = find_relevant(nb, query="responds Patel Henderson", limit=1)
        assert len(results) == 1

    def test_no_matches_returns_empty(self):
        nb = self._populated()
        results = find_relevant(nb, subject="Nobody", query="xyz123")
        assert results == ()


# ===========================================================================
# Citation bridge
# ===========================================================================

class TestEntryToCitation:
    def test_basic_roundtrip(self):
        e = NotebookEntry.new(
            bucket=Bucket.PEOPLE, subject="Patel",
            text="Patel — responds to directness, not warmth. Don't follow up Fridays.",
        )
        c = entry_to_citation(e, confidence_pct=94)
        assert c.confidence_pct == 94
        assert "directness" in c.observation
        # No newlines — citations are single-line.
        assert "\n" not in c.observation

    def test_long_entry_truncated(self):
        long_text = (
            "Patel — responds to directness. " * 20
        ).strip()
        e = NotebookEntry.new(
            bucket=Bucket.PEOPLE, subject="Patel", text=long_text,
        )
        c = entry_to_citation(e, confidence_pct=80)
        assert len(c.observation) <= 200

    def test_confidence_pct_passthrough(self):
        e = NotebookEntry.new(
            bucket=Bucket.PATTERNS, text="Reply rates drop on Tuesdays.",
        )
        c = entry_to_citation(e, confidence_pct=50)
        assert c.confidence_pct == 50
        with pytest.raises(ValueError):
            entry_to_citation(e, confidence_pct=200)
