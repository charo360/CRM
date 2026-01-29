import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Force reload env
load_dotenv(Path('.env'), override=True)
key = os.environ.get('OPENAI_API_KEY', '')

print(f"Testing key ending in: {key[-10:]}")
print(f"Key length: {len(key)}")

# Test with OpenAI
try:
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{"role": "user", "content": "Say hello"}],
        max_tokens=10
    )
    print("\n✓ API Key WORKS!")
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"\n✗ API Key failed: {e}")
