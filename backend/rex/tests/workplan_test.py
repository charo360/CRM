"""
Unit tests for the Zilo Work Plan AI parsing services and HTTP routes.
"""
from __future__ import annotations
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rex.workplan.service import (
    parse_quick_update_with_llm,
    suggest_project_steps_with_llm,
    parse_notes_and_create_tasks,
)
from rex.workplan.routes import init_workplan_routes, _IN_MEMORY_TASKS, _IN_MEMORY_PROJECTS


def run_async(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# Mock current user dependency
def mock_get_current_user():
    return {"id": "test_user_123", "_id": "test_user_123", "email": "founder@test.com"}


@pytest.fixture
def test_client():
    # Clear in-memory DBs
    _IN_MEMORY_TASKS.clear()
    _IN_MEMORY_PROJECTS.clear()
    
    app = FastAPI()
    router = init_workplan_routes(mock_get_current_user, db=None)
    app.include_router(router)
    return TestClient(app)


class TestWorkPlanService:
    def test_parse_quick_update_fallback_done(self):
        """Test fallback parsing of quick logs when complete keywords are used."""
        res = run_async(parse_quick_update_with_llm("Call Chen Li", "I signed the NDA and got it done."))
        assert res["complete"] is True
        assert len(res["new_tasks"]) == 0

    def test_parse_quick_update_fallback_progress_and_followup(self):
        """Test fallback parsing of progress updates and follow up triggers."""
        res = run_async(parse_quick_update_with_llm("Call leads", "Called 3 of them. Need to follow up next week."))
        assert res["complete"] is False
        assert "3 steps done" in res["progress"] or "3 done" in res["progress"]
        assert len(res["new_tasks"]) == 1
        assert "Follow up" in res["new_tasks"][0]["title"]

    def test_suggest_project_steps_fallback(self):
        """Test fallback step generation for projects."""
        steps = run_async(suggest_project_steps_with_llm("Launch CRM", "Acquire 10 customers", "2026-06-30T00:00:00Z"))
        assert len(steps) >= 3
        # Should have at least one founder step and one Zilo step
        owners = {s["owner"] for s in steps}
        assert "founder" in owners
        assert "zilo" in owners

    def test_parse_notes_and_create_tasks_fallback(self):
        """Test notes parsing matching current tasks and extracting commitments."""
        current_tasks = [
            {"id": "task_nda", "title": "Get NDA signed by Henderson"},
            {"id": "task_other", "title": "Other work"},
        ]
        res = run_async(parse_notes_and_create_tasks(
            "Met with Henderson. The NDA is signed. Sam will send the deck by Friday.",
            current_tasks
        ))
        assert "task_nda" in res["completed_task_ids"]
        assert len(res["new_tasks"]) == 1
        assert "deck" in res["new_tasks"][0]["title"].lower()


class TestWorkPlanRoutes:
    def test_get_workplan_initial_load(self, test_client):
        """Test loading initial workplan returns tasks and projects."""
        res = test_client.get("/workplan")
        assert res.status_code == 200
        data = res.json()
        assert "tasks" in data
        assert "projects" in data
        assert len(data["tasks"]) > 0

    def test_create_task(self, test_client):
        """Test creating a manual task."""
        res = test_client.post("/workplan/tasks", json={
            "title": "Review marketing copy",
            "owner": "founder",
            "due_date": "2026-06-15T12:00:00Z",
            "context": "Needs review before publish",
            "sub_tasks": ["Check headline", "Check CTA"]
        })
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "Review marketing copy"
        assert len(data["sub_tasks"]) == 2
        assert data["sub_tasks"][0]["done"] is False

    def test_complete_task(self, test_client):
        """Test marking a task completed."""
        # Get tasks first to find a pending one
        data = test_client.get("/workplan").json()
        pending_task = next(t for t in data["tasks"] if t["status"] == "pending")
        
        res = test_client.post(f"/workplan/tasks/{pending_task['id']}/complete")
        assert res.status_code == 200
        assert res.json() == {"ok": True}
        
        # Verify status updated
        updated_data = test_client.get("/workplan").json()
        completed_task = next(t for t in updated_data["tasks"] if t["id"] == pending_task["id"])
        assert completed_task["status"] == "done"

    def test_toggle_subtask(self, test_client):
        """Test toggling a subtask done status."""
        data = test_client.get("/workplan").json()
        task_with_subtasks = next(t for t in data["tasks"] if len(t.get("sub_tasks", [])) > 0)
        task_id = task_with_subtasks["id"]
        
        res = test_client.post(f"/workplan/tasks/{task_id}/subtask/3/toggle")
        assert res.status_code == 200
        
        # Verify fourth subtask is now done
        updated_data = test_client.get("/workplan").json()
        updated_task = next(t for t in updated_data["tasks"] if t["id"] == task_id)
        assert updated_task["sub_tasks"][3]["done"] is True

    def test_delegate_and_reassign_task(self, test_client):
        """Test delegating task to Zilo and reassigning to founder."""
        # 1. Delegate a delegatable task
        res = test_client.post("/workplan/tasks", json={
            "title": "Clean list data",
            "owner": "founder"
        })
        task_id = res.json()["id"]
        
        del_res = test_client.post(f"/workplan/tasks/{task_id}/delegate")
        assert del_res.status_code == 200
        assert del_res.json() == {"ok": True}
        
        # Verify owner is now Zilo
        task_data = next(t for t in test_client.get("/workplan").json()["tasks"] if t["id"] == task_id)
        assert task_data["owner"] == "zilo"
        
        # 2. Reassign back to founder
        re_res = test_client.post(f"/workplan/tasks/{task_id}/reassign")
        assert re_res.status_code == 200
        assert re_res.json() == {"ok": True}
        
        task_data_re = next(t for t in test_client.get("/workplan").json()["tasks"] if t["id"] == task_id)
        assert task_data_re["owner"] == "founder"

    def test_delegate_non_delegatable_task(self, test_client):
        """Test delegating non-delegatable task returns customized warning."""
        res = test_client.post("/workplan/tasks", json={
            "title": "Sign the partnership contract",
            "owner": "founder"
        })
        task_id = res.json()["id"]
        
        del_res = test_client.post(f"/workplan/tasks/{task_id}/delegate")
        assert del_res.status_code == 200
        del_data = del_res.json()
        assert del_data["ok"] is False
        assert "needs you personally" in del_data["warning"]

    def test_log_task_update(self, test_client):
        """Test logging task update updates status and creates followups."""
        res = test_client.post("/workplan/tasks", json={
            "title": "Check invoices",
            "owner": "founder"
        })
        task_id = res.json()["id"]
        
        log_res = test_client.post(f"/workplan/tasks/{task_id}/log", json={
            "update_text": "I got it done. Call back next week if they don't reply."
        })
        assert log_res.status_code == 200
        log_data = log_res.json()
        assert log_data["ok"] is True
        assert log_data["analysis"]["complete"] is True
        
        # Verify task is complete and follow-up was created
        updated_data = test_client.get("/workplan").json()
        task_data = next(t for t in updated_data["tasks"] if t["id"] == task_id)
        assert task_data["status"] == "done"
        
        followup_task = next((t for t in updated_data["tasks"] if "Follow up" in t["title"]), None)
        assert followup_task is not None

    def test_create_project_suggest_and_confirm(self, test_client):
        """Test project step suggestions and final confirmation creation."""
        # 1. Suggestion mode
        sug_res = test_client.post("/workplan/projects", json={
            "name": "Design New Homepage",
            "goal": "Rebrand the site and make it faster",
            "due_date": "2026-07-01T00:00:00Z",
            "confirm": False
        })
        assert sug_res.status_code == 200
        sug_data = sug_res.json()
        assert "suggested_steps" in sug_data
        assert len(sug_data["suggested_steps"]) > 0
        
        # 2. Confirm mode
        conf_res = test_client.post("/workplan/projects", json={
            "name": "Design New Homepage",
            "goal": "Rebrand the site and make it faster",
            "due_date": "2026-07-01T00:00:00Z",
            "confirm": True
        })
        assert conf_res.status_code == 200
        conf_data = conf_res.json()
        assert conf_data["name"] == "Design New Homepage"
        assert len(conf_data["steps"]) > 0
        
        # Verify project exists and project step tasks created
        wp_data = test_client.get("/workplan").json()
        assert any(p["name"] == "Design New Homepage" for p in wp_data["projects"])
        assert any("Design New Homepage" in t["title"] for t in wp_data["tasks"])

    def test_parse_input_dedups_against_open_task(self, test_client):
        """Pasting notes whose task already exists (open) must not duplicate it."""
        # Demo seed already contains an open "Send pitch deck to investor" task.
        res = test_client.post("/workplan/parse-input", json={
            "text": "Signed the partnership contract. Sam will send the deck by Friday."
        })
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert len(data["new_tasks"]) == 0  # deduped, not re-created

        wp = test_client.get("/workplan").json()
        deck = [t for t in wp["tasks"] if "pitch deck" in t["title"].lower()]
        assert len(deck) == 1

    def test_parse_input_creates_after_existing_done(self, test_client):
        """Once the matching task is done, the same paste can create a fresh one."""
        wp = test_client.get("/workplan").json()
        deck = next(t for t in wp["tasks"] if "pitch deck" in t["title"].lower())
        test_client.post(f"/workplan/tasks/{deck['id']}/complete")

        res = test_client.post("/workplan/parse-input", json={
            "text": "Sam will send the deck by Friday."
        })
        assert res.status_code == 200
        assert len(res.json()["new_tasks"]) == 1

    def test_create_task_dedup(self, test_client):
        """Creating the same open task twice returns a duplicate warning, not a copy."""
        r1 = test_client.post("/workplan/tasks", json={"title": "Review Q3 budget", "owner": "founder"})
        assert r1.status_code == 200
        assert r1.json().get("id")

        # Same title with different case/whitespace is still a duplicate.
        r2 = test_client.post("/workplan/tasks", json={"title": "  review q3 budget ", "owner": "founder"})
        assert r2.status_code == 200
        assert r2.json().get("duplicate") is True

        matches = [t for t in test_client.get("/workplan").json()["tasks"]
                   if "review q3 budget" in t["title"].lower()]
        assert len(matches) == 1

    def test_parse_input_ignores_completion_without_signal(self, test_client, monkeypatch):
        """Re-pasting a task description (no completion words) must NOT mark it done."""
        r = test_client.post("/workplan/tasks", json={"title": "Fix duplicate call bug", "owner": "founder"})
        tid = r.json()["id"]

        async def fake_parse(notes_text, current_tasks):
            return {"completed_task_ids": [tid], "new_tasks": [], "notebook_entries": []}

        import rex.workplan.service as svc
        monkeypatch.setattr(svc, "parse_notes_and_create_tasks", fake_parse)

        # No completion language -> completion ignored, task stays open.
        test_client.post("/workplan/parse-input", json={
            "text": "Fix duplicate call bug. This may be a bug or inefficiency."
        })
        task = next(t for t in test_client.get("/workplan").json()["tasks"] if t["id"] == tid)
        assert task["status"] != "done"

        # Explicit completion language -> completion is applied.
        test_client.post("/workplan/parse-input", json={
            "text": "Fixed the duplicate call bug, it's done."
        })
        task2 = next(t for t in test_client.get("/workplan").json()["tasks"] if t["id"] == tid)
        assert task2["status"] == "done"

    def test_sync_calendar_events_to_workplan(self):
        """Test that sync_calendar_events_to_workplan fetches calendar, resolves CRM context, offsets prep due, and inserts tasks."""
        from unittest.mock import AsyncMock, MagicMock, patch
        import sys
        
        # Mock composio_service
        mock_composio = MagicMock()
        mock_composio.get_connection_status = AsyncMock(return_value={"connected": True})
        mock_composio.execute_action = AsyncMock(return_value={
            "items": [
                {
                    "summary": "Sales call — Chen Li",
                    "attendees": [{"email": "chen.li@example.com"}],
                    "start": {"dateTime": "2026-06-10T10:00:00Z"},
                    "end": {"dateTime": "2026-06-10T11:00:00Z"}
                }
            ]
        })
        
        sys.modules["composio_service"] = mock_composio
        
        from rex.workplan.routes import sync_calendar_events_to_workplan
        
        # Mock db and collections
        db = AsyncMock()
        db.customers.find_one = AsyncMock(return_value={
            "_id": "customer_chen_li",
            "name": "Chen Li",
            "email": "chen.li@example.com",
            "last_contacted": "2026-06-04T10:00:00Z", # 6 days before June 10
            "tags": ["proposal"]
        })
        
        db.workplan_tasks.find_one = AsyncMock(return_value=None)
        
        inserted_docs = []
        db.workplan_tasks.insert_one = AsyncMock(side_effect=lambda doc: inserted_docs.append(doc))
        
        with patch.dict("os.environ", {"ZILO_DEMO_ONLY": "0"}):
            run_async(sync_calendar_events_to_workplan(db, {"_id": "test_user_123"}))
            
        assert len(inserted_docs) == 2
        founder_task = next(t for t in inserted_docs if t["owner"] == "founder")
        zilo_task = next(t for t in inserted_docs if t["owner"] == "zilo")
        
        assert "Prep for sales call" in founder_task["title"]
        assert "Last contact" in founder_task["context"]
        assert "Proposal pending." in founder_task["context"]
        # Verify 1-hour offset: meeting at 10:00:00, prep due at 09:00:00
        assert "T09:00:00" in founder_task["due_date"]
        
        assert "Pull Chen Li's history" in zilo_task["title"]
        assert zilo_task["zilo_status"] == "running"
