import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

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
    const url = buildServerCrmApiUrl(req, `/composio/connections/${toolkit}`);
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
