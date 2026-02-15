import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_API_URL = os.environ.get('EVOLUTION_API_URL', 'http://localhost:8080')
EVOLUTION_API_KEY = os.environ.get('EVOLUTION_API_KEY', '')
INSTANCE_NAME = "user_366e141a_115c_4b28_8bed_362db48b2031"
# Use the detected LAN IP
WEBHOOK_URL = "http://10.0.0.139:8000/api/webhooks/evolution"

async def fix_webhook():
    print(f"Setting Webhook for {INSTANCE_NAME} to {WEBHOOK_URL}...")
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "webhook": {
            "enabled": True,
            "url": WEBHOOK_URL,
            "webhookByEvents": False,
            "webhookBase64": False,
            "events": [
                "MESSAGES_UPSERT",
                "MESSAGES_UPDATE",
                "CONNECTION_UPDATE",
                "CHATS_SET",
                "MESSAGES_SET",
                "CONTACTS_SET",
                "CONTACTS_UPSERT",
                "CONTACTS_UPDATE",
                "GROUPS_UPSERT",
                "LABELS_EDIT",
                "LABELS_ASSOCIATION"
            ]
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{EVOLUTION_API_URL}/webhook/set/{INSTANCE_NAME}",
                json=payload,
                headers=headers
            )
            print(f"Response: {resp.status_code} {resp.text}")
            
            # Verify
            resp2 = await client.get(f"{EVOLUTION_API_URL}/webhook/find/{INSTANCE_NAME}", headers=headers)
            print(f"Verified Config: {resp2.text}")
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(fix_webhook())
