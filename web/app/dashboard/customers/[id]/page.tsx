"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, Customer, Message, Sale, Order, FollowUp } from "@/lib/api";
import { formatCurrency, formatDate, formatDateTime, timeAgo } from "@/lib/utils";
import {
  ArrowLeft, MessageSquare, Phone, Mail, MapPin, ShoppingBag,
  TrendingUp, Calendar, FileText, Sparkles, Loader2, Edit, Save, X,
  CheckCircle2, Clock, Package, CreditCard
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
  const [activeTab, setActiveTab] = useState<"timeline" | "messages" | "sales" | "orders" | "followups">("timeline");
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-indigo-600" size={28} />
      </div>
    );
  }

  if (!customer) {
    return (
      <div className="p-6 text-center text-slate-400">
        Customer not found.{" "}
        <button onClick={() => router.back()} className="text-indigo-600 hover:underline">Go back</button>
      </div>
    );
  }

  const TABS = [
    { id: "timeline", label: "Timeline", count: timeline.length },
    { id: "messages", label: "Messages", count: messages.length },
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
            <div className="w-16 h-16 rounded-2xl bg-indigo-100 flex items-center justify-center shrink-0">
              {customer.profile_picture ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={customer.profile_picture} alt={customer.name} className="w-16 h-16 rounded-2xl object-cover" />
              ) : (
                <span className="text-2xl font-bold text-indigo-600">{customer.name.charAt(0).toUpperCase()}</span>
              )}
            </div>
            <div>
              {editing ? (
                <input
                  value={editForm.name}
                  onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                  className="text-xl font-bold text-slate-900 border-b border-indigo-400 outline-none"
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
                  <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">{t}</span>
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
                <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50">
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
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Tags (comma-separated)</label>
              <input value={editForm.tags} onChange={e => setEditForm(f => ({ ...f, tags: e.target.value }))}
                placeholder="VIP, Returning"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Notes</label>
              <textarea value={editForm.notes} onChange={e => setEditForm(f => ({ ...f, notes: e.target.value }))}
                rows={2} className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
            </div>
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5 pt-5 border-t border-slate-100">
          {[
            { label: "Total Spent", value: formatCurrency(customer.total_spent || 0), icon: TrendingUp, color: "text-green-600", bg: "bg-green-50" },
            { label: "Orders", value: customer.purchase_count || 0, icon: Package, color: "text-blue-600", bg: "bg-blue-50" },
            { label: "Last Contact", value: customer.last_contacted ? timeAgo(customer.last_contacted) : "Never", icon: Clock, color: "text-amber-600", bg: "bg-amber-50" },
            { label: "Member Since", value: formatDate(customer.created_at), icon: Calendar, color: "text-indigo-600", bg: "bg-indigo-50" },
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
            className="flex items-center gap-1.5 text-xs text-purple-600 hover:text-purple-800 disabled:opacity-50"
          >
            <Sparkles size={12} className={generatingNotes ? "animate-spin" : ""} />
            {generatingNotes ? "Generating AI notes…" : "Generate AI customer notes"}
          </button>
          {aiNotes && (
            <div className="mt-2 p-3 bg-purple-50 rounded-xl text-sm text-purple-800 border border-purple-100">
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
            onClick={() => setActiveTab(tid)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === tid
                ? "bg-white border-b-2 border-indigo-600 text-indigo-600"
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
                order: "bg-indigo-50 text-indigo-600",
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
                <div className={`max-w-sm rounded-xl px-4 py-2 text-sm ${m.direction === "outgoing" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"}`}>
                  <p>{m.content}</p>
                  <p className={`text-xs mt-1 ${m.direction === "outgoing" ? "text-indigo-200" : "text-slate-400"}`}>{timeAgo(m.created_at)}</p>
                </div>
              </div>
            ))}
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
                    <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">
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
