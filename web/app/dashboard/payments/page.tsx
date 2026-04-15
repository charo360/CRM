"use client";

import { useEffect, useState } from "react";
import { ordersApi, Order } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { CheckCircle2, Clock, AlertCircle, Search, Download } from "lucide-react";

type PaymentStatus = "Paid" | "Pending" | "Partial";

const STATUS_CONFIG: Record<PaymentStatus, { icon: React.ReactNode; cls: string }> = {
  Paid:    { icon: <CheckCircle2 size={14} />, cls: "text-green-700 bg-green-100" },
  Pending: { icon: <Clock size={14} />,        cls: "text-amber-700 bg-amber-100" },
  Partial: { icon: <AlertCircle size={14} />,  cls: "text-blue-700 bg-blue-100" },
};

/** API may return paid/unpaid/partial in any casing — normalize for UI. */
function normalizePaymentStatus(raw: string | undefined | null): PaymentStatus {
  const s = (raw || "").toLowerCase();
  if (s === "paid") return "Paid";
  if (s === "partial") return "Partial";
  return "Pending";
}

export default function PaymentsPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [markingPaidId, setMarkingPaidId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"All" | PaymentStatus>("All");

  useEffect(() => {
    ordersApi.list().then(setOrders).finally(() => setLoading(false));
  }, []);

  const filtered = orders.filter((o) => {
    const ps = normalizePaymentStatus(o.payment_status);
    const matchFilter = filter === "All" || ps === filter;
    const matchSearch =
      !search ||
      o.customer_name.toLowerCase().includes(search.toLowerCase()) ||
      (o.order_number || "").includes(search);
    return matchFilter && matchSearch;
  });

  const paid = orders.filter((o) => normalizePaymentStatus(o.payment_status) === "Paid");
  const pending = orders.filter((o) => normalizePaymentStatus(o.payment_status) === "Pending");
  const partial = orders.filter((o) => normalizePaymentStatus(o.payment_status) === "Partial");

  const totalPaid = paid.reduce((s, o) => s + o.total_amount, 0);
  const totalPending = pending.reduce((s, o) => s + o.total_amount, 0);
  const totalPartial = partial.reduce((s, o) => s + o.total_amount, 0);

  function exportCSV() {
    const rows = [
      ["Order #", "Customer", "Amount", "Status", "Date"],
      ...filtered.map((o) => [
        o.order_number || o.id,
        o.customer_name,
        o.total_amount,
        o.payment_status,
        formatDate(o.created_at),
      ]),
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "payments.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function markPaid(order: Order) {
    setMarkingPaidId(order.id);
    try {
      await ordersApi.updateStatus(order.id, { payment_status: "Paid" });
      const updated = await ordersApi.list();
      setOrders(updated);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not mark as paid");
    } finally {
      setMarkingPaidId(null);
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Payments</h1>
          <p className="text-slate-500 text-sm mt-1">Reconcile and track all order payments</p>
        </div>
        <button
          onClick={exportCSV}
          className="flex items-center gap-2 px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 font-medium"
        >
          <Download size={15} />
          Export CSV
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryCard
          label="Collected"
          amount={totalPaid}
          count={paid.length}
          color="border-green-200 bg-green-50"
          textColor="text-green-700"
        />
        <SummaryCard
          label="Outstanding"
          amount={totalPending}
          count={pending.length}
          color="border-amber-200 bg-amber-50"
          textColor="text-amber-700"
        />
        <SummaryCard
          label="Partial"
          amount={totalPartial}
          count={partial.length}
          color="border-blue-200 bg-blue-50"
          textColor="text-blue-700"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by customer or order #..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="flex gap-2">
          {(["All", "Paid", "Pending", "Partial"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                filter === s
                  ? "bg-indigo-600 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {["Order #", "Customer", "Phone", "Amount", "Status", "Fulfillment", "Date", "Action"].map((h) => (
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
                      {Array.from({ length: 8 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <div className="h-4 bg-slate-100 rounded animate-pulse" />
                        </td>
                      ))}
                    </tr>
                  ))
                : filtered.map((order) => {
                    const ps = normalizePaymentStatus(order.payment_status);
                    const cfg = STATUS_CONFIG[ps];
                    return (
                      <tr key={order.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-mono text-slate-700 text-xs">
                          #{order.order_number || order.id.slice(-8)}
                        </td>
                        <td className="px-4 py-3 font-medium text-slate-800">{order.customer_name}</td>
                        <td className="px-4 py-3 text-slate-500 text-xs">{order.customer_phone}</td>
                        <td className="px-4 py-3 font-semibold text-slate-900">
                          {formatCurrency(order.total_amount)}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${cfg.cls}`}>
                            {cfg.icon} {ps}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500">
                          {order.fulfillment_status || "—"}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-400">{formatDate(order.created_at)}</td>
                        <td className="px-4 py-3">
                          {ps !== "Paid" ? (
                            <button
                              type="button"
                              onClick={() => void markPaid(order)}
                              disabled={markingPaidId === order.id}
                              className="px-3 py-1 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-wait"
                            >
                              {markingPaidId === order.id ? "Saving…" : "Mark Paid"}
                            </button>
                          ) : (
                            <span className="text-xs text-green-600 font-medium">✓ Paid</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <p className="text-center text-sm text-slate-400 py-12">No payments match your filters</p>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryCard({
  label, amount, count, color, textColor,
}: {
  label: string; amount: number; count: number; color: string; textColor: string;
}) {
  return (
    <div className={`rounded-xl border-2 p-5 ${color}`}>
      <p className="text-sm font-medium text-slate-600">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${textColor}`}>{formatCurrency(amount)}</p>
      <p className="text-xs text-slate-500 mt-1">{count} order{count !== 1 ? "s" : ""}</p>
    </div>
  );
}
