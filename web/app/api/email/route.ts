import { NextRequest, NextResponse } from "next/server";
import {
  resolveUserId,
  detectEmailProvider,
  nangoProxy,
} from "@/lib/nango-proxy";

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

/** GET /api/email?q=...&limit=... */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return err("Unauthorized", 401);

  const provider = await detectEmailProvider(userId);
  if (!provider) return NextResponse.json({ threads: [], provider: null, connected: false });

  const q = req.nextUrl.searchParams.get("q") ?? "";
  const limit = Math.min(parseInt(req.nextUrl.searchParams.get("limit") ?? "25"), 50);

  try {
    if (provider.provider === "gmail") {
      const rawThreads = await gmailListThreads(provider.connectionId, q, limit);

      // Fetch first message of each thread for headers
      const threads = await Promise.all(
        rawThreads.slice(0, limit).map(async (t) => {
          try {
            const full = await gmailGetThread(provider.connectionId, t.id);
            const first = full.messages[0];
            const last  = full.messages[full.messages.length - 1];
            const hdrs  = last.payload.headers;
            const unread = last.labelIds?.includes("UNREAD") ?? false;
            return {
              id:          t.id,
              subject:     headerVal(hdrs, "Subject") || "(no subject)",
              from:        headerVal(last.payload.headers, "From"),
              date:        new Date(parseInt(last.internalDate)).toISOString(),
              snippet:     t.snippet,
              unread,
              messageCount: full.messages.length,
              provider:    "gmail",
            };
          } catch {
            return {
              id: t.id, subject: "(error)", from: "", date: "", snippet: t.snippet,
              unread: false, messageCount: 1, provider: "gmail",
            };
          }
        }),
      );
      return NextResponse.json({ threads, provider: "gmail", connected: true });
    }

    // Microsoft
    const msgs = await msListMessages(provider.connectionId, q, limit) as Record<string, unknown>[];
    const threads = msgs.map((m) => ({
      id:           m.id as string,
      subject:      (m.subject as string) || "(no subject)",
      from:         ((m.from as { emailAddress?: { name?: string; address?: string } })?.emailAddress?.name || (m.from as { emailAddress?: { address?: string } })?.emailAddress?.address) ?? "",
      date:         m.receivedDateTime as string,
      snippet:      (m.bodyPreview as string) ?? "",
      unread:       m.isRead === false,
      messageCount: 1,
      provider:     "microsoft",
    }));
    return NextResponse.json({ threads, provider: "microsoft", connected: true });
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
    action: "get_thread" | "send" | "mark_read";
    threadId?: string;
    messageId?: string;
    raw?: string;          // base64url RFC-2822 for Gmail send
    to?: string;
    subject?: string;
    replyBody?: string;
    inReplyTo?: string;
  };

  const provider = await detectEmailProvider(userId);
  if (!provider) return err("No email account connected", 400);

  try {
    if (body.action === "get_thread") {
      if (!body.threadId) return err("threadId required");

      if (provider.provider === "gmail") {
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
        await gmailMarkRead(provider.connectionId, body.messageId);
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
        if (!body.raw) return err("raw (base64url email) required for Gmail send");
        const res = await gmailSend(provider.connectionId, body.raw);
        if (!res.ok) return err("Gmail send failed", 502);
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
