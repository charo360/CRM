"use client";

import { Plug } from "lucide-react";

export function MarketingApiBanner({ product }: { product: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-950">
      <Plug size={14} className="mt-0.5 shrink-0 text-amber-700" />
      <p>
        <span className="font-semibold">Backend pending.</span> {product} UI is fully interactive; data is stored in this
        browser until your APIs are connected. Replace <code className="rounded bg-amber-100/80 px-1 py-0.5 font-mono text-[10px]">lib/marketing-stubs.ts</code>{" "}
        hooks with real calls when ready.
      </p>
    </div>
  );
}
