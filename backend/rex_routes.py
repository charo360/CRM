"""
Rex HTTP routes.

Currently exposes Phase 11 Day 0 Onboarding. More Rex surfaces
(Briefing, Notebook, Journal, Ledger) will mount here as later
phases get wired up.

Session storage is in-memory keyed by user_id — fine for the
Improved_AI test branch. Restart-safe persistence is a later concern.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rex.onboarding import (
    OnboardingEngine,
    OnboardingState,
    CommunicationChannel,
    DirectnessLevel,
    MockDataScanner,
)

logger = logging.getLogger(__name__)


# ── Session store ─────────────────────────────────────────────────────────

_ENGINES: dict[str, OnboardingEngine] = {}


def _get_engine(user_id: str) -> OnboardingEngine:
    engine = _ENGINES.get(user_id)
    if engine is None:
        # MockDataScanner produces realistic placeholder findings so the
        # "I see it" moment lands even before real CRM data is wired in.
        engine = OnboardingEngine(scanner=MockDataScanner())
        _ENGINES[user_id] = engine
    return engine


def _reset_engine(user_id: str) -> OnboardingEngine:
    engine = OnboardingEngine(scanner=MockDataScanner())
    _ENGINES[user_id] = engine
    return engine


# ── Request/response models ───────────────────────────────────────────────

class StartResponse(BaseModel):
    welcome: str
    state: str
    question: Optional[str] = None


class AnswerRequest(BaseModel):
    value: str


class AnswerResponse(BaseModel):
    next_prompt: str
    state: str
    question: Optional[str] = None
    i_see_it: Optional[str] = None
    complete: bool = False


class StateResponse(BaseModel):
    state: str
    question: Optional[str] = None
    complete: bool


class PreferencesResponse(BaseModel):
    preferences: dict


# ── Router factory ────────────────────────────────────────────────────────

def init_rex_routes(get_current_user) -> APIRouter:
    """Build the Rex router with the host app's auth dependency."""
    router = APIRouter(prefix="/api/rex", tags=["rex"])

    @router.post("/onboarding/start", response_model=StartResponse)
    async def onboarding_start(user=Depends(get_current_user)):
        engine = _reset_engine(str(user.get("_id") or user.get("id")))
        welcome = engine.start()
        return StartResponse(
            welcome=welcome,
            state=engine.state.value,
            question=engine.get_current_question(),
        )

    @router.get("/onboarding/state", response_model=StateResponse)
    async def onboarding_state(user=Depends(get_current_user)):
        engine = _get_engine(str(user.get("_id") or user.get("id")))
        return StateResponse(
            state=engine.state.value,
            question=engine.get_current_question(),
            complete=engine.state in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE),
        )

    @router.post("/onboarding/answer/{question_num}", response_model=AnswerResponse)
    async def onboarding_answer(question_num: int, body: AnswerRequest, user=Depends(get_current_user)):
        engine = _get_engine(str(user.get("_id") or user.get("id")))
        value = (body.value or "").strip()

        try:
            if question_num == 1:
                prompt = engine.answer_question_1(value)
            elif question_num == 2:
                prompt = engine.answer_question_2(value)
            elif question_num == 3:
                prompt = engine.answer_question_3(value)
            elif question_num == 4:
                try:
                    channel = CommunicationChannel(value.lower())
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Unknown channel: {value}")
                prompt = engine.answer_question_4(channel)
            elif question_num == 5:
                try:
                    directness = DirectnessLevel(value.lower())
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Unknown directness: {value}")
                prompt = engine.answer_question_5(directness)
            elif question_num == 6:
                prompt = engine.answer_question_6(value)
            else:
                raise HTTPException(status_code=400, detail="question_num must be 1-6")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        complete = engine.state in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE)
        i_see_it = None
        if engine.i_see_it is not None:
            i_see_it = engine.i_see_it.rex_response

        return AnswerResponse(
            next_prompt=prompt,
            state=engine.state.value,
            question=engine.get_current_question(),
            i_see_it=i_see_it,
            complete=complete,
        )

    @router.get("/onboarding/preferences", response_model=PreferencesResponse)
    async def onboarding_preferences(user=Depends(get_current_user)):
        engine = _get_engine(str(user.get("_id") or user.get("id")))
        if engine.state not in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE):
            raise HTTPException(status_code=409, detail="Onboarding not complete yet")
        return PreferencesResponse(preferences=engine.get_preferences())

    @router.post("/onboarding/reset")
    async def onboarding_reset(user=Depends(get_current_user)):
        engine = _reset_engine(str(user.get("_id") or user.get("id")))
        return {"ok": True, "state": engine.state.value}

    return router
