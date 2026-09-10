"""Make each copy of a broadcast its own message.

A broadcast sent as one identical string to every recipient is the easiest
possible thing to match on, and it is a stronger signal than any gap between
sends. Three identical texts to three people who had never messaged the
business is what a real send here looked like.

The variation is the recipient's own name, not decoration. Using it makes every
copy genuinely different, and it reads better than the same block of text sent
to everybody -- the same reason a person writing these by hand would open with
"Hi Salma" rather than nothing.

Nothing is invented. The owner's own words are never rewritten, reordered or
added to beyond a greeting with a name we actually know. Where there is no real
name -- WhatsApp gives back "Contact 3434" and "WhatsApp contact" often enough
-- the message goes out exactly as written, because greeting somebody by a
placeholder is worse than not greeting them at all.
"""
import hashlib
import re
from typing import Optional

# What WhatsApp hands back when it has no name for someone.
_PLACEHOLDER_NAME = re.compile(
    r"^\s*(?:whatsapp\s+contact|contact|customer|client|user|unknown)"
    r"(?:\s*[#-]?\s*\d+)?\s*$",
    re.IGNORECASE,
)

# Openers a person actually uses. The name carries the variation; these keep
# the greeting itself from being a fixed prefix on every send.
_OPENERS = ("Hi {name},", "Hey {name},", "{name},", "Hi {name}!")

# A message that already greets, so a prepended "Hi X," would greet twice.
_GREETS = re.compile(
    r"^\s*(hi|hey|hello|habari|niaje|sasa|mambo|hola|good\s+(morning|afternoon|evening))"
    r"\s*([,!.]|\b)",
    re.IGNORECASE,
)


def usable_first_name(name: Optional[str]) -> Optional[str]:
    """The name to greet somebody by, or None if we do not really have one."""
    raw = (name or "").strip()
    if not raw or len(raw) < 2:
        return None
    if _PLACEHOLDER_NAME.match(raw):
        return None
    # A phone number stored as a name is not a name.
    if sum(ch.isdigit() for ch in raw) > len(raw) / 2:
        return None

    # The saved name, not its first word. WhatsApp contacts are often handles
    # rather than given names, and slicing them produces "Hi African," out of
    # "African Princess" and "Hey Bro," out of "Bro Frog". Greeting somebody by
    # the name their contact card actually shows is what a person typing these
    # would do, and it is never wrong -- only occasionally formal.
    words = [w.strip(",.!:;") for w in raw.split()]
    words = [w for w in words if w][:2]
    if not words:
        return None
    if any(sum(ch.isdigit() for ch in w) for w in words):
        return None
    name = " ".join(words)
    if len(name) < 2 or len(name) > 24 or _PLACEHOLDER_NAME.match(name):
        return None
    # Keep the owner's own capitalisation for names like "KuHu"; only fix the
    # all-lower-case case, where "sarcharo" should read as "Sarcharo".
    return " ".join(w if not w.islower() else w.capitalize() for w in words)


def _variant_index(seed: str, count: int) -> int:
    """Stable choice, so a resumed send does not reword what it already sent."""
    digest = hashlib.sha256(seed.encode("utf-8", "replace")).digest()
    return digest[0] % count


def personalise(message: str, customer: dict, seed: str = "") -> str:
    """One recipient's copy of the broadcast.

    Returns the message unchanged when the owner has already personalised it
    with {{name}}, or when we have no real name for this person.
    """
    text = message or ""
    if "{{name}}" in text:
        # The owner placed the name themselves; the send loop substitutes it.
        return text

    first = usable_first_name(customer.get("name"))
    if not first:
        return text

    stripped = text.lstrip()
    if _GREETS.match(stripped):
        # Already opens with a greeting -- put the name into it rather than
        # greeting twice: "Hi! Just checking in" -> "Hi Salma! Just checking in".
        return re.sub(
            r"^(\s*)(hi|hey|hello|habari|niaje|sasa|mambo|hola"
            r"|good\s+(?:morning|afternoon|evening))",
            lambda m: f"{m.group(1)}{m.group(2)} {first}",
            text,
            count=1,
            flags=re.IGNORECASE,
        )

    opener = _OPENERS[_variant_index(seed or first, len(_OPENERS))]
    return f"{opener.format(name=first)}\n{text.lstrip()}"
