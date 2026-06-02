"""
One-off maintenance: purge leaked Zilo notebook/company data.

Background
----------
`rex/persistence/extractor.py` previously hardcoded two personal emails into
`user_emails` (newlife101au@gmail.com, sarcharo@gmail.com). That made every
tenant's notebook extraction treat those addresses as "self", which could seed
one person's identity/contacts into other accounts' Zilo notebooks (stored in
the `zilo_sessions` collection).

This script finds `zilo_sessions` whose persisted notebook/companies reference
the leaked identities but whose owner is NOT that person, and clears the
`notebook` + `companies` arrays so they re-extract cleanly on next load.

Usage
-----
Dry run (default — shows what would change, makes NO writes):
    python _cleanup_leaked_notebook.py

Apply the cleanup (writes to the DB):
    python _cleanup_leaked_notebook.py --apply
"""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

# Substrings that indicate leaked identity in a session's notebook/companies.
LEAKED_MARKERS = ("newlife101au", "sarcharo@gmail")


def _session_is_polluted(doc: dict, owner_email: str) -> bool:
    """True if the session contains a leaked marker that is not the owner's own."""
    blob = json.dumps(
        {
            "notebook": doc.get("notebook") or [],
            "companies": doc.get("companies") or [],
        },
        default=str,
    ).lower()

    owner = (owner_email or "").lower().strip()
    for marker in LEAKED_MARKERS:
        if marker in blob and marker not in owner:
            return True
    return False


async def main(apply_changes: bool) -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "whatsapp_crm")]

    mode = "APPLY" if apply_changes else "DRY RUN"
    print(f"[cleanup] mode={mode}")

    scanned = 0
    polluted = 0
    cleared = 0

    async for doc in db.zilo_sessions.find(
        {}, {"user_id": 1, "business_id": 1, "notebook": 1, "companies": 1}
    ):
        scanned += 1
        user_id = doc.get("user_id")

        # Resolve the owner's email to avoid wiping the legitimate owner's data.
        owner = await db.users.find_one({"_id": user_id}, {"email": 1}) or {}
        owner_email = owner.get("email", "")

        if not _session_is_polluted(doc, owner_email):
            continue

        polluted += 1
        nb = len(doc.get("notebook") or [])
        co = len(doc.get("companies") or [])
        print(
            f"[cleanup] polluted user_id={user_id} owner={owner_email or '<unknown>'} "
            f"notebook={nb} companies={co}"
        )

        if apply_changes:
            await db.zilo_sessions.update_one(
                {"user_id": user_id},
                {"$set": {"notebook": [], "companies": []}},
            )
            cleared += 1

    print(
        f"[cleanup] done — scanned={scanned} polluted={polluted} "
        f"cleared={cleared} (apply={apply_changes})"
    )
    if not apply_changes and polluted:
        print("[cleanup] re-run with --apply to clear the listed sessions.")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(main(apply))
