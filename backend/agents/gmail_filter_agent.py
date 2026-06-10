"""
Gmail Filter Agent

AI agent that can intelligently manage Gmail filters through natural language.
Enables users to create, modify, and manage email filters conversationally.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GmailFilterAgent:
    """
    AI agent for managing Gmail filters through natural language commands.
    
    Capabilities:
    - Create filters from natural language descriptions
    - Suggest filters based on inbox analysis
    - Batch create filters for common patterns
    - Explain existing filters in plain English
    """
    
    def __init__(self, user_id: str, db: Any):
        self.user_id = user_id
        self.db = db
    
    async def process_command(self, command: str) -> Dict[str, Any]:
        """
        Process a natural language filter command.
        
        Examples:
        - "Archive all emails from newsletter@example.com"
        - "Mark emails from boss@company.com as important"
        - "Set up filters for all my newsletters"
        - "Show me filter suggestions based on my inbox"
        - "Delete the filter for sender@example.com"
        """
        command_lower = command.lower().strip()
        
        # Archive sender
        if "archive" in command_lower and "from" in command_lower:
            return await self._handle_archive_sender(command)
        
        # Mark as important
        elif "important" in command_lower and "from" in command_lower:
            return await self._handle_mark_important(command)
        
        # Batch newsletter setup
        elif "newsletter" in command_lower and ("setup" in command_lower or "filter" in command_lower):
            return await self._handle_newsletter_setup()
        
        # Get suggestions
        elif "suggest" in command_lower or "recommend" in command_lower:
            return await self._handle_suggestions()
        
        # List filters
        elif "list" in command_lower or "show" in command_lower:
            return await self._handle_list_filters()
        
        # Delete filter
        elif "delete" in command_lower or "remove" in command_lower:
            return await self._handle_delete_filter(command)
        
        else:
            return {
                "error": "I didn't understand that command. Try:\n"
                         "- 'Archive emails from sender@example.com'\n"
                         "- 'Mark emails from boss@company.com as important'\n"
                         "- 'Set up newsletter filters'\n"
                         "- 'Show me filter suggestions'"
            }
    
    async def _handle_archive_sender(self, command: str) -> Dict[str, Any]:
        """Extract sender email and create archive filter."""
        # Simple email extraction
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, command)
        
        if not matches:
            return {"error": "Could not find an email address in your command"}
        
        sender = matches[0]
        also_mark_read = "mark as read" in command.lower() or "mark read" in command.lower()
        
        from gmail_filter_service import create_sender_archive_filter, save_filter_to_db
        result = await create_sender_archive_filter(self.user_id, sender, also_mark_read)
        
        if result.get("error"):
            return result
        
        # Save to DB
        if result.get("filter_id"):
            action = {"removeLabelIds": ["INBOX"]}
            if also_mark_read:
                action["removeLabelIds"].append("UNREAD")
            
            await save_filter_to_db(
                self.user_id,
                self.db,
                result["filter_id"],
                criteria={"from": sender},
                action=action,
                filter_type="archive_sender",
            )
        
        return {
            "success": True,
            "message": f"✓ Created filter to archive emails from {sender}" + 
                      (" and mark as read" if also_mark_read else ""),
            "filter_id": result.get("filter_id"),
        }
    
    async def _handle_mark_important(self, command: str) -> Dict[str, Any]:
        """Extract sender and create important filter."""
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, command)
        
        if not matches:
            return {"error": "Could not find an email address in your command"}
        
        sender = matches[0]
        
        from gmail_filter_service import create_smart_filter, save_filter_to_db
        result = await create_smart_filter(
            self.user_id,
            "important_sender",
            {"sender": sender},
        )
        
        if result.get("error"):
            return result
        
        # Save to DB
        if result.get("filter_id"):
            await save_filter_to_db(
                self.user_id,
                self.db,
                result["filter_id"],
                criteria={"from": sender},
                action={"addLabelIds": ["IMPORTANT"]},
                filter_type="important_sender",
            )
        
        return {
            "success": True,
            "message": f"✓ Created filter to mark emails from {sender} as important",
            "filter_id": result.get("filter_id"),
        }
    
    async def _handle_newsletter_setup(self) -> Dict[str, Any]:
        """Batch create filters for all newsletter senders."""
        from gmail_filter_service import setup_newsletter_filters
        result = await setup_newsletter_filters(self.user_id)
        
        if result.get("error"):
            return result
        
        created = result.get("created", 0)
        failed = result.get("failed", 0)
        
        message = f"✓ Newsletter filter setup complete!\n"
        message += f"  • Created {created} filters\n"
        if failed > 0:
            message += f"  • Failed: {failed}\n"
        message += "\nThese senders will now be auto-archived:\n"
        
        for filter_info in result.get("filters", [])[:5]:
            if filter_info.get("status") == "created":
                message += f"  • {filter_info['sender']}\n"
        
        if created > 5:
            message += f"  ... and {created - 5} more"
        
        return {
            "success": True,
            "message": message,
            "created": created,
            "failed": failed,
        }
    
    async def _handle_suggestions(self) -> Dict[str, Any]:
        """Analyze inbox and provide filter suggestions."""
        from gmail_filter_service import analyze_inbox_for_filter_suggestions
        result = await analyze_inbox_for_filter_suggestions(self.user_id, self.db)
        
        if result.get("error"):
            return result
        
        suggestions = result.get("suggestions", [])
        
        if not suggestions:
            return {
                "success": True,
                "message": "Your inbox looks clean! No filter suggestions at this time.",
                "suggestions": [],
            }
        
        message = f"📊 Found {len(suggestions)} filter suggestions:\n\n"
        
        for i, sugg in enumerate(suggestions[:5], 1):
            sender = sugg["sender"]
            count = sugg["count"]
            reason = sugg["reason"]
            read_rate = sugg.get("read_rate", 0)
            
            message += f"{i}. **{sender}**\n"
            message += f"   • {count} emails ({int(read_rate * 100)}% read rate)\n"
            message += f"   • {reason}\n"
            message += f"   • Suggested: Archive automatically\n\n"
        
        if len(suggestions) > 5:
            message += f"... and {len(suggestions) - 5} more suggestions"
        
        return {
            "success": True,
            "message": message,
            "suggestions": suggestions,
        }
    
    async def _handle_list_filters(self) -> Dict[str, Any]:
        """List all active filters."""
        from gmail_filter_service import get_user_filters_from_db
        filters = await get_user_filters_from_db(self.user_id, self.db)
        
        if not filters:
            return {
                "success": True,
                "message": "You don't have any filters set up yet.",
                "filters": [],
            }
        
        message = f"📋 Your active filters ({len(filters)}):\n\n"
        
        for i, f in enumerate(filters[:10], 1):
            criteria = f.get("criteria", {})
            action = f.get("action", {})
            filter_type = f.get("filter_type", "custom")
            
            # Format criteria
            if "from" in criteria:
                message += f"{i}. Archive emails from: {criteria['from']}\n"
            elif "subject" in criteria:
                message += f"{i}. Filter by subject: {criteria['subject']}\n"
            elif "query" in criteria:
                message += f"{i}. Filter by query: {criteria['query']}\n"
            else:
                message += f"{i}. Custom filter ({filter_type})\n"
        
        if len(filters) > 10:
            message += f"\n... and {len(filters) - 10} more filters"
        
        return {
            "success": True,
            "message": message,
            "filters": filters,
            "count": len(filters),
        }
    
    async def _handle_delete_filter(self, command: str) -> Dict[str, Any]:
        """Delete a filter by sender or ID."""
        import re
        
        # Try to extract email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, command)
        
        if not matches:
            return {
                "error": "Please specify the sender email for the filter you want to delete"
            }
        
        sender = matches[0]
        
        # Find filter in DB
        filter_doc = await self.db.gmail_filters.find_one({
            "user_id": self.user_id,
            "criteria.from": sender,
        })
        
        if not filter_doc:
            return {
                "error": f"No filter found for sender: {sender}"
            }
        
        filter_id = filter_doc.get("filter_id")
        
        from gmail_filter_service import delete_gmail_filter
        result = await delete_gmail_filter(self.user_id, filter_id)
        
        if result.get("error"):
            return result
        
        # Remove from DB
        await self.db.gmail_filters.delete_one({
            "user_id": self.user_id,
            "filter_id": filter_id,
        })
        
        return {
            "success": True,
            "message": f"✓ Deleted filter for {sender}",
        }


# ── Agent Tool Interface ───────────────────────────────────────────────────

async def gmail_filter_agent_tool(
    user_id: str,
    db: Any,
    command: str,
) -> Dict[str, Any]:
    """
    Tool interface for AI assistants to manage Gmail filters.
    
    Usage in agent context:
    ```python
    result = await gmail_filter_agent_tool(
        user_id="user123",
        db=db,
        command="Archive all emails from newsletter@example.com"
    )
    ```
    """
    agent = GmailFilterAgent(user_id, db)
    return await agent.process_command(command)
