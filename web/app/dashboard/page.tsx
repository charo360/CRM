"use client";

import MorningBriefing from "@/components/rex/MorningBriefing";

/** Overview is Zilo Briefing — live feed from the whole CRM. */
export default function DashboardPage() {
  return (
    <div className="h-[calc(100vh-4rem)] min-h-0 overflow-hidden bg-[#050f0a] text-slate-100">
      <MorningBriefing />
    </div>
  );
}
