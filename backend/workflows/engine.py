"""
engine.py — workflow execution engine.

Flow:
  1. fire_trigger(event) — check all enabled workflows for this tenant
  2. For each matching workflow, start a run
  3. Execute steps in order:
     - Steps with delay_minutes == 0 → run immediately
     - Steps with delay_minutes > 0  → store in workflow_pending_steps
  4. deferred_runner() — background loop that processes pending steps every 60s

Tenant isolation:
  Every query is scoped to user_id. No cross-tenant access is possible.

Capability safety:
  Only actions listed in capabilities.CAPABILITIES are executed.
  Unknown actions are skipped with a warning log.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .capabilities import CAPABILITIES
from .models import WorkflowEvent, WorkflowStep, PendingStep

logger = logging.getLogger(__name__)

# ── Condition evaluator ────────────────────────────────────────────────────────

def _evaluate_condition(condition: Optional[str], event: WorkflowEvent) -> bool:
    """
    Evaluate a simple condition string against event data.
    Supported forms:
      always
      intent == 'order'
      tag == 'hot_lead'
      stage == 'won'
      message_contains('price')
      sentiment == 'negative'
    """
    if not condition or condition.strip().lower() == "always":
        return True

    cond = condition.strip()
    data = event.data

    # intent == 'value'
    m = re.match(r"^intent\s*==\s*['\"]([^'\"]+)['\"]$", cond)
    if m:
        return data.get("intent", "") == m.group(1)

    # tag == 'value'
    m = re.match(r"^tag\s*==\s*['\"]([^'\"]+)['\"]$", cond)
    if m:
        return data.get("tag", "") == m.group(1)

    # stage == 'value'
    m = re.match(r"^stage\s*==\s*['\"]([^'\"]+)['\"]$", cond)
    if m:
        return data.get("stage", "") == m.group(1)

    # sentiment == 'value'
    m = re.match(r"^sentiment\s*==\s*['\"]([^'\"]+)['\"]$", cond)
    if m:
        return data.get("sentiment", "") == m.group(1)

    # message_contains('text')
    m = re.match(r"^message_contains\(['\"]([^'\"]+)['\"]\)$", cond)
    if m:
        msg = data.get("message", "").lower()
        return m.group(1).lower() in msg

    # Shopify numeric comparisons: order_value > 100, cart_value > 50, quantity < 5, quantity == 0
    m = re.match(r"^(\w+)\s*(>|<|==|>=|<=)\s*(\d+(?:\.\d+)?)$", cond)
    if m:
        field, op, val_str = m.group(1), m.group(2), m.group(3)
        try:
            actual = float(data.get(field, 0))
            threshold = float(val_str)
            if op == ">":  return actual > threshold
            if op == "<":  return actual < threshold
            if op == "==": return actual == threshold
            if op == ">=": return actual >= threshold
            if op == "<=": return actual <= threshold
        except (TypeError, ValueError):
            pass

    # financial_status == 'paid', fulfillment_status == 'unfulfilled'
    m = re.match(r"^(\w+)\s*==\s*['\"]([^'\"]+)['\"]$", cond)
    if m:
        field, val = m.group(1), m.group(2)
        return str(data.get(field, "")).lower() == val.lower()

    logger.warning(f"[WorkflowEngine] Unknown condition syntax: {cond!r} — treating as True")
    return True


# ── Message interpolation ──────────────────────────────────────────────────────

def _interpolate(text: str, user: dict, customer: dict, event_data: dict) -> str:
    """Replace {placeholder} tokens in message text."""
    replacements = {
        "customer_name":  (customer or {}).get("name", "there"),
        "business_name":  (user or {}).get("business_name", ""),
        "first_name":     ((customer or {}).get("name") or "there").split()[0],
        "phone":          (customer or {}).get("phone", ""),
    }
    for key, value in replacements.items():
        text = text.replace(f"{{{key}}}", str(value))
    return text


# ── Capability executor ────────────────────────────────────────────────────────

async def _execute_capability(
    db,
    step: WorkflowStep,
    user: dict,
    customer: dict,
    from_number: str,
    event_data: dict,
    whatsapp_service,
) -> bool:
    """
    Execute a single capability step.
    Returns True on success, False on skip/failure.
    """
    action = step.action
    params = step.params
    user_id = user["_id"]
    customer_id = (customer or {}).get("_id")

    if action not in CAPABILITIES:
        logger.warning(f"[WorkflowEngine] Unknown capability '{action}' — skipped")
        return False

    try:
        if action == "send_message":
            msg = _interpolate(params.get("message", ""), user, customer, event_data)
            raw_dest = (params.get("destination") or params.get("channel") or "customer_whatsapp")
            dest = str(raw_dest).strip().lower()

            # Push to business owner only (no WhatsApp to customer)
            if dest in ("owner_push", "notify_me", "team_push", "push", "owner_notification"):
                title = _interpolate(
                    params.get("title", "Automation"),
                    user,
                    customer,
                    event_data,
                ) or "Automation"
                body = msg.strip() if msg else "Workflow notification"
                await _push_notify(db, user_id, title, body, {"type": "workflow", "channel": "owner_push"})
                logger.info("[WorkflowEngine] send_message → owner_push")
                return True

            # Default: WhatsApp to the contact
            if msg and from_number:
                customer_name = (customer or {}).get("name", "")
                await whatsapp_service.send_message(
                    user_id=user_id,
                    to_number=from_number,
                    message=msg,
                    customer_name=customer_name,
                    send_context="workflow",
                )
                logger.info(f"[WorkflowEngine] send_message → whatsapp {from_number}")
            elif msg and not from_number:
                logger.warning("[WorkflowEngine] send_message skipped — no phone on contact for WhatsApp")
            return True

        elif action == "tag_contact":
            tag = params.get("tag", "").strip()
            if tag and customer_id:
                await db.customers.update_one(
                    {"_id": customer_id},
                    {"$addToSet": {"tags": tag}},
                )
                logger.info(f"[WorkflowEngine] tag_contact '{tag}' → {customer_id}")
            return True

        elif action == "move_pipeline_stage":
            stage = params.get("stage", "").strip().lower()
            if stage and customer_id:
                await db.customers.update_one(
                    {"_id": customer_id},
                    {"$set": {"pipeline_stage": stage, "pipeline_updated_at": datetime.utcnow()}},
                )
                logger.info(f"[WorkflowEngine] move_pipeline_stage '{stage}' → {customer_id}")
            return True

        elif action == "notify_owner":
            msg = _interpolate(params.get("message", "Workflow alert"), user, customer, event_data)
            title = params.get("title", "Workflow Alert")
            await _push_notify(db, user_id, title, msg, {"type": "workflow"})
            return True

        elif action == "create_followup":
            note = _interpolate(params.get("note", "Follow up"), user, customer, event_data)
            due_hours = int(params.get("due_hours", 24))
            due_at = datetime.utcnow() + timedelta(hours=due_hours)
            await db.followups.insert_one({
                "_id": str(uuid.uuid4()),
                "user_id": user_id,
                "customer_id": customer_id,
                "customer_name": (customer or {}).get("name", ""),
                "customer_phone": from_number,
                "note": note,
                "due_date": due_at,
                "status": "pending",
                "created_by": "workflow",
                "created_at": datetime.utcnow(),
            })
            logger.info(f"[WorkflowEngine] create_followup → customer {customer_id}")
            return True

        elif action == "escalate_to_human":
            reason = _interpolate(params.get("reason", "Workflow escalation"), user, customer, event_data)
            if customer_id:
                await db.customers.update_one(
                    {"_id": customer_id},
                    {"$set": {
                        "needs_human": True,
                        "needs_human_reason": reason,
                        "needs_human_at": datetime.utcnow(),
                    }},
                )
            logger.info(f"[WorkflowEngine] escalate_to_human → {customer_id}")
            return True

        elif action == "assign_owner":
            member_name = params.get("member_name", "").strip()
            if member_name and customer_id:
                member = await db.team_members.find_one(
                    {"user_id": user_id, "name": {"$regex": member_name, "$options": "i"}}
                )
                if member:
                    await db.customers.update_one(
                        {"_id": customer_id},
                        {"$set": {"assigned_to": member["_id"], "assigned_name": member.get("name", "")}},
                    )
                    logger.info(f"[WorkflowEngine] assign_owner '{member_name}' → {customer_id}")
            return True

        elif action in ("wait", "if_no_reply"):
            # Handled by the step scheduler, not here
            return True

        elif action == "shopify_fulfill_order":
            order_id = event_data.get("shopify_order_id")
            if not order_id:
                logger.warning("[WorkflowEngine] shopify_fulfill_order: no order_id in event_data")
                return False
            try:
                from assistant.nango import nango_proxy
                fo_data = await nango_proxy(
                    user_id, "shopify", "GET",
                    f"/admin/api/2024-01/orders/{order_id}/fulfillment_orders.json",
                )
                fo_list = fo_data.get("fulfillment_orders", [])
                open_fos = [fo for fo in fo_list if fo.get("status") == "open"]
                if not open_fos:
                    logger.info(f"[WorkflowEngine] shopify_fulfill_order: no open FOs for order {order_id}")
                    return True
                lifo = [
                    {"fulfillment_order_id": fo["id"], "fulfillment_order_line_items": [
                        {"id": li["id"], "quantity": li["fulfillable_quantity"]}
                        for li in fo.get("line_items", [])
                    ]}
                    for fo in open_fos
                ]
                payload: Dict[str, Any] = {
                    "fulfillment": {
                        "line_items_by_fulfillment_order": lifo,
                        "notify_customer": params.get("notify_customer", True),
                    }
                }
                tracking = params.get("tracking_number", "").strip()
                if tracking:
                    payload["fulfillment"]["tracking_info"] = {
                        "number": tracking,
                        "company": params.get("tracking_company", ""),
                    }
                await nango_proxy(user_id, "shopify", "POST", "/admin/api/2024-01/fulfillments.json", json=payload)
                logger.info(f"[WorkflowEngine] shopify_fulfill_order → order {order_id}")
            except Exception as e:
                logger.error(f"[WorkflowEngine] shopify_fulfill_order error: {e}")
                return False
            return True

        elif action == "shopify_create_discount":
            try:
                from assistant.nango import nango_proxy
                import random, string as string_mod
                from datetime import timezone as _tz
                discount_type = params.get("type", "percentage")
                value         = float(params.get("value", 10))
                expiry_days   = int(params.get("expiry_days", 7))
                usage_limit   = int(params.get("usage_limit", 1))
                code = "".join(random.choices(string_mod.ascii_uppercase + string_mod.digits, k=8))
                ends_at = (datetime.utcnow().replace(tzinfo=_tz.utc) + timedelta(days=expiry_days)).isoformat()
                pr_payload: Dict[str, Any] = {
                    "price_rule": {
                        "title": code, "target_type": "line_item",
                        "target_selection": "all", "allocation_method": "across",
                        "value_type": "percentage" if discount_type == "percentage" else "fixed_amount",
                        "value": f"-{value}",
                        "customer_selection": "all",
                        "starts_at": datetime.utcnow().replace(tzinfo=_tz.utc).isoformat(),
                        "ends_at": ends_at, "usage_limit": usage_limit,
                    }
                }
                pr = await nango_proxy(user_id, "shopify", "POST", "/admin/api/2024-01/price_rules.json", json=pr_payload)
                pr_id = pr.get("price_rule", {}).get("id")
                if pr_id:
                    await nango_proxy(
                        user_id, "shopify", "POST",
                        f"/admin/api/2024-01/price_rules/{pr_id}/discount_codes.json",
                        json={"discount_code": {"code": code}},
                    )
                # Store generated code in event_data so subsequent steps can use {discount_code}
                event_data["discount_code"] = code
                event_data["discount_expires"] = ends_at[:10]
                logger.info(f"[WorkflowEngine] shopify_create_discount → code {code}")
            except Exception as e:
                logger.error(f"[WorkflowEngine] shopify_create_discount error: {e}")
                return False
            return True

        elif action == "shopify_send_recovery":
            # Extended version of send_message that knows about cart placeholders
            msg = params.get("message", "")
            discount_value = float(params.get("discount_value", 0))

            # Auto-create discount if requested and not already in event_data
            if discount_value > 0 and not event_data.get("discount_code"):
                try:
                    from assistant.nango import nango_proxy
                    import random, string as string_mod
                    from datetime import timezone as _tz
                    code = "".join(random.choices(string_mod.ascii_uppercase + string_mod.digits, k=8))
                    ends_at = (datetime.utcnow().replace(tzinfo=_tz.utc) + timedelta(days=7)).isoformat()
                    pr = await nango_proxy(user_id, "shopify", "POST", "/admin/api/2024-01/price_rules.json", json={
                        "price_rule": {
                            "title": code, "target_type": "line_item",
                            "target_selection": "all", "allocation_method": "across",
                            "value_type": "percentage", "value": f"-{discount_value}",
                            "customer_selection": "all",
                            "starts_at": datetime.utcnow().replace(tzinfo=_tz.utc).isoformat(),
                            "ends_at": ends_at, "usage_limit": 1,
                        }
                    })
                    pr_id = pr.get("price_rule", {}).get("id")
                    if pr_id:
                        await nango_proxy(user_id, "shopify", "POST",
                            f"/admin/api/2024-01/price_rules/{pr_id}/discount_codes.json",
                            json={"discount_code": {"code": code}})
                    event_data["discount_code"] = code
                except Exception as e:
                    logger.warning(f"[WorkflowEngine] shopify_send_recovery discount creation failed: {e}")

            # Interpolate Shopify-specific tokens
            cart_customer = customer or {}
            msg = _interpolate(msg, user, cart_customer, event_data)
            msg = msg.replace("{recovery_url}", event_data.get("recovery_url", ""))
            msg = msg.replace("{cart_value}",   str(event_data.get("cart_value", "")))
            msg = msg.replace("{discount_code}", event_data.get("discount_code", ""))

            phone = event_data.get("customer_phone") or from_number
            if msg and phone:
                await whatsapp_service.send_message(
                    user_id=user_id, to_number=phone, message=msg,
                    customer_name=cart_customer.get("name", ""),
                    send_context="shopify_recovery",
                )
                logger.info(f"[WorkflowEngine] shopify_send_recovery → {phone}")
            return True

        else:
            logger.warning(f"[WorkflowEngine] Unhandled capability '{action}'")
            return False

    except Exception as exc:
        logger.error(f"[WorkflowEngine] Error executing '{action}': {exc}", exc_info=True)
        return False


async def _push_notify(db, user_id, title: str, body: str, data: dict) -> None:
    """Send Expo push notification to the business owner."""
    import httpx
    try:
        user = await db.users.find_one({"_id": user_id})
        tokens = (user or {}).get("push_tokens", []) or []
        messages = [
            {"to": t, "title": title, "body": body, "data": data, "sound": "default"}
            for t in tokens
            if t and (t.startswith("ExponentPushToken") or t.startswith("ExpoPushToken"))
        ]
        if not messages:
            return
        async with httpx.AsyncClient(timeout=10) as http:
            await http.post(
                "https://exp.host/--/api/v2/push/send",
                json=messages,
                headers={"Content-Type": "application/json"},
            )
    except Exception as exc:
        logger.warning(f"[WorkflowEngine] Push notify failed: {exc}")


# ── Check if customer has replied since a timestamp ───────────────────────────

async def _customer_replied_since(db, user_id, customer_id, since: datetime) -> bool:
    """Return True if the customer sent any message after `since`."""
    msg = await db.messages.find_one({
        "user_id": user_id,
        "customer_id": customer_id,
        "role": "customer",
        "created_at": {"$gt": since},
    })
    return msg is not None


# ── Run a sequence of steps (immediate + deferred) ────────────────────────────

async def _run_steps(
    db,
    steps: List[WorkflowStep],
    workflow_id: str,
    run_id: str,
    user: dict,
    customer: dict,
    from_number: str,
    event_data: dict,
    whatsapp_service,
    started_at: Optional[datetime] = None,
) -> None:
    """
    Execute steps in sequence.
    Steps with delay_minutes > 0 are stored as pending and handled by deferred_runner().
    """
    if started_at is None:
        started_at = datetime.utcnow()

    user_id = user["_id"]
    customer_id = (customer or {}).get("_id")

    accumulated_delay = 0  # total minutes of delay so far in this chain

    for i, step in enumerate(steps):
        accumulated_delay += step.delay_minutes

        if accumulated_delay > 0:
            # Store this step + all remaining steps as a single pending task
            execute_at = started_at + timedelta(minutes=accumulated_delay)
            pending = {
                "_id": str(uuid.uuid4()),
                "workflow_id": workflow_id,
                "workflow_run_id": run_id,
                "user_id": user_id,
                "customer_id": customer_id,
                "from_number": from_number,
                "step": step.model_dump(),
                "remaining_steps": [s.model_dump() for s in steps[i + 1:]],
                "execute_at": execute_at,
                "status": "pending",
                "created_at": datetime.utcnow(),
                "event_data": event_data,
            }
            await db.workflow_pending_steps.insert_one(pending)
            logger.info(
                f"[WorkflowEngine] Step '{step.action}' deferred "
                f"{accumulated_delay}min → {execute_at.isoformat()}"
            )
            return  # Remaining steps will be handled by deferred_runner

        # Immediate execution
        if step.action == "if_no_reply":
            # Check if customer replied since workflow started
            replied = await _customer_replied_since(db, user_id, customer_id, started_at)
            if replied:
                logger.info(f"[WorkflowEngine] if_no_reply: customer DID reply — stopping workflow")
                await _mark_run_done(db, run_id, "stopped_by_reply")
                return
            # else continue to next step

        else:
            await _execute_capability(
                db=db, step=step, user=user, customer=customer,
                from_number=from_number, event_data=event_data,
                whatsapp_service=whatsapp_service,
            )

    await _mark_run_done(db, run_id, "completed")


async def _mark_run_done(db, run_id: str, final_status: str) -> None:
    await db.workflow_runs.update_one(
        {"_id": run_id},
        {"$set": {"status": final_status, "finished_at": datetime.utcnow()}},
    )


# ── Public: fire a trigger event ──────────────────────────────────────────────

async def fire_trigger(db, event: WorkflowEvent, whatsapp_service) -> None:
    """
    Check all enabled workflows for this tenant and run any that match the event.
    Called from the webhook handler (as a background task).
    """
    # Load all enabled workflows for this tenant
    workflows = await db.workflows.find({
        "user_id": event.user_id,
        "enabled": True,
        "trigger.type": event.trigger_type,
    }).to_list(50)

    if not workflows:
        return

    # Load user + customer once
    user = await db.users.find_one({"_id": event.user_id})
    customer = await db.customers.find_one({"_id": event.customer_id}) if event.customer_id else None

    if not user:
        return

    for wf in workflows:
        trigger = wf.get("trigger", {})
        condition = trigger.get("condition")

        if not _evaluate_condition(condition, event):
            continue

        run_id = str(uuid.uuid4())
        steps = [WorkflowStep(**s) for s in (wf.get("steps") or [])]

        # Create run record
        await db.workflow_runs.insert_one({
            "_id": run_id,
            "workflow_id": str(wf["_id"]),
            "workflow_name": wf.get("name", ""),
            "user_id": event.user_id,
            "customer_id": event.customer_id,
            "from_number": event.from_number,
            "trigger_type": event.trigger_type,
            "status": "running",
            "started_at": datetime.utcnow(),
            "event_data": event.data,
        })

        # Increment run count on the workflow
        await db.workflows.update_one(
            {"_id": wf["_id"]},
            {"$inc": {"run_count": 1}, "$set": {"last_run_at": datetime.utcnow()}},
        )

        logger.info(
            f"[WorkflowEngine] Firing workflow '{wf.get('name')}' "
            f"(run {run_id}) for customer {event.customer_id}"
        )

        try:
            await _run_steps(
                db=db, steps=steps,
                workflow_id=str(wf["_id"]), run_id=run_id,
                user=user, customer=customer,
                from_number=event.from_number,
                event_data=event.data,
                whatsapp_service=whatsapp_service,
            )
        except Exception as exc:
            logger.error(f"[WorkflowEngine] Error running workflow '{wf.get('name')}': {exc}", exc_info=True)
            await db.workflow_runs.update_one(
                {"_id": run_id},
                {"$set": {"status": "failed", "error": str(exc), "finished_at": datetime.utcnow()}},
            )


# ── Background: process deferred steps ────────────────────────────────────────

async def process_pending_steps(db, whatsapp_service) -> None:
    """
    Pick up and execute all pending steps whose execute_at has passed.
    Called every 60s by the background runner in server.py.
    """
    now = datetime.utcnow()
    pending = await db.workflow_pending_steps.find({
        "status": "pending",
        "execute_at": {"$lte": now},
    }).to_list(100)

    for doc in pending:
        # Mark as processing to avoid double-run
        result = await db.workflow_pending_steps.update_one(
            {"_id": doc["_id"], "status": "pending"},
            {"$set": {"status": "processing"}},
        )
        if result.modified_count == 0:
            continue  # Already grabbed by another instance

        try:
            user = await db.users.find_one({"_id": doc["user_id"]})
            customer = await db.customers.find_one({"_id": doc["customer_id"]}) if doc.get("customer_id") else None

            if not user:
                await db.workflow_pending_steps.update_one(
                    {"_id": doc["_id"]}, {"$set": {"status": "failed", "error": "user_not_found"}}
                )
                continue

            step = WorkflowStep(**doc["step"])
            remaining = [WorkflowStep(**s) for s in (doc.get("remaining_steps") or [])]
            event_data = doc.get("event_data", {})

            # Handle if_no_reply check
            if step.action == "if_no_reply":
                run = await db.workflow_runs.find_one({"_id": doc["workflow_run_id"]})
                started_at = (run or {}).get("started_at", doc["created_at"])
                replied = await _customer_replied_since(db, doc["user_id"], doc["customer_id"], started_at)
                if replied:
                    logger.info(f"[WorkflowEngine] Deferred if_no_reply: customer DID reply — stopping")
                    await db.workflow_pending_steps.update_one(
                        {"_id": doc["_id"]}, {"$set": {"status": "skipped"}}
                    )
                    await _mark_run_done(db, doc["workflow_run_id"], "stopped_by_reply")
                    continue
            else:
                await _execute_capability(
                    db=db, step=step, user=user, customer=customer,
                    from_number=doc.get("from_number", ""),
                    event_data=event_data,
                    whatsapp_service=whatsapp_service,
                )

            await db.workflow_pending_steps.update_one(
                {"_id": doc["_id"]}, {"$set": {"status": "done"}}
            )

            # Continue with remaining steps
            if remaining:
                await _run_steps(
                    db=db, steps=remaining,
                    workflow_id=doc["workflow_id"], run_id=doc["workflow_run_id"],
                    user=user, customer=customer,
                    from_number=doc.get("from_number", ""),
                    event_data=event_data,
                    whatsapp_service=whatsapp_service,
                    started_at=doc.get("created_at"),
                )
            else:
                await _mark_run_done(db, doc["workflow_run_id"], "completed")

        except Exception as exc:
            logger.error(f"[WorkflowEngine] Deferred step failed: {exc}", exc_info=True)
            await db.workflow_pending_steps.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": "failed", "error": str(exc)}},
            )


async def deferred_runner(db, get_whatsapp_service_fn) -> None:
    """
    Infinite async loop that processes deferred steps every 60 seconds.
    Started once on app startup.
    """
    logger.info("[WorkflowEngine] Deferred step runner started")
    while True:
        try:
            ws = get_whatsapp_service_fn(db)
            await process_pending_steps(db, ws)
        except Exception as exc:
            logger.error(f"[WorkflowEngine] deferred_runner error: {exc}", exc_info=True)
        await asyncio.sleep(60)


# ═════════════════════════════════════════════════════════════════════════════
# SHOPIFY AUTOPILOT POLLER
# Polls every 5 minutes for all users with Shopify connected + workflows enabled.
# Fires: shopify_order_created, shopify_abandoned_cart, shopify_low_stock, shopify_refund_created
# ═════════════════════════════════════════════════════════════════════════════

async def _get_users_with_shopify_workflows(db) -> list:
    """Return user docs that have at least one enabled Shopify-trigger workflow."""
    trigger_types = [
        "shopify_order_created", "shopify_order_fulfilled",
        "shopify_abandoned_cart", "shopify_low_stock", "shopify_refund_created",
    ]
    pipeline = [
        {"$match": {"enabled": True, "trigger.type": {"$in": trigger_types}}},
        {"$group": {"_id": "$user_id"}},
    ]
    docs = await db.workflows.aggregate(pipeline).to_list(500)
    user_ids = [d["_id"] for d in docs]
    if not user_ids:
        return []
    users = await db.users.find({"_id": {"$in": user_ids}}).to_list(500)
    return users


async def _poll_shopify_for_user(db, user: dict, whatsapp_service) -> None:
    """Run all Shopify autopilot checks for a single user (tenant)."""
    from assistant.nango import nango_proxy
    user_id = user["_id"]

    # Load or create poll state
    state = await db.shopify_poll_state.find_one({"user_id": user_id}) or {}
    now = datetime.utcnow()

    # ── 1. New orders ──────────────────────────────────────────────────────────
    last_order_check = state.get("last_order_check") or (now - timedelta(minutes=10))
    try:
        data = await nango_proxy(
            user_id, "shopify", "GET",
            "/admin/api/2024-01/orders.json",
            params={"status": "open", "limit": 50,
                    "created_at_min": last_order_check.isoformat() + "Z"},
        )
        for order in data.get("orders", []):
            event = WorkflowEvent(
                trigger_type="shopify_order_created",
                user_id=user_id,
                customer_id=None,
                from_number="",
                data={
                    "shopify_order_id":  str(order.get("id", "")),
                    "order_number":      order.get("order_number"),
                    "order_value":       float(order.get("total_price", 0)),
                    "financial_status":  order.get("financial_status", ""),
                    "fulfillment_status": order.get("fulfillment_status") or "unfulfilled",
                    "customer_name":     (
                        (order.get("customer") or {}).get("first_name", "") + " " +
                        (order.get("customer") or {}).get("last_name", "")
                    ).strip() or "Customer",
                    "customer_email":    order.get("email", ""),
                },
            )
            await fire_trigger(db, event, whatsapp_service)
        logger.info(f"[ShopifyAutopilot] {user_id}: checked new orders ({len(data.get('orders', []))} found)")
    except Exception as e:
        logger.warning(f"[ShopifyAutopilot] {user_id}: order poll error: {e}")

    # ── 2. Refunds ──────────────────────────────────────────────────────────────
    last_refund_check = state.get("last_refund_check") or (now - timedelta(minutes=10))
    try:
        r_data = await nango_proxy(
            user_id, "shopify", "GET",
            "/admin/api/2024-01/orders.json",
            params={"status": "any", "financial_status": "refunded", "limit": 25,
                    "updated_at_min": last_refund_check.isoformat() + "Z"},
        )
        for order in r_data.get("orders", []):
            event = WorkflowEvent(
                trigger_type="shopify_refund_created",
                user_id=user_id,
                customer_id=None,
                from_number="",
                data={
                    "shopify_order_id": str(order.get("id", "")),
                    "order_number":     order.get("order_number"),
                    "order_value":      float(order.get("total_price", 0)),
                },
            )
            await fire_trigger(db, event, whatsapp_service)
    except Exception as e:
        logger.warning(f"[ShopifyAutopilot] {user_id}: refund poll error: {e}")

    # ── 3. Abandoned carts ─────────────────────────────────────────────────────
    last_cart_check = state.get("last_cart_check") or (now - timedelta(hours=2))
    try:
        c_data = await nango_proxy(
            user_id, "shopify", "GET",
            "/admin/api/2024-01/checkouts.json",
            params={"limit": 50, "created_at_min": last_cart_check.isoformat() + "Z"},
        )
        cutoff = now - timedelta(hours=1)  # Only carts at least 1h old
        for cart in c_data.get("checkouts", []):
            updated_raw = cart.get("updated_at", "")
            try:
                from datetime import timezone as _tz
                ts = datetime.fromisoformat(updated_raw.replace("Z", "+00:00")).replace(tzinfo=None)
                if ts > cutoff:
                    continue  # Still fresh — might convert
            except Exception:
                pass
            event = WorkflowEvent(
                trigger_type="shopify_abandoned_cart",
                user_id=user_id,
                customer_id=None,
                from_number="",
                data={
                    "cart_token":      cart.get("token", ""),
                    "customer_name":   (
                        (cart.get("billing_address") or {}).get("first_name", "") + " " +
                        (cart.get("billing_address") or {}).get("last_name", "")
                    ).strip() or cart.get("email", "Guest"),
                    "customer_email":  cart.get("email", ""),
                    "customer_phone":  (cart.get("billing_address") or {}).get("phone", ""),
                    "cart_value":      float(cart.get("total_price", 0)),
                    "recovery_url":    cart.get("abandoned_checkout_url", ""),
                    "item_count":      len(cart.get("line_items", [])),
                },
            )
            await fire_trigger(db, event, whatsapp_service)
        logger.info(f"[ShopifyAutopilot] {user_id}: checked abandoned carts ({len(c_data.get('checkouts', []))} found)")
    except Exception as e:
        logger.warning(f"[ShopifyAutopilot] {user_id}: cart poll error: {e}")

    # ── 4. Low stock ───────────────────────────────────────────────────────────
    # Only check stock every 15 minutes to avoid excessive API calls
    last_stock_check = state.get("last_stock_check")
    if not last_stock_check or (now - last_stock_check).total_seconds() > 900:
        try:
            p_data = await nango_proxy(
                user_id, "shopify", "GET",
                "/admin/api/2024-01/products.json",
                params={"limit": 250, "status": "active"},
            )
            threshold = 5  # Items with stock below this fire low_stock
            for product in p_data.get("products", []):
                for variant in product.get("variants", []):
                    qty = int(variant.get("inventory_quantity", 999))
                    if qty <= threshold:
                        event = WorkflowEvent(
                            trigger_type="shopify_low_stock",
                            user_id=user_id,
                            customer_id=None,
                            from_number="",
                            data={
                                "product_title":    product.get("title", ""),
                                "variant_title":    variant.get("title", ""),
                                "inventory_item_id": str(variant.get("inventory_item_id", "")),
                                "quantity":          qty,
                            },
                        )
                        await fire_trigger(db, event, whatsapp_service)
        except Exception as e:
            logger.warning(f"[ShopifyAutopilot] {user_id}: stock poll error: {e}")

    # ── Save poll state ────────────────────────────────────────────────────────
    await db.shopify_poll_state.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id":          user_id,
            "last_order_check": now,
            "last_refund_check": now,
            "last_cart_check":  now,
            "last_stock_check": now,
            "updated_at":       now,
        }},
        upsert=True,
    )


async def shopify_autopilot_runner(db, get_whatsapp_service_fn) -> None:
    """
    Infinite async loop that polls Shopify every 5 minutes for all users
    who have Shopify autopilot workflows enabled.
    Started once on app startup alongside deferred_runner.
    """
    logger.info("[ShopifyAutopilot] Autopilot runner started")
    while True:
        try:
            ws = get_whatsapp_service_fn(db)
            users = await _get_users_with_shopify_workflows(db)
            for user in users:
                try:
                    await _poll_shopify_for_user(db, user, ws)
                except Exception as exc:
                    logger.error(f"[ShopifyAutopilot] Error polling user {user.get('_id')}: {exc}", exc_info=True)
        except Exception as exc:
            logger.error(f"[ShopifyAutopilot] Runner error: {exc}", exc_info=True)
        await asyncio.sleep(300)  # Poll every 5 minutes
