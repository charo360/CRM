"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatCurrency, timeAgo } from "@/lib/utils";
import { Truck, Plus, RefreshCw, Loader2, Sparkles, X, Star } from "lucide-react";

interface Supplier {
  id: string;
  name: string;
  phone_number: string;
  email?: string;
  supplier_category?: string;
  payment_terms?: string;
  lead_time_days?: number;
  rating?: number;
  total_spent?: number;
  last_contacted?: string;
  tags?: string[];
}

interface SupplierInsights {
  potential_suppliers: { id: string; name: string; phone_number: string; reason: string }[];
  restock_suggestions: { product_name: string; supplier_name?: string; suggested_qty?: number }[];
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [insights, setInsights] = useState<SupplierInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"suppliers" | "insights">("suppliers");
  const [tagging, setTagging] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [sups, ins] = await Promise.all([
        api.get<Supplier[]>("/suppliers").catch(() => []),
        api.get<SupplierInsights>("/suppliers/insights").catch(() => null),
      ]);
      setSuppliers(sups);
      setInsights(ins);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleTagAsSupplier(customerId: string, category = "Other") {
    setTagging(customerId);
    try {
      await api.post(`/suppliers/${customerId}/tag`, { category });
      await load();
    } finally {
      setTagging(null);
    }
  }

  async function handleRemove(customerId: string) {
    if (!confirm("Remove supplier tag from this contact?")) return;
    await api.delete(`/suppliers/${customerId}`);
    await load();
  }

  const TABS = [
    { id: "suppliers" as const, label: "Suppliers", count: suppliers.length },
    { id: "insights" as const, label: "AI Insights", count: insights?.potential_suppliers?.length ?? 0 },
  ];

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Suppliers</h1>
          <p className="text-slate-500 text-sm mt-1">Manage vendors and restocking</p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map(({ id, label, count }) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === id ? "bg-white border-b-2 border-indigo-600 text-indigo-600" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {label} {count > 0 && <span className="ml-1 text-xs text-slate-400">({count})</span>}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin text-indigo-600" size={24} /></div>
      ) : activeTab === "suppliers" ? (
        suppliers.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
            <Truck size={32} className="text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500 font-medium">No suppliers yet</p>
            <p className="text-slate-400 text-sm mt-1">Check AI Insights to find potential suppliers from your contacts</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  {["Supplier", "Category", "Phone", "Rating", "Total Spent", "Last Contact", ""].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {suppliers.map(s => (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{s.name}</p>
                      {s.email && <p className="text-xs text-slate-400">{s.email}</p>}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">
                        {s.supplier_category || "Other"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs font-mono">{s.phone_number}</td>
                    <td className="px-4 py-3">
                      {s.rating ? (
                        <div className="flex items-center gap-1">
                          <Star size={12} className="text-amber-400 fill-amber-400" />
                          <span className="text-sm font-medium">{s.rating}/5</span>
                        </div>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-800">{formatCurrency(s.total_spent || 0)}</td>
                    <td className="px-4 py-3 text-xs text-slate-400">{s.last_contacted ? timeAgo(s.last_contacted) : "—"}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => handleRemove(s.id)} className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600" title="Remove supplier">
                        <X size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        <div className="space-y-5">
          {/* Potential Suppliers */}
          {insights?.potential_suppliers && insights.potential_suppliers.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
                <Sparkles size={16} className="text-purple-500" />
                <h2 className="font-semibold text-slate-800">Potential Suppliers</h2>
                <span className="text-xs text-slate-400 ml-1">AI-identified from your contacts</span>
              </div>
              <div className="divide-y divide-slate-100">
                {insights.potential_suppliers.map(p => (
                  <div key={p.id} className="flex items-center justify-between px-5 py-4 gap-4">
                    <div>
                      <p className="font-medium text-slate-800">{p.name}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{p.phone_number}</p>
                      <p className="text-xs text-purple-600 mt-0.5">{p.reason}</p>
                    </div>
                    <button
                      onClick={() => handleTagAsSupplier(p.id)}
                      disabled={tagging === p.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 shrink-0"
                    >
                      {tagging === p.id ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                      Tag as Supplier
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Restock Suggestions */}
          {insights?.restock_suggestions && insights.restock_suggestions.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100">
                <h2 className="font-semibold text-slate-800">Restock Suggestions</h2>
              </div>
              <div className="divide-y divide-slate-100">
                {insights.restock_suggestions.map((r, i) => (
                  <div key={i} className="flex items-center justify-between px-5 py-3">
                    <div>
                      <p className="font-medium text-slate-800">{r.product_name}</p>
                      {r.supplier_name && <p className="text-xs text-slate-400">via {r.supplier_name}</p>}
                    </div>
                    {r.suggested_qty && (
                      <span className="text-xs px-2 py-1 bg-amber-50 text-amber-700 rounded-lg font-medium">
                        Order {r.suggested_qty} units
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {!insights?.potential_suppliers?.length && !insights?.restock_suggestions?.length && (
            <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
              <Sparkles size={32} className="text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500">No insights available yet</p>
              <p className="text-slate-400 text-sm mt-1">Add more customer and sales data to generate AI insights</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
