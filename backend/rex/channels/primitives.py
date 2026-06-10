"""
Primitives for channels, urgency routing levels, and bidirectional parse results.
"""

from __future__ import annotations

from enum import Enum


class Channel(str, Enum):
    IN_APP = "in_app"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    SMS = "sms"
    EMAIL = "email"


class UrgencyLevel(str, Enum):
    DAILY = "daily"          # e.g., morning letter (In-app, WhatsApp, Telegram, Email)
    INTRADAY = "intraday"    # e.g., general subagent promotion (In-app, Email)
    URGENT = "urgent"        # e.g., payment failures, deal-killers (SMS, WhatsApp, In-app)


class ActionVerb(str, Enum):
    APPROVE = "approve"      # Approve the contextual action
    REJECT = "reject"        # Reject it
    REVIEW = "review"        # Show full draft/details
    EDIT = "edit"            # Open edit flow link
    LEDGER = "ledger"        # Summary of the ledger
    PAUSE = "pause"          # Pause notifications
    UNKNOWN = "unknown"      # Fallback when parsing fails
