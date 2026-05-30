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
  const [activeTab, setActiveTab] = useState<"timeline" | "status">("timeline");

  const [approvedActions, setApprovedActions] = useState<Set<string>>(new Set());
  const [dismissedActions, setDismissedActions] = useState<Set<string>>(new Set());
  const [promotedCategories, setPromotedCategories] = useState<Set<string>>(new Set());
  const [declinedRecommendations, setDeclinedRecommendations] = useState<Set<string>>(new Set());
  const [actionBusy, setActionBusy] = useState<string | null>(null);

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

  const handleApprove = useCallback(async (actionId: string) => {
    setActionBusy(actionId);
    setToast(null);
    try {
      await api.post(`/rex/actions/${actionId}/approve`, {});
      setApprovedActions((prev) => new Set([...prev, actionId]));
      setToast({ message: "Action approved and outreach sent.", type: "success" });
    } catch (e) {
      setToast({
        message: e instanceof Error ? e.message : "Failed to approve action.",
        type: "error",
      });
    } finally {
      setActionBusy(null);
    }
  }, []);

  const handleDismiss = useCallback(async (actionId: string) => {
    setActionBusy(actionId);
    setToast(null);
    try {
      await api.post(`/rex/actions/${actionId}/dismiss`, {});
      setDismissedActions((prev) => new Set([...prev, actionId]));
      setToast({ message: "Action dismissed.", type: "success" });
    } catch (e) {
      setToast({
        message: e instanceof Error ? e.message : "Failed to dismiss action.",
        type: "error",
      });
    } finally {
      setActionBusy(null);
    }
  }, []);

  const handlePromoteCategory = useCallback(async (category: string, recommendationId: string) => {
    setActionBusy(recommendationId);
    setToast(null);
    try {
      await api.post("/rex/promote", { category });
      setPromotedCategories((prev) => new Set([...prev, category]));
      setDeclinedRecommendations((prev) => new Set([...prev, recommendationId]));
      setToast({ message: "Zilo promoted successfully!", type: "success" });
    } catch (e) {
      setToast({
        message: e instanceof Error ? e.message : "Failed to promote.",
        type: "error",
      });
    } finally {
      setActionBusy(null);
    }
  }, []);

  const handleDeclinePromotion = useCallback((recommendationId: string) => {
    setDeclinedRecommendations((prev) => new Set([...prev, recommendationId]));
    setToast({ message: "Promotion deferred.", type: "success" });
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
    <div className="mx-auto max-w-3xl px-6 py-8 animate-fadeIn">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#0d2818]/60">Zilo Autopilot</p>
          <h1 className="mt-1 text-3xl font-semibold text-slate-900">Journal & Progress</h1>
          <p className="mt-2 max-w-xl text-sm text-slate-600">
            Zilo&apos;s diary of his own growth — written in his voice, evolving as the
            relationship deepens. Not a log of what you did. A log of what he became.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowExplainer((v) => !v)}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
        >
          <Info size={13} />
          {showExplainer ? "Hide Help" : "How this works"}
        </button>
      </div>

      {showExplainer && (
        <div className="mt-4 rounded-xl border border-brand/30 bg-brand/5 p-5 text-sm text-slate-700 animate-slideDown">
          <p className="font-semibold text-[#0d2818]">What you&apos;re reading</p>
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
          {/* Quick Stats Bar */}
          <div className="mt-6 grid grid-cols-3 gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="text-center">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Relationship</p>
              <p className="mt-1 text-base font-bold text-slate-800">Day {data.relationship_day}</p>
            </div>
            <div className="text-center border-x border-slate-100">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Voice Phase</p>
              <p className="mt-1 text-base font-bold text-[#0d2818]">
                {data.phase ? PHASE_LABEL[data.phase.phase] ?? data.phase.phase : "Observing"}
              </p>
            </div>
            <div className="text-center">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Daily Streak</p>
              <p className="mt-1 text-base font-bold text-amber-600 flex items-center justify-center gap-1">
                <Flame size={14} className="fill-amber-500 text-amber-500" />
                {data.engagement?.streak_days ?? 0} Days
              </p>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="mt-6 flex border-b border-slate-200">
            <button
              type="button"
              onClick={() => setActiveTab("timeline")}
              className={`pb-3 text-sm font-semibold transition-all border-b-2 px-4 ${
                activeTab === "timeline"
                  ? "border-[#0d2818] text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Timeline Logs
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("status")}
              className={`pb-3 text-sm font-semibold transition-all border-b-2 px-4 ${
                activeTab === "status"
                  ? "border-[#0d2818] text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              System Progress & Learnings
            </button>
          </div>

          <div className="mt-6">
            {activeTab === "timeline" ? (
              <>
                {data.ambient_thought && (
                  <div className="mb-6 rounded-xl border border-[#0d2818]/15 bg-gradient-to-r from-[#eefaf2] to-white p-5 shadow-sm">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-[#0d2818]/70">Zilo&apos;s Daily Ambient Thought</p>
                    <blockquote className="mt-2 text-base italic font-serif leading-relaxed text-slate-800 border-l-2 border-[#0d2818] pl-3">
                      &ldquo;{data.ambient_thought}&rdquo;
                    </blockquote>
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
                    <div className="mt-6 space-y-6">
                      {entriesByDay.map(([day, entries]) => (
                        <DaySection
                          key={day}
                          day={day}
                          entries={entries}
                          undoneActions={undoneActions}
                          undoing={undoing}
                          onUndo={handleUndo}
                          approvedActions={approvedActions}
                          dismissedActions={dismissedActions}
                          declinedRecommendations={declinedRecommendations}
                          actionBusy={actionBusy}
                          onApprove={handleApprove}
                          onDismiss={handleDismiss}
                          onPromote={handlePromoteCategory}
                          onDeclinePromotion={handleDeclinePromotion}
                          pendingRecommendationIds={data?.pending_recommendations || []}
                        />
                      ))}
                    </div>
                  </>
                )}
              </>
            ) : (
              <div className="space-y-6 animate-fadeIn">
                {data.phase && (
                  <PhaseBanner
                    phase={data.phase}
                    day={data.relationship_day}
                    engagement={data.engagement}
                    autopilotProgress={data.autopilot_progress}
                  />
                )}

                {data.active_learnings && data.active_learnings.length > 0 && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 pt-2">
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                      </span>
                      <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500">Active Learning Loop</h3>
                    </div>
                    
                    <div className="grid gap-4 sm:grid-cols-2">
                      {data.active_learnings.map((learning) => {
                        const isApplied = learning.status === "applied";
                        const isMuted = learning.status === "muted";
                        const statusLabel = isApplied 
                          ? "Applied" 
                          : isMuted 
                          ? "Muted" 
                          : "Observing";
                        const statusColor = isApplied
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                          : isMuted
                          ? "bg-amber-50 text-amber-700 border-amber-200"
                          : "bg-blue-50 text-blue-700 border-blue-200";
                        
                        return (
                          <div 
                            key={learning.id} 
                            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-all hover:shadow-md"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="inline-flex rounded bg-slate-50 border border-slate-200 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-600">
                                {formatCategory(learning.category)}
                              </span>
                              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold ${statusColor}`}>
                                {isApplied && <CheckCircle2 size={10} />}
                                {learning.status === "observing" && <Loader2 size={10} className="animate-spin" />}
                                {statusLabel}
                              </span>
                            </div>
                            
                            <div className="mt-3 space-y-3">
                              <div>
                                <p className="text-xs font-semibold text-slate-800 leading-normal">&ldquo;{learning.observation}&rdquo;</p>
                                <p className="mt-1 text-[9px] text-slate-400">Observed from {learning.source}</p>
                              </div>
                              
                              <div className="rounded-lg bg-blue-50/40 border border-blue-100 p-2.5">
                                <p className="text-[9px] font-bold text-blue-600 uppercase tracking-wider">Lesson</p>
                                <p className="mt-0.5 text-xs font-medium text-slate-850 leading-relaxed">{learning.lesson}</p>
                              </div>
                              
                              <div className="flex justify-between items-center text-[11px] text-slate-500 pt-1">
                                <span>Impact: {learning.impact}</span>
                                {learning.applied_to && (
                                  <span className="text-[9px] font-semibold bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded text-slate-700">
                                    {learning.applied_to}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
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
        className="mt-10 inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-light transition"
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
  const nextDays = phase.next_phase_in_days;
  const nextLabel = phase.next_phase ? PHASE_LABEL[phase.next_phase] ?? phase.next_phase : null;
  return (
    <div className="space-y-6">
      {/* Voice Phase Card */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-sm font-bold text-slate-800 font-sans">Voice Phase: {label}</h4>
            <p className="mt-1 text-xs text-slate-500">{PHASE_HINT[phase.phase] ?? ""}</p>
          </div>
          <span className="rounded bg-slate-50 border border-slate-200 px-2 py-1 text-[10px] font-bold text-slate-600">
            Day {phase.day_range_lo}
            {phase.day_range_hi != null ? `–${phase.day_range_hi}` : "+"}
          </span>
        </div>

        <div className="mt-4">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full bg-gradient-to-r from-emerald-500 to-teal-600 transition-all"
              style={{ width: `${phase.progress_pct}%` }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
            <span>{phase.progress_pct}% Phase Progress</span>
            {nextLabel && nextDays != null ? (
              <span>
                Next Phase: <strong className="text-slate-700">{nextLabel}</strong> in {nextDays} day{nextDays === 1 ? "" : "s"}
              </span>
            ) : (
              <span>Final Phase Achieved</span>
            )}
          </div>
        </div>

        {phase.tease && (
          <div className="mt-4 rounded-lg bg-amber-50/50 border border-amber-200/50 p-3 text-xs italic text-amber-800 font-sans">
            &ldquo;{phase.tease}&rdquo;
          </div>
        )}

        <div className="mt-4 rounded-lg bg-slate-50 border border-slate-100 p-3">
          <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400">
            Writing Sample Today
          </p>
          <p className="mt-1 text-xs italic text-slate-600">&ldquo;{phase.example}&rdquo;</p>
        </div>
      </div>

      {/* Autopilot Rank Progression Card */}
      {autopilotProgress && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h4 className="text-sm font-bold text-slate-800">Autopilot Rank Progression</h4>
              <p className="mt-1 text-xs text-slate-500">
                Current: <strong className="text-slate-700">{autopilotProgress.current_rank}</strong> &rarr; Target: <strong className="text-emerald-600">{autopilotProgress.target_rank}</strong> ({formatCategory(autopilotProgress.category)})
              </p>
            </div>
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-xs font-bold text-emerald-700">
              <Star size={12} className="fill-emerald-500 text-emerald-500" />
              {autopilotProgress.progress_pct}% Complete
            </span>
          </div>
          <div className="mt-4">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-teal-600 transition-all"
                style={{ width: `${autopilotProgress.progress_pct}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-slate-600 leading-relaxed">
              {autopilotProgress.text}
            </p>
          </div>
        </div>
      )}
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
        className={`rounded-full border px-3 py-1 text-xs font-medium transition-all ${
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
          className={`rounded-full border px-3 py-1 text-xs font-medium transition-all ${
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
  approvedActions,
  dismissedActions,
  declinedRecommendations,
  actionBusy,
  onApprove,
  onDismiss,
  onPromote,
  onDeclinePromotion,
  pendingRecommendationIds,
}: {
  day: number;
  entries: JournalEntry[];
  undoneActions: Set<string>;
  undoing: string | null;
  onUndo: (actionId: string) => void;
  approvedActions: Set<string>;
  dismissedActions: Set<string>;
  declinedRecommendations: Set<string>;
  actionBusy: string | null;
  onApprove: (actionId: string) => void;
  onDismiss: (actionId: string) => void;
  onPromote: (category: string, recommendationId: string) => void;
  onDeclinePromotion: (recommendationId: string) => void;
  pendingRecommendationIds: string[];
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
            approvedActions={approvedActions}
            dismissedActions={dismissedActions}
            declinedRecommendations={declinedRecommendations}
            actionBusy={actionBusy}
            onApprove={onApprove}
            onDismiss={onDismiss}
            onPromote={onPromote}
            onDeclinePromotion={onDeclinePromotion}
            pendingRecommendationIds={pendingRecommendationIds}
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
  approvedActions,
  dismissedActions,
  declinedRecommendations,
  actionBusy,
  onApprove,
  onDismiss,
  onPromote,
  onDeclinePromotion,
  pendingRecommendationIds,
}: {
  entry: JournalEntry;
  isUndone: boolean;
  isUndoing: boolean;
  onUndo: (actionId: string) => void;
  approvedActions: Set<string>;
  dismissedActions: Set<string>;
  declinedRecommendations: Set<string>;
  actionBusy: string | null;
  onApprove: (actionId: string) => void;
  onDismiss: (actionId: string) => void;
  onPromote: (category: string, recommendationId: string) => void;
  onDeclinePromotion: (recommendationId: string) => void;
  pendingRecommendationIds: string[];
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
    ? "rounded-xl border-2 border-amber-300 bg-gradient-to-br from-amber-50 via-white to-white p-5 shadow-md ring-1 ring-amber-200/50 transition hover:shadow-lg animate-fadeIn"
    : isAnchor
    ? "rounded-xl border border-slate-200 bg-slate-50/60 p-4 shadow-sm transition hover:bg-slate-50"
    : isReturned
    ? "rounded-xl border border-sky-200 bg-sky-50/60 p-4 shadow-sm transition hover:shadow-md"
    : `rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md ${isUndone ? "opacity-75" : ""}`;

  const bodyClass = isMilestone
    ? `mt-1.5 whitespace-pre-wrap text-[16px] font-medium leading-relaxed text-slate-900 ${isUndone ? "line-through text-slate-400" : ""}`
    : isAnchor
    ? "mt-1.5 whitespace-pre-wrap text-[14px] italic leading-relaxed text-slate-500"
    : `mt-1.5 whitespace-pre-wrap text-[14px] leading-relaxed text-slate-850 ${isUndone ? "line-through text-slate-400" : ""}`;

  const recId = entry.source_event_ids[0];
  const isPendingRec = entry.kind === "recommendation" && pendingRecommendationIds.includes(recId) && !declinedRecommendations.has(recId);
  const isPendingAction = entry.action_id && !approvedActions.has(entry.action_id) && !dismissedActions.has(entry.action_id) && !isUndone && (entry.kind === "background_action" || entry.kind === "recommendation" || entry.kind === "operational_win" || entry.id.includes("reddit-scout"));

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

          {/* Interactive buttons for Pending Actions (Send it / Not now) */}
          {entry.action_id && isPendingAction && !isPendingRec && (
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                disabled={actionBusy === entry.action_id}
                onClick={() => onApprove(entry.action_id!)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#0d2818] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#1b4d2c] transition disabled:opacity-50"
              >
                {actionBusy === entry.action_id ? <Loader2 size={11} className="animate-spin" /> : null}
                Send it
              </button>
              <button
                type="button"
                disabled={actionBusy === entry.action_id}
                onClick={() => onDismiss(entry.action_id!)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition disabled:opacity-50"
              >
                Not now
              </button>
            </div>
          )}

          {/* Interactive buttons for Pending Promotion Recommendations (Yes / Not yet) */}
          {isPendingRec && (
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                disabled={actionBusy === recId}
                onClick={() => onPromote(entry.category, recId)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#0d2818] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#1b4d2c] transition disabled:opacity-50"
              >
                {actionBusy === recId ? <Loader2 size={11} className="animate-spin" /> : null}
                Yes — you&apos;ve earned it
              </button>
              <button
                type="button"
                disabled={actionBusy === recId}
                onClick={() => onDeclinePromotion(recId)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition disabled:opacity-50"
              >
                Not yet
              </button>
            </div>
          )}

          {/* Static state feedback badges for completed interactive events */}
          {entry.action_id && approvedActions.has(entry.action_id) && (
            <div className="mt-2.5">
              <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200">
                ✓ Sent
              </span>
            </div>
          )}
          {entry.action_id && dismissedActions.has(entry.action_id) && (
            <div className="mt-2.5">
              <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500 border border-slate-200">
                Not now
              </span>
            </div>
          )}
          {entry.kind === "recommendation" && !pendingRecommendationIds.includes(recId) && (
            <div className="mt-2.5">
              <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200">
                ✓ Promoted
              </span>
            </div>
          )}
          {entry.kind === "recommendation" && pendingRecommendationIds.includes(recId) && declinedRecommendations.has(recId) && (
            <div className="mt-2.5">
              <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700 border border-amber-200">
                Not yet
              </span>
            </div>
          )}

          {entry.details && entry.details.length > 0 && (
            <div className="mt-2">
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-slate-800 transition"
              >
                {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                {isExpanded ? "Hide details" : `View details (${entry.details.length})`}
              </button>

              {isExpanded && (
                <div className="mt-2 rounded-lg border border-slate-150 bg-slate-50/50 p-3 text-xs text-slate-700 space-y-1.5">
                  {entry.details.map((detail, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="h-1 w-1 rounded-full bg-slate-400"></span>
                      <span className={isUndone ? "line-through text-slate-400" : ""}>{detail}</span>
                    </div>
                  ))}

                  {entry.action_id && (
                    <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-end">
                      {isUndone ? (
                        <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">
                          Undone
                        </span>
                      ) : (
                        <button
                          type="button"
                          disabled={isUndoing}
                          onClick={() => onUndo(entry.action_id!)}
                          className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-semibold text-slate-700 hover:bg-slate-50 transition disabled:opacity-50"
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
