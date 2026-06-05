import { NextRequest, NextResponse } from "next/server";
import { buildInternalCrmApiUrl } from "@/lib/server-crm-api";

/**
 * GET /api/composio/connections
 * Proxies to FastAPI GET /composio/connections — returns all toolkit statuses.
 */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  try {
    const url = buildInternalCrmApiUrl("/composio/connections");
    const res = await fetch(url, { headers: { Authorization: auth } });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    console.error("[api/composio/connections GET]", e);
    return NextResponse.json({ connected: { gmail: false, googlecalendar: false } });
  }
}
