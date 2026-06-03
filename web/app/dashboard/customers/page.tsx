"use client";

import { useEffect, useMemo, useState } from "react";
import { customersApi, Customer } from "@/lib/api";
import { formatCurrency, timeAgo } from "@/lib/utils";
import { useRouter } from "next/navigation";
import { Search, UserPlus, MessageSquare, Loader2, X, Users, Crown, TrendingUp, Eye, Trash2 } from "lucide-react";
import { useBusiness } from "@/contexts/BusinessContext";

const INPUT_CLASS =
  "w-full text-sm border border-slate-200 rounded-lg outline-none transition-colors focus:border-brand";

const TABLE_HEADERS = [
  { label: "Customer", className: "w-[200px] max-w-[200px]" },
  { label: "Phone", className: "min-w-[120px]" },
  { label: "Stage", className: "min-w-[140px]" },
  { label: "Tags", className: "min-w-[160px]" },
  { label: "Spent", className: "min-w-[90px]" },
  { label: "Orders", className: "min-w-[72px]" },
  { label: "Last contact", className: "min-w-[100px]" },
  { label: "Actions", className: "w-[132px] min-w-[132px] text-right" },
] as const;

const STAGES = ["all", "lead", "contacted", "negotiating", "won", "lost"];
const STAGE_OPTIONS = ["lead", "contacted", "negotiating", "won", "lost"] as const;
const QUICK_TAGS = ["VIP", "New", "Returning"] as const;
const STAGE_COLORS: Record<string, string> = {
  lead:        "border-slate-200 bg-slate-50 text-slate-600",
  contacted:   "border-blue-200 bg-blue-50 text-blue-700",
  negotiating: "border-amber-200 bg-amber-50 text-amber-800",
  won:         "border-emerald-200 bg-emerald-50 text-emerald-800",
  lost:        "border-red-200 bg-red-50 text-red-700",
};
const TAG_COLORS: Record<string, string> = {
  VIP:       "border-amber-200 bg-amber-50 text-amber-800",
  New:       "border-blue-200 bg-blue-50 text-blue-700",
  Returning: "border-emerald-200 bg-emerald-50 text-emerald-800",
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
  const vipCount = customers.filter((c) => c.tags?.includes("VIP")).length;

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = { all: customers.length };
    for (const s of STAGE_OPTIONS) {
      counts[s] = customers.filter((c) => (c.stage || "lead") === s).length;
    }
    return counts;
  }, [customers]);

  function stageCountLabel(stage: string) {
    const n = stageCounts[stage] ?? 0;
    return stage === "all" ? `All · ${n}` : `${stage} · ${n}`;
  }

  return (
    <div className="p-6 w-full mx-auto space-y-6 pb-16 text-slate-900">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-brand-dark">
            <Users size={20} aria-hidden />
            <span className="text-xs font-semibold uppercase tracking-wide">CRM</span>
          </div>
          <h1 className="text-2xl font-semibold text-slate-900">{ui.customersNavLabel}</h1>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-slate-500">
            Track pipeline stages, tags, and spend. Click a row or the view icon in Actions to open a profile.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAdd(true)}
          className="flex shrink-0 items-center gap-2 rounded-lg border border-brand-dark bg-brand-dark px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand hover:text-brand-ink"
        >
          <UserPlus size={15} aria-hidden />
          Add customer
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Total" value={String(customers.length)} icon={Users} />
        <StatCard label="Showing" value={String(filtered.length)} icon={Search} muted />
        <StatCard label="VIP" value={String(vipCount)} icon={Crown} />
        <StatCard label="Lifetime value" value={formatCurrency(totalSpent)} icon={TrendingUp} />
      </div>

      <div className="space-y-3">
        <div className="relative max-w-md">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, phone, or email…"
            className={`${INPUT_CLASS} py-2.5 pl-9 pr-9`}
          />
          {search ? (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 hover:text-slate-600"
              aria-label="Clear search"
            >
              <X size={15} />
            </button>
          ) : null}
        </div>

        {/* <div className="overflow-x-auto pb-0.5">
          <div className="inline-flex min-w-full gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 sm:min-w-0">
            {STAGES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStageFilter(s)}
                className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium capitalize whitespace-nowrap transition-colors ${
                  stageFilter === s
                    ? "border border-slate-200 bg-white text-slate-900"
                    : "border border-transparent text-slate-600 hover:text-slate-800"
                }`}
              >
                {stageCountLabel(s)}
              </button>
            ))}
          </div>
        </div> */}
      </div>

      {!loading && customers.length > 0 ? (
        <p className="text-xs text-slate-500">
          Showing <span className="font-medium text-slate-700">{filtered.length}</span> of{" "}
          <span className="font-medium text-slate-700">{customers.length}</span> customers
        </p>
      ) : null}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-sm">
            <colgroup>
              <col className="w-[200px]" />
              <col />
              <col className="w-[140px]" />
              <col className="w-[180px]" />
              <col className="w-[100px]" />
              <col className="w-[80px]" />
              <col className="w-[110px]" />
              <col className="w-[132px]" />
            </colgroup>
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80">
                {TABLE_HEADERS.map((h) => (
                  <th
                    key={h.label}
                    className={`whitespace-nowrap px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500 ${h.className} ${
                      h.label === "Actions" ? "text-right" : "text-left"
                    }`}
                  >
                    {h.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 8 }).map((_, j) => (
                        <td key={j} className="px-4 py-3.5">
                          <div
                            className={`h-4 animate-pulse rounded bg-slate-100 ${j === 7 ? "ml-auto w-[88px]" : ""}`}
                          />
                        </td>
                      ))}
                    </tr>
                  ))
                : filtered.map((c) => {
                    const stage = c.stage || "lead";
                    return (
                      <tr
                        key={c.id}
                        className="group cursor-pointer transition-colors hover:bg-slate-50/80"
                        onClick={() => router.push(`/dashboard/customers/${c.id}`)}
                      >
                        <td className="w-[200px] max-w-[200px] overflow-hidden px-4 py-3.5">
                          <div className="flex min-w-0 max-w-full items-center gap-3">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-brand/10">
                              {c.profile_picture ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={c.profile_picture} alt="" className="h-full w-full object-cover" />
                              ) : (
                                <span className="text-xs font-semibold text-brand-dark">
                                  {c.name.charAt(0).toUpperCase()}
                                </span>
                              )}
                            </div>
                            <div className="min-w-0 flex-1 overflow-hidden">
                              <p className="truncate font-medium text-slate-900" title={c.name}>
                                {c.name}
                              </p>
                              {c.email ? (
                                <p className="truncate text-xs text-slate-400" title={c.email}>
                                  {c.email}
                                </p>
                              ) : null}
                            </div>
                          </div>
                        </td>
                        <td className="max-w-[160px] px-4 py-3.5">
                          <span className="block truncate font-mono text-xs text-slate-600" title={c.phone_number}>
                            {c.phone_number}
                          </span>
                        </td>
                        <td className="px-4 py-3.5" onClick={(e) => e.stopPropagation()}>
                          <div className="flex min-w-[140px] items-center gap-2">
                            <select
                              value={stage}
                              disabled={updatingId === c.id}
                              onChange={(e) => void handleStageChange(c.id, e.target.value)}
                              className={`max-w-[150px] rounded-md border px-2 py-1.5 text-xs font-medium capitalize outline-none transition-colors focus:border-brand disabled:opacity-50 ${STAGE_COLORS[stage] || "border-slate-200 bg-white text-slate-800"}`}
                            >
                              {STAGE_OPTIONS.map((s) => (
                                <option key={s} value={s}>
                                  {s}
                                </option>
                              ))}
                            </select>
                            {updatingId === c.id ? (
                              <Loader2 size={14} className="shrink-0 animate-spin text-brand-dark" />
                            ) : null}
                          </div>
                        </td>
                        <td className="max-w-[220px] px-4 py-3.5" onClick={(e) => e.stopPropagation()}>
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
                                    className={`rounded border px-2 py-0.5 text-[10px] font-semibold transition-colors disabled:opacity-50 ${
                                      on
                                        ? TAG_COLORS[tag] || "border-slate-200 bg-slate-50 text-slate-600"
                                        : "border-slate-200 bg-white text-slate-500 hover:border-brand/40 hover:text-brand-dark"
                                    }`}
                                  >
                                    {tag}
                                  </button>
                                );
                              })}
                            </div>
                            {(c.tags || []).filter((t) => !(QUICK_TAGS as readonly string[]).includes(t)).length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {(c.tags || [])
                                  .filter((t) => !(QUICK_TAGS as readonly string[]).includes(t))
                                  .map((t) => (
                                    <span
                                      key={t}
                                      className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${TAG_COLORS[t] || "border-slate-200 bg-slate-50 text-slate-600"}`}
                                    >
                                      {t}
                                    </span>
                                  ))}
                              </div>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 font-medium tabular-nums text-slate-900">
                          {formatCurrency(c.total_spent || 0)}
                        </td>
                        <td className="px-4 py-3.5 tabular-nums text-slate-600">{c.purchase_count || 0}</td>
                        <td className="px-4 py-3.5 text-xs text-slate-500">
                          {c.last_contacted ? timeAgo(c.last_contacted) : "Never"}
                        </td>
                        <td className="px-4 py-3.5" onClick={(e) => e.stopPropagation()}>
                          <CustomerRowActions
                            onView={() => router.push(`/dashboard/customers/${c.id}`)}
                            onMessage={() =>
                              router.push(`/dashboard/messages?customer=${encodeURIComponent(c.id)}`)
                            }
                            onDelete={() => handleDelete(c.id)}
                          />
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-3 px-4 py-16 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-slate-200 bg-slate-50">
                <Users size={22} className="text-slate-400" aria-hidden />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-700">No customers found</p>
                <p className="mt-1 text-xs text-slate-400">
                  {search || stageFilter !== "all"
                    ? "Try another search or stage filter."
                    : "Add your first customer to get started."}
                </p>
              </div>
              {!search && stageFilter === "all" ? (
                <button
                  type="button"
                  onClick={() => setShowAdd(true)}
                  className="inline-flex items-center gap-2 rounded-lg border border-brand-dark bg-brand-dark px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand hover:text-brand-ink"
                >
                  <UserPlus size={15} aria-hidden />
                  Add customer
                </button>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {showAdd ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <h3 className="font-semibold text-slate-900">Add customer</h3>
              <button
                type="button"
                onClick={() => setShowAdd(false)}
                className="rounded-md p-1 text-slate-400 transition-colors hover:text-slate-600"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleAdd} className="space-y-4 p-5">
              <Field label="Full name *" value={form.name} onChange={(v) => setForm((f) => ({ ...f, name: v }))} placeholder="Jane Doe" required />
              <Field label="Phone number *" value={form.phone_number} onChange={(v) => setForm((f) => ({ ...f, phone_number: v }))} placeholder="+254700000000" required />
              <Field label="Email" value={form.email} onChange={(v) => setForm((f) => ({ ...f, email: v }))} placeholder="jane@example.com" />
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-700">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  rows={2}
                  className={`${INPUT_CLASS} resize-none px-3 py-2`}
                />
              </div>
              <button
                type="submit"
                disabled={saving}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-brand-dark bg-brand-dark py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand hover:text-brand-ink disabled:opacity-50"
              >
                {saving ? <Loader2 size={15} className="animate-spin" /> : <UserPlus size={15} />}
                Add customer
              </button>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const ACTION_ICON_BTN =
  "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors";

function CustomerRowActions({
  onView,
  onMessage,
  onDelete,
}: {
  onView: () => void;
  onMessage: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex justify-end gap-1.5">
      <button
        type="button"
        onClick={onView}
        className={`${ACTION_ICON_BTN} hover:border-brand/40 hover:bg-brand/10 hover:text-brand-dark`}
        title="View details"
        aria-label="View details"
      >
        <Eye size={15} aria-hidden />
      </button>
      <button
        type="button"
        onClick={onMessage}
        className={`${ACTION_ICON_BTN} hover:border-brand/40 hover:bg-slate-50 hover:text-brand-dark`}
        title="Message"
        aria-label="Message customer"
      >
        <MessageSquare size={15} aria-hidden />
      </button>
      <button
        type="button"
        onClick={onDelete}
        className={`${ACTION_ICON_BTN} hover:border-red-200 hover:bg-red-50 hover:text-red-600`}
        title="Delete"
        aria-label="Delete customer"
      >
        <Trash2 size={15} aria-hidden />
      </button>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  muted,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ size?: number; className?: string; "aria-hidden"?: boolean }>;
  muted?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="flex items-center gap-2 text-slate-400">
        <Icon size={14} className={muted ? "" : "text-brand-dark"} aria-hidden />
        <span className="text-[11px] font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-1.5 truncate text-lg font-semibold tabular-nums text-slate-900">{value}</p>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, required, type = "text" }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; required?: boolean; type?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-700">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className={`${INPUT_CLASS} px-3 py-2`}
      />
    </div>
  );
}

