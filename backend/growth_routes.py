"""
Growth Suite Routes — Daily Digest, AI Follow-up Autopilot, Deal Room,
Competitor Intelligence, Voice Input, Client Portal
"""
from __future__ import annotations

import logging
import uuid
import os
import tempfile
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AutopilotAction(BaseModel):
    customer_id: str
    action: str
    message: Optional[str] = None


class CreateDealRoom(BaseModel):
    title: str
    document_id: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    message: Optional[str] = None
    valid_days: Optional[int] = 30


class DealRoomUpdate(BaseModel):
    status: Optional[str] = None


class CompetitorAdd(BaseModel):
    name: str
    website: Optional[str] = None
    industry: Optional[str] = None



def _uid(user) -> str:
    return str(user["_id"])


def make_growth_router(db, user_dep):
    router = APIRouter(prefix="/growth", tags=["growth"])

    # ════════════════════════════════════════════════════════════════════════
    # PUBLIC endpoints (no auth) — must be defined BEFORE auth-guarded ones
    # ════════════════════════════════════════════════════════════════════════

    @router.get("/deal/{token}/view")
    async def view_deal_room(token: str, request: Request):
        room = await db.deal_rooms.find_one({"token": token})
        if not room:
            raise HTTPException(404, "Deal not found")
        if room.get("expires_at") and room["expires_at"] < datetime.utcnow():
            raise HTTPException(410, "This link has expired")
        await db.deal_rooms.update_one(
            {"token": token},
            {
                "$inc": {"views": 1},
                "$set": {"status": "viewed" if room.get("status") == "sent" else room.get("status"), "updated_at": datetime.utcnow()},
                "$push": {"view_events": {"at": datetime.utcnow(), "ip": request.client.host if request.client else ""}},
            },
        )
        return {
            "title": room.get("title"),
            "file_url": room.get("file_url"),
            "recipient_name": room.get("recipient_name"),
            "token": token,
            "status": room.get("status"),
        }

    @router.post("/deal/{token}/sign")
    async def sign_deal(token: str):
        room = await db.deal_rooms.find_one({"token": token})
        if not room:
            raise HTTPException(404, "Deal not found")
        await db.deal_rooms.update_one(
            {"token": token},
            {"$set": {"status": "signed", "signed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
        )
        return {"status": "signed"}

    @router.get("/portal/{customer_id}")
    async def get_client_portal(customer_id: str):
        """
        Public endpoint — no auth required.
        Returns all portal data for a customer in one call.
        Security: customer_id is a UUID (hard to guess); data is scoped to that customer's business.
        """
        customer = await db.customers.find_one({"_id": customer_id})
        if not customer:
            raise HTTPException(404, "Client not found")

        user_id = customer.get("user_id")

        # Orders for this customer
        orders_cursor = db.orders.find({"user_id": user_id, "customer_id": customer_id}).sort("created_at", -1)
        orders = await orders_cursor.to_list(50)
        for o in orders:
            o["_id"] = str(o["_id"])

        # Invoices for this customer
        invoices_cursor = db.invoices.find({"user_id": user_id, "customer_id": customer_id}).sort("created_at", -1)
        invoices = await invoices_cursor.to_list(50)
        for inv in invoices:
            inv["_id"] = str(inv["_id"])

        # Proposals (deal rooms) for this customer — exclude declined
        proposals_cursor = db.deal_rooms.find(
            {"user_id": user_id, "customer_id": customer_id, "status": {"$ne": "declined"}}
        ).sort("created_at", -1)
        proposals = await proposals_cursor.to_list(20)
        for p in proposals:
            p["_id"] = str(p["_id"])

        return {
            "customer": {"name": customer.get("name", "Client"), "email": customer.get("email")},
            "orders": orders,
            "invoices": invoices,
            "proposals": proposals,
        }

    # ════════════════════════════════════════════════════════════════════════
    # 1. DAILY DIGEST
    # ════════════════════════════════════════════════════════════════════════

    @router.get("/digest")
    async def get_daily_digest(user=Depends(user_dep)):
        uid = _uid(user)
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Revenue today
        orders_today = await db.orders.find({
            "user_id": uid,
            "created_at": {"$gte": today_start},
            "payment_status": "Paid",
        }).to_list(500)
        revenue_today = sum(o.get("total_amount", 0) for o in orders_today)

        # Revenue yesterday (for delta)
        yesterday_start = today_start - timedelta(days=1)
        orders_yesterday = await db.orders.find({
            "user_id": uid,
            "created_at": {"$gte": yesterday_start, "$lt": today_start},
            "payment_status": "Paid",
        }).to_list(500)
        revenue_yesterday = sum(o.get("total_amount", 0) for o in orders_yesterday)
        revenue_delta = revenue_today - revenue_yesterday

        # Cold customers (no contact 30+ days)
        cutoff_30 = now - timedelta(days=30)
        cold_customers = await db.customers.find({
            "user_id": uid,
            "$or": [
                {"last_contacted": {"$lt": cutoff_30}},
                {"last_contacted": {"$exists": False}},
            ],
            "is_customer": {"$ne": False},
        }).to_list(200)

        # Top products this month
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        orders_month = await db.orders.find({
            "user_id": uid,
            "created_at": {"$gte": month_start},
        }).to_list(1000)
        product_counts: Dict[str, int] = {}
        for o in orders_month:
            for item in (o.get("items") or []):
                name = item.get("product_name") or item.get("name") or "Unknown"
                product_counts[name] = product_counts.get(name, 0) + item.get("quantity", 1)
        top_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Follow-ups due today
        today_end = now.replace(hour=23, minute=59, second=59)
        followups_due = await db.followups.find({
            "user_id": uid,
            "status": "pending",
            "reminder_date": {"$gte": today_start, "$lte": today_end},
        }).to_list(50)
        for fu in followups_due:
            c = await db.customers.find_one({"_id": fu.get("customer_id")})
            fu["customer_name"] = c.get("name", "Unknown") if c else "Unknown"
            fu["_id"] = str(fu["_id"])

        # New customers (48h)
        new_customers = await db.customers.find({
            "user_id": uid,
            "created_at": {"$gte": now - timedelta(hours=48)},
        }).to_list(20)

        # Overdue follow-ups
        overdue = await db.followups.find({
            "user_id": uid,
            "status": "pending",
            "reminder_date": {"$lt": today_start},
        }).to_list(50)
        for fu in overdue:
            c = await db.customers.find_one({"_id": fu.get("customer_id")})
            fu["customer_name"] = c.get("name", "Unknown") if c else "Unknown"
            fu["days_overdue"] = (now - fu["reminder_date"]).days if fu.get("reminder_date") else 0
            fu["_id"] = str(fu["_id"])

        return {
            "generated_at": now.isoformat(),
            "revenue": {
                "today": revenue_today,
                "yesterday": revenue_yesterday,
                "delta": revenue_delta,
                "orders_today": len(orders_today),
            },
            "cold_customers": {
                "count": len(cold_customers),
                "items": [{"id": str(c["_id"]), "name": c.get("name", ""), "last_contacted": str(c.get("last_contacted", ""))} for c in cold_customers[:5]],
            },
            "top_products": [{"name": n, "count": c} for n, c in top_products],
            "followups_due_today": {
                "count": len(followups_due),
                "items": followups_due[:5],
            },
            "overdue_followups": {
                "count": len(overdue),
                "items": sorted(overdue, key=lambda x: x.get("days_overdue", 0), reverse=True)[:5],
            },
            "new_customers": {
                "count": len(new_customers),
                "items": [{"id": str(c["_id"]), "name": c.get("name", "")} for c in new_customers[:5]],
            },
        }

    # ════════════════════════════════════════════════════════════════════════
    # 2. DAILY PULSE (existing frontend endpoint — now wired)
    # ════════════════════════════════════════════════════════════════════════

    @router.get("/pulse/preview")
    async def get_pulse_preview(user=Depends(user_dep)):
        uid = _uid(user)
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        orders_today = await db.orders.find({
            "user_id": uid, "created_at": {"$gte": today_start}
        }).to_list(200)
        paid_today = [o for o in orders_today if o.get("payment_status") == "Paid"]
        revenue = sum(o.get("total_amount", 0) for o in paid_today)

        cold = await db.customers.count_documents({
            "user_id": uid,
            "$or": [
                {"last_contacted": {"$lt": now - timedelta(days=30)}},
                {"last_contacted": {"$exists": False}},
            ],
        })
        pending_followups = await db.followups.count_documents({
            "user_id": uid, "status": "pending",
            "reminder_date": {"$lte": now},
        })

        biz = await db.users.find_one({"_id": uid})
        biz_name = (biz or {}).get("business_name") or "your business"

        parts = []
        if paid_today:
            parts.append(f"{len(paid_today)} sale{'s' if len(paid_today) != 1 else ''} today ({revenue:,.0f} revenue)")
        if pending_followups:
            parts.append(f"{pending_followups} follow-up{'s' if pending_followups != 1 else ''} due")
        if cold:
            parts.append(f"{cold} customer{'s' if cold != 1 else ''} need re-engagement")
        if not parts:
            parts.append("All caught up — no urgent items today")

        message = f"📊 {biz_name}: " + " · ".join(parts) + "."
        return {"message": message, "summary": message}

    # ════════════════════════════════════════════════════════════════════════
    # 3. AI FOLLOW-UP AUTOPILOT
    # ════════════════════════════════════════════════════════════════════════

    @router.get("/autopilot/queue")
    async def get_autopilot_queue(user=Depends(user_dep)):
        """Return cold leads with AI-drafted follow-up messages ready to approve."""
        uid = _uid(user)
        now = datetime.utcnow()
        cutoff = now - timedelta(days=30)

        cold = await db.customers.find({
            "user_id": uid,
            "$or": [
                {"last_contacted": {"$lt": cutoff}},
                {"last_contacted": {"$exists": False}},
            ],
            "is_customer": {"$ne": False},
        }).to_list(50)

        biz = await db.users.find_one({"_id": uid})
        biz_name = (biz or {}).get("business_name") or "us"

        queue = []
        for c in cold:
            name = c.get("name", "there")
            first_name = name.split()[0] if name else "there"
            days_since = (now - c["last_contacted"]).days if c.get("last_contacted") else 60

            # AI-style personalized draft based on customer data
            products = c.get("last_product") or c.get("top_product") or ""
            if products:
                draft = f"Hi {first_name}! 👋 Hope you're doing well. It's been a while since your last order of {products}. We'd love to have you back — any questions or anything we can help with?"
            else:
                draft = f"Hi {first_name}! 👋 It's been {days_since} days since we last connected. We've got some great things at {biz_name} — would love to catch up when you have a moment!"

            # Note: autopilot_queue collection may not exist yet — ignore if not present
            try:
                existing = await db.autopilot_queue.find_one({
                    "user_id": uid, "customer_id": str(c["_id"]), "status": "pending"
                })
            except:
                existing = None
            if existing:
                continue

            queue.append({
                "customer_id": str(c["_id"]),
                "customer_name": c.get("name", ""),
                "phone": c.get("phone", ""),
                "days_since_contact": days_since,
                "draft_message": draft,
                "channel": "whatsapp" if c.get("phone") else "email",
            })

        return {"queue": queue[:20], "total": len(queue)}

    @router.post("/autopilot/action")
    async def autopilot_action(body: AutopilotAction, user=Depends(user_dep)):
        """Approve (send), skip, or save-edited message for a queued follow-up."""
        uid = _uid(user)

        customer = await db.customers.find_one({"_id": body.customer_id, "user_id": uid})
        if not customer:
            raise HTTPException(404, "Customer not found")

        if body.action == "approve" or body.action == "edit":
            msg = body.message or ""
            # Create a followup record so it shows up in the followups page
            await db.followups.insert_one({
                "_id": str(uuid.uuid4()),
                "user_id": uid,
                "customer_id": body.customer_id,
                "notes": msg,
                "status": "sent",
                "source": "autopilot",
                "created_at": datetime.utcnow(),
                "reminder_date": datetime.utcnow(),
            })
            # Update customer last_contacted
            await db.customers.update_one(
                {"_id": body.customer_id},
                {"$set": {"last_contacted": datetime.utcnow(), "last_autopilot_msg": msg}},
            )
            return {"status": "sent", "message": msg}

        elif body.action == "skip":
            # Mark as snoozed for 7 days
            await db.customers.update_one(
                {"_id": body.customer_id},
                {"$set": {"autopilot_snoozed_until": datetime.utcnow() + timedelta(days=7)}},
            )
            return {"status": "skipped"}

        raise HTTPException(400, "Invalid action")

    # ════════════════════════════════════════════════════════════════════════
    # 4. DEAL ROOM — shareable proposal link with view tracking
    # ════════════════════════════════════════════════════════════════════════

    @router.post("/deal-room")
    async def create_deal_room(body: CreateDealRoom, user=Depends(user_dep)):
        uid = _uid(user)

        file_url = body.file_url or ""
        if body.document_id:
            doc = await db.design_templates.find_one({"_id": body.document_id, "user_id": uid})
            if doc:
                file_url = doc.get("file_url", "")

        token = str(uuid.uuid4()).replace("-", "")[:16]
        now = datetime.utcnow()
        deal = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "document_id": body.document_id,
            "title": body.title,
            "description": body.description,
            "token": token,
            "recipient_name": body.recipient_name,
            "recipient_email": body.recipient_email,
            "file_url": file_url,
            "status": "sent",
            "views": 0,
            "view_events": [],
            "expires_at": now + timedelta(days=body.expires_days),
            "created_at": now,
            "updated_at": now,
        }
        await db.deal_rooms.insert_one(deal)
        deal["_id"] = str(deal["_id"])
        return {"deal_room": deal, "share_url": f"/deal/{token}"}

    @router.get("/deal-room")
    async def list_deal_rooms(user=Depends(user_dep), customer_id: Optional[str] = None):
        uid = _uid(user)
        query: Dict[str, Any] = {"user_id": uid}
        if customer_id:
            query["customer_id"] = customer_id
        rooms = await db.deal_rooms.find(query).sort("created_at", -1).to_list(100)
        for r in rooms:
            r["_id"] = str(r["_id"])
        return {"deal_rooms": rooms}

    @router.get("/deal-room/{deal_id}")
    async def get_deal_room(deal_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        room = await db.deal_rooms.find_one({"_id": deal_id, "user_id": uid})
        if not room:
            raise HTTPException(404, "Deal room not found")
        room["_id"] = str(room["_id"])
        return room

    @router.patch("/deal-room/{deal_id}")
    async def update_deal_room(deal_id: str, body: DealRoomUpdate, user=Depends(user_dep)):
        uid = _uid(user)
        update: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if body.status:
            update["status"] = body.status
        await db.deal_rooms.update_one({"_id": deal_id, "user_id": uid}, {"$set": update})
        return {"status": "updated"}

    # ════════════════════════════════════════════════════════════════════════
    # 5. COMPETITOR INTELLIGENCE FEED
    # ════════════════════════════════════════════════════════════════════════

    @router.post("/competitors")
    async def add_competitor(body: CompetitorAdd, user=Depends(user_dep)):
        uid = _uid(user)
        existing = await db.competitors.find_one({"user_id": uid, "name": body.name})
        if existing:
            return {"competitor": existing}
        comp = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "name": body.name,
            "website": body.website,
            "industry": body.industry,
            "created_at": datetime.utcnow(),
        }
        await db.competitors.insert_one(comp)
        return {"competitor": comp}

    @router.get("/competitors")
    async def list_competitors(user=Depends(user_dep)):
        uid = _uid(user)
        comps = await db.competitors.find({"user_id": uid}).to_list(50)
        for c in comps:
            c["_id"] = str(c["_id"])
        return {"competitors": comps}

    @router.delete("/competitors/{comp_id}")
    async def delete_competitor(comp_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        await db.competitors.delete_one({"_id": comp_id, "user_id": uid})
        return {"status": "deleted"}

    @router.get("/competitors/insights")
    async def get_competitor_insights(user=Depends(user_dep)):
        """Get latest cached competitor insights or trigger a fresh analysis."""
        uid = _uid(user)
        week_ago = datetime.utcnow() - timedelta(days=7)
        insights = await db.competitor_insights.find({
            "user_id": uid,
            "created_at": {"$gte": week_ago},
        }).sort("created_at", -1).to_list(20)
        for i in insights:
            i["_id"] = str(i["_id"])
        return {"insights": insights}

    @router.post("/competitors/insights/refresh")
    async def refresh_competitor_insights(user=Depends(user_dep)):
        """Trigger AI web search for each competitor and store insights."""
        uid = _uid(user)
        comps = await db.competitors.find({"user_id": uid}).to_list(10)
        if not comps:
            raise HTTPException(400, "No competitors added yet. Add competitors first.")

        import httpx
        results = []
        for comp in comps:
            name = comp.get("name", "")
            website = comp.get("website", "")
            query = f"{name} {website} latest news pricing promotions".strip()
            search_results: list = []
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    search_results = list(ddgs.text(query, max_results=5))
                snippets = [f"• {r.get('title', '')}: {r.get('body', '')[:200]}" for r in search_results]
                summary = f"**{name}** — Recent activity:\n" + "\n".join(snippets[:3])
            except Exception as e:
                logger.warning("[competitor-intel] search failed for %s: %s", name, e)
                summary = f"**{name}** — Could not fetch recent data."

            insight = {
                "_id": str(uuid.uuid4()),
                "user_id": uid,
                "competitor_id": str(comp["_id"]),
                "competitor_name": name,
                "summary": summary,
                "raw_results": search_results[:5],
                "created_at": datetime.utcnow(),
            }
            await db.competitor_insights.insert_one(insight)
            insight["_id"] = str(insight["_id"])
            results.append(insight)

        return {"insights": results}

    # ════════════════════════════════════════════════════════════════════════
    # 6. VOICE INPUT — store transcription job, return text
    # ════════════════════════════════════════════════════════════════════════

    @router.post("/voice/transcribe")
    async def transcribe_voice(request: Request):
        """
        Accepts a base64-encoded audio blob, transcribes it via OpenAI Whisper,
        and returns the transcribed text so the chat input can be pre-filled.
        """
        user = await user_dep()
        body = await request.json()
        audio_b64 = body.get("audio_b64", "")
        mime_type = body.get("mime_type", "audio/webm")

        if not audio_b64:
            raise HTTPException(400, "No audio provided")

        audio_bytes = base64.b64decode(audio_b64)

        # Determine file extension from mime type
        ext_map = {
            "audio/webm": "webm", "audio/mp4": "mp4", "audio/wav": "wav",
            "audio/ogg": "ogg", "audio/mpeg": "mp3",
        }
        ext = ext_map.get(mime_type, "webm")

        try:
            import httpx
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            async with httpx.AsyncClient(timeout=30) as client:
                with open(tmp_path, "rb") as f:
                    resp = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"},
                        files={"file": (f"audio.{ext}", f, mime_type)},
                        data={"model": "whisper-1"},
                    )
            os.unlink(tmp_path)

            if resp.status_code == 200:
                text = resp.json().get("text", "")
                return {"text": text, "status": "ok"}
            else:
                logger.warning("[voice] Whisper API error: %s", resp.text)
                raise HTTPException(502, "Transcription failed")

        except HTTPException:
            raise
        except Exception as e:
            logger.error("[voice] transcribe error: %s", e)
            raise HTTPException(500, str(e))

    return router
