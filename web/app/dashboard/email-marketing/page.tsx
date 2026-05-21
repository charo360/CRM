"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Mail, Plus, Send, Trash2, BarChart2, Settings,
  Loader2, CheckCircle2, Clock, FileText, RefreshCw, X,
  Zap, Users, AlertCircle, Eye, Play, Sparkles, Trash,
} from "lucide-react";
import { getToken } from "@/lib/auth";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { EMAIL_TEMPLATES, EmailTemplate, TemplateVar, applyVars } from "./templates";

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
};

type Stats = {
  campaigns: { total: number; sent: number; draft: number; scheduled: number };
  emails_sent: number;
  emails_failed: number;
};

type Settings = {
  provider: string;
  from_name: string;
  from_email: string;
  credentials: Record<string, string>;
};

type Tab = "campaigns" | "settings";

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

// ── Create Campaign Modal ─────────────────────────────────────────────────────

// ── AI Generate Step ──────────────────────────────────────────────────────────

type Product = { name: string; price: string; description: string };

const THEMES = [
  { id: "indigo", label: "Indigo",  color: "#6366f1" },
  { id: "red",    label: "Red",     color: "#ef4444" },
  { id: "green",  label: "Green",   color: "#10b981" },
  { id: "blue",   label: "Blue",    color: "#3b82f6" },
  { id: "amber",  label: "Amber",   color: "#f59e0b" },
  { id: "purple", label: "Purple",  color: "#8b5cf6" },
  { id: "orange", label: "Orange",  color: "#f97316" },
  { id: "dark",   label: "Dark",    color: "#0f172a" },
];

function AIGenerateStep({
  onApply, onBack,
}: {
  onApply: (html: string, subject: string) => void;
  onBack: () => void;
}) {
  const [description, setDescription] = useState("");
  const [brand, setBrand] = useState("");
  const [theme, setTheme] = useState("indigo");
  const [products, setProducts] = useState<Product[]>([{ name: "", price: "", description: "" }]);
  const [generating, setGenerating] = useState(false);
  const [status, setStatus] = useState("");

  const addProduct = () => {
    if (products.length < 6) setProducts(p => [...p, { name: "", price: "", description: "" }]);
  };
  const removeProduct = (i: number) => setProducts(p => p.filter((_, idx) => idx !== i));
  const setProduct = (i: number, k: keyof Product, v: string) =>
    setProducts(p => p.map((item, idx) => idx === i ? { ...item, [k]: v } : item));

  async function generate() {
    if (!description.trim()) { toast.error("Describe your email first"); return; }
    setGenerating(true);
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
      onApply(html, subjectLine);
      toast.success("AI template applied!");
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
        <div className="bg-gradient-to-r from-indigo-50 to-purple-50 border border-indigo-100 rounded-xl p-4 flex gap-3">
          <Sparkles size={20} className="text-indigo-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-indigo-800">AI Email Generator</p>
            <p className="text-xs text-indigo-600 mt-0.5">Describe your campaign and add products — Claude writes the full responsive template.</p>
          </div>
        </div>

        {/* Description */}
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700">Describe your email *</label>
          <textarea value={description} onChange={e => setDescription(e.target.value)}
            rows={3} placeholder="e.g. Flash sale email promoting our summer collection with 30% off, urgency tone, ends Sunday"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
        </div>

        {/* Brand + Theme row */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Brand / company name</label>
            <input value={brand} onChange={e => setBrand(e.target.value)}
              placeholder="Your Brand"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Colour theme</label>
            <div className="flex flex-wrap gap-2 pt-1">
              {THEMES.map(t => (
                <button key={t.id} onClick={() => setTheme(t.id)}
                  title={t.label}
                  className={cn(
                    "w-7 h-7 rounded-full border-2 transition-all",
                    theme === t.id ? "border-slate-700 scale-110" : "border-transparent hover:scale-105"
                  )}
                  style={{ backgroundColor: t.color }} />
              ))}
            </div>
          </div>
        </div>

        {/* Products */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-slate-700">Products to feature <span className="text-slate-400 font-normal">(optional, up to 6)</span></label>
            {products.length < 6 && (
              <button onClick={addProduct}
                className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium">
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
                  className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white" />
                <input value={p.price} onChange={e => setProduct(i, "price", e.target.value)}
                  placeholder="Price (e.g. $49.99)"
                  className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white" />
              </div>
              <input value={p.description} onChange={e => setProduct(i, "description", e.target.value)}
                placeholder="Short description (optional)"
                className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white" />
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-slate-100 px-6 py-3 flex justify-between items-center gap-3">
        <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-700">← Back</button>
        <div className="flex items-center gap-3">
          {status && <p className="text-xs text-indigo-600 animate-pulse">{status}</p>}
          <button onClick={generate} disabled={generating || !description.trim()}
            className="flex items-center gap-2 px-5 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors">
            {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {generating ? "Generating…" : "Generate template"}
          </button>
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
          className="w-full flex items-center gap-2 px-3 py-2.5 mb-1 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:from-indigo-700 hover:to-purple-700 transition-all">
          <Sparkles size={13} className="shrink-0" />
          <span className="text-xs font-semibold leading-tight">Generate with AI</span>
        </button>
        <div className="border-t border-slate-100 my-1" />
        {categories.map(c => (
          <button key={c} onClick={() => setActiveCategory(c)}
            className={cn(
              "w-full text-left px-3 py-2 rounded-lg text-xs font-medium transition-colors",
              activeCategory === c
                ? "bg-indigo-600 text-white"
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
              className="text-left border border-slate-200 rounded-xl p-4 hover:border-indigo-400 hover:shadow-md transition-all">
              <div className="text-3xl mb-2">{tpl.thumbnail}</div>
              <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                <span className="text-sm font-semibold text-slate-800 leading-tight">{tpl.name.replace(" (MJML)", "")}</span>
                {tpl.type === "mjml" && (
                  <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] font-bold rounded-full border border-indigo-200">MJML</span>
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
  template, onApply, onBack,
}: {
  template: EmailTemplate;
  onApply: (html: string, subject: string) => void;
  onBack: () => void;
}) {
  const [vars, setVars] = useState<Record<string, string>>(
    Object.fromEntries(template.variables.map(v => [v.key, v.defaultValue]))
  );
  const [compiling, setCompiling] = useState(false);

  const setVar = (k: string, v: string) => setVars(p => ({ ...p, [k]: v }));

  async function handleApply() {
    setCompiling(true);
    try {
      let html = "";
      if (template.type === "mjml" && template.mjmlSource) {
        const res = await fetch("/api/email-marketing/render-mjml", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mjml: template.mjmlSource }),
        });
        if (!res.ok) {
          const err = await res.json();
          toast.error("Failed to compile template: " + (err.error ?? "Unknown error"));
          return;
        }
        const data = await res.json();
        html = applyVars(data.html, vars);
      } else {
        html = applyVars(template.html, vars);
      }
      const subject = applyVars(template.defaultSubject, vars);
      onApply(html, subject);
    } catch {
      toast.error("Failed to apply template");
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
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
            ) : (
              <input value={vars[v.key] ?? ""}
                onChange={e => setVar(v.key, e.target.value)}
                placeholder={v.placeholder}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            )}
          </div>
        ))}
      </div>

      <div className="border-t border-slate-100 px-6 py-3 flex gap-2 justify-between items-center">
        <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-700">← Back</button>
        <button onClick={handleApply} disabled={compiling}
          className="flex items-center gap-2 px-5 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
          {compiling ? <Loader2 size={14} className="animate-spin" /> : null}
          Use this template →
        </button>
      </div>
    </div>
  );
}

// ── Create Campaign Modal ─────────────────────────────────────────────────────

function CreateCampaignModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [step, setStep] = useState<"form" | "template-pick" | "template-vars" | "ai-generate">("form");
  const [selectedTemplate, setSelectedTemplate] = useState<EmailTemplate | null>(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    name: "", subject: "", from_name: "", from_email: "",
    body_html: "", recipient_emails: "", recipient_tags: "",
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
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
          <AIGenerateStep
            onApply={(html, subject) => {
              set("body_html", html);
              if (!form.subject) set("subject", subject);
              setStep("form");
            }}
            onBack={() => setStep("template-pick")}
          />
        )}

        {/* Template picker step */}
        {step === "template-pick" && (
          <TemplatePicker
            onSelect={tpl => { setSelectedTemplate(tpl); setStep("template-vars"); }}
            onBack={() => setStep("form")}
            onAiGenerate={() => setStep("ai-generate")}
          />
        )}

        {/* Variable filler step */}
        {step === "template-vars" && selectedTemplate && (
          <VariableFiller
            template={selectedTemplate}
            onApply={(html, subject) => {
              set("body_html", html);
              if (!form.subject) set("subject", subject);
              setStep("form");
            }}
            onBack={() => setStep("template-pick")}
          />
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
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate-700">Subject line *</label>
                  <input value={form.subject} onChange={e => set("subject", e.target.value)}
                    placeholder="e.g. 🔥 50% off this weekend only"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate-700">From name</label>
                  <input value={form.from_name} onChange={e => set("from_name", e.target.value)}
                    placeholder="Your Brand"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate-700">From email</label>
                  <input value={form.from_email} onChange={e => set("from_email", e.target.value)}
                    placeholder="hello@yourdomain.com"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Recipients — emails (comma-separated)</label>
                <input value={form.recipient_emails} onChange={e => set("recipient_emails", e.target.value)}
                  placeholder="alice@example.com, bob@example.com"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>

              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Recipients — contact tags (comma-separated)</label>
                <input value={form.recipient_tags} onChange={e => set("recipient_tags", e.target.value)}
                  placeholder="vip, newsletter, shopify-customers"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                <p className="text-xs text-slate-400">Sends to all contacts/customers with these tags</p>
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-slate-700">Email body (HTML) *</label>
                  <button onClick={() => setStep("template-pick")}
                    className="flex items-center gap-1.5 px-3 py-1 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-medium hover:bg-indigo-100 transition-colors border border-indigo-200">
                    <FileText size={12} /> Browse templates
                  </button>
                </div>
                <textarea value={form.body_html} onChange={e => set("body_html", e.target.value)}
                  rows={8} placeholder="<p>Hello! Here's our latest offer...</p>"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
              </div>

              {/* Preview */}
              {form.body_html && (
                <div className="border border-slate-200 rounded-lg overflow-hidden">
                  <div className="bg-slate-50 px-4 py-2 flex items-center gap-2 text-xs text-slate-500 font-medium border-b border-slate-200">
                    <Eye size={13} /> Preview
                  </div>
                  <div className="p-4 max-h-48 overflow-y-auto"
                    dangerouslySetInnerHTML={{ __html: form.body_html }} />
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 gap-3">
              <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-700 transition-colors">
                Cancel
              </button>
              <div className="flex gap-2">
                <button onClick={() => handleCreate(false)} disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50">
                  {loading ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
                  Save draft
                </button>
                <button onClick={() => handleCreate(true)} disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50">
                  {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                  Send now
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
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
                className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
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
            className="flex-1 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 flex items-center justify-center gap-2">
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
  { value: "platform", label: "Zilo Platform (recommended)", desc: "Built-in email via Resend. Zero setup required." },
  { value: "sendgrid", label: "SendGrid",    desc: "Use your own SendGrid API key." },
  { value: "brevo",    label: "Brevo",       desc: "Use your own Brevo (Sendinblue) API key." },
  { value: "mailgun",  label: "Mailgun",     desc: "Use your own Mailgun account." },
  { value: "smtp",     label: "Custom SMTP", desc: "Any SMTP server (Gmail, Outlook, etc.)." },
];

function SettingsPanel() {
  const [settings, setSettings] = useState<Settings>({
    provider: "platform", from_name: "", from_email: "", credentials: {},
  });
  const [saving, setSaving] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    apiGet<Settings>("/email-marketing/settings")
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

  const set = (k: keyof Settings, v: string) => setSettings(p => ({ ...p, [k]: v }));
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
                settings.provider === p.value ? "border-indigo-500 bg-indigo-50" : "border-slate-200 hover:border-slate-300")}>
              <input type="radio" name="provider" value={p.value}
                checked={settings.provider === p.value}
                onChange={() => set("provider", p.value)}
                className="mt-0.5 accent-indigo-600" />
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
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">From email</label>
              <input value={settings.from_email} onChange={e => set("from_email", e.target.value)}
                placeholder="hello@yourdomain.com"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
          </div>

          {/* Provider-specific credentials */}
          {settings.provider === "sendgrid" && (
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">SendGrid API Key</label>
              <input type="password" value={settings.credentials.api_key ?? ""}
                onChange={e => setCred("api_key", e.target.value)}
                placeholder="SG.xxxxxx"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
          )}
          {settings.provider === "brevo" && (
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700">Brevo API Key</label>
              <input type="password" value={settings.credentials.api_key ?? ""}
                onChange={e => setCred("api_key", e.target.value)}
                placeholder="xkeysib-xxxxxx"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>
          )}
          {settings.provider === "mailgun" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Mailgun API Key</label>
                <input type="password" value={settings.credentials.api_key ?? ""}
                  onChange={e => setCred("api_key", e.target.value)}
                  placeholder="key-xxxxxx"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Mailgun Domain</label>
                <input value={settings.credentials.domain ?? ""}
                  onChange={e => setCred("domain", e.target.value)}
                  placeholder="mg.yourdomain.com"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Port</label>
                <input value={settings.credentials.port ?? "587"}
                  onChange={e => setCred("port", e.target.value)}
                  placeholder="587"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Username</label>
                <input value={settings.credentials.username ?? ""}
                  onChange={e => setCred("username", e.target.value)}
                  placeholder="you@gmail.com"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">Password</label>
                <input type="password" value={settings.credentials.password ?? ""}
                  onChange={e => setCred("password", e.target.value)}
                  placeholder="App password"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
            </div>
          )}
        </div>
        <div className="px-6 py-4 border-t border-slate-100 flex items-center gap-3">
          <div className="flex gap-2 flex-1">
            <input value={testEmail} onChange={e => setTestEmail(e.target.value)}
              placeholder="Test to: your@email.com"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <button onClick={test} disabled={testing}
              className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 flex items-center gap-1.5">
              {testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
              Test
            </button>
          </div>
          <button onClick={save} disabled={saving}
            className="px-5 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2">
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

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-sm">
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
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm">
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
              { label: "Total campaigns",   value: stats.campaigns.total,     icon: <Mail size={18} />,         color: "text-indigo-600 bg-indigo-50" },
              { label: "Sent",              value: stats.campaigns.sent,       icon: <CheckCircle2 size={18} />, color: "text-green-600 bg-green-50" },
              { label: "Emails delivered",  value: stats.emails_sent,          icon: <Send size={18} />,         color: "text-blue-600 bg-blue-50" },
              { label: "Drafts",            value: stats.campaigns.draft,      icon: <FileText size={18} />,     color: "text-slate-600 bg-slate-100" },
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
            { id: "settings",  label: "Settings",  icon: <Settings size={14} /> },
          ] as { id: Tab; label: string; icon: React.ReactNode }[]).map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={cn("flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                tab === t.id ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600 hover:text-slate-800")}>
              {t.icon}{t.label}
            </button>
          ))}
        </div>

        {/* Campaigns tab */}
        {tab === "campaigns" && (
          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 size={24} className="animate-spin text-indigo-600" />
              </div>
            ) : campaigns.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center mb-4">
                  <Mail size={28} className="text-indigo-500" />
                </div>
                <h3 className="text-lg font-semibold text-slate-700 mb-1">No campaigns yet</h3>
                <p className="text-sm text-slate-400 mb-5 max-w-xs">Create your first email campaign to reach your customers and grow your business.</p>
                <button onClick={() => setShowCreate(true)}
                  className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
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
                          {c.status === "draft" && (
                            <button onClick={() => setSendTarget(c)}
                              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-medium hover:bg-indigo-100 transition-colors">
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

        {/* Settings tab */}
        {tab === "settings" && <SettingsPanel />}
      </div>

      {/* Modals */}
      {showCreate && (
        <CreateCampaignModal onClose={() => setShowCreate(false)} onCreated={loadData} />
      )}
      {sendTarget && (
        <SendModal campaign={sendTarget} onClose={() => setSendTarget(null)} onSent={loadData} />
      )}
    </div>
  );
}
