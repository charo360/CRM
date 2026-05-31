"""
Tests for rex.channels — Phase 9: Channel Delivery Layer (REX.md §4.7).

Coverage:
    1. Channel urgency routing (UrgencyLevel, EventType matching)
    2. Multi-channel letter renderers (WhatsApp, Telegram, SMS, Email, In-app)
    3. Inbound text parser (unstructured reply parsing, indices, keywords)
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from rex.briefing.letter import Letter, LetterAction
from rex.channels import (
    Channel,
    UrgencyLevel,
    ActionVerb,
    route_event_to_channels,
    render_for_channel,
    parse_reply,
)
from rex.ranks.events import EventType, TrustEvent


def _mock_letter(quiet_night=False) -> Letter:
    if quiet_night:
        return Letter(
            opener="Tuesday. 6:47am.",
            body="Tuesday. 6:47am.\n\nQuiet night. Nothing needs you this morning.\n\n— Rex",
            actions=(),
            quiet_night=True,
        )

    a1 = LetterAction(
        action_id="act-1",
        summary="Nudge Meridian about cold deal",
        confidence_pct=94,
        line="  06:47 — Nudge Meridian about cold deal",
        has_citation=False,
    )
    a2 = LetterAction(
        action_id="act-2",
        summary="Send pricing to Henderson",
        confidence_pct=88,
        line="  06:47 — Send pricing to Henderson",
        has_citation=True,
    )
    return Letter(
        opener="Tuesday. 6:47am.",
        body="Tuesday. 6:47am.\n\nQuiet night overall — but two things need you.\n\n...",
        actions=(a1, a2),
        quiet_night=False,
    )


class TestChannelRouting:
    def test_urgent_routes_to_sms(self):
        # Demoting Rex is a high-risk safety event — must route to SMS immediately
        evt = TrustEvent.user_demoted_rex(
            category="payments",
            from_rank=Rank.SENDER if hasattr(EventType, "SENDER") else 2,
            to_rank=Rank.DRAFTER if hasattr(EventType, "DRAFTER") else 1,
        )
        channels = route_event_to_channels(evt)
        assert Channel.SMS in channels
        assert Channel.WHATSAPP in channels

    def test_daily_operational_does_not_route_to_sms(self):
        evt = TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=0,
            to_rank=1,
        )
        channels = route_event_to_channels(evt)
        assert Channel.SMS not in channels
        assert Channel.EMAIL in channels


class TestChannelRenderers:
    def test_render_in_app_returns_raw_body(self):
        letter = _mock_letter()
        rendered = render_for_channel(letter, Channel.IN_APP)
        assert rendered == letter.body

    def test_render_whatsapp_numbered_layout(self):
        letter = _mock_letter()
        rendered = render_for_channel(letter, Channel.WHATSAPP)
        assert "Rex 🤝" in rendered
        assert "1/ Nudge Meridian" in rendered
        assert "Reply 1 YES to send" in rendered
        assert "2/ Send pricing" in rendered
        assert "LEDGER" in rendered

    def test_render_telegram_numbered_layout(self):
        letter = _mock_letter()
        rendered = render_for_channel(letter, Channel.TELEGRAM)
        assert "Rex 🤖" in rendered
        assert "1/ Nudge Meridian" in rendered

    def test_render_whatsapp_quiet_night(self):
        letter = _mock_letter(quiet_night=True)
        rendered = render_for_channel(letter, Channel.WHATSAPP)
        assert "Quiet night. Nothing needs you." in rendered

    def test_render_sms_dense_layout(self):
        letter = _mock_letter()
        rendered = render_for_channel(letter, Channel.SMS)
        assert "URGENT from Rex" in rendered
        assert "Nudge Meridian" in rendered
        assert "94%" in rendered

    def test_render_email_layout(self):
        letter = _mock_letter()
        rendered = render_for_channel(letter, Channel.EMAIL)
        assert "Subject: Daily Briefing" in rendered
        assert letter.body in rendered


class TestReplyParser:
    def test_exact_keywords(self):
        assert parse_reply(Channel.WHATSAPP, "yes")[0] is ActionVerb.APPROVE
        assert parse_reply(Channel.WHATSAPP, "send")[0] is ActionVerb.APPROVE
        assert parse_reply(Channel.WHATSAPP, "dismiss")[0] is ActionVerb.REJECT
        assert parse_reply(Channel.WHATSAPP, "ledger")[0] is ActionVerb.LEDGER
        assert parse_reply(Channel.WHATSAPP, "pause")[0] is ActionVerb.PAUSE

    def test_index_specific_reply(self):
        verb, action_id, idx = parse_reply(Channel.WHATSAPP, "1 yes")
        assert verb is ActionVerb.APPROVE
        assert action_id is None
        assert idx == 1

        verb, action_id, idx = parse_reply(Channel.WHATSAPP, "2 review")
        assert verb is ActionVerb.REVIEW
        assert idx == 2

    def test_context_awareness(self):
        verb, action_id, idx = parse_reply(Channel.WHATSAPP, "yes", context_action_id="act-1")
        assert verb is ActionVerb.APPROVE
        assert action_id == "act-1"
        assert idx is None

    def test_digit_fallback_to_review(self):
        verb, action_id, idx = parse_reply(Channel.WHATSAPP, "2")
        assert verb is ActionVerb.REVIEW
        assert idx == 2

    def test_unknown_fallback(self):
        assert parse_reply(Channel.WHATSAPP, "hello rex")[0] is ActionVerb.UNKNOWN
