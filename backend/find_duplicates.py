
filename = "server.py"
print(f"Scanning {filename} for 'def health_check'...")
try:
    with open(filename, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if "def health_check" in line:
                print(f"Line {i}: {line.strip()}")
except Exception as e:
    print(f"Error: {e}")
