"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, Customer, Message, Sale, Order, FollowUp } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { formatCurrency, formatDate, formatDateTime, timeAgo } from "@/lib/utils";
import {
  ArrowLeft,
  MessageSquare,
  Phone,
  Mail,
  TrendingUp,
  Calendar,
  Sparkles,
  Loader2,
  Edit,
  Save,
  X,
  CheckCircle2,
  Clock,
  Package,
  CreditCard,
  Inbox,
  ChevronDown,
  ChevronUp,
  User,
} from "lucide-react";

const INPUT_CLASS =
  "w-full text-sm border border-slate-200 rounded-lg outline-none transition-colors focus:border-brand";

const STAGE_COLORS: Record<string, string> = {
  lead: "border-slate-200 bg-slate-50 text-slate-600",
  contacted: "border-blue-200 bg-blue-50 text-blue-700",
  negotiating: "border-amber-200 bg-amber-50 text-amber-800",
  won: "border-emerald-200 bg-emerald-50 text-emerald-800",
  lost: "border-red-200 bg-red-50 text-red-700",
};

const TIMELINE_ICON_STYLES: Record<string, string> = {
  message: "border-blue-200 bg-blue-50 text-blue-700",
  sale: "border-emerald-200 bg-emerald-50 text-emerald-800",
  order: "border-slate-200 bg-brand/10 text-brand-dark",
  followup: "border-amber-200 bg-amber-50 text-amber-800",
};

const STAGES = ["lead", "contacted", "negotiating", "won", "lost"] as const;

interface TimelineEvent {
  id: string;
  type: "message" | "sale" | "followup" | "order";
  content: string;
  amount?: number;
  status?: string;
  direction?: string;
  created_at: string;
}

interface StockAnalytics {
  total_products: number;
  out_of_stock: unknown[];
  low_stock: unknown[];
  total_value: number;
  in_stock_count: number;
}

interface EmailMessage {
  id: string;
  from: string;
  to: string;
  subject: string;
  date: string;
  body: string;
  unread: boolean;
}

interface EmailThread {
  id: string;
  subject: string;
  from: string;
  to?: string;
  date: string;
  snippet: string;
  unread: boolean;
  messageCount: number;
  provider: "gmail" | "microsoft";
  messages?: EmailMessage[];
}

export default function CustomerProfilePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sales, setSales] = useState<Sale[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"timeline" | "messages" | "emails" | "sales" | "orders" | "followups">("timeline");
  const [emails, setEmails] = useState<EmailThread[]>([]);
  const [emailsLoading, setEmailsLoading] = useState(false);
  const [emailsLoaded, setEmailsLoaded] = useState(false);
  const [expandedThread, setExpandedThread] = useState<string | null>(null);
  const [threadMessages, setThreadMessages] = useState<Record<string, EmailMessage[]>>({});
  const [threadLoading, setThreadLoading] = useState<string | null>(null);
  const [aiNotes, setAiNotes] = useState<string>("");
  const [generatingNotes, setGeneratingNotes] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", email: "", notes: "", stage: "", tags: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (id) load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function load() {
    setLoading(true);
    try {
      const cust = await api.get<Customer>(`/customers/${id}`);
      const [tl, msgs, sls, ords, fups] = await Promise.all([
        api.get<{ timeline: TimelineEvent[] }>(`/customers/${id}/timeline`).then(r => r.timeline || []).catch(() => []),
        api.get<Message[]>(`/customers/${id}/messages?limit=30`).catch(() => []),
        api.get<Sale[]>("/sales").then(r => r.filter(s => s.customer_id === id)).catch(() => []),
        api.get<Order[]>("/orders").then(r => r.filter(o => o.customer_phone === cust.phone_number)).catch(() => []),
        api.get<FollowUp[]>("/followups").then(r => r.filter(f => f.customer_id === id)).catch(() => []),
      ]);
      setCustomer(cust);
      setTimeline(tl);
      setMessages(msgs);
      setSales(sls);
      setOrders(ords);
      setFollowups(fups);
      setEditForm({
        name: cust.name,
        email: cust.email || "",
        notes: cust.notes || "",
        stage: cust.stage || "lead",
        tags: (cust.tags || []).join(", "),
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!customer) return;
    setSaving(true);
    try {
      await api.put(`/customers/${id}`, {
        name: editForm.name,
        email: editForm.email,
        notes: editForm.notes,
        stage: editForm.stage,
        tags: editForm.tags.split(",").map(t => t.trim()).filter(Boolean),
      });
      setEditing(false);
      await load();
    } finally {
      setSaving(false);
    }
  }

  async function generateAINotes() {
    setGeneratingNotes(true);
    try {
      const res = await api.post<{ notes: string; analysis?: string }>(`/customers/${id}/generate-notes`, {});
      setAiNotes(res.notes || res.analysis || "No notes generated");
    } catch {
      setAiNotes("Failed to generate notes");
    } finally {
      setGeneratingNotes(false);
    }
  }

  async function loadEmails(emailAddress: string) {
    if (emailsLoaded || emailsLoading) return;
    setEmailsLoading(true);
    try {
      const token = getToken();
      const q = encodeURIComponent(`from:${emailAddress} OR to:${emailAddress}`);
      const res = await fetch(`/api/email?q=${q}&limit=50`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Failed to load emails");
      const data = await res.json() as { threads?: EmailThread[] };
      setEmails(data.threads ?? []);
      setEmailsLoaded(true);
    } catch {
      setEmails([]);
      setEmailsLoaded(true);
    } finally {
      setEmailsLoading(false);
    }
  }

  async function loadThread(thread: EmailThread) {
    if (threadMessages[thread.id]) {
      setExpandedThread(expandedThread === thread.id ? null : thread.id);
      return;
    }
    setExpandedThread(thread.id);
    setThreadLoading(thread.id);
    try {
      const token = getToken();
      const res = await fetch(`/api/email`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ action: "get_thread", provider: thread.provider, threadId: thread.id }),
      });
      if (!res.ok) throw new Error("Failed to load thread");
      const data = await res.json() as { messages?: EmailMessage[] };
      setThreadMessages(prev => ({ ...prev, [thread.id]: data.messages ?? [] }));
    } catch {
      setThreadMessages(prev => ({ ...prev, [thread.id]: [] }));
    } finally {
      setThreadLoading(null);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[320px] items-center justify-center p-6">
        <Loader2 className="animate-spin text-brand-dark" size={26} aria-hidden />
      </div>
    );
  }

  if (!customer) {
    return (
      <div className="mx-auto max-w-6xl p-6">
        <div className="rounded-lg border border-slate-200 bg-white px-6 py-12 text-center">
          <p className="text-sm font-medium text-slate-600">Customer not found</p>
          <button
            type="button"
            onClick={() => router.back()}
            className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand-dark hover:underline"
          >
            <ArrowLeft size={15} aria-hidden />
            Back to customers
          </button>
        </div>
      </div>
    );
  }

  const TABS = [
    { id: "timeline", label: "Timeline", count: timeline.length },
    { id: "messages", label: "Messages", count: messages.length },
    { id: "emails", label: "Emails", count: emails.length },
    { id: "sales", label: "Sales", count: sales.length },
    { id: "orders", label: "Orders", count: orders.length },
    { id: "followups", label: "Follow-ups", count: followups.length },
  ] as const;

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6 pb-16 text-slate-900">
      <button
        type="button"
        onClick={() => router.back()}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-slate-800"
      >
        <ArrowLeft size={15} aria-hidden />
        Back to customers
      </button>

      <div className="rounded-lg border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-brand/10 sm:h-16 sm:w-16">
              {customer.profile_picture ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={customer.profile_picture} alt="" className="h-full w-full object-cover" />
              ) : (
                <span className="text-xl font-semibold text-brand-dark sm:text-2xl">
                  {customer.name.charAt(0).toUpperCase()}
                </span>
              )}
            </div>
            <div className="min-w-0">
              {editing ? (
                <input
                  value={editForm.name}
                  onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                  className={`${INPUT_CLASS} max-w-md px-2 py-1 text-lg font-semibold`}
                />
              ) : (
                <h1 className="truncate text-xl font-semibold text-slate-900 sm:text-2xl">{customer.name}</h1>
              )}
              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="flex items-center gap-1 font-mono text-sm text-slate-500">
                  <Phone size={13} className="shrink-0" aria-hidden />
                  {customer.phone_number}
                </span>
                {customer.email ? (
                  <span className="flex min-w-0 max-w-full items-center gap-1 text-sm text-slate-500">
                    <Mail size={13} className="shrink-0" aria-hidden />
                    <span className="truncate">{customer.email}</span>
                  </span>
                ) : null}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {editing ? (
                  <select
                    value={editForm.stage}
                    onChange={(e) => setEditForm((f) => ({ ...f, stage: e.target.value }))}
                    className={`rounded-md border px-2 py-1 text-xs font-medium capitalize outline-none focus:border-brand ${STAGE_COLORS[editForm.stage] || "border-slate-200 bg-white"}`}
                  >
                    {STAGES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span
                    className={`rounded border px-2 py-0.5 text-xs font-medium capitalize ${STAGE_COLORS[customer.stage || "lead"]}`}
                  >
                    {customer.stage || "lead"}
                  </span>
                )}
                {(customer.tags || []).map((t) => (
                  <span
                    key={t}
                    className="rounded border border-brand/25 bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand-dark"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            {editing ? (
              <>
                <button
                  type="button"
                  onClick={() => setEditing(false)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors hover:bg-slate-50"
                  aria-label="Cancel edit"
                >
                  <X size={16} />
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-brand-dark bg-brand-dark px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand hover:text-brand-ink disabled:opacity-50"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  Save
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => router.push(`/dashboard/messages?customer=${encodeURIComponent(customer.id)}`)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-brand-dark bg-brand-dark px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-brand hover:text-brand-ink"
                >
                  <MessageSquare size={14} aria-hidden />
                  Message
                </button>
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
                >
                  <Edit size={14} aria-hidden />
                  Edit
                </button>
              </>
            )}
          </div>
        </div>

        {/* Edit fields */}
        {editing ? (
          <div className="mt-5 grid grid-cols-1 gap-3 border-t border-slate-200 pt-5 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-700">Email</label>
              <input
                value={editForm.email}
                onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))}
                className={`${INPUT_CLASS} px-3 py-2`}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-700">Tags (comma-separated)</label>
              <input
                value={editForm.tags}
                onChange={(e) => setEditForm((f) => ({ ...f, tags: e.target.value }))}
                placeholder="VIP, Returning"
                className={`${INPUT_CLASS} px-3 py-2`}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-700">Notes</label>
              <textarea
                value={editForm.notes}
                onChange={(e) => setEditForm((f) => ({ ...f, notes: e.target.value }))}
                rows={3}
                className={`${INPUT_CLASS} resize-none px-3 py-2`}
              />
            </div>
          </div>
        ) : null}

        <div className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-200 pt-5 sm:grid-cols-4">
          {[
            { label: "Total spent", value: formatCurrency(customer.total_spent || 0), icon: TrendingUp },
            { label: "Orders", value: String(customer.purchase_count || 0), icon: Package },
            {
              label: "Last contact",
              value: customer.last_contacted ? timeAgo(customer.last_contacted) : "Never",
              icon: Clock,
            },
            { label: "Member since", value: formatDate(customer.created_at), icon: Calendar },
          ].map(({ label, value, icon: Icon }) => (
            <div key={label} className="rounded-lg border border-slate-200 px-3 py-3">
              <div className="flex items-center gap-1.5 text-slate-400">
                <Icon size={13} className="text-brand-dark" aria-hidden />
                <span className="text-[11px] font-semibold uppercase tracking-wide">{label}</span>
              </div>
              <p className="mt-1 truncate text-sm font-semibold tabular-nums text-slate-900">{value}</p>
            </div>
          ))}
        </div>

        {customer.notes && !editing ? (
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-relaxed text-slate-600">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Notes</p>
            {customer.notes}
          </div>
        ) : null}

        <div className="mt-4 border-t border-slate-200 pt-4">
          <button
            type="button"
            onClick={generateAINotes}
            disabled={generatingNotes}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-brand-dark transition-colors hover:border-brand/40 hover:bg-brand/10 disabled:opacity-50"
          >
            <Sparkles size={13} className={generatingNotes ? "animate-spin" : ""} aria-hidden />
            {generatingNotes ? "Generating…" : "Generate AI notes"}
          </button>
          {aiNotes ? (
            <div className="mt-3 rounded-lg border border-brand/25 bg-brand/10 px-4 py-3 text-sm leading-relaxed text-brand-ink">
              {aiNotes}
            </div>
          ) : null}
        </div>
      </div>

      <div className="overflow-x-auto pb-0.5">
        <div className="inline-flex min-w-full gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 sm:min-w-0">
          {TABS.map(({ id: tid, label, count }) => (
            <button
              key={tid}
              type="button"
              onClick={() => {
                setActiveTab(tid);
                if (tid === "emails" && customer.email && !emailsLoaded) {
                  loadEmails(customer.email);
                }
              }}
              className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors sm:text-sm ${
                activeTab === tid
                  ? "border border-slate-200 bg-white text-slate-900"
                  : "border border-transparent text-slate-600 hover:text-slate-800"
              }`}
            >
              {label}
              {count > 0 ? <span className="ml-1 text-slate-400">({count})</span> : null}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">

        {/* Timeline */}
        {activeTab === "timeline" && (
          <div className="divide-y divide-slate-100">
            {timeline.length === 0 ? (
              <EmptyTab message="No activity yet" />
            ) : (
              timeline.map((event) => {
                const Icon =
                  event.type === "message"
                    ? MessageSquare
                    : event.type === "sale"
                      ? CreditCard
                      : event.type === "order"
                        ? Package
                        : CheckCircle2;
                return (
                  <div key={event.id} className="flex items-start gap-3 px-4 py-3.5">
                    <div
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${TIMELINE_ICON_STYLES[event.type] || "border-slate-200 bg-slate-50 text-slate-600"}`}
                    >
                      <Icon size={14} aria-hidden />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-slate-700">{event.content}</p>
                      {event.amount !== undefined && event.amount > 0 ? (
                        <p className="mt-0.5 text-xs font-medium tabular-nums text-emerald-700">
                          {formatCurrency(event.amount)}
                        </p>
                      ) : null}
                    </div>
                    <span className="shrink-0 text-xs text-slate-400">{timeAgo(event.created_at)}</span>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Messages */}
        {activeTab === "messages" && (
          <div className="max-h-[500px] space-y-3 overflow-y-auto p-4">
            {messages.length === 0 ? (
              <EmptyTab message="No messages" icon={MessageSquare} />
            ) : (
              messages.map((m) => (
                <div key={m.id} className={`flex ${m.direction === "outgoing" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] rounded-lg border px-3 py-2 text-sm sm:max-w-sm ${
                      m.direction === "outgoing"
                        ? "border-brand-dark bg-brand-dark text-white"
                        : "border-slate-200 bg-slate-50 text-slate-800"
                    }`}
                  >
                    <p className="leading-relaxed">{m.content}</p>
                    <p
                      className={`mt-1 text-xs ${m.direction === "outgoing" ? "text-white/70" : "text-slate-400"}`}
                    >
                      {timeAgo(m.created_at)}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Emails */}
        {activeTab === "emails" && (
          <div className="divide-y divide-slate-100">
            {!customer.email ? (
              <EmptyTab message="No email address on file for this customer." icon={Mail} />
            ) : null}
            {customer.email && emailsLoading ? (
              <div className="flex items-center justify-center gap-2 py-12 text-slate-400">
                <Loader2 size={18} className="animate-spin" aria-hidden />
                <span className="text-sm">Loading emails…</span>
              </div>
            ) : null}
            {customer.email && !emailsLoading && emailsLoaded && emails.length === 0 ? (
              <EmptyTab message={`No emails found for ${customer.email}`} icon={Inbox} />
            ) : null}
            {emails.map((thread) => {
              const isExpanded = expandedThread === thread.id;
              const msgs = threadMessages[thread.id];
              const isLoadingThread = threadLoading === thread.id;
              return (
                <div key={thread.id} className="flex flex-col">
                  <button
                    type="button"
                    onClick={() => loadThread(thread)}
                    className="flex w-full items-start gap-3 p-4 text-left transition-colors hover:bg-slate-50/80"
                  >
                    <div className={`w-2 h-2 rounded-full mt-2 shrink-0 ${thread.unread ? "bg-brand-dark" : "bg-transparent border border-slate-300"}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p className={`text-sm truncate ${thread.unread ? "font-semibold text-slate-900" : "text-slate-700"}`}>
                          {thread.subject || "(no subject)"}
                        </p>
                        <span className="text-xs text-slate-400 shrink-0">{timeAgo(thread.date)}</span>
                      </div>
                      <p className="text-xs text-slate-500 truncate mt-0.5">{thread.from}</p>
                      <p className="text-xs text-slate-400 truncate mt-0.5">{thread.snippet}</p>
                    </div>
                    <div className="shrink-0 text-slate-400">
                      {isLoadingThread
                        ? <Loader2 size={14} className="animate-spin" />
                        : isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />
                      }
                    </div>
                  </button>
                  {isExpanded && !isLoadingThread && msgs && (
                    <div className="bg-slate-50 border-t border-slate-100 divide-y divide-slate-200 px-4 pb-2">
                      {msgs.length === 0 && (
                        <p className="text-xs text-slate-400 py-3">No message content available.</p>
                      )}
                      {msgs.map((msg) => (
                        <div key={msg.id} className="py-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-medium text-slate-600">{msg.from || thread.from}</span>
                            <span className="text-xs text-slate-400">{timeAgo(msg.date || thread.date)}</span>
                          </div>
                          <p className="text-xs text-slate-700 whitespace-pre-wrap line-clamp-6">{msg.body || thread.snippet}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Sales */}
        {activeTab === "sales" && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80">
                  {["Item", "Amount", "Method", "Date"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sales.length === 0 ? (
                  <tr>
                    <td colSpan={4}>
                      <EmptyTab message="No sales yet" icon={CreditCard} />
                    </td>
                  </tr>
                ) : (
                  sales.map((s) => (
                    <tr key={s.id} className="transition-colors hover:bg-slate-50/80">
                      <td className="px-4 py-3.5 text-slate-800">{s.item}</td>
                      <td className="px-4 py-3.5 font-medium tabular-nums text-emerald-700">
                        {formatCurrency(s.amount)}
                      </td>
                      <td className="px-4 py-3.5 capitalize text-slate-600">{s.payment_method}</td>
                      <td className="px-4 py-3.5 text-xs text-slate-500">{formatDate(s.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Orders */}
        {activeTab === "orders" && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80">
                  {["Order", "Product", "Total", "Status", "Date"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {orders.length === 0 ? (
                  <tr>
                    <td colSpan={5}>
                      <EmptyTab message="No orders yet" icon={Package} />
                    </td>
                  </tr>
                ) : (
                  orders.map((o) => (
                    <tr key={o.id} className="transition-colors hover:bg-slate-50/80">
                      <td className="px-4 py-3.5 font-medium text-slate-900">
                        #{o.order_number || o.id.slice(-6)}
                      </td>
                      <td className="px-4 py-3.5 text-slate-600">{o.product}</td>
                      <td className="px-4 py-3.5 font-medium tabular-nums text-slate-900">
                        {formatCurrency(o.total_amount)}
                      </td>
                      <td className="px-4 py-3.5">
                        <span className="rounded border border-brand/25 bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand-dark">
                          {o.fulfillment_status || "New"}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-xs text-slate-500">{timeAgo(o.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Follow-ups */}
        {activeTab === "followups" && (
          <div className="divide-y divide-slate-100">
            {followups.length === 0 ? (
              <EmptyTab message="No follow-ups" icon={CheckCircle2} />
            ) : (
              followups.map((f) => (
                <div key={f.id} className="flex items-start gap-3 px-4 py-3.5">
                  <span
                    className={`mt-2 h-2 w-2 shrink-0 rounded-full border ${
                      f.status === "done" ? "border-emerald-400 bg-emerald-400" : "border-amber-400 bg-amber-400"
                    }`}
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium capitalize text-slate-900">{f.type} follow-up</p>
                    {f.message ? <p className="mt-0.5 text-xs text-slate-500">{f.message}</p> : null}
                    <p className="mt-1 text-xs text-slate-400">
                      {formatDateTime(f.reminder_date)} · <span className="capitalize">{f.status}</span>
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyTab({
  message,
  icon: Icon = User,
}: {
  message: string;
  icon?: React.ComponentType<{ size?: number; className?: string; "aria-hidden"?: boolean }>;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-slate-50">
        <Icon size={18} className="text-slate-400" aria-hidden />
      </div>
      <p className="text-sm text-slate-500">{message}</p>
    </div>
  );
}
