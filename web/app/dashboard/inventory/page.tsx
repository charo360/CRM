"use client";
import { useEffect, useState, useCallback } from "react";
import { inventoryApi } from "@/lib/api";
import { Package, Plus, Trash2, AlertTriangle, RefreshCw, ArrowUp, ArrowDown, Edit2 } from "lucide-react";

type Product = {
  id: string; name: string; sku: string; category: string; unit: string;
  cost_price: number; selling_price: number; quantity: number; reorder_level: number; description: string;
};

function emptyForm() {
  return { name: "", sku: "", category: "", unit: "pcs", cost_price: 0, selling_price: 0, quantity: 0, reorder_level: 0, description: "" };
}

export default function InventoryPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [movModal, setMovModal] = useState<Product | null>(null);
  const [movForm, setMovForm] = useState({ type: "in", quantity: 1, reason: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, sum] = await Promise.all([
        inventoryApi.listProducts({ low_stock: lowStockOnly }),
        inventoryApi.summary(),
      ]);
      setProducts(list as Product[]);
      setSummary(sum as Record<string, unknown>);
    } finally { setLoading(false); }
  }, [lowStockOnly]);

  useEffect(() => { load(); }, [load]);

  function openNew() { setEditing(null); setForm(emptyForm()); setShowModal(true); }
  function openEdit(p: Product) {
    setEditing(p);
    setForm({ name: p.name, sku: p.sku, category: p.category, unit: p.unit, cost_price: p.cost_price, selling_price: p.selling_price, quantity: p.quantity, reorder_level: p.reorder_level, description: p.description });
    setShowModal(true);
  }

  async function save() {
    setSaving(true);
    try {
      if (editing) { await inventoryApi.updateProduct(editing.id, form); }
      else { await inventoryApi.createProduct(form); }
      setShowModal(false); await load();
    } finally { setSaving(false); }
  }

  async function del(p: Product) {
    if (!confirm(`Delete "${p.name}"?`)) return;
    await inventoryApi.deleteProduct(p.id);
    await load();
  }

  async function recordMovement() {
    if (!movModal) return;
    await inventoryApi.recordMovement({ product_id: movModal.id, ...movForm });
    setMovModal(null);
    await load();
  }

  const profit_margin = (p: Product) => p.selling_price > 0
    ? Math.round(((p.selling_price - p.cost_price) / p.selling_price) * 100) : 0;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Package className="text-brand-dark" size={24} /> Inventory
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Track stock levels and product catalogue</p>
        </div>
        <button onClick={openNew} className="flex items-center gap-2 bg-brand-dark text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand">
          <Plus size={16} /> Add Product
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border p-4"><p className="text-xs text-slate-500">Total products</p><p className="text-2xl font-bold text-slate-800">{String(summary.total_items || 0)}</p></div>
        <div className="bg-white rounded-xl border p-4"><p className="text-xs text-slate-500">Stock value (cost)</p><p className="text-xl font-bold text-slate-800">KES {Number(summary.total_value || 0).toLocaleString()}</p></div>
        <div className={`rounded-xl border p-4 ${Number(summary.low_stock_count) > 0 ? "bg-amber-50 border-amber-200" : "bg-white"}`}>
          <p className="text-xs text-slate-500">Low stock</p>
          <p className="text-2xl font-bold text-amber-600">{String(summary.low_stock_count || 0)}</p>
        </div>
        <div className={`rounded-xl border p-4 ${Number(summary.out_of_stock_count) > 0 ? "bg-red-50 border-red-200" : "bg-white"}`}>
          <p className="text-xs text-slate-500">Out of stock</p>
          <p className="text-2xl font-bold text-red-600">{String(summary.out_of_stock_count || 0)}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
          <input type="checkbox" checked={lowStockOnly} onChange={e => setLowStockOnly(e.target.checked)} className="rounded" />
          Show low stock only
        </label>
        <button onClick={load} className="ml-auto text-slate-400 hover:text-slate-700">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-slate-400">Loading...</div>
      ) : products.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
          <Package size={40} className="opacity-30" />
          <p>No products. Add your first product to start tracking stock.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-3">Product</th>
                <th className="text-left px-4 py-3">Category</th>
                <th className="text-right px-4 py-3">Stock</th>
                <th className="text-right px-4 py-3">Cost</th>
                <th className="text-right px-4 py-3">Price</th>
                <th className="text-right px-4 py-3">Margin</th>
                <th className="text-right px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {products.map(p => {
                const isLow = p.quantity <= p.reorder_level && p.reorder_level > 0;
                return (
                  <tr key={p.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{p.name}</p>
                      {p.sku && <p className="text-xs text-slate-400">SKU: {p.sku}</p>}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{p.category || "—"}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={`font-semibold ${isLow ? "text-amber-600" : p.quantity === 0 ? "text-red-600" : "text-slate-800"}`}>
                        {p.quantity} {p.unit}
                      </span>
                      {isLow && <AlertTriangle size={12} className="inline ml-1 text-amber-500" />}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-600">{p.cost_price.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-medium text-slate-800">{p.selling_price.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={`text-xs font-medium ${profit_margin(p) > 30 ? "text-green-600" : profit_margin(p) > 10 ? "text-amber-600" : "text-red-500"}`}>
                        {profit_margin(p)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => { setMovModal(p); setMovForm({ type: "in", quantity: 1, reason: "" }); }}
                          className="text-slate-400 hover:text-green-600 p-1" title="Stock in">
                          <ArrowUp size={14} />
                        </button>
                        <button onClick={() => { setMovModal(p); setMovForm({ type: "out", quantity: 1, reason: "" }); }}
                          className="text-slate-400 hover:text-red-500 p-1" title="Stock out">
                          <ArrowDown size={14} />
                        </button>
                        <button onClick={() => openEdit(p)} className="text-slate-400 hover:text-brand-dark p-1" title="Edit">
                          <Edit2 size={14} />
                        </button>
                        <button onClick={() => del(p)} className="text-slate-400 hover:text-red-500 p-1" title="Delete">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Product Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-lg font-semibold">{editing ? "Edit Product" : "New Product"}</h2>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-slate-600 mb-1">Product name *</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.name}
                    onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Maize Flour 2kg" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">SKU</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.sku}
                    onChange={e => setForm(f => ({ ...f, sku: e.target.value }))} placeholder="PROD-001" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Category</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.category}
                    onChange={e => setForm(f => ({ ...f, category: e.target.value }))} placeholder="Food, Electronics..." />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Unit</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.unit}
                    onChange={e => setForm(f => ({ ...f, unit: e.target.value }))} placeholder="pcs, kg, litre..." />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Cost price</label>
                  <input type="number" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.cost_price}
                    onChange={e => setForm(f => ({ ...f, cost_price: +e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Selling price</label>
                  <input type="number" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.selling_price}
                    onChange={e => setForm(f => ({ ...f, selling_price: +e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Opening stock</label>
                  <input type="number" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.quantity}
                    onChange={e => setForm(f => ({ ...f, quantity: +e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Reorder level</label>
                  <input type="number" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.reorder_level}
                    onChange={e => setForm(f => ({ ...f, reorder_level: +e.target.value }))} />
                </div>
              </div>
            </div>
            <div className="p-6 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={save} disabled={saving || !form.name} className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50">
                {saving ? "Saving..." : editing ? "Update" : "Add Product"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Movement Modal */}
      {movModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setMovModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-lg font-semibold">Stock Movement — {movModal.name}</h2>
              <p className="text-sm text-slate-500 mt-1">Current: {movModal.quantity} {movModal.unit}</p>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Type</label>
                <div className="flex gap-2">
                  {["in","out","adjustment"].map(t => (
                    <button key={t} onClick={() => setMovForm(f => ({ ...f, type: t }))}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium capitalize border transition-colors ${movForm.type === t ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200"}`}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Quantity</label>
                <input type="number" min="1" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={movForm.quantity}
                  onChange={e => setMovForm(f => ({ ...f, quantity: +e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Reason</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={movForm.reason}
                  onChange={e => setMovForm(f => ({ ...f, reason: e.target.value }))} placeholder="Purchase, sale, damage..." />
              </div>
            </div>
            <div className="p-6 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setMovModal(null)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={recordMovement} className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand">
                Record
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
