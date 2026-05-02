"use client";

import Link from "next/link";
import { MarketingApiBanner } from "@/components/marketing/MarketingApiBanner";
import { MapPinned, Star, MessageSquareText, CalendarClock, ExternalLink, Store } from "lucide-react";

export default function GoogleBusinessPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 pb-16 sm:p-6">
      <div>
        <div className="mb-1 flex items-center gap-2 text-[#4285F4]">
          <MapPinned size={20} />
          <span className="text-[11px] font-semibold uppercase tracking-wide">Local presence</span>
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Google Business Profile</h1>
        <p className="mt-1 text-sm text-slate-600">
          Manage how you show up on Google Search and Maps — reviews, posts, and messages in one flow. Connect your
          profile through{" "}
          <strong className="text-slate-800">Integrations → Social Channels</strong> (Google Business is supported
          alongside Meta and other networks).
        </p>
      </div>

      <MarketingApiBanner product="Google Business Profile" />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <Star className="mb-2 h-5 w-5 text-amber-500" aria-hidden />
          <h2 className="font-semibold text-slate-900">Reviews &amp; reputation</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">
            Track new Google reviews, draft replies with Zilo Chat, and keep your rating healthy.
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <MessageSquareText className="mb-2 h-5 w-5 text-[#4285F4]" aria-hidden />
          <h2 className="font-semibold text-slate-900">Messages &amp; Q&amp;A</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">
            Route Business Profile messages into your social inbox once the account is linked.
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <CalendarClock className="mb-2 h-5 w-5 text-emerald-600" aria-hidden />
          <h2 className="font-semibold text-slate-900">Posts &amp; updates</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">
            Plan offers and updates; use the social scheduler for consistent publishing where supported.
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <Store className="mb-2 h-5 w-5 text-slate-700" aria-hidden />
          <h2 className="font-semibold text-slate-900">Store info &amp; hours</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">
            Keep address, hours, and services accurate so local search converts.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-[#4285F4]/25 bg-gradient-to-br from-blue-50/80 to-white p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-900">Connect Google Business</p>
          <p className="mt-1 text-xs text-slate-600">
            Open Social Channels and authorize Google Business to start receiving reviews and messages.
          </p>
        </div>
        <Link
          href="/dashboard/integrations#integrations-social"
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-[#4285F4] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#3367d6]"
        >
          Go to Integrations
          <ExternalLink size={14} aria-hidden />
        </Link>
      </div>

      <div className="flex flex-wrap gap-2 text-sm">
        <Link
          href="/dashboard/social-inbox"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-medium text-slate-700 shadow-sm hover:border-[#009B3A]/30 hover:bg-emerald-50/50"
        >
          Social Inbox
        </Link>
        <Link
          href="/dashboard/social-scheduler"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-medium text-slate-700 shadow-sm hover:border-[#009B3A]/30 hover:bg-emerald-50/50"
        >
          Social scheduler
        </Link>
        <Link
          href="/dashboard/channels"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-medium text-slate-700 shadow-sm hover:border-[#009B3A]/30 hover:bg-emerald-50/50"
        >
          Channels overview
        </Link>
      </div>
    </div>
  );
}
