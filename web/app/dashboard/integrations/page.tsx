"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { NANGO_INTEGRATION_IDS } from "@/lib/nango-config";
import { openNangoConnect } from "@/lib/nango-connect";
import { Plug, Mail, Calendar } from "lucide-react";

function SlackGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834V5.042zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.122 2.521a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zm-1.269 0a2.528 2.528 0 0 1-2.521 2.521 2.527 2.527 0 0 1-2.521-2.521V2.522A2.528 2.528 0 0 1 15.165 0a2.528 2.528 0 0 1 2.521 2.522v6.312zm-2.521 10.122a2.527 2.527 0 0 1 2.521 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.521-2.522v-2.521h2.521zm0-1.269a2.527 2.527 0 0 1-2.521-2.521 2.528 2.528 0 0 1 2.521-2.521h6.313A2.528 2.528 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.521h-6.313z" />
    </svg>
  );
}

type SmallTileProps = {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  borderClass: string;
  children: ReactNode;
};

function SmallTile({ icon, title, subtitle, borderClass, children }: SmallTileProps) {
  return (
    <div className={`flex flex-col rounded-xl border p-3 shadow-sm ${borderClass}`}>
      <div className="flex items-start gap-2.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/90 shadow-sm">{icon}</div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-tight text-slate-900">{title}</h3>
          {subtitle ? <p className="mt-0.5 text-[11px] leading-snug text-slate-500">{subtitle}</p> : null}
        </div>
      </div>
      <div className="mt-2.5">{children}</div>
    </div>
  );
}

export default function IntegrationsPage() {
  return (
    <div className="mx-auto max-w-3xl min-w-0 space-y-6 p-4 sm:p-6">
      <div>
        <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600">
          <Plug size={18} />
        </div>
        <h1 className="text-xl font-bold text-slate-900">Integrations</h1>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 sm:text-sm">
          Connect Slack, email, and calendar through{" "}
          <a href="https://nango.dev" target="_blank" rel="noopener noreferrer" className="font-medium text-indigo-600 hover:underline">
            Nango
          </a>
          . OAuth is handled for you; wire sync and webhooks in your backend when you&apos;re ready.
        </p>
        <p className="mt-1.5 text-xs text-indigo-600">
          <Link href="/dashboard/messages" className="font-medium hover:underline">
            Messages inbox →
          </Link>
        </p>
      </div>

      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Slack · Email · Calendar</h2>
        <div className="grid gap-2.5 sm:grid-cols-3">
          <SmallTile
            title="Slack"
            subtitle="Workspace alerts & threads"
            borderClass="border-slate-200 bg-slate-50/80"
            icon={<SlackGlyph className="h-5 w-5 text-[#4A154B]" />}
          >
            <button
              type="button"
              onClick={() => openNangoConnect([NANGO_INTEGRATION_IDS.slack])}
              className="w-full rounded-lg bg-[#4A154B] px-2.5 py-1.5 text-center text-xs font-semibold text-white hover:bg-[#3e1240]"
            >
              Connect
            </button>
          </SmallTile>

          <SmallTile
            title="Email"
            subtitle="Gmail / Outlook via Nango"
            borderClass="border-slate-200 bg-slate-50/80"
            icon={<Mail size={18} className="text-slate-600" />}
          >
            <button
              type="button"
              onClick={() => openNangoConnect([NANGO_INTEGRATION_IDS.email])}
              className="w-full rounded-lg bg-slate-800 px-2.5 py-1.5 text-center text-xs font-semibold text-white hover:bg-slate-900"
            >
              Connect
            </button>
          </SmallTile>

          <SmallTile
            title="Calendar"
            subtitle="Google / Microsoft"
            borderClass="border-slate-200 bg-slate-50/80"
            icon={<Calendar size={18} className="text-emerald-600" />}
          >
            <button
              type="button"
              onClick={() => openNangoConnect([NANGO_INTEGRATION_IDS.calendar])}
              className="w-full rounded-lg bg-emerald-600 px-2.5 py-1.5 text-center text-xs font-semibold text-white hover:bg-emerald-700"
            >
              Connect
            </button>
          </SmallTile>
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          Set <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[10px]">NANGO_SECRET_KEY</code> on the Next server.
          In Nango, create integrations whose IDs match{" "}
          <code className="rounded bg-slate-100 px-1 font-mono text-[10px]">{NANGO_INTEGRATION_IDS.slack}</code>,{" "}
          <code className="rounded bg-slate-100 px-1 font-mono text-[10px]">{NANGO_INTEGRATION_IDS.email}</code>,{" "}
          <code className="rounded bg-slate-100 px-1 font-mono text-[10px]">{NANGO_INTEGRATION_IDS.calendar}</code> — or override with{" "}
          <code className="rounded bg-slate-100 px-1 font-mono text-[10px]">NEXT_PUBLIC_NANGO_ID_*</code>.
        </p>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[11px] leading-relaxed text-slate-600">
        <strong className="text-slate-800">Team &amp; shop</strong> live in{" "}
        <Link href="/dashboard/settings" className="font-medium text-indigo-600 hover:underline">
          Settings
        </Link>
        . WhatsApp stays under <strong className="text-slate-800">Business → WhatsApp</strong> in the sidebar.
      </section>
    </div>
  );
}
