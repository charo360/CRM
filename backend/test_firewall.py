import socket
import sys

def test_port(host, port, name):
    print(f"\n--- Testing {name} ({host}:{port}) ---")
    try:
        ip = socket.gethostbyname(host)
        print(f"✅ DNS Resolved: {ip}")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((ip, port))
        if result == 0:
            print(f"✅ Connection SUCCESSFUL")
            return True
        else:
            print(f"❌ Connection BLOCKED (Error: {result})")
            return False
        sock.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

print("Diagnostic: Comparing Google (Port 80) vs MongoDB (Port 27017)")

# 1. Control: Google.com on Port 80 (Should almost always work)
google_ok = test_port("google.com", 80, "Google HTTP")

# 2. Target: MongoDB Shard (from previous nslookup)
# Usage: check if we can even reach the shard
mongo_host = "cluster0-shard-00-00.olkh678.mongodb.net"
mongo_ok = test_port(mongo_host, 27017, "MongoDB Atlas")

print("\n--- CONCLUSION ---")
if google_ok and not mongo_ok:
    print("Likely Scenario: Network Firewall is blocking 'non-standard' ports like 27017.")
    print("Use a defined 'Business/Home' network, or try a mobile hotspot.")
elif not google_ok:
    print("Likely Scenario: Local application blocking. Check Windows Firewall for Python.")
else:
    print("Result is ambiguous or both worked.")
