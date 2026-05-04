"use client";

import { useEffect, useMemo, useState } from "react";
import { adminApi, type AdminUser } from "@/lib/api";
import {
  BadgeCheck,
  Building2,
  CalendarDays,
  Shield,
  TrendingUp,
  Users,
} from "lucide-react";
import { formatDate } from "@/lib/utils";

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">{label}</p>
          <p className="text-3xl font-bold text-slate-900 mt-1">{value}</p>
          {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
        </div>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon size={18} />
        </div>
      </div>
    </div>
  );
}

export default function AdminAnalyticsPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    adminApi.listUsers({ limit: 500 }).then((d) => { setUsers(d.users); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const total = users.length;
  const subscribed = useMemo(() => users.filter((u) => u.subscription_active).length, [users]);
  const setupDone = useMemo(() => users.filter((u) => u.setup_complete).length, [users]);
  const owners = useMemo(() => users.filter((u) => !u.business_id).length, [users]);
  const subPct = total ? Math.round((subscribed / total) * 100) : 0;
  const setupPct = total ? Math.round((setupDone / total) * 100) : 0;

  // Signups by month (last 6)
  const byMonth = useMemo(() => {
    const map: Record<string, number> = {};
    users.forEach((u) => {
      if (!u.created_at) return;
      const d = new Date(u.created_at);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      map[key] = (map[key] || 0) + 1;
    });
    const months = Object.keys(map).sort().slice(-6);
    return months.map((k) => ({ month: k, count: map[k] }));
  }, [users]);

  const maxCount = Math.max(...byMonth.map((b) => b.count), 1);

  // Recent signups
  const recent = useMemo(
    () => [...users].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? "")).slice(0, 8),
    [users],
  );

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total accounts" value={loading ? "—" : total} icon={Users} color="bg-slate-100 text-slate-600" />
        <StatCard label="Subscribed" value={loading ? "—" : subscribed} sub={`${subPct}% of accounts`} icon={BadgeCheck} color="bg-emerald-100 text-emerald-700" />
        <StatCard label="Setup complete" value={loading ? "—" : setupDone} sub={`${setupPct}% of accounts`} icon={Shield} color="bg-indigo-100 text-indigo-700" />
        <StatCard label="Business owners" value={loading ? "—" : owners} icon={Building2} color="bg-amber-100 text-amber-700" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Signups by month */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-2 mb-5">
            <TrendingUp size={15} className="text-indigo-600" />
            <h2 className="text-sm font-semibold text-slate-800">Signups — last 6 months</h2>
          </div>
          {loading ? (
            <div className="h-32 bg-slate-50 rounded-lg animate-pulse" />
          ) : byMonth.length === 0 ? (
            <p className="text-sm text-slate-400 py-6 text-center">No data</p>
          ) : (
            <div className="flex items-end gap-2 h-32">
              {byMonth.map(({ month, count }) => (
                <div key={month} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-[10px] font-medium text-slate-600">{count}</span>
                  <div
                    className="w-full rounded-t-md bg-indigo-500 transition-all"
                    style={{ height: `${Math.round((count / maxCount) * 100)}%`, minHeight: 4 }}
                  />
                  <span className="text-[10px] text-slate-400">{month.slice(5)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Subscription breakdown */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-2 mb-5">
            <BadgeCheck size={15} className="text-emerald-600" />
            <h2 className="text-sm font-semibold text-slate-800">Subscription breakdown</h2>
          </div>
          {loading ? (
            <div className="h-32 bg-slate-50 rounded-lg animate-pulse" />
          ) : (
            <div className="space-y-3">
              {[
                { label: "Subscribed", value: subscribed, total, color: "bg-emerald-500" },
                { label: "No plan", value: total - subscribed, total, color: "bg-slate-200" },
                { label: "Setup done", value: setupDone, total, color: "bg-indigo-500" },
                { label: "Setup pending", value: total - setupDone, total, color: "bg-amber-300" },
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <div className="flex justify-between text-xs text-slate-600 mb-1">
                    <span>{label}</span>
                    <span className="font-semibold">{value}</span>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${color}`}
                      style={{ width: total ? `${Math.round((value / total) * 100)}%` : "0%" }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent signups */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3.5 border-b border-slate-100">
          <CalendarDays size={14} className="text-slate-500" />
          <h2 className="text-sm font-semibold text-slate-800">Recent signups</h2>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              {["Name", "Email", "Business", "Subscribed", "Joined"].map((h) => (
                <th key={h} className="px-4 py-2.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 5 }).map((__, j) => (
                      <td key={j} className="px-4 py-3"><div className="h-3 bg-slate-100 rounded animate-pulse" /></td>
                    ))}
                  </tr>
                ))
              : recent.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 font-medium text-slate-800">{u.owner_name || "—"}</td>
                    <td className="px-4 py-2.5 text-slate-500 text-xs">{u.email || "—"}</td>
                    <td className="px-4 py-2.5 text-slate-600">{u.business_name || "—"}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[11px] px-2 py-0.5 rounded-full ${u.subscription_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                        {u.subscription_active ? "Yes" : "No"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-400">{u.created_at ? formatDate(u.created_at) : "—"}</td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
