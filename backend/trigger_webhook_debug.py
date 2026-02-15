
import asyncio
import httpx

WEBHOOK_URL = "http://localhost:8000/api/webhooks/evolution"

async def trigger():
    payload = {
        "event": "messages.upsert",
        "instance": "test_instance",
        "data": {
            "key": {
                "remoteJid": "1234567890@s.whatsapp.net",
                "fromMe": False,
                "id": "debug_msg_001"
            },
            "pushName": "Debug User",
            "message": {
                "conversation": "Hello bot"
            },
            "messageType": "conversation"
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            print(f"Sending webhook to {WEBHOOK_URL}...")
            resp = await client.post(WEBHOOK_URL, json=payload, headers={"apikey": "crm-evolution-key-2024"})
            print(f"Response: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(trigger())
