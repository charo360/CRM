import os
from pathlib import Path
from dotenv import load_dotenv
import requests

# Load env
load_dotenv(Path('.env'))
key = os.environ.get('OPENAI_API_KEY', '')

print(f"Testing API key: {key[:20]}...{key[-10:]}")

# Test with raw HTTP request
headers = {
    'Authorization': f'Bearer {key}',
    'Content-Type': 'application/json'
}

data = {
    'model': 'gpt-4o-mini',
    'messages': [{'role': 'user', 'content': 'Say hello'}],
    'max_tokens': 10
}

try:
    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers=headers,
        json=data,
        timeout=30
    )
    
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        print("\n✓ API Key is VALID and working!")
    else:
        print("\n✗ API Key failed")
        
except Exception as e:
    print(f"\n✗ Request failed: {e}")
