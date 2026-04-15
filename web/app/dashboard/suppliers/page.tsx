"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { api, customersApi, Customer } from "@/lib/api";
import { formatCurrency, timeAgo, cn } from "@/lib/utils";
import {
  Truck,
  Plus,
  RefreshCw,
  Loader2,
  Sparkles,
  X,
  Star,
  MessageSquare,
  Search,
  ChevronDown,
  ChevronUp,
  ArrowLeft,
} from "lucide-react";

const PRESET_CATEGORIES = [
  "Electronics",
  "Clothing",
  "Food & Beverage",
  "Beauty & Health",
  "Home & Garden",
  "Automotive",
  "Raw Materials",
  "Packaging",
  "Stationery",
  "Services",
  "Agriculture",
  "Construction",
  "Pharmacy",
  "Furniture",
  "Printing",
  "Other",
];

function contactId(c: { id?: string; _id?: string }) {
  return c.id || c._id || "";
}

interface SupplierRow {
  id?: string;
  _id?: string;
  name: string;
  phone_number: string;
  email?: string;
  supplier_category?: string;
  payment_terms?: string;
  lead_time?: string;
  rating?: number;
  total_spent?: number;
  last_contacted?: string;
}

interface RestockSuggestion {
  type: string;
  product_name: string;
  current_stock: number;
  monthly_sales?: number;
  suggested_action: string;
  priority: string;
}

interface SupplierInsights {
  potential_suppliers: SupplierRow[];
  restock_suggestions: RestockSuggestion[];
}

export default function SuppliersPage() {
  const router = useRouter();
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [insights, setInsights] = useState<SupplierInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"list" | "add">("list");

  const [allCustomers, setAllCustomers] = useState<Customer[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [addingIds, setAddingIds] = useState<string[]>([]);

  const [categoryTarget, setCategoryTarget] = useState<SupplierRow | null>(null);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [customCategory, setCustomCategory] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editCategory, setEditCategory] = useState("");
  const [editCustomCategory, setEditCustomCategory] = useState("");
  const [showEditCustomInput, setShowEditCustomInput] = useState(false);
  const [editPaymentTerms, setEditPaymentTerms] = useState("");
  const [editLeadTime, setEditLeadTime] = useState("");
  const [editRating, setEditRating] = useState(0);
  const [savingId, setSavingId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [sups, ins] = await Promise.all([
        api.get<SupplierRow[]>("/suppliers").catch(() => []),
        api.get<SupplierInsights>("/suppliers/insights").catch(() => null),
      ]);
      const normalized = (sups || []).map((s) => ({
        ...s,
        id: s.id || s._id,
      }));
      setSuppliers(normalized);
      if (ins) {
        setInsights({
          potential_suppliers: (ins.potential_suppliers || []).map((p) => ({
            ...p,
            id: p.id || p._id,
          })),
          restock_suggestions: ins.restock_suggestions || [],
        });
      } else setInsights(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const potentialSuppliers = insights?.potential_suppliers ?? [];
  const restockSuggestions = insights?.restock_suggestions ?? [];

  async function fetchAllCustomers() {
    setLoading(true);
    try {
      const list = await customersApi.list();
      const supplierIds = new Set(suppliers.map((s) => contactId(s)));
      setAllCustomers(list.filter((c) => !supplierIds.has(c.id)));
    } catch {
      setAllCustomers([]);
    } finally {
      setLoading(false);
    }
  }

  function startAddMode() {
    setViewMode("add");
    setSearchQuery("");
    fetchAllCustomers();
  }

  function openCategoryPicker(customer: SupplierRow) {
    setCategoryTarget(customer);
    setSelectedCategory("");
    setCustomCategory("");
    setShowCustomInput(false);
  }

  async function tagThenUpdate(customer: SupplierRow, category?: string) {
    const id = contactId(customer);
    if (!id) return;
    setAddingIds((prev) => [...prev, id]);
    try {
      await api.post(`/suppliers/${id}/tag`, {});
      if (category) await api.put(`/suppliers/${id}`, { supplier_category: category });
      setCategoryTarget(null);
      setAllCustomers((prev) => prev.filter((c) => c.id !== id));
      await load();
    } catch {
      alert("Failed to add supplier");
    } finally {
      setAddingIds((prev) => prev.filter((pid) => pid !== id));
    }
  }

  function handleConfirmCategory() {
    if (!categoryTarget) return;
    const finalCategory = showCustomInput ? customCategory.trim() : selectedCategory;
    tagThenUpdate(categoryTarget, finalCategory || undefined);
  }

  async function handleRemove(supplier: SupplierRow) {
    const id = contactId(supplier);
    if (!id) return;
    if (!confirm(`Remove ${supplier.name} as a supplier? Their contact will remain.`)) return;
    try {
      await api.delete(`/suppliers/${id}`);
      if (expandedId === id) setExpandedId(null);
      await load();
    } catch {
      alert("Failed to remove supplier");
    }
  }

  function handleOpenExpand(supplier: SupplierRow) {
    const id = contactId(supplier);
    if (!id) return;
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    const cat = supplier.supplier_category || "";
    const isPreset = PRESET_CATEGORIES.includes(cat);
    setEditCategory(isPreset ? cat : "");
    setEditCustomCategory(!isPreset && cat ? cat : "");
    setShowEditCustomInput(!isPreset && !!cat);
    setEditPaymentTerms(supplier.payment_terms || "");
    setEditLeadTime(supplier.lead_time || "");
    setEditRating(supplier.rating || 0);
  }

  async function handleSaveDetails(supplier: SupplierRow) {
    const id = contactId(supplier);
    if (!id) return;
    const finalCategory = showEditCustomInput ? editCustomCategory.trim() : editCategory;
    setSavingId(id);
    try {
      const body: Record<string, unknown> = {};
      if (finalCategory) body.supplier_category = finalCategory;
      if (editPaymentTerms.trim()) body.payment_terms = editPaymentTerms.trim();
      if (editLeadTime.trim()) body.lead_time = editLeadTime.trim();
      if (editRating > 0) body.rating = editRating;
      await api.put(`/suppliers/${id}`, body);
      setSuppliers((prev) =>
        prev.map((s) =>
          contactId(s) === id
            ? {
                ...s,
                supplier_category: (finalCategory || s.supplier_category) as string | undefined,
                payment_terms: editPaymentTerms.trim(),
                lead_time: editLeadTime.trim(),
                rating: editRating,
              }
            : s
        )
      );
      setExpandedId(null);
    } catch {
      alert("Failed to save details");
    } finally {
      setSavingId(null);
    }
  }

  function openMessages(supplier: SupplierRow) {
    const id = contactId(supplier);
    if (!id) return;
    router.push(`/dashboard/messages?customer=${encodeURIComponent(id)}`);
  }

  const filteredCustomers = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return allCustomers.filter(
      (c) =>
        !q || c.name.toLowerCase().includes(q) || c.phone_number.includes(q)
    );
  }, [allCustomers, searchQuery]);

  function renderStars(rating: number, onPick?: (r: number) => void) {
    return (
      <div className="flex items-center gap-0.5">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            disabled={!onPick}
            onClick={() => onPick?.(star)}
            className={cn(
              "p-0.5 rounded transition-colors",
              onPick && "hover:bg-amber-50 cursor-pointer",
              !onPick && "cursor-default"
            )}
          >
            <Star
              size={18}
              className={cn(
                star <= rating ? "text-amber-400 fill-amber-400" : "text-slate-300"
              )}
            />
          </button>
        ))}
      </div>
    );
  }

  const categoryPickerModal =
    categoryTarget && (
      <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-4">
        <div className="bg-white rounded-t-2xl sm:rounded-2xl w-full max-w-md shadow-xl max-h-[90vh] flex flex-col">
          <div className="p-5 border-b border-slate-100">
            <h3 className="text-lg font-semibold text-slate-900">Choose a category</h3>
            <p className="text-sm text-slate-500 mt-0.5">for {categoryTarget.name}</p>
          </div>
          <div className="p-4 overflow-y-auto flex-1">
            <div className="flex flex-wrap gap-2">
              {PRESET_CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => {
                    setSelectedCategory(cat);
                    setShowCustomInput(false);
                  }}
                  className={cn(
                    "px-3 py-1.5 rounded-full text-sm border transition-colors",
                    selectedCategory === cat && !showCustomInput
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "bg-slate-50 text-slate-700 border-slate-200 hover:border-indigo-300"
                  )}
                >
                  {cat}
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  setShowCustomInput(true);
                  setSelectedCategory("");
                }}
                className={cn(
                  "px-3 py-1.5 rounded-full text-sm border transition-colors",
                  showCustomInput
                    ? "bg-indigo-600 text-white border-indigo-600"
                    : "bg-slate-50 text-slate-700 border-slate-200 hover:border-indigo-300"
                )}
              >
                Custom
              </button>
            </div>
            {showCustomInput && (
              <input
                className="mt-3 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="e.g. Spare parts, Fabrics…"
                value={customCategory}
                onChange={(e) => setCustomCategory(e.target.value)}
              />
            )}
          </div>
          <div className="p-4 border-t border-slate-100 flex gap-2">
            <button
              type="button"
              onClick={() => setCategoryTarget(null)}
              className="px-4 py-2.5 rounded-lg border border-slate-200 text-slate-600 text-sm font-medium hover:bg-slate-50"
            >
              Skip
            </button>
            <button
              type="button"
              onClick={handleConfirmCategory}
              disabled={addingIds.includes(contactId(categoryTarget))}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50"
            >
              {addingIds.includes(contactId(categoryTarget)) ? (
                <Loader2 className="animate-spin" size={16} />
              ) : null}
              Add supplier
            </button>
          </div>
        </div>
      </div>
    );

  if (viewMode === "add") {
    return (
      <div className="p-6 max-w-3xl mx-auto space-y-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setViewMode("list")}
            className="p-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
            aria-label="Back"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Add supplier</h1>
            <p className="text-slate-500 text-sm">Pick a contact and set a category</p>
          </div>
        </div>

        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search contacts…"
            className="w-full pl-9 pr-3 py-2.5 text-sm border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100 min-h-[240px]">
          {loading ? (
            <div className="flex justify-center py-16">
              <Loader2 className="animate-spin text-indigo-600" size={28} />
            </div>
          ) : filteredCustomers.length === 0 ? (
            <p className="text-center text-slate-400 text-sm py-12">No contacts found</p>
          ) : (
            filteredCustomers.map((c) => (
              <div key={c.id} className="flex items-center justify-between px-4 py-3 gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-slate-800 truncate">{c.name}</p>
                  <p className="text-xs text-slate-500 font-mono">{c.phone_number}</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    openCategoryPicker({
                      id: c.id,
                      name: c.name,
                      phone_number: c.phone_number,
                    })
                  }
                  disabled={addingIds.includes(c.id)}
                  className="shrink-0 px-3 py-1.5 text-sm font-semibold rounded-lg border border-indigo-600 text-indigo-600 hover:bg-indigo-50 disabled:opacity-50"
                >
                  {addingIds.includes(c.id) ? <Loader2 className="animate-spin" size={14} /> : "Add"}
                </button>
              </div>
            ))
          )}
        </div>
        {categoryPickerModal}
      </div>
    );
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Smart sourcing</h1>
          <p className="text-slate-500 text-sm mt-1">Suppliers, restock alerts, and AI suggestions</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={load}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
          <button
            type="button"
            onClick={startAddMode}
            className="flex items-center gap-2 px-3 py-2 text-sm font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700"
          >
            <Plus size={16} /> Add supplier
          </button>
        </div>
      </div>

      {loading && suppliers.length === 0 && !insights ? (
        <div className="flex justify-center py-20">
          <Loader2 className="animate-spin text-indigo-600" size={28} />
        </div>
      ) : (
        <>
          {restockSuggestions.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                Restock alerts
              </h2>
              <div className="space-y-2">
                {restockSuggestions.map((item, index) => (
                  <div
                    key={`${item.product_name}-${index}`}
                    className={cn(
                      "rounded-xl border p-4 bg-white",
                      item.priority === "High"
                        ? "border-l-4 border-l-red-400 border-slate-200"
                        : "border-l-4 border-l-amber-400 border-slate-200"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span
                        className={cn(
                          "text-xs font-bold uppercase",
                          item.priority === "High" ? "text-red-600" : "text-amber-600"
                        )}
                      >
                        {item.priority} priority
                      </span>
                    </div>
                    <p className="text-slate-900 font-medium">{item.product_name}</p>
                    <p className="text-sm text-slate-600 mt-1">
                      Stock: {item.current_stock}
                      {item.monthly_sales != null ? ` · ${item.monthly_sales} sold (30d)` : null}
                    </p>
                    <p className="text-sm text-indigo-600 font-medium mt-2">{item.suggested_action}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {potentialSuppliers.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                Potential suppliers
              </h2>
              <div className="space-y-2">
                {potentialSuppliers.map((p) => {
                  const pid = contactId(p);
                  return (
                    <div
                      key={pid}
                      className="flex items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3"
                    >
                      <div className="min-w-0">
                        <p className="font-semibold text-slate-900">{p.name}</p>
                        <p className="text-xs text-slate-500 font-mono">{p.phone_number}</p>
                        <p className="text-xs text-emerald-700 mt-1">AI detected supplier signals in chat</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => openCategoryPicker(p)}
                        disabled={!pid || addingIds.includes(pid)}
                        className="shrink-0 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50"
                      >
                        {addingIds.includes(pid) ? (
                          <Loader2 className="animate-spin" size={14} />
                        ) : (
                          "Add"
                        )}
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section>
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              My suppliers ({suppliers.length})
            </h2>
            {suppliers.length === 0 ? (
              <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
                <Truck size={36} className="text-slate-300 mx-auto mb-3" />
                <p className="text-slate-600 font-medium">No suppliers yet</p>
                <p className="text-slate-400 text-sm mt-1">
                  Add suppliers from your contacts or use suggestions above.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {suppliers.map((s) => {
                  const sid = contactId(s);
                  const isOpen = expandedId === sid;
                  const isSaving = savingId === sid;
                  const cat = s.supplier_category;
                  const displayCat = cat && cat !== "Other" ? cat : null;

                  return (
                    <div
                      key={sid}
                      className="rounded-xl border border-slate-200 bg-white overflow-hidden"
                    >
                      <div className="flex items-stretch gap-2">
                        <button
                          type="button"
                          onClick={() => handleOpenExpand(s)}
                          className="flex-1 flex items-start gap-3 p-4 text-left min-w-0 hover:bg-slate-50/80"
                        >
                          <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
                            <Truck size={20} className="text-indigo-600" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="font-semibold text-slate-900">{s.name}</p>
                            <p className="text-sm text-slate-500 font-mono">{s.phone_number}</p>
                            <div className="flex flex-wrap items-center gap-2 mt-2">
                              {displayCat ? (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">
                                  {displayCat}
                                </span>
                              ) : (
                                <span className="text-xs text-indigo-600 italic">Tap to set category</span>
                              )}
                              {!!s.rating && s.rating > 0 && renderStars(s.rating)}
                            </div>
                            {s.payment_terms ? (
                              <p className="text-xs text-slate-500 mt-1">💳 {s.payment_terms}</p>
                            ) : null}
                            {s.lead_time ? (
                              <p className="text-xs text-slate-500">⏱ {s.lead_time}</p>
                            ) : null}
                            {(s.total_spent != null && s.total_spent > 0) || s.last_contacted ? (
                              <div className="flex flex-wrap gap-3 mt-2 text-xs text-slate-400">
                                {s.total_spent != null && s.total_spent > 0 ? (
                                  <span>Spent {formatCurrency(s.total_spent)}</span>
                                ) : null}
                                {s.last_contacted ? (
                                  <span>Last contact {timeAgo(s.last_contacted)}</span>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                          <div className="shrink-0 pt-1 text-slate-400">
                            {isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                          </div>
                        </button>
                        <div className="flex flex-col justify-center gap-1 pr-3 py-3 border-l border-slate-100">
                          <button
                            type="button"
                            onClick={() => openMessages(s)}
                            className="p-2 rounded-lg text-slate-500 hover:bg-emerald-50 hover:text-emerald-600"
                            title="Open messages"
                          >
                            <MessageSquare size={18} />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRemove(s)}
                            className="p-2 rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600"
                            title="Remove supplier"
                          >
                            <X size={18} />
                          </button>
                        </div>
                      </div>

                      {isOpen && (
                        <div className="px-4 pb-4 pt-0 border-t border-slate-100 space-y-3">
                          <div>
                            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide mb-2">
                              Category
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {PRESET_CATEGORIES.map((c) => (
                                <button
                                  key={c}
                                  type="button"
                                  onClick={() => {
                                    setEditCategory(c);
                                    setShowEditCustomInput(false);
                                  }}
                                  className={cn(
                                    "px-2.5 py-1 rounded-full text-xs border",
                                    editCategory === c && !showEditCustomInput
                                      ? "bg-indigo-600 text-white border-indigo-600"
                                      : "bg-slate-50 text-slate-700 border-slate-200"
                                  )}
                                >
                                  {c}
                                </button>
                              ))}
                              <button
                                type="button"
                                onClick={() => {
                                  setShowEditCustomInput(true);
                                  setEditCategory("");
                                }}
                                className={cn(
                                  "px-2.5 py-1 rounded-full text-xs border",
                                  showEditCustomInput
                                    ? "bg-indigo-600 text-white border-indigo-600"
                                    : "bg-slate-50 text-slate-700 border-slate-200"
                                )}
                              >
                                Custom
                              </button>
                            </div>
                            {showEditCustomInput && (
                              <input
                                className="mt-2 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                                placeholder="Type your category…"
                                value={editCustomCategory}
                                onChange={(e) => setEditCustomCategory(e.target.value)}
                              />
                            )}
                          </div>
                          <div>
                            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide mb-1">
                              Payment terms
                            </p>
                            <input
                              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                              placeholder="e.g. Net 30, COD…"
                              value={editPaymentTerms}
                              onChange={(e) => setEditPaymentTerms(e.target.value)}
                            />
                          </div>
                          <div>
                            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide mb-1">
                              Lead time
                            </p>
                            <input
                              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                              placeholder="e.g. 3–5 days, 2 weeks…"
                              value={editLeadTime}
                              onChange={(e) => setEditLeadTime(e.target.value)}
                            />
                          </div>
                          <div>
                            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide mb-1">
                              Rating
                            </p>
                            {renderStars(editRating, setEditRating)}
                          </div>
                          <div className="flex gap-2 pt-1">
                            <button
                              type="button"
                              onClick={() => setExpandedId(null)}
                              className="px-4 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSaveDetails(s)}
                              disabled={isSaving}
                              className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50"
                            >
                              {isSaving ? <Loader2 className="animate-spin" size={16} /> : null}
                              Save
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {!loading &&
            suppliers.length === 0 &&
            potentialSuppliers.length === 0 &&
            restockSuggestions.length === 0 && (
              <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
                <Sparkles size={36} className="text-slate-300 mx-auto mb-3" />
                <p className="text-slate-600 font-medium">No supplier data yet</p>
                <p className="text-slate-400 text-sm mt-1">
                  Chat with contacts and add products to unlock AI insights and restock alerts.
                </p>
              </div>
            )}
        </>
      )}

      {categoryPickerModal}
    </div>
  );
}
