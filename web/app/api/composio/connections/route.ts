import { NextRequest, NextResponse } from "next/server";
import { buildComposioDisconnectedStatus } from "@/lib/integrations-composio";
import { buildInternalCrmApiUrl } from "@/lib/server-crm-api";

const DISCONNECTED = buildComposioDisconnectedStatus();

const PROXY_TIMEOUT_MS = 12_000;

/**
 * GET /api/composio/connections
 * Proxies to FastAPI GET /composio/connections — returns all toolkit statuses.
 */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const cachedOnly = req.nextUrl.searchParams.get("cached") === "1";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), cachedOnly ? 5_000 : PROXY_TIMEOUT_MS);
  try {
    const path = cachedOnly ? "/composio/connections?cached=1" : "/composio/connections";
    const url = buildInternalCrmApiUrl(path);
    const res = await fetch(url, {
      headers: { Authorization: auth },
      signal: controller.signal,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    console.error("[api/composio/connections GET]", e);
    return NextResponse.json({ connected: DISCONNECTED });
  } finally {
    clearTimeout(timer);
  }
}
