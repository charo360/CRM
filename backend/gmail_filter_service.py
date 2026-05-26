"""
Gmail Filter Management Service

Provides programmatic control over Gmail filters using the Gmail API via Composio.
Enables automated filter creation, listing, updating, and deletion.

Features:
- Create filters with multiple criteria (from, subject, query, size, attachments)
- Auto-archive newsletters and promotional emails
- Batch filter creation from templates
- List and manage existing filters
- AI agent integration for intelligent filter suggestions
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── Predefined Filter Templates ────────────────────────────────────────────

NEWSLETTER_SENDERS = [
    "customerservice@exct.stansberryresearch.com",
    "info@exct.chaikinanalytics.com",
    "stocknewsletter@mail.beehiiv.com",
    "info@analyticsindiamag.com",
    "newsletters@analystratings.net",
    "partners@analystratings.net",
    "newsmax@latest.newsmax.com",
    "team@cmail.bark.com",
]


# ── Core Filter Operations ─────────────────────────────────────────────────

async def create_gmail_filter(
    user_id: str,
    criteria: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a Gmail filter using Composio's Gmail API integration.
    
    Args:
        user_id: The user's business_id
        criteria: Filter criteria dict with keys:
            - from: sender email address
            - to: recipient email address
            - subject: subject line text
            - query: Gmail search query (advanced syntax)
            - negatedQuery: exclude messages matching this
            - hasAttachment: bool
            - size: size in bytes
            - sizeComparison: 'larger' or 'smaller'
        action: Filter action dict with keys:
            - addLabelIds: list of label IDs to add (e.g., ['IMPORTANT'])
            - removeLabelIds: list of label IDs to remove (e.g., ['INBOX', 'UNREAD'])
            - forward: email address to forward to
    
    Returns:
        {"success": True, "filter_id": "...", "filter": {...}} or {"error": "..."}
    """
    try:
        from composio_service import composio_proxy, TOOLKIT_GMAIL
    except ImportError:
        return {"error": "Composio service not available"}
    
    # Build filter body for Gmail API
    filter_body = {}
    
    if criteria:
        filter_body["criteria"] = criteria
    
    if action:
        filter_body["action"] = action
    
    if not filter_body.get("criteria") or not filter_body.get("action"):
        return {"error": "Both criteria and action are required"}
    
    try:
        # Use Composio proxy to call Gmail API
        result = await composio_proxy(
            user_id,
            TOOLKIT_GMAIL,
            "POST",
            "/gmail/v1/users/me/settings/filters",
            json=filter_body,
            timeout=15.0,
        )
        
        if "id" in result:
            logger.info(f"[gmail_filter] Created filter {result['id']} for user {user_id}")
            return {
                "success": True,
                "filter_id": result["id"],
                "filter": result,
            }
        
        return {"error": f"Failed to create filter: {result}"}
        
    except Exception as e:
        logger.error(f"[gmail_filter] create_gmail_filter error: {e}")
        return {"error": str(e)}


async def list_gmail_filters(user_id: str) -> Dict[str, Any]:
    """
    List all Gmail filters for a user.
    
    Returns:
        {"success": True, "filters": [...]} or {"error": "..."}
    """
    try:
        from composio_service import composio_proxy, TOOLKIT_GMAIL
    except ImportError:
        return {"error": "Composio service not available"}
    
    try:
        result = await composio_proxy(
            user_id,
            TOOLKIT_GMAIL,
            "GET",
            "/gmail/v1/users/me/settings/filters",
            timeout=15.0,
        )
        
        filters = result.get("filter", [])
        logger.info(f"[gmail_filter] Listed {len(filters)} filters for user {user_id}")
        
        return {
            "success": True,
            "filters": filters,
            "count": len(filters),
        }
        
    except Exception as e:
        logger.error(f"[gmail_filter] list_gmail_filters error: {e}")
        return {"error": str(e)}


async def delete_gmail_filter(user_id: str, filter_id: str) -> Dict[str, Any]:
    """
    Delete a Gmail filter by ID.
    
    Returns:
        {"success": True} or {"error": "..."}
    """
    try:
        from composio_service import composio_proxy, TOOLKIT_GMAIL
    except ImportError:
        return {"error": "Composio service not available"}
    
    try:
        await composio_proxy(
            user_id,
            TOOLKIT_GMAIL,
            "DELETE",
            f"/gmail/v1/users/me/settings/filters/{filter_id}",
            timeout=15.0,
        )
        
        logger.info(f"[gmail_filter] Deleted filter {filter_id} for user {user_id}")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"[gmail_filter] delete_gmail_filter error: {e}")
        return {"error": str(e)}


# ── Batch Operations ───────────────────────────────────────────────────────

async def create_sender_archive_filter(
    user_id: str,
    sender_email: str,
    also_mark_read: bool = False,
) -> Dict[str, Any]:
    """
    Create a filter to auto-archive emails from a specific sender.
    
    Args:
        user_id: The user's business_id
        sender_email: Email address to filter
        also_mark_read: If True, also mark as read
    
    Returns:
        {"success": True, "filter_id": "..."} or {"error": "..."}
    """
    criteria = {"from": sender_email}
    
    action = {"removeLabelIds": ["INBOX"]}
    if also_mark_read:
        action["removeLabelIds"].append("UNREAD")
    
    return await create_gmail_filter(user_id, criteria, action)


async def create_unsubscribe_catchall_filter(user_id: str) -> Dict[str, Any]:
    """
    Create a catch-all filter that archives any email with "unsubscribe" in the body.
    This is a safety net for newsletters that slip through other filters.
    
    Returns:
        {"success": True, "filter_id": "..."} or {"error": "..."}
    """
    criteria = {"query": "unsubscribe"}
    action = {"removeLabelIds": ["INBOX"]}
    
    return await create_gmail_filter(user_id, criteria, action)


async def setup_newsletter_filters(
    user_id: str,
    custom_senders: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Batch create filters for all newsletter senders.
    
    Args:
        user_id: The user's business_id
        custom_senders: Optional list of additional sender emails to filter
    
    Returns:
        {
            "success": True,
            "created": 8,
            "failed": 0,
            "filters": [{"sender": "...", "filter_id": "..."}, ...]
        }
    """
    senders = NEWSLETTER_SENDERS.copy()
    if custom_senders:
        senders.extend(custom_senders)
    
    results = []
    created = 0
    failed = 0
    
    for sender in senders:
        result = await create_sender_archive_filter(user_id, sender)
        
        if result.get("success"):
            created += 1
            results.append({
                "sender": sender,
                "filter_id": result.get("filter_id"),
                "status": "created",
            })
        else:
            failed += 1
            results.append({
                "sender": sender,
                "error": result.get("error"),
                "status": "failed",
            })
    
    # Also create the unsubscribe catch-all
    catchall_result = await create_unsubscribe_catchall_filter(user_id)
    if catchall_result.get("success"):
        created += 1
        results.append({
            "sender": "unsubscribe (catch-all)",
            "filter_id": catchall_result.get("filter_id"),
            "status": "created",
        })
    else:
        failed += 1
        results.append({
            "sender": "unsubscribe (catch-all)",
            "error": catchall_result.get("error"),
            "status": "failed",
        })
    
    logger.info(f"[gmail_filter] Batch setup complete: {created} created, {failed} failed")
    
    return {
        "success": True,
        "created": created,
        "failed": failed,
        "filters": results,
    }


# ── Advanced Filter Creation ───────────────────────────────────────────────

async def create_smart_filter(
    user_id: str,
    filter_type: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a smart filter based on common use cases.
    
    Args:
        user_id: The user's business_id
        filter_type: One of:
            - 'archive_sender': Archive emails from specific sender
            - 'archive_domain': Archive emails from entire domain
            - 'archive_subject': Archive emails with subject keyword
            - 'important_sender': Mark sender as important
            - 'label_sender': Apply custom label to sender
            - 'forward_sender': Forward emails from sender
            - 'archive_large': Archive large attachments
            - 'archive_unsubscribe': Archive emails with unsubscribe links
        params: Filter-specific parameters
    
    Returns:
        {"success": True, "filter_id": "..."} or {"error": "..."}
    """
    criteria = {}
    action = {}
    
    if filter_type == "archive_sender":
        criteria["from"] = params.get("sender")
        action["removeLabelIds"] = ["INBOX"]
        
    elif filter_type == "archive_domain":
        domain = params.get("domain")
        criteria["from"] = f"@{domain}"
        action["removeLabelIds"] = ["INBOX"]
        
    elif filter_type == "archive_subject":
        criteria["subject"] = params.get("subject")
        action["removeLabelIds"] = ["INBOX"]
        
    elif filter_type == "important_sender":
        criteria["from"] = params.get("sender")
        action["addLabelIds"] = ["IMPORTANT"]
        
    elif filter_type == "label_sender":
        criteria["from"] = params.get("sender")
        label_id = params.get("label_id")
        if not label_id:
            return {"error": "label_id required for label_sender filter"}
        action["addLabelIds"] = [label_id]
        
    elif filter_type == "forward_sender":
        criteria["from"] = params.get("sender")
        forward_to = params.get("forward_to")
        if not forward_to:
            return {"error": "forward_to required for forward_sender filter"}
        action["forward"] = forward_to
        
    elif filter_type == "archive_large":
        size_mb = params.get("size_mb", 10)
        criteria["size"] = size_mb * 1024 * 1024
        criteria["sizeComparison"] = "larger"
        action["removeLabelIds"] = ["INBOX"]
        
    elif filter_type == "archive_unsubscribe":
        criteria["query"] = "unsubscribe"
        action["removeLabelIds"] = ["INBOX"]
        
    else:
        return {"error": f"Unknown filter_type: {filter_type}"}
    
    if not criteria or not action:
        return {"error": "Invalid filter configuration"}
    
    return await create_gmail_filter(user_id, criteria, action)


# ── Filter Analysis & Suggestions ──────────────────────────────────────────

async def analyze_inbox_for_filter_suggestions(
    user_id: str,
    db: Any,
    min_sender_count: int = 3,
) -> Dict[str, Any]:
    """
    Analyze user's inbox to suggest filters for frequent senders.
    
    Args:
        user_id: The user's business_id
        db: MongoDB database instance
        min_sender_count: Minimum emails from sender to suggest filter
    
    Returns:
        {
            "suggestions": [
                {
                    "sender": "newsletter@example.com",
                    "count": 15,
                    "sample_subjects": ["...", "..."],
                    "suggested_action": "archive",
                    "reason": "High volume promotional sender"
                }
            ]
        }
    """
    try:
        # Aggregate emails by sender
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": "$from_addr",
                "count": {"$sum": 1},
                "subjects": {"$push": "$subject"},
                "is_read_avg": {"$avg": {"$cond": ["$is_read", 1, 0]}},
            }},
            {"$match": {"count": {"$gte": min_sender_count}}},
            {"$sort": {"count": -1}},
            {"$limit": 50},
        ]
        
        results = await db.email_messages.aggregate(pipeline).to_list(50)
        
        suggestions = []
        for result in results:
            sender = result["_id"]
            count = result["count"]
            subjects = result["subjects"][:3]
            read_rate = result.get("is_read_avg", 0)
            
            # Heuristics for filter suggestions
            reason = ""
            suggested_action = "archive"
            
            if "unsubscribe" in sender.lower() or "newsletter" in sender.lower():
                reason = "Newsletter sender"
            elif "noreply" in sender.lower() or "no-reply" in sender.lower():
                reason = "Automated notification sender"
            elif read_rate < 0.3 and count >= 5:
                reason = "Low engagement sender (rarely read)"
            elif count >= 10:
                reason = "High volume sender"
            else:
                continue  # Skip if no clear pattern
            
            suggestions.append({
                "sender": sender,
                "count": count,
                "sample_subjects": subjects,
                "suggested_action": suggested_action,
                "reason": reason,
                "read_rate": round(read_rate, 2),
            })
        
        logger.info(f"[gmail_filter] Generated {len(suggestions)} filter suggestions for user {user_id}")
        
        return {
            "success": True,
            "suggestions": suggestions,
            "count": len(suggestions),
        }
        
    except Exception as e:
        logger.error(f"[gmail_filter] analyze_inbox_for_filter_suggestions error: {e}")
        return {"error": str(e)}


# ── Database Tracking ──────────────────────────────────────────────────────

async def save_filter_to_db(
    user_id: str,
    db: Any,
    filter_id: str,
    criteria: Dict[str, Any],
    action: Dict[str, Any],
    filter_type: str = "custom",
) -> None:
    """
    Save filter metadata to MongoDB for tracking and management.
    """
    try:
        await db.gmail_filters.update_one(
            {"user_id": user_id, "filter_id": filter_id},
            {"$set": {
                "user_id": user_id,
                "filter_id": filter_id,
                "criteria": criteria,
                "action": action,
                "filter_type": filter_type,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        logger.info(f"[gmail_filter] Saved filter {filter_id} to DB")
    except Exception as e:
        logger.warning(f"[gmail_filter] Failed to save filter to DB: {e}")


async def get_user_filters_from_db(user_id: str, db: Any) -> List[Dict[str, Any]]:
    """
    Get all filters for a user from MongoDB.
    """
    try:
        cursor = db.gmail_filters.find({"user_id": user_id}).sort("created_at", -1)
        filters = await cursor.to_list(1000)
        return filters
    except Exception as e:
        logger.error(f"[gmail_filter] get_user_filters_from_db error: {e}")
        return []
