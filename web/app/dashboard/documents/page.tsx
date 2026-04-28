"use client";

import { useEffect, useState } from "react";
import {
  FileText, Download, Trash2, Loader2, Calendar,
  File, FileSpreadsheet, Presentation,
  Search, RefreshCw, Eye, X, Copy, MessageSquare, ArrowUpDown,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { cn, resolveMediaUrl, downloadAsset } from "@/lib/utils";

type Document = {
  id: string;
  name: string;
  asset_kind: string;
  file_url: string;
  thumbnail_url: string;
  source: string;
  source_tool: string;
  format_label: string;
  created_at: string;
  conversation_id?: string;
};

type Category = "all" | "pdf" | "docx" | "pptx";
type SortKey = "newest" | "oldest" | "az";

function CloneModal({ doc, onClose, onCloned }: { doc: Document; onClose: () => void; onCloned: (d: Document) => void }) {
  const [name, setName] = useState(`Clone of ${doc.name}`);
  const [saving, setSaving] = useState(false);
  const [cloned, setCloned] = useState<Document | null>(null);

  const handleClone = async () => {
    setSaving(true);
    try {
      const result = await api.post<Document>(`/design-templates/${doc.id}/clone`, {});
      const finalName = name.trim();
      const finalDoc = (finalName && finalName !== `Clone of ${doc.name}`)
        ? await api.put<Document>(`/design-templates/${result.id}`, { name: finalName })
        : result;
      onCloned(finalDoc);
      setCloned(finalDoc);
      toast.success("Document cloned");
    } catch {
      toast.error("Clone failed");
    } finally {
      setSaving(false);
    }
  };

  const kindLabel: Record<string, string> = { pdf: "PDF", docx: "Word document", pptx: "PowerPoint presentation" };
  const toolHint: Record<string, string> = { pdf: "create_business_document", docx: "create_business_document", pptx: "create_presentation" };
  const templatePrompt = cloned
    ? `I want to generate a new ${kindLabel[cloned.asset_kind] ?? "document"} using my saved template "${cloned.name}" as the style reference (file: ${resolveMediaUrl(cloned.file_url)}). This is a custom document from my Documents library — do NOT search Orshot for it. Use the ${toolHint[cloned.asset_kind] ?? "create_business_document"} tool to produce a new document that matches the same sections, layout, tone, and professional structure as that template. Ask me what content to fill in.`
    : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
        {!cloned ? (
          <>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Clone Document</h2>
                <p className="text-xs text-slate-500 mt-0.5">Create a reusable copy of this document</p>
              </div>
              <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="mb-4">
              <label className="block text-xs font-medium text-slate-700 mb-1.5">Clone name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/50"
              />
              <p className="text-xs text-slate-400 mt-1.5">After cloning, you can open Zilo Chat and the AI will know to follow this template.</p>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors">Cancel</button>
              <button
                onClick={handleClone}
                disabled={saving || !name.trim()}
                className="px-4 py-2 text-sm rounded-lg bg-brand-dark text-white font-medium hover:bg-brand-dark/90 disabled:opacity-50 transition-colors flex items-center gap-1.5"
              >
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Copy className="w-3.5 h-3.5" />}
                Clone
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-violet-100 flex items-center justify-center shrink-0">
                <Copy className="w-4 h-4 text-violet-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Clone created!</h2>
                <p className="text-xs text-slate-500 mt-0.5">"{cloned.name}" is ready to use as a template</p>
              </div>
            </div>
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 mb-4">
              <p className="text-xs font-medium text-slate-700 mb-1">Zilo Chat will receive this prompt:</p>
              <p className="text-xs text-slate-500 leading-relaxed italic">"{templatePrompt}"</p>
            </div>
            <div className="flex flex-col gap-2">
              <Link
                href={`/dashboard/assistant?template_message=${encodeURIComponent(templatePrompt)}`}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm rounded-lg bg-[#009B3A] text-white font-medium hover:bg-[#4CD137] hover:text-[#0a2614] transition-colors"
                onClick={onClose}
              >
                <MessageSquare className="w-4 h-4" />
                Open in Zilo Chat with template
              </Link>
              <button onClick={onClose} className="w-full px-4 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors">
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function PreviewModal({ doc, onClose }: { doc: Document; onClose: () => void }) {
  const url = resolveMediaUrl(doc.file_url);
  const isPdf = doc.asset_kind === "pdf";
  const viewerUrl = isPdf
    ? url
    : `https://docs.google.com/viewer?url=${encodeURIComponent(url)}&embedded=true`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <FileText className="w-4 h-4 text-slate-500 shrink-0" />
            <span className="text-sm font-medium text-slate-800 truncate">{doc.name}</span>
            <span className="text-xs text-slate-400 uppercase shrink-0">{doc.asset_kind}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-3">
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
            >
              Open in new tab
            </a>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-hidden">
          {isPdf ? (
            <embed
              src={url}
              type="application/pdf"
              className="w-full h-full"
            />
          ) : (
            <iframe
              src={viewerUrl}
              className="w-full h-full border-0"
              title={doc.name}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<Category>("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");
  const [deleting, setDeleting] = useState<string | null>(null);
  const [preview, setPreview] = useState<Document | null>(null);
  const [cloning, setCloning] = useState<Document | null>(null);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const res = await api.get<Document[]>("/design-templates?source=assistant_generated");
      setDocuments(res || []);
    } catch (e) {
      console.error(e);
      toast.error("Failed to load documents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDocuments(); }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this document?")) return;
    setDeleting(id);
    try {
      await api.delete(`/design-templates/${id}`);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      toast.success("Document deleted");
    } catch (e) {
      console.error(e);
      toast.error("Failed to delete");
    } finally {
      setDeleting(null);
    }
  };

  const handleDownload = async (url: string, name: string) => {
    try { await downloadAsset(url, name); }
    catch { toast.error("Download failed"); }
  };

  const DOC_KINDS = ["pdf", "docx", "pptx"];

  const counts = {
    pdf: documents.filter((d) => d.asset_kind === "pdf").length,
    docx: documents.filter((d) => d.asset_kind === "docx").length,
    pptx: documents.filter((d) => d.asset_kind === "pptx").length,
  };

  const filtered = documents
    .filter((d) => {
      const isDocument = DOC_KINDS.includes(d.asset_kind);
      const matchesCategory = category === "all" || d.asset_kind === category;
      const matchesSearch = search === "" || d.name.toLowerCase().includes(search.toLowerCase());
      return isDocument && matchesCategory && matchesSearch;
    })
    .sort((a, b) => {
      if (sort === "newest") return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      if (sort === "oldest") return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      return a.name.localeCompare(b.name);
    });

  const getIcon = (kind: string) => {
    if (kind === "pdf") return FileText;
    if (kind === "docx") return FileSpreadsheet;
    if (kind === "pptx") return Presentation;
    return File;
  };

  const formatDate = (date: string) =>
    new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Documents</h1>
          <p className="text-sm text-slate-500 mt-1">AI-generated PDFs, Word docs, and presentations from Zilo Chat</p>
          {documents.length > 0 && (
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              {counts.pdf > 0 && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-50 text-red-600 text-xs font-medium">{counts.pdf} PDF</span>}
              {counts.docx > 0 && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 text-xs font-medium">{counts.docx} Word</span>}
              {counts.pptx > 0 && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-orange-50 text-orange-600 text-xs font-medium">{counts.pptx} PPT</span>}
            </div>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search documents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/50"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as Category)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/20"
          >
            <option value="all">All Types</option>
            <option value="pdf">PDF</option>
            <option value="docx">Word</option>
            <option value="pptx">PowerPoint</option>
          </select>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/20"
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="az">A → Z</option>
          </select>
          <button onClick={fetchDocuments} disabled={loading} className="p-2 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50" title="Refresh">
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="w-12 h-12 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500">No documents found</p>
          <p className="text-sm text-slate-400 mt-1">Generate documents in Zilo Chat to see them here</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map((doc) => {
            const Icon = getIcon(doc.asset_kind);
            const kindColors: Record<string, string> = {
              pdf: "bg-red-50 text-red-600",
              docx: "bg-blue-50 text-blue-600",
              pptx: "bg-orange-50 text-orange-600",
            };
            return (
              <div
                key={doc.id}
                className="flex items-center gap-4 p-4 bg-white border border-slate-200 rounded-lg hover:border-brand/30 transition-colors"
              >
                <div className={cn("p-2 rounded-lg", kindColors[doc.asset_kind] ?? "bg-slate-100 text-slate-600")}>
                  <Icon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-slate-900 truncate">{doc.name}</h3>
                    {doc.source === "clone" && (
                      <span className="shrink-0 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-600 text-[10px] font-medium">
                        <Copy className="w-2.5 h-2.5" /> Clone
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    <span className="capitalize">{doc.format_label || doc.asset_kind.toUpperCase()}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {formatDate(doc.created_at)}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {doc.conversation_id && (
                    <Link
                      href={`/dashboard/assistant?conversation_id=${doc.conversation_id}`}
                      className="p-2 text-slate-500 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors"
                      title="Open in Zilo Chat"
                    >
                      <MessageSquare className="w-4 h-4" />
                    </Link>
                  )}
                  <button onClick={() => setPreview(doc)} className="p-2 text-slate-500 hover:text-brand hover:bg-brand/5 rounded-lg transition-colors" title="Preview">
                    <Eye className="w-4 h-4" />
                  </button>
                  <button onClick={() => setCloning(doc)} className="p-2 text-slate-500 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-colors" title="Clone">
                    <Copy className="w-4 h-4" />
                  </button>
                  <button onClick={() => void handleDownload(doc.file_url, doc.name)} className="p-2 text-slate-500 hover:text-brand hover:bg-brand/5 rounded-lg transition-colors" title="Download">
                    <Download className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => void handleDelete(doc.id)}
                    disabled={deleting === doc.id}
                    className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                    title="Delete"
                  >
                    {deleting === doc.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {preview && <PreviewModal doc={preview} onClose={() => setPreview(null)} />}
      {cloning && (
        <CloneModal
          doc={cloning}
          onClose={() => setCloning(null)}
          onCloned={(d) => setDocuments((prev) => [d, ...prev])}
        />
      )}
    </div>
  );
}
