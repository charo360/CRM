"""
Tests for Phase 1 (Compliance & Audit Hardening) and Phase 2 (Reliability & Resilience):
1. Audit logging to MongoDB
2. /admin/audit/export endpoint
3. tenacity retry and streaming fallback chain
4. Dead Letter Queue (DLQ) operations
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from datetime import datetime

class AsyncIterator:
    def __init__(self, items):
        self.iter = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.iter)
        except StopIteration:
            raise StopAsyncIteration

class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __aiter__(self):
        return AsyncIterator(self.docs)

    async def to_list(self, *args, **kwargs):
        return self.docs

# ── Compliance Tests (Phase 1) ────────────────────────────────────────────────
@pytest.mark.anyio
async def test_write_audit_event():
    from assistant.audit_service import write_audit_event
    
    db_mock = MagicMock()
    db_mock.assistant_audit_log.insert_one = AsyncMock()
    
    await write_audit_event(
        db=db_mock,
        user_id="user-1",
        actor_id="actor-1",
        event_type="data_read",
        payload={"tool": "get_customer", "severity": "info"}
    )
    
    db_mock.assistant_audit_log.insert_one.assert_called_once()
    args = db_mock.assistant_audit_log.insert_one.call_args[0][0]
    assert args["user_id"] == "user-1"
    assert args["event_type"] == "data_read"
    assert args["severity"] == "info"
    assert "created_at" in args


@pytest.mark.anyio
async def test_audit_export_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from assistant.routes import _mk_router
    
    app = FastAPI()
    db_mock = MagicMock()
    
    # Mock data to stream
    mock_event = {
        "_id": "event-1",
        "user_id": "user-1",
        "event_type": "data_write",
        "severity": "write",
        "created_at": datetime.utcnow()
    }
    
    mock_cursor = MockCursor([mock_event])
    db_mock.assistant_audit_log.find.return_value = mock_cursor
    
    async def mock_get_current_user():
        return {"_id": "user-1", "role": "admin"}
        
    router = _mk_router(db_mock, mock_get_current_user)
    app.include_router(router)
    
    try:
        from server import get_current_user as real_get_current_user
        app.dependency_overrides[real_get_current_user] = mock_get_current_user
    except Exception:
        pass
    app.dependency_overrides[mock_get_current_user] = mock_get_current_user
    
    client = TestClient(app)
    response = client.get("/assistant/admin/audit/export?start=2026-01-01&end=2026-12-31")
    assert response.status_code == 200
    lines = response.text.strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["user_id"] == "user-1"
    assert data["event_type"] == "data_write"


# ── Reliability & Resilience Tests (Phase 2) ──────────────────────────────────
@pytest.mark.anyio
async def test_tenacity_retry_on_openai_failure():
    from assistant.models import _call_openai_compatible
    import httpx
    
    mock_client = MagicMock()
    # First call raises timeout, second call succeeds
    mock_client.post = AsyncMock(side_effect=[
        httpx.TimeoutException("Timeout!"),
        MagicMock(status_code=200, json=lambda: {
            "choices": [{"message": {"role": "assistant", "content": "Success!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        })
    ])
    
    cfg = {"provider": "openai", "model": "gpt-4o-mini"}
    
    with patch("assistant.models._get_http_client", return_value=mock_client), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}), \
         patch("logging.getLogger") as mock_get_logger:
         
        mock_log = MagicMock()
        mock_get_logger.return_value = mock_log
        
        res = await _call_openai_compatible(cfg, [{"role": "user", "content": "hi"}], [], 0.2, 30.0)
        assert res["content"] == "Success!"
        assert mock_client.post.call_count == 2


@pytest.mark.anyio
async def test_streaming_fallback_chain():
    from assistant.models import stream_reply
    import httpx
    
    # Primary deepseek-chat fails, fallback to openai gpt-4o-mini is triggered
    mock_client = MagicMock()
    
    # We mock get_http_client in the fallback. The stream primary fails (timeout exception),
    # which makes it fall back to chat_with_tools on alternative configurations.
    # We mock chat_with_tools to return a valid response.
    async def mock_chat_with_tools(*args, **kwargs):
        return {"content": "Fallback text success"}
        
    with patch("assistant.models._stream_openai_compatible", side_effect=httpx.TimeoutException("Timeout!")), \
         patch("assistant.models.chat_with_tools", side_effect=mock_chat_with_tools), \
         patch.dict("os.environ", {
             "DEEPSEEK_API_KEY": "fake-ds-key",
             "OPENAI_API_KEY": "fake-oai-key"
         }):
         
        chunks = []
        async for chunk in stream_reply(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            model_id="deepseek-v4-pro"
        ):
            chunks.append(chunk)
            
        assert "".join(chunks) == "Fallback text success"


@pytest.mark.anyio
async def test_dead_letter_queue_operations():
    from rex.integrations.dead_letter import enqueue_dead_letter, retry_dead_letter_jobs
    
    db_mock = MagicMock()
    db_mock.dead_letter_queue.insert_one = AsyncMock()
    
    # 1. Enqueue job
    await enqueue_dead_letter(
        db=db_mock,
        queue="queue:broadcast",
        job_payload={"broadcast_id": "b1"},
        error="Connection refused",
        attempt=1
    )
    db_mock.dead_letter_queue.insert_one.assert_called_once()
    
    # 2. Retry dead letter jobs
    mock_job = {
        "_id": "job-1",
        "queue": "queue:broadcast",
        "payload": {"broadcast_id": "b1"},
        "attempt": 1,
    }
    mock_cursor = MockCursor([mock_job])
    db_mock.dead_letter_queue.find.return_value = mock_cursor
    db_mock.dead_letter_queue.update_one = AsyncMock()
    
    mock_redis = MagicMock()
    mock_redis.enqueue_job = AsyncMock(return_value=True)
    
    await retry_dead_letter_jobs(db_mock, mock_redis, "queue:broadcast", limit=10)
    mock_redis.enqueue_job.assert_called_once()
    db_mock.dead_letter_queue.update_one.assert_called_once()
