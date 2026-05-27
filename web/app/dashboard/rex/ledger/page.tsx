"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2 } from "lucide-react";

type LedgerPayload = {
  story: string;
  inspect: {
    action_id: string;
    at: string;
    summary: string;
    state: string;
    category: string;
    kind: string;
    actor: string;
    confidence_pct: number;
  }[];
  total_actions: number;
};

export default function ZiloLedgerPage() {
  const [data, setData] = useState<LedgerPayload | null>(null);
  const [tab, setTab] = useState<"story" | "inspect">("story");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<LedgerPayload>("/rex/ledger");
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load ledger");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-dark/60">Zilo</p>
      <h1 className="mt-1 text-2xl font-semibold text-slate-900">Action Log</h1>
      <p className="mt-1 text-sm text-slate-600">
        Persisted in Mongo — every approve, dismiss, and CRM sync is recorded here.
      </p>

      <div className="mt-6 flex gap-2">
        <button
          type="button"
          onClick={() => setTab("story")}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
            tab === "story" ? "bg-brand text-brand-ink" : "bg-slate-100 text-slate-700"
          }`}
        >
          Story
        </button>
        <button
          type="button"
          onClick={() => setTab("inspect")}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
            tab === "inspect" ? "bg-brand text-brand-ink" : "bg-slate-100 text-slate-700"
          }`}
        >
          Inspect
        </button>
        <button
          type="button"
          onClick={() => load()}
          className="ml-auto text-sm text-brand-dark hover:underline"
        >
          Refresh
        </button>
      </div>

      {loading && (
        <div className="mt-12 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-brand" />
        </div>
      )}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && data && tab === "story" && (
        <pre className="mt-6 whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs leading-relaxed text-slate-800">
          {data.story}
        </pre>
      )}

      {!loading && data && tab === "inspect" && (
        <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-100 text-slate-600">
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">State</th>
                <th className="px-3 py-2">Summary</th>
                <th className="px-3 py-2">Category</th>
              </tr>
            </thead>
            <tbody>
              {data.inspect.map((row) => (
                <tr key={row.action_id} className="border-t border-slate-100">
                  <td className="px-3 py-2 whitespace-nowrap text-slate-500">
                    {new Date(row.at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">{row.state}</td>
                  <td className="px-3 py-2">{row.summary}</td>
                  <td className="px-3 py-2 text-slate-500">{row.category}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.inspect.length === 0 && (
            <p className="p-4 text-sm text-slate-500">No actions yet. Open Zilo Briefing and use Sync CRM.</p>
          )}
        </div>
      )}

      <Link
        href="/dashboard"
        className="mt-8 inline-block rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-light"
      >
        Back to Zilo Briefing
      </Link>
    </div>
  );
}
