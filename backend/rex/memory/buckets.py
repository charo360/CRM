"""
The three Notebook buckets — REX.md §3.13.

People    — observations about specific humans (contacts, customers, leads)
Patterns  — recurring mechanics of how the user / their market behaves
Lanes     — which categories Rex deliberately stays out of, and why

Each bucket has its own voice constraints (enforced in voice_check.py):

  People   : Subject is required. Refer by name. "Patel — responds to..."
  Patterns : Subject is optional. Generic mechanics. "Reply rates drop 60% on Tuesdays."
  Lanes    : Subject is the Category name. Always self-aware.
             "Payments — Observer only. Their call, not mine. Yet."
"""

from __future__ import annotations

from enum import Enum


class Bucket(str, Enum):
    PEOPLE = "people"
    PATTERNS = "patterns"
    LANES = "lanes"

    @property
    def display(self) -> str:
        return {
            Bucket.PEOPLE: "People",
            Bucket.PATTERNS: "Patterns",
            Bucket.LANES: "Lanes",
        }[self]

    @property
    def subject_required(self) -> bool:
        """People + Lanes need a subject. Patterns don't."""
        return self is not Bucket.PATTERNS
