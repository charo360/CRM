import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = req.headers.get("authorization");
  if (!auth) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const backendUrl = buildServerCrmApiUrl(req, `/admin/shop-reports/${encodeURIComponent(id)}`);
  const res = await fetch(backendUrl, {
    method: "PATCH",
    headers: { Authorization: auth, "Content-Type": "application/json" },
    body: await req.text(),
  });
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
