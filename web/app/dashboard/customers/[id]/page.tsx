"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, Customer, Message, Sale, Order, FollowUp } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { formatCurrency, formatDate, formatDateTime, timeAgo } from "@/lib/utils";
import {
  ArrowLeft, MessageSquare, Phone, Mail, MapPin, ShoppingBag,
  TrendingUp, Calendar, FileText, Sparkles, Loader2, Edit, Save, X,
  CheckCircle2, Clock, Package, CreditCard, Inbox, ChevronDown, ChevronUp
} from "lucide-react";

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
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-brand-dark" size={28} />
      </div>
    );
  }

  if (!customer) {
    return (
      <div className="p-6 text-center text-slate-400">
        Customer not found.{" "}
        <button onClick={() => router.back()} className="text-brand-dark hover:underline">Go back</button>
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

  const STAGES = ["lead", "contacted", "negotiating", "won", "lost"];
  const STAGE_COLORS: Record<string, string> = {
    lead: "bg-slate-100 text-slate-600",
    contacted: "bg-blue-100 text-blue-700",
    negotiating: "bg-amber-100 text-amber-700",
    won: "bg-green-100 text-green-700",
    lost: "bg-red-100 text-red-600",
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Back */}
      <button onClick={() => router.back()} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800">
        <ArrowLeft size={15} /> Back to Customers
      </button>

      {/* Header Card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-brand/15 flex items-center justify-center shrink-0">
              {customer.profile_picture ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={customer.profile_picture} alt={customer.name} className="w-16 h-16 rounded-2xl object-cover" />
              ) : (
                <span className="text-2xl font-bold text-brand-dark">{customer.name.charAt(0).toUpperCase()}</span>
              )}
            </div>
            <div>
              {editing ? (
                <input
                  value={editForm.name}
                  onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                  className="text-xl font-bold text-slate-900 border-b border-brand outline-none"
                />
              ) : (
                <h1 className="text-xl font-bold text-slate-900">{customer.name}</h1>
              )}
              <div className="flex items-center gap-3 mt-1 flex-wrap">
                <span className="flex items-center gap-1 text-sm text-slate-500">
                  <Phone size={12} /> {customer.phone_number}
                </span>
                {customer.email && (
                  <span className="flex items-center gap-1 text-sm text-slate-500">
                    <Mail size={12} /> {customer.email}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                {editing ? (
                  <select
                    value={editForm.stage}
                    onChange={e => setEditForm(f => ({ ...f, stage: e.target.value }))}
                    className="text-xs px-2 py-1 border border-slate-200 rounded-lg outline-none"
                  >
                    {STAGES.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                ) : (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${STAGE_COLORS[customer.stage || "lead"]}`}>
                    {customer.stage || "lead"}
                  </span>
                )}
                {(customer.tags || []).map(t => (
                  <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-brand/10 text-brand-dark font-medium">{t}</span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            {editing ? (
              <>
                <button onClick={() => setEditing(false)} className="p-2 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50">
                  <X size={16} />
                </button>
                <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand disabled:opacity-50">
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => router.push(`/dashboard/messages?customer=${encodeURIComponent(customer.id)}`)}
                  className="flex items-center gap-1.5 px-3 py-2 bg-green-500 text-white text-sm font-medium rounded-lg hover:bg-green-600"
                >
                  <MessageSquare size={14} /> Message
                </button>
                <button onClick={() => setEditing(true)} className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 text-slate-600 text-sm rounded-lg hover:bg-slate-50">
                  <Edit size={14} /> Edit
                </button>
              </>
            )}
          </div>
        </div>

        {/* Edit fields */}
        {editing && (
          <div className="mt-4 grid grid-cols-1 gap-3 pt-4 border-t border-slate-100">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Email</label>
              <input value={editForm.email} onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Tags (comma-separated)</label>
              <input value={editForm.tags} onChange={e => setEditForm(f => ({ ...f, tags: e.target.value }))}
                placeholder="VIP, Returning"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Notes</label>
              <textarea value={editForm.notes} onChange={e => setEditForm(f => ({ ...f, notes: e.target.value }))}
                rows={2} className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand resize-none" />
            </div>
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5 pt-5 border-t border-slate-100">
          {[
            { label: "Total Spent", value: formatCurrency(customer.total_spent || 0), icon: TrendingUp, color: "text-green-600", bg: "bg-green-50" },
            { label: "Orders", value: customer.purchase_count || 0, icon: Package, color: "text-blue-600", bg: "bg-blue-50" },
            { label: "Last Contact", value: customer.last_contacted ? timeAgo(customer.last_contacted) : "Never", icon: Clock, color: "text-amber-600", bg: "bg-amber-50" },
            { label: "Member Since", value: formatDate(customer.created_at), icon: Calendar, color: "text-brand-dark", bg: "bg-brand/10" },
          ].map(({ label, value, icon: Icon, color, bg }) => (
            <div key={label} className="flex items-center gap-3">
              <div className={`w-9 h-9 rounded-xl ${bg} flex items-center justify-center shrink-0`}>
                <Icon size={16} className={color} />
              </div>
              <div>
                <p className="text-xs text-slate-500">{label}</p>
                <p className="text-sm font-semibold text-slate-800">{value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Notes */}
        {customer.notes && !editing && (
          <div className="mt-4 p-3 bg-slate-50 rounded-xl text-sm text-slate-600 border border-slate-100">
            <p className="text-xs font-medium text-slate-400 mb-1">Notes</p>
            {customer.notes}
          </div>
        )}

        {/* AI Notes */}
        <div className="mt-4">
          <button
            onClick={generateAINotes}
            disabled={generatingNotes}
            className="flex items-center gap-1.5 text-xs text-brand-dark hover:text-brand-ink disabled:opacity-50"
          >
            <Sparkles size={12} className={generatingNotes ? "animate-spin" : ""} />
            {generatingNotes ? "Generating AI notes…" : "Generate AI customer notes"}
          </button>
          {aiNotes && (
            <div className="mt-2 p-3 bg-brand/10 rounded-xl text-sm text-brand-ink border border-brand/15">
              {aiNotes}
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map(({ id: tid, label, count }) => (
          <button
            key={tid}
            onClick={() => {
              setActiveTab(tid);
              if (tid === "emails" && customer?.email && !emailsLoaded) {
                loadEmails(customer.email);
              }
            }}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === tid
                ? "bg-white border-b-2 border-brand-dark text-brand-dark"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {label} {count > 0 && <span className="ml-1 text-xs text-slate-400">({count})</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">

        {/* Timeline */}
        {activeTab === "timeline" && (
          <div className="divide-y divide-slate-100">
            {timeline.length === 0 && <p className="text-center text-slate-400 text-sm py-10">No activity yet</p>}
            {timeline.map((event) => {
              const Icon = event.type === "message" ? MessageSquare
                : event.type === "sale" ? CreditCard
                : event.type === "order" ? Package
                : CheckCircle2;
              const colors: Record<string, string> = {
                message: "bg-blue-50 text-blue-600",
                sale: "bg-green-50 text-green-600",
                order: "bg-brand/10 text-brand-dark",
                followup: "bg-amber-50 text-amber-600",
              };
              return (
                <div key={event.id} className="flex items-start gap-3 p-4">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${colors[event.type]}`}>
                    <Icon size={14} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-700">{event.content}</p>
                    {event.amount !== undefined && event.amount > 0 && (
                      <p className="text-xs font-semibold text-green-600 mt-0.5">{formatCurrency(event.amount)}</p>
                    )}
                  </div>
                  <span className="text-xs text-slate-400 shrink-0">{timeAgo(event.created_at)}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Messages */}
        {activeTab === "messages" && (
          <div className="divide-y divide-slate-100 max-h-[500px] overflow-y-auto">
            {messages.length === 0 && <p className="text-center text-slate-400 text-sm py-10">No messages</p>}
            {messages.map((m) => (
              <div key={m.id} className={`flex p-4 ${m.direction === "outgoing" ? "justify-end" : ""}`}>
                <div className={`max-w-sm rounded-xl px-4 py-2 text-sm ${m.direction === "outgoing" ? "bg-brand-dark text-white" : "bg-slate-100 text-slate-800"}`}>
                  <p>{m.content}</p>
                  <p className={`text-xs mt-1 ${m.direction === "outgoing" ? "text-brand/30" : "text-slate-400"}`}>{timeAgo(m.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Emails */}
        {activeTab === "emails" && (
          <div className="divide-y divide-slate-100">
            {!customer?.email && (
              <div className="text-center text-slate-400 text-sm py-10">
                <Mail size={24} className="mx-auto mb-2 opacity-30" />
                No email address on file for this customer.
              </div>
            )}
            {customer?.email && emailsLoading && (
              <div className="flex items-center justify-center py-12 gap-2 text-slate-400">
                <Loader2 size={18} className="animate-spin" />
                <span className="text-sm">Loading emails…</span>
              </div>
            )}
            {customer?.email && !emailsLoading && emailsLoaded && emails.length === 0 && (
              <div className="text-center text-slate-400 text-sm py-10">
                <Inbox size={24} className="mx-auto mb-2 opacity-30" />
                No emails found for {customer.email}
              </div>
            )}
            {emails.map((thread) => {
              const isExpanded = expandedThread === thread.id;
              const msgs = threadMessages[thread.id];
              const isLoadingThread = threadLoading === thread.id;
              return (
                <div key={thread.id} className="flex flex-col">
                  <button
                    onClick={() => loadThread(thread)}
                    className="flex items-start gap-3 p-4 hover:bg-slate-50 text-left w-full"
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
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {["Item", "Amount", "Method", "Date"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sales.length === 0 ? (
                <tr><td colSpan={4} className="text-center text-slate-400 py-10">No sales yet</td></tr>
              ) : sales.map(s => (
                <tr key={s.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-800">{s.item}</td>
                  <td className="px-4 py-3 font-semibold text-green-600">{formatCurrency(s.amount)}</td>
                  <td className="px-4 py-3 text-slate-500 capitalize">{s.payment_method}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{formatDate(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Orders */}
        {activeTab === "orders" && (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {["Order", "Product", "Total", "Status", "Date"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {orders.length === 0 ? (
                <tr><td colSpan={5} className="text-center text-slate-400 py-10">No orders yet</td></tr>
              ) : orders.map(o => (
                <tr key={o.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-800">#{o.order_number || o.id.slice(-6)}</td>
                  <td className="px-4 py-3 text-slate-600">{o.product}</td>
                  <td className="px-4 py-3 font-semibold text-slate-800">{formatCurrency(o.total_amount)}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-brand/10 text-brand-dark font-medium">
                      {o.fulfillment_status || "New"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{timeAgo(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Follow-ups */}
        {activeTab === "followups" && (
          <div className="divide-y divide-slate-100">
            {followups.length === 0 && <p className="text-center text-slate-400 text-sm py-10">No follow-ups</p>}
            {followups.map(f => (
              <div key={f.id} className="flex items-start gap-3 p-4">
                <div className={`w-2 h-2 rounded-full mt-2 ${f.status === "done" ? "bg-green-400" : "bg-amber-400"}`} />
                <div className="flex-1">
                  <p className="text-sm font-medium text-slate-800 capitalize">{f.type} follow-up</p>
                  {f.message && <p className="text-xs text-slate-500 mt-0.5">{f.message}</p>}
                  <p className="text-xs text-slate-400 mt-1">
                    {formatDateTime(f.reminder_date)} · <span className="capitalize">{f.status}</span>
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
