"use client";

import { useEffect, useState, useCallback } from "react";
import { ordersApi, customersApi, Order, Customer } from "@/lib/api";
import { formatCurrency, timeAgo } from "@/lib/utils";
import { Search, RefreshCw, ChevronDown, Plus, X, Loader2, ArrowRightLeft, Trash2, Pencil, Download } from "lucide-react";

const PAYMENT_METHODS = ["M-Pesa", "Cash", "Bank Transfer", "Airtel Money", "Card", "PayPal", "Other"];

const FULFILLMENT_STATUSES = ["All", "New", "Confirmed", "Preparing", "Ready", "Done"];
const DELIVERY_TYPES = ["All", "dine-in", "pickup", "delivery"];

const STATUS_COLORS: Record<string, string> = {
  New:        "bg-red-100 text-red-700",
  Confirmed:  "bg-orange-100 text-orange-700",
  Preparing:  "bg-yellow-100 text-yellow-700",
  Ready:      "bg-green-100 text-green-700",
  Done:       "bg-slate-100 text-slate-500",
  Paid:       "bg-emerald-100 text-emerald-700",
  Pending:    "bg-amber-100 text-amber-700",
  Partial:           "bg-blue-100 text-blue-700",
  "BNPL / Partial":   "bg-blue-100 text-blue-700",
};

const PAYMENT_STATUSES = ["All", "Pending", "Partial", "Paid"];

function emptyForm() {
  return {
    customer_id: "",
    product: "",
    quantity: 1,
    price: 0,
    payment_status: "Pending",
    delivery_type: "pickup",
    delivery_address: "",
    table_number: "",
    notes: "",
  };
}

export default function OrdersPage() {
  const [orders, setOrders]     = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [statusFilter, setStatusFilter]   = useState("All");
  const [payFilter, setPayFilter]         = useState("All");
  const [typeFilter, setTypeFilter]       = useState("All");
  const [updatingId, setUpdatingId]       = useState<string | null>(null);
  const [deletingId, setDeletingId]       = useState<string | null>(null);
  const [convertingId, setConvertingId]   = useState<string | null>(null);

  // Create / Edit modal
  const [showModal, setShowModal]   = useState(false);
  const [editingOrder, setEditingOrder] = useState<Order | null>(null);
  const [saving, setSaving]         = useState(false);
  const [form, setForm]             = useState(emptyForm());

  // Convert-to-sale modal
  const [convertModal, setConvertModal] = useState<Order | null>(null);
  const [convertMethod, setConvertMethod] = useState("Cash");

  const load = useCallback(async (showSkeleton = true) => {
    if (showSkeleton) setLoading(true);
    try {
      const [ordersData, customersData] = await Promise.all([
        ordersApi.list(),
        customersApi.list(),
      ]);
      setOrders(ordersData);
      setCustomers(customersData);
    } finally {
      if (showSkeleton) setLoading(false);
    }
  }, []);

  useEffect(() => { load(true); }, [load]);

  function openCreate() {
    setEditingOrder(null);
    setForm(emptyForm());
    setShowModal(true);
  }

  function openEdit(order: Order) {
    setEditingOrder(order);
    setForm({
      customer_id: "",
      product: order.product ?? "",
      quantity: order.quantity ?? 1,
      price: order.price ?? 0,
      payment_status: order.payment_status ?? "Pending",
      delivery_type: order.delivery_type ?? "pickup",
      delivery_address: order.delivery_address ?? "",
      table_number: order.table_number ?? "",
      notes: order.notes ?? "",
    });
    setShowModal(true);
  }

  async function advanceStatus(order: Order) {
    const flow = ["New", "Confirmed", "Preparing", "Ready", "Done"];
    const current = order.fulfillment_status || "New";
    const nextIdx = flow.indexOf(current) + 1;
    if (nextIdx >= flow.length) return;
    setUpdatingId(order.id);
    try {
      await ordersApi.updateProgress(order.id, { fulfillment_status: flow[nextIdx] });
      await load(false);
    } finally { setUpdatingId(null); }
  }

  async function handleDelete(order: Order) {
    if (!confirm(`Delete order #${order.order_number || order.id.slice(-6)}?`)) return;
    setDeletingId(order.id);
    try {
      await ordersApi.delete(order.id);
      await load(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete");
    } finally { setDeletingId(null); }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!form.customer_id) return alert("Select a customer");
    setSaving(true);
    try {
      const total = form.price * form.quantity;
      if (editingOrder) {
        await ordersApi.updateStatus(editingOrder.id, {
          payment_status: form.payment_status,
          notes: form.notes || undefined,
        });
      } else {
        await ordersApi.create({
          customer_id: form.customer_id,
          product: form.product,
          quantity: form.quantity,
          price: form.price,
          total_amount: total,
          payment_status: form.payment_status,
          delivery_type: form.delivery_type,
          delivery_address: form.delivery_address || undefined,
          table_number: form.table_number || undefined,
          notes: form.notes || undefined,
        });
      }
      setShowModal(false);
      setEditingOrder(null);
      await load(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save order");
    } finally { setSaving(false); }
  }

  async function confirmConvert() {
    if (!convertModal) return;
    setConvertingId(convertModal.id);
    setConvertModal(null);
    try {
      await ordersApi.convertToSale(convertModal.id, convertMethod);
      await load(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to convert");
    } finally { setConvertingId(null); }
  }

  function exportCSV() {
    const rows = [
      ["Order #", "Customer", "Phone", "Product", "Qty", "Total", "Payment", "Fulfillment", "Type", "Date"],
      ...filtered.map(o => [
        o.order_number || o.id,
        o.customer_name, o.customer_phone,
        o.product, o.quantity, o.total_amount,
        o.payment_status, o.fulfillment_status || "New",
        o.delivery_type || "", o.created_at,
      ]),
    ];
    const csv = rows.map(r => r.join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = "orders.csv"; a.click();
    URL.revokeObjectURL(url);
  }

  const filtered = orders.filter((o) => {
    const matchSearch =
      !search ||
      o.customer_name.toLowerCase().includes(search.toLowerCase()) ||
      (o.order_number || "").includes(search) ||
      o.product.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "All" || (o.fulfillment_status || "New") === statusFilter;
    const matchPay = payFilter === "All" || (o.payment_status || "").toLowerCase() === payFilter.toLowerCase();
    const matchType = typeFilter === "All" || (o.delivery_type || "").toLowerCase() === typeFilter.toLowerCase();
    return matchSearch && matchStatus && matchPay && matchType;
  });

  const totalRevenue   = orders.filter(o => o.payment_status?.toLowerCase() === "paid").reduce((s, o) => s + o.total_amount, 0);
  const totalPending   = orders.filter(o => o.payment_status?.toLowerCase() === "pending").reduce((s, o) => s + o.total_amount, 0);
  const totalPartial   = orders.filter(o => o.payment_status?.toLowerCase() === "partial").length;
  const activeOrders   = orders.filter(o => !["Done"].includes(o.fulfillment_status || "New")).length;

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Orders</h1>
          <p className="text-slate-500 text-sm mt-0.5">{orders.length} total · {activeOrders} active</p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportCSV}
            className="flex items-center gap-1.5 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
            <Download size={14} /> Export
          </button>
          <button onClick={() => load(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
          <button onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm font-semibold rounded-lg hover:bg-brand">
            <Plus size={15} /> New Order
          </button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
          <p className="text-xs text-emerald-700 font-medium">Revenue Collected</p>
          <p className="text-xl font-bold text-emerald-800 mt-0.5">{formatCurrency(totalRevenue)}</p>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-xs text-amber-700 font-medium">Pending Payment</p>
          <p className="text-xl font-bold text-amber-800 mt-0.5">{formatCurrency(totalPending)}</p>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
          <p className="text-xs text-blue-700 font-medium">BNPL / Partial</p>
          <p className="text-xl font-bold text-blue-800 mt-0.5">{totalPartial} orders</p>
        </div>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
          <p className="text-xs text-slate-600 font-medium">Active Orders</p>
          <p className="text-xl font-bold text-slate-800 mt-0.5">{activeOrders}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search customer, order #, product..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
        </div>
        <Select value={statusFilter} onChange={setStatusFilter} options={FULFILLMENT_STATUSES} label="Fulfillment" />
        <Select value={payFilter} onChange={setPayFilter} options={PAYMENT_STATUSES} label="Payment" />
        <Select value={typeFilter} onChange={setTypeFilter} options={DELIVERY_TYPES} label="Type" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[800px]">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {["Order", "Customer", "Items", "Type", "Status", "Payment", "Total", "Time", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 9 }).map((_, j) => (
                        <td key={j} className="px-4 py-3"><div className="h-4 bg-slate-100 rounded animate-pulse" /></td>
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
                        <td className="px-4 py-3 font-mono font-medium text-slate-800 text-xs">
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
                                <p key={i} className="text-xs text-slate-700 truncate">{it.quantity}× {it.product_name}</p>
                              ))}
                              {items.length > 2 && <p className="text-xs text-slate-400">+{items.length - 2} more</p>}
                            </div>
                          ) : (
                            <p className="text-xs text-slate-700 truncate">{order.quantity}× {order.product}</p>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-600 capitalize text-xs">
                          {order.delivery_type || "—"}
                          {order.table_number && <span className="ml-1 text-slate-400">#{order.table_number}</span>}
                        </td>
                        <td className="px-4 py-3"><Badge status={fs} /></td>
                        <td className="px-4 py-3"><Badge status={order.payment_status} /></td>
                        <td className="px-4 py-3 font-semibold text-slate-800 tabular-nums">{formatCurrency(order.total_amount)}</td>
                        <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{timeAgo(order.created_at)}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            {nextStatus ? (
                              <button onClick={() => advanceStatus(order)} disabled={updatingId === order.id}
                                className="px-2 py-1 text-xs font-medium bg-brand-dark text-white rounded-lg hover:bg-brand disabled:opacity-50 transition-colors whitespace-nowrap">
                                {updatingId === order.id ? <Loader2 size={11} className="animate-spin inline" /> : `→ ${nextStatus}`}
                              </button>
                            ) : (
                              <span className="text-xs text-slate-400 whitespace-nowrap">Done ✓</span>
                            )}
                            {order.payment_status?.toLowerCase() !== "paid" && (
                              <button onClick={() => { setConvertModal(order); setConvertMethod("Cash"); }}
                                disabled={convertingId === order.id}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-green-100 hover:text-green-700 transition-colors" title="Convert to Sale">
                                {convertingId === order.id ? <Loader2 size={13} className="animate-spin" /> : <ArrowRightLeft size={13} />}
                              </button>
                            )}
                            <button onClick={() => openEdit(order)}
                              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-brand-dark transition-colors" title="Edit">
                              <Pencil size={13} />
                            </button>
                            <button onClick={() => handleDelete(order)} disabled={deletingId === order.id}
                              className="p-1.5 rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors" title="Delete">
                              {deletingId === order.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                            </button>
                          </div>
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

      {/* Create / Edit Order Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">{editingOrder ? "Edit Order" : "New Order"}</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
            </div>
            <form onSubmit={handleSave} className="p-6 space-y-4">
              {!editingOrder && (
                <>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Customer *</label>
                    <select value={form.customer_id} onChange={(e) => setForm(f => ({ ...f, customer_id: e.target.value }))}
                      required className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand">
                      <option value="">Select customer…</option>
                      {customers.map((c) => <option key={c.id} value={c.id}>{c.name} — {c.phone_number}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Product / Item *</label>
                    <input value={form.product} onChange={(e) => setForm(f => ({ ...f, product: e.target.value }))}
                      placeholder="e.g. Chicken Burger" required
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-700 mb-1">Quantity</label>
                      <input type="number" min={1} value={form.quantity}
                        onChange={(e) => setForm(f => ({ ...f, quantity: Number(e.target.value) }))}
                        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-700 mb-1">Unit Price</label>
                      <input type="number" min={0} step="0.01" value={form.price}
                        onChange={(e) => setForm(f => ({ ...f, price: Number(e.target.value) }))}
                        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
                    </div>
                  </div>
                  {form.price > 0 && (
                    <p className="text-xs text-slate-500">Total: <strong>{formatCurrency(form.price * form.quantity)}</strong></p>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-700 mb-1">Delivery Type</label>
                      <select value={form.delivery_type} onChange={(e) => setForm(f => ({ ...f, delivery_type: e.target.value }))}
                        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand">
                        <option value="pickup">Pickup</option>
                        <option value="delivery">Delivery</option>
                        <option value="dine-in">Dine-in</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-700 mb-1">Payment Status</label>
                      <select value={form.payment_status} onChange={(e) => setForm(f => ({ ...f, payment_status: e.target.value }))}
                        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand">
                        <option value="Pending">Pending</option>
                        <option value="Partial">BNPL / Partial</option>
                        <option value="Paid">Paid</option>
                      </select>
                    </div>
                  </div>
                  {form.delivery_type === "delivery" && (
                    <div>
                      <label className="block text-xs font-medium text-slate-700 mb-1">Delivery Address</label>
                      <input value={form.delivery_address} onChange={(e) => setForm(f => ({ ...f, delivery_address: e.target.value }))}
                        placeholder="Enter delivery address"
                        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
                    </div>
                  )}
                  {form.delivery_type === "dine-in" && (
                    <div>
                      <label className="block text-xs font-medium text-slate-700 mb-1">Table Number</label>
                      <input value={form.table_number} onChange={(e) => setForm(f => ({ ...f, table_number: e.target.value }))}
                        placeholder="e.g. 5"
                        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand" />
                    </div>
                  )}
                </>
              )}
              {/* Edit-only fields */}
              {editingOrder && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Payment Status</label>
                  <select value={form.payment_status} onChange={(e) => setForm(f => ({ ...f, payment_status: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand">
                    <option value="Pending">Pending</option>
                    <option value="Partial">BNPL / Partial</option>
                    <option value="Paid">Paid</option>
                  </select>
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Notes</label>
                <textarea value={form.notes} onChange={(e) => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="Special instructions…" rows={2}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand resize-none" />
              </div>
              <button type="submit" disabled={saving}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-brand-dark text-white text-sm font-semibold rounded-xl hover:bg-brand disabled:opacity-50">
                {saving && <Loader2 size={14} className="animate-spin" />}
                {editingOrder ? "Save Changes" : "Create Order"}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Convert to Sale modal */}
      {convertModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setConvertModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="p-5 border-b border-slate-100">
              <h2 className="text-base font-semibold">Convert to Sale</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Order #{convertModal.order_number || convertModal.id.slice(-6)} · {convertModal.customer_name} · {formatCurrency(convertModal.total_amount)}
              </p>
            </div>
            <div className="p-5">
              <label className="block text-xs font-medium text-slate-600 mb-2">Payment method</label>
              <div className="grid grid-cols-2 gap-2">
                {PAYMENT_METHODS.map(m => (
                  <button key={m} onClick={() => setConvertMethod(m)}
                    className={`px-3 py-2 rounded-lg text-sm border transition-colors text-left ${
                      convertMethod === m ? "bg-brand-dark text-white border-brand-dark font-medium" : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                    }`}>{m}</button>
                ))}
              </div>
            </div>
            <div className="p-5 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setConvertModal(null)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={confirmConvert}
                className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand flex items-center gap-1.5">
                <ArrowRightLeft size={14} /> Convert to Sale
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Badge({ status }: { status: string | null }) {
  const cls = STATUS_COLORS[status || ""] || "bg-slate-100 text-slate-500";
  const label = status?.toLowerCase() === "partial" ? "BNPL / Partial" : (status || "—");
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {label}
    </span>
  );
}

function Select({ value, onChange, options, label }: {
  value: string; onChange: (v: string) => void; options: string[]; label: string;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand bg-white text-slate-700"
      >
        {options.map((o) => (
          <option key={o} value={o}>{o === "All" ? `${label}: All` : o}</option>
        ))}
      </select>
      <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
    </div>
  );
}
