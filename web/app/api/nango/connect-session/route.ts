import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

const NANGO_API = process.env.NANGO_API_URL || "https://api.nango.dev";

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const secret = process.env.NANGO_SECRET_KEY;
  if (!secret) {
    return NextResponse.json(
      { error: "Nango is not configured. Add NANGO_SECRET_KEY to the server environment." },
      { status: 503 }
    );
  }

  let me: { id?: string; business_id?: string };
  try {
    const meUrl = buildServerCrmApiUrl(req, "/auth/me");
    const meRes = await fetch(meUrl, { headers: { Authorization: auth } });
    if (!meRes.ok) {
      return NextResponse.json({ error: "Invalid session" }, { status: 401 });
    }
    me = (await meRes.json()) as { id?: string; business_id?: string };
  } catch {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }
  if (!me?.id) {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }

  let body: { allowed_integrations?: string[] };
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const allowed = body.allowed_integrations;
  if (!allowed?.length) {
    return NextResponse.json({ error: "allowed_integrations is required" }, { status: 400 });
  }

  const sessionRes = await fetch(`${NANGO_API}/connect/sessions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secret}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      allowed_integrations: allowed,
      tags: {
        end_user_id: String(me.id!),
        organization_id: String(me.business_id ?? ""),
      },
    }),
  });

  if (!sessionRes.ok) {
    const err = await sessionRes.json().catch(() => ({} as { error?: { message?: string } }));
    const msg = err?.error?.message || sessionRes.statusText;
    return NextResponse.json({ error: msg }, { status: sessionRes.status });
  }

  const json = (await sessionRes.json()) as { data?: { token?: string } };
  const token = json.data?.token;
  if (!token) {
    return NextResponse.json({ error: "No session token from Nango" }, { status: 502 });
  }

  return NextResponse.json({ sessionToken: token });
}
