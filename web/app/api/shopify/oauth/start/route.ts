import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const shop = req.nextUrl.searchParams.get("shop") ?? "";
  if (!shop.trim()) {
    return NextResponse.json({ error: "shop parameter required" }, { status: 400 });
  }
  try {
    const url = buildServerCrmApiUrl(req, `/shopify/oauth/start?shop=${encodeURIComponent(shop)}`);
    const res = await fetch(url, { headers: { Authorization: auth } });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json(
      { error: "Request failed", detail: e instanceof Error ? e.message : String(e) },
      { status: 502 },
    );
  }
}
