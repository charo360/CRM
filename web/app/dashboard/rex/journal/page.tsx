"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  BookOpen,
  Loader2,
  Star,
  Sunrise,
  Moon,
} from "lucide-react";

type JournalEntry = {
  id: string;
  kind: string;
  kind_label: string;
  body: string;
  actor_name: string;
  category: string;
  phase: string;
  word_count: number;
  source_event_ids: string[];
  created_at: string;
  relationship_day: number;
  is_synthetic?: boolean;
  action_id?: string | null;
  details?: string[];
};

type JournalPayload = {
  relationship_day: number;
  entries: JournalEntry[];
};

const KIND_ICON: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  milestone: Star,
  daily_anchor: Moon,
  returned: Sunrise,
};

const KIND_TONE: Record<string, string> = {
  milestone: "bg-gradient-to-br from-amber-50 to-amber-100 text-amber-800 border-amber-300",
  daily_anchor: "bg-slate-50 text-slate-500 border-slate-200",
  returned: "bg-sky-50 text-sky-700 border-sky-200",
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

  const normalizedEntries = useMemo<JournalEntry[]>(() => {
    if (!data?.entries) return [];
    const fallbackDay = data.relationship_day ?? 1;
    return data.entries.map((e) => ({
      ...e,
      kind_label: e.kind_label ?? e.kind ?? "Entry",
      relationship_day: e.relationship_day ?? fallbackDay,
      created_at: e.created_at ?? new Date().toISOString(),
      word_count: e.word_count ?? 0,
      source_event_ids: e.source_event_ids ?? [],
    }));
  }, [data]);

  const entriesByDay = useMemo(() => {
    const groups = new Map<number, JournalEntry[]>();
    for (const e of normalizedEntries) {
      const arr = groups.get(e.relationship_day) ?? [];
      arr.push(e);
      groups.set(e.relationship_day, arr);
    }
    return [...groups.entries()].sort((a, b) => b[0] - a[0]);
  }, [normalizedEntries]);

  const dayCount = data?.relationship_day ?? 0;

  return (
    <div className="mx-auto max-w-3xl px-6 py-8 animate-fadeIn">
      <div>
        <h1 className="text-3xl font-semibold text-slate-900">Zilo&apos;s Journal</h1>
        <p className="mt-2 text-sm text-slate-600">
          Zilo&apos;s story of working with your business — from Day 1.
        </p>
      </div>

      {loading && (
        <div className="mt-12 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-brand" />
        </div>
      )}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && data && (
        <>
          <div className="mt-8 text-center">
            <p className="text-sm font-semibold text-slate-700">Day {dayCount}</p>
          </div>

          {(data.entries?.length ?? 0) === 0 ? (
            <EmptyState day={dayCount} />
          ) : (
            <div className="mt-8 space-y-6">
              {entriesByDay.map(([day, entries]) => (
                <DaySection key={day} day={day} entries={entries} />
              ))}
            </div>
          )}

          <div className="mt-12 border-t border-slate-200 pt-6">
            <p className="text-xs text-slate-500 leading-relaxed">
              Zilo started working with you {dayCount} day{dayCount === 1 ? "" : "s"} ago.
              Every entry is written by Zilo — not generated from a template.
              This is its actual record.
            </p>
            <button
              type="button"
              onClick={() => window.print()}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
            >
              Export journal
            </button>
          </div>
        </>
      )}

      <Link
        href="/dashboard"
        className="mt-10 inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-light transition"
      >
        Back to Briefing
      </Link>
    </div>
  );
}

function DaySection({ day, entries }: { day: number; entries: JournalEntry[] }) {
  return (
    <section>
      <div className="sticky top-0 z-[1] -mx-6 mb-3 bg-gradient-to-b from-white via-white to-white/0 px-6 py-2">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Day {day}
        </p>
      </div>
      <ul className="space-y-3">
        {entries.map((e) => (
          <EntryCard key={e.id} entry={e} />
        ))}
      </ul>
    </section>
  );
}

function EntryCard({ entry }: { entry: JournalEntry }) {
  const Icon = KIND_ICON[entry.kind] ?? BookOpen;
  const tone = KIND_TONE[entry.kind] ?? "bg-slate-50 text-slate-700 border-slate-200";

  const cleanBody = entry.body.replace(/^Day \d+\.\s*\n?/, "").trim();

  const isMilestone = entry.kind === "milestone";
  const isAnchor = entry.kind === "daily_anchor";
  const isReturned = entry.kind === "returned";

  const cardClass = isMilestone
    ? "rounded-xl border-2 border-amber-300 bg-gradient-to-br from-amber-50 via-white to-white p-5 shadow-md ring-1 ring-amber-200/50 transition hover:shadow-lg animate-fadeIn"
    : isAnchor
    ? "rounded-xl border border-slate-200 bg-slate-50/60 p-4 shadow-sm transition hover:bg-slate-50"
    : isReturned
    ? "rounded-xl border border-sky-200 bg-sky-50/60 p-4 shadow-sm transition hover:shadow-md"
    : "rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md";

  const bodyClass = isMilestone
    ? "whitespace-pre-wrap text-[16px] font-medium leading-relaxed text-slate-900"
    : isAnchor
    ? "whitespace-pre-wrap text-[14px] italic leading-relaxed text-slate-500"
    : "whitespace-pre-wrap text-[14px] leading-relaxed text-slate-850";

  return (
    <li className={cardClass}>
      <div className="flex items-start gap-3">
        <div className={`shrink-0 rounded-lg border p-2 ${tone}`}>
          <Icon size={isMilestone ? 16 : 14} />
        </div>
        <div className="flex-1 min-w-0">
          <p className={bodyClass}>{cleanBody}</p>
        </div>
      </div>
    </li>
  );
}

function EmptyState({ day }: { day: number }) {
  const body = day <= 1
    ? "First day. A lot to learn.\nObserving."
    : `Day ${day}. Quiet. Watching.`;
  return (
    <div className="mt-8 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="shrink-0 rounded-lg border bg-slate-50 text-slate-500 border-slate-200 p-2">
          <BookOpen size={14} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-slate-850">
            {body}
          </p>
        </div>
      </div>
    </div>
  );
}
