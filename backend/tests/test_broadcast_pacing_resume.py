"""A broadcast sends slowly, survives a restart, and never sends twice.

Bulk traffic through an unofficial gateway is what gets a number banned, so the
send is paced on purpose: a wait between every message and a longer rest after
each batch. A few hundred recipients therefore takes an hour or more, which
means a deploy will land in the middle of one sooner or later. Each delivery is
recorded as it happens so a resumed run skips whoever already has the message.

Sending nothing is bad. Sending the same person the same broadcast twice is
worse, and it is the failure a naive resume produces.
"""
import asyncio
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import whatsapp_service as ws  # noqa: E402


# ----------------------------------------------------------------- pacing

def test_there_is_always_a_gap_between_two_messages():
    low, high = ws.BROADCAST_DELAY
    assert low > 0, "a zero delay is a burst, which is what gets a number banned"
    assert high >= low


def test_the_run_rests_between_batches():
    assert ws.BROADCAST_BATCH_SIZE > 0
    rest_low, _ = ws.BROADCAST_BATCH_REST
    # A rest that is no longer than an ordinary gap is not a rest.
    assert rest_low > ws.BROADCAST_DELAY[1]


# ------------------------------------------------------- a tiny fake Mongo

class FakeCollection:
    def __init__(self, docs=None):
        self.docs = {d["_id"]: dict(d) for d in (docs or [])}

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not k.startswith("$")):
                return dict(doc)
        return None

    async def update_one(self, query, update):
        for doc in self.docs.values():
            if not all(doc.get(k) == v for k, v in query.items()
                       if not k.startswith("$") and not isinstance(v, dict)):
                continue
            for k, v in (update.get("$set") or {}).items():
                doc[k] = v
            for k, v in (update.get("$addToSet") or {}).items():
                doc.setdefault(k, [])
                if v not in doc[k]:
                    doc[k].append(v)
            return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()


class FakeDB:
    def __init__(self, broadcast):
        self.broadcasts = FakeCollection([broadcast])


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    async def send_message(self, user_id, to_number, message, **kw):
        self.sent.append(to_number)
        return {"success": True}


def _customers(n):
    return [{"_id": f"c{i}", "name": f"P{i}", "phone_number": f"25470000000{i}"}
            for i in range(n)]


@pytest.fixture
def fast_pacing(monkeypatch):
    monkeypatch.setattr(ws, "BROADCAST_DELAY", (0, 0))
    monkeypatch.setattr(ws, "BROADCAST_BATCH_SIZE", 0)
    monkeypatch.setattr(ws, "BROADCAST_BATCH_REST", (0, 0))


def _run(broadcast, customers, monkeypatch):
    import server

    fake_wa = FakeWhatsApp()
    db = FakeDB(broadcast)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(ws, "get_whatsapp_service", lambda _db: fake_wa)

    asyncio.run(server.send_broadcast_messages(
        broadcast["_id"], broadcast["user_id"], broadcast["message"], customers, []))
    return fake_wa, db.broadcasts.docs[broadcast["_id"]]


def _broadcast(**over):
    doc = {"_id": "b1", "user_id": "u1", "message": "Hi {{name}}",
           "status": "pending", "sent_ids": [], "sent_count": 0}
    doc.update(over)
    return doc


def test_a_resumed_send_skips_everyone_who_already_got_it(fast_pacing, monkeypatch):
    customers = _customers(5)
    bc = _broadcast(status="sending", sent_ids=["c0", "c1"], sent_count=2)
    wa, final = _run(bc, customers, monkeypatch)

    assert wa.sent == ["254700000002", "254700000003", "254700000004"], (
        "a resume must not message the people it already reached"
    )
    assert final["sent_count"] == 5
    assert final["status"] == "completed"


def test_a_fresh_send_reaches_everyone_once(fast_pacing, monkeypatch):
    customers = _customers(4)
    wa, final = _run(_broadcast(), customers, monkeypatch)
    assert len(wa.sent) == len(set(wa.sent)) == 4
    assert final["status"] == "completed"


def test_progress_is_recorded_as_it_goes_not_at_the_end(fast_pacing, monkeypatch):
    """If it were written at the end, a restart would lose the whole run."""
    customers = _customers(3)
    bc = _broadcast()
    wa, final = _run(bc, customers, monkeypatch)
    assert set(final["sent_ids"]) == {"c0", "c1", "c2"}
    assert final.get("progress_at") is not None, (
        "progress_at is what tells the scheduler a send is alive, not abandoned"
    )


def test_a_send_that_reaches_nobody_is_failed_not_completed(fast_pacing, monkeypatch):
    import server

    class DeadWhatsApp:
        sent = []

        async def send_message(self, *a, **kw):
            raise RuntimeError("WhatsApp disconnected")

    bc = _broadcast()
    db = FakeDB(bc)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(ws, "get_whatsapp_service", lambda _db: DeadWhatsApp())
    asyncio.run(server.send_broadcast_messages(
        "b1", "u1", "Hi", _customers(3), []))

    final = db.broadcasts.docs["b1"]
    assert final["status"] == "failed"
    assert final["sent_count"] == 0
    assert final["failed_count"] == 3


def test_the_scheduler_exists_and_is_started():
    """Scheduling was offered in the app and nothing ever sent those rows."""
    import server

    assert hasattr(server, "process_due_and_stalled_broadcasts")
    assert hasattr(server, "run_broadcast_scheduler")
    src = (BACKEND / "server.py").read_text(encoding="utf-8-sig", errors="replace")
    assert "asyncio.create_task(run_broadcast_scheduler())" in src, (
        "the scheduler must actually be started, or scheduled broadcasts "
        "sit in the database forever like they used to"
    )


def test_a_long_missed_schedule_is_not_sent_late():
    """A broadcast written for last month should not go out today."""
    src = (BACKEND / "server.py").read_text(encoding="utf-8-sig", errors="replace")
    fn = src[src.index("async def process_due_and_stalled_broadcasts"):]
    fn = fn[:fn.index("async def run_broadcast_scheduler")]
    assert "scheduled time missed" in fn and "never started" in fn, (
        "stale scheduled and never-started broadcasts must be closed as failed, "
        "not fired off unexpectedly at whoever is in the audience now"
    )


# ------------------------------------------- believing what the send returns

def test_send_status_reads_the_result_not_the_absence_of_an_exception():
    import server

    assert server._send_status({"status": "success"}) == "ok"
    assert server._send_status({"status": "error", "message": "x"}) == "error"
    assert server._send_status({"status": "limit_reached"}) == "limit_reached"
    # Older shapes that just return an id, and anything unrecognised, count
    # as sent rather than silently dropping people.
    assert server._send_status({"id": "abc"}) == "ok"
    assert server._send_status(None) == "ok"


class ScriptedWhatsApp:
    def __init__(self, script):
        self.script = list(script)
        self.sent = []

    async def send_message(self, user_id, to_number, message, **kw):
        self.sent.append(to_number)
        return self.script.pop(0) if self.script else {"status": "success"}


def _run_scripted(broadcast, customers, script, monkeypatch):
    import server

    wa = ScriptedWhatsApp(script)
    db = FakeDB(broadcast)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(ws, "get_whatsapp_service", lambda _db: wa)
    asyncio.run(server.send_broadcast_messages(
        broadcast["_id"], broadcast["user_id"], broadcast["message"], customers, []))
    return wa, db.broadcasts.docs[broadcast["_id"]]


def test_a_message_the_gateway_refuses_is_not_counted_as_delivered(fast_pacing, monkeypatch):
    """It returns {"status": "error"} rather than raising."""
    wa, final = _run_scripted(
        _broadcast(), _customers(4),
        [{"status": "success"}, {"status": "error", "message": "not accepted"},
         {"status": "success"}, {"status": "success"}],
        monkeypatch)

    assert final["sent_count"] == 3
    assert final["failed_count"] == 1
    assert "c1" not in final["sent_ids"], (
        "a refused message must not go into sent_ids, or a resume will skip "
        "that person forever"
    )


def test_running_out_of_allowance_pauses_rather_than_burning_the_list(fast_pacing, monkeypatch):
    """The plan's daily cap stops a send; the rest must stay unsent."""
    wa, final = _run_scripted(
        _broadcast(), _customers(6),
        [{"status": "success"}, {"status": "success"},
         {"status": "limit_reached", "message": "Daily limit of 500 messages reached."}],
        monkeypatch)

    assert final["status"] == "paused"
    assert final["paused_reason"] == "Daily limit of 500 messages reached."
    assert len(wa.sent) == 3, "it should stop at the cap, not attempt everyone"
    assert final["sent_ids"] == ["c0", "c1"], (
        "only the two that actually went out may be recorded as delivered"
    )
