"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2 } from "lucide-react";

type JournalEntry = {
  id: string;
  kind: string;
  body: string;
  actor_name: string;
  category: string;
  phase: string;
};

type JournalPayload = {
  relationship_day: number;
  entries: JournalEntry[];
};

export default function ZiloJournalPage() {
  const [data, setData] = useState<JournalPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<JournalPayload>("/rex/journal");
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load journal");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-dark/60">Zilo</p>
      <h1 className="mt-1 text-2xl font-semibold text-slate-900">Journal</h1>
      <p className="mt-1 text-sm text-slate-600">
        Trust events replayed into Zilo&apos;s voice — promotions, approvals, setbacks.
      </p>

      {loading && (
        <div className="mt-12 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-brand" />
        </div>
      )}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && data && (
        <p className="mt-4 text-xs text-slate-500">Relationship day {data.relationship_day}</p>
      )}

      {!loading && data && data.entries.length === 0 && (
        <p className="mt-8 text-sm text-slate-600">
          No journal entries yet. Approve or reject staged actions to emit trust events Zilo will narrate here.
        </p>
      )}

      {!loading && data && (
        <ul className="mt-6 space-y-4">
          {data.entries.map((e) => (
            <li key={e.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-[10px] font-semibold uppercase text-brand-dark/70">
                {e.kind} · {e.category}
              </p>
              <p className="mt-2 whitespace-pre-wrap text-sm text-slate-800">{e.body}</p>
            </li>
          ))}
        </ul>
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
