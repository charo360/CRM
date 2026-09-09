"""Decide whether the auto-reply should answer a contact at all.

A Kenyan business number is also a personal number: the same WhatsApp gets
customers, family, landlords and wrong numbers. The V2 auto-reply engine
answers everyone as a shop, because the contact classification lived in the
pre-router pipeline that V2 replaced, and the owner's own "Personal" toggle
was read into context and then never consulted.

Two failures matter here and they are not symmetric:

  * Answering a friend like a shop is embarrassing, and it keeps happening
    every message until someone notices.
  * Staying silent on a real customer loses a sale nobody ever hears about.

So silence is only for cases we are confident about: the owner said so, or
the contact is talking about something with no commercial reading and has
never once talked business. Anything ambiguous — including a bare "Niaje",
which is identical from a customer and a cousin — gets answered.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Someone asking about goods, money, delivery or an appointment. Swahili and
# Sheng included, because that is what these messages are actually written in.
BUSINESS_MARKERS = (
    "price", "bei", "cost", "how much", "ngapi", "pesa", "gharama",
    "catalog", "catalogue", "menu", "stock", "available", "unapatikana",
    "do you have", "uko na", "mko na", "mnayo", "iko",
    "nataka", "i want", "buy", "order", "nunua", "purchase", "oda",
    "delivery", "deliver", "shipping", "tuma", "nitumie", "pickup", "pick up",
    "mpesa", "payment", "pay", "lipa", "malipo", "paid", "invoice", "receipt",
    "till", "paybill", "book", "appointment", "booking", "reserve", "slot",
    "discount", "offer", "punguza", "bei poa", "wholesale", "bulk", "jumla",
    "refund", "exchange", "warranty", "complaint", "size", "colour", "color",
    "rangi", "quantity", "how many", "ngapi", "shop", "duka", "open", "closed",
)

# Signals with no ordinary commercial reading. One of these is enough to
# stop: waiting for a second means selling to someone we already know is not
# a customer, which is exactly what the owner asked not to happen.
PERSONAL_MARKERS_STRONG = (
    "miss you", "nakumiss", "love you", "nakupenda", "my love", "mpenzi",
    "happy birthday", "hbd", "rest in peace", "rip", "pole sana kwa msiba",
    "my brother", "my sister", "buda", "mzee wangu", "bro ", "sis ",
    "tuonane", "tukutane", "see you later", "wacha nikupigie",
    "it's me", "ni mimi", "unanijua", "you know me",
    "mama", "baba", "dad", "mum", "mom", "family", "familia",
    "church", "kanisa", "wedding", "harusi", "funeral", "mazishi",
    "good night", "usiku mwema", "how was your day",
    " bb ", "babe", "sweetheart", "sweetie",
)

# Friendly, but a polite customer opens this way too. One is not enough;
# two, with nothing commercial anywhere, is.
PERSONAL_MARKERS_SOFT = (
    "how are you", "habari yako", "uko aje", "mambo vipi", "niaje buda",
    "long time", "siku mingi", "congrats", "umeamkaje",
    "sasa we", "uko wapi kwani", "kwani umepotea", "call me later",
)

PERSONAL_MARKERS = PERSONAL_MARKERS_STRONG + PERSONAL_MARKERS_SOFT

# A verdict the owner made by hand always wins over anything inferred here.
OWNER_MARKED_PERSONAL = "owner marked this contact personal"
LOOKS_PERSONAL = "no business signal and repeated friendly signals"
CLEARLY_PERSONAL = "said something only a person says to a person"


def _hits(text: str, markers: Iterable[str]) -> int:
    """Count distinct markers present in the text."""
    low = f" {(text or '').lower()} "
    low = re.sub(r"\s+", " ", low)
    return sum(1 for m in markers if m in low)


def _incoming_texts(history: Optional[List[Dict[str, Any]]]) -> List[str]:
    rows = history or []
    out = []
    for row in rows:
        if (row.get("direction") or "") != "incoming":
            continue
        out.append(row.get("content") or row.get("text") or "")
    return out


def qualify(
    customer: Optional[Dict[str, Any]],
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, str, str]:
    """Return (should_auto_reply, verdict, reason).

    verdict is "personal", "customer" or "unclear". The auto-reply stays
    silent only on "personal".
    """
    if customer and customer.get("is_personal") is True:
        return False, "personal", OWNER_MARKED_PERSONAL

    # An explicit customer marking, or a history of doing business, settles it.
    if customer and customer.get("is_personal") is False and customer.get("contact_type") == "KNOWN_CUSTOMER":
        return True, "customer", "already known as a customer"

    incoming = _incoming_texts(history)
    business_now = _hits(message, BUSINESS_MARKERS)
    business_before = sum(_hits(t, BUSINESS_MARKERS) for t in incoming)
    if business_now or business_before:
        return True, "customer", "talking about products, money or delivery"

    # Something only a person says to a person — stop now rather than sell
    # one more message to someone we already know is not a customer.
    if _hits(message, PERSONAL_MARKERS_STRONG) or any(
        _hits(t, PERSONAL_MARKERS_STRONG) for t in incoming
    ):
        return False, "personal", CLEARLY_PERSONAL

    # Friendly but ambiguous. A polite customer opens this way too, so one is
    # not enough; a pattern with nothing commercial anywhere is.
    soft = _hits(message, PERSONAL_MARKERS_SOFT) + sum(
        _hits(t, PERSONAL_MARKERS_SOFT) for t in incoming
    )
    if soft >= 2:
        return False, "personal", LOOKS_PERSONAL

    # Everything else — a bare greeting, an unclear opener, a photo with no
    # caption — gets a reply. Losing a customer is the worse mistake.
    return True, "unclear", "not enough signal to stay silent"
