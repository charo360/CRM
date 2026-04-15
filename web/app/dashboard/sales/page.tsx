"use client";

import { useEffect, useMemo, useState } from "react";
import { salesApi, expensesApi, Sale, Expense, api, customersApi, Customer } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import {
  TrendingUp,
  TrendingDown,
  Plus,
  Download,
  X,
  Loader2,
  ChevronDown,
  Send,
  Search,
  Footprints,
  User,
  UserPlus,
  CheckCircle2,
} from "lucide-react";

type Tab = "sales" | "expenses";
type DateRange = "Today" | "This Week" | "This Month" | "All Time";
type CustomerMode = "walkin" | "crm" | "new";

const EXPENSE_CATEGORIES = ["Inventory", "Rent", "Transport", "Utilities", "Salaries", "Other"];
const SALE_PAYMENT_METHODS = ["Cash", "Mobile Money", "Card", "Bank Transfer", "M-Pesa"];

function inRange(dateStr: string, range: DateRange): boolean {
  const d = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (range === "Today") return d >= today;
  if (range === "This Week") {
    const w = new Date(today);
    w.setDate(today.getDate() - today.getDay());
    return d >= w;
  }
  if (range === "This Month")
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  return true;
}

export default function SalesPage() {
  const [tab, setTab] = useState<Tab>("sales");
  const [sales, setSales] = useState<Sale[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<DateRange>("This Month");
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [markingPaidId, setMarkingPaidId] = useState<string | null>(null);

  const [customerMode, setCustomerMode] = useState<CustomerMode>("crm");
  const [customerSearch, setCustomerSearch] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [newContactName, setNewContactName] = useState("");
  const [newContactPhone, setNewContactPhone] = useState("");

  const [saleForm, setSaleForm] = useState({
    item: "",
    amount: "",
    payment_method: "Cash",
    send_receipt: true,
    is_credit: false,
    due_date: "",
  });

  const [expForm, setExpForm] = useState({ category: "Inventory", amount: "", description: "" });

  async function load() {
    setLoading(true);
    try {
      const [s, e, c] = await Promise.all([
        salesApi.list(),
        expensesApi.list(),
        customersApi.list().catch(() => [] as Customer[]),
      ]);
      setSales(s);
      setExpenses(e);
      setCustomers(c);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function resetSaleModal() {
    setCustomerMode("crm");
    setCustomerSearch("");
    setSelectedCustomer(null);
    setNewContactName("");
    setNewContactPhone("");
    setSaleForm({
      item: "",
      amount: "",
      payment_method: "Cash",
      send_receipt: true,
      is_credit: false,
      due_date: "",
    });
  }

  useEffect(() => {
    if (showAdd && tab === "sales") resetSaleModal();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showAdd, tab]);

  const filteredSales = sales.filter((s) => inRange(s.created_at, range));
  const filteredExpenses = expenses.filter((e) => inRange(e.created_at, range));

  const filteredCustomersPick = useMemo(() => {
    const q = customerSearch.trim().toLowerCase();
    return customers.filter(
      (c) =>
        !q ||
        c.name.toLowerCase().includes(q) ||
        c.phone_number.includes(q)
    );
  }, [customers, customerSearch]);

  const totalSales = filteredSales.reduce((s, x) => s + x.amount, 0);
  const totalExpenses = filteredExpenses.reduce((s, x) => s + x.amount, 0);
  const netProfit = totalSales - totalExpenses;

  async function handleSaleAdd(e: React.FormEvent) {
    e.preventDefault();
    const item = saleForm.item.trim();
    const amount = parseFloat(saleForm.amount);
    if (!item) {
      alert("Enter the item or service sold.");
      return;
    }
    if (!saleForm.amount || Number.isNaN(amount) || amount <= 0) {
      alert("Enter a valid amount.");
      return;
    }

    let customerId = "";
    if (customerMode === "walkin") {
      customerId = "walk-in";
    } else if (customerMode === "crm") {
      if (!selectedCustomer) {
        alert("Select a customer from your list, or choose Walk-in / New contact.");
        return;
      }
      customerId = selectedCustomer.id;
    } else if (customerMode === "new") {
      const name = newContactName.trim();
      const phone = newContactPhone.trim();
      if (!name || !phone) {
        alert("Enter name and phone for the new contact.");
        return;
      }
    }

    setSaving(true);
    try {
      if (customerMode === "new") {
        const created = await customersApi.create({
          name: newContactName.trim(),
          phone_number: newContactPhone.trim(),
          notes: "Added via Sales (web)",
        });
        customerId = created.id;
      }

      const sendReceipt = customerMode === "walkin" ? false : saleForm.send_receipt;

      await salesApi.create({
        customer_id: customerId,
        item,
        amount,
        payment_method: saleForm.is_credit ? undefined : saleForm.payment_method,
        send_receipt: sendReceipt,
        is_credit: saleForm.is_credit,
        due_date: saleForm.is_credit && saleForm.due_date ? saleForm.due_date : undefined,
      });
      setShowAdd(false);
      resetSaleModal();
      await load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to record sale";
      alert(msg);
    } finally {
      setSaving(false);
    }
  }

  async function handleExpenseAdd(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await expensesApi.create({ ...expForm, amount: parseFloat(expForm.amount) });
      setShowAdd(false);
      await load();
    } finally {
      setSaving(false);
    }
  }

  async function handleMarkPaid(sale: Sale) {
    const method =
      window.prompt("Payment method used?", sale.payment_method || "Cash") || "Cash";
    setMarkingPaidId(sale.id);
    try {
      await salesApi.markPaid(sale.id, method);
      await load();
    } catch {
      alert("Could not mark as paid");
    } finally {
      setMarkingPaidId(null);
    }
  }

  function exportCSV() {
    const rows =
      tab === "sales"
        ? [
            ["Customer", "Item", "Amount", "Method", "Date"],
            ...filteredSales.map((s) => [
              s.customer_name,
              s.item,
              s.amount,
              s.payment_method,
              formatDate(s.created_at),
            ]),
          ]
        : [
            ["Category", "Amount", "Description", "Date"],
            ...filteredExpenses.map((e) => [
              e.category,
              e.amount,
              e.description || "",
              formatDate(e.created_at),
            ]),
          ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })),
      download: `${tab}.csv`,
    });
    a.click();
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Sales & Expenses</h1>
          <p className="text-slate-500 text-sm mt-1">Track revenue and spending — same flows as the mobile app</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={exportCSV}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
          >
            <Download size={14} /> Export
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700"
          >
            <Plus size={15} /> {tab === "sales" ? "Add Sale" : "Add Expense"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
        <div
          className={`rounded-xl border p-5 ${
            netProfit >= 0 ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"
          }`}
        >
          <p className="text-sm font-medium text-slate-600 mb-2">Net Profit</p>
          <p className={`text-2xl font-bold ${netProfit >= 0 ? "text-green-700" : "text-red-700"}`}>
            {netProfit >= 0 ? "+" : ""}
            {formatCurrency(netProfit)}
          </p>
          <p className="text-xs text-slate-500 mt-1">{range}</p>
        </div>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex gap-1">
          {(["sales", "expenses"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${
                tab === t
                  ? "bg-indigo-600 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {t === "sales" ? `Sales (${filteredSales.length})` : `Expenses (${filteredExpenses.length})`}
            </button>
          ))}
        </div>
        <div className="relative">
          <select
            value={range}
            onChange={(e) => setRange(e.target.value as DateRange)}
            className="appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-slate-700"
          >
            {(["Today", "This Week", "This Month", "All Time"] as DateRange[]).map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <ChevronDown
            size={13}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
          />
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          {tab === "sales" ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {["Customer", "Item", "Amount", "Method", "Credit", "Date", "Actions"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading
                  ? Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 7 }).map((_, j) => (
                          <td key={j} className="px-4 py-3">
                            <div className="h-4 bg-slate-100 rounded animate-pulse" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : filteredSales.map((s) => {
                      const isWalkIn = s.customer_id === "walk-in";
                      const canResend =
                        !isWalkIn && (!s.is_credit || Boolean(s.paid_date));
                      const showMarkPaid = s.is_credit && !s.paid_date;
                      return (
                        <tr key={s.id} className="hover:bg-slate-50">
                          <td className="px-4 py-3">
                            <p className="font-medium text-slate-800">{s.customer_name}</p>
                            <p className="text-xs text-slate-400">{isWalkIn ? "Walk-in" : s.customer_phone}</p>
                          </td>
                          <td className="px-4 py-3 text-slate-700">{s.item}</td>
                          <td className="px-4 py-3 font-semibold text-slate-900">
                            {formatCurrency(s.amount)}
                          </td>
                          <td className="px-4 py-3 text-slate-600 text-xs">
                            {s.payment_method || (s.is_credit ? "—" : "—")}
                          </td>
                          <td className="px-4 py-3">
                            {s.is_credit && (
                              <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                                {s.paid_date ? "Paid" : "Credit"}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-400">{formatDate(s.created_at)}</td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1">
                              {canResend && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    api
                                      .post(`/sales/${s.id}/resend-receipt`, {})
                                      .then(() => alert("Receipt sent!"))
                                      .catch(() => alert("Failed to send receipt"))
                                  }
                                  className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-100 hover:text-indigo-600 transition-colors"
                                  title="Resend receipt"
                                >
                                  <Send size={13} />
                                </button>
                              )}
                              {showMarkPaid && (
                                <button
                                  type="button"
                                  onClick={() => handleMarkPaid(s)}
                                  disabled={markingPaidId === s.id}
                                  className="p-1.5 rounded-lg text-slate-400 hover:bg-green-100 hover:text-green-700 transition-colors disabled:opacity-50"
                                  title="Mark credit as paid"
                                >
                                  {markingPaidId === s.id ? (
                                    <Loader2 size={13} className="animate-spin" />
                                  ) : (
                                    <CheckCircle2 size={13} />
                                  )}
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
              </tbody>
            </table>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {["Category", "Amount", "Description", "Date", ""].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading
                  ? Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 5 }).map((_, j) => (
                          <td key={j} className="px-4 py-3">
                            <div className="h-4 bg-slate-100 rounded animate-pulse" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : filteredExpenses.map((exp) => (
                      <tr key={exp.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3">
                          <span className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full font-medium">
                            {exp.category}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-semibold text-red-600">{formatCurrency(exp.amount)}</td>
                        <td className="px-4 py-3 text-slate-600">{exp.description || "—"}</td>
                        <td className="px-4 py-3 text-xs text-slate-400">{formatDate(exp.created_at)}</td>
                        <td className="px-4 py-3">
                          <button
                            onClick={async () => {
                              await expensesApi.delete(exp.id);
                              await load();
                            }}
                            className="text-slate-400 hover:text-red-500 transition-colors"
                          >
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

      {showAdd && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg my-8">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">{tab === "sales" ? "Add Sale" : "Add Expense"}</h3>
              <button type="button" onClick={() => setShowAdd(false)} aria-label="Close">
                <X size={20} className="text-slate-400" />
              </button>
            </div>
            {tab === "sales" ? (
              <form onSubmit={handleSaleAdd} className="p-6 space-y-4 max-h-[calc(100vh-8rem)] overflow-y-auto">
                <div>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Customer</p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setCustomerMode("walkin");
                        setSelectedCustomer(null);
                      }}
                      className={cn(
                        "flex items-center gap-2 px-3 py-2 rounded-xl border text-left text-sm transition-colors",
                        customerMode === "walkin"
                          ? "border-indigo-600 bg-indigo-50 text-indigo-900"
                          : "border-slate-200 hover:bg-slate-50"
                      )}
                    >
                      <Footprints size={16} className="text-emerald-600 shrink-0" />
                      <span className="font-medium">Walk-in</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setCustomerMode("crm")}
                      className={cn(
                        "flex items-center gap-2 px-3 py-2 rounded-xl border text-left text-sm transition-colors",
                        customerMode === "crm"
                          ? "border-indigo-600 bg-indigo-50 text-indigo-900"
                          : "border-slate-200 hover:bg-slate-50"
                      )}
                    >
                      <User size={16} className="text-indigo-600 shrink-0" />
                      <span className="font-medium">CRM contact</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setCustomerMode("new");
                        setSelectedCustomer(null);
                      }}
                      className={cn(
                        "flex items-center gap-2 px-3 py-2 rounded-xl border text-left text-sm transition-colors",
                        customerMode === "new"
                          ? "border-indigo-600 bg-indigo-50 text-indigo-900"
                          : "border-slate-200 hover:bg-slate-50"
                      )}
                    >
                      <UserPlus size={16} className="text-violet-600 shrink-0" />
                      <span className="font-medium">New contact</span>
                    </button>
                  </div>
                  <p className="text-xs text-slate-500 mt-2">
                    Walk-in: quick sale with no WhatsApp receipt. CRM: pick an existing customer. New: create a contact
                    then record the sale.
                  </p>
                </div>

                {customerMode === "crm" && (
                  <div className="space-y-2">
                    <div className="relative">
                      <Search
                        size={14}
                        className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"
                      />
                      <input
                        value={customerSearch}
                        onChange={(e) => setCustomerSearch(e.target.value)}
                        placeholder="Search customers…"
                        className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg"
                      />
                    </div>
                    <div className="max-h-36 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100">
                      {filteredCustomersPick.length === 0 ? (
                        <p className="text-xs text-slate-400 p-3">No matches</p>
                      ) : (
                        filteredCustomersPick.slice(0, 50).map((c) => (
                          <button
                            key={c.id}
                            type="button"
                            onClick={() => setSelectedCustomer(c)}
                            className={cn(
                              "w-full text-left px-3 py-2 text-sm hover:bg-slate-50",
                              selectedCustomer?.id === c.id && "bg-indigo-50"
                            )}
                          >
                            <span className="font-medium text-slate-800">{c.name}</span>
                            <span className="block text-xs text-slate-500 font-mono">{c.phone_number}</span>
                          </button>
                        ))
                      )}
                    </div>
                    {selectedCustomer && (
                      <p className="text-xs text-indigo-700">
                        Selected: <strong>{selectedCustomer.name}</strong>
                      </p>
                    )}
                  </div>
                )}

                {customerMode === "new" && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <FField
                      label="Contact name *"
                      value={newContactName}
                      onChange={setNewContactName}
                      placeholder="Jane Doe"
                      required
                    />
                    <FField
                      label="Phone *"
                      value={newContactPhone}
                      onChange={setNewContactPhone}
                      placeholder="+254…"
                      required
                    />
                  </div>
                )}

                <FField
                  label="Item / service *"
                  value={saleForm.item}
                  onChange={(v) => setSaleForm((f) => ({ ...f, item: v }))}
                  placeholder="e.g. Chicken burger"
                  required
                />
                <FField
                  label="Amount *"
                  type="number"
                  step="any"
                  value={saleForm.amount}
                  onChange={(v) => setSaleForm((f) => ({ ...f, amount: v }))}
                  placeholder="0"
                  required
                />

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={saleForm.is_credit}
                    onChange={(e) => setSaleForm((f) => ({ ...f, is_credit: e.target.checked }))}
                    className="rounded border-slate-300"
                  />
                  <span className="text-sm text-slate-700">Credit sale (pay later)</span>
                </label>
                {saleForm.is_credit && (
                  <FField
                    label="Due date"
                    type="date"
                    value={saleForm.due_date}
                    onChange={(v) => setSaleForm((f) => ({ ...f, due_date: v }))}
                  />
                )}

                {!saleForm.is_credit && (
                  <SelectField
                    label="Payment method"
                    value={saleForm.payment_method}
                    onChange={(v) => setSaleForm((f) => ({ ...f, payment_method: v }))}
                    options={SALE_PAYMENT_METHODS}
                  />
                )}

                {customerMode !== "walkin" && (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={saleForm.send_receipt}
                      onChange={(e) => setSaleForm((f) => ({ ...f, send_receipt: e.target.checked }))}
                      className="rounded border-slate-300"
                    />
                    <span className="text-sm text-slate-700">Send WhatsApp receipt</span>
                  </label>
                )}

                <button
                  type="submit"
                  disabled={saving}
                  className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm"
                >
                  {saving && <Loader2 size={15} className="animate-spin" />} Record sale
                </button>
              </form>
            ) : (
              <form onSubmit={handleExpenseAdd} className="p-6 space-y-4">
                <SelectField
                  label="Category *"
                  value={expForm.category}
                  onChange={(v) => setExpForm((f) => ({ ...f, category: v }))}
                  options={EXPENSE_CATEGORIES}
                />
                <FField
                  label="Amount *"
                  type="number"
                  value={expForm.amount}
                  onChange={(v) => setExpForm((f) => ({ ...f, amount: v }))}
                  placeholder="1000"
                  required
                />
                <FField
                  label="Description"
                  value={expForm.description}
                  onChange={(v) => setExpForm((f) => ({ ...f, description: v }))}
                  placeholder="Optional note"
                />
                <button
                  type="submit"
                  disabled={saving}
                  className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm"
                >
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

function FField({
  label,
  value,
  onChange,
  placeholder,
  required,
  type = "text",
  step,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
  type?: string;
  step?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <input
        type={type}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
      />
    </div>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          {options.map((o) => (
            <option key={o}>
              {o}
            </option>
          ))}
        </select>
        <ChevronDown
          size={13}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
        />
      </div>
    </div>
  );
}
