"""Unit tests for Delegate scheduling and trigger matching."""

from datetime import datetime

from delegate.service import (
    _customer_matches_trigger_channel,
    _matches_frequency,
    _opportunity_matches_filter,
    compute_next_run,
)


def test_matches_frequency_every_day():
    assert _matches_frequency("every_day", datetime(2026, 6, 9, 12, 0))


def test_matches_frequency_weekday_only():
    monday = datetime(2026, 6, 8, 12, 0)  # Monday
    saturday = datetime(2026, 6, 13, 12, 0)
    assert _matches_frequency("every_weekday", monday)
    assert not _matches_frequency("every_weekday", saturday)


def test_compute_next_run_same_day_future_time():
    after = datetime(2026, 6, 9, 6, 0, 0)
    nxt = compute_next_run({"frequency": "every_day", "time": "07:00"}, after=after)
    assert nxt.date() == after.date()
    assert nxt.hour == 7
    assert nxt > after


def test_compute_next_run_rolls_forward_after_time_passed():
    after = datetime(2026, 6, 9, 18, 0, 0)
    nxt = compute_next_run({"frequency": "every_day", "time": "07:00"}, after=after)
    assert nxt > after
    assert nxt.hour == 7


def test_opportunity_filter_reddit():
    assert _opportunity_matches_filter({"url": "https://reddit.com/r/sales/foo"}, "reddit")
    assert not _opportunity_matches_filter({"url": "https://example.com"}, "reddit")


def test_opportunity_filter_excludes_client_triggers():
    assert not _opportunity_matches_filter({"url": "https://reddit.com/x"}, "first_message")
    assert not _opportunity_matches_filter({"url": "https://reddit.com/x"}, "client_message")


def test_customer_channel_filter():
    slack_customer = {"phone": "slack_U123", "slack_channel_id": "D123", "channel": "slack"}
    wa_customer = {"phone": "+15551234567", "channel": "whatsapp"}

    assert _customer_matches_trigger_channel(slack_customer, "any")
    assert _customer_matches_trigger_channel(slack_customer, "slack")
    assert not _customer_matches_trigger_channel(slack_customer, "whatsapp")
    assert _customer_matches_trigger_channel(wa_customer, "whatsapp")


def test_sanitize_lead_source_url_blocks_owner_and_zilo():
    from delegate.service import (
        _contacts_from_opportunity,
        _is_web_manual_item,
        _sanitize_lead_source_url,
        _work_item_from_opportunity_dict,
    )

    assert _sanitize_lead_source_url("https://zilo.pro/pricing") == ""
    assert _sanitize_lead_source_url("https://mybiz.com/page", owner_website="https://mybiz.com") == ""
    assert _sanitize_lead_source_url("https://reddit.com/r/sales/x") == "https://reddit.com/r/sales/x"
    assert _sanitize_lead_source_url(
        "https://example.com/listing",
        email="lead@example.com",
    ) == ""

    item = _work_item_from_opportunity_dict(
        {
            "title": "Jane at Acme",
            "contact_info": "jane@acme.com",
            "url": "https://zilo.pro",
            "snippet": "Looking for CRM",
        },
        owner_website="https://zilo.pro",
    )
    assert item["email"] == "jane@acme.com"
    assert not item.get("url")
    assert not _is_web_manual_item(item)


def test_map_category_email_review():
    from delegate.service import map_category

    assert map_category("review all latest email and write drafts") == "emails"
    assert map_category("check my gmail inbox and draft replies") == "emails"
    assert map_category("follow up cold leads") == "follow_ups"


def test_resolve_delegate_specialist_email():
    import asyncio

    from delegate.agent_bridge import resolve_delegate_specialist

    class FakeDb:
        pass

    agent = asyncio.run(
        resolve_delegate_specialist(
            FakeDb(), "user1", "review latest emails", "emails"
        )
    )
    assert agent in ("gmail", "microsoft")


def test_parse_agent_work_items_json():
    from delegate.agent_bridge import _parse_work_items_from_agent, normalize_agent_work_items

    result = {
        "text": '{"work_items": [{"label": "Jane", "email": "jane@x.com", "context": "Subject: Hi\\n\\nNeed help", "source": "email"}]}'
    }
    raw = _parse_work_items_from_agent(result)
    items = normalize_agent_work_items(raw, category="emails", limit=5)
    assert len(items) == 1
    assert items[0]["email"] == "jane@x.com"
    assert items[0]["reply_channel"] == "email"


def test_automation_diagnostics_handles_string_timestamps():
    import asyncio

    from delegate.service import get_automation_diagnostics

    class FakeCursor:
        def __init__(self, docs):
            self.docs = docs

        def sort(self, *args, **kwargs):
            return self

        async def to_list(self, n):
            return self.docs

    class FakeCol:
        def __init__(self, docs):
            self.docs = docs

        def find(self, q, sort=None):
            return FakeCursor(self.docs)

    class FakeDb:
        def __init__(self, docs):
            self.delegations = FakeCol(docs)

        def __getitem__(self, key):
            if key == "delegations":
                return self.delegations
            raise KeyError(key)

    docs = [
        {
            "_id": "sched-1",
            "user_id": "user-1",
            "mode": "schedule",
            "status": "scheduled",
            "task": "Weekly follow-up",
            "next_run_at": "2026-06-09T07:00:00",
            "last_run_at": "2026-06-02T07:00:00Z",
            "updated_at": datetime(2026, 6, 9, 6, 0, 0),
        }
    ]

    result = asyncio.run(get_automation_diagnostics(FakeDb(docs), "user-1"))
    row = result["automations"][0]
    assert row["next_run_at"] == "2026-06-09T07:00:00Z"
    assert row["last_run_at"] == "2026-06-02T07:00:00Z"
