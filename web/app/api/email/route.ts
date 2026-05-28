import { NextRequest, NextResponse } from "next/server";
import {
  resolveUserId,
  detectAllEmailProviders,
  nangoProxy,
} from "@/lib/nango-proxy";
import { buildInternalCrmApiUrl } from "@/lib/server-crm-api";

/** Call a Composio Gmail structured backend endpoint */
async function composioBackend(auth: string, path: string, opts?: { method?: string; body?: unknown }): Promise<Response> {
  const init: RequestInit = {
    method: opts?.method ?? "GET",
    headers: { Authorization: auth, "Content-Type": "application/json" },
  };
  if (opts?.body) init.body = JSON.stringify(opts.body);
  return fetch(buildInternalCrmApiUrl(path), init);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function err(msg: string, status = 400) {
  return NextResponse.json({ error: msg }, { status });
}

/** Parse a base64url Gmail message part into plain text */
function decodeGmailBody(data?: string): string {
  if (!data) return "";
  try {
    const b64 = data.replace(/-/g, "+").replace(/_/g, "/");
    return atob(b64);
  } catch {
    return "";
  }
}

/** Recursively find the plain-text or html part */
function extractBody(payload: Record<string, unknown>): string {
  const mimeType = payload.mimeType as string | undefined;
  const body = payload.body as { data?: string } | undefined;
  const parts = payload.parts as Record<string, unknown>[] | undefined;

  if (mimeType === "text/plain" && body?.data) return decodeGmailBody(body.data);
  if (mimeType === "text/html" && body?.data) return decodeGmailBody(body.data);
  if (parts) {
    for (const part of parts) {
      const text = extractBody(part);
      if (text) return text;
    }
  }
  return "";
}

function headerVal(headers: { name: string; value: string }[], name: string): string {
  return headers.find((h) => h.name.toLowerCase() === name.toLowerCase())?.value ?? "";
}

// ── Composio Gmail helpers (when Nango Gmail not connected) ──────────────────

type ComposioThread = {
  id: string; subject: string; from: string; to?: string; date: string;
  snippet: string; messages?: ComposioMessage[]; unread: boolean; messageCount: number; provider: "gmail";
};

type ComposioMessage = {
  id: string; from: string; to: string; subject: string;
  date: string; body: string; unread: boolean;
};

async function composioGmailListThreads(auth: string, query = "", maxResults = 25): Promise<ComposioThread[]> {
  const params = new URLSearchParams({ limit: String(maxResults) });
  if (query) params.set("q", query);
  const res = await composioBackend(auth, `/composio/gmail/threads?${params}`);
  if (!res.ok) throw new Error(`Composio Gmail threads ${res.status}`);
  const data = await res.json() as { threads?: ComposioThread[] };
  return data.threads ?? [];
}

async function composioGmailGetThread(auth: string, threadId: string): Promise<{ messages: ComposioMessage[] }> {
  const res = await composioBackend(auth, `/composio/gmail/threads/${encodeURIComponent(threadId)}`);
  if (!res.ok) throw new Error(`Composio Gmail thread ${res.status}`);
  return res.json() as Promise<{ messages: ComposioMessage[] }>;
}

// ── Gmail ─────────────────────────────────────────────────────────────────────

async function gmailListThreads(connectionId: string, query = "", maxResults = 25) {
  const params: Record<string, string> = { maxResults: String(maxResults) };
  if (query) params.q = query;

  const res = await nangoProxy({
    integrationKey: "google-mail",
    connectionId,
    path: "/gmail/v1/users/me/threads",
    params,
  });
  if (!res.ok) throw new Error(`Gmail threads ${res.status}`);
  const data = await res.json() as { threads?: { id: string; snippet: string }[] };
  return data.threads ?? [];
}

async function gmailGetThread(connectionId: string, threadId: string) {
  const res = await nangoProxy({
    integrationKey: "google-mail",
    connectionId,
    path: `/gmail/v1/users/me/threads/${threadId}`,
    params: { format: "full" },
  });
  if (!res.ok) throw new Error(`Gmail thread ${res.status}`);
  return res.json() as Promise<{
    id: string;
    messages: {
      id: string;
      labelIds: string[];
      internalDate: string;
      payload: {
        headers: { name: string; value: string }[];
        mimeType: string;
        body?: { data?: string };
        parts?: unknown[];
      };
    }[];
  }>;
}

async function gmailMarkRead(connectionId: string, messageId: string) {
  await nangoProxy({
    integrationKey: "google-mail",
    connectionId,
    method: "POST",
    path: `/gmail/v1/users/me/messages/${messageId}/modify`,
    body: { removeLabelIds: ["UNREAD"] },
  });
}

async function gmailSend(connectionId: string, raw: string) {
  return nangoProxy({
    integrationKey: "google-mail",
    connectionId,
    method: "POST",
    path: "/gmail/v1/users/me/messages/send",
    body: { raw },
  });
}

// ── Microsoft Graph ───────────────────────────────────────────────────────────

async function msListMessages(connectionId: string, search = "", top = 25) {
  const params: Record<string, string> = { $top: String(top), $orderby: "receivedDateTime desc" };
  if (search) params.$search = `"${search}"`;

  const res = await nangoProxy({
    integrationKey: "microsoft",
    connectionId,
    path: "/v1.0/me/mailFolders/inbox/messages",
    params,
  });
  if (!res.ok) throw new Error(`MS messages ${res.status}`);
  const data = await res.json() as { value?: unknown[] };
  return data.value ?? [];
}

async function msGetMessage(connectionId: string, messageId: string) {
  const res = await nangoProxy({
    integrationKey: "microsoft",
    connectionId,
    path: `/v1.0/me/messages/${messageId}`,
  });
  if (!res.ok) throw new Error(`MS message ${res.status}`);
  return res.json();
}

// ── Route handlers ────────────────────────────────────────────────────────────

/** GET /api/email?q=...&limit=...&provider=gmail|microsoft */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return err("Unauthorized", 401);

  const q = req.nextUrl.searchParams.get("q") ?? "";
  const limit = Math.min(parseInt(req.nextUrl.searchParams.get("limit") ?? "25"), 100);
  const preferredProvider = req.nextUrl.searchParams.get("provider") as "gmail" | "microsoft" | null ?? undefined;

  // ── Try DB first (instant) ─────────────────────────────────────────────────
  try {
    const params = new URLSearchParams({ limit: String(limit) });
    if (q) params.set("q", q);
    const dbRes = await fetch(`${buildInternalCrmApiUrl("/email-db/threads")}?${params}`, {
      headers: { Authorization: auth! },
    });
    if (dbRes.ok) {
      const data = await dbRes.json() as { threads?: unknown[]; source?: string };
      if (data.threads && data.threads.length > 0) {
        return NextResponse.json({
          threads: data.threads,
          provider: preferredProvider ?? "gmail",
          connected: true,
          connectedProviders: ["gmail"],
          source: "db",
        });
      }
    }
  } catch { /* fall through to live fetch */ }

  // ── Fall back to live provider fetch (with provider fallback) ────────────
  try {
    const allProviders = await detectAllEmailProviders(userId, auth ?? undefined);
    const connectedProviders = [...new Set(allProviders.map((p) => p.provider))] as ("gmail" | "microsoft")[];
    if (allProviders.length === 0) {
      return NextResponse.json({ threads: [], provider: null, connected: false, connectedProviders: [] });
    }

    const listThreadsForProvider = async (provider: (typeof allProviders)[number]) => {
      const viaComposio = (provider as { via?: string }).via === "composio";
      if (provider.provider === "gmail") {
        // Composio path — backend already returns fully-shaped threads
        if (viaComposio) {
          const threads = await composioGmailListThreads(auth!, q, limit);
          return { threads, provider: "gmail" as const };
        }
        // Nango path — fetch each thread for header details
        const rawThreads = await gmailListThreads(provider.connectionId, q, limit);
        const threads = await Promise.all(
          rawThreads.slice(0, limit).map(async (t) => {
            try {
              const full = await gmailGetThread(provider.connectionId, t.id);
              const last = full.messages[full.messages.length - 1];
              const hdrs = last.payload.headers;
              const unread = last.labelIds?.includes("UNREAD") ?? false;
              return {
                id: t.id,
                subject: headerVal(hdrs, "Subject") || "(no subject)",
                from: headerVal(last.payload.headers, "From"),
                date: new Date(parseInt(last.internalDate)).toISOString(),
                snippet: t.snippet,
                unread,
                messageCount: full.messages.length,
                provider: "gmail" as const,
              };
            } catch {
              return {
                id: t.id, subject: "(error)", from: "", date: "", snippet: t.snippet,
                unread: false, messageCount: 1, provider: "gmail" as const,
              };
            }
          }),
        );
        return { threads, provider: "gmail" as const };
      }

      const msgs = await msListMessages(provider.connectionId, q, limit) as Record<string, unknown>[];
      const threads = msgs.map((m) => ({
        id: m.id as string,
        subject: (m.subject as string) || "(no subject)",
        from: ((m.from as { emailAddress?: { name?: string; address?: string } })?.emailAddress?.name || (m.from as { emailAddress?: { address?: string } })?.emailAddress?.address) ?? "",
        date: m.receivedDateTime as string,
        snippet: (m.bodyPreview as string) ?? "",
        unread: m.isRead === false,
        messageCount: 1,
        provider: "microsoft" as const,
      }));
      return { threads, provider: "microsoft" as const };
    };

    // Try preferred provider first (if provided), then the rest.
    const orderedProviders = (() => {
      if (!preferredProvider) return allProviders;
      const preferred = allProviders.filter((p) => p.provider === preferredProvider);
      const others = allProviders.filter((p) => p.provider !== preferredProvider);
      return [...preferred, ...others];
    })();

    let lastResult: { threads: unknown[]; provider: "gmail" | "microsoft" } | null = null;
    for (const p of orderedProviders) {
      try {
        const result = await listThreadsForProvider(p);
        lastResult = result;
        if ((result.threads ?? []).length > 0) {
          return NextResponse.json({ ...result, connected: true, connectedProviders });
        }
      } catch {
        // Try next connected provider.
      }
    }

    // No provider had threads (or all failed) — one-shot recovery sync, then re-read DB.
    try {
      const syncRes = await fetch(buildInternalCrmApiUrl("/email-db/sync"), {
        method: "POST",
        headers: { Authorization: auth!, "Content-Type": "application/json" },
      });
      if (syncRes.ok) {
        const params = new URLSearchParams({ limit: String(limit) });
        if (q) params.set("q", q);
        const dbRes = await fetch(`${buildInternalCrmApiUrl("/email-db/threads")}?${params}`, {
          headers: { Authorization: auth! },
        });
        if (dbRes.ok) {
          const data = await dbRes.json() as { threads?: unknown[] };
          if (Array.isArray(data.threads) && data.threads.length > 0) {
            return NextResponse.json({
              threads: data.threads,
              provider: preferredProvider ?? connectedProviders[0] ?? null,
              connected: true,
              connectedProviders,
              source: "db-after-sync",
            });
          }
        }
      }
    } catch {
      // If recovery sync fails, fall through to connected-empty response.
    }

    // Still empty — report connected so UI can show provider/sync state.
    return NextResponse.json({
      threads: lastResult?.threads ?? [],
      provider: lastResult?.provider ?? (preferredProvider ?? connectedProviders[0] ?? null),
      connected: true,
      connectedProviders,
    });
  } catch (e) {
    return err(e instanceof Error ? e.message : "Failed to load email", 500);
  }
}

/** POST /api/email — send or get thread */
export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return err("Unauthorized", 401);

  const body = await req.json() as {
    action: "get_thread" | "send" | "mark_read" | "sync";
    provider?: "gmail" | "microsoft";
    threadId?: string;
    messageId?: string;
    raw?: string;          // base64url RFC-2822 for Gmail send
    to?: string;
    subject?: string;
    replyBody?: string;
    inReplyTo?: string;
  };

  // ── Sync action — backend handles Gmail + Outlook via Composio ─────────────
  if (body.action === "sync") {
    const syncRes = await fetch(buildInternalCrmApiUrl("/email-db/sync"), {
      method: "POST",
      headers: { Authorization: auth!, "Content-Type": "application/json" },
    });
    if (!syncRes.ok) return err("Sync failed", 502);
    const syncData = await syncRes.json();
    return NextResponse.json(syncData);
  }

  // ── get_thread — try DB first ─────────────────────────────────────────────
  if (body.action === "get_thread" && body.threadId) {
    try {
      const dbRes = await fetch(buildInternalCrmApiUrl(`/email-db/threads/${encodeURIComponent(body.threadId)}/messages`), {
        headers: { Authorization: auth! },
      });
      if (dbRes.ok) {
        const data = await dbRes.json() as { messages?: unknown[] };
        if (data.messages && data.messages.length > 0) {
          return NextResponse.json({ messages: data.messages, provider: body.provider ?? "gmail", source: "db" });
        }
      }
    } catch { /* fall through to live fetch */ }
  }

  const allProviders = await detectAllEmailProviders(userId, auth ?? undefined);
  let provider = allProviders[0];
  if (body.provider) {
    const match = allProviders.find((p) => p.provider === body.provider);
    if (match) provider = match;
  }
  if (!provider) return err("No email account connected", 400);

  const viaComposio = (provider as { via?: string }).via === "composio";

  try {
    if (body.action === "get_thread") {
      if (!body.threadId) return err("threadId required");

      if (provider.provider === "gmail") {
        if (viaComposio) {
          // Composio path — messages already flat from backend
          const result = await composioGmailGetThread(auth!, body.threadId);
          return NextResponse.json({ messages: result.messages, provider: "gmail" });
        }
        // Nango path
        const thread = await gmailGetThread(provider.connectionId, body.threadId);
        const messages = thread.messages.map((m) => {
          const hdrs = m.payload.headers;
          return {
            id:      m.id,
            from:    headerVal(hdrs, "From"),
            to:      headerVal(hdrs, "To"),
            subject: headerVal(hdrs, "Subject"),
            date:    new Date(parseInt(m.internalDate)).toISOString(),
            body:    extractBody(m.payload as Record<string, unknown>),
            unread:  m.labelIds?.includes("UNREAD") ?? false,
          };
        });
        return NextResponse.json({ messages, provider: "gmail" });
      }

      // Microsoft — single message
      const msg = await msGetMessage(provider.connectionId, body.threadId) as Record<string, unknown>;
      return NextResponse.json({
        messages: [{
          id:      msg.id as string,
          from:    (msg.from as { emailAddress?: { name?: string; address?: string } })?.emailAddress?.address ?? "",
          to:      ((msg.toRecipients as { emailAddress?: { address?: string } }[])?.[0])?.emailAddress?.address ?? "",
          subject: msg.subject as string,
          date:    msg.receivedDateTime as string,
          body:    (msg.body as { content?: string })?.content ?? msg.bodyPreview as string ?? "",
          unread:  msg.isRead === false,
        }],
        provider: "microsoft",
      });
    }

    if (body.action === "mark_read") {
      if (provider.provider === "gmail" && body.messageId) {
        if (viaComposio) {
          // Composio doesn't have a mark-read action — best-effort no-op
        } else {
          await gmailMarkRead(provider.connectionId, body.messageId);
        }
      } else if (provider.provider === "microsoft" && body.messageId) {
        await nangoProxy({
          integrationKey: "microsoft",
          connectionId: provider.connectionId,
          method: "PATCH",
          path: `/v1.0/me/messages/${body.messageId}`,
          body: { isRead: true },
        });
      }
      return NextResponse.json({ ok: true });
    }

    if (body.action === "send") {
      if (provider.provider === "gmail") {
        if (viaComposio) {
          // Prefer explicit fields; fall back to parsing raw only if needed
          const sendTo = body.to || (() => {
            if (!body.raw) return "";
            try {
              const decoded = Buffer.from(body.raw.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf-8");
              return decoded.split(/\r?\n/).find(l => l.toLowerCase().startsWith("to:"))?.slice(3).trim() ?? "";
            } catch { return ""; }
          })();
          const sendSubject = body.subject || (() => {
            if (!body.raw) return "";
            try {
              const decoded = Buffer.from(body.raw.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf-8");
              return decoded.split(/\r?\n/).find(l => l.toLowerCase().startsWith("subject:"))?.slice(8).trim() ?? "";
            } catch { return ""; }
          })();
          const sendBody = body.replyBody || (() => {
            if (!body.raw) return "";
            try {
              const decoded = Buffer.from(body.raw.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf-8");
              const lines = decoded.split(/\r?\n/);
              const sep = lines.findIndex(l => l === "");
              return sep >= 0 ? lines.slice(sep + 1).join("\n") : "";
            } catch { return ""; }
          })();
          if (!sendTo) return err("to is required for Gmail send");
          const res = await composioBackend(auth!, "/composio/gmail/send", {
            method: "POST",
            body: { to: sendTo, subject: sendSubject, body: sendBody },
          });
          if (!res.ok) {
            const errText = await res.text();
            return err(`Gmail send failed: ${errText}`, 502);
          }
        } else {
          if (!body.raw) return err("raw (base64url email) required for Gmail send");
          const res = await gmailSend(provider.connectionId, body.raw);
          if (!res.ok) return err("Gmail send failed", 502);
        }
        return NextResponse.json({ ok: true });
      }

      // Microsoft
      if (!body.to || !body.subject) return err("to and subject required");
      const res = await nangoProxy({
        integrationKey: "microsoft",
        connectionId: provider.connectionId,
        method: "POST",
        path: "/v1.0/me/sendMail",
        body: {
          message: {
            subject: body.subject,
            body: { contentType: "Text", content: body.replyBody ?? "" },
            toRecipients: [{ emailAddress: { address: body.to } }],
          },
        },
      });
      if (!res.ok) return err("Outlook send failed", 502);
      return NextResponse.json({ ok: true });
    }

    return err("Unknown action");
  } catch (e) {
    return err(e instanceof Error ? e.message : "Email operation failed", 500);
  }
}
