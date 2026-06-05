import { NextRequest, NextResponse } from "next/server";
import { buildInternalCrmApiUrl } from "@/lib/server-crm-api";

/**
 * GET /api/composio/connections/[toolkit]
 * Proxies to FastAPI GET /composio/connections/{toolkit}
 * Returns { connected: bool, connection_id: string|null }
 * Called by the OAuth polling loop after the popup closes.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ toolkit: string }> }
) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { toolkit } = await params;
  try {
    const url = buildInternalCrmApiUrl(`/composio/connections/${toolkit}`);
    const res = await fetch(url, { headers: { Authorization: auth } });
    const data = await res.json().catch(() => ({ connected: false }));
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    console.error("[api/composio/connections GET]", e);
    return NextResponse.json({ connected: false }, { status: 502 });
  }
}

/**
 * DELETE /api/composio/connections/[toolkit]
 * Proxies to FastAPI DELETE /composio/connections/{toolkit}
 */
export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ toolkit: string }> }
) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { toolkit } = await params;
  try {
    const url = buildInternalCrmApiUrl(`/composio/connections/${toolkit}`);
    const res = await fetch(url, {
      method: "DELETE",
      headers: { Authorization: auth },
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    console.error("[api/composio/connections DELETE]", e);
    return NextResponse.json({ error: "Request failed" }, { status: 502 });
  }
}
