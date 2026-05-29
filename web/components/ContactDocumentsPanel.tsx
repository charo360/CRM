"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { cn, formatDateSafe, resolveMediaUrl, downloadAsset } from "@/lib/utils";
import { FileText, Upload, Loader2, Trash2, Download, ExternalLink } from "lucide-react";

export type DocTypeOption = { value: string; label: string };

export interface ContactDocument {
  id: string;
  title: string;
  doc_type: string;
  filename: string;
  file_url: string;
  mime_type?: string;
  size?: number;
  uploaded_at?: string;
}

interface ContactDocumentsPanelProps {
  apiPrefix: string;
  customerId: string;
  documentTypes: DocTypeOption[];
  label?: string;
}

function formatFileSize(bytes?: number) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function docTypeLabel(types: DocTypeOption[], value: string) {
  return types.find((t) => t.value === value)?.label || value.replace(/_/g, " ");
}

export default function ContactDocumentsPanel({
  apiPrefix,
  customerId,
  documentTypes,
  label = "Contracts & documents",
}: ContactDocumentsPanelProps) {
  const [docs, setDocs] = useState<ContactDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState(documentTypes[0]?.value || "other");
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const list = await api.get<ContactDocument[]>(`${apiPrefix}/${customerId}/documents`);
      setDocs(list || []);
    } catch {
      setDocs([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [apiPrefix, customerId]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      alert("Choose a file to upload.");
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", title.trim());
      form.append("doc_type", docType);
      const created = await api.postForm<ContactDocument>(`${apiPrefix}/${customerId}/documents`, form);
      setDocs((prev) => [created, ...prev]);
      setTitle("");
      setDocType(documentTypes[0]?.value || "other");
      if (fileRef.current) fileRef.current.value = "";
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(doc: ContactDocument) {
    if (!confirm(`Delete "${doc.title}"?`)) return;
    setDeletingId(doc.id);
    try {
      await api.delete(`${apiPrefix}/${customerId}/documents/${doc.id}`);
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Could not delete document");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleDownload(doc: ContactDocument) {
    const url = resolveMediaUrl(doc.file_url);
    if (!url) return;
    try {
      await downloadAsset(url, doc.filename || doc.title);
    } catch {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
      <div className="flex items-center gap-2">
        <FileText size={16} className="text-brand-dark" />
        <h4 className="text-sm font-semibold text-slate-900">{label}</h4>
        <span className="text-xs text-slate-400">({docs.length})</span>
      </div>

      {loading ? (
        <div className="flex justify-center py-4">
          <Loader2 className="animate-spin text-brand" size={20} />
        </div>
      ) : docs.length === 0 ? (
        <p className="text-xs text-slate-500">No documents yet — upload term sheets, NDAs, or contracts below.</p>
      ) : (
        <div className="space-y-2">
          {docs.map((doc) => {
            const url = resolveMediaUrl(doc.file_url);
            return (
              <div key={doc.id} className="flex items-start gap-2 p-2.5 rounded-lg border border-slate-100 bg-slate-50/80">
                <FileText size={16} className="text-slate-400 shrink-0 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900 truncate">{doc.title}</p>
                  <div className="flex flex-wrap items-center gap-2 mt-0.5">
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand/10 text-brand-dark font-medium capitalize">
                      {docTypeLabel(documentTypes, doc.doc_type)}
                    </span>
                    {doc.uploaded_at && (
                      <span className="text-[10px] text-slate-400">{formatDateSafe(doc.uploaded_at)}</span>
                    )}
                    {doc.size ? (
                      <span className="text-[10px] text-slate-400">{formatFileSize(doc.size)}</span>
                    ) : null}
                  </div>
                  <p className="text-[10px] text-slate-400 truncate mt-0.5">{doc.filename}</p>
                </div>
                <div className="flex items-center gap-0.5 shrink-0">
                  {url && (
                    <>
                      <button
                        type="button"
                        onClick={() => void handleDownload(doc)}
                        className="p-1.5 rounded-md text-slate-500 hover:bg-white hover:text-brand-dark"
                        title="Download"
                      >
                        <Download size={14} />
                      </button>
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-1.5 rounded-md text-slate-500 hover:bg-white hover:text-brand-dark"
                        title="Open"
                      >
                        <ExternalLink size={14} />
                      </a>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleDelete(doc)}
                    disabled={deletingId === doc.id}
                    className="p-1.5 rounded-md text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                    title="Delete"
                  >
                    {deletingId === doc.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <form onSubmit={handleUpload} className="pt-2 border-t border-slate-100 space-y-2">
        <p className="text-xs font-semibold text-slate-500 uppercase">Upload</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <input
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm sm:col-span-2"
            placeholder="Document title (optional)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
          >
            {documentTypes.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.doc,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.gif"
            className="text-sm file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-100 file:text-slate-700"
          />
        </div>
        <button
          type="submit"
          disabled={uploading}
          className={cn(
            "inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold",
            "bg-brand-dark text-white hover:bg-brand disabled:opacity-50"
          )}
        >
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          Upload document
        </button>
      </form>
    </div>
  );
}
