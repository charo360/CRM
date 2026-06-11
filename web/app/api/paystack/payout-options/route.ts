import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const base = (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000")
    .trim()
    .replace(/\/$/, "");
  const qs = req.nextUrl.searchParams.toString();
  const url = `${base}/api/paystack/payout-options${qs ? `?${qs}` : ""}`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(20_000) });
    const text = await res.text();
    let data: unknown = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { detail: text || res.statusText };
    }
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { detail: `Could not load Paystack payout options: ${msg}` },
      { status: 503 },
    );
  }
}
