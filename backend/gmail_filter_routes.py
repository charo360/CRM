"""
Gmail Filter Management API Routes

RESTful endpoints for managing Gmail filters programmatically.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Query, Body
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def init_gmail_filter_routes(db: Any) -> APIRouter:
    """Initialize Gmail filter routes with database connection."""
    
    router = APIRouter(prefix="/api/gmail/filters", tags=["gmail-filters"])
    
    @router.get("/list")
    async def list_filters(user_id: str = Query(..., description="User ID")):
        """List all Gmail filters for the authenticated user."""
        try:
            from gmail_filter_service import list_gmail_filters
            result = await list_gmail_filters(user_id)
            
            if result.get("error"):
                return JSONResponse(content=result, status_code=400)
            
            return JSONResponse(content=result, status_code=200)
            
        except Exception as e:
            logger.error(f"[gmail_filter_routes] list_filters error: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)
    
    
    @router.post("/create")
    async def create_filter(data: Dict[str, Any] = Body(...)):
        """
        Create a new Gmail filter.
        
        Body:
        {
            "user_id": "...",
            "criteria": {
                "from": "sender@example.com",
                "subject": "...",
                "query": "...",
                "hasAttachment": true
            },
            "action": {
                "addLabelIds": ["IMPORTANT"],
                "removeLabelIds": ["INBOX", "UNREAD"]
            }
        }
        """
        try:
            user_id = data.get("user_id")
            criteria = data.get("criteria", {})
            action = data.get("action", {})
            
            if not user_id:
                return JSONResponse(content={"error": "user_id required"}, status_code=400)
            
            if not criteria or not action:
                return JSONResponse(content={"error": "Both criteria and action required"}, status_code=400)
            
            from gmail_filter_service import create_gmail_filter, save_filter_to_db
            result = await create_gmail_filter(user_id, criteria, action)
            
            if result.get("error"):
                return JSONResponse(content=result, status_code=400)
            
            # Save to DB for tracking
            if result.get("filter_id"):
                await save_filter_to_db(
                    user_id,
                    db,
                    result["filter_id"],
                    criteria,
                    action,
                    filter_type="custom",
                )
            
            return JSONResponse(content=result, status_code=201)
            
        except Exception as e:
            logger.error(f"[gmail_filter_routes] create_filter error: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)
    
    
    @router.delete("/delete/{filter_id}")
    async def delete_filter(filter_id: str, user_id: str = Query(...)):
        """Delete a Gmail filter by ID."""
        try:
            
            from gmail_filter_service import delete_gmail_filter
            result = await delete_gmail_filter(user_id, filter_id)
            
            if result.get("error"):
                return JSONResponse(content=result, status_code=400)
            
            # Remove from DB
            await db.gmail_filters.delete_one({
                "user_id": user_id,
                "filter_id": filter_id,
            })
            
            return JSONResponse(content=result, status_code=200)
            
        except Exception as e:
            logger.error(f"[gmail_filter_routes] delete_filter error: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)
    
    
    @router.post("/smart-create")
    async def smart_create_filter(data: Dict[str, Any] = Body(...)):
        """
        Create a smart filter using predefined templates.
        
        Body:
        {
            "user_id": "...",
            "filter_type": "archive_sender",
            "params": {
                "sender": "newsletter@example.com"
            }
        }
        
        Filter types:
        - archive_sender: Archive emails from sender
        - archive_domain: Archive emails from domain
        - archive_subject: Archive by subject keyword
        - important_sender: Mark sender as important
        - label_sender: Apply custom label
        - forward_sender: Forward to another email
        - archive_large: Archive large attachments
        - archive_unsubscribe: Archive emails with unsubscribe
        """
        try:
            user_id = data.get("user_id")
            filter_type = data.get("filter_type")
            params = data.get("params", {})
            
            if not user_id or not filter_type:
                return JSONResponse(content={"error": "user_id and filter_type required"}, status_code=400)
            
            from gmail_filter_service import create_smart_filter, save_filter_to_db
            result = await create_smart_filter(user_id, filter_type, params)
            
            if result.get("error"):
                return JSONResponse(content=result, status_code=400)
            
            # Save to DB
            if result.get("filter_id"):
                await save_filter_to_db(
                    user_id,
                    db,
                    result["filter_id"],
                    criteria=params,
                    action={"type": filter_type},
                    filter_type=filter_type,
                )
            
            return JSONResponse(content=result, status_code=201)
            
        except Exception as e:
            logger.error(f"[gmail_filter_routes] smart_create_filter error: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)
    
    
    @router.post("/batch/newsletters")
    async def batch_setup_newsletters(data: Dict[str, Any] = Body(...)):
        """
        Batch create filters for all predefined newsletter senders.
        
        Body:
        {
            "user_id": "...",
            "custom_senders": ["extra@example.com"]  // optional
        }
        """
        try:
            user_id = data.get("user_id")
            custom_senders = data.get("custom_senders", [])
            
            if not user_id:
                return JSONResponse(content={"error": "user_id required"}, status_code=400)
            
            from gmail_filter_service import setup_newsletter_filters
            result = await setup_newsletter_filters(user_id, custom_senders)
            
            # Save successful filters to DB
            for filter_info in result.get("filters", []):
                if filter_info.get("status") == "created" and filter_info.get("filter_id"):
                    from gmail_filter_service import save_filter_to_db
                    await save_filter_to_db(
                        user_id,
                        db,
                        filter_info["filter_id"],
                        criteria={"from": filter_info["sender"]},
                        action={"removeLabelIds": ["INBOX"]},
                        filter_type="newsletter_archive",
                    )
            
            return JSONResponse(content=result, status_code=201)
            
        except Exception as e:
            logger.error(f"[gmail_filter_routes] batch_setup_newsletters error: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)
    
    
    @router.get("/suggestions")
    async def get_filter_suggestions(
        user_id: str = Query(...),
        min_count: int = Query(3)
    ):
        """
        Analyze inbox and suggest filters for frequent senders.
        
        Query params:
        - user_id: required
        - min_count: minimum emails from sender (default: 3)
        """
        try:
            
            from gmail_filter_service import analyze_inbox_for_filter_suggestions
            result = await analyze_inbox_for_filter_suggestions(
                user_id,
                db,
                min_sender_count=min_count,
            )
            
            if result.get("error"):
                return JSONResponse(content=result, status_code=400)
            
            return JSONResponse(content=result, status_code=200)
            
        except Exception as e:
            logger.error(f"[gmail_filter_routes] get_filter_suggestions error: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)
    
    
    @router.post("/archive-sender")
    async def archive_sender(data: Dict[str, Any] = Body(...)):
        """
        Quick endpoint to archive a specific sender.
        
        Body:
        {
            "user_id": "...",
            "sender": "newsletter@example.com",
            "also_mark_read": false
        }
        """
        try:
            user_id = data.get("user_id")
            sender = data.get("sender")
            also_mark_read = data.get("also_mark_read", False)
            
            if not user_id or not sender:
                return JSONResponse(content={"error": "user_id and sender required"}, status_code=400)
            
            from gmail_filter_service import create_sender_archive_filter, save_filter_to_db
            result = await create_sender_archive_filter(user_id, sender, also_mark_read)
            
            if result.get("error"):
                return JSONResponse(content=result, status_code=400)
            
            # Save to DB
            if result.get("filter_id"):
                action = {"removeLabelIds": ["INBOX"]}
                if also_mark_read:
                    action["removeLabelIds"].append("UNREAD")
                
                await save_filter_to_db(
                    user_id,
                    db,
                    result["filter_id"],
                    criteria={"from": sender},
                    action=action,
                    filter_type="archive_sender",
                )
            
            return JSONResponse(content=result, status_code=201)
            
        except Exception as e:
            logger.error(f"[gmail_filter_routes] archive_sender error: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)
    
    
    @router.get("/my-filters")
    async def get_my_filters(user_id: str = Query(...)):
        """Get all filters for user from local DB (faster than Gmail API)."""
        try:
            
            from gmail_filter_service import get_user_filters_from_db
            filters = await get_user_filters_from_db(user_id, db)
            
            # Format for frontend
            formatted = []
            for f in filters:
                formatted.append({
                    "id": f.get("filter_id"),
                    "criteria": f.get("criteria", {}),
                    "action": f.get("action", {}),
                    "type": f.get("filter_type", "custom"),
                    "created_at": f.get("created_at", "").isoformat() if hasattr(f.get("created_at"), "isoformat") else str(f.get("created_at", "")),
                })
            
            return JSONResponse(content={
                "success": True,
                "filters": formatted,
                "count": len(formatted),
            }, status_code=200)
            
        except Exception as e:
            logger.error(f"[gmail_filter_routes] get_my_filters error: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)
    
    
    return router
