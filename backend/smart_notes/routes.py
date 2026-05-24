"""Smart Notes — calendar-aware meeting note-taker with Deepgram Nova-2 streaming."""
from __future__ import annotations
import logging, uuid, os, tempfile, asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState
from pydantic import BaseModel, ConfigDict
import httpx

logger = logging.getLogger(__name__)

ASSEMBLYAI_BASE = "https://api.assemblyai.com/v2"

def _tid(user): return user.get("business_id", user["_id"])

def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at", "meeting_start", "meeting_end"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"):
            doc[f] = v.isoformat()
    return doc


class NoteSave(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str
    meeting_start: Optional[str] = None
    meeting_end: Optional[str] = None
    meeting_url: Optional[str] = None
    attendees: Optional[List[str]] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: Optional[List[str]] = None
    raw_calendar_event_id: Optional[str] = None


# ── AssemblyAI helpers ─────────────────────────────────────────────────────────

async def _aai_upload(content: bytes, api_key: str) -> str:
    """Upload raw audio bytes to AssemblyAI CDN, return upload_url."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{ASSEMBLYAI_BASE}/upload",
            headers={"authorization": api_key},
            content=content,
        )
        resp.raise_for_status()
        return resp.json()["upload_url"]


async def _aai_submit(upload_url: str, api_key: str) -> str:
    """Submit a diarization job, return transcript_id."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{ASSEMBLYAI_BASE}/transcript",
            headers={"authorization": api_key, "content-type": "application/json"},
            json={"audio_url": upload_url, "speaker_labels": True},
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def _aai_poll(job_id: str, api_key: str) -> dict:
    """Fetch current status of an AssemblyAI transcript job."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{ASSEMBLYAI_BASE}/transcript/{job_id}",
            headers={"authorization": api_key},
        )
        resp.raise_for_status()
        return resp.json()


def make_smart_notes_router(db, auth_dep):
    router = APIRouter(prefix="/smart-notes", tags=["smart-notes"])

    # ── Upcoming calendar meetings ─────────────────────────────────────────────

    @router.get("/upcoming")
    async def upcoming_meetings(user=auth_dep):
        tid = _tid(user)
        try:
            from composio_service import (
                execute_action, get_connection_status,
                TOOLKIT_CALENDAR, ACTION_CALENDAR_LIST,
            )
        except ImportError:
            return {"meetings": [], "error": "Composio not available"}

        status = await get_connection_status(tid, TOOLKIT_CALENDAR)
        if not status.get("connected"):
            return {"meetings": [], "connected": False}

        now = datetime.now(timezone.utc)
        result = await execute_action(tid, ACTION_CALENDAR_LIST, {
            "max_results": 20,
            "calendar_id": "primary",
            "time_min": now.strftime("%Y-%m-%dT00:00:00Z"),
            "time_max": now.strftime("%Y-%m-%dT23:59:59Z"),
        })

        raw_items = (
            result.get("items")
            or result.get("data", {}).get("items")
            or result.get("response", {}).get("items")
            or []
        )
        events = []
        for ev in raw_items:
            meet_url = _extract_meeting_url(ev)
            events.append({
                "id":          ev.get("id", ""),
                "title":       ev.get("summary", "Untitled meeting"),
                "start":       _parse_event_time(ev.get("start", {})),
                "end":         _parse_event_time(ev.get("end", {})),
                "meet_url":    meet_url,
                "attendees":   [a.get("email", "") for a in ev.get("attendees", [])],
                "description": ev.get("description", ""),
            })
        return {"meetings": events, "connected": True}

    # ── Whisper transcription (live 30 s chunks) ───────────────────────────────

    @router.post("/transcribe")
    async def transcribe_audio(audio: UploadFile = File(...), user=auth_dep):
        import openai
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise HTTPException(502, "OpenAI API key not configured")

        content = await audio.read()
        if len(content) < 1000:
            raise HTTPException(400, "Audio file too short or empty")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            client = openai.AsyncOpenAI(api_key=api_key)
            with open(tmp_path, "rb") as f:
                resp = await client.audio.transcriptions.create(
                    model="whisper-1", file=f, response_format="text",
                )
            transcript = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        finally:
            try: os.unlink(tmp_path)
            except OSError: pass

        return {"transcript": transcript.strip()}

    # ── AssemblyAI diarization — start job ────────────────────────────────────

    @router.post("/diarize")
    async def start_diarization(audio: UploadFile = File(...), user=auth_dep):
        """Upload audio to AssemblyAI, start speaker-diarization job, return job_id."""
        api_key = os.environ.get("ASSEMBLYAI_API_KEY", "")
        if not api_key:
            raise HTTPException(502, "ASSEMBLYAI_API_KEY not configured — add it to .env")

        content = await audio.read()
        if len(content) < 1000:
            raise HTTPException(400, "Audio too short")

        try:
            upload_url = await _aai_upload(content, api_key)
            job_id     = await _aai_submit(upload_url, api_key)
        except httpx.HTTPStatusError as e:
            raise HTTPException(502, f"AssemblyAI error: {e.response.text[:200]}")

        return {"job_id": job_id}

    # ── AssemblyAI diarization — poll status ──────────────────────────────────

    @router.get("/diarize/{job_id}")
    async def poll_diarization(job_id: str, user=auth_dep):
        """Poll an AssemblyAI diarization job. Returns status + utterances when done."""
        api_key = os.environ.get("ASSEMBLYAI_API_KEY", "")
        if not api_key:
            raise HTTPException(502, "ASSEMBLYAI_API_KEY not configured")

        try:
            data = await _aai_poll(job_id, api_key)
        except httpx.HTTPStatusError as e:
            raise HTTPException(502, f"AssemblyAI error: {e.response.text[:200]}")

        status = data.get("status")

        if status == "completed":
            utterances = data.get("utterances") or []
            speakers   = sorted({u["speaker"] for u in utterances})
            return {
                "status":     "completed",
                "speakers":   speakers,
                "utterances": [
                    {"speaker": u["speaker"], "text": u["text"],
                     "start": u.get("start", 0), "end": u.get("end", 0)}
                    for u in utterances
                ],
                "text": data.get("text", ""),
            }
        if status == "error":
            return {"status": "error", "error": data.get("error", "Transcription failed")}

        return {"status": status}   # "queued" | "processing"

    # ── Generate structured notes ──────────────────────────────────────────────

    @router.post("/generate")
    async def generate_notes(payload: Dict[str, Any], user=auth_dep):
        """
        Accepts either:
          - { transcript: "plain text", title, meeting_start, ... }
          - { utterances: [{ speaker: "John", text: "..." }], title, ... }
        Returns structured JSON notes.
        """
        utterances: List[Dict[str, str]] = payload.get("utterances") or []
        if utterances:
            # Build speaker-attributed transcript
            transcript = "\n".join(f"{u['speaker']}: {u['text']}" for u in utterances)
        else:
            transcript = (payload.get("transcript") or "").strip()

        if not transcript:
            raise HTTPException(400, "transcript or utterances required")

        title     = payload.get("title", "Meeting")
        start     = payload.get("meeting_start", "")
        end       = payload.get("meeting_end", "")
        attendees = ", ".join(payload.get("attendees") or []) or "unknown"
        has_speakers = bool(utterances)

        speaker_note = (
            "\nThe transcript is speaker-attributed. Use the real speaker names in your output."
            if has_speakers else ""
        )

        prompt = f"""You are a professional meeting note-taker. Produce structured notes from this meeting.

Meeting: {title}
Time: {start} – {end}
Attendees: {attendees}{speaker_note}

TRANSCRIPT:
{transcript}

Return a JSON object with exactly these fields:
{{
  "summary": "2-4 sentence executive summary",
  "key_points": ["bullet 1", "bullet 2", ...],
  "action_items": ["action (owner, deadline if mentioned)", ...],
  "decisions": ["decision 1", ...],
  "next_steps": "brief paragraph on what happens next"
}}

Respond ONLY with valid JSON. No markdown fences."""

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        openai_key    = os.environ.get("OPENAI_API_KEY", "")

        if anthropic_key:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=anthropic_key)
            msg = await client.messages.create(
                model="claude-opus-4-7", max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
        elif openai_key:
            import openai
            client = openai.AsyncOpenAI(api_key=openai_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()
        else:
            raise HTTPException(502, "No AI API key configured")

        import json as _json
        try:
            return _json.loads(raw)
        except Exception:
            return {"summary": raw, "key_points": [], "action_items": [], "decisions": [], "next_steps": ""}

    # ── Deepgram Nova-2 real-time streaming proxy ──────────────────────────────

    @router.websocket("/stream")
    async def stream_audio(
        websocket: WebSocket,
        token: str = Query(""),
        keyterms: List[str] = Query(default=[]),
    ):
        """
        WebSocket proxy: frontend 16 kHz mono PCM → Deepgram Nova-2 → JSON results back.
        Auth: JWT passed as ?token= query param (standard Bearer auth doesn't work on WS).
        keyterms: custom words/names to bias recognition toward (brand names, people, etc.)
        """
        import jwt as _jwt
        import json as _json
        from urllib.parse import quote as _quote

        secret    = os.environ.get("JWT_SECRET", "")
        algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        try:
            _jwt.decode(token, secret, algorithms=[algorithm])
        except Exception:
            await websocket.close(code=1008)
            return

        api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            await websocket.accept()
            await websocket.send_text(_json.dumps({
                "type": "error",
                "message": "DEEPGRAM_API_KEY not set — add it to backend/.env and restart",
            }))
            await websocket.close()
            return

        await websocket.accept()

        dg_url = (
            "wss://api.deepgram.com/v1/listen"
            "?model=nova-2"
            "&smart_format=true"
            "&diarize=true"
            "&language=en"
            "&punctuate=true"
            "&interim_results=true"
            "&utterance_end_ms=1500"
            "&filler_words=false"
            "&encoding=linear16"
            "&sample_rate=16000"
            "&channels=1"
        )
        # Append custom keyterms (cap at 20 to stay within URL limits)
        for term in keyterms[:20]:
            if term.strip():
                dg_url += f"&keyterms={_quote(term.strip())}"

        try:
            import websockets as _ws
            async with _ws.connect(
                dg_url,
                additional_headers={"Authorization": f"Token {api_key}"},
            ) as dg_ws:

                async def client_to_dg():
                    try:
                        while True:
                            data = await websocket.receive_bytes()
                            await dg_ws.send(data)
                    except (WebSocketDisconnect, Exception):
                        pass

                async def dg_to_client():
                    try:
                        async for msg in dg_ws:
                            if isinstance(msg, str):
                                try:
                                    await websocket.send_text(msg)
                                except Exception:
                                    break
                    except Exception:
                        pass

                t1 = asyncio.create_task(client_to_dg())
                t2 = asyncio.create_task(dg_to_client())
                done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        except Exception as exc:
            logger.error("[smart-notes/stream] %s", exc)
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(_json.dumps({"type": "error", "message": "Deepgram connection failed"}))
            except Exception:
                pass
        finally:
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.close()
            except Exception:
                pass

    # ── Notes CRUD ─────────────────────────────────────────────────────────────

    @router.get("")
    async def list_notes(user=auth_dep):
        tid = _tid(user)
        docs = await db.smart_notes.find(
            {"user_id": tid}, {"transcript": 0}
        ).sort("created_at", -1).limit(100).to_list(100)
        return {"notes": [_ser(d) for d in docs]}

    @router.post("")
    async def save_note(body: NoteSave, user=auth_dep):
        tid = _tid(user)
        now = datetime.now(timezone.utc)
        doc = {
            "_id":                   str(uuid.uuid4()),
            "user_id":               tid,
            "title":                 body.title,
            "meeting_start":         body.meeting_start,
            "meeting_end":           body.meeting_end,
            "meeting_url":           body.meeting_url,
            "attendees":             body.attendees or [],
            "transcript":            body.transcript or "",
            "summary":               body.summary or "",
            "action_items":          body.action_items or [],
            "raw_calendar_event_id": body.raw_calendar_event_id,
            "created_at":            now,
            "updated_at":            now,
        }
        await db.smart_notes.insert_one(doc)
        return _ser(doc)

    @router.get("/{note_id}")
    async def get_note(note_id: str, user=auth_dep):
        tid = _tid(user)
        doc = await db.smart_notes.find_one({"_id": note_id, "user_id": tid})
        if not doc:
            raise HTTPException(404, "Note not found")
        return _ser(doc)

    @router.delete("/{note_id}")
    async def delete_note(note_id: str, user=auth_dep):
        tid = _tid(user)
        r = await db.smart_notes.delete_one({"_id": note_id, "user_id": tid})
        if r.deleted_count == 0:
            raise HTTPException(404, "Note not found")
        return {"ok": True}

    return router


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_meeting_url(event: dict) -> str:
    conf = event.get("conferenceData", {})
    for ep in conf.get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            return ep.get("uri", "")
    loc = event.get("location", "")
    if loc.startswith("http"):
        return loc
    desc = event.get("description", "")
    import re
    m = re.search(
        r"https?://(?:meet\.google\.com|zoom\.us|teams\.microsoft\.com|us\d+web\.zoom\.us)[^\s\"<>]+",
        desc,
    )
    return m.group(0) if m else ""


def _parse_event_time(time_obj: dict) -> str:
    return time_obj.get("dateTime") or time_obj.get("date") or ""
