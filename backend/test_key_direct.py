import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load env
load_dotenv(Path('.env'))
key = os.environ.get('OPENAI_API_KEY', '')

print(f"Key length: {len(key)}")
print(f"Key starts: {key[:15]}")
print(f"Key ends: {key[-15:]}")

# Test with OpenAI directly
try:
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{"role": "user", "content": "Say hello"}],
        max_tokens=10
    )
    print("\n✓ API Key works!")
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"\n✗ API Key failed: {e}")
