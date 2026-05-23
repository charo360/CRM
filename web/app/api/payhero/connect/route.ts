import { NextRequest, NextResponse } from "next/server";

/** PayHero token verification can be slow; avoid brittle rewrite proxy resets. */
export const maxDuration = 60;

function backendConnectUrl(): string {
  const base = (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000").trim().replace(/\/$/, "");
  return `${base}/api/payhero/connect`;
}

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  let body = "{}";
  try {
    body = await req.text();
  } catch {
    body = "{}";
  }

  try {
    const res = await fetch(backendConnectUrl(), {
      method: "POST",
      headers: {
        Authorization: auth,
        "Content-Type": "application/json",
      },
      body: body || "{}",
      signal: AbortSignal.timeout(55_000),
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
    const isReset =
      msg.includes("ECONNRESET") ||
      msg.includes("socket hang up") ||
      msg.includes("fetch failed") ||
      msg.includes("ECONNREFUSED");
    console.error("[payhero/connect proxy]", e);
    return NextResponse.json(
      {
        detail: isReset
          ? "CRM backend is not reachable at " +
            (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000") +
            ". Start the FastAPI server (port 8000) and try again."
          : `PayHero connect failed: ${msg}`,
      },
      { status: isReset ? 503 : 502 },
    );
  }
}
