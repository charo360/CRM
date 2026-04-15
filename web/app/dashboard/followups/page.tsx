"use client";

import Link from "next/link";
import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  api,
  followupsApi,
  teamApi,
  messagesApi,
  aiApi,
  type FollowUp,
  type FollowupSuggestionStats,
  type TeamMember,
} from "@/lib/api";
import { getUser, getBusinessId } from "@/lib/auth";
import { formatDateTime, toDatetimeLocalValue } from "@/lib/utils";
import {
  Bell, Plus, Phone, MessageSquare, Mail, Users, Clock, CheckCircle2, X,
  Loader2, Trash2, Edit2, AlarmClock, Zap, Calendar,
  TrendingUp, BarChart2, RefreshCw, Send, Search, Download, ExternalLink,
} from "lucide-react";

/* ─── Types ─────────────────────────────────────────────── */
interface ColdCustomer {
  id: string; name: string; phone_number: string; days_since_contact?: number;
  ai_reason?: string; urgency_level?: string; urgency_score?: number;
  has_pending_followup?: boolean; ai_draft_message?: string; ai_draft_day?: number;
}
interface Analytics {
  stats: {
    total_followups?: number; completed_followups?: number; response_rate?: number;
    conversion_rate?: number; total_revenue?: number; avg_response_time?: number;
    needs_attention_contacted?: number; total_all?: number;
  };
  best_times: { best_day?: string; best_hour?: number; sample_size?: number };
  outcome_counts: Record<string, number>;
}

/* ─── Config ─────────────────────────────────────────────── */
const TYPE_CONFIG: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
  call:     { icon: Phone,         color: "text-blue-600",   bg: "bg-blue-50" },
  whatsapp: { icon: MessageSquare, color: "text-green-600",  bg: "bg-green-50" },
  meeting:  { icon: Users,         color: "text-purple-600", bg: "bg-purple-50" },
  email:    { icon: Mail,          color: "text-amber-600",  bg: "bg-amber-50" },
};
const STATUS_COLORS: Record<string, string> = {
  pending:   "bg-amber-100 text-amber-700",
  completed: "bg-green-100 text-green-700",
  overdue:   "bg-red-100 text-red-700",
  snoozed:   "bg-slate-100 text-slate-500",
};
const URGENCY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high:     "bg-orange-100 text-orange-700",
  normal:   "bg-blue-100 text-blue-700",
  low:      "bg-slate-100 text-slate-500",
};
const OUTCOMES = [
  { value: "called",      label: "Called — They answered" },
  { value: "replied",     label: "Replied on WhatsApp" },
  { value: "converted",   label: "Made a sale!" },
  { value: "no_answer",   label: "No answer / No reply" },
  { value: "rescheduled", label: "Rescheduled for later" },
  { value: "not_interested", label: "Not interested" },
];
const DATE_FILTERS = ["all", "overdue", "due_24h", "today", "tomorrow", "this_week", "later"] as const;
type DateFilter = (typeof DATE_FILTERS)[number];
type ListScope = "pending" | "completed" | "all";
type AssigneeFilter = "all" | "mine" | "unassigned" | string;

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function computeStatus(fu: FollowUp) {
  if (fu.status !== "pending") return fu.status;
  const d = new Date(fu.reminder_date);
  const today = startOfDay(new Date());
  return d < today ? "overdue" : "pending";
}

function matchDateFilter(fu: FollowUp, f: DateFilter): boolean {
  if (f === "all") return true;
  const d = new Date(fu.reminder_date);
  const now = new Date();
  const today = startOfDay(now);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const dayAfterTomorrow = new Date(tomorrow);
  dayAfterTomorrow.setDate(dayAfterTomorrow.getDate() + 1);
  const weekEnd = new Date(today);
  weekEnd.setDate(weekEnd.getDate() + 7);

  if (f === "due_24h") {
    const end = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    return fu.status === "pending" && d >= now && d <= end;
  }
  if (f === "overdue") {
    return fu.status === "pending" && d < today;
  }
  if (f === "today") {
    return d >= today && d < tomorrow;
  }
  if (f === "tomorrow") {
    return d >= tomorrow && d < dayAfterTomorrow;
  }
  if (f === "this_week") {
    return d >= today && d < weekEnd;
  }
  if (f === "later") {
    return d >= weekEnd;
  }
  return true;
}

function digitsOnly(phone: string) {
  return (phone || "").replace(/\D/g, "");
}

/* ─── Main Component ─────────────────────────────────────── */
export default function FollowupsPage() {
  const [tab, setTab] = useState<"reminders" | "attention" | "results">("reminders");

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-4 sm:space-y-5 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Follow-ups</h1>
          <p className="text-slate-500 text-sm mt-0.5">Track reminders, cold customers, and outcomes</p>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 bg-slate-100 rounded-xl p-1 w-fit">
        {(["reminders", "attention", "results"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-lg text-sm font-semibold capitalize transition-colors ${
              tab === t ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}>
            {t === "attention" ? "Attention Needed" : t === "results" ? "Results" : "Reminders"}
          </button>
        ))}
      </div>

      {tab === "reminders" && <RemindersTab setMainTab={setTab} />}
      {tab === "attention" && <AttentionTab />}
      {tab === "results"   && <ResultsTab />}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   TAB 1 — REMINDERS
══════════════════════════════════════════════════════════ */
function RemindersTab({
  setMainTab,
}: {
  setMainTab: (t: "reminders" | "attention" | "results") => void;
}) {
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [customers, setCustomers] = useState<{ id: string; name: string; phone_number: string }[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [suggestions, setSuggestions] = useState<FollowupSuggestionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [listScope, setListScope] = useState<ListScope>("pending");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [assigneeFilter, setAssigneeFilter] = useState<AssigneeFilter>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<FollowUp | null>(null);
  const [outcomeFor, setOutcomeFor] = useState<FollowUp | null>(null);
  const [whatsappFor, setWhatsappFor] = useState<FollowUp | null>(null);
  const [snoozingId, setSnoozingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey) return;
      const t = document.activeElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || (t as HTMLElement).isContentEditable)) return;
      e.preventDefault();
      searchRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [fu, cu, sug, tm] = await Promise.all([
        followupsApi.list(),
        api.get<{ id: string; name: string; phone_number: string }[]>("/customers"),
        followupsApi.suggestionStats().catch(() => null),
        teamApi.list().catch(() => []),
      ]);
      setFollowups(fu);
      setCustomers(cu);
      setSuggestions(sug);
      setTeamMembers(tm);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const uid = (getUser()?._id as string) || "";

  const baseFiltered = useMemo(() => {
    let rows = followups;
    if (listScope === "pending") rows = rows.filter((f) => f.status === "pending");
    else if (listScope === "completed") rows = rows.filter((f) => f.status === "completed");
    if (assigneeFilter === "mine") {
      rows = rows.filter((f) => f.assigned_to === uid);
    } else if (assigneeFilter === "unassigned") {
      rows = rows.filter((f) => !f.assigned_to);
    } else if (assigneeFilter !== "all") {
      rows = rows.filter((f) => f.assigned_to === assigneeFilter);
    }
    rows = rows.filter((f) => matchDateFilter(f, dateFilter));
    const q = search.trim().toLowerCase();
    if (q) {
      rows = rows.filter(
        (f) =>
          f.customer_name.toLowerCase().includes(q) ||
          (f.customer_phone || "").toLowerCase().includes(q) ||
          (f.message || "").toLowerCase().includes(q)
      );
    }
    return rows.sort((a, b) => new Date(a.reminder_date).getTime() - new Date(b.reminder_date).getTime());
  }, [followups, listScope, dateFilter, assigneeFilter, search, uid]);

  const pending = followups.filter((f) => f.status === "pending");
  const overdue = pending.filter((f) => computeStatus(f) === "overdue").length;
  const todayCount = followups.filter((f) => matchDateFilter(f, "today")).length;

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function selectAllVisible() {
    const pend = baseFiltered.filter((f) => f.status === "pending").map((f) => f.id);
    setSelected(new Set(pend));
  }

  function exportCsv() {
    const rows = baseFiltered;
    const header = ["Customer", "Phone", "When", "Type", "Status", "Assignee", "Message"];
    const lines = [
      header.join(","),
      ...rows.map((f) =>
        [
          JSON.stringify(f.customer_name),
          JSON.stringify(f.customer_phone || ""),
          JSON.stringify(formatDateTime(f.reminder_date)),
          f.type,
          f.status,
          JSON.stringify(f.assigned_to_name || ""),
          JSON.stringify((f.message || "").replace(/\n/g, " ")),
        ].join(",")
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `follow-ups-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this follow-up?")) return;
    setBusyId(id);
    try {
      await followupsApi.delete(id);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function handleSnooze(id: string, days: number) {
    setSnoozingId(null);
    setBusyId(id);
    try {
      await followupsApi.snooze(id, days);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function bulkSnooze(days: number) {
    const ids = [...selected].filter((id) => followups.find((f) => f.id === id)?.status === "pending");
    if (!ids.length) return;
    setBusyId("bulk");
    try {
      await followupsApi.bulkSnooze(ids, days);
      setSelected(new Set());
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function bulkDelete() {
    if (!confirm(`Delete ${selected.size} follow-up(s)?`)) return;
    setBusyId("bulk");
    try {
      await followupsApi.bulkDelete([...selected]);
      setSelected(new Set());
      await load();
    } finally {
      setBusyId(null);
    }
  }

  const dateLabels: Record<DateFilter, string> = {
    all: "All dates",
    overdue: "Overdue",
    due_24h: "Next 24h",
    today: "Today",
    tomorrow: "Tomorrow",
    this_week: "This week",
    later: "Later",
  };

  return (
    <>
      {/* Insight strip */}
      {suggestions && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            { k: "neglected_week" as const, label: "Needs touch (7d)", sub: "pipeline" },
            { k: "neglected_month" as const, label: "Quiet 30d", sub: "customers" },
            { k: "new_no_followup" as const, label: "New, no reminder", sub: "7 days" },
            { k: "vip_neglected" as const, label: "VIP quiet", sub: "priority" },
          ].map((x) => (
            <button
              key={x.k}
              type="button"
              onClick={() => setMainTab("attention")}
              className="text-left rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-50/50"
            >
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{x.sub}</p>
              <p className="text-xl font-bold text-slate-900">{suggestions[x.k]}</p>
              <p className="text-xs text-slate-600">{x.label}</p>
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate-500">
          {overdue > 0 && <span className="text-red-600 font-medium">{overdue} overdue · </span>}
          {todayCount} due today · {followups.length} loaded
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => load()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            type="button"
            onClick={exportCsv}
            disabled={!baseFiltered.length}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
          >
            <Download size={14} /> Export CSV
          </button>
          <button
            onClick={() => {
              setEditing(null);
              setShowAdd(true);
            }}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
          >
            <Plus size={15} /> Add Follow-up
          </button>
        </div>
      </div>

      {/* Scope + assignee */}
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1">
          {(["pending", "completed", "all"] as ListScope[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setListScope(s)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize ${
                listScope === s ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
              }`}
            >
              {s === "all" ? "All statuses" : s}
            </button>
          ))}
        </div>
        <select
          value={assigneeFilter}
          onChange={(e) => setAssigneeFilter(e.target.value as AssigneeFilter)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
        >
          <option value="all">Everyone</option>
          <option value="mine">Assigned to me</option>
          <option value="unassigned">Unassigned</option>
          {teamMembers
            .filter((m) => m.user_id)
            .map((m) => (
              <option key={m.id} value={m.user_id!}>
                {m.name}
              </option>
            ))}
        </select>
      </div>

      {/* Search + date chips */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          ref={searchRef}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name, phone, note… (press /)"
          className="w-full rounded-xl border border-slate-200 py-2 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {DATE_FILTERS.map((f) => {
          const count = followups.filter((fu) => {
            if (listScope === "pending" && fu.status !== "pending") return false;
            if (listScope === "completed" && fu.status !== "completed") return false;
            return matchDateFilter(fu, f);
          }).length;
          return (
            <button
              key={f}
              type="button"
              onClick={() => setDateFilter(f)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                dateFilter === f
                  ? "bg-indigo-600 text-white"
                  : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {dateLabels[f]}
              {count > 0 && f !== "all" && <span className="ml-1 opacity-80">({count})</span>}
            </button>
          );
        })}
      </div>

      {/* Bulk bar */}
      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm">
          <span className="font-medium text-indigo-900">{selected.size} selected</span>
          <button type="button" onClick={() => bulkSnooze(1)} className="rounded-lg bg-white px-2 py-1 text-xs font-semibold text-indigo-800 shadow-sm">
            Snooze 1d
          </button>
          <button type="button" onClick={() => bulkSnooze(3)} className="rounded-lg bg-white px-2 py-1 text-xs font-semibold text-indigo-800 shadow-sm">
            Snooze 3d
          </button>
          <button type="button" onClick={bulkDelete} className="rounded-lg bg-red-100 px-2 py-1 text-xs font-semibold text-red-800">
            Delete
          </button>
          <button type="button" onClick={() => setSelected(new Set())} className="text-xs text-indigo-600 underline">
            Clear
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl border border-slate-200 bg-white p-4" />
          ))}
        </div>
      ) : baseFiltered.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-slate-200 bg-white py-20">
          <Bell size={36} className="text-slate-300" />
          <p className="font-medium text-slate-500">No follow-ups match</p>
          <p className="text-sm text-slate-400">Try another filter or add a new follow-up</p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <button type="button" onClick={selectAllVisible} className="font-medium text-indigo-600 hover:underline">
              Select all pending (visible)
            </button>
          </div>
          {baseFiltered.map((fu) => {
            const cfg = TYPE_CONFIG[fu.type] || TYPE_CONFIG.call;
            const Icon = cfg.icon;
            const status = computeStatus(fu);
            const busy = busyId === fu.id || busyId === "bulk";
            const wa = digitsOnly(fu.customer_phone || "");
            return (
              <div
                key={fu.id}
                className={`flex min-w-0 items-center gap-2 rounded-xl border px-3 py-3 sm:gap-4 sm:px-5 sm:py-4 ${
                  status === "overdue" ? "border-red-200 bg-white" : "border-slate-200 bg-white"
                }`}
              >
                {fu.status === "pending" && (
                  <input
                    type="checkbox"
                    checked={selected.has(fu.id)}
                    onChange={() => toggleSelect(fu.id)}
                    className="h-4 w-4 shrink-0 rounded border-slate-300"
                  />
                )}
                <div className={`w-10 h-10 shrink-0 rounded-xl ${cfg.bg} flex items-center justify-center`}>
                  <Icon size={18} className={cfg.color} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/dashboard/customers/${fu.customer_id}`}
                      className="font-semibold text-slate-800 hover:text-indigo-600 hover:underline"
                    >
                      {fu.customer_name}
                    </Link>
                    <ExternalLink size={12} className="text-slate-300" />
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] || STATUS_COLORS.pending}`}>
                      {status}
                    </span>
                    {fu.assigned_to_name && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                        {fu.assigned_to_name}
                      </span>
                    )}
                    {fu.is_auto_sequence && (
                      <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
                        AI Draft · Day {fu.sequence_day}
                      </span>
                    )}
                    <span className="text-xs capitalize text-slate-400">{fu.type}</span>
                  </div>
                  {fu.message && <p className="mt-0.5 truncate text-sm text-slate-500">{fu.message}</p>}
                  {fu.outcome && (
                    <p className="mt-0.5 text-xs text-green-700">
                      Outcome: {OUTCOMES.find((o) => o.value === fu.outcome)?.label || fu.outcome}
                    </p>
                  )}
                </div>
                <div className="flex min-w-0 shrink-0 flex-wrap items-center justify-end gap-1">
                  <div className="mr-1 flex min-w-0 flex-col items-end gap-0.5 text-right sm:min-w-[4.5rem]">
                    <span className="text-[11px] font-medium leading-tight text-slate-500">
                      {new Date(fu.reminder_date).toLocaleDateString(undefined, {
                        weekday: "short",
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-slate-700">
                      <Clock size={10} className="text-indigo-400" />
                      {new Date(fu.reminder_date).toLocaleTimeString(undefined, {
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                  {wa && (
                    <>
                      <button
                        type="button"
                        onClick={() => setWhatsappFor(fu)}
                        className="rounded-lg p-1.5 text-green-600 hover:bg-green-50"
                        title="Compose WhatsApp (send from CRM)"
                      >
                        <MessageSquare size={15} />
                      </button>
                      <a href={`tel:${encodeURIComponent(fu.customer_phone || "")}`} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100" title="Call">
                        <Phone size={15} />
                      </a>
                    </>
                  )}
                  {fu.status === "pending" && (
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setSnoozingId(snoozingId === fu.id ? null : fu.id)}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-amber-50 hover:text-amber-600"
                        title="Snooze"
                      >
                        <AlarmClock size={15} />
                      </button>
                      {snoozingId === fu.id && (
                        <div className="absolute right-0 top-8 z-10 w-32 rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
                          {[1, 3, 7].map((d) => (
                            <button
                              key={d}
                              type="button"
                              onClick={() => handleSnooze(fu.id, d)}
                              className="w-full px-3 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-50"
                            >
                              {d === 1 ? "1 day" : d === 3 ? "3 days" : "1 week"}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setEditing(fu);
                      setShowAdd(true);
                    }}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
                    title="Edit"
                  >
                    <Edit2 size={15} />
                  </button>
                  {fu.status === "pending" && (
                    <button
                      type="button"
                      onClick={() => setOutcomeFor(fu)}
                      disabled={busy}
                      className="flex items-center gap-1 rounded-lg bg-green-100 px-2.5 py-1.5 text-xs font-medium text-green-700 hover:bg-green-200 disabled:opacity-50"
                    >
                      {busy ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />} Done
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleDelete(fu.id)}
                    disabled={busy}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                    title="Delete"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showAdd && (
        <AddEditModal
          key={editing?.id ?? "new"}
          editing={editing}
          customers={customers}
          teamMembers={teamMembers}
          onClose={() => {
            setShowAdd(false);
            setEditing(null);
          }}
          onSave={load}
        />
      )}
      {whatsappFor && (
        <QuickWhatsAppModal
          followup={whatsappFor}
          onClose={() => setWhatsappFor(null)}
        />
      )}
      {outcomeFor && (
        <OutcomeModal
          followup={outcomeFor}
          onClose={() => setOutcomeFor(null)}
          onSave={load}
        />
      )}
    </>
  );
}

/* ══════════════════════════════════════════════════════════
   TAB 2 — ATTENTION NEEDED
══════════════════════════════════════════════════════════ */
function AttentionTab() {
  const [cold, setCold]       = useState<ColdCustomer[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays]       = useState(14);
  const [draftFor, setDraftFor]   = useState<ColdCustomer | null>(null);
  const [draftMsg, setDraftMsg]   = useState("");
  const [draftLoading, setDraftLoading] = useState(false);
  const [sending, setSending]     = useState(false);
  const [sendDone, setSendDone]   = useState(false);
  const [direction, setDirection] = useState("");
  const [busyId, setBusyId]   = useState<string | null>(null);
  const [outcomeFor, setOutcomeFor] = useState<ColdCustomer | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<ColdCustomer[]>(`/customers/cold-with-reasons?days=${days}`);
      setCold(Array.isArray(data) ? data : []);
    } finally { setLoading(false); }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  async function fetchDraft(c: ColdCustomer, instructions?: string, regen?: number) {
    setDraftLoading(true);
    try {
      const params = new URLSearchParams({ customer_id: c.id });
      if (instructions) params.set("custom_instructions", instructions);
      if (regen) params.set("regen", String(regen));
      const res = await api.get<{ message: string; reason?: string }>(`/ai/draft-message?${params}`);
      setDraftMsg(res.message || "");
    } catch { setDraftMsg(c.ai_draft_message || ""); }
    finally { setDraftLoading(false); }
  }

  async function openDraft(c: ColdCustomer) {
    setDraftFor(c); setDirection(""); setSendDone(false);
    if (c.ai_draft_message) { setDraftMsg(c.ai_draft_message); }
    else { await fetchDraft(c); }
  }

  async function sendMessage(c: ColdCustomer, message: string) {
    setSending(true);
    try {
      const params = new URLSearchParams({ to_number: c.phone_number, message, customer_name: c.name });
      await api.post(`/messages/send?${params}`, {});
      setSendDone(true);
      setCold(prev => prev.filter(x => x.id !== c.id));
    } finally { setSending(false); }
  }

  async function removeCold(c: ColdCustomer) {
    if (!confirm(`Remove ${c.name} from attention list?`)) return;
    setBusyId(c.id);
    try {
      await api.post("/followup-events", { customer_id: c.id, outcome: "removed", note: "" });
      setCold(prev => prev.filter(x => x.id !== c.id));
    } finally { setBusyId(null); }
  }

  const urgencyOrder = { critical: 0, high: 1, normal: 2, low: 3 };
  const sorted = [...cold].sort((a,b) =>
    (urgencyOrder[a.urgency_level as keyof typeof urgencyOrder] ?? 2) -
    (urgencyOrder[b.urgency_level as keyof typeof urgencyOrder] ?? 2)
  );

  const critical = cold.filter(c => c.urgency_level === "critical").length;
  const high = cold.filter(c => c.urgency_level === "high").length;

  return (
    <>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex gap-2 items-center text-sm text-slate-500">
          {critical > 0 && <span className="text-red-600 font-medium">{critical} critical</span>}
          {high > 0 && <span className="text-orange-600 font-medium">{high} high priority</span>}
          <span>{cold.length} total needing attention</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">No contact in:</span>
          {[7, 14, 30].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                days === d ? "bg-indigo-600 text-white" : "bg-white border border-slate-200 text-slate-600"
              }`}>
              {d}d
            </button>
          ))}
          <button onClick={load} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 transition-colors">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">{Array.from({length:5}).map((_,i) => (
          <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse h-24" />
        ))}</div>
      ) : sorted.length === 0 ? (
        <div className="flex flex-col items-center py-20 gap-3 bg-white rounded-xl border border-slate-200">
          <CheckCircle2 size={36} className="text-green-400" />
          <p className="text-slate-500 font-medium">All customers are engaged!</p>
          <p className="text-slate-400 text-sm">No one has been silent for {days}+ days.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map(c => {
            const busy = busyId === c.id;
            return (
              <div key={c.id} className="bg-white rounded-xl border border-slate-200 px-5 py-4">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-600 font-bold text-sm shrink-0">
                    {c.name.charAt(0).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-slate-800">{c.name}</p>
                      {c.urgency_level && (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${URGENCY_COLORS[c.urgency_level] || URGENCY_COLORS.normal}`}>
                          {c.urgency_level}
                        </span>
                      )}
                      {c.has_pending_followup && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 font-medium">Reminder set</span>
                      )}
                      {c.ai_draft_message && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium">
                          AI Draft · Day {c.ai_draft_day}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">{c.phone_number} · {c.days_since_contact != null ? `${c.days_since_contact} days silent` : "never replied"}</p>
                    {c.ai_reason && <p className="text-sm text-slate-600 mt-1 italic">"{c.ai_reason}"</p>}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {c.ai_draft_message ? (
                      <button onClick={() => openDraft(c)}
                        className="flex items-center gap-1 text-xs font-medium text-purple-700 bg-purple-100 px-2.5 py-1.5 rounded-lg hover:bg-purple-200 transition-colors">
                        <Zap size={11} /> Review & Send
                      </button>
                    ) : (
                      <button onClick={() => openDraft(c)}
                        className="flex items-center gap-1 text-xs font-medium text-indigo-700 bg-indigo-100 px-2.5 py-1.5 rounded-lg hover:bg-indigo-200 transition-colors">
                        <Zap size={11} /> AI Draft
                      </button>
                    )}
                    <button onClick={() => setOutcomeFor({ id: c.id, name: c.name } as unknown as ColdCustomer)}
                      className="flex items-center gap-1 text-xs font-medium text-green-700 bg-green-100 px-2.5 py-1.5 rounded-lg hover:bg-green-200 transition-colors">
                      <CheckCircle2 size={11} /> Done
                    </button>
                    <button onClick={() => removeCold(c)} disabled={busy}
                      className="p-1.5 rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors">
                      {busy ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* AI Draft Modal */}
      {draftFor && (
        <div className="fixed inset-0 z-50 overflow-y-auto overscroll-contain bg-black/50">
          <div className="flex min-h-full items-center justify-center p-3 sm:p-4">
            <div className="my-auto flex w-full max-w-lg max-h-[92vh] flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-6 sm:py-4">
              <div className="min-w-0">
                <h3 className="font-bold text-slate-900">AI Draft Message</h3>
                <p className="text-xs text-slate-500 truncate">{draftFor.name} · {draftFor.phone_number}</p>
              </div>
              <button type="button" onClick={() => setDraftFor(null)} className="shrink-0"><X size={20} className="text-slate-400" /></button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Message</label>
                <textarea
                  value={draftMsg}
                  onChange={e => setDraftMsg(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Give AI direction (optional)</label>
                <div className="flex gap-2">
                  <input
                    value={direction}
                    onChange={e => setDirection(e.target.value)}
                    placeholder='e.g. "Make it more casual" or "mention discount"'
                    className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <button
                    onClick={() => fetchDraft(draftFor, direction, Math.floor(Math.random()*100))}
                    disabled={draftLoading}
                    className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-50 disabled:opacity-50 transition-colors">
                    {draftLoading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Regenerate
                  </button>
                </div>
              </div>
              {sendDone ? (
                <div className="flex flex-col items-center gap-2 py-3">
                  <CheckCircle2 size={28} className="text-green-500" />
                  <p className="text-sm font-semibold text-green-700">Message sent!</p>
                  <button onClick={() => setDraftFor(null)}
                    className="text-xs text-slate-500 hover:underline">Close</button>
                </div>
              ) : (
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setDraftFor(null)}
                    className="flex-1 py-2 text-sm font-semibold border border-slate-200 rounded-xl text-slate-600 hover:bg-slate-50 transition-colors">
                    Cancel
                  </button>
                  <button
                    onClick={() => sendMessage(draftFor, draftMsg)}
                    disabled={sending || !draftMsg}
                    className="flex-1 flex items-center justify-center gap-2 py-2 text-sm font-semibold bg-green-600 text-white rounded-xl hover:bg-green-700 disabled:opacity-50 transition-colors">
                    {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                    {sending ? "Sending…" : "Send Message"}
                  </button>
                </div>
              )}
            </div>
            </div>
          </div>
        </div>
      )}

      {/* Outcome for cold customer */}
      {outcomeFor && (
        <ColdOutcomeModal
          customer={outcomeFor as unknown as ColdCustomer}
          onClose={() => setOutcomeFor(null)}
          onSave={() => { setOutcomeFor(null); load(); }}
        />
      )}
    </>
  );
}

/* ══════════════════════════════════════════════════════════
   TAB 3 — RESULTS / ANALYTICS
══════════════════════════════════════════════════════════ */
function ResultsTab() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  useEffect(() => {
    setLoading(true);
    followupsApi
      .analytics(days)
      .then((r) => setAnalytics(r as unknown as Analytics))
      .catch(() => setAnalytics(null))
      .finally(() => setLoading(false));
  }, [days]);

  if (loading) return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {Array.from({length:4}).map((_,i) => <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse h-24" />)}
    </div>
  );

  const s = analytics?.stats || {};
  const oc = analytics?.outcome_counts || {};
  const bt = analytics?.best_times || {};
  const total = s.total_all || s.total_followups || 0;
  const done  = s.completed_followups || 0;

  const OUTCOME_LABELS: Record<string, string> = {
    called: "Called — answered", replied: "Replied on WhatsApp",
    converted: "Made a sale", no_answer: "No answer/reply",
    rescheduled: "Rescheduled", not_interested: "Not interested",
  };
  const maxOutcome = Math.max(...Object.values(oc), 1);

  return (
    <div className="space-y-5">
      {/* Period */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-500">Period:</span>
        {[7, 30, 90].map(d => (
          <button key={d} onClick={() => setDays(d)}
            className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
              days === d ? "bg-indigo-600 text-white" : "bg-white border border-slate-200 text-slate-600"
            }`}>
            {d} days
          </button>
        ))}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total Follow-ups", value: total, color: "text-slate-900" },
          { label: "Completed", value: done, color: "text-green-700" },
          { label: "Response Rate", value: s.response_rate != null ? `${Math.round(s.response_rate)}%` : "—", color: "text-blue-700" },
          { label: "Conversion Rate", value: s.conversion_rate != null ? `${Math.round(s.conversion_rate)}%` : "—", color: "text-indigo-700" },
        ].map(c => (
          <div key={c.label} className="bg-white rounded-xl border border-slate-200 p-5">
            <p className="text-xs text-slate-500 font-medium">{c.label}</p>
            <p className={`text-2xl font-bold mt-1 ${c.color}`}>{c.value}</p>
          </div>
        ))}
      </div>

      {/* Revenue */}
      {s.total_revenue != null && s.total_revenue > 0 && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-5 flex items-center gap-4">
          <TrendingUp size={28} className="text-green-600 shrink-0" />
          <div>
            <p className="text-sm text-green-700 font-medium">Revenue from Follow-ups</p>
            <p className="text-2xl font-bold text-green-900">KES {s.total_revenue.toLocaleString()}</p>
          </div>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-5">
        {/* Outcomes */}
        {Object.keys(oc).length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
            <div className="flex items-center gap-2">
              <BarChart2 size={16} className="text-slate-400" />
              <h3 className="font-semibold text-slate-800 text-sm">Outcome Breakdown</h3>
            </div>
            {Object.entries(oc).map(([outcome, count]) => (
              <div key={outcome}>
                <div className="flex items-center justify-between text-xs text-slate-600 mb-1">
                  <span>{OUTCOME_LABELS[outcome] || outcome}</span>
                  <span className="font-semibold">{count}</span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${(count/maxOutcome)*100}%` }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Best times */}
        {(bt.best_day || bt.best_hour != null) && (
          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Clock size={16} className="text-slate-400" />
              <h3 className="font-semibold text-slate-800 text-sm">Best Time to Follow Up</h3>
            </div>
            {bt.best_day && (
              <div className="flex items-center justify-between py-2 border-b border-slate-100">
                <span className="text-sm text-slate-500">Best Day</span>
                <span className="text-sm font-semibold text-slate-800">{bt.best_day}</span>
              </div>
            )}
            {bt.best_hour != null && (
              <div className="flex items-center justify-between py-2 border-b border-slate-100">
                <span className="text-sm text-slate-500">Best Hour</span>
                <span className="text-sm font-semibold text-slate-800">
                  {bt.best_hour}:00 — {bt.best_hour + 1}:00
                </span>
              </div>
            )}
            {bt.sample_size && (
              <p className="text-xs text-slate-400">Based on {bt.sample_size} responses</p>
            )}
          </div>
        )}

        {/* Avg response time */}
        {s.avg_response_time != null && s.avg_response_time > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5 flex items-center gap-4">
            <Clock size={24} className="text-blue-500 shrink-0" />
            <div>
              <p className="text-xs text-slate-500 font-medium">Avg Response Time</p>
              <p className="text-xl font-bold text-slate-800">
                {s.avg_response_time < 1
                  ? `${Math.round(s.avg_response_time * 60)} min`
                  : `${s.avg_response_time.toFixed(1)} hrs`}
              </p>
            </div>
          </div>
        )}
      </div>

      {!analytics && (
        <div className="flex flex-col items-center py-20 gap-3 bg-white rounded-xl border border-slate-200">
          <BarChart2 size={36} className="text-slate-300" />
          <p className="text-slate-500 font-medium">No analytics data yet</p>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   SHARED MODALS
══════════════════════════════════════════════════════════ */
function AddEditModal({ editing, customers, teamMembers, onClose, onSave }: {
  editing: FollowUp | null;
  customers: { id: string; name: string; phone_number: string }[];
  teamMembers: TeamMember[];
  onClose: () => void;
  onSave: () => void;
}) {
  const myId = (getUser()?._id as string) || "";
  const ownerId = getBusinessId() || myId;
  const [form, setForm] = useState({
    customer_id: editing?.customer_id || "",
    type: editing?.type || "whatsapp",
    reminder_date: editing?.reminder_date
      ? toDatetimeLocalValue(editing.reminder_date)
      : toDatetimeLocalValue(new Date()),
    message: editing?.message || "",
    assigned_to: editing ? editing.assigned_to || "" : myId,
  });
  const [saving, setSaving]           = useState(false);
  const [draftLoading, setDraftLoading] = useState(false);
  const [search, setSearch]           = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  /** New follow-ups: collapse time UI after user confirms; edits start confirmed. */
  const [scheduleConfirmed, setScheduleConfirmed] = useState(!!editing);

  useEffect(() => {
    setScheduleConfirmed(!!editing);
  }, [editing?.id]);

  const filtered = customers
    .filter(
      (c) =>
        !search ||
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        (c.phone_number || "").includes(search)
    )
    .slice(0, 50);

  async function handleSubmit(e?: React.SyntheticEvent) {
    e?.preventDefault();
    setSaving(true);
    const reminderIso = new Date(form.reminder_date).toISOString();
    const payload: Record<string, unknown> = {
      customer_id: form.customer_id,
      type: form.type,
      reminder_date: reminderIso,
      message: form.message || null,
      assigned_to: form.assigned_to === "" ? "" : form.assigned_to,
    };
    try {
      if (editing) {
        await followupsApi.update(editing.id, payload);
      } else {
        await followupsApi.create(payload);
      }
      onSave();
      onClose();
    } finally {
      setSaving(false);
    }
  }

  async function generateDraft() {
    if (!form.customer_id) return;
    setDraftLoading(true);
    try {
      const res = await api.get<{message:string}>(`/ai/draft-message?customer_id=${form.customer_id}`);
      setForm(f => ({ ...f, message: res.message || "" }));
    } finally { setDraftLoading(false); }
  }

  const quickDate = (offset: number) => {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    d.setHours(9, 0, 0, 0);
    return toDatetimeLocalValue(d);
  };

  const selectedCustomer = customers.find(c => String(c.id) === String(form.customer_id));
  const typeConfig = TYPE_CONFIG[form.type] || TYPE_CONFIG.whatsapp;
  const TypeIcon = typeConfig.icon;

  const { datePart, timePart } = useMemo(() => {
    const [d, t] = form.reminder_date.split("T");
    return {
      datePart: d || "",
      timePart: (t || "09:00").slice(0, 5),
    };
  }, [form.reminder_date]);

  function setDatePart(v: string) {
    setForm((f) => ({ ...f, reminder_date: `${v}T${timePart}` }));
  }
  function setTimePart(v: string) {
    const day =
      datePart || toDatetimeLocalValue(new Date()).split("T")[0] || "";
    setForm((f) => ({ ...f, reminder_date: `${day}T${v}` }));
  }

  const reminderReady =
    form.customer_id &&
    form.reminder_date &&
    (editing || scheduleConfirmed);
  const canSubmit =
    form.customer_id && form.reminder_date && (editing || scheduleConfirmed);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto overscroll-contain bg-black/60">
      <div className="flex min-h-full items-center justify-center p-3 sm:p-4">
        <div
          className="my-auto flex w-full max-w-md max-h-[92vh] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
          role="dialog"
          aria-modal="true"
        >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5 sm:py-4">
          <div className="min-w-0">
            <h3 className="text-base font-bold text-slate-900">{editing ? "Edit Follow-up" : "New Follow-up"}</h3>
            <p className="mt-0.5 text-xs text-slate-400">Schedule a reminder to reach out</p>
          </div>
          <button type="button" onClick={onClose} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full hover:bg-slate-100 transition-colors">
            <X size={18} className="text-slate-400" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-5 sm:py-5 space-y-4">
          {/* ① Customer */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">① Who</p>
            {selectedCustomer ? (
              <div className="flex items-center justify-between px-4 py-3 bg-indigo-50 border-2 border-indigo-200 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
                    {selectedCustomer.name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="font-semibold text-indigo-900 text-sm">{selectedCustomer.name}</p>
                    <p className="text-xs text-indigo-400">{selectedCustomer.phone_number}</p>
                  </div>
                </div>
                <button type="button"
                  onClick={() => { setForm(f => ({...f, customer_id: ""})); setSearch(""); setDropdownOpen(false); }}
                  className="text-xs text-indigo-400 hover:text-indigo-700 font-medium transition-colors">
                  Change
                </button>
              </div>
            ) : (
              <div className="relative">
                <input
                  value={search}
                  onChange={e => { setSearch(e.target.value); setDropdownOpen(true); }}
                  onFocus={() => setDropdownOpen(true)}
                  onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
                  placeholder="Search or scroll all customers…"
                  className="w-full px-4 py-2.5 text-sm border-2 border-slate-200 rounded-xl outline-none focus:border-indigo-400 transition-colors"
                />
                {dropdownOpen && filtered.length > 0 && (
                  <div className="absolute left-0 right-0 top-full mt-1 border border-slate-200 rounded-xl shadow-xl bg-white max-h-52 overflow-y-auto z-10">
                    {filtered.map(c => (
                      <button key={c.id} type="button"
                        onMouseDown={e => e.preventDefault()}
                        onClick={() => { setForm(f => ({...f, customer_id: String(c.id)})); setSearch(""); setDropdownOpen(false); }}
                        className="w-full text-left px-4 py-2.5 text-sm flex items-center justify-between hover:bg-indigo-50 transition-colors border-b border-slate-50 last:border-0">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold shrink-0">
                            {c.name.charAt(0).toUpperCase()}
                          </div>
                          <span className="font-medium text-slate-800">{c.name}</span>
                        </div>
                        <span className="text-slate-400 text-xs">{c.phone_number}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ② Type */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">② How</p>
            <div className="grid grid-cols-4 gap-2">
              {(["call","whatsapp","meeting","email"] as const).map(t => {
                const Ic = TYPE_CONFIG[t].icon;
                const active = form.type === t;
                return (
                  <button key={t} type="button" onClick={() => setForm(f => ({...f, type: t}))}
                    className={`flex flex-col items-center gap-1.5 py-3 rounded-xl border-2 text-xs font-semibold capitalize transition-all ${
                      active
                        ? `${TYPE_CONFIG[t].bg} ${TYPE_CONFIG[t].color} border-current`
                        : "border-slate-100 text-slate-500 hover:border-slate-200 hover:bg-slate-50"
                    }`}>
                    <Ic size={16} /> {t}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Assignee */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1">
              <Users size={12} /> Assign to
            </p>
            <select
              value={form.assigned_to}
              onChange={(e) => setForm((f) => ({ ...f, assigned_to: e.target.value }))}
              className="w-full rounded-xl border-2 border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
            >
              <option value="">Unassigned</option>
              {ownerId && (
                <option value={ownerId}>
                  Owner / business
                </option>
              )}
              {teamMembers
                .filter((m) => m.user_id)
                .map((m) => (
                  <option key={m.id} value={m.user_id!}>
                    {m.name}
                    {m.user_id === myId ? " (you)" : ""}
                  </option>
                ))}
            </select>
            <p className="mt-1 text-[11px] text-slate-400">New follow-ups default to you unless you pick someone else</p>
          </div>

          {/* ③ When */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">③ When</p>

            {scheduleConfirmed ? (
              <div className="flex items-center justify-between gap-3 px-4 py-3.5 bg-gradient-to-br from-slate-50 to-indigo-50/40 border-2 border-indigo-100 rounded-xl">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-10 h-10 rounded-xl bg-white border border-indigo-100 shadow-sm flex items-center justify-center shrink-0">
                    <Calendar size={18} className="text-indigo-600" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900 truncate">
                      {new Date(form.reminder_date).toLocaleDateString(undefined, {
                        weekday: "short",
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </p>
                    <p className="text-xs text-indigo-600 font-medium mt-0.5">
                      {new Date(form.reminder_date).toLocaleTimeString(undefined, {
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setScheduleConfirmed(false)}
                  className="shrink-0 text-xs font-semibold text-indigo-600 hover:text-indigo-800 px-3 py-1.5 rounded-lg hover:bg-white/80 transition-colors"
                >
                  Change
                </button>
              </div>
            ) : (
              <div className="rounded-xl border-2 border-slate-100 bg-slate-50/90 p-4 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600 mb-1.5">
                      <Calendar size={12} className="text-slate-400" />
                      Date
                    </label>
                    <input
                      type="date"
                      value={datePart}
                      onChange={(e) => setDatePart(e.target.value)}
                      className="w-full px-3 py-2.5 text-sm bg-white border-2 border-slate-200 rounded-xl outline-none focus:border-indigo-400 focus:ring-0 transition-colors"
                    />
                  </div>
                  <div>
                    <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600 mb-1.5">
                      <Clock size={12} className="text-slate-400" />
                      Time
                    </label>
                    <input
                      type="time"
                      value={timePart}
                      onChange={(e) => setTimePart(e.target.value)}
                      className="w-full px-3 py-2.5 text-sm bg-white border-2 border-slate-200 rounded-xl outline-none focus:border-indigo-400 focus:ring-0 transition-colors"
                    />
                  </div>
                </div>

                <div>
                  <p className="text-[11px] font-medium text-slate-500 mb-2">Quick start</p>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { label: "Today 9:00", offset: 0 },
                      { label: "Tomorrow 9:00", offset: 1 },
                      { label: "In 7 days", offset: 7 },
                    ].map((q) => (
                      <button
                        key={q.label}
                        type="button"
                        onClick={() =>
                          setForm((f) => ({ ...f, reminder_date: quickDate(q.offset) }))
                        }
                        className="text-xs font-medium px-3 py-1.5 rounded-full bg-white border border-slate-200 text-slate-700 shadow-sm hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-800 transition-colors"
                      >
                        {q.label}
                      </button>
                    ))}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setScheduleConfirmed(true)}
                  disabled={!datePart || !timePart}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
                >
                  <CheckCircle2 size={16} />
                  Done — use this time
                </button>
              </div>
            )}
          </div>

          {/* Summary card — appears once customer + date are set */}
          {reminderReady && (
            <div className="bg-white border-2 border-emerald-100 rounded-xl px-4 py-3 flex items-center gap-3 shadow-sm">
              <div className={`w-9 h-9 rounded-xl ${typeConfig.bg} flex items-center justify-center shrink-0`}>
                <TypeIcon size={16} className={typeConfig.color} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-800">
                  {form.type.charAt(0).toUpperCase() + form.type.slice(1)} with {selectedCustomer?.name}
                </p>
                <p className="text-xs text-emerald-700/90 font-medium">
                  {formatDateTime(form.reminder_date)}
                </p>
              </div>
              <CheckCircle2 size={18} className="text-emerald-500 shrink-0" />
            </div>
          )}

          {/* Note */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Note</p>
              <button type="button" onClick={generateDraft} disabled={!form.customer_id || draftLoading}
                className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-40 font-medium transition-colors">
                {draftLoading ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
                AI Draft
              </button>
            </div>
            <textarea value={form.message}
              onChange={e => setForm(f => ({...f, message: e.target.value}))}
              rows={2}
              placeholder="What to discuss or send…"
              className="w-full px-4 py-2.5 text-sm border-2 border-slate-200 rounded-xl outline-none focus:border-indigo-400 resize-none transition-colors"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex shrink-0 gap-2 border-t border-slate-100 bg-white px-4 py-3 sm:gap-3 sm:px-5 sm:py-4">
          <button type="button" onClick={onClose}
            className="flex-1 rounded-xl border-2 border-slate-200 py-2.5 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => handleSubmit()}
            disabled={saving || !canSubmit}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-40"
          >
            {saving ? <Loader2 size={15} className="animate-spin" /> : null}
            {editing ? "Update" : "Schedule"}
          </button>
        </div>
        </div>
      </div>
    </div>
  );
}

function QuickWhatsAppModal({
  followup,
  onClose,
}: {
  followup: FollowUp;
  onClose: () => void;
}) {
  const [text, setText] = useState(followup.message || "");
  const [sending, setSending] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    setText(followup.message || "");
  }, [followup.id, followup.message]);

  async function handleSend() {
    const phone = followup.customer_phone?.trim();
    if (!text.trim() || !phone) return;
    setSending(true);
    try {
      await messagesApi.send(phone, text.trim(), followup.customer_name);
      onClose();
    } catch {
      alert("Could not send. Check that WhatsApp is connected in Settings.");
    } finally {
      setSending(false);
    }
  }

  async function handleAiDraft() {
    setAiLoading(true);
    try {
      const res = await aiApi.draftMessage({ customer_id: followup.customer_id });
      setText(res.message || "");
    } catch {
      alert("Could not generate a draft.");
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto overscroll-contain bg-black/50">
      <div className="flex min-h-full items-center justify-center p-3 sm:p-4">
        <div className="my-auto w-full max-w-lg max-h-[92vh] overflow-hidden rounded-2xl bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 sm:px-5">
            <div className="min-w-0">
              <h3 className="font-bold text-slate-900">Send WhatsApp</h3>
              <p className="truncate text-xs text-slate-500">
                {followup.customer_name} · {followup.customer_phone}
              </p>
            </div>
            <button type="button" onClick={onClose} className="shrink-0 rounded-full p-1.5 hover:bg-slate-100">
              <X size={18} className="text-slate-400" />
            </button>
          </div>
          <div className="space-y-3 p-4 sm:p-5">
            <p className="text-xs text-slate-500">
              Message is sent through your connected WhatsApp Business number, same as the Messages page.
            </p>
            <div>
              <div className="mb-1 flex items-center justify-between">
                <label className="text-xs font-medium text-slate-700">Message</label>
                <button
                  type="button"
                  onClick={handleAiDraft}
                  disabled={aiLoading}
                  className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-40"
                >
                  {aiLoading ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
                  AI draft
                </button>
              </div>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={5}
                placeholder="Type your message…"
                className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-green-500"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                href="/dashboard/messages"
                className="text-xs font-medium text-slate-500 hover:text-indigo-600 hover:underline"
              >
                Open full Messages inbox →
              </Link>
            </div>
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSend}
                disabled={sending || !text.trim()}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-[#25D366] py-2.5 text-sm font-semibold text-white hover:bg-[#20bd5a] disabled:opacity-40"
              >
                {sending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                {sending ? "Sending…" : "Send now"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function OutcomeModal({ followup, onClose, onSave }: {
  followup: FollowUp; onClose: () => void; onSave: () => void;
}) {
  const [selected, setSelected] = useState("");
  const [note, setNote]         = useState("");
  const [saving, setSaving]     = useState(false);

  async function handleSave() {
    if (!selected) return;
    setSaving(true);
    try {
      await followupsApi.update(followup.id, {
        status: "completed",
        outcome: selected,
        outcome_note: note,
      });
      onSave();
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto overscroll-contain bg-black/50">
      <div className="flex min-h-full items-center justify-center p-3 sm:p-4">
        <div className="my-auto flex w-full max-w-sm max-h-[92vh] flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-6">
          <h3 className="font-bold text-slate-900">What happened?</h3>
          <button type="button" onClick={onClose} className="shrink-0"><X size={20} className="text-slate-400" /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6 space-y-3">
          <p className="text-xs text-slate-500">Follow-up with {followup.customer_name}</p>
          <Link
            href={`/dashboard/customers/${followup.customer_id}`}
            className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline"
          >
            Open customer profile <ExternalLink size={10} />
          </Link>
          <div className="space-y-2">
            {OUTCOMES.map(o => (
              <button key={o.value} type="button" onClick={() => setSelected(o.value)}
                className={`w-full text-left px-4 py-3 rounded-xl border text-sm font-medium transition-colors ${
                  selected === o.value ? "border-indigo-500 bg-indigo-50 text-indigo-700" : "border-slate-200 text-slate-700 hover:bg-slate-50"
                }`}>
                {o.label}
              </button>
            ))}
          </div>
          <textarea value={note} onChange={e => setNote(e.target.value)}
            placeholder="Add a note (optional)…"
            rows={2}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          />
          <button type="button" onClick={handleSave} disabled={!selected || saving}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm transition-colors">
            {saving && <Loader2 size={15} className="animate-spin" />}
            Save Outcome
          </button>
        </div>
        </div>
      </div>
    </div>
  );
}

function ColdOutcomeModal({ customer, onClose, onSave }: {
  customer: ColdCustomer; onClose: () => void; onSave: () => void;
}) {
  const [selected, setSelected] = useState("");
  const [note, setNote]         = useState("");
  const [saving, setSaving]     = useState(false);

  async function handleSave() {
    if (!selected) return;
    setSaving(true);
    try {
      await api.post("/followup-events", { customer_id: customer.id, outcome: selected, note });
      onSave();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto overscroll-contain bg-black/50">
      <div className="flex min-h-full items-center justify-center p-3 sm:p-4">
        <div className="my-auto flex w-full max-w-sm max-h-[92vh] flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-6">
          <h3 className="font-bold text-slate-900">What happened?</h3>
          <button type="button" onClick={onClose} className="shrink-0"><X size={20} className="text-slate-400" /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6 space-y-3">
          <p className="text-xs text-slate-500">Contact with {customer.name}</p>
          <Link
            href={`/dashboard/customers/${customer.id}`}
            className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline"
          >
            Open customer profile <ExternalLink size={10} />
          </Link>
          <div className="space-y-2">
            {OUTCOMES.map(o => (
              <button key={o.value} type="button" onClick={() => setSelected(o.value)}
                className={`w-full text-left px-4 py-3 rounded-xl border text-sm font-medium transition-colors ${
                  selected === o.value ? "border-indigo-500 bg-indigo-50 text-indigo-700" : "border-slate-200 text-slate-700 hover:bg-slate-50"
                }`}>
                {o.label}
              </button>
            ))}
          </div>
          <textarea value={note} onChange={e => setNote(e.target.value)}
            placeholder="Add a note (optional)…"
            rows={2}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          />
          <button type="button" onClick={handleSave} disabled={!selected || saving}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm transition-colors">
            {saving && <Loader2 size={15} className="animate-spin" />}
            Save Outcome
          </button>
        </div>
        </div>
      </div>
    </div>
  );
}
