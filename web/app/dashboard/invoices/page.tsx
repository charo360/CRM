"use client";

/**
 * Invoices — list + full-screen editor with live preview, branding controls,
 * AI assist, sharing (copy link / WhatsApp / Email / Print-as-PDF), templates,
 * partial payments and duplication. Backed by /api/invoices (see
 * `backend/invoices/routes.py`).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoicesApi, customersApi, settingsApi, type Customer } from "@/lib/api";
import { getCurrency, getUser } from "@/lib/auth";
import { printNode } from "@/lib/printInvoice";
import InvoicePreview, { type InvoiceData, type InvoiceItem, type InvoiceBranding } from "@/components/InvoicePreview";
import {
  FileText, Plus, Trash2, Eye, RefreshCw, Sparkles, Share2, Link as LinkIcon,
  Download, Copy, Check, MessageCircle, Mail, X, Palette, Image as ImageIcon,
  Receipt, ArrowLeft, MoreVertical, CopyPlus, Printer, DollarSign, Pencil,
} from "lucide-react";

// ── types ───────────────────────────────────────────────────────────────────

type Invoice = InvoiceData & {
  id: string;
  share_token?: string;
  created_at?: string;
  sent_at?: string;
  viewed_at?: string;
  paid_at?: string;
  view_count?: number;
  payments?: Array<{ amount: number; method?: string; note?: string; at: string }>;
};

type Branding = InvoiceBranding;

const EMPTY_ITEM: InvoiceItem = { name: "", description: "", qty: 1, unit_price: 0, amount: 0 };

const STATUSES = ["draft", "sent", "viewed", "paid", "partial", "overdue", "cancelled"] as const;

const STATUS_COLOR: Record<string, string> = {
  draft:     "bg-slate-100 text-slate-700",
  sent:      "bg-blue-100 text-blue-700",
  viewed:    "bg-violet-100 text-violet-700",
  paid:      "bg-green-100 text-green-700",
  partial:   "bg-amber-100 text-amber-700",
  overdue:   "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-500",
};

const CURRENCIES = ["KES", "USD", "EUR", "GBP", "UGX", "TZS", "NGN", "ZAR", "INR", "AED"];

const TEMPLATES: Array<{ id: string; label: string; hint: string }> = [
  { id: "modern",  label: "Modern",  hint: "Clean, accent-lined tables (default)" },
  { id: "classic", label: "Classic", hint: "Full border, traditional look" },
  { id: "minimal", label: "Minimal", hint: "Lots of whitespace, no fills" },
  { id: "bold",    label: "Bold",    hint: "Color header band with logo" },
];

// ── helpers ─────────────────────────────────────────────────────────────────

function emptyForm(defaults?: Partial<Invoice> & { branding?: Branding; currency?: string }) {
  return {
    customer_id: undefined as string | undefined,
    customer_name: "", customer_phone: "", customer_email: "", customer_address: "",
    items: [{ ...EMPTY_ITEM }],
    tax_rate: 0, discount: 0,
    currency: defaults?.currency || "USD",
    issue_date: new Date().toISOString().slice(0, 10),
    due_date: "",
    notes: "",
    terms: "Payment due within 14 days of invoice date.",
    po_number: "",
    status: "draft",
    branding: defaults?.branding || {},
  };
}

function calcItem(i: InvoiceItem): InvoiceItem {
  return { ...i, amount: +(Number(i.qty || 0) * Number(i.unit_price || 0)).toFixed(2) };
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
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/png", quality);
}

// ── page ────────────────────────────────────────────────────────────────────

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  const [summary, setSummary] = useState<{ by_status?: Record<string, { count: number; total: number }>; total_invoiced?: number; total_paid?: number; outstanding?: number }>({});
  const [brandingDefaults, setBrandingDefaults] = useState<Branding>({});
  const [defaultCurrency, setDefaultCurrency] = useState<string>(() => {
    // Read from localStorage immediately so there's no USD flash before API returns.
    // getUser() top-level currency is what PUT /settings writes; getCurrency() reads
    // from user.settings.currency (auto-detected on first GET /settings).
    try {
      const u = getUser();
      return (u?.currency as string) || getCurrency() || "USD";
    } catch { return "USD"; }
  });

  const [editor, setEditor] = useState<{ open: boolean; editing: Invoice | null }>({ open: false, editing: null });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, sum, branding, userSettings] = await Promise.all([
        invoicesApi.list(),
        invoicesApi.summary(),
        invoicesApi.getBranding().catch(() => ({})),
        settingsApi.get().catch(() => ({})),
      ]);
      setInvoices(list as unknown as Invoice[]);
      setSummary(sum as typeof summary);
      const b = branding as Branding & { currency?: string };
      setBrandingDefaults(b);
      // settingsApi is the authoritative source — it reads directly from the
      // user doc that PUT /settings writes to.
      const cur = (userSettings as { currency?: string }).currency
        || b.currency
        || "";
      if (cur) setDefaultCurrency(cur);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function openNew() {
    setEditor({ open: true, editing: null });
  }

  function openEdit(inv: Invoice) {
    setEditor({ open: true, editing: inv });
  }

  async function del(inv: Invoice) {
    if (!confirm(`Delete ${inv.number}? This cannot be undone.`)) return;
    await invoicesApi.delete(inv.id);
    await load();
  }

  async function duplicate(inv: Invoice) {
    await invoicesApi.duplicate(inv.id);
    await load();
  }

  const filtered = invoices.filter(i => {
    if (filter && i.status !== filter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (i.number || "").toLowerCase().includes(q)
        || (i.customer_name || "").toLowerCase().includes(q)
        || (i.customer_email || "").toLowerCase().includes(q);
    }
    return true;
  });

  const totals = {
    invoiced: summary.total_invoiced || 0,
    paid: summary.total_paid || 0,
    outstanding: summary.outstanding || 0,
  };
  const primaryCur = invoices[0]?.currency || defaultCurrency;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Receipt className="text-brand-dark" size={24} /> Invoices
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Create, brand, share &amp; get paid faster.</p>
        </div>
        <button
          onClick={openNew}
          className="flex items-center gap-2 bg-brand-dark text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand shadow-sm"
        >
          <Plus size={16} /> New invoice
        </button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Total invoiced" value={`${primaryCur} ${totals.invoiced.toLocaleString()}`} accent="slate" />
        <KpiCard label="Paid"            value={`${primaryCur} ${totals.paid.toLocaleString()}`}      accent="green" />
        <KpiCard label="Outstanding"     value={`${primaryCur} ${totals.outstanding.toLocaleString()}`} accent="amber" />
        <KpiCard label="Invoices"        value={String(invoices.length)} accent="violet" />
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap items-center">
        {(["", ...STATUSES] as const).map(s => (
          <button key={s || "all"} onClick={() => setFilter(s)}
            className={`px-3 py-1 rounded-full text-xs font-medium border capitalize transition ${
              filter === s ? "bg-brand-dark text-white border-brand-dark"
                            : "bg-white text-slate-600 border-slate-200 hover:border-brand"
            }`}>
            {s || "All"} {s && summary.by_status?.[s] ? `(${summary.by_status[s].count})` : ""}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search #, customer…"
            className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm w-56"
          />
          <button onClick={load} className="text-slate-400 hover:text-slate-700"><RefreshCw size={16} /></button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-60 text-slate-400 gap-2 border-2 border-dashed border-slate-200 rounded-xl">
          <FileText size={40} className="opacity-30" />
          <p>No invoices yet.</p>
          <button onClick={openNew} className="mt-2 text-sm text-brand-dark font-medium hover:underline">
            Create your first invoice →
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-3">Number</th>
                <th className="text-left px-4 py-3">Customer</th>
                <th className="text-right px-4 py-3">Total</th>
                <th className="text-left px-4 py-3">Due</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-right px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map(inv => (
                <InvoiceRow
                  key={inv.id}
                  inv={inv}
                  onEdit={() => openEdit(inv)}
                  onDuplicate={() => duplicate(inv)}
                  onDelete={() => del(inv)}
                  onReload={load}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editor.open && (
        <InvoiceEditor
          editing={editor.editing}
          brandingDefaults={brandingDefaults}
          defaultCurrency={defaultCurrency}
          onClose={() => setEditor({ open: false, editing: null })}
          onSaved={() => { setEditor({ open: false, editing: null }); load(); }}
          onBrandingSaved={(b) => setBrandingDefaults(b)}
        />
      )}
    </div>
  );
}

// ── list row ────────────────────────────────────────────────────────────────

function InvoiceRow({
  inv, onEdit, onDuplicate, onDelete, onReload,
}: {
  inv: Invoice;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onReload: () => void | Promise<void>;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState({ top: 0, right: 0 });
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!menuRef.current?.contains(e.target as Node) &&
          !triggerRef.current?.contains(e.target as Node)) setMenuOpen(false);
    }
    if (menuOpen) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [menuOpen]);

  function openMenu() {
    if (triggerRef.current) {
      const r = triggerRef.current.getBoundingClientRect();
      setMenuPos({ top: r.bottom + 4, right: window.innerWidth - r.right });
    }
    setMenuOpen(m => !m);
  }

  async function setStatus(s: string) {
    await invoicesApi.setStatus(inv.id, s);
    await onReload();
  }

  const st = inv.status || "draft";

  // Status transitions available from each state
  const transitions: Array<{ status: string; label: string; icon: React.ReactNode }> = [
    ...(st !== "sent"      && st !== "paid" && st !== "cancelled" ? [{ status: "sent",      label: "Mark as sent",     icon: <Share2 size={14} /> }] : []),
    ...(st !== "viewed"    && st !== "paid" && st !== "cancelled" && st !== "draft" ? [{ status: "viewed",    label: "Mark as viewed",   icon: <Eye size={14} /> }] : []),
    ...(st !== "paid"      && st !== "cancelled"                                    ? [{ status: "paid",      label: "Mark as paid",     icon: <Check size={14} /> }] : []),
    ...(st !== "partial"   && st !== "paid" && st !== "cancelled" && st !== "draft" ? [{ status: "partial",   label: "Mark as partial",  icon: <DollarSign size={14} /> }] : []),
    ...(st !== "overdue"   && st !== "paid" && st !== "cancelled"                   ? [{ status: "overdue",   label: "Mark as overdue",  icon: <RefreshCw size={14} /> }] : []),
    ...(st !== "cancelled"                                                          ? [{ status: "cancelled", label: "Cancel invoice",   icon: <X size={14} /> }] : []),
    ...(st === "cancelled"                                                          ? [{ status: "draft",     label: "Reopen as draft",  icon: <FileText size={14} /> }] : []),
  ];

  return (
    <tr className="hover:bg-slate-50 transition-colors cursor-pointer" onClick={onEdit}>
      <td className="px-4 py-3 font-mono font-medium text-brand-dark">{inv.number}</td>
      <td className="px-4 py-3">
        <p className="font-medium text-slate-800">{inv.customer_name || "—"}</p>
        <p className="text-slate-400 text-xs">{inv.customer_email || inv.customer_phone || ""}</p>
      </td>
      <td className="px-4 py-3 text-right font-semibold text-slate-800">
        {inv.currency} {(inv.total || 0).toLocaleString()}
      </td>
      <td className="px-4 py-3 text-slate-500">{inv.due_date ? new Date(inv.due_date).toLocaleDateString() : "—"}</td>
      <td className="px-4 py-3">
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_COLOR[inv.status || "draft"]}`}>
          {inv.status}
        </span>
      </td>
      <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-end gap-2 relative">
          <button onClick={onEdit} className="text-slate-400 hover:text-brand-dark transition-colors" title="Edit">
            <Pencil size={15} />
          </button>
          <div>
            <button ref={triggerRef} onClick={openMenu} className="text-slate-400 hover:text-slate-700 transition-colors" title="More">
              <MoreVertical size={16} />
            </button>
            {menuOpen && (
              <div
                ref={menuRef}
                style={{ position: "fixed", top: menuPos.top, right: menuPos.right, zIndex: 9999 }}
                className="bg-white border border-slate-200 rounded-lg shadow-xl w-52 py-1 text-sm"
              >
                {transitions.length > 0 && (
                  <>
                    <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Change status</div>
                    {transitions.map(t => (
                      <MenuItem key={t.status} onClick={() => { setMenuOpen(false); setStatus(t.status); }} icon={t.icon} label={t.label} />
                    ))}
                    <div className="border-t border-slate-100 my-1" />
                  </>
                )}
                <MenuItem onClick={() => { setMenuOpen(false); onDuplicate(); }} icon={<CopyPlus size={14} />} label="Duplicate" />
                <MenuItem onClick={() => { setMenuOpen(false); onDelete(); }} icon={<Trash2 size={14} />} label="Delete" danger />
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  );
}

function MenuItem({ onClick, icon, label, danger }: { onClick: () => void; icon: React.ReactNode; label: string; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-slate-50 ${danger ? "text-red-600" : "text-slate-700"}`}
    >
      {icon}{label}
    </button>
  );
}

function KpiCard({ label, value, accent }: { label: string; value: string; accent: "slate" | "green" | "amber" | "violet" }) {
  const tone: Record<string, string> = {
    slate:  "border-slate-200",
    green:  "border-green-200 bg-green-50/30",
    amber:  "border-amber-200 bg-amber-50/30",
    violet: "border-violet-200 bg-violet-50/30",
  };
  return (
    <div className={`bg-white rounded-xl border p-4 ${tone[accent]}`}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-lg font-bold text-slate-800 mt-1 truncate">{value}</p>
    </div>
  );
}

// ── editor ──────────────────────────────────────────────────────────────────

type Form = ReturnType<typeof emptyForm>;

function InvoiceEditor({
  editing, brandingDefaults, defaultCurrency, onClose, onSaved, onBrandingSaved,
}: {
  editing: Invoice | null;
  brandingDefaults: Branding;
  defaultCurrency: string;
  onClose: () => void;
  onSaved: () => void;
  onBrandingSaved: (b: Branding) => void;
}) {
  const [form, setForm] = useState<Form>(() => {
    if (editing) {
      return {
        customer_id: (editing as unknown as { customer_id?: string }).customer_id,
        customer_name: editing.customer_name || "",
        customer_phone: editing.customer_phone || "",
        customer_email: editing.customer_email || "",
        customer_address: editing.customer_address || "",
        items: (editing.items && editing.items.length ? editing.items : [{ ...EMPTY_ITEM }]).map(calcItem),
        tax_rate: editing.tax_rate || 0,
        discount: editing.discount || 0,
        currency: editing.currency || defaultCurrency,
        issue_date: editing.issue_date || new Date().toISOString().slice(0, 10),
        due_date: editing.due_date || "",
        notes: editing.notes || "",
        terms: editing.terms || "",
        po_number: editing.po_number || "",
        status: editing.status || "draft",
        branding: editing.branding || brandingDefaults,
      };
    }
    return emptyForm({ branding: brandingDefaults, currency: defaultCurrency });
  });
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(editing?.id || null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  useEffect(() => {
    customersApi.list().then(setCustomers).catch(() => { /* ignore */ });
  }, []);
  const [shareToken, setShareToken] = useState<string | undefined>(editing?.share_token);
  const [tab, setTab] = useState<"details" | "branding" | "share">("details");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [showAi, setShowAi] = useState(false);
  const [savedBranding, setSavedBranding] = useState(false);

  // ── derived totals ────────────────────────────────────────────────────────
  const subtotal = useMemo(() => form.items.reduce((s, i) => s + Number(i.qty || 0) * Number(i.unit_price || 0), 0), [form.items]);
  const discount_amount = useMemo(() => +(subtotal * ((form.discount || 0) / 100)).toFixed(2), [subtotal, form.discount]);
  const tax_amount = useMemo(() => +((Math.max(subtotal - discount_amount, 0)) * ((form.tax_rate || 0) / 100)).toFixed(2), [subtotal, discount_amount, form.tax_rate]);
  const total = useMemo(() => +(Math.max(subtotal - discount_amount, 0) + tax_amount).toFixed(2), [subtotal, discount_amount, tax_amount]);

  const previewData: InvoiceData = {
    number: editing?.number || "INV-PREVIEW",
    customer_name: form.customer_name,
    customer_phone: form.customer_phone,
    customer_email: form.customer_email,
    customer_address: form.customer_address,
    items: form.items,
    subtotal, discount: form.discount, discount_amount,
    tax_rate: form.tax_rate, tax_amount,
    total,
    amount_paid: editing?.amount_paid,
    currency: form.currency,
    issue_date: form.issue_date,
    due_date: form.due_date,
    notes: form.notes,
    terms: form.terms,
    po_number: form.po_number,
    status: form.status,
    branding: form.branding,
  };

  // ── item ops ──────────────────────────────────────────────────────────────
  function updateItem(idx: number, patch: Partial<InvoiceItem>) {
    setForm(f => {
      const items = f.items.slice();
      items[idx] = calcItem({ ...items[idx], ...patch });
      return { ...f, items };
    });
  }
  function addItem() { setForm(f => ({ ...f, items: [...f.items, { ...EMPTY_ITEM }] })); }
  function removeItem(idx: number) {
    setForm(f => ({ ...f, items: f.items.length === 1 ? [{ ...EMPTY_ITEM }] : f.items.filter((_, i) => i !== idx) }));
  }

  function patchBranding(p: Partial<Branding>) {
    setForm(f => ({ ...f, branding: { ...f.branding, ...p } }));
  }

  // ── save ──────────────────────────────────────────────────────────────────
  async function save(closeAfter = true) {
    setSaving(true);
    try {
      const payload = {
        customer_name: form.customer_name,
        customer_phone: form.customer_phone,
        customer_email: form.customer_email,
        customer_address: form.customer_address,
        items: form.items.map(i => ({
          name: i.name, description: i.description || "",
          qty: Number(i.qty) || 0, unit_price: Number(i.unit_price) || 0,
          amount: Number(i.amount) || 0,
        })),
        tax_rate: Number(form.tax_rate) || 0,
        discount: Number(form.discount) || 0,
        currency: form.currency,
        issue_date: form.issue_date || null,
        due_date: form.due_date || null,
        notes: form.notes, terms: form.terms, po_number: form.po_number,
        status: form.status,
        branding: form.branding,
      };
      if (savedId) {
        const updated = await invoicesApi.update(savedId, payload) as unknown as Invoice;
        setShareToken(updated.share_token);
      } else {
        const created = await invoicesApi.create(payload) as unknown as Invoice;
        setSavedId(created.id);
        setShareToken(created.share_token);
      }
      if (closeAfter) onSaved();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to save invoice");
    } finally {
      setSaving(false);
    }
  }

  // ── AI ────────────────────────────────────────────────────────────────────
  async function runAi() {
    if (!aiPrompt.trim()) return;
    setAiBusy(true);
    try {
      const out = await invoicesApi.aiDraft({
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

  // ── branding save as default ──────────────────────────────────────────────
  async function saveBrandingDefault() {
    const saved = await invoicesApi.saveBranding(form.branding as Record<string, unknown>) as unknown as Branding;
    onBrandingSaved(saved);
    setSavedBranding(true);
    setTimeout(() => setSavedBranding(false), 1800);
  }

  // ── logo upload ──────────────────────────────────────────────────────────
  const fileRef = useRef<HTMLInputElement | null>(null);
  async function onLogoFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]; if (!file) return;
    if (file.size > 4 * 1024 * 1024) { alert("Logo must be under 4MB"); return; }
    const dataUrl = await shrinkImageToDataUrl(file, 256, 0.9);
    patchBranding({ logo_url: dataUrl });
    e.target.value = "";
  }

  // ── share helpers ────────────────────────────────────────────────────────
  const shareUrl = useMemo(() => {
    if (!shareToken) return "";
    if (typeof window === "undefined") return "";
    return `${window.location.origin}/invoice/${shareToken}`;
  }, [shareToken]);

  const [copied, setCopied] = useState(false);
  async function copyLink() {
    if (!shareUrl) return;
    try { await navigator.clipboard.writeText(shareUrl); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { /* ignore */ }
  }

  async function rotateShare() {
    if (!savedId) return;
    if (!confirm("Rotate share link? The previous link will stop working.")) return;
    const r = await invoicesApi.rotateShare(savedId);
    setShareToken(r.share_token);
  }

  function whatsappHref() {
    const phone = (form.customer_phone || "").replace(/[^\d]/g, "");
    const text = encodeURIComponent(
      `Hi ${form.customer_name || "there"}, here is your invoice ${editing?.number || ""} for ${form.currency} ${total.toLocaleString()}.\n${shareUrl}`
    );
    return phone ? `https://wa.me/${phone}?text=${text}` : `https://wa.me/?text=${text}`;
  }
  function emailHref() {
    const to = encodeURIComponent(form.customer_email || "");
    const subject = encodeURIComponent(`Invoice ${editing?.number || ""} from ${form.branding.from_name || "us"}`);
    const body = encodeURIComponent(
      `Hi ${form.customer_name || "there"},\n\nYour invoice ${editing?.number || ""} for ${form.currency} ${total.toLocaleString()} is ready.\n\nView online: ${shareUrl}\n\nThanks!`
    );
    return `mailto:${to}?subject=${subject}&body=${body}`;
  }

  const previewRef = useRef<HTMLDivElement | null>(null);
  function printNow() {
    // Clone the preview into a clean new window and print there — avoids
    // modal clipping, overflow:hidden ancestors, and viewport-fixed layout
    // issues that `@media print` can't reach.
    const node = previewRef.current?.querySelector<HTMLElement>(".invoice-preview-root") ?? null;
    printNode(node, `Invoice ${editing?.number || ""}`.trim());
  }

  // Esc to close
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <div
      className="no-print fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-2 sm:p-4 print:static print:bg-white print:p-0 print:backdrop-blur-0"
      onClick={onClose}
    >

      <div
        className="bg-slate-50 rounded-xl shadow-2xl overflow-hidden flex flex-col w-full max-w-7xl h-[95vh] print:bg-white print:rounded-none print:shadow-none print:max-w-none print:h-auto"
        onClick={e => e.stopPropagation()}
      >

      {/* Top bar */}
      <div className="no-print h-14 border-b bg-white flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={onClose} className="p-2 -ml-2 text-slate-500 hover:text-slate-800" title="Back">
            <ArrowLeft size={18} />
          </button>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-800 truncate">
              {editing ? `Invoice ${editing.number}` : "New invoice"}
            </div>
            <div className="text-xs text-slate-400 truncate">
              {form.customer_name || "Untitled customer"} · {form.currency} {total.toLocaleString()}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAi(true)}
            className="hidden sm:inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-violet-200 text-violet-700 bg-violet-50 hover:bg-violet-100"
          >
            <Sparkles size={14} /> AI assist
          </button>
          <button
            onClick={printNow}
            className="hidden sm:inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50"
            title="Print / save as PDF"
          >
            <Printer size={14} /> Print
          </button>
          <button
            onClick={() => save(true)}
            disabled={saving}
            className="inline-flex items-center gap-1.5 text-sm px-4 py-1.5 rounded-lg bg-brand-dark text-white hover:bg-brand disabled:opacity-50 font-medium"
          >
            {saving ? "Saving…" : savedId ? "Save" : "Create invoice"}
          </button>
          {savedId && (
            <button
              onClick={() => save(false)}
              disabled={saving}
              className="hidden md:inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50"
              title="Save without closing"
            >
              Save &amp; keep editing
            </button>
          )}
        </div>
      </div>

      {/* Body: split editor / preview */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-5 overflow-hidden">
        {/* Editor pane */}
        <div className="no-print col-span-1 lg:col-span-2 border-r bg-white overflow-y-auto">
          {/* Tabs */}
          <div className="flex items-center gap-1 px-2 border-b bg-slate-50 sticky top-0 z-10">
            {[
              { id: "details",  label: "Details",  icon: FileText },
              { id: "branding", label: "Branding", icon: Palette },
              { id: "share",    label: "Share",    icon: Share2   },
            ].map(t => {
              const Icon = t.icon;
              return (
                <button key={t.id} onClick={() => setTab(t.id as typeof tab)}
                  className={`flex items-center gap-1.5 text-sm px-3 py-2 border-b-2 -mb-px ${
                    tab === t.id ? "border-brand-dark text-brand-dark font-medium"
                                  : "border-transparent text-slate-500 hover:text-slate-800"
                  }`}
                >
                  <Icon size={14} />{t.label}
                </button>
              );
            })}
          </div>

          <div className="p-5 space-y-5">
            {tab === "details" && (
              <DetailsTab
                form={form} setForm={setForm}
                customers={customers}
                updateItem={updateItem} addItem={addItem} removeItem={removeItem}
                subtotal={subtotal} discount_amount={discount_amount}
                tax_amount={tax_amount} total={total}
                onOpenAi={() => setShowAi(true)}
              />
            )}

            {tab === "branding" && (
              <BrandingTab
                branding={form.branding}
                patch={patchBranding}
                onLogoFile={onLogoFile}
                fileRef={fileRef}
                onSaveDefault={saveBrandingDefault}
                saved={savedBranding}
              />
            )}

            {tab === "share" && (
              <ShareTab
                savedId={savedId}
                shareUrl={shareUrl}
                copyLink={copyLink}
                copied={copied}
                rotateShare={rotateShare}
                waHref={whatsappHref()}
                emailHref={emailHref()}
                printNow={printNow}
                onSave={() => save(false)}
              />
            )}
          </div>
        </div>

        {/* Preview pane */}
        <div ref={previewRef} className="col-span-1 lg:col-span-3 overflow-y-auto bg-slate-100 p-6 lg:p-10">
          <InvoicePreview data={previewData} />
        </div>
      </div>

      {/* AI modal */}
      {showAi && (
        <div className="no-print fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4" onClick={e => { e.stopPropagation(); setShowAi(false); }}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="p-5 border-b flex items-center justify-between">
              <h3 className="text-base font-semibold text-slate-800 flex items-center gap-2">
                <Sparkles size={16} className="text-violet-600" /> AI invoice assistant
              </h3>
              <button onClick={() => setShowAi(false)} className="text-slate-400 hover:text-slate-700"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-sm text-slate-600">
                Describe the work and we&apos;ll turn it into line items. Prices in <strong>{form.currency}</strong>.
              </p>
              <textarea
                value={aiPrompt}
                onChange={e => setAiPrompt(e.target.value)}
                rows={5}
                placeholder="e.g. 3 hours of web consulting for Acme Ltd at 120 an hour, plus a 500 setup fee and a 10% discount."
                className="w-full border border-slate-200 rounded-lg p-3 text-sm"
              />
              <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                {[
                  "2 cakes for a birthday party + delivery 500",
                  "Haircut + beard trim + color treatment",
                  "Branding package: logo, business card, social kit",
                ].map(p => (
                  <button key={p} onClick={() => setAiPrompt(p)}
                    className="px-2 py-1 rounded-full border border-slate-200 hover:border-violet-400 hover:text-violet-700">
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <div className="p-5 border-t flex justify-end gap-2">
              <button onClick={() => setShowAi(false)} className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900">Cancel</button>
              <button
                onClick={runAi}
                disabled={aiBusy || !aiPrompt.trim()}
                className="px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                <Sparkles size={14} /> {aiBusy ? "Drafting…" : "Draft items"}
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

// ── tabs ────────────────────────────────────────────────────────────────────

const DIAL_CODES: Record<string, string> = {
  KE:"+254",TZ:"+255",UG:"+256",RW:"+250",ET:"+251",NG:"+234",GH:"+233",
  ZA:"+27", EG:"+20", MA:"+212",SN:"+221",CI:"+225",CM:"+237",ZM:"+260",
  ZW:"+263",AE:"+971",SA:"+966",IN:"+91", PK:"+92", BD:"+880",
  ID:"+62", PH:"+63", MY:"+60", TH:"+66", VN:"+84",
  BR:"+55", MX:"+52", AR:"+54", CO:"+57", CL:"+56", PE:"+51",
  US:"+1",  CA:"+1",  GB:"+44", DE:"+49", FR:"+33", AU:"+61",
};

function getDialCode(): string {
  try {
    const u = getUser();
    const code = (u?.country_code as string) || ((u?.settings as Record<string,unknown>)?.country_code as string) || "";
    return DIAL_CODES[code.toUpperCase()] || "+";
  } catch { return "+"; }
}

function DetailsTab({
  form, setForm, customers, updateItem, addItem, removeItem, subtotal, discount_amount, tax_amount, total, onOpenAi,
}: {
  form: Form;
  setForm: React.Dispatch<React.SetStateAction<Form>>;
  customers: Customer[];
  updateItem: (idx: number, patch: Partial<InvoiceItem>) => void;
  addItem: () => void;
  removeItem: (idx: number) => void;
  subtotal: number; discount_amount: number; tax_amount: number; total: number;
  onOpenAi: () => void;
}) {
  const phonePlaceholder = useMemo(() => `${getDialCode()}…`, []);
  const fmt = (n: number) => `${form.currency} ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return (
    <>
      <Section title="Customer">
        <CustomerPicker
          customers={customers}
          value={form.customer_name}
          onChange={v => setForm(f => ({ ...f, customer_name: v, customer_id: undefined }))}
          onPick={c => setForm(f => ({
            ...f,
            customer_id: c.id,
            customer_name: c.name || "",
            customer_phone: c.phone_number || f.customer_phone,
            customer_email: c.email || f.customer_email,
          }))}
        />
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Input label="Email" value={form.customer_email} onChange={v => setForm(f => ({ ...f, customer_email: v }))} placeholder="jane@acme.co" />
          <Input label="Phone" value={form.customer_phone} onChange={v => setForm(f => ({ ...f, customer_phone: v }))} placeholder={phonePlaceholder} />
          <Input label="PO #"  value={form.po_number}       onChange={v => setForm(f => ({ ...f, po_number: v }))}       placeholder="Optional" />
          <div />
          <Textarea label="Billing address" value={form.customer_address} onChange={v => setForm(f => ({ ...f, customer_address: v }))} className="col-span-2" rows={2} />
        </div>
      </Section>

      <Section
        title="Line items"
        actions={
          <button onClick={onOpenAi} className="text-xs text-violet-700 hover:text-violet-800 inline-flex items-center gap-1">
            <Sparkles size={12} /> AI assist
          </button>
        }
      >
        {/* Column headers — matches the grid below: 4 | 2 | 3 | 2 | 1 = 12 */}
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
                  value={item.name}
                  onChange={e => updateItem(idx, { name: e.target.value })}
                  placeholder="Item / service"
                />
                <input
                  className="mt-1 w-full border border-slate-100 rounded px-2 py-1 text-xs text-slate-600"
                  value={item.description || ""}
                  onChange={e => updateItem(idx, { description: e.target.value })}
                  placeholder="Optional description"
                />
              </div>
              <input
                type="number" min="0" step="1"
                className="col-span-3 md:col-span-2 border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                value={item.qty === 0 ? "" : item.qty}
                onFocus={e => e.target.select()}
                onChange={e => updateItem(idx, { qty: e.target.value === "" ? 0 : +e.target.value })}
                placeholder="0"
              />
              <input
                type="number" min="0" step="0.01"
                className="col-span-5 md:col-span-3 border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                value={item.unit_price === 0 ? "" : item.unit_price}
                onFocus={e => e.target.select()}
                onChange={e => updateItem(idx, { unit_price: e.target.value === "" ? 0 : +e.target.value })}
                placeholder="0.00"
              />
              <div className="col-span-3 md:col-span-2 text-xs font-medium text-slate-700 text-right self-center tabular-nums">
                {item.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <button
                onClick={() => removeItem(idx)}
                className="col-span-1 text-slate-300 hover:text-red-500 flex justify-center pt-1.5"
                title="Remove"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
        <button onClick={addItem} className="mt-2 text-xs text-brand-dark hover:underline inline-flex items-center gap-1">
          <Plus size={12} /> Add item
        </button>
      </Section>

      <Section title="Totals">
        <div className="grid grid-cols-3 gap-3">
          <Input label="Tax %"      type="number" value={String(form.tax_rate)} onChange={v => setForm(f => ({ ...f, tax_rate: +v }))} />
          <Input label="Discount %" type="number" value={String(form.discount)} onChange={v => setForm(f => ({ ...f, discount: +v }))} />
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Currency</label>
            <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.currency}
              onChange={e => setForm(f => ({ ...f, currency: e.target.value }))}>
              {CURRENCIES.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-4 bg-slate-50 rounded-lg p-3 text-sm space-y-1">
          <Row label="Subtotal" value={fmt(subtotal)} />
          {form.discount ? <Row label={`Discount (${form.discount}%)`} value={`− ${fmt(discount_amount)}`} /> : null}
          {form.tax_rate ? <Row label={`Tax (${form.tax_rate}%)`} value={fmt(tax_amount)} /> : null}
          <div className="border-t border-slate-200 pt-1 mt-1">
            <Row label="Total" value={fmt(total)} bold />
          </div>
        </div>
      </Section>

      <Section title="Dates & status">
        <div className="grid grid-cols-3 gap-3">
          <Input label="Issue date" type="date" value={form.issue_date} onChange={v => setForm(f => ({ ...f, issue_date: v }))} />
          <Input label="Due date"   type="date" value={form.due_date}   onChange={v => setForm(f => ({ ...f, due_date: v }))} />
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Status</label>
            <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.status}
              onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
              {STATUSES.map(s => <option key={s} value={s} className="capitalize">{s}</option>)}
            </select>
          </div>
        </div>
      </Section>

      <Section title="Notes & terms">
        <Textarea label="Notes (visible on invoice)" value={form.notes} onChange={v => setForm(f => ({ ...f, notes: v }))} rows={2} />
        <div className="h-3" />
        <Textarea label="Terms"                        value={form.terms} onChange={v => setForm(f => ({ ...f, terms: v }))} rows={2} />
      </Section>
    </>
  );
}

function BrandingTab({
  branding, patch, onLogoFile, fileRef, onSaveDefault, saved,
}: {
  branding: Branding;
  patch: (p: Partial<Branding>) => void;
  onLogoFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  fileRef: React.RefObject<HTMLInputElement | null>;
  onSaveDefault: () => void;
  saved: boolean;
}) {
  return (
    <>
      <Section title="Logo">
        <div className="flex items-center gap-4">
          <div className="w-20 h-20 rounded-lg border-2 border-dashed border-slate-200 bg-slate-50 flex items-center justify-center overflow-hidden">
            {branding.logo_url ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img src={branding.logo_url} alt="Logo" className="w-full h-full object-cover" />
            ) : (
              <ImageIcon className="text-slate-300" size={24} />
            )}
          </div>
          <div className="flex flex-col gap-2">
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onLogoFile} />
            <button onClick={() => fileRef.current?.click()}
              className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 hover:border-brand-dark hover:text-brand-dark inline-flex items-center gap-2">
              <ImageIcon size={14} /> Upload logo
            </button>
            {branding.logo_url && (
              <button onClick={() => patch({ logo_url: "" })} className="text-xs text-red-600 hover:underline text-left">
                Remove logo
              </button>
            )}
            <p className="text-xs text-slate-400">PNG / JPG / SVG up to 4MB. Auto-resized.</p>
          </div>
        </div>
      </Section>

      <Section title="Colors">
        <div className="grid grid-cols-2 gap-3">
          <ColorInput label="Accent color" value={branding.accent_color || "#0f766e"} onChange={v => patch({ accent_color: v })} />
          <ColorInput label="Text color"   value={branding.text_color   || "#0f172a"} onChange={v => patch({ text_color: v })} />
        </div>
      </Section>

      <Section title="Template">
        <div className="grid grid-cols-2 gap-2">
          {TEMPLATES.map(t => (
            <button key={t.id} onClick={() => patch({ template: t.id })}
              className={`text-left p-3 rounded-lg border transition ${
                (branding.template || "modern") === t.id
                  ? "border-brand-dark bg-brand-dark/5 ring-1 ring-brand-dark/20"
                  : "border-slate-200 hover:border-slate-300"
              }`}>
              <div className="text-sm font-medium text-slate-800">{t.label}</div>
              <div className="text-xs text-slate-500 mt-0.5">{t.hint}</div>
            </button>
          ))}
        </div>
      </Section>

      <Section title="Company details">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Business name" value={branding.from_name || ""}    onChange={v => patch({ from_name: v })} />
          <Input label="Email"         value={branding.from_email || ""}   onChange={v => patch({ from_email: v })} />
          <Input label="Phone"         value={branding.from_phone || ""}   onChange={v => patch({ from_phone: v })} />
          <Input label="Address"       value={branding.from_address || ""} onChange={v => patch({ from_address: v })} />
        </div>
      </Section>

      <Section title="Payment instructions">
        <Textarea
          label="Shown on every invoice"
          value={branding.payment_instructions || ""}
          onChange={v => patch({ payment_instructions: v })}
          rows={4}
          placeholder={"M-Pesa: 1234567\nBank: KCB 000123456"}
        />
      </Section>

      <Section title="Footer">
        <Input
          label="Thank-you / legal line"
          value={branding.footer || ""}
          onChange={v => patch({ footer: v })}
          placeholder="Thank you for your business!"
        />
      </Section>

      <div className="flex justify-end">
        <button
          onClick={onSaveDefault}
          className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 hover:border-brand-dark hover:text-brand-dark inline-flex items-center gap-2"
        >
          {saved ? <><Check size={14} /> Saved as default</> : <>Save as default for future invoices</>}
        </button>
      </div>
    </>
  );
}

function ShareTab({
  savedId, shareUrl, copyLink, copied, rotateShare, waHref, emailHref, printNow, onSave,
}: {
  savedId: string | null;
  shareUrl: string;
  copyLink: () => void;
  copied: boolean;
  rotateShare: () => void;
  waHref: string;
  emailHref: string;
  printNow: () => void;
  onSave: () => void;
}) {
  if (!savedId) {
    return (
      <div className="text-center text-slate-500 text-sm space-y-3 py-8">
        <Share2 className="mx-auto text-slate-300" size={36} />
        <p>Save the invoice first to get a shareable link.</p>
        <button onClick={onSave} className="px-4 py-2 rounded-lg bg-brand-dark text-white text-sm font-medium hover:bg-brand">
          Save now
        </button>
      </div>
    );
  }
  return (
    <>
      <Section title="Public link">
        <p className="text-xs text-slate-500 mb-2">
          Anyone with this link can view the invoice — no login required.
        </p>
        <div className="flex gap-2 items-stretch">
          <input readOnly value={shareUrl} className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm bg-slate-50 font-mono" />
          <button onClick={copyLink}
            className="px-3 py-2 rounded-lg bg-brand-dark text-white text-sm font-medium hover:bg-brand inline-flex items-center gap-1.5">
            {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy</>}
          </button>
        </div>
        <button onClick={rotateShare} className="mt-2 text-xs text-slate-500 hover:text-red-600 inline-flex items-center gap-1">
          <RefreshCw size={12} /> Rotate link
        </button>
      </Section>

      <Section title="Send now">
        <div className="grid grid-cols-1 gap-2">
          <a href={waHref} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-green-200 bg-green-50 text-green-800 hover:bg-green-100">
            <MessageCircle size={16} /> Send on WhatsApp
          </a>
          <a href={emailHref}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100">
            <Mail size={16} /> Send by email
          </a>
          <button onClick={printNow}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-slate-200 hover:bg-slate-50">
            <Download size={16} /> Download / Print as PDF
          </button>
        </div>
      </Section>

      <Section title="Quick link preview">
        <a href={shareUrl} target="_blank" rel="noreferrer" className="text-sm text-brand-dark hover:underline inline-flex items-center gap-1.5">
          <LinkIcon size={14} /> Open public view →
        </a>
      </Section>
    </>
  );
}

// ── tiny UI ─────────────────────────────────────────────────────────────────

function Section({ title, children, actions }: { title: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</h3>
        {actions}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Input({ label, value, onChange, type = "text", placeholder, className = "" }:
  { label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string; className?: string }) {
  return (
    <div className={className}>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/30" />
    </div>
  );
}

function Textarea({ label, value, onChange, rows = 3, placeholder, className = "" }:
  { label: string; value: string; onChange: (v: string) => void; rows?: number; placeholder?: string; className?: string }) {
  return (
    <div className={className}>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <textarea value={value} onChange={e => onChange(e.target.value)} rows={rows} placeholder={placeholder}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/30" />
    </div>
  );
}

function CustomerPicker({
  customers, value, onChange, onPick,
}: {
  customers: Customer[];
  value: string;
  onChange: (v: string) => void;
  onPick: (c: Customer) => void;
}) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function h(e: MouseEvent) { if (!boxRef.current?.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const q = value.trim().toLowerCase();
  const matches = (q
    ? customers.filter(c =>
        (c.name || "").toLowerCase().includes(q) ||
        (c.phone_number || "").includes(q) ||
        (c.email || "").toLowerCase().includes(q))
    : customers
  ).slice(0, 8);

  return (
    <div ref={boxRef} className="relative">
      <label className="block text-xs font-medium text-slate-600 mb-1">Customer</label>
      <input
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="Search by name, phone or email…"
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-dark/30"
      />
      {open && matches.length > 0 && (
        <div className="absolute z-20 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
          {matches.map(c => (
            <button
              key={c.id}
              type="button"
              onClick={() => { onPick(c); setOpen(false); }}
              className="w-full text-left px-3 py-2 hover:bg-slate-50 border-b last:border-b-0 border-slate-100"
            >
              <div className="text-sm font-medium text-slate-800 truncate">{c.name || "(unnamed)"}</div>
              <div className="text-xs text-slate-500 truncate">
                {[c.phone_number, c.email].filter(Boolean).join(" · ") || "No contact info"}
              </div>
            </button>
          ))}
        </div>
      )}
      {open && q && matches.length === 0 && (
        <div className="absolute z-20 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-xs text-slate-500">
          No match — &quot;{value}&quot; will be used as a one-off customer.
        </div>
      )}
    </div>
  );
}

const COLOR_PRESETS = [
  "#0f766e", "#0ea5e9", "#2563eb", "#4f46e5", "#7c3aed",
  "#db2777", "#e11d48", "#ea580c", "#ca8a04", "#16a34a",
  "#0f172a", "#475569",
];

function ColorInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
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
        {COLOR_PRESETS.map(c => (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            title={c}
            className={`h-5 w-5 rounded-full border transition ${
              value.toLowerCase() === c.toLowerCase() ? "border-slate-900 ring-2 ring-slate-300" : "border-slate-200 hover:scale-110"
            }`}
            style={{ background: c }}
          />
        ))}
      </div>
    </div>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={`flex justify-between ${bold ? "font-bold text-slate-800" : "text-slate-600"}`}>
      <span>{label}</span><span>{value}</span>
    </div>
  );
}
