"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { adminApi, type AdminUser } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import {
  BadgeCheck,
  Building2,
  Calendar,
  Edit,
  Mail,
  Phone,
  RefreshCw,
  Search,
  Shield,
  Trash2,
  Users,
  X,
} from "lucide-react";

type DateFilter = "all" | "today" | "week" | "month" | "3months";

const DATE_FILTERS: { key: DateFilter; label: string }[] = [
  { key: "all",     label: "All time" },
  { key: "today",   label: "Today" },
  { key: "week",    label: "This week" },
  { key: "month",   label: "This month" },
  { key: "3months", label: "Last 3 months" },
];

function filterByDate(users: AdminUser[], f: DateFilter): AdminUser[] {
  if (f === "all") return users;
  const now = new Date();
  let cutoff: Date;
  if (f === "today") {
    cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  } else if (f === "week") {
    const day = now.getDay(); // 0=Sun
    cutoff = new Date(now);
    cutoff.setDate(now.getDate() - day);
    cutoff.setHours(0, 0, 0, 0);
  } else if (f === "month") {
    cutoff = new Date(now.getFullYear(), now.getMonth(), 1);
  } else {
    cutoff = new Date(now);
    cutoff.setMonth(now.getMonth() - 3);
  }
  return users.filter((u) => u.created_at && new Date(u.created_at) >= cutoff);
}

type EditForm = {
  owner_name: string;
  business_name: string;
  phone_number: string;
  role: string;
  subscription_active: boolean;
  setup_complete: boolean;
};

function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const letter = (name || "?")[0].toUpperCase();
  const colors = [
    "bg-indigo-100 text-indigo-700",
    "bg-emerald-100 text-emerald-700",
    "bg-amber-100 text-amber-700",
    "bg-rose-100 text-rose-700",
    "bg-violet-100 text-violet-700",
    "bg-cyan-100 text-cyan-700",
  ];
  const colour = colors[letter.charCodeAt(0) % colors.length];
  return (
    <div
      style={{ width: size, height: size, fontSize: size * 0.42 }}
      className={`rounded-full flex items-center justify-center font-semibold shrink-0 ${colour}`}
    >
      {letter}
    </div>
  );
}

export default function AdminUsersManager() {
  const [rows, setRows] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [activeQ, setActiveQ] = useState("");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [selected, setSelected] = useState<AdminUser | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<EditForm>({
    owner_name: "",
    business_name: "",
    phone_number: "",
    role: "owner",
    subscription_active: false,
    setup_complete: false,
  });

  const filteredRows = useMemo(() => filterByDate(rows, dateFilter), [rows, dateFilter]);
  const activeCount = useMemo(() => filteredRows.filter((u) => u.subscription_active).length, [filteredRows]);
  const setupCount = useMemo(() => filteredRows.filter((u) => u.setup_complete).length, [filteredRows]);
  const ownerCount = useMemo(() => filteredRows.filter((u) => !u.business_id).length, [filteredRows]);

  function showToast(msg: string, type: "ok" | "err" = "ok") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }

  async function loadUsers(q = activeQ, silent = false) {
    if (!silent) setLoading(true); else setRefreshing(true);
    try {
      const data = await adminApi.listUsers({ q, limit: 200, skip: 0 });
      setRows(data.users);
      setTotal(data.total);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Failed to load users", "err");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => { void loadUsers(""); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function doSearch() {
    const q = search.trim();
    setActiveQ(q);
    void loadUsers(q);
  }

  function openEdit(u: AdminUser) {
    setSelected(u);
    setForm({
      owner_name: u.owner_name || "",
      business_name: u.business_name || "",
      phone_number: u.phone_number || "",
      role: u.role || "owner",
      subscription_active: !!u.subscription_active,
      setup_complete: !!u.setup_complete,
    });
  }

  async function saveEdit() {
    if (!selected) return;
    setSaving(true);
    try {
      await adminApi.updateUser(selected.id, form);
      setSelected(null);
      showToast("User updated");
      await loadUsers(activeQ, true);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Failed to update", "err");
    } finally {
      setSaving(false);
    }
  }

  async function deleteUser(u: AdminUser) {
    if (!confirm(`Permanently delete ${u.email || u.owner_name || u.id}? This cannot be undone.`)) return;
    setDeletingId(u.id);
    try {
      await adminApi.deleteUser(u.id);
      showToast("User deleted");
      await loadUsers(activeQ, true);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Failed to delete", "err");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: dateFilter === "all" ? "Total accounts" : `Accounts · ${DATE_FILTERS.find(f=>f.key===dateFilter)?.label}`, value: loading ? "—" : (dateFilter === "all" ? total : filteredRows.length), icon: Users, color: "text-slate-600 bg-slate-100" },
          { label: "Subscribed", value: loading ? "—" : activeCount, icon: BadgeCheck, color: "text-emerald-700 bg-emerald-100" },
          { label: "Setup complete", value: loading ? "—" : setupCount, icon: Shield, color: "text-indigo-700 bg-indigo-100" },
          { label: "Business owners", value: loading ? "—" : ownerCount, icon: Building2, color: "text-amber-700 bg-amber-100" },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-4">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${color}`}>
              <Icon size={18} />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{loading ? "—" : value}</p>
              <p className="text-xs text-slate-500 mt-0.5">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Table card */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {/* Toolbar */}
        <div className="border-b border-slate-100">
          {/* Search row */}
          <div className="flex items-center gap-3 px-4 py-3">
            <div className="flex-1 flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
              <Search size={13} className="text-slate-400 shrink-0" />
              <input
                ref={searchRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
                placeholder="Search email, name, business, phone…"
                className="flex-1 text-sm bg-transparent outline-none text-slate-700 placeholder:text-slate-400"
              />
            </div>
            <button
              onClick={doSearch}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors"
            >
              Search
            </button>
            <button
              onClick={() => void loadUsers(activeQ, true)}
              disabled={refreshing}
              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 transition-colors"
              title="Refresh"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            </button>
          </div>
          {/* Date filter pills */}
          <div className="flex items-center gap-2 px-4 pb-3">
            <Calendar size={12} className="text-slate-400 shrink-0" />
            <div className="flex flex-wrap gap-1.5">
              {DATE_FILTERS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setDateFilter(key)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    dateFilter === key
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {dateFilter !== "all" && (
              <span className="ml-auto text-xs text-slate-400">
                {filteredRows.length} of {total} accounts
              </span>
            )}
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                {["Account", "Business", "Role", "Status", "Joined", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 6 }).map((__, j) => (
                        <td key={j} className="px-4 py-3">
                          <div className="h-3.5 bg-slate-100 rounded animate-pulse" style={{ width: `${60 + ((i * j * 17) % 40)}%` }} />
                        </td>
                      ))}
                    </tr>
                  ))
                : filteredRows.length === 0
                ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center">
                      <Users size={36} className="mx-auto text-slate-200 mb-3" />
                      <p className="text-slate-400 text-sm">
                        {dateFilter !== "all" ? `No accounts signed up in this period` : "No accounts found"}
                      </p>
                    </td>
                  </tr>
                )
                : filteredRows.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <Avatar name={u.owner_name || u.email || "?"} />
                          <div className="min-w-0">
                            <div className="font-medium text-slate-800 truncate">{u.owner_name || "—"}</div>
                            <div className="flex items-center gap-1 text-xs text-slate-500 mt-0.5">
                              <Mail size={10} /><span className="truncate">{u.email || "—"}</span>
                            </div>
                            {u.phone_number && (
                              <div className="flex items-center gap-1 text-xs text-slate-400 mt-0.5">
                                <Phone size={10} /><span>{u.phone_number}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-700 max-w-[160px] truncate">{u.business_name || "—"}</td>
                      <td className="px-4 py-3">
                        <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${
                          u.role === "owner" ? "bg-slate-100 text-slate-700"
                          : u.role === "manager" ? "bg-blue-100 text-blue-700"
                          : "bg-slate-50 text-slate-500"
                        }`}>
                          {u.role || "owner"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${u.subscription_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                            {u.subscription_active ? "✓ Subscribed" : "No plan"}
                          </span>
                          <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${u.setup_complete ? "bg-indigo-100 text-indigo-700" : "bg-amber-50 text-amber-600"}`}>
                            {u.setup_complete ? "✓ Setup" : "Pending"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                        {u.created_at ? formatDate(u.created_at) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => openEdit(u)}
                            className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-50 hover:text-indigo-600 transition-colors"
                            title="Edit"
                          >
                            <Edit size={13} />
                          </button>
                          <button
                            onClick={() => void deleteUser(u)}
                            disabled={deletingId === u.id}
                            className="p-1.5 rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors disabled:opacity-40"
                            title="Delete"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>

        {!loading && filteredRows.length > 0 && (
          <div className="px-4 py-2.5 border-t border-slate-100 text-xs text-slate-400">
            Showing {filteredRows.length}{dateFilter !== "all" ? ` (filtered)` : ""} of {total} accounts
          </div>
        )}
      </div>

      {/* Edit modal */}
      {selected && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <Avatar name={selected.owner_name || selected.email || "?"} size={32} />
                <div>
                  <p className="font-semibold text-slate-900 text-sm">{selected.owner_name || "User"}</p>
                  <p className="text-xs text-slate-500">{selected.email || selected.id}</p>
                </div>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-slate-600 p-1">
                <X size={16} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Owner name</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-300 outline-none" value={form.owner_name} onChange={(e) => setForm((f) => ({ ...f, owner_name: e.target.value }))} placeholder="Owner name" />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Business name</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-300 outline-none" value={form.business_name} onChange={(e) => setForm((f) => ({ ...f, business_name: e.target.value }))} placeholder="Business name" />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Phone</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-300 outline-none" value={form.phone_number} onChange={(e) => setForm((f) => ({ ...f, phone_number: e.target.value }))} placeholder="+1234567890" />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Role</label>
                  <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-300 outline-none" value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
                    <option value="owner">Owner</option>
                    <option value="manager">Manager</option>
                    <option value="employee">Employee</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-6 pt-1">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 accent-indigo-600" checked={form.subscription_active} onChange={(e) => setForm((f) => ({ ...f, subscription_active: e.target.checked }))} />
                  <span className="text-sm text-slate-700">Subscription active</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 accent-indigo-600" checked={form.setup_complete} onChange={(e) => setForm((f) => ({ ...f, setup_complete: e.target.checked }))} />
                  <span className="text-sm text-slate-700">Setup complete</span>
                </label>
              </div>
            </div>
            <div className="flex justify-end gap-2 px-6 pb-5">
              <button className="px-4 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50" onClick={() => setSelected(null)}>
                Cancel
              </button>
              <button
                className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                onClick={() => void saveEdit()}
                disabled={saving}
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-5 right-5 z-50 px-4 py-2.5 rounded-xl shadow-lg text-sm font-medium text-white transition-all ${toast.type === "ok" ? "bg-emerald-600" : "bg-red-600"}`}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
