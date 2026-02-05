import socket
import sys

host = "cluster0-shard-00-00.olkh678.mongodb.net"
port = 27017

print(f"Testing TCP connection to {host}:{port}...")

try:
    # 1. Resolve IP
    ip = socket.gethostbyname(host)
    print(f"✅ DNS Resolved: {host} -> {ip}")
    
    # 2. Connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    result = sock.connect_ex((ip, port))
    if result == 0:
        print("✅ TCP Port 27017 is OPEN!")
    else:
        print(f"❌ TCP Port 27017 is BLOCKED (Error code: {result})")
        print("   (10060 = Timeout, 10061 = Refused, 10013 = Permission Denied)")
    sock.close()

except Exception as e:
    print(f"❌ Error: {e}")
