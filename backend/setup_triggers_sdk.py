"""
Setup Composio triggers using the official SDK.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY")
WEBHOOK_URL = "https://crm-1-pnfo.onrender.com/api/webhooks/composio"


async def setup_composio_triggers():
    """Setup webhook subscription and triggers using Composio SDK."""
    from composio import Composio
    
    print("=" * 60)
    print("Setting up Composio Triggers via SDK")
    print("=" * 60)
    print()
    
    # Initialize Composio client
    client = Composio(api_key=COMPOSIO_API_KEY)
    
    # Step 1: Get all connected accounts
    print("📋 Fetching connected accounts...\n")
    
    try:
        connected_accounts = client.connected_accounts.get()
        
        gmail_accounts = [
            acc for acc in connected_accounts 
            if acc.appName.lower() == "gmail" and acc.status == "ACTIVE"
        ]
        
        print(f"Found {len(gmail_accounts)} active Gmail account(s):\n")
        
        for acc in gmail_accounts:
            print(f"  Account ID: {acc.id}")
            print(f"  User: {acc.clientUniqueUserId}")
            print(f"  Status: {acc.status}")
            print()
        
        if not gmail_accounts:
            print("❌ No active Gmail accounts found")
            return
        
    except Exception as e:
        print(f"❌ Error fetching accounts: {e}")
        return
    
    # Step 2: Set webhook URL
    print("📡 Setting webhook URL...\n")
    
    try:
        callback = client.triggers.callbacks.set(url=WEBHOOK_URL)
        print(f"✅ Webhook URL configured: {WEBHOOK_URL}")
        print(f"   Callback ID: {callback.id if hasattr(callback, 'id') else 'N/A'}")
        print()
    except Exception as e:
        print(f"⚠️  Webhook setup error: {e}")
        import traceback
        traceback.print_exc()
        print()
    
    # Step 3: Enable triggers for each Gmail account
    print("📧 Enabling Gmail triggers...\n")
    
    for acc in gmail_accounts:
        try:
            print(f"Enabling trigger for {acc.clientUniqueUserId}...")
            
            # Enable the trigger using correct SDK signature
            trigger = client.triggers.enable(
                name="GMAIL_NEW_GMAIL_MESSAGE",
                connected_account_id=acc.id,
                config={}
            )
            
            print(f"  ✅ Trigger enabled!")
            print(f"     Trigger data: {trigger}")
            print()
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    print("=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Send a test email to your connected Gmail account")
    print("2. Check backend logs for webhook events")
    print("3. Verify email appears in CRM within seconds")


if __name__ == "__main__":
    asyncio.run(setup_composio_triggers())
