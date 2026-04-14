"use client";

import { useEffect, useState } from "react";
import { followupsApi, customersApi, FollowUp, Customer } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/utils";
import { Bell, Plus, Phone, MessageSquare, Mail, Users, Clock, CheckCircle2, X, Loader2, ChevronDown } from "lucide-react";

const TYPE_CONFIG = {
  call:      { icon: Phone,          color: "text-blue-600",  bg: "bg-blue-50"  },
  whatsapp:  { icon: MessageSquare,  color: "text-green-600", bg: "bg-green-50" },
  meeting:   { icon: Users,          color: "text-purple-600",bg: "bg-purple-50"},
  email:     { icon: Mail,           color: "text-amber-600", bg: "bg-amber-50" },
};

const STATUS_COLORS: Record<string, string> = {
  pending:   "bg-amber-100 text-amber-700",
  done:      "bg-green-100 text-green-700",
  overdue:   "bg-red-100 text-red-700",
  snoozed:   "bg-slate-100 text-slate-500",
};

const FILTER_TABS = ["all", "overdue", "today", "this_week"] as const;
type FilterTab = (typeof FILTER_TABS)[number];

function getFilterLabel(f: FilterTab) {
  return { all: "All", overdue: "Overdue", today: "Today", this_week: "This Week" }[f];
}

function matchFilter(fu: FollowUp, filter: FilterTab): boolean {
  if (filter === "all") return true;
  const date = new Date(fu.reminder_date);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const weekEnd = new Date(today); weekEnd.setDate(today.getDate() + 7);
  if (filter === "overdue") return date < today && fu.status === "pending";
  if (filter === "today") return date >= today && date < tomorrow;
  if (filter === "this_week") return date >= today && date < weekEnd;
  return true;
}

function computeStatus(fu: FollowUp): string {
  if (fu.status !== "pending") return fu.status;
  const d = new Date(fu.reminder_date);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return d < today ? "overdue" : "pending";
}

export default function FollowupsPage() {
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterTab>("all");
  const [showAdd, setShowAdd] = useState(false);
  const [completing, setCompleting] = useState<string | null>(null);
  const [form, setForm] = useState({
    customer_id: "",
    type: "whatsapp" as FollowUp["type"],
    reminder_date: new Date().toISOString().split("T")[0],
    message: "",
  });
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [fu, cu] = await Promise.all([followupsApi.list(), customersApi.list()]);
      setFollowups(fu);
      setCustomers(cu);
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function markDone(fu: FollowUp) {
    setCompleting(fu.id);
    try {
      await followupsApi.update(fu.id, { status: "done" });
      await load();
    } finally { setCompleting(null); }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await followupsApi.create(form);
      setShowAdd(false);
      await load();
    } finally { setSaving(false); }
  }

  const filtered = followups.filter((f) => matchFilter(f, filter));
  const overdue = followups.filter((f) => computeStatus(f) === "overdue").length;
  const today = followups.filter((f) => matchFilter(f, "today")).length;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Follow-ups</h1>
          <p className="text-slate-500 text-sm mt-1">
            {overdue > 0 && <span className="text-red-600 font-medium">{overdue} overdue · </span>}
            {today} due today · {followups.length} total
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus size={15} /> Add Follow-up
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1">
        {FILTER_TABS.map((f) => {
          const count = followups.filter((fu) => matchFilter(fu, f)).length;
          return (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                filter === f ? "bg-indigo-600 text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {getFilterLabel(f)} {count > 0 && <span className="ml-1 opacity-70">({count})</span>}
            </button>
          );
        })}
      </div>

      {/* Cards */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse h-20" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center py-20 gap-3 bg-white rounded-xl border border-slate-200">
          <Bell size={36} className="text-slate-300" />
          <p className="text-slate-500 font-medium">No follow-ups here</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered
            .sort((a, b) => new Date(a.reminder_date).getTime() - new Date(b.reminder_date).getTime())
            .map((fu) => {
              const cfg = TYPE_CONFIG[fu.type] || TYPE_CONFIG.call;
              const Icon = cfg.icon;
              const status = computeStatus(fu);
              return (
                <div key={fu.id} className={`bg-white rounded-xl border flex items-center gap-4 px-5 py-4 ${status === "overdue" ? "border-red-200" : "border-slate-200"}`}>
                  <div className={`w-10 h-10 rounded-xl ${cfg.bg} flex items-center justify-center shrink-0`}>
                    <Icon size={18} className={cfg.color} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-slate-800">{fu.customer_name}</p>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[status] || STATUS_COLORS.pending}`}>
                        {status}
                      </span>
                      <span className="text-xs text-slate-400 capitalize">{fu.type}</span>
                    </div>
                    {fu.message && (
                      <p className="text-sm text-slate-500 mt-0.5 truncate">{fu.message}</p>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div className="flex items-center gap-1 text-xs text-slate-400 justify-end">
                      <Clock size={11} />
                      {formatDate(fu.reminder_date)}
                    </div>
                    {fu.status === "pending" && (
                      <button
                        onClick={() => markDone(fu)}
                        disabled={completing === fu.id}
                        className="mt-1.5 flex items-center gap-1 text-xs font-medium text-green-700 bg-green-100 px-2.5 py-1 rounded-lg hover:bg-green-200 transition-colors disabled:opacity-50"
                      >
                        {completing === fu.id ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
                        Done
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
        </div>
      )}

      {/* Add modal */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">Add Follow-up</h3>
              <button onClick={() => setShowAdd(false)}><X size={20} className="text-slate-400" /></button>
            </div>
            <form onSubmit={handleAdd} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Customer *</label>
                <div className="relative">
                  <select
                    value={form.customer_id}
                    onChange={(e) => setForm((f) => ({ ...f, customer_id: e.target.value }))}
                    required
                    className="w-full appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                  >
                    <option value="">Select customer…</option>
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>{c.name} · {c.phone_number}</option>
                    ))}
                  </select>
                  <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Type *</label>
                <div className="grid grid-cols-4 gap-2">
                  {(["call", "whatsapp", "meeting", "email"] as FollowUp["type"][]).map((t) => {
                    const Ic = TYPE_CONFIG[t].icon;
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setForm((f) => ({ ...f, type: t }))}
                        className={`flex flex-col items-center gap-1 py-2 rounded-lg border text-xs font-medium capitalize transition-colors ${
                          form.type === t ? "border-indigo-500 bg-indigo-50 text-indigo-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        <Ic size={15} /> {t}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Date *</label>
                <input
                  type="date"
                  value={form.reminder_date}
                  onChange={(e) => setForm((f) => ({ ...f, reminder_date: e.target.value }))}
                  required
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Message / Note</label>
                <textarea
                  value={form.message}
                  onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
                  rows={2}
                  placeholder="What to discuss or send…"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>
              <button type="submit" disabled={saving}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm">
                {saving && <Loader2 size={15} className="animate-spin" />}
                Schedule Follow-up
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
