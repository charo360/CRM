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
    let me: { id?: string; business_id?: string };
    try {
      me = (await meRes.json()) as { id?: string; business_id?: string };
    } catch {
      return NextResponse.json({ error: "Invalid session" }, { status: 401 });
    }
    const tenantIdRaw = me.business_id ?? me.id;
    const tenantId = tenantIdRaw != null ? String(tenantIdRaw) : "";
    if (!tenantId) {
      return NextResponse.json({ error: "Invalid session" }, { status: 401 });
    }

    const connectedSet = await mergeConnectionProviderKeys(secret, me);

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

async function nangoConnectionsForTag(
  secret: string,
  endUserTag: string
): Promise<Array<{ provider_config_key: string; id?: unknown; connection_id?: string }>> {
  const nangoUrl = new URL(`${NANGO_API}/connections`);
  nangoUrl.searchParams.set("tags[end_user_id]", endUserTag);
  const nangoRes = await fetch(nangoUrl.toString(), {
    headers: { Authorization: `Bearer ${secret}` },
  });
  if (!nangoRes.ok) {
    return [];
  }
  try {
    const data = (await nangoRes.json()) as {
      connections?: Array<{ provider_config_key: string; id?: unknown; connection_id?: string }>;
    };
    return data.connections ?? [];
  } catch {
    return [];
  }
}

/** Tenant tag + legacy per-user tag (same as connect-session historically used user id). */
async function mergeConnectionProviderKeys(
  secret: string,
  me: { id?: string; business_id?: string }
): Promise<Set<string>> {
  const tenantTag = String(me.business_id ?? me.id ?? "").trim();
  const userTag = String(me?.id ?? "").trim();
  const keys = new Set<string>();
  if (tenantTag) {
    for (const c of await nangoConnectionsForTag(secret, tenantTag)) {
      keys.add(c.provider_config_key);
    }
  }
  if (userTag && userTag !== tenantTag) {
    for (const c of await nangoConnectionsForTag(secret, userTag)) {
      keys.add(c.provider_config_key);
    }
  }
  return keys;
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

  const apiSecret: string = secret;

  const meUrl = buildServerCrmApiUrl(req, "/auth/me");
  const meRes = await fetch(meUrl, { headers: { Authorization: auth } });
  if (!meRes.ok) {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }
  let me: { id?: string; business_id?: string };
  try {
    me = (await meRes.json()) as { id?: string; business_id?: string };
  } catch {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }
  const tenantId = String(me.business_id ?? me.id ?? "").trim();
  const userId = String(me?.id ?? "").trim();
  if (!tenantId && !userId) {
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

  /** Walk tenant + legacy user-tag lists for this integration */
  async function findConnectionPathId(): Promise<string | undefined> {
    const tagsOrdered = [...new Set([tenantId, userId].filter((t): t is string => t.length > 0))];
    for (const tag of tagsOrdered) {
      const list = await nangoConnectionsForTag(apiSecret, tag);
      const match = list.find((c) => c.provider_config_key === integrationId);
      if (match != null) {
        const pathIdRaw = match.connection_id ?? match.id;
        if (pathIdRaw === undefined || pathIdRaw === null) continue;
        return String(pathIdRaw);
      }
    }
    return undefined;
  }

  const pathIdFromBody = body.connection_id?.trim();
  const pathId = pathIdFromBody || (await findConnectionPathId());
  if (!pathId) {
    return NextResponse.json({ error: "No connection found" }, { status: 404 });
  }

  const delRes = await fetch(
    `${NANGO_API}/connections/${encodeURIComponent(pathId)}?provider_config_key=${encodeURIComponent(integrationId)}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${apiSecret}` },
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
