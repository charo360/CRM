"""One definition of who counts as a customer.

The Broadcast screen shows an audience count taken from GET /customers, which
deliberately leaves out contacts synced off the phone -- "WhatsApp-synced
contacts live in /contacts". Every broadcast sender queried
{"user_id": business_id} with no such filter, so the number the owner was
shown and the people who actually got the message came from different
populations.

On real data that gap was not small. One account's screen said 0 recipients
while a send to "all customers" would have dialled 5,025 numbers -- every
person who had ever appeared in the phone's contact list, none of whom asked
to hear from the business. Another showed 1 and would have sent 820.

Three consequences, in order of how much they hurt: a mass message to people
who never opted in (and the WhatsApp ban that follows), a plan's whole message
quota spent in one click, and -- because enforce_message_limit is handed the
real recipient count -- a broadcast that simply fails for an owner whose
screen says the audience is empty.

The predicate itself was already written out by hand in server.get_customers
and again in digest_service. Copies drift; this is the single copy.
"""
from typing import Any, Dict, List, Optional

# A customer is someone explicitly marked as one, or an older record from
# before is_customer existed that was not auto-created by a contact sync.
# Auto-created contacts with is_customer False are the ones to leave out.
VISIBLE_CUSTOMER = {
    "$or": [
        {"is_customer": True},
        {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}},
    ]
}

TAG_FOR_FILTER = {
    "returning": "Returning",
    "vip": "VIP",
    "new": "New",
}


def audience_query(
    business_id: Any,
    filter_type: Optional[str] = "all",
    customer_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """The recipients of a broadcast, matching what the owner was shown.

    Explicit ids are honoured as given. If the owner picked particular people
    -- a custom selection or a saved group -- that choice is the consent, and
    silently dropping someone they chose would be its own surprise.
    """
    query: Dict[str, Any] = {"user_id": business_id}

    if filter_type in ("custom", "group") or customer_ids:
        query["_id"] = {"$in": list(customer_ids or [])}
        return query

    tag = TAG_FOR_FILTER.get(filter_type or "")
    if tag:
        query["tags"] = tag

    # Composed under $and so a caller that adds its own $or cannot silently
    # replace this one -- a duplicate key in a dict literal keeps the last.
    query["$and"] = [VISIBLE_CUSTOMER]
    return query


def visible_customer_query(business_id: Any, **extra: Any) -> Dict[str, Any]:
    """The customer list itself: what GET /customers returns."""
    query: Dict[str, Any] = {"user_id": business_id, **extra}
    query["$and"] = [VISIBLE_CUSTOMER]
    return query
