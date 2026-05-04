"use client";

import { useEffect, useMemo, useState } from "react";
import { adminApi, type AdminUser } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Edit, Search, Shield, Trash2, Users } from "lucide-react";
import { isAuthenticated } from "@/lib/auth";
import { useRouter } from "next/navigation";

type EditForm = {
  owner_name: string;
  business_name: string;
  phone_number: string;
  role: string;
  subscription_active: boolean;
  setup_complete: boolean;
};

export default function AdminUsersManager() {
  const router = useRouter();
  const [accessChecked, setAccessChecked] = useState(false);
  const [hasAccess, setHasAccess] = useState(false);
  const [rows, setRows] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AdminUser | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [form, setForm] = useState<EditForm>({
    owner_name: "",
    business_name: "",
    phone_number: "",
    role: "owner",
    subscription_active: false,
    setup_complete: false,
  });

  async function loadUsers(query = q) {
    setLoading(true);
    try {
      const data = await adminApi.listUsers({ q: query, limit: 200, skip: 0 });
      setRows(data.users);
      setTotal(data.total);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      if (!isAuthenticated()) {
        router.replace("/login");
        setAccessChecked(true);
        setHasAccess(false);
        return;
      }
      try {
        const res = await adminApi.canAccess();
        setHasAccess(!!res.access);
        if (res.access) {
          await loadUsers("");
        }
      } catch {
        setHasAccess(false);
      } finally {
        setAccessChecked(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  if (!accessChecked) {
    return <div className="p-6 text-sm text-slate-500">Checking admin access…</div>;
  }

  if (!hasAccess) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <h1 className="text-lg font-semibold text-red-700">Access denied</h1>
          <p className="text-sm text-red-600 mt-1">
            This dashboard is for platform admins only.
          </p>
        </div>
      </div>
    );
  }

  const activeCount = useMemo(
    () => rows.filter((u) => u.subscription_active).length,
    [rows],
  );

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
      await loadUsers(q);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to update user");
    } finally {
      setSaving(false);
    }
  }

  async function deleteUser(u: AdminUser) {
    if (!confirm(`Delete user ${u.email || u.owner_name || u.id}? This cannot be undone.`)) return;
    setDeletingId(u.id);
    try {
      await adminApi.deleteUser(u.id);
      await loadUsers(q);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to delete user");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Admin Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">Manage all registered users</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <Users className="text-slate-500" size={18} />
            <div>
              <p className="text-xs text-slate-500">Total users</p>
              <p className="text-2xl font-bold text-slate-900">{total}</p>
            </div>
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <Shield className="text-emerald-600" size={18} />
            <div>
              <p className="text-xs text-slate-500">Active subscriptions</p>
              <p className="text-2xl font-bold text-slate-900">{activeCount}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-2">
        <Search size={16} className="text-slate-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by email, owner, business, phone"
          className="flex-1 text-sm outline-none"
        />
        <button
          onClick={() => {
            setQ(search.trim());
            void loadUsers(search.trim());
          }}
          className="px-3 py-1.5 rounded-lg bg-brand-dark text-white text-xs font-semibold"
        >
          Search
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {["User", "Business", "Role", "Status", "Created", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    <td className="px-4 py-3" colSpan={6}>
                      <div className="h-4 bg-slate-100 rounded animate-pulse" />
                    </td>
                  </tr>
                ))
              ) : rows.length === 0 ? (
                <tr>
                  <td className="px-4 py-8 text-center text-slate-500" colSpan={6}>
                    No users found
                  </td>
                </tr>
              ) : (
                rows.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-800">{u.owner_name || "—"}</div>
                      <div className="text-xs text-slate-500">{u.email || "—"}</div>
                      <div className="text-xs text-slate-400">{u.phone_number || "—"}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{u.business_name || "—"}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                        {u.role || "owner"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        <span className={`text-[11px] px-2 py-0.5 rounded-full ${u.subscription_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                          {u.subscription_active ? "Subscribed" : "No plan"}
                        </span>
                        <span className={`text-[11px] px-2 py-0.5 rounded-full ${u.setup_complete ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"}`}>
                          {u.setup_complete ? "Setup done" : "Setup pending"}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {u.created_at ? formatDate(u.created_at) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => openEdit(u)}
                          className="p-1.5 rounded hover:bg-blue-100 text-slate-500 hover:text-blue-700"
                          title="Edit user"
                        >
                          <Edit size={14} />
                        </button>
                        <button
                          onClick={() => void deleteUser(u)}
                          disabled={deletingId === u.id}
                          className="p-1.5 rounded hover:bg-red-100 text-slate-500 hover:text-red-700 disabled:opacity-50"
                          title="Delete user"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-xl p-6 space-y-4">
            <h3 className="text-lg font-semibold text-slate-900">Edit user</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input className="border rounded-lg px-3 py-2 text-sm" value={form.owner_name} onChange={(e) => setForm((f) => ({ ...f, owner_name: e.target.value }))} placeholder="Owner name" />
              <input className="border rounded-lg px-3 py-2 text-sm" value={form.business_name} onChange={(e) => setForm((f) => ({ ...f, business_name: e.target.value }))} placeholder="Business name" />
              <input className="border rounded-lg px-3 py-2 text-sm" value={form.phone_number} onChange={(e) => setForm((f) => ({ ...f, phone_number: e.target.value }))} placeholder="Phone" />
              <select className="border rounded-lg px-3 py-2 text-sm" value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
                <option value="owner">owner</option>
                <option value="manager">manager</option>
                <option value="employee">employee</option>
              </select>
            </div>
            <div className="flex gap-6 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.subscription_active} onChange={(e) => setForm((f) => ({ ...f, subscription_active: e.target.checked }))} />
                Subscription active
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.setup_complete} onChange={(e) => setForm((f) => ({ ...f, setup_complete: e.target.checked }))} />
                Setup complete
              </label>
            </div>
            <div className="flex justify-end gap-2">
              <button className="px-4 py-2 rounded-lg border text-sm" onClick={() => setSelected(null)}>
                Cancel
              </button>
              <button
                className="px-4 py-2 rounded-lg bg-brand-dark text-white text-sm font-semibold disabled:opacity-50"
                onClick={() => void saveEdit()}
                disabled={saving}
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

