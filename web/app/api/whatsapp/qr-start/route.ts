import { NextRequest, NextResponse } from "next/server";

/** Evolution instance setup can take 30–90s; avoid Next rewrite/proxy timeouts. */
export const maxDuration = 120;

function backendQrStartUrl(): string {
  const base = (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000").trim().replace(/\/$/, "");
  return `${base}/api/whatsapp/qr-start`;
}

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  try {
    const res = await fetch(backendQrStartUrl(), {
      method: "POST",
      headers: {
        Authorization: auth,
        "Content-Type": "application/json",
      },
      body: "{}",
      signal: AbortSignal.timeout(115_000),
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
    console.error("[whatsapp/qr-start proxy]", e);
    return NextResponse.json(
      { detail: "WhatsApp QR setup timed out. Please try again." },
      { status: 504 },
    );
  }
}
