import { NextRequest, NextResponse } from "next/server";
import {
  resolveUserId,
  detectCalendarProvider,
  nangoProxy,
} from "@/lib/nango-proxy";
import { buildInternalCrmApiUrl } from "@/lib/server-crm-api";

function err(msg: string, status = 400) {
  return NextResponse.json({ error: msg }, { status });
}

type CalendarConnection = {
  provider: "google" | "microsoft";
  via: "nango" | "composio";
  integrationKey: string;
  connectionId: string;
};

/** Nango (legacy) or Composio — matches Integrations page connect flow. */
async function composioToolkitConnected(
  authHeader: string,
  toolkit: string,
): Promise<boolean> {
  try {
    const url = buildInternalCrmApiUrl(`/composio/connections/${toolkit}`);
    const res = await fetch(url, { headers: { Authorization: authHeader } });
    if (!res.ok) return false;
    const data = await res.json() as { connected?: boolean };
    return Boolean(data.connected);
  } catch {
    return false;
  }
}

async function detectCalendarConnection(
  _req: NextRequest,
  userId: string,
  authHeader: string | null,
): Promise<CalendarConnection | null> {
  if (authHeader) {
    const [googleConnected, outlookConnected] = await Promise.all([
      composioToolkitConnected(authHeader, "googlecalendar"),
      composioToolkitConnected(authHeader, "outlook"),
    ]);
    if (googleConnected) {
      return { provider: "google", via: "composio", integrationKey: "googlecalendar", connectionId: userId };
    }
    if (outlookConnected) {
      return { provider: "microsoft", via: "composio", integrationKey: "outlook", connectionId: userId };
    }
  }

  const nango = await detectCalendarProvider(userId);
  if (nango?.provider) {
    return {
      provider: nango.provider,
      via: "nango",
      integrationKey: nango.integrationKey,
      connectionId: nango.connectionId,
    };
  }

  return null;
}

async function composioCalendarFetch(
  authHeader: string,
  method: string,
  opts?: { query?: Record<string, string>; body?: Record<string, unknown> },
) {
  const qs = opts?.query ? `?${new URLSearchParams(opts.query).toString()}` : "";
  const url = buildInternalCrmApiUrl(`/composio/calendar/events${qs}`);
  const res = await fetch(url, {
    method,
    headers: { Authorization: authHeader, "Content-Type": "application/json" },
    body: opts?.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = `Calendar API ${res.status}`;
    try {
      const data = await res.json() as { detail?: string; error?: string };
      msg = data.detail || data.error || msg;
    } catch {
      msg = await res.text().catch(() => msg);
    }
    throw new Error(msg);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

function buildGCalEventPayload(body: EventBody) {
  const event: Record<string, unknown> = {
    summary: body.title,
    description: body.description ?? "",
    location: body.location ?? "",
    start: body.allDay
      ? { date: body.start.slice(0, 10) }
      : { dateTime: body.start, timeZone: body.timeZone ?? "UTC" },
    end: body.allDay
      ? { date: body.end.slice(0, 10) }
      : { dateTime: body.end, timeZone: body.timeZone ?? "UTC" },
  };
  if (body.attendees?.length) {
    event.attendees = body.attendees.map((e) => ({ email: e }));
  }
  return event;
}

function buildMSEventPayload(body: EventBody) {
  const event: Record<string, unknown> = {
    subject: body.title,
    body: { contentType: "Text", content: body.description ?? "" },
    location: { displayName: body.location ?? "" },
    start: { dateTime: body.start, timeZone: body.timeZone ?? "UTC" },
    end: { dateTime: body.end, timeZone: body.timeZone ?? "UTC" },
    isAllDay: body.allDay ?? false,
  };
  if (body.attendees?.length) {
    event.attendees = body.attendees.map((e) => ({
      emailAddress: { address: e },
      type: "required",
    }));
  }
  return event;
}

// ── Google Calendar ───────────────────────────────────────────────────────────

async function gCalListEvents(connectionId: string, opts: {
  timeMin?: string;
  timeMax?: string;
  maxResults?: number;
  q?: string;
}) {
  const params: Record<string, string> = {
    maxResults: String(opts.maxResults ?? 50),
    orderBy: "startTime",
    singleEvents: "true",
  };
  if (opts.timeMin) params.timeMin = opts.timeMin;
  if (opts.timeMax) params.timeMax = opts.timeMax;
  if (opts.q) params.q = opts.q;

  const res = await nangoProxy({
    integrationKey: "google-calendar",
    connectionId,
    path: "/calendar/v3/calendars/primary/events",
    params,
  });
  if (!res.ok) throw new Error(`GCal list ${res.status}`);
  const data = await res.json() as { items?: unknown[] };
  return (data.items ?? []) as GCalEvent[];
}

type GCalEvent = {
  id: string;
  summary?: string;
  description?: string;
  location?: string;
  start?: { dateTime?: string; date?: string; timeZone?: string };
  end?: { dateTime?: string; date?: string; timeZone?: string };
  attendees?: { email: string; displayName?: string; responseStatus?: string }[];
  htmlLink?: string;
  status?: string;
  colorId?: string;
};

function normalizeGCalEvent(e: GCalEvent) {
  return {
    id: e.id,
    title: e.summary ?? "(no title)",
    description: e.description ?? "",
    location: e.location ?? "",
    start: e.start?.dateTime ?? e.start?.date ?? "",
    end: e.end?.dateTime ?? e.end?.date ?? "",
    allDay: !e.start?.dateTime,
    attendees: (e.attendees ?? []).map((a) => ({ email: a.email, name: a.displayName ?? "" })),
    link: e.htmlLink ?? "",
    status: e.status ?? "confirmed",
    provider: "google" as const,
  };
}

async function gCalCreateEvent(connectionId: string, body: EventBody) {
  const event = buildGCalEventPayload(body);

  const res = await nangoProxy({
    integrationKey: "google-calendar",
    connectionId,
    method: "POST",
    path: "/calendar/v3/calendars/primary/events",
    params: { sendUpdates: body.attendees?.length ? "all" : "none" },
    body: event,
  });
  if (!res.ok) throw new Error(`GCal create ${res.status}`);
  return normalizeGCalEvent(await res.json() as GCalEvent);
}

async function gCalUpdateEvent(connectionId: string, eventId: string, body: EventBody) {
  const patch: Record<string, unknown> = {};
  if (body.title !== undefined) patch.summary = body.title;
  if (body.description !== undefined) patch.description = body.description;
  if (body.location !== undefined) patch.location = body.location;
  if (body.start) patch.start = body.allDay ? { date: body.start.slice(0, 10) } : { dateTime: body.start, timeZone: body.timeZone ?? "UTC" };
  if (body.end) patch.end = body.allDay ? { date: body.end.slice(0, 10) } : { dateTime: body.end, timeZone: body.timeZone ?? "UTC" };

  const res = await nangoProxy({
    integrationKey: "google-calendar",
    connectionId,
    method: "PATCH",
    path: `/calendar/v3/calendars/primary/events/${eventId}`,
    body: patch,
  });
  if (!res.ok) throw new Error(`GCal update ${res.status}`);
  return normalizeGCalEvent(await res.json() as GCalEvent);
}

async function gCalDeleteEvent(connectionId: string, eventId: string) {
  const res = await nangoProxy({
    integrationKey: "google-calendar",
    connectionId,
    method: "DELETE",
    path: `/calendar/v3/calendars/primary/events/${eventId}`,
  });
  if (!res.ok && res.status !== 204 && res.status !== 410) {
    throw new Error(`GCal delete ${res.status}`);
  }
}

// ── Microsoft Calendar ────────────────────────────────────────────────────────

type MSEvent = {
  id: string;
  subject?: string;
  bodyPreview?: string;
  body?: { content?: string };
  location?: { displayName?: string };
  start?: { dateTime?: string; timeZone?: string };
  end?: { dateTime?: string; timeZone?: string };
  isAllDay?: boolean;
  attendees?: { emailAddress?: { address?: string; name?: string } }[];
  webLink?: string;
  showAs?: string;
};

function normalizeMSEvent(e: MSEvent) {
  const startDT = e.start?.dateTime ? `${e.start.dateTime}Z` : "";
  const endDT = e.end?.dateTime ? `${e.end.dateTime}Z` : "";
  return {
    id: e.id,
    title: e.subject ?? "(no title)",
    description: e.bodyPreview ?? e.body?.content ?? "",
    location: e.location?.displayName ?? "",
    start: startDT,
    end: endDT,
    allDay: e.isAllDay ?? false,
    attendees: (e.attendees ?? []).map((a) => ({
      email: a.emailAddress?.address ?? "",
      name: a.emailAddress?.name ?? "",
    })),
    link: e.webLink ?? "",
    status: e.showAs ?? "busy",
    provider: "microsoft" as const,
  };
}

async function msListEvents(connectionId: string, opts: {
  timeMin?: string;
  timeMax?: string;
  top?: number;
}) {
  const params: Record<string, string> = {
    $top: String(opts.top ?? 50),
    $orderby: "start/dateTime asc",
  };
  const filters: string[] = [];
  if (opts.timeMin) filters.push(`start/dateTime ge '${opts.timeMin}'`);
  if (opts.timeMax) filters.push(`end/dateTime le '${opts.timeMax}'`);
  if (filters.length) params.$filter = filters.join(" and ");

  const res = await nangoProxy({
    integrationKey: "microsoft",
    connectionId,
    path: "/v1.0/me/events",
    params,
  });
  if (!res.ok) throw new Error(`MS events ${res.status}`);
  const data = await res.json() as { value?: unknown[] };
  return (data.value ?? []).map((e) => normalizeMSEvent(e as MSEvent));
}

async function msCreateEvent(connectionId: string, body: EventBody) {
  const event = buildMSEventPayload(body);

  const res = await nangoProxy({
    integrationKey: "microsoft",
    connectionId,
    method: "POST",
    path: "/v1.0/me/events",
    body: event,
  });
  if (!res.ok) throw new Error(`MS create event ${res.status}`);
  return normalizeMSEvent(await res.json() as MSEvent);
}

async function msUpdateEvent(connectionId: string, eventId: string, body: EventBody) {
  const patch: Record<string, unknown> = {};
  if (body.title !== undefined) patch.subject = body.title;
  if (body.description !== undefined) patch.body = { contentType: "Text", content: body.description };
  if (body.location !== undefined) patch.location = { displayName: body.location };
  if (body.start) patch.start = { dateTime: body.start, timeZone: body.timeZone ?? "UTC" };
  if (body.end) patch.end = { dateTime: body.end, timeZone: body.timeZone ?? "UTC" };

  const res = await nangoProxy({
    integrationKey: "microsoft",
    connectionId,
    method: "PATCH",
    path: `/v1.0/me/events/${eventId}`,
    body: patch,
  });
  if (!res.ok) throw new Error(`MS update event ${res.status}`);
  return normalizeMSEvent(await res.json() as MSEvent);
}

async function msDeleteEvent(connectionId: string, eventId: string) {
  const res = await nangoProxy({
    integrationKey: "microsoft",
    connectionId,
    method: "DELETE",
    path: `/v1.0/me/events/${eventId}`,
  });
  if (!res.ok && res.status !== 204) throw new Error(`MS delete event ${res.status}`);
}

// ── Types ─────────────────────────────────────────────────────────────────────

type EventBody = {
  title: string;
  description?: string;
  location?: string;
  start: string;
  end: string;
  allDay?: boolean;
  timeZone?: string;
  attendees?: string[];
};

/** Composio requires YYYY-MM-DDTHH:MM:SS (naive). */
function toComposioDateTime(value: string): string {
  const s = (value || "").trim();
  if (!s) return s;
  if (s.length <= 10 && !s.includes("T")) return `${s.slice(0, 10)}T00:00:00`;
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(s)) return `${s}:00`;
  const d = new Date(s);
  if (!Number.isNaN(d.getTime())) {
    return d.toISOString().replace(/\.\d{3}Z$/, "").replace(/Z$/, "");
  }
  return s.includes("T") ? s : `${s.slice(0, 10)}T00:00:00`;
}

function composioEventTimes(body: EventBody): { start: string; end: string } {
  const start = toComposioDateTime(body.start);
  let end = toComposioDateTime(body.end || body.start);
  if (body.allDay) {
    const startDay = start.slice(0, 10);
    let endDay = end.slice(0, 10);
    if (endDay < startDay) endDay = startDay;
    const endDate = new Date(`${endDay}T00:00:00`);
    endDate.setDate(endDate.getDate() + 1);
    end = `${endDate.toISOString().slice(0, 10)}T00:00:00`;
  } else if (end <= start) {
    const endDate = new Date(start.includes("T") ? start : `${start.slice(0, 10)}T00:00:00`);
    endDate.setHours(endDate.getHours() + 1);
    end = toComposioDateTime(endDate.toISOString());
  }
  return { start, end };
}

async function listCalendarEvents(
  req: NextRequest,
  cal: CalendarConnection,
  authHeader: string,
  opts: { timeMin?: string; timeMax?: string; q?: string },
) {
  if (cal.via === "nango") {
    if (cal.provider === "google") {
      return (await gCalListEvents(cal.connectionId, opts)).map(normalizeGCalEvent);
    }
    return msListEvents(cal.connectionId, opts);
  }

  if (cal.provider === "google" || cal.provider === "microsoft") {
    const data = await composioCalendarFetch(authHeader, "GET", {
      query: {
        provider: cal.provider,
        ...(opts.timeMin ? { timeMin: opts.timeMin } : {}),
        ...(opts.timeMax ? { timeMax: opts.timeMax } : {}),
      },
    });
    return (data.events ?? []) as ReturnType<typeof normalizeGCalEvent>[];
  }

  return [];
}

async function createCalendarEvent(
  req: NextRequest,
  cal: CalendarConnection,
  authHeader: string,
  body: EventBody,
) {
  if (cal.via === "nango") {
    return cal.provider === "google"
      ? gCalCreateEvent(cal.connectionId, body)
      : msCreateEvent(cal.connectionId, body);
  }

  const { start, end } = composioEventTimes(body);
  const payload = {
    title: body.title,
    description: body.description ?? "",
    location: body.location ?? "",
    start,
    end,
    allDay: body.allDay ?? false,
    timeZone: body.timeZone ?? "UTC",
    attendees: body.attendees ?? [],
    provider: cal.provider,
  };
  const data = await composioCalendarFetch(authHeader, "POST", { body: payload });
  return data.event as ReturnType<typeof normalizeGCalEvent>;
}

async function updateCalendarEvent(
  req: NextRequest,
  cal: CalendarConnection,
  authHeader: string,
  eventId: string,
  body: EventBody,
) {
  if (cal.via === "nango") {
    return cal.provider === "google"
      ? gCalUpdateEvent(cal.connectionId, eventId, body)
      : msUpdateEvent(cal.connectionId, eventId, body);
  }

  const { start, end } = composioEventTimes(body);
  const payload = {
    eventId,
    title: body.title,
    description: body.description,
    location: body.location,
    start,
    end,
    allDay: body.allDay ?? false,
    timeZone: body.timeZone ?? "UTC",
    attendees: body.attendees ?? [],
    provider: cal.provider,
  };
  const data = await composioCalendarFetch(authHeader, "PATCH", { body: payload });
  return data.event as ReturnType<typeof normalizeGCalEvent>;
}

async function deleteCalendarEvent(
  req: NextRequest,
  cal: CalendarConnection,
  authHeader: string,
  eventId: string,
) {
  if (cal.via === "nango") {
    if (cal.provider === "google") await gCalDeleteEvent(cal.connectionId, eventId);
    else await msDeleteEvent(cal.connectionId, eventId);
    return;
  }

  await composioCalendarFetch(authHeader, "DELETE", {
    query: { eventId, provider: cal.provider },
  });
}

// ── Route Handlers ────────────────────────────────────────────────────────────

/** GET /api/calendar/events?timeMin=...&timeMax=...&q=... */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return err("Unauthorized", 401);

  const cal = await detectCalendarConnection(req, userId, auth);
  if (!cal) return NextResponse.json({ events: [], provider: null, connected: false });

  const sp = req.nextUrl.searchParams;
  const timeMin = sp.get("timeMin") ?? new Date(Date.now() - 7 * 86400000).toISOString();
  const timeMax = sp.get("timeMax") ?? new Date(Date.now() + 60 * 86400000).toISOString();
  const q = sp.get("q") ?? "";

  try {
    const events = await listCalendarEvents(req, cal, auth!, { timeMin, timeMax, q: q || undefined });
    return NextResponse.json({ events, provider: cal.provider, connected: true });
  } catch (e) {
    return err(e instanceof Error ? e.message : "Failed to load events", 500);
  }
}

/** POST /api/calendar/events — create */
export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return err("Unauthorized", 401);

  const cal = await detectCalendarConnection(req, userId, auth);
  if (!cal) return err("No calendar connected", 400);

  const body = await req.json() as EventBody;
  if (!body.title || !body.start || !body.end) return err("title, start, end required");

  try {
    const event = await createCalendarEvent(req, cal, auth!, body);
    return NextResponse.json({ event });
  } catch (e) {
    return err(e instanceof Error ? e.message : "Create failed", 500);
  }
}

/** PATCH /api/calendar/events — update (eventId in body) */
export async function PATCH(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return err("Unauthorized", 401);

  const cal = await detectCalendarConnection(req, userId, auth);
  if (!cal) return err("No calendar connected", 400);

  const body = await req.json() as EventBody & { eventId: string };
  if (!body.eventId) return err("eventId required");

  try {
    const event = await updateCalendarEvent(req, cal, auth!, body.eventId, body);
    return NextResponse.json({ event });
  } catch (e) {
    return err(e instanceof Error ? e.message : "Update failed", 500);
  }
}

/** DELETE /api/calendar/events?eventId=... */
export async function DELETE(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return err("Unauthorized", 401);

  const cal = await detectCalendarConnection(req, userId, auth);
  if (!cal) return err("No calendar connected", 400);

  const eventId = req.nextUrl.searchParams.get("eventId");
  if (!eventId) return err("eventId required");

  try {
    await deleteCalendarEvent(req, cal, auth!, eventId);
    return NextResponse.json({ ok: true });
  } catch (e) {
    return err(e instanceof Error ? e.message : "Delete failed", 500);
  }
}
