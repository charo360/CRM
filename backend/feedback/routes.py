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

    # --- Surveys ---
    @router.get("/surveys")
    async def list_surveys(active: Optional[bool] = None, user=user_dep):
        q: Dict[str, Any] = {"user_id": _tid(user)}
        if active is not None: q["active"] = active
        docs = await db.feedback_surveys.find(q, sort=[("created_at", -1)]).to_list(100)
        return [_ser(d) for d in docs]

    @router.post("/surveys")
    async def create_survey(payload: SurveyCreate, user=user_dep):
        import re
        tid = _tid(user)
        now = datetime.utcnow()
        survey_id = str(uuid.uuid4())
        form_id = str(uuid.uuid4())

        # Generate unique slug for public page access
        slug = re.sub(r"[^a-z0-9]+", "-", payload.title.lower()).strip("-")
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        # Standard high-converting NPS fields
        fields = [
            {"id": str(uuid.uuid4())[:8], "type": "text", "label": "Full Name", "placeholder": "Your name", "required": True},
            {"id": str(uuid.uuid4())[:8], "type": "phone", "label": "Phone Number", "placeholder": "+1...", "required": True},
            {"id": str(uuid.uuid4())[:8], "type": "dropdown", "label": "Recommendation Score", "placeholder": "Select score (0 to 10)", "required": True, "options": [str(x) for x in range(11)]},
            {"id": str(uuid.uuid4())[:8], "type": "textarea", "label": "Comments", "placeholder": "What can we do to improve?", "required": False}
        ]

        # Resolve primary color settings if possible
        header_bg = "#0f172a"
        button_bg = "#0f172a"
        try:
            brand_connections = await db.brand_settings.find_one({"user_id": tid})
            if brand_connections and brand_connections.get("brand_primary_color"):
                header_bg = brand_connections["brand_primary_color"]
                button_bg = brand_connections["brand_primary_color"]
        except Exception:
            pass

        # Create editable form record in main Forms collection
        await db.forms.insert_one({
            "_id": form_id,
            "user_id": tid,
            "title": payload.title,
            "description": payload.description or "",
            "slug": slug,
            "fields": fields,
            "settings": {
                "success_message": "Thank you! We'll be in touch soon.",
                "create_contact": True,
                "auto_whatsapp": False,
                "is_nps": True
            },
            "branding": {
                "logo_url": "",
                "header_bg": header_bg,
                "header_text": "#ffffff",
                "button_bg": button_bg,
                "button_text": "#ffffff",
                "page_bg": "#f8fafc"
            },
            "active": payload.active,
            "response_count": 0,
            "created_at": now
        })

        doc = {
            "_id": survey_id,
            "user_id": tid,
            "form_id": form_id,
            "slug": slug,
            "title": payload.title,
            "description": payload.description,
            "questions": payload.questions,
            "active": payload.active,
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
        
        # Clean up linked forms document & submissions
        form_id = doc.get("form_id")
        if form_id:
            try:
                await db.forms.delete_one({"_id": form_id, "user_id": _tid(user)})
                await db.form_submissions.delete_many({"form_id": form_id, "user_id": _tid(user)})
            except Exception as e:
                logger.error("[delete_survey] Failed to delete linked forms data: %s", str(e))

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
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "survey_id": payload.survey_id,
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name,
            "customer_phone": payload.customer_phone,
            "nps_score": payload.nps_score,
            "nps_category": _nps_category(payload.nps_score) if payload.nps_score is not None else None,
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
