"""NPS / Customer Feedback — surveys, NPS score, sentiment tracking."""
from __future__ import annotations
import logging, uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

def _tid(user): return user.get("business_id", user["_id"])

def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"): doc[f] = v.isoformat()
    return doc

def _nps_category(score: int) -> str:
    if score >= 9: return "promoter"
    if score >= 7: return "passive"
    return "detractor"

def _calc_nps(responses: list) -> float:
    if not responses: return 0.0
    total = len(responses)
    promoters = sum(1 for r in responses if r.get("nps_score", 0) >= 9)
    detractors = sum(1 for r in responses if r.get("nps_score", 0) <= 6)
    return round(((promoters - detractors) / total) * 100, 1)

def _derive_nps_score(survey: Dict[str, Any], answers: List[Dict[str, Any]], fallback: Optional[int]) -> Optional[int]:
    if fallback is not None:
        return fallback
    questions = {
        str(q.get("id") or q.get("_id") or q.get("question_id") or q.get("key")): q
        for q in survey.get("questions", [])
    }
    for item in answers:
        qid = str(item.get("question_id", ""))
        question = questions.get(qid)
        if not question or question.get("type") != "nps":
            continue
        try:
            score = int(item.get("answer"))
        except (TypeError, ValueError):
            continue
        return max(0, min(10, score))
    return None

class SurveyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str
    description: str = ""
    questions: List[Dict] = []   # [{id, text, type: "nps"|"rating"|"text"|"choice", options: []}]
    active: bool = True

class SurveyUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: Optional[str] = None
    description: Optional[str] = None
    questions: Optional[List[Dict]] = None
    active: Optional[bool] = None

class FeedbackResponse(BaseModel):
    survey_id: str
    customer_id: Optional[str] = None
    customer_name: str = ""
    customer_phone: str = ""
    nps_score: Optional[int] = None   # 0-10
    answers: List[Dict] = []          # [{question_id, answer}]
    comment: str = ""

def make_feedback_router(db, user_dep):
    router = APIRouter(prefix="/feedback", tags=["feedback"])

    # --- Public survey links ---
    @router.get("/public/surveys/{survey_id}")
    async def get_public_survey(survey_id: str):
        doc = await db.feedback_surveys.find_one({"_id": survey_id, "active": True})
        if not doc:
            raise HTTPException(404, "Survey not found or inactive")
        public = _ser(doc)
        public.pop("user_id", None)
        return public

    @router.post("/public/responses")
    async def submit_public_response(payload: FeedbackResponse):
        survey = await db.feedback_surveys.find_one({"_id": payload.survey_id, "active": True})
        if not survey:
            raise HTTPException(404, "Survey not found or inactive")
        tid = survey["user_id"]
        now = datetime.utcnow()
        nps_score = _derive_nps_score(survey, payload.answers, payload.nps_score)
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "survey_id": payload.survey_id,
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name,
            "customer_phone": payload.customer_phone,
            "nps_score": nps_score,
            "nps_category": _nps_category(nps_score) if nps_score is not None else None,
            "answers": payload.answers,
            "comment": payload.comment,
            "source": "public_link",
            "created_at": now, "updated_at": now,
        }
        await db.feedback_responses.insert_one(doc)
        await db.feedback_surveys.update_one(
            {"_id": payload.survey_id}, {"$inc": {"response_count": 1}}
        )
        return _ser(doc)

    # --- Surveys ---
    @router.get("/surveys")
    async def list_surveys(active: Optional[bool] = None, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if active is not None: q["active"] = active
        docs = await db.feedback_surveys.find(q, sort=[("created_at", -1)]).to_list(100)
        return [_ser(d) for d in docs]

    @router.post("/surveys")
    async def create_survey(payload: SurveyCreate, user=user_dep):
        tid = _tid(user)
        now = datetime.utcnow()
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            **payload.model_dump(),
            "response_count": 0,
            "created_at": now, "updated_at": now,
        }
        await db.feedback_surveys.insert_one(doc)
        return _ser(doc)

    @router.get("/surveys/{survey_id}")
    async def get_survey(survey_id: str, user=user_dep):
        doc = await db.feedback_surveys.find_one({"_id": survey_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Survey not found")
        return _ser(doc)

    @router.put("/surveys/{survey_id}")
    async def update_survey(survey_id: str, payload: SurveyUpdate, user=user_dep):
        doc = await db.feedback_surveys.find_one({"_id": survey_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Survey not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        for f, v in payload.model_dump(exclude_none=True).items():
            upd[f] = v
        await db.feedback_surveys.update_one({"_id": survey_id}, {"$set": upd})
        updated = await db.feedback_surveys.find_one({"_id": survey_id})
        return _ser(updated)

    @router.delete("/surveys/{survey_id}")
    async def delete_survey(survey_id: str, user=user_dep):
        doc = await db.feedback_surveys.find_one({"_id": survey_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Survey not found")
        await db.feedback_surveys.delete_one({"_id": survey_id})
        await db.feedback_responses.delete_many({"survey_id": survey_id, "user_id": _tid(user)})
        return {"deleted": True}

    # --- Responses ---
    @router.get("/responses")
    async def list_responses(survey_id: Optional[str] = None, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if survey_id: q["survey_id"] = survey_id
        docs = await db.feedback_responses.find(q, sort=[("created_at", -1)]).to_list(500)
        return [_ser(d) for d in docs]

    @router.post("/responses")
    async def submit_response(payload: FeedbackResponse, user=user_dep):
        tid = _tid(user)
        survey = await db.feedback_surveys.find_one({"_id": payload.survey_id, "user_id": tid})
        if not survey: raise HTTPException(404, "Survey not found")
        now = datetime.utcnow()
        nps_score = _derive_nps_score(survey, payload.answers, payload.nps_score)
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "survey_id": payload.survey_id,
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name,
            "customer_phone": payload.customer_phone,
            "nps_score": nps_score,
            "nps_category": _nps_category(nps_score) if nps_score is not None else None,
            "answers": payload.answers,
            "comment": payload.comment,
            "created_at": now, "updated_at": now,
        }
        await db.feedback_responses.insert_one(doc)
        await db.feedback_surveys.update_one(
            {"_id": payload.survey_id}, {"$inc": {"response_count": 1}}
        )
        return _ser(doc)

    @router.delete("/responses/{response_id}")
    async def delete_response(response_id: str, user=user_dep):
        doc = await db.feedback_responses.find_one({"_id": response_id, "user_id": _tid(user)})
        if not doc: raise HTTPException(404, "Response not found")
        await db.feedback_responses.delete_one({"_id": response_id})
        return {"deleted": True}

    # --- NPS Dashboard ---
    @router.get("/nps")
    async def nps_dashboard(survey_id: Optional[str] = None, user=user_dep):
        tid = _tid(user)
        q: Dict[str, Any] = {"user_id": tid, "nps_score": {"$ne": None}}
        if survey_id: q["survey_id"] = survey_id
        docs = await db.feedback_responses.find(q).to_list(2000)
        nps = _calc_nps(docs)
        total = len(docs)
        promoters = sum(1 for d in docs if d.get("nps_score", 0) >= 9)
        passives = sum(1 for d in docs if 7 <= d.get("nps_score", 0) <= 8)
        detractors = sum(1 for d in docs if d.get("nps_score", 0) <= 6)
        recent = sorted(docs, key=lambda x: x.get("created_at", datetime.min), reverse=True)[:10]
        return {
            "nps_score": nps,
            "total_responses": total,
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "promoter_pct": round(promoters / total * 100, 1) if total else 0,
            "detractor_pct": round(detractors / total * 100, 1) if total else 0,
            "recent_comments": [{"name": r.get("customer_name",""), "score": r.get("nps_score"), "comment": r.get("comment","")} for r in recent if r.get("comment")],
        }

    return router
