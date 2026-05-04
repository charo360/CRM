import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

/**
 * /api/composio/gmail-proxy/[...path]
 * Forwards Gmail API calls to FastAPI /composio/gmail-proxy/{path}
 * which injects the Composio-managed OAuth access token.
 */

async function handler(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { path } = await params;
  const pathStr = path.join("/");
  const query = req.nextUrl.search; // includes the leading ?

  const backendPath = `/composio/gmail-proxy/${pathStr}${query}`;
  const url = buildServerCrmApiUrl(req, backendPath);

  try {
    const body = req.method !== "GET" && req.method !== "HEAD"
      ? await req.arrayBuffer()
      : undefined;

    const res = await fetch(url, {
      method: req.method,
      headers: {
        Authorization: auth,
        "Content-Type": "application/json",
      },
      body: body ? Buffer.from(body) : undefined,
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    console.error("[composio/gmail-proxy]", e);
    return NextResponse.json({ error: "Gmail proxy failed" }, { status: 502 });
  }
}

export { handler as GET, handler as POST, handler as DELETE, handler as PATCH };
