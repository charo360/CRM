"""
Audit Service — central service for compliance and audit logging.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

READ_AUDIT_TOOLS = frozenset({
    "list_customers",
    "get_customer",
    "get_analytics_summary",
    "get_top_customers",
    "search_meeting_notes",
    "retrieve_knowledge",
    "search_notebook",
    "list_orders",
    "get_sales_pipeline",
})

async def write_audit_event(
    db: Any,
    user_id: str,
    actor_id: str,
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    """
    Write an audit log event to MongoDB.
    
    Fields in payload can include:
    - severity: str ('info', 'write', 'destructive')
    - tool: Optional[str]
    - arguments: Optional[Dict[str, Any]]
    - result: Optional[Any]
    - success: Optional[bool]
    - agent: Optional[str]
    - conversation_id: Optional[str]
    """
    try:
        event = {
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "actor_id": actor_id,
            "event_type": event_type,
            "severity": payload.get("severity", "info"),
            "tool": payload.get("tool"),
            "arguments": payload.get("arguments"),
            "result": payload.get("result"),
            "success": payload.get("success", True),
            "agent": payload.get("agent"),
            "conversation_id": payload.get("conversation_id"),
            "created_at": datetime.utcnow(),
        }
        await db.assistant_audit_log.insert_one(event)
    except Exception as e:
        logger.error(
            "[assistant.audit] CRITICAL — audit write failed: %s. user_id=%s actor_id=%s event_type=%s payload=%r",
            e, user_id, actor_id, event_type, payload, exc_info=True
        )
