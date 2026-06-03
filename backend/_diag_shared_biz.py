"""Diagnostic: explain accounts whose business_id != their own _id.

Read-only. Determines if a foreign business_id came from a team invite
(by design) or is an unexplained leak (bug).
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "whatsapp_crm")]

    users = await db.users.find(
        {}, {"_id": 1, "email": 1, "business_id": 1, "role": 1, "auth_provider": 1, "password_hash": 1}
    ).to_list(500)

    print("[diag] accounts where business_id != _id:\n")
    for u in users:
        uid = u["_id"]
        bid = u.get("business_id")
        if not bid or bid == uid:
            continue

        owner = await db.users.find_one({"_id": bid}, {"email": 1}) or {}
        # Was this user explicitly invited to that business?
        tm = await db.team_members.find_one({
            "business_id": bid,
            "$or": [{"user_id": uid}, {"email": u.get("email")}],
        })

        print(f"user={u.get('email','<no-email>')} _id={uid}")
        print(f"    role={u.get('role')} auth={u.get('auth_provider')} has_password={bool(u.get('password_hash'))}")
        print(f"    business_id={bid}  -> owner={owner.get('email','<unknown/missing>')}")
        if tm:
            print(f"    INVITE FOUND: team_member _id={tm['_id']} status={tm.get('status')} invited_by={tm.get('invited_by')}")
        else:
            print(f"    *** NO team_member invite record — UNEXPLAINED foreign business_id (likely bug) ***")
        print()


if __name__ == "__main__":
    asyncio.run(main())
