"""
List all connected accounts in Composio to debug connection IDs.
"""
import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY")
COMPOSIO_API_BASE = "https://backend.composio.dev/api/v3.1"


async def list_all_connected_accounts():
    """List all connected accounts in Composio."""
    if not COMPOSIO_API_KEY:
        print("❌ COMPOSIO_API_KEY not found")
        return
    
    async with httpx.AsyncClient() as client:
        # List all connected accounts (no user filter)
        # Try v1 endpoint since v3.1 might not have this
        response = await client.get(
            "https://backend.composio.dev/api/v1/connectedAccounts",
            headers={"X-API-Key": COMPOSIO_API_KEY}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch accounts: {response.status_code}")
            print(response.text)
            return
        
        data = response.json()
        items = data.get("items", [])
        
        print(f"Found {len(items)} connected account(s):\n")
        
        for item in items:
            account_id = item.get("id")
            app_name = item.get("appName")
            status = item.get("status")
            user_uuid = item.get("userUuid") or item.get("clientUniqueUserId")
            
            print(f"Account ID: {account_id}")
            print(f"  App: {app_name}")
            print(f"  Status: {status}")
            print(f"  User UUID: {user_uuid}")
            print()


if __name__ == "__main__":
    asyncio.run(list_all_connected_accounts())
