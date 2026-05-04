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
    const url = buildServerCrmApiUrl(req, `/composio/connect/${toolkit}`);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25000);
    const res = await fetch(url, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
      signal: controller.signal,
    });
    clearTimeout(timeout);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    console.error("[api/composio/connect POST]", e);
    return NextResponse.json({ error: "Request failed" }, { status: 502 });
  }
}
