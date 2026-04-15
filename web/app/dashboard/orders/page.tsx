"use client";

import { useEffect, useState } from "react";
import { ordersApi, customersApi, Order, Customer, api } from "@/lib/api";
import { formatCurrency, timeAgo } from "@/lib/utils";
import { Search, RefreshCw, ChevronDown, Plus, X, Loader2, ArrowRightLeft } from "lucide-react";

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
  Partial:    "bg-blue-100 text-blue-700",
};

const EMPTY_FORM = {
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

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [typeFilter, setTypeFilter] = useState("All");
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [convertingId, setConvertingId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  async function load(showSkeleton = true) {
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
  }

  useEffect(() => {
    load(true);
  }, []);

  async function advanceStatus(order: Order) {
    const flow = ["New", "Confirmed", "Preparing", "Ready", "Done"];
    const current = order.fulfillment_status || "New";
    const nextIdx = flow.indexOf(current) + 1;
    if (nextIdx >= flow.length) return;
    setUpdatingId(order.id);
    try {
      await ordersApi.updateProgress(order.id, { fulfillment_status: flow[nextIdx] });
      await load(false);
    } finally {
      setUpdatingId(null);
    }
  }

  async function convertToSale(order: Order) {
    const method = prompt("Payment method? (Cash / Mobile Money / Card)", "Cash");
    if (!method) return;
    setConvertingId(order.id);
    try {
      await api.post(`/orders/${order.id}/convert-to-sale?payment_method=${encodeURIComponent(method)}`, {});
      alert("Order converted to sale!");
      await load(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to convert");
    } finally {
      setConvertingId(null);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.customer_id) return alert("Select a customer");
    setCreating(true);
    try {
      const total = form.price * form.quantity;
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
      setShowCreate(false);
      setForm(EMPTY_FORM);
      await load(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create order");
    } finally {
      setCreating(false);
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
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => load(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700"
          >
            <Plus size={15} /> New Order
          </button>
        </div>
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
                        <td className="px-4 py-3"><Badge status={fs} /></td>
                        <td className="px-4 py-3"><Badge status={order.payment_status} /></td>
                        <td className="px-4 py-3 font-semibold text-slate-800">
                          {formatCurrency(order.total_amount)}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-400">
                          {timeAgo(order.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            {nextStatus ? (
                              <button
                                type="button"
                                onClick={() => advanceStatus(order)}
                                disabled={updatingId === order.id}
                                className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                              >
                                {updatingId === order.id ? "..." : `→ ${nextStatus}`}
                              </button>
                            ) : (
                              <span className="text-xs text-slate-400">Done ✓</span>
                            )}
                            {order.payment_status !== "Paid" && (
                              <button
                                type="button"
                                onClick={() => convertToSale(order)}
                                disabled={convertingId === order.id}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-green-100 hover:text-green-700 transition-colors"
                                title="Convert to Sale"
                              >
                                {convertingId === order.id ? <Loader2 size={13} className="animate-spin" /> : <ArrowRightLeft size={13} />}
                              </button>
                            )}
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

      {/* Create Order Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">New Order</h3>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Customer *</label>
                <select
                  value={form.customer_id}
                  onChange={(e) => setForm(f => ({ ...f, customer_id: e.target.value }))}
                  required
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Select customer…</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>{c.name} — {c.phone_number}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Product / Item *</label>
                <input
                  value={form.product}
                  onChange={(e) => setForm(f => ({ ...f, product: e.target.value }))}
                  placeholder="e.g. Chicken Burger"
                  required
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Quantity</label>
                  <input
                    type="number"
                    min={1}
                    value={form.quantity}
                    onChange={(e) => setForm(f => ({ ...f, quantity: Number(e.target.value) }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Unit Price</label>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={form.price}
                    onChange={(e) => setForm(f => ({ ...f, price: Number(e.target.value) }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              {form.price > 0 && (
                <p className="text-xs text-slate-500">
                  Total: <strong>{formatCurrency(form.price * form.quantity)}</strong>
                </p>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Delivery Type</label>
                  <select
                    value={form.delivery_type}
                    onChange={(e) => setForm(f => ({ ...f, delivery_type: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="pickup">Pickup</option>
                    <option value="delivery">Delivery</option>
                    <option value="dine-in">Dine-in</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Payment Status</label>
                  <select
                    value={form.payment_status}
                    onChange={(e) => setForm(f => ({ ...f, payment_status: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="Pending">Pending</option>
                    <option value="Partial">Partial</option>
                    <option value="Paid">Paid</option>
                  </select>
                </div>
              </div>

              {form.delivery_type === "delivery" && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Delivery Address</label>
                  <input
                    value={form.delivery_address}
                    onChange={(e) => setForm(f => ({ ...f, delivery_address: e.target.value }))}
                    placeholder="Enter delivery address"
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              )}

              {form.delivery_type === "dine-in" && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Table Number</label>
                  <input
                    value={form.table_number}
                    onChange={(e) => setForm(f => ({ ...f, table_number: e.target.value }))}
                    placeholder="e.g. 5"
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="Special instructions…"
                  rows={2}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>

              <button
                type="submit"
                disabled={creating}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50"
              >
                {creating && <Loader2 size={14} className="animate-spin" />}
                Create Order
              </button>
            </form>
          </div>
        </div>
      )}
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

function Select({ value, onChange, options, label }: {
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
