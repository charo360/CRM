"""Coverage for WAHA contact syncing, LID handling and own-profile lookup.

These exercise the paths a business hits right after linking WhatsApp: the
address book must import in full, contacts WhatsApp identifies only by an
opaque LID must survive with no number invented for them, and the linked
account's own profile must be readable.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import waha_service
from waha_service import (
    WahaWhatsAppService,
    _is_lid_jid,
    _is_placeholder_name,
)


# ── Minimal in-memory stand-ins ────────────────────────────────────────────

class FakeCollection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    @staticmethod
    def _matches(row, query):
        for key, expected in query.items():
            if key == "$or":
                if not any(FakeCollection._matches(row, clause) for clause in expected):
                    return False
                continue
            if key == "$and":
                if not all(FakeCollection._matches(row, clause) for clause in expected):
                    return False
                continue
            actual = row
            for part in key.split("."):
                actual = (actual or {}).get(part) if isinstance(actual, dict) else None
            if isinstance(expected, dict):
                if "$exists" in expected and (actual is not None) != expected["$exists"]:
                    return False
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
                if "$lt" in expected and not (actual is not None and actual < expected["$lt"]):
                    return False
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$nin" in expected and actual in expected["$nin"]:
                    return False
                if "$regex" in expected:
                    import re as _re
                    if not (actual is not None
                            and _re.search(expected["$regex"], str(actual))):
                        return False
                if "$not" in expected:
                    import re as _re
                    inner = expected["$not"]
                    pattern = inner.get("$regex") if isinstance(inner, dict) else inner
                    if actual is not None and _re.search(pattern, str(actual)):
                        return False
                continue
            if actual != expected:
                return False
        return True

    async def find_one(self, query, projection=None):
        for row in self.rows:
            if self._matches(row, query):
                return dict(row)
        return None

    def find(self, query, projection=None):
        matched = [dict(r) for r in self.rows if self._matches(r, query)]

        class _Cursor:
            async def to_list(self, limit):
                return matched[:limit]

        return _Cursor()

    async def insert_one(self, document):
        self.rows.append(dict(document))

    async def count_documents(self, query):
        return sum(1 for row in self.rows if self._matches(row, query))

    async def update_many(self, query, operation):
        changed = 0
        for row in self.rows:
            if self._matches(row, query):
                for key, value in (operation.get("$set") or {}).items():
                    self._set_path(row, key, value)
                changed += 1
        return type("R", (), {"modified_count": changed})()

    async def delete_one(self, query):
        for i, row in enumerate(self.rows):
            if self._matches(row, query):
                self.rows.pop(i)
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    async def delete_many(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not self._matches(r, query)]
        return type("R", (), {"deleted_count": before - len(self.rows)})()

    def aggregate(self, pipeline):
        """Support the $match + $group shape the repair pass uses."""
        rows = [dict(r) for r in self.rows]
        for stage in pipeline:
            if "$match" in stage:
                match = stage["$match"]
                kept = []
                for row in rows:
                    ok = True
                    for key, expected in match.items():
                        value = row.get(key)
                        if isinstance(expected, dict) and "$regex" in expected:
                            import re as _re
                            if not (value and _re.search(expected["$regex"], str(value))):
                                ok = False
                        elif value != expected:
                            ok = False
                    if ok:
                        kept.append(row)
                rows = kept
            elif "$group" in stage:
                spec = stage["$group"]["_id"]
                seen = {}
                for row in rows:
                    if isinstance(spec, dict):
                        # {"_id": {"a": "$x", "b": "$y"}} -> a compound key
                        key = tuple(
                            (name, row.get(str(src).lstrip("$")))
                            for name, src in spec.items()
                        )
                        seen[key] = {"_id": {name: value for name, value in key}}
                    else:
                        # {"_id": "$field"} -> the field's value alone
                        value = row.get(str(spec).lstrip("$"))
                        seen[value] = {"_id": value}
                rows = list(seen.values())

        class _Cursor:
            def __aiter__(self):
                async def gen():
                    for row in rows:
                        yield row
                return gen()

        return _Cursor()

    @staticmethod
    def _set_path(row, key, value):
        """Apply a dotted key the way Mongo does, creating parents as needed."""
        parts = key.split(".")
        target = row
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value

    async def update_one(self, query, operation):
        for row in self.rows:
            if self._matches(row, query):
                for key, value in (operation.get("$set") or {}).items():
                    self._set_path(row, key, value)
                for key in (operation.get("$unset") or {}):
                    row.pop(key, None)
                return
        # Mirror Mongo: an update that matches nothing is a no-op.


class FakeDb:
    def __init__(self, users=None, customers=None, messages=None, **extra):
        self.users = FakeCollection(users)
        self.customers = FakeCollection(customers)
        self.messages = FakeCollection(messages)
        self._extra = {name: FakeCollection(rows) for name, rows in extra.items()}

    def __getitem__(self, name):
        """Mirror Mongo's db["collection"], creating unknown ones empty."""
        if hasattr(self, name) and isinstance(getattr(self, name), FakeCollection):
            return getattr(self, name)
        return self._extra.setdefault(name, FakeCollection())


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeClient:
    """Serve canned WAHA responses and record which URLs were asked for."""

    def __init__(self, routes, calls):
        self.routes = routes
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None, params=None):
        self.calls.append((url, dict(params or {})))
        for fragment, handler in self.routes.items():
            if fragment in url:
                result = handler(params or {})
                return result if isinstance(result, FakeResponse) else FakeResponse(result)
        return FakeResponse({}, status_code=404)


def build_service(db, routes):
    calls = []
    service = WahaWhatsAppService(db)
    service.node_urls = ("http://waha.test",)
    service.base_url = "http://waha.test"
    service.verify_ssl = False
    original = waha_service.httpx.AsyncClient
    waha_service.httpx.AsyncClient = lambda *a, **k: FakeClient(routes, calls)
    return service, calls, original


def run(db, routes, coroutine_factory):
    service, calls, original = build_service(db, routes)
    try:
        return asyncio.run(coroutine_factory(service)), calls
    finally:
        waha_service.httpx.AsyncClient = original


USER = {"_id": "biz-1", "whatsapp": {"instance_name": "user_biz_1", "waha_node": 0}}


# ── Helpers ────────────────────────────────────────────────────────────────

def test_placeholder_names_are_replaceable_but_real_names_are_not():
    assert _is_placeholder_name("Contact 1234")
    assert _is_placeholder_name("Customer 88")
    assert _is_placeholder_name("WhatsApp contact")
    assert _is_placeholder_name("+254 712 345 678")
    assert not _is_placeholder_name("Jane from Accounts")


def test_only_exact_lid_jids_are_treated_as_lids():
    assert _is_lid_jid("123456789@lid")
    assert not _is_lid_jid("123456789@c.us")
    assert not _is_lid_jid("123456789")


# ── Contact syncing ────────────────────────────────────────────────────────

def test_fetch_contacts_pages_beyond_the_first_batch():
    """A large address book must not stop at the first page."""
    page_one = [{"id": f"2547000000{i:02d}@c.us", "number": f"2547000000{i:02d}", "name": f"Person {i}"}
                for i in range(500)]
    page_two = [{"id": "254733333333@c.us", "number": "254733333333", "name": "Last Person"}]

    db = FakeDb(users=[USER])
    routes = {
        "/lids": lambda p: [],
        "/api/contacts/all": lambda p: page_two if int(p.get("offset", 0)) else page_one,
    }
    result, calls = run(db, routes, lambda s: s.fetch_contacts("biz-1"))

    assert result["status"] == "success"
    assert result["created"] == 501, result
    assert any(c.get("name") == "Last Person" for c in db.customers.rows)
    offsets = [p.get("offset") for url, p in calls if "/api/contacts/all" in url]
    assert offsets == [0, 500], offsets


def test_engine_that_ignores_offset_does_not_spin():
    """Some engines return the whole book regardless of offset."""
    everything = [{"id": f"2547000000{i:02d}@c.us", "number": f"2547000000{i:02d}", "name": f"P{i}"}
                  for i in range(500)]

    db = FakeDb(users=[USER])
    routes = {
        "/lids": lambda p: [],
        "/api/contacts/all": lambda p: everything,   # offset deliberately ignored
    }
    result, calls = run(db, routes, lambda s: s.fetch_contacts("biz-1"))

    assert result["created"] == 500
    assert len(db.customers.rows) == 500
    contact_calls = [url for url, _ in calls if "/api/contacts/all" in url]
    assert len(contact_calls) == 2, contact_calls  # one real page, one that repeats


def test_lid_contact_without_a_number_is_kept_not_dropped():
    """An unresolved number must not lose the contact entirely."""
    db = FakeDb(users=[USER])
    routes = {
        "/lids": lambda p: [],
        "/api/contacts/all": lambda p: [] if int(p.get("offset", 0)) else [
            {"id": "99887766554433@lid", "name": "Hidden Buyer"},
        ],
    }
    result, _ = run(db, routes, lambda s: s.fetch_contacts("biz-1"))

    assert result["created"] == 1
    assert result["without_number"] == 1
    saved = db.customers.rows[0]
    assert saved["lid_jid"] == "99887766554433@lid"
    assert saved["phone_number"] == ""
    assert saved["phone_number_unavailable"] is True
    # The LID digits must never be presented as a phone number.
    assert "99887766554433" not in saved["phone_number"]


def test_lid_contact_uses_the_bulk_mapping_when_whatsapp_exposes_a_number():
    db = FakeDb(users=[USER])
    routes = {
        "/lids": lambda p: [] if int(p.get("offset", 0)) else [
            {"lid": "99887766554433@lid", "pn": "254712345678@c.us"},
        ],
        "/api/contacts/all": lambda p: [] if int(p.get("offset", 0)) else [
            {"id": "99887766554433@lid", "name": "Known Buyer"},
        ],
    }
    result, calls = run(db, routes, lambda s: s.fetch_contacts("biz-1"))

    assert result["created"] == 1
    saved = db.customers.rows[0]
    assert saved["phone_number"] == "254712345678"
    assert saved["lid_jid"] == "99887766554433@lid"
    assert "phone_number_unavailable" not in saved
    # The bulk table must satisfy the lookup without a per-contact request.
    assert not [url for url, _ in calls if "/lids/" in url]


def test_existing_lid_contact_is_updated_not_duplicated():
    existing = {
        "_id": "cust-1", "user_id": "biz-1", "name": "Contact 4433",
        "phone_number": "", "lid_jid": "99887766554433@lid",
        "phone_number_unavailable": True,
    }
    db = FakeDb(users=[USER], customers=[existing])
    routes = {
        "/lids": lambda p: [] if int(p.get("offset", 0)) else [
            {"lid": "99887766554433@lid", "pn": "254712345678@c.us"},
        ],
        "/api/contacts/all": lambda p: [] if int(p.get("offset", 0)) else [
            {"id": "99887766554433@lid", "name": "Real Name"},
        ],
    }
    result, _ = run(db, routes, lambda s: s.fetch_contacts("biz-1"))

    assert result["created"] == 0 and result["updated"] == 1
    assert len(db.customers.rows) == 1
    saved = db.customers.rows[0]
    assert saved["phone_number"] == "254712345678"
    assert saved["name"] == "Real Name"          # placeholder was replaced
    assert "phone_number_unavailable" not in saved


def test_sync_never_overwrites_a_name_the_business_typed():
    existing = {
        "_id": "cust-1", "user_id": "biz-1", "name": "Best Supplier Ltd",
        "phone_number": "254712345678",
    }
    db = FakeDb(users=[USER], customers=[existing])
    routes = {
        "/lids": lambda p: [],
        "/api/contacts/all": lambda p: [] if int(p.get("offset", 0)) else [
            {"id": "254712345678@c.us", "number": "254712345678", "name": "whatsapp pushname"},
        ],
    }
    run(db, routes, lambda s: s.fetch_contacts("biz-1"))
    assert db.customers.rows[0]["name"] == "Best Supplier Ltd"


def test_contact_with_neither_number_nor_lid_is_skipped():
    db = FakeDb(users=[USER])
    routes = {
        "/lids": lambda p: [],
        "/api/contacts/all": lambda p: [] if int(p.get("offset", 0)) else [
            {"id": "status@broadcast", "name": "Status"},
            {"id": "12@c.us", "number": "12", "name": "Too short"},
        ],
    }
    result, _ = run(db, routes, lambda s: s.fetch_contacts("biz-1"))
    assert result["created"] == 0
    assert db.customers.rows == []


# ── Own profile ────────────────────────────────────────────────────────────

def test_fetch_own_profile_stores_name_photo_and_number():
    db = FakeDb(users=[dict(USER)])
    routes = {
        "/profile": lambda p: {
            "id": "254799999999@c.us",
            "name": "Zilo Store",
            "picture": "https://waha.test/photo.jpg",
        },
    }
    profile, _ = run(db, routes, lambda s: s.fetch_own_profile("biz-1"))

    assert profile["name"] == "Zilo Store"
    assert profile["picture"] == "https://waha.test/photo.jpg"
    assert profile["number"] == "254799999999"
    stored = db.users.rows[0]["whatsapp"]
    assert stored["profile_name"] == "Zilo Store"
    assert stored["profile_picture"] == "https://waha.test/photo.jpg"
    assert stored["phone_number"] == "254799999999"
    assert stored["profile_checked_at"] is not None


def test_failed_profile_lookup_records_an_attempt_so_it_backs_off():
    db = FakeDb(users=[dict(USER)])
    routes = {"/profile": lambda p: FakeResponse({}, status_code=422)}
    profile, _ = run(db, routes, lambda s: s.fetch_own_profile("biz-1"))

    assert profile == {}
    assert db.users.rows[0]["whatsapp"]["profile_checked_at"] is not None


# ── History import ─────────────────────────────────────────────────────────

def test_history_for_a_hidden_number_contact_uses_its_lid_chat():
    """Building a phone JID for a hidden number produced a bare '@c.us'."""
    customer = {
        "_id": "cust-1", "user_id": "biz-1", "name": "Hidden Buyer",
        "phone_number": "", "lid_jid": "99887766554433@lid",
    }
    db = FakeDb(users=[USER], customers=[customer])
    routes = {
        "/lids/": lambda p: {"lid": "99887766554433@lid", "pn": None},
        "/messages": lambda p: [
            {"id": "msg-1", "body": "Do you deliver?", "fromMe": False, "timestamp": 1700000000},
        ],
    }
    result, calls = run(
        db, routes, lambda s: s.fetch_history_for_contact("biz-1", "", "cust-1")
    )

    assert result["messages_imported"] == 1
    message_urls = [url for url, _ in calls if url.endswith("/messages")]
    assert message_urls and "99887766554433%40lid" in message_urls[0].replace("@", "%40")
    assert "%40c.us" not in message_urls[0].replace("@", "%40")
    stored = db.messages.rows[0]
    assert stored["remote_jid"] == "99887766554433@lid"
    assert stored["from_number"] == ""   # no number invented


def test_history_falls_back_to_the_phone_chat_for_a_normal_contact():
    customer = {
        "_id": "cust-2", "user_id": "biz-1", "name": "Jane",
        "phone_number": "254712345678",
    }
    db = FakeDb(users=[USER], customers=[customer])
    routes = {
        "/messages": lambda p: [
            {"id": "msg-9", "body": "Hi", "fromMe": False, "timestamp": 1700000000},
        ],
    }
    result, calls = run(
        db, routes, lambda s: s.fetch_history_for_contact("biz-1", "254712345678", "cust-2")
    )

    assert result["messages_imported"] == 1
    assert db.messages.rows[0]["from_number"] == "254712345678"
    assert any("c.us" in url for url, _ in calls)


# ── Reading the number out of the engine payload ───────────────────────────

def test_gows_payload_yields_the_senders_real_number():
    """GOWS resolves the LID itself and reports it as _data.Info.SenderAlt."""
    from waha_service import _payload_phone
    payload = {
        "chatId": "99887766554433@lid",
        "fromMe": False,
        "from": "99887766554433@lid",
        "_data": {"Info": {
            "Chat": "99887766554433@lid",
            "Sender": "99887766554433@lid",
            "SenderAlt": "254712345678@s.whatsapp.net",
        }},
    }
    assert _payload_phone(payload, from_me=False, own_number="254799999999") == "254712345678"


def test_outgoing_message_takes_the_recipient_not_our_own_number():
    """For a message we sent, SenderAlt is us - storing it would be wrong."""
    from waha_service import _payload_phone
    payload = {
        "chatId": "99887766554433@lid",
        "fromMe": True,
        "to": "99887766554433@lid",
        "_data": {"Info": {
            "SenderAlt": "254799999999@s.whatsapp.net",   # the business itself
            "RecipientAlt": "254712345678@s.whatsapp.net",  # the customer
        }},
    }
    assert _payload_phone(payload, from_me=True, own_number="254799999999") == "254712345678"


def test_owner_number_is_only_used_when_it_is_the_only_party():
    """A payload naming just the owner is the self-chat, so keep that number.

    The guard exists to stop an outgoing message filing our number against a
    customer - not to blank the one number we are certain of. The stronger
    invariant is covered by the test below: a real contact always wins.
    """
    from waha_service import _payload_phone
    payload = {"_data": {"Info": {"SenderAlt": "254799999999@s.whatsapp.net"}}}
    assert _payload_phone(payload, from_me=False, own_number="+254799999999") == "254799999999"


def test_group_participant_pn_is_accepted():
    from waha_service import _payload_phone
    payload = {"participant": {"pn": "254712345678@c.us"}}
    assert _payload_phone(payload, from_me=False, own_number="") == "254712345678"


def test_a_lid_is_never_mistaken_for_a_phone_number():
    """The whole point: an opaque LID must not become a stored number."""
    from waha_service import _payload_phone
    payload = {
        "from": "99887766554433@lid",
        "_data": {"Info": {"Sender": "99887766554433@lid", "SenderAlt": ""}},
    }
    assert _payload_phone(payload, from_me=False, own_number="") is None


def test_payload_lookup_is_case_insensitive_across_engines():
    from waha_service import _payload_phone
    payload = {"_data": {"info": {"senderalt": "254712345678@s.whatsapp.net"}}}
    assert _payload_phone(payload, from_me=False, own_number="") == "254712345678"


def test_self_chat_keeps_the_owners_own_number():
    """The chat a business has with itself must not be blanked.

    Skipping the owner's number is there to stop an outgoing message filing
    our number as the customer's - but when every identity in the payload is
    the owner, the contact really is the owner.
    """
    from waha_service import _payload_phone
    payload = {
        "chatId": "13444002652393@lid",
        "fromMe": True,
        "_data": {"Info": {
            "SenderAlt": "12026995029@s.whatsapp.net",
            "RecipientAlt": "12026995029@s.whatsapp.net",
        }},
    }
    assert _payload_phone(payload, from_me=True, own_number="12026995029") == "12026995029"


def test_a_real_contact_still_wins_over_the_owners_number():
    """The fallback must not weaken the outgoing-message protection."""
    from waha_service import _payload_phone
    payload = {
        "fromMe": True,
        "_data": {"Info": {
            "SenderAlt": "12026995029@s.whatsapp.net",     # us
            "RecipientAlt": "254712345678@s.whatsapp.net",  # the customer
        }},
    }
    assert _payload_phone(payload, from_me=True, own_number="12026995029") == "254712345678"


def test_repair_recovers_a_number_the_lids_endpoint_will_not_give():
    """The endpoint returns null, but the chat's messages carry the answer."""
    customer = {
        "_id": "cust-1", "user_id": "biz-1", "name": "Contact 6293",
        "phone_number": "", "lid_jid": "178752445276293@lid",
        "phone_number_unavailable": True,
    }
    message = {
        "_id": "m1", "user_id": "biz-1", "customer_id": "cust-1",
        "remote_jid": "178752445276293@lid",
    }
    db = FakeDb(users=[USER], customers=[customer], messages=[message])
    routes = {
        "/lids": lambda p: FakeResponse({"lid": "178752445276293@lid", "pn": None}),
        "/messages": lambda p: [
            {"id": "x1", "fromMe": False,
             "_data": {"Info": {"SenderAlt": "254712345678@s.whatsapp.net"}}},
        ],
    }
    result, _ = run(db, routes, lambda s: s.repair_lid_contacts("biz-1"))

    assert result["repaired"] == 1, result
    saved = db.customers.rows[0]
    assert saved["phone_number"] == "254712345678"
    assert "phone_number_unavailable" not in saved


# ── Merging duplicate contacts ─────────────────────────────────────────────

def _merge_fixture():
    """The real shape seen in production: a LID record holding the whole
    conversation, and a second record carrying only the phone number."""
    lid_record = {
        "_id": "lid-rec", "user_id": "biz-1", "name": "Sarcharo",
        "phone_number": "", "lid_jid": "13444002652393@lid",
        "phone_number_unavailable": True, "is_customer": True,
        "profile_picture": "https://waha.test/pic.jpg", "tags": ["New"],
        "stage": "negotiating", "notes": "asked about delivery",
        "last_message": "see you then", "last_contacted": 200,
        "purchase_count": 2, "total_spent": 50.0,
    }
    phone_record = {
        "_id": "num-rec", "user_id": "biz-1", "name": "sarcharo",
        "phone_number": "+12026995029", "is_customer": False,
        "tags": ["Synced"], "stage": "lead", "last_contacted": 100,
        "purchase_count": 1, "total_spent": 25.0,
    }
    return lid_record, phone_record


def test_merge_keeps_the_record_holding_the_conversation():
    lid_record, phone_record = _merge_fixture()
    db = FakeDb(
        users=[USER], customers=[lid_record, phone_record],
        messages=[{"_id": f"m{i}", "user_id": "biz-1", "customer_id": "lid-rec",
                   "remote_jid": "13444002652393@lid"} for i in range(85)],
    )
    routes = {
        "/lids": lambda p: FakeResponse({"lid": "13444002652393@lid", "pn": None}),
        "/messages": lambda p: [
            {"id": "x", "fromMe": True,
             "_data": {"Info": {"SenderAlt": "12026995029@s.whatsapp.net",
                                "RecipientAlt": "12026995029@s.whatsapp.net"}}},
        ],
    }
    result, _ = run(db, routes, lambda s: s.repair_lid_contacts("biz-1"))

    assert result["merged"] == 1, result
    assert len(db.customers.rows) == 1
    survivor = db.customers.rows[0]
    assert survivor["_id"] == "lid-rec"          # the one with the 85 messages
    assert survivor["phone_number"] == "12026995029"
    assert "phone_number_unavailable" not in survivor
    # Every message still points at the surviving contact.
    assert all(m["customer_id"] == "lid-rec" for m in db.messages.rows)


def test_merge_preserves_work_from_both_records():
    lid_record, phone_record = _merge_fixture()
    # Flip which side carries the promotion and the picture.
    lid_record["is_customer"] = False
    lid_record["profile_picture"] = None
    phone_record["is_customer"] = True
    phone_record["profile_picture"] = "https://waha.test/other.jpg"

    db = FakeDb(users=[USER], customers=[lid_record, phone_record],
                messages=[{"_id": "m1", "user_id": "biz-1", "customer_id": "lid-rec",
                           "remote_jid": "13444002652393@lid"}])
    routes = {
        "/lids": lambda p: FakeResponse({"lid": "13444002652393@lid", "pn": None}),
        "/messages": lambda p: [
            {"id": "x", "fromMe": True,
             "_data": {"Info": {"SenderAlt": "12026995029@s.whatsapp.net",
                                "RecipientAlt": "12026995029@s.whatsapp.net"}}},
        ],
    }
    run(db, routes, lambda s: s.repair_lid_contacts("biz-1"))

    survivor = db.customers.rows[0]
    assert survivor["is_customer"] is True                       # promotion kept
    assert survivor["profile_picture"] == "https://waha.test/other.jpg"
    assert survivor["stage"] == "negotiating"                    # richer stage kept
    assert survivor["notes"] == "asked about delivery"
    assert set(survivor["tags"]) == {"New", "Synced"}            # tags unioned
    assert survivor["purchase_count"] == 3                       # 2 + 1
    assert survivor["total_spent"] == 75.0                       # 50 + 25


def test_merge_repoints_orders_and_loyalty_not_just_messages():
    """Orders and loyalty are money; orphaning them loses real records."""
    lid_record, phone_record = _merge_fixture()
    db = FakeDb(
        users=[USER], customers=[lid_record, phone_record],
        messages=[{"_id": "m1", "user_id": "biz-1", "customer_id": "lid-rec",
                   "remote_jid": "13444002652393@lid"}],
        orders=[{"_id": "o1", "customer_id": "num-rec", "total": 25.0}],
        loyalty_transactions=[{"_id": "l1", "customer_id": "num-rec", "points": 10}],
        customer_analysis=[{"_id": "a1", "customer_id": "num-rec"}],
        conversation_states=[{"_id": "s1", "customer_id": "num-rec"}],
    )
    routes = {
        "/lids": lambda p: FakeResponse({"lid": "13444002652393@lid", "pn": None}),
        "/messages": lambda p: [
            {"id": "x", "fromMe": True,
             "_data": {"Info": {"SenderAlt": "12026995029@s.whatsapp.net",
                                "RecipientAlt": "12026995029@s.whatsapp.net"}}},
        ],
    }
    run(db, routes, lambda s: s.repair_lid_contacts("biz-1"))

    for name in ("orders", "loyalty_transactions", "customer_analysis",
                 "conversation_states"):
        rows = db[name].rows
        assert rows and all(r["customer_id"] == "lid-rec" for r in rows), name


def test_first_sync_does_not_leave_the_same_person_listed_twice():
    """The new-account path: the address book imports a contact by number, then
    history resolves a LID chat to that same number. One person, one record."""
    from_addressbook = {
        "_id": "book-rec", "user_id": "biz-1", "name": "Jane",
        "phone_number": "254712345678", "is_customer": False, "tags": ["Synced"],
    }
    from_lid_chat = {
        "_id": "lid-rec", "user_id": "biz-1", "name": "WhatsApp contact",
        "phone_number": "", "lid_jid": "99887766554433@lid",
        "phone_number_unavailable": True, "tags": ["New"],
    }
    db = FakeDb(
        users=[USER], customers=[from_addressbook, from_lid_chat],
        messages=[{"_id": "m1", "user_id": "biz-1", "customer_id": "lid-rec",
                   "remote_jid": "99887766554433@lid"}],
        orders=[{"_id": "o1", "customer_id": "book-rec", "total": 10.0}],
    )
    routes = {
        "/lids/": lambda p: {"lid": "99887766554433@lid", "pn": None},
        "/messages": lambda p: [
            {"id": "h1", "body": "hello", "fromMe": False, "timestamp": 1700000000,
             "_data": {"Info": {"SenderAlt": "254712345678@s.whatsapp.net"}}},
        ],
    }
    run(db, routes, lambda s: s.fetch_history_for_contact("biz-1", "", "lid-rec"))

    assert len(db.customers.rows) == 1, [c["name"] for c in db.customers.rows]
    survivor = db.customers.rows[0]
    assert survivor["phone_number"] == "254712345678"
    assert "phone_number_unavailable" not in survivor
    assert survivor["name"] == "Jane"                    # real name beat the placeholder
    assert set(survivor["tags"]) == {"New", "Synced"}
    # The order followed the merge rather than being orphaned.
    assert db["orders"].rows[0]["customer_id"] == survivor["_id"]


# ── A LID must never become a phone number ─────────────────────────────────

def test_lids_endpoint_echoing_the_lid_is_not_a_number():
    """WhatsApp returns the LID as 'pn' when it has no mapping to give.

    Storing that is what produced contacts whose number was a 15-digit code.
    """
    from waha_service import _resolved_phone
    assert _resolved_phone("226465153077249", "226465153077249@lid") is None
    assert _resolved_phone("226465153077249@c.us", "226465153077249@lid") is None
    # A genuine mapping for the same LID still gets through.
    assert _resolved_phone("254712345678", "226465153077249@lid") == "254712345678"


def test_bulk_lid_table_discards_rows_that_echo_the_lid():
    db = FakeDb(users=[USER])
    routes = {
        "/lids": lambda p: [] if int(p.get("offset", 0)) else [
            {"lid": "226465153077249@lid", "pn": "226465153077249@c.us"},  # echo
            {"lid": "99887766554433@lid", "pn": "254712345678@c.us"},      # real
        ],
        "/api/contacts/all": lambda p: [],
    }
    mapping, _ = run(db, routes, lambda s: s._lid_phone_map("biz-1"))
    assert mapping == {"99887766554433": "254712345678"}


def test_contact_sync_leaves_an_echoed_lid_without_a_number():
    """Better a contact honestly marked hidden than one wearing a fake number."""
    db = FakeDb(users=[USER])
    routes = {
        "/lids": lambda p: [] if int(p.get("offset", 0)) else [
            {"lid": "226465153077249@lid", "pn": "226465153077249@c.us"},
        ],
        "/api/contacts/all": lambda p: [] if int(p.get("offset", 0)) else [
            {"id": "226465153077249@lid", "name": "Contact 7249"},
        ],
    }
    result, _ = run(db, routes, lambda s: s.fetch_contacts("biz-1"))

    saved = db.customers.rows[0]
    assert saved["phone_number"] == ""
    assert saved["phone_number_unavailable"] is True
    assert result["without_number"] == 1


def test_payload_echoing_the_lid_is_rejected():
    from waha_service import _payload_phone
    payload = {
        "chatId": "226465153077249@lid",
        "_data": {"Info": {"SenderAlt": "226465153077249@s.whatsapp.net"}},
    }
    assert _payload_phone(payload, from_me=False, own_number="",
                          lid="226465153077249@lid") is None


def test_repair_blanks_a_contact_whose_number_is_its_own_lid():
    """The three real rows found in production: phone == lid digits."""
    customer = {
        "_id": "cust-1", "user_id": "biz-1", "name": "Contact 7249",
        "phone_number": "226465153077249", "lid_jid": "226465153077249@lid",
    }
    db = FakeDb(users=[USER], customers=[customer],
                messages=[{"_id": "m1", "user_id": "biz-1", "customer_id": "cust-1",
                           "remote_jid": "226465153077249@lid"}])
    routes = {
        # The endpoint echoes the LID; the chat has nothing better to offer.
        "/lids/": lambda p: {"lid": "226465153077249@lid", "pn": "226465153077249@c.us"},
        "/messages": lambda p: [],
    }
    result, _ = run(db, routes, lambda s: s.repair_lid_contacts("biz-1"))

    assert result["number_unavailable"] == 1, result
    saved = db.customers.rows[0]
    assert saved["phone_number"] == ""
    assert saved["phone_number_unavailable"] is True


def test_a_number_whatsapp_says_does_not_exist_is_cleared():
    """The four rows with a long code but no LID recorded to compare against."""
    db = FakeDb(users=[USER], customers=[
        {"_id": "c1", "user_id": "biz-1", "name": "politician",
         "phone_number": "153055840444434"},
        {"_id": "c2", "user_id": "biz-1", "name": "Jane",
         "phone_number": "254712345678"},   # normal length, never questioned
    ])
    routes = {"/contacts/check-exists": lambda p: {"numberExists": False, "pn": None}}
    result, calls = run(db, routes, lambda s: s.verify_suspicious_numbers("biz-1"))

    assert result["cleared"] == 1
    bad = next(c for c in db.customers.rows if c["_id"] == "c1")
    assert bad["phone_number"] == ""
    assert bad["phone_number_unavailable"] is True
    # The ordinary contact was never questioned, so it costs no request.
    assert result["checked"] == 1
    assert next(c for c in db.customers.rows if c["_id"] == "c2")["phone_number"] == "254712345678"


def test_an_inconclusive_answer_leaves_the_number_alone():
    """Never destroy a number on a failed or ambiguous lookup."""
    db = FakeDb(users=[USER], customers=[
        {"_id": "c1", "user_id": "biz-1", "name": "maybe real",
         "phone_number": "153055840444434"},
    ])
    routes = {"/contacts/check-exists": lambda p: FakeResponse({}, status_code=500)}
    result, _ = run(db, routes, lambda s: s.verify_suspicious_numbers("biz-1"))

    assert result["cleared"] == 0
    assert db.customers.rows[0]["phone_number"] == "153055840444434"


def test_whatsapp_correcting_the_number_is_applied():
    db = FakeDb(users=[USER], customers=[
        {"_id": "c1", "user_id": "biz-1", "name": "Contact 9721",
         "phone_number": "265858811199721", "phone_number_unavailable": True},
    ])
    routes = {"/contacts/check-exists": lambda p: {
        "numberExists": True, "pn": "254712345678@c.us"}}
    result, _ = run(db, routes, lambda s: s.verify_suspicious_numbers("biz-1"))

    assert result["corrected"] == 1
    saved = db.customers.rows[0]
    assert saved["phone_number"] == "254712345678"
    assert "phone_number_unavailable" not in saved


def test_contacts_endpoint_answers_when_the_lids_endpoint_will_not():
    """A source that is sometimes right beats calling the number unknowable.

    This endpoint used to be skipped entirely because it can echo the LID.
    Rejecting echoes makes it safe to ask.
    """
    db = FakeDb(users=[USER])
    routes = {
        "/lids/": lambda p: {"lid": "99887766554433@lid", "pn": None},
        "/api/contacts": lambda p: {"id": "99887766554433@lid",
                                    "number": "254712345678"},
    }
    phone, _ = run(db, routes, lambda s: s._resolve_lid_phone("biz-1", "99887766554433@lid"))
    assert phone == "254712345678"


def test_contacts_endpoint_echoing_the_lid_is_still_rejected():
    db = FakeDb(users=[USER])
    routes = {
        "/lids/": lambda p: {"lid": "99887766554433@lid", "pn": None},
        # The exact failure mode that made this endpoint untrusted.
        "/api/contacts": lambda p: {"id": "99887766554433@lid",
                                    "number": "99887766554433"},
    }
    phone, _ = run(db, routes, lambda s: s._resolve_lid_phone("biz-1", "99887766554433@lid"))
    assert phone is None


# ── Channels, groups and other non-people ──────────────────────────────────

def test_a_channel_is_not_a_person():
    from waha_service import _is_person_chat
    assert _is_person_chat("254712345678@c.us")
    assert _is_person_chat("99887766554433@lid")
    # The real row found in production: a WhatsApp Channel saved as a contact.
    assert not _is_person_chat("120363179873679741@newsletter")
    assert not _is_person_chat("120363179873679741@g.us")
    assert not _is_person_chat("status@broadcast")
    assert not _is_person_chat("")


def test_a_channel_post_never_creates_a_contact():
    db = FakeDb(users=[USER])
    service, _, original = build_service(db, {})
    try:
        parsed = asyncio.run(service.handle_incoming_message("user_biz_1", {
            "chatId": "120363179873679741@newsletter",
            "from": "120363179873679741@newsletter",
            "body": "https://example.com/an-article",
            "fromMe": False,
        }))
    finally:
        waha_service.httpx.AsyncClient = original
    assert parsed is None


def test_removing_a_channel_contact_leaves_real_people_alone():
    """Only a contact whose every message came from a channel is dropped."""
    db = FakeDb(
        users=[USER],
        customers=[
            {"_id": "chan", "user_id": "biz-1", "name": "Contact 9741"},
            {"_id": "person", "user_id": "biz-1", "name": "Jane",
             "phone_number": "254712345678"},
        ],
        messages=[
            {"_id": "n1", "user_id": "biz-1", "customer_id": "chan",
             "remote_jid": "120363179873679741@newsletter"},
            # Jane appears in a group but is a real person with a real chat.
            {"_id": "g1", "user_id": "biz-1", "customer_id": "person",
             "remote_jid": "120363000000000001@g.us"},
            {"_id": "p1", "user_id": "biz-1", "customer_id": "person",
             "remote_jid": "254712345678@c.us"},
        ],
    )
    removed, _ = run(db, {}, lambda s: s.remove_non_person_contacts("biz-1"))

    assert removed == 1
    assert [c["_id"] for c in db.customers.rows] == ["person"]
    # The channel's posts go with it; Jane keeps every message.
    assert {m["_id"] for m in db.messages.rows} == {"g1", "p1"}


# ── Real names for placeholder contacts ────────────────────────────────────

def test_placeholder_names_are_replaced_with_the_real_one():
    db = FakeDb(users=[USER], customers=[
        {"_id": "c1", "user_id": "biz-1", "name": "Contact 3665",
         "phone_number": "", "lid_jid": "267413270593665@lid"},
        {"_id": "c2", "user_id": "biz-1", "name": "Contact 9721",
         "phone_number": "254712345678"},
        {"_id": "c3", "user_id": "biz-1", "name": "Real Business Ltd",
         "phone_number": "254700000000"},
    ])
    routes = {"/api/contacts": lambda p: (
        {"pushname": "Amina"} if "lid" in str(p.get("contactId"))
        else {"name": "Peter Otieno"}
    )}
    result, calls = run(db, routes, lambda s: s.backfill_contact_names("biz-1"))

    assert result["renamed"] == 2
    names = {c["_id"]: c["name"] for c in db.customers.rows}
    assert names["c1"] == "Amina"
    assert names["c2"] == "Peter Otieno"
    # A name the business already recognises is never questioned or overwritten.
    assert names["c3"] == "Real Business Ltd"
    assert result["checked"] == 2


def test_a_number_returned_as_a_name_is_not_accepted():
    """The API happily hands back the number as the contact's 'name'."""
    db = FakeDb(users=[USER], customers=[
        {"_id": "c1", "user_id": "biz-1", "name": "Contact 5678",
         "phone_number": "254712345678"},
    ])
    routes = {"/api/contacts": lambda p: {"name": "254712345678",
                                          "pushname": "+254 712 345678"}}
    result, _ = run(db, routes, lambda s: s.backfill_contact_names("biz-1"))

    assert result["renamed"] == 0
    assert db.customers.rows[0]["name"] == "Contact 5678"
