"use client";

import { useEffect, useState, useCallback } from "react";
import { ordersApi, Order, OrderPayment } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { CheckCircle2, Clock, AlertCircle, Search, Download, ChevronDown, ChevronRight, RefreshCw, X, Check } from "lucide-react";

type PaymentStatus = "Paid" | "Pending" | "Partial";

const PAYMENT_METHODS = ["M-Pesa", "Cash", "Bank Transfer", "Airtel Money", "Card", "PayPal", "Other"];

const STATUS_CONFIG: Record<PaymentStatus, { icon: React.ReactNode; cls: string; label: string }> = {
  Paid:    { icon: <CheckCircle2 size={14} />, cls: "text-green-700 bg-green-100", label: "Paid" },
  Pending: { icon: <Clock size={14} />,        cls: "text-amber-700 bg-amber-100", label: "Pending" },
  Partial: { icon: <AlertCircle size={14} />,  cls: "text-blue-700 bg-blue-100",  label: "BNPL / Partial" },
};

/** API may return paid/unpaid/partial in any casing — normalize for UI. */
function normalizePaymentStatus(raw: string | undefined | null): PaymentStatus {
  const s = (raw || "").toLowerCase();
  if (s === "paid") return "Paid";
  if (s === "partial") return "Partial";
  return "Pending";
}

export default function PaymentsPage() {
  const [orders, setOrders]   = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState("");
  const [filter, setFilter]   = useState<"All" | PaymentStatus>("All");

  // Record payment modal
  const [payModal, setPayModal]   = useState<Order | null>(null);
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState("M-Pesa");
  const [payNote, setPayNote]     = useState("");
  const [saving, setSaving]       = useState(false);

  // Payment history per order (expandable rows)
  const [expanded, setExpanded]         = useState<string | null>(null);
  const [history, setHistory]           = useState<Record<string, OrderPayment[]>>({});
  const [loadingHistory, setLoadingHistory] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    ordersApi.list().then(setOrders).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = orders.filter((o) => {
    const ps = normalizePaymentStatus(o.payment_status);
    const matchFilter = filter === "All" || ps === filter;
    const matchSearch =
      !search ||
      o.customer_name.toLowerCase().includes(search.toLowerCase()) ||
      (o.order_number || "").includes(search);
    return matchFilter && matchSearch;
  });

  const paid    = orders.filter((o) => normalizePaymentStatus(o.payment_status) === "Paid");
  const pending = orders.filter((o) => normalizePaymentStatus(o.payment_status) === "Pending");
  const partial = orders.filter((o) => normalizePaymentStatus(o.payment_status) === "Partial");

  const totalCollected = paid.reduce((s, o) => s + (o.amount_paid ?? o.total_amount), 0)
    + partial.reduce((s, o) => s + (o.amount_paid ?? 0), 0);
  const totalOutstanding = pending.reduce((s, o) => s + o.total_amount, 0)
    + partial.reduce((s, o) => s + (o.amount_remaining ?? o.total_amount), 0);
  const totalPartialOrders = partial.reduce((s, o) => s + o.total_amount, 0);

  function exportCSV() {
    const rows = [
      ["Order #", "Customer", "Total", "Paid", "Remaining", "Status", "Date"],
      ...filtered.map((o) => [
        o.order_number || o.id,
        o.customer_name,
        o.total_amount,
        o.amount_paid ?? "",
        o.amount_remaining ?? "",
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

  function openPayModal(order: Order) {
    setPayModal(order);
    const remaining = order.amount_remaining ?? order.total_amount;
    setPayAmount(String(remaining > 0 ? remaining : order.total_amount));
    setPayMethod("M-Pesa");
    setPayNote("");
  }

  async function submitPayment() {
    if (!payModal) return;
    const amt = parseFloat(payAmount);
    if (isNaN(amt) || amt <= 0) { alert("Enter a valid amount"); return; }
    setSaving(true);
    try {
      await ordersApi.recordPayment(payModal.id, { amount: amt, method: payMethod, note: payNote });
      setPayModal(null);
      // Refresh history if expanded
      if (expanded === payModal.id) {
        const h = await ordersApi.getPayments(payModal.id);
        setHistory(prev => ({ ...prev, [payModal.id]: h }));
      }
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not record payment");
    } finally {
      setSaving(false);
    }
  }

  async function toggleHistory(orderId: string) {
    if (expanded === orderId) { setExpanded(null); return; }
    setExpanded(orderId);
    if (!history[orderId]) {
      setLoadingHistory(orderId);
      try {
        const h = await ordersApi.getPayments(orderId);
        setHistory(prev => ({ ...prev, [orderId]: h }));
      } finally {
        setLoadingHistory(null);
      }
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Payments</h1>
          <p className="text-slate-500 text-sm mt-1">Track instalments, deposits and full payments</p>
        </div>
        <button onClick={exportCSV}
          className="flex items-center gap-2 px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 font-medium">
          <Download size={15} /> Export CSV
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryCard label="Total Collected" amount={totalCollected} count={paid.length + partial.length}
          color="border-green-200 bg-green-50" textColor="text-green-700" />
        <SummaryCard label="Outstanding Balance" amount={totalOutstanding} count={pending.length + partial.length}
          color="border-amber-200 bg-amber-50" textColor="text-amber-700" />
        <SummaryCard label="BNPL / Partial" amount={totalPartialOrders} count={partial.length}
          color="border-blue-200 bg-blue-50" textColor="text-blue-700" />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by customer or order #..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
        </div>
        <div className="flex gap-2">
          {(["All", "Paid", "Pending", "Partial"] as const).map((s) => (
            <button key={s} onClick={() => setFilter(s)}
              className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                filter === s ? "bg-brand-dark text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}>{s}</button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                <th className="w-8 px-2 py-3" />
                {["Order #", "Customer", "Total", "Paid", "Remaining", "Status", "Date", "Action"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      {Array.from({ length: 9 }).map((_, j) => (
                        <td key={j} className="px-4 py-3"><div className="h-4 bg-slate-100 rounded animate-pulse" /></td>
                      ))}
                    </tr>
                  ))
                : filtered.map((order) => {
                    const ps = normalizePaymentStatus(order.payment_status);
                    const cfg = STATUS_CONFIG[ps];
                    const isExpanded = expanded === order.id;
                    const amtPaid = order.amount_paid ?? (ps === "Paid" ? order.total_amount : 0);
                    const amtRemaining = order.amount_remaining ?? (ps === "Paid" ? 0 : order.total_amount);
                    const hist = history[order.id];
                    return (
                      <>
                        <tr key={order.id} className={`border-b border-slate-100 hover:bg-slate-50 ${isExpanded ? "bg-slate-50" : ""}`}>
                          {/* Expand toggle */}
                          <td className="px-2 py-3 text-center">
                            <button onClick={() => toggleHistory(order.id)} className="text-slate-400 hover:text-slate-600">
                              {loadingHistory === order.id
                                ? <RefreshCw size={13} className="animate-spin" />
                                : isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </button>
                          </td>
                          <td className="px-4 py-3 font-mono text-slate-700 text-xs">
                            #{order.order_number || order.id.slice(-8)}
                          </td>
                          <td className="px-4 py-3 font-medium text-slate-800">{order.customer_name}</td>
                          <td className="px-4 py-3 font-semibold text-slate-900 tabular-nums">
                            {formatCurrency(order.total_amount)}
                          </td>
                          <td className="px-4 py-3 tabular-nums text-green-700 font-medium">
                            {amtPaid > 0 ? formatCurrency(amtPaid) : "—"}
                          </td>
                          <td className="px-4 py-3 tabular-nums">
                            {amtRemaining > 0
                              ? <span className="text-amber-700 font-medium">{formatCurrency(amtRemaining)}</span>
                              : <span className="text-green-600">✓</span>}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${cfg.cls}`}>
                              {cfg.icon} {cfg.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-400">{formatDate(order.created_at)}</td>
                          <td className="px-4 py-3">
                            {ps !== "Paid" ? (
                              <button type="button" onClick={() => openPayModal(order)}
                                className="px-3 py-1 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors">
                                + Record Payment
                              </button>
                            ) : (
                              <span className="text-xs text-green-600 font-medium">✓ Fully Paid</span>
                            )}
                          </td>
                        </tr>
                        {/* Expanded payment history */}
                        {isExpanded && (
                          <tr key={`${order.id}-hist`} className="border-b border-slate-100 bg-slate-50/80">
                            <td colSpan={9} className="px-8 py-3">
                              {!hist ? (
                                <p className="text-xs text-slate-400">Loading history…</p>
                              ) : hist.length === 0 ? (
                                <p className="text-xs text-slate-400 italic">No payments recorded yet. Use "+ Record Payment" to add the first instalment.</p>
                              ) : (
                                <div className="space-y-1">
                                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-2">Payment History</p>
                                  {hist.map((p, idx) => (
                                    <div key={p.id} className="flex items-center gap-4 text-xs text-slate-600">
                                      <span className="text-slate-400 tabular-nums w-4 text-right">{idx + 1}.</span>
                                      <span className="font-semibold text-green-700 tabular-nums">{formatCurrency(p.amount)}</span>
                                      <span className="px-2 py-0.5 bg-white border border-slate-200 rounded-full">{p.method}</span>
                                      <span className="text-slate-400">{new Date(p.created_at).toLocaleDateString()}</span>
                                      {p.note && <span className="text-slate-500 italic">{p.note}</span>}
                                    </div>
                                  ))}
                                  <div className="flex items-center gap-4 text-xs font-semibold border-t border-slate-200 pt-1 mt-1">
                                    <span className="w-4" />
                                    <span className="text-green-700">Total: {formatCurrency(hist.reduce((s,p)=>s+p.amount,0))}</span>
                                    {amtRemaining > 0 && <span className="text-amber-600">Remaining: {formatCurrency(amtRemaining)}</span>}
                                  </div>
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <p className="text-center text-sm text-slate-400 py-12">No payments match your filters</p>
          )}
        </div>
      </div>

      {/* Record Payment modal */}
      {payModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setPayModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Record Payment</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Order #{payModal.order_number || payModal.id.slice(-8)} · {payModal.customer_name}
                  {" · "}<span className="font-medium">Total: {formatCurrency(payModal.total_amount)}</span>
                  {payModal.amount_paid != null && payModal.amount_paid > 0 && (
                    <> · <span className="text-amber-600">Remaining: {formatCurrency(payModal.amount_remaining ?? 0)}</span></>
                  )}
                </p>
              </div>
              <button onClick={() => setPayModal(null)} className="text-slate-400 hover:text-slate-700"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              {/* Amount */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Amount received</label>
                <input type="number" min="0.01" step="0.01"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/20"
                  value={payAmount} onFocus={e => e.target.select()}
                  onChange={e => setPayAmount(e.target.value)} />
              </div>
              {/* Method */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Payment method</label>
                <div className="grid grid-cols-2 gap-2">
                  {PAYMENT_METHODS.map(m => (
                    <button key={m} onClick={() => setPayMethod(m)}
                      className={`px-3 py-2 rounded-lg text-sm border transition-colors text-left ${
                        payMethod === m ? "bg-green-600 text-white border-green-600 font-medium" : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                      }`}>{m}</button>
                  ))}
                </div>
              </div>
              {/* Note */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Note <span className="text-slate-400">(optional)</span></label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/20"
                  placeholder="e.g. deposit, 1st instalment…"
                  value={payNote} onChange={e => setPayNote(e.target.value)} />
              </div>
            </div>
            <div className="p-5 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setPayModal(null)} className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900">Cancel</button>
              <button onClick={submitPayment} disabled={saving}
                className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 flex items-center gap-1.5">
                {saving ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                {saving ? "Saving…" : `Record ${payMethod} Payment`}
              </button>
            </div>
          </div>
        </div>
      )}
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
