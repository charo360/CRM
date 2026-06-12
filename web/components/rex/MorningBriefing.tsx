"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Bell, Loader2, ThumbsUp, ThumbsDown, Settings, X, Mail, MessageSquare, Globe, ShoppingCart, Calendar, Award, CheckCircle, Newspaper, Scale } from "lucide-react";
import { cn } from "@/lib/utils";

function SlackIcon({ size = 14, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
    >
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523 2.528 2.528 0 0 1-2.522-2.523 2.528 2.528 0 0 1 2.522-2.52h2.52v2.52zm1.261 0a2.528 2.528 0 0 1 2.52-2.52h5.043a2.528 2.528 0 0 1 2.522 2.52v5.042a2.528 2.528 0 0 1-2.522 2.52H8.823a2.528 2.528 0 0 1-2.52-2.52v-5.042zM8.823 5.043a2.528 2.528 0 0 1-2.52-2.522A2.528 2.528 0 0 1 8.823 0a2.528 2.528 0 0 1 2.52 2.521v2.522h-2.52zm0 1.261a2.528 2.528 0 0 1 2.52 2.52v5.043a2.528 2.528 0 0 1-2.52 2.522H3.78a2.528 2.528 0 0 1-2.52-2.522V8.824a2.528 2.528 0 0 1 2.52-2.52h5.043zm10.135 3.781a2.528 2.528 0 0 1 2.522-2.52 2.528 2.528 0 0 1 2.52 2.52 2.528 2.528 0 0 1-2.52 2.522h-2.522v-2.522zm-1.262 0a2.528 2.528 0 0 1-2.52 2.52h-5.043a2.528 2.528 0 0 1-2.522-2.52V3.78a2.528 2.528 0 0 1 2.522-2.52h5.043a2.528 2.528 0 0 1 2.52 2.52v5.043zm-3.781 10.135a2.528 2.528 0 0 1 2.52 2.522a2.528 2.528 0 0 1-2.52 2.52a2.528 2.528 0 0 1-2.522-2.52v-2.522h2.522zm0-1.262a2.528 2.528 0 0 1-2.52-2.52v-5.043a2.528 2.528 0 0 1 2.52-2.522h5.043a2.528 2.528 0 0 1 2.522 2.522v5.043a2.528 2.528 0 0 1-2.522 2.52h-5.043z" />
    </svg>
  );
}

function CategoryIcon({ cat, size = 14, className }: { cat: string; size?: number; className?: string }) {
  if (cat === "competitor") return <Globe size={size} className={cn("text-blue-400 animate-pulse", className)} />;
  if (cat === "replies") return <Mail size={size} className={cn("text-brand-light", className)} />;
  if (cat === "slack") return <SlackIcon size={size} className={cn("text-pink-400", className)} />;
  if (cat === "calendar") return <Calendar size={size} className={cn("text-amber-400", className)} />;
  if (cat === "storefront" || cat === "orders" || cat === "inventory") {
    return <ShoppingCart size={size} className={cn("text-emerald-400", className)} />;
  }
  if (cat === "news") return <Newspaper size={size} className={cn("text-sky-400", className)} />;
  if (cat === "strategy") return <Scale size={size} className={cn("text-violet-400", className)} />;
  return <MessageSquare size={size} className={cn("text-slate-400", className)} />;
}


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
  decision_session_id?: string;
  decision_href?: string;
  source_url?: string | null;
  is_informational?: boolean;
  feedback?: "like" | "dislike" | null;
  proposed_at?: string;
};

function getDayBucket(isoString?: string): "today" | "yesterday" {
  if (!isoString) return "today";
  try {
    const d = new Date(isoString);
    const now = new Date();
    
    const dDate = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const nowDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    
    const diffTime = nowDate.getTime() - dDate.getTime();
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays <= 0) return "today";
    return "yesterday";
  } catch {
    return "today";
  }
}

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
  if (action.action_mode_type === "decision_outcome") {
    return "View outcome";
  }
  if (action.action_mode_type === "decision_room") {
    return "Open Decision Room";
  }
  if (action.review_only || action.action_mode_type === "send_email") {
    return "Send it";
  }
  if (action.action_mode_type === "post_comment") {
    return "Send it";
  }
  return "Send it";
}

function decisionRoomHref(action: LetterAction): string {
  if (action.decision_href) return action.decision_href;
  if (action.decision_session_id) {
    const tab = action.action_mode_type === "decision_outcome" ? "&tab=outcomes" : "";
    return `/dashboard/rex/decisions?session=${action.decision_session_id}${tab}`;
  }
  return "/dashboard/rex/decisions";
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
  if (cat === "competitor") return "COMPETITOR ANALYSIS";
  if (cat === "replies") return "EMAIL REPLIES";
  if (cat === "slack") return "SLACK";
  if (cat === "calendar") return "CALENDAR";
  if (cat === "storefront") return "SHOPIFY STOREFRONT";
  if (cat === "orders") return "SHOPIFY ORDERS";
  if (cat === "inventory") return "SHOPIFY INVENTORY";
  if (cat === "news") return "NEWS & INDUSTRY UPDATES";
  if (cat === "strategy") return "DECISION ROOM";
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
  const [quickFilter, setQuickFilter] = useState<string>("all");
  const [workplanBriefing, setWorkplanBriefing] = useState<any>(null);

  const [showPreferencesModal, setShowPreferencesModal] = useState(false);
  const [preferences, setPreferences] = useState<{ name: string; display: string; tier: number; enabled: boolean }[]>([]);
  const [prefLoading, setPrefLoading] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);

  const [leadScoutInterval, setLeadScoutInterval] = useState<string>("24h");
  const [openScoutInterval, setOpenScoutInterval] = useState<string>("12h");
  const [fbGroupInterval, setFbGroupInterval] = useState<string>("6h");

  const fetchPrefs = useCallback(async () => {
    setPrefLoading(true);
    try {
      const data = await api.get<{
        categories: typeof preferences;
        lead_scout_interval?: string;
        open_scout_interval?: string;
        fb_group_interval?: string;
      }>("/rex/briefing/preferences");
      setPreferences(data.categories);
      setLeadScoutInterval(data.lead_scout_interval || "24h");
      setOpenScoutInterval(data.open_scout_interval || "12h");
      setFbGroupInterval(data.fb_group_interval || "6h");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setPrefLoading(false);
    }
  }, []);

  function toggleCategoryLocal(name: string) {
    setPreferences((prev) =>
      prev.map((cat) => (cat.name === name ? { ...cat, enabled: !cat.enabled } : cat))
    );
  }

  function enableAllLocal() {
    setPreferences((prev) => prev.map((cat) => ({ ...cat, enabled: true })));
  }

  function disableAllLocal() {
    setPreferences((prev) => prev.map((cat) => ({ ...cat, enabled: false })));
  }

  async function savePrefs() {
    setSavingPrefs(true);
    try {
      const enabled_categories = preferences.filter((cat) => cat.enabled).map((cat) => cat.name);
      const res = await api.post<{ home: ZiloHome }>("/rex/briefing/preferences", {
        enabled_categories,
        lead_scout_interval: leadScoutInterval,
        open_scout_interval: openScoutInterval,
        fb_group_interval: fbGroupInterval,
      });
      const next = normalizeHome(res.home);
      setHome(next);
      onStagedCountRef.current?.(next.counts.staged);
      toast.success("Briefing preferences saved successfully.");
      setShowPreferencesModal(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSavingPrefs(false);
    }
  }

  const TIER_LABELS: Record<number, string> = {
    1: "Core Operations",
    2: "Operations & Quotes",
    3: "Growth & Marketing",
    4: "Customer Acquisition",
    5: "Customer Relationships",
    6: "Pipeline Management",
    7: "Commerce & Inventory",
    8: "Team & Analytics"
  };

  const onStagedCountRef = useRef(onStagedCount);
  useEffect(() => {
    onStagedCountRef.current = onStagedCount;
  }, [onStagedCount]);

  const syncCrm = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.post<{ home: ZiloHome }>("/rex/sync", {});
      const data = normalizeHome(res.home);
      setHome(data);
      onStagedCountRef.current?.(data.counts.staged);
      toast.success("Synced from your CRM.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "CRM sync failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      // No ?live=1 — backend SWR returns the cached briefing instantly and
      // refreshes in the background. Next poll picks up the fresh state.
      const data = normalizeHome(await api.get<ZiloHome>("/rex/home"));
      setHome(data);
      onStagedCountRef.current?.(data.counts.staged);

      // Fetch workplan briefing data
      try {
        const wpData = await api.get<any>("/rex/workplan/briefing");
        setWorkplanBriefing(wpData);
      } catch (wpErr) {
        console.warn("Failed to load workplan briefing", wpErr);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not load briefing";
      if (msg.includes("404")) {
        toast.error("Restart the backend on port 8000 — missing /api/rex/home.");
      } else if (/fetch|network|failed to fetch|ECONNREFUSED/i.test(msg)) {
        toast.error("Backend not reachable. Start uvicorn on port 8000.");
      } else {
        toast.error(msg);
      }
      onStagedCountRef.current?.(0);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void load({ silent: true });
    }, 45_000);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    const count = home ? home.counts.staged : 0;
    window.dispatchEvent(new CustomEvent("zilo-staged-count-change", { detail: count }));
  }, [home]);

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

  async function setFeedback(actionId: string, value: "like" | "dislike") {
    if (value === "dislike") {
      setHome((prev) => {
        if (!prev) return null;
        const actions = prev.letter.actions.filter((a) => a.action_id !== actionId);
        return {
          ...prev,
          letter: {
            ...prev.letter,
            actions,
          },
          counts: {
            ...prev.counts,
            staged: Math.max(0, prev.counts.staged - 1),
          },
        };
      });
    } else {
      setHome((prev) => {
        if (!prev) return null;
        const actions = prev.letter.actions.map((a) =>
          a.action_id === actionId ? { ...a, feedback: value } : a
        );
        return {
          ...prev,
          letter: {
            ...prev.letter,
            actions,
          },
        };
      });
    }

    try {
      const res = await api.post<{ home: ZiloHome }>(
        `/rex/actions/${actionId}/${value}`,
        {}
      );
      const next = normalizeHome(res.home);
      setHome(next);
      onStagedCountRef.current?.(next.counts.staged);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Feedback failed");
      void load({ silent: true });
    }
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
      onStagedCountRef.current?.(next.counts.staged);
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
              onClick={() => {
                setShowPreferencesModal(true);
                void fetchPrefs();
              }}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/5 flex items-center gap-1.5"
            >
              <Settings size={13} />
              Briefing Settings
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
              <div className="relative overflow-hidden rounded-xl border border-brand/20 bg-gradient-to-br from-[#0a2818] to-[#04140c] p-6 shadow-xl shadow-brand/5 backdrop-blur-md">
                <div className="absolute -top-12 -right-12 h-24 w-24 rounded-full bg-brand/10 blur-xl pointer-events-none" />
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-brand/20 text-base font-bold text-brand border border-brand/30 shadow-inner animate-in fade-in zoom-in duration-300">
                      Z
                      <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-brand"></span>
                      </span>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-base font-semibold tracking-tight text-white">Zilo</p>
                        <span className="rounded-full bg-brand/15 px-2.5 py-0.5 text-[9px] font-mono font-bold tracking-wider text-brand border border-brand/20 shadow-inner">
                          AI CHIEF OF STAFF
                        </span>
                      </div>
                      <p className="text-xs text-slate-400/80">
                        <span className="font-mono text-amber-400 font-medium">{home.zilo_rank.toUpperCase()}</span>
                        {" · "}
                        <span className="font-mono">DAY {home.relationship_day}</span>
                        {" · "}
                        Today · {formatBriefingTime(home.generated_at)}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="border-l-2 border-brand/40 pl-3.5">
                  <LinkifiedText text={openerLine} className="text-sm leading-relaxed text-slate-200" />
                </div>
              </div>

              {workplanBriefing && (workplanBriefing.due_today?.length > 0 || workplanBriefing.completed_overnight?.length > 0 || workplanBriefing.coming_up?.length > 0) && (
                <div className="relative overflow-hidden rounded-xl border border-brand/20 bg-gradient-to-br from-[#07150e]/60 via-[#040e0a]/80 to-[#020604]/95 p-5 shadow-lg shadow-black/10 transition hover:border-brand/40 duration-300">
                  <div className="flex items-center justify-between border-b border-white/5 pb-2.5 mb-3">
                    <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-brand-light">
                      YOUR PLAN TODAY
                    </span>
                    <Link href="/dashboard/workplan" className="text-xs text-brand hover:text-brand-light hover:underline transition">
                      View full work plan →
                    </Link>
                  </div>
                  
                  <div className="space-y-4 text-xs text-slate-300">
                    {workplanBriefing.due_today?.length > 0 && (
                      <div>
                        <p className="text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1.5 tracking-wider">Due Today:</p>
                        <ul className="space-y-1.5">
                          {workplanBriefing.due_today.map((task: any) => (
                            <li key={task.id} className="flex justify-between items-center pl-2 border-l border-amber-500/40 py-0.5">
                              <span className="text-slate-200 font-medium">{task.title}</span>
                              <span className="text-[9px] rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-400 font-mono">You</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {workplanBriefing.completed_overnight?.length > 0 && (
                      <div>
                        <p className="text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1.5 tracking-wider">Zilo Completed Overnight:</p>
                        <ul className="space-y-1.5">
                          {workplanBriefing.completed_overnight.map((task: any) => (
                            <li key={task.id} className="flex justify-between items-center pl-2 border-l border-emerald-500/40 py-0.5">
                              <span className="text-slate-200 font-medium">{task.title}</span>
                              <span className="text-[9px] text-emerald-400 font-mono font-medium">{task.result ? `→ ${task.result}` : "Complete"}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {workplanBriefing.coming_up?.length > 0 && (
                      <div>
                        <p className="text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1.5 tracking-wider">Coming Up:</p>
                        <ul className="space-y-1.5">
                          {workplanBriefing.coming_up.map((task: any) => (
                            <li key={task.id} className="flex justify-between items-center pl-2 border-l border-slate-500/40 py-0.5">
                              <span className="text-slate-200 font-medium">{task.title}</span>
                              <span className="text-[9px] text-slate-400 italic">{task.context || "Upcoming"}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* On-Screen Interactive Quick Filters */}
              {staged.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 pb-1 bg-black/10 p-2 rounded-xl border border-white/5 shadow-inner">
                  {[
                    { id: "all", label: "All Items", count: staged.length },
                    {
                      id: "email",
                      label: "Email Replies",
                      count: staged.filter(a => a.category === "replies" || a.channel === "email").length
                    },
                    {
                      id: "slack",
                      label: "Slack",
                      count: staged.filter(a => a.category === "slack").length
                    },
                    {
                      id: "calendar",
                      label: "Calendar",
                      count: staged.filter(a => a.category === "calendar").length
                    },
                    {
                      id: "competitor",
                      label: "Competitor Analysis",
                      count: staged.filter(a => a.category === "competitor").length
                    },
                    {
                      id: "shopify",
                      label: "Shopify Store",
                      count: staged.filter(a => ["storefront", "orders", "inventory"].includes(a.category)).length
                    },
                    {
                      id: "news",
                      label: "News",
                      count: staged.filter(a => a.category === "news").length
                    }
                  ].map((pill) => {
                    // Only show filter badge if count > 0 or it's 'all'
                    if (pill.count === 0 && pill.id !== "all") return null;
                    const isActive = quickFilter === pill.id;
                    return (
                      <button
                        key={pill.id}
                        type="button"
                        onClick={() => setQuickFilter(pill.id)}
                        className={cn(
                          "flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold tracking-wide border transition-all duration-200 cursor-pointer select-none",
                          isActive
                            ? "bg-brand/15 border-brand/40 text-brand-light shadow-md shadow-brand/5"
                            : "bg-black/30 border-white/5 text-slate-400 hover:border-white/15 hover:bg-white/5 hover:text-slate-200"
                        )}
                      >
                        <span>{pill.label}</span>
                        <span className={cn(
                          "flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[9px] font-bold transition-colors",
                          isActive ? "bg-brand/20 text-brand-light" : "bg-white/5 text-slate-500"
                        )}>
                          {pill.count}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {staged.length > 0 ? (
                (() => {
                  const filteredStaged = staged.filter((action) => {
                    if (quickFilter === "all") return true;
                    if (quickFilter === "email") return action.category === "replies" || action.channel === "email";
                    if (quickFilter === "slack") return action.category === "slack";
                    if (quickFilter === "calendar") return action.category === "calendar";
                    if (quickFilter === "competitor") return action.category === "competitor";
                    if (quickFilter === "shopify") return ["storefront", "orders", "inventory"].includes(action.category);
                    if (quickFilter === "news") return action.category === "news";
                    return true;
                  });

                  if (filteredStaged.length === 0) {
                    return (
                      <div className="py-12 text-center border border-dashed border-white/10 rounded-xl bg-black/10">
                        <p className="text-sm text-slate-400">
                          No items matching the "{quickFilter.toUpperCase()}" filter.
                        </p>
                      </div>
                    );
                  }

                  const todayActions = filteredStaged.filter(a => getDayBucket(a.proposed_at) === "today");
                  const yesterdayActions = filteredStaged.filter(a => getDayBucket(a.proposed_at) === "yesterday");

                  return (
                    <div className="space-y-6">
                      {/* Today Section */}
                      {todayActions.length > 0 && (
                        <div className="space-y-4">
                          <div className="flex items-center gap-2 px-1 py-1">
                            <span className="flex h-2 w-2 rounded-full bg-brand animate-pulse" />
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-brand-light">
                              Today's Feed ({todayActions.length})
                            </h3>
                            <div className="flex-1 h-px bg-brand/10 ml-2" />
                          </div>
                          <div className="space-y-4">
                            {todayActions.map((action, idx) => (
                              <BriefingActionCard
                                key={action.action_id}
                                action={action}
                                index={idx}
                                dayBucket="today"
                                draftOpen={draftOpen.has(action.action_id)}
                                busy={busyId === action.action_id}
                                draft={draftFor(action)}
                                onDraftOpen={() => toggleDraftOpen(action.action_id)}
                                onDraftChange={(text) => setDraft(action.action_id, text)}
                                onApprove={() => void verb(action.action_id, "approve", action)}
                                onDismiss={() => void verb(action.action_id, "dismiss")}
                                onLike={() => void setFeedback(action.action_id, "like")}
                                onDislike={() => void setFeedback(action.action_id, "dislike")}
                              />
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Yesterday Section */}
                      {yesterdayActions.length > 0 && (
                        <div className="space-y-4">
                          <div className="flex items-center gap-2 px-1 py-1 mt-6">
                            <span className="flex h-2 w-2 rounded-full bg-slate-500" />
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                              Yesterday & Older ({yesterdayActions.length})
                            </h3>
                            <div className="flex-1 h-px bg-white/5 ml-2" />
                          </div>
                          <div className="space-y-4">
                            {yesterdayActions.map((action, idx) => (
                              <BriefingActionCard
                                key={action.action_id}
                                action={action}
                                index={todayActions.length + idx}
                                dayBucket="yesterday"
                                draftOpen={draftOpen.has(action.action_id)}
                                busy={busyId === action.action_id}
                                draft={draftFor(action)}
                                onDraftOpen={() => toggleDraftOpen(action.action_id)}
                                onDraftChange={(text) => setDraft(action.action_id, text)}
                                onApprove={() => void verb(action.action_id, "approve", action)}
                                onDismiss={() => void verb(action.action_id, "dismiss")}
                                onLike={() => void setFeedback(action.action_id, "like")}
                                onDislike={() => void setFeedback(action.action_id, "dislike")}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()
              ) : (
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

      {/* Preferences Modal */}
      {showPreferencesModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="bg-[#071a10] border border-white/10 rounded-xl max-w-lg w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            
            {/* Header */}
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4 shrink-0">
              <div>
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Settings size={18} className="text-brand" />
                  Briefing Settings
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Select which categories Zilo should include in your briefing feed.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowPreferencesModal(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-white/5 hover:text-slate-100 transition"
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            </div>

            {/* Global toggles bar */}
            <div className="flex items-center justify-end gap-3 px-5 py-2.5 bg-black/20 border-b border-white/5 shrink-0">
              <button
                type="button"
                onClick={enableAllLocal}
                className="text-[11px] font-semibold uppercase tracking-wider text-brand hover:text-brand-light transition"
              >
                Switch On All
              </button>
              <span className="text-slate-600 text-xs">|</span>
              <button
                type="button"
                onClick={disableAllLocal}
                className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200 transition"
              >
                Switch Off All
              </button>
            </div>

            {/* Scrollable category list */}
            <div className="flex-1 overflow-y-auto p-5 space-y-6 min-h-0">
              {prefLoading ? (
                <div className="flex h-40 items-center justify-center text-slate-400">
                  <Loader2 className="h-6 w-6 animate-spin text-brand" />
                </div>
              ) : (
                <>
                  {/* Category toggles */}
                  <div className="space-y-5">
                    {Object.entries(
                      preferences.reduce<Record<number, typeof preferences>>((acc, cat) => {
                        acc[cat.tier] = acc[cat.tier] || [];
                        acc[cat.tier].push(cat);
                        return acc;
                      }, {})
                    ).map(([tierStr, cats]) => {
                      const tier = parseInt(tierStr, 10);
                      const label = TIER_LABELS[tier] || `Tier ${tier} Operations`;
                      return (
                        <div key={tier} className="space-y-2">
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 border-b border-white/5 pb-1">
                            {label}
                          </h3>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {cats.map((cat) => (
                              <label
                                key={cat.name}
                                className={cn(
                                  "flex items-center justify-between p-2.5 rounded-lg border text-sm font-medium transition cursor-pointer select-none",
                                  cat.enabled
                                    ? "bg-brand/10 border-brand/35 text-slate-200 hover:bg-brand/15"
                                    : "bg-black/20 border-white/5 text-slate-400 hover:bg-white/5 hover:text-slate-300"
                                )}
                              >
                                <span>{categoryLabel(cat.name)}</span>
                                <input
                                  type="checkbox"
                                  checked={cat.enabled}
                                  onChange={() => toggleCategoryLocal(cat.name)}
                                  className="sr-only"
                                />
                                {/* Custom switch element */}
                                <div
                                  className={cn(
                                    "relative w-9 h-5 rounded-full transition-colors duration-200",
                                    cat.enabled ? "bg-brand" : "bg-slate-700"
                                  )}
                                >
                                  <div
                                    className={cn(
                                      "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform duration-200",
                                      cat.enabled ? "translate-x-4" : "translate-x-0"
                                    )}
                                  />
                                </div>
                              </label>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* AI & Paid Search Schedulers Section */}
                  <div className="space-y-4 pt-5 border-t border-white/10">
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 pb-1">
                        AI & Opportunity Search Frequencies
                      </h3>
                      <p className="text-[11px] text-slate-500 leading-relaxed">
                        Control how often Zilo performs cost-intensive background scans for your business. Higher frequencies consume more credits.
                      </p>
                    </div>
                    
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {/* Zilo Open Scouts */}
                      <div className="bg-black/30 border border-white/5 rounded-xl p-3.5 flex flex-col justify-between space-y-3">
                        <div>
                          <label className="text-xs font-semibold text-slate-200">Web Scouts</label>
                          <p className="text-[10px] text-slate-400 mt-1 leading-normal">
                            Crawls forums & webs for custom buy-intent queries.
                          </p>
                        </div>
                        <select
                          value={openScoutInterval}
                          onChange={(e) => setOpenScoutInterval(e.target.value)}
                          className="w-full bg-[#05140c] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-brand transition"
                        >
                          <option value="1h">Every 1 Hour</option>
                          <option value="2h">Every 2 Hours</option>
                          <option value="6h">Every 6 Hours</option>
                          <option value="12h">Every 12 Hours</option>
                          <option value="24h">Every 24 Hours</option>
                          <option value="weekly">Weekly</option>
                        </select>
                      </div>

                      {/* Lead Finder */}
                      <div className="bg-black/30 border border-white/5 rounded-xl p-3.5 flex flex-col justify-between space-y-3">
                        <div>
                          <label className="text-xs font-semibold text-slate-200">Lead Finder</label>
                          <p className="text-[10px] text-slate-400 mt-1 leading-normal">
                            Monitors keyword leads and extracts domain contacts.
                          </p>
                        </div>
                        <select
                          value={leadScoutInterval}
                          onChange={(e) => setLeadScoutInterval(e.target.value)}
                          className="w-full bg-[#05140c] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-brand transition"
                        >
                          <option value="1h">Every 1 Hour</option>
                          <option value="2h">Every 2 Hours</option>
                          <option value="6h">Every 6 Hours</option>
                          <option value="12h">Every 12 Hours</option>
                          <option value="24h">Every 24 Hours</option>
                          <option value="weekly">Weekly</option>
                          <option value="manual">Manual Only</option>
                        </select>
                      </div>

                      {/* Facebook Scraper */}
                      <div className="bg-black/30 border border-white/5 rounded-xl p-3.5 flex flex-col justify-between space-y-3">
                        <div>
                          <label className="text-xs font-semibold text-slate-200">Social Scrapers</label>
                          <p className="text-[10px] text-slate-400 mt-1 leading-normal">
                            Scrapes target Facebook groups for key buying signals.
                          </p>
                        </div>
                        <select
                          value={fbGroupInterval}
                          onChange={(e) => setFbGroupInterval(e.target.value)}
                          className="w-full bg-[#05140c] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-brand transition"
                        >
                          <option value="1h">Every 1 Hour</option>
                          <option value="2h">Every 2 Hours</option>
                          <option value="6h">Every 6 Hours</option>
                          <option value="12h">Every 12 Hours</option>
                          <option value="24h">Every 24 Hours</option>
                          <option value="weekly">Weekly</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-white/10 px-5 py-4 flex items-center justify-end gap-3 shrink-0">
              <button
                type="button"
                disabled={savingPrefs}
                onClick={() => setShowPreferencesModal(false)}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-white/5 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={savingPrefs || prefLoading}
                onClick={savePrefs}
                className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-ink transition hover:bg-brand-light disabled:opacity-50 flex items-center gap-1.5"
              >
                {savingPrefs && <Loader2 size={14} className="animate-spin" />}
                {savingPrefs ? "Saving..." : "Save Settings"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function BriefingActionCard({
  action,
  index,
  dayBucket = "today",
  draftOpen,
  busy,
  draft,
  onDraftOpen,
  onDraftChange,
  onApprove,
  onDismiss,
  onLike,
  onDislike,
}: {
  action: LetterAction;
  index: number;
  dayBucket?: "today" | "yesterday";
  draftOpen: boolean;
  busy: boolean;
  draft: string;
  onDraftOpen: () => void;
  onDraftChange: (text: string) => void;
  onApprove: () => void;
  onDismiss: () => void;
  onLike: () => void;
  onDislike: () => void;
}) {
  const hasDraft = Boolean(action.draft_preview || draft);
  const category =
    action.channel === "email"
      ? "EMAIL"
      : action.channel === "whatsapp"
        ? "MESSAGES"
        : categoryLabel(action.category);

  const sourceUrl = action.source_url?.trim();
  const isTodayCard = dayBucket === "today";

  return (
    <article className={cn(
      "group relative overflow-hidden rounded-xl border transition-all duration-300 backdrop-blur-md p-5",
      isTodayCard
        ? "border-brand/20 bg-gradient-to-br from-[#0c2418]/75 via-[#071910]/85 to-[#030906]/95 shadow-lg shadow-black/10 hover:border-brand/45 hover:translate-y-[-2px] hover:shadow-brand/5 hover:shadow-xl"
        : "border-white/5 bg-gradient-to-br from-[#07150e]/60 via-[#040e0a]/80 to-[#020604]/95 opacity-85 hover:opacity-100 hover:border-white/15 hover:translate-y-[-1px] shadow-none"
    )}>
      {/* Category header tag */}
      <div className="flex items-center justify-between border-b border-white/5 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-6 items-center justify-center rounded-full bg-white/5 px-2.5 py-0.5 border border-white/10">
            <CategoryIcon cat={action.category} className={!isTodayCard ? "opacity-60" : ""} />
            <span className={cn(
              "ml-1.5 font-mono text-[9px] font-semibold tracking-wider",
              isTodayCard ? "text-slate-300" : "text-slate-500"
            )}>
              {category}
            </span>
          </div>
          {isTodayCard ? (
            <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[8px] font-mono font-bold tracking-wider text-brand border border-brand/20">
              TODAY
            </span>
          ) : (
            <span className="rounded-full bg-white/5 px-2 py-0.5 text-[8px] font-mono font-semibold tracking-wider text-slate-500 border border-white/5">
              YESTERDAY
            </span>
          )}
          {action.review_only && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[8px] font-mono font-semibold tracking-wider text-amber-400 border border-amber-500/20">
              REVIEW REQUIRED
            </span>
          )}
          {action.channel && (
            <span className="rounded-full bg-white/5 px-2 py-0.5 text-[8px] font-mono text-slate-400 border border-white/5">
              {channelLabel(action.channel).toUpperCase()}
            </span>
          )}
        </div>
        <span className="font-mono text-[10px] text-slate-500">
          {String(index + 1).padStart(2, "0")}
        </span>
      </div>

      <h2 className="mt-3 text-lg font-bold leading-snug text-white group-hover:text-brand-light/95 transition-colors duration-200">{action.summary}</h2>
      <LinkifiedText text={action.reasoning} className="mt-2.5 text-sm leading-relaxed text-slate-300" />
      
      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-brand hover:text-brand-light transition duration-200"
        >
          View source →
        </a>
      )}

      {action.memory_line && (
        <div className="mt-4 rounded-lg border-l-2 border-brand/50 bg-[#0c2818]/40 px-3.5 py-3 shadow-inner">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-brand-light/90 flex items-center gap-1">
            <Award size={10} className="text-brand-light" />
            Zilo Context Memory
          </p>
          <LinkifiedText
            text={action.memory_line}
            className="mt-1 font-mono text-xs leading-relaxed text-slate-300/90"
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

      {/* Confidence progress bar */}
      <div className="mt-5 border-t border-white/5 pt-4">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
          <span className="flex items-center gap-1.5">
            AI Confidence Score
          </span>
          <span className={cn(
            "font-bold",
            action.confidence_pct >= 90 ? "text-brand" : action.confidence_pct >= 70 ? "text-amber-400" : "text-slate-400"
          )}>
            {action.confidence_pct}%
          </span>
        </div>
        <div className="mt-1.5 h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500",
              action.confidence_pct >= 90 ? "bg-gradient-to-r from-brand/70 to-brand" : action.confidence_pct >= 70 ? "bg-amber-400" : "bg-slate-500"
            )}
            style={{ width: `${action.confidence_pct}%` }}
          />
        </div>
      </div>

      {/* Action buttons */}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        {action.action_mode_type === "decision_room" || action.action_mode_type === "decision_outcome" ? (
          <>
            <Link
              href={decisionRoomHref(action)}
              className="rounded-lg bg-brand px-4 py-2 text-xs font-bold text-brand-ink transition hover:bg-brand-light hover:scale-102 active:scale-98 shadow-md shadow-brand/10 flex items-center gap-1.5 cursor-pointer"
            >
              {action.action_mode_type === "decision_outcome" ? "View outcome" : "Open Decision Room"}
            </Link>
            <button
              type="button"
              disabled={busy}
              onClick={onDismiss}
              className="rounded-lg px-3 py-2 text-xs text-slate-500 transition hover:text-slate-300 hover:bg-white/5 cursor-pointer"
            >
              Not now
            </button>
          </>
        ) : action.is_informational ? (
          <button
            type="button"
            disabled={busy}
            onClick={onDismiss}
            className="rounded-lg bg-brand px-4 py-2 text-xs font-bold text-brand-ink transition hover:bg-brand-light hover:scale-102 active:scale-98 disabled:opacity-50 flex items-center gap-1.5 shadow-md shadow-brand/10 cursor-pointer"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
            Mark read
          </button>
        ) : (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={onApprove}
              className="rounded-lg bg-brand px-4 py-2 text-xs font-bold text-brand-ink transition hover:bg-brand-light hover:scale-102 active:scale-98 disabled:opacity-50 shadow-md shadow-brand/10 flex items-center gap-1.5 cursor-pointer"
            >
              {busy && <Loader2 size={13} className="animate-spin" />}
              {primaryActionLabel(action)}
            </button>
            {hasDraft && (
              <button
                type="button"
                disabled={busy}
                onClick={onDraftOpen}
                className={cn(
                  "rounded-lg border px-4 py-2 text-xs font-semibold transition hover:scale-102 active:scale-98 cursor-pointer",
                  draftOpen 
                    ? "bg-amber-500/10 border-amber-500/40 text-amber-200"
                    : "border-white/15 text-slate-200 hover:bg-white/5 hover:border-white/25"
                )}
              >
                {draftOpen ? "Hide draft" : "Read draft first"}
              </button>
            )}
            <Link
              href={action.channel === "whatsapp" ? "/dashboard/messages" : "/dashboard/email"}
              className="rounded-lg border border-white/15 px-4 py-2 text-xs font-semibold text-brand-light transition hover:bg-white/5 hover:border-white/25 hover:text-white hover:scale-102 active:scale-98 cursor-pointer"
            >
              Open inbox
            </Link>
            <button
              type="button"
              disabled={busy}
              onClick={onDismiss}
              className="rounded-lg px-3 py-2 text-xs text-slate-500 transition hover:text-slate-300 hover:bg-white/5 cursor-pointer"
            >
              Not now
            </button>
          </>
        )}

        {/* Feedback buttons */}
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            disabled={busy}
            onClick={onLike}
            className={cn(
              "rounded-lg p-2 transition-all duration-200 hover:scale-105 active:scale-95 cursor-pointer border",
              action.feedback === "like"
                ? "bg-brand/20 text-brand border-brand/30"
                : "text-slate-400 hover:bg-white/5 hover:text-slate-200 border-transparent"
            )}
            title="Like"
          >
            <ThumbsUp size={14} className={action.feedback === "like" ? "fill-current animate-bounce" : ""} />
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onDislike}
            className={cn(
              "rounded-lg p-2 transition-all duration-200 hover:scale-105 active:scale-95 cursor-pointer border",
              action.feedback === "dislike"
                ? "bg-red-500/20 text-red-400 border-red-500/30"
                : "text-slate-400 hover:bg-white/5 hover:text-red-400 border-transparent"
            )}
            title="Dislike"
          >
            <ThumbsDown size={14} className={action.feedback === "dislike" ? "fill-current" : ""} />
          </button>
        </div>
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
