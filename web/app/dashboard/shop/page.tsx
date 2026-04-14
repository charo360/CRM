"use client";

import { useEffect, useState } from "react";
import { productsApi, Product } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import {
  Plus, Pencil, Trash2, ExternalLink, Store, Loader2, X,
} from "lucide-react";

export default function ShopPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<"add" | "edit" | null>(null);
  const [editing, setEditing] = useState<Product | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", price: "", description: "", category: "" });

  const shopUrl = typeof window !== "undefined"
    ? `${window.location.origin}/shop/${encodeURIComponent(
        localStorage.getItem("user")
          ? JSON.parse(localStorage.getItem("user") || "{}").business_slug || "my-shop"
          : "my-shop"
      )}`
    : "";

  async function load() {
    setLoading(true);
    try { setProducts(await productsApi.list()); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  function openAdd() {
    setForm({ name: "", price: "", description: "", category: "" });
    setEditing(null);
    setModal("add");
  }

  function openEdit(product: Product) {
    setForm({
      name: product.name,
      price: String(product.price),
      description: product.description || "",
      category: product.category || "",
    });
    setEditing(product);
    setModal("edit");
  }

  async function handleSave() {
    if (!form.name || !form.price) return;
    setSaving(true);
    try {
      const body = {
        name: form.name,
        price: parseFloat(form.price),
        description: form.description,
        category: form.category,
      };
      if (editing) {
        await productsApi.update(editing.id, body);
      } else {
        await productsApi.create(body);
      }
      setModal(null);
      await load();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Remove this product from the shop?")) return;
    await productsApi.delete(id);
    await load();
  }

  // Group by category
  const categories = [...new Set(products.map((p) => p.category || "Uncategorised"))];

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Shop</h1>
          <p className="text-slate-500 text-sm mt-1">
            Manage your storefront products. Share the link with customers to let them browse and order.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {shopUrl && (
            <a
              href={shopUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 font-medium"
            >
              <ExternalLink size={14} />
              View Shop
            </a>
          )}
          <button
            onClick={openAdd}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition-colors"
          >
            <Plus size={15} />
            Add Product
          </button>
        </div>
      </div>

      {/* Shop link banner */}
      <div className="flex items-center gap-3 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3">
        <Store size={18} className="text-indigo-600 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-indigo-900">Your shop link</p>
          <p className="text-xs text-indigo-500 truncate">{shopUrl || "Sign in to see your shop URL"}</p>
        </div>
        <button
          onClick={() => navigator.clipboard.writeText(shopUrl)}
          className="text-xs font-medium text-indigo-700 hover:underline shrink-0"
        >
          Copy
        </button>
      </div>

      {/* Products grid */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse">
              <div className="h-32 bg-slate-100 rounded-lg mb-3" />
              <div className="h-4 bg-slate-100 rounded w-3/4 mb-1" />
              <div className="h-3 bg-slate-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : products.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-4 bg-white rounded-xl border border-slate-200">
          <Store size={40} className="text-slate-300" />
          <p className="text-slate-500 font-medium">No products yet</p>
          <button
            onClick={openAdd}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700"
          >
            <Plus size={15} /> Add your first product
          </button>
        </div>
      ) : (
        <div className="space-y-8">
          {categories.map((cat) => (
            <div key={cat}>
              <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">{cat}</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                {products
                  .filter((p) => (p.category || "Uncategorised") === cat)
                  .map((product) => (
                    <div
                      key={product.id}
                      className="bg-white rounded-xl border border-slate-200 hover:shadow-md transition-shadow flex flex-col overflow-hidden"
                    >
                      {/* Image placeholder */}
                      <div className="h-32 bg-slate-100 flex items-center justify-center text-slate-300">
                        {product.images?.[0] ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={product.images[0]} alt={product.name} className="w-full h-full object-cover" />
                        ) : (
                          <Store size={28} />
                        )}
                      </div>
                      <div className="p-3 flex-1 flex flex-col gap-1">
                        <p className="text-sm font-semibold text-slate-800 line-clamp-1">{product.name}</p>
                        {product.description && (
                          <p className="text-xs text-slate-400 line-clamp-2">{product.description}</p>
                        )}
                        <p className="text-sm font-bold text-indigo-600 mt-auto pt-1">
                          {formatCurrency(product.price)}
                        </p>
                      </div>
                      <div className="flex border-t border-slate-100">
                        <button
                          onClick={() => openEdit(product)}
                          className="flex-1 flex items-center justify-center gap-1 py-2 text-xs text-slate-500 hover:bg-slate-50 transition-colors"
                        >
                          <Pencil size={12} /> Edit
                        </button>
                        <div className="w-px bg-slate-100" />
                        <button
                          onClick={() => handleDelete(product.id)}
                          className="flex-1 flex items-center justify-center gap-1 py-2 text-xs text-red-500 hover:bg-red-50 transition-colors"
                        >
                          <Trash2 size={12} /> Remove
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add / Edit modal */}
      {modal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">
                {modal === "add" ? "Add Product" : "Edit Product"}
              </h3>
              <button onClick={() => setModal(null)} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <Field label="Product name *" value={form.name} onChange={(v) => setForm((f) => ({ ...f, name: v }))} placeholder="e.g. Chicken Burger" />
              <Field label="Price (KES) *" type="number" value={form.price} onChange={(v) => setForm((f) => ({ ...f, price: v }))} placeholder="250" />
              <Field label="Category" value={form.category} onChange={(v) => setForm((f) => ({ ...f, category: v }))} placeholder="e.g. Beverages, Main Course" />
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Description</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder="Short description shown to customers…"
                  rows={3}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>
              <button
                onClick={handleSave}
                disabled={saving || !form.name || !form.price}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors text-sm"
              >
                {saving && <Loader2 size={15} className="animate-spin" />}
                {modal === "add" ? "Add to Shop" : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({
  label, type = "text", value, onChange, placeholder,
}: {
  label: string; type?: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
      />
    </div>
  );
}
