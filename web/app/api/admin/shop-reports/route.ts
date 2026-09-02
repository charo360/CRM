import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });

  const { searchParams } = new URL(req.url);
  const qs = searchParams.toString();
  const backendUrl = buildServerCrmApiUrl(req, `/admin/shop-reports${qs ? `?${qs}` : ""}`);
  const res = await fetch(backendUrl, { headers: { Authorization: auth } });
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
