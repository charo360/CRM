#!/usr/bin/env python3
"""
Smoke-test Bird AccessKey: GET /me (auth), GET channels (needs BIRD_WORKSPACE_ID).

Usage (from CRM/backend):
  python bird_smoke_test.py

Requires in .env / .env.local:
  BIRD_API_KEY
  BIRD_WORKSPACE_ID  — optional; if set, also lists channels for that workspace.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)


def main() -> int:
    key = (os.environ.get("BIRD_API_KEY") or "").strip()
    if not key:
        print("FAIL: BIRD_API_KEY is not set")
        return 2

    import urllib.error
    import urllib.request

    def get(path: str) -> tuple[int, str]:
        url = f"https://api.bird.com{path}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"AccessKey {key}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")

    s1, body1 = get("/me")
    print(f"GET /me -> HTTP {s1}")
    if s1 == 403:
        print("OK: Access key is accepted (403 = authenticated; /me is not allowed for this key type).")
    elif s1 == 200:
        print(json.dumps(json.loads(body1), indent=2)[:1200])
    else:
        print(body1[:500])
        return 1

    ws = (os.environ.get("BIRD_WORKSPACE_ID") or "").strip()
    if not ws:
        print("Skip channels list: set BIRD_WORKSPACE_ID to test GET /workspaces/{id}/channels")
        return 0

    s2, body2 = get(f"/workspaces/{ws}/channels?limit=5")
    print(f"GET /workspaces/.../channels -> HTTP {s2}")
    try:
        data = json.loads(body2)
        print("results:", len(data.get("results") or data.get("items") or []))
        print(json.dumps(data, indent=2)[:2000])
    except json.JSONDecodeError:
        print(body2[:800])
    return 0 if s2 == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
