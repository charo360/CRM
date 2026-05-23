import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

/**
 * POST /api/composio/connect/[toolkit]
 * Proxies to FastAPI POST /composio/connect/{toolkit}
 * Returns { redirect_url, connection_id } for the OAuth popup.
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ toolkit: string }> }
) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { toolkit } = await params;
  try {
    const forward = await req.text();
    const url = buildServerCrmApiUrl(req, `/composio/connect/${toolkit}`);
    console.log(`[composio/connect] Forwarding to: ${url}`);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25000);
    const res = await fetch(url, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
      body: forward.trim() ? forward : "{}",
      signal: controller.signal,
    });
    clearTimeout(timeout);
    console.log(`[composio/connect] Backend responded: ${res.status}`);
    const data = await res.json().catch(() => ({}));
    console.log(`[composio/connect] Response data:`, JSON.stringify(data));
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    console.error("[api/composio/connect POST] Error:", e);
    console.error("[api/composio/connect POST] URL was:", buildServerCrmApiUrl(req, `/composio/connect/${toolkit}`));
    return NextResponse.json({ error: "Request failed", details: e instanceof Error ? e.message : String(e) }, { status: 502 });
  }
}
