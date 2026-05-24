"use client";

import { useEffect, useState } from "react";
import { ordersApi, customersApi, budgetApi, Order, Customer, api } from "@/lib/api";
import { formatCurrency, timeAgo } from "@/lib/utils";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  ShoppingCart,
  Users,
  TrendingUp,
  CreditCard,
  ArrowUpRight,
  Clock,
  Zap,
  Loader2,
  Send,
  MessageSquare,
  Bell,
  Megaphone,
  CalendarClock,
  Target,
  LineChart,
  Hash,
  Sparkles,
  Plug,
  AlertTriangle,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

export default function DashboardPage() {
  const { currency, ui, accountMode } = useBusiness();
  const [orders, setOrders] = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [pulse, setPulse] = useState<string>("");
  const [pulseLoading, setPulseLoading] = useState(false);
  const [sendingPulse, setSendingPulse] = useState(false);
  const [budget, setBudget] = useState<{ budgeted: number; actual: number; over: number; near: number } | null>(null);

  useEffect(() => {
    Promise.all([ordersApi.list(), customersApi.list()])
      .then(([o, c]) => { setOrders(o); setCustomers(c); })
      .finally(() => setLoading(false));
    loadPulse();
    budgetApi.vsActual().then((r: Record<string, unknown>) => {
      const items = (r.items as Array<{ pct_used: number | null; budgeted: number | null; actual: number }>) ?? [];
      setBudget({
        budgeted: (r.totals as { budgeted: number })?.budgeted ?? 0,
        actual: (r.totals as { actual: number })?.actual ?? 0,
        over: items.filter(i => i.pct_used !== null && i.pct_used >= 100).length,
        near: items.filter(i => i.pct_used !== null && i.pct_used >= 75 && i.pct_used < 100).length,
      });
    }).catch(() => {});
  }, []);

  async function loadPulse() {
    setPulseLoading(true);
    try {
      const res = await api.get<{ message?: string; summary?: string }>("/daily-pulse/preview");
      setPulse(res.message || res.summary || "");
    } catch { /* optional feature */ }
    finally { setPulseLoading(false); }
  }

  async function sendPulse() {
    setSendingPulse(true);
    try {
      await api.post("/daily-pulse/send", {});
      toast.success("Daily pulse sent to all customers!");
    } catch { toast.error("Failed to send pulse"); }
    finally { setSendingPulse(false); }
  }

  const totalRevenue = orders
    .filter((o) => o.payment_status === "Paid")
    .reduce((s, o) => s + o.total_amount, 0);

  const activeOrders = orders.filter(
    (o) => !["Done", "Delivered"].includes(o.fulfillment_status || o.delivery_status || "")
  );

  const recentOrders = [...orders]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5);

  const stats = [
    {
      label: "Total Revenue",
      value: formatCurrency(totalRevenue, currency),
      icon: TrendingUp,
      color: "text-brand-dark",
      bg: "bg-brand/10",
    },
    {
      label: ui.activeOrdersLabel,
      value: activeOrders.length,
      icon: ShoppingCart,
      color: "text-orange-600",
      bg: "bg-orange-50",
    },
    {
      label: ui.customersNavLabel,
      value: customers.length,
      icon: Users,
      color: "text-blue-600",
      bg: "bg-blue-50",
    },
    {
      label: ui.paidOrdersLabel,
      value: orders.filter((o) => o.payment_status === "Paid").length,
      icon: CreditCard,
      color: "text-green-600",
      bg: "bg-green-50",
    },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{ui.overviewTitle}</h1>
        <p className="text-slate-500 text-sm mt-1">{ui.overviewSubtitle}</p>
        {accountMode === "individual" && (
          <p className="text-xs text-brand-dark/90 mt-2">
            Workspace mode: individual — same tools as businesses, with wording fit for solo use.
          </p>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className="bg-white rounded-xl border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-slate-500 font-medium">{label}</span>
              <div className={`w-9 h-9 rounded-lg ${bg} flex items-center justify-center`}>
                <Icon size={18} className={color} />
              </div>
            </div>
            <p className="text-2xl font-bold text-slate-900">
              {loading ? <span className="text-slate-300">—</span> : value}
            </p>
          </div>
        ))}
      </div>

      {/* Budget snapshot */}
      {budget !== null && (budget.budgeted > 0 || budget.actual > 0) && (
        <Link href="/dashboard/finance" className="block">
          <div className={`rounded-xl border p-4 flex items-center gap-4 transition-colors hover:border-brand/40 ${
            budget.over > 0 ? "bg-red-50 border-red-200" :
            budget.near > 0 ? "bg-amber-50 border-amber-200" :
            "bg-white border-slate-200"
          }`}>
            <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
              budget.over > 0 ? "bg-red-100" : budget.near > 0 ? "bg-amber-100" : "bg-blue-50"
            }`}>
              {budget.over > 0
                ? <AlertTriangle size={18} className="text-red-600" />
                : <Wallet size={18} className={budget.near > 0 ? "text-amber-600" : "text-blue-600"} />
              }
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-1">
                <p className="text-sm font-semibold text-slate-800">
                  {budget.over > 0
                    ? `${budget.over} categor${budget.over > 1 ? "ies" : "y"} over budget this month`
                    : budget.near > 0
                    ? `${budget.near} categor${budget.near > 1 ? "ies" : "y"} nearing budget limit`
                    : "Budget on track this month"}
                </p>
                <span className="text-xs text-slate-400 flex items-center gap-1 shrink-0 ml-2">
                  View <ArrowUpRight size={11} />
                </span>
              </div>
              <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(budget.budgeted > 0 ? Math.round((budget.actual / budget.budgeted) * 100) : 0, 100)}%`,
                    background: budget.over > 0 ? "#ef4444" : budget.near > 0 ? "#f59e0b" : "#22c55e",
                  }}
                />
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {formatCurrency(budget.actual, "KES")} spent of {formatCurrency(budget.budgeted, "KES")} budgeted
              </p>
            </div>
          </div>
        </Link>
      )}

      {/* Sales & growth — links pipeline to campaigns (Zilo = sell + reach) */}
      <section className="rounded-2xl border border-[#009B3A]/20 bg-gradient-to-br from-emerald-50/70 via-white to-sky-50/50 p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Sales &amp; growth</h2>
        <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-600">
          Turn attention into revenue: work your pipeline here, then launch or refine campaigns and creative with Zilo
          Chat — without switching products.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200/90 bg-white/95 p-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Pipeline &amp; sell</p>
            <ul className="space-y-2 text-sm">
              {[
                { href: "/dashboard/customers", label: ui.customersNavLabel, Icon: Users },
                { href: "/dashboard/followups", label: "Follow-ups", Icon: Bell },
                { href: "/dashboard/messages", label: "Messages", Icon: MessageSquare },
                { href: "/dashboard/orders", label: "Orders", Icon: ShoppingCart },
              ].map(({ href, label, Icon }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="flex items-center gap-2 font-medium text-slate-700 hover:text-[#009B3A] hover:underline"
                  >
                    <Icon size={15} className="shrink-0 text-slate-400" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-slate-200/90 bg-white/95 p-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Reach &amp; campaigns</p>
            <ul className="space-y-2 text-sm">
              {[
                { href: "/dashboard/broadcast", label: "Broadcast", Icon: Megaphone },
                { href: "/dashboard/social-scheduler", label: "Social scheduler", Icon: CalendarClock },
                { href: "/dashboard/meta-ads", label: "Meta Ads", Icon: Target },
                { href: "/dashboard/google-ads", label: "Google Ads", Icon: LineChart },
                { href: "/dashboard/x-ads", label: "X Ads", Icon: Hash },
                { href: "/dashboard/assistant", label: "Zilo Chat (AI)", Icon: Sparkles },
                { href: "/dashboard/integrations", label: "Integrations", Icon: Plug },
              ].map(({ href, label, Icon }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="flex items-center gap-2 font-medium text-slate-700 hover:text-[#009B3A] hover:underline"
                  >
                    <Icon size={15} className="shrink-0 text-slate-400" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent orders */}
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900">{ui.recentOrdersTitle}</h2>
            <Link href="/dashboard/orders" className="text-xs text-brand-dark hover:underline flex items-center gap-1">
              View all <ArrowUpRight size={12} />
            </Link>
          </div>
          <div className="divide-y divide-slate-100">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="px-5 py-3 animate-pulse">
                    <div className="h-4 bg-slate-100 rounded w-3/4 mb-1" />
                    <div className="h-3 bg-slate-100 rounded w-1/2" />
                  </div>
                ))
              : recentOrders.map((order) => (
                  <div key={order.id} className="px-5 py-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-slate-800">
                        #{order.order_number || order.id.slice(-6)} · {order.customer_name}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1">
                        <Clock size={10} /> {timeAgo(order.created_at)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-slate-900">
                        {formatCurrency(order.total_amount, currency)}
                      </p>
                      <StatusBadge status={order.fulfillment_status || order.payment_status} />
                    </div>
                  </div>
                ))}
            {!loading && recentOrders.length === 0 && (
              <p className="px-5 py-6 text-sm text-slate-400 text-center">No orders yet</p>
            )}
          </div>
        </div>

        {/* Quick actions */}
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="px-5 py-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900">Quick Actions</h2>
          </div>
          <div className="p-5 grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              ...(ui.showKdsNav
                ? [{ href: "/kds", label: "Open KDS", icon: "🖥️", desc: "Kitchen display" as const }]
                : []),
              { href: "/dashboard/orders", label: "Orders", icon: "📦", desc: "Manage orders" },
              { href: "/dashboard/channels", label: "Channels", icon: "📡", desc: "WhatsApp & more" },
              { href: "/dashboard/broadcast", label: "Broadcast", icon: "📣", desc: "Reach your list" },
              { href: "/dashboard/assistant", label: "Zilo Chat", icon: "✨", desc: "Sales & growth AI" },
              { href: "/dashboard/imports", label: "Import", icon: "⬆️", desc: "Bulk upload" },
              { href: "/dashboard/payments", label: "Payments", icon: "💰", desc: "Reconcile" },
              { href: "/dashboard/shop", label: ui.shopNavLabel, icon: "🛍️", desc: "Storefront" },
            ].map(({ href, label, icon, desc }) => (
              <Link
                key={href}
                href={href}
                className="flex flex-col gap-1 p-4 rounded-xl border border-slate-200 hover:border-brand/50 hover:bg-brand/10 transition-colors"
              >
                <span className="text-2xl">{icon}</span>
                <span className="text-sm font-semibold text-slate-800">{label}</span>
                <span className="text-xs text-slate-400">{desc}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Daily Pulse */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center">
              <Zap size={16} className="text-brand-dark" />
            </div>
            <div>
              <h2 className="font-semibold text-slate-900">Daily Pulse</h2>
              <p className="text-[11px] text-slate-500 mt-0.5">AI snapshot — useful before a broadcast or follow-up push</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={loadPulse} disabled={pulseLoading}
              className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 disabled:opacity-50">
              {pulseLoading ? "Loading…" : "Refresh"}
            </button>
            <button onClick={sendPulse} disabled={sendingPulse || !pulse}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand-dark text-white rounded-lg hover:bg-brand disabled:opacity-50">
              {sendingPulse ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
              Send to Customers
            </button>
          </div>
        </div>
        {pulseLoading ? (
          <div className="h-16 bg-slate-50 rounded-xl animate-pulse" />
        ) : pulse ? (
          <p className="text-sm text-slate-700 bg-brand/10 rounded-xl px-4 py-3 leading-relaxed">{pulse}</p>
        ) : (
          <p className="text-sm text-slate-400 text-center py-4">Click Refresh to generate today&apos;s business pulse</p>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  const map: Record<string, string> = {
    New: "bg-red-100 text-red-700",
    Confirmed: "bg-orange-100 text-orange-700",
    Preparing: "bg-yellow-100 text-yellow-700",
    Ready: "bg-green-100 text-green-700",
    Done: "bg-slate-100 text-slate-500",
    Paid: "bg-emerald-100 text-emerald-700",
    Pending: "bg-amber-100 text-amber-700",
    Partial: "bg-blue-100 text-blue-700",
  };
  const label = status === "Partial" ? "BNPL / Partial" : status;
  const cls = map[status || ""] || "bg-slate-100 text-slate-500";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {label || "—"}
    </span>
  );
}
