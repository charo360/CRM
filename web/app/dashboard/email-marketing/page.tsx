"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Mail, Plus, Send, Trash2, BarChart2, Settings,
  Loader2, CheckCircle2, Clock, FileText, RefreshCw, X,
  Zap, Users, AlertCircle, Eye, Play, Sparkles, Trash,
  BookOpen, Save, ImageIcon,
} from "lucide-react";
import { getToken } from "@/lib/auth";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { EMAIL_TEMPLATES, EmailTemplate, TemplateVar, applyVars } from "./templates";

// ── Brand green tokens ────────────────────────────────────────────────────────
const G = {
  bg:     "bg-[#009b3a]",
  hover:  "hover:bg-[#007a2e]",
  text:   "text-[#009b3a]",
  border: "border-[#009b3a]",
  ring:   "focus:ring-[#009b3a]",
  light:  "bg-[#f0fdf4]",
  lb:     "border-[#bbf7d0]",
  badge:  "bg-[#dcfce7] text-[#166534]",
  icon:   "bg-[#009b3a]",
  sel:    "border-[#009b3a] bg-[#f0fdf4]",
  tab:    "text-[#009b3a]",
};

// ── Types ─────────────────────────────────────────────────────────────────────

type Campaign = {
  id: string;
  name: string;
  subject: string;
  status: "draft" | "scheduled" | "sending" | "sent" | "partial";
  recipients: number;
  stats: { sent: number; failed: number };
  sent_at: string;
  created_at: string;
  body_html?: string;
};

type Stats = {
  campaigns: { total: number; sent: number; draft: number; scheduled: number };
  emails_sent: number;
  emails_failed: number;
};

type EmailSettings = {
  provider: string;
  from_name: string;
  from_email: string;
  credentials: Record<string, string>;
};

type SavedTemplate = {
  id: string;
  name: string;
  category: string;
  subject: string;
  body_html: string;
  created_at: string;
};

type Tab = "campaigns" | "library" | "settings";

// ── API helpers ───────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json();
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { method: "POST", headers: authHeaders(), body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json();
}

async function apiDelete(path: string) {
  const r = await fetch(`${BASE}${path}`, { method: "DELETE", headers: authHeaders() });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Campaign["status"] }) {
  const map: Record<string, { label: string; cls: string; icon: React.ReactNode }> = {
    draft:     { label: "Draft",     cls: "bg-slate-100 text-slate-600",   icon: <FileText size={11} /> },
    scheduled: { label: "Scheduled", cls: "bg-blue-100 text-blue-700",     icon: <Clock size={11} /> },
    sending:   { label: "Sending…",  cls: "bg-yellow-100 text-yellow-700", icon: <Loader2 size={11} className="animate-spin" /> },
    sent:      { label: "Sent",      cls: "bg-green-100 text-green-700",   icon: <CheckCircle2 size={11} /> },
    partial:   { label: "Partial",   cls: "bg-orange-100 text-orange-700", icon: <AlertCircle size={11} /> },
  };
  const s = map[status] ?? map.draft;
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium", s.cls)}>
      {s.icon}{s.label}
    </span>
  );
}

// ── Email Preview Modal ───────────────────────────────────────────────────────

function EmailPreviewModal({ html, title, onClose }: { html: string; title: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[92vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 shrink-0">
          <div className="flex items-center gap-2">
            <Eye size={16} className={G.text} />
            <h2 className="text-base font-semibold text-slate-800 truncate max-w-xs">{title}</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-hidden bg-slate-100 p-4">
          <iframe
            srcDoc={html}
            sandbox="allow-same-origin"
            className="w-full h-full rounded-xl border border-slate-200 bg-white"
            style={{ minHeight: "60vh" }}
            title="Email preview"
          />
        </div>
      </div>
    </div>
  );
}

// ── Save To Library Modal ─────────────────────────────────────────────────────

function SaveToLibraryModal({
  html, defaultSubject, onClose, onSaved,
}: {
  html: string;
  defaultSubject: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Newsletter");
  const [subject, setSubject] = useState(defaultSubject);
  const [saving, setSaving] = useState(false);

  const CATS = ["Newsletter","Promotional","Seasonal","Onboarding","Retention","Growth","E-commerce","Transactional","Events","News","Feedback","Custom"];

  async function save() {
    if (!name.trim()) { toast.error("Template name is required"); return; }
    setSaving(true);
    try {
      await apiPost("/email-marketing/templates", { name: name.trim(), category, subject, body_html: html });
      toast.success("Template saved to library!");
      onSaved();
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Save size={16} className={G.text} />
            <h2 className="text-base font-semibold text-slate-800">Save to Library</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={20} /></button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Template name *</label>
            <input value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. Summer Flash Sale"
              className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Category</label>
            <select value={category} onChange={e => setCategory(e.target.value)}
              className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`}>
              {CATS.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Default subject</label>
            <input value={subject} onChange={e => setSubject(e.target.value)}
              placeholder="Subject line for this template"
              className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
          </div>
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-slate-100">
          <button onClick={onClose} className="flex-1 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={save} disabled={saving}
            className={`flex-1 py-2 ${G.bg} ${G.hover} text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50`}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            Save template
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Library Panel ─────────────────────────────────────────────────────────────

function MiniEmailPreview({ html }: { html: string }) {
  return (
    <div className="relative w-full h-36 overflow-hidden rounded-lg bg-white border border-slate-100">
      {html ? (
        <iframe
          srcDoc={html}
          sandbox="allow-same-origin"
          className="absolute top-0 left-0 border-none"
          style={{ width: "600px", height: "800px", transform: "scale(0.3)", transformOrigin: "top left", pointerEvents: "none" }}
          title="mini preview"
        />
      ) : (
        <div className="flex items-center justify-center h-full text-slate-300">
          <ImageIcon size={28} />
        </div>
      )}
    </div>
  );
}

function LibraryPanel({ onUseTemplate }: { onUseTemplate: (html: string, subject: string) => void }) {
  const [templates, setTemplates] = useState<SavedTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [preview, setPreview] = useState<SavedTemplate | null>(null);
  const [filterCat, setFilterCat] = useState("All");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet<{ templates: SavedTemplate[] }>("/email-marketing/templates");
      setTemplates(data.templates ?? []);
    } catch { toast.error("Failed to load template library"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function deleteTemplate(id: string) {
    setDeleting(id);
    try {
      await apiDelete(`/email-marketing/templates/${id}`);
      setTemplates(p => p.filter(t => t.id !== id));
      toast.success("Template deleted");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally { setDeleting(null); }
  }

  const categories = ["All", ...Array.from(new Set(templates.map(t => t.category)))];
  const filtered = filterCat === "All" ? templates : templates.filter(t => t.category === filterCat);

  return (
    <>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-800">Template Library</h2>
            <p className="text-sm text-slate-500 mt-0.5">Saved templates you can reuse across campaigns</p>
          </div>
          <button onClick={load} className="p-2 text-slate-400 hover:text-slate-600 transition-colors">
            <RefreshCw size={16} />
          </button>
        </div>

        {/* Category filter */}
        {categories.length > 1 && (
          <div className="flex flex-wrap gap-2">
            {categories.map(c => (
              <button key={c} onClick={() => setFilterCat(c)}
                className={cn(
                  "px-3 py-1 rounded-full text-xs font-medium border transition-colors",
                  filterCat === c
                    ? `${G.bg} text-white border-transparent`
                    : "border-slate-200 text-slate-600 hover:border-slate-300 bg-white"
                )}>
                {c}
              </button>
            ))}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className={`animate-spin ${G.text}`} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 flex flex-col items-center justify-center py-16 text-center">
            <div className={`w-16 h-16 ${G.light} rounded-2xl flex items-center justify-center mb-4`}>
              <BookOpen size={28} className={G.text} />
            </div>
            <h3 className="text-lg font-semibold text-slate-700 mb-1">No saved templates yet</h3>
            <p className="text-sm text-slate-400 max-w-xs">
              Create a campaign, apply a template or generate one with AI, then save it to your library for reuse.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map(tpl => (
              <div key={tpl.id} className="bg-white rounded-2xl border border-slate-200 overflow-hidden hover:shadow-md transition-shadow">
                <MiniEmailPreview html={tpl.body_html} />
                <div className="p-4">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="font-semibold text-slate-800 text-sm leading-tight truncate">{tpl.name}</div>
                    <span className={`shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full ${G.badge}`}>{tpl.category}</span>
                  </div>
                  {tpl.subject && (
                    <p className="text-xs text-slate-400 mb-3 truncate">Subject: {tpl.subject}</p>
                  )}
                  <div className="flex gap-2">
                    <button onClick={() => setPreview(tpl)}
                      className="flex-1 flex items-center justify-center gap-1 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 hover:bg-slate-50 transition-colors">
                      <Eye size={11} /> Preview
                    </button>
                    <button onClick={() => onUseTemplate(tpl.body_html, tpl.subject)}
                      className={`flex-1 flex items-center justify-center gap-1 py-1.5 ${G.bg} ${G.hover} text-white rounded-lg text-xs font-medium transition-colors`}>
                      <Play size={11} /> Use
                    </button>
                    <button onClick={() => deleteTemplate(tpl.id)} disabled={deleting === tpl.id}
                      className="p-1.5 text-slate-400 hover:text-red-500 transition-colors disabled:opacity-50">
                      {deleting === tpl.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {preview && (
        <EmailPreviewModal html={preview.body_html} title={preview.name} onClose={() => setPreview(null)} />
      )}
    </>
  );
}

// ── AI Generate Step ──────────────────────────────────────────────────────────

type Product = { name: string; price: string; description: string; image_url: string };

const THEMES = [
  { id: "zilo",   label: "Zilo Green", color: "#009b3a" },
  { id: "indigo", label: "Indigo",     color: "#6366f1" },
  { id: "red",    label: "Red",        color: "#ef4444" },
  { id: "green",  label: "Green",      color: "#10b981" },
  { id: "blue",   label: "Blue",       color: "#3b82f6" },
  { id: "amber",  label: "Amber",      color: "#f59e0b" },
  { id: "purple", label: "Purple",     color: "#8b5cf6" },
  { id: "orange", label: "Orange",     color: "#f97316" },
  { id: "dark",   label: "Dark",       color: "#0f172a" },
];

function AIGenerateStep({
  onApply, onBack, onSaveToLibrary,
}: {
  onApply: (html: string, subject: string) => void;
  onBack: () => void;
  onSaveToLibrary?: (html: string, subject: string) => void;
}) {
  const [description, setDescription] = useState("");
  const [brand, setBrand] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [heroImageUrl, setHeroImageUrl] = useState("");
  const [theme, setTheme] = useState("zilo");
  const [products, setProducts] = useState<Product[]>([{ name: "", price: "", description: "", image_url: "" }]);
  const [generating, setGenerating] = useState(false);
  const [status, setStatus] = useState("");
  const [generatedHtml, setGeneratedHtml] = useState("");
  const [generatedSubject, setGeneratedSubject] = useState("");

  const addProduct = () => {
    if (products.length < 6) setProducts(p => [...p, { name: "", price: "", description: "", image_url: "" }]);
  };
  const removeProduct = (i: number) => setProducts(p => p.filter((_, idx) => idx !== i));
  const setProduct = (i: number, k: keyof Product, v: string) =>
    setProducts(p => p.map((item, idx) => idx === i ? { ...item, [k]: v } : item));

  async function generate() {
    if (!description.trim()) { toast.error("Describe your email first"); return; }
    setGenerating(true);
    setGeneratedHtml("");
    setStatus("Asking AI to write your template…");
    try {
      const token = getToken();
      const aiRes = await fetch("/api/email-marketing/ai-generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          description, brand, theme,
          logo_url: logoUrl.trim(),
          hero_image_url: heroImageUrl.trim(),
          products: products.filter(p => p.name.trim()),
        }),
      });
      if (!aiRes.ok) {
        const err = await aiRes.json() as { error?: string };
        toast.error(err.error ?? "AI generation failed");
        return;
      }
      const { mjml } = await aiRes.json() as { mjml: string };

      setStatus("Compiling to responsive HTML…");
      const renderRes = await fetch("/api/email-marketing/render-mjml", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mjml }),
      });
      if (!renderRes.ok) {
        const err = await renderRes.json() as { error?: string };
        toast.error("MJML compile error: " + (err.error ?? "unknown"));
        return;
      }
      const { html } = await renderRes.json() as { html: string };
      const subjectLine = description.length > 60 ? description.slice(0, 57) + "…" : description;
      setGeneratedHtml(html);
      setGeneratedSubject(subjectLine);
      toast.success("AI template ready!");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setGenerating(false);
      setStatus("");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {/* Intro banner */}
        <div className={`${G.light} border ${G.lb} rounded-xl p-4 flex gap-3`}>
          <Sparkles size={20} className={`${G.text} shrink-0 mt-0.5`} />
          <div>
            <p className="text-sm font-semibold text-green-900">AI Email Generator</p>
            <p className="text-xs text-green-700 mt-0.5">Describe your campaign and add products — Claude writes the full responsive template.</p>
          </div>
        </div>

        {/* Description */}
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Describe your email *</label>
          <textarea value={description} onChange={e => setDescription(e.target.value)}
            rows={3} placeholder="e.g. Flash sale email promoting our summer collection with 30% off, urgency tone, ends Sunday"
            className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring} resize-none`} />
        </div>

        {/* Brand + Logo row */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Brand / company name</label>
            <input value={brand} onChange={e => setBrand(e.target.value)}
              placeholder="Your Brand"
              className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Logo URL <span className="text-slate-400 font-normal">(optional)</span></label>
            <input value={logoUrl} onChange={e => setLogoUrl(e.target.value)}
              placeholder="https://yoursite.com/logo.png"
              className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
            {logoUrl.trim() && (
              <div className="mt-1 flex items-center gap-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={logoUrl} alt="logo preview" className="h-8 max-w-[100px] object-contain rounded border border-slate-200 bg-white p-1" onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
                <span className="text-[10px] text-green-600 font-medium">Logo loaded</span>
              </div>
            )}
          </div>
        </div>

        {/* Hero image */}
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Hero / banner image URL <span className="text-slate-400 font-normal">(optional — makes a big visual impact)</span></label>
          <input value={heroImageUrl} onChange={e => setHeroImageUrl(e.target.value)}
            placeholder="https://yoursite.com/banner.jpg"
            className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
          {heroImageUrl.trim() && (
            <div className="mt-1 rounded-lg overflow-hidden border border-slate-200 bg-slate-100" style={{ height: 64 }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={heroImageUrl} alt="hero preview" className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
            </div>
          )}
        </div>

        {/* Theme row */}
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Colour theme</label>
          <div className="flex flex-wrap gap-2 pt-0.5">
            {THEMES.map(t => (
              <button key={t.id} onClick={() => setTheme(t.id)}
                title={t.label}
                className={cn(
                  "w-7 h-7 rounded-full border-2 transition-all",
                  theme === t.id ? "border-slate-700 scale-110 shadow-md" : "border-transparent hover:scale-105"
                )}
                style={{ backgroundColor: t.color }} />
            ))}
            <span className="text-xs text-slate-400 self-center ml-1">
              {THEMES.find(t => t.id === theme)?.label}
            </span>
          </div>
        </div>

        {/* Products */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-slate-700">Products to feature <span className="text-slate-400 font-normal">(optional, up to 6)</span></label>
            {products.length < 6 && (
              <button onClick={addProduct}
                className={`flex items-center gap-1 text-xs ${G.text} hover:text-green-800 font-medium`}>
                <Plus size={12} /> Add product
              </button>
            )}
          </div>
          {products.map((p, i) => (
            <div key={i} className="border border-slate-200 rounded-xl p-3 space-y-2 bg-slate-50">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">Product {i + 1}</span>
                {products.length > 1 && (
                  <button onClick={() => removeProduct(i)} className="text-slate-400 hover:text-red-500">
                    <Trash size={13} />
                  </button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <input value={p.name} onChange={e => setProduct(i, "name", e.target.value)}
                  placeholder="Product name"
                  className={`w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 ${G.ring} bg-white`} />
                <input value={p.price} onChange={e => setProduct(i, "price", e.target.value)}
                  placeholder="Price (e.g. $49.99)"
                  className={`w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 ${G.ring} bg-white`} />
              </div>
              <input value={p.description} onChange={e => setProduct(i, "description", e.target.value)}
                placeholder="Short description (optional)"
                className={`w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 ${G.ring} bg-white`} />
              <div className="flex items-center gap-2">
                <input value={p.image_url} onChange={e => setProduct(i, "image_url", e.target.value)}
                  placeholder="Product image URL (optional)"
                  className={`flex-1 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 ${G.ring} bg-white`} />
                {p.image_url.trim() && (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img src={p.image_url} alt="product" className="h-8 w-8 object-cover rounded border border-slate-200 bg-white shrink-0" onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Mini preview of generated template */}
        {generatedHtml && (
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            <div className={`${G.light} px-4 py-2 flex items-center justify-between border-b ${G.lb}`}>
              <span className={`text-xs font-semibold ${G.text}`}>Generated preview</span>
              <span className="text-xs text-slate-400">Scroll to see full email</span>
            </div>
            <div className="max-h-48 overflow-y-auto">
              <iframe
                srcDoc={generatedHtml}
                sandbox="allow-same-origin"
                className="w-full border-none"
                style={{ height: "400px", pointerEvents: "none" }}
                title="generated preview"
              />
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-slate-100 px-6 py-3 flex justify-between items-center gap-3">
        <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-700">← Back</button>
        <div className="flex items-center gap-2">
          {status && <p className={`text-xs ${G.text} animate-pulse`}>{status}</p>}
          {generatedHtml && onSaveToLibrary && (
            <button onClick={() => onSaveToLibrary(generatedHtml, generatedSubject)}
              className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 rounded-lg text-xs text-slate-600 hover:bg-slate-50 transition-colors">
              <Save size={13} /> Save to library
            </button>
          )}
          {generatedHtml && (
            <button onClick={() => onApply(generatedHtml, generatedSubject)}
              className={`flex items-center gap-2 px-4 py-2 ${G.bg} ${G.hover} text-white rounded-lg text-sm font-medium transition-colors`}>
              Use this template →
            </button>
          )}
          {!generatedHtml && (
            <button onClick={generate} disabled={generating || !description.trim()}
              className={`flex items-center gap-2 px-5 py-2 ${G.bg} ${G.hover} text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors`}>
              {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {generating ? "Generating…" : "Generate template"}
            </button>
          )}
          {generatedHtml && !generating && (
            <button onClick={generate}
              className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 rounded-lg text-xs text-slate-600 hover:bg-slate-50 transition-colors">
              <RefreshCw size={13} /> Regenerate
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Template Picker ───────────────────────────────────────────────────────────

const CATEGORY_ORDER = [
  "Newsletter","Promotional","Seasonal","Onboarding","Retention","Growth",
  "E-commerce","Transactional","Events","News","Feedback",
];

function TemplatePicker({
  onSelect, onBack, onAiGenerate,
}: {
  onSelect: (tpl: EmailTemplate) => void;
  onBack: () => void;
  onAiGenerate: () => void;
}) {
  const categories = CATEGORY_ORDER.filter(c =>
    EMAIL_TEMPLATES.some(t => t.category === c)
  );
  const [activeCategory, setActiveCategory] = useState<string>(categories[0] ?? "");

  const filtered = EMAIL_TEMPLATES.filter(t => t.category === activeCategory);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Vertical category sidebar */}
      <div className="w-44 shrink-0 border-r border-slate-100 flex flex-col overflow-y-auto py-3 px-2 gap-0.5">
        {/* AI Generate button */}
        <button onClick={onAiGenerate}
          className={`w-full flex items-center gap-2 px-3 py-2.5 mb-1 rounded-lg ${G.bg} ${G.hover} text-white transition-all`}>
          <Sparkles size={13} className="shrink-0" />
          <span className="text-xs font-semibold leading-tight">Generate with AI</span>
        </button>
        <div className="border-t border-slate-100 my-1" />
        {categories.map(c => (
          <button key={c} onClick={() => setActiveCategory(c)}
            className={cn(
              "w-full text-left px-3 py-2 rounded-lg text-xs font-medium transition-colors",
              activeCategory === c
                ? `${G.bg} text-white`
                : "text-slate-600 hover:bg-slate-100"
            )}>
            {c}
          </button>
        ))}
        <div className="mt-auto pt-3 px-1">
          <p className="text-[10px] text-slate-400">{EMAIL_TEMPLATES.length} templates</p>
        </div>
      </div>

      {/* Template grid */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 grid grid-cols-2 gap-3 content-start">
          {filtered.map(tpl => (
            <button key={tpl.id} onClick={() => onSelect(tpl)}
              className={`text-left border border-slate-200 rounded-xl p-4 hover:${G.border} hover:shadow-md transition-all`}>
              <div className="text-3xl mb-2">{tpl.thumbnail}</div>
              <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                <span className="text-sm font-semibold text-slate-800 leading-tight">{tpl.name.replace(" (MJML)", "")}</span>
                {tpl.type === "mjml" && (
                  <span className={`px-1.5 py-0.5 ${G.light} ${G.text} text-[10px] font-bold rounded-full border ${G.lb}`}>MJML</span>
                )}
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{tpl.description}</p>
            </button>
          ))}
        </div>

        <div className="border-t border-slate-100 px-4 py-3 flex justify-start">
          <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-700">← Back</button>
        </div>
      </div>
    </div>
  );
}

// ── Variable Filler ───────────────────────────────────────────────────────────

function VariableFiller({
  template, onApply, onBack, onSaveToLibrary,
}: {
  template: EmailTemplate;
  onApply: (html: string, subject: string) => void;
  onBack: () => void;
  onSaveToLibrary?: (html: string, subject: string) => void;
}) {
  const [vars, setVars] = useState<Record<string, string>>(
    Object.fromEntries(template.variables.map(v => [v.key, v.defaultValue]))
  );
  const [compiling, setCompiling] = useState(false);
  const [compiledHtml, setCompiledHtml] = useState("");

  const setVar = (k: string, v: string) => setVars(p => ({ ...p, [k]: v }));

  async function compile(): Promise<string> {
    if (template.type === "mjml" && template.mjmlSource) {
      const res = await fetch("/api/email-marketing/render-mjml", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mjml: template.mjmlSource }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error("Failed to compile template: " + (err.error ?? "Unknown error"));
      }
      const data = await res.json();
      return applyVars(data.html, vars);
    }
    return applyVars(template.html, vars);
  }

  async function handleApply() {
    setCompiling(true);
    try {
      const html = await compile();
      const subject = applyVars(template.defaultSubject, vars);
      setCompiledHtml(html);
      onApply(html, subject);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to apply template");
    } finally {
      setCompiling(false);
    }
  }

  async function handleSaveToLibrary() {
    if (!onSaveToLibrary) return;
    setCompiling(true);
    try {
      const html = await compile();
      const subject = applyVars(template.defaultSubject, vars);
      setCompiledHtml(html);
      onSaveToLibrary(html, subject);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to compile template");
    } finally {
      setCompiling(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 pt-4 pb-2 flex items-center gap-2">
        <span className="text-2xl">{template.thumbnail}</span>
        <div>
          <div className="text-sm font-semibold text-slate-800">{template.name}</div>
          <div className="text-xs text-slate-500">{template.description}</div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-3 space-y-3">
        {template.variables.map((v: TemplateVar) => (
          <div key={v.key} className="space-y-1">
            <label className="text-xs font-medium text-slate-700">{v.label}</label>
            {v.multiline ? (
              <textarea value={vars[v.key] ?? ""}
                onChange={e => setVar(v.key, e.target.value)}
                placeholder={v.placeholder} rows={3}
                className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring} resize-none`} />
            ) : (
              <input value={vars[v.key] ?? ""}
                onChange={e => setVar(v.key, e.target.value)}
                placeholder={v.placeholder}
                className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
            )}
          </div>
        ))}
      </div>

      <div className="border-t border-slate-100 px-6 py-3 flex gap-2 justify-between items-center">
        <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-700">← Back</button>
        <div className="flex gap-2">
          {onSaveToLibrary && (
            <button onClick={handleSaveToLibrary} disabled={compiling}
              className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 rounded-lg text-xs text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50">
              <Save size={13} /> Save to library
            </button>
          )}
          <button onClick={handleApply} disabled={compiling}
            className={`flex items-center gap-2 px-5 py-2 ${G.bg} ${G.hover} text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors`}>
            {compiling ? <Loader2 size={14} className="animate-spin" /> : null}
            Use this template →
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Create Campaign Modal ─────────────────────────────────────────────────────

function CreateCampaignModal({
  onClose, onCreated,
  prefillHtml, prefillSubject,
}: {
  onClose: () => void;
  onCreated: () => void;
  prefillHtml?: string;
  prefillSubject?: string;
}) {
  const [step, setStep] = useState<"form" | "template-pick" | "template-vars" | "ai-generate">("form");
  const [selectedTemplate, setSelectedTemplate] = useState<EmailTemplate | null>(null);
  const [loading, setLoading] = useState(false);
  const [saveLibraryTarget, setSaveLibraryTarget] = useState<{ html: string; subject: string } | null>(null);
  const [form, setForm] = useState({
    name: "", subject: prefillSubject ?? "", from_name: "", from_email: "",
    body_html: prefillHtml ?? "", recipient_emails: "", recipient_tags: "",
  });

  const set = (k: keyof typeof form, v: string) => setForm(p => ({ ...p, [k]: v }));

  async function handleCreate(sendNow = false) {
    if (!form.name || !form.subject || !form.body_html) {
      toast.error("Name, subject, and body are required");
      return;
    }
    setLoading(true);
    try {
      const payload = {
        name: form.name, subject: form.subject,
        from_name: form.from_name, from_email: form.from_email,
        body_html: form.body_html,
        recipient_emails: form.recipient_emails ? form.recipient_emails.split(",").map(e => e.trim()).filter(Boolean) : [],
        recipient_tags:   form.recipient_tags   ? form.recipient_tags.split(",").map(t => t.trim()).filter(Boolean)   : [],
      };
      const res = await apiPost<{ id: string }>("/email-marketing/campaigns", payload);
      if (sendNow) {
        await apiPost(`/email-marketing/campaigns/${res.id}/send`, {});
        toast.success("Campaign sent!");
      } else {
        toast.success("Campaign saved as draft");
      }
      onCreated();
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to create campaign");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <h2 className="text-lg font-semibold text-slate-800">
              {step === "form" ? "New Campaign" : step === "template-pick" ? "Choose a Template" : step === "ai-generate" ? "AI Email Generator" : "Customize Template"}
            </h2>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
              <X size={20} />
            </button>
          </div>

          {/* AI Generate step */}
          {step === "ai-generate" && (
            <div className="flex-1 overflow-hidden min-h-0">
              <AIGenerateStep
                onApply={(html, subject) => {
                  set("body_html", html);
                  if (!form.subject) set("subject", subject);
                  setStep("form");
                }}
                onBack={() => setStep("template-pick")}
                onSaveToLibrary={(html, subject) => setSaveLibraryTarget({ html, subject })}
              />
            </div>
          )}

          {/* Template picker step */}
          {step === "template-pick" && (
            <div className="flex-1 overflow-hidden min-h-0">
              <TemplatePicker
                onSelect={tpl => { setSelectedTemplate(tpl); setStep("template-vars"); }}
                onBack={() => setStep("form")}
                onAiGenerate={() => setStep("ai-generate")}
              />
            </div>
          )}

          {/* Variable filler step */}
          {step === "template-vars" && selectedTemplate && (
            <div className="flex-1 overflow-hidden min-h-0">
              <VariableFiller
                template={selectedTemplate}
                onApply={(html, subject) => {
                  set("body_html", html);
                  if (!form.subject) set("subject", subject);
                  setStep("form");
                }}
                onBack={() => setStep("template-pick")}
                onSaveToLibrary={(html, subject) => setSaveLibraryTarget({ html, subject })}
              />
            </div>
          )}

          {/* Main form step */}
          {step === "form" && (
            <>
              <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-sm font-medium text-slate-700">Campaign name *</label>
                    <input value={form.name} onChange={e => set("name", e.target.value)}
                      placeholder="e.g. June Flash Sale"
                      className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium text-slate-700">Subject line *</label>
                    <input value={form.subject} onChange={e => set("subject", e.target.value)}
                      placeholder="e.g. 🔥 50% off this weekend only"
                      className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-sm font-medium text-slate-700">From name</label>
                    <input value={form.from_name} onChange={e => set("from_name", e.target.value)}
                      placeholder="Your Brand"
                      className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium text-slate-700">From email</label>
                    <input value={form.from_email} onChange={e => set("from_email", e.target.value)}
                      placeholder="hello@yourdomain.com"
                      className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate-700">Recipients — emails (comma-separated)</label>
                  <input value={form.recipient_emails} onChange={e => set("recipient_emails", e.target.value)}
                    placeholder="alice@example.com, bob@example.com"
                    className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
                </div>

                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate-700">Recipients — contact tags (comma-separated)</label>
                  <input value={form.recipient_tags} onChange={e => set("recipient_tags", e.target.value)}
                    placeholder="vip, newsletter, shopify-customers"
                    className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
                  <p className="text-xs text-slate-400">Sends to all contacts/customers with these tags</p>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-700">Email body (HTML) *</label>
                    <button onClick={() => setStep("template-pick")}
                      className={`flex items-center gap-1.5 px-3 py-1 ${G.light} ${G.text} rounded-lg text-xs font-medium hover:bg-green-100 transition-colors border ${G.lb}`}>
                      <FileText size={12} /> Browse templates
                    </button>
                  </div>
                  <textarea value={form.body_html} onChange={e => set("body_html", e.target.value)}
                    rows={8} placeholder="<p>Hello! Here's our latest offer...</p>"
                    className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 ${G.ring} resize-none`} />
                </div>

                {/* Preview */}
                {form.body_html && (
                  <div className="border border-slate-200 rounded-lg overflow-hidden">
                    <div className={`${G.light} px-4 py-2 flex items-center gap-2 text-xs ${G.text} font-medium border-b ${G.lb}`}>
                      <Eye size={13} /> Preview
                    </div>
                    <iframe
                      srcDoc={form.body_html}
                      sandbox="allow-same-origin"
                      className="w-full border-none"
                      style={{ height: "200px", pointerEvents: "none" }}
                      title="body preview"
                    />
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 gap-3">
                <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-700 transition-colors">
                  Cancel
                </button>
                <div className="flex gap-2">
                  {form.body_html && (
                    <button onClick={() => setSaveLibraryTarget({ html: form.body_html, subject: form.subject })}
                      className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 rounded-lg text-xs text-slate-600 hover:bg-slate-50 transition-colors">
                      <Save size={13} /> Save to library
                    </button>
                  )}
                  <button onClick={() => handleCreate(false)} disabled={loading}
                    className="flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50">
                    {loading ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
                    Save draft
                  </button>
                  <button onClick={() => handleCreate(true)} disabled={loading}
                    className={`flex items-center gap-2 px-4 py-2 ${G.bg} ${G.hover} text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50`}>
                    {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                    Send now
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {saveLibraryTarget && (
        <SaveToLibraryModal
          html={saveLibraryTarget.html}
          defaultSubject={saveLibraryTarget.subject}
          onClose={() => setSaveLibraryTarget(null)}
          onSaved={() => setSaveLibraryTarget(null)}
        />
      )}
    </>
  );
}

// ── Send / Test modal ─────────────────────────────────────────────────────────

function SendModal({ campaign, onClose, onSent }: { campaign: Campaign; onClose: () => void; onSent: () => void }) {
  const [testEmail, setTestEmail] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleTest() {
    if (!testEmail) { toast.error("Enter a test email address"); return; }
    setLoading(true);
    try {
      await apiPost(`/email-marketing/campaigns/${campaign.id}/send`, { test_email: testEmail });
      toast.success(`Test sent to ${testEmail}`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Test send failed");
    } finally { setLoading(false); }
  }

  async function handleSend() {
    setLoading(true);
    try {
      const res = await apiPost<{ sent: number; failed: number; status: string }>(
        `/email-marketing/campaigns/${campaign.id}/send`, {}
      );
      toast.success(`Sent to ${res.sent} recipients`);
      onSent();
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Send failed");
    } finally { setLoading(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="text-lg font-semibold text-slate-800">Send Campaign</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={20} /></button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div className="bg-slate-50 rounded-xl p-4 space-y-1">
            <p className="font-medium text-slate-800 text-sm">{campaign.name}</p>
            <p className="text-xs text-slate-500">Subject: {campaign.subject}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">Send a test first (optional)</label>
            <div className="flex gap-2">
              <input value={testEmail} onChange={e => setTestEmail(e.target.value)}
                placeholder="your@email.com"
                className={`flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
              <button onClick={handleTest} disabled={loading}
                className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                Test
              </button>
            </div>
          </div>
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-slate-100">
          <button onClick={onClose} className="flex-1 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={handleSend} disabled={loading}
            className={`flex-1 py-2 ${G.bg} ${G.hover} text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50 transition-colors`}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Send to all
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Settings panel ─────────────────────────────────────────────────────────────

const PROVIDERS = [
  { value: "platform",   label: "Zilo Platform (recommended)", desc: "Built-in email via Resend. Zero setup required." },
  { value: "mailchimp",  label: "Mailchimp",  desc: "Send via Mailchimp Transactional (Mandrill). Requires a Mailchimp Transactional API key." },
  { value: "klaviyo",    label: "Klaviyo",    desc: "Send via your Klaviyo account using the SMTP relay. Needs your Public and Private API keys." },
  { value: "sendgrid",   label: "SendGrid",   desc: "Use your own SendGrid API key." },
  { value: "brevo",      label: "Brevo",      desc: "Use your own Brevo (Sendinblue) API key." },
  { value: "mailgun",    label: "Mailgun",    desc: "Use your own Mailgun account." },
  { value: "smtp",       label: "Custom SMTP", desc: "Any SMTP server (Gmail, Outlook, etc.)." },
];

function SettingsPanel() {
  const [settings, setSettings] = useState<EmailSettings>({
    provider: "platform", from_name: "", from_email: "", credentials: {},
  });
  const [saving, setSaving] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    apiGet<EmailSettings>("/email-marketing/settings")
      .then(d => setSettings(d))
      .catch(() => {});
  }, []);

  async function save() {
    setSaving(true);
    try {
      await apiPost("/email-marketing/settings", settings);
      toast.success("Settings saved");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally { setSaving(false); }
  }

  async function test() {
    if (!testEmail) { toast.error("Enter a test email address"); return; }
    setTesting(true);
    try {
      const res = await apiPost<{ ok: boolean; message: string }>("/email-marketing/settings/test", {
        ...settings, test_email: testEmail,
      });
      toast.success(res.message);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Test failed");
    } finally { setTesting(false); }
  }

  const set = (k: keyof EmailSettings, v: string) => setSettings(p => ({ ...p, [k]: v }));
  const setCred = (k: string, v: string) => setSettings(p => ({
    ...p, credentials: { ...p.credentials, [k]: v },
  }));

  return (
    <div className="max-w-2xl space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="font-semibold text-slate-800">Email Provider</h3>
          <p className="text-sm text-slate-500 mt-0.5">Choose how emails are sent from your account</p>
        </div>
        <div className="p-6 space-y-3">
          {PROVIDERS.map(p => (
            <label key={p.value}
              className={cn("flex items-start gap-3 p-4 border-2 rounded-xl cursor-pointer transition-colors",
                settings.provider === p.value ? G.sel : "border-slate-200 hover:border-slate-300")}>
              <input type="radio" name="provider" value={p.value}
                checked={settings.provider === p.value}
                onChange={() => set("provider", p.value)}
                className={`mt-0.5 accent-[#009b3a]`} />
              <div>
                <div className="text-sm font-medium text-slate-800">{p.label}</div>
                <div className="text-xs text-slate-500">{p.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="font-semibold text-slate-800">Sender Details</h3>
        </div>
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">From name</label>
              <input value={settings.from_name} onChange={e => set("from_name", e.target.value)}
                placeholder="Your Brand"
                className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">From email</label>
              <input value={settings.from_email} onChange={e => set("from_email", e.target.value)}
                placeholder="hello@yourdomain.com"
                className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
            </div>
          </div>

          {/* Provider-specific credentials */}
          {settings.provider === "mailchimp" && (
            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Mailchimp Transactional API Key</label>
                <input type="password" value={settings.credentials.api_key ?? ""}
                  onChange={e => setCred("api_key", e.target.value)}
                  placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-us1"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 ${G.ring}`} />
                <p className="text-xs text-slate-400">
                  This is your <strong>Mailchimp Transactional</strong> key (formerly Mandrill) — not your regular Mailchimp API key.
                  Find it at <span className="font-mono">mailchimp.com → Transactional → Settings → SMTP &amp; API Info</span>.
                </p>
              </div>
            </div>
          )}
          {settings.provider === "klaviyo" && (
            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Klaviyo Public API Key</label>
                <input value={settings.credentials.public_key ?? ""}
                  onChange={e => setCred("public_key", e.target.value)}
                  placeholder="pk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 ${G.ring}`} />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Klaviyo Private API Key</label>
                <input type="password" value={settings.credentials.private_key ?? ""}
                  onChange={e => setCred("private_key", e.target.value)}
                  placeholder="sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 ${G.ring}`} />
                <p className="text-xs text-slate-400">
                  Find your keys at <span className="font-mono">Klaviyo → Settings → API Keys</span>.
                  Create a Private Key with <em>Full Access</em>.
                </p>
              </div>
            </div>
          )}
          {settings.provider === "sendgrid" && (
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">SendGrid API Key</label>
              <input type="password" value={settings.credentials.api_key ?? ""}
                onChange={e => setCred("api_key", e.target.value)}
                placeholder="SG.xxxxxx"
                className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 ${G.ring}`} />
            </div>
          )}
          {settings.provider === "brevo" && (
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">Brevo API Key</label>
              <input type="password" value={settings.credentials.api_key ?? ""}
                onChange={e => setCred("api_key", e.target.value)}
                placeholder="xkeysib-xxxxxx"
                className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 ${G.ring}`} />
            </div>
          )}
          {settings.provider === "mailgun" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Mailgun API Key</label>
                <input type="password" value={settings.credentials.api_key ?? ""}
                  onChange={e => setCred("api_key", e.target.value)}
                  placeholder="key-xxxxxx"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 ${G.ring}`} />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Mailgun Domain</label>
                <input value={settings.credentials.domain ?? ""}
                  onChange={e => setCred("domain", e.target.value)}
                  placeholder="mg.yourdomain.com"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
              </div>
            </div>
          )}
          {settings.provider === "smtp" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">SMTP Host</label>
                <input value={settings.credentials.host ?? ""}
                  onChange={e => setCred("host", e.target.value)}
                  placeholder="smtp.gmail.com"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Port</label>
                <input value={settings.credentials.port ?? "587"}
                  onChange={e => setCred("port", e.target.value)}
                  placeholder="587"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Username</label>
                <input value={settings.credentials.username ?? ""}
                  onChange={e => setCred("username", e.target.value)}
                  placeholder="you@gmail.com"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Password</label>
                <input type="password" value={settings.credentials.password ?? ""}
                  onChange={e => setCred("password", e.target.value)}
                  placeholder="App password"
                  className={`w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
              </div>
            </div>
          )}
        </div>
        <div className="px-6 py-4 border-t border-slate-100 flex items-center gap-3">
          <div className="flex gap-2 flex-1">
            <input value={testEmail} onChange={e => setTestEmail(e.target.value)}
              placeholder="Test to: your@email.com"
              className={`flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${G.ring}`} />
            <button onClick={test} disabled={testing}
              className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 flex items-center gap-1.5">
              {testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
              Test
            </button>
          </div>
          <button onClick={save} disabled={saving}
            className={`px-5 py-2 ${G.bg} ${G.hover} text-white rounded-lg text-sm font-medium disabled:opacity-50 flex items-center gap-2 transition-colors`}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function EmailMarketingPage() {
  const [tab, setTab] = useState<Tab>("campaigns");
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [sendTarget, setSendTarget] = useState<Campaign | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [previewCampaign, setPreviewCampaign] = useState<Campaign | null>(null);
  const [libraryPrefill, setLibraryPrefill] = useState<{ html: string; subject: string } | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [c, s] = await Promise.all([
        apiGet<{ campaigns: Campaign[] }>("/email-marketing/campaigns"),
        apiGet<Stats>("/email-marketing/stats"),
      ]);
      setCampaigns(c.campaigns);
      setStats(s);
    } catch {
      toast.error("Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  async function deleteCampaign(id: string) {
    setDeleting(id);
    try {
      await apiDelete(`/email-marketing/campaigns/${id}`);
      setCampaigns(p => p.filter(c => c.id !== id));
      toast.success("Campaign deleted");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally { setDeleting(null); }
  }

  async function previewCampaignHtml(campaign: Campaign) {
    if (campaign.body_html) { setPreviewCampaign(campaign); return; }
    try {
      const full = await apiGet<Campaign>(`/email-marketing/campaigns/${campaign.id}`);
      setPreviewCampaign({ ...campaign, body_html: full.body_html });
    } catch {
      toast.error("Could not load campaign preview");
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl ${G.icon} flex items-center justify-center shadow-sm`}>
              <Mail size={20} className="text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-800">Email Marketing</h1>
              <p className="text-sm text-slate-500">Create and send campaigns to your contacts</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={loadData} className="p-2 text-slate-400 hover:text-slate-600 transition-colors">
              <RefreshCw size={18} />
            </button>
            {tab === "campaigns" && (
              <button onClick={() => setShowCreate(true)}
                className={`flex items-center gap-2 px-4 py-2 ${G.bg} ${G.hover} text-white rounded-xl text-sm font-medium transition-colors shadow-sm`}>
                <Plus size={16} /> New Campaign
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">
        {/* Stats row */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: "Total campaigns",  value: stats.campaigns.total,    icon: <Mail size={18} />,         color: `${G.text} ${G.light}` },
              { label: "Sent",             value: stats.campaigns.sent,      icon: <CheckCircle2 size={18} />, color: "text-green-600 bg-green-50" },
              { label: "Emails delivered", value: stats.emails_sent,         icon: <Send size={18} />,         color: "text-blue-600 bg-blue-50" },
              { label: "Drafts",           value: stats.campaigns.draft,     icon: <FileText size={18} />,     color: "text-slate-600 bg-slate-100" },
            ].map(s => (
              <div key={s.label} className="bg-white rounded-2xl border border-slate-200 p-4 flex items-center gap-3">
                <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", s.color)}>
                  {s.icon}
                </div>
                <div>
                  <div className="text-2xl font-bold text-slate-800">{s.value.toLocaleString()}</div>
                  <div className="text-xs text-slate-500">{s.label}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 bg-slate-100 rounded-xl p-1 w-fit">
          {([
            { id: "campaigns", label: "Campaigns", icon: <BarChart2 size={14} /> },
            { id: "library",   label: "Library",   icon: <BookOpen size={14} /> },
            { id: "settings",  label: "Settings",  icon: <Settings size={14} /> },
          ] as { id: Tab; label: string; icon: React.ReactNode }[]).map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={cn("flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                tab === t.id ? `bg-white ${G.tab} shadow-sm` : "text-slate-600 hover:text-slate-800")}>
              {t.icon}{t.label}
            </button>
          ))}
        </div>

        {/* Campaigns tab */}
        {tab === "campaigns" && (
          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 size={24} className={`animate-spin ${G.text}`} />
              </div>
            ) : campaigns.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className={`w-16 h-16 ${G.light} rounded-2xl flex items-center justify-center mb-4`}>
                  <Mail size={28} className={G.text} />
                </div>
                <h3 className="text-lg font-semibold text-slate-700 mb-1">No campaigns yet</h3>
                <p className="text-sm text-slate-400 mb-5 max-w-xs">Create your first email campaign to reach your customers and grow your business.</p>
                <button onClick={() => setShowCreate(true)}
                  className={`flex items-center gap-2 px-5 py-2.5 ${G.bg} ${G.hover} text-white rounded-xl text-sm font-medium transition-colors`}>
                  <Plus size={15} /> Create campaign
                </button>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="bg-slate-50 text-left">
                    <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Campaign</th>
                    <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider hidden md:table-cell">Status</th>
                    <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider hidden lg:table-cell">Sent</th>
                    <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider hidden lg:table-cell">Date</th>
                    <th className="px-5 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {campaigns.map(c => (
                    <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-5 py-4">
                        <div className="font-medium text-slate-800 text-sm">{c.name}</div>
                        <div className="text-xs text-slate-400 mt-0.5 truncate max-w-xs">{c.subject}</div>
                      </td>
                      <td className="px-5 py-4 hidden md:table-cell">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="px-5 py-4 hidden lg:table-cell">
                        {c.stats.sent > 0 ? (
                          <div className="flex items-center gap-1 text-sm">
                            <Users size={13} className="text-slate-400" />
                            <span className="text-slate-700">{c.stats.sent.toLocaleString()}</span>
                            {c.stats.failed > 0 && (
                              <span className="text-red-500 text-xs">({c.stats.failed} failed)</span>
                            )}
                          </div>
                        ) : <span className="text-xs text-slate-400">—</span>}
                      </td>
                      <td className="px-5 py-4 hidden lg:table-cell">
                        <span className="text-xs text-slate-400">
                          {c.sent_at ? new Date(c.sent_at).toLocaleDateString() : new Date(c.created_at).toLocaleDateString()}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-1 justify-end">
                          <button onClick={() => previewCampaignHtml(c)}
                            className="p-1.5 text-slate-400 hover:text-slate-700 transition-colors" title="Preview">
                            <Eye size={14} />
                          </button>
                          {c.status === "draft" && (
                            <button onClick={() => setSendTarget(c)}
                              className={`flex items-center gap-1.5 px-3 py-1.5 ${G.light} ${G.text} rounded-lg text-xs font-medium hover:bg-green-100 transition-colors`}>
                              <Play size={11} /> Send
                            </button>
                          )}
                          <button onClick={() => deleteCampaign(c.id)} disabled={deleting === c.id}
                            className="p-1.5 text-slate-400 hover:text-red-500 transition-colors disabled:opacity-50">
                            {deleting === c.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Library tab */}
        {tab === "library" && (
          <LibraryPanel
            onUseTemplate={(html, subject) => {
              setLibraryPrefill({ html, subject });
              setShowCreate(true);
            }}
          />
        )}

        {/* Settings tab */}
        {tab === "settings" && <SettingsPanel />}
      </div>

      {/* Modals */}
      {showCreate && (
        <CreateCampaignModal
          onClose={() => { setShowCreate(false); setLibraryPrefill(null); }}
          onCreated={loadData}
          prefillHtml={libraryPrefill?.html}
          prefillSubject={libraryPrefill?.subject}
        />
      )}
      {sendTarget && (
        <SendModal campaign={sendTarget} onClose={() => setSendTarget(null)} onSent={loadData} />
      )}
      {previewCampaign?.body_html && (
        <EmailPreviewModal
          html={previewCampaign.body_html}
          title={previewCampaign.name}
          onClose={() => setPreviewCampaign(null)}
        />
      )}
    </div>
  );
}
