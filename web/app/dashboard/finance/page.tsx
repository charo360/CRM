"use client";
import { useEffect, useState, useCallback } from "react";
import { financeApi } from "@/lib/api";
import { PieChart, Plus, Trash2, TrendingUp, TrendingDown, DollarSign, RefreshCw, Edit2 } from "lucide-react";

type FinanceEntry = {
  id: string; type: "income" | "expense"; category: string; amount: number;
  description: string; date: string; reference: string; currency: string;
};
type Summary = { income: number; expenses: number; profit: number; income_by_category: Record<string, number>; expense_by_category: Record<string, number> };

function today() { return new Date().toISOString().split("T")[0]; }
function monthStart() { const d = new Date(); d.setDate(1); return d.toISOString().split("T")[0]; }

function emptyForm() {
  return { type: "income" as "income" | "expense", category: "", amount: 0, description: "", date: today(), reference: "", currency: "KES" };
}

export default function FinancePage() {
  const [entries, setEntries] = useState<FinanceEntry[]>([]);
  const [summary, setSummary] = useState<Summary>({ income: 0, expenses: 0, profit: 0, income_by_category: {}, expense_by_category: {} });
  const [categories, setCategories] = useState<{ income: string[]; expense: string[] }>({ income: [], expense: [] });
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<FinanceEntry | null>(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [fromDate, setFromDate] = useState(monthStart());
  const [toDate, setToDate] = useState(today());
  const [typeFilter, setTypeFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, sum, cats] = await Promise.all([
        financeApi.listEntries({ type: typeFilter || undefined, from_date: fromDate, to_date: toDate }),
        financeApi.summary({ from_date: fromDate, to_date: toDate }),
        financeApi.categories(),
      ]);
      setEntries(list as FinanceEntry[]);
      setSummary(sum as Summary);
      setCategories(cats as { income: string[]; expense: string[] });
    } finally { setLoading(false); }
  }, [fromDate, toDate, typeFilter]);

  useEffect(() => { load(); }, [load]);

  function openNew() { setEditing(null); setForm(emptyForm()); setShowModal(true); }
  function openEdit(e: FinanceEntry) {
    setEditing(e);
    setForm({ type: e.type, category: e.category, amount: e.amount, description: e.description, date: e.date, reference: e.reference, currency: e.currency });
    setShowModal(true);
  }

  async function save() {
    setSaving(true);
    try {
      if (editing) { await financeApi.updateEntry(editing.id, form); }
      else { await financeApi.createEntry(form); }
      setShowModal(false); await load();
    } finally { setSaving(false); }
  }

  async function del(e: FinanceEntry) {
    if (!confirm("Delete this entry?")) return;
    await financeApi.deleteEntry(e.id);
    await load();
  }

  const currentCats = form.type === "income" ? categories.income : categories.expense;
  const profitColor = summary.profit >= 0 ? "text-green-600" : "text-red-600";

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <PieChart className="text-brand-dark" size={24} /> Finance & P&L
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Track income, expenses and profitability</p>
        </div>
        <button onClick={openNew} className="flex items-center gap-2 bg-brand-dark text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand">
          <Plus size={16} /> Add Entry
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
            <TrendingUp className="text-green-600" size={20} />
          </div>
          <div>
            <p className="text-xs text-green-700 font-medium">Total Income</p>
            <p className="text-2xl font-bold text-green-800">KES {summary.income.toLocaleString()}</p>
          </div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
            <TrendingDown className="text-red-600" size={20} />
          </div>
          <div>
            <p className="text-xs text-red-700 font-medium">Total Expenses</p>
            <p className="text-2xl font-bold text-red-800">KES {summary.expenses.toLocaleString()}</p>
          </div>
        </div>
        <div className={`${summary.profit >= 0 ? "bg-brand/10 border-brand/30" : "bg-orange-50 border-orange-200"} border rounded-xl p-4 flex items-center gap-4`}>
          <div className={`w-10 h-10 ${summary.profit >= 0 ? "bg-brand/15" : "bg-orange-100"} rounded-full flex items-center justify-center`}>
            <DollarSign className={summary.profit >= 0 ? "text-brand-dark" : "text-orange-600"} size={20} />
          </div>
          <div>
            <p className={`text-xs font-medium ${summary.profit >= 0 ? "text-brand-dark" : "text-orange-700"}`}>Net Profit</p>
            <p className={`text-2xl font-bold ${profitColor}`}>KES {summary.profit.toLocaleString()}</p>
          </div>
        </div>
      </div>

      {/* Category breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border p-4">
          <h3 className="font-semibold text-slate-700 mb-3 text-sm">Income by Category</h3>
          <div className="space-y-2">
            {Object.entries(summary.income_by_category).sort((a,b) => b[1]-a[1]).map(([cat, amt]) => (
              <div key={cat} className="flex justify-between text-sm">
                <span className="text-slate-600">{cat}</span>
                <span className="font-medium text-green-700">KES {amt.toLocaleString()}</span>
              </div>
            ))}
            {Object.keys(summary.income_by_category).length === 0 && <p className="text-slate-400 text-sm">No income entries</p>}
          </div>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <h3 className="font-semibold text-slate-700 mb-3 text-sm">Expenses by Category</h3>
          <div className="space-y-2">
            {Object.entries(summary.expense_by_category).sort((a,b) => b[1]-a[1]).map(([cat, amt]) => (
              <div key={cat} className="flex justify-between text-sm">
                <span className="text-slate-600">{cat}</span>
                <span className="font-medium text-red-700">KES {amt.toLocaleString()}</span>
              </div>
            ))}
            {Object.keys(summary.expense_by_category).length === 0 && <p className="text-slate-400 text-sm">No expense entries</p>}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex gap-1">
          {["","income","expense"].map(t => (
            <button key={t} onClick={() => setTypeFilter(t)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors capitalize ${typeFilter === t ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200"}`}>
              {t || "All"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <input type="date" className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs" value={fromDate} onChange={e => setFromDate(e.target.value)} />
          <span className="text-slate-400 text-xs">to</span>
          <input type="date" className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs" value={toDate} onChange={e => setToDate(e.target.value)} />
          <button onClick={load} className="text-slate-400 hover:text-slate-700"><RefreshCw size={16} /></button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-slate-400">Loading...</div>
      ) : entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
          <PieChart size={40} className="opacity-30" />
          <p>No entries in this period. Add your income or expenses.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-3">Date</th>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Category</th>
                <th className="text-left px-4 py-3">Description</th>
                <th className="text-right px-4 py-3">Amount</th>
                <th className="text-right px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {entries.map(e => (
                <tr key={e.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-500">{new Date(e.date).toLocaleDateString()}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${e.type === "income" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {e.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{e.category}</td>
                  <td className="px-4 py-3 text-slate-700">{e.description || "—"}</td>
                  <td className={`px-4 py-3 text-right font-semibold ${e.type === "income" ? "text-green-700" : "text-red-700"}`}>
                    {e.type === "income" ? "+" : "-"}{e.currency} {e.amount.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => openEdit(e)} className="text-slate-400 hover:text-brand-dark"><Edit2 size={14} /></button>
                      <button onClick={() => del(e)} className="text-slate-400 hover:text-red-500"><Trash2 size={14} /></button>
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
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-lg font-semibold">{editing ? "Edit Entry" : "New Entry"}</h2>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Type</label>
                <div className="flex gap-2">
                  <button onClick={() => setForm(f => ({ ...f, type: "income", category: "" }))}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium border ${form.type === "income" ? "bg-green-600 text-white border-green-600" : "bg-white text-slate-600 border-slate-200"}`}>
                    Income
                  </button>
                  <button onClick={() => setForm(f => ({ ...f, type: "expense", category: "" }))}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium border ${form.type === "expense" ? "bg-red-600 text-white border-red-600" : "bg-white text-slate-600 border-slate-200"}`}>
                    Expense
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Category</label>
                  <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.category}
                    onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
                    <option value="">Select...</option>
                    {currentCats.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Amount (KES)</label>
                  <input type="number" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.amount}
                    onChange={e => setForm(f => ({ ...f, amount: +e.target.value }))} />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.description}
                    onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Optional note" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Date</label>
                  <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.date}
                    onChange={e => setForm(f => ({ ...f, date: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Reference</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.reference}
                    onChange={e => setForm(f => ({ ...f, reference: e.target.value }))} placeholder="Receipt #, invoice #" />
                </div>
              </div>
            </div>
            <div className="p-6 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={save} disabled={saving || !form.category || form.amount <= 0}
                className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50">
                {saving ? "Saving..." : editing ? "Update" : "Add Entry"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
