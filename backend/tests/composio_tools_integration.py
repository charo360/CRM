"""Integration-style tests for Composio-first Stripe / Klaviyo / Slack helpers and assistant tools.

Patches network I/O (execute_action, composio_proxy). Run from backend:

    python -m pytest tests/composio_tools_integration.py -v

Optional live smoke (skipped unless COMPOSIO_LIVE_BUSINESS_ID is set): hits Composio with real credentials.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from assistant.tools import ToolContext, run_tool
from composio_service import (
    klaviyo_flows_via_composio_or_proxy,
    klaviyo_metrics_via_composio_or_proxy,
    slack_auth_test_via_composio_or_proxy,
    slack_conversations_list_via_composio_or_proxy,
    slack_post_message_via_composio_or_proxy,
    stripe_invoices_via_composio_or_proxy,
    stripe_payment_intents_via_composio_or_proxy,
)


def _ctx() -> ToolContext:
    return ToolContext(None, {"_id": "user-1", "business_id": "biz-1"})


def _pi_sample() -> Dict[str, Any]:
    return {
        "id": "pi_test",
        "amount": 2500,
        "currency": "usd",
        "status": "succeeded",
        "description": "Test",
        "customer": "cus_x",
        "created": 1700000000,
    }


def test_stripe_payment_intents_uses_composio_data():
    async def _run():
        exec_mock = AsyncMock(
            return_value={"success": True, "data": {"data": [_pi_sample()], "has_more": False}}
        )
        proxy_mock = AsyncMock(return_value={"data": [_pi_sample()]})
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", proxy_mock):
                out = await stripe_payment_intents_via_composio_or_proxy("biz-1", limit=10)
        assert out["data"][0]["id"] == "pi_test"
        exec_mock.assert_awaited_once()
        proxy_mock.assert_not_called()

    asyncio.run(_run())


def test_stripe_payment_intents_falls_back_to_proxy():
    async def _run():
        exec_mock = AsyncMock(return_value={"success": True, "data": {}})
        proxy_mock = AsyncMock(return_value={"data": [_pi_sample()]})
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", proxy_mock):
                out = await stripe_payment_intents_via_composio_or_proxy("biz-1", limit=5)
        proxy_mock.assert_awaited_once()
        assert proxy_mock.await_args.args[0] == "biz-1"
        assert proxy_mock.await_args.args[2] == "GET"
        assert "/payment_intents" in proxy_mock.await_args.args[3]
        assert out["data"][0]["status"] == "succeeded"

    asyncio.run(_run())


def test_stripe_invoices_composio_path():
    async def _run():
        inv = {
            "id": "in_1",
            "number": "A-1",
            "customer_email": "a@b.co",
            "amount_due": 0,
            "amount_paid": 1000,
            "currency": "usd",
            "status": "paid",
            "due_date": None,
            "description": None,
        }
        exec_mock = AsyncMock(return_value={"success": True, "data": {"data": [inv]}})
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", AsyncMock()):
                out = await stripe_invoices_via_composio_or_proxy("biz-1", limit=20, status="paid")
        assert out["data"][0]["id"] == "in_1"

    asyncio.run(_run())


def test_klaviyo_flows_passes_filter_for_live():
    async def _run():
        exec_mock = AsyncMock(
            return_value={
                "success": True,
                "data": {"data": [{"id": "f1", "attributes": {"name": "Welcome", "status": "live"}}]},
            }
        )
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", AsyncMock()):
                out = await klaviyo_flows_via_composio_or_proxy("biz-1", status="live")
        kw = exec_mock.await_args.args[2]
        assert kw.get("filter") == 'equals(status,"live")'
        assert len(out["data"]) == 1

    asyncio.run(_run())


def test_klaviyo_metrics_slices_to_limit():
    async def _run():
        metrics = [{"id": f"m{i}", "attributes": {"name": f"M{i}"}} for i in range(10)]
        exec_mock = AsyncMock(return_value={"success": True, "data": {"data": metrics}})
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", AsyncMock()):
                out = await klaviyo_metrics_via_composio_or_proxy("biz-1", limit=3)
        assert len(out["data"]) == 3
        assert out["data"][0]["id"] == "m0"

    asyncio.run(_run())


def test_slack_auth_composio_inner():
    async def _run():
        exec_mock = AsyncMock(
            return_value={
                "success": True,
                "data": {"ok": True, "team": "T", "team_id": "T1", "url": "https://x.slack.com/"},
            }
        )
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", AsyncMock()):
                out = await slack_auth_test_via_composio_or_proxy("biz-1")
        assert out.get("ok") is True
        assert out.get("team_id") == "T1"

    asyncio.run(_run())


def test_slack_conversations_nested_channels():
    async def _run():
        ch = {"id": "C1", "name": "general", "is_private": False, "is_archived": False}
        exec_mock = AsyncMock(
            return_value={"success": True, "data": {"data": {"channels": [ch]}}}
        )
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", AsyncMock()):
                out = await slack_conversations_list_via_composio_or_proxy(
                    "biz-1",
                    types="public_channel",
                    limit=200,
                    exclude_archived=True,
                )
        assert out["channels"][0]["id"] == "C1"

    asyncio.run(_run())


def test_slack_post_composio_path():
    async def _run():
        exec_mock = AsyncMock(
            return_value={"success": True, "data": {"ok": True, "channel": "C1", "ts": "1.2"}}
        )
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", AsyncMock()):
                out = await slack_post_message_via_composio_or_proxy(
                    "biz-1", channel="C1", text="hi", thread_ts=None
                )
        assert out.get("ts") == "1.2"

    asyncio.run(_run())


def test_list_stripe_payments_tool_filters_status():
    async def _run():
        exec_mock = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "data": [
                        {**_pi_sample(), "id": "pi_ok", "status": "succeeded"},
                        {**_pi_sample(), "id": "pi_pending", "status": "requires_payment_method"},
                    ]
                },
            }
        )
        with patch("composio_service.execute_action", exec_mock):
            with patch("composio_service.composio_proxy", AsyncMock()):
                res = await run_tool(
                    "list_stripe_payments",
                    _ctx(),
                    {"limit": 10, "status": "succeeded"},
                )
        assert "error" not in res
        assert res["count"] == 1
        assert res["payments"][0]["id"] == "pi_ok"

    asyncio.run(_run())


def test_slack_list_channels_tool_paginates():
    async def _run():
        page1 = {
            "ok": True,
            "channels": [
                {"id": "C1", "name": "a", "is_private": False, "is_archived": False},
            ],
            "response_metadata": {"next_cursor": "cur1"},
        }
        page2 = {"ok": True, "channels": [], "response_metadata": {}}

        async def fake_conv_list(uid, *, types, limit, exclude_archived, cursor=None):
            assert uid == "biz-1"
            if cursor is None:
                return page1
            if cursor == "cur1":
                return page2
            raise AssertionError(f"unexpected cursor {cursor!r}")

        with patch(
            "composio_service.slack_conversations_list_via_composio_or_proxy",
            side_effect=fake_conv_list,
        ):
            res = await run_tool(
                "slack_list_channels",
                _ctx(),
                {"include_private": False, "include_archived": False, "page_limit": 5},
            )
        assert "error" not in res
        assert res["total"] == 1
        assert res["channels"][0]["name"] == "a"

    asyncio.run(_run())


_live_biz = os.environ.get("COMPOSIO_LIVE_BUSINESS_ID", "").strip()


@pytest.mark.skipif(not _live_biz, reason="Set COMPOSIO_LIVE_BUSINESS_ID for live Composio smoke test")
def test_live_slack_auth_smoke():
    async def _run():
        out = await slack_auth_test_via_composio_or_proxy(_live_biz)
        assert isinstance(out, dict)

    asyncio.run(_run())
