"""
Inbound Bidirectional Reply Parser — translates unstructured SMS/WhatsApp/Telegram
responses into actionable business verbs (REX.md §4.7).

It is context-aware: we accept a context target_action_id so a simple "YES"
automatically binds to the relevant staged action in focus.
"""

from __future__ import annotations

import re

from rex.channels.primitives import ActionVerb, Channel


def parse_reply(channel: Channel, text: str, context_action_id: str | None = None) -> tuple[ActionVerb, str | None, int | None]:
    """
    Parse a text message from a user on a given channel.

    Returns:
        tuple[ActionVerb, action_id_or_none, action_index_or_none]

    Vocabulary:
        - "YES", "SEND", "1 YES" -> APPROVE
        - "NO", "DISMISS", "1 NO" -> REJECT
        - "REVIEW", "1 REVIEW" -> REVIEW
        - "EDIT" -> EDIT
        - "LEDGER" -> LEDGER
        - "PAUSE" -> PAUSE
    """
    norm = text.strip().upper()

    # 1) Try index-aware extraction e.g., "1 YES", "2 REVIEW"
    index_match = re.match(r"^(\d+)\s+(YES|NO|SEND|REVIEW|EDIT)$", norm)
    if index_match:
        idx = int(index_match.group(1))
        keyword = index_match.group(2)
        verb = _map_keyword(keyword)
        return verb, None, idx

    # 2) Standard keyword matching
    verb = _map_keyword(norm)
    if verb is not ActionVerb.UNKNOWN:
        return verb, context_action_id, None

    # Handle simple single digits as a request to REVIEW that item
    if re.match(r"^\d+$", norm):
        return ActionVerb.REVIEW, None, int(norm)

    return ActionVerb.UNKNOWN, None, None


def _map_keyword(kw: str) -> ActionVerb:
    if kw in {"YES", "SEND", "APPROVE", "OK"}:
        return ActionVerb.APPROVE
    if kw in {"NO", "DISMISS", "REJECT"}:
        return ActionVerb.REJECT
    if kw in {"REVIEW", "VIEW", "SHOW", "DETAILS"}:
        return ActionVerb.REVIEW
    if kw in {"EDIT", "CHANGE"}:
        return ActionVerb.EDIT
    if kw in {"LEDGER", "SUMMARY", "OVERVIEW"}:
        return ActionVerb.LEDGER
    if kw in {"PAUSE", "SILENCE", "STOP"}:
        return ActionVerb.PAUSE
    return ActionVerb.UNKNOWN
