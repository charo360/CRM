import logging
import asyncio
import os
import httpx
from typing import Any, Dict, List, Optional
from composio_service import execute_action, get_connection_status

logger = logging.getLogger(__name__)

def _normalize_time(t: str) -> str:
    # Convert Meta time (e.g. 2026-05-07T12:49:51+0000) to ISO string
    if not t:
        return ""
    if "+" in t:
        t = t.split("+")[0]
    return t + "Z"

async def list_conversations(user_id: str, platform: Optional[str] = None) -> List[Dict[str, Any]]:
    """List Facebook & Instagram conversations via Composio."""
    conversations: List[Dict[str, Any]] = []
    
    # 1. Resolve connected platforms
    platforms_to_check = ["instagram", "facebook"]
    if platform:
        platforms_to_check = [platform.lower()]
        
    tasks = []
    for plat in platforms_to_check:
        tasks.append(get_connection_status(user_id, plat))
        
    statuses = await asyncio.gather(*tasks)
    
    active_plats = []
    for plat, status in zip(platforms_to_check, statuses):
        if status.get("connected") and status.get("connection_id"):
            active_plats.append({
                "platform": plat,
                "connection_id": status["connection_id"]
            })
            
    if not active_plats:
        return []
        
    # Helper to process one conversation
    async def process_ig_conv(conv: Dict[str, Any], connection_id: str, page_username: str) -> Optional[Dict[str, Any]]:
        conv_id = conv.get("id")
        if not conv_id:
            return None
        try:
            msgs_res = await execute_action(
                user_id,
                "INSTAGRAM_LIST_ALL_MESSAGES",
                {"conversation_id": conv_id, "limit": 1}
            )
            if not msgs_res.get("success") or not msgs_res.get("data"):
                return None
                
            msgs_list = msgs_res["data"].get("data") or []
            if not msgs_list:
                return None
                
            latest_msg = msgs_list[0]
            
            # Resolve participant
            from_obj = latest_msg.get("from_") or latest_msg.get("from") or {}
            to_obj = latest_msg.get("to") or {}
            to_data = to_obj.get("data") if isinstance(to_obj, dict) else to_obj
            if not isinstance(to_data, list):
                to_data = []
                
            from_username = from_obj.get("username") or from_obj.get("name") or ""
            from_id = from_obj.get("id") or ""
            
            if from_username and from_username.lower() != page_username.lower():
                participant_name = from_username
                participant_id = from_id
            else:
                # Use first recipient that isn't the page
                participant_name = ""
                participant_id = ""
                for recipient in to_data:
                    r_username = recipient.get("username") or recipient.get("name") or ""
                    if r_username and r_username.lower() != page_username.lower():
                        participant_name = r_username
                        participant_id = recipient.get("id") or ""
                        break
                if not participant_name and to_data:
                    participant_name = to_data[0].get("username") or to_data[0].get("name") or "User"
                    participant_id = to_data[0].get("id") or ""
                    
            return {
                "id": conv_id,
                "platform": "instagram",
                "source": "social",
                "accountId": connection_id,
                "account_id": connection_id,
                "participantId": participant_id,
                "participant_name": participant_name,
                "participant": participant_name,
                "last_message": latest_msg.get("message") or "[Attachment]",
                "last_message_at": _normalize_time(latest_msg.get("created_time") or conv.get("updated_time") or ""),
                "unread": 0,
            }
        except Exception as exc:
            logger.warning(f"[composio-inbox] Failed to process IG conv {conv_id}: {exc}")
            return None

    async def process_fb_conv(conv: Dict[str, Any], connection_id: str, page_id: str, page_name: str) -> Optional[Dict[str, Any]]:
        conv_id = conv.get("id")
        if not conv_id:
            return None
        try:
            msgs_res = await execute_action(
                user_id,
                "FACEBOOK_GET_CONVERSATION_MESSAGES",
                {"conversation_id": conv_id, "limit": 1}
            )
            if not msgs_res.get("success") or not msgs_res.get("data"):
                return None
                
            raw_data = msgs_res["data"]
            # Meta FB API nests messages: data: { messages: { data: [...] } } or data: [...]
            msgs_list = []
            if isinstance(raw_data, dict):
                inner_msgs = raw_data.get("messages") or {}
                if isinstance(inner_msgs, dict):
                    msgs_list = inner_msgs.get("data") or []
                else:
                    msgs_list = raw_data.get("data") or []
            
            if not msgs_list:
                return None
                
            latest_msg = msgs_list[0]
            
            # Resolve participant
            from_obj = latest_msg.get("from") or latest_msg.get("from_") or {}
            to_obj = latest_msg.get("to") or {}
            to_data = to_obj.get("data") if isinstance(to_obj, dict) else to_obj
            if not isinstance(to_data, list):
                to_data = []
                
            from_name = from_obj.get("name") or from_obj.get("username") or ""
            from_id = from_obj.get("id") or ""
            
            if from_id and from_id != page_id:
                participant_name = from_name or f"User {from_id[-8:]}"
                participant_id = from_id
            else:
                participant_name = ""
                participant_id = ""
                for recipient in to_data:
                    r_id = recipient.get("id") or ""
                    if r_id and r_id != page_id:
                        participant_name = recipient.get("name") or recipient.get("username") or f"User {r_id[-8:]}"
                        participant_id = r_id
                        break
                if not participant_name and to_data:
                    participant_name = to_data[0].get("name") or to_data[0].get("username") or "User"
                    participant_id = to_data[0].get("id") or ""
                    
            return {
                "id": conv_id,
                "platform": "facebook",
                "source": "social",
                "accountId": connection_id,
                "account_id": connection_id,
                "participantId": participant_id,
                "participant_name": participant_name,
                "participant": participant_name,
                "last_message": latest_msg.get("message") or "[Attachment]",
                "last_message_at": _normalize_time(latest_msg.get("created_time") or conv.get("updated_time") or ""),
                "unread": 0,
            }
        except Exception as exc:
            logger.warning(f"[composio-inbox] Failed to process FB conv {conv_id}: {exc}")
            return None

    # Fetch and process conversations for each active platform
    for info in active_plats:
        plat = info["platform"]
        conn_id = info["connection_id"]
        
        if plat == "instagram":
            try:
                # A. Get page username
                user_info = await execute_action(user_id, "INSTAGRAM_GET_USER_INFO", {})
                page_username = ""
                if user_info.get("success") and user_info.get("data"):
                    page_username = user_info["data"].get("username") or ""
                    
                # B. List conversations
                conv_res = await execute_action(user_id, "INSTAGRAM_LIST_ALL_CONVERSATIONS", {})
                if conv_res.get("success") and conv_res.get("data"):
                    convs = conv_res["data"].get("data") or []
                    conv_tasks = [process_ig_conv(c, conn_id, page_username) for c in convs[:15]]
                    results = await asyncio.gather(*conv_tasks)
                    conversations.extend([r for r in results if r])
            except Exception as e:
                logger.error(f"[composio-inbox] Instagram load error: {e}")
                
        elif plat == "facebook":
            try:
                # A. Get user pages to find page details
                pages_res = await execute_action(user_id, "FACEBOOK_GET_USER_PAGES", {})
                if pages_res.get("success") and pages_res.get("data"):
                    pages_list = pages_res["data"].get("data") or pages_res["data"].get("pages") or []
                    for page in pages_list[:3]: # Limit to first few pages
                        page_id = page.get("id")
                        page_name = page.get("name") or page_id
                        if not page_id:
                            continue
                            
                        # B. List conversations for page
                        conv_res = await execute_action(
                            user_id,
                            "FACEBOOK_GET_PAGE_CONVERSATIONS",
                            {"page_id": page_id, "limit": 15}
                        )
                        if conv_res.get("success") and conv_res.get("data"):
                            convs = conv_res["data"].get("data") or []
                            conv_tasks = [process_fb_conv(c, conn_id, page_id, page_name) for c in convs]
                            results = await asyncio.gather(*conv_tasks)
                            conversations.extend([r for r in results if r])
            except Exception as e:
                logger.error(f"[composio-inbox] Facebook load error: {e}")
                
    return conversations

async def get_conversation_messages(user_id: str, conversation_id: str, connection_id: str) -> List[Dict[str, Any]]:
    """Get message history for a conversation via Composio."""
    # Resolve platform from toolkit connection ID
    # Get all active connection list
    headers = {
        "x-api-key": os.environ.get("COMPOSIO_API_KEY", ""),
        "Content-Type": "application/json"
    }
    platform = "instagram"
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            f"https://backend.composio.dev/api/v3/connected_accounts/{connection_id}",
            headers=headers
        )
        if resp.status_code == 200:
            data = resp.json()
            platform = (data.get("toolkit") or {}).get("slug") or "instagram"
            
    messages: List[Dict[str, Any]] = []
    
    if platform == "instagram":
        # Resolve page username to determine direction
        user_info = await execute_action(user_id, "INSTAGRAM_GET_USER_INFO", {})
        page_username = ""
        if user_info.get("success") and user_info.get("data"):
            page_username = user_info["data"].get("username") or ""
            
        res = await execute_action(
            user_id,
            "INSTAGRAM_LIST_ALL_MESSAGES",
            {"conversation_id": conversation_id, "limit": 50}
        )
        if res.get("success") and res.get("data"):
            raw_list = res["data"].get("data") or []
            for msg in raw_list:
                from_obj = msg.get("from_") or msg.get("from") or {}
                from_username = from_obj.get("username") or from_obj.get("name") or ""
                direction = "out" if from_username.lower() == page_username.lower() else "in"
                messages.append({
                    "id": msg["id"],
                    "content": msg.get("message") or "[Attachment]",
                    "direction": direction,
                    "created_at": _normalize_time(msg.get("created_time") or ""),
                    "sender": from_username or msg.get("from", {}).get("id") or "User",
                })
                
    elif platform == "facebook":
        # Get page details to find page_id for direction
        # Try finding page_id from pages list
        pages_res = await execute_action(user_id, "FACEBOOK_GET_USER_PAGES", {})
        page_ids = set()
        if pages_res.get("success") and pages_res.get("data"):
            pages_list = pages_res["data"].get("data") or pages_res["data"].get("pages") or []
            for p in pages_list:
                if p.get("id"):
                    page_ids.add(p["id"])
                    
        res = await execute_action(
            user_id,
            "FACEBOOK_GET_CONVERSATION_MESSAGES",
            {"conversation_id": conversation_id, "limit": 50}
        )
        if res.get("success") and res.get("data"):
            raw_data = res["data"]
            raw_list = []
            if isinstance(raw_data, dict):
                inner_msgs = raw_data.get("messages") or {}
                if isinstance(inner_msgs, dict):
                    raw_list = inner_msgs.get("data") or []
                else:
                    raw_list = raw_data.get("data") or []
            
            for msg in raw_list:
                from_obj = msg.get("from") or msg.get("from_") or {}
                from_id = from_obj.get("id") or ""
                from_name = from_obj.get("name") or from_obj.get("username") or ""
                direction = "out" if from_id in page_ids else "in"
                messages.append({
                    "id": msg["id"],
                    "content": msg.get("message") or "[Attachment]",
                    "direction": direction,
                    "created_at": _normalize_time(msg.get("created_time") or ""),
                    "sender": from_name or from_id or "User",
                })
                
    # Sort messages chronologically
    messages.sort(key=lambda m: m["created_at"])
    return messages

async def send_message(user_id: str, conversation_id: str, connection_id: str, message: str) -> Dict[str, Any]:
    """Send a reply message via Composio."""
    headers = {
        "x-api-key": os.environ.get("COMPOSIO_API_KEY", ""),
        "Content-Type": "application/json"
    }
    platform = "instagram"
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            f"https://backend.composio.dev/api/v3/connected_accounts/{connection_id}",
            headers=headers
        )
        if resp.status_code == 200:
            data = resp.json()
            platform = (data.get("toolkit") or {}).get("slug") or "instagram"
            
    if platform == "instagram":
        # Resolve participant ID to send the DM
        conv_details = await execute_action(
            user_id,
            "INSTAGRAM_GET_CONVERSATION",
            {"conversation_id": conversation_id}
        )
        if not conv_details.get("success") or not conv_details.get("data"):
            return {"error": "Failed to get conversation details for recipient resolution"}
            
        participants = conv_details["data"].get("participants") or []
        # Find page ID to exclude it
        user_info = await execute_action(user_id, "INSTAGRAM_GET_USER_INFO", {})
        page_id = ""
        if user_info.get("success") and user_info.get("data"):
            page_id = user_info["data"].get("id") or ""
            
        recipient_id = ""
        for p in participants:
            p_id = p.get("id")
            if p_id and p_id != page_id:
                recipient_id = p_id
                break
                
        if not recipient_id and participants:
            # Fallback to the non-page participant or first participant
            recipient_id = participants[-1].get("id") or ""
            
        if not recipient_id:
            return {"error": "Could not resolve recipient ID for conversation"}
            
        res = await execute_action(
            user_id,
            "INSTAGRAM_SEND_TEXT_MESSAGE",
            {
                "recipient_id": recipient_id,
                "text": message
            }
        )
        return res
        
    elif platform == "facebook":
        # Resolve page_id and recipient_id
        # Let's get the conversation details to find the participant ID
        # Since FACEBOOK_GET_PAGE_CONVERSATIONS defaults to updated_time, participants, id,
        # we can retrieve user pages to identify which page owns the conversation.
        pages_res = await execute_action(user_id, "FACEBOOK_GET_USER_PAGES", {})
        if not pages_res.get("success") or not pages_res.get("data"):
            return {"error": "Failed to retrieve user pages"}
            
        pages_list = pages_res["data"].get("data") or pages_res["data"].get("pages") or []
        
        # Let's fetch conversation messages to find page_id and recipient_id
        msgs_res = await execute_action(
            user_id,
            "FACEBOOK_GET_CONVERSATION_MESSAGES",
            {"conversation_id": conversation_id, "limit": 5}
        )
        if not msgs_res.get("success") or not msgs_res.get("data"):
            return {"error": "Failed to retrieve conversation messages to resolve page/recipient"}
            
        raw_data = msgs_res["data"]
        msgs_list = []
        if isinstance(raw_data, dict):
            inner_msgs = raw_data.get("messages") or {}
            if isinstance(inner_msgs, dict):
                msgs_list = inner_msgs.get("data") or []
            else:
                msgs_list = raw_data.get("data") or []
                
        if not msgs_list:
            return {"error": "Empty conversation history, cannot resolve sender page"}
            
        # Inspect messages to identify the recipient_id (the user PSID) and page_id
        recipient_id = ""
        page_id = ""
        page_ids = {p.get("id") for p in pages_list if p.get("id")}
        
        for msg in msgs_list:
            from_id = (msg.get("from") or {}).get("id")
            to_data = (msg.get("to") or {}).get("data") or []
            
            if from_id in page_ids:
                page_id = from_id
                if to_data:
                    recipient_id = to_data[0].get("id")
            else:
                recipient_id = from_id
                if to_data:
                    for r in to_data:
                        r_id = r.get("id")
                        if r_id in page_ids:
                            page_id = r_id
                            break
                            
            if page_id and recipient_id:
                break
                
        if not page_id and pages_list:
            page_id = pages_list[0].get("id")
        if not recipient_id:
            return {"error": "Could not resolve recipient ID for page reply"}
            
        res = await execute_action(
            user_id,
            "FACEBOOK_SEND_MESSAGE",
            {
                "page_id": page_id,
                "recipient_id": recipient_id,
                "message_text": message
            }
        )
        return res
        
    return {"error": f"Unsupported platform: {platform}"}
