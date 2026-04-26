import { NextRequest, NextResponse } from "next/server";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

const NANGO_API = process.env.NANGO_API_URL || "https://api.nango.dev";

function allFalse(ids: string[]): Record<string, boolean> {
  const connected: Record<string, boolean> = {};
  for (const id of ids) connected[id] = false;
  return connected;
}

/**
 * GET /api/nango/connections?integrations=slack,google-mail,shopify,google-calendar
 *
 * Returns which of the requested integration IDs are connected for the
 * currently authenticated user.
 *
 * Response: { connected: Record<string, boolean> }
 */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const secret = process.env.NANGO_SECRET_KEY;
  if (!secret) {
    return NextResponse.json({ connected: {} });
  }

  const url = new URL(req.url);
  const integrations = (url.searchParams.get("integrations") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  if (!integrations.length) {
    return NextResponse.json({ connected: {} });
  }

  try {
    const meUrl = buildServerCrmApiUrl(req, "/auth/me");
    const meRes = await fetch(meUrl, { headers: { Authorization: auth } });
    if (!meRes.ok) {
      return NextResponse.json({ error: "Invalid session" }, { status: 401 });
    }
    let me: { id?: string };
    try {
      me = (await meRes.json()) as { id?: string };
    } catch {
      return NextResponse.json({ error: "Invalid session" }, { status: 401 });
    }
    const endUserId = me?.id != null ? String(me.id) : "";
    if (!endUserId) {
      return NextResponse.json({ error: "Invalid session" }, { status: 401 });
    }

    const nangoUrl = new URL(`${NANGO_API}/connection`);
    nangoUrl.searchParams.set("end_user_id", endUserId);

    const nangoRes = await fetch(nangoUrl.toString(), {
      headers: { Authorization: `Bearer ${secret}` },
    });

    if (!nangoRes.ok) {
      return NextResponse.json({ connected: allFalse(integrations) });
    }

    let data: { connections?: Array<{ provider_config_key: string }> };
    try {
      data = (await nangoRes.json()) as { connections?: Array<{ provider_config_key: string }> };
    } catch {
      return NextResponse.json({ connected: allFalse(integrations) });
    }

    const connectedSet = new Set(
      (data.connections ?? []).map((c) => c.provider_config_key)
    );

    const connected: Record<string, boolean> = {};
    for (const id of integrations) {
      connected[id] = connectedSet.has(id);
    }

    return NextResponse.json({ connected });
  } catch (e) {
    console.error("[api/nango/connections]", e);
    return NextResponse.json({ connected: allFalse(integrations) });
  }
}

/**
 * DELETE /api/nango/connections
 * Body: { integration_id: string }
 *
 * Disconnects a specific integration for the current user.
 */
export async function DELETE(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const secret = process.env.NANGO_SECRET_KEY;
  if (!secret) {
    return NextResponse.json({ error: "Nango not configured" }, { status: 503 });
  }

  const meUrl = buildServerCrmApiUrl(req, "/auth/me");
  const meRes = await fetch(meUrl, { headers: { Authorization: auth } });
  if (!meRes.ok) {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }
  let me: { id?: string };
  try {
    me = (await meRes.json()) as { id?: string };
  } catch {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }
  const endUserId = me?.id != null ? String(me.id) : "";
  if (!endUserId) {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }

  let body: { integration_id?: string; connection_id?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  const integrationId = body.integration_id;
  if (!integrationId) {
    return NextResponse.json({ error: "integration_id is required" }, { status: 400 });
  }

  // Find the connection ID for this user + integration
  const listUrl = new URL(`${NANGO_API}/connection`);
  listUrl.searchParams.set("end_user_id", endUserId);
  listUrl.searchParams.set("provider_config_key", integrationId);

  const listRes = await fetch(listUrl.toString(), {
    headers: { Authorization: `Bearer ${secret}` },
  });

  if (!listRes.ok) {
    return NextResponse.json({ error: "Could not look up connection" }, { status: 502 });
  }

  const listData = (await listRes.json()) as {
    connections?: Array<{ id: string }>;
  };

  const connectionId = body.connection_id ?? listData.connections?.[0]?.id;
  if (!connectionId) {
    return NextResponse.json({ error: "No connection found" }, { status: 404 });
  }

  const delRes = await fetch(
    `${NANGO_API}/connection/${connectionId}?provider_config_key=${encodeURIComponent(integrationId)}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${secret}` },
    }
  );

  if (!delRes.ok) {
    const err = await delRes.json().catch(() => ({} as { error?: { message?: string } }));
    return NextResponse.json(
      { error: err?.error?.message || "Failed to disconnect" },
      { status: delRes.status }
    );
  }

  return NextResponse.json({ ok: true });
}
