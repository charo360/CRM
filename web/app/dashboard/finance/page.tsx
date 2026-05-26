"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { financeApi, budgetApi } from "@/lib/api";
import {
  BarChart2, Plus, Trash2, TrendingUp, TrendingDown, DollarSign,
  RefreshCw, Edit2, Download, X, Check, Target, AlertTriangle,
  ChevronLeft, ChevronRight,
} from "lucide-react";

// ── types ────────────────────────────────────────────────────────────────────
type FinanceEntry = {
  id: string; type: "income" | "expense"; category: string; amount: number;
  description: string; date: string; reference: string; currency: string;
};
type Summary = {
  income: number; expenses: number; profit: number;
  income_by_category: Record<string, number>;
  expense_by_category: Record<string, number>;
};
type MonthBar = { month: string; income: number; expense: number; profit: number };
type BudgetItem = {
  id: string | null; category: string; budgeted: number | null; actual: number;
  remaining: number | null; pct_used: number | null; currency: string; notes: string;
};
type BudgetReport = {
  from_date: string; to_date: string; period: string; year: number; month: number | null;
  items: BudgetItem[];
  totals: { budgeted: number; actual: number };
};

// ── helpers ───────────────────────────────────────────────────────────────────
function today() { return new Date().toISOString().split("T")[0]; }
function monthStart() { const d = new Date(); d.setDate(1); return d.toISOString().split("T")[0]; }
function yearStart() { return `${new Date().getFullYear()}-01-01`; }
function lastNDays(n: number) {
  const d = new Date(); d.setDate(d.getDate() - n);
  return d.toISOString().split("T")[0];
}
function quarterStart() {
  const d = new Date();
  const q = Math.floor(d.getMonth() / 3);
  return new Date(d.getFullYear(), q * 3, 1).toISOString().split("T")[0];
}
function fmt(n: number, cur = "KES") {
  return `${cur} ${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}
const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const PERIODS = [
  { label: "This month",    from: monthStart,  to: today },
  { label: "Last 30 days",  from: () => lastNDays(30), to: today },
  { label: "This quarter",  from: quarterStart, to: today },
  { label: "This year",     from: yearStart,    to: today },
  { label: "Custom",        from: monthStart,   to: today },
];

function emptyForm() {
  return { type: "income" as "income" | "expense", category: "", customCategory: "", amount: 0, description: "", date: today(), reference: "", currency: "KES" };
}

// ── SVG bar chart ─────────────────────────────────────────────────────────────
function TrendChart({ data }: { data: MonthBar[] }) {
  const W = 720, H = 180, PAD = { top: 16, right: 8, bottom: 36, left: 56 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  if (!data.length) return null;

  const maxVal = Math.max(...data.map(d => Math.max(d.income, d.expense)), 1);
  const barW = innerW / data.length;
  const bw = Math.max(4, barW * 0.3);
  const yTicks = 4;

  function xOf(i: number) { return PAD.left + i * barW + barW / 2; }
  function yOf(v: number) { return PAD.top + innerH - (v / maxVal) * innerH; }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" style={{ maxHeight: 200 }}>
      {Array.from({ length: yTicks + 1 }, (_, i) => {
        const v = (maxVal / yTicks) * i;
        const y = yOf(v);
        return (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="#e2e8f0" strokeWidth={1} />
            <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize={10} fill="#94a3b8">
              {v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v.toFixed(0)}
            </text>
          </g>
        );
      })}
      {data.map((d, i) => (
        <g key={i}>
          <rect x={xOf(i) - bw - 1} y={yOf(d.income)} width={bw} height={Math.max(1, innerH - (yOf(d.income) - PAD.top))} fill="#22c55e" rx={2} opacity={0.85} />
          <rect x={xOf(i) + 1} y={yOf(d.expense)} width={bw} height={Math.max(1, innerH - (yOf(d.expense) - PAD.top))} fill="#f87171" rx={2} opacity={0.85} />
          <text x={xOf(i)} y={H - 6} textAnchor="middle" fontSize={9} fill="#64748b">
            {d.month.split(" ")[0]}
          </text>
        </g>
      ))}
      {data.length > 1 && (
        <polyline
          points={data.map((d, i) => `${xOf(i)},${yOf(Math.max(0, d.profit))}`).join(" ")}
          fill="none" stroke="#6366f1" strokeWidth={2} strokeDasharray="4 2" strokeLinecap="round"
        />
      )}
    </svg>
  );
}

// ── category bar ─────────────────────────────────────────────────────────────
function CatBar({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-xs">
        <span className="text-slate-600 truncate max-w-[60%]">{label}</span>
        <span className={`font-medium ${color}`}>{pct}%</span>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color === "text-green-600" ? "#22c55e" : "#f87171" }} />
      </div>
    </div>
  );
}

// ── budget progress bar ───────────────────────────────────────────────────────
function BudgetBar({ pct }: { pct: number }) {
  const capped = Math.min(pct, 100);
  const color = pct >= 100 ? "#ef4444" : pct >= 75 ? "#f59e0b" : "#22c55e";
  return (
    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
      <div className="h-full rounded-full transition-all" style={{ width: `${capped}%`, background: color }} />
    </div>
  );
}

function budgetStatusColor(pct: number | null) {
  if (pct === null) return "text-slate-400";
  if (pct >= 100) return "text-red-600";
  if (pct >= 75) return "text-amber-600";
  return "text-green-600";
}

// ── Budget Tab ────────────────────────────────────────────────────────────────
function BudgetTab({ categories }: { categories: { income: string[]; expense: string[] } }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [report, setReport] = useState<BudgetReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<BudgetItem | null>(null);
  const [form, setForm] = useState({ category: "", customCategory: "", amount: 0, currency: "KES", notes: "" });
  const [saving, setSaving] = useState(false);

  const loadReport = useCallback(async () => {
    setLoading(true);
    try {
      const data = await budgetApi.vsActual({ year, month, period: "monthly" });
      setReport(data as unknown as BudgetReport);
    } finally {
      setLoading(false);
    }
  }, [year, month]);

  useEffect(() => { loadReport(); }, [loadReport]);

  function prevMonth() {
    if (month === 1) { setYear(y => y - 1); setMonth(12); }
    else setMonth(m => m - 1);
  }
  function nextMonth() {
    const n = new Date(); n.setDate(1);
    if (year > n.getFullYear() || (year === n.getFullYear() && month >= n.getMonth() + 1)) return;
    if (month === 12) { setYear(y => y + 1); setMonth(1); }
    else setMonth(m => m + 1);
  }

  function openNew() {
    setEditItem(null);
    setForm({ category: "", customCategory: "", amount: 0, currency: "KES", notes: "" });
    setShowModal(true);
  }
  function openEdit(item: BudgetItem) {
    setEditItem(item);
    setForm({ category: item.category, customCategory: "", amount: item.budgeted ?? 0, currency: item.currency, notes: item.notes });
    setShowModal(true);
  }

  async function save() {
    setSaving(true);
    const finalCat = form.category === "__custom__" ? form.customCategory.trim() : form.category;
    if (!finalCat || form.amount <= 0) { setSaving(false); return; }
    try {
      await budgetApi.upsert({
        category: finalCat, amount: form.amount, period: "monthly",
        year, month, currency: form.currency, notes: form.notes,
      });
      setShowModal(false);
      await loadReport();
    } finally { setSaving(false); }
  }

  async function deleteBudget(item: BudgetItem) {
    if (!item.id || !confirm(`Remove budget for "${item.category}"?`)) return;
    await budgetApi.delete(item.id);
    await loadReport();
  }

  const allExpenseCats = [...categories.expense, "__custom__"];
  const cur = report?.items[0]?.currency || "KES";
  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1;

  const totalBudgeted = report?.totals.budgeted ?? 0;
  const totalActual = report?.totals.actual ?? 0;
  const totalRemaining = totalBudgeted - totalActual;
  const totalPct = totalBudgeted > 0 ? Math.round((totalActual / totalBudgeted) * 100) : 0;
  const overBudget = (report?.items ?? []).filter(i => i.pct_used !== null && i.pct_used >= 100).length;
  const nearLimit = (report?.items ?? []).filter(i => i.pct_used !== null && i.pct_used >= 75 && i.pct_used < 100).length;

  return (
    <div className="space-y-5">
      {/* Month nav + add button */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button onClick={prevMonth} className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600">
            <ChevronLeft size={16} />
          </button>
          <span className="font-semibold text-slate-800 min-w-[110px] text-center">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <button onClick={nextMonth} disabled={isCurrentMonth}
            className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600 disabled:opacity-30">
            <ChevronRight size={16} />
          </button>
        </div>
        <button onClick={openNew}
          className="flex items-center gap-2 bg-brand-dark text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand">
          <Plus size={16} /> Set Budget
        </button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
          <p className="text-xs text-blue-700 font-medium">Total Budgeted</p>
          <p className="text-xl font-bold text-blue-800 mt-1 truncate">{fmt(totalBudgeted, cur)}</p>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <p className="text-xs text-red-700 font-medium">Total Spent</p>
          <p className="text-xl font-bold text-red-800 mt-1 truncate">{fmt(totalActual, cur)}</p>
        </div>
        <div className={`${totalRemaining >= 0 ? "bg-green-50 border-green-200" : "bg-orange-50 border-orange-200"} border rounded-xl p-4`}>
          <p className={`text-xs font-medium ${totalRemaining >= 0 ? "text-green-700" : "text-orange-700"}`}>
            {totalRemaining >= 0 ? "Remaining" : "Over Budget"}
          </p>
          <p className={`text-xl font-bold mt-1 truncate ${totalRemaining >= 0 ? "text-green-800" : "text-orange-700"}`}>
            {fmt(Math.abs(totalRemaining), cur)}
          </p>
        </div>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
          <p className="text-xs text-slate-500 font-medium">Budget Used</p>
          <p className="text-xl font-bold text-slate-800 mt-1">{totalPct}%</p>
          <div className="mt-2"><BudgetBar pct={totalPct} /></div>
        </div>
      </div>

      {/* Alert banners */}
      {overBudget > 0 && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          <AlertTriangle size={16} className="shrink-0" />
          <span><strong>{overBudget} categor{overBudget > 1 ? "ies" : "y"}</strong> exceeded the budget this month.</span>
        </div>
      )}
      {nearLimit > 0 && overBudget === 0 && (
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700">
          <AlertTriangle size={16} className="shrink-0" />
          <span><strong>{nearLimit} categor{nearLimit > 1 ? "ies" : "y"}</strong> at 75%+ of budget.</span>
        </div>
      )}

      {/* Budget table */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-slate-400">Loading…</div>
      ) : !report || report.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 bg-white rounded-xl border text-slate-400 gap-3">
          <Target size={40} className="opacity-30" />
          <p className="text-sm">No budgets or expenses for {MONTH_NAMES[month - 1]} {year}.</p>
          <button onClick={openNew}
            className="flex items-center gap-1.5 text-brand-dark text-sm font-medium hover:underline">
            <Plus size={14} /> Set your first budget
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-x-auto">
          <table className="w-full text-sm min-w-[620px]">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-3">Category</th>
                <th className="text-right px-4 py-3">Budgeted</th>
                <th className="text-right px-4 py-3">Spent</th>
                <th className="text-right px-4 py-3">Remaining</th>
                <th className="px-4 py-3 min-w-[140px]">Progress</th>
                <th className="text-right px-4 py-3">% Used</th>
                <th className="text-right px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {report.items.map((item, idx) => (
                <tr key={item.id ?? `unbudgeted-${idx}`} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-700">{item.category}</td>
                  <td className="px-4 py-3 text-right text-slate-600 tabular-nums">
                    {item.budgeted != null ? fmt(item.budgeted, item.currency) : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-right text-red-600 font-medium tabular-nums">
                    {fmt(item.actual, item.currency)}
                  </td>
                  <td className={`px-4 py-3 text-right font-medium tabular-nums ${
                    item.remaining == null ? "text-slate-300" :
                    item.remaining < 0 ? "text-red-600" : "text-green-600"
                  }`}>
                    {item.remaining != null
                      ? (item.remaining < 0 ? `-${fmt(Math.abs(item.remaining), item.currency)}` : fmt(item.remaining, item.currency))
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {item.pct_used != null
                      ? <BudgetBar pct={item.pct_used} />
                      : <div className="h-2 bg-slate-100 rounded-full" title="No budget set" />}
                  </td>
                  <td className={`px-4 py-3 text-right font-semibold tabular-nums ${budgetStatusColor(item.pct_used)}`}>
                    {item.pct_used != null ? `${item.pct_used}%` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => openEdit(item)} className="text-slate-400 hover:text-brand-dark" title="Edit budget">
                        <Edit2 size={14} />
                      </button>
                      {item.id && (
                        <button onClick={() => deleteBudget(item)} className="text-slate-400 hover:text-red-500" title="Remove budget">
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-2 text-xs text-slate-400 border-t">{report.items.length} categories</div>
        </div>
      )}

      {/* Set / Edit budget modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-base font-semibold">{editItem ? "Edit Budget" : "Set Budget"}</h2>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-700"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Expense Category</label>
                <select
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  value={form.category}
                  disabled={!!editItem}
                  onChange={e => setForm(f => ({ ...f, category: e.target.value, customCategory: "" }))}>
                  <option value="">Select category…</option>
                  {categories.expense.map(c => <option key={c} value={c}>{c}</option>)}
                  <option value="__custom__">+ Add custom category</option>
                </select>
                {form.category === "__custom__" && (
                  <input
                    className="mt-2 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    placeholder="Custom category name"
                    value={form.customCategory}
                    onChange={e => setForm(f => ({ ...f, customCategory: e.target.value }))}
                  />
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Budget Amount</label>
                  <input type="number" min="0" step="0.01"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.amount || ""}
                    onFocus={e => e.target.select()}
                    onChange={e => setForm(f => ({ ...f, amount: +e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Currency</label>
                  <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.currency}
                    onChange={e => setForm(f => ({ ...f, currency: e.target.value }))}>
                    {["KES","USD","EUR","GBP","NGN","GHS","ZAR","TZS","UGX"].map(c => <option key={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Notes <span className="text-slate-400">(optional)</span></label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="e.g. Q2 marketing spend" />
              </div>
              <p className="text-xs text-slate-400">Period: <span className="font-medium text-slate-600">{MONTH_NAMES[month - 1]} {year}</span></p>
            </div>
            <div className="p-5 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900">Cancel</button>
              <button
                onClick={save}
                disabled={saving || (!editItem && (!form.category || (form.category === "__custom__" && !form.customCategory.trim()))) || form.amount <= 0}
                className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50 flex items-center gap-1.5">
                {saving ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                {saving ? "Saving…" : "Save Budget"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Finance Page ─────────────────────────────────────────────────────────
export default function FinancePage() {
  const [tab, setTab] = useState<"transactions" | "budget">("transactions");
  const [entries, setEntries]   = useState<FinanceEntry[]>([]);
  const [summary, setSummary]   = useState<Summary>({ income: 0, expenses: 0, profit: 0, income_by_category: {}, expense_by_category: {} });
  const [monthly, setMonthly]   = useState<MonthBar[]>([]);
  const [categories, setCategories] = useState<{ income: string[]; expense: string[] }>({ income: [], expense: [] });
  const [loading, setLoading]   = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing]   = useState<FinanceEntry | null>(null);
  const [form, setForm]         = useState(emptyForm());
  const [saving, setSaving]     = useState(false);
  const [periodIdx, setPeriodIdx] = useState(0);
  const [fromDate, setFromDate] = useState(monthStart());
  const [toDate, setToDate]     = useState(today());
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch]     = useState("");
  const [exporting, setExporting] = useState(false);

  async function doExport() {
    setExporting(true);
    try {
      await financeApi.exportCsv({ type: typeFilter || undefined, from_date: fromDate, to_date: toDate });
    } catch (e) {
      alert(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  function applyPeriod(idx: number) {
    setPeriodIdx(idx);
    if (idx !== 4) {
      setFromDate(PERIODS[idx].from());
      setToDate(PERIODS[idx].to());
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, sum, cats, mon] = await Promise.all([
        financeApi.listEntries({ type: typeFilter || undefined, from_date: fromDate, to_date: toDate }),
        financeApi.summary({ from_date: fromDate, to_date: toDate }),
        financeApi.categories(),
        financeApi.monthly(12),
      ]);
      setEntries(list as FinanceEntry[]);
      setSummary(sum as Summary);
      setCategories(cats as { income: string[]; expense: string[] });
      setMonthly(mon as MonthBar[]);
    } finally { setLoading(false); }
  }, [fromDate, toDate, typeFilter]);

  useEffect(() => { load(); }, [load]);

  function openNew() { setEditing(null); setForm(emptyForm()); setShowModal(true); }
  function openEdit(e: FinanceEntry) {
    setEditing(e);
    setForm({ type: e.type, category: e.category, customCategory: "", amount: e.amount, description: e.description, date: e.date, reference: e.reference, currency: e.currency });
    setShowModal(true);
  }

  async function save() {
    setSaving(true);
    const finalCat = form.category === "__custom__" ? form.customCategory.trim() : form.category;
    if (!finalCat) { setSaving(false); return; }
    try {
      const payload = { ...form, category: finalCat };
      if (editing) { await financeApi.updateEntry(editing.id, payload as Record<string, unknown>); }
      else { await financeApi.createEntry(payload as Record<string, unknown>); }
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
  const margin = summary.income > 0 ? Math.round((summary.profit / summary.income) * 100) : 0;

  const filtered = useMemo(() => entries.filter(e => {
    if (search) {
      const s = search.toLowerCase();
      return e.category.toLowerCase().includes(s) || e.description.toLowerCase().includes(s) || e.reference.toLowerCase().includes(s);
    }
    return true;
  }), [entries, search]);

  const cur = entries[0]?.currency || "KES";

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <BarChart2 className="text-brand-dark" size={24} /> Finance &amp; P&amp;L
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Income, expenses, profitability and budgets</p>
        </div>
        {tab === "transactions" && (
          <div className="flex items-center gap-2">
            <button
              onClick={doExport} disabled={exporting}
              className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50">
              {exporting ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />} Export CSV
            </button>
            <button onClick={openNew} className="flex items-center gap-2 bg-brand-dark text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand">
              <Plus size={16} /> Add Entry
            </button>
          </div>
        )}
      </div>

      {/* Tab switcher */}
      <div className="flex border-b border-slate-200">
        <button
          onClick={() => setTab("transactions")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "transactions" ? "border-brand-dark text-brand-dark" : "border-transparent text-slate-500 hover:text-slate-700"
          }`}>
          Transactions &amp; P&amp;L
        </button>
        <button
          onClick={() => setTab("budget")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5 ${
            tab === "budget" ? "border-brand-dark text-brand-dark" : "border-transparent text-slate-500 hover:text-slate-700"
          }`}>
          <Target size={14} /> Budget Tracker
        </button>
      </div>

      {/* ── Budget Tab ── */}
      {tab === "budget" && <BudgetTab categories={categories} />}

      {/* ── Transactions Tab ── */}
      {tab === "transactions" && (
        <>
          {/* Period presets */}
          <div className="flex flex-wrap gap-2 items-center">
            {PERIODS.map((p, i) => (
              <button key={p.label} onClick={() => applyPeriod(i)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  periodIdx === i ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                }`}>{p.label}</button>
            ))}
            {periodIdx === 4 && (
              <div className="flex items-center gap-2 ml-1">
                <input type="date" className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs" value={fromDate} onChange={e => setFromDate(e.target.value)} />
                <span className="text-slate-400 text-xs">→</span>
                <input type="date" className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs" value={toDate} onChange={e => setToDate(e.target.value)} />
                <button onClick={load} className="text-slate-400 hover:text-slate-700"><RefreshCw size={14} /></button>
              </div>
            )}
          </div>

          {/* KPI cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-4">
              <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center shrink-0">
                <TrendingUp className="text-green-600" size={20} />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-green-700 font-medium">Total Income</p>
                <p className="text-xl font-bold text-green-800 truncate">{fmt(summary.income, cur)}</p>
              </div>
            </div>
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-4">
              <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center shrink-0">
                <TrendingDown className="text-red-600" size={20} />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-red-700 font-medium">Total Expenses</p>
                <p className="text-xl font-bold text-red-800 truncate">{fmt(summary.expenses, cur)}</p>
              </div>
            </div>
            <div className={`${ summary.profit >= 0 ? "bg-emerald-50 border-emerald-200" : "bg-orange-50 border-orange-200"} border rounded-xl p-4 flex items-center gap-4`}>
              <div className={`w-10 h-10 ${ summary.profit >= 0 ? "bg-emerald-100" : "bg-orange-100"} rounded-full flex items-center justify-center shrink-0`}>
                <DollarSign className={summary.profit >= 0 ? "text-emerald-600" : "text-orange-600"} size={20} />
              </div>
              <div className="min-w-0">
                <p className={`text-xs font-medium ${ summary.profit >= 0 ? "text-emerald-700" : "text-orange-700"}`}>
                  Net Profit {summary.income > 0 && <span className="ml-1 opacity-70">({margin}% margin)</span>}
                </p>
                <p className={`text-xl font-bold truncate ${profitColor}`}>
                  {summary.profit < 0 ? "-" : ""}{fmt(summary.profit, cur)}
                </p>
              </div>
            </div>
          </div>

          {/* Chart + breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-white rounded-xl border p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-slate-700 text-sm">12-Month Trend</h3>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <span className="flex items-center gap-1"><span className="w-3 h-2 rounded bg-green-400 inline-block" /> Income</span>
                  <span className="flex items-center gap-1"><span className="w-3 h-2 rounded bg-red-400 inline-block" /> Expenses</span>
                  <span className="flex items-center gap-1"><span className="w-5 border-t-2 border-dashed border-indigo-500 inline-block" /> Profit</span>
                </div>
              </div>
              {monthly.length > 0 ? <TrendChart data={monthly} /> : (
                <div className="h-40 flex items-center justify-center text-slate-400 text-sm">No data yet</div>
              )}
            </div>

            <div className="bg-white rounded-xl border p-4 space-y-4">
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Income by category</h4>
                <div className="space-y-2">
                  {Object.entries(summary.income_by_category).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([cat, amt]) => (
                    <div key={cat}>
                      <CatBar label={cat} value={amt} total={summary.income} color="text-green-600" />
                      <p className="text-right text-[11px] text-green-600 font-medium mt-0.5">{fmt(amt, cur)}</p>
                    </div>
                  ))}
                  {Object.keys(summary.income_by_category).length === 0 && <p className="text-slate-400 text-xs">None</p>}
                </div>
              </div>
              <div className="border-t pt-3">
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Expenses by category</h4>
                <div className="space-y-2">
                  {Object.entries(summary.expense_by_category).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([cat, amt]) => (
                    <div key={cat}>
                      <CatBar label={cat} value={amt} total={summary.expenses} color="text-red-500" />
                      <p className="text-right text-[11px] text-red-500 font-medium mt-0.5">{fmt(amt, cur)}</p>
                    </div>
                  ))}
                  {Object.keys(summary.expense_by_category).length === 0 && <p className="text-slate-400 text-xs">None</p>}
                </div>
              </div>
            </div>
          </div>

          {/* Filters + search */}
          <div className="flex flex-wrap gap-2 items-center">
            <div className="flex gap-1">
              {["","income","expense"].map(t => (
                <button key={t} onClick={() => setTypeFilter(t)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors capitalize ${
                    typeFilter === t ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200"
                  }`}>{t || "All"}</button>
              ))}
            </div>
            <input
              placeholder="Search description, category…"
              value={search} onChange={e => setSearch(e.target.value)}
              className="ml-auto border border-slate-200 rounded-lg px-3 py-1.5 text-sm w-52 focus:outline-none focus:ring-2 focus:ring-brand-dark/20"
            />
          </div>

          {/* Table */}
          {loading ? (
            <div className="flex items-center justify-center h-40 text-slate-400">Loading…</div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
              <BarChart2 size={40} className="opacity-30" />
              <p className="text-sm">{entries.length === 0 ? "No entries in this period. Add income or expenses to get started." : "No results match your search."}</p>
            </div>
          ) : (
            <div className="bg-white rounded-xl border overflow-x-auto">
              <table className="w-full text-sm min-w-[600px]">
                <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                  <tr>
                    <th className="text-left px-4 py-3">Date</th>
                    <th className="text-left px-4 py-3">Type</th>
                    <th className="text-left px-4 py-3">Category</th>
                    <th className="text-left px-4 py-3">Description</th>
                    <th className="text-left px-4 py-3">Ref</th>
                    <th className="text-right px-4 py-3">Amount</th>
                    <th className="text-right px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filtered.map(e => (
                    <tr key={e.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-500 tabular-nums whitespace-nowrap">{new Date(e.date).toLocaleDateString()}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          e.type === "income" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                        }`}>{e.type}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{e.category}</td>
                      <td className="px-4 py-3 text-slate-700 max-w-[180px] truncate">{e.description || "—"}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{e.reference || "—"}</td>
                      <td className={`px-4 py-3 text-right font-semibold tabular-nums ${
                        e.type === "income" ? "text-green-700" : "text-red-600"
                      }`}>
                        {e.type === "income" ? "+" : "-"}{e.currency} {e.amount.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <button onClick={() => openEdit(e)} className="text-slate-400 hover:text-brand-dark" title="Edit"><Edit2 size={14} /></button>
                          <button onClick={() => del(e)} className="text-slate-400 hover:text-red-500" title="Delete"><Trash2 size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="px-4 py-2 text-xs text-slate-400 border-t">{filtered.length} entries</div>
            </div>
          )}
        </>
      )}

      {/* Add / Edit entry modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-base font-semibold">{editing ? "Edit Entry" : "New Entry"}</h2>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-700"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="flex rounded-lg overflow-hidden border border-slate-200">
                <button onClick={() => setForm(f => ({ ...f, type: "income", category: "", customCategory: "" }))}
                  className={`flex-1 py-2 text-sm font-medium transition-colors ${
                    form.type === "income" ? "bg-green-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                  }`}>Income</button>
                <button onClick={() => setForm(f => ({ ...f, type: "expense", category: "", customCategory: "" }))}
                  className={`flex-1 py-2 text-sm font-medium border-l border-slate-200 transition-colors ${
                    form.type === "expense" ? "bg-red-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                  }`}>Expense</button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-slate-600 mb-1">Category</label>
                  <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.category}
                    onChange={e => setForm(f => ({ ...f, category: e.target.value, customCategory: "" }))}>
                    <option value="">Select category…</option>
                    {currentCats.map(c => <option key={c} value={c}>{c}</option>)}
                    <option value="__custom__">+ Add custom category</option>
                  </select>
                  {form.category === "__custom__" && (
                    <input
                      className="mt-2 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                      placeholder="Type custom category name"
                      value={form.customCategory}
                      onChange={e => setForm(f => ({ ...f, customCategory: e.target.value }))}
                    />
                  )}
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Amount</label>
                  <input type="number" min="0" step="0.01"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.amount || ""}
                    onFocus={e => e.target.select()}
                    onChange={e => setForm(f => ({ ...f, amount: +e.target.value }))} />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Currency</label>
                  <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.currency}
                    onChange={e => setForm(f => ({ ...f, currency: e.target.value }))}>
                    {["KES","USD","EUR","GBP","NGN","GHS","ZAR","TZS","UGX"].map(c => <option key={c}>{c}</option>)}
                  </select>
                </div>

                <div className="col-span-2">
                  <label className="block text-xs font-medium text-slate-600 mb-1">Description <span className="text-slate-400">(optional)</span></label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.description}
                    onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Brief note" />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Date</label>
                  <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.date}
                    onChange={e => setForm(f => ({ ...f, date: e.target.value }))} />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Reference <span className="text-slate-400">(optional)</span></label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.reference}
                    onChange={e => setForm(f => ({ ...f, reference: e.target.value }))} placeholder="Receipt #, INV-001" />
                </div>
              </div>
            </div>
            <div className="p-5 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900">Cancel</button>
              <button
                onClick={save}
                disabled={saving || (form.category === "" || (form.category === "__custom__" && !form.customCategory.trim())) || form.amount <= 0}
                className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50 flex items-center gap-1.5">
                {saving ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                {saving ? "Saving…" : editing ? "Update" : "Add Entry"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
