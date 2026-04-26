"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CalendarDays, ChevronLeft, ChevronRight, Plus, RefreshCw,
  Sparkles, X, Loader2, Clock, MapPin, Users, Trash2, Edit3,
  Zap, LayoutList, Grid3x3, Calendar, Search, Star,
  CheckCircle2, Circle, ArrowRight, Mic,
} from "lucide-react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

type CalEvent = {
  id: string;
  title: string;
  description: string;
  location: string;
  start: string;
  end: string;
  allDay: boolean;
  attendees: { email: string; name: string }[];
  link: string;
  status: string;
  provider: "google" | "microsoft";
};

type View = "month" | "week" | "agenda";

type EventFormData = {
  title: string;
  description: string;
  location: string;
  start: string;
  end: string;
  allDay: boolean;
  attendees: string;
  timeZone: string;
  color: string;
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch(path: string, opts: RequestInit = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(opts.headers ?? {}) },
  });
  if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
  if (res.status === 204) return {};
  return res.json();
}

function addDays(d: Date, n: number) {
  const r = new Date(d); r.setDate(r.getDate() + n); return r;
}
function addMonths(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}
function startOfWeek(d: Date) {
  const day = d.getDay();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - day);
}
function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function isoDay(d: Date) { return d.toISOString().slice(0, 10); }
function eventDay(e: CalEvent) { return (e.start || "").slice(0, 10); }

function formatTime(iso: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function formatDuration(start: string, end: string) {
  const diff = (new Date(end).getTime() - new Date(start).getTime()) / 60000;
  if (diff <= 0) return "";
  const h = Math.floor(diff / 60), m = diff % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}
function toLocalInput(d: Date) {
  const off = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
}

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const DAYS_SHORT = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

// Smart color by keyword
const KEYWORD_COLORS: [string, string][] = [
  ["meeting", "bg-brand"], ["standup", "bg-brand"], ["sync", "bg-brand"],
  ["call", "bg-brand"], ["interview", "bg-brand"],
  ["lunch", "bg-emerald-500"], ["dinner", "bg-emerald-500"], ["coffee", "bg-emerald-500"],
  ["deadline", "bg-rose-500"], ["review", "bg-rose-500"], ["demo", "bg-rose-500"],
  ["travel", "bg-amber-500"], ["flight", "bg-amber-500"],
  ["birthday", "bg-pink-500"], ["anniversary", "bg-pink-500"],
];

const ALL_EVENT_COLORS = [
  { label: "Indigo", value: "bg-brand" },
  { label: "Violet", value: "bg-brand" },
  { label: "Emerald", value: "bg-emerald-500" },
  { label: "Rose", value: "bg-rose-500" },
  { label: "Amber", value: "bg-amber-500" },
  { label: "Cyan", value: "bg-cyan-500" },
  { label: "Pink", value: "bg-pink-500" },
  { label: "Orange", value: "bg-orange-500" },
];

function smartColor(title: string, override?: string) {
  if (override && override !== "auto") return override;
  const lower = title.toLowerCase();
  for (const [kw, color] of KEYWORD_COLORS) {
    if (lower.includes(kw)) return color;
  }
  let h = 0;
  for (let i = 0; i < title.length; i++) h = (h * 31 + title.charCodeAt(i)) & 0xffffffff;
  return ALL_EVENT_COLORS[Math.abs(h) % ALL_EVENT_COLORS.length].value;
}

function defaultForm(prefillDate?: string): EventFormData {
  const base = prefillDate ? new Date(prefillDate) : new Date();
  base.setMinutes(0, 0, 0);
  const end = new Date(base.getTime() + 3600000);
  return {
    title: "", description: "", location: "",
    start: toLocalInput(base), end: toLocalInput(end),
    allDay: false, attendees: "",
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    color: "auto",
  };
}

// ── No-connection ─────────────────────────────────────────────────────────────

function NoConnection() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-8">
      <div className="w-14 h-14 rounded-2xl bg-slate-800 flex items-center justify-center">
        <CalendarDays size={26} className="text-slate-400" />
      </div>
      <div>
        <p className="font-semibold text-slate-200">No calendar connected</p>
        <p className="text-sm text-slate-500 mt-1 leading-relaxed">
          Go to{" "}
          <a href="/dashboard/integrations" className="text-brand underline underline-offset-2">Integrations</a>
          {" "}and connect Google Calendar or Outlook.
        </p>
      </div>
    </div>
  );
}

// ── Event modal ───────────────────────────────────────────────────────────────

function EventModal({
  initial, onSave, onDelete, onClose, saving, deleting, editEvent, onAiSuggest,
}: {
  initial: EventFormData;
  onSave: (f: EventFormData) => void;
  onDelete?: () => void;
  onClose: () => void;
  saving: boolean; deleting: boolean;
  editEvent: CalEvent | null;
  onAiSuggest: (title: string) => Promise<string>;
}) {
  const [form, setForm] = useState<EventFormData>(initial);
  const [suggesting, setSuggesting] = useState(false);
  const [naturalInput, setNaturalInput] = useState("");
  const [parsing, setParsing] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => { titleRef.current?.focus(); }, []);

  function set<K extends keyof EventFormData>(k: K, v: EventFormData[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  async function handleSuggest() {
    if (!form.title) { toast.error("Enter a title first"); return; }
    setSuggesting(true);
    try { set("description", await onAiSuggest(form.title)); }
    finally { setSuggesting(false); }
  }

  async function parseNatural() {
    if (!naturalInput.trim()) return;
    setParsing(true);
    try {
      const BACKEND = process.env.NEXT_PUBLIC_API_URL || "/api";
      const token = getToken();
      const now = new Date().toISOString();
      const res = await fetch(`${BACKEND}/assistant/ai-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          prompt: `Parse this natural language event description into JSON. Current time: ${now}.
Return ONLY valid JSON with keys: title, start (ISO 8601 local), end (ISO 8601 local), location, description.
Input: "${naturalInput}"`,
        }),
      });
      if (res.ok) {
        const data = await res.json() as { reply?: string; draft?: string; text?: string };
        const raw = data.reply ?? data.draft ?? data.text ?? "";
        const match = raw.match(/\{[\s\S]*\}/);
        if (match) {
          const parsed = JSON.parse(match[0]) as Partial<EventFormData>;
          setForm((p) => ({
            ...p,
            title: parsed.title ?? p.title,
            start: parsed.start ? toLocalInput(new Date(parsed.start)) : p.start,
            end: parsed.end ? toLocalInput(new Date(parsed.end)) : p.end,
            location: parsed.location ?? p.location,
            description: parsed.description ?? p.description,
          }));
          setNaturalInput("");
          toast.success("Event details filled in!");
        }
      }
    } catch { toast.error("Couldn't parse — fill in manually"); }
    finally { setParsing(false); }
  }

  const previewColor = smartColor(form.title, form.color === "auto" ? undefined : form.color);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md shadow-2xl flex flex-col max-h-[90vh]">
        {/* Color strip */}
        <div className={cn("h-1 w-full rounded-t-2xl transition-colors", previewColor)} />

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
          <h2 className="font-semibold text-sm">{editEvent ? "Edit event" : "New event"}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-100"><X size={15} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {/* Natural language input */}
          {!editEvent && (
            <div className="flex items-center gap-2 bg-brand-ink/40 border border-brand-ink/40 rounded-xl px-3 py-2">
              <Sparkles size={12} className="text-brand shrink-0" />
              <input
                value={naturalInput}
                onChange={(e) => setNaturalInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); parseNatural(); } }}
                placeholder='Try "Meeting with John tomorrow at 3pm"…'
                className="flex-1 bg-transparent text-xs text-slate-300 placeholder-slate-600 outline-none"
              />
              <button
                onClick={parseNatural}
                disabled={parsing || !naturalInput.trim()}
                className="text-[10px] text-brand hover:text-brand/50 disabled:opacity-40 flex items-center gap-1 shrink-0"
              >
                {parsing ? <Loader2 size={10} className="animate-spin" /> : <ArrowRight size={10} />}
                Fill
              </button>
            </div>
          )}

          {/* Title */}
          <input
            ref={titleRef}
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
            placeholder="Event title"
            className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-4 py-2.5 outline-none focus:ring-1 focus:ring-brand border border-slate-700 font-medium"
          />

          {/* Color picker */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500">Color</span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => set("color", "auto")}
                className={cn("w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all", form.color === "auto" ? "border-white" : "border-transparent")}
                style={{ background: "linear-gradient(135deg, #6366f1, #10b981, #f59e0b)" }}
                title="Auto (smart)"
              />
              {ALL_EVENT_COLORS.map((c) => (
                <button
                  key={c.value}
                  onClick={() => set("color", c.value)}
                  className={cn("w-5 h-5 rounded-full border-2 transition-all", c.value, form.color === c.value ? "border-white scale-110" : "border-transparent")}
                  title={c.label}
                />
              ))}
            </div>
          </div>

          {/* All day */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={form.allDay} onChange={(e) => set("allDay", e.target.checked)} className="accent-brand" />
            <span className="text-xs text-slate-400">All day</span>
          </label>

          {/* Start / End */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Start</label>
              <input
                type={form.allDay ? "date" : "datetime-local"}
                value={form.start}
                onChange={(e) => set("start", e.target.value)}
                className="w-full bg-slate-800 text-xs text-slate-200 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">End</label>
              <input
                type={form.allDay ? "date" : "datetime-local"}
                value={form.end}
                onChange={(e) => set("end", e.target.value)}
                className="w-full bg-slate-800 text-xs text-slate-200 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700"
              />
            </div>
          </div>

          {/* Location */}
          <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-xl px-3 py-2">
            <MapPin size={12} className="text-slate-500 shrink-0" />
            <input value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="Location or meeting link" className="flex-1 bg-transparent text-xs text-slate-200 placeholder-slate-500 outline-none" />
          </div>

          {/* Attendees */}
          <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-xl px-3 py-2">
            <Users size={12} className="text-slate-500 shrink-0" />
            <input value={form.attendees} onChange={(e) => set("attendees", e.target.value)} placeholder="Attendees (comma-separated emails)" className="flex-1 bg-transparent text-xs text-slate-200 placeholder-slate-500 outline-none" />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[10px] text-slate-500">Description</label>
              <button onClick={handleSuggest} disabled={suggesting} className="flex items-center gap-1 text-[10px] text-brand hover:text-brand/50 disabled:opacity-40 transition-colors">
                {suggesting ? <Loader2 size={9} className="animate-spin" /> : <Sparkles size={9} />}
                AI suggest
              </button>
            </div>
            <textarea
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder="Agenda, notes, context…"
              rows={3}
              className="w-full bg-slate-800 text-xs text-slate-200 placeholder-slate-500 rounded-xl border border-slate-700 px-3 py-2 outline-none focus:ring-1 focus:ring-brand resize-none"
            />
          </div>
        </div>

        <div className="flex items-center gap-2 px-5 pb-5 pt-2 border-t border-slate-800">
          {editEvent && onDelete && (
            <button onClick={onDelete} disabled={deleting} className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs text-rose-400 hover:bg-rose-900/20 border border-rose-800/30 disabled:opacity-50 transition-colors">
              {deleting ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
              Delete
            </button>
          )}
          <div className="flex-1" />
          <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs text-slate-400 hover:text-slate-100 transition-colors">Cancel</button>
          <button
            onClick={() => onSave(form)}
            disabled={saving || !form.title.trim()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold disabled:opacity-40 transition-colors"
          >
            {saving ? <Loader2 size={11} className="animate-spin" /> : null}
            {editEvent ? "Save changes" : "Create event"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Mini calendar ─────────────────────────────────────────────────────────────

function MiniCalendar({ cursor, setCursor, events, onDayClick }: {
  cursor: Date;
  setCursor: (d: Date) => void;
  events: CalEvent[];
  onDayClick: (d: Date) => void;
}) {
  const [mini, setMini] = useState(new Date(cursor));
  const todayStr = isoDay(new Date());

  function miniDays() {
    const first = startOfMonth(mini);
    const start = startOfWeek(first);
    return Array.from({ length: 42 }, (_, i) => addDays(start, i));
  }

  const eventDays = new Set(events.map(eventDay));

  return (
    <div className="select-none">
      {/* Month nav */}
      <div className="flex items-center justify-between mb-2">
        <button onClick={() => setMini(addMonths(mini, -1))} className="p-1 rounded hover:bg-slate-800 text-slate-400"><ChevronLeft size={12} /></button>
        <button
          onClick={() => { setMini(new Date()); setCursor(new Date()); }}
          className="text-xs font-semibold text-slate-300 hover:text-brand transition-colors"
        >
          {MONTHS_SHORT[mini.getMonth()]} {mini.getFullYear()}
        </button>
        <button onClick={() => setMini(addMonths(mini, 1))} className="p-1 rounded hover:bg-slate-800 text-slate-400"><ChevronRight size={12} /></button>
      </div>
      {/* Day headers */}
      <div className="grid grid-cols-7 mb-1">
        {DAYS_SHORT.map((d) => <div key={d} className="text-[9px] text-slate-600 text-center">{d[0]}</div>)}
      </div>
      {/* Days */}
      <div className="grid grid-cols-7 gap-y-0.5">
        {miniDays().map((day) => {
          const ds = isoDay(day);
          const isToday = ds === todayStr;
          const isCursor = ds === isoDay(cursor);
          const hasEvents = eventDays.has(ds);
          const inMonth = day.getMonth() === mini.getMonth();
          return (
            <button
              key={ds}
              onClick={() => { setCursor(day); onDayClick(day); }}
              className={cn(
                "text-[11px] w-6 h-6 mx-auto rounded-full flex items-center justify-center transition-colors relative",
                !inMonth && "opacity-30",
                isToday && !isCursor && "text-brand font-bold",
                isCursor && "bg-brand-dark text-white font-bold",
                !isToday && !isCursor && "text-slate-400 hover:bg-slate-800"
              )}
            >
              {day.getDate()}
              {hasEvents && !isCursor && (
                <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-brand" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Agenda view ───────────────────────────────────────────────────────────────

function AgendaView({ events, onEventClick, onDayClick, eventColor: getColor }: {
  events: CalEvent[];
  onEventClick: (e: CalEvent) => void;
  onDayClick: (d: Date) => void;
  eventColor: (e: CalEvent) => string;
}) {
  const todayStr = isoDay(new Date());
  // Group by date
  const grouped = new Map<string, CalEvent[]>();
  const sorted = [...events].sort((a, b) => a.start.localeCompare(b.start));
  for (const ev of sorted) {
    const day = eventDay(ev);
    if (!grouped.has(day)) grouped.set(day, []);
    grouped.get(day)!.push(ev);
  }
  const days = [...grouped.keys()].sort();

  if (days.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-700">
        <CalendarDays size={32} />
        <p className="text-sm text-slate-600">No events in this period</p>
        <button onClick={() => onDayClick(new Date())} className="text-xs text-brand hover:text-brand/50">
          + Add an event
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
      {days.map((day) => {
        const date = new Date(day + "T00:00:00");
        const isToday = day === todayStr;
        const isPast = day < todayStr;
        const dayEvents = grouped.get(day)!;
        return (
          <div key={day}>
            {/* Day label */}
            <div className="flex items-center gap-3 mb-2">
              <div className={cn(
                "flex items-center gap-2 text-xs font-semibold",
                isToday ? "text-brand" : isPast ? "text-slate-600" : "text-slate-300"
              )}>
                <span className={cn(
                  "w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold",
                  isToday ? "bg-brand-dark text-white" : "text-slate-500"
                )}>
                  {date.getDate()}
                </span>
                <div>
                  <p>{DAYS_SHORT[date.getDay()]}</p>
                  <p className="text-[10px] font-normal text-slate-500">{MONTHS_SHORT[date.getMonth()]} {date.getFullYear()}</p>
                </div>
              </div>
              <div className="flex-1 h-px bg-slate-800" />
              {isToday && <span className="text-[10px] text-brand font-medium bg-brand-ink/50 px-2 py-0.5 rounded-full">Today</span>}
            </div>
            {/* Events */}
            <div className="space-y-2 ml-9">
              {dayEvents.map((ev) => (
                <button
                  key={ev.id}
                  onClick={() => onEventClick(ev)}
                  className={cn(
                    "w-full text-left rounded-xl p-3 border transition-all hover:shadow-md group",
                    isPast ? "border-slate-800 bg-slate-900/50 opacity-70" : "border-slate-700 bg-slate-900 hover:border-slate-600"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className={cn("w-1 self-stretch rounded-full shrink-0 mt-0.5", getColor(ev))} />
                    <div className="flex-1 min-w-0">
                      <p className={cn("text-sm font-medium truncate", isPast ? "text-slate-500" : "text-slate-200")}>
                        {ev.title}
                      </p>
                      <div className="flex items-center gap-3 mt-1 flex-wrap">
                        {!ev.allDay && (
                          <span className="flex items-center gap-1 text-[11px] text-slate-500">
                            <Clock size={10} /> {formatTime(ev.start)}{ev.end && ` – ${formatTime(ev.end)}`}
                            {ev.start && ev.end && <span className="text-slate-700">· {formatDuration(ev.start, ev.end)}</span>}
                          </span>
                        )}
                        {ev.allDay && <span className="text-[11px] text-slate-500">All day</span>}
                        {ev.location && (
                          <span className="flex items-center gap-1 text-[11px] text-slate-500">
                            <MapPin size={10} /> <span className="truncate max-w-[150px]">{ev.location}</span>
                          </span>
                        )}
                        {ev.attendees.length > 0 && (
                          <span className="flex items-center gap-1 text-[11px] text-slate-500">
                            <Users size={10} /> {ev.attendees.length}
                          </span>
                        )}
                      </div>
                    </div>
                    <Edit3 size={12} className="text-slate-700 group-hover:text-slate-500 transition-colors shrink-0 mt-0.5" />
                  </div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Month grid ────────────────────────────────────────────────────────────────

function MonthGrid({ days, cursor, todayStr, eventsForDay, onDayClick, onEventClick, eventColor: getColor }: {
  days: Date[]; cursor: Date; todayStr: string;
  eventsForDay: (d: Date) => CalEvent[];
  onDayClick: (d: Date) => void;
  onEventClick: (e: CalEvent) => void;
  eventColor: (e: CalEvent) => string;
}) {
  const curMonth = cursor.getMonth();
  return (
    <div className="h-full flex flex-col">
      <div className="grid grid-cols-7 border-b border-slate-800">
        {DAYS_SHORT.map((d) => (
          <div key={d} className="py-2 text-center text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{d}</div>
        ))}
      </div>
      <div className="flex-1 grid grid-rows-6">
        {Array.from({ length: 6 }, (_, wi) => (
          <div key={wi} className="grid grid-cols-7 border-b border-slate-800/40 last:border-0">
            {days.slice(wi * 7, wi * 7 + 7).map((day) => {
              const ds = isoDay(day);
              const isToday = ds === todayStr;
              const inMonth = day.getMonth() === curMonth;
              const dayEvents = eventsForDay(day);
              return (
                <div
                  key={ds}
                  onClick={() => onDayClick(day)}
                  className={cn(
                    "border-r border-slate-800/40 last:border-0 p-1.5 cursor-pointer hover:bg-slate-800/20 transition-colors min-h-[80px]",
                    !inMonth && "opacity-35",
                    isToday && "bg-brand-ink/20"
                  )}
                >
                  <div className={cn(
                    "text-[11px] font-semibold w-6 h-6 flex items-center justify-center rounded-full mb-1",
                    isToday ? "bg-brand-dark text-white" : "text-slate-500"
                  )}>
                    {day.getDate()}
                  </div>
                  <div className="space-y-0.5">
                    {dayEvents.slice(0, 3).map((ev) => (
                      <button
                        key={ev.id}
                        onClick={(e) => { e.stopPropagation(); onEventClick(ev); }}
                        className={cn("w-full text-left text-[10px] font-medium px-1.5 py-0.5 rounded text-white truncate hover:brightness-110 transition-all", getColor(ev))}
                      >
                        {ev.allDay ? ev.title : `${formatTime(ev.start)} ${ev.title}`}
                      </button>
                    ))}
                    {dayEvents.length > 3 && (
                      <p className="text-[10px] text-slate-600 px-1">+{dayEvents.length - 3} more</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Week grid ─────────────────────────────────────────────────────────────────

function WeekGrid({ days, todayStr, eventsForDay, onDayClick, onEventClick, eventColor: getColor }: {
  days: Date[]; todayStr: string;
  eventsForDay: (d: Date) => CalEvent[];
  onDayClick: (d: Date) => void;
  onEventClick: (e: CalEvent) => void;
  eventColor: (e: CalEvent) => string;
}) {
  return (
    <div className="h-full flex flex-col">
      <div className="grid grid-cols-7 border-b border-slate-800">
        {days.map((day) => {
          const ds = isoDay(day);
          const isToday = ds === todayStr;
          return (
            <div key={ds} className="py-2 text-center border-r border-slate-800 last:border-0">
              <p className="text-[10px] text-slate-600 uppercase">{DAYS_SHORT[day.getDay()]}</p>
              <div className={cn(
                "text-sm font-semibold w-8 h-8 mx-auto flex items-center justify-center rounded-full mt-0.5",
                isToday ? "bg-brand-dark text-white" : "text-slate-400 hover:bg-slate-800 cursor-pointer"
              )} onClick={() => onDayClick(day)}>
                {day.getDate()}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex-1 grid grid-cols-7 overflow-y-auto">
        {days.map((day) => {
          const ds = isoDay(day);
          const isToday = ds === todayStr;
          const dayEvents = eventsForDay(day);
          return (
            <div
              key={ds}
              onClick={() => onDayClick(day)}
              className={cn("border-r border-slate-800 last:border-0 p-2 space-y-1.5 cursor-pointer min-h-[200px] hover:bg-slate-800/10 transition-colors", isToday && "bg-brand-ink/10")}
            >
              {dayEvents.length === 0 && (
                <div className="flex items-center justify-center h-16">
                  <Plus size={14} className="text-slate-800" />
                </div>
              )}
              {dayEvents.map((ev) => (
                <button
                  key={ev.id}
                  onClick={(e) => { e.stopPropagation(); onEventClick(ev); }}
                  className={cn("w-full text-left rounded-xl p-2 text-white text-xs space-y-0.5 hover:brightness-110 transition-all", getColor(ev))}
                >
                  <p className="font-semibold truncate">{ev.title}</p>
                  {!ev.allDay && <p className="opacity-80 text-[10px]">{formatTime(ev.start)}{ev.end && ` – ${formatTime(ev.end)}`}</p>}
                  {ev.location && <p className="opacity-70 text-[10px] truncate">{ev.location}</p>}
                </button>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CalendarPage() {
  const [view, setView] = useState<View>("month");
  const [cursor, setCursor] = useState(new Date());
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [provider, setProvider] = useState<"google" | "microsoft" | null>(null);

  const [showModal, setShowModal] = useState(false);
  const [editEvent, setEditEvent] = useState<CalEvent | null>(null);
  const [prefillDate, setPrefillDate] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<CalEvent | null>(null);

  // Local event colors (overrides)
  const [eventColors, setEventColors] = useState<Record<string, string>>({});

  useEffect(() => {
    try {
      const saved = localStorage.getItem("cal_event_colors");
      if (saved) setEventColors(JSON.parse(saved) as Record<string, string>);
    } catch { /* ignore */ }
  }, []);

  function getEventColor(ev: CalEvent) {
    return eventColors[ev.id] ?? smartColor(ev.title);
  }

  const timeRange = useCallback(() => {
    if (view === "month") {
      const s = startOfMonth(cursor);
      return { timeMin: addDays(s, -7).toISOString(), timeMax: addDays(addMonths(cursor, 1), 7).toISOString() };
    }
    if (view === "week") {
      const s = startOfWeek(cursor);
      return { timeMin: s.toISOString(), timeMax: addDays(s, 7).toISOString() };
    }
    // Agenda: next 60 days
    return { timeMin: addDays(new Date(), -1).toISOString(), timeMax: addDays(new Date(), 60).toISOString() };
  }, [view, cursor]);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const { timeMin, timeMax } = timeRange();
      const res = await apiFetch(`/api/calendar/events?timeMin=${encodeURIComponent(timeMin)}&timeMax=${encodeURIComponent(timeMax)}`) as {
        events: CalEvent[]; provider: "google" | "microsoft" | null; connected: boolean;
      };
      setConnected(res.connected);
      setProvider(res.provider ?? null);
      setEvents(res.events ?? []);
    } catch {
      toast.error("Failed to load calendar");
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => { loadEvents(); }, [loadEvents]);

  async function handleAiSuggest(title: string) {
    const BACKEND = process.env.NEXT_PUBLIC_API_URL || "/api";
    const token = getToken();
    try {
      const res = await fetch(`${BACKEND}/assistant/ai-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ prompt: `Write a short, useful description for a calendar event titled "${title}". Include purpose, what to prepare, max 60 words.` }),
      });
      if (!res.ok) return "";
      const data = await res.json() as { reply?: string; draft?: string; text?: string };
      return data.reply ?? data.draft ?? data.text ?? "";
    } catch { return ""; }
  }

  async function handleSave(form: EventFormData) {
    setSaving(true);
    try {
      const attendees = form.attendees.split(",").map((e) => e.trim()).filter(Boolean);
      const payload = {
        title: form.title, description: form.description,
        location: form.location,
        start: form.allDay ? form.start.slice(0, 10) : new Date(form.start).toISOString(),
        end: form.allDay ? form.end.slice(0, 10) : new Date(form.end).toISOString(),
        allDay: form.allDay, timeZone: form.timeZone, attendees,
        ...(editEvent ? { eventId: editEvent.id } : {}),
      };

      const result = await apiFetch("/api/calendar/events", {
        method: editEvent ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      }) as { event?: CalEvent };

      // Save local color preference
      const targetId = result.event?.id ?? editEvent?.id;
      if (targetId && form.color && form.color !== "auto") {
        const updated = { ...eventColors, [targetId]: form.color };
        setEventColors(updated);
        localStorage.setItem("cal_event_colors", JSON.stringify(updated));
      }

      toast.success(editEvent ? "Event updated" : "Event created");
      setShowModal(false); setEditEvent(null); setSelectedEvent(null);
      await loadEvents();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save");
    } finally { setSaving(false); }
  }

  async function handleDelete() {
    if (!editEvent) return;
    setDeleting(true);
    try {
      await apiFetch(`/api/calendar/events?eventId=${encodeURIComponent(editEvent.id)}`, { method: "DELETE" });
      toast.success("Deleted");
      setShowModal(false); setEditEvent(null); setSelectedEvent(null);
      await loadEvents();
    } catch { toast.error("Delete failed"); }
    finally { setDeleting(false); }
  }

  function openCreate(date?: string) {
    setPrefillDate(date); setEditEvent(null); setShowModal(true);
  }
  function openEdit(event: CalEvent) {
    setEditEvent(event); setPrefillDate(undefined); setShowModal(true); setSelectedEvent(null);
  }

  function prev() {
    if (view === "month") setCursor((d) => addMonths(d, -1));
    else if (view === "week") setCursor((d) => addDays(d, -7));
    else setCursor((d) => addDays(d, -30));
  }
  function next() {
    if (view === "month") setCursor((d) => addMonths(d, 1));
    else if (view === "week") setCursor((d) => addDays(d, 7));
    else setCursor((d) => addDays(d, 30));
  }
  function goToday() { setCursor(new Date()); }

  function monthDays() {
    const first = startOfMonth(cursor);
    const start = startOfWeek(first);
    return Array.from({ length: 42 }, (_, i) => addDays(start, i));
  }
  function weekDays() {
    const start = startOfWeek(cursor);
    return Array.from({ length: 7 }, (_, i) => addDays(start, i));
  }

  const todayStr = isoDay(new Date());

  function eventsForDay(d: Date) {
    const ds = isoDay(d);
    return events.filter((e) => eventDay(e) === ds);
  }

  // Today's upcoming events
  const todayEvents = events
    .filter((e) => eventDay(e) === todayStr && !e.allDay)
    .sort((a, b) => a.start.localeCompare(b.start))
    .slice(0, 3);

  const headerTitle = view === "month"
    ? `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`
    : view === "week"
    ? (() => {
        const days = weekDays();
        const s = days[0], e = days[6];
        return s.getMonth() === e.getMonth()
          ? `${MONTHS[s.getMonth()]} ${s.getDate()}–${e.getDate()}, ${s.getFullYear()}`
          : `${MONTHS_SHORT[s.getMonth()]} ${s.getDate()} – ${MONTHS_SHORT[e.getMonth()]} ${e.getDate()}, ${e.getFullYear()}`;
      })()
    : "Upcoming Events";

  return (
    <div className="flex h-full bg-slate-950 text-slate-100 overflow-hidden">

      {/* ── Left sidebar ─────────────────────────────────────────────────── */}
      <div className="w-56 border-r border-slate-800 bg-slate-900 flex-col p-4 space-y-5 hidden lg:flex shrink-0">
        {/* New event button */}
        <button
          onClick={() => openCreate()}
          disabled={connected === false}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-brand-dark hover:bg-brand text-white text-sm font-semibold disabled:opacity-40 transition-colors shadow-lg shadow-brand-ink/30"
        >
          <Plus size={16} /> New Event
        </button>

        {/* Mini calendar */}
        <MiniCalendar
          cursor={cursor}
          setCursor={setCursor}
          events={events}
          onDayClick={(d) => { setCursor(d); if (view === "month") setView("week"); }}
        />

        {/* Today's schedule */}
        <div>
          <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-wider mb-2">Today</p>
          {loading ? (
            <div className="flex justify-center py-2"><Loader2 size={14} className="animate-spin text-slate-700" /></div>
          ) : todayEvents.length === 0 ? (
            <p className="text-[11px] text-slate-700">No events today</p>
          ) : (
            <div className="space-y-1.5">
              {todayEvents.map((ev) => (
                <button
                  key={ev.id}
                  onClick={() => setSelectedEvent(ev)}
                  className="w-full text-left group"
                >
                  <div className="flex items-center gap-2">
                    <div className={cn("w-1.5 h-1.5 rounded-full shrink-0", getEventColor(ev))} />
                    <div className="min-w-0">
                      <p className="text-[11px] text-slate-300 font-medium truncate group-hover:text-brand transition-colors">{ev.title}</p>
                      <p className="text-[10px] text-slate-600">{formatTime(ev.start)}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Provider badge */}
        {provider && (
          <div className="mt-auto">
            <div className="flex items-center gap-2 bg-slate-800 rounded-xl px-3 py-2">
              <div className={cn("w-2 h-2 rounded-full", provider === "google" ? "bg-emerald-500" : "bg-blue-500")} />
              <span className="text-[11px] text-slate-400">{provider === "google" ? "Google Calendar" : "Outlook"}</span>
            </div>
          </div>
        )}
      </div>

      {/* ── Main area ────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Toolbar */}
        <div className="px-4 py-3 border-b border-slate-800 bg-slate-900/80 flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1">
            <button onClick={prev} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"><ChevronLeft size={15} /></button>
            <button onClick={goToday} className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors">Today</button>
            <button onClick={next} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"><ChevronRight size={15} /></button>
          </div>

          <span className="text-sm font-semibold text-slate-200 flex-1 truncate">{headerTitle}</span>

          {/* View tabs */}
          <div className="flex items-center bg-slate-800 rounded-xl p-0.5 gap-0.5">
            {([
              { v: "month" as View, icon: Grid3x3, label: "Month" },
              { v: "week" as View, icon: Calendar, label: "Week" },
              { v: "agenda" as View, icon: LayoutList, label: "Agenda" },
            ]).map(({ v, icon: Icon, label }) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors", view === v ? "bg-brand-dark text-white" : "text-slate-500 hover:text-slate-100")}
              >
                <Icon size={11} /> {label}
              </button>
            ))}
          </div>

          <button onClick={loadEvents} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors" title="Refresh">
            <RefreshCw size={13} />
          </button>

          {/* Mobile new event */}
          <button onClick={() => openCreate()} disabled={connected === false} className="lg:hidden flex items-center gap-1 px-3 py-1.5 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold disabled:opacity-40 transition-colors">
            <Plus size={13} /> New
          </button>
        </div>

        {/* Calendar body */}
        <div className="flex-1 overflow-hidden flex">
          <div className="flex-1 overflow-hidden flex flex-col">
            {loading ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 size={24} className="animate-spin text-slate-600" />
              </div>
            ) : connected === false ? (
              <NoConnection />
            ) : view === "month" ? (
              <MonthGrid
                days={monthDays()} cursor={cursor} todayStr={todayStr}
                eventsForDay={eventsForDay}
                onDayClick={(d) => openCreate(isoDay(d))}
                onEventClick={setSelectedEvent}
                eventColor={getEventColor}
              />
            ) : view === "week" ? (
              <WeekGrid
                days={weekDays()} todayStr={todayStr}
                eventsForDay={eventsForDay}
                onDayClick={(d) => openCreate(isoDay(d))}
                onEventClick={setSelectedEvent}
                eventColor={getEventColor}
              />
            ) : (
              <AgendaView
                events={events}
                onEventClick={setSelectedEvent}
                onDayClick={(d) => openCreate(isoDay(d))}
                eventColor={getEventColor}
              />
            )}
          </div>

          {/* Event detail panel */}
          {selectedEvent && (
            <div className="w-72 border-l border-slate-800 bg-slate-900 flex flex-col overflow-y-auto shrink-0">
              <div className={cn("h-1 w-full", getEventColor(selectedEvent))} />
              <div className="flex items-start justify-between px-4 py-3 border-b border-slate-800">
                <p className="text-sm font-semibold text-slate-200 pr-2 leading-snug">{selectedEvent.title}</p>
                <button onClick={() => setSelectedEvent(null)} className="text-slate-500 hover:text-slate-100 shrink-0"><X size={14} /></button>
              </div>
              <div className="px-4 py-4 space-y-3 flex-1">
                <div className="flex items-start gap-2.5 text-xs">
                  <Clock size={13} className="text-slate-500 shrink-0 mt-0.5" />
                  <div>
                    {selectedEvent.allDay ? (
                      <p className="text-slate-200 font-medium">All day · {selectedEvent.start.slice(0, 10)}</p>
                    ) : (
                      <>
                        <p className="text-slate-200 font-medium">
                          {new Date(selectedEvent.start).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
                        </p>
                        <p className="text-slate-500">{formatTime(selectedEvent.start)} – {formatTime(selectedEvent.end)}</p>
                        <p className="text-slate-700 text-[10px]">{formatDuration(selectedEvent.start, selectedEvent.end)}</p>
                      </>
                    )}
                  </div>
                </div>

                {selectedEvent.location && (
                  <div className="flex items-start gap-2.5 text-xs">
                    <MapPin size={13} className="text-slate-500 shrink-0 mt-0.5" />
                    <span className="text-slate-300">{selectedEvent.location}</span>
                  </div>
                )}

                {selectedEvent.attendees.length > 0 && (
                  <div className="flex items-start gap-2.5 text-xs">
                    <Users size={13} className="text-slate-500 shrink-0 mt-0.5" />
                    <div className="space-y-0.5">
                      {selectedEvent.attendees.map((a) => (
                        <p key={a.email} className="text-slate-300">{a.name || a.email}</p>
                      ))}
                    </div>
                  </div>
                )}

                {selectedEvent.description && (
                  <div className="text-xs text-slate-400 leading-relaxed bg-slate-800/50 rounded-xl p-3">
                    {selectedEvent.description}
                  </div>
                )}

                {selectedEvent.link && (
                  <a href={selectedEvent.link} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-xs text-brand hover:text-brand/50 transition-colors">
                    <Zap size={11} /> Open in {selectedEvent.provider === "google" ? "Google Calendar" : "Outlook"}
                  </a>
                )}
              </div>
              <div className="px-4 pb-4 pt-2 border-t border-slate-800">
                <button
                  onClick={() => openEdit(selectedEvent)}
                  className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 transition-colors"
                >
                  <Edit3 size={12} /> Edit event
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <EventModal
          initial={editEvent ? {
            title: editEvent.title, description: editEvent.description,
            location: editEvent.location,
            start: editEvent.allDay ? editEvent.start.slice(0, 10) : toLocalInput(new Date(editEvent.start)),
            end: editEvent.allDay ? editEvent.end.slice(0, 10) : toLocalInput(new Date(editEvent.end)),
            allDay: editEvent.allDay,
            attendees: editEvent.attendees.map((a) => a.email).join(", "),
            timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            color: eventColors[editEvent.id] ?? "auto",
          } : defaultForm(prefillDate)}
          onSave={handleSave}
          onDelete={editEvent ? handleDelete : undefined}
          onClose={() => { setShowModal(false); setEditEvent(null); }}
          saving={saving} deleting={deleting} editEvent={editEvent}
          onAiSuggest={handleAiSuggest}
        />
      )}
    </div>
  );
}
