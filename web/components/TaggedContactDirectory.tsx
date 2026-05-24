"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, customersApi, Customer } from "@/lib/api";
import { timeAgo, cn } from "@/lib/utils";
import {
  Plus,
  RefreshCw,
  Loader2,
  X,
  Star,
  MessageSquare,
  Search,
  ChevronDown,
  ChevronUp,
  UserPlus,
  Mail,
  LucideIcon,
} from "lucide-react";
import ContactDocumentsPanel, { DocTypeOption } from "@/components/ContactDocumentsPanel";

type MainTab = "list" | "add";

export interface DirectoryConfig {
  apiPrefix: string;
  title: string;
  subtitle: string;
  entityLabel: string;
  icon: LucideIcon;
  presetTypes: string[];
  typeField: string;
  typeLabel: string;
  /** Optional pipeline stages (investors) */
  stages?: string[];
  stageField?: string;
  stageLabel?: string;
  /** Extra editable fields shown in expanded row */
  extraFields: Array<{
    key: string;
    label: string;
    placeholder?: string;
    multiline?: boolean;
  }>;
  /** Optional string-array field (e.g. focus_areas) */
  arrayField?: { key: string; label: string; placeholder?: string };
  /** Show star rating */
  showRating?: boolean;
  /** Document / contract types for upload */
  documentTypes?: DocTypeOption[];
  documentsLabel?: string;
}

interface ContactRow {
  id?: string;
  _id?: string;
  name: string;
  phone_number: string;
  email?: string;
  last_contacted?: string;
  [key: string]: unknown;
}

function contactId(c: { id?: string; _id?: string }) {
  return c.id || c._id || "";
}

export default function TaggedContactDirectory({ config }: { config: DirectoryConfig }) {
  const router = useRouter();
  const Icon = config.icon;

  const [rows, setRows] = useState<ContactRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<MainTab>("list");

  const [allCustomers, setAllCustomers] = useState<Customer[]>([]);
  const [loadingContacts, setLoadingContacts] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [manualName, setManualName] = useState("");
  const [manualPhone, setManualPhone] = useState("");
  const [manualEmail, setManualEmail] = useState("");
  const [manualType, setManualType] = useState("");
  const [manualSaving, setManualSaving] = useState(false);
  const [addingIds, setAddingIds] = useState<string[]>([]);

  const [typeTarget, setTypeTarget] = useState<ContactRow | null>(null);
  const [selectedType, setSelectedType] = useState("");
  const [customType, setCustomType] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editType, setEditType] = useState("");
  const [editCustomType, setEditCustomType] = useState("");
  const [showEditCustomInput, setShowEditCustomInput] = useState(false);
  const [editStage, setEditStage] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editExtras, setEditExtras] = useState<Record<string, string>>({});
  const [editArrayItems, setEditArrayItems] = useState<string[]>([]);
  const [arrayInput, setArrayInput] = useState("");
  const [editRating, setEditRating] = useState(0);
  const [savingId, setSavingId] = useState<string | null>(null);

  const [listQuery, setListQuery] = useState("");
  const [filterType, setFilterType] = useState("all");
  const [filterStage, setFilterStage] = useState("all");

  function normalize(rows: ContactRow[]) {
    return (rows || []).map((r) => ({ ...r, id: r.id || r._id }));
  }

  async function load() {
    setLoading(true);
    try {
      const data = await api.get<ContactRow[]>(config.apiPrefix).catch(() => []);
      setRows(normalize(data || []));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [config.apiPrefix]);

  useEffect(() => {
    if (activeTab !== "add") return;
    let cancelled = false;
    setLoadingContacts(true);
    (async () => {
      try {
        const list = await customersApi.list();
        if (cancelled) return;
        const taggedIds = new Set(rows.map((r) => contactId(r)));
        setAllCustomers(list.filter((c) => !taggedIds.has(c.id)));
      } catch {
        if (!cancelled) setAllCustomers([]);
      } finally {
        if (!cancelled) setLoadingContacts(false);
      }
    })();
    return () => { cancelled = true; };
  }, [activeTab, rows]);

  const filteredRows = useMemo(() => {
    let list = [...rows];
    const q = listQuery.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (r) =>
          r.name.toLowerCase().includes(q) ||
          r.phone_number.includes(q) ||
          (r.email && String(r.email).toLowerCase().includes(q)) ||
          String(r[config.typeField] || "").toLowerCase().includes(q)
      );
    }
    if (filterType !== "all") {
      list = list.filter((r) => (r[config.typeField] || "Other") === filterType);
    }
    if (config.stageField && filterStage !== "all") {
      list = list.filter((r) => (r[config.stageField!] || "") === filterStage);
    }
    return list.sort((a, b) => a.name.localeCompare(b.name));
  }, [rows, listQuery, filterType, filterStage, config.typeField, config.stageField]);

  async function handleManualAdd(e: React.FormEvent) {
    e.preventDefault();
    const name = manualName.trim();
    const phone = manualPhone.trim();
    if (!name || !phone) {
      alert("Name and phone are required.");
      return;
    }
    setManualSaving(true);
    try {
      const created = await customersApi.create({
        name,
        phone_number: phone,
        ...(manualEmail.trim() ? { email: manualEmail.trim() } : {}),
        notes: `Added from ${config.title} (manual)`,
      });
      const id = created.id;
      await api.post(`${config.apiPrefix}/${id}/tag`, {});
      if (manualType) {
        await api.put(`${config.apiPrefix}/${id}`, { [config.typeField]: manualType });
      }
      setManualName("");
      setManualPhone("");
      setManualEmail("");
      setManualType("");
      await load();
      setActiveTab("list");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : `Could not add ${config.entityLabel.toLowerCase()}`);
    } finally {
      setManualSaving(false);
    }
  }

  async function tagThenUpdate(contact: ContactRow, type?: string) {
    const id = contactId(contact);
    if (!id) return;
    setAddingIds((prev) => [...prev, id]);
    try {
      await api.post(`${config.apiPrefix}/${id}/tag`, {});
      if (type) await api.put(`${config.apiPrefix}/${id}`, { [config.typeField]: type });
      setTypeTarget(null);
      setAllCustomers((prev) => prev.filter((c) => c.id !== id));
      await load();
      setActiveTab("list");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to add ${config.entityLabel.toLowerCase()}`;
      alert(msg);
    } finally {
      setAddingIds((prev) => prev.filter((pid) => pid !== id));
    }
  }

  function handleConfirmType() {
    if (!typeTarget) return;
    const finalType = showCustomInput ? customType.trim() : selectedType;
    tagThenUpdate(typeTarget, finalType || undefined);
  }

  async function handleRemove(row: ContactRow) {
    const id = contactId(row);
    if (!id) return;
    if (!confirm(`Remove ${row.name} as a ${config.entityLabel.toLowerCase()}? Their contact will remain.`)) return;
    try {
      await api.delete(`${config.apiPrefix}/${id}`);
      if (expandedId === id) setExpandedId(null);
      await load();
    } catch {
      alert(`Failed to remove ${config.entityLabel.toLowerCase()}`);
    }
  }

  function handleOpenExpand(row: ContactRow) {
    const id = contactId(row);
    if (!id) return;
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    const t = String(row[config.typeField] || "");
    const isPreset = config.presetTypes.includes(t);
    setEditType(isPreset ? t : "");
    setEditCustomType(!isPreset && t ? t : "");
    setShowEditCustomInput(!isPreset && !!t);
    if (config.stageField) setEditStage(String(row[config.stageField] || config.stages?.[0] || ""));
    setEditEmail(String(row.email || ""));
    const extras: Record<string, string> = {};
    for (const f of config.extraFields) extras[f.key] = String(row[f.key] || "");
    setEditExtras(extras);
    if (config.arrayField) {
      const arr = row[config.arrayField.key];
      setEditArrayItems(Array.isArray(arr) ? [...arr] : []);
    }
    setArrayInput("");
    setEditRating(Number(row.rating) || 0);
  }

  async function handleSaveDetails(row: ContactRow) {
    const id = contactId(row);
    if (!id) return;
    const finalType = showEditCustomInput ? editCustomType.trim() : editType;
    setSavingId(id);
    try {
      const body: Record<string, unknown> = {};
      if (finalType) body[config.typeField] = finalType;
      if (config.stageField && editStage) body[config.stageField] = editStage;
      for (const f of config.extraFields) body[f.key] = editExtras[f.key]?.trim() || "";
      if (config.arrayField) {
        body[config.arrayField.key] = [...new Set(editArrayItems.map((s) => s.trim()).filter(Boolean))];
      }
      if (config.showRating) body.rating = editRating;
      await api.put(`${config.apiPrefix}/${id}`, body);
      const emailTrimmed = editEmail.trim();
      await customersApi.update(id, { email: emailTrimmed || undefined });
      setRows((prev) =>
        prev.map((r) => (contactId(r) === id ? { ...r, ...body, email: emailTrimmed || undefined } : r))
      );
      setExpandedId(null);
    } catch {
      alert("Failed to save details");
    } finally {
      setSavingId(null);
    }
  }

  function openMessages(row: ContactRow) {
    const id = contactId(row);
    if (!id) return;
    router.push(`/dashboard/messages?customer=${encodeURIComponent(id)}`);
  }

  function openEmail(row: ContactRow) {
    const email = String(row.email || "").trim();
    if (!email) {
      alert("Add an email address first (expand the row to edit).");
      return;
    }
    router.push(`/dashboard/email?compose=1&to=${encodeURIComponent(email)}`);
  }

  const filteredCustomers = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return allCustomers.filter(
      (c) =>
        !q ||
        c.name.toLowerCase().includes(q) ||
        c.phone_number.includes(q) ||
        (c.email || "").toLowerCase().includes(q)
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
            className={cn("p-0.5 rounded transition-colors", onPick && "hover:bg-amber-50 cursor-pointer", !onPick && "cursor-default")}
          >
            <Star size={18} className={cn(star <= rating ? "text-amber-400 fill-amber-400" : "text-slate-300")} />
          </button>
        ))}
      </div>
    );
  }

  const typePickerModal = typeTarget && (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-t-2xl sm:rounded-2xl w-full max-w-md shadow-xl max-h-[90vh] flex flex-col">
        <div className="p-5 border-b border-slate-100">
          <h3 className="text-lg font-semibold text-slate-900">Choose {config.typeLabel.toLowerCase()}</h3>
          <p className="text-sm text-slate-500 mt-0.5">for {typeTarget.name}</p>
        </div>
        <div className="p-4 overflow-y-auto flex-1">
          <div className="flex flex-wrap gap-2">
            {config.presetTypes.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => { setSelectedType(t); setShowCustomInput(false); }}
                className={cn(
                  "px-3 py-1.5 rounded-full text-sm border transition-colors",
                  selectedType === t && !showCustomInput
                    ? "bg-brand-dark text-white border-brand-dark"
                    : "bg-slate-50 text-slate-700 border-slate-200 hover:border-brand/50"
                )}
              >
                {t}
              </button>
            ))}
            <button
              type="button"
              onClick={() => { setShowCustomInput(true); setSelectedType(""); }}
              className={cn(
                "px-3 py-1.5 rounded-full text-sm border transition-colors",
                showCustomInput ? "bg-brand-dark text-white border-brand-dark" : "bg-slate-50 text-slate-700 border-slate-200 hover:border-brand/50"
              )}
            >
              Custom
            </button>
          </div>
          {showCustomInput && (
            <input
              className="mt-3 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand"
              placeholder="Custom type…"
              value={customType}
              onChange={(e) => setCustomType(e.target.value)}
            />
          )}
        </div>
        <div className="p-4 border-t border-slate-100 flex gap-2">
          <button type="button" onClick={() => setTypeTarget(null)} className="px-4 py-2.5 rounded-lg border border-slate-200 text-slate-600 text-sm font-medium hover:bg-slate-50">
            Skip
          </button>
          <button
            type="button"
            onClick={handleConfirmType}
            disabled={addingIds.includes(contactId(typeTarget))}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-brand-dark text-white text-sm font-semibold hover:bg-brand disabled:opacity-50"
          >
            {addingIds.includes(contactId(typeTarget)) ? <Loader2 className="animate-spin" size={16} /> : null}
            Add {config.entityLabel.toLowerCase()}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="p-6 w-full max-w-5xl mx-auto space-y-6">
      {typePickerModal}

      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{config.title}</h1>
          <p className="text-slate-500 text-sm mt-1">{config.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={load} className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
          <button type="button" onClick={() => setActiveTab("add")} className="flex items-center gap-2 px-3 py-2 text-sm font-semibold rounded-lg bg-brand-dark text-white hover:bg-brand">
            <Plus size={16} /> Add {config.entityLabel.toLowerCase()}
          </button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {([
          { id: "list" as MainTab, label: `My ${config.entityLabel.toLowerCase()}s` },
          { id: "add" as MainTab, label: `Add ${config.entityLabel.toLowerCase()}` },
        ]).map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-4 py-2 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap",
              activeTab === tab.id ? "bg-white border-b-2 border-brand-dark text-brand-dark" : "text-slate-500 hover:text-slate-800"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading && rows.length === 0 ? (
        <div className="flex justify-center py-20">
          <Loader2 className="animate-spin text-brand-dark" size={28} />
        </div>
      ) : activeTab === "list" ? (
        <section>
          {rows.length > 0 && (
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap mb-3">
              <div className="relative flex-1 min-w-[180px]">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input
                  value={listQuery}
                  onChange={(e) => setListQuery(e.target.value)}
                  placeholder="Search name, phone, email…"
                  className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand"
                />
              </div>
              <select value={filterType} onChange={(e) => setFilterType(e.target.value)} className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white text-slate-700 min-w-[140px]">
                <option value="all">All types</option>
                {config.presetTypes.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              {config.stages && config.stageField && (
                <select value={filterStage} onChange={(e) => setFilterStage(e.target.value)} className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white text-slate-700 min-w-[160px]">
                  <option value="all">All stages</option>
                  {config.stages.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              )}
            </div>
          )}

          {rows.length === 0 ? (
            <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
              <Icon size={36} className="text-slate-300 mx-auto mb-3" />
              <p className="text-slate-600 font-medium">No {config.entityLabel.toLowerCase()}s yet</p>
              <p className="text-slate-400 text-sm mt-1">Use the Add tab to create one manually or tag an existing contact.</p>
            </div>
          ) : filteredRows.length === 0 ? (
            <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
              <p className="text-slate-600 font-medium">No matches for your filters</p>
              <button type="button" onClick={() => { setListQuery(""); setFilterType("all"); setFilterStage("all"); }} className="mt-3 text-sm font-semibold text-brand-dark">
                Clear filters
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredRows.map((row) => {
                const rid = contactId(row);
                const isOpen = expandedId === rid;
                const isSaving = savingId === rid;
                const typeVal = String(row[config.typeField] || "");
                const displayType = typeVal && typeVal !== "Other" ? typeVal : null;
                const stageVal = config.stageField ? String(row[config.stageField] || "") : null;
                const arrayItems = config.arrayField ? (row[config.arrayField.key] as string[] | undefined) : undefined;

                return (
                  <div key={rid} className="rounded-xl border border-slate-200 bg-white overflow-hidden">
                    <div className="flex items-stretch gap-2">
                      <button type="button" onClick={() => handleOpenExpand(row)} className="flex-1 flex items-start gap-3 p-4 text-left min-w-0 hover:bg-slate-50/80">
                        <div className="w-10 h-10 rounded-full bg-brand/15 flex items-center justify-center shrink-0">
                          <Icon size={20} className="text-brand-dark" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold text-slate-900">{row.name}</p>
                          <p className="text-sm text-slate-500 font-mono">{row.phone_number}</p>
                          {row.email ? <p className="text-xs text-slate-400 truncate">{String(row.email)}</p> : null}
                          <div className="flex flex-wrap items-center gap-2 mt-2">
                            {displayType ? (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-brand/10 text-brand-dark font-medium">{displayType}</span>
                            ) : (
                              <span className="text-xs text-brand-dark italic">Tap to set type</span>
                            )}
                            {stageVal && (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 font-medium">{stageVal}</span>
                            )}
                            {config.showRating && !!row.rating && Number(row.rating) > 0 && renderStars(Number(row.rating))}
                          </div>
                          {config.extraFields.map((f) => {
                            const v = String(row[f.key] || "");
                            return v ? <p key={f.key} className="text-xs text-slate-500 mt-1">{f.label}: {v}</p> : null;
                          })}
                          {arrayItems && arrayItems.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1.5">
                              {arrayItems.slice(0, 4).map((item) => (
                                <span key={item} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{item}</span>
                              ))}
                              {arrayItems.length > 4 && <span className="text-[10px] text-slate-400">+{arrayItems.length - 4}</span>}
                            </div>
                          )}
                          {row.last_contacted && (
                            <p className="text-xs text-slate-400 mt-2">Last contact {timeAgo(row.last_contacted)}</p>
                          )}
                        </div>
                        <div className="shrink-0 pt-1 text-slate-400">
                          {isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </div>
                      </button>
                      <div className="flex flex-col gap-1 p-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => row.email && openEmail(row)}
                          disabled={!row.email}
                          className={cn(
                            "p-2 rounded-lg",
                            row.email ? "text-slate-500 hover:bg-slate-100" : "text-slate-300 cursor-not-allowed"
                          )}
                          title={row.email ? "Send email" : "No email on file"}
                        >
                          <Mail size={16} />
                        </button>
                        <button type="button" onClick={() => openMessages(row)} className="p-2 rounded-lg text-slate-500 hover:bg-slate-100" title="Message">
                          <MessageSquare size={16} />
                        </button>
                        <Link href={`/dashboard/customers/${rid}`} className="p-2 rounded-lg text-slate-500 hover:bg-slate-100" title="Profile">
                          <UserPlus size={16} />
                        </Link>
                      </div>
                    </div>

                    {isOpen && (
                      <div className="border-t border-slate-100 p-4 bg-slate-50/50 space-y-4">
                        <div>
                          <label className="text-xs font-semibold text-slate-500 uppercase">Email</label>
                          <input
                            type="email"
                            className="mt-2 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                            value={editEmail}
                            onChange={(e) => setEditEmail(e.target.value)}
                            placeholder="name@company.com"
                          />
                          {editEmail.trim() && (
                            <button
                              type="button"
                              onClick={() => openEmail({ ...row, email: editEmail.trim() })}
                              className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-brand-dark hover:text-brand"
                            >
                              <Mail size={13} /> Send email
                            </button>
                          )}
                        </div>

                        <div>
                          <label className="text-xs font-semibold text-slate-500 uppercase">{config.typeLabel}</label>
                          <div className="flex flex-wrap gap-2 mt-2">
                            {config.presetTypes.map((t) => (
                              <button
                                key={t}
                                type="button"
                                onClick={() => { setEditType(t); setShowEditCustomInput(false); }}
                                className={cn(
                                  "px-3 py-1 rounded-full text-xs border",
                                  editType === t && !showEditCustomInput ? "bg-brand-dark text-white border-brand-dark" : "bg-white border-slate-200 text-slate-600"
                                )}
                              >
                                {t}
                              </button>
                            ))}
                            <button type="button" onClick={() => setShowEditCustomInput(true)} className={cn("px-3 py-1 rounded-full text-xs border", showEditCustomInput ? "bg-brand-dark text-white" : "bg-white border-slate-200 text-slate-600")}>
                              Custom
                            </button>
                          </div>
                          {showEditCustomInput && (
                            <input className="mt-2 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm" value={editCustomType} onChange={(e) => setEditCustomType(e.target.value)} placeholder="Custom type…" />
                          )}
                        </div>

                        {config.stages && config.stageField && (
                          <div>
                            <label className="text-xs font-semibold text-slate-500 uppercase">{config.stageLabel || "Stage"}</label>
                            <select value={editStage} onChange={(e) => setEditStage(e.target.value)} className="mt-2 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white">
                              {config.stages.map((s) => <option key={s} value={s}>{s}</option>)}
                            </select>
                          </div>
                        )}

                        {config.extraFields.map((f) => (
                          <div key={f.key}>
                            <label className="text-xs font-semibold text-slate-500 uppercase">{f.label}</label>
                            {f.multiline ? (
                              <textarea
                                className="mt-2 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm min-h-[72px]"
                                value={editExtras[f.key] || ""}
                                onChange={(e) => setEditExtras((prev) => ({ ...prev, [f.key]: e.target.value }))}
                                placeholder={f.placeholder}
                              />
                            ) : (
                              <input
                                className="mt-2 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                                value={editExtras[f.key] || ""}
                                onChange={(e) => setEditExtras((prev) => ({ ...prev, [f.key]: e.target.value }))}
                                placeholder={f.placeholder}
                              />
                            )}
                          </div>
                        ))}

                        {config.arrayField && (
                          <div>
                            <label className="text-xs font-semibold text-slate-500 uppercase">{config.arrayField.label}</label>
                            <div className="flex flex-wrap gap-1 mt-2">
                              {editArrayItems.map((item) => (
                                <span key={item} className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-slate-200 text-slate-700">
                                  {item}
                                  <button type="button" onClick={() => setEditArrayItems((prev) => prev.filter((x) => x !== item))}><X size={12} /></button>
                                </span>
                              ))}
                            </div>
                            <div className="flex gap-2 mt-2">
                              <input
                                className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm"
                                value={arrayInput}
                                onChange={(e) => setArrayInput(e.target.value)}
                                placeholder={config.arrayField.placeholder}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    e.preventDefault();
                                    const t = arrayInput.trim();
                                    if (t && !editArrayItems.includes(t)) setEditArrayItems((prev) => [...prev, t]);
                                    setArrayInput("");
                                  }
                                }}
                              />
                              <button
                                type="button"
                                onClick={() => {
                                  const t = arrayInput.trim();
                                  if (t && !editArrayItems.includes(t)) setEditArrayItems((prev) => [...prev, t]);
                                  setArrayInput("");
                                }}
                                className="px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-white"
                              >
                                Add
                              </button>
                            </div>
                          </div>
                        )}

                        {config.showRating && (
                          <div>
                            <label className="text-xs font-semibold text-slate-500 uppercase">Rating</label>
                            <div className="mt-2">{renderStars(editRating, setEditRating)}</div>
                          </div>
                        )}

                        {config.documentTypes && config.documentTypes.length > 0 && (
                          <ContactDocumentsPanel
                            apiPrefix={config.apiPrefix}
                            customerId={rid}
                            documentTypes={config.documentTypes}
                            label={config.documentsLabel}
                          />
                        )}

                        <div className="flex gap-2 pt-2">
                          <button type="button" onClick={() => handleSaveDetails(row)} disabled={isSaving} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-dark text-white text-sm font-semibold hover:bg-brand disabled:opacity-50">
                            {isSaving ? <Loader2 className="animate-spin" size={14} /> : null}
                            Save
                          </button>
                          <button type="button" onClick={() => handleRemove(row)} className="px-4 py-2 rounded-lg border border-red-200 text-red-600 text-sm font-medium hover:bg-red-50">
                            Remove
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
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
            <h2 className="font-semibold text-slate-900">Add manually</h2>
            <form onSubmit={handleManualAdd} className="space-y-3">
              <input required className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm" placeholder="Name" value={manualName} onChange={(e) => setManualName(e.target.value)} />
              <input required className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm" placeholder="Phone number" value={manualPhone} onChange={(e) => setManualPhone(e.target.value)} />
              <input type="email" className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm" placeholder="Email (optional)" value={manualEmail} onChange={(e) => setManualEmail(e.target.value)} />
              <select className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white" value={manualType} onChange={(e) => setManualType(e.target.value)}>
                <option value="">Type (optional)</option>
                {config.presetTypes.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <button type="submit" disabled={manualSaving} className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-brand-dark text-white text-sm font-semibold hover:bg-brand disabled:opacity-50">
                {manualSaving ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />}
                Create {config.entityLabel.toLowerCase()}
              </button>
            </form>
          </section>

          <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
            <h2 className="font-semibold text-slate-900">Tag existing contact</h2>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search contacts by name, phone, or email…"
                className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand"
              />
            </div>
            {loadingContacts ? (
              <div className="flex justify-center py-8"><Loader2 className="animate-spin text-brand" size={24} /></div>
            ) : filteredCustomers.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-6">No contacts available to tag.</p>
            ) : (
              <div className="max-h-80 overflow-y-auto space-y-2">
                {filteredCustomers.map((c) => (
                  <div key={c.id} className="flex items-center justify-between gap-2 p-3 rounded-lg border border-slate-100 hover:bg-slate-50">
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900 truncate">{c.name}</p>
                      <p className="text-xs text-slate-500 font-mono">{c.phone_number}</p>
                      {c.email ? <p className="text-xs text-slate-400 truncate">{c.email}</p> : null}
                    </div>
                    <button
                      type="button"
                      disabled={addingIds.includes(c.id)}
                      onClick={() => setTypeTarget({ id: c.id, name: c.name, phone_number: c.phone_number, email: c.email })}
                      className="shrink-0 px-3 py-1.5 text-xs font-semibold rounded-lg bg-brand/10 text-brand-dark hover:bg-brand/20 disabled:opacity-50"
                    >
                      {addingIds.includes(c.id) ? <Loader2 className="animate-spin" size={14} /> : "Add"}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
