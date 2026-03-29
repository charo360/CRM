import sys

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Apply all the replacements
    content = content.replace(
        'currency = user.get("settings", {}).get("currency", "USD")',
        'currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")'
    )
    content = content.replace(
        '_currency = user.get("settings", {}).get("currency", "USD")',
        '_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")'
    )
    content = content.replace(
        'currency = user.get("settings", {}).get("currency", "KES")',
        'currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")'
    )
    content = content.replace(
        'currency = user.get("settings", {}).get("currency", "USD") if user else "USD"',
        'currency = (user.get("currency") or user.get("settings", {}).get("currency", "USD")) if user else "USD"'
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_file("server.py")
fix_file("whatsapp_service.py")
print("Fixed!")
