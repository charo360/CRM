import os
import socket
import sys
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

mongo_url = os.environ.get('MONGO_URL')
if not mongo_url:
    print("❌ MONGO_URL not found in .env")
    sys.exit(1)

# Handle mongodb+srv:// style which requires DNS seed list lookup
# For simplicity in this diagnostic, if it's srv, we might need dnspython, 
# but let's try to just parse the hostname if it's standard.
# If it's SRV, 'mongodb+srv://user:pass@cluster.mongodb.net/...'
# The actual host is slightly different but checking the cluster domain is a good start.

try:
    # Basic parsing
    if '@' in mongo_url:
        host_part = mongo_url.split('@')[1].split('/')[0]
    else:
        host_part = mongo_url.split('//')[1].split('/')[0]
    
    # Remove options
    if '?' in host_part:
        host_part = host_part.split('?')[0]
        
    print(f"Target Hostname: {host_part}")
    
    # 1. DNS Resolution
    try:
        ip = socket.gethostbyname(host_part)
        print(f"✅ DNS Resolution successful: {host_part} -> {ip}")
    except Exception as e:
        print(f"❌ DNS Resolution failed: {e}")
        # If it's an SRV record, this might fail, which is expected for direct lookup
        # But usually pinging the cluster domain works.
        pass

    # 2. TCP Connect (Port 27017)
    # Note: SRV records usually point to 27017, but let's try.
    print(f"Attempting TCP connection to {host_part}:27017...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host_part, 27017))
        if result == 0:
            print("✅ TCP Port 27017 is OPEN and reachable.")
        else:
            print(f"❌ TCP Port 27017 is BLOCKED (Error code: {result})")
        sock.close()
    except Exception as e:
        print(f"❌ TCP Connection failed with exception: {e}")

except Exception as e:
    print(f"Error parsing/testing: {e}")

try:
    print("\nChecking general internet connectivity...")
    ip = socket.gethostbyname("google.com")
    print(f"✅ Google.com resolved to {ip}")
except Exception as e:
    print(f"❌ Google.com DNS lookup failed: {e}")
