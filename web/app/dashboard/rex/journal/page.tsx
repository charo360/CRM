"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type JournalEntry = {
  id: string;
  kind: string;
  body: string;
  relationship_day: number;
  created_at: string;
};

type JournalPayload = {
  relationship_day: number;
  entries: JournalEntry[];
};

const DAY_1_FALLBACK: JournalEntry = {
  id: "fallback-day-1",
  kind: "daily_anchor",
  body: "Day 1.\nFirst day. Just getting started.\nA lot to learn.\nObserving.",
  relationship_day: 1,
  created_at: new Date().toISOString(),
};

function stripDayPrefix(body: string): string {
  return body.replace(/^Day \d+\.\s*\n?/, "").trim();
}

function splitVerdict(body: string): { observation: string; verdict: string } {
  const trimmed = stripDayPrefix(body);
  if (!trimmed) return { observation: "", verdict: "" };

  const lines = trimmed.split(/\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length >= 2) {
    return {
      observation: lines.slice(0, -1).join("\n"),
      verdict: lines[lines.length - 1],
    };
  }

  const sentences = trimmed.match(/[^.!?]+[.!?]+/g);
  if (sentences && sentences.length >= 2) {
    return {
      observation: sentences.slice(0, -1).join(" ").trim(),
      verdict: sentences[sentences.length - 1].trim(),
    };
  }

  return { observation: "", verdict: trimmed };
}

export default function ZiloJournalPage() {
  const [data, setData] = useState<JournalPayload | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<JournalPayload>("/rex/journal");
      setData(res);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const entries = useMemo<JournalEntry[]>(() => {
    if (!data?.entries || data.entries.length === 0) {
      return [DAY_1_FALLBACK];
    }
    return [...data.entries].sort(
      (a, b) => (b.relationship_day ?? 0) - (a.relationship_day ?? 0),
    );
  }, [data]);

  const dayCount = data?.relationship_day ?? 1;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      {/* Page header — spec copy */}
      <div>
        <h1 className="text-3xl font-semibold text-slate-900">
          Zilo&apos;s Journal
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Zilo&apos;s story of working with your business — from Day 1.
        </p>
      </div>

      {/* The counter — spec format */}
      <div className="mt-10 border-b border-slate-200 pb-6 flex items-center justify-between">
        <p className="font-mono text-sm text-slate-600">
          <span className="text-amber-600 font-semibold">Day {dayCount}</span>
          {loading ? null : (
            <span className="text-slate-400">
              {"  ·  "}Zilo&apos;s record from Day 1 to today
            </span>
          )}
        </p>
      </div>

      {/* The feed */}
      <ul className="mt-2">
        {entries.map((e) => (
          <EntryRow key={e.id} entry={e} />
        ))}
      </ul>

      {/* The bottom of the journal — spec copy */}
      <div className="mt-12 pt-6 border-t border-slate-200">
        <p className="font-mono text-xs text-slate-500 leading-relaxed">
          Zilo started working with you {dayCount} day
          {dayCount === 1 ? "" : "s"} ago.
          <br />
          Every entry is written by Zilo — not generated from a template. This
          is its actual record.
        </p>
        <button
          type="button"
          onClick={() => window.print()}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
        >
          Export journal
        </button>
      </div>

      <Link
        href="/dashboard"
        className="mt-10 inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-light transition"
      >
        Back to Briefing
      </Link>
    </div>
  );
}

function EntryRow({ entry }: { entry: JournalEntry }) {
  const { observation, verdict } = splitVerdict(entry.body);
  const isMistake =
    entry.kind === "operational_setback" ||
    /flagged|mistake|wrong|undone/i.test(entry.body);
  const isPromotion = entry.kind === "promotion";

  return (
    <li className="flex gap-6 border-b border-slate-100 py-6">
      {/* Left: day number, amber mono */}
      <div className="w-20 shrink-0">
        <p className="font-mono text-base font-semibold text-amber-600">
          Day {entry.relationship_day}
        </p>
      </div>

      {/* Right: observation + verdict */}
      <div className="flex-1 min-w-0">
        {observation && (
          <p className="font-mono text-[14px] leading-relaxed text-slate-500 whitespace-pre-wrap">
            {observation}
          </p>
        )}
        {verdict && (
          <p
            className={`font-mono text-[14px] leading-relaxed text-slate-900 font-medium whitespace-pre-wrap ${
              observation ? "mt-2" : ""
            }`}
          >
            {verdict}
          </p>
        )}

        {/* Spec-defined small links on mistake / promotion entries */}
        {isMistake && (
          <button
            type="button"
            className="mt-3 font-mono text-[11px] text-slate-400 hover:text-slate-600 underline-offset-4 hover:underline transition"
          >
            What changed after this
          </button>
        )}
        {isPromotion && (
          <button
            type="button"
            className="mt-3 font-mono text-[11px] text-slate-400 hover:text-slate-600 underline-offset-4 hover:underline transition"
          >
            See the full promotion moment
          </button>
        )}
      </div>
    </li>
  );
}
