import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load env
load_dotenv(Path('.env'))
key = os.environ.get('OPENAI_API_KEY', '')
org_id = os.environ.get('OPENAI_ORG_ID', '')
project_id = os.environ.get('OPENAI_PROJECT_ID', '')

print(f"API Key: {key[:20]}...{key[-10:]}")
print(f"Org ID: {org_id if org_id else 'Not set'}")
print(f"Project ID: {project_id if project_id else 'Not set'}")

# Test with organization/project if available
try:
    client_kwargs = {'api_key': key}
    if org_id:
        client_kwargs['organization'] = org_id
    if project_id:
        client_kwargs['project'] = project_id
    
    client = OpenAI(**client_kwargs)
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{"role": "user", "content": "Say hello"}],
        max_tokens=10
    )
    print("\n✓ API Key works with these settings!")
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"\n✗ Failed: {e}")
