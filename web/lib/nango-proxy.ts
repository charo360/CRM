/**
 * Integration auth helpers for Next.js API routes.
 * Composio is the sole OAuth provider — Nango is no longer used.
 */

function backendInternalBase(): string {
  return (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function backendAuthMeUrl(): string {
  const publicBase = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api").trim();
  if (publicBase.startsWith("http://") || publicBase.startsWith("https://")) {
    return `${publicBase.replace(/\/$/, "")}/auth/me`;
  }
  return `${backendInternalBase()}/api/auth/me`;
}

/** Resolve the user_id from a Bearer token via /auth/me */
export async function resolveUserId(authHeader: string | null): Promise<string | null> {
  if (!authHeader) return null;
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(backendAuthMeUrl(), {
      headers: { Authorization: authHeader },
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) return null;
    const me = await res.json() as { id?: string; _id?: string; business_id?: string };
    return me.business_id || me.id || me._id || null;
  } catch {
    return null;
  }
}

/** Check if a Composio toolkit is connected; returns connection id when available. */
export async function getComposioToolkitConnectionId(
  authHeader: string,
  toolkit: string,
): Promise<string | null> {
  try {
    const res = await fetch(`${backendInternalBase()}/api/composio/connections/${toolkit}`, {
      headers: { Authorization: authHeader },
    });
    if (!res.ok) return null;
    const data = await res.json() as { connected?: boolean; connection_id?: string };
    if (!data.connected) return null;
    return data.connection_id || toolkit;
  } catch {
    return null;
  }
}

/** @deprecated Nango removed — kept for type compatibility in legacy call sites. */
export async function getNangoConnectionId(): Promise<string | null> {
  return null;
}

/** @deprecated Nango removed — legacy call sites should use Composio backend routes. */
export async function nangoProxy(_opts?: unknown): Promise<Response> {
  return new Response(JSON.stringify({ error: "Nango is disabled; connect via Composio in Integrations." }), {
    status: 410,
    headers: { "Content-Type": "application/json" },
  });
}

/** Detect ALL email providers connected for this user (Composio only). */
export async function detectAllEmailProviders(
  _userId: string,
  authHeader?: string,
): Promise<Array<{
  provider: "gmail" | "microsoft";
  integrationKey: string;
  connectionId: string;
  via: "composio";
}>> {
  if (!authHeader) return [];
  const [gmailId, outlookId] = await Promise.all([
    getComposioToolkitConnectionId(authHeader, "gmail"),
    getComposioToolkitConnectionId(authHeader, "outlook"),
  ]);
  const results: Array<{
    provider: "gmail" | "microsoft";
    integrationKey: string;
    connectionId: string;
    via: "composio";
  }> = [];
  if (gmailId) {
    results.push({ provider: "gmail", integrationKey: "gmail", connectionId: gmailId, via: "composio" });
  }
  if (outlookId) {
    results.push({ provider: "microsoft", integrationKey: "outlook", connectionId: outlookId, via: "composio" });
  }
  return results;
}

/** Detect which email provider is connected (Composio only). */
export async function detectEmailProvider(
  userId: string,
  preferredProvider?: "gmail" | "microsoft",
  authHeader?: string,
): Promise<{
  provider: "gmail" | "microsoft" | null;
  integrationKey: string;
  connectionId: string;
  via: "composio";
} | null> {
  const all = await detectAllEmailProviders(userId, authHeader);
  if (!all.length) return null;
  if (preferredProvider) {
    const match = all.find((p) => p.provider === preferredProvider);
    if (match) return match;
  }
  return all[0];
}

/** @deprecated Use Composio googlecalendar / outlook via detectCalendarConnection in calendar route. */
export async function detectCalendarProvider(): Promise<null> {
  return null;
}

/** Back-compat alias */
export async function getComposioGmailConnectionId(
  _userId: string,
  authHeader: string,
): Promise<string | null> {
  return getComposioToolkitConnectionId(authHeader, "gmail");
}
