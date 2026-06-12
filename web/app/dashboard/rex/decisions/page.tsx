"use client";

import { Suspense } from "react";
import DecisionRoom from "@/components/rex/DecisionRoom";
import { Loader2 } from "lucide-react";

export default function ZiloDecisionsPage() {
  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#050f0a] text-slate-100">
      <Suspense
        fallback={
          <div className="flex justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
          </div>
        }
      >
        <DecisionRoom />
      </Suspense>
    </div>
  );
}
