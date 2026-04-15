"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { Users, Trophy, TrendingUp, ShoppingBag, Loader2, RefreshCw } from "lucide-react";

interface EmployeeSales {
  user_id: string;
  name: string;
  total: number;
  count: number;
}

export default function TeamAnalyticsPage() {
  const [data, setData] = useState<EmployeeSales[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<EmployeeSales[]>("/sales/by-employee");
      setData(res);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const totalRevenue = data.reduce((s, e) => s + e.total, 0);
  const totalSales = data.reduce((s, e) => s + e.count, 0);
  const topPerformer = data[0];

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Team Analytics</h1>
          <p className="text-slate-500 text-sm mt-1">Sales performance by team member</p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-slate-500 font-medium">Team Members</p>
            <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center">
              <Users size={16} className="text-indigo-600" />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{data.length}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-slate-500 font-medium">Total Revenue</p>
            <div className="w-8 h-8 rounded-lg bg-green-50 flex items-center justify-center">
              <TrendingUp size={16} className="text-green-600" />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{formatCurrency(totalRevenue)}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-slate-500 font-medium">Total Sales</p>
            <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
              <ShoppingBag size={16} className="text-blue-600" />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{totalSales}</p>
        </div>
      </div>

      {/* Top Performer */}
      {topPerformer && (
        <div className="bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200 rounded-xl p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-amber-400 flex items-center justify-center shrink-0">
            <Trophy size={22} className="text-white" />
          </div>
          <div>
            <p className="text-xs font-semibold text-amber-600 uppercase tracking-wide">Top Performer</p>
            <p className="text-lg font-bold text-slate-900">{topPerformer.name}</p>
            <p className="text-sm text-slate-600">{formatCurrency(topPerformer.total)} · {topPerformer.count} sales</p>
          </div>
        </div>
      )}

      {/* Leaderboard */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">Sales Leaderboard</h2>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="animate-spin text-indigo-600" size={24} />
          </div>
        ) : data.length === 0 ? (
          <p className="text-center text-slate-400 text-sm py-12">No sales data yet</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {data.map((emp, idx) => {
              const pct = totalRevenue > 0 ? (emp.total / totalRevenue) * 100 : 0;
              return (
                <div key={emp.user_id} className="flex items-center gap-4 px-5 py-4">
                  <span className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                    idx === 0 ? "bg-amber-100 text-amber-700"
                    : idx === 1 ? "bg-slate-200 text-slate-600"
                    : idx === 2 ? "bg-orange-100 text-orange-700"
                    : "bg-slate-100 text-slate-500"
                  }`}>
                    {idx + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <p className="font-medium text-slate-800 truncate">{emp.name}</p>
                      <div className="flex items-center gap-3 shrink-0 ml-4">
                        <span className="text-xs text-slate-400">{emp.count} sales</span>
                        <span className="font-semibold text-slate-900">{formatCurrency(emp.total)}</span>
                      </div>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-indigo-500 transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">{pct.toFixed(1)}% of team revenue</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
