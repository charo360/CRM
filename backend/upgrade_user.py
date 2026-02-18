import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# Load env
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

async def upgrade_user():
    mongo_url = os.environ.get('MONGO_URL')
    if not mongo_url:
        print("Error: MONGO_URL not found in .env")
        return

    try:
        client = AsyncIOMotorClient(mongo_url)
        db_name = os.environ.get('DB_NAME', 'whatsapp_crm')
        db = client[db_name]
        
        # Get the first user
        user = await db.users.find_one()
        
        if not user:
            print("No users found to upgrade.")
            return

        user_id = user['_id']
        phone = user.get('phone_number', 'Unknown')
        
        print(f"Upgrading user: {phone} (ID: {user_id})")
        print(f"Current Plan: {user.get('subscription_plan')}, Active: {user.get('subscription_active')}")
        
        # Update to Pro
        result = await db.users.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "subscription_plan": "pro",
                    "subscription_active": True,
                    "subscription_date": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            print("\nSUCCESS: User upgraded to PRO plan!")
            
            # Verify
            updated_user = await db.users.find_one({"_id": user_id})
            print(f"New Plan: {updated_user.get('subscription_plan')}")
            print(f"Active: {updated_user.get('subscription_active')}")
        else:
            print("\nNo changes made (User might already be on PRO).")
            
    except Exception as e:
        print(f"Error upgrading user: {e}")

if __name__ == "__main__":
    asyncio.run(upgrade_user())
