"""One-off: top up the dev user's lead credits."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient


async def topup(email: str, amount: float) -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "whatsapp_crm")]
    user = await db.users.find_one({"email": email})
    if not user:
        print(f"No user found with email {email}")
        return
    uid = user.get("business_id") or user["_id"]
    print(f"Topping up user_id={uid} (email={email})")
    result = await db.lead_credits.find_one_and_update(
        {"user_id": uid},
        {
            "$inc": {"balance_credits": amount},
            "$setOnInsert": {
                "_id": uid,
                "user_id": uid,
                "total_spent_usd": 0.0,
                "total_runs": 0,
            },
        },
        upsert=True,
        return_document=True,
    )
    print(f"New balance: {result['balance_credits']:.1f} credits")


if __name__ == "__main__":
    asyncio.run(topup("newlife101au@gmail.com", 500.0))
