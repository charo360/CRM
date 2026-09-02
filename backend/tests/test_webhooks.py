"""Tests for the outbound webhook system (Phase 4)."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from webhooks.schemas import (
    BroadcastSentEvent,
    CustomerCreatedEvent,
    WebhookEnvelope,
)
from webhooks.signing import sign_payload, verify_signature


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestWebhookSchemas:
    def test_broadcast_event_has_required_fields(self):
        evt = BroadcastSentEvent.create(
            tenant_id="t1",
            broadcast_id="b1",
            recipient_count=100,
            message="Hello world",
        )
        assert evt.event == "broadcast.sent"
        assert evt.tenant_id == "t1"
        assert evt.data["broadcast_id"] == "b1"
        assert evt.data["recipient_count"] == 100
        assert evt.timestamp  # non-empty
        assert evt.delivery_id is None  # set later by worker

    def test_message_preview_truncated_to_120(self):
        long_msg = "x" * 200
        evt = BroadcastSentEvent.create(
            tenant_id="t1", broadcast_id="b1", recipient_count=1, message=long_msg,
        )
        assert len(evt.data["message_preview"]) == 120

    def test_customer_event_fields(self):
        evt = CustomerCreatedEvent.create(
            tenant_id="t2", customer_id="c1", name="Alice", phone="+254700000000"
        )
        assert evt.event == "customer.created"
        assert evt.data["name"] == "Alice"

    def test_envelope_serialization(self):
        evt = CustomerCreatedEvent.create(
            tenant_id="t2", customer_id="c1", name="Alice", phone="+254700000000"
        )
        d = evt.model_dump()
        assert d["event"] == "customer.created"
        assert "data" in d
        # Must be JSON-serializable
        json.dumps(d)


# ── Signing tests ─────────────────────────────────────────────────────────────

class TestWebhookSigning:
    def test_sign_returns_sha256_prefix(self):
        sig, ts = sign_payload("mysecret", '{"foo":"bar"}')
        assert sig.startswith("sha256=")
        assert len(sig) > 10

    def test_sign_deterministic_with_fixed_timestamp(self):
        body = '{"x":1}'
        sig1, _ = sign_payload("secret", body, timestamp=1000)
        sig2, _ = sign_payload("secret", body, timestamp=1000)
        assert sig1 == sig2

    def test_sign_differs_with_different_secrets(self):
        body = '{"x":1}'
        sig1, _ = sign_payload("secret1", body, timestamp=1000)
        sig2, _ = sign_payload("secret2", body, timestamp=1000)
        assert sig1 != sig2

    def test_verify_valid_signature(self):
        secret = "topsecret"
        body = '{"event":"test"}'
        sig, ts = sign_payload(secret, body, timestamp=int(time.time()))
        assert verify_signature(secret, body, sig, ts, max_age_sec=60)

    def test_verify_rejects_stale_timestamp(self):
        secret = "topsecret"
        body = '{"event":"test"}'
        old_ts = int(time.time()) - 400  # 400 s ago
        sig, _ = sign_payload(secret, body, timestamp=old_ts)
        assert not verify_signature(secret, body, sig, old_ts, max_age_sec=300)

    def test_verify_rejects_wrong_signature(self):
        secret = "topsecret"
        body = '{"event":"test"}'
        ts = int(time.time())
        assert not verify_signature(secret, body, "sha256=badhash", ts, max_age_sec=60)

    def test_verify_rejects_tampered_body(self):
        secret = "topsecret"
        body = '{"event":"test"}'
        sig, ts = sign_payload(secret, body, timestamp=int(time.time()))
        tampered = '{"event":"tampered"}'
        assert not verify_signature(secret, tampered, sig, ts, max_age_sec=60)


# ── Delivery tests ────────────────────────────────────────────────────────────

def _make_mock_db(doc=None):
    """Create a minimal async mock MongoDB database."""
    col = MagicMock()
    col.insert_one = AsyncMock()
    col.find_one = AsyncMock(return_value=doc)
    col.update_one = AsyncMock()

    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    db.webhook_deliveries = col
    return db, col


@pytest.mark.anyio
async def test_enqueue_inserts_doc():
    db, col = _make_mock_db()
    evt = BroadcastSentEvent.create(
        tenant_id="t1", broadcast_id="b1", recipient_count=5, message="hi"
    )

    with patch("webhooks.delivery.enqueue_job", new=AsyncMock(return_value=True)):
        from webhooks.delivery import enqueue_webhook
        delivery_id = await enqueue_webhook(
            db, "t1", evt, endpoint_url="https://example.com/hook", secret="s3cr3t"
        )

    assert delivery_id
    col.insert_one.assert_awaited_once()
    inserted_doc = col.insert_one.call_args[0][0]
    assert inserted_doc["status"] == "pending"
    assert inserted_doc["event"] == "broadcast.sent"


@pytest.mark.anyio
async def test_deliver_one_success():
    doc = {
        "_id": "d1",
        "tenant_id": "t1",
        "endpoint_url": "https://example.com/hook",
        "secret": "s3cr3t",
        "payload": {
            "event": "broadcast.sent",
            "tenant_id": "t1",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "data": {"broadcast_id": "b1", "recipient_count": 5, "message_preview": "hi"},
            "delivery_id": "d1",
        },
        "status": "pending",
        "attempts": 0,
    }
    db, col = _make_mock_db(doc=doc)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from webhooks.delivery import deliver_one
        result = await deliver_one(db, "d1")

    assert result is True
    col.update_one.assert_awaited_once()
    update_call = col.update_one.call_args[0][1]
    assert update_call["$set"]["status"] == "delivered"


@pytest.mark.anyio
async def test_deliver_one_retries_on_failure():
    doc = {
        "_id": "d1",
        "tenant_id": "t1",
        "endpoint_url": "https://example.com/hook",
        "secret": "s3cr3t",
        "payload": {
            "event": "broadcast.sent",
            "tenant_id": "t1",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "data": {"broadcast_id": "b1", "recipient_count": 5, "message_preview": "hi"},
            "delivery_id": "d1",
        },
        "status": "pending",
        "attempts": 0,
    }
    db, col = _make_mock_db(doc=doc)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_cls.return_value = mock_client

        from webhooks.delivery import deliver_one
        result = await deliver_one(db, "d1")

    assert result is False
    col.update_one.assert_awaited_once()
    update_call = col.update_one.call_args[0][1]
    assert update_call["$set"]["status"] == "failed"
    assert "next_retry_at" in update_call["$set"]


@pytest.mark.anyio
async def test_deliver_marks_dead_after_max_attempts():
    from webhooks.delivery import MAX_ATTEMPTS
    doc = {
        "_id": "d1",
        "tenant_id": "t1",
        "endpoint_url": "https://example.com/hook",
        "secret": "s3cr3t",
        "payload": {
            "event": "broadcast.sent",
            "tenant_id": "t1",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "data": {"broadcast_id": "b1", "recipient_count": 5, "message_preview": "hi"},
            "delivery_id": "d1",
        },
        "status": "failed",
        "attempts": MAX_ATTEMPTS - 1,
    }
    db, col = _make_mock_db(doc=doc)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))
        mock_client_cls.return_value = mock_client

        from webhooks.delivery import deliver_one
        result = await deliver_one(db, "d1")

    assert result is False
    update_call = col.update_one.call_args[0][1]
    assert update_call["$set"]["status"] == "dead"
