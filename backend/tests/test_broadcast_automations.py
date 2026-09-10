"""The automations must read the fields the endpoints actually write.

create_auto_followup stored "follow_up_message". execute_broadcast_automations
read "followup_message", got the empty-string default, and hit its `continue`
every single time -- so auto follow-up never fired once, for anyone, and
nothing anywhere reported a problem. The automation sat in the list marked
"active" forever.

Nothing catches that class of bug at runtime: both names are plausible, the
read has a default, and the skip is silent. So it is checked here against the
source, alongside the live behaviour it produces.
"""
import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SRC = (BACKEND / "server.py").read_text(encoding="utf-8-sig", errors="replace")


def _function_source(name: str) -> str:
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SRC, node) or ""
    raise AssertionError(f"{name} not found in server.py")


def test_the_follow_up_message_is_read_under_the_name_it_is_stored_under():
    written = _function_source("create_auto_followup")
    executor = _function_source("execute_broadcast_automations")

    assert '"follow_up_message"' in written, (
        "create_auto_followup no longer stores follow_up_message"
    )
    assert "follow_up_message" in executor, (
        "execute_broadcast_automations does not read follow_up_message -- "
        "auto follow-up will silently never fire, which is exactly the bug "
        "this test exists for"
    )


def test_every_automation_field_written_is_a_field_read():
    """Any key create_* stores must be one the executor knows about."""
    executor = _function_source("execute_broadcast_automations")
    for endpoint in ("create_auto_followup", "create_recurring_broadcast"):
        written = _function_source(endpoint)
        insert = written[written.index("broadcast_automations.insert_one"):]
        # Stop at the end of the insert call, or the return statement's own
        # keys get counted as stored fields.
        insert = insert[:insert.index("})") + 2]
        keys = set(re.findall(r'"([a-z_]+)":', insert))
        # Bookkeeping the executor has no reason to read.
        keys -= {"_id", "user_id", "status", "created_at", "runs", "type"}
        unread = sorted(k for k in keys if k not in executor)
        assert not unread, (
            f"{endpoint} stores {unread} but execute_broadcast_automations "
            "never reads those keys -- a stored setting nothing acts on"
        )


def test_the_follow_up_is_sent_through_the_paced_sender():
    """It used to send in a tight loop with no delay between messages."""
    executor = _function_source("execute_broadcast_automations")
    followup = executor[:executor.index('elif a_type == "recurring"')]
    assert "send_broadcast_messages" in followup, (
        "auto follow-up must go through the ordinary broadcast sender so it is "
        "paced and resumable; sending in a bare loop is how a number gets banned"
    )


def test_neither_automation_blocks_the_loop_behind_a_paced_send():
    """A paced send runs for an hour; awaiting it stalls every other automation."""
    executor = _function_source("execute_broadcast_automations")
    assert not re.search(r"^\s*await send_broadcast_messages\(", executor, re.M), (
        "send_broadcast_messages is awaited inline in the automation loop; "
        "with pacing that holds up every automation behind it for hours"
    )
    assert executor.count("asyncio.create_task(") >= 1


def test_replies_are_found_in_one_query_not_one_per_customer():
    executor = _function_source("execute_broadcast_automations")
    followup = executor[:executor.index('elif a_type == "recurring"')]
    assert "distinct(" in followup, (
        "the no-reply filter should ask once who replied, not run a query per "
        "customer -- that was 5,000 round trips on the largest account here"
    )
