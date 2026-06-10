"""
Set up Composio webhook via API (bypass dashboard restrictions).
"""
import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY")
WEBHOOK_URL = "https://crm-1-pnfo.onrender.com/api/webhooks/composio"


async def setup_webhook():
    """Configure webhook using Composio API."""
    print("=" * 60)
    print("Composio Webhook Setup via API")
    print("=" * 60)
    print()
    
    if not COMPOSIO_API_KEY:
        print("❌ COMPOSIO_API_KEY not found in .env")
        return
    
    print(f"API Key: {COMPOSIO_API_KEY[:10]}...")
    print(f"Webhook URL: {WEBHOOK_URL}")
    print()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # First, check if webhook already exists
        print("Checking existing webhook subscriptions...")
        try:
            response = await client.get(
                "https://backend.composio.dev/api/v1/webhooks",
                headers={"X-API-Key": COMPOSIO_API_KEY}
            )
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response: {data}")
                
                if data and isinstance(data, dict):
                    existing_url = data.get("url") or data.get("webhook_url")
                    if existing_url:
                        print(f"\n✅ Webhook already configured!")
                        print(f"   URL: {existing_url}")
                        print(f"   Secret: {data.get('secret', 'N/A')[:20]}...")
                        
                        if data.get('secret'):
                            print(f"\n⚠️  Add this to Render environment:")
                            print(f"   COMPOSIO_WEBHOOK_SECRET={data.get('secret')}")
                        return
            
        except Exception as e:
            print(f"⚠️  Check failed: {e}")
        
        print()
        
        # Try to create webhook using v1 API
        print("Creating webhook subscription (v1 API)...")
        try:
            response = await client.post(
                "https://backend.composio.dev/api/v1/webhooks",
                headers={
                    "X-API-Key": COMPOSIO_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "url": WEBHOOK_URL
                }
            )
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                secret = data.get("secret")
                
                print(f"\n✅ Webhook created successfully!")
                print(f"   URL: {WEBHOOK_URL}")
                print(f"   Secret: {secret}")
                print(f"\n⚠️  IMPORTANT: Add to Render environment:")
                print(f"   COMPOSIO_WEBHOOK_SECRET={secret}")
                
            elif response.status_code == 409:
                print("\nℹ️  Webhook already exists")
                
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(setup_webhook())
