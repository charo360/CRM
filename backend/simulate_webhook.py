import requests
import json

url = "http://localhost:8000/api/webhooks/evolution"
headers = {"Content-Type": "application/json"}

payload = {
    "event": "messages.upsert",
    "instance": "test_instance",
    "data": {
        "key": {
            "remoteJid": "1234567890@s.whatsapp.net",
            "fromMe": False,
            "id": "TEST_MSG_ID"
        },
        "pushName": "Test User",
        "message": {
            "conversation": "dresses"
        },
        "messageType": "conversation"
    },
    "sender": "1234567890@s.whatsapp.net"
}

print(f"Sending webhook to {url}...")
try:
    response = requests.post(url, json=payload)
    print(f"Response Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Failed to send request: {e}")
