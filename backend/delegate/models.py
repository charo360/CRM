"""Pydantic schemas for the Delegate feature."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Frequencies the founder can pick. Mapped to a matcher in service.py.
Frequency = Literal[
    "every_day",
    "every_weekday",
    "every_monday",
    "every_friday",
    "every_sunday",
    "first_of_month",
]

OpportunityTriggerFilter = Literal["reddit", "scouted", "any", "first_message", "client_message"]

TriggerChannel = Literal[
    "any",
    "whatsapp",
    "slack",
    "instagram",
    "facebook",
    "telegram",
    "linkedin",
    "email",
    "bird",
]

DelegationMode = Literal["once", "schedule", "on_opportunity"]
DelegationStatus = Literal["running", "scheduled", "completed", "paused", "watching"]


class InterpretRequest(BaseModel):
    task: str = Field(min_length=1, max_length=2000)


class Schedule(BaseModel):
    frequency: Frequency
    # 24h "HH:MM" — defaults to 07:00, interpreted in `timezone`
    time: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")
    # IANA timezone the founder picked the time in (e.g. "America/Toronto").
    # Defaults to UTC so existing schedules with no tz keep their old behavior.
    timezone: str = Field(default="UTC", max_length=64)


class DelegationCreate(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    mode: DelegationMode = "once"
    schedule: Optional[Schedule] = None
    # When mode=on_opportunity — which event should auto-draft outreach.
    trigger_filter: Optional[OpportunityTriggerFilter] = None
    # Optional channel scope for client-message triggers (first_message / client_message).
    trigger_channel: Optional[TriggerChannel] = "any"


class DraftUpdateRequest(BaseModel):
    draft: str = Field(min_length=1, max_length=8000)


class DraftRegenerateRequest(BaseModel):
    feedback: str = Field(default="", max_length=1000)


class SimulateEventRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    message: str = Field(default="Hi — I wanted to reach out about your services.", max_length=2000)
    is_first: Optional[bool] = None


class DelegationInterpretation(BaseModel):
    interpreted_task: str = ""
    action: str = ""
    output: str = ""
    criteria_summary: str = ""
    contact_count: int = 0
    # Plain-English restatement shown in the confirmation box.
    plain_summary: str = ""
    # If Zilo could not interpret the request.
    needs_detail: bool = False
    detail_prompt: str = ""
    # Trust-ladder category this task maps to (e.g. "follow_ups").
    category: str = "follow_ups"
    # Specialist agent Zilo invokes in the background (e.g. "gmail", "customers").
    specialist_agent: Optional[str] = None
