"""
Tests for Phase 3 (Observability & Cost Control):
1. Prompt token estimation using tiktoken
2. Quota budget tracking and enforcement
3. /assistant/usage API endpoint
4. SLA latency span logging
"""
from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from datetime import datetime

# ── Helper for Mocking Redis ──────────────────────────────────────────────────
class MockRedis:
    def __init__(self, data=None):
        self.data = data or {}

    async def get(self, key):
        return self.data.get(key)

    async def incrby(self, key, amount):
        val = int(self.data.get(key) or 0) + amount
        self.data[key] = str(val)
        return val

    async def expire(self, key, ttl):
        return True


# ── Tests for tiktoken prompt token estimation ──────────────────────────────
@pytest.mark.anyio
async def test_estimate_prompt_tokens():
    from assistant.orchestrator import _estimate_prompt_tokens
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I am fine, thank you."}
            ]
        }
    ]
    
    tokens = _estimate_prompt_tokens(messages)
    assert tokens > 10
    assert isinstance(tokens, int)


# ── Tests for quota budget check & usage summary ───────────────────────────
@pytest.mark.anyio
async def test_quota_service_checks():
    from assistant.quota_service import check_quota, get_usage_summary
    from redis_client import _k
    
    month = datetime.utcnow().strftime("%Y-%m")
    
    # 1. Under limits for free plan
    redis_mock = MockRedis({_k(f"quota:tokens:biz-1:{month}"): "50000"})
    res = await check_quota(redis_mock, "biz-1", plan="free")
    assert res["allowed"] is True
    assert res["used"] == 50000
    assert res["limit"] == 100000
    assert res["remaining"] == 50000
    assert res["pct_used"] == 50.0

    # 2. Exceeded limits for free plan
    redis_mock = MockRedis({_k(f"quota:tokens:biz-1:{month}"): "120000"})
    res = await check_quota(redis_mock, "biz-1", plan="free")
    assert res["allowed"] is False
    assert res["used"] == 120000
    assert res["remaining"] == 0
    assert res["pct_used"] == 120.0

    # 3. Starter plan checks
    redis_mock = MockRedis({_k(f"quota:tokens:biz-2:{month}"): "300000"})
    res = await check_quota(redis_mock, "biz-2", plan="starter")
    assert res["allowed"] is True
    assert res["limit"] == 500000
    assert res["pct_used"] == 60.0

    # 4. Pro plan is unlimited
    redis_mock = MockRedis({_k(f"quota:tokens:biz-3:{month}"): "1500000"})
    res = await check_quota(redis_mock, "biz-3", plan="pro")
    assert res["allowed"] is True
    assert res["limit"] is None
    assert res["remaining"] is None

    # 5. Usage summary cost estimation
    redis_mock = MockRedis({_k(f"quota:tokens:biz-1:{month}"): "10000"})
    summary = await get_usage_summary(redis_mock, "biz-1", plan="free", model_provider="deepseek")
    assert summary["estimated_cost_usd"] == 0.0014 # 10k * 0.00014
    
    summary_openai = await get_usage_summary(redis_mock, "biz-1", plan="starter", model_provider="openai")
    assert summary_openai["estimated_cost_usd"] == 0.0150 # 10k * 0.0150


# ── Tests for assistant usage REST API ─────────────────────────────────────
@pytest.mark.anyio
async def test_assistant_usage_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from assistant.routes import _mk_router
    import redis_client
    
    app = FastAPI()
    db_mock = MagicMock()
    
    # Simple auth mock returning custom user
    async def mock_get_current_user():
        return {
            "_id": "user-123",
            "business_id": "biz-123",
            "plan": "starter",
        }
        
    router = _mk_router(db_mock, mock_get_current_user)
    app.include_router(router)
    
    try:
        from server import get_current_user as real_get_current_user
        app.dependency_overrides[real_get_current_user] = mock_get_current_user
    except Exception:
        pass
    app.dependency_overrides[mock_get_current_user] = mock_get_current_user
    
    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value="100000")
    
    # Manually replace the function to ensure thread-safety and scope propagation
    original_get_redis = redis_client.get_redis
    redis_client.get_redis = AsyncMock(return_value=redis_mock)
    
    try:
        with patch.dict("os.environ", {"ASSISTANT_DEFAULT_MODEL": "gpt-4o-mini"}):
            client = TestClient(app)
            response = client.get("/assistant/usage")
            assert response.status_code == 200
            data = response.json()
            assert data["used"] == 100000
            assert data["plan"] == "starter"
            assert data["limit"] == 500000
            assert data["estimated_cost_usd"] > 0
    finally:
        redis_client.get_redis = original_get_redis


# ── Tests for LLM SLA latency span logging ───────────────────────────────
@pytest.mark.anyio
async def test_llm_sla_latency_span_logging():
    from assistant.models import _call_openai_compatible
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "Hello human!"},
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 5
        }
    }
    
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    
    cfg = {"provider": "openai", "model": "gpt-4o-mini", "id": "oai-mini"}
    
    # Spy on python logging
    with patch("assistant.models._get_http_client", return_value=mock_client), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}), \
         patch("logging.getLogger") as mock_get_logger:
        
        mock_log = MagicMock()
        mock_get_logger.return_value = mock_log
        
        res = await _call_openai_compatible(cfg, [{"role": "user", "content": "hi"}], [], 0.2, 30.0)
        
        # Verify the logger for llm_call_log was requested and logged to
        mock_get_logger.assert_any_call("llm_call_log")
        assert mock_log.info.called
        
        # Verify the structure of the JSON logged
        logged_str = mock_log.info.call_args[0][0]
        logged_data = json.loads(logged_str)
        assert logged_data["provider"] == "openai"
        assert logged_data["model"] == "gpt-4o-mini"
        assert logged_data["prompt_tokens"] == 15
        assert logged_data["completion_tokens"] == 5
        assert "latency_ms" in logged_data
