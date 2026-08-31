"""NPS / Customer Feedback — surveys, NPS score, sentiment tracking."""
from __future__ import annotations
import logging, os, uuid
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
    request_token: Optional[str] = None

def make_feedback_router(db, user_dep):
    router = APIRouter(prefix="/feedback", tags=["feedback"])

    def _phone_key(value: Optional[str]) -> str:
        """Compare phone numbers reliably across +, spaces, and dashes."""
        return "".join(character for character in (value or "") if character.isdigit())

    def _public_survey_url(survey_id: str, request_token: Optional[str] = None) -> str:
        base_url = (
            os.environ.get("PUBLIC_WEB_URL")
            or os.environ.get("WEB_APP_URL")
            or os.environ.get("FRONTEND_URL")
            or "https://zilo.pro"
        ).rstrip("/")
        url = f"{base_url}/feedback/survey/{survey_id}"
        return f"{url}?request={request_token}" if request_token else url

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

        # A link sent from a Customer Profile contains a private token. Resolve
        # the customer server-side so a public form response is recorded against
        # the right CRM customer without exposing or trusting a customer id.
        delivery = None
        if payload.request_token:
            delivery = await db.feedback_deliveries.find_one({
                "token": payload.request_token,
                "survey_id": payload.survey_id,
                "user_id": tid,
            })
            if not delivery:
                raise HTTPException(404, "Survey link is invalid or expired")
        # Compatibility for an already-deployed survey page while it receives
        # the token-aware update. The recipient's phone is still required by
        # that page and lets us safely match the most recent delivery.
        if not delivery and payload.customer_phone:
            submitted_phone = _phone_key(payload.customer_phone)
            if submitted_phone:
                recent_deliveries = await db.feedback_deliveries.find(
                    {"survey_id": payload.survey_id, "user_id": tid},
                    sort=[("created_at", -1)],
                ).to_list(100)
                delivery = next(
                    (
                        item for item in recent_deliveries
                        if _phone_key(item.get("customer_phone")) == submitted_phone
                    ),
                    None,
                )

        now = datetime.utcnow()
        nps_score = _derive_nps_score(survey, payload.answers, payload.nps_score)
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "survey_id": payload.survey_id,
            "customer_id": delivery.get("customer_id") if delivery else payload.customer_id,
            "customer_name": delivery.get("customer_name", "") if delivery else payload.customer_name,
            "customer_phone": delivery.get("customer_phone", "") if delivery else payload.customer_phone,
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
        if delivery:
            await db.feedback_deliveries.update_one(
                {"_id": delivery["_id"]},
                {"$set": {"responded_at": now, "response_id": doc["_id"]}},
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

    @router.get("/customer/{customer_id}")
    async def get_customer_responses(customer_id: str, user=user_dep):
        tid = _tid(user)
        customer = await db.customers.find_one({"_id": customer_id, "user_id": tid})
        if not customer:
            raise HTTPException(404, "Customer not found")
        docs = await db.feedback_responses.find(
            {"user_id": tid, "customer_id": customer_id},
            sort=[("created_at", -1)],
        ).to_list(100)
        return [_ser(d) for d in docs]

    @router.post("/surveys/{survey_id}/send")
    async def send_survey_link(survey_id: str, payload: Dict[str, str], user=user_dep):
        """Send one customer a private, tracked feedback link over WhatsApp."""
        tid = _tid(user)
        customer_id = (payload.get("customer_id") or "").strip()
        if not customer_id:
            raise HTTPException(400, "Customer is required")

        survey = await db.feedback_surveys.find_one({"_id": survey_id, "user_id": tid, "active": True})
        if not survey:
            raise HTTPException(404, "Active survey not found")
        customer = await db.customers.find_one({"_id": customer_id, "user_id": tid})
        if not customer:
            raise HTTPException(404, "Customer not found")
        phone = (customer.get("phone_number") or customer.get("phone") or "").strip()
        if not phone:
            raise HTTPException(400, "This customer does not have a WhatsApp phone number")

        now = datetime.utcnow()
        token = uuid.uuid4().hex
        url = _public_survey_url(survey_id, token)
        delivery = {
            "_id": str(uuid.uuid4()),
            "token": token,
            "user_id": tid,
            "survey_id": survey_id,
            "customer_id": customer_id,
            "customer_name": customer.get("name", ""),
            "customer_phone": phone,
            "url": url,
            "status": "sending",
            "created_at": now,
        }
        await db.feedback_deliveries.insert_one(delivery)

        business = await db.users.find_one({"_id": tid}, {"business_name": 1, "owner_name": 1}) or {}
        business_name = business.get("business_name") or business.get("owner_name") or "us"
        greeting = customer.get("name") or "there"
        message = (
            f"Hi {greeting}, thank you for choosing {business_name}. "
            f"We would appreciate your feedback: {url}"
        )
        try:
            from whatsapp_service import get_whatsapp_service
            result = await get_whatsapp_service(db).send_message(
                user_id=tid,
                to_number=phone,
                message=message,
                customer_name=customer.get("name"),
                send_context="feedback_survey",
            )
        except Exception as exc:
            await db.feedback_deliveries.update_one(
                {"_id": delivery["_id"]}, {"$set": {"status": "failed", "error": str(exc), "updated_at": datetime.utcnow()}},
            )
            logger.exception("Failed to send feedback survey")
            raise HTTPException(502, "Could not send the survey over WhatsApp")

        if result.get("status") in {"error", "limit_reached"}:
            detail = result.get("message") or "WhatsApp did not accept the survey message"
            await db.feedback_deliveries.update_one(
                {"_id": delivery["_id"]}, {"$set": {"status": "failed", "error": detail, "updated_at": datetime.utcnow()}},
            )
            raise HTTPException(429 if result.get("status") == "limit_reached" else 502, detail)

        await db.feedback_deliveries.update_one(
            {"_id": delivery["_id"]},
            {"$set": {"status": "sent", "sent_at": datetime.utcnow(), "message_id": result.get("message_id")}},
        )
        return {"status": "sent", "url": url, "delivery_id": delivery["_id"], "message_id": result.get("message_id")}

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
