"""
Setup Composio Webhooks for Gmail Real-Time Notifications.

This script:
1. Creates a webhook subscription in Composio
2. Registers GMAIL_NEW_GMAIL_MESSAGE triggers for all connected users
"""
import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

# Load environment
load_dotenv()

COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY")
COMPOSIO_API_BASE = "https://backend.composio.dev/api/v3.1"

# Your webhook URL (update this with your actual domain)
# For local testing, use ngrok: https://ngrok.com
WEBHOOK_URL = os.environ.get("COMPOSIO_WEBHOOK_URL", "https://your-domain.com/api/webhooks/composio")


async def create_webhook_subscription():
    """Create or update webhook subscription in Composio."""
    print("📡 Setting up Composio webhook subscription...\n")
    
    if not COMPOSIO_API_KEY:
        print("❌ COMPOSIO_API_KEY not found in environment")
        return None
    
    if "your-domain.com" in WEBHOOK_URL:
        print("⚠️  WARNING: Using placeholder webhook URL")
        print(f"   Current URL: {WEBHOOK_URL}")
        print("   Update COMPOSIO_WEBHOOK_URL in .env with your actual domain")
        print("   For local testing, use ngrok: https://ngrok.com\n")
    
    async with httpx.AsyncClient() as client:
        # Check if subscription already exists
        try:
            response = await client.get(
                f"{COMPOSIO_API_BASE}/webhook_subscriptions",
                headers={"X-API-Key": COMPOSIO_API_KEY}
            )
            
            if response.status_code == 200:
                existing = response.json()
                items = existing.get("items") if isinstance(existing, dict) else existing
                if items:
                    sub = items[0] if isinstance(items, list) else items
                    print(f"ℹ️  Webhook subscription already exists:")
                    print(f"   URL: {sub.get('webhook_url')}")
                    secret = sub.get('secret') or ''
                    print(f"   Secret: {secret[:20]}..." if secret else "   Secret: <not exposed by API>")
                    print("\n   To update, delete the existing subscription first")
                    return sub
        except Exception as e:
            print(f"⚠️  Could not check existing subscription: {e}")
        
        # Create new subscription
        try:
            response = await client.post(
                f"{COMPOSIO_API_BASE}/webhook_subscriptions",
                headers={
                    "X-API-Key": COMPOSIO_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "webhook_url": WEBHOOK_URL,
                    "enabled_events": [
                        "composio.trigger.message",
                        "composio.connected_account.expired",
                        "composio.trigger.disabled",
                    ],
                    "version": "V3",
                }
            )
            
            if response.status_code in [200, 201]:
                subscription = response.json()
                secret = subscription.get("secret")
                
                print("✅ Webhook subscription created!")
                print(f"   URL: {subscription.get('webhook_url')}")
                print(f"   Secret: {secret}")
                print(f"\n   ⚠️  IMPORTANT: Add this to your .env file:")
                print(f"   COMPOSIO_WEBHOOK_SECRET={secret}\n")
                
                return subscription
            else:
                print(f"❌ Failed to create subscription: {response.status_code}")
                print(f"   Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error creating subscription: {e}")
            return None


async def register_gmail_triggers():
    """Register GMAIL_NEW_GMAIL_MESSAGE trigger for all connected Gmail accounts."""
    print("\n📧 Registering Gmail triggers for connected users...\n")
    
    # Import database connection
    sys.path.insert(0, os.path.dirname(__file__))
    from motor.motor_asyncio import AsyncIOMotorClient
    
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        print("❌ MONGO_URL not found in environment")
        return
    
    client = AsyncIOMotorClient(mongo_url)
    db_name = os.environ.get("DB_NAME", "whatsapp_crm")
    db = client[db_name]
    
    # Fetch all ACTIVE Gmail connections from Composio (v3 endpoint — v1 is gone)
    gmail_accounts = []
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(
            "https://backend.composio.dev/api/v3/connected_accounts",
            headers={"X-API-Key": COMPOSIO_API_KEY},
        )
        if resp.status_code != 200:
            print(f"❌ Failed to list connected accounts: {resp.status_code} {resp.text[:200]}")
            client.close()
            return
        for item in resp.json().get("items", []):
            toolkit_slug = (item.get("toolkit") or {}).get("slug", "").lower()
            if toolkit_slug != "gmail":
                continue
            if item.get("status") != "ACTIVE":
                print(f"⏭  Skipping {item.get('id')} (status={item.get('status')})")
                continue
            gmail_accounts.append({
                "id": item.get("id"),
                "user_uuid": item.get("user_id"),
            })

    if not gmail_accounts:
        print("❌ No ACTIVE Gmail connections in Composio")
        client.close()
        return

    print(f"📧 Found {len(gmail_accounts)} ACTIVE Gmail connection(s) in Composio\n")

    # Map each Composio account back to a MongoDB user (business_id == user_uuid)
    gmail_users = []
    for acct in gmail_accounts:
        user = await db.users.find_one({"business_id": acct["user_uuid"]})
        if not user:
            user = await db.users.find_one({"_id": acct["user_uuid"]})
        if not user:
            print(f"⚠️  {acct['id']} — no MongoDB user matches Composio user_uuid={acct['user_uuid']}")
            continue
        email = user.get("email", str(user.get("_id")))
        user_id = str(user.get("business_id") or user["_id"])
        gmail_users.append((user, user_id, email, acct["id"]))
        print(f"✅ {email} → {acct['id']}")
    
    if not gmail_users:
        print("\n❌ No users with Gmail connected")
        client.close()
        return
    
    print(f"\n📧 Found {len(gmail_users)} user(s) with Gmail connected")
    print("=" * 60)
    
    # Register trigger for each user
    async with httpx.AsyncClient() as http_client:
        for user, user_id, email, connected_account_id in gmail_users:
            print(f"\n📧 Registering trigger for {email}...")
            
            try:
                response = await http_client.post(
                    f"{COMPOSIO_API_BASE}/trigger_instances/GMAIL_NEW_GMAIL_MESSAGE/upsert",
                    headers={
                        "X-API-Key": COMPOSIO_API_KEY,
                        "Content-Type": "application/json"
                    },
                    json={
                        "connected_account_id": connected_account_id,
                        "trigger_config": {}
                    }
                )
                
                if response.status_code in [200, 201, 204]:
                    print(f"   ✅ Trigger registered successfully")
                    
                    # Store connected_account_id in user document for webhook lookup
                    await db.users.update_one(
                        {"_id": user["_id"]},
                        {
                            "$set": {
                                "composio_connections.gmail.connected_account_id": connected_account_id
                            }
                        }
                    )
                else:
                    print(f"   ❌ Failed: {response.status_code}")
                    print(f"   Response: {response.text}")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
    
    client.close()
    print("\n✅ Done!")


async def main():
    print("=" * 60)
    print("Composio Webhook Setup for Gmail Real-Time Notifications")
    print("=" * 60)
    print()
    
    # Step 1: Create webhook subscription
    subscription = await create_webhook_subscription()
    
    if not subscription:
        print("\n⚠️  Webhook subscription setup incomplete")
        print("   Fix the errors above and try again")
        return
    
    # Step 2: Register triggers for all Gmail users
    await register_gmail_triggers()
    
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Add COMPOSIO_WEBHOOK_SECRET to your .env file (see above)")
    print("2. Restart your backend server")
    print("3. Send a test email to a connected Gmail account")
    print("4. Check backend logs for: [composio-webhook] Received: GMAIL_NEW_GMAIL_MESSAGE")


if __name__ == "__main__":
    asyncio.run(main())
