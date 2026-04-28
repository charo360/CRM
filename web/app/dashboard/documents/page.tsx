"use client";

import { useEffect, useState } from "react";
import {
  FileText, Download, Trash2, Loader2, Calendar,
  Filter, File, FileSpreadsheet, Presentation,
  Search, RefreshCw, Eye, X,
} from "lucide-react";
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
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors shrink-0 ml-3"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-hidden">
          <iframe
            src={viewerUrl}
            className="w-full h-full border-0"
            title={doc.name}
            sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
          />
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
  const [deleting, setDeleting] = useState<string | null>(null);
  const [preview, setPreview] = useState<Document | null>(null);

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

  useEffect(() => {
    fetchDocuments();
  }, []);

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
    try {
      await downloadAsset(url, name);
    } catch {
      toast.error("Download failed");
    }
  };

  const DOC_KINDS = ["pdf", "docx", "pptx"];

  const filtered = documents.filter((d) => {
    const isDocument = DOC_KINDS.includes(d.asset_kind);
    const matchesCategory = category === "all" || d.asset_kind === category;
    const matchesSearch = search === "" || d.name.toLowerCase().includes(search.toLowerCase());
    return isDocument && matchesCategory && matchesSearch;
  });

  const getIcon = (kind: string) => {
    if (kind === "pdf") return FileText;
    if (kind === "docx") return FileSpreadsheet;
    if (kind === "pptx") return Presentation;
    return File;
  };

  const formatDate = (date: string) => {
    return new Date(date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-900">Documents</h1>
        <p className="text-sm text-slate-500 mt-1">AI-generated PDFs, Word docs, and presentations from Zilo Chat</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 mb-6">
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
            className="px-4 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/50"
          >
            <option value="all">All Types</option>
            <option value="pdf">PDF</option>
            <option value="docx">Word</option>
            <option value="pptx">PowerPoint</option>
          </select>
          <button
            onClick={fetchDocuments}
            disabled={loading}
            className="p-2 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
          </button>
        </div>
      </div>

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
            return (
              <div
                key={doc.id}
                className="flex items-center gap-4 p-4 bg-white border border-slate-200 rounded-lg hover:border-brand/30 transition-colors"
              >
                <div className="p-2 bg-slate-100 rounded-lg">
                  <Icon className="w-5 h-5 text-slate-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-slate-900 truncate">{doc.name}</h3>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    <span className="capitalize">{doc.format_label}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {formatDate(doc.created_at)}
                    </span>
                    {doc.source_tool && (
                      <>
                        <span>•</span>
                        <span className="text-slate-400">{doc.source_tool}</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPreview(doc)}
                    className="p-2 text-slate-500 hover:text-brand hover:bg-brand/5 rounded-lg transition-colors"
                    title="Preview"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => void handleDownload(doc.file_url, doc.name)}
                    className="p-2 text-slate-500 hover:text-brand hover:bg-brand/5 rounded-lg transition-colors"
                    title="Download"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => void handleDelete(doc.id)}
                    disabled={deleting === doc.id}
                    className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                    title="Delete"
                  >
                    {deleting === doc.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Trash2 className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {preview && <PreviewModal doc={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
