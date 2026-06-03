"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { api, designTemplatesApi } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/utils";
import {
  ArrowLeft, Plus, Trash2, GripVertical, Copy, Check,
  Loader2, AlertCircle, ExternalLink, CheckCircle, Save,
  BarChart2, Settings, Layers, ToggleLeft, ToggleRight, Palette,
  Upload,
} from "lucide-react";

interface FormField {
  id: string;
  type: "text" | "email" | "phone" | "textarea" | "dropdown" | "checkbox" | "checklist";
  label: string;
  placeholder: string;
  required: boolean;
  options?: string[];
}

interface FormSettings {
  success_message: string;
  create_contact: boolean;
  auto_whatsapp: boolean;
}

interface FormBranding {
  logo_url?: string;
  header_bg?: string;
  header_text?: string;
  button_bg?: string;
  button_text?: string;
  page_bg?: string;
}

interface FormDoc {
  _id: string;
  title: string;
  description: string;
  slug: string;
  fields: FormField[];
  settings: FormSettings;
  branding: FormBranding;
  active: boolean;
  response_count: number;
  created_at: string;
}

interface Response {
  _id: string;
  data: Record<string, string>;
  created_at: string;
}

type Tab = "builder" | "branding" | "settings_tab" | "responses";

const FIELD_TYPES = [
  { value: "text",      label: "Short Text",              hint: "One line of text input" },
  { value: "textarea", label: "Long Text",               hint: "Multi-line text area" },
  { value: "email",    label: "Email",                   hint: "Validates email format" },
  { value: "phone",    label: "Phone",                   hint: "Phone number field" },
  { value: "dropdown", label: "Dropdown (Pick One)",     hint: "User picks exactly one option from a list" },
  { value: "checklist",label: "Checklist (Pick Many)",  hint: "User can tick multiple options" },
  { value: "checkbox", label: "Checkbox (Yes / No)",    hint: "A single tick box — great for agreements" },
] as const;

const DEFAULT_BRANDING: FormBranding = {
  logo_url: "",
  header_bg: "#0f172a",
  header_text: "#ffffff",
  button_bg: "#0f172a",
  button_text: "#ffffff",
  page_bg: "#f8fafc",
};

function newField(type: FormField["type"] = "text"): FormField {
  return {
    id: Math.random().toString(36).slice(2, 10),
    type,
    label: type === "checklist" ? "Checklist Question"
         : type === "dropdown" ? "Select Option"
         : type === "checkbox" ? "Agree to terms"
         : type === "textarea" ? "Long description"
         : "New Field",
    placeholder: type === "checkbox" ? "Yes, I agree" : "",
    required: false,
    options: (type === "dropdown" || type === "checklist") ? ["Option 1", "Option 2"] : undefined,
  };
}

export default function FormBuilderPage() {
  return (
    <Suspense fallback={<div className="flex-1 flex items-center justify-center"><span className="text-slate-400 text-sm">Loading…</span></div>}>
      <FormBuilderPageInner />
    </Suspense>
  );
}

function FormBuilderPageInner() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [tab, setTab] = useState<Tab>(
    searchParams.get("tab") === "responses" ? "responses" : "builder"
  );
  const [form, setForm] = useState<FormDoc | null>(null);
  const [responses, setResponses] = useState<Response[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [brandLogos, setBrandLogos] = useState<any[]>([]);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [cleaningLogo, setCleaningLogo] = useState(false);

  const loadForm = useCallback(async () => {
    try {
      const data = await api.get<FormDoc>(`/forms/${id}`);
      if (!data.branding) data.branding = { ...DEFAULT_BRANDING };
      setForm(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load form");
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadResponses = useCallback(async () => {
    try {
      const data = await api.get<{ responses: Response[] }>(`/forms/${id}/responses`);
      setResponses(data.responses);
    } catch { /* ignore */ }
  }, [id]);

  const loadBrandLogos = useCallback(async () => {
    try {
      const data = await designTemplatesApi.list({ content_type: "brand_logo" });
      setBrandLogos(data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    loadForm();
    loadResponses();
    loadBrandLogos();
  }, [loadForm, loadResponses, loadBrandLogos]);

  async function handleLogoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingLogo(true);
    setError("");
    try {
      const res = await designTemplatesApi.uploadBrandKitFile(file, {
        name: file.name,
        material_type: "brand_logo",
        is_default_logo: brandLogos.length === 0,
      });
      if (res && res.file_url) {
        setBranding({ logo_url: res.file_url as string });
        loadBrandLogos();
      } else {
        throw new Error("No URL returned from upload");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload logo");
    } finally {
      setUploadingLogo(false);
    }
  }

  async function handleCleanBackground() {
    if (!b.logo_url || cleaningLogo) return;
    setCleaningLogo(true);
    setError("");
    try {
      const res = await designTemplatesApi.cleanBackground(b.logo_url);
      if (res && res.file_url) {
        setBranding({ logo_url: res.file_url });
        loadBrandLogos();
      } else {
        throw new Error("No URL returned from background cleaning");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clean background");
    } finally {
      setCleaningLogo(false);
    }
  }

  async function save() {
    if (!form) return;
    setSaving(true);
    setError("");
    try {
      await api.put(`/forms/${form._id}`, form);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function copyLink() {
    if (!form) return;
    const url = `${window.location.origin}/f/${form.slug}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function updateField(idx: number, patch: Partial<FormField>) {
    setForm(f => {
      if (!f) return f;
      const fields = f.fields.map((field, i) => i === idx ? { ...field, ...patch } : field);
      return { ...f, fields };
    });
  }

  function addField(type: FormField["type"] = "text") {
    setForm(f => f ? { ...f, fields: [...f.fields, newField(type)] } : f);
  }

  function removeField(idx: number) {
    setForm(f => f ? { ...f, fields: f.fields.filter((_, i) => i !== idx) } : f);
  }

  function moveField(idx: number, dir: -1 | 1) {
    setForm(f => {
      if (!f) return f;
      const fields = [...f.fields];
      const target = idx + dir;
      if (target < 0 || target >= fields.length) return f;
      [fields[idx], fields[target]] = [fields[target], fields[idx]];
      return { ...f, fields };
    });
  }

  function setBranding(patch: Partial<FormBranding>) {
    setForm(f => f ? { ...f, branding: { ...DEFAULT_BRANDING, ...f.branding, ...patch } } : f);
  }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <Loader2 size={28} className="animate-spin text-slate-400" />
    </div>
  );

  if (!form) return <div className="p-6 text-slate-500">Form not found.</div>;

  const shareUrl = typeof window !== "undefined"
    ? `${window.location.origin}/f/${form.slug}`
    : `/f/${form.slug}`;

  const b: FormBranding = { ...DEFAULT_BRANDING, ...form.branding };

  const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: "builder", label: "Fields", icon: Layers },
    { id: "branding", label: "Branding", icon: Palette },
    { id: "settings_tab", label: "Settings", icon: Settings },
    { id: "responses", label: `Responses (${form.response_count})`, icon: BarChart2 },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => router.push("/dashboard/forms")}
          className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors">
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <input
            value={form.title}
            onChange={e => setForm(f => f ? { ...f, title: e.target.value } : f)}
            className="text-xl font-bold text-slate-900 bg-transparent border-none outline-none w-full focus:bg-white focus:border focus:border-slate-200 focus:rounded-lg focus:px-2 py-0.5"
          />
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={() => setForm(f => f ? { ...f, active: !f.active } : f)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50">
            {form.active
              ? <><ToggleRight size={15} className="text-emerald-500" /> Active</>
              : <><ToggleLeft size={15} className="text-slate-400" /> Inactive</>}
          </button>
          <button onClick={save} disabled={saving}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-semibold rounded-lg disabled:opacity-60 transition-colors"
            style={{ background: "var(--brand)", color: "var(--brand-ink)" }}
            onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-dark)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "var(--brand)"; e.currentTarget.style.color = "var(--brand-ink)"; }}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : saved ? <CheckCircle size={13} /> : <Save size={13} />}
            {saved ? "Saved!" : "Save"}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3">
          <AlertCircle size={15} className="shrink-0" /> {error}
          <button onClick={() => setError("")} className="ml-auto text-rose-400 hover:text-rose-600">✕</button>
        </div>
      )}

      {/* Share bar */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 flex items-center gap-3">
        <span className="text-xs text-slate-400 font-mono flex-1 truncate">{shareUrl}</span>
        <button onClick={copyLink}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 bg-white rounded-lg hover:bg-slate-50 text-slate-600 font-medium shrink-0">
          {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
          {copied ? "Copied!" : "Copy Link"}
        </button>
        <a href={`/f/${form.slug}`} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 bg-white rounded-lg hover:bg-slate-50 text-slate-600 shrink-0">
          <ExternalLink size={12} /> Preview
        </a>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white border border-slate-200 rounded-xl p-1 w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold rounded-lg transition-all"
            style={tab === t.id
              ? { background: "var(--brand)", color: "var(--brand-ink)" }
              : { background: "transparent", color: "#475569" }
            }
            onMouseEnter={e => { if (t.id !== tab) e.currentTarget.style.background = "color-mix(in srgb, var(--brand) 15%, transparent)"; }}
            onMouseLeave={e => { if (t.id !== tab) e.currentTarget.style.background = "transparent"; }}
          >
            <t.icon size={13} /> {t.label}
          </button>
        ))}
      </div>

      {/* ── FIELDS TAB ── */}
      {tab === "builder" && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-600 block mb-1">Form description (optional)</label>
            <input
              value={form.description}
              onChange={e => setForm(f => f ? { ...f, description: e.target.value } : f)}
              placeholder="Tell visitors what this form is for…"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
            />
          </div>

          <div>
            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Fields</p>

            <div className="space-y-2">
              {form.fields.map((field, idx) => (
                <FieldEditor
                  key={field.id}
                  field={field}
                  idx={idx}
                  total={form.fields.length}
                  onChange={patch => updateField(idx, patch)}
                  onRemove={() => removeField(idx)}
                  onMove={dir => moveField(idx, dir)}
                />
              ))}
            </div>

            {form.fields.length === 0 && (
              <div className="text-center py-8 border border-dashed border-slate-200 rounded-xl text-slate-400 text-sm">
                No fields yet — use the buttons below to add your first field
              </div>
            )}
          </div>

          {/* Add field buttons — below the list for easy access */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Add a field</p>
            <div className="flex flex-wrap gap-1.5">
              {([
                ["text",      "Text"],
                ["textarea",  "Long Text"],
                ["email",     "Email"],
                ["phone",     "Phone"],
                ["dropdown",  "Dropdown"],
                ["checklist", "Checklist"],
                ["checkbox",  "Checkbox"],
              ] as [FormField["type"], string][]).map(([type, label]) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => addField(type)}
                  className="flex items-center gap-1 text-[11px] font-medium bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 hover:border-slate-300 px-2.5 py-1.5 rounded-lg transition"
                >
                  <Plus size={11} /> {label}
                </button>
              ))}
            </div>
          </div>

          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-lg disabled:opacity-60 transition-colors"
            style={{ background: "var(--brand)", color: "var(--brand-ink)" }}
            onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-dark)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "var(--brand)"; e.currentTarget.style.color = "var(--brand-ink)"; }}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            Save Form
          </button>
        </div>
      )}

      {/* ── BRANDING TAB ── */}
      {tab === "branding" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Controls */}
          <div className="space-y-5">
            <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-800">Logo</p>
                <div className="flex items-center gap-3">
                  {b.logo_url && (
                    <>
                      <button
                        type="button"
                        onClick={handleCleanBackground}
                        disabled={cleaningLogo}
                        className="text-xs text-brand-dark hover:underline font-medium disabled:opacity-55 flex items-center gap-1"
                      >
                        {cleaningLogo && <Loader2 size={11} className="animate-spin" />}
                        Remove background
                      </button>
                      <span className="text-slate-200">|</span>
                    </>
                  )}
                  {b.logo_url && (
                    <button
                      onClick={() => setBranding({ logo_url: "" })}
                      className="text-xs text-rose-500 hover:text-rose-700 font-medium"
                    >
                      Remove logo
                    </button>
                  )}
                </div>
              </div>

              {b.logo_url ? (
                <div className="border border-slate-100 rounded-xl p-4 bg-slate-50 flex items-center justify-center h-28 relative group">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={resolveMediaUrl(b.logo_url) || b.logo_url}
                    alt="Current Logo"
                    className="max-h-full max-w-full object-contain"
                  />
                </div>
              ) : (
                <label className="border-2 border-dashed border-slate-200 hover:border-slate-300 rounded-xl p-6 flex flex-col items-center justify-center gap-2 cursor-pointer bg-slate-50/50 hover:bg-slate-50 transition-all h-28">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleLogoUpload}
                    disabled={uploadingLogo}
                    className="hidden"
                  />
                  {uploadingLogo ? (
                    <Loader2 size={20} className="animate-spin text-slate-400" />
                  ) : (
                    <Upload size={20} className="text-slate-400" />
                  )}
                  <span className="text-xs font-semibold text-slate-600">
                    {uploadingLogo ? "Uploading logo..." : "Upload logo image"}
                  </span>
                  <span className="text-[10px] text-slate-400">PNG, JPG or WebP</span>
                </label>
              )}

              {/* Presets from brand kit */}
              {brandLogos.length > 0 && (
                <div className="space-y-2 border-t border-slate-100 pt-3">
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Or select from Brand Kit
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {brandLogos.map((logo) => {
                      const isSelected = resolveMediaUrl(b.logo_url) === resolveMediaUrl(logo.file_url);
                      return (
                        <button
                          key={logo.id}
                          type="button"
                          onClick={() => setBranding({ logo_url: logo.file_url })}
                          className={`h-12 w-16 border rounded-lg p-1.5 flex items-center justify-center bg-white transition hover:border-slate-400 relative overflow-hidden ${
                            isSelected ? "border-slate-900 ring-2 ring-slate-900/25" : "border-slate-200"
                          }`}
                          title={logo.name || "Brand logo"}
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={resolveMediaUrl(logo.file_url) || logo.file_url}
                            alt={logo.name || "Brand logo"}
                            className="max-h-full max-w-full object-contain"
                          />
                          {logo.is_default && (
                            <span className="absolute bottom-0 inset-x-0 bg-slate-900/90 text-[8px] font-bold text-white text-center py-0.5 uppercase tracking-wide leading-none">
                              Default
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="border-t border-slate-100 pt-3">
                <details className="group">
                  <summary className="text-xs text-slate-500 cursor-pointer select-none hover:text-slate-700 font-medium">
                    Or use custom logo image URL
                  </summary>
                  <div className="mt-2.5">
                    <input
                      value={b.logo_url || ""}
                      onChange={e => setBranding({ logo_url: e.target.value })}
                      placeholder="https://yourdomain.com/logo.png"
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                    />
                    <p className="text-xs text-slate-400 mt-1">Paste a direct link to your logo image</p>
                  </div>
                </details>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
              <p className="text-sm font-semibold text-slate-800">Colors</p>

              <ColorRow
                label="Header background"
                desc="The top band color"
                value={b.header_bg || "#0f172a"}
                onChange={v => setBranding({ header_bg: v })}
              />
              <ColorRow
                label="Header text"
                desc="Title and description color"
                value={b.header_text || "#ffffff"}
                onChange={v => setBranding({ header_text: v })}
              />
              <ColorRow
                label="Submit button"
                desc="Background of the submit button"
                value={b.button_bg || "#0f172a"}
                onChange={v => setBranding({ button_bg: v })}
              />
              <ColorRow
                label="Button text"
                desc="Text on the submit button"
                value={b.button_text || "#ffffff"}
                onChange={v => setBranding({ button_text: v })}
              />
              <ColorRow
                label="Page background"
                desc="The page behind the form card"
                value={b.page_bg || "#f8fafc"}
                onChange={v => setBranding({ page_bg: v })}
              />

              <button
                onClick={() => setBranding({ ...DEFAULT_BRANDING })}
                className="text-xs text-slate-400 hover:text-slate-600 hover:underline"
              >
                Reset to defaults
              </button>
            </div>

            <button onClick={save} disabled={saving}
              className="flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-lg disabled:opacity-60 transition-colors"
              style={{ background: "var(--brand)", color: "var(--brand-ink)" }}
              onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-dark)"; e.currentTarget.style.color = "#fff"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "var(--brand)"; e.currentTarget.style.color = "var(--brand-ink)"; }}>
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              Save Branding
            </button>
          </div>

          {/* Live preview */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Live Preview</p>
            <div
              className="rounded-2xl overflow-hidden shadow-md border border-slate-200"
              style={{ background: b.page_bg || "#f8fafc" }}
            >
              {/* Header */}
              <div
                className="px-7 py-5"
                style={{ background: b.header_bg || "#0f172a" }}
              >
                {b.logo_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={resolveMediaUrl(b.logo_url) || b.logo_url}
                    alt="Logo"
                    className="h-9 w-auto object-contain mb-3"
                    onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                )}
                <p className="text-base font-bold" style={{ color: b.header_text || "#ffffff" }}>
                  {form.title}
                </p>
                {form.description && (
                  <p className="text-sm mt-0.5 opacity-70" style={{ color: b.header_text || "#ffffff" }}>
                    {form.description}
                  </p>
                )}
              </div>

              {/* Body preview */}
              <div className="px-7 py-5 space-y-3">
                {(form.fields.slice(0, 3)).map(field => (
                  <div key={field.id}>
                    {field.type === "checkbox" ? (
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-slate-700">
                          {field.label}{field.required && <span className="text-rose-500 ml-0.5">*</span>}
                        </p>
                        <label className="flex items-center gap-2.5 cursor-pointer py-1">
                          <input
                            type="checkbox"
                            disabled
                            className="w-4 h-4 rounded cursor-not-allowed"
                            style={{ accentColor: b.button_bg }}
                          />
                          <span className="text-xs text-slate-500 font-medium">
                            {field.placeholder || "Yes"}
                          </span>
                        </label>
                      </div>
                    ) : field.type === "checklist" ? (
                      <div className="space-y-1.5">
                        <p className="text-xs font-medium text-slate-700">
                          {field.label}{field.required && <span className="text-rose-500 ml-0.5">*</span>}
                        </p>
                        <div className="space-y-1">
                          {(field.options || ["Option 1", "Option 2"]).slice(0, 3).map((opt, oIdx) => (
                            <label key={oIdx} className="flex items-center gap-2.5 cursor-pointer py-0.5">
                              <input
                                type="checkbox"
                                disabled
                                className="w-4 h-4 rounded cursor-not-allowed"
                                style={{ accentColor: b.button_bg }}
                              />
                              <span className="text-xs text-slate-500 font-medium">{opt}</span>
                            </label>
                          ))}
                          {(field.options || []).length > 3 && (
                            <p className="text-[10px] text-slate-400">+{field.options.length - 3} more options</p>
                          )}
                        </div>
                      </div>
                    ) : field.type === "dropdown" ? (
                      <div>
                        <p className="text-xs font-medium text-slate-700 mb-1">
                          {field.label}{field.required && <span className="text-rose-500 ml-0.5">*</span>}
                        </p>
                        <div className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-400 bg-white flex items-center justify-between select-none">
                          <span>{field.placeholder || "Select option…"}</span>
                          <span className="text-slate-400">▼</span>
                        </div>
                      </div>
                    ) : field.type === "textarea" ? (
                      <div>
                        <p className="text-xs font-medium text-slate-700 mb-1">
                          {field.label}{field.required && <span className="text-rose-500 ml-0.5">*</span>}
                        </p>
                        <div className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-400 bg-white min-h-[60px]">
                          {field.placeholder || field.label}
                        </div>
                      </div>
                    ) : (
                      <div>
                        <p className="text-xs font-medium text-slate-700 mb-1">
                          {field.label}{field.required && <span className="text-rose-500 ml-0.5">*</span>}
                        </p>
                        <div className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-400 bg-white">
                          {field.placeholder || field.label}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                {form.fields.length > 3 && (
                  <p className="text-xs text-slate-400">+{form.fields.length - 3} more fields</p>
                )}

                {/* Submit button preview */}
                <div
                  className="w-full text-center py-2.5 rounded-xl text-sm font-semibold mt-2"
                  style={{ background: b.button_bg || "#0f172a", color: b.button_text || "#ffffff" }}
                >
                  Submit
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── SETTINGS TAB ── */}
      {tab === "settings_tab" && (
        <div className="space-y-4 max-w-xl">
          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">Success message</label>
              <p className="text-xs text-slate-400 mb-2">Shown after the visitor submits</p>
              <input
                value={form.settings?.success_message ?? ""}
                onChange={e => setForm(f => f ? { ...f, settings: { ...f.settings, success_message: e.target.value } } : f)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
              />
            </div>

            <div className="flex items-center justify-between py-2 border-t border-slate-100">
              <div>
                <p className="text-sm font-medium text-slate-700">Auto-create contact</p>
                <p className="text-xs text-slate-400">Name, phone & email saved automatically as a contact</p>
              </div>
              <button
                onClick={() => setForm(f => f ? {
                  ...f, settings: { ...f.settings, create_contact: !f.settings?.create_contact }
                } : f)}
                className={`w-11 h-6 rounded-full relative transition-colors ${
                  form.settings?.create_contact !== false ? "bg-emerald-500" : "bg-slate-200"
                }`}
              >
                <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-all ${
                  form.settings?.create_contact !== false ? "left-5" : "left-0.5"
                }`} />
              </button>
            </div>
          </div>

          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-lg disabled:opacity-60 transition-colors"
            style={{ background: "var(--brand)", color: "var(--brand-ink)" }}
            onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-dark)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "var(--brand)"; e.currentTarget.style.color = "var(--brand-ink)"; }}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            Save Settings
          </button>
        </div>
      )}

      {/* ── RESPONSES TAB ── */}
      {tab === "responses" && (
        <div className="space-y-4">
          {responses.length === 0 ? (
            <div className="bg-white rounded-xl border border-dashed border-slate-200 p-12 text-center">
              <BarChart2 size={32} className="mx-auto text-slate-200 mb-3" />
              <p className="font-semibold text-slate-600">No responses yet</p>
              <p className="text-sm text-slate-400 mt-1">Share your form link to start collecting submissions</p>
            </div>
          ) : (
            <>
              <p className="text-sm text-slate-500">{responses.length} response{responses.length !== 1 ? "s" : ""}</p>
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">Date</th>
                      {form.fields.map(f => (
                        <th key={f.id} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">
                          {f.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {responses.map(r => (
                      <tr key={r._id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">
                          {new Date(r.created_at).toLocaleString()}
                        </td>
                        {form.fields.map(f => (
                          <td key={f.id} className="px-4 py-3 text-sm text-slate-700 max-w-xs">
                            <span className="truncate block">{r.data[f.label] ?? r.data[f.id] ?? "—"}</span>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ColorRow({
  label, desc, value, onChange,
}: {
  label: string; desc: string; value: string; onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-700">{label}</p>
        <p className="text-xs text-slate-400">{desc}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-24 text-xs border border-slate-200 rounded-lg px-2 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-slate-300"
        />
        <label className="relative cursor-pointer">
          <input
            type="color"
            value={value}
            onChange={e => onChange(e.target.value)}
            className="opacity-0 absolute inset-0 w-full h-full cursor-pointer"
          />
          <div
            className="w-8 h-8 rounded-lg border-2 border-slate-200 shadow-sm"
            style={{ background: value }}
          />
        </label>
      </div>
    </div>
  );
}

function FieldEditor({
  field, idx, total, onChange, onRemove, onMove,
}: {
  field: FormField;
  idx: number;
  total: number;
  onChange: (p: Partial<FormField>) => void;
  onRemove: () => void;
  onMove: (dir: -1 | 1) => void;
}) {
  // Local label state so typing feels instant and doesn't get reset by parent re-renders
  const [localLabel, setLocalLabel] = useState(field.label);
  useEffect(() => { setLocalLabel(field.label); }, [field.id]); // only sync when field identity changes
  const hasOptions = field.type === "dropdown" || field.type === "checklist";
  const [bulkMode, setBulkMode] = useState(false);

  const options = field.options || [];

  // When the type changes, auto-initialise options if needed
  function handleTypeChange(newType: FormField["type"]) {
    const patch: Partial<FormField> = { type: newType };
    if ((newType === "dropdown" || newType === "checklist") && (!field.options || field.options.length === 0)) {
      patch.options = ["Option 1", "Option 2"];
    }
    if (newType !== "dropdown" && newType !== "checklist") {
      patch.options = undefined;
    }
    if (newType === "checkbox") {
      patch.placeholder = field.placeholder || "Yes, I agree";
    }
    onChange(patch);
  }

  const addOption = () => {
    onChange({ options: [...options, `Option ${options.length + 1}`] });
  };

  const addOtherOption = () => {
    onChange({ options: [...options, "Other (please specify)"] });
  };

  const updateOption = (optIdx: number, val: string) => {
    const updated = options.map((opt, i) => i === optIdx ? val : opt);
    onChange({ options: updated });
  };

  const removeOption = (optIdx: number) => {
    onChange({ options: options.filter((_, i) => i !== optIdx) });
  };

  const applyPreset = (preset: string[]) => {
    onChange({ options: preset });
  };

  // Type hint badge text
  const typeHint = FIELD_TYPES.find(t => t.value === field.type)?.hint ?? "";

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      {/* Field header row */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-slate-100">
        {/* Move handles */}
        <div className="flex flex-col gap-0.5 shrink-0">
          <button onClick={() => onMove(-1)} disabled={idx === 0}
            className="p-0.5 text-slate-300 hover:text-slate-500 disabled:opacity-30">
            <GripVertical size={12} className="rotate-180" />
          </button>
          <button onClick={() => onMove(1)} disabled={idx === total - 1}
            className="p-0.5 text-slate-300 hover:text-slate-500 disabled:opacity-30">
            <GripVertical size={12} />
          </button>
        </div>

        {/* Field type selector */}
        <select
          value={field.type}
          onChange={e => handleTypeChange(e.target.value as FormField["type"])}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none shrink-0 font-medium"
        >
          {FIELD_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>

        {/* Field label */}
        <input
          value={localLabel}
          onChange={e => {
            setLocalLabel(e.target.value);
            onChange({ label: e.target.value });
          }}
          onBlur={() => onChange({ label: localLabel })}
          placeholder="Field label"
          className="flex-1 text-sm border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-slate-300"
        />

        {/* Required toggle */}
        <label className="flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer shrink-0">
          <input
            type="checkbox"
            checked={field.required}
            onChange={e => onChange({ required: e.target.checked })}
            className="w-3.5 h-3.5 accent-slate-800"
          />
          Required
        </label>

        {/* Remove button */}
        <button onClick={onRemove}
          className="p-1.5 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors">
          <Trash2 size={13} />
        </button>
      </div>

      {/* Type hint */}
      <div className="px-4 pt-2.5">
        <span className="inline-flex items-center text-[10px] font-medium text-slate-400 bg-slate-50 border border-slate-100 rounded-full px-2.5 py-0.5">
          {typeHint}
        </span>
      </div>

      {/* Field-specific controls */}
      <div className="px-4 pb-4 pt-2.5 space-y-3">

        {/* CHECKBOX: single tick with label text */}
        {field.type === "checkbox" && (
          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              Label shown next to the checkbox
            </label>
            <input
              value={field.placeholder || ""}
              onChange={e => onChange({ placeholder: e.target.value })}
              placeholder="e.g. Yes, I agree to the terms and conditions"
              className="w-full text-sm border border-slate-200 bg-slate-50 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-slate-300"
            />
            <p className="text-[10px] text-slate-400">
              The visitor will see a single tick box. When ticked it records <strong>yes</strong>, unticked records <strong>no</strong>.
            </p>
          </div>
        )}

        {/* TEXT / EMAIL / PHONE / TEXTAREA: placeholder */}
        {(field.type === "text" || field.type === "email" || field.type === "phone" || field.type === "textarea") && (
          <div className="space-y-1">
            <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              Placeholder text (optional)
            </label>
            <input
              value={field.placeholder || ""}
              onChange={e => onChange({ placeholder: e.target.value })}
              placeholder="Hint shown inside the input…"
              className="w-full text-sm border border-slate-200 bg-slate-50 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-slate-300"
            />
          </div>
        )}

        {/* DROPDOWN / CHECKLIST: options builder */}
        {hasOptions && (
          <div className="bg-slate-50 border border-slate-100 rounded-lg p-3 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                {field.type === "checklist" ? "Options (visitor can tick many)" : "Options (visitor picks one)"}
              </span>
              <button
                type="button"
                onClick={() => setBulkMode(!bulkMode)}
                className="text-[10px] text-brand-dark hover:underline font-semibold"
              >
                {bulkMode ? "Visual editor" : "Paste a list"}
              </button>
            </div>

            {/* Quick presets — dropdown only */}
            {!bulkMode && field.type === "dropdown" && (
              <div className="flex flex-wrap gap-1.5 pb-1 border-b border-slate-100">
                <span className="text-[10px] text-slate-400 self-center">Quick fill:</span>
                {([
                  [["Yes", "No"], "Yes / No"],
                  [["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"], "Ratings"],
                  [["Morning (8AM – 12PM)", "Afternoon (12PM – 4PM)", "Evening (4PM – 8PM)"], "Time slots"],
                  [["Under 10,000", "10,000–50,000", "50,000–100,000", "Above 100,000"], "Budget"],
                ] as [string[], string][]).map(([preset, name]) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => applyPreset(preset)}
                    className="text-[10px] bg-white border border-slate-200 hover:border-slate-400 hover:bg-slate-50 text-slate-600 px-2 py-0.5 rounded-md transition font-medium"
                  >
                    {name}
                  </button>
                ))}
              </div>
            )}

            {/* Bulk import */}
            {bulkMode ? (
              <div className="space-y-1">
                <textarea
                  value={options.join("\n")}
                  onChange={e => onChange({ options: e.target.value.split("\n").map(o => o.trim()).filter(Boolean) })}
                  rows={5}
                  placeholder={"Paste each option on its own line:\nOption A\nOption B\nOption C"}
                  className="w-full text-xs border border-slate-200 bg-white rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-slate-300 font-mono"
                />
                <p className="text-[9px] text-slate-400">One option per line. Empty lines are ignored.</p>
              </div>
            ) : (
              /* Visual option list */
              <div className="space-y-2">
                <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                  {options.map((opt, oIdx) => (
                    <div key={oIdx} className="flex items-center gap-2">
                      {/* Bullet/number */}
                      {field.type === "checklist" ? (
                        <span className="w-4 h-4 border-2 border-slate-300 rounded shrink-0" />
                      ) : (
                        <span className="text-[10px] text-slate-400 font-mono w-5 text-right shrink-0">{oIdx + 1}.</span>
                      )}
                      <input
                        value={opt}
                        onChange={e => updateOption(oIdx, e.target.value)}
                        onKeyDown={e => {
                          if (e.key === "Enter") { e.preventDefault(); addOption(); }
                        }}
                        autoFocus={oIdx === options.length - 1 && (opt.startsWith("Option ") || opt === "Other (please specify)")}
                        placeholder={`Option ${oIdx + 1}`}
                        className="flex-1 text-sm border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-slate-300"
                      />
                      <button
                        type="button"
                        onClick={() => removeOption(oIdx)}
                        disabled={options.length <= 1}
                        className="text-slate-400 hover:text-rose-500 p-1 rounded hover:bg-rose-50 transition disabled:opacity-30"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                  {options.length === 0 && (
                    <p className="text-[11px] text-slate-400 italic py-2 text-center bg-white rounded border border-dashed border-slate-200">
                      No options yet — click &quot;+ Add option&quot; below
                    </p>
                  )}
                </div>

                {/* Add button */}
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={addOption}
                    className="flex items-center gap-1 text-xs font-semibold text-brand-dark hover:underline"
                  >
                    <Plus size={12} /> Add option
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
