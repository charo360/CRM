"""
Manual script to register Gmail watch for a user.
Run this once to set up push notifications.
"""
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

async def main():
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Connect to MongoDB (same as server.py)
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        print("❌ MONGO_URL not found in environment")
        print("Make sure .env file has MONGO_URL set")
        return
    
    client = AsyncIOMotorClient(mongo_url)
    db_name = os.environ.get("DB_NAME", "whatsapp_crm")
    db = client[db_name]
    
    # Get all users
    all_users = await db.users.find({}).to_list(length=1000)
    
    if not all_users:
        print("❌ No users found in database")
        return
    
    print(f"Checking {len(all_users)} user(s) for Gmail connections...\n")
    
    # Check each user via Composio API
    from composio_service import get_connection_status
    from gmail_watch_manager import register_gmail_watch
    
    gmail_users = []
    
    for user in all_users:
        user_id = str(user.get("business_id") or user["_id"])
        email = user.get("email", user_id)
        
        try:
            # Check if Gmail is connected via Composio API
            status = await get_connection_status(user_id, "gmail")
            
            if status.get("connected"):
                gmail_users.append(user)
                print(f"✅ {email} - Gmail connected")
            else:
                print(f"⚪ {email} - No Gmail connection")
        except Exception as e:
            print(f"⚠️  {email} - Error checking status: {e}")
    
    if not gmail_users:
        print("\n❌ No users found with active Gmail connections")
        print("Make sure you've connected Gmail via Composio first")
        client.close()
        return
    
    print(f"\n📧 Found {len(gmail_users)} user(s) with Gmail connected")
    print("=" * 60)
    
    # Register watch for each user with Gmail
    for user in gmail_users:
        user_id = str(user.get("business_id") or user["_id"])
        email = user.get("email", user_id)
        
        print(f"\n📧 Registering Gmail watch for {email}...")
        
        try:
            result = await register_gmail_watch(user_id, db)
            
            if "error" in result:
                print(f"❌ Failed: {result['error']}")
            else:
                print(f"✅ Success!")
                print(f"   History ID: {result.get('historyId')}")
                print(f"   Expires: {result.get('expiration')}")
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    client.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    asyncio.run(main())
