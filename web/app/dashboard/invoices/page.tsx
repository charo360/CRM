"use client";
import { useEffect, useState, useCallback } from "react";
import { invoicesApi } from "@/lib/api";
import { FileText, Plus, Trash2, Send, CheckCircle, Clock, XCircle, Eye, RefreshCw } from "lucide-react";

type InvoiceItem = { name: string; qty: number; unit_price: number; amount: number };
type Invoice = {
  id: string; number: string; customer_name: string; customer_phone: string;
  items: InvoiceItem[]; subtotal: number; tax_rate: number; tax_amount: number;
  total: number; currency: string; due_date?: string; notes: string;
  status: string; created_at: string;
};

const STATUS_COLOR: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  sent: "bg-blue-100 text-blue-700",
  paid: "bg-green-100 text-green-700",
  overdue: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-500",
};
const STATUS_NEXT: Record<string, string> = { draft: "sent", sent: "paid", paid: "paid", overdue: "paid", cancelled: "draft" };

const EMPTY_ITEM: InvoiceItem = { name: "", qty: 1, unit_price: 0, amount: 0 };

function emptyForm() {
  return { customer_name: "", customer_phone: "", items: [{ ...EMPTY_ITEM }], tax_rate: 0, currency: "KES", due_date: "", notes: "", status: "draft" };
}

function calcItem(i: InvoiceItem) { return { ...i, amount: +(i.qty * i.unit_price).toFixed(2) }; }

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Invoice | null>(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState("");
  const [summary, setSummary] = useState<Record<string, { count: number; total: number }>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, sum] = await Promise.all([invoicesApi.list(), invoicesApi.summary()]);
      setInvoices(list as Invoice[]);
      setSummary(((sum as { by_status?: Record<string, { count: number; total: number }> }).by_status) || {});
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  function openNew() { setEditing(null); setForm(emptyForm()); setShowModal(true); }
  function openEdit(inv: Invoice) {
    setEditing(inv);
    setForm({
      customer_name: inv.customer_name, customer_phone: inv.customer_phone,
      items: inv.items.length ? inv.items : [{ ...EMPTY_ITEM }],
      tax_rate: inv.tax_rate, currency: inv.currency,
      due_date: inv.due_date || "", notes: inv.notes, status: inv.status,
    });
    setShowModal(true);
  }

  function updateItem(idx: number, field: keyof InvoiceItem, val: string | number) {
    setForm(f => {
      const items = [...f.items];
      items[idx] = calcItem({ ...items[idx], [field]: field === "name" ? val : +val });
      return { ...f, items };
    });
  }

  function addItem() { setForm(f => ({ ...f, items: [...f.items, { ...EMPTY_ITEM }] })); }
  function removeItem(idx: number) { setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) })); }

  const subtotal = form.items.reduce((s, i) => s + i.qty * i.unit_price, 0);
  const tax = +(subtotal * (form.tax_rate / 100)).toFixed(2);
  const total = +(subtotal + tax).toFixed(2);

  async function save() {
    setSaving(true);
    try {
      if (editing) { await invoicesApi.update(editing.id, { ...form }); }
      else { await invoicesApi.create({ ...form }); }
      setShowModal(false); await load();
    } finally { setSaving(false); }
  }

  async function quickStatus(inv: Invoice) {
    await invoicesApi.setStatus(inv.id, STATUS_NEXT[inv.status] || "sent");
    await load();
  }

  async function del(inv: Invoice) {
    if (!confirm(`Delete ${inv.number}?`)) return;
    await invoicesApi.delete(inv.id);
    await load();
  }

  const filtered = invoices.filter(i =>
    !filter || i.status === filter || i.customer_name.toLowerCase().includes(filter.toLowerCase())
  );

  const totalInvoiced = Object.values(summary).reduce((s, v) => s + v.total, 0);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FileText className="text-brand-dark" size={24} /> Invoices
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Create, send & track payments</p>
        </div>
        <button onClick={openNew} className="flex items-center gap-2 bg-brand-dark text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand">
          <Plus size={16} /> New Invoice
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {["draft","sent","paid","overdue"].map(s => (
          <div key={s} className="bg-white rounded-xl border border-slate-200 p-4">
            <p className="text-xs text-slate-500 capitalize">{s}</p>
            <p className="text-xl font-bold text-slate-800 mt-1">{summary[s]?.count || 0}</p>
            <p className="text-xs text-slate-400">KES {(summary[s]?.total || 0).toLocaleString()}</p>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div className="flex gap-2 flex-wrap">
        {["", "draft","sent","paid","overdue","cancelled"].map(s => (
          <button key={s} onClick={() => setFilter(s)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${filter === s ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200 hover:border-brand"}`}>
            {s || "All"} {s && summary[s] ? `(${summary[s].count})` : ""}
          </button>
        ))}
        <button onClick={load} className="ml-auto text-slate-400 hover:text-slate-700 transition-colors">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-slate-400">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
          <FileText size={40} className="opacity-30" />
          <p>No invoices yet. Create your first one!</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-3">Number</th>
                <th className="text-left px-4 py-3">Customer</th>
                <th className="text-left px-4 py-3">Total</th>
                <th className="text-left px-4 py-3">Due</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-right px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map(inv => (
                <tr key={inv.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 font-mono font-medium text-brand-dark">{inv.number}</td>
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-800">{inv.customer_name || "—"}</p>
                    <p className="text-slate-400 text-xs">{inv.customer_phone}</p>
                  </td>
                  <td className="px-4 py-3 font-semibold text-slate-800">
                    {inv.currency} {inv.total.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{inv.due_date ? new Date(inv.due_date).toLocaleDateString() : "—"}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => quickStatus(inv)}
                      className={`px-2 py-1 rounded-full text-xs font-medium cursor-pointer capitalize ${STATUS_COLOR[inv.status] || "bg-slate-100 text-slate-600"}`}>
                      {inv.status}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button onClick={() => openEdit(inv)} className="text-slate-400 hover:text-brand-dark transition-colors" title="Edit">
                        <Eye size={15} />
                      </button>
                      <button onClick={() => del(inv)} className="text-slate-400 hover:text-red-500 transition-colors" title="Delete">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-lg font-semibold text-slate-800">{editing ? `Edit ${editing.number}` : "New Invoice"}</h2>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Customer name</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.customer_name}
                    onChange={e => setForm(f => ({ ...f, customer_name: e.target.value }))} placeholder="Jane Wanjiku" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Phone</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.customer_phone}
                    onChange={e => setForm(f => ({ ...f, customer_phone: e.target.value }))} placeholder="+254..." />
                </div>
              </div>

              {/* Items */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-2">Line items</label>
                <div className="space-y-2">
                  {form.items.map((item, idx) => (
                    <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                      <input className="col-span-5 border border-slate-200 rounded-lg px-2 py-1.5 text-sm" value={item.name}
                        onChange={e => updateItem(idx, "name", e.target.value)} placeholder="Item description" />
                      <input className="col-span-2 border border-slate-200 rounded-lg px-2 py-1.5 text-sm" type="number" min="1" value={item.qty}
                        onChange={e => updateItem(idx, "qty", e.target.value)} />
                      <input className="col-span-3 border border-slate-200 rounded-lg px-2 py-1.5 text-sm" type="number" min="0" value={item.unit_price}
                        onChange={e => updateItem(idx, "unit_price", e.target.value)} placeholder="Price" />
                      <div className="col-span-1 text-xs text-slate-500 text-right">{item.amount.toLocaleString()}</div>
                      <button onClick={() => removeItem(idx)} className="col-span-1 text-slate-300 hover:text-red-500 transition-colors flex justify-center">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                <button onClick={addItem} className="mt-2 text-xs text-brand-dark hover:underline">+ Add item</button>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Tax %</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" type="number" min="0" max="100"
                    value={form.tax_rate} onChange={e => setForm(f => ({ ...f, tax_rate: +e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Currency</label>
                  <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.currency}
                    onChange={e => setForm(f => ({ ...f, currency: e.target.value }))}>
                    {["KES","USD","EUR","GBP","UGX","TZS"].map(c => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Due date</label>
                  <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.due_date}
                    onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
                </div>
              </div>

              {/* Totals */}
              <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
                <div className="flex justify-between text-slate-600"><span>Subtotal</span><span>{form.currency} {subtotal.toLocaleString()}</span></div>
                <div className="flex justify-between text-slate-600"><span>Tax ({form.tax_rate}%)</span><span>{form.currency} {tax.toLocaleString()}</span></div>
                <div className="flex justify-between font-bold text-slate-800 border-t border-slate-200 pt-1 mt-1"><span>Total</span><span>{form.currency} {total.toLocaleString()}</span></div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Notes</label>
                <textarea className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" rows={2}
                  value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Status</label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.status}
                  onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                  {["draft","sent","paid","overdue","cancelled"].map(s => <option key={s} value={s} className="capitalize">{s}</option>)}
                </select>
              </div>
            </div>
            <div className="p-6 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800">Cancel</button>
              <button onClick={save} disabled={saving} className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50">
                {saving ? "Saving..." : editing ? "Update" : "Create Invoice"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
