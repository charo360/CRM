"""
Read-only diagnostic for the Composio Gmail webhook pipeline.

Tells you:
  1. What webhook URL Composio is configured to deliver to
  2. Which Gmail connected accounts exist and their status
  3. Which trigger instances are registered and whether they're enabled

Run: python diagnose_composio_webhook.py
"""
import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("COMPOSIO_API_KEY")
V3 = "https://backend.composio.dev/api/v3"
V31 = "https://backend.composio.dev/api/v3.1"


async def main():
    if not API_KEY:
        print("COMPOSIO_API_KEY missing from .env")
        return

    headers = {"X-API-Key": API_KEY}

    async with httpx.AsyncClient(timeout=30, headers=headers) as http:
        print("=" * 70)
        print("1. WEBHOOK SUBSCRIPTIONS")
        print("=" * 70)
        r = await http.get(f"{V31}/webhook_subscriptions")
        print(f"HTTP {r.status_code}")
        if r.status_code == 200:
            items = r.json().get("items") or []
            if not items:
                print("  (none) — no webhook subscription exists. Composio has no URL to call.")
            for sub in items:
                print(f"  id={sub.get('id')}")
                print(f"  url={sub.get('webhook_url')}")
                print(f"  events={sub.get('enabled_events')}")
                print(f"  version={sub.get('version')}")
                print()
        else:
            print(r.text[:500])

        print("=" * 70)
        print("2. GMAIL CONNECTED ACCOUNTS")
        print("=" * 70)
        r = await http.get(f"{V3}/connected_accounts")
        gmail_accounts = []
        if r.status_code == 200:
            for acct in r.json().get("items", []):
                toolkit = (acct.get("toolkit") or {}).get("slug", "").lower()
                if toolkit != "gmail":
                    continue
                gmail_accounts.append(acct)
                print(f"  id={acct.get('id')}")
                print(f"  status={acct.get('status')}")
                print(f"  user_id={acct.get('user_id')}")
                print()
        else:
            print(f"HTTP {r.status_code}: {r.text[:300]}")

        if not gmail_accounts:
            print("  No Gmail connected accounts found.")
            return

        print("=" * 70)
        print("3. TRIGGER INSTANCES PER GMAIL ACCOUNT")
        print("=" * 70)
        for acct in gmail_accounts:
            acct_id = acct.get("id")
            print(f"\n--- {acct_id} ---")
            # Try the trigger_instances list endpoint
            r = await http.get(
                f"{V31}/trigger_instances",
                params={"connected_account_id": acct_id},
            )
            if r.status_code == 200:
                items = r.json().get("items") or r.json().get("data") or []
                if not items:
                    print("  No triggers registered. <-- LIKELY THE PROBLEM if account is ACTIVE")
                for ti in items:
                    print(f"  trigger={ti.get('trigger_name') or ti.get('triggerName')}")
                    print(f"  state={ti.get('state') or ti.get('status')}")
                    print(f"  id={ti.get('id')}")
            else:
                print(f"  HTTP {r.status_code}: {r.text[:300]}")


if __name__ == "__main__":
    asyncio.run(main())
