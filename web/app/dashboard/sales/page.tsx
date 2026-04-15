"use client";

import { useEffect, useState } from "react";
import { salesApi, expensesApi, Sale, Expense, api } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { TrendingUp, TrendingDown, Plus, Download, X, Loader2, ChevronDown, Send } from "lucide-react";

type Tab = "sales" | "expenses";
type DateRange = "Today" | "This Week" | "This Month" | "All Time";

const EXPENSE_CATEGORIES = ["Inventory", "Rent", "Transport", "Utilities", "Salaries", "Other"];
const PAYMENT_METHODS = ["Cash", "Mobile Money", "Card", "Bank Transfer", "Credit"];

function inRange(dateStr: string, range: DateRange): boolean {
  const d = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (range === "Today") return d >= today;
  if (range === "This Week") { const w = new Date(today); w.setDate(today.getDate() - today.getDay()); return d >= w; }
  if (range === "This Month") return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  return true;
}

export default function SalesPage() {
  const [tab, setTab] = useState<Tab>("sales");
  const [sales, setSales] = useState<Sale[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<DateRange>("This Month");
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saleForm, setSaleForm] = useState({ customer_id: "", item: "", amount: "", payment_method: "Cash", is_credit: false });
  const [expForm, setExpForm] = useState({ category: "Inventory", amount: "", description: "" });

  async function load() {
    setLoading(true);
    try {
      const [s, e] = await Promise.all([salesApi.list(), expensesApi.list()]);
      setSales(s);
      setExpenses(e);
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  const filteredSales = sales.filter((s) => inRange(s.created_at, range));
  const filteredExpenses = expenses.filter((e) => inRange(e.created_at, range));

  const totalSales = filteredSales.reduce((s, x) => s + x.amount, 0);
  const totalExpenses = filteredExpenses.reduce((s, x) => s + x.amount, 0);
  const netProfit = totalSales - totalExpenses;

  async function handleSaleAdd(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await salesApi.create({ ...saleForm, amount: parseFloat(saleForm.amount) });
      setShowAdd(false);
      await load();
    } finally { setSaving(false); }
  }

  async function handleExpenseAdd(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await expensesApi.create({ ...expForm, amount: parseFloat(expForm.amount) });
      setShowAdd(false);
      await load();
    } finally { setSaving(false); }
  }

  function exportCSV() {
    const rows = tab === "sales"
      ? [["Customer", "Item", "Amount", "Method", "Date"], ...filteredSales.map((s) => [s.customer_name, s.item, s.amount, s.payment_method, formatDate(s.created_at)])]
      : [["Category", "Amount", "Description", "Date"], ...filteredExpenses.map((e) => [e.category, e.amount, e.description || "", formatDate(e.created_at)])];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: `${tab}.csv` });
    a.click();
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Sales & Expenses</h1>
          <p className="text-slate-500 text-sm mt-1">Track revenue and spending</p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportCSV} className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
            <Download size={14} /> Export
          </button>
          <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700">
            <Plus size={15} /> {tab === "sales" ? "Add Sale" : "Add Expense"}
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-slate-500 font-medium">Revenue</p>
            <div className="w-8 h-8 bg-green-50 rounded-lg flex items-center justify-center">
              <TrendingUp size={16} className="text-green-600" />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{formatCurrency(totalSales)}</p>
          <p className="text-xs text-slate-400 mt-1">{filteredSales.length} sales</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-slate-500 font-medium">Expenses</p>
            <div className="w-8 h-8 bg-red-50 rounded-lg flex items-center justify-center">
              <TrendingDown size={16} className="text-red-500" />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{formatCurrency(totalExpenses)}</p>
          <p className="text-xs text-slate-400 mt-1">{filteredExpenses.length} expenses</p>
        </div>
        <div className={`rounded-xl border p-5 ${netProfit >= 0 ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}`}>
          <p className="text-sm font-medium text-slate-600 mb-2">Net Profit</p>
          <p className={`text-2xl font-bold ${netProfit >= 0 ? "text-green-700" : "text-red-700"}`}>
            {netProfit >= 0 ? "+" : ""}{formatCurrency(netProfit)}
          </p>
          <p className="text-xs text-slate-500 mt-1">{range}</p>
        </div>
      </div>

      {/* Tabs + date range */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex gap-1">
          {(["sales", "expenses"] as Tab[]).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${
                tab === t ? "bg-indigo-600 text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {t === "sales" ? `Sales (${filteredSales.length})` : `Expenses (${filteredExpenses.length})`}
            </button>
          ))}
        </div>
        <div className="relative">
          <select value={range} onChange={(e) => setRange(e.target.value as DateRange)}
            className="appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-slate-700">
            {(["Today", "This Week", "This Month", "All Time"] as DateRange[]).map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          {tab === "sales" ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {["Customer", "Item", "Amount", "Method", "Credit", "Date", ""].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i}>{Array.from({ length: 6 }).map((_, j) => (
                    <td key={j} className="px-4 py-3"><div className="h-4 bg-slate-100 rounded animate-pulse" /></td>
                  ))}</tr>
                )) : filteredSales.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{s.customer_name}</p>
                      <p className="text-xs text-slate-400">{s.customer_phone}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{s.item}</td>
                    <td className="px-4 py-3 font-semibold text-slate-900">{formatCurrency(s.amount)}</td>
                    <td className="px-4 py-3 text-slate-600 text-xs">{s.payment_method}</td>
                    <td className="px-4 py-3">
                      {s.is_credit && <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">Credit</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">{formatDate(s.created_at)}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => api.post(`/sales/${s.id}/resend-receipt`, {}).then(() => alert("Receipt sent!")).catch(() => alert("Failed"))}
                        className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-100 hover:text-indigo-600 transition-colors"
                        title="Resend receipt"
                      >
                        <Send size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {["Category", "Amount", "Description", "Date", ""].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i}>{Array.from({ length: 5 }).map((_, j) => (
                    <td key={j} className="px-4 py-3"><div className="h-4 bg-slate-100 rounded animate-pulse" /></td>
                  ))}</tr>
                )) : filteredExpenses.map((exp) => (
                  <tr key={exp.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <span className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full font-medium">{exp.category}</span>
                    </td>
                    <td className="px-4 py-3 font-semibold text-red-600">{formatCurrency(exp.amount)}</td>
                    <td className="px-4 py-3 text-slate-600">{exp.description || "—"}</td>
                    <td className="px-4 py-3 text-xs text-slate-400">{formatDate(exp.created_at)}</td>
                    <td className="px-4 py-3">
                      <button onClick={async () => { await expensesApi.delete(exp.id); await load(); }}
                        className="text-slate-400 hover:text-red-500 transition-colors">
                        <X size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!loading && (tab === "sales" ? filteredSales : filteredExpenses).length === 0 && (
            <p className="text-center text-sm text-slate-400 py-12">No {tab} in this period</p>
          )}
        </div>
      </div>

      {/* Add modal */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">{tab === "sales" ? "Add Sale" : "Add Expense"}</h3>
              <button onClick={() => setShowAdd(false)}><X size={20} className="text-slate-400" /></button>
            </div>
            {tab === "sales" ? (
              <form onSubmit={handleSaleAdd} className="p-6 space-y-4">
                <FField label="Customer name *" value={saleForm.customer_id} onChange={(v) => setSaleForm((f) => ({ ...f, customer_id: v }))} placeholder="Jane Doe" required />
                <FField label="Item / service *" value={saleForm.item} onChange={(v) => setSaleForm((f) => ({ ...f, item: v }))} placeholder="e.g. Chicken Burger" required />
                <FField label="Amount (KES) *" type="number" value={saleForm.amount} onChange={(v) => setSaleForm((f) => ({ ...f, amount: v }))} placeholder="500" required />
                <SelectField label="Payment method" value={saleForm.payment_method} onChange={(v) => setSaleForm((f) => ({ ...f, payment_method: v }))} options={PAYMENT_METHODS} />
                <button type="submit" disabled={saving}
                  className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm">
                  {saving && <Loader2 size={15} className="animate-spin" />} Record Sale
                </button>
              </form>
            ) : (
              <form onSubmit={handleExpenseAdd} className="p-6 space-y-4">
                <SelectField label="Category *" value={expForm.category} onChange={(v) => setExpForm((f) => ({ ...f, category: v }))} options={EXPENSE_CATEGORIES} />
                <FField label="Amount (KES) *" type="number" value={expForm.amount} onChange={(v) => setExpForm((f) => ({ ...f, amount: v }))} placeholder="1000" required />
                <FField label="Description" value={expForm.description} onChange={(v) => setExpForm((f) => ({ ...f, description: v }))} placeholder="Optional note" />
                <button type="submit" disabled={saving}
                  className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm">
                  {saving && <Loader2 size={15} className="animate-spin" />} Add Expense
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function FField({ label, value, onChange, placeholder, required, type = "text" }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; required?: boolean; type?: string }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} required={required}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500" />
    </div>
  );
}

function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <div className="relative">
        <select value={value} onChange={(e) => onChange(e.target.value)}
          className="w-full appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 bg-white">
          {options.map((o) => <option key={o}>{o}</option>)}
        </select>
        <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
      </div>
    </div>
  );
}
