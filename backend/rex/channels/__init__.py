"""
rex.channels — Phase 9: Channel Delivery Layer (REX.md §4.7).

Provides bidirectional capability allowing the principal to receive briefs and
communicate with Rex (approvals, reviews, rejections) entirely from off-app surfaces.

Key Concept: Same Rex. Same Letter. Different Renderers.
=========================================================
The daily Letter is built once. Channel-specific renderers transform it:

    WhatsApp/Telegram  -> Numbered top-3 with reply tokens (YES / REVIEW)
    SMS                -> Single line urgent alerts with situational links
    Email              -> Letter with the ledger appendix below the fold
    In-App             -> Canonical Single-Column Letter

Inbound parsing processes text replies (e.g., "YES", "REVIEW") to allow direct,
app-less delegation.
"""

from rex.channels.primitives import Channel, UrgencyLevel, ActionVerb
from rex.channels.routing import route_event_to_channels
from rex.channels.renderers import render_for_channel
from rex.channels.parser import parse_reply

__all__ = [
    "Channel",
    "UrgencyLevel",
    "ActionVerb",
    "route_event_to_channels",
    "render_for_channel",
    "parse_reply",
]
