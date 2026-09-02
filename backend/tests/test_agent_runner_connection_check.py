"""Unit tests for agent runner integration connection checks."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from assistant.agent_runner import run_agent_stream

@pytest.mark.anyio
async def test_agent_runner_shopify_not_connected():
    # Mock cfg to return shopify agent configs
    mock_cfg = {
        "id": "shopify_products",
        "system_prompt": "You manage shopify products.",
        "allowed_tools": ["list_shopify_products"],
        "model": "deepseek-v4-flash",
    }
    
    # Mock db and user
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    # Mock get_connection_status to return connected=False
    mock_status = {"connected": False}
    
    # Mock chat_with_tools to capture messages and return empty dict
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Shopify is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Shopify is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                # Run the runner generator to exhaustion
                async for _ in run_agent_stream(
                    agent_id="shopify_products",
                    task="List my products",
                    db=db,
                    user=user,
                ):
                    pass
                    
    # Verify that captured system prompt contains the CRITICAL SYSTEM NOTICE
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'shopify' is NOT connected for this user." in sys_msg
    assert "shopify_partner_create_store" in sys_msg

@pytest.mark.anyio
async def test_agent_runner_shopify_connected():
    # Mock cfg
    mock_cfg = {
        "id": "shopify_products",
        "system_prompt": "You manage shopify products.",
        "allowed_tools": ["list_shopify_products"],
        "model": "deepseek-v4-flash",
    }
    
    # Mock db and user
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    # Mock get_connection_status to return connected=True
    mock_status = {"connected": True}
    
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Here is the product list...", "raw_assistant_message": {"role": "assistant", "content": "Here is the product list..."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(
                    agent_id="shopify_products",
                    task="List my products",
                    db=db,
                    user=user,
                ):
                    pass
                    
    # Verify that captured system prompt does NOT contain the notice
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" not in sys_msg


@pytest.mark.anyio
async def test_agent_runner_whatsapp_not_connected():
    mock_cfg = {
        "id": "whatsapp",
        "system_prompt": "You send WhatsApp messages.",
        "allowed_tools": ["send_whatsapp_message"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    mock_status = {"connected": False, "state": "disconnected"}
    mock_service = AsyncMock()
    mock_service.get_instance_status = AsyncMock(return_value=mock_status)
    
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "WhatsApp is not connected.", "raw_assistant_message": {"role": "assistant", "content": "WhatsApp is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("whatsapp_service.get_whatsapp_service", return_value=mock_service):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(
                    agent_id="whatsapp",
                    task="Send WhatsApp message",
                    db=db,
                    user=user,
                ):
                    pass
                    
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'whatsapp' is NOT connected for this user." in sys_msg
    assert "Integrations page" in sys_msg


@pytest.mark.anyio
async def test_agent_runner_telegram_not_connected():
    mock_cfg = {
        "id": "telegram",
        "system_prompt": "You monitor Telegram.",
        "allowed_tools": ["telegram_status"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    # Mock database query find_one to return None (not connected)
    db.telegram_connections.find_one = AsyncMock(return_value=None)
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Telegram is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Telegram is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
            async for _ in run_agent_stream(
                agent_id="telegram",
                task="Telegram status",
                db=db,
                user=user,
            ):
                pass
                
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'telegram' is NOT connected for this user." in sys_msg
    assert "Integrations page" in sys_msg


@pytest.mark.anyio
async def test_agent_runner_meta_ads_not_configured():
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    with patch("meta_ads_service._is_configured", return_value=False):
        from assistant.tools import run_tool, ToolContext
        tool_ctx = ToolContext(db, user)
        res = await run_tool("list_meta_campaigns", tool_ctx, {})
        assert res.get("configured") is False
        assert "Meta Ads not configured" in res.get("error")


@pytest.mark.anyio
async def test_agent_runner_stripe_not_connected():
    mock_cfg = {
        "id": "stripe",
        "system_prompt": "You are a Stripe specialist.",
        "allowed_tools": ["get_stripe_balance"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Stripe is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Stripe is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(
                    agent_id="stripe",
                    task="Check my balance",
                    db=db,
                    user=user,
                ):
                    pass
                    
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'stripe' is NOT connected for this user." in sys_msg
    assert "Integrations page" in sys_msg


@pytest.mark.anyio
async def test_stripe_missing_tools_success():
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    mock_balance = {
        "available": [{"amount": 15000, "currency": "usd"}],
        "pending": [{"amount": 5000, "currency": "usd"}]
    }
    
    with patch("composio_service.composio_proxy", AsyncMock(return_value=mock_balance)):
        from assistant.tools import run_tool, ToolContext
        tool_ctx = ToolContext(db, user)
        res = await run_tool("get_stripe_balance", tool_ctx, {})
        assert res.get("available") == [{"amount": 150.0, "currency": "USD"}]
        assert res.get("pending") == [{"amount": 50.0, "currency": "USD"}]


@pytest.mark.anyio
async def test_agent_runner_klaviyo_not_connected():
    mock_cfg = {
        "id": "klaviyo",
        "system_prompt": "You are a Klaviyo specialist.",
        "allowed_tools": ["list_klaviyo_flows"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Klaviyo is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Klaviyo is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(
                    agent_id="klaviyo",
                    task="List my flows",
                    db=db,
                    user=user,
                ):
                    pass
                    
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'klaviyo' is NOT connected for this user." in sys_msg
    assert "Integrations page" in sys_msg


@pytest.mark.anyio
async def test_agent_runner_slack_not_connected():
    mock_cfg = {
        "id": "slack",
        "system_prompt": "You are a Slack specialist.",
        "allowed_tools": ["slack_list_channels"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Slack is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Slack is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(
                    agent_id="slack",
                    task="List my channels",
                    db=db,
                    user=user,
                ):
                    pass
                    
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'slack' is NOT connected for this user." in sys_msg
    assert "Integrations page" in sys_msg


@pytest.mark.anyio
async def test_agent_runner_microsoft_not_connected():
    mock_cfg = {
        "id": "microsoft",
        "system_prompt": "You are a Microsoft specialist.",
        "allowed_tools": ["outlook_list_messages"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Outlook is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Outlook is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="microsoft", task="Check inbox", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'outlook' is NOT connected for this user." in sys_msg


@pytest.mark.anyio
async def test_agent_runner_google_sheets_not_connected():
    mock_cfg = {
        "id": "google_sheets",
        "system_prompt": "You are a Sheets specialist.",
        "allowed_tools": ["sheets_list"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Sheets is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Sheets is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="google_sheets", task="List sheets", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'googlesheets' is NOT connected for this user." in sys_msg


@pytest.mark.anyio
async def test_agent_runner_notion_not_connected():
    mock_cfg = {
        "id": "notion",
        "system_prompt": "You are a Notion specialist.",
        "allowed_tools": ["notion_search"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Notion is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Notion is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="notion", task="Search pages", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'notion' is NOT connected for this user." in sys_msg


@pytest.mark.anyio
async def test_agent_runner_google_calendar_not_connected():
    mock_cfg = {
        "id": "google_calendar",
        "system_prompt": "You are a Calendar specialist.",
        "allowed_tools": ["list_calendar_events"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Calendar is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Calendar is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="google_calendar", task="List events", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'googlecalendar' is NOT connected for this user." in sys_msg


@pytest.mark.anyio
async def test_agent_runner_invoices_not_connected_stripe():
    mock_cfg = {
        "id": "invoices",
        "system_prompt": "You are an invoices specialist.",
        "allowed_tools": ["list_stripe_invoices"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Stripe is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Stripe is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="invoices", task="List Stripe invoices", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'stripe' is NOT connected for this user." in sys_msg


@pytest.mark.anyio
async def test_agent_runner_payments_not_connected_stripe():
    mock_cfg = {
        "id": "payments",
        "system_prompt": "You are a payments specialist.",
        "allowed_tools": ["list_stripe_payments"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False}
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "Stripe is not connected.", "raw_assistant_message": {"role": "assistant", "content": "Stripe is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("composio_service.get_connection_status", AsyncMock(return_value=mock_status)):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="payments", task="List Stripe payments", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'stripe' is NOT connected for this user." in sys_msg


@pytest.mark.anyio
async def test_agent_runner_messages_not_connected_whatsapp():
    mock_cfg = {
        "id": "messages",
        "system_prompt": "You send WhatsApp messages.",
        "allowed_tools": ["send_whatsapp_message"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False, "state": "disconnected"}
    mock_service = AsyncMock()
    mock_service.get_instance_status = AsyncMock(return_value=mock_status)
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "WhatsApp is not connected.", "raw_assistant_message": {"role": "assistant", "content": "WhatsApp is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("whatsapp_service.get_whatsapp_service", return_value=mock_service):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="messages", task="Send message", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'whatsapp' is NOT connected for this user." in sys_msg


@pytest.mark.anyio
async def test_agent_runner_broadcasts_not_connected_whatsapp():
    mock_cfg = {
        "id": "broadcasts",
        "system_prompt": "You send broadcast messages.",
        "allowed_tools": ["create_broadcast"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False, "state": "disconnected"}
    mock_service = AsyncMock()
    mock_service.get_instance_status = AsyncMock(return_value=mock_status)
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "WhatsApp is not connected.", "raw_assistant_message": {"role": "assistant", "content": "WhatsApp is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("whatsapp_service.get_whatsapp_service", return_value=mock_service):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="broadcasts", task="Send broadcast", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'whatsapp' is NOT connected for this user." in sys_msg


@pytest.mark.anyio
async def test_agent_runner_nps_not_connected_whatsapp():
    mock_cfg = {
        "id": "nps",
        "system_prompt": "You collect NPS feedback.",
        "allowed_tools": ["send_whatsapp_message"],
        "model": "deepseek-v4-flash",
    }
    db = AsyncMock()
    user = {"_id": "user-123", "business_id": "biz-123"}
    mock_status = {"connected": False, "state": "disconnected"}
    mock_service = AsyncMock()
    mock_service.get_instance_status = AsyncMock(return_value=mock_status)
    captured_messages = []
    async def fake_chat_with_tools(messages, tools, model_id, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        return {"content": "WhatsApp is not connected.", "raw_assistant_message": {"role": "assistant", "content": "WhatsApp is not connected."}}
        
    with patch("assistant.agents.get_agent_config", return_value=mock_cfg):
        with patch("whatsapp_service.get_whatsapp_service", return_value=mock_service):
            with patch("assistant.models.chat_with_tools", fake_chat_with_tools):
                async for _ in run_agent_stream(agent_id="nps", task="Collect feedback", db=db, user=user):
                    pass
    assert len(captured_messages) > 0
    sys_msg = captured_messages[0]["content"]
    assert "⚠️ CRITICAL SYSTEM NOTICE:" in sys_msg
    assert "The required integration 'whatsapp' is NOT connected for this user." in sys_msg


def test_smart_notes_tools_allowed_for_document_agent():
    from assistant.agents import get_agent_config
    cfg = get_agent_config("document")
    allowed = cfg.get("allowed_tools")
    assert allowed is not None
    assert "search_meeting_notes" in allowed
    assert "list_meeting_notes" in allowed







