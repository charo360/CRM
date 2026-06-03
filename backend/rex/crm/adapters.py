"""
Mongo-backed CRM adapters for onboarding scan + live counts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from rex.onboarding.scanner import (
    ConversationStore,
    DealStore,
    EmailStore,
    InvoiceStore,
    LiveDataScanner,
    ScoutStore,
    _run_async,
)


def _business_id(user: dict) -> str:
    return str(user.get("business_id") or user.get("_id") or "")


class MongoInvoiceStore:
    def __init__(self, db: Any, uid: str) -> None:
        self._db = db
        self._uid = uid

    async def _count_overdue(self, days: int) -> int:
        now = datetime.utcnow()
        cutoff = now - timedelta(days=max(days, 7))
        return await self._db.invoices.count_documents({
            "user_id": self._uid,
            "status": {"$in": ["unpaid", "Pending", "overdue", "Overdue"]},
            "created_at": {"$lt": cutoff},
        })

    def count_overdue(self, days: int = 0) -> int:
        return int(_run_async(self._count_overdue(days)) or 0)


class MongoConversationStore:
    def __init__(self, db: Any, uid: str) -> None:
        self._db = db
        self._uid = uid

    async def _count_cold(self, days: int) -> int:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return await self._db.customers.count_documents({
            "user_id": self._uid,
            "is_customer": True,
            "$or": [
                {"last_contacted": {"$lt": cutoff}},
                {"last_contacted": {"$exists": False}},
            ],
        })

    def count_cold(self, days: int = 7) -> int:
        return int(_run_async(self._count_cold(days)) or 0)


class MongoDealStore:
    def __init__(self, db: Any, uid: str) -> None:
        self._db = db
        self._uid = uid

    async def _count_stalled(self, days: int) -> int:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return await self._db.customers.count_documents({
            "user_id": self._uid,
            "pipeline_stage": {"$exists": True, "$nin": ["", "won", "lost", "closed"]},
            "$or": [
                {"pipeline_updated_at": {"$lt": cutoff}},
                {"pipeline_updated_at": {"$exists": False}, "last_contacted": {"$lt": cutoff}},
            ],
        })

    def count_stalled(self, days: int = 7) -> int:
        return int(_run_async(self._count_stalled(days)) or 0)


class MongoEmailStore:
    def __init__(self, db: Any, uid: str) -> None:
        self._db = db
        self._uid = uid

    async def _count_unread(self) -> int:
        return await self._db.email_messages.count_documents({
            "user_id": self._uid,
            "is_read": {"$ne": True},
        })

    def count_unread(self) -> int:
        return int(_run_async(self._count_unread()) or 0)


class MongoScoutStore:
    def __init__(self, db: Any, uid: str) -> None:
        self._db = db
        self._uid = uid

    async def _count_recent(self, days: int) -> int:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return await self._db.action_mode_opportunities.count_documents({
            "user_id": self._uid,
            "created_at": {"$gte": cutoff},
        })

    def count_recent_opportunities(self, days: int = 7) -> int:
        return int(_run_async(self._count_recent(days)) or 0)


def make_live_scanner(db: Any, user: dict) -> LiveDataScanner:
    uid = _business_id(user)
    return LiveDataScanner(
        invoices=MongoInvoiceStore(db, uid),
        conversations=MongoConversationStore(db, uid),
        deals=MongoDealStore(db, uid),
        emails=MongoEmailStore(db, uid),
        scout=MongoScoutStore(db, uid),
    )
