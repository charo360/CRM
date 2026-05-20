import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

function err(msg: string, status = 400) {
  return NextResponse.json({ error: msg }, { status });
}

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) return err("Unauthorized", 401);

  const sp = req.nextUrl.searchParams;
  const params = new URLSearchParams();
  for (const [k, v] of sp.entries()) params.set(k, v);

  const url = buildServerCrmApiUrl(req, `/cj/products?${params.toString()}`);
  const res = await fetch(url, { headers: { Authorization: auth } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return err((data as { detail?: string }).detail ?? "CJ request failed", res.status);
  return NextResponse.json(data);
}
