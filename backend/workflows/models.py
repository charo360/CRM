"""
models.py — Pydantic schemas for the workflow engine.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ── Trigger ────────────────────────────────────────────────────────────────────

class WorkflowTrigger(BaseModel):
    type: Literal[
        "incoming_message",
        "intent_detected",
        "tag_added",
        "customer_created",
        "pipeline_stage_changed",
    ]
    condition: Optional[str] = None  # e.g. "intent == 'order'" or "always"


# ── Step ───────────────────────────────────────────────────────────────────────

class WorkflowStep(BaseModel):
    id: str  # e.g. "step_1", "step_2"
    action: str  # capability name from capabilities.py
    params: Dict[str, Any] = Field(default_factory=dict)
    # delay_minutes BEFORE this step fires (0 = immediate)
    delay_minutes: int = 0


# ── Workflow document ──────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    trigger: WorkflowTrigger
    steps: List[WorkflowStep] = Field(..., min_length=1)
    enabled: bool = True


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[WorkflowTrigger] = None
    steps: Optional[List[WorkflowStep]] = None
    enabled: Optional[bool] = None


# ── Runtime event ──────────────────────────────────────────────────────────────

class WorkflowEvent(BaseModel):
    """Passed to the engine when a trigger fires."""
    trigger_type: str
    user_id: Any           # MongoDB user _id
    customer_id: Any       # MongoDB customer _id (may be None for customer_created)
    from_number: str = ""  # WhatsApp number
    data: Dict[str, Any] = Field(default_factory=dict)
    # data keys by trigger_type:
    #   incoming_message  → {"message": str}
    #   intent_detected   → {"intent": str, "message": str}
    #   tag_added         → {"tag": str}
    #   pipeline_stage_changed → {"stage": str}
    #   customer_created  → {}


# ── Pending step (deferred execution) ─────────────────────────────────────────

class PendingStep(BaseModel):
    """Stored in workflow_pending_steps for deferred execution."""
    workflow_id: str
    workflow_run_id: str
    user_id: Any
    customer_id: Any
    from_number: str
    step: WorkflowStep
    # Remaining steps after this one (so we can chain them)
    remaining_steps: List[WorkflowStep] = Field(default_factory=list)
    execute_at: datetime
    status: Literal["pending", "done", "failed", "skipped"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    event_data: Dict[str, Any] = Field(default_factory=dict)
