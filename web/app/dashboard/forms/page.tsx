"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import {
  FileInput, Plus, Copy, Check, Trash2, Edit2, ExternalLink,
  Loader2, AlertCircle, BarChart2, ToggleLeft, ToggleRight, Users, Search, X,
} from "lucide-react";

interface Form {
  _id: string;
  title: string;
  description: string;
  slug: string;
  active: boolean;
  response_count: number;
  created_at: string;
}

export default function FormsPage() {
  const router = useRouter();
  const [forms, setForms] = useState<Form[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const data = await api.get<{ forms: Form[] }>("/forms");
      setForms(data.forms);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load forms");
    } finally {
      setLoading(false);
    }
  }

  async function createForm() {
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const form = await api.post<Form>("/forms", { title: newTitle.trim() });
      router.push(`/dashboard/forms/${form._id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create form");
      setCreating(false);
    }
  }

  async function deleteForm(id: string) {
    if (!confirm("Delete this form and all its responses?")) return;
    setDeleting(id);
    try {
      await api.delete(`/forms/${id}`);
      setForms(f => f.filter(x => x._id !== id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setDeleting(null);
    }
  }

  async function toggleActive(form: Form) {
    try {
      await api.put(`/forms/${form._id}`, { ...form, active: !form.active });
      setForms(fs => fs.map(f => f._id === form._id ? { ...f, active: !f.active } : f));
    } catch { /* ignore */ }
  }

  function copyLink(slug: string) {
    const url = `${window.location.origin}/f/${slug}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(slug);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  const filtered = query.trim()
    ? forms.filter(f =>
        f.title.toLowerCase().includes(query.toLowerCase()) ||
        f.description?.toLowerCase().includes(query.toLowerCase())
      )
    : forms;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Forms</h1>
          <p className="text-sm text-slate-500 mt-1">Create shareable forms — submissions land as contacts in your CRM</p>
        </div>
        <button
          onClick={() => { setShowModal(true); setNewTitle(""); }}
          className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-colors"
          style={{ background: "var(--brand)", color: "var(--brand-ink)" }}
          onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-dark)"; e.currentTarget.style.color = "#fff"; }}
          onMouseLeave={e => { e.currentTarget.style.background = "var(--brand)"; e.currentTarget.style.color = "var(--brand-ink)"; }}
        >
          <Plus size={15} /> New Form
        </button>
      </div>

      {/* Search bar — only shown once forms exist */}
      {!loading && forms.length > 0 && (
        <div className="relative">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search forms by name or description…"
            className="w-full pl-10 pr-10 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-slate-200 placeholder:text-slate-400"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X size={14} />
            </button>
          )}
        </div>
      )}

      {/* Result count hint */}
      {query && (
        <p className="text-xs text-slate-400 -mt-3">
          {filtered.length === 0
            ? `No forms match "${query}"`
            : `${filtered.length} form${filtered.length !== 1 ? "s" : ""} found`}
        </p>
      )}

      {error && (
        <div className="flex items-center gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3">
          <AlertCircle size={15} className="shrink-0" /> {error}
          <button onClick={() => setError("")} className="ml-auto text-rose-400 hover:text-rose-600">✕</button>
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-bold text-slate-900">Create New Form</h2>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Form name</label>
              <input
                autoFocus
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                onKeyDown={e => e.key === "Enter" && createForm()}
                placeholder="e.g. Service Request, Contact Us, Booking Inquiry…"
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
              >
                Cancel
              </button>
              <button
                onClick={createForm}
                disabled={creating || !newTitle.trim()}
                className="flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-lg disabled:opacity-50 transition-colors"
                style={{ background: "var(--brand)", color: "var(--brand-ink)" }}
                onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-dark)"; e.currentTarget.style.color = "#fff"; }}
                onMouseLeave={e => { e.currentTarget.style.background = "var(--brand)"; e.currentTarget.style.color = "var(--brand-ink)"; }}
              >
                {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                Create & Edit
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Forms grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse h-40" />
          ))}
        </div>
      ) : forms.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-slate-200 p-16 text-center">
          <FileInput size={36} className="mx-auto text-slate-200 mb-3" />
          <p className="font-semibold text-slate-600">No forms yet</p>
          <p className="text-sm text-slate-400 mt-1 mb-5">Create your first form and share the link anywhere</p>
          <button
            onClick={() => setShowModal(true)}
            className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-lg transition-colors"
            style={{ background: "var(--brand)", color: "var(--brand-ink)" }}
            onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-dark)"; e.currentTarget.style.color = "#fff"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "var(--brand)"; e.currentTarget.style.color = "var(--brand-ink)"; }}
          >
            <Plus size={14} /> Create Form
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-slate-200 p-12 text-center">
          <Search size={32} className="mx-auto text-slate-200 mb-3" />
          <p className="font-semibold text-slate-600">No results for &quot;{query}&quot;</p>
          <p className="text-sm text-slate-400 mt-1">Try a different search term</p>
          <button onClick={() => setQuery("")} className="mt-4 text-xs text-slate-500 hover:underline">
            Clear search
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(form => (
            <div key={form._id} className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col gap-3 hover:border-slate-300 transition-colors">
              {/* Title row */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-slate-800 text-sm truncate">{form.title}</p>
                  {form.description && (
                    <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{form.description}</p>
                  )}
                </div>
                <button
                  onClick={() => toggleActive(form)}
                  title={form.active ? "Active — click to deactivate" : "Inactive — click to activate"}
                >
                  {form.active
                    ? <ToggleRight size={22} className="text-emerald-500" />
                    : <ToggleLeft size={22} className="text-slate-300" />}
                </button>
              </div>

              {/* Stats */}
              <div className="flex items-center gap-4 text-xs text-slate-500">
                <span className="flex items-center gap-1">
                  <Users size={12} /> {form.response_count} response{form.response_count !== 1 ? "s" : ""}
                </span>
                <span className="flex items-center gap-1">
                  <BarChart2 size={12} /> {new Date(form.created_at).toLocaleDateString()}
                </span>
              </div>

              {/* Link row */}
              <div className="flex items-center gap-1.5 bg-slate-50 rounded-lg px-3 py-1.5 text-xs text-slate-500 font-mono truncate">
                <span className="flex-1 truncate">/f/{form.slug}</span>
                <button
                  onClick={() => copyLink(form.slug)}
                  className="shrink-0 text-slate-400 hover:text-slate-700 transition-colors"
                  title="Copy link"
                >
                  {copied === form.slug ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                </button>
                <a
                  href={`/f/${form.slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-slate-400 hover:text-slate-700 transition-colors"
                  title="Open form"
                >
                  <ExternalLink size={12} />
                </a>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 pt-1 border-t border-slate-100">
                <button
                  onClick={() => router.push(`/dashboard/forms/${form._id}`)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 font-medium"
                >
                  <Edit2 size={11} /> Edit
                </button>
                <button
                  onClick={() => router.push(`/dashboard/forms/${form._id}?tab=responses`)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
                >
                  <BarChart2 size={11} /> Responses
                </button>
                <button
                  onClick={() => deleteForm(form._id)}
                  disabled={deleting === form._id}
                  className="ml-auto p-1.5 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors"
                >
                  {deleting === form._id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
