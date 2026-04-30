"use client";

import { CheckCircle2, Clock } from "lucide-react";

export function MarketingApiBanner({ product }: { product: string }) {
  return (
    <div className="flex flex-wrap items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-[11px] text-slate-700">
      <span className="flex items-center gap-1.5 font-medium text-green-700">
        <CheckCircle2 size={13} className="text-green-500" />
        Drafts saved to your workspace
      </span>
      <span className="flex items-center gap-1.5 text-slate-500">
        <Clock size={13} />
        {product} Platform API (live metrics &amp; publishing) — coming soon
      </span>
    </div>
  );
}
