"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { assistantApi, type AssistantAuditEntry } from "@/lib/api";
import { ArrowLeft, Loader2, ShieldCheck, Wrench, AlertCircle } from "lucide-react";

function formatWhen(iso: string): string {
  try {
    const d = new Date(iso);
    const diffMs = Date.now() - d.getTime();
    const diffMin = Math.round(diffMs / 60_000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.round(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function shortArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return "";
  const entries = Object.entries(args);
  if (!entries.length) return "—";
  return entries
    .map(([k, v]) => {
      let s = typeof v === "string" ? v : JSON.stringify(v);
      if (s.length > 60) s = s.slice(0, 60) + "…";
      return `${k}: ${s}`;
    })
    .join(", ");
}

export default function AssistantAuditPage() {
  const [rows, setRows] = useState<AssistantAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await assistantApi.audit(100);
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="min-h-full bg-slate-50 p-6">
      <div className="mx-auto w-full max-w-4xl">
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard/assistant"
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
            >
              <ArrowLeft size={12} /> Back to chat
            </Link>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900">
              <ShieldCheck size={18} className="text-indigo-600" /> Zilo audit log
            </h1>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
          >
            Refresh
          </button>
        </div>

        <p className="mb-4 text-sm text-slate-500">
          A record of every destructive action Zilo Chat has taken on your behalf — creating customers,
          sending messages, broadcasts, disconnecting channels, etc.
        </p>

        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {loading ? (
            <div className="flex items-center justify-center p-10 text-slate-400">
              <Loader2 className="animate-spin" size={18} />
            </div>
          ) : error ? (
            <div className="flex items-center gap-2 p-6 text-sm text-red-600">
              <AlertCircle size={14} /> {error}
            </div>
          ) : rows.length === 0 ? (
            <div className="p-10 text-center text-sm text-slate-400">
              No audited actions yet. Once Zilo sends a WhatsApp, creates a broadcast, or edits a record,
              it will appear here.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">When</th>
                  <th className="px-3 py-2 text-left font-semibold">Tool</th>
                  <th className="px-3 py-2 text-left font-semibold">Arguments</th>
                  <th className="px-3 py-2 text-left font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.id} className="align-top hover:bg-slate-50/50">
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-500">
                      {formatWhen(r.created_at)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
                        <Wrench size={10} />
                        {r.tool}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-600">
                      {shortArgs(r.arguments)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[10.5px] font-medium ${
                          r.status === "ok" || r.status === "success"
                            ? "bg-green-50 text-green-700"
                            : r.status === "pending"
                            ? "bg-amber-50 text-amber-700"
                            : "bg-red-50 text-red-700"
                        }`}
                      >
                        {r.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
