"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import {
  ArrowLeft, Plus, Trash2, GripVertical, Copy, Check,
  Loader2, AlertCircle, ExternalLink, CheckCircle, Save,
  BarChart2, Settings, Layers, ToggleLeft, ToggleRight, Palette,
} from "lucide-react";

interface FormField {
  id: string;
  type: "text" | "email" | "phone" | "textarea" | "dropdown" | "checkbox";
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
  { value: "text", label: "Short Text" },
  { value: "textarea", label: "Long Text" },
  { value: "email", label: "Email" },
  { value: "phone", label: "Phone" },
  { value: "dropdown", label: "Dropdown" },
  { value: "checkbox", label: "Checkbox (Yes/No)" },
];

const DEFAULT_BRANDING: FormBranding = {
  logo_url: "",
  header_bg: "#0f172a",
  header_text: "#ffffff",
  button_bg: "#0f172a",
  button_text: "#ffffff",
  page_bg: "#f8fafc",
};

function newField(): FormField {
  return {
    id: Math.random().toString(36).slice(2, 10),
    type: "text",
    label: "New Field",
    placeholder: "",
    required: false,
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

  useEffect(() => {
    loadForm();
    loadResponses();
  }, [loadForm, loadResponses]);

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

  function addField() {
    setForm(f => f ? { ...f, fields: [...f.fields, newField()] } : f);
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
            className="flex items-center gap-1.5 px-4 py-1.5 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-60">
            {saving ? <Loader2 size={13} className="animate-spin" /> : saved ? <CheckCircle size={13} className="text-emerald-400" /> : <Save size={13} />}
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
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              tab === t.id ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"
            }`}>
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
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Fields</p>
              <button onClick={addField}
                className="flex items-center gap-1 text-xs text-brand-dark hover:underline font-medium">
                <Plus size={12} /> Add field
              </button>
            </div>

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
                No fields yet — click &quot;Add field&quot; to start
              </div>
            )}
          </div>

          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-5 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-60">
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
              <p className="text-sm font-semibold text-slate-800">Logo</p>
              <div>
                <label className="text-xs text-slate-500 block mb-1.5">Logo URL</label>
                <input
                  value={b.logo_url || ""}
                  onChange={e => setBranding({ logo_url: e.target.value })}
                  placeholder="https://yourdomain.com/logo.png"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                />
                <p className="text-xs text-slate-400 mt-1">Paste a direct link to your logo image</p>
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
              className="flex items-center gap-2 px-5 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-60">
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
                    src={b.logo_url}
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
                    <p className="text-xs font-medium text-slate-700 mb-1">
                      {field.label}{field.required && <span className="text-rose-500 ml-0.5">*</span>}
                    </p>
                    <div className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-400 bg-white">
                      {field.placeholder || field.label}
                    </div>
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
            className="flex items-center gap-2 px-5 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-60">
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
  const hasOptions = field.type === "dropdown";

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
      <div className="flex items-center gap-2">
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

        <select
          value={field.type}
          onChange={e => onChange({ type: e.target.value as FormField["type"] })}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none shrink-0"
        >
          {FIELD_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>

        <input
          value={field.label}
          onChange={e => onChange({ label: e.target.value })}
          placeholder="Field label"
          className="flex-1 text-sm border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-slate-300"
        />

        <label className="flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer shrink-0">
          <input
            type="checkbox"
            checked={field.required}
            onChange={e => onChange({ required: e.target.checked })}
            className="w-3.5 h-3.5 accent-slate-800"
          />
          Required
        </label>

        <button onClick={onRemove}
          className="p-1.5 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors">
          <Trash2 size={13} />
        </button>
      </div>

      {field.type !== "checkbox" && (
        <input
          value={field.placeholder || ""}
          onChange={e => onChange({ placeholder: e.target.value })}
          placeholder="Placeholder text (optional)"
          className="w-full text-xs border border-slate-100 bg-slate-50 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-slate-200"
        />
      )}

      {hasOptions && (
        <div>
          <p className="text-xs text-slate-500 mb-1">Options (one per line)</p>
          <textarea
            value={(field.options || []).join("\n")}
            onChange={e => onChange({ options: e.target.value.split("\n").map(o => o.trim()).filter(Boolean) })}
            rows={3}
            placeholder={"Option 1\nOption 2\nOption 3"}
            className="w-full text-xs border border-slate-100 bg-slate-50 rounded-lg px-2.5 py-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-slate-200"
          />
        </div>
      )}
    </div>
  );
}
