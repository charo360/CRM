"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2 } from "lucide-react";

type Entry = {
  id: string;
  subject: string | null;
  text: string;
  created_at: string;
  tags: string[];
};

type NotebookPayload = {
  buckets: { people: Entry[]; patterns: Entry[]; lanes: Entry[] };
  total: number;
};

function BucketSection({ title, items }: { title: string; items: Entry[] }) {
  if (!items.length) return null;
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      <ul className="mt-3 space-y-3">
        {items.map((e) => (
          <li key={e.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            {e.subject && <p className="text-sm font-semibold text-slate-900">{e.subject}</p>}
            <p className="mt-1 text-sm text-slate-700">{e.text}</p>
            <p className="mt-2 text-[10px] text-slate-400">
              {new Date(e.created_at).toLocaleString()}
              {e.tags.length ? ` · ${e.tags.join(", ")}` : ""}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ZiloNotebookPage() {
  const [data, setData] = useState<NotebookPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<NotebookPayload>("/rex/notebook");
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load notebook");
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
      <h1 className="mt-1 text-2xl font-semibold text-slate-900">Notebook</h1>
      <p className="mt-1 text-sm text-slate-600">
        People, patterns, and lanes — saved with your Zilo session in Mongo.
      </p>

      {loading && (
        <div className="mt-12 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-brand" />
        </div>
      )}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && data && data.total === 0 && (
        <p className="mt-8 text-sm text-slate-600">
          Empty notebook. CRM sync adds people notes for overdue invoices; approve actions to grow memory.
        </p>
      )}

      {!loading && data && (
        <>
          <BucketSection title="People" items={data.buckets.people} />
          <BucketSection title="Patterns" items={data.buckets.patterns} />
          <BucketSection title="Lanes" items={data.buckets.lanes} />
        </>
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
