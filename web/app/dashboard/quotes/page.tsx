"use client";

/**
 * Quotes — list + full-screen editor with live preview, branding, AI assist,
 * sharing, and convert-to-invoice. Backed by /api/quotes.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { quotesApi, customersApi, settingsApi, type Customer } from "@/lib/api";
import { getCurrency, getUser } from "@/lib/auth";
import { printNode } from "@/lib/printInvoice";
import InvoicePreview, { type InvoiceData, type InvoiceItem, type InvoiceBranding } from "@/components/InvoicePreview";
import {
  ClipboardList, Plus, Trash2, Eye, RefreshCw, Sparkles, Share2, Link as LinkIcon,
  Download, Copy, Check, MessageCircle, Mail, X, Palette, Image as ImageIcon,
  ArrowLeft, MoreVertical, CopyPlus, Printer, ArrowRight, CheckCircle2,
} from "lucide-react";

// ── types ────────────────────────────────────────────────────────────────────

type Quote = InvoiceData & {
  id: string;
  share_token?: string;
  subject?: string;
  expires_date?: string;
  accepted_at?: string;
  sent_at?: string;
  viewed_at?: string;
  view_count?: number;
  invoice_id?: string;
};

type Branding = InvoiceBranding;

const EMPTY_ITEM: InvoiceItem = { name: "", description: "", qty: 1, unit_price: 0, amount: 0 };

const STATUSES = ["draft", "sent", "viewed", "accepted", "declined", "expired"] as const;

const STATUS_COLOR: Record<string, string> = {
  draft:    "bg-slate-100 text-slate-700",
  sent:     "bg-blue-100 text-blue-700",
  viewed:   "bg-violet-100 text-violet-700",
  accepted: "bg-green-100 text-green-700",
  declined: "bg-red-100 text-red-700",
  expired:  "bg-gray-100 text-gray-500",
};

const CURRENCIES = ["KES", "USD", "EUR", "GBP", "UGX", "TZS", "NGN", "ZAR", "INR", "AED"];

const TEMPLATES: Array<{ id: string; label: string; hint: string }> = [
  { id: "modern",  label: "Modern",  hint: "Clean, accent-lined tables (default)" },
  { id: "classic", label: "Classic", hint: "Full border, traditional look" },
  { id: "minimal", label: "Minimal", hint: "Lots of whitespace, no fills" },
  { id: "bold",    label: "Bold",    hint: "Color header band with logo" },
];

// ── helpers ──────────────────────────────────────────────────────────────────

function calcItem(i: InvoiceItem): InvoiceItem {
  return { ...i, amount: +(i.qty * i.unit_price).toFixed(2) };
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(String(fr.result));
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(file);
  });
}

async function shrinkImageToDataUrl(file: File, max = 256, quality = 0.85): Promise<string> {
  const raw = await readFileAsDataUrl(file);
  const img = new Image();
  img.src = raw;
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; });
  const scale = Math.min(1, max / Math.max(img.width, img.height));
  const w = Math.round(img.width * scale);
  const h = Math.round(img.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  canvas.getContext("2d")!.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/png", quality);
}

function emptyForm(defaults?: Partial<Quote> & { branding?: Branding; currency?: string }) {
  return {
    customer_id: undefined as string | undefined,
    customer_name: "", customer_phone: "", customer_email: "", customer_address: "",
    subject: "",
    items: [{ ...EMPTY_ITEM }],
    tax_rate: 0, discount: 0,
    currency: defaults?.currency || "KES",
    issue_date: new Date().toISOString().slice(0, 10),
    expires_date: "",
    notes: "",
    terms: "This quote is valid for 30 days from the issue date.",
    po_number: "",
    status: "draft",
    branding: (defaults?.branding || {}) as Branding,
  };
}

type Form = ReturnType<typeof emptyForm>;

// ── row action helper ─────────────────────────────────────────────────────────

function quoteActions(st: string) {
  return [
    ...(st !== "sent"     && st !== "accepted" && st !== "declined" ? [{ status: "sent",     label: "Mark as sent",     icon: <Share2 size={14} /> }] : []),
    ...(st !== "viewed"   && st !== "accepted" && st !== "declined" && st !== "expired" ? [{ status: "viewed",   label: "Mark as viewed",   icon: <Eye size={14} /> }] : []),
    ...(st !== "accepted" && st !== "declined" ? [{ status: "accepted", label: "Mark accepted",    icon: <CheckCircle2 size={14} /> }] : []),
    ...(st !== "declined" && st !== "accepted" ? [{ status: "declined", label: "Mark declined",    icon: <X size={14} /> }] : []),
    ...(st !== "expired"  && st !== "accepted" && st !== "declined" ? [{ status: "expired",  label: "Mark expired",     icon: <RefreshCw size={14} /> }] : []),
    ...(st !== "draft"    && st === "declined" ? [{ status: "draft",    label: "Reopen as draft",  icon: <ClipboardList size={14} /> }] : []),
  ];
}

// ── sub-components ───────────────────────────────────────────────────────────

function Section({ title, children, actions }: { title: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-bold uppercase tracking-widest text-slate-400">{title}</h3>
        {actions}
      </div>
      {children}
    </div>
  );
}

function Input({ label, value, onChange, placeholder, type = "text", className = "" }: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; type?: string; className?: string;
}) {
  return (
    <div className={className}>
      <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">{label}</label>
      <input
        type={type} value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/20"
      />
    </div>
  );
}

function Textarea({ label, value, onChange, rows = 3, className = "" }: {
  label: string; value: string; onChange: (v: string) => void; rows?: number; className?: string;
}) {
  return (
    <div className={className}>
      <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">{label}</label>
      <textarea
        value={value} rows={rows}
        onChange={e => onChange(e.target.value)}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/20 resize-none"
      />
    </div>
  );
}

const COLOR_PRESETS_Q = [
  "#7c3aed","#0f766e","#1d4ed8","#b91c1c","#d97706","#059669",
  "#0f172a","#1e293b","#374151","#6b7280","#9ca3af","#ffffff",
];

const DIAL_CODES_Q: Record<string, string> = {
  US:"+1",CA:"+1",GB:"+44",AU:"+61",DE:"+49",FR:"+33",FI:"+358",
  SE:"+46",NO:"+47",NL:"+31",AE:"+971",IN:"+91",SG:"+65",
  ZA:"+27",NG:"+234",KE:"+254",
};
function getDialCodeQ(): string {
  try {
    const u = getUser();
    const code = (u?.country_code as string) || "";
    return DIAL_CODES_Q[code.toUpperCase()] || "+";
  } catch { return "+"; }
}

// ── QuoteEditor ───────────────────────────────────────────────────────────────

function QuoteEditor({
  editing, onClose, onSaved, customers, brandingDefaults,
}: {
  editing: Quote | null;
  onClose: () => void;
  onSaved: () => void;
  customers: Customer[];
  brandingDefaults: Branding;
}) {
  const [tab, setTab] = useState<"details" | "branding" | "share">("details");
  const [form, setForm] = useState<Form>(() => {
    if (editing) {
      return {
        customer_id: (editing as unknown as { customer_id?: string }).customer_id,
        customer_name: editing.customer_name || "",
        customer_phone: (editing as unknown as { customer_phone?: string }).customer_phone || "",
        customer_email: (editing as unknown as { customer_email?: string }).customer_email || "",
        customer_address: (editing as unknown as { customer_address?: string }).customer_address || "",
        subject: editing.subject || "",
        items: (editing.items?.length ? editing.items : [{ ...EMPTY_ITEM }]).map(calcItem),
        tax_rate: (editing as unknown as { tax_rate?: number }).tax_rate || 0,
        discount: (editing as unknown as { discount?: number }).discount || 0,
        currency: editing.currency || "KES",
        issue_date: (editing as unknown as { issue_date?: string }).issue_date || new Date().toISOString().slice(0, 10),
        expires_date: editing.expires_date || "",
        notes: editing.notes || "",
        terms: editing.terms || "",
        po_number: (editing as unknown as { po_number?: string }).po_number || "",
        status: editing.status || "draft",
        branding: (editing.branding || brandingDefaults) as Branding,
      };
    }
    return emptyForm({ branding: brandingDefaults, currency: (brandingDefaults as unknown as { currency?: string }).currency || "KES" });
  });

  const [savedId, setSavedId] = useState<string | null>(editing?.id || null);
  const [shareToken, setShareToken] = useState<string | null>(editing?.share_token || null);
  const [saving, setSaving] = useState(false);
  const [showAi, setShowAi] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [converting, setConverting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 });
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const logoFileRef = useRef<HTMLInputElement>(null);

  async function onLogoFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) { alert("Logo must be under 4 MB"); return; }
    const dataUrl = await shrinkImageToDataUrl(file, 256, 0.9);
    patch({ logo_url: dataUrl });
    e.target.value = "";
  }

  const shareUrl = useMemo(() => {
    if (!shareToken) return "";
    if (typeof window === "undefined") return "";
    return `${window.location.origin}/quote/${shareToken}`;
  }, [shareToken]);

  function updateItem(idx: number, patch: Partial<InvoiceItem>) {
    setForm(f => {
      const items = [...f.items];
      const updated = { ...items[idx], ...patch };
      items[idx] = calcItem(updated);
      return { ...f, items };
    });
  }
  function addItem() { setForm(f => ({ ...f, items: [...f.items, { ...EMPTY_ITEM }] })); }
  function removeItem(idx: number) { setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) })); }

  const subtotal  = useMemo(() => form.items.reduce((s, i) => s + i.qty * i.unit_price, 0), [form.items]);
  const disc_pct  = form.discount || 0;
  const disc_amt  = useMemo(() => +(subtotal * disc_pct / 100).toFixed(2), [subtotal, disc_pct]);
  const tax_base  = Math.max(subtotal - disc_amt, 0);
  const tax_amount = useMemo(() => +(tax_base * (form.tax_rate / 100)).toFixed(2), [tax_base, form.tax_rate]);
  const total     = useMemo(() => +(tax_base + tax_amount).toFixed(2), [tax_base, tax_amount]);

  const previewData: InvoiceData = {
    number: editing?.number || "QTE-PREVIEW",
    customer_name: form.customer_name,
    customer_email: (form as unknown as { customer_email?: string }).customer_email,
    customer_address: (form as unknown as { customer_address?: string }).customer_address,
    items: form.items,
    subtotal,
    discount_amount: disc_amt,
    tax_rate: form.tax_rate,
    tax_amount,
    total,
    currency: form.currency,
    issue_date: form.issue_date,
    due_date: form.expires_date,
    notes: form.notes,
    terms: form.terms,
    status: form.status,
    branding: form.branding,
  };

  async function save() {
    setSaving(true);
    try {
      const payload = {
        customer_name: form.customer_name,
        customer_phone: (form as unknown as { customer_phone?: string }).customer_phone,
        customer_email: (form as unknown as { customer_email?: string }).customer_email,
        customer_address: (form as unknown as { customer_address?: string }).customer_address,
        subject: form.subject,
        items: form.items.map(i => ({ name: i.name, description: i.description || "", qty: i.qty, unit_price: i.unit_price, amount: i.amount })),
        tax_rate: form.tax_rate,
        discount: form.discount,
        currency: form.currency,
        issue_date: form.issue_date || null,
        expires_date: form.expires_date || null,
        notes: form.notes,
        terms: form.terms,
        po_number: form.po_number || null,
        status: form.status,
        branding: form.branding,
      };
      if (savedId) {
        const updated = await quotesApi.update(savedId, payload) as unknown as Quote;
        setShareToken(updated.share_token || null);
        onSaved();
      } else {
        await quotesApi.create(payload);
        onSaved();
        onClose();
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to save quote");
    } finally {
      setSaving(false);
    }
  }

  async function runAi() {
    if (!aiPrompt.trim()) return;
    setAiBusy(true);
    try {
      const out = await quotesApi.aiDraft({
        prompt: aiPrompt,
        currency: form.currency,
        customer_name: form.customer_name,
      });
      setForm(f => ({
        ...f,
        customer_name: out.customer_name || f.customer_name,
        items: (out.items || []).map(calcItem),
        notes: out.notes || f.notes,
        terms: out.terms || f.terms,
      }));
      setShowAi(false);
      setAiPrompt("");
    } catch (e) {
      alert(e instanceof Error ? e.message : "AI draft failed");
    } finally {
      setAiBusy(false);
    }
  }

  async function handleConvert() {
    if (!savedId) { alert("Save the quote first."); return; }
    if (!confirm("Convert this quote to a draft invoice?")) return;
    setConverting(true);
    try {
      const res = await quotesApi.convertToInvoice(savedId);
      alert(`Invoice ${(res as unknown as { invoice: { number: string } }).invoice?.number || ""} created! Go to Invoices to view it.`);
      onSaved();
      onClose();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Conversion failed");
    } finally {
      setConverting(false);
    }
  }

  async function copyShareLink() {
    try { await navigator.clipboard.writeText(shareUrl); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { /* ignore */ }
  }

  async function rotateLink() {
    if (!savedId) return;
    const r = await quotesApi.rotateShare(savedId);
    setShareToken(r.share_token);
  }

  function openActionMenu() {
    const rect = menuBtnRef.current?.getBoundingClientRect();
    if (rect) setMenuPos({ top: rect.bottom + 6, left: rect.right - 180 });
    setActionMenuOpen(v => !v);
  }

  const phonePlaceholder = useMemo(() => `${getDialCodeQ()}…`, []);

  const patch = (b: Partial<Branding>) => setForm(f => ({ ...f, branding: { ...f.branding, ...b } }));

  return (
    <div
      className="no-print fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-2 sm:p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-50 rounded-xl shadow-2xl overflow-hidden flex flex-col w-full max-w-7xl h-[95vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Top bar */}
        <div className="h-14 border-b bg-white flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={onClose} className="p-2 -ml-2 text-slate-500 hover:text-slate-800"><ArrowLeft size={18} /></button>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-800 truncate">{editing?.number || "New Quote"}</p>
              {editing?.customer_name && <p className="text-xs text-slate-400 truncate">{editing.customer_name}</p>}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {form.status && (
              <span className={`hidden sm:inline-flex px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_COLOR[form.status] || ""}`}>
                {form.status}
              </span>
            )}
            {savedId && (
              <button ref={menuBtnRef} onClick={e => { e.stopPropagation(); openActionMenu(); }}
                className="p-2 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100">
                <MoreVertical size={16} />
              </button>
            )}
            <button
              onClick={save} disabled={saving}
              className="bg-brand-dark text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50">
              {saving ? "Saving…" : savedId ? "Save" : "Create Quote"}
            </button>
          </div>
        </div>

        {/* Action menu */}
        {actionMenuOpen && (
          <>
          <div className="fixed inset-0 z-[59]" onClick={() => setActionMenuOpen(false)} />
          <div
            className="fixed z-[60] bg-white rounded-xl shadow-xl border border-slate-200 py-1 w-48"
            style={{ top: menuPos.top, left: menuPos.left }}
            onClick={e => e.stopPropagation()}
          >
            {quoteActions(form.status).map(a => (
              <button key={a.status}
                onClick={async () => {
                  if (savedId) {
                    await quotesApi.setStatus(savedId, a.status);
                    setForm(f => ({ ...f, status: a.status }));
                    onSaved();
                  }
                  setActionMenuOpen(false);
                }}
                className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                {a.icon}{a.label}
              </button>
            ))}
            <div className="border-t border-slate-100 my-1" />
            <button
              onClick={async () => {
                if (savedId) { await quotesApi.duplicate(savedId); onSaved(); }
                setActionMenuOpen(false);
              }}
              className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
              <CopyPlus size={14} /> Duplicate
            </button>
            <button
              onClick={() => { handleConvert(); setActionMenuOpen(false); }}
              className="w-full text-left px-4 py-2 text-sm text-green-700 hover:bg-green-50 flex items-center gap-2">
              <ArrowRight size={14} /> Convert to Invoice
            </button>
          </div>
          </>
        )}

        {/* Main area */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: form */}
          <div className="w-full md:w-[420px] lg:w-[460px] shrink-0 flex flex-col border-r border-slate-200">
            {/* Tabs */}
            <div className="flex items-center gap-1 px-2 border-b bg-slate-50 sticky top-0 z-10">
              {[
                { id: "details",  label: "Details",  icon: ClipboardList },
                { id: "branding", label: "Branding", icon: Palette },
                { id: "share",    label: "Share",    icon: Share2 },
              ].map(t => (
                <button key={t.id} onClick={() => setTab(t.id as typeof tab)}
                  className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                    tab === t.id ? "border-brand-dark text-brand-dark" : "border-transparent text-slate-500 hover:text-slate-700"
                  }`}>
                  <t.icon size={13} />{t.label}
                </button>
              ))}
            </div>

            {/* Scrollable form content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-5">

              {tab === "details" && (
                <>
                  {/* Subject */}
                  <Section title="Quote Subject">
                    <input
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/20"
                      value={form.subject}
                      onChange={e => setForm(f => ({ ...f, subject: e.target.value }))}
                      placeholder="e.g. Website Redesign Proposal"
                    />
                  </Section>

                  {/* Customer */}
                  <Section title="Customer">
                    <CustomerPickerQ
                      customers={customers}
                      value={form.customer_name}
                      onChange={v => setForm(f => ({ ...f, customer_name: v, customer_id: undefined }))}
                      onPick={c => setForm(f => ({
                        ...f,
                        customer_id: c.id,
                        customer_name: c.name || "",
                        customer_phone: c.phone_number || (f as unknown as { customer_phone?: string }).customer_phone || "",
                        customer_email: c.email || (f as unknown as { customer_email?: string }).customer_email || "",
                      } as unknown as Form))}
                    />
                    <div className="grid grid-cols-2 gap-3 mt-3">
                      <Input label="Email" value={(form as unknown as { customer_email?: string }).customer_email || ""} onChange={v => setForm(f => ({ ...f, customer_email: v } as unknown as Form))} placeholder="jane@acme.co" />
                      <Input label="Phone" value={(form as unknown as { customer_phone?: string }).customer_phone || ""} onChange={v => setForm(f => ({ ...f, customer_phone: v } as unknown as Form))} placeholder={phonePlaceholder} />
                      <Input label="PO #" value={form.po_number || ""} onChange={v => setForm(f => ({ ...f, po_number: v }))} placeholder="Optional" />
                      <div />
                      <Textarea label="Billing address" value={(form as unknown as { customer_address?: string }).customer_address || ""} onChange={v => setForm(f => ({ ...f, customer_address: v } as unknown as Form))} className="col-span-2" rows={2} />
                    </div>
                  </Section>

                  {/* Line items */}
                  <Section
                    title="Line items"
                    actions={
                      <button onClick={() => setShowAi(v => !v)} className="text-xs text-violet-700 hover:text-violet-800 inline-flex items-center gap-1">
                        <Sparkles size={12} /> AI assist
                      </button>
                    }
                  >
                    {showAi && (
                      <div className="rounded-xl border border-violet-200 bg-violet-50 p-3 space-y-2 mb-2">
                        <p className="text-xs font-semibold text-violet-800">Describe the proposal in plain language</p>
                        <textarea
                          rows={3}
                          className="w-full text-sm border border-violet-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-violet-300 resize-none"
                          placeholder="e.g. Social media management for 3 months, 2 posts/week, includes content creation..."
                          value={aiPrompt}
                          onChange={e => setAiPrompt(e.target.value)}
                          onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runAi(); }}
                        />
                        <div className="flex justify-end gap-2">
                          <button onClick={() => setShowAi(false)} className="text-xs text-slate-500">Cancel</button>
                          <button onClick={runAi} disabled={aiBusy || !aiPrompt.trim()}
                            className="text-xs bg-violet-700 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
                            {aiBusy ? "Generating…" : "Generate items"}
                          </button>
                        </div>
                      </div>
                    )}
                    {/* Column headers */}
                    <div className="hidden md:grid grid-cols-12 gap-2 mb-1 px-0.5">
                      <div className="col-span-4 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Item / service</div>
                      <div className="col-span-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Qty</div>
                      <div className="col-span-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Unit price</div>
                      <div className="col-span-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400 text-right">Amount</div>
                    </div>
                    <div className="space-y-2">
                      {form.items.map((item, idx) => (
                        <div key={idx} className="grid grid-cols-12 gap-2 items-start">
                          <div className="col-span-12 md:col-span-4">
                            <input
                              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                              value={item.name} placeholder="Item / service"
                              onChange={e => updateItem(idx, { name: e.target.value })}
                            />
                            <input
                              className="mt-1 w-full border border-slate-100 rounded px-2 py-1 text-xs text-slate-600"
                              value={item.description || ""} placeholder="Optional description"
                              onChange={e => updateItem(idx, { description: e.target.value })}
                            />
                          </div>
                          <input type="number" min="0" step="1"
                            className="col-span-3 md:col-span-2 border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                            value={item.qty === 0 ? "" : item.qty}
                            onFocus={e => e.target.select()}
                            onChange={e => updateItem(idx, { qty: e.target.value === "" ? 0 : +e.target.value })}
                            placeholder="0"
                          />
                          <input type="number" min="0" step="0.01"
                            className="col-span-5 md:col-span-3 border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                            value={item.unit_price === 0 ? "" : item.unit_price}
                            onFocus={e => e.target.select()}
                            onChange={e => updateItem(idx, { unit_price: e.target.value === "" ? 0 : +e.target.value })}
                            placeholder="0.00"
                          />
                          <div className="col-span-3 md:col-span-2 text-xs font-medium text-slate-700 text-right self-center tabular-nums">
                            {item.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </div>
                          <button onClick={() => removeItem(idx)}
                            className="col-span-1 text-slate-300 hover:text-red-500 flex justify-center pt-1.5">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                    <button onClick={addItem} className="mt-2 text-xs text-brand-dark hover:underline inline-flex items-center gap-1">
                      <Plus size={12} /> Add item
                    </button>
                  </Section>

                  {/* Totals */}
                  <Section title="Totals">
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">Tax %</label>
                        <input type="number" min="0" max="100" step="0.5"
                          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                          value={form.tax_rate}
                          onChange={e => setForm(f => ({ ...f, tax_rate: +e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">Discount %</label>
                        <input type="number" min="0" max="100" step="0.5"
                          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                          value={form.discount}
                          onChange={e => setForm(f => ({ ...f, discount: +e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">Currency</label>
                        <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                          value={form.currency}
                          onChange={e => setForm(f => ({ ...f, currency: e.target.value }))}>
                          {CURRENCIES.map(c => <option key={c}>{c}</option>)}
                        </select>
                      </div>
                    </div>
                    <div className="mt-3 bg-white border border-slate-100 rounded-xl p-3 space-y-1.5 text-sm">
                      <RowQ label="Subtotal" value={`${form.currency} ${subtotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} />
                      {disc_pct > 0 && <RowQ label={`Discount (${disc_pct}%)`} value={`- ${form.currency} ${disc_amt.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} className="text-amber-600" />}
                      {form.tax_rate > 0 && <RowQ label={`Tax (${form.tax_rate}%)`} value={`${form.currency} ${tax_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} />}
                      <div className="border-t border-slate-100 pt-1.5">
                        <RowQ label="Total" value={`${form.currency} ${total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} bold />
                      </div>
                    </div>
                  </Section>

                  {/* Dates & Status */}
                  <Section title="Dates & Status">
                    <div className="grid grid-cols-2 gap-3">
                      <Input label="Issue date" type="date" value={form.issue_date || ""} onChange={v => setForm(f => ({ ...f, issue_date: v }))} />
                      <Input label="Expires date" type="date" value={form.expires_date || ""} onChange={v => setForm(f => ({ ...f, expires_date: v }))} />
                    </div>
                    <div className="mt-3">
                      <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">Status</label>
                      <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                        value={form.status}
                        onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                        {STATUSES.map(s => <option key={s}>{s}</option>)}
                      </select>
                    </div>
                  </Section>

                  {/* Notes / Terms */}
                  <Section title="Notes & Terms">
                    <Textarea label="Notes" value={form.notes} onChange={v => setForm(f => ({ ...f, notes: v }))} rows={2} />
                    <Textarea label="Terms" value={form.terms} onChange={v => setForm(f => ({ ...f, terms: v }))} rows={2} />
                  </Section>
                </>
              )}

              {tab === "branding" && (
                <>
                  <Section title="Logo">
                    <div className="flex items-center gap-4">
                      <div className="w-20 h-20 rounded-lg border-2 border-dashed border-slate-200 bg-slate-50 flex items-center justify-center overflow-hidden shrink-0">
                        {form.branding?.logo_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={form.branding.logo_url} alt="Logo" className="w-full h-full object-contain" />
                        ) : (
                          <ImageIcon className="text-slate-300" size={24} />
                        )}
                      </div>
                      <div className="flex flex-col gap-2">
                        <input ref={logoFileRef} type="file" accept="image/*" className="hidden" onChange={onLogoFile} />
                        <button onClick={() => logoFileRef.current?.click()}
                          className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 hover:border-brand-dark hover:text-brand-dark inline-flex items-center gap-2">
                          <ImageIcon size={14} /> Upload logo
                        </button>
                        {form.branding?.logo_url && (
                          <button onClick={() => patch({ logo_url: "" })} className="text-xs text-red-600 hover:underline text-left">
                            Remove logo
                          </button>
                        )}
                        <p className="text-xs text-slate-400">PNG / JPG / SVG · max 4 MB</p>
                      </div>
                    </div>
                  </Section>
                  <Section title="Colors">
                    <div className="grid grid-cols-2 gap-3">
                      <ColorInputQ label="Accent color" value={form.branding?.accent_color || "#7c3aed"} onChange={v => patch({ accent_color: v })} />
                      <ColorInputQ label="Text color"   value={form.branding?.text_color   || "#0f172a"} onChange={v => patch({ text_color: v })} />
                    </div>
                  </Section>
                  <Section title="Template">
                    <div className="grid grid-cols-2 gap-2">
                      {TEMPLATES.map(t => (
                        <button key={t.id} onClick={() => patch({ template: t.id })}
                          className={`p-2 rounded-lg border text-left transition-all ${
                            form.branding?.template === t.id
                              ? "border-brand-dark bg-brand-dark/5 ring-1 ring-brand-dark"
                              : "border-slate-200 hover:border-slate-300"
                          }`}>
                          <p className="text-xs font-semibold text-slate-800">{t.label}</p>
                          <p className="text-[10px] text-slate-400">{t.hint}</p>
                        </button>
                      ))}
                    </div>
                  </Section>
                  <Section title="Company info">
                    <div className="grid grid-cols-2 gap-3">
                      <Input label="Business name" value={form.branding?.from_name || ""} onChange={v => patch({ from_name: v })} />
                      <Input label="Email"         value={form.branding?.from_email || ""} onChange={v => patch({ from_email: v })} />
                      <Input label="Phone"         value={form.branding?.from_phone || ""} onChange={v => patch({ from_phone: v })} />
                      <Input label="Address"       value={form.branding?.from_address || ""} onChange={v => patch({ from_address: v })} />
                    </div>
                  </Section>
                  <Section title="Footer">
                    <Textarea label="Footer text" value={form.branding?.footer || ""} onChange={v => patch({ footer: v })} rows={2} />
                  </Section>
                </>
              )}

              {tab === "share" && (
                <>
                  <Section title="Share link">
                    {!savedId ? (
                      <p className="text-sm text-slate-500">Save the quote first to get a shareable link.</p>
                    ) : !shareToken ? (
                      <p className="text-sm text-slate-500">Resave to generate a share link.</p>
                    ) : (
                      <>
                        <div className="flex gap-2">
                          <input readOnly value={shareUrl}
                            className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-600 bg-slate-50" />
                          <button onClick={copyShareLink}
                            className="px-3 py-2 border border-slate-200 rounded-lg text-sm hover:bg-slate-50">
                            {copied ? <Check size={14} className="text-green-600" /> : <Copy size={14} />}
                          </button>
                        </div>
                        <div className="flex flex-wrap gap-2 mt-3">
                          <a href={shareUrl} target="_blank" rel="noreferrer"
                            className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50">
                            <LinkIcon size={13} /> Open quote →
                          </a>
                          <a href={`https://wa.me/${
                            ((form as unknown as { customer_phone?: string }).customer_phone || "").replace(/[^\d]/g, "")
                          }?text=${encodeURIComponent(`Hi ${form.customer_name || "there"}, here is your quote ${editing?.number || ""}.\n${shareUrl}`)}`}
                            target="_blank" rel="noreferrer"
                            className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-green-200 text-green-800 bg-green-50 hover:bg-green-100">
                            <MessageCircle size={13} /> WhatsApp
                          </a>
                          <a href={`mailto:${
                            (form as unknown as { customer_email?: string }).customer_email || ""
                          }?subject=Quote ${editing?.number || ""}&body=${encodeURIComponent(`Hi ${form.customer_name || "there"},\n\nPlease find your quote here: ${shareUrl}`)}`}
                            className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-blue-200 text-blue-800 bg-blue-50 hover:bg-blue-100">
                            <Mail size={13} /> Email
                          </a>
                          <button
                            onClick={() => {
                              const node = previewRef.current?.querySelector<HTMLElement>(".invoice-preview-root") ?? null;
                              printNode(node, `Quote ${editing?.number || ""}`.trim());
                            }}
                            className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50">
                            <Printer size={13} /> Print / PDF
                          </button>
                        </div>
                        <button onClick={rotateLink}
                          className="mt-3 text-xs text-slate-400 hover:text-slate-600 inline-flex items-center gap-1">
                          <RefreshCw size={11} /> Rotate link (invalidates old link)
                        </button>
                      </>
                    )}
                  </Section>
                  {savedId && (
                    <Section title="Convert to Invoice">
                      <p className="text-xs text-slate-500 mb-2">Once the client accepts, convert this quote into a draft invoice with all line items pre-filled.</p>
                      <button onClick={handleConvert} disabled={converting}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50">
                        <ArrowRight size={15} /> {converting ? "Converting…" : "Convert to Invoice"}
                      </button>
                    </Section>
                  )}
                </>
              )}

            </div>
          </div>

          {/* Right: live preview */}
          <div ref={previewRef} className="hidden md:flex flex-1 overflow-y-auto bg-slate-200/60 p-6">
            <InvoicePreview data={previewData} docType="QUOTE" />
          </div>
        </div>
      </div>
    </div>
  );
}

function RowQ({ label, value, bold, className }: { label: string; value: string; bold?: boolean; className?: string }) {
  return (
    <div className={`flex justify-between items-center ${bold ? "font-bold text-slate-800" : "text-slate-600"} ${className || ""}`.trim()}>
      <span>{label}</span><span className="tabular-nums">{value}</span>
    </div>
  );
}

function ColorInputQ({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <div className="flex items-center gap-2">
        <label className="relative h-9 w-9 rounded-lg border border-slate-200 cursor-pointer overflow-hidden shrink-0" style={{ background: value }}>
          <input type="color" value={value} onChange={e => onChange(e.target.value)}
            className="absolute inset-0 opacity-0 cursor-pointer" />
        </label>
        <input value={value} onChange={e => onChange(e.target.value)}
          className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono uppercase" />
      </div>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {COLOR_PRESETS_Q.map(c => (
          <button key={c} type="button" onClick={() => onChange(c)} title={c}
            className={`h-5 w-5 rounded-full border transition ${
              value === c ? "ring-2 ring-offset-1 ring-brand-dark scale-110" : "border-slate-300 hover:scale-110"
            }`}
            style={{ background: c }} />
        ))}
      </div>
    </div>
  );
}

function CustomerPickerQ({ customers, value, onChange, onPick }: {
  customers: Customer[];
  value: string;
  onChange: (v: string) => void;
  onPick: (c: Customer) => void;
}) {
  const [open, setOpen] = useState(false);
  const q = value.toLowerCase();
  const matches = (q
    ? customers.filter(c =>
        (c.name || "").toLowerCase().includes(q) ||
        (c.phone_number || "").includes(q) ||
        (c.email || "").toLowerCase().includes(q))
    : customers
  ).slice(0, 8);
  return (
    <div className="relative">
      <input
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="Search by name, phone or email…"
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/30"
      />
      {open && matches.length > 0 && (
        <div className="absolute z-20 w-full mt-1 bg-white border border-slate-200 rounded-xl shadow-lg overflow-hidden">
          {matches.map(c => (
            <button key={c.id} className="w-full text-left px-3 py-2 hover:bg-slate-50 transition-colors"
              onMouseDown={e => { e.preventDefault(); onPick(c); setOpen(false); }}>
              <div className="text-sm font-medium text-slate-800 truncate">{c.name || "(unnamed)"}</div>
              <div className="text-xs text-slate-500 truncate">
                {[c.phone_number, c.email].filter(Boolean).join(" · ") || "No contact info"}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function QuotesPage() {
  const [quotes, setQuotes]   = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter]   = useState("");
  const [search, setSearch]   = useState("");
  const [summary, setSummary] = useState<Record<string, { count: number; total: number }>>({});
  const [editor, setEditor]   = useState<{ open: boolean; editing: Quote | null }>({ open: false, editing: null });
  const [customers, setCustomers]         = useState<Customer[]>([]);
  const [brandingDefaults, setBrandingDefaults] = useState<Branding>({});
  const [defaultCurrency, setDefaultCurrency]   = useState<string>(() => {
    try { const u = getUser(); return (u?.currency as string) || getCurrency() || "KES"; }
    catch { return "KES"; }
  });
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [menuPos, setMenuPos]   = useState({ top: 0, left: 0 });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, sum, branding, cs, settings] = await Promise.all([
        quotesApi.list(),
        quotesApi.summary(),
        quotesApi.getBranding().catch(() => ({})),
        customersApi.list().catch(() => []),
        settingsApi.get().catch(() => ({})),
      ]);
      setQuotes(list as Quote[]);
      setSummary(((sum as { by_status?: Record<string, { count: number; total: number }> }).by_status) || {});
      setBrandingDefaults(branding as Branding);
      setCustomers(cs as Customer[]);
      const sc = (settings as { currency?: string }).currency;
      if (sc) setDefaultCurrency(sc);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function openNew() { setEditor({ open: true, editing: null }); }
  function openEdit(q: Quote) { setEditor({ open: true, editing: q }); }

  const filtered = useMemo(() => quotes.filter(q => {
    if (filter && q.status !== filter) return false;
    if (search) {
      const s = search.toLowerCase();
      return (q.customer_name || "").toLowerCase().includes(s) ||
             (q.number || "").toLowerCase().includes(s) ||
             ((q as unknown as { subject?: string }).subject || "").toLowerCase().includes(s);
    }
    return true;
  }), [quotes, filter, search]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ClipboardList className="text-brand-dark" size={24} /> Quotes & Proposals
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Send proposals, get accepted, convert to invoices.</p>
        </div>
        <button onClick={openNew}
          className="flex items-center gap-2 bg-brand-dark text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand">
          <Plus size={16} /> New Quote
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {(["draft","sent","viewed","accepted","declined","expired"] as const).map(s => (
          <button key={s} onClick={() => setFilter(filter === s ? "" : s)}
            className={`rounded-xl border p-3 text-left transition-all ${
              filter === s ? "border-brand-dark bg-brand-dark/5" : "bg-white hover:border-slate-300"
            }`}>
            <p className="text-[10px] text-slate-400 capitalize font-medium">{s}</p>
            <p className="text-lg font-bold text-slate-800 mt-0.5">{summary[s]?.count || 0}</p>
          </button>
        ))}
      </div>

      {/* Search + filter */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search customer, number or subject…"
          className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/20 w-64"
        />
        <div className="flex gap-1.5 flex-wrap">
          {["", ...STATUSES].map(s => (
            <button key={s} onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded-full text-xs font-medium border capitalize ${
                filter === s ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}>{s || "All"}</button>
          ))}
        </div>
        <button onClick={load} className="ml-auto text-slate-400 hover:text-slate-700"><RefreshCw size={16} /></button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-60 text-slate-400 gap-2 border-2 border-dashed border-slate-200 rounded-xl">
          <ClipboardList size={40} className="opacity-30" />
          <p>No quotes yet.</p>
          <button onClick={openNew} className="mt-2 text-sm text-brand-dark font-medium hover:underline">Create your first quote →</button>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-400 text-[11px] uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-3">Number</th>
                <th className="text-left px-4 py-3">Customer</th>
                <th className="text-left px-4 py-3 hidden md:table-cell">Subject</th>
                <th className="text-right px-4 py-3">Total</th>
                <th className="text-left px-4 py-3 hidden lg:table-cell">Expires</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-right px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map(q => (
                <tr key={q.id} className="hover:bg-slate-50 cursor-pointer" onClick={() => openEdit(q)}>
                  <td className="px-4 py-3 font-mono font-medium text-brand-dark">{q.number}</td>
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-800">{q.customer_name || "—"}</p>
                    <p className="text-xs text-slate-400">{(q as unknown as { customer_email?: string }).customer_email || (q as unknown as { customer_phone?: string }).customer_phone || ""}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-500 hidden md:table-cell max-w-[160px] truncate">{(q as unknown as { subject?: string }).subject || "—"}</td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-800 tabular-nums">
                    {q.currency} {(q.total || 0).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-slate-500 hidden lg:table-cell">
                    {q.expires_date ? new Date(q.expires_date).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
                      STATUS_COLOR[q.status || ""] || "bg-slate-100 text-slate-600"
                    }`}>{q.status}</span>
                  </td>
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-2">
                      <button
                        title="Convert to invoice"
                        onClick={async e => {
                          e.stopPropagation();
                          if (!confirm(`Convert ${q.number} to invoice?`)) return;
                          try { await quotesApi.convertToInvoice(q.id); await load(); }
                          catch (err) { alert(err instanceof Error ? err.message : "Failed"); }
                        }}
                        className="p-1.5 rounded-lg text-slate-400 hover:bg-green-50 hover:text-green-600 transition-colors">
                        <ArrowRight size={15} />
                      </button>
                      <button
                        title="More actions"
                        onClick={e => {
                          e.stopPropagation();
                          const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
                          setMenuPos({ top: rect.bottom + 6, left: rect.right - 180 });
                          setMenuOpen(menuOpen === q.id ? null : q.id);
                        }}
                        className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 transition-colors">
                        <MoreVertical size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Row action dropdown */}
      {menuOpen && (
        <>
        <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(null)} />
        <div
          className="fixed z-50 bg-white rounded-xl shadow-xl border border-slate-200 py-1 w-48"
          style={{ top: menuPos.top, left: menuPos.left }}
          onClick={e => e.stopPropagation()}
        >
          {(() => {
            const q = quotes.find(x => x.id === menuOpen);
            if (!q) return null;
            return (
              <>
                {quoteActions(q.status || "").map(a => (
                  <button key={a.status}
                    onClick={async () => {
                      await quotesApi.setStatus(q.id, a.status);
                      await load();
                      setMenuOpen(null);
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                    {a.icon}{a.label}
                  </button>
                ))}
                <div className="border-t border-slate-100 my-1" />
                <button
                  onClick={async () => { await quotesApi.duplicate(q.id); await load(); setMenuOpen(null); }}
                  className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                  <CopyPlus size={14} /> Duplicate
                </button>
                <button
                  onClick={() => { openEdit(q); setMenuOpen(null); }}
                  className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                  <Eye size={14} /> Edit
                </button>
                <div className="border-t border-slate-100 my-1" />
                <button
                  onClick={async () => {
                    if (!confirm(`Delete ${q.number}?`)) return;
                    await quotesApi.delete(q.id);
                    await load();
                    setMenuOpen(null);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2">
                  <Trash2 size={14} /> Delete
                </button>
              </>
            );
          })()}
        </div>
        </>
      )}

      {/* Editor */}
      {editor.open && (
        <QuoteEditor
          editing={editor.editing}
          onClose={() => setEditor({ open: false, editing: null })}
          onSaved={load}
          customers={customers}
          brandingDefaults={brandingDefaults}
        />
      )}
    </div>
  );
}
