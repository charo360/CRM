"""
30 / 60 / 90-day outcome tracking for recorded decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from rex.decisions.context import gather_decision_context

logger = logging.getLogger(__name__)

OUTCOME_CHECKPOINT_DAYS = (30, 60, 90)


def normalize_review_days(raw: Any) -> list[int]:
    """Validate a custom review schedule; fall back to 30/60/90 default."""
    if not raw or not isinstance(raw, (list, tuple)):
        return list(OUTCOME_CHECKPOINT_DAYS)
    out: set[int] = set()
    for v in raw:
        try:
            d = int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= d <= 365:
            out.add(d)
    if not out:
        return list(OUTCOME_CHECKPOINT_DAYS)
    return sorted(out)[:6]


def baseline_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Snapshot metrics at decision time."""
    return {
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "customer_count": ctx.get("customer_count"),
        "revenue_30d": ctx.get("revenue_30d"),
        "revenue_90d": ctx.get("revenue_90d"),
        "sales_count_30d": ctx.get("sales_count_30d"),
        "stalled_deals": ctx.get("stalled_deals"),
        "followups_due": ctx.get("followups_due"),
        "followup_conversion_30d": ctx.get("followup_conversion_30d"),
        "followup_response_rate_30d": ctx.get("followup_response_rate_30d"),
        "open_orders": ctx.get("open_orders"),
        "pending_payments": ctx.get("pending_payments"),
    }


def _checkpoints_from_decided_at(
    decided_at: datetime, days: list[int] | tuple[int, ...] | None = None
) -> list[dict[str, Any]]:
    if decided_at.tzinfo is not None:
        decided_at = decided_at.replace(tzinfo=None)
    day_list = list(days) if days else list(OUTCOME_CHECKPOINT_DAYS)
    out = []
    for day in day_list:
        out.append({
            "day": day,
            "due_at": (decided_at + timedelta(days=day)).isoformat() + "Z",
            "status": "pending",
        })
    return out


def init_outcome_tracking(
    decided_at: datetime,
    baseline: dict[str, Any],
    days: list[int] | tuple[int, ...] | None = None,
) -> dict[str, Any]:
    return {
        "metrics_baseline": baseline,
        "outcome_checkpoints": _checkpoints_from_decided_at(decided_at, days),
        "outcome_reports": [],
    }


def rebuild_checkpoints_for_schedule(
    *,
    existing_checkpoints: list[dict[str, Any]] | None,
    outcome_reports: list[dict[str, Any]] | None,
    decided_at: datetime,
    review_days: list[int] | None,
) -> list[dict[str, Any]]:
    """Merge a new review schedule with checkpoints that already ran."""
    if decided_at.tzinfo is not None:
        decided_at = decided_at.replace(tzinfo=None)

    existing = existing_checkpoints or []
    reports = outcome_reports or []
    reported_days = {
        cp["day"]
        for cp in existing
        if cp.get("status") == "reported" and isinstance(cp.get("day"), int)
    }
    reported_days.update(
        r["day"] for r in reports if isinstance(r.get("day"), int)
    )

    new_days = set(normalize_review_days(review_days))
    all_days = sorted(reported_days | new_days)

    by_day = {cp["day"]: cp for cp in existing if isinstance(cp.get("day"), int)}
    out: list[dict[str, Any]] = []
    for day in all_days:
        existing_cp = by_day.get(day)
        if existing_cp and existing_cp.get("status") == "reported":
            out.append(existing_cp)
        else:
            out.append({
                "day": day,
                "due_at": (decided_at + timedelta(days=day)).isoformat() + "Z",
                "status": "pending",
            })
    return out


def _num_delta(current: Any, baseline: Any) -> dict[str, Any] | None:
    try:
        if current is None or baseline is None:
            return None
        c, b = float(current), float(baseline)
        if b == 0:
            return {"current": c, "baseline": b, "delta": c, "pct": None}
        return {
            "current": c,
            "baseline": b,
            "delta": round(c - b, 2),
            "pct": round((c - b) / b * 100, 1),
        }
    except (TypeError, ValueError):
        return None


VALID_VERDICTS = {"held_up", "mixed", "worth_revisiting", "too_early"}


def _deltas_block(baseline: dict[str, Any], current_ctx: dict[str, Any], currency: str) -> str:
    """Plain delta lines (baseline → now) for the review prompt / fallback."""
    lines: list[str] = []
    rev = _num_delta(current_ctx.get("revenue_30d"), baseline.get("revenue_30d"))
    if rev and rev.get("pct") is not None:
        sign = "+" if rev["delta"] >= 0 else ""
        lines.append(
            f"30d revenue: {currency} {rev['baseline']:,.0f} → {currency} {rev['current']:,.0f} ({sign}{rev['pct']}%)"
        )
    cust = _num_delta(current_ctx.get("customer_count"), baseline.get("customer_count"))
    if cust:
        sign = "+" if cust["delta"] >= 0 else ""
        lines.append(f"Customers: {int(cust['baseline'])} → {int(cust['current'])} ({sign}{int(cust['delta'])})")
    stalled = _num_delta(current_ctx.get("stalled_deals"), baseline.get("stalled_deals"))
    if stalled:
        lines.append(f"Stalled deals: {int(stalled['baseline'])} → {int(stalled['current'])}")
    conv = _num_delta(current_ctx.get("followup_conversion_30d"), baseline.get("followup_conversion_30d"))
    if conv:
        lines.append(f"Follow-up conversion: {conv['baseline']}% → {conv['current']}%")
    fd = _num_delta(current_ctx.get("followups_due"), baseline.get("followups_due"))
    if fd:
        lines.append(f"Overdue follow-ups: {int(fd['baseline'])} → {int(fd['current'])}")
    return "\n".join(lines) if lines else "No comparable metrics moved enough to report."


def _fallback_summary(
    *, session: dict, checkpoint_day: int, baseline: dict[str, Any], current_ctx: dict[str, Any]
) -> str:
    decision = (session.get("founder_decision") or "").strip()
    currency = current_ctx.get("currency") or "USD"
    parts = [f"Day {checkpoint_day} check on your call."]
    if decision:
        parts.append(f"You decided: {decision[:120]}.")
    parts.append(_deltas_block(baseline, current_ctx, currency).replace("\n", " · "))
    parts.append("Correlation isn't causation. Your call still stands unless you reopen it.")
    return " ".join(parts)


_OUTCOME_SYSTEM = """You are Zilo, reviewing the real-world outcome of a decision a solo founder made, N days ago.

You are an advisor, not a scorekeeper. Look at what moved since the decision and tell the founder what the numbers MEAN — interpret, don't recite. Connect the movement back to what they predicted or feared.

RULES:
- Never tell them to reverse or keep the decision. You may ask "Worth revisiting?" — that's a question, not a directive.
- Interpret as human reality, not raw numbers. "New customers fell 34% — the marketing pause is showing." not "customer_count delta -34%."
- Be honest when something went worse than expected. The value is in the truth.
- Note when correlation isn't causation, briefly.
- 3–5 sentences. Direct, warm, zero emoji, no hedging. Plain text.

Output EXACTLY this format:
VERDICT: <held_up|mixed|worth_revisiting|too_early>
<your 3–5 sentence review>

Verdict meaning:
- held_up: the decision looks right so far — the metrics moved the way the founder hoped.
- mixed: some of it worked, some didn't — trade-offs showing as expected.
- worth_revisiting: the numbers moved against the decision enough that it's worth a fresh look.
- too_early: not enough movement or data to judge yet."""


async def review_outcome(
    *,
    session: dict,
    checkpoint_day: int,
    baseline: dict[str, Any],
    current_ctx: dict[str, Any],
) -> tuple[str, str]:
    """Advisor-voice outcome review. Returns (summary, verdict)."""
    decision = (session.get("founder_decision") or "").strip()
    question = (session.get("question") or "").strip()
    currency = current_ctx.get("currency") or "USD"
    deltas = _deltas_block(baseline, current_ctx, currency)

    prompt = f"""DECISION REVIEWED (made {checkpoint_day} days ago):
Question: {question}
What the founder decided: {decision or "(not recorded)"}

WHAT MOVED SINCE THE DECISION (baseline → now):
{deltas}

Write the Day {checkpoint_day} review."""

    try:
        from rex.decisions.spar import _call_llm_text

        raw = await _call_llm_text(_OUTCOME_SYSTEM, prompt, max_tokens=350)
        if raw and raw.strip():
            verdict = "too_early"
            text = raw.strip()
            first, _, rest = text.partition("\n")
            if first.upper().startswith("VERDICT:"):
                v = first.split(":", 1)[1].strip().lower()
                if v in VALID_VERDICTS:
                    verdict = v
                text = rest.strip() or text
            return text, verdict
    except Exception as e:
        logger.warning("[decision-outcomes] LLM review failed: %s", e)

    return (
        _fallback_summary(
            session=session,
            checkpoint_day=checkpoint_day,
            baseline=baseline,
            current_ctx=current_ctx,
        ),
        "too_early",
    )


async def process_due_outcomes(
    db: Any,
    user: dict,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    """
    Evaluate decided sessions whose 30/60/90-day checkpoints are due.
    Returns list of newly created outcome reports.
    """
    uid = str(user.get("_id") or "")
    if not uid:
        return []

    now = datetime.utcnow()
    created: list[dict[str, Any]] = []

    try:
        cursor = db.decision_sessions.find({
            "user_id": uid,
            "status": "decided",
            "decided_at": {"$exists": True},
        }).sort("decided_at", -1).limit(50)
        sessions = await cursor.to_list(50)
    except Exception as e:
        logger.warning("[decision-outcomes] list: %s", e)
        return []

    current_ctx = await gather_decision_context(db, user)

    for doc in sessions or []:
        decided_at = doc.get("decided_at")
        if not decided_at:
            continue
        if hasattr(decided_at, "replace") and getattr(decided_at, "tzinfo", None) is not None:
            decided_at_naive = decided_at.replace(tzinfo=None)
        else:
            decided_at_naive = decided_at

        baseline = doc.get("metrics_baseline") or {}
        checkpoints = list(doc.get("outcome_checkpoints") or [])
        if not checkpoints:
            checkpoints = _checkpoints_from_decided_at(decided_at_naive)
        reports = list(doc.get("outcome_reports") or [])
        reported_days = {int(r.get("day")) for r in reports if r.get("day") is not None}
        session_new: list[dict[str, Any]] = []

        # Iterate this session's OWN schedule (supports custom review days).
        session_days = sorted({int(cp.get("day")) for cp in checkpoints if cp.get("day") is not None})
        if not session_days:
            session_days = list(OUTCOME_CHECKPOINT_DAYS)

        for day in session_days:
            if day in reported_days:
                continue
            due = decided_at_naive + timedelta(days=day)
            if not force and now < due:
                continue

            summary, verdict = await review_outcome(
                session=doc,
                checkpoint_day=day,
                baseline=baseline,
                current_ctx=current_ctx,
            )
            report = {
                "day": day,
                "due_at": due.isoformat() + "Z",
                "reported_at": now.isoformat() + "Z",
                "summary": summary,
                "verdict": verdict,
                "metrics_current": baseline_from_context(current_ctx),
                "metrics_baseline": baseline,
                "deltas": {
                    "revenue_30d": _num_delta(current_ctx.get("revenue_30d"), baseline.get("revenue_30d")),
                    "customer_count": _num_delta(current_ctx.get("customer_count"), baseline.get("customer_count")),
                    "stalled_deals": _num_delta(current_ctx.get("stalled_deals"), baseline.get("stalled_deals")),
                },
                "briefing_ack": False,
            }
            reports.append(report)
            session_new.append(report)

            for cp in checkpoints:
                if cp.get("day") == day:
                    cp["status"] = "reported"
                    cp["reported_at"] = report["reported_at"]

        if session_new:
            await db.decision_sessions.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "outcome_reports": reports,
                        "outcome_checkpoints": checkpoints,
                        "updated_at": now,
                    }
                },
            )
            sid = str(doc["_id"])
            for r in session_new:
                created.append({
                    **r,
                    "session_id": sid,
                    "question": doc.get("question"),
                })

    # Notify the founder when real deadlines arrive (skip forced/test runs).
    if created and not force:
        await _notify_outcomes_due(uid, created)

    return created


async def _notify_outcomes_due(user_id: str, created: list[dict[str, Any]]) -> None:
    """Best-effort push notification when a review checkpoint comes due."""
    try:
        from server import send_push_notification
    except Exception:
        return
    for r in created:
        try:
            day = r.get("day")
            question = (r.get("question") or "your decision").strip()[:60]
            title = f"Decision Room — Day {day} review"
            body = f"Time to review: {question}"
            await send_push_notification(
                user_id,
                title,
                body,
                {"type": "decision_outcome", "session_id": r.get("session_id"), "day": day},
            )
        except Exception as e:
            logger.debug("[decision-outcomes] notify failed: %s", e)
