"""
Billing Integration Check Script
Run with: python billing_check.py
Tests all /subscription/ endpoints against the running backend.
Set BACKEND_URL and AUTH_TOKEN before running.
"""
import asyncio
import json
import httpx
import os

BACKEND_URL = os.environ.get("BACKEND_URL", "https://crm-1-pnfo.onrender.com")
AUTH_TOKEN  = os.environ.get("AUTH_TOKEN", "")   # paste your JWT here or set env var

HEADERS: dict = {"Content-Type": "application/json"}
if AUTH_TOKEN:
    HEADERS["Authorization"] = f"Bearer {AUTH_TOKEN}"

PASS = "  [PASS]"
FAIL = "  [FAIL]"
INFO = "  [INFO]"


async def check(label: str, coro):
    try:
        result = await coro
        print(f"{PASS} {label}")
        return result
    except AssertionError as e:
        print(f"{FAIL} {label} — {e}")
        return None
    except Exception as e:
        print(f"{FAIL} {label} — unexpected error: {e}")
        return None


async def main():
    if not AUTH_TOKEN:
        print("[WARN] AUTH_TOKEN not set — authenticated endpoints will return 401")
        print("       Set it with:  $env:AUTH_TOKEN='<your_jwt>'  (PowerShell)")
        print()

    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=20) as client:

        print("=" * 60)
        print("  BILLING INTEGRATION CHECK")
        print(f"  Backend: {BACKEND_URL}")
        print("=" * 60)

        # ── 1. Plans endpoint ──────────────────────────────────────────
        print("\n[1] GET /api/subscription/plans")
        async def _plans():
            r = await client.get("/api/subscription/plans", headers=HEADERS)
            assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
            data = r.json()
            assert isinstance(data, list), "Expected list"
            assert len(data) == 3, f"Expected 3 plans, got {len(data)}"
            ids = [p["id"] for p in data]
            assert ids == ["starter", "standard", "pro"], f"Unexpected IDs: {ids}"
            print(f"{INFO}   Plans: " + ", ".join(
                f"{p['id']}={p['currency']}{p['amount']}" for p in data
            ))
            return data

        plans = await check("Plans returned (starter/standard/pro)", _plans())

        # ── 2. Subscription status ─────────────────────────────────────
        print("\n[2] GET /api/subscription/status")
        async def _status():
            r = await client.get("/api/subscription/status", headers=HEADERS)
            assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
            data = r.json()
            assert "subscription_plan" in data, "Missing subscription_plan"
            assert "subscription_active" in data, "Missing subscription_active"
            assert "limits" in data, "Missing limits"
            print(f"{INFO}   Plan={data['subscription_plan']}, Active={data['subscription_active']}")
            print(f"{INFO}   Limits keys: {list(data['limits'].keys())}")
            return data

        status = await check("Status endpoint returns correct fields", _status())

        # ── 3. Credit bundles ──────────────────────────────────────────
        print("\n[3] GET /api/subscription/credit-bundles")
        async def _bundles():
            r = await client.get("/api/subscription/credit-bundles", headers=HEADERS)
            assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
            data = r.json()
            assert "bundles" in data or isinstance(data, (list, dict)), "Unexpected format"
            print(f"{INFO}   Bundles: {json.dumps(data)[:120]}")
            return data

        await check("Credit bundles returned", _bundles())

        # ── 4. Verify purchase (mock — expects validation, not activation) ──
        print("\n[4] POST /api/subscription/verify-purchase (mock token)")
        async def _verify_mock():
            payload = {
                "plan_id": "starter",
                "purchase_token": "mock_token_for_testing_only",
                "platform": "android",
            }
            r = await client.post(
                "/api/subscription/verify-purchase",
                json=payload,
                headers=HEADERS,
            )
            # With a mock token and the service account present, Google will reject it.
            # Without the service account, server returns {"status":"success"} (no_server_config).
            # Both 200 and 400 are acceptable — 401/422/500 are bugs.
            assert r.status_code not in (401, 422, 500), \
                f"Unexpected HTTP {r.status_code}: {r.text[:200]}"
            print(f"{INFO}   Response {r.status_code}: {r.text[:120]}")
            return r.json()

        await check("Verify endpoint reachable (mock token — no server crash)", _verify_mock())

        # ── 5. Restore purchases (empty) ───────────────────────────────
        print("\n[5] POST /api/subscription/restore-purchases (empty list)")
        async def _restore_empty():
            r = await client.post(
                "/api/subscription/restore-purchases",
                json={"purchases": []},
                headers=HEADERS,
            )
            assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
            data = r.json()
            assert data.get("restored") == 0, f"Expected restored=0, got {data}"
            print(f"{INFO}   {data}")
            return data

        await check("Restore empty list returns restored=0", _restore_empty())

        # ── 6. RTDN webhook (Pub/Sub format) ───────────────────────────
        print("\n[6] POST /api/subscription/rtdn-webhook (Pub/Sub mock)")
        async def _rtdn():
            import base64
            notification = json.dumps({
                "notificationType": 4,
                "purchaseToken": "mock_token_rtdn",
                "subscriptionId": "crm_pro_monthly",
            })
            encoded = base64.b64encode(notification.encode()).decode()
            payload = {"message": {"data": encoded, "messageId": "test-123"}, "subscription": "test"}
            r = await client.post(
                "/api/subscription/rtdn-webhook",
                json=payload,
                # RTDN webhook is unauthenticated (called by Google Pub/Sub)
            )
            assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
            data = r.json()
            assert data.get("status") == "ok", f"Unexpected: {data}"
            print(f"{INFO}   RTDN acknowledged: {data}")
            return data

        await check("RTDN webhook accepts Pub/Sub message", _rtdn())

        # ── 7. Service account file ────────────────────────────────────
        print("\n[7] Service account key file check (local only)")
        import os as _os
        sa_path = "google-service-account.json"
        if _os.path.exists(sa_path):
            with open(sa_path) as f:
                sa = json.load(f)
            required_keys = ["type", "project_id", "private_key", "client_email"]
            missing = [k for k in required_keys if k not in sa]
            if missing:
                print(f"{FAIL} Service account missing keys: {missing}")
            else:
                print(f"{PASS} Service account file valid — client_email: {sa.get('client_email','?')}")
        else:
            print(f"{FAIL} google-service-account.json not found at '{sa_path}'")

        # ── Summary ────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("  PRODUCT IDs TO CREATE IN GOOGLE PLAY CONSOLE:")
        print("=" * 60)
        skus = [
            "crm_starter_monthly",
            "crm_starter_yearly",
            "crm_standard_monthly",
            "crm_standard_yearly",
            "crm_pro_monthly",
            "crm_pro_yearly",
        ]
        for sku in skus:
            print(f"    {sku}")
        print()
        print("  RTDN WEBHOOK URL TO SET IN PLAY CONSOLE:")
        print(f"    {BACKEND_URL}/api/subscription/rtdn-webhook")
        print()
        print("  ENV VARS NEEDED ON RENDER:")
        print("    GOOGLE_PLAY_PACKAGE_NAME = com.charo360.whatsappcrm")
        print("    GOOGLE_SA_KEY_PATH       = google-service-account.json")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
