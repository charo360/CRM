"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  Loader2,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Users,
  Sparkles,
  Info,
  Flame,
  Star,
  Sunrise,
  Moon,
  Activity,
  Undo2,
  ChevronDown,
  ChevronUp,
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

type Engagement = {
  streak_days: number;
  gap_days: number;
  milestones_unlocked: string[];
  next_milestone_phase: string | null;
  next_milestone_in_days: number | null;
};

type PhaseInfo = {
  phase: string;
  day_range_lo: number;
  day_range_hi: number | null;
  directive: string;
  example: string;
  word_ceiling: number;
  progress_pct: number;
  next_phase: string | null;
  next_phase_in_days: number | null;
  tease?: string;
};

type Summary = {
  total: number;
  by_kind: { kind: string; label: string; count: number }[];
  by_category: { category: string; count: number }[];
};

type OvernightEphemeraTask = {
  id: string;
  category: string;
  summary: string;
  kind: string;
  timestamp: string;
  status: string;
  action_id?: string;
  details?: string[];
};

type AutopilotProgress = {
  category: string;
  current_rank: string;
  target_rank: string;
  progress_pct: number;
  tasks_completed: number;
  tasks_required: number;
  text: string;
};

type ActiveLearning = {
  id: string;
  category: string;
  observation: string;
  lesson: string;
  impact: string;
  timestamp: string;
  source: string;
  status: string;
  applied_to?: string;
};

type JournalPayload = {
  relationship_day: number;
  phase?: PhaseInfo;
  summary?: Summary;
  engagement?: Engagement;
  entries: JournalEntry[];
  ambient_thought?: string;
  overnight_ephemera?: OvernightEphemeraTask[];
  autopilot_progress?: AutopilotProgress;
  active_learnings?: ActiveLearning[];
};

const PHASE_LABEL: Record<string, string> = {
  observing: "Observing",
  shifting: "Shifting",
  blended: "Blended",
  earned: "Earned",
  perspective: "Perspective",
};

const PHASE_HINT: Record<string, string> = {
  observing: "Day 1–14. Facts only. No verdicts yet.",
  shifting: "Day 15–30. Patterns start appearing. Closes with “Noted.”",
  blended: "Day 31–60. Fact → human detail → short verdict.",
  earned: "Day 61–90. Pattern recognition, earned confidence.",
  perspective: "Day 91+. Looks backward when it matters.",
};

const KIND_ICON: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  promotion: TrendingUp,
  demotion: TrendingDown,
  recommendation: ArrowUpRight,
  recommendation_resolved: CheckCircle2,
  operational_win: Sparkles,
  operational_setback: TrendingDown,
  milestone: Star,
  daily_anchor: Moon,
  returned: Sunrise,
  probation: ShieldCheck,
  team: Users,
  background_action: Activity,
};

const KIND_TONE: Record<string, string> = {
  promotion: "bg-emerald-50 text-emerald-700 border-emerald-200",
  demotion: "bg-amber-50 text-amber-700 border-amber-200",
  recommendation: "bg-blue-50 text-blue-700 border-blue-200",
  recommendation_resolved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  operational_win: "bg-emerald-50 text-emerald-700 border-emerald-200",
  operational_setback: "bg-rose-50 text-rose-700 border-rose-200",
  probation: "bg-slate-100 text-slate-700 border-slate-200",
  team: "bg-violet-50 text-violet-700 border-violet-200",
  milestone: "bg-gradient-to-br from-amber-50 to-amber-100 text-amber-800 border-amber-300",
  daily_anchor: "bg-slate-50 text-slate-500 border-slate-200",
  returned: "bg-sky-50 text-sky-700 border-sky-200",
  background_action: "bg-slate-50 text-slate-700 border-slate-200",
};

function formatCategory(cat: string): string {
  return cat.replace(/_/g, " ");
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = now - then;
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return new Date(iso).toLocaleDateString();
}

export default function ZiloJournalPage() {
  const [data, setData] = useState<JournalPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<string | null>(null);
  const [showExplainer, setShowExplainer] = useState(false);
  const [undoneActions, setUndoneActions] = useState<Set<string>>(new Set());
  const [undoing, setUndoing] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

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

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const handleUndo = useCallback(async (actionId: string) => {
    setUndoing(actionId);
    setToast(null);
    try {
      await api.post(`/rex/actions/${actionId}/undo`, {});
      setUndoneActions((prev) => {
        const next = new Set(prev);
        next.add(actionId);
        return next;
      });
      setToast({ message: "Action successfully undone.", type: "success" });
    } catch (e) {
      setToast({
        message: e instanceof Error ? e.message : "Failed to undo action.",
        type: "error",
      });
    } finally {
      setUndoing(null);
    }
  }, []);

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

  const filteredEntries = useMemo(() => {
    if (!kindFilter) return normalizedEntries;
    return normalizedEntries.filter((e) => e.kind === kindFilter);
  }, [normalizedEntries, kindFilter]);

  const entriesByDay = useMemo(() => {
    const groups = new Map<number, JournalEntry[]>();
    for (const e of filteredEntries) {
      const arr = groups.get(e.relationship_day) ?? [];
      arr.push(e);
      groups.set(e.relationship_day, arr);
    }
    return [...groups.entries()].sort((a, b) => b[0] - a[0]);
  }, [filteredEntries]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-dark/60">Zilo</p>
          <h1 className="mt-1 text-3xl font-semibold text-slate-900">Journal</h1>
          <p className="mt-2 max-w-xl text-sm text-slate-600">
            Zilo&apos;s diary of his own growth — written in his voice, evolving as the
            relationship deepens. Not a log of what you did. A log of what he became.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowExplainer((v) => !v)}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          <Info size={13} />
          How this works
        </button>
      </div>

      {showExplainer && (
        <div className="mt-4 rounded-xl border border-brand/30 bg-brand/5 p-5 text-sm text-slate-700">
          <p className="font-semibold text-brand-dark">What you&apos;re reading</p>
          <ul className="mt-2 space-y-1.5 list-disc list-inside text-slate-600">
            <li>Every <strong>trust event</strong> (promotion, approval, mistake, clean send) becomes one short entry.</li>
            <li>The <strong>voice changes over time</strong> — terse and observational early, more confident later.</li>
            <li>Entries are <strong>auto-generated</strong> from real events. Nothing is invented.</li>
            <li>Only <strong>you</strong> see this — it&apos;s founder-only by default.</li>
          </ul>
        </div>
      )}

      {loading && (
        <div className="mt-12 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-brand" />
        </div>
      )}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && data && (
        <>
          {data.phase && (
            <PhaseBanner
              phase={data.phase}
              day={data.relationship_day}
              engagement={data.engagement}
              autopilotProgress={data.autopilot_progress}
            />
          )}

          {data.ambient_thought && (
            <div className="mt-6 rounded-xl border border-[#0d2818]/15 bg-gradient-to-r from-[#eefaf2] to-white p-5 shadow-sm">
              <p className="text-[10px] font-bold uppercase tracking-wider text-[#0d2818]/70">Zilo&apos;s Daily Ambient Thought</p>
              <blockquote className="mt-2 text-base italic font-serif leading-relaxed text-slate-800 border-l-2 border-[#0d2818] pl-3">
                &ldquo;{data.ambient_thought}&rdquo;
              </blockquote>
            </div>
          )}




          {data.active_learnings && data.active_learnings.length > 0 && (
            <div className="mt-8">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                </span>
                <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500">Zilo&apos;s Active Learning Loop</h3>
              </div>
              
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                {data.active_learnings.map((learning) => {
                  const isApplied = learning.status === "applied";
                  const isMuted = learning.status === "muted";
                  const statusLabel = isApplied 
                    ? "Applied to Autopilot" 
                    : isMuted 
                    ? "Alert Muted" 
                    : "Observing Style";
                  const statusColor = isApplied
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                    : isMuted
                    ? "bg-amber-50 text-amber-700 border-amber-200"
                    : "bg-blue-50 text-blue-700 border-blue-200";
                  
                  return (
                    <div 
                      key={learning.id} 
                      className="group relative rounded-xl border border-slate-100 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-md hover:border-blue-100/50"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <span className="inline-flex rounded-full bg-slate-50 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-500">
                          {formatCategory(learning.category)}
                        </span>
                        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold ${statusColor}`}>
                          {isApplied && <CheckCircle2 size={10} />}
                          {learning.status === "observing" && <Loader2 size={10} className="animate-spin" />}
                          {statusLabel}
                        </span>
                      </div>
                      
                      <div className="mt-3.5 space-y-2.5">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Interaction</span>
                            <p className="text-xs text-slate-700 font-medium truncate">{learning.observation}</p>
                          </div>
                          <div className="shrink-0 text-right">
                            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Source</span>
                            <p className="text-[10px] font-medium text-slate-500">{learning.source}</p>
                          </div>
                        </div>
                        
                        <div className="border-t border-slate-50 pt-2.5 bg-gradient-to-r from-blue-50/20 to-transparent p-2 rounded-lg border border-blue-500/5">
                          <span className="text-[9px] font-bold uppercase tracking-wider text-blue-600">Lesson Extracted</span>
                          <p className="text-xs font-semibold text-slate-900 leading-normal">{learning.lesson}</p>
                        </div>
                        
                        <div className="rounded-lg bg-slate-50/50 p-2.5 border border-slate-100/50 flex justify-between items-center gap-2">
                          <div className="min-w-0 flex-1">
                            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Autopilot Impact</span>
                            <p className="text-[11px] text-slate-600 font-medium truncate">{learning.impact}</p>
                          </div>
                          {learning.applied_to && (
                            <div className="shrink-0 text-right">
                              <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">System Path</span>
                              <p className="text-[10px] font-bold text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200/50">{learning.applied_to}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {(data.entries?.length ?? 0) === 0 ? (
            <EmptyState />
          ) : (
            <>
              {data.summary && data.summary.by_kind.length > 0 && (
                <FilterChips
                  summary={data.summary}
                  selected={kindFilter}
                  onSelect={setKindFilter}
                />
              )}
              <div className="mt-6 space-y-8">
                {entriesByDay.map(([day, entries]) => (
                  <DaySection
                    key={day}
                    day={day}
                    entries={entries}
                    undoneActions={undoneActions}
                    undoing={undoing}
                    onUndo={handleUndo}
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}

      {toast && (
        <div className={`fixed bottom-5 right-5 z-50 rounded-lg px-4 py-3 text-xs font-semibold shadow-md transition-all border ${
          toast.type === "success" 
            ? "bg-emerald-50 text-emerald-800 border-emerald-200" 
            : "bg-red-50 text-red-800 border-red-200"
        }`}>
          {toast.message}
        </div>
      )}

      <Link
        href="/dashboard"
        className="mt-10 inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-light"
      >
        Back to Briefing
      </Link>
    </div>
  );
}

function PhaseBanner({
  phase,
  day,
  engagement,
  autopilotProgress,
}: {
  phase: PhaseInfo;
  day: number;
  engagement?: Engagement;
  autopilotProgress?: AutopilotProgress;
}) {
  const label = PHASE_LABEL[phase.phase] ?? phase.phase;
  const streak = engagement?.streak_days ?? 0;
  const nextDays = phase.next_phase_in_days;
  const nextLabel = phase.next_phase ? PHASE_LABEL[phase.next_phase] ?? phase.next_phase : null;
  return (
    <div className="mt-6 rounded-2xl border border-slate-200 bg-gradient-to-br from-[#071a10] to-[#0d2818] p-6 text-white shadow-lg">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-light/70">Relationship</p>
          <p className="mt-1 text-3xl font-semibold">Day {day}</p>
          {streak > 0 && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-amber-400/20 px-2.5 py-0.5 text-xs font-semibold text-amber-200">
              <Flame size={12} />
              {streak}-day streak
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-light/70">Voice Phase</p>
          <p className="mt-1 text-xl font-semibold text-brand-light">{label}</p>
          <p className="mt-1 text-[11px] text-slate-300">{PHASE_HINT[phase.phase] ?? ""}</p>
        </div>
      </div>

      <div className="mt-5">
        <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full bg-gradient-to-r from-brand to-amber-300 transition-all"
            style={{ width: `${phase.progress_pct}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] text-slate-300">
          <span>
            Day {phase.day_range_lo}
            {phase.day_range_hi != null ? `–${phase.day_range_hi}` : "+"}
          </span>
          {nextLabel && nextDays != null ? (
            <span>
              <strong className="text-white">{nextLabel}</strong> unlocks in {nextDays} day
              {nextDays === 1 ? "" : "s"}
            </span>
          ) : (
            <span>Final phase</span>
          )}
        </div>
      </div>

      {phase.tease && (
        <p className="mt-4 text-sm italic text-amber-200/90">
          &ldquo;{phase.tease}&rdquo;
        </p>
      )}

      {autopilotProgress && (
        <div className="mt-5 border-t border-white/10 pt-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-light/70">Autopilot Rank Progression</p>
              <p className="mt-1 text-sm font-semibold text-white">
                {autopilotProgress.current_rank} &rarr; <span className="text-brand-light">{autopilotProgress.target_rank}</span> ({formatCategory(autopilotProgress.category)})
              </p>
            </div>
            <div className="text-right">
              <span className="inline-flex items-center gap-1 rounded-full bg-brand/20 px-2 py-0.5 text-[10px] font-bold text-brand-light border border-brand/30">
                <Star size={10} className="animate-pulse text-amber-300" />
                {autopilotProgress.progress_pct}% Earned
              </span>
            </div>
          </div>
          <div className="mt-2.5">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/15">
              <div
                className="h-full bg-gradient-to-r from-brand to-emerald-400 transition-all"
                style={{ width: `${autopilotProgress.progress_pct}%` }}
              />
            </div>
            <p className="mt-1.5 text-[11px] text-slate-300">
              {autopilotProgress.text}
            </p>
          </div>
        </div>
      )}

      <div className="mt-5 rounded-xl border border-white/10 bg-white/5 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-light/60">
          How Zilo writes today
        </p>
        <p className="mt-1 text-sm italic text-slate-200">&ldquo;{phase.example}&rdquo;</p>
      </div>
    </div>
  );
}

function FilterChips({
  summary,
  selected,
  onSelect,
}: {
  summary: Summary;
  selected: string | null;
  onSelect: (kind: string | null) => void;
}) {
  return (
    <div className="mt-6 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
          selected === null
            ? "border-brand bg-brand text-brand-ink"
            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
        }`}
      >
        All ({summary.total})
      </button>
      {summary.by_kind.map((k) => (
        <button
          key={k.kind}
          type="button"
          onClick={() => onSelect(k.kind === selected ? null : k.kind)}
          className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
            selected === k.kind
              ? "border-brand bg-brand text-brand-ink"
              : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          }`}
        >
          {k.label} ({k.count})
        </button>
      ))}
    </div>
  );
}

function DaySection({
  day,
  entries,
  undoneActions,
  undoing,
  onUndo,
}: {
  day: number;
  entries: JournalEntry[];
  undoneActions: Set<string>;
  undoing: string | null;
  onUndo: (actionId: string) => void;
}) {
  return (
    <section>
      <div className="sticky top-0 z-[1] -mx-6 mb-3 bg-gradient-to-b from-white via-white to-white/0 px-6 py-2">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Day {day} <span className="ml-1 text-slate-300">· {formatRelative(entries[0].created_at)}</span>
        </p>
      </div>
      <ul className="space-y-3">
        {entries.map((e) => (
          <EntryCard
            key={e.id}
            entry={e}
            isUndone={e.action_id ? undoneActions.has(e.action_id) : false}
            isUndoing={e.action_id ? undoing === e.action_id : false}
            onUndo={onUndo}
          />
        ))}
      </ul>
    </section>
  );
}

function EntryCard({
  entry,
  isUndone,
  isUndoing,
  onUndo,
}: {
  entry: JournalEntry;
  isUndone: boolean;
  isUndoing: boolean;
  onUndo: (actionId: string) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const Icon = KIND_ICON[entry.kind] ?? BookOpen;
  const tone = KIND_TONE[entry.kind] ?? "bg-slate-50 text-slate-700 border-slate-200";

  // Strip the "Day N." prefix so we don't show it twice — the section header has it.
  const cleanBody = entry.body.replace(/^Day \d+\.\s*\n?/, "").trim();

  const isMilestone = entry.kind === "milestone";
  const isAnchor = entry.kind === "daily_anchor";
  const isReturned = entry.kind === "returned";

  const cardClass = isMilestone
    ? "rounded-xl border-2 border-amber-300 bg-gradient-to-br from-amber-50 via-white to-white p-5 shadow-md ring-1 ring-amber-200/50 transition hover:shadow-lg"
    : isAnchor
    ? "rounded-xl border border-slate-200 bg-slate-50/60 p-4 shadow-sm transition hover:bg-slate-50"
    : isReturned
    ? "rounded-xl border border-sky-200 bg-sky-50/60 p-4 shadow-sm transition hover:shadow-md"
    : `rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md ${isUndone ? "opacity-75" : ""}`;

  const bodyClass = isMilestone
    ? `mt-1.5 whitespace-pre-wrap text-[17px] font-medium leading-relaxed text-slate-900 ${isUndone ? "line-through text-slate-400" : ""}`
    : isAnchor
    ? "mt-1.5 whitespace-pre-wrap text-[14px] italic leading-relaxed text-slate-500"
    : `mt-1.5 whitespace-pre-wrap text-[15px] leading-relaxed text-slate-800 ${isUndone ? "line-through text-slate-400" : ""}`;

  return (
    <li className={cardClass}>
      <div className="flex items-start gap-3">
        <div className={`shrink-0 rounded-lg border p-2 ${tone}`}>
          <Icon size={isMilestone ? 16 : 14} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <span className={isMilestone ? "text-amber-700" : ""}>{entry.kind_label}</span>
            {!entry.is_synthetic && (
              <>
                <span className="text-slate-300">·</span>
                <span className="text-slate-600">{formatCategory(entry.category)}</span>
              </>
            )}
            {entry.actor_name && entry.actor_name !== "Zilo" && (
              <>
                <span className="text-slate-300">·</span>
                <span className="text-slate-600">{entry.actor_name}</span>
              </>
            )}
            {isMilestone && (
              <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-amber-200/60 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                <Star size={10} />
                Phase unlocked
              </span>
            )}
            {isUndone && (
              <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">
                Undone
              </span>
            )}
          </div>
          <p className={bodyClass}>{cleanBody}</p>

          {entry.details && entry.details.length > 0 && (
            <div className="mt-2.5">
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-slate-800 transition"
              >
                {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                {isExpanded ? "Hide details" : `View details (${entry.details.length})`}
              </button>

              {isExpanded && (
                <div className="mt-2.5 rounded-lg border border-slate-100 bg-slate-50/50 p-3 text-xs text-slate-700 space-y-1.5">
                  {entry.details.map((detail, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="h-1.5 w-1.5 rounded-full bg-slate-400"></span>
                      <span className={isUndone ? "line-through text-slate-400" : ""}>{detail}</span>
                    </div>
                  ))}

                  {entry.action_id && (
                    <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between">
                      <span className="text-[10px] text-slate-400">Action ID: {entry.action_id}</span>
                      {isUndone ? (
                        <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">
                          Undone
                        </span>
                      ) : (
                        <button
                          type="button"
                          disabled={isUndoing}
                          onClick={() => onUndo(entry.action_id!)}
                          className="inline-flex items-center gap-1 rounded bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-700 hover:bg-slate-200 transition disabled:opacity-50"
                        >
                          {isUndoing ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : (
                            <Undo2 size={10} />
                          )}
                          Undo Action
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {!isAnchor && (
            <p className="mt-2 text-[11px] text-slate-400">
              {entry.word_count} words · {new Date(entry.created_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

function EmptyState() {
  return (
    <div className="mt-8 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <BookOpen className="mx-auto h-8 w-8 text-slate-400" />
      <p className="mt-3 text-sm font-semibold text-slate-700">No entries yet</p>
      <p className="mt-1 max-w-md mx-auto text-xs text-slate-500">
        Zilo writes here automatically as trust events happen — when you approve a staged action,
        promote him on a category, or flag a mistake. Start by reviewing today&apos;s briefing.
      </p>
      <Link
        href="/dashboard"
        className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-brand-ink hover:bg-brand-light"
      >
        Open Briefing
      </Link>
    </div>
  );
}
