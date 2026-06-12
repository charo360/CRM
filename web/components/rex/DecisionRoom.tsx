"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Loader2,
  Scale,
  Archive,
  MessageSquareWarning,
  Send,
  Check,
  Plus,
  Lightbulb,
  Sparkles,
  CornerDownLeft,
  Pencil,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

type DataFact = { fact: string; source: string; confidence: "high" | "medium" | "low" };
type DataGap = { gap: string; connect: string };
type SparResult = {
  founder_lean_detected: string;
  your_data: DataFact[];
  case_for_lean: string[];
  case_against: string[];
  blind_spots: string[];
  data_gaps: DataGap[];
  pressure_question: string;
  zilo_note: string;
};

type Verdict = "held_up" | "mixed" | "worth_revisiting" | "too_early";

type OutcomeReport = {
  day: number;
  summary: string;
  verdict?: Verdict;
  reported_at?: string;
  due_at?: string;
  deltas?: Record<
    string,
    { current?: number; baseline?: number; delta?: number; pct?: number | null } | null
  >;
};

const VERDICT_META: Record<Verdict, { label: string; className: string }> = {
  held_up: { label: "Held up", className: "border-emerald-500/30 text-emerald-400" },
  mixed: { label: "Mixed", className: "border-amber-500/30 text-amber-400" },
  worth_revisiting: { label: "Worth revisiting", className: "border-orange-500/40 text-orange-400" },
  too_early: { label: "Too early", className: "border-slate-600 text-slate-400" },
};

type ThreadMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  regeneration_count?: number;
  feedback?: "up" | "down" | null;
};

type FounderUpdate = {
  text: string;
  zilo_reaction?: string;
  created_at?: string;
  regeneration_count?: number;
  feedback?: "up" | "down" | null;
};

const MAX_UPDATE_REGENERATIONS = 3;

type DecisionSession = {
  id: string;
  question: string;
  founder_lean: string;
  status: "open" | "decided" | "archived";
  spar: SparResult;
  thread?: ThreadMessage[];
  founder_updates?: FounderUpdate[];
  founder_decision: string | null;
  push_back_count: number;
  outcome_reports?: OutcomeReport[];
  outcome_checkpoints?: { day: number; due_at: string; status: string }[];
  metrics_baseline?: Record<string, unknown>;
  pricing_simulation?: DataFact[];
  created_at: string;
  updated_at: string;
  decided_at: string | null;
};

const CONFIDENCE_STYLE: Record<string, string> = {
  high: "text-emerald-400",
  medium: "text-amber-400",
  low: "text-slate-500",
};

const EXAMPLE_PROMPTS = [
  "Should I raise my prices or keep them where they are?",
  "Do I pause marketing and fix follow-ups first?",
  "Should I hire my first employee or stay solo?",
  "Is it time to drop my lowest-margin product line?",
];

/* ── helpers ─────────────────────────────────────────────────────────── */

function splitFact(fact: string): { label: string; value: string } {
  const idx = fact.indexOf(":");
  if (idx > 0 && idx <= 40) {
    return { label: fact.slice(0, idx).trim(), value: fact.slice(idx + 1).trim() };
  }
  return { label: "", value: fact };
}

function dayNumber(createdAt: string): number {
  const created = new Date(createdAt).getTime();
  if (Number.isNaN(created)) return 1;
  return Math.max(1, Math.floor((Date.now() - created) / 86_400_000) + 1);
}

function shortDate(d?: string | null): string {
  if (!d) return "";
  const t = new Date(d);
  if (Number.isNaN(t.getTime())) return "";
  return t.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function latestVerdict(s: DecisionSession): Verdict | null {
  const reports = (s.outcome_reports || []).filter((r) => r.verdict);
  if (!reports.length) return null;
  const latest = reports.reduce((a, b) => (b.day > a.day ? b : a));
  return (latest.verdict as Verdict) ?? null;
}

function reviewStatus(s: DecisionSession): { text: string; reviewed: boolean } {
  const v = latestVerdict(s);
  if (v) return { text: VERDICT_META[v].label, reviewed: v === "held_up" };
  const cps = s.outcome_checkpoints || [];
  const reports = s.outcome_reports || [];
  if (cps.length && reports.length >= cps.length) return { text: "reviewed", reviewed: true };
  const due = cps.find((c) => c.status !== "reported");
  if (due) return { text: `${due.day}-day review due`, reviewed: false };
  if (reports.length) return { text: "reviewed", reviewed: true };
  return { text: "tracking", reviewed: false };
}

function activeStatus(s: DecisionSession): string {
  const hasChat = (s.thread || []).some((m) => m.role === "user");
  return hasChat ? "sparring" : "pending decision";
}

function caseTitles(s: DecisionSession): { forTitle: string; againstTitle: string } {
  const lean = (s.founder_lean || "").trim();
  const short = lean && lean.length <= 22 ? lean.toLowerCase() : "";
  return {
    forTitle: short ? `Case for ${short}` : "Case for your lean",
    againstTitle: short ? `Case against ${short}` : "Case against",
  };
}

/* ── small presentational pieces ─────────────────────────────────────── */

function Label({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">{children}</p>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (!items.length) return <p className="text-sm text-slate-500">—</p>;
  return (
    <ul className="space-y-2 text-sm leading-relaxed text-slate-200">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2">
          <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand-light" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function MetricsRow({ facts }: { facts: DataFact[] }) {
  if (!facts.length) return null;
  return (
    <div className="flex flex-wrap gap-x-10 gap-y-4 border-y border-white/5 py-4">
      {facts.slice(0, 6).map((d, i) => {
        const { label, value } = splitFact(d.fact);
        return (
          <div key={i} className="min-w-[90px]">
            {label && (
              <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
            )}
            <p className="mt-0.5 text-base font-semibold text-slate-100">{value}</p>
            <p className={cn("mt-0.5 text-[11px]", CONFIDENCE_STYLE[d.confidence])}>
              {d.confidence} confidence
            </p>
          </div>
        );
      })}
    </div>
  );
}

/* ── conversation ────────────────────────────────────────────────────── */

function AdvisorReactionControls({
  index,
  regenerationCount = 0,
  feedback,
  isRegenerating,
  disableRegenerate,
  hoverClass,
  onFeedback,
  onRegenerate,
}: {
  index: number;
  regenerationCount?: number;
  feedback?: "up" | "down" | null;
  isRegenerating: boolean;
  disableRegenerate?: boolean;
  hoverClass: string;
  onFeedback: (index: number, value: "up" | "down") => void;
  onRegenerate: (index: number) => void;
}) {
  const atCap = regenerationCount >= MAX_UPDATE_REGENERATIONS;

  return (
    <div className={cn("flex items-center gap-0.5 opacity-0 transition-opacity", hoverClass)}>
      <button
        type="button"
        disabled={isRegenerating}
        onClick={() => onFeedback(index, "up")}
        className={cn(
          "rounded p-1 text-slate-600 hover:text-slate-400 disabled:opacity-40",
          feedback === "up" && "text-emerald-500/70"
        )}
        aria-label="Helpful response"
        title="Helpful"
      >
        <ThumbsUp className="h-3 w-3" />
      </button>
      <button
        type="button"
        disabled={isRegenerating}
        onClick={() => onFeedback(index, "down")}
        className={cn(
          "rounded p-1 text-slate-600 hover:text-slate-400 disabled:opacity-40",
          feedback === "down" && "text-rose-500/70"
        )}
        aria-label="Unhelpful response"
        title="Unhelpful"
      >
        <ThumbsDown className="h-3 w-3" />
      </button>
      {!atCap && (
        <button
          type="button"
          disabled={isRegenerating || disableRegenerate}
          onClick={() => onRegenerate(index)}
          className="rounded p-1 text-slate-600 hover:text-slate-400 disabled:opacity-40"
          aria-label="Regenerate response"
          title="Regenerate response"
        >
          {isRegenerating ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
        </button>
      )}
    </div>
  );
}

function ConversationThread({
  session,
  busy,
  interactive,
  onFeedback,
  onRegenerate,
  regeneratingIndex,
  onPrefillChat,
}: {
  session: DecisionSession;
  busy: boolean;
  interactive: boolean;
  onFeedback: (index: number, value: "up" | "down") => void;
  onRegenerate: (index: number) => void;
  regeneratingIndex: number | null;
  onPrefillChat: (text: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const thread = session.thread || [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread.length, busy]);

  if (thread.length === 0 && !busy) return <div ref={bottomRef} />;

  return (
    <div className="space-y-5">
      {thread.map((m, i) =>
        m.role === "user" ? (
          <div key={i} className="flex justify-end">
            <div className="max-w-[80%] rounded-lg rounded-br-sm bg-brand px-4 py-2.5 text-sm leading-relaxed text-black">
              {m.content}
            </div>
          </div>
        ) : (
          <div key={i} className="group/advisor">
            <div className="flex items-center justify-between gap-2">
              <Label>Zilo</Label>
              {interactive && (
                <AdvisorReactionControls
                  index={i}
                  regenerationCount={m.regeneration_count ?? 0}
                  feedback={m.feedback}
                  isRegenerating={regeneratingIndex === i}
                  disableRegenerate={busy}
                  hoverClass="group-hover/advisor:opacity-100"
                  onFeedback={onFeedback}
                  onRegenerate={onRegenerate}
                />
              )}
            </div>
            <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
              {m.content}
            </p>
            {interactive && (m.regeneration_count ?? 0) >= MAX_UPDATE_REGENERATIONS && (
              <button
                type="button"
                onClick={() =>
                  onPrefillChat(
                    "More context on what I need from you here: "
                  )
                }
                className="mt-2 text-left text-[11px] text-slate-500 underline-offset-2 hover:text-slate-400 hover:underline"
              >
                Add more context to get a better response
              </button>
            )}
          </div>
        )
      )}
      {busy && (
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Loader2 className="h-3 w-3 animate-spin" />
          Zilo is thinking…
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

/* ── main detail view ────────────────────────────────────────────────── */

function fmtDate(d?: string): string {
  if (!d) return "";
  const t = new Date(d);
  if (Number.isNaN(t.getTime())) return "";
  return t.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function ZiloReactionBar({
  updateIndex,
  reaction,
  founderLogText,
  regenerationCount = 0,
  feedback,
  isRegenerating,
  logBusy,
  onFeedback,
  onRegenerate,
  onNeedMoreContext,
}: {
  updateIndex: number;
  reaction: string;
  founderLogText: string;
  regenerationCount?: number;
  feedback?: "up" | "down" | null;
  isRegenerating: boolean;
  logBusy: boolean;
  onFeedback: (index: number, value: "up" | "down") => void;
  onRegenerate: (index: number) => void;
  onNeedMoreContext: (prefill: string) => void;
}) {
  const atCap = regenerationCount >= MAX_UPDATE_REGENERATIONS;

  return (
    <div className="mt-2 border-t border-white/5 pt-2">
      <div className="flex items-center justify-between gap-2">
        <Label>Zilo</Label>
        <AdvisorReactionControls
          index={updateIndex}
          regenerationCount={regenerationCount}
          feedback={feedback}
          isRegenerating={isRegenerating}
          disableRegenerate={logBusy}
          hoverClass="group-hover/update:opacity-100"
          onFeedback={onFeedback}
          onRegenerate={onRegenerate}
        />
      </div>
      <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{reaction}</p>
      {atCap && (
        <button
          type="button"
          onClick={() =>
            onNeedMoreContext(
              `More context on my earlier update ("${founderLogText.slice(0, 120)}${founderLogText.length > 120 ? "…" : ""}"): `
            )
          }
          className="mt-2 text-left text-[11px] text-slate-500 underline-offset-2 hover:text-slate-400 hover:underline"
        >
          Add more context to get a better response
        </button>
      )}
    </div>
  );
}

/** Founder can come back and log what actually happened; Zilo reacts as advisor. */
function UpdateLog({
  session,
  onAddNote,
  onFeedback,
  onRegenerate,
  regeneratingIndex,
  busy,
}: {
  session: DecisionSession;
  onAddNote: (text: string) => void;
  onFeedback: (index: number, value: "up" | "down") => void;
  onRegenerate: (index: number) => void;
  regeneratingIndex: number | null;
  busy: boolean;
}) {
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const updates = session.founder_updates || [];

  const submit = () => {
    const text = draft.trim();
    if (!text || busy) return;
    onAddNote(text);
    setDraft("");
  };

  const prefillDraft = (text: string) => {
    setDraft(text);
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  return (
    <div className="space-y-3">
      <div>
        <Label>Updates &amp; outcomes</Label>
        <p className="mt-1 text-xs text-slate-500">
          Come back anytime and log what actually happened. Zilo reviews it against your call.
        </p>
      </div>

      {updates.length > 0 && (
        <div className="space-y-3">
          {updates.map((u, i) => (
            <div
              key={i}
              className="group/update rounded-lg border border-white/10 bg-white/[0.02] p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <Label>You logged</Label>
                {u.created_at && (
                  <span className="text-[10px] text-slate-600">{fmtDate(u.created_at)}</span>
                )}
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-slate-200">{u.text}</p>
              {u.zilo_reaction && (
                <ZiloReactionBar
                  updateIndex={i}
                  reaction={u.zilo_reaction}
                  founderLogText={u.text}
                  regenerationCount={u.regeneration_count ?? 0}
                  feedback={u.feedback}
                  isRegenerating={regeneratingIndex === i}
                  logBusy={busy}
                  onFeedback={onFeedback}
                  onRegenerate={onRegenerate}
                  onNeedMoreContext={prefillDraft}
                />
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="e.g. Called the 7 overdue follow-ups — 2 converted, 3 said the price was too high, 2 went silent."
          rows={2}
          disabled={busy}
          className="min-h-[2.75rem] flex-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-brand/40 focus:outline-none disabled:opacity-50"
        />
        <button
          type="button"
          disabled={busy || !draft.trim()}
          onClick={submit}
          className="inline-flex shrink-0 items-center justify-center rounded-lg bg-brand px-3.5 text-black hover:bg-brand-light disabled:opacity-50"
          aria-label="Log update"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

function DetailView({
  session,
  onPushBack,
  onSendMessage,
  onAddNote,
  onUpdateFeedback,
  onRegenerateReaction,
  regeneratingUpdateIndex,
  onThreadFeedback,
  onThreadRegenerate,
  regeneratingThreadIndex,
  onDecide,
  onUpdateSchedule,
  onArchive,
  busy,
}: {
  session: DecisionSession;
  onPushBack: () => void;
  onSendMessage: (text: string) => void;
  onAddNote: (text: string) => void;
  onUpdateFeedback: (index: number, value: "up" | "down") => void;
  onRegenerateReaction: (index: number) => void;
  regeneratingUpdateIndex: number | null;
  onThreadFeedback: (index: number, value: "up" | "down") => void;
  onThreadRegenerate: (index: number) => void;
  regeneratingThreadIndex: number | null;
  onDecide: (decision: string, reviewDays: number[]) => void;
  onUpdateSchedule: (reviewDays: number[]) => void;
  onArchive: () => void;
  busy: boolean;
}) {
  const [draft, setDraft] = useState("");
  const chatRef = useRef<HTMLTextAreaElement>(null);
  const [deciding, setDeciding] = useState(false);
  const [decisionText, setDecisionText] = useState(session.founder_decision || "");
  const [reviewDays, setReviewDays] = useState<number[]>([30, 60, 90]);
  const spar = session.spar;
  const decided = session.status === "decided";
  const { forTitle, againstTitle } = caseTitles(session);
  const lean = session.founder_lean || spar.founder_lean_detected;

  const send = () => {
    const text = draft.trim();
    if (!text || busy || decided) return;
    onSendMessage(text);
    setDraft("");
  };

  const prefillChat = (text: string) => {
    setDraft(text);
    requestAnimationFrame(() => chatRef.current?.focus());
  };

  return (
    <div className="space-y-7 px-6 py-7 sm:px-10">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Label>The call you&apos;re weighing</Label>
          <h1 className="mt-1.5 text-xl font-medium leading-snug text-slate-100">
            {session.question}
          </h1>
        </div>
        {lean && (
          <p className="shrink-0 whitespace-nowrap text-xs text-slate-500">
            Leaning: <span className="text-slate-300">{lean}</span>
          </p>
        )}
      </div>

      {/* Metrics */}
      <MetricsRow facts={spar.your_data} />

      {(session.pricing_simulation?.length ?? 0) > 0 && (
        <p className="rounded-lg border border-violet-500/20 bg-violet-500/5 px-3 py-2 text-xs text-violet-300">
          Pricing scenarios included — numbers are illustrative from your CRM data.
        </p>
      )}

      {/* Zilo's read */}
      <div className="space-y-6">
        <Label>Zilo</Label>

        <div className="grid gap-8 md:grid-cols-2">
          <div className="space-y-2">
            <Label>{forTitle}</Label>
            <BulletList items={spar.case_for_lean} />
          </div>
          <div className="space-y-2">
            <Label>{againstTitle}</Label>
            <BulletList items={spar.case_against} />
          </div>
        </div>

        {spar.blind_spots.length > 0 && (
          <div className="space-y-2">
            <Label>Blind spot</Label>
            <BulletList items={spar.blind_spots} />
          </div>
        )}

        {spar.pressure_question && (
          <div className="space-y-2">
            <Label>Pressure question</Label>
            <p className="text-base font-medium text-slate-100">{spar.pressure_question}</p>
          </div>
        )}

        {spar.data_gaps.length > 0 && (
          <p className="text-xs text-slate-500">
            Limited by missing data:{" "}
            {spar.data_gaps.map((g, i) => (
              <span key={i}>
                {i > 0 ? ", " : ""}
                {g.connect ? (
                  <Link href="/dashboard/integrations" className="text-brand-light hover:underline">
                    {g.connect}
                  </Link>
                ) : (
                  g.gap
                )}
              </span>
            ))}
          </p>
        )}
      </div>

      {/* Conversation */}
      <ConversationThread
        session={session}
        busy={busy}
        interactive={!decided}
        onFeedback={onThreadFeedback}
        onRegenerate={onThreadRegenerate}
        regeneratingIndex={regeneratingThreadIndex}
        onPrefillChat={prefillChat}
      />

      {/* Decided state */}
      {decided ? (
        <div className="space-y-6 border-t border-white/5 pt-6">
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-5">
            <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-emerald-400">
              <Check className="h-3.5 w-3.5" /> Your decision (recorded)
            </p>
            <p className="mt-2 text-sm leading-relaxed text-slate-200">
              {session.founder_decision}
            </p>
          </div>
          <OutcomesPanel session={session} onUpdateSchedule={onUpdateSchedule} busy={busy} />
          <UpdateLog
            session={session}
            onAddNote={onAddNote}
            onFeedback={onUpdateFeedback}
            onRegenerate={onRegenerateReaction}
            regeneratingIndex={regeneratingUpdateIndex}
            busy={busy}
          />
        </div>
      ) : deciding ? (
        <div className="space-y-3 border-t border-white/5 pt-6">
          <Label>Make your call</Label>
          <p className="text-xs text-slate-400">
            State what you decided and why. Zilo records it and checks back at 30/60/90 days — he
            won&apos;t override you.
          </p>
          <textarea
            value={decisionText}
            onChange={(e) => setDecisionText(e.target.value)}
            placeholder="e.g. Shipping the seeding flow this week, then launching marketing next week. The first-impression risk is solvable in days — not a reason to delay growth."
            rows={4}
            autoFocus
            className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-brand/40 focus:outline-none"
          />

          <ReviewSchedulePicker reviewDays={reviewDays} onChange={setReviewDays} disabled={busy} />

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || !decisionText.trim() || reviewDays.length === 0}
              onClick={() => onDecide(decisionText.trim(), reviewDays)}
              className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-black hover:bg-brand-light disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              Record my decision
            </button>
            <button
              type="button"
              onClick={() => setDeciding(false)}
              className="rounded-lg px-3 py-2 text-sm text-slate-400 hover:text-slate-200"
            >
              Not yet
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3 border-t border-white/5 pt-5">
          {/* Action bar */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={onPushBack}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 hover:bg-white/10 disabled:opacity-50"
            >
              <MessageSquareWarning className="h-3.5 w-3.5" />
              Push back harder
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                onSendMessage(
                  "Walk me through 2–3 what-if scenarios for this decision and how each would likely play out."
                )
              }
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 hover:bg-white/10 disabled:opacity-50"
            >
              <Sparkles className="h-3.5 w-3.5" />
              What-if scenarios
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                onSendMessage("I'm stuck. What are my realistic options here, with the trade-offs?")
              }
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 hover:bg-white/10 disabled:opacity-50"
            >
              <Lightbulb className="h-3.5 w-3.5" />
              I&apos;m stuck
            </button>
            <button
              type="button"
              onClick={() => setDeciding(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3.5 py-1.5 text-xs font-medium text-black hover:bg-brand-light"
            >
              <Check className="h-3.5 w-3.5" />
              Record my decision
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onArchive}
              className="ml-auto inline-flex items-center gap-1.5 px-2 py-1.5 text-xs text-slate-500 hover:text-slate-300 disabled:opacity-50"
            >
              <Archive className="h-3.5 w-3.5" />
              Archive
            </button>
          </div>

          {/* Composer */}
          <div className="flex gap-2">
            <textarea
              ref={chatRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Push back or think out loud…"
              rows={2}
              disabled={busy}
              className="min-h-[2.75rem] flex-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-brand/40 focus:outline-none disabled:opacity-50"
            />
            <button
              type="button"
              disabled={busy || !draft.trim()}
              onClick={send}
              className="inline-flex shrink-0 items-center justify-center rounded-lg bg-brand px-3.5 text-black hover:bg-brand-light disabled:opacity-50"
              aria-label="Send message"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </div>
          <p className="flex items-center gap-1 text-[11px] text-slate-600">
            <CornerDownLeft className="h-3 w-3" /> Enter to send · Shift+Enter for a new line
          </p>
        </div>
      )}
    </div>
  );
}

const PRESET_REVIEW_DAYS = [7, 14, 30, 60, 90];

function ReviewSchedulePicker({
  reviewDays,
  onChange,
  disabled,
}: {
  reviewDays: number[];
  onChange: (days: number[]) => void;
  disabled?: boolean;
}) {
  const [customDay, setCustomDay] = useState("");
  const [editingDay, setEditingDay] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");

  const addCustom = () => {
    const n = parseInt(customDay, 10);
    if (n >= 1 && n <= 365 && !reviewDays.includes(n)) {
      onChange([...reviewDays, n].sort((a, b) => a - b));
    }
    setCustomDay("");
  };

  const commitEdit = () => {
    if (editingDay === null) return;
    const n = parseInt(editValue, 10);
    if (n >= 1 && n <= 365 && n !== editingDay && !reviewDays.includes(n)) {
      onChange(
        reviewDays.map((d) => (d === editingDay ? n : d)).sort((a, b) => a - b)
      );
    }
    setEditingDay(null);
    setEditValue("");
  };

  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3">
      <p className="text-xs font-medium text-slate-300">When should Zilo check back?</p>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Tap presets to toggle. Add a custom period, or click a custom chip to change its days.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {PRESET_REVIEW_DAYS.map((d) => {
          const on = reviewDays.includes(d);
          return (
            <button
              key={d}
              type="button"
              disabled={disabled}
              onClick={() =>
                onChange(
                  on ? reviewDays.filter((x) => x !== d) : [...reviewDays, d].sort((a, b) => a - b)
                )
              }
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs",
                on
                  ? "border-brand/40 bg-brand/10 text-brand-light"
                  : "border-white/10 text-slate-400 hover:text-slate-200",
                disabled && "opacity-50"
              )}
            >
              {d}d
            </button>
          );
        })}
        {reviewDays
          .filter((d) => !PRESET_REVIEW_DAYS.includes(d))
          .map((d) =>
            editingDay === d ? (
              <span key={d} className="flex items-center gap-1">
                <input
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value.replace(/[^0-9]/g, ""))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      commitEdit();
                    }
                    if (e.key === "Escape") {
                      setEditingDay(null);
                      setEditValue("");
                    }
                  }}
                  onBlur={commitEdit}
                  autoFocus
                  inputMode="numeric"
                  className="w-14 rounded-full border border-brand/40 bg-black/20 px-2 py-1 text-xs text-slate-100 focus:outline-none"
                />
                <span className="text-[11px] text-slate-600">days</span>
              </span>
            ) : (
              <span
                key={d}
                className="inline-flex items-center rounded-full border border-brand/40 bg-brand/10 text-xs text-brand-light"
              >
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    setEditingDay(d);
                    setEditValue(String(d));
                  }}
                  className="px-2.5 py-1 hover:bg-brand/20 disabled:opacity-50"
                  title="Click to edit days"
                >
                  {d}d
                </button>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange(reviewDays.filter((x) => x !== d))}
                  className="border-l border-brand/30 px-2 py-1 text-slate-400 hover:text-slate-200 disabled:opacity-50"
                  aria-label={`Remove ${d} day review`}
                >
                  ✕
                </button>
              </span>
            )
          )}
        <span className="flex items-center gap-1">
          <input
            value={customDay}
            onChange={(e) => setCustomDay(e.target.value.replace(/[^0-9]/g, ""))}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustom();
              }
            }}
            placeholder="custom"
            inputMode="numeric"
            disabled={disabled}
            className="w-16 rounded-full border border-white/10 bg-black/20 px-2.5 py-1 text-xs text-slate-100 placeholder:text-slate-600 focus:border-brand/40 focus:outline-none disabled:opacity-50"
          />
          <button
            type="button"
            disabled={disabled || !customDay.trim()}
            onClick={addCustom}
            className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-300 hover:border-brand/40 hover:text-brand-light disabled:opacity-50"
          >
            Add
          </button>
        </span>
      </div>
    </div>
  );
}

function OutcomesPanel({
  session,
  onUpdateSchedule,
  busy,
}: {
  session: DecisionSession;
  onUpdateSchedule?: (reviewDays: number[]) => void;
  busy?: boolean;
}) {
  const reports = session.outcome_reports || [];
  const checkpoints = session.outcome_checkpoints || [];
  const [editing, setEditing] = useState(false);
  const checkpointDays = checkpoints.map((cp) => cp.day);
  const [reviewDays, setReviewDays] = useState<number[]>(
    checkpointDays.length ? checkpointDays : [30, 60, 90]
  );

  useEffect(() => {
    if (!editing) {
      setReviewDays(checkpointDays.length ? checkpointDays : [30, 60, 90]);
    }
  }, [checkpointDays.join(","), editing]);

  const scheduleLabel =
    checkpointDays.length > 0
      ? checkpointDays.map((d) => `${d}d`).join(" / ")
      : "30 / 60 / 90 days";

  if (!reports.length && !checkpoints.length && !onUpdateSchedule) {
    return (
      <div className="space-y-2">
        <Label>Outcome tracking</Label>
        <p className="text-sm text-slate-400">
          Zilo will check this decision at 30, 60, and 90 days against your baseline metrics.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label>Outcome tracking ({scheduleLabel})</Label>
        {onUpdateSchedule && !editing && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-xs text-slate-400 hover:border-brand/30 hover:text-brand-light"
          >
            <Pencil className="h-3 w-3" />
            Edit schedule
          </button>
        )}
      </div>

      {editing && onUpdateSchedule && (
        <div className="space-y-2">
          <ReviewSchedulePicker
            reviewDays={reviewDays}
            onChange={setReviewDays}
            disabled={busy}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || reviewDays.length === 0}
              onClick={() => {
                onUpdateSchedule(reviewDays);
                setEditing(false);
              }}
              className="inline-flex items-center gap-2 rounded-lg bg-brand px-3 py-1.5 text-xs font-medium text-black hover:bg-brand-light disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              Save schedule
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setReviewDays(checkpointDays.length ? checkpointDays : [30, 60, 90]);
                setEditing(false);
              }}
              className="rounded-lg px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
          </div>
          <p className="text-[11px] text-slate-500">
            Completed reviews stay locked. You can add or change upcoming check-ins.
          </p>
        </div>
      )}

      {checkpoints.length > 0 && !editing && (
        <div className="flex flex-wrap gap-2">
          {checkpoints.map((cp) => (
            <span
              key={cp.day}
              className={cn(
                "rounded-full border px-2.5 py-1 text-[11px] font-medium",
                cp.status === "reported"
                  ? "border-emerald-500/30 text-emerald-400"
                  : "border-slate-600 text-slate-500"
              )}
            >
              Day {cp.day}:{" "}
              {cp.status === "reported"
                ? "reported"
                : `due ${new Date(cp.due_at).toLocaleDateString()}`}
            </span>
          ))}
        </div>
      )}
      {reports.length > 0 && (
        <div className="space-y-3">
          {reports.map((r) => (
            <div
              key={r.day}
              className="rounded-lg border border-white/10 bg-white/[0.02] px-3 py-3 text-sm text-slate-200"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold uppercase tracking-widest text-brand-light">
                  Day {r.day} check
                </p>
                {r.verdict && (
                  <span
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                      VERDICT_META[r.verdict].className
                    )}
                  >
                    {VERDICT_META[r.verdict].label}
                  </span>
                )}
              </div>
              <p className="mt-2 leading-relaxed">{r.summary}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── start a new decision ────────────────────────────────────────────── */

function StartCard({
  question,
  setQuestion,
  lean,
  setLean,
  busy,
  onStart,
}: {
  question: string;
  setQuestion: (v: string) => void;
  lean: string;
  setLean: (v: string) => void;
  busy: boolean;
  onStart: () => void;
}) {
  const [showLean, setShowLean] = useState(false);
  return (
    <div className="px-6 py-7 sm:px-10">
      <Label>New decision</Label>
      <h1 className="mt-1.5 text-xl font-medium text-slate-100">What are you deciding?</h1>
      <p className="mt-1 text-sm text-slate-400">
        Describe the call in plain words. Zilo pulls your real numbers and argues both sides — you
        decide.
      </p>

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            onStart();
          }
        }}
        placeholder="e.g. Should I start marketing now or wait until more features are complete?"
        rows={3}
        className="mt-4 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-brand/40 focus:outline-none"
      />

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLE_PROMPTS.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => setQuestion(ex)}
            className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300 hover:border-brand/30 hover:text-slate-100"
          >
            {ex}
          </button>
        ))}
      </div>

      {showLean ? (
        <div className="mt-4">
          <label className="block text-xs font-medium text-slate-400">
            Which way are you leaning? (optional)
          </label>
          <input
            value={lean}
            onChange={(e) => setLean(e.target.value)}
            placeholder="e.g. delay"
            className="mt-2 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-brand/40 focus:outline-none"
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowLean(true)}
          className="mt-3 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
        >
          <Plus className="h-3 w-3" /> Add which way you&apos;re leaning
        </button>
      )}

      <div className="mt-5 flex items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={onStart}
          className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-black hover:bg-brand-light disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Scale className="h-4 w-4" />}
          Spar with Zilo
        </button>
        <span className="text-[11px] text-slate-600">Zilo pressure-tests it — you decide.</span>
      </div>
    </div>
  );
}

/* ── left rail ───────────────────────────────────────────────────────── */

function RailItem({
  session,
  active,
  onClick,
}: {
  session: DecisionSession;
  active: boolean;
  onClick: () => void;
}) {
  const decided = session.status === "decided";
  const review = decided ? reviewStatus(session) : null;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-lg px-3 py-2.5 text-left transition-colors",
        active
          ? "border border-brand/30 bg-brand/5"
          : "border border-transparent hover:bg-white/5"
      )}
    >
      {decided && (
        <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
          {shortDate(session.decided_at)}
        </p>
      )}
      <p className="truncate text-sm text-slate-100">{session.question}</p>
      <p className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
        {decided && review ? (
          <>
            {review.reviewed ? (
              <Check className="h-3 w-3 shrink-0 text-emerald-400" />
            ) : (
              <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
            )}
            <span className={cn(review.reviewed && "text-emerald-400")}>{review.text}</span>
          </>
        ) : (
          <>
            <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
            Day {dayNumber(session.created_at)} · {activeStatus(session)}
          </>
        )}
      </p>
    </button>
  );
}

/* ── page ────────────────────────────────────────────────────────────── */

export default function DecisionRoom() {
  const searchParams = useSearchParams();
  const sessionFromUrl = searchParams.get("session");
  const sparFromUrl = searchParams.get("spar");
  const tabFromUrl = searchParams.get("tab");
  const autoSparRef = useRef(false);

  const [sessions, setSessions] = useState<DecisionSession[]>([]);
  const [decidedSessions, setDecidedSessions] = useState<DecisionSession[]>([]);
  const [openCount, setOpenCount] = useState(0);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [lean, setLean] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [regeneratingUpdateIndex, setRegeneratingUpdateIndex] = useState<number | null>(null);
  const [regeneratingThreadIndex, setRegeneratingThreadIndex] = useState<number | null>(null);
  const [startingNew, setStartingNew] = useState(false);

  const allSessions = [
    ...sessions,
    ...decidedSessions.filter((d) => !sessions.some((s) => s.id === d.id)),
  ];
  const active = allSessions.find((s) => s.id === activeId) ?? null;
  const openSessions = sessions.filter((s) => s.status === "open");
  const pastSessions = allSessions.filter((s) => s.status === "decided");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [openRes, decidedRes] = await Promise.all([
        api.get<{ sessions: DecisionSession[]; open_count: number }>("/rex/decisions?status=open"),
        api
          .get<{ sessions: DecisionSession[] }>("/rex/decisions?status=decided")
          .catch(() => ({ sessions: [] as DecisionSession[] })),
      ]);
      let openList = openRes.sessions || [];
      let decidedList = decidedRes.sessions || [];
      setOpenCount(openRes.open_count ?? 0);

      if (sessionFromUrl && ![...openList, ...decidedList].some((s) => s.id === sessionFromUrl)) {
        try {
          const one = await api.get<DecisionSession>(`/rex/decisions/${sessionFromUrl}`);
          if (one.status === "decided") decidedList = [one, ...decidedList];
          else if (one.status === "open") openList = [one, ...openList];
        } catch {
          /* missing */
        }
      }

      setSessions(openList);
      setDecidedSessions(decidedList);
      if (sessionFromUrl) setActiveId(sessionFromUrl);
      else if (!activeId && openList.length) setActiveId(openList[0].id);
      else if (!activeId && !openList.length && !decidedList.length) setStartingNew(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load decisions");
    } finally {
      setLoading(false);
    }
  }, [activeId, sessionFromUrl]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeId) return;
    api
      .get<DecisionSession>(`/rex/decisions/${activeId}`)
      .then((s) => {
        setSessions((prev) => prev.map((x) => (x.id === s.id ? s : x)));
        setDecidedSessions((prev) => prev.map((x) => (x.id === s.id ? s : x)));
      })
      .catch(() => {});
  }, [activeId]);

  useEffect(() => {
    if (!sparFromUrl || sparFromUrl.length < 8 || autoSparRef.current || busy) return;
    autoSparRef.current = true;
    setQuestion(sparFromUrl);
    (async () => {
      setBusy(true);
      try {
        const res = await api.post<{ session: DecisionSession }>("/rex/decisions/spar", {
          question: sparFromUrl.trim(),
          founder_lean: "",
        });
        const s = res.session;
        setSessions((prev) => [s, ...prev.filter((x) => x.id !== s.id)]);
        setActiveId(s.id);
        setStartingNew(false);
        setOpenCount((c) => c + 1);
        setQuestion("");
        toast.success("Zilo sparred from Command Bar. Your call.");
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Spar failed");
      } finally {
        setBusy(false);
      }
    })();
  }, [sparFromUrl, busy]);

  const startSpar = async () => {
    if (question.trim().length < 8) {
      toast.error("Describe your decision in at least a few words.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post<{ session: DecisionSession }>("/rex/decisions/spar", {
        question: question.trim(),
        founder_lean: lean.trim(),
      });
      const s = res.session;
      setSessions((prev) => [s, ...prev.filter((x) => x.id !== s.id)]);
      setActiveId(s.id);
      setOpenCount((c) => c + 1);
      setQuestion("");
      setLean("");
      setStartingNew(false);
      toast.success("Zilo sparred. Your call.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Spar failed");
    } finally {
      setBusy(false);
    }
  };

  const sendMessage = async (text: string) => {
    if (!active) return;
    setBusy(true);
    try {
      const res = await api.post<{ session: DecisionSession; reply: string }>(
        `/rex/decisions/${active.id}/message`,
        { message: text }
      );
      const s = res.session;
      setSessions((prev) => prev.map((x) => (x.id === s.id ? s : x)));
      setDecidedSessions((prev) => prev.map((x) => (x.id === s.id ? s : x)));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Message failed");
    } finally {
      setBusy(false);
    }
  };

  const syncSession = (s: DecisionSession) => {
    setSessions((prev) => prev.map((x) => (x.id === s.id ? s : x)));
    setDecidedSessions((prev) => prev.map((x) => (x.id === s.id ? s : x)));
  };

  const addNote = async (text: string) => {
    if (!active) return;
    setBusy(true);
    try {
      const res = await api.post<{ session: DecisionSession; reaction: string }>(
        `/rex/decisions/${active.id}/note`,
        { text }
      );
      syncSession(res.session);
      toast.success("Update logged. Zilo weighed in.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't log update");
    } finally {
      setBusy(false);
    }
  };

  const updateFeedback = async (index: number, value: "up" | "down") => {
    if (!active) return;
    try {
      const res = await api.post<{ session: DecisionSession }>(
        `/rex/decisions/${active.id}/note/${index}/feedback`,
        { feedback: value }
      );
      syncSession(res.session);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save feedback");
    }
  };

  const regenerateReaction = async (index: number) => {
    if (!active || regeneratingUpdateIndex !== null) return;
    setRegeneratingUpdateIndex(index);
    try {
      const res = await api.post<{ session: DecisionSession; reaction: string }>(
        `/rex/decisions/${active.id}/note/${index}/regenerate`,
        {}
      );
      syncSession(res.session);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Couldn't regenerate";
      if (msg.toLowerCase().includes("limit")) {
        toast.error("Add more context in a new log entry.");
      } else {
        toast.error(msg);
      }
    } finally {
      setRegeneratingUpdateIndex(null);
    }
  };

  const updateThreadFeedback = async (index: number, value: "up" | "down") => {
    if (!active) return;
    try {
      const res = await api.post<{ session: DecisionSession }>(
        `/rex/decisions/${active.id}/thread/${index}/feedback`,
        { feedback: value }
      );
      syncSession(res.session);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save feedback");
    }
  };

  const regenerateThreadMessage = async (index: number) => {
    if (!active || regeneratingThreadIndex !== null) return;
    setRegeneratingThreadIndex(index);
    try {
      const res = await api.post<{ session: DecisionSession; reply: string }>(
        `/rex/decisions/${active.id}/thread/${index}/regenerate`,
        {}
      );
      syncSession(res.session);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Couldn't regenerate";
      if (msg.toLowerCase().includes("limit")) {
        toast.error("Add more context in the conversation.");
      } else {
        toast.error(msg);
      }
    } finally {
      setRegeneratingThreadIndex(null);
    }
  };

  const pushBack = async () => {
    if (!active) return;
    setBusy(true);
    try {
      const res = await api.post<{ session: DecisionSession }>("/rex/decisions/spar", {
        question: active.question,
        founder_lean: active.founder_lean,
        session_id: active.id,
        push_back_harder: true,
      });
      const s = res.session;
      setSessions((prev) => prev.map((x) => (x.id === s.id ? s : x)));
      toast.success("Pushed back harder.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Push back failed");
    } finally {
      setBusy(false);
    }
  };

  const decide = async (text: string, reviewDays: number[]) => {
    if (!active) return;
    setBusy(true);
    try {
      const res = await api.post<{ session: DecisionSession }>(
        `/rex/decisions/${active.id}/decide`,
        { decision: text, review_days: reviewDays }
      );
      const s = res.session;
      setSessions((prev) => prev.filter((x) => x.id !== s.id));
      setDecidedSessions((prev) => [s, ...prev.filter((x) => x.id !== s.id)]);
      setActiveId(s.id);
      setOpenCount((c) => Math.max(0, c - 1));
      const first = reviewDays[0] ?? 30;
      toast.success(`Decision recorded. First check-in at day ${first}.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to record");
    } finally {
      setBusy(false);
    }
  };

  const updateSchedule = async (reviewDays: number[]) => {
    if (!active) return;
    setBusy(true);
    try {
      const res = await api.post<{ session: DecisionSession }>(
        `/rex/decisions/${active.id}/schedule`,
        { review_days: reviewDays }
      );
      const s = res.session;
      setDecidedSessions((prev) => prev.map((x) => (x.id === s.id ? s : x)));
      toast.success("Review schedule updated.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't update schedule");
    } finally {
      setBusy(false);
    }
  };

  const archive = async () => {
    if (!active) return;
    setBusy(true);
    try {
      await api.post(`/rex/decisions/${active.id}/archive`, {});
      setSessions((prev) => prev.filter((x) => x.id !== active.id));
      setActiveId(sessions.find((s) => s.id !== active.id)?.id ?? null);
      setOpenCount((c) => Math.max(0, c - 1));
      toast.success("Archived.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Archive failed");
    } finally {
      setBusy(false);
    }
  };

  const newSpar = () => {
    setActiveId(null);
    setStartingNew(true);
    setQuestion("");
    setLean("");
  };

  const selectSession = (id: string) => {
    setActiveId(id);
    setStartingNew(false);
  };

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col md:flex-row">
      {/* Left rail */}
      <aside className="w-full shrink-0 border-b border-white/10 md:w-72 md:border-b-0 md:border-r">
        <div className="space-y-5 p-4">
          <div className="flex items-center gap-2 text-brand-light">
            <Scale className="h-4 w-4" />
            <span className="text-[11px] font-semibold uppercase tracking-widest">
              Decision Room
            </span>
          </div>

          <button
            type="button"
            onClick={newSpar}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-black hover:bg-brand-light"
          >
            <Plus className="h-4 w-4" />
            New spar
          </button>

          {openSessions.length > 0 && (
            <div className="space-y-1">
              <p className="px-1 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
                Active{openCount > 0 ? ` (${openCount})` : ""}
              </p>
              <div className="space-y-1">
                {openSessions.map((s) => (
                  <RailItem
                    key={s.id}
                    session={s}
                    active={s.id === activeId}
                    onClick={() => selectSession(s.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {pastSessions.length > 0 && (
            <div className="space-y-1">
              <p className="px-1 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
                Decision Log
              </p>
              <div className="space-y-1">
                {pastSessions.map((s) => (
                  <RailItem
                    key={s.id}
                    session={s}
                    active={s.id === activeId}
                    onClick={() => selectSession(s.id)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="min-w-0 flex-1">
        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
          </div>
        ) : startingNew || !active ? (
          <StartCard
            question={question}
            setQuestion={setQuestion}
            lean={lean}
            setLean={setLean}
            busy={busy}
            onStart={startSpar}
          />
        ) : (
          <DetailView
            session={active}
            onPushBack={pushBack}
            onSendMessage={sendMessage}
            onAddNote={addNote}
            onUpdateFeedback={updateFeedback}
            onRegenerateReaction={regenerateReaction}
            regeneratingUpdateIndex={regeneratingUpdateIndex}
            onThreadFeedback={updateThreadFeedback}
            onThreadRegenerate={regenerateThreadMessage}
            regeneratingThreadIndex={regeneratingThreadIndex}
            onDecide={decide}
            onUpdateSchedule={updateSchedule}
            onArchive={archive}
            busy={busy}
          />
        )}
      </main>
    </div>
  );
}
