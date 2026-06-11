import { NextResponse } from "next/server";

export async function GET() {
  const base = (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000")
    .trim()
    .replace(/\/$/, "");
  try {
    const res = await fetch(`${base}/api/flutterwave/setup`, {
      signal: AbortSignal.timeout(12_000),
    });
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
      { detail: `Could not load Flutterwave setup: ${msg}` },
      { status: 503 },
    );
  }
}
