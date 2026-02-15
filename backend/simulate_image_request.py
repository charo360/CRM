
import requests
import json
import time

url = "http://localhost:8000/api/webhooks/evolution"

payload = {
    "event": "messages.upsert",
    "instance": "paya_motors",
    "data": {
        "key": {
            "remoteJid": "1234567890@s.whatsapp.net",
            "fromMe": False,
            "id": "TEST_MSG_IMG_002"
        },
        "pushName": "Test User",
        "message": {
            "conversation": "Which AI model are you?"
        },
        "messageType": "conversation"
    },
    "sender": "1234567890@s.whatsapp.net"
}

print(f"Sending webhook to {url}...")
try:
    response = requests.post(url, json=payload)
    print(f"Response: {response.status_code} - {response.text}")
except Exception as e:
    print(f"Failed to send webhook: {e}")
