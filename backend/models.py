"""
Additional Pydantic models for API endpoints
"""
from pydantic import BaseModel
from typing import Optional

class SendMessageRequest(BaseModel):
    """Request to send a WhatsApp message (with auto-contact creation)"""
    to_number: str
    message: str
    customer_name: Optional[str] = None  # Optional: if you know their name

class SendMessageResponse(BaseModel):
    """Response after sending a message"""
    status: str
    customer_id: str
    message_id: str
    created_new_contact: bool
    customer_name: str
    twilio_sid: Optional[str] = None
