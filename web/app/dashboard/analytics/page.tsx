"use client";

import { useEffect, useState } from "react";
import { analyticsApi, salesApi, ordersApi, customersApi, AnalyticsSummary, Sale, Order, Customer } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { BarChart2, Users, TrendingUp, ShoppingCart, Bell, MessageSquare, Calendar } from "lucide-react";

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [sales, setSales] = useState<Sale[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      analyticsApi.summary().catch(() => null),
      salesApi.list().catch(() => []),
      ordersApi.list().catch(() => []),
      customersApi.list().catch(() => []),
    ]).then(([s, sa, o, c]) => {
      setSummary(s);
      setSales(sa as Sale[]);
      setOrders(o as Order[]);
      setCustomers(c as Customer[]);
    }).finally(() => setLoading(false));
  }, []);

  // Compute from raw data as fallback
  const totalRevenue = sales.reduce((s, x) => s + x.amount, 0);
  const paidOrders = orders.filter((o) => o.payment_status === "Paid");
  const orderRevenue = paidOrders.reduce((s, o) => s + o.total_amount, 0);
  const combinedRevenue = totalRevenue + orderRevenue;

  const vipCount = customers.filter((c) => c.tags?.includes("VIP")).length;
  const newThisMonth = customers.filter((c) => {
    const d = new Date(c.created_at);
    const now = new Date();
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  }).length;

  // Revenue by month (last 6 months) from sales
  const monthlyRevenue = getLast6Months().map(({ label, start, end }) => {
    const total = sales
      .filter((s) => { const d = new Date(s.created_at); return d >= start && d < end; })
      .reduce((sum, s) => sum + s.amount, 0);
    return { label, total };
  });
  const maxMonthly = Math.max(...monthlyRevenue.map((m) => m.total), 1);

  // Top payment methods
  const methodMap: Record<string, number> = {};
  sales.forEach((s) => { methodMap[s.payment_method] = (methodMap[s.payment_method] || 0) + s.amount; });
  const topMethods = Object.entries(methodMap).sort((a, b) => b[1] - a[1]).slice(0, 5);

  // Stage distribution
  const stageMap: Record<string, number> = {};
  customers.forEach((c) => { const s = c.stage || "lead"; stageMap[s] = (stageMap[s] || 0) + 1; });

  const statsCards = [
    { label: "Total Revenue", value: formatCurrency(combinedRevenue), icon: TrendingUp, color: "text-indigo-600", bg: "bg-indigo-50" },
    { label: "Total Customers", value: customers.length, icon: Users, color: "text-blue-600", bg: "bg-blue-50" },
    { label: "Active Orders", value: orders.filter((o) => !["Done"].includes(o.fulfillment_status || "")).length, icon: ShoppingCart, color: "text-orange-600", bg: "bg-orange-50" },
    { label: "VIP Customers", value: vipCount, icon: BarChart2, color: "text-yellow-600", bg: "bg-yellow-50" },
    { label: "New This Month", value: newThisMonth, icon: Users, color: "text-green-600", bg: "bg-green-50" },
    { label: "Unread Messages", value: summary?.unread_messages ?? "—", icon: MessageSquare, color: "text-red-600", bg: "bg-red-50" },
    { label: "Follow-ups Today", value: summary?.followups_today ?? "—", icon: Bell, color: "text-purple-600", bg: "bg-purple-50" },
    { label: "Bookings Today", value: summary?.bookings_today ?? "—", icon: Calendar, color: "text-sky-600", bg: "bg-sky-50" },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
        <p className="text-slate-500 text-sm mt-1">Business performance overview</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statsCards.map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className="bg-white rounded-xl border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium text-slate-500">{label}</span>
              <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
                <Icon size={16} className={color} />
              </div>
            </div>
            <p className="text-2xl font-bold text-slate-900">
              {loading ? <span className="text-slate-300">—</span> : value}
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly revenue bar chart */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-900 mb-4">Revenue – Last 6 Months</h2>
          <div className="flex items-end gap-2 h-40">
            {monthlyRevenue.map(({ label, total }) => (
              <div key={label} className="flex-1 flex flex-col items-center gap-1">
                <span className="text-xs text-slate-500">{formatCurrency(total, "")}</span>
                <div
                  className="w-full rounded-t-md bg-indigo-500 transition-all"
                  style={{ height: `${Math.max((total / maxMonthly) * 120, total > 0 ? 4 : 0)}px` }}
                />
                <span className="text-[10px] text-slate-400">{label}</span>
              </div>
            ))}
          </div>
          {sales.length === 0 && !loading && (
            <p className="text-xs text-slate-400 text-center mt-2">No sales data yet</p>
          )}
        </div>

        {/* Payment methods */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-900 mb-4">Revenue by Payment Method</h2>
          {loading ? (
            <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-5 bg-slate-100 rounded animate-pulse" />)}</div>
          ) : topMethods.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">No data yet</p>
          ) : (
            <div className="space-y-3">
              {topMethods.map(([method, amount]) => {
                const pct = Math.round((amount / combinedRevenue) * 100) || 0;
                return (
                  <div key={method}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-slate-700 font-medium">{method}</span>
                      <span className="text-slate-500">{formatCurrency(amount)} ({pct}%)</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Customer stages */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-900 mb-4">Customer Pipeline</h2>
          {loading ? (
            <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-5 bg-slate-100 rounded animate-pulse" />)}</div>
          ) : (
            <div className="space-y-3">
              {[["lead", "text-slate-600"], ["contacted", "text-blue-600"], ["negotiating", "text-amber-600"], ["won", "text-green-600"], ["lost", "text-red-500"]].map(([stage, color]) => {
                const count = stageMap[stage] || 0;
                const pct = customers.length ? Math.round((count / customers.length) * 100) : 0;
                return (
                  <div key={stage}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={`font-medium capitalize ${color}`}>{stage}</span>
                      <span className="text-slate-500">{count} ({pct}%)</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${stage === "won" ? "bg-green-500" : stage === "lost" ? "bg-red-400" : stage === "negotiating" ? "bg-amber-400" : stage === "contacted" ? "bg-blue-400" : "bg-slate-300"}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Order fulfillment breakdown */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-900 mb-4">Order Fulfillment</h2>
          {loading ? (
            <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-5 bg-slate-100 rounded animate-pulse" />)}</div>
          ) : orders.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">No orders yet</p>
          ) : (
            <div className="space-y-3">
              {["New", "Confirmed", "Preparing", "Ready", "Done"].map((s) => {
                const count = orders.filter((o) => (o.fulfillment_status || "New") === s).length;
                const pct = Math.round((count / orders.length) * 100) || 0;
                const barColor = { New: "bg-red-400", Confirmed: "bg-orange-400", Preparing: "bg-yellow-400", Ready: "bg-green-400", Done: "bg-slate-300" }[s];
                return (
                  <div key={s}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-slate-700 font-medium">{s}</span>
                      <span className="text-slate-500">{count} ({pct}%)</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function getLast6Months() {
  const months = [];
  for (let i = 5; i >= 0; i--) {
    const d = new Date();
    d.setDate(1);
    d.setMonth(d.getMonth() - i);
    const start = new Date(d.getFullYear(), d.getMonth(), 1);
    const end = new Date(d.getFullYear(), d.getMonth() + 1, 1);
    const label = start.toLocaleString("default", { month: "short" });
    months.push({ label, start, end });
  }
  return months;
}
