"use client";

import { useEffect, useState } from "react";
import { ordersApi, Order } from "@/lib/api";
import { formatCurrency, timeAgo } from "@/lib/utils";
import { Search, RefreshCw, ChevronDown } from "lucide-react";

type FS = string;

const FULFILLMENT_STATUSES = ["All", "New", "Confirmed", "Preparing", "Ready", "Done"];
const DELIVERY_TYPES = ["All", "dine-in", "pickup", "delivery"];

const STATUS_COLORS: Record<string, string> = {
  New:       "bg-red-100 text-red-700",
  Confirmed: "bg-orange-100 text-orange-700",
  Preparing: "bg-yellow-100 text-yellow-700",
  Ready:     "bg-green-100 text-green-700",
  Done:      "bg-slate-100 text-slate-500",
  Paid:      "bg-emerald-100 text-emerald-700",
  Pending:   "bg-amber-100 text-amber-700",
  Partial:   "bg-blue-100 text-blue-700",
};

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [typeFilter, setTypeFilter] = useState("All");
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await ordersApi.list();
      setOrders(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function advanceStatus(order: Order) {
    const flow = ["New", "Confirmed", "Preparing", "Ready", "Done"];
    const current = order.fulfillment_status || "New";
    const nextIdx = flow.indexOf(current) + 1;
    if (nextIdx >= flow.length) return;
    setUpdatingId(order.id);
    try {
      await ordersApi.updateProgress(order.id, { fulfillment_status: flow[nextIdx] });
      await load();
    } finally {
      setUpdatingId(null);
    }
  }

  const filtered = orders.filter((o) => {
    const matchSearch =
      !search ||
      o.customer_name.toLowerCase().includes(search.toLowerCase()) ||
      (o.order_number || "").includes(search) ||
      o.product.toLowerCase().includes(search.toLowerCase());
    const matchStatus =
      statusFilter === "All" || (o.fulfillment_status || "New") === statusFilter;
    const matchType =
      typeFilter === "All" ||
      (o.delivery_type || "").toLowerCase() === typeFilter.toLowerCase();
    return matchSearch && matchStatus && matchType;
  });

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Orders</h1>
          <p className="text-slate-500 text-sm mt-1">{orders.length} total orders</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search customer, order #, product..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <Select value={statusFilter} onChange={setStatusFilter} options={FULFILLMENT_STATUSES} label="Status" />
        <Select value={typeFilter} onChange={setTypeFilter} options={DELIVERY_TYPES} label="Type" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {["Order", "Customer", "Items", "Type", "Status", "Payment", "Total", "Time", "Action"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 9 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <div className="h-4 bg-slate-100 rounded animate-pulse" />
                        </td>
                      ))}
                    </tr>
                  ))
                : filtered.map((order) => {
                    const fs = order.fulfillment_status || "New";
                    const flow = ["New", "Confirmed", "Preparing", "Ready", "Done"];
                    const nextStatus = flow[flow.indexOf(fs) + 1];
                    const items = order.items?.length ? order.items : null;
                    return (
                      <tr key={order.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-slate-800">
                          #{order.order_number || order.id.slice(-6)}
                        </td>
                        <td className="px-4 py-3">
                          <p className="font-medium text-slate-800">{order.customer_name}</p>
                          <p className="text-xs text-slate-400">{order.customer_phone}</p>
                        </td>
                        <td className="px-4 py-3 max-w-[160px]">
                          {items ? (
                            <div className="space-y-0.5">
                              {items.slice(0, 2).map((it, i) => (
                                <p key={i} className="text-xs text-slate-700 truncate">
                                  {it.quantity}× {it.product_name}
                                </p>
                              ))}
                              {items.length > 2 && (
                                <p className="text-xs text-slate-400">+{items.length - 2} more</p>
                              )}
                            </div>
                          ) : (
                            <p className="text-xs text-slate-700 truncate">{order.quantity}× {order.product}</p>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-600 capitalize text-xs">
                          {order.delivery_type || "—"}
                          {order.table_number && (
                            <span className="ml-1 text-slate-400">#{order.table_number}</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <Badge status={fs} />
                        </td>
                        <td className="px-4 py-3">
                          <Badge status={order.payment_status} />
                        </td>
                        <td className="px-4 py-3 font-semibold text-slate-800">
                          {formatCurrency(order.total_amount)}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-400">
                          {timeAgo(order.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          {nextStatus ? (
                            <button
                              onClick={() => advanceStatus(order)}
                              disabled={updatingId === order.id}
                              className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                            >
                              {updatingId === order.id ? "..." : `→ ${nextStatus}`}
                            </button>
                          ) : (
                            <span className="text-xs text-slate-400">Done ✓</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <p className="text-center text-sm text-slate-400 py-12">No orders match your filters</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Badge({ status }: { status: string | null }) {
  const cls = STATUS_COLORS[status || ""] || "bg-slate-100 text-slate-500";
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {status || "—"}
    </span>
  );
}

function Select({
  value, onChange, options, label,
}: {
  value: string; onChange: (v: string) => void; options: string[]; label: string;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-slate-700"
      >
        {options.map((o) => (
          <option key={o} value={o}>{o === "All" ? `${label}: All` : o}</option>
        ))}
      </select>
      <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
    </div>
  );
}
