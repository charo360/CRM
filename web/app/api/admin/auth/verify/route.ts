import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth) return NextResponse.json({ access: false }, { status: 401 });

  const backendUrl = buildServerCrmApiUrl(req, "/admin/auth/verify");
  const res = await fetch(backendUrl, {
    headers: { Authorization: auth },
  });

  const data = await res.json().catch(() => ({ access: false }));
  return NextResponse.json(data, { status: res.status });
}
