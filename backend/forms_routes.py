"""
Form Builder — create shareable lead-capture forms.
Submissions auto-create contacts in the CRM.
"""
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _uid(user) -> str:
    return str(user["_id"])


def _make_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"


class CreateForm(BaseModel):
    title: str
    description: Optional[str] = None
    fields: Optional[List[Dict[str, Any]]] = None
    settings: Optional[Dict[str, Any]] = None
    branding: Optional[Dict[str, Any]] = None
    active: bool = True


class SubmitForm(BaseModel):
    data: Dict[str, Any]


def make_forms_router(db, user_dep):
    router = APIRouter(prefix="/forms", tags=["forms"])

    # ─────────────────────────────────────────────────────────────────────────
    # Public — serve & submit (NO auth — must be defined before /{form_id})
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/public/{slug}")
    async def get_public_form(slug: str):
        doc = await db.forms.find_one({"slug": slug, "active": True})
        if not doc:
            raise HTTPException(404, "Form not found or inactive")
        return {
            "id": str(doc["_id"]),
            "title": doc.get("title", ""),
            "description": doc.get("description", ""),
            "fields": doc.get("fields", []),
            "settings": {
                "success_message": doc.get("settings", {}).get(
                    "success_message", "Thank you! We'll be in touch soon."
                ),
            },
            "branding": doc.get("branding", {}),
        }

    @router.post("/public/{slug}/submit")
    async def submit_form(slug: str, body: SubmitForm):
        form = await db.forms.find_one({"slug": slug, "active": True})
        if not form:
            raise HTTPException(404, "Form not found")

        form_id = str(form["_id"])
        uid = form["user_id"]
        settings = form.get("settings", {})

        submission: Dict[str, Any] = {
            "_id": str(uuid.uuid4()),
            "form_id": form_id,
            "user_id": uid,
            "data": body.data,
            "created_at": datetime.utcnow(),
        }

        # Auto-create contact from submission data
        if settings.get("create_contact", True):
            name = (
                body.data.get("name")
                or body.data.get("full_name")
                or body.data.get("Name")
                or body.data.get("Full Name")
                or ""
            )
            phone = (
                body.data.get("phone")
                or body.data.get("Phone")
                or body.data.get("Phone Number")
                or body.data.get("mobile")
                or ""
            )
            email = (
                body.data.get("email")
                or body.data.get("Email")
                or body.data.get("Email Address")
                or ""
            )

            if name or phone or email:
                existing = None
                if phone:
                    existing = await db.contacts.find_one({"user_id": uid, "phone": phone})
                if not existing and email:
                    existing = await db.contacts.find_one({"user_id": uid, "email": email})

                if not existing:
                    contact_id = str(uuid.uuid4())
                    # Build a notes string from all submitted data
                    notes_lines = [f"{k}: {v}" for k, v in body.data.items() if v]
                    await db.contacts.insert_one({
                        "_id": contact_id,
                        "user_id": uid,
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "source": f"form:{form.get('title', '')}",
                        "notes": "Form: " + form.get("title", "") + "\n" + "\n".join(notes_lines),
                        "created_at": datetime.utcnow(),
                    })
                    submission["contact_id"] = contact_id
                else:
                    submission["contact_id"] = str(existing["_id"])

        await db.form_submissions.insert_one(submission)
        await db.forms.update_one({"_id": form_id}, {"$inc": {"response_count": 1}})

        return {
            "status": "ok",
            "message": settings.get("success_message", "Thank you! We'll be in touch soon."),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Authenticated CRUD
    # ─────────────────────────────────────────────────────────────────────────

    @router.post("")
    async def create_form(body: CreateForm, user=Depends(user_dep)):
        uid = _uid(user)
        slug = _make_slug(body.title)
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "title": body.title,
            "description": body.description or "",
            "slug": slug,
            "fields": body.fields if body.fields is not None else _default_fields(),
            "settings": body.settings or {
                "success_message": "Thank you! We'll be in touch soon.",
                "create_contact": True,
                "auto_whatsapp": False,
            },
            "branding": body.branding or {},
            "active": body.active,
            "response_count": 0,
            "created_at": datetime.utcnow(),
        }
        await db.forms.insert_one(doc)
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @router.get("")
    async def list_forms(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.forms.find({"user_id": uid}).sort("created_at", -1).to_list(100)
        for i in items:
            if hasattr(i.get("created_at"), "isoformat"):
                i["created_at"] = i["created_at"].isoformat()
        return {"forms": items}

    @router.get("/{form_id}")
    async def get_form(form_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        doc = await db.forms.find_one({"_id": form_id, "user_id": uid})
        if not doc:
            raise HTTPException(404, "Form not found")
        if hasattr(doc.get("created_at"), "isoformat"):
            doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @router.put("/{form_id}")
    async def update_form(form_id: str, body: CreateForm, user=Depends(user_dep)):
        uid = _uid(user)
        result = await db.forms.update_one(
            {"_id": form_id, "user_id": uid},
            {"$set": {
                "title": body.title,
                "description": body.description or "",
                "fields": body.fields if body.fields is not None else [],
                "settings": body.settings or {},
                "branding": body.branding or {},
                "active": body.active,
                "updated_at": datetime.utcnow(),
            }},
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Form not found")
        return {"status": "updated"}

    @router.delete("/{form_id}")
    async def delete_form(form_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        result = await db.forms.delete_one({"_id": form_id, "user_id": uid})
        if result.deleted_count == 0:
            raise HTTPException(404, "Form not found")
        await db.form_submissions.delete_many({"form_id": form_id})
        return {"status": "deleted"}

    @router.get("/{form_id}/responses")
    async def get_responses(form_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        form = await db.forms.find_one({"_id": form_id, "user_id": uid})
        if not form:
            raise HTTPException(404, "Form not found")
        items = await db.form_submissions.find(
            {"form_id": form_id}
        ).sort("created_at", -1).to_list(500)
        for i in items:
            if hasattr(i.get("created_at"), "isoformat"):
                i["created_at"] = i["created_at"].isoformat()
        return {"responses": items, "total": len(items)}

    return router


def _default_fields() -> list:
    return [
        {
            "id": str(uuid.uuid4())[:8],
            "type": "text",
            "label": "Full Name",
            "placeholder": "Your name",
            "required": True,
        },
        {
            "id": str(uuid.uuid4())[:8],
            "type": "phone",
            "label": "Phone Number",
            "placeholder": "+254...",
            "required": True,
        },
        {
            "id": str(uuid.uuid4())[:8],
            "type": "email",
            "label": "Email Address",
            "placeholder": "you@example.com",
            "required": False,
        },
        {
            "id": str(uuid.uuid4())[:8],
            "type": "textarea",
            "label": "Message",
            "placeholder": "What can we help you with?",
            "required": False,
        },
    ]
