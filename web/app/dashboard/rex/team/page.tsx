"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getAgentPersona, personaBadgeLabel } from "@/lib/agentPersonas";
import { Loader2, MessageSquare, ExternalLink, Radar, Users, Bot } from "lucide-react";
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

export default function ZiloTeamPage() {
  const [data, setData] = useState<TeamPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<TeamPayload>("/rex/team"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load team");
    } finally {
      setLoading(false);
    }
  }, []);

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
