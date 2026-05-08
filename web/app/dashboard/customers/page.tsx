"use client";

import { useEffect, useState } from "react";
import { customersApi, Customer } from "@/lib/api";
import { formatCurrency, timeAgo } from "@/lib/utils";
import { useRouter } from "next/navigation";
import { Search, UserPlus, MessageSquare, Loader2, X } from "lucide-react";
import { useBusiness } from "@/contexts/BusinessContext";

const STAGES = ["all", "lead", "contacted", "negotiating", "won", "lost"];
const STAGE_OPTIONS = ["lead", "contacted", "negotiating", "won", "lost"] as const;
const QUICK_TAGS = ["VIP", "New", "Returning"] as const;
const STAGE_COLORS: Record<string, string> = {
  lead:        "bg-slate-100 text-slate-600",
  contacted:   "bg-blue-100 text-blue-700",
  negotiating: "bg-amber-100 text-amber-700",
  won:         "bg-green-100 text-green-700",
  lost:        "bg-red-100 text-red-600",
};
const TAG_COLORS: Record<string, string> = {
  VIP:       "bg-yellow-100 text-yellow-700",
  New:       "bg-blue-100 text-blue-700",
  Returning: "bg-green-100 text-green-700",
};

export default function CustomersPage() {
  const { ui } = useBusiness();
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", phone_number: "", email: "", notes: "" });

  async function load() {
    setLoading(true);
    try { setCustomers(await customersApi.list()); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await customersApi.create(form);
      setShowAdd(false);
      setForm({ name: "", phone_number: "", email: "", notes: "" });
      await load();
    } finally { setSaving(false); }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this customer?")) return;
    await customersApi.delete(id);
    await load();
  }

  async function handleStageChange(customerId: string, stage: string) {
    setUpdatingId(customerId);
    try {
      await customersApi.update(customerId, { stage });
      setCustomers((prev) =>
        prev.map((c) => (c.id === customerId ? { ...c, stage } : c))
      );
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not update stage");
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleQuickTagToggle(customer: Customer, tag: (typeof QUICK_TAGS)[number]) {
    const id = customer.id;
    const current = [...(customer.tags || [])];
    const next = current.includes(tag)
      ? current.filter((t) => t !== tag)
      : [...current, tag];
    setUpdatingId(id);
    try {
      await customersApi.update(id, { tags: next });
      setCustomers((prev) =>
        prev.map((c) => (c.id === id ? { ...c, tags: next } : c))
      );
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not update tags");
    } finally {
      setUpdatingId(null);
    }
  }

  const filtered = customers.filter((c) => {
    const matchStage = stageFilter === "all" || (c.stage || "lead") === stageFilter;
    const q = search.toLowerCase();
    const matchSearch = !q || c.name.toLowerCase().includes(q) || c.phone_number.includes(q) || (c.email || "").toLowerCase().includes(q);
    return matchStage && matchSearch;
  });

  const totalSpent = customers.reduce((s, c) => s + (c.total_spent || 0), 0);
  const vip = customers.filter((c) => c.tags?.includes("VIP")).length;

  return (
    <div className="p-6 w-full maxw-6xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{ui.customersNavLabel}</h1>
          <p className="text-slate-500 text-sm mt-1">
            {customers.length} total · {vip} VIP · {formatCurrency(totalSpent)} lifetime value
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm font-semibold rounded-lg hover:bg-brand transition-colors"
        >
          <UserPlus size={15} /> Add Customer
        </button>
      </div>

      {/* Stage tabs */}
      <div className="flex gap-1 flex-wrap">
        {STAGES.map((s) => (
          <button
            key={s}
            onClick={() => setStageFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium capitalize transition-colors ${
              stageFilter === s
                ? "bg-brand-dark text-white"
                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {s === "all" ? `All (${customers.length})` : s}
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name, phone, email..."
          className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand"
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {["Customer", "Phone", "Stage", "Tags", "Spent", "Orders", "Last Contact", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 8 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <div className="h-4 bg-slate-100 rounded animate-pulse" />
                        </td>
                      ))}
                    </tr>
                  ))
                : filtered.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50 group cursor-pointer" onClick={() => router.push(`/dashboard/customers/${c.id}`)}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-brand/15 flex items-center justify-center shrink-0">
                            {c.profile_picture ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={c.profile_picture} alt={c.name} className="w-8 h-8 rounded-full object-cover" />
                            ) : (
                              <span className="text-brand-dark font-semibold text-xs">
                                {c.name.charAt(0).toUpperCase()}
                              </span>
                            )}
                          </div>
                          <div>
                            <p className="font-medium text-slate-800">{c.name}</p>
                            {c.email && <p className="text-xs text-slate-400">{c.email}</p>}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-600 text-xs font-mono">{c.phone_number}</td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-1.5 min-w-[128px]">
                          <select
                            value={c.stage || "lead"}
                            disabled={updatingId === c.id}
                            onChange={(e) => void handleStageChange(c.id, e.target.value)}
                            className="text-xs pl-2 pr-7 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-800 font-medium capitalize focus:ring-2 focus:ring-brand focus:border-brand max-w-[150px]"
                          >
                            {STAGE_OPTIONS.map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                          {updatingId === c.id ? (
                            <Loader2 size={14} className="animate-spin text-brand shrink-0" />
                          ) : null}
                        </div>
                      </td>
                      <td className="px-4 py-3 max-w-[220px]" onClick={(e) => e.stopPropagation()}>
                        <div className="flex flex-col gap-1.5">
                          <div className="flex flex-wrap gap-1">
                            {QUICK_TAGS.map((tag) => {
                              const on = (c.tags || []).includes(tag);
                              return (
                                <button
                                  key={tag}
                                  type="button"
                                  disabled={updatingId === c.id}
                                  onClick={() => void handleQuickTagToggle(c, tag)}
                                  className={`text-[10px] px-1.5 py-0.5 rounded font-semibold border transition-colors ${
                                    on
                                      ? `${TAG_COLORS[tag] || "bg-slate-200"} border-transparent`
                                      : "bg-white text-slate-500 border-slate-200 hover:border-brand/50 hover:text-brand-dark"
                                  } disabled:opacity-50`}
                                >
                                  {tag}
                                </button>
                              );
                            })}
                          </div>
                          {(c.tags || []).filter((t) => !(QUICK_TAGS as readonly string[]).includes(t)).length > 0 ? (
                            <div className="flex gap-1 flex-wrap">
                              {(c.tags || [])
                                .filter((t) => !(QUICK_TAGS as readonly string[]).includes(t))
                                .map((t) => (
                                  <span
                                    key={t}
                                    className={`text-xs px-1.5 py-0.5 rounded font-medium ${TAG_COLORS[t] || "bg-slate-100 text-slate-600"}`}
                                  >
                                    {t}
                                  </span>
                                ))}
                            </div>
                          ) : null}
                        </div>
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-800">
                        {formatCurrency(c.total_spent || 0)}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{c.purchase_count || 0}</td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        {c.last_contacted ? timeAgo(c.last_contacted) : "Never"}
                      </td>
                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            type="button"
                            onClick={() => router.push(`/dashboard/messages?customer=${encodeURIComponent(c.id)}`)}
                            className="p-1.5 rounded-lg text-slate-400 hover:bg-green-100 hover:text-green-700 transition-colors"
                            title="Message in Zilo (business WhatsApp)"
                          >
                            <MessageSquare size={14} />
                          </button>
                          <button
                            onClick={() => handleDelete(c.id)}
                            className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600 transition-colors"
                            title="Delete"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <p className="text-center text-sm text-slate-400 py-12">No customers found</p>
          )}
        </div>
      </div>

      {/* Add customer modal */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">Add Customer</h3>
              <button onClick={() => setShowAdd(false)} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleAdd} className="p-6 space-y-4">
              <Field label="Full name *" value={form.name} onChange={(v) => setForm((f) => ({ ...f, name: v }))} placeholder="Jane Doe" required />
              <Field label="Phone number *" value={form.phone_number} onChange={(v) => setForm((f) => ({ ...f, phone_number: v }))} placeholder="+254700000000" required />
              <Field label="Email" value={form.email} onChange={(v) => setForm((f) => ({ ...f, email: v }))} placeholder="jane@example.com" />
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  rows={2}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand resize-none"
                />
              </div>
              <button
                type="submit"
                disabled={saving}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-brand-dark text-white font-semibold rounded-xl hover:bg-brand disabled:opacity-50 text-sm"
              >
                {saving && <Loader2 size={15} className="animate-spin" />}
                Add Customer
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, onChange, placeholder, required, type = "text" }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; required?: boolean; type?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} required={required}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
    </div>
  );
}

