import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

/**
 * POST /api/composio/connections/[toolkit]/cleanup
 * Removes stale in-progress OAuth sessions (user closed popup without finishing login).
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
    const url = buildServerCrmApiUrl(req, `/composio/connections/${toolkit}/cleanup`);
    const res = await fetch(url, {
      method: "POST",
      headers: { Authorization: auth },
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    console.error("[api/composio/connections cleanup POST]", e);
    return NextResponse.json({ error: "Request failed" }, { status: 502 });
  }
}
