"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Loader2, CheckCircle, AlertCircle, Send } from "lucide-react";

interface PublicField {
  id: string;
  type: "text" | "email" | "phone" | "textarea" | "dropdown" | "checkbox";
  label: string;
  placeholder: string;
  required: boolean;
  options?: string[];
}

interface Branding {
  logo_url?: string;
  header_bg?: string;
  header_text?: string;
  button_bg?: string;
  button_text?: string;
  page_bg?: string;
}

interface PublicForm {
  id: string;
  title: string;
  description: string;
  fields: PublicField[];
  settings: { success_message: string };
  branding: Branding;
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const DEFAULT_BRANDING: Required<Branding> = {
  logo_url: "",
  header_bg: "#0f172a",
  header_text: "#ffffff",
  button_bg: "#0f172a",
  button_text: "#ffffff",
  page_bg: "#f8fafc",
};

export default function PublicFormPage() {
  const { slug } = useParams<{ slug: string }>();
  const [form, setForm] = useState<PublicForm | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    fetch(`${API}/forms/public/${slug}`)
      .then(r => {
        if (!r.ok) { setNotFound(true); return null; }
        return r.json();
      })
      .then(data => {
        if (data) {
          setForm(data);
          const init: Record<string, string> = {};
          data.fields.forEach((f: PublicField) => { init[f.label] = ""; });
          setValues(init);
        }
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [slug]);

  function validate(): boolean {
    if (!form) return false;
    const errs: Record<string, string> = {};
    form.fields.forEach(f => {
      if (f.required && !values[f.label]?.trim()) {
        errs[f.label] = `${f.label} is required`;
      }
      if (f.type === "email" && values[f.label] && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values[f.label])) {
        errs[f.label] = "Please enter a valid email address";
      }
    });
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate() || !form) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/forms/public/${slug}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: values }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Submission failed");
      }
      const result = await res.json();
      setSuccessMessage(result.message || form.settings.success_message);
    } catch (err: unknown) {
      setErrors({ _form: err instanceof Error ? err.message : "Something went wrong. Please try again." });
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: DEFAULT_BRANDING.page_bg }}>
      <Loader2 size={28} className="animate-spin text-slate-400" />
    </div>
  );

  if (notFound) return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: DEFAULT_BRANDING.page_bg }}>
      <div className="text-center max-w-sm">
        <AlertCircle size={40} className="mx-auto text-slate-300 mb-3" />
        <h2 className="text-lg font-bold text-slate-700">Form not found</h2>
        <p className="text-sm text-slate-500 mt-1">This form may have been removed or is no longer active.</p>
      </div>
    </div>
  );

  if (!form) return null;

  const br: Required<Branding> = { ...DEFAULT_BRANDING, ...form.branding };

  if (successMessage) return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: br.page_bg }}>
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-10 text-center max-w-sm w-full">
        {br.logo_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={br.logo_url}
            alt="Logo"
            className="h-10 w-auto object-contain mx-auto mb-5"
            onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        )}
        <div
          className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4"
          style={{ background: br.button_bg + "20" }}
        >
          <CheckCircle size={28} style={{ color: br.button_bg }} />
        </div>
        <h2 className="text-xl font-bold text-slate-800 mb-2">Submitted!</h2>
        <p className="text-slate-500 text-sm leading-relaxed">{successMessage}</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen py-12 px-4 flex items-start justify-center" style={{ background: br.page_bg }}>
      <div className="w-full max-w-lg">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          {/* Branded header */}
          <div className="px-8 py-6" style={{ background: br.header_bg }}>
            {br.logo_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={br.logo_url}
                alt="Logo"
                className="h-10 w-auto object-contain mb-4"
                onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
            )}
            <h1 className="text-xl font-bold" style={{ color: br.header_text }}>
              {form.title}
            </h1>
            {form.description && (
              <p className="text-sm mt-1 leading-relaxed" style={{ color: br.header_text, opacity: 0.75 }}>
                {form.description}
              </p>
            )}
          </div>

          {/* Form body */}
          <form onSubmit={submit} className="px-8 py-7 space-y-5">
            {errors._form && (
              <div className="flex items-center gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3">
                <AlertCircle size={15} className="shrink-0" /> {errors._form}
              </div>
            )}

            {form.fields.map(field => (
              <div key={field.id}>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  {field.label}
                  {field.required && <span className="text-rose-500 ml-0.5">*</span>}
                </label>

                {field.type === "textarea" ? (
                  <textarea
                    value={values[field.label] ?? ""}
                    onChange={e => setValues(v => ({ ...v, [field.label]: e.target.value }))}
                    placeholder={field.placeholder}
                    rows={4}
                    className={`w-full border rounded-xl px-4 py-3 text-sm resize-none focus:outline-none transition-colors ${
                      errors[field.label]
                        ? "border-rose-300 bg-rose-50 focus:ring-2 focus:ring-rose-200"
                        : "border-slate-200 bg-white hover:border-slate-300 focus:ring-2 focus:ring-slate-200"
                    }`}
                  />
                ) : field.type === "dropdown" ? (
                  <select
                    value={values[field.label] ?? ""}
                    onChange={e => setValues(v => ({ ...v, [field.label]: e.target.value }))}
                    className={`w-full border rounded-xl px-4 py-3 text-sm bg-white focus:outline-none transition-colors ${
                      errors[field.label]
                        ? "border-rose-300 bg-rose-50 focus:ring-2 focus:ring-rose-200"
                        : "border-slate-200 hover:border-slate-300 focus:ring-2 focus:ring-slate-200"
                    }`}
                  >
                    <option value="">Select an option…</option>
                    {(field.options || []).map(opt => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                ) : field.type === "checkbox" ? (
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={values[field.label] === "yes"}
                      onChange={e => setValues(v => ({ ...v, [field.label]: e.target.checked ? "yes" : "no" }))}
                      className="w-5 h-5 rounded cursor-pointer"
                      style={{ accentColor: br.button_bg }}
                    />
                    <span className="text-sm text-slate-600">{field.placeholder || "Yes"}</span>
                  </label>
                ) : (
                  <input
                    type={field.type === "email" ? "email" : field.type === "phone" ? "tel" : "text"}
                    value={values[field.label] ?? ""}
                    onChange={e => setValues(v => ({ ...v, [field.label]: e.target.value }))}
                    placeholder={field.placeholder}
                    className={`w-full border rounded-xl px-4 py-3 text-sm focus:outline-none transition-colors ${
                      errors[field.label]
                        ? "border-rose-300 bg-rose-50 focus:ring-2 focus:ring-rose-200"
                        : "border-slate-200 bg-white hover:border-slate-300 focus:ring-2 focus:ring-slate-200"
                    }`}
                  />
                )}

                {errors[field.label] && (
                  <p className="text-xs text-rose-500 mt-1">{errors[field.label]}</p>
                )}
              </div>
            ))}

            {/* Branded submit button */}
            <button
              type="submit"
              disabled={submitting}
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl text-sm font-semibold disabled:opacity-60 transition-opacity mt-2"
              style={{ background: br.button_bg, color: br.button_text }}
            >
              {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={15} />}
              {submitting ? "Submitting…" : "Submit"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-slate-400 mt-5">Powered by Zilo</p>
      </div>
    </div>
  );
}
