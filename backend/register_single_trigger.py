"""
Register Gmail trigger for the single active account.
"""
import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY")
WEBHOOK_URL = "https://crm-1-pnfo.onrender.com/api/webhooks/composio"

# The one active Gmail account
CONNECTED_ACCOUNT_ID = "deb4a5f0-1e3d-4a1d-a08b-e86325dd36d8"
USER_UUID = "4eccd62d-a032-496d-8ba1-819c0b5f1e69"


async def register_trigger():
    """Register GMAIL_NEW_GMAIL_MESSAGE trigger."""
    print(f"Registering trigger for account: {CONNECTED_ACCOUNT_ID}\n")
    
    async with httpx.AsyncClient() as client:
        # Try v3.1 endpoint
        print("Trying v3.1 API...")
        response = await client.post(
            f"https://backend.composio.dev/api/v3.1/trigger_instances/GMAIL_NEW_GMAIL_MESSAGE/upsert",
            headers={
                "X-API-Key": COMPOSIO_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "connected_account_id": CONNECTED_ACCOUNT_ID,
                "trigger_config": {}
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}\n")
        
        if response.status_code not in [200, 201, 204]:
            # Try v1 endpoint
            print("Trying v1 API...")
            response = await client.post(
                f"https://backend.composio.dev/api/v1/triggers/enable",
                headers={
                    "X-API-Key": COMPOSIO_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "connectedAccountId": CONNECTED_ACCOUNT_ID,
                    "triggerName": "GMAIL_NEW_GMAIL_MESSAGE"
                }
            )
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")


if __name__ == "__main__":
    asyncio.run(register_trigger())
