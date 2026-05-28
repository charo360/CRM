"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Bell, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type LetterAction = {
  action_id: string;
  summary: string;
  confidence_pct: number;
  category: string;
  kind: string;
  reasoning: string;
  memory_line: string | null;
  target_subject: string | null;
  draft_preview?: string;
  channel?: string;
  review_only?: boolean;
  action_mode_type?: string;
  source_url?: string | null;
};

const URL_IN_TEXT = /https?:\/\/[^\s<>"']+/gi;

function trimUrlTrailingPunctuation(url: string) {
  return url.replace(/[.,;:!?)]+$/g, "");
}

function linkifyText(text: string, linkClass: string): ReactNode {
  if (!text) return null;
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(URL_IN_TEXT)) {
    const raw = match[0];
    const href = trimUrlTrailingPunctuation(raw);
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    nodes.push(
      <a
        key={`url-${key++}`}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={linkClass}
        onClick={(e) => e.stopPropagation()}
      >
        {href}
      </a>
    );
    last = index + raw.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length ? nodes : text;
}

function LinkifiedText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <p className={cn("whitespace-pre-wrap", className)}>
      {linkifyText(text, "text-brand underline-offset-2 hover:underline break-all")}
    </p>
  );
}

function channelLabel(ch?: string) {
  const m: Record<string, string> = {
    email: "Email draft",
    whatsapp: "WhatsApp",
    social: "Social",
    crm: "CRM",
  };
  return m[ch || ""] || "";
}

function primaryActionLabel(action: LetterAction) {
  if (action.review_only || action.action_mode_type === "send_email") {
    return "Send it";
  }
  if (action.action_mode_type === "post_comment") {
    return "Send it";
  }
  return "Send it";
}

type OvernightItem = {
  action_id: string;
  summary: string;
  state: string;
  tone: "done" | "pending" | "flag";
};

/** API payload (supports legacy rex_* field names from older backends). */
export type ZiloHome = {
  letter: {
    opener: string;
    body: string;
    quiet_night: boolean;
    actions: LetterAction[];
  };
  counts: {
    staged: number;
    top_count?: number;
    activity_total?: number;
    overnight_total: number;  // legacy alias
  };
  activity?: OvernightItem[];
  overnight: OvernightItem[];  // legacy alias
  zilo_rank?: string;
  rex_rank?: string;
  relationship_day: number;
  generated_at: string;
  metrics: {
    revenue_today: string;
    revenue_delta: string;
    followups_due: number;
    followups_zilo?: number;
    followups_rex?: number;
    open_deals: number;
    deals_at_risk: number;
  };
};

type ZiloHomeNormalized = ZiloHome & {
  zilo_rank: string;
  metrics: ZiloHome["metrics"] & { followups_zilo: number };
};

/** @deprecated Use ZiloHome */
export type RexHome = ZiloHome;

function normalizeHome(raw: ZiloHome): ZiloHomeNormalized {
  return {
    ...raw,
    zilo_rank: raw.zilo_rank ?? raw.rex_rank ?? "Observer",
    metrics: {
      ...raw.metrics,
      followups_zilo: raw.metrics.followups_zilo ?? raw.metrics.followups_rex ?? 0,
    },
  };
}

type MorningBriefingProps = {
  /** Lets the CRM sidebar show the staged-action badge. */
  onStagedCount?: (count: number) => void;
};

function categoryLabel(cat: string) {
  return cat.replace(/_/g, " ").toUpperCase();
}

function formatBriefingDate(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "Today";
  }
}

function formatBriefingTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase();
  } catch {
    return "7:00am";
  }
}

export default function MorningBriefing({ onStagedCount }: MorningBriefingProps) {
  const [home, setHome] = useState<ZiloHomeNormalized | null>(null);
  const [loading, setLoading] = useState(true);
  const [rawMode, setRawMode] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [draftOpen, setDraftOpen] = useState<Set<string>>(new Set());
  const [draftEdits, setDraftEdits] = useState<Record<string, string>>({});

  const syncCrm = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.post<{ home: ZiloHome }>("/rex/sync", {});
      const data = normalizeHome(res.home);
      setHome(data);
      onStagedCount?.(data.counts.staged);
      toast.success("Synced from your CRM.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "CRM sync failed");
    } finally {
      setLoading(false);
    }
  }, [onStagedCount]);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      // No ?live=1 — backend SWR returns the cached briefing instantly and
      // refreshes in the background. Next poll picks up the fresh state.
      const data = normalizeHome(await api.get<ZiloHome>("/rex/home"));
      setHome(data);
      onStagedCount?.(data.counts.staged);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not load briefing";
      if (msg.includes("404")) {
        toast.error("Restart the backend on port 8000 — missing /api/rex/home.");
      } else if (/fetch|network|failed to fetch|ECONNREFUSED/i.test(msg)) {
        toast.error("Backend not reachable. Start uvicorn on port 8000.");
      } else {
        toast.error(msg);
      }
      onStagedCount?.(0);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, [onStagedCount]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void load({ silent: true });
    }, 45_000);
    return () => window.clearInterval(id);
  }, [load]);

  function toggleDraftOpen(actionId: string) {
    setDraftOpen((prev) => {
      const next = new Set(prev);
      if (next.has(actionId)) next.delete(actionId);
      else next.add(actionId);
      return next;
    });
  }

  function draftFor(action: LetterAction) {
    if (draftEdits[action.action_id] !== undefined) {
      return draftEdits[action.action_id];
    }
    return action.draft_preview ?? "";
  }

  function setDraft(actionId: string, text: string) {
    setDraftEdits((prev) => ({ ...prev, [actionId]: text }));
  }

  async function verb(
    actionId: string,
    path: "approve" | "dismiss" | "reject",
    action?: LetterAction
  ) {
    setBusyId(actionId);
    const body: { draft_body?: string } = {};
    if (path === "approve" && action) {
      const draft = draftFor(action).trim();
      if (draft) body.draft_body = draft;
    }
    try {
      const res = await api.post<{ home: ZiloHome }>(
        `/rex/actions/${actionId}/${path}`,
        body
      );
      const next = normalizeHome(res.home);
      setHome(next);
      onStagedCount?.(next.counts.staged);
      setDraftOpen((prev) => {
        const n = new Set(prev);
        n.delete(actionId);
        return n;
      });
      setDraftEdits((prev) => {
        const n = { ...prev };
        delete n[actionId];
        return n;
      });
      if (path === "approve") {
        toast.success(
          action?.review_only ? "Marked reviewed — send when you're ready." : "Sent."
        );
      } else if (path === "dismiss") toast.info("Dismissed for now.");
      else toast.info("Rejected.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  if (loading && !home) {
    return (
      <div className="flex min-h-[60vh] flex-1 items-center justify-center text-slate-400">
        <Loader2 className="h-6 w-6 animate-spin text-brand" />
      </div>
    );
  }

  if (!home) {
    return (
      <div className="flex min-h-[60vh] flex-1 flex-col items-center justify-center gap-3 px-8 text-center text-slate-400">
        <p>Briefing unavailable.</p>
        <p className="max-w-md text-sm text-slate-500">
          Start the API on port <span className="font-mono text-brand">8000</span>, then refresh.
        </p>
      </div>
    );
  }

  const staged = home.letter.actions;
  const openerLine =
    home.letter.quiet_night
      ? home.letter.body.split("\n")[0]
      : staged.length > 0
        ? `${staged.length} thing${staged.length === 1 ? "" : "s"} need you. Everything else is handled.`
        : home.letter.opener;

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden">
      {/* Center briefing feed — this column scrolls */}
      <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-white/10 px-5 py-3 lg:px-8">
          <div>
            <p className="text-xs text-slate-500">
              {formatBriefingDate(home.generated_at)} · {formatBriefingTime(home.generated_at)}
            </p>
            <h1 className="mt-0.5 text-xl font-semibold tracking-tight text-white">Zilo Briefing</h1>
            <p className="mt-1 max-w-lg text-xs text-slate-500">
              Everything that needs you today.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void syncCrm()}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/5"
            >
              Sync CRM
            </button>
            <button
              type="button"
              onClick={() => void load({ silent: false })}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/5"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={() => setRawMode(false)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                !rawMode ? "bg-brand text-brand-ink" : "text-slate-400 hover:text-slate-200"
              )}
            >
              Zilo&apos;s version
            </button>
            <button
              type="button"
              onClick={() => setRawMode(true)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                rawMode ? "bg-white/10 text-slate-100" : "text-slate-400 hover:text-slate-200"
              )}
            >
              Raw data
            </button>
            <button
              type="button"
              className="rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-slate-200"
              aria-label="Notifications"
            >
              <Bell size={18} />
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 lg:px-8">
          {rawMode ? (
            <pre className="whitespace-pre-wrap rounded-xl border border-white/10 bg-black/30 p-6 font-mono text-xs leading-relaxed text-slate-300">
              {home.letter.body}
            </pre>
          ) : (
            <div className="mx-auto w-full max-w-3xl space-y-5 pb-6">
              <div className="rounded-xl border border-white/10 bg-[#0a1f14]/80 p-5">
                <div className="mb-3 flex flex-wrap items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand/20 text-sm font-bold text-brand">
                    Z
                  </div>
                  <div>
                    <p className="text-base font-semibold text-white">Zilo</p>
                    <p className="text-xs text-slate-500">
                      <span className="font-mono text-amber-400">{home.zilo_rank.toUpperCase()}</span>
                      {" · "}
                      <span className="font-mono">DAY {home.relationship_day}</span>
                      {" · "}
                      Today · {formatBriefingTime(home.generated_at)}
                    </p>
                  </div>
                </div>
                <LinkifiedText text={openerLine} className="text-sm leading-relaxed text-slate-300" />
              </div>

              {staged.map((action, idx) => (
                <BriefingActionCard
                  key={action.action_id}
                  action={action}
                  index={idx}
                  draftOpen={draftOpen.has(action.action_id)}
                  busy={busyId === action.action_id}
                  draft={draftFor(action)}
                  onDraftOpen={() => toggleDraftOpen(action.action_id)}
                  onDraftChange={(text) => setDraft(action.action_id, text)}
                  onApprove={() => void verb(action.action_id, "approve", action)}
                  onDismiss={() => void verb(action.action_id, "dismiss")}
                />
              ))}

              {staged.length === 0 && (
                <p className="py-12 text-center text-sm text-slate-500">
                  Nothing needs you right now. Recent activity is in the log.
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Right rail — fixed; only overnight list scrolls inside */}
      <aside className="hidden h-full w-64 shrink-0 flex-col overflow-hidden border-l border-white/10 bg-[#071a10] xl:flex xl:w-72">
        <div className="grid grid-cols-2 gap-2.5 p-3">
          {isZeroRevenue(home.metrics.revenue_today) ? (
            <ConnectCard
              label="Today's revenue"
              prompt="Connect Stripe so Zilo can watch your revenue."
            />
          ) : (
            <MetricCard label="Today's revenue" value={home.metrics.revenue_today} sub={home.metrics.revenue_delta} subTone="up" />
          )}
          <MetricCard
            label="Follow-ups due"
            value={String(home.metrics.followups_due)}
            sub={`Zilo handling ${home.metrics.followups_zilo}`}
            subTone="warn"
          />
          {home.metrics.open_deals === 0 ? (
            <ConnectCard
              label="Open deals"
              prompt="Add a deal so Zilo can track your pipeline."
            />
          ) : (
            <MetricCard
              label="Open deals"
              value={String(home.metrics.open_deals)}
              sub={`${home.metrics.deals_at_risk} at risk`}
              subTone="risk"
            />
          )}
          <MetricCard
            label="Recent activity"
            value={String(home.counts.activity_total ?? home.counts.overnight_total)}
            sub="Live"
            subTone="up"
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Recent activity
          </h3>
          <ul className="mt-3 space-y-2">
            {(home.activity ?? home.overnight).map((item) => (
              <li key={item.action_id} className="flex gap-2 text-xs text-slate-400">
                <span
                  className={cn(
                    "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                    item.tone === "done" && "bg-brand",
                    item.tone === "pending" && "bg-amber-400",
                    item.tone === "flag" && "bg-slate-500"
                  )}
                />
                <span className="leading-snug">
                  {linkifyText(
                    item.summary,
                    "text-brand underline-offset-2 hover:underline break-all"
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="border-t border-white/10 p-4">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Zilo&apos;s rank</p>
          <p className="mt-2 inline-block rounded-md bg-amber-400/20 px-2 py-1 font-mono text-sm font-semibold text-amber-300">
            {home.zilo_rank.toUpperCase()}
          </p>
        </div>
      </aside>
    </div>
  );
}

function BriefingActionCard({
  action,
  index,
  draftOpen,
  busy,
  draft,
  onDraftOpen,
  onDraftChange,
  onApprove,
  onDismiss,
}: {
  action: LetterAction;
  index: number;
  draftOpen: boolean;
  busy: boolean;
  draft: string;
  onDraftOpen: () => void;
  onDraftChange: (text: string) => void;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  const hasDraft = Boolean(action.draft_preview || draft);
  const category =
    action.channel === "email"
      ? "EMAIL"
      : action.channel === "whatsapp"
        ? "MESSAGES"
        : categoryLabel(action.category);

  const sourceUrl = action.source_url?.trim();

  return (
    <article className="rounded-xl border border-white/10 bg-[#0a1f14]/60 p-5">
      <p className="font-mono text-[10px] tracking-widest text-brand-light/60">
        {String(index + 1).padStart(2, "0")} / {category}
        {action.channel && action.channel !== "email" ? ` · ${channelLabel(action.channel)}` : ""}
        {action.review_only ? " · review before send" : ""}
      </p>
      <h2 className="mt-2 text-base font-semibold leading-snug text-white">{action.summary}</h2>
      <LinkifiedText text={action.reasoning} className="mt-3 text-sm leading-relaxed text-slate-400" />
      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex text-sm font-medium text-brand underline-offset-2 hover:underline"
        >
          View source →
        </a>
      )}
      {action.memory_line && (
        <div className="mt-4 rounded-lg border border-brand/20 bg-brand/5 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-brand-light/80">
            Memory
          </p>
          <LinkifiedText
            text={action.memory_line}
            className="mt-1.5 font-mono text-xs leading-relaxed text-slate-300"
          />
        </div>
      )}
      {hasDraft && !draftOpen && (
        <LinkifiedText
          text={draft || action.draft_preview || ""}
          className="mt-3 line-clamp-3 text-sm leading-relaxed text-slate-500"
        />
      )}
      {hasDraft && draftOpen && (
        <div className="mt-4">
          <label
            htmlFor={`draft-${action.action_id}`}
            className="text-[10px] font-semibold uppercase tracking-wide text-amber-200/80"
          >
            Draft — edit before sending
          </label>
          <textarea
            id={`draft-${action.action_id}`}
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            rows={6}
            className="mt-1.5 w-full resize-y rounded-lg border border-amber-500/25 bg-black/30 px-3 py-2.5 text-sm leading-relaxed text-slate-200 focus:border-brand/50 focus:outline-none focus:ring-1 focus:ring-brand/30"
          />
        </div>
      )}
      <p className="mt-3 font-mono text-[11px] text-slate-500">Confidence {action.confidence_pct}%.</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onApprove}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-ink transition hover:bg-brand-light disabled:opacity-50"
        >
          {busy ? "…" : primaryActionLabel(action)}
        </button>
        {hasDraft && (
          <button
            type="button"
            disabled={busy}
            onClick={onDraftOpen}
            className="rounded-lg border border-white/20 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-white/5"
          >
            {draftOpen ? "Hide draft" : "Read it first"}
          </button>
        )}
        <Link
          href={action.channel === "whatsapp" ? "/dashboard/messages" : "/dashboard/email"}
          className="rounded-lg border border-white/20 px-4 py-2 text-sm font-medium text-brand-light transition hover:bg-white/5 hover:text-white"
        >
          Open inbox
        </Link>
        <button
          type="button"
          disabled={busy}
          onClick={onDismiss}
          className="rounded-lg px-3 py-2 text-sm text-slate-500 transition hover:text-slate-300"
        >
          Not now
        </button>
      </div>
    </article>
  );
}

function MetricCard({
  label,
  value,
  sub,
  subTone,
}: {
  label: string;
  value: string;
  sub: string;
  subTone: "up" | "warn" | "risk";
}) {
  const subClass =
    subTone === "up" ? "text-brand" : subTone === "risk" ? "text-red-400" : "text-amber-400";
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-2.5">
      <p className="text-[10px] text-slate-500">{label}</p>
      <p className="mt-0.5 text-base font-semibold text-white">{value}</p>
      <p className={cn("mt-0.5 text-[10px] font-medium", subClass)}>{sub}</p>
    </div>
  );
}

function ConnectCard({ label, prompt }: { label: string; prompt: string }) {
  return (
    <div className="rounded-lg border border-dashed border-white/15 bg-black/10 p-2.5">
      <p className="text-[10px] text-slate-500">{label}</p>
      <p className="mt-1 text-[11px] leading-snug text-slate-300">{prompt}</p>
    </div>
  );
}

function isZeroRevenue(value: string | undefined): boolean {
  if (!value) return true;
  // "USD 0.00", "$0", "KES 0", "0.00" — any string whose numeric tokens are all 0.
  const nums = value.match(/\d+(\.\d+)?/g);
  if (!nums) return true;
  return nums.every((n) => parseFloat(n) === 0);
}
