"""Never hand work to a queue unless something is consuming it.

The server enqueued broadcasts and receipts to Redis and only sent in-process
if enqueueing *failed*. Redis being reachable says nothing about whether a
consumer exists, and this deployment's render.yaml defines three web services
and no worker -- worker.py is never started. So the job sat in Redis forever:
the broadcast record stuck on "pending", the receipt never sent, nothing
raised, and the owner told nothing.

Every queue in worker.QUEUES needs a live worker before anything is handed to
it. The exception is a queue whose jobs are also durable somewhere else --
webhook deliveries are written to MongoDB first and the consumer polls it, so
losing the Redis job costs latency, not the work.
"""
import ast
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SERVER = BACKEND / "server.py"

# Queues drained by worker.py, which nothing currently starts.
WORKER_QUEUES = {"QUEUE_BROADCAST", "QUEUE_RECEIPT", "QUEUE_AI_REPLY"}


def _enqueue_calls(tree):
    """Every enqueue_job(...) call, with the queue name it targets."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        if name != "enqueue_job" or not node.args:
            continue
        first = node.args[0]
        queue = first.id if isinstance(first, ast.Name) else getattr(first, "attr", None)
        yield node, queue


def test_every_worker_queue_handoff_checks_for_a_live_worker():
    src = SERVER.read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(src)

    unguarded = []
    for node, queue in _enqueue_calls(tree):
        if queue not in WORKER_QUEUES:
            continue
        # The guard sits on the same statement: `await worker_is_alive() and
        # await enqueue_job(...)`. Read the source line it starts on plus the
        # line above, which is where the assignment begins.
        lines = src.splitlines()
        window = "\n".join(lines[max(0, node.lineno - 3):node.lineno])
        if "worker_is_alive" not in window:
            unguarded.append(f"server.py:{node.lineno} enqueues to {queue} "
                             "without checking worker_is_alive()")
    assert not unguarded, "\n".join(unguarded)


def test_a_handoff_still_has_an_in_process_fallback():
    """Guarding the enqueue is only half of it; the work must still happen."""
    src = SERVER.read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(src)
    missing = []
    lines = src.splitlines()
    for node, queue in _enqueue_calls(tree):
        if queue not in WORKER_QUEUES:
            continue
        after = "\n".join(lines[node.lineno - 1:node.lineno + 25])
        if "if not queued" not in after:
            missing.append(f"server.py:{node.lineno} enqueues to {queue} with no "
                           "`if not queued:` fallback -- the job is lost when "
                           "there is no worker")
    assert not missing, "\n".join(missing)


def test_the_heartbeat_helpers_exist_and_fail_closed():
    from redis_client import WORKER_HEARTBEAT_TTL, worker_is_alive

    # blpop waits up to 30s per loop, so the window must comfortably exceed it
    # or a busy worker would be declared dead mid-job.
    assert WORKER_HEARTBEAT_TTL >= 60

    import asyncio
    import redis_client

    async def _no_redis():
        return None

    original = redis_client.get_redis
    redis_client.get_redis = _no_redis
    try:
        # No Redis at all means no worker, so send in-process rather than
        # assuming one is there.
        assert asyncio.run(worker_is_alive()) is False
    finally:
        redis_client.get_redis = original


def test_worker_publishes_the_heartbeat():
    src = (BACKEND / "worker.py").read_text(encoding="utf-8-sig", errors="replace")
    assert "worker_heartbeat" in src, (
        "worker.py must publish a heartbeat, or the server will always fall "
        "back to in-process sending even when a worker is running"
    )
    tree = ast.parse(src)
    in_loop = False
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            body = ast.dump(node)
            if "worker_heartbeat" in body:
                in_loop = True
    assert in_loop, "the heartbeat must be refreshed inside the worker loop, not once at startup"
