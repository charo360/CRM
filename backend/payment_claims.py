"""A payment is not received because the customer says it was.

A customer on a manual payment method replied "Samuel Mweni, 3000", and the AI
answered "Payment of USD 3,000 received. Your order will be ready for pickup
tomorrow at 4pm." Nobody had seen the money. The order itself was handled
correctly -- pending verification, owner alerted -- but the customer was told
the opposite, in writing, which is how a shop ends up handing over goods it
was never paid for.

The prompts were part of it: five of them told the model to say "Payment
received". They are corrected, but a prompt is only a request, and this reply
showed the model embellishing past it. So the reply itself is checked before
it is sent. If it asserts that a payment was received or confirmed, and that
payment has not been verified -- marked paid by the owner, or paid online --
the reply is replaced with one that says what is actually true: it has gone to
the owner to check.
"""
import re
from typing import Any, Iterable, Optional

# Payments that really have been settled. Anything else -- unpaid, pending,
# pending_verification, nothing at all -- has not been seen by anyone.
VERIFIED_STATUSES = {"paid", "completed"}

# Wording that makes a statement conditional, future or negative rather than
# a claim. "Once your payment is received we'll ship" and "your payment hasn't
# been confirmed yet" are both true things to say.
_CONDITIONAL = re.compile(
    r"(n't|\b(once|when|after|as soon as|until|if|will|shall|to be|awaiting|pending|"
    r"not|no|never|yet|ikishafika|yakifika|yakishathibitishwa|bado|haija\w*|hayaja\w*)\b)",
    re.IGNORECASE,
)

# The claim itself, English and Swahili. "Complete" is left out on purpose:
# "send the payment to complete your order" is a request, not a receipt.
_ASSERTS_RECEIPT = re.compile(
    r"(\b(payment|malipo|pesa|money)\b[^.!?\n]{0,40}"
    r"\b(received|confirmed|verified|successful|"
    r"imepokelewa|yamepokelewa|imethibitishwa|yamethibitishwa|imefika|yamefika)\b)"
    r"|(\b(we'?ve|we have|i'?ve|i have)\s+(received|got|confirmed)\b[^.!?\n]{0,20}"
    r"\b(payment|money|malipo|pesa)\b)"
    r"|(\b(tumepokea|nimepokea)\b[^.!?\n]{0,20}\b(malipo|pesa)\b)",
    re.IGNORECASE,
)

_SWAHILI = re.compile(
    r"\b(nimetuma|nimelipa|nimepay|nimetuma|asante|malipo|pesa|tuma|sawa|"
    r"karibu|habari|niaje|ndio|hapana|nime\w+|tafadhali)\b",
    re.IGNORECASE,
)


def claims_payment_received(text: Optional[str]) -> bool:
    """Does this reply assert, as a fact, that a payment arrived?"""
    for sentence in re.split(r"[.!?\n]+", text or ""):
        match = _ASSERTS_RECEIPT.search(sentence)
        if not match:
            continue
        # Only the words leading up to the claim can soften it: "once your
        # payment is received" is conditional, but "payment received, we will
        # prepare your order" is a claim followed by a promise.
        if _CONDITIONAL.search(sentence[:match.end()]):
            continue
        return True
    return False


def _money(currency: str, amount: Any) -> str:
    try:
        value = f"{float(str(amount).replace(',', '')):,.2f}".replace(".00", "")
    except (TypeError, ValueError):
        value = str(amount)
    return f"{currency} {value}".strip()


def safe_claim_reply(name: str = "", amount: Any = None, currency: str = "",
                     swahili: bool = False) -> str:
    """What is actually true once a customer says they have paid."""
    name = (name or "").strip()
    has_amount = amount not in (None, "", 0, "0")
    if swahili:
        who = f" {name}" if name else ""
        what = f" ya {_money(currency, amount)}" if has_amount else ""
        return (f"Asante{who}! 🙏 Nimetuma taarifa ya malipo yako{what} kwa mwenye "
                "biashara ili ayathibitishe. Utapata uthibitisho hapa punde "
                "yakikaguliwa.")
    who = f" {name}" if name else ""
    what = f" of {_money(currency, amount)}" if has_amount else ""
    return (f"Thank you{who}! 🙏 I've passed your payment{what} to the owner to check. "
            "You'll get a confirmation here as soon as it's verified.")


def no_payment_reply(swahili: bool = False) -> str:
    """The AI said money arrived, and nobody has even said they paid."""
    if swahili:
        return ("Sijaona malipo kwenye oda yako bado. Ukishalipa, nitumie jina na "
                "kiasi ulicholipa, nami nitampa mwenye biashara ayathibitishe.")
    return ("I can't see a payment on your order yet. Once you've paid, send me the "
            "name and amount you paid and I'll pass it to the owner to check.")


def _claim_from(actions: Iterable[Any]) -> Optional[dict]:
    for action in actions or []:
        if isinstance(action, dict) and action.get("type") == "set_payment_pending":
            return action
    return None


async def guard_payment_claim(
    db,
    reply_text: str,
    *,
    actions: Iterable[Any],
    user_id: Any,
    customer_id: Any,
    customer_message: str = "",
    currency: str = "",
) -> str:
    """Return the reply, or a truthful one if it claims an unverified payment."""
    if not claims_payment_received(reply_text):
        return reply_text

    swahili = bool(_SWAHILI.search(customer_message or "")) or bool(_SWAHILI.search(reply_text or ""))
    claim = _claim_from(actions)
    if claim is None:
        # No claim this turn, so the question is whether the customer's latest
        # order really has been paid. If it has, saying so is true.
        try:
            order = await db.orders.find_one(
                {"user_id": user_id, "customer_id": customer_id,
                 "status": {"$ne": "cancelled"}},
                sort=[("created_at", -1)],
            )
        except Exception:
            order = None
        status = str((order or {}).get("payment_status") or "").strip().lower()
        if status in VERIFIED_STATUSES:
            return reply_text
        if status != "pending_verification":
            # Nobody has claimed a payment either -- telling them it went to
            # the owner would be a second invention.
            return no_payment_reply(swahili)
        # Claimed earlier and still unchecked: "did you get it?" gets the truth.
        if swahili:
            return ("Malipo yako yako kwa mwenye biashara ili ayathibitishe. Utapata "
                    "uthibitisho hapa punde yakikaguliwa.")
        return ("Your payment is with the owner to check. You'll get a confirmation "
                "here as soon as it's verified.")

    return safe_claim_reply(
        name=(claim or {}).get("payee_name") or "",
        amount=(claim or {}).get("amount_paid") or (claim or {}).get("amount"),
        currency=currency,
        swahili=swahili,
    )
