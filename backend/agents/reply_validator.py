"""
ReplyValidator — Fast rules-only quality gate on every outgoing AI reply.

No LLM call — uses deterministic checks only for speed and consistency:
  1. Empty reply check
  2. ChatAgent money promise patterns
  3. Too-short reply for non-chat intents
  4. Too-long reply (WhatsApp readability)
  5. Dangerous commitment patterns (any agent)

Returns: APPROVE | REJECT(reason) | ESCALATE(reason)
"""
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

RESULT_APPROVE = "APPROVE"
RESULT_REJECT = "REJECT"
RESULT_ESCALATE = "ESCALATE"

# Hard rules that auto-escalate — dangerous commitments
MONEY_PROMISE_PATTERNS = [
    r'\b(i will|we will|i\'ll|we\'ll)\s+(give|offer|send|pay|refund|deliver)\b',
    r'\bfree\s+of\s+charge\b',
    r'\bno\s+charge\b',
    r'\bpromise\b',
    r'\bguarantee\s+(you|delivery|arrival)\b',
    r'\bby\s+(tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
]

# Patterns that indicate the AI is hallucinating an identity
IDENTITY_HALLUCINATION_PATTERNS = [
    r'\b(i am|i\'m|my name is)\s+(an?\s+)?(ai|bot|assistant|language model|chatbot|virtual)\b',
    r'\bas an ai\b',
]

# Chat intents where short replies are fine
SHORT_OK_INTENTS = {"GREETING", "SMALL_TALK", "GENERAL_CHAT", "PERSONAL_CHAT"}

# 12.4: Revised length thresholds
MIN_REPLY_CHARS = 20          # minimum characters for non-chat intents
MAX_REPLY_CHARS = 600         # ~150 words — WhatsApp readability limit
MAX_REPLY_CHARS_COMPLAINT = 800  # complaint/booking can be a bit longer

# 12.6: Booking hallucination patterns — inventing availability or prices
BOOKING_HALLUCINATION_PATTERNS = [
    r'\bavailable\s+(on|at|for)\s+\w+\s+(at\s+)?\d+',   # "available on Monday at 3"
    r'\b(slot|appointment|booking)\s+(is\s+)?available\b',
    r'\bwe have\s+(a\s+)?(slot|opening|appointment|space)\b',
    r'\b(come in|come\s+at|be here)\s+(on\s+)?\w+\s+at\s+\d+',
    r'\bprice\s+(is|for)\s+[\$\£\€\₦\₹\¥]?\s*\d+',     # inventing service prices
    r'\bcosts?\s+[\$\£\€\₦\₹\¥]?\s*\d+',
]

# 12.7: Sales hallucination patterns — refusing to sell or claiming lack of access
SALES_HALLUCINATION_PATTERNS = [
    r'\b(i don\'t have access|i cannot access|i don\'t know the price)\b',
    r'\b(let me check with|i will ask the owner|i\'ll ask the owner)\b',
    r'\b(i don\'t have a catalog|no catalog available)\b',
    r'\b(i\'m just an ai|i am an ai)\b',
]

# 12.8: Fake confirmation patterns — AI pretends to book/order/schedule without DB writes
# These MUST be broad enough to catch every creative variation the LLM generates.
FAKE_CONFIRMATION_PATTERNS = [
    # Direct confirmation language
    r'\b(is\s+now\s+booked|has\s+been\s+booked|is\s+confirmed|has\s+been\s+confirmed)\b',
    r'\b(booked\s+you\s+(for|in|at)|booking\s+you\s+(for|in|at))\b',
    r'\b(you\'?re\s+(all\s+)?booked|all\s+booked|you\s+are\s+booked)\b',
    r'\b(booked\s+for\s+(the|a|your|haircut|massage|service|appointment))\b',
    r'\b(booked\s+for\s+[\w\s]+at\s+\$[\d,]+)\b',  # "Booked for haircut at $500"
    r'(✅\s*booked|booked\s*✅|✅\s*confirmed|confirmed\s*✅)',
    # "See you" language
    r'\b(see\s+you\s+(then|at|on|there|soon|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b',
    r'\b(see\s+you\s+in\s+a\s+bit)\b',
    # Appointment/booking confirmations
    r'\b(appointment\s+(is|has\s+been)\s+(set|scheduled|confirmed|booked))\b',
    r'\b(your\s+(order|booking|appointment|reservation)\s+(is|has\s+been)\s+(placed|confirmed|set|ready|booked))\b',
    r'\b(reservation\s+(is|has\s+been)\s+(made|confirmed|booked))\b',
    # Inventing opening hours / availability
    r'\b(we(\'re|\s+are)\s+open\s+(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b',
    r'\b(our\s+hours\s+are|we\s+open\s+at|hours\s+of\s+operation)\b',
    r'\b(open\s+(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday).*(am|pm))\b',
    r'\b(we\'?re\s+closed\s+(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b',
    r'\b(\d{1,2}\s*am\s*[\-–to]+\s*\d{1,2}\s*pm)\b',  # "8am-5pm", "8am–5pm", "8am to 5pm"
    # Specific time confirmations without DB context
    r'\b(you\'?re\s+set\s+for|you\'?re\s+all\s+set)\b',
    r'\b((monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+works)\b',
    r'\b(\d{1,2}(:\d{2})?\s*(am|pm)?\s+(on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+works)\b',
    r'\b(we\'?ll\s+see\s+you\s+(at|on))\b',
    r'\b(confirmed\s+for\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today))\b',
    r'\b(slot\s+(is|has been)\s+(reserved|booked|confirmed))\b',
]


async def validate_reply(
    reply_text: str,
    original_message: str,
    intent: str,
    sentiment: str,
    language: str,
    agent_name: str,
    business_knowledge: str,
    history: list,
) -> Dict[str, Any]:
    """
    Fast rules-only validation — no LLM call.
    Checks for empty, too short, too long, money promises, and identity hallucinations.
    """
    # Rule 1: Empty reply
    if not reply_text or not reply_text.strip():
        return {
            "result": RESULT_ESCALATE,
            "reason": "Empty reply generated",
            "suggestion": None,
        }

    reply_lower = reply_text.lower()
    word_count = len(reply_text.split())
    char_count = len(reply_text.strip())

    # Rule 2: ChatAgent must never make money promises
    if agent_name == "chat":
        for pattern in MONEY_PROMISE_PATTERNS:
            if re.search(pattern, reply_lower):
                return {
                    "result": RESULT_ESCALATE,
                    "reason": f"ChatAgent reply contains money/delivery promise",
                    "suggestion": None,
                }

    # Rule 3: Any agent — dangerous commitment patterns
    if agent_name != "chat":
        # Only escalate on very specific dangerous patterns
        dangerous = [
            r'\b(we guarantee|i guarantee)\b',
            r'\b(legal|lawyer|sue|court)\b.*\b(will|promise)\b',
        ]
        for pattern in dangerous:
            if re.search(pattern, reply_lower):
                return {
                    "result": RESULT_ESCALATE,
                    "reason": "Reply contains dangerous commitment language",
                    "suggestion": None,
                }

    # Rule 4: Identity hallucination — AI revealing itself as a bot
    for pattern in IDENTITY_HALLUCINATION_PATTERNS:
        if re.search(pattern, reply_lower):
            return {
                "result": RESULT_REJECT,
                "reason": "Reply reveals AI identity — should sound like the business owner",
                "suggestion": "Reply as the business owner, not as an AI assistant.",
            }

    # Rule 5: Too short for non-chat intents
    if char_count < MIN_REPLY_CHARS and intent not in SHORT_OK_INTENTS:
        return {
            "result": RESULT_REJECT,
            "reason": f"Reply too short ({char_count} chars) for intent {intent}",
            "suggestion": "Provide a complete answer to the customer's question.",
        }

    # Rule 6: Too long — WhatsApp messages should be concise
    max_chars = MAX_REPLY_CHARS_COMPLAINT if agent_name in ("complaint", "booking") else MAX_REPLY_CHARS
    if char_count > max_chars:
        return {
            "result": RESULT_REJECT,
            "reason": f"Reply too long ({char_count} chars) — will bore the customer on WhatsApp",
            "suggestion": "Keep the reply under 600 characters. Be direct and WhatsApp-natural.",
        }

    # Rule 7: Booking agent must not invent availability slots or prices
    if agent_name == "booking":
        for pattern in BOOKING_HALLUCINATION_PATTERNS:
            if re.search(pattern, reply_lower):
                return {
                    "result": RESULT_REJECT,
                    "reason": "Booking reply appears to invent availability or prices not from business data",
                    "suggestion": "Do NOT invent specific time slots or prices. Ask the customer what date works and let the owner confirm.",
                }

    # Rule 8: Sales agent must not hallucinate lack of knowledge or access
    if agent_name == "sales":
        for pattern in SALES_HALLUCINATION_PATTERNS:
            if re.search(pattern, reply_lower):
                return {
                    "result": RESULT_REJECT,
                    "reason": "Sales agent hallucinated lack of knowledge or access to catalog",
                    "suggestion": "You are the business owner. Use the provided business knowledge and product list to answer directly. Never say you don't have access or need to check.",
                }

    # Rule 9: Any agent must NOT fake-confirm bookings/orders/appointments
    # This is the most critical guard — prevents the AI from telling a customer
    # 'Your 9:30 is now booked' when nothing was actually saved to the database.
    for pattern in FAKE_CONFIRMATION_PATTERNS:
        if re.search(pattern, reply_lower):
            return {
                "result": RESULT_REJECT,
                "reason": f"Reply contains fake booking/order confirmation — nothing was saved to the database",
                "suggestion": "NEVER confirm a booking, appointment, or order. Instead, collect the customer's preferred date/time and tell them you will confirm shortly. Do NOT say 'booked', 'confirmed', or 'see you then'.",
            }

    # All rules passed
    logger.info(f"[ReplyValidator] APPROVE agent={agent_name} intent={intent} words={word_count}")
    return {
        "result": RESULT_APPROVE,
        "reason": "Passed all quality checks",
        "suggestion": None,
    }


# ── Post-Action DB State Validator ────────────────────────────────────────────
# This checks whether claims in the AI's reply actually match database state.
# If the AI says "your booking is confirmed" but no booking exists, it gets rejected.

# Patterns that claim a concrete action was taken
_CLAIMS_BOOKING_DONE = [
    r'\b(booked|reserved|scheduled|appointment\s+set)\b',
    r'\b(booking\s+(ref|reference|number|confirmed))\b',
    r'\bBK-\d+\b',  # booking reference number format
]
_CLAIMS_ORDER_DONE = [
    r'\b(order\s+(placed|confirmed|received|number))\b',
    r'\b(ORD-\d+)\b',  # order reference format
    r'\byour\s+order\s+has\s+been\b',
]
_CLAIMS_CANCEL_DONE = [
    r'\b(cancelled|canceled|cancellation\s+confirmed)\b',
]


async def validate_db_state(
    reply_text: str,
    agent_name: str,
    intent: str,
    customer_id: Optional[str],
    user_id: str,
    db,
) -> Dict[str, Any]:
    """
    Post-action validator: checks if claims in the AI reply match actual DB state.
    This runs AFTER the text validator passes, as a second gate.
    
    Only checks if the reply text contains action-claiming language.
    If no claims are detected, auto-approves (fast path).
    """
    if not reply_text or not customer_id or db is None:
        return {"result": RESULT_APPROVE, "reason": "No DB check needed", "suggestion": None}

    reply_lower = reply_text.lower()

    # ── Check booking claims ──────────────────────────────────────────────
    claims_booking = any(re.search(p, reply_lower) for p in _CLAIMS_BOOKING_DONE)
    if claims_booking and agent_name in ("booking", "chat", "sales"):
        try:
            # Check if a recent booking exists for this customer (created in last 2 minutes)
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
            recent_booking = await db.bookings.find_one({
                "user_id": user_id,
                "customer_id": str(customer_id),
                "created_at": {"$gte": cutoff},
            })
            if not recent_booking:
                logger.warning(f"[DBValidator] Reply claims booking but no recent booking found in DB")
                return {
                    "result": RESULT_REJECT,
                    "reason": "Reply claims a booking was made but no booking exists in the database",
                    "suggestion": (
                        "Do NOT confirm a booking. No booking has been created yet. "
                        "Instead, ask the customer for their preferred date and time so you can book it for them."
                    ),
                }
        except Exception as e:
            logger.error(f"[DBValidator] Booking check error: {e}")

    # ── Check order claims ────────────────────────────────────────────────
    claims_order = any(re.search(p, reply_lower) for p in _CLAIMS_ORDER_DONE)
    if claims_order and agent_name in ("order", "chat", "sales"):
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
            recent_order = await db.orders.find_one({
                "user_id": user_id,
                "customer_id": str(customer_id),
                "created_at": {"$gte": cutoff},
            })
            if not recent_order:
                logger.warning(f"[DBValidator] Reply claims order but no recent order found in DB")
                return {
                    "result": RESULT_REJECT,
                    "reason": "Reply claims an order was placed but no order exists in the database",
                    "suggestion": (
                        "Do NOT confirm an order. No order has been placed yet. "
                        "Instead, ask the customer to confirm which product and quantity they want."
                    ),
                }
        except Exception as e:
            logger.error(f"[DBValidator] Order check error: {e}")

    # ── Check cancellation claims ─────────────────────────────────────────
    claims_cancel = any(re.search(p, reply_lower) for p in _CLAIMS_CANCEL_DONE)
    if claims_cancel and agent_name in ("booking", "order", "chat"):
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
            recent_cancel = await db.bookings.find_one({
                "user_id": user_id,
                "customer_id": str(customer_id),
                "status": "cancelled",
                "cancelled_at": {"$gte": cutoff},
            })
            if not recent_cancel:
                # Also check orders
                recent_cancel = await db.orders.find_one({
                    "user_id": user_id,
                    "customer_id": str(customer_id),
                    "status": "cancelled",
                    "cancelled_at": {"$gte": cutoff},
                })
            if not recent_cancel:
                logger.warning(f"[DBValidator] Reply claims cancellation but nothing was cancelled in DB")
                return {
                    "result": RESULT_REJECT,
                    "reason": "Reply claims a cancellation but nothing was actually cancelled in the database",
                    "suggestion": (
                        "Do NOT confirm a cancellation. Nothing has been cancelled yet. "
                        "Ask the customer which booking or order they want to cancel."
                    ),
                }
        except Exception as e:
            logger.error(f"[DBValidator] Cancellation check error: {e}")

    # All DB checks passed (or no claims detected)
    return {"result": RESULT_APPROVE, "reason": "DB state consistent", "suggestion": None}

