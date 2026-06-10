/**
 * Nango proxy helper for Next.js API routes.
 * Looks up the user's connection ID then routes calls through the Nango proxy.
 */

const NANGO_API = process.env.NANGO_API_URL || "https://api.nango.dev";
const NANGO_KEY = process.env.NANGO_SECRET_KEY || "";

function backendAuthMeUrl(): string {
  const publicBase = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api").trim();
  if (publicBase.startsWith("http://") || publicBase.startsWith("https://")) {
    return `${publicBase.replace(/\/$/, "")}/auth/me`;
  }
  const internal = (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  return `${internal}/api/auth/me`;
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

/** Get the Nango connection ID for a user + integration */
export async function getNangoConnectionId(
  userId: string,
  integrationKey: string,
): Promise<string | null> {
  if (!NANGO_KEY) return null;
  try {
    const res = await fetch(
      `${NANGO_API}/connection?end_user_id=${encodeURIComponent(userId)}&provider_config_key=${integrationKey}`,
      { headers: { Authorization: `Bearer ${NANGO_KEY}` } },
    );
    if (!res.ok) return null;
    const data = await res.json() as { connections?: { connection_id?: string }[] };
    return data.connections?.[0]?.connection_id ?? null;
  } catch {
    return null;
  }
}

/** Proxy a request through Nango to a third-party API */
export async function nangoProxy(opts: {
  integrationKey: string;
  connectionId: string;
  method?: string;
  path: string;                     // path on the provider API, e.g. /gmail/v1/users/me/threads
  params?: Record<string, string>;  // URL query params
  body?: unknown;
  headers?: Record<string, string>;
}): Promise<Response> {
  const { integrationKey, connectionId, method = "GET", path, params, body, headers = {} } = opts;

  let url = `${NANGO_API}/proxy${path}`;
  if (params && Object.keys(params).length) {
    url += "?" + new URLSearchParams(params).toString();
  }

  const init: RequestInit = {
    method,
    headers: {
      "Authorization": `Bearer ${NANGO_KEY}`,
      "Connection-Id": connectionId,
      "Provider-Config-Key": integrationKey,
      "Content-Type": "application/json",
      ...headers,
    },
  };
  if (body) init.body = JSON.stringify(body);

  return fetch(url, init);
}

/** Check if Gmail is connected via Composio for this user.
 *  Returns the composio connected account ID or null. */
export async function getComposioGmailConnectionId(
  userId: string,
  authHeader: string,
): Promise<string | null> {
  try {
    const internal = (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    const res = await fetch(`${internal}/api/composio/connections/gmail`, {
      headers: { Authorization: authHeader },
    });
    if (!res.ok) return null;
    const data = await res.json() as { connected?: boolean; connection_id?: string };
    return data.connected && data.connection_id ? data.connection_id : null;
  } catch {
    return null;
  }
}

/** Detect ALL email providers connected for this user */
export async function detectAllEmailProviders(
  userId: string,
  authHeader?: string,
): Promise<Array<{
  provider: "gmail" | "microsoft";
  integrationKey: string;
  connectionId: string;
  via?: "nango" | "composio";
}>> {
  const [gmailId, msId] = await Promise.all([
    getNangoConnectionId(userId, "google-mail"),
    getNangoConnectionId(userId, "microsoft"),
  ]);
  const results: Array<{ provider: "gmail" | "microsoft"; integrationKey: string; connectionId: string; via?: "nango" | "composio" }> = [];
  if (gmailId) results.push({ provider: "gmail", integrationKey: "google-mail", connectionId: gmailId, via: "nango" });
  if (msId)    results.push({ provider: "microsoft", integrationKey: "microsoft", connectionId: msId, via: "nango" });

  // Fall back to Composio Gmail if Nango Gmail not connected
  if (!gmailId && authHeader) {
    const composioConnId = await getComposioGmailConnectionId(userId, authHeader);
    if (composioConnId) {
      results.unshift({ provider: "gmail", integrationKey: "composio-gmail", connectionId: composioConnId, via: "composio" });
    }
  }

  return results;
}

/** Detect which email provider is connected for this user (gmail preferred).
 *  Pass preferredProvider to override the default Gmail-first order. */
export async function detectEmailProvider(
  userId: string,
  preferredProvider?: "gmail" | "microsoft",
): Promise<{
  provider: "gmail" | "microsoft" | null;
  integrationKey: string;
  connectionId: string;
} | null> {
  const all = await detectAllEmailProviders(userId);
  if (!all.length) return null;
  if (preferredProvider) {
    const match = all.find((p) => p.provider === preferredProvider);
    if (match) return match;
  }
  return all[0]; // Gmail first by default (inserted first above)
}

/** Detect which calendar provider is connected */
export async function detectCalendarProvider(userId: string): Promise<{
  provider: "google" | "microsoft" | null;
  integrationKey: string;
  connectionId: string;
} | null> {
  const gcalId = await getNangoConnectionId(userId, "google-calendar");
  if (gcalId) return { provider: "google", integrationKey: "google-calendar", connectionId: gcalId };

  const msId = await getNangoConnectionId(userId, "microsoft");
  if (msId) return { provider: "microsoft", integrationKey: "microsoft", connectionId: msId };

  return null;
}
