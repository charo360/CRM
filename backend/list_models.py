
import os
import sys
from openai import OpenAI
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

api_key = os.environ.get('OPENAI_API_KEY')
if not api_key:
    print("No OpenAI API Key found")
    sys.exit(1)

client = OpenAI(api_key=api_key)

print("Listing available OpenAI models...")
try:
    models = client.models.list()
    for model in models.data:
        print(model.id)
except Exception as e:
    print(f"Error listing models: {e}")
