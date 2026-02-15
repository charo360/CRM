import asyncio
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_API_URL = os.environ.get('EVOLUTION_API_URL', 'http://localhost:8080')
EVOLUTION_API_KEY = os.environ.get('EVOLUTION_API_KEY', '')
INSTANCE_NAME = "user_366e141a_115c_4b28_8bed_362db48b2031"

async def get_url():
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{EVOLUTION_API_URL}/webhook/find/{INSTANCE_NAME}", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                print(f"FULL DATA: {data}")
                url = data.get("url") or data.get("webhook", {}).get("url")
                events = data.get("events") or data.get("webhook", {}).get("events")
                print(f"URL: {url}")
                print(f"Events: {events}")
            else:
                print(f"Error: {resp.status_code}")
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(get_url())
