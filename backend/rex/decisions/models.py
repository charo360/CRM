"""Decision Room data shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Strategy never auto-executes — capped at Drafter in trust ladder (ZILO.md pillar 3).
STRATEGY_CATEGORY = "strategy"
MAX_STRATEGY_RANK = "Drafter"

DecisionStatus = Literal["open", "decided", "archived"]


class DataFact(BaseModel):
    fact: str
    source: str
    confidence: Literal["high", "medium", "low"] = "medium"


class DataGap(BaseModel):
    gap: str
    connect: str = ""


class SparResult(BaseModel):
    founder_lean_detected: str = ""
    your_data: list[DataFact] = Field(default_factory=list)
    case_for_lean: list[str] = Field(default_factory=list)
    case_against: list[str] = Field(default_factory=list)
    blind_spots: list[str] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    pressure_question: str = ""
    zilo_note: str = "Your call. I won't choose."


class SparRequest(BaseModel):
    question: str = Field(min_length=8, max_length=2000)
    founder_lean: str = Field(default="", max_length=500)
    push_back_harder: bool = False
    session_id: str | None = None


class ThreadMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str = ""


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class NoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class NoteFeedbackRequest(BaseModel):
    feedback: Literal["up", "down"]


class DecideRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=2000)
    notes: str = Field(default="", max_length=4000)
    # Optional custom review schedule (days from decision). Defaults to 30/60/90.
    review_days: list[int] | None = None


class ScheduleRequest(BaseModel):
    review_days: list[int] = Field(min_length=1, max_length=6)


class DecisionSessionOut(BaseModel):
    id: str
    question: str
    founder_lean: str
    status: DecisionStatus
    spar: SparResult
    founder_decision: str | None = None
    push_back_count: int = 0
    created_at: str
    updated_at: str
    decided_at: str | None = None


def serialize_session(doc: dict[str, Any]) -> dict[str, Any]:
    spar_raw = doc.get("spar") or {}
    return {
        "id": str(doc["_id"]),
        "question": doc.get("question", ""),
        "founder_lean": doc.get("founder_lean", ""),
        "status": doc.get("status", "open"),
        "spar": spar_raw,
        "founder_decision": doc.get("founder_decision"),
        "founder_notes": doc.get("founder_notes"),
        "push_back_count": int(doc.get("push_back_count") or 0),
        "metrics_baseline": doc.get("metrics_baseline"),
        "outcome_checkpoints": doc.get("outcome_checkpoints") or [],
        "outcome_reports": doc.get("outcome_reports") or [],
        "pricing_simulation": doc.get("pricing_simulation") or [],
        "thread": doc.get("thread") or [],
        "founder_updates": doc.get("founder_updates") or [],
        "created_at": _iso(doc.get("created_at")),
        "updated_at": _iso(doc.get("updated_at")),
        "decided_at": _iso(doc.get("decided_at")) if doc.get("decided_at") else None,
    }


def _iso(v: Any) -> str:
    if v is None:
        return datetime.utcnow().isoformat() + "Z"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)
