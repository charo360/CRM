"""
One-off cleanup script for malformed / duplicate phone numbers in the customers collection.

Run dry-run (shows what would change):
    python backend/cleanup_phone_numbers.py

Apply changes:
    python backend/cleanup_phone_numbers.py --apply

Requires MONGO_URL and DB_NAME (or a backend/.env file with them).
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=True)

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "whatsapp_crm")

# Collections that are known to reference a customer by _id
REFERENCE_COLLECTIONS = [
    "messages",
    "orders",
    "conversation_assignments",
    "pending_classifications",
    "customer_analysis",
    "follow_ups",
    "appointments",
    "quotes",
    "invoices",
    "payments",
]


def sanitize_phone(phone: str) -> str:
    """Keep digits and a leading + only."""
    if not phone:
        return ""
    phone = phone.strip()
    digits = re.sub(r"[^\d]", "", phone)
    if phone.startswith("+") and digits:
        return "+" + digits
    return digits


def core_digits(phone: str) -> str:
    """Digits only, used for grouping duplicates."""
    return re.sub(r"[^\d]", "", phone or "")


def is_valid(phone: str) -> bool:
    digits = core_digits(phone)
    return 6 <= len(digits) <= 15


def connect() -> MongoClient:
    if not MONGO_URL:
        print("[ERROR] MONGO_URL is not set. Set it in backend/.env or the environment.")
        sys.exit(1)
    return MongoClient(MONGO_URL, serverSelectionTimeoutMS=10_000)


def choose_canonical(group, msg_counts, order_counts):
    """Pick the best customer record to keep from a duplicate group."""

    def score(doc):
        cid = doc["_id"]
        msgs = msg_counts.get(cid, 0)
        orders = order_counts.get(cid, 0)
        spent = doc.get("total_spent", 0) or 0
        created = doc.get("created_at") or datetime.min.replace(tzinfo=timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (
            msgs + orders,
            spent,
            created,
            doc.get("is_customer", False),
            str(cid),
        )

    return max(group, key=score)


def _count_map(collection, field):
    """Return a dict mapping customer_id -> count for a collection."""
    pipeline = [
        {"$match": {field: {"$exists": True}}},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
    ]
    return {doc["_id"]: doc["count"] for doc in collection.aggregate(pipeline)}


def main():
    parser = argparse.ArgumentParser(description="Clean up malformed and duplicate customer phone numbers")
    parser.add_argument("--apply", action="store_true", help="Actually write changes to the database")
    parser.add_argument("--delete-invalid", action="store_true", help="Delete customers whose phone number is invalid")
    args = parser.parse_args()

    client = connect()
    db = client[DB_NAME]
    customers_col = db["customers"]

    print(f"Connected to {DB_NAME}. {'APPLYING' if args.apply else 'DRY RUN'} changes...")

    total = customers_col.count_documents({})
    print(f"Scanning {total} customer records...\n")

    # Count references once per customer for canonical selection (read-only)
    print("Counting references...")
    msg_counts = _count_map(db["messages"], "customer_id")
    order_counts = _count_map(db["orders"], "customer_id")

    # Pass 1: normalize/format phones and identify invalid records
    formatted = 0
    invalid = []
    for doc in customers_col.find({}):
        raw = doc.get("phone_number") or ""
        clean = sanitize_phone(raw)
        if clean != raw:
            formatted += 1
            print(f"  FORMAT: {doc.get('name')} {raw!r} -> {clean!r}")
            if args.apply:
                customers_col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"phone_number": clean or None}},
                )
        if not is_valid(clean):
            invalid.append(doc)

    # Pass 2: merge/delete duplicate phone numbers per business
    duplicates = defaultdict(list)
    for doc in customers_col.find({}):
        phone = doc.get("phone_number") or ""
        if is_valid(phone):
            duplicates[(doc.get("user_id"), core_digits(phone))].append(doc)

    merged = 0
    deleted = 0
    for (user_id, digits), group in duplicates.items():
        if len(group) < 2:
            continue
        canonical = choose_canonical(group, msg_counts, order_counts)
        print(f"\nDUPLICATES for {user_id} / {digits}: keeping {canonical['_id']}")
        for other in group:
            if other["_id"] == canonical["_id"]:
                continue
            print(f"  -> merging {other['_id']} ({other.get('name')}) into canonical")
            if args.apply:
                # Merge tags / notes / profile picture where canonical is missing
                updates = {}
                other_tags = set(other.get("tags") or [])
                canonical_tags = set(canonical.get("tags") or [])
                merged_tags = list(canonical_tags | other_tags)
                if merged_tags != list(canonical_tags):
                    updates["tags"] = merged_tags
                other_notes = (other.get("notes") or "").strip()
                canonical_notes = (canonical.get("notes") or "").strip()
                if other_notes and not canonical_notes:
                    updates["notes"] = other_notes
                elif other_notes and canonical_notes and other_notes not in canonical_notes:
                    updates["notes"] = f"{canonical_notes}\n\n{other_notes}"
                if other.get("profile_picture") and not canonical.get("profile_picture"):
                    updates["profile_picture"] = other["profile_picture"]
                if updates:
                    customers_col.update_one({"_id": canonical["_id"]}, {"$set": updates})

                # Reassign references
                for col_name in REFERENCE_COLLECTIONS:
                    if col_name in db.list_collection_names():
                        db[col_name].update_many(
                            {"customer_id": other["_id"]},
                            {"$set": {"customer_id": canonical["_id"]}},
                        )

                customers_col.delete_one({"_id": other["_id"]})
            deleted += 1
        merged += 1

    # Pass 3: handle invalid phone numbers
    removed_invalid = 0
    if invalid:
        print(f"\nINVALID PHONE NUMBERS ({len(invalid)}):")
        for doc in invalid:
            phone = doc.get("phone_number")
            print(f"  {doc.get('user_id')} / {doc['_id']} ({doc.get('name')}): {phone!r}")
            if args.apply:
                if args.delete_invalid:
                    customers_col.delete_one({"_id": doc["_id"]})
                    removed_invalid += 1
                else:
                    customers_col.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {"phone_number": None},
                            "$addToSet": {"tags": "InvalidPhone"},
                        },
                    )

    # Cleanup helper fields
    if args.apply:
        customers_col.update_many({}, {"$unset": {"_cleanup_msg_count": 1, "_cleanup_order_count": 1}})

    print(f"\nSummary:")
    print(f"  Total scanned:   {total}")
    print(f"  Reformatted:     {formatted}")
    print(f"  Duplicate sets:  {merged}")
    print(f"  Duplicates removed: {deleted}")
    print(f"  Invalid records: {len(invalid)}")
    if args.delete_invalid and args.apply:
        print(f"  Invalid deleted: {removed_invalid}")
    elif invalid and args.apply:
        print(f"  Invalid records had phone_number set to None and tagged 'InvalidPhone'.")

    print("\nDone." if args.apply else "\nThis was a dry run. Use --apply to execute changes.")


if __name__ == "__main__":
    main()
