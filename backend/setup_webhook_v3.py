"""
Set webhook URL using v3 API directly.
"""
import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY")
WEBHOOK_URL = "https://crm-1-pnfo.onrender.com/api/webhooks/composio"


async def setup_webhook():
    """Set webhook URL using v3.1 API."""
    print("Setting webhook URL via v3.1 API...\n")
    
    async with httpx.AsyncClient() as client:
        # Create webhook subscription
        response = await client.post(
            "https://backend.composio.dev/api/v3.1/webhook_subscriptions",
            headers={
                "X-API-Key": COMPOSIO_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "webhook_url": WEBHOOK_URL,
                "enabled_events": ["*"],  # Try wildcard
                "version": "V3"
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}\n")
        
        if response.status_code in [200, 201]:
            data = response.json()
            secret = data.get("secret")
            print(f"✅ Webhook configured successfully!")
            print(f"   URL: {WEBHOOK_URL}")
            print(f"   Secret: {secret}")
            print(f"\n⚠️  IMPORTANT: Add to your .env file:")
            print(f"   COMPOSIO_WEBHOOK_SECRET={secret}")
        elif response.status_code == 409:
            print("ℹ️  Webhook subscription already exists")
            print("   To update, delete the existing one first")
        else:
            print(f"❌ Failed to set webhook")


if __name__ == "__main__":
    asyncio.run(setup_webhook())
