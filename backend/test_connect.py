from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

load_dotenv()

# Construct URI from .env to ensure we use the saved password
# Or use the one from .env directly since we know it matches the structure
uri = os.environ.get('MONGO_URL')

print(f"Testing connection to: {uri.split('@')[1] if '@' in uri else '...'} ...")

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=5000)

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"Connection failed: {e}")
