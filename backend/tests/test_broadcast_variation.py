"""Each copy of a broadcast is its own message, without rewriting the owner.

An identical string sent to every recipient is the easiest possible thing to
match on, and a stronger signal than any gap between sends: a real send here
went out as three byte-identical texts to three people who had never messaged
the business.

The variation is the recipient's own name. Nothing is invented, reordered or
added beyond a greeting, because the owner's words are theirs.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from broadcast_variation import personalise, usable_first_name  # noqa: E402

PLAIN = "FLASH SALE\n20% off everything today only!\nVisit us now."
GREETS = "Hi! Just checking in.\nWe have new stock you might like."


def _c(name, cid="c1"):
    return {"_id": cid, "name": name}


# ------------------------------------------------------------- the name

def test_a_placeholder_is_not_a_name():
    """WhatsApp hands these back constantly; greeting by one is worse than not."""
    for junk in ("Contact 3434", "WhatsApp contact", "Customer 91", "contact",
                 "Unknown", "254712345678", "", None, " ", "+254 712 345 678"):
        assert usable_first_name(junk) is None, f"{junk!r} should not be greeted by"


def test_a_saved_name_is_used_as_saved():
    """Slicing to the first word makes 'African Princess' into 'African'."""
    assert usable_first_name("African Princess") == "African Princess"
    assert usable_first_name("Bro Frog") == "Bro Frog"
    assert usable_first_name("Salma") == "Salma"
    assert usable_first_name("Queen T") == "Queen T"
    # Capitalisation the owner chose is kept; an all-lower-case handle is fixed.
    assert usable_first_name("KuHu") == "KuHu"
    assert usable_first_name("sarcharo") == "Sarcharo"
    # Long names are trimmed to something greetable.
    assert usable_first_name("Samuel Mweni Odhiambo Otieno") == "Samuel Mweni"


# ------------------------------------------------------- the variation

def test_no_two_people_get_the_same_message():
    names = ["Salma", "Faith", "Kibe", "Queen T", "African Princess", "Rubby"]
    outs = {personalise(PLAIN, _c(n, n), seed=f"b:{n}") for n in names}
    assert len(outs) == len(names), "two recipients received identical text"


def test_the_owners_words_are_never_altered():
    out = personalise(PLAIN, _c("Salma"), seed="b:1")
    for line in PLAIN.splitlines():
        assert line in out, f"the owner's line {line!r} did not survive"
    assert out.endswith("Visit us now.")


def test_a_message_that_already_greets_is_not_greeted_twice():
    out = personalise(GREETS, _c("Salma"), seed="b:1")
    assert out.startswith("Hi Salma!"), out
    assert out.count("Hi") == 1, f"greeted twice: {out!r}"


def test_someone_with_no_real_name_gets_the_message_as_written():
    for junk in ("Contact 3434", "WhatsApp contact", None):
        assert personalise(PLAIN, _c(junk), seed="b:1") == PLAIN


def test_an_owner_who_personalised_it_themselves_is_left_alone():
    """The send loop substitutes {{name}}; do not also prepend a greeting."""
    msg = "Hi {{name}}, we have new hoodies in."
    assert personalise(msg, _c("Salma"), seed="b:1") == msg


def test_the_same_person_always_gets_the_same_wording():
    """A resumed send must not reword what it already sent."""
    first = personalise(PLAIN, _c("Salma"), seed="b1:c1")
    for _ in range(20):
        assert personalise(PLAIN, _c("Salma"), seed="b1:c1") == first


def test_the_greeting_form_is_not_always_the_same_one():
    """A fixed 'Hi X,' on every message is itself a prefix to match on."""
    outs = {personalise(PLAIN, _c("Salma"), seed=f"b{i}:c").splitlines()[0]
            for i in range(60)}
    assert len(outs) > 1, "every send used the identical opener"
