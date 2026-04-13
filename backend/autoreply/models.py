"""
Pydantic schemas for the autoreply v2 engine.
Claude must return JSON matching AutoReplyResponse.
All fields are validated strictly — failure triggers retry then fallback.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


# ── Menu item ────────────────────────────────────────────────────────────────

class MenuItem(BaseModel):
    id: str
    name: str
    price: float = 0
    type: Literal["product", "service"] = "product"
    category: str = ""


# ── Actions ──────────────────────────────────────────────────────────────────

class OrderItem(BaseModel):
    product_name: str
    product_id: str = ""
    quantity: int = Field(default=1, ge=1)
    unit_price: float = Field(default=0, ge=0)
    variant: str = ""       # e.g. "Pepperoni", "Chicken", "Large"
    modifiers: List[Dict[str, Any]] = Field(default_factory=list)
    # e.g. [{"group": "Spice Level", "choice": "Hot", "price_delta": 0},
    #        {"group": "Extras", "choice": "Soda", "price_delta": 100}]


class CreateOrderAction(BaseModel):
    type: Literal["create_order"]
    # Multi-item (preferred)
    items: List[OrderItem] = Field(default_factory=list)
    # Single-item legacy shorthand
    product_id: str = ""
    product_name: str = ""
    quantity: int = Field(default=1, ge=1)
    unit_price: float = Field(default=0, ge=0)
    # Fulfilment
    delivery_type: Literal["delivery", "pickup", "dine_in"] = "pickup"
    delivery_address: str = ""
    table_number: str = ""    # dine-in table number
    notes: str = ""


class CreateBookingAction(BaseModel):
    type: Literal["create_booking"]
    service_id: str = ""
    service_name: str
    price: float = 0
    date: str = ""
    time: str = ""
    is_rental: bool = False
    checkin_date: str = ""
    checkout_date: str = ""
    notes: str = ""


class CancelOrderAction(BaseModel):
    type: Literal["cancel_order"]
    order_id: str = "latest"
    reason: str = ""


class CancelBookingAction(BaseModel):
    type: Literal["cancel_booking"]
    booking_id: str = "latest"
    reason: str = ""


class RescheduleBookingAction(BaseModel):
    type: Literal["reschedule_booking"]
    booking_id: str = "latest"
    new_date: str
    reason: str = ""


class TagCustomerAction(BaseModel):
    type: Literal["tag_customer"]
    tag: str


class SetPaymentPendingAction(BaseModel):
    type: Literal["set_payment_pending"]
    order_id: str = "latest"


class NotifyOwnerAction(BaseModel):
    type: Literal["notify_owner"]
    reason: Literal["payment_received", "escalation", "complaint", "other"] = "other"
    message: str = ""


class ClearFlowAction(BaseModel):
    type: Literal["clear_flow"]


Action = Union[
    CreateOrderAction,
    CreateBookingAction,
    CancelOrderAction,
    CancelBookingAction,
    RescheduleBookingAction,
    TagCustomerAction,
    SetPaymentPendingAction,
    NotifyOwnerAction,
    ClearFlowAction,
]


# ── Flow update ───────────────────────────────────────────────────────────────

class FlowUpdate(BaseModel):
    active_flow: Optional[str] = None          # "ordering" | "booking" | "browsing" | null
    flow_product_id: Optional[str] = None
    flow_step: Optional[str] = None            # "awaiting_qty" | "awaiting_address" | "awaiting_date" | "awaiting_payment"


# ── Main response ─────────────────────────────────────────────────────────────

VALID_INTENTS = {"order", "booking", "inquiry", "complaint", "greeting", "payment_received", "cancel", "reschedule", "other"}
VALID_SENTIMENTS = {"positive", "neutral", "negative", "angry"}


class AutoReplyResponse(BaseModel):
    reply: str = Field(..., min_length=1, description="WhatsApp message to send")
    intent: str = "other"
    sentiment: str = "neutral"
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    escalate: bool = False
    escalate_reason: str = ""
    new_menu: Optional[Dict[str, Dict]] = None   # {"1": {id, name, price, type}, ...}
    flow_update: Optional[Dict] = None

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        return v if v in VALID_INTENTS else "other"

    @field_validator("sentiment")
    @classmethod
    def validate_sentiment(cls, v: str) -> str:
        return v if v in VALID_SENTIMENTS else "neutral"
