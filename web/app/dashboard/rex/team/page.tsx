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
} from "lucide-react";
import { cn } from "@/lib/utils";

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

const TIER_LABEL: Record<number, string> = {
  1: "Core",
  2: "Operations",
  3: "Growth",
  4: "Acquisition",
  5: "Customer",
  6: "Pipeline",
  7: "Commerce",
  8: "Team ops",
};

const RANK_TONE: Record<string, string> = {
  Observer: "bg-slate-100 text-slate-700 border-slate-200",
  Drafter: "bg-blue-50 text-blue-700 border-blue-200",
  Sender: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Operator: "bg-violet-50 text-violet-700 border-violet-200",
  "Chief of Staff": "bg-amber-50 text-amber-800 border-amber-200",
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

function chatUrl(agentId: string, prompt?: string) {
  const q = new URLSearchParams();
  if (prompt) q.set("template_message", prompt);
  const s = q.toString();
  return `/dashboard/assistant${s ? `?${s}` : ""}`;
}

function AgentCard({
  id,
  label,
  description,
  rank,
  onProbation,
  chatAgentId,
  href,
}: {
  id: string;
  label: string;
  description: string;
  rank?: string;
  onProbation?: boolean;
  chatAgentId?: string | null;
  href?: string;
}) {
  const persona = chatAgentId ? getAgentPersona(chatAgentId) : null;
  const openChat = chatAgentId
    ? chatUrl(chatAgentId, `I want to work with the ${label} specialist.`)
    : href || null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-brand/30">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">{label}</span>
            {persona && (
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold",
                  persona.cls
                )}
              >
                {persona.firstName} · {personaBadgeLabel(chatAgentId!)}
              </span>
            )}
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-600 line-clamp-3">{description}</p>
          {rank && rank !== "—" && (
            <p className="mt-2 text-[10px] font-medium uppercase tracking-wide text-slate-500">
              Rank: {rank}
              {onProbation ? " · probation" : ""}
            </p>
          )}
        </div>
      </div>
      {openChat && (
        <Link
          href={openChat}
          className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-brand-dark hover:text-brand"
        >
          <MessageSquare className="h-3.5 w-3.5" />
          Open in Zilo Chat
        </Link>
      )}
      {!openChat && href && (
        <Link
          href={href}
          className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-brand-dark hover:text-brand"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open
        </Link>
      )}
    </div>
  );
}

function Section({
  title,
  subtitle,
  icon: Icon,
  children,
}: {
  title: string;
  subtitle?: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-10">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-brand-dark" />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-800">{title}</h2>
      </div>
      {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </section>
  );
}

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

  // By default show only categories Zilo has actually earned a rank on, plus Tier 1.
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
    <section className="mt-10">
      <div className="flex items-center gap-2">
        <Award className="h-4 w-4 text-brand-dark" />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-800">
          Trust ladder
        </h2>
      </div>
      <p className="mt-1 max-w-2xl text-xs text-slate-500">
        Zilo earns a rank per category. Promote him when his work proves out; demote him when
        the trust has to be re-earned. Each change is recorded in the Journal in his voice.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        <span>Ladder:</span>
        {data.ranks.map((r, i) => (
          <span key={r} className="flex items-center gap-1.5">
            <span
              className={cn(
                "inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                RANK_TONE[r] ?? "bg-slate-100 text-slate-700 border-slate-200"
              )}
            >
              {r}
            </span>
            {i < data.ranks.length - 1 && <span className="text-slate-300">›</span>}
          </span>
        ))}
      </div>

      <ul className="mt-4 divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
        {visible.map((s) => {
          const tone = RANK_TONE[s.rank] ?? "bg-slate-100 text-slate-700 border-slate-200";
          const atTop = s.rank_value >= data.max_rank_value;
          const atBottom = s.rank_value <= 0;
          const isBusy = busyCategory === s.category;
          const isDemoting = demoteFor === s.category;

          return (
            <li key={s.category} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-slate-900">{s.display}</p>
                  <span className="text-[10px] uppercase tracking-wider text-slate-400">
                    {TIER_LABEL[s.tier] ?? `Tier ${s.tier}`}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-2">
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
                      onClick={() => {
                        setDemoteFor(null);
                        setDemoteReason("");
                      }}
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
                    onClick={() => {
                      setDemoteFor(s.category);
                      setDemoteReason("");
                    }}
                    title={atBottom ? "Already Observer" : `Demote on ${s.display}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <TrendingDown size={13} />
                    Demote
                  </button>
                  <button
                    type="button"
                    disabled={atTop || isBusy}
                    onClick={async () => {
                      await promote(s.category);
                      onChange();
                    }}
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

      {sorted.length > visible.length && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-3 text-xs font-medium text-brand-dark hover:underline"
        >
          Show all {sorted.length} categories →
        </button>
      )}
      {showAll && (
        <button
          type="button"
          onClick={() => setShowAll(false)}
          className="mt-3 text-xs font-medium text-slate-500 hover:underline"
        >
          Hide unearned categories
        </button>
      )}
    </section>
  );
}

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
    } catch {
      // keep previous standings
    }
  }, []);

  const promote = useCallback(
    async (category: string, reason?: string) => {
      setBusyCategory(category);
      setRankError(null);
      try {
        await api.post("/rex/promote", { category, reason });
      } catch (e) {
        setRankError(e instanceof Error ? e.message : "Promotion failed");
      } finally {
        setBusyCategory(null);
      }
    },
    []
  );

  const demote = useCallback(
    async (category: string, reason?: string) => {
      setBusyCategory(category);
      setRankError(null);
      try {
        await api.post("/rex/demote", { category, reason });
      } catch (e) {
        setRankError(e instanceof Error ? e.message : "Demotion failed");
      } finally {
        setBusyCategory(null);
      }
    },
    []
  );

  useEffect(() => {
    load();
  }, [load]);

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

  return (
    <div className="mx-auto max-w-5xl px-6 py-8 pb-16">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-dark/60">Zilo</p>
      <h1 className="mt-1 text-2xl font-semibold text-slate-900">Zilo&apos;s team</h1>
      <p className="mt-2 max-w-2xl text-sm text-slate-600">
        Every AI specialist in your CRM — the same agents Zilo Chat routes to, plus overnight
        scouts and deputies. Zilo coordinates; you talk to specialists when you need depth.
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {data.chat_total} chat specialists · {data.operations.length + data.customer_service.length}{" "}
        deputies · {data.action_mode.length} Action Mode runners
      </p>

      <div className="mt-8 rounded-2xl border border-brand/25 bg-gradient-to-br from-[#071a10] to-[#0d2818] p-6 text-white">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-light/70">
              Chief of Staff
            </p>
            <h2 className="mt-1 text-xl font-semibold">{data.chief.label}</h2>
            <p className="mt-2 max-w-xl text-sm text-slate-300">{data.chief.description}</p>
            {data.chief.standing && (
              <p className="mt-3 text-xs text-brand-light">
                Current rank (outreach): {data.chief.standing.rank}
                {data.chief.standing.on_probation ? " · on probation" : ""}
              </p>
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

      {rankError && (
        <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {rankError}
        </p>
      )}

      {standings && (
        <TrustLadder
          data={standings}
          onChange={refreshStandings}
          busyCategory={busyCategory}
          promote={promote}
          demote={demote}
        />
      )}

      <Section
        title="Zilo Chat specialists"
        subtitle="Pick any specialist — same registry as the agent menu in chat."
        icon={Bot}
      >
        {data.chat_groups.flatMap((g) =>
          g.agents.map((a) => (
            <AgentCard
              key={a.id}
              id={a.id}
              label={a.label}
              description={a.description}
              chatAgentId={a.id}
            />
          ))
        )}
      </Section>

      <Section
        title="Operations"
        subtitle="Overnight workers — scouts, pipeline, ads, funding."
        icon={Radar}
      >
        {data.operations.map((d) => (
          <AgentCard
            key={d.id}
            id={d.id}
            label={d.label}
            description={d.description}
            rank={d.rank}
            onProbation={d.on_probation}
            chatAgentId={d.chat_agent_id}
            href={d.name === "Scout" ? "/dashboard/action-mode" : undefined}
          />
        ))}
      </Section>

      <Section
        title="Customer service"
        subtitle="Talks to your customers — sales, orders, support, inbox."
        icon={Users}
      >
        {data.customer_service.map((d) => (
          <AgentCard
            key={d.id}
            id={d.id}
            label={d.label}
            description={d.description}
            rank={d.rank}
            onProbation={d.on_probation}
            chatAgentId={d.chat_agent_id}
          />
        ))}
      </Section>

      <Section
        title="Action Mode runners"
        subtitle="Autonomous scans and queue drafts — approve from Zilo Briefing or Action Mode."
        icon={Radar}
      >
        {data.action_mode.map((a) => (
          <AgentCard
            key={a.id}
            id={a.id}
            label={a.label}
            description={a.description}
            href={a.href}
          />
        ))}
      </Section>

      <Link
        href="/dashboard"
        className="mt-10 inline-block text-sm font-medium text-brand-dark hover:underline"
      >
        ← Back to Zilo Briefing
      </Link>
    </div>
  );
}
