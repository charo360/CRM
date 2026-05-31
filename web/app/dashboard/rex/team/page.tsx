"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getAgentPersona, personaBadgeLabel } from "@/lib/agentPersonas";
import {
  Loader2,
  MessageSquare,
  ExternalLink,
  Radar,
  Users,
  Bot,
  TrendingUp,
  TrendingDown,
  Award,
  ChevronDown,
  ChevronUp,
  Moon,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

/* ─── Types ─────────────────────────────────────────────────────────────── */

type Deputy = {
  id: string;
  name: string;
  label: string;
  team: string;
  description: string;
  categories: string[];
  rank: string;
  on_probation: boolean;
  chat_agent_id: string | null;
};

type ChatAgent = { id: string; label: string; description: string };

type Standing = {
  category: string;
  display: string;
  tier: number;
  rank: string;
  rank_value: number;
  on_probation: boolean;
};

type StandingsPayload = {
  standings: Standing[];
  ranks: string[];
  max_rank_value: number;
};

type TeamPayload = {
  chief: {
    name: string;
    label: string;
    description: string;
    chat_agent_id: string;
    standing?: { rank: string; on_probation: boolean };
  };
  operations: Deputy[];
  customer_service: Deputy[];
  action_mode: { id: string; label: string; description: string; href: string }[];
  chat_groups: { id: string; label: string; agents: ChatAgent[] }[];
  chat_total: number;
};

/* ─── Helpers ────────────────────────────────────────────────────────────── */

const RANK_TONE: Record<string, string> = {
  Observer:       "bg-slate-100 text-slate-600 border-slate-200",
  Drafter:        "bg-blue-50 text-blue-700 border-blue-200",
  Sender:         "bg-emerald-50 text-emerald-700 border-emerald-200",
  Operator:       "bg-violet-50 text-violet-700 border-violet-200",
  "Chief of Staff":"bg-amber-50 text-amber-800 border-amber-200",
};

const TIER_LABEL: Record<number, string> = {
  1: "Core", 2: "Operations", 3: "Growth", 4: "Acquisition",
  5: "Customer", 6: "Pipeline", 7: "Commerce", 8: "Team ops",
};

function chatUrl(agentId: string, prompt?: string) {
  const q = new URLSearchParams();
  if (prompt) q.set("template_message", prompt);
  const s = q.toString();
  return `/dashboard/assistant${s ? `?${s}` : ""}`;
}

/* Deduplicate specialists — keep one entry per unique label, merge dual roles */
function deduplicateAgents(agents: ChatAgent[]): ChatAgent[] {
  const seen = new Map<string, ChatAgent>();
  for (const a of agents) {
    const key = a.label.toLowerCase().replace(/\s+/g, "-");
    if (!seen.has(key)) {
      seen.set(key, a);
    }
  }
  return Array.from(seen.values());
}

/* ─── Specialist Card ────────────────────────────────────────────────────── */

function SpecialistCard({
  id,
  label,
  description,
  rank,
  onProbation,
  chatAgentId,
  href,
  compact = false,
}: {
  id: string;
  label: string;
  description: string;
  rank?: string;
  onProbation?: boolean;
  chatAgentId?: string | null;
  href?: string;
  compact?: boolean;
}) {
  const persona = chatAgentId ? getAgentPersona(chatAgentId) : null;
  const openChat = chatAgentId
    ? chatUrl(chatAgentId, `I want to work with the ${label} specialist.`)
    : href || null;

  return (
    <div
      className={cn(
        "group rounded-xl border border-slate-200 bg-white transition-all hover:border-brand/40 hover:shadow-sm",
        compact ? "p-3" : "p-4"
      )}
    >
      <div className="flex items-start gap-3">
        {persona && (
          <div
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
              persona.cls
            )}
          >
            {persona.firstName[0]}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold text-slate-900">{label}</span>
            {persona && (
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                  persona.cls
                )}
              >
                {persona.firstName}
              </span>
            )}
            {rank && rank !== "—" && (
              <span
                className={cn(
                  "inline-block rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
                  RANK_TONE[rank] ?? "bg-slate-100 text-slate-600 border-slate-200"
                )}
              >
                {rank}
                {onProbation ? " · probation" : ""}
              </span>
            )}
          </div>
          <p className={cn("mt-1.5 text-xs leading-relaxed text-slate-500", compact ? "line-clamp-2" : "line-clamp-3")}>
            {description}
          </p>
          {openChat && (
            <Link
              href={openChat}
              className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-brand-dark hover:text-brand"
            >
              <MessageSquare className="h-3 w-3" />
              Open in Zilo Chat
            </Link>
          )}
          {!openChat && href && (
            <Link
              href={href}
              className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-brand-dark hover:text-brand"
            >
              <ExternalLink className="h-3 w-3" />
              Open
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Overnight Operations Card ─────────────────────────────────────────── */

function OvernightCard({
  label,
  description,
  chatAgentId,
  href,
}: {
  label: string;
  description: string;
  chatAgentId?: string | null;
  href?: string;
}) {
  const openChat = chatAgentId
    ? chatUrl(chatAgentId, `I want to work with ${label}.`)
    : href || null;

  return (
    <div className="rounded-xl border border-[#1a3a28] bg-[#0d2818] p-4 transition hover:border-brand/40">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-brand animate-pulse" />
        <span className="text-sm font-semibold text-white">{label}</span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-400">{description}</p>
      {openChat && (
        <Link
          href={openChat}
          className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-brand-light hover:text-brand"
        >
          <ExternalLink className="h-3 w-3" />
          View in Action Mode
        </Link>
      )}
    </div>
  );
}

/* ─── Collapsible Group ─────────────────────────────────────────────────── */

function CollapsibleGroup({
  title,
  subtitle,
  icon: Icon,
  count,
  defaultOpen = false,
  children,
}: {
  title: string;
  subtitle: string;
  icon: React.ElementType;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="mt-6 rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left transition hover:bg-slate-50"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100">
            <Icon className="h-4 w-4 text-slate-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                {count}
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500">{subtitle}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!open && (
            <span className="hidden text-[11px] text-slate-400 sm:block">
              Click to expand
            </span>
          )}
          {open ? (
            <ChevronUp className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          )}
        </div>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-5 pb-5 pt-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
        </div>
      )}
    </div>
  );
}

/* ─── Trust Ladder ───────────────────────────────────────────────────────── */

function TrustLadder({
  data,
  onChange,
  busyCategory,
  promote,
  demote,
}: {
  data: StandingsPayload;
  onChange: () => void;
  busyCategory: string | null;
  promote: (category: string, reason?: string) => Promise<void>;
  demote: (category: string, reason?: string) => Promise<void>;
}) {
  const [showAll, setShowAll] = useState(false);
  const [demoteFor, setDemoteFor] = useState<string | null>(null);
  const [demoteReason, setDemoteReason] = useState("");

  const sorted = [...data.standings].sort((a, b) => {
    if (b.rank_value !== a.rank_value) return b.rank_value - a.rank_value;
    return a.tier - b.tier;
  });

  const visible = showAll
    ? sorted
    : sorted.filter((s) => s.rank_value > 0 || s.tier === 1);

  const handleDemoteConfirm = async (category: string) => {
    await demote(category, demoteReason.trim() || undefined);
    setDemoteFor(null);
    setDemoteReason("");
    onChange();
  };

  return (
    <div className="mt-6 rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <div className="border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-50">
            <Award className="h-4 w-4 text-amber-600" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Trust ladder</h2>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Zilo earns trust one lane at a time. Promote when the work proves out.
            </p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {data.ranks.map((r, i) => (
            <span key={r} className="flex items-center gap-1.5">
              <span
                className={cn(
                  "inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                  RANK_TONE[r] ?? "bg-slate-100 text-slate-600 border-slate-200"
                )}
              >
                {r}
              </span>
              {i < data.ranks.length - 1 && (
                <span className="text-slate-300 text-xs">›</span>
              )}
            </span>
          ))}
        </div>
      </div>

      <ul className="divide-y divide-slate-100">
        {visible.map((s) => {
          const tone = RANK_TONE[s.rank] ?? "bg-slate-100 text-slate-600 border-slate-200";
          const atTop = s.rank_value >= data.max_rank_value;
          const atBottom = s.rank_value <= 0;
          const isBusy = busyCategory === s.category;
          const isDemoting = demoteFor === s.category;

          return (
            <li
              key={s.category}
              className="flex flex-wrap items-center justify-between gap-3 px-5 py-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-slate-900">{s.display}</p>
                  <span className="text-[10px] uppercase tracking-wider text-slate-400">
                    {TIER_LABEL[s.tier] ?? `Tier ${s.tier}`}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <span
                    className={cn(
                      "inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                      tone
                    )}
                  >
                    {s.rank}
                  </span>
                  {s.on_probation && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                      probation
                    </span>
                  )}
                </div>
              </div>

              {isDemoting ? (
                <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
                  <input
                    type="text"
                    value={demoteReason}
                    onChange={(e) => setDemoteReason(e.target.value)}
                    placeholder="Why? (optional)"
                    className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs focus:border-brand focus:outline-none"
                    autoFocus
                  />
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleDemoteConfirm(s.category)}
                      className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-50"
                    >
                      Confirm demote
                    </button>
                    <button
                      type="button"
                      onClick={() => { setDemoteFor(null); setDemoteReason(""); }}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    disabled={atBottom || isBusy}
                    onClick={() => { setDemoteFor(s.category); setDemoteReason(""); }}
                    title={atBottom ? "Already Observer" : `Demote on ${s.display}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <TrendingDown size={13} />
                    Demote
                  </button>
                  <button
                    type="button"
                    disabled={atTop || isBusy}
                    onClick={async () => { await promote(s.category); onChange(); }}
                    title={atTop ? "Already Chief of Staff" : `Promote on ${s.display}`}
                    className="inline-flex items-center gap-1 rounded-lg bg-brand px-2.5 py-1.5 text-xs font-semibold text-brand-ink hover:bg-brand-light disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {isBusy ? <Loader2 size={13} className="animate-spin" /> : <TrendingUp size={13} />}
                    Promote
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <div className="border-t border-slate-100 px-5 py-3">
        {sorted.length > visible.length && !showAll && (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="text-xs font-medium text-brand-dark hover:underline"
          >
            Show all {sorted.length} categories →
          </button>
        )}
        {showAll && (
          <button
            type="button"
            onClick={() => setShowAll(false)}
            className="text-xs font-medium text-slate-500 hover:underline"
          >
            Hide unearned categories
          </button>
        )}
      </div>
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────── */

export default function ZiloTeamPage() {
  const [data, setData] = useState<TeamPayload | null>(null);
  const [standings, setStandings] = useState<StandingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyCategory, setBusyCategory] = useState<string | null>(null);
  const [rankError, setRankError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [team, st] = await Promise.all([
        api.get<TeamPayload>("/rex/team"),
        api.get<StandingsPayload>("/rex/standings").catch(() => null),
      ]);
      setData(team);
      setStandings(st);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load team");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshStandings = useCallback(async () => {
    try {
      setStandings(await api.get<StandingsPayload>("/rex/standings"));
    } catch { /* keep previous */ }
  }, []);

  const promote = useCallback(async (category: string, reason?: string) => {
    setBusyCategory(category);
    setRankError(null);
    try {
      await api.post("/rex/promote", { category, reason });
    } catch (e) {
      setRankError(e instanceof Error ? e.message : "Promotion failed");
    } finally {
      setBusyCategory(null);
    }
  }, []);

  const demote = useCallback(async (category: string, reason?: string) => {
    setBusyCategory(category);
    setRankError(null);
    try {
      await api.post("/rex/demote", { category, reason });
    } catch (e) {
      setRankError(e instanceof Error ? e.message : "Demotion failed");
    } finally {
      setBusyCategory(null);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-lg px-6 py-12 text-center">
        <p className="text-sm text-red-600">{error || "Team unavailable"}</p>
        <button
          type="button"
          onClick={() => load()}
          className="mt-4 text-sm font-medium text-brand-dark hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  // Deduplicate all chat agents across all groups
  const allChatAgents = deduplicateAgents(
    data.chat_groups.flatMap((g) => g.agents)
  );
  const overnightCount = data.operations.length;
  const customerFacingCount = data.customer_service.length;

  return (
    <div className="mx-auto max-w-5xl px-6 py-8 pb-20">

      {/* ── Page Header ─────────────────────────────────────── */}
      <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-dark/60">
        Zilo
      </p>
      <h1 className="mt-1 text-2xl font-semibold text-slate-900">Zilo&apos;s team</h1>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-600">
        These are the people Zilo works with on your behalf.
        <br />
        You never manage them directly. Tell Zilo what you need — Zilo decides who handles it.
      </p>

      {/* Counts — plain language */}
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <Bot className="h-3.5 w-3.5 text-brand-dark" />
          <strong className="text-slate-700">{allChatAgents.length}</strong> specialists ready when you need them
        </span>
        <span className="flex items-center gap-1.5">
          <Moon className="h-3.5 w-3.5 text-indigo-500" />
          <strong className="text-slate-700">{overnightCount}</strong> overnight agents always running
        </span>
        <span className="flex items-center gap-1.5">
          <Users className="h-3.5 w-3.5 text-emerald-600" />
          <strong className="text-slate-700">{customerFacingCount}</strong> customer-facing agents on standby
        </span>
      </div>

      {/* ── Zilo — Chief of Staff ────────────────────────────── */}
      <div className="mt-8 rounded-2xl border border-brand/25 bg-gradient-to-br from-[#071a10] to-[#0d2818] p-6 text-white">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-light/70">
              Chief of Staff · always on
            </p>
            <h2 className="mt-1 text-xl font-semibold">{data.chief.label}</h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-300">
              {data.chief.description}
            </p>
            {data.chief.standing && (
              <span
                className={cn(
                  "mt-3 inline-block rounded-full border px-2.5 py-1 text-[11px] font-semibold",
                  RANK_TONE[data.chief.standing.rank] ?? "bg-slate-100 text-slate-700 border-slate-300"
                )}
              >
                {data.chief.standing.rank}
                {data.chief.standing.on_probation ? " · probation" : ""}
              </span>
            )}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Link
              href="/dashboard"
              className="rounded-lg bg-brand px-4 py-2 text-center text-sm font-semibold text-brand-ink hover:bg-brand-light"
            >
              Zilo Briefing
            </Link>
            <Link
              href={chatUrl("general")}
              className="rounded-lg border border-white/20 px-4 py-2 text-center text-sm font-medium text-slate-200 hover:bg-white/5"
            >
              Zilo Chat
            </Link>
          </div>
        </div>
      </div>

      {/* Connector line */}
      <div className="mt-0 flex justify-center">
        <div className="flex flex-col items-center">
          <div className="h-6 w-px bg-slate-200" />
          <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
            coordinates
          </span>
          <div className="h-6 w-px bg-slate-200" />
        </div>
      </div>

      {rankError && (
        <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {rankError}
        </p>
      )}

      {/* ── GROUP 1: Overnight Operations — always visible ───── */}
      <div className="rounded-2xl border border-[#1a3a28] bg-[#071a10] overflow-hidden">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-[#1a3a28]">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand/20">
            <Moon className="h-4 w-4 text-brand-light" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-white">Overnight Operations</h2>
              <span className="rounded-full bg-brand/20 px-2 py-0.5 text-[10px] font-semibold text-brand-light">
                {overnightCount}
              </span>
              <span className="flex items-center gap-1 rounded-full bg-brand/20 px-2 py-0.5 text-[10px] font-semibold text-brand-light">
                <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
                running now
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-slate-400">
              These run while you sleep. Every morning their findings appear in your Zilo Briefing — already drafted, ready for your approval. You never manage them directly.
            </p>
          </div>
        </div>
        <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
          {data.operations.map((d) => (
            <OvernightCard
              key={d.id}
              label={d.label}
              description={d.description}
              chatAgentId={d.chat_agent_id}
              href={d.name === "Scout" ? "/dashboard/action-mode" : undefined}
            />
          ))}
        </div>
      </div>

      {/* ── GROUP 2: Chat Specialists — collapsed by default ─── */}
      <CollapsibleGroup
        title="Chat Specialists"
        subtitle="Call on these when you need something specific done now. Tell Zilo which one, or let Zilo route automatically."
        icon={Bot}
        count={allChatAgents.length}
        defaultOpen={false}
      >
        {allChatAgents.map((a) => (
          <SpecialistCard
            key={a.id}
            id={a.id}
            label={a.label}
            description={a.description}
            chatAgentId={a.id}
            compact
          />
        ))}
      </CollapsibleGroup>

      {/* ── GROUP 3: Customer-Facing — collapsed by default ─── */}
      <CollapsibleGroup
        title="Customer-Facing Agents"
        subtitle="These talk to your customers on your behalf — sales conversations, orders, support, and payments."
        icon={Users}
        count={customerFacingCount}
        defaultOpen={false}
      >
        {data.customer_service.map((d) => (
          <SpecialistCard
            key={d.id}
            id={d.id}
            label={d.label}
            description={d.description}
            rank={d.rank}
            onProbation={d.on_probation}
            chatAgentId={d.chat_agent_id}
          />
        ))}
      </CollapsibleGroup>

      {/* ── GROUP 4: Action Mode Runners ─────────────────────── */}
      <div className="mt-6 rounded-2xl border border-violet-200 bg-violet-50 overflow-hidden">
        <div className="flex items-center gap-3 border-b border-violet-100 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-violet-100">
            <Zap className="h-4 w-4 text-violet-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-violet-900">Action Mode Runners</h2>
              <span className="rounded-full bg-violet-200 px-2 py-0.5 text-[10px] font-semibold text-violet-700">
                {data.action_mode.length}
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-violet-600">
              These run overnight without being asked. Every morning their findings appear in your Zilo Briefing — already drafted, ready for your approval. You never manage them directly. Zilo deploys them automatically.
            </p>
          </div>
        </div>
        <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
          {data.action_mode.map((a) => (
            <div
              key={a.id}
              className="rounded-xl border border-violet-200 bg-white p-4 transition hover:border-violet-400"
            >
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-violet-400" />
                <span className="text-sm font-semibold text-slate-900">{a.label}</span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-slate-500">{a.description}</p>
              {a.href && (
                <Link
                  href={a.href}
                  className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-violet-700 hover:text-violet-900"
                >
                  <ExternalLink className="h-3 w-3" />
                  View queue
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Trust Ladder ─────────────────────────────────────── */}
      {standings && (
        <TrustLadder
          data={standings}
          onChange={refreshStandings}
          busyCategory={busyCategory}
          promote={promote}
          demote={demote}
        />
      )}

      <Link
        href="/dashboard"
        className="mt-10 inline-block text-sm font-medium text-brand-dark hover:underline"
      >
        ← Back to Zilo Briefing
      </Link>
    </div>
  );
}
