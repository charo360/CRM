"use client";

import { useEffect, useState } from "react";
import { ordersApi, customersApi, Order, Customer } from "@/lib/api";
import { formatCurrency, timeAgo } from "@/lib/utils";
import {
  ShoppingCart, Users, TrendingUp, CreditCard,
  ArrowUpRight, Clock, CheckCircle2,
} from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([ordersApi.list(), customersApi.list()])
      .then(([o, c]) => { setOrders(o); setCustomers(c); })
      .finally(() => setLoading(false));
  }, []);

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
      value: formatCurrency(totalRevenue),
      icon: TrendingUp,
      color: "text-indigo-600",
      bg: "bg-indigo-50",
    },
    {
      label: "Active Orders",
      value: activeOrders.length,
      icon: ShoppingCart,
      color: "text-orange-600",
      bg: "bg-orange-50",
    },
    {
      label: "Customers",
      value: customers.length,
      icon: Users,
      color: "text-blue-600",
      bg: "bg-blue-50",
    },
    {
      label: "Paid Orders",
      value: orders.filter((o) => o.payment_status === "Paid").length,
      icon: CreditCard,
      color: "text-green-600",
      bg: "bg-green-50",
    },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Overview</h1>
        <p className="text-slate-500 text-sm mt-1">Welcome back. Here's what's happening.</p>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent orders */}
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900">Recent Orders</h2>
            <Link href="/dashboard/orders" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
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
                        {formatCurrency(order.total_amount)}
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
          <div className="p-5 grid grid-cols-2 gap-3">
            {[
              { href: "/kds", label: "Open KDS", icon: "🖥️", desc: "Kitchen display" },
              { href: "/dashboard/orders", label: "Orders", icon: "📦", desc: "Manage orders" },
              { href: "/dashboard/channels", label: "Channels", icon: "📡", desc: "WhatsApp & more" },
              { href: "/dashboard/imports", label: "Import", icon: "⬆️", desc: "Bulk upload" },
              { href: "/dashboard/payments", label: "Payments", icon: "💰", desc: "Reconcile" },
              { href: "/dashboard/shop", label: "Shop", icon: "🛍️", desc: "Storefront" },
            ].map(({ href, label, icon, desc }) => (
              <Link
                key={href}
                href={href}
                className="flex flex-col gap-1 p-4 rounded-xl border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 transition-colors"
              >
                <span className="text-2xl">{icon}</span>
                <span className="text-sm font-semibold text-slate-800">{label}</span>
                <span className="text-xs text-slate-400">{desc}</span>
              </Link>
            ))}
          </div>
        </div>
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
  };
  const cls = map[status || ""] || "bg-slate-100 text-slate-500";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {status || "—"}
    </span>
  );
}
