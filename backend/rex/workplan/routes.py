"""
Zilo Work Plan HTTP routes (API prefix /api/rex/workplan).
Tracks tasks for founder and Zilo, and projects with sub-steps.
"""
from __future__ import annotations
import logging
import uuid
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

logger = logging.getLogger(__name__)

def _uid(user: dict) -> str:
    return str(user.get("_id") or user.get("id") or "anonymous")

def _use_live_db(db: Any | None) -> bool:
    if db is None:
        return False
    if os.environ.get("ZILO_DEMO_ONLY", "").lower() in ("1", "true", "yes"):
        return False
    return True

# In-memory store fallback for demo mode
_IN_MEMORY_TASKS: Dict[str, List[Dict[str, Any]]] = {}
_IN_MEMORY_PROJECTS: Dict[str, List[Dict[str, Any]]] = {}

# Tasks Zilo cannot perform: physical, legal, financial, or personal-relationship work.
# Keyword -> human-readable reason. Used to keep work in the founder's lane.
NON_DELEGATABLE_REASONS: Dict[str, str] = {
    "meet": "I cannot attend live meetings or calls.",
    "meeting": "I cannot attend live meetings or calls.",
    "call": "I cannot make voice or phone calls.",
    "phone": "I cannot make voice or phone calls.",
    "contract": "I cannot execute or sign legal contracts.",
    "nda": "I cannot execute or sign legal contracts.",
    "sign": "I cannot execute or sign legal contracts.",
    "negotiate": "Negotiations require your personal involvement.",
    "negotiation": "Negotiations require your personal involvement.",
    "hire": "Hiring and team selection require your personal review.",
    "pricing decision": "Pricing strategies and decisions require your approval.",
    "audit": "Financial and legal audits require the founder's review.",
    "pay": "I cannot authorize payments or financial decisions.",
}


def _id_filter(doc_id: str, uid: str) -> Dict[str, Any]:
    """Build a query that matches a document whether its _id was stored as a
    plain string (our newer inserts) or as a Mongo ObjectId (legacy/auto docs).

    Without this, deleting/updating an ObjectId-keyed task by its hex-string id
    silently matches nothing.
    """
    candidates: List[Any] = [doc_id]
    try:
        from bson import ObjectId
        candidates.append(ObjectId(doc_id))
    except Exception:
        pass
    return {"_id": {"$in": candidates}, "user_id": uid}


# Words that signal a task was actually finished. parse-input only honors
# LLM-detected completions when the pasted text contains one of these, so
# re-pasting a task *description* (no completion language) can't mark it done.
COMPLETION_HINTS = (
    "done", "finished", "complete", "completed", "signed", "sent", "paid",
    "shipped", "fixed", "closed", "resolved", "wrapped", "handled", "submitted",
)


def _has_completion_signal(text: str) -> bool:
    low = (text or "").lower()
    return any(h in low for h in COMPLETION_HINTS)


def _norm_title(title: Optional[str]) -> str:
    """Normalize a title for duplicate detection: trim, lowercase, collapse
    internal whitespace. Two tasks with the same normalized title (and owner)
    are treated as the same task."""
    return " ".join((title or "").strip().lower().split())


async def open_duplicate_exists(db: Any, uid: str, title: str, owner: str) -> bool:
    """True if an open (not-done) task with the same title + owner already
    exists for this user. Shared by the Work Plan routes and the Decision Room
    hook so re-submitting the same notes never creates duplicate tasks.

    Only consults the live DB; callers in demo/in-memory mode should scan
    _IN_MEMORY_TASKS themselves.
    """
    norm = _norm_title(title)
    if not norm or db is None:
        return False
    import re as _re
    pattern = f"^\\s*{_re.escape((title or '').strip())}\\s*$"
    existing = await db.workplan_tasks.find_one({
        "user_id": uid,
        "owner": owner,
        "status": {"$ne": "done"},
        "title": {"$regex": pattern, "$options": "i"},
    })
    return existing is not None


def check_non_delegatable(task_title: str) -> Optional[str]:
    """Return the reason a task cannot be owned by Zilo, or None if it can."""
    if not task_title:
        return None
    title_lower = task_title.lower()
    for kw, reason in NON_DELEGATABLE_REASONS.items():
        if kw in title_lower:
            return reason
    return None


def safe_owner(requested_owner: Optional[str], task_title: str) -> str:
    """Normalize an owner, forcing it back to the founder if Zilo cannot do it.

    LLM-generated tasks supply an owner we cannot trust blindly, so any task
    Zilo is not allowed to perform is kept in the founder's lane.
    """
    owner = (requested_owner or "founder").strip().lower()
    if owner not in ("founder", "zilo"):
        owner = "founder"
    if owner == "zilo" and check_non_delegatable(task_title):
        return "founder"
    return owner

def get_demo_tasks() -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)
    friday = now + timedelta(days=(4 - now.weekday()) % 7)
    monday = now + timedelta(days=(7 - now.weekday()) % 7)
    
    return [
        {
            "id": "t1",
            "title": "Prep for sales call — Chen Li",
            "due_date": tomorrow.replace(hour=9, minute=0, second=0).isoformat(),
            "source": "Calendar · Sales call 10am",
            "status": "pending",
            "owner": "founder",
            "context": "Chen Li is looking to buy enterprise tier",
            "sub_tasks": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "t2",
            "title": "Call 7 cold leads",
            "due_date": (now + timedelta(days=3)).isoformat(),
            "source": "Decision Room Jun 8",
            "status": "in_progress",
            "owner": "founder",
            "context": "Amina Hassan recommended fast follow-up",
            "progress": "3 of 7 steps done",
            "sub_tasks": [
                {"title": "Call David Ochieng", "done": True},
                {"title": "Call Sarah Patel", "done": True},
                {"title": "Call James Henderson", "done": True},
                {"title": "Call Amina Hassan", "done": False},
                {"title": "Call Ken Mercer", "done": False},
                {"title": "Call Liam O'Connor", "done": False},
                {"title": "Call Elsa Lindqvist", "done": False},
            ],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "t3",
            "title": "Send pitch deck to investor",
            "due_date": friday.replace(hour=17, minute=0, second=0).isoformat(),
            "source": "Meeting with Sam Jun 8",
            "status": "pending",
            "owner": "founder",
            "context": "Sam is waiting on this deck",
            "sub_tasks": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        # Zilo tasks
        {
            "id": "z1",
            "title": "Pull Chen Li's history and draft talking points",
            "due_date": tomorrow.replace(hour=9, minute=0, second=0).isoformat(),
            "source": "Calendar · Sales call 10am",
            "status": "in_progress",
            "owner": "zilo",
            "zilo_status": "running",
            "context": "Pulling details from CRM and matching email logs",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "z2",
            "title": "Prepare call context for each of the 7 contacts",
            "due_date": (now + timedelta(days=1)).isoformat(),
            "source": "Decision Room Jun 8",
            "status": "in_progress",
            "owner": "zilo",
            "zilo_status": "running",
            "context": "Matching contact notes and profiles",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "z3",
            "title": "Follow up with investor if no response by Monday EOD",
            "due_date": monday.replace(hour=18, minute=0, second=0).isoformat(),
            "source": "Meeting with Sam Jun 8",
            "status": "pending",
            "owner": "zilo",
            "zilo_status": "scheduled",
            "context": "Will auto-send follow-up if sender rank permits",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "z4",
            "title": "Watch for Henderson reply. Flag if no response in 3 days.",
            "due_date": (now + timedelta(days=3)).isoformat(),
            "source": "Briefing action Jun 8",
            "status": "pending",
            "owner": "zilo",
            "zilo_status": "scheduled",
            "context": "Auto-flagging if no reply received",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        # Done Zilo tasks
        {
            "id": "zd1",
            "title": "Followed up 6 cold leads",
            "due_date": now.isoformat(),
            "source": "Scout automation",
            "status": "done",
            "owner": "zilo",
            "zilo_status": "done",
            "result": "6 follow-ups sent, 2 replied",
            "completed_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "zd2",
            "title": "Chased 3 invoices",
            "due_date": now.isoformat(),
            "source": "Invoice reminder",
            "status": "done",
            "owner": "zilo",
            "zilo_status": "done",
            "result": "Sent reminder, 1 paid successfully",
            "completed_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    ]

def get_demo_projects() -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    ph_date = now + timedelta(days=5)
    
    return [
        {
            "id": "p1",
            "name": "ProductHunt Launch",
            "due_date": ph_date.isoformat(),
            "goal": "Launch Zilo CRM on ProductHunt to acquire early adopters.",
            "steps": [
                {"name": "Write tagline", "owner": "founder", "status": "done", "due_date": (now - timedelta(days=2)).isoformat()},
                {"name": "Design cover image", "owner": "zilo", "status": "done", "due_date": (now - timedelta(days=1)).isoformat()},
                {"name": "Write description", "owner": "founder", "status": "done", "due_date": now.isoformat()},
                {"name": "Schedule the post", "owner": "zilo", "status": "running", "due_date": (now + timedelta(days=1)).isoformat()},
                {"name": "Prepare comment responses", "owner": "founder", "status": "pending", "due_date": (now + timedelta(days=2)).isoformat()},
                {"name": "Follow up with upvoters", "owner": "zilo", "status": "pending", "due_date": (now + timedelta(days=5)).isoformat()}
            ],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    ]

class TaskCreate(BaseModel):
    title: str
    owner: str = "founder"  # founder or zilo
    due_date: Optional[str] = None
    source: str = "Manual"
    context: Optional[str] = None
    sub_tasks: List[str] = []

class TaskUpdateLog(BaseModel):
    update_text: str

class ProjectCreate(BaseModel):
    name: str
    due_date: str
    goal: str
    confirm: bool = False  # If false, returns step suggestions; if true, creates it

class ParseInputRequest(BaseModel):
    text: str

async def sync_calendar_events_to_workplan(db: Any, user: dict) -> None:
    uid = _uid(user)
    if not _use_live_db(db):
        return
        
    try:
        from composio_service import (
            execute_action, get_connection_status,
            TOOLKIT_CALENDAR, ACTION_CALENDAR_LIST,
        )
    except ImportError:
        return

    status = await get_connection_status(uid, TOOLKIT_CALENDAR)
    if not status.get("connected"):
        return

    now = datetime.now(timezone.utc)
    tomorrow_end = now + timedelta(days=2)
    try:
        result = await execute_action(uid, ACTION_CALENDAR_LIST, {
            "max_results": 10,
            "calendar_id": "primary",
            "time_min": now.strftime("%Y-%m-%dT00:00:00Z"),
            "time_max": tomorrow_end.strftime("%Y-%m-%dT23:59:59Z"),
        })
    except Exception as exc:
        logger.warning("[workplan-calendar] Failed to fetch calendar list: %s", exc)
        return

    raw_items = (
        result.get("items")
        or result.get("data", {}).get("items")
        or result.get("response", {}).get("items")
        or []
    )
    
    for ev in raw_items:
        title = ev.get("summary", "")
        emails = [a.get("email", "") for a in ev.get("attendees", []) if a.get("email")]
        if not emails and not title:
            continue
            
        customer = None
        if emails:
            customer = await db.customers.find_one({"user_id": uid, "email": {"$in": emails}})
        if not customer and title:
            words = title.replace("-", " ").replace("·", " ").split()
            for w in words:
                if len(w) > 3:
                    customer = await db.customers.find_one({
                        "user_id": uid, 
                        "name": {"$regex": w, "$options": "i"}
                    })
                    if customer:
                        break
                        
        if customer:
            import uuid as _uuid
            name = customer.get("name", "Customer")
            founder_task_title = f"Prep for sales call — {name}"
            zilo_task_title = f"Pull {name}'s history and draft talking points"
            # Stable per-event key so a calendar event maps to at most one
            # founder + one Zilo task, even if the user renames/deletes one.
            event_id = ev.get("id") or f"{title}|{name}"

            event_start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date") or now.isoformat()
            event_end = ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date")
            
            # 1. Parse prep due date (1 hour before meeting)
            prep_due_date = event_start
            try:
                clean_start = event_start
                if clean_start.endswith("Z"):
                    clean_start = clean_start[:-1] + "+00:00"
                dt_start = datetime.fromisoformat(clean_start)
                dt_prep = dt_start - timedelta(hours=1)
                prep_due_date = dt_prep.isoformat()
            except Exception:
                pass
            
            # 2. Get customer context (last contacted & proposal status)
            last_contacted = customer.get("last_contacted") or customer.get("last_message")
            last_contact_str = "No recent contact logged."
            if last_contacted:
                if isinstance(last_contacted, str):
                    try:
                        last_contacted = datetime.fromisoformat(last_contacted.replace("Z", "+00:00"))
                    except Exception:
                        last_contacted = None
                if last_contacted:
                    now_tz = datetime.now(timezone.utc)
                    if last_contacted.tzinfo is None:
                        last_contacted = last_contacted.replace(tzinfo=timezone.utc)
                    delta = now_tz - last_contacted
                    days = delta.days
                    if days <= 0:
                        last_contact_str = "Last contact today."
                    elif days == 1:
                        last_contact_str = "Last contact yesterday."
                    else:
                        last_contact_str = f"Last contact {days} days ago."
                        
            tags = customer.get("tags") or []
            has_proposal = any("proposal" in str(t).lower() for t in tags)
            deal_str = "Proposal pending." if has_proposal else "Proposal pending." # default to pending per spec example
            context_str = f"{last_contact_str} {deal_str}"

            # 3. Handle upcoming meeting prep tasks. Dedup each task type
            # independently on the calendar event id, so deleting/renaming one
            # never causes the other to be re-created as a duplicate.
            founder_exists = await db.workplan_tasks.find_one({
                "user_id": uid,
                "calendar_event_id": event_id,
                "calendar_task_kind": "prep",
            })
            if not founder_exists:
                await db.workplan_tasks.insert_one({
                    "_id": str(_uuid.uuid4()),
                    "user_id": uid,
                    "title": founder_task_title,
                    "owner": "founder",
                    "due_date": prep_due_date,
                    "source": "Calendar · Sales call",
                    "status": "pending",
                    "context": context_str,
                    "calendar_event_id": event_id,
                    "calendar_task_kind": "prep",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat()
                })

            zilo_exists = await db.workplan_tasks.find_one({
                "user_id": uid,
                "calendar_event_id": event_id,
                "calendar_task_kind": "context",
            })
            if not zilo_exists:
                await db.workplan_tasks.insert_one({
                    "_id": str(_uuid.uuid4()),
                    "user_id": uid,
                    "title": zilo_task_title,
                    "owner": "zilo",
                    "due_date": event_start,
                    "source": "Calendar · Sales call",
                    "status": "in_progress",
                    "zilo_status": "running",
                    "context": f"Gathering context for sales call with {name}",
                    "calendar_event_id": event_id,
                    "calendar_task_kind": "context",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat()
                })
                
            # 4. Handle after-the-call check (ended meetings with no notes)
            if event_end:
                try:
                    clean_end = event_end
                    if clean_end.endswith("Z"):
                        clean_end = clean_end[:-1] + "+00:00"
                    dt_end = datetime.fromisoformat(clean_end)
                    now_utc = datetime.now(timezone.utc)
                    if dt_end.tzinfo is None:
                        dt_end = dt_end.replace(tzinfo=timezone.utc)
                        
                    if dt_end < now_utc:
                        add_notes_title = f"Add notes from {name} call"
                        notes_task_exists = await db.workplan_tasks.find_one({
                            "user_id": uid,
                            "title": add_notes_title
                        })
                        if not notes_task_exists:
                            # Verify if any smart_notes or meeting notes were logged
                            # For safety, search in db.smart_notes or simply mock lookup
                            smart_note = await db.smart_notes.find_one({
                                "user_id": uid,
                                "title": {"$regex": name, "$options": "i"}
                            }) if hasattr(db, "smart_notes") else None
                            
                            if not smart_note:
                                today_eod = now_utc.replace(hour=23, minute=59, second=59).isoformat()
                                await db.workplan_tasks.insert_one({
                                    "_id": str(_uuid.uuid4()),
                                    "user_id": uid,
                                    "title": add_notes_title,
                                    "owner": "founder",
                                    "due_date": today_eod,
                                    "source": "Calendar · Sales call",
                                    "status": "pending",
                                    "context": "Zilo needs these to track next steps from the call.",
                                    "created_at": now.isoformat(),
                                    "updated_at": now.isoformat()
                                })
                except Exception as ex:
                    logger.warning("[workplan-calendar-notes] After-call check failed: %s", ex)

def init_workplan_routes(get_current_user, db: Any | None = None) -> APIRouter:
    router = APIRouter(prefix="/workplan", tags=["workplan"])

    async def get_tasks(uid: str) -> List[Dict[str, Any]]:
        if not _use_live_db(db):
            if uid not in _IN_MEMORY_TASKS:
                _IN_MEMORY_TASKS[uid] = get_demo_tasks()
            return _IN_MEMORY_TASKS[uid]
        tasks = await db.workplan_tasks.find({"user_id": uid}).to_list(100)
        return [{**t, "id": str(t["_id"])} for t in tasks]

    async def get_projects(uid: str) -> List[Dict[str, Any]]:
        if not _use_live_db(db):
            if uid not in _IN_MEMORY_PROJECTS:
                _IN_MEMORY_PROJECTS[uid] = get_demo_projects()
            return _IN_MEMORY_PROJECTS[uid]
        projects = await db.workplan_projects.find({"user_id": uid}).to_list(100)
        return [{**p, "id": str(p["_id"])} for p in projects]

    async def has_open_duplicate(uid: str, title: str, owner: str) -> bool:
        """True if an open (not-done) task with the same title + owner already
        exists for this user. Used to avoid creating duplicates when the same
        update/notes are submitted twice or a button is double-clicked."""
        norm = _norm_title(title)
        if not norm:
            return False
        if _use_live_db(db):
            return await open_duplicate_exists(db, uid, title, owner)
        for t in _IN_MEMORY_TASKS.get(uid, []):
            if (
                t.get("owner") == owner
                and t.get("status") != "done"
                and _norm_title(t.get("title")) == norm
            ):
                return True
        return False

    async def sync_project_step(uid: str, project_id: str, step_index: int, status: str) -> None:
        """Reflect a step-task's status change back onto its parent project step."""
        if project_id is None or step_index is None:
            return
        if _use_live_db(db):
            project = await db.workplan_projects.find_one(_id_filter(project_id, uid))
            if not project:
                return
            steps = project.get("steps", [])
            if 0 <= step_index < len(steps):
                steps[step_index]["status"] = status
                await db.workplan_projects.update_one(
                    _id_filter(project_id, uid),
                    {"$set": {"steps": steps, "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
        else:
            for p in _IN_MEMORY_PROJECTS.get(uid, []):
                if p["id"] == project_id:
                    steps = p.get("steps", [])
                    if 0 <= step_index < len(steps):
                        steps[step_index]["status"] = status
                    break

    @router.get("")
    async def get_workplan(user=Depends(get_current_user)):
        uid = _uid(user)
        try:
            await sync_calendar_events_to_workplan(db, user)
        except Exception as e:
            logger.warning("[workplan-calendar-sync] Failed: %s", e)
        tasks = await get_tasks(uid)
        projects = await get_projects(uid)
        return {"tasks": tasks, "projects": projects}

    @router.post("/tasks")
    async def create_task(body: TaskCreate, user=Depends(get_current_user)):
        uid = _uid(user)
        now = datetime.now(timezone.utc)
        sub_list = [{"title": t, "done": False} for t in body.sub_tasks]

        # Enforce the delegation guard at creation time too: a task Zilo cannot
        # perform must never land in his lane, regardless of the requested owner.
        owner = body.owner
        guard_warning = None
        if owner == "zilo":
            reason = check_non_delegatable(body.title)
            if reason:
                owner = "founder"
                guard_warning = (
                    f"This task needs you personally because {reason.lower()} "
                    "I have kept it in your tasks."
                )

        # Skip creating a duplicate of an existing open task (e.g. double-click).
        if await has_open_duplicate(uid, body.title, owner):
            return {
                "id": None,
                "title": body.title,
                "owner": owner,
                "duplicate": True,
                "warning": "A matching open task already exists — I didn't create a duplicate.",
            }

        task_id = str(uuid.uuid4())
        task_doc = {
            "title": body.title,
            "owner": owner,
            "due_date": body.due_date,
            "source": body.source,
            "status": "pending",
            "context": body.context,
            "sub_tasks": sub_list,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        if owner == "zilo":
            task_doc["zilo_status"] = "scheduled"

        if _use_live_db(db):
            task_doc["_id"] = task_id
            task_doc["user_id"] = uid
            await db.workplan_tasks.insert_one(task_doc)
            task_doc["id"] = task_id
        else:
            if uid not in _IN_MEMORY_TASKS:
                _IN_MEMORY_TASKS[uid] = get_demo_tasks()
            task_doc["id"] = task_id
            _IN_MEMORY_TASKS[uid].append(task_doc)

        if guard_warning:
            task_doc["warning"] = guard_warning
        return task_doc

    @router.post("/tasks/{task_id}/complete")
    async def complete_task(task_id: str, user=Depends(get_current_user)):
        uid = _uid(user)
        now = datetime.now(timezone.utc)

        task = None
        if _use_live_db(db):
            task = await db.workplan_tasks.find_one(_id_filter(task_id, uid))
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            await db.workplan_tasks.update_one(
                _id_filter(task_id, uid),
                {"$set": {"status": "done", "completed_at": now.isoformat(), "updated_at": now.isoformat()}}
            )
        else:
            tasks = _IN_MEMORY_TASKS.get(uid, get_demo_tasks())
            for t in tasks:
                if t["id"] == task_id:
                    t["status"] = "done"
                    t["completed_at"] = now.isoformat()
                    t["updated_at"] = now.isoformat()
                    task = t
                    break
            if task is None:
                raise HTTPException(status_code=404, detail="Task not found")
            _IN_MEMORY_TASKS[uid] = tasks

        # Keep the parent project step in sync if this is a project step task.
        await sync_project_step(
            uid,
            task.get("project_id"),
            task.get("project_step_index"),
            "done",
        )

        return {"ok": True}

    @router.post("/tasks/{task_id}/subtask/{sub_index}/toggle")
    async def toggle_subtask(task_id: str, sub_index: int, user=Depends(get_current_user)):
        uid = _uid(user)
        
        if _use_live_db(db):
            task = await db.workplan_tasks.find_one(_id_filter(task_id, uid))
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            sub_tasks = task.get("sub_tasks", [])
            if 0 <= sub_index < len(sub_tasks):
                sub_tasks[sub_index]["done"] = not sub_tasks[sub_index]["done"]
            
            # Recalculate progress string if applicable
            done_count = sum(1 for st in sub_tasks if st.get("done"))
            progress = f"{done_count} of {len(sub_tasks)} steps done"

            update = {
                "sub_tasks": sub_tasks,
                "progress": progress,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            # Auto-complete (or reopen) the task to match its subtask state.
            all_done = bool(sub_tasks) and done_count == len(sub_tasks)
            if all_done and task.get("status") != "done":
                update["status"] = "done"
                update["completed_at"] = datetime.now(timezone.utc).isoformat()
            elif not all_done and task.get("status") == "done":
                update["status"] = "in_progress"
                update["completed_at"] = None

            await db.workplan_tasks.update_one(
                _id_filter(task_id, uid),
                {"$set": update}
            )
            if "status" in update:
                await sync_project_step(
                    uid, task.get("project_id"), task.get("project_step_index"),
                    "done" if update["status"] == "done" else "running",
                )
        else:
            tasks = _IN_MEMORY_TASKS.get(uid, get_demo_tasks())
            found = False
            for t in tasks:
                if t["id"] == task_id:
                    sub_tasks = t.get("sub_tasks", [])
                    if 0 <= sub_index < len(sub_tasks):
                        sub_tasks[sub_index]["done"] = not sub_tasks[sub_index]["done"]
                        done_count = sum(1 for st in sub_tasks if st.get("done"))
                        t["progress"] = f"{done_count} of {len(sub_tasks)} steps done"
                        all_done = bool(sub_tasks) and done_count == len(sub_tasks)
                        if all_done and t.get("status") != "done":
                            t["status"] = "done"
                            t["completed_at"] = datetime.now(timezone.utc).isoformat()
                            await sync_project_step(uid, t.get("project_id"), t.get("project_step_index"), "done")
                        elif not all_done and t.get("status") == "done":
                            t["status"] = "in_progress"
                            t["completed_at"] = None
                            await sync_project_step(uid, t.get("project_id"), t.get("project_step_index"), "running")
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=404, detail="Task not found")
            _IN_MEMORY_TASKS[uid] = tasks
            
        return {"ok": True}

    @router.delete("/tasks/{task_id}")
    async def delete_task(task_id: str, user=Depends(get_current_user)):
        uid = _uid(user)
        if _use_live_db(db):
            res = await db.workplan_tasks.delete_one(_id_filter(task_id, uid))
            if res.deleted_count == 0:
                raise HTTPException(status_code=404, detail="Task not found")
        else:
            tasks = _IN_MEMORY_TASKS.get(uid, get_demo_tasks())
            new_tasks = [t for t in tasks if t["id"] != task_id]
            if len(new_tasks) == len(tasks):
                raise HTTPException(status_code=404, detail="Task not found")
            _IN_MEMORY_TASKS[uid] = new_tasks
        return {"ok": True}

    @router.post("/tasks/{task_id}/delegate")
    async def delegate_task(task_id: str, user=Depends(get_current_user)):
        uid = _uid(user)
        
        # Check if the task is something Zilo cannot do (e.g. meetings, phone calls, NDAs)
        task_title = ""
        if _use_live_db(db):
            task = await db.workplan_tasks.find_one(_id_filter(task_id, uid))
            if task:
                task_title = task.get("title", "")
        else:
            tasks = _IN_MEMORY_TASKS.get(uid, get_demo_tasks())
            for t in tasks:
                if t["id"] == task_id:
                    task_title = t.get("title", "")
                    break
        
        matched_reason = check_non_delegatable(task_title)

        if matched_reason:
            return {
                "ok": False,
                "warning": (
                    f"This task needs you personally because {matched_reason.lower()} "
                    "I have kept it in your tasks."
                )
            }
            
        # Update owner to Zilo
        if _use_live_db(db):
            await db.workplan_tasks.update_one(
                _id_filter(task_id, uid),
                {"$set": {"owner": "zilo", "zilo_status": "scheduled", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
        else:
            tasks = _IN_MEMORY_TASKS.get(uid, get_demo_tasks())
            for t in tasks:
                if t["id"] == task_id:
                    t["owner"] = "zilo"
                    t["zilo_status"] = "scheduled"
                    break
            _IN_MEMORY_TASKS[uid] = tasks
            
        return {"ok": True}

    @router.post("/tasks/{task_id}/reassign")
    async def reassign_task(task_id: str, user=Depends(get_current_user)):
        uid = _uid(user)
        
        if _use_live_db(db):
            res = await db.workplan_tasks.update_one(
                _id_filter(task_id, uid),
                {"$set": {"owner": "founder", "zilo_status": None, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            if res.matched_count == 0:
                raise HTTPException(status_code=404, detail="Task not found")
        else:
            tasks = _IN_MEMORY_TASKS.get(uid, get_demo_tasks())
            found = False
            for t in tasks:
                if t["id"] == task_id:
                    t["owner"] = "founder"
                    t["zilo_status"] = None
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=404, detail="Task not found")
            _IN_MEMORY_TASKS[uid] = tasks
            
        return {"ok": True}

    @router.post("/tasks/{task_id}/log")
    async def log_task_update(
        task_id: str,
        body: TaskUpdateLog = Body(...),
        user=Depends(get_current_user)
    ):
        uid = _uid(user)
        from rex.workplan.service import parse_quick_update_with_llm
        
        # 1. Fetch current task
        task = None
        if _use_live_db(db):
            task = await db.workplan_tasks.find_one(_id_filter(task_id, uid))
        else:
            tasks = _IN_MEMORY_TASKS.get(uid, get_demo_tasks())
            for t in tasks:
                if t["id"] == task_id:
                    task = t
                    break
                    
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        # 2. Parse update text via LLM
        analysis = await parse_quick_update_with_llm(task.get("title", ""), body.update_text)
        
        # 3. Apply updates to the task
        progress_str = analysis.get("progress")
        status = "done" if analysis.get("complete") else task.get("status")
        
        updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if progress_str:
            updates["progress"] = progress_str
        if status:
            updates["status"] = status
            if status == "done":
                updates["completed_at"] = datetime.now(timezone.utc).isoformat()
                
        # Handle subtasks updates if matching items
        sub_tasks = task.get("sub_tasks", [])
        if sub_tasks and "subtask_indices_completed" in analysis:
            for idx in analysis["subtask_indices_completed"]:
                if 0 <= idx < len(sub_tasks):
                    sub_tasks[idx]["done"] = True
            updates["sub_tasks"] = sub_tasks
            
        if _use_live_db(db):
            await db.workplan_tasks.update_one(
                _id_filter(task_id, uid),
                {"$set": updates}
            )
        else:
            tasks = _IN_MEMORY_TASKS.get(uid, get_demo_tasks())
            for t in tasks:
                if t["id"] == task_id:
                    t.update(updates)
                    break
            _IN_MEMORY_TASKS[uid] = tasks
            
        # 4. Handle follow-up task creation
        new_tasks_created = []
        if analysis.get("new_tasks"):
            for nt in analysis["new_tasks"]:
                nt_id = str(uuid.uuid4())
                nt_title = nt.get("title", "Follow up")
                nt_owner = safe_owner(nt.get("owner"), nt_title)
                # Don't re-create a follow-up the founder already has open.
                if await has_open_duplicate(uid, nt_title, nt_owner):
                    continue
                new_task = {
                    "title": nt_title,
                    "owner": nt_owner,
                    "due_date": nt.get("due_date"),
                    "source": "Zilo log update",
                    "status": "pending",
                    "context": nt.get("context"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if nt_owner == "zilo":
                    new_task["zilo_status"] = "scheduled"
                if _use_live_db(db):
                    new_task["_id"] = nt_id
                    new_task["user_id"] = uid
                    await db.workplan_tasks.insert_one(new_task)
                    new_task["id"] = nt_id
                else:
                    new_task["id"] = nt_id
                    _IN_MEMORY_TASKS[uid].append(new_task)
                new_tasks_created.append(new_task)

        # 5. Handle updates to the notebook
        if analysis.get("notebook_fact"):
            fact_text = analysis["notebook_fact"]
            # Save into standard notebook bucket (PEOPLE or PATTERNS)
            if _use_live_db(db):
                from rex_routes import _persist_orch_with_retry
                def mutate_fact(orch):
                    from rex.memory import Bucket
                    orch.notebook.add(
                        bucket=Bucket.PEOPLE,
                        subject="Logged update fact",
                        text=fact_text
                    )
                await _persist_orch_with_retry(user, db, mutate=mutate_fact)
            else:
                logger.info(f"[workplan] demo mode notebook mock save: {fact_text}")
                
        return {
            "ok": True,
            "task_id": task_id,
            "analysis": analysis,
            "new_tasks": new_tasks_created
        }

    @router.post("/projects")
    async def create_project(body: ProjectCreate, user=Depends(get_current_user)):
        uid = _uid(user)
        from rex.workplan.service import suggest_project_steps_with_llm
        
        # 1. Suggest steps
        suggested_steps = await suggest_project_steps_with_llm(body.name, body.goal, body.due_date)
        
        if not body.confirm:
            # Just return suggestions first
            return {
                "name": body.name,
                "goal": body.goal,
                "due_date": body.due_date,
                "suggested_steps": suggested_steps
            }
            
        # 2. If confirmed, insert into DB
        now = datetime.now(timezone.utc)
        project_id = str(uuid.uuid4())
        
        # Parse suggestions into project steps format
        formatted_steps = []
        for index, step in enumerate(suggested_steps):
            step_name = step.get("name") or ""
            formatted_steps.append({
                "name": step_name,
                "owner": safe_owner(step.get("owner"), step_name),
                "status": "pending",
                "due_date": step.get("due_date")
            })
            
        project_doc = {
            "name": body.name,
            "goal": body.goal,
            "due_date": body.due_date,
            "steps": formatted_steps,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        
        if _use_live_db(db):
            project_doc["_id"] = project_id
            project_doc["user_id"] = uid
            await db.workplan_projects.insert_one(project_doc)
            project_doc["id"] = project_id
        else:
            if uid not in _IN_MEMORY_PROJECTS:
                _IN_MEMORY_PROJECTS[uid] = get_demo_projects()
            project_doc["id"] = project_id
            _IN_MEMORY_PROJECTS[uid].append(project_doc)
            
        # Also create initial tasks for the project steps
        for step_index, step in enumerate(formatted_steps):
            t_id = str(uuid.uuid4())
            task_doc = {
                "title": f"[{body.name}] {step['name']}",
                "owner": step["owner"],
                "due_date": step["due_date"],
                "source": f"Project: {body.name}",
                "status": "pending",
                "context": f"Part of the {body.name} project",
                # Link back to the parent project step so completing the task
                # keeps the project's progress in sync.
                "project_id": project_id,
                "project_step_index": step_index,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            if _use_live_db(db):
                task_doc["_id"] = t_id
                task_doc["user_id"] = uid
                await db.workplan_tasks.insert_one(task_doc)
            else:
                if uid not in _IN_MEMORY_TASKS:
                    _IN_MEMORY_TASKS[uid] = get_demo_tasks()
                task_doc["id"] = t_id
                _IN_MEMORY_TASKS[uid].append(task_doc)

        return project_doc

    @router.post("/projects/{project_id}/steps/{step_index}/status")
    async def update_project_step_status(
        project_id: str,
        step_index: int,
        status: str = Body(embed=True),
        user=Depends(get_current_user)
    ):
        uid = _uid(user)
        
        if _use_live_db(db):
            project = await db.workplan_projects.find_one(_id_filter(project_id, uid))
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            steps = project.get("steps", [])
            if 0 <= step_index < len(steps):
                steps[step_index]["status"] = status
                
            await db.workplan_projects.update_one(
                _id_filter(project_id, uid),
                {"$set": {"steps": steps, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
        else:
            projects = _IN_MEMORY_PROJECTS.get(uid, get_demo_projects())
            found = False
            for p in projects:
                if p["id"] == project_id:
                    steps = p.get("steps", [])
                    if 0 <= step_index < len(steps):
                        steps[step_index]["status"] = status
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=404, detail="Project not found")
            _IN_MEMORY_PROJECTS[uid] = projects
            
        return {"ok": True}

    @router.delete("/projects/{project_id}")
    async def delete_project(project_id: str, user=Depends(get_current_user)):
        uid = _uid(user)
        if _use_live_db(db):
            res = await db.workplan_projects.delete_one(_id_filter(project_id, uid))
            if res.deleted_count == 0:
                raise HTTPException(status_code=404, detail="Project not found")
            # Remove the step tasks generated for this project too.
            await db.workplan_tasks.delete_many({"user_id": uid, "project_id": project_id})
        else:
            projects = _IN_MEMORY_PROJECTS.get(uid, get_demo_projects())
            new_projects = [p for p in projects if p["id"] != project_id]
            if len(new_projects) == len(projects):
                raise HTTPException(status_code=404, detail="Project not found")
            _IN_MEMORY_PROJECTS[uid] = new_projects
            if uid in _IN_MEMORY_TASKS:
                _IN_MEMORY_TASKS[uid] = [
                    t for t in _IN_MEMORY_TASKS[uid] if t.get("project_id") != project_id
                ]
        return {"ok": True}

    @router.post("/parse-input")
    async def parse_input(body: ParseInputRequest, user=Depends(get_current_user)):
        """
        Main intelligence endpoint to accept notes, transcript, or voice updates from anywhere.
        Zilo parses the text, maps actions, auto-completes tasks, or generates new ones.
        """
        uid = _uid(user)
        from rex.workplan.service import parse_notes_and_create_tasks
        
        tasks_list = await get_tasks(uid)
        
        # Call LLM helper
        result = await parse_notes_and_create_tasks(body.text, tasks_list)
        
        # Apply LLM updates
        # 1. Complete existing tasks — but only if the pasted text actually
        # expresses completion. Without this guard, re-pasting a task's own
        # description leads the LLM to "complete" the matching open task.
        completed_task_ids = result.get("completed_task_ids", [])
        if not _has_completion_signal(body.text):
            if completed_task_ids:
                logger.info(
                    "[workplan] ignoring %d LLM completion(s); no completion language in input",
                    len(completed_task_ids),
                )
            completed_task_ids = []
        for tid in completed_task_ids:
            if _use_live_db(db):
                await db.workplan_tasks.update_one(
                    _id_filter(tid, uid),
                    {"$set": {"status": "done", "completed_at": datetime.now(timezone.utc).isoformat()}}
                )
            else:
                for t in _IN_MEMORY_TASKS.get(uid, []):
                    if t["id"] == tid:
                        t["status"] = "done"
                        t["completed_at"] = datetime.now(timezone.utc).isoformat()
                        
        # 2. Create new tasks
        new_tasks_added = []
        for nt in result.get("new_tasks", []):
            nt_id = str(uuid.uuid4())
            nt_title = nt.get("title")
            nt_owner = safe_owner(nt.get("owner"), nt_title or "")
            # Pasting the same notes twice must not create duplicate tasks.
            if await has_open_duplicate(uid, nt_title or "", nt_owner):
                continue
            new_task = {
                "title": nt_title,
                "owner": nt_owner,
                "due_date": nt.get("due_date"),
                "source": nt.get("source", "Zilo parsed input"),
                "status": "pending",
                "context": nt.get("context"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if nt_owner == "zilo":
                new_task["zilo_status"] = "scheduled"
            if _use_live_db(db):
                new_task["_id"] = nt_id
                new_task["user_id"] = uid
                await db.workplan_tasks.insert_one(new_task)
                new_task["id"] = nt_id
            else:
                new_task["id"] = nt_id
                if uid not in _IN_MEMORY_TASKS:
                    _IN_MEMORY_TASKS[uid] = get_demo_tasks()
                _IN_MEMORY_TASKS[uid].append(new_task)
            new_tasks_added.append(new_task)

        # 3. Update notebook
        if result.get("notebook_entries"):
            if _use_live_db(db):
                from rex_routes import _persist_orch_with_retry
                def mutate_notebook(orch):
                    from rex.memory import Bucket
                    for entry in result["notebook_entries"]:
                        orch.notebook.add(
                            bucket=Bucket.PEOPLE,
                            subject=entry.get("subject", "Sync Note"),
                            text=entry.get("text", "")
                        )
                await _persist_orch_with_retry(user, db, mutate=mutate_notebook)
                    
        return {
            "ok": True,
            "completed_task_ids": completed_task_ids,
            "new_tasks": new_tasks_added,
            "notebook_entries": result.get("notebook_entries", [])
        }

    @router.get("/briefing")
    async def get_briefing_integration(user=Depends(get_current_user)):
        uid = _uid(user)
        tasks = await get_tasks(uid)
        
        # Compile briefing:
        # 1. Due today
        due_today = []
        now = datetime.now(timezone.utc)
        today_date = now.date()
        
        for t in tasks:
            if t.get("status") != "done" and t.get("owner") == "founder":
                if t.get("due_date"):
                    try:
                        due_dt = datetime.fromisoformat(t["due_date"].replace('Z', '+00:00'))
                        if due_dt.date() == today_date:
                            due_today.append(t)
                    except ValueError:
                        pass
        
        # 2. Zilo completed overnight (Zilo tasks completed in last 24 hours)
        completed_overnight = []
        for t in tasks:
            if t.get("status") == "done" and t.get("owner") == "zilo":
                if t.get("completed_at"):
                    try:
                        comp_dt = datetime.fromisoformat(t["completed_at"].replace('Z', '+00:00'))
                        if now - comp_dt < timedelta(hours=24):
                            completed_overnight.append(t)
                    except ValueError:
                        pass
                        
        # 3. Coming up (pending tasks due in the next 3 days, or upcoming project steps)
        coming_up = []
        three_days_later = today_date + timedelta(days=3)
        for t in tasks:
            if t.get("status") != "done":
                if t.get("due_date"):
                    try:
                        due_dt = datetime.fromisoformat(t["due_date"].replace('Z', '+00:00'))
                        if today_date < due_dt.date() <= three_days_later:
                            coming_up.append(t)
                    except ValueError:
                        pass
                        
        return {
            "due_today": due_today,
            "completed_overnight": completed_overnight,
            "coming_up": coming_up
        }

    return router
