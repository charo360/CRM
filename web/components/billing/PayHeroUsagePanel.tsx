"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { payheroApi, type PayheroUsageSummary } from "@/lib/api";

export function PayHeroUsagePanel({ connected }: { connected: boolean }) {
  const [summary, setSummary] = useState<PayheroUsageSummary | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!connected) {
      setSummary(null);
      return;
    }
    setLoading(true);
    payheroApi
      .usageSummary()
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [connected]);

  if (!connected) return null;

  const mpesa = summary?.mpesa_payments;
  const totalFees = summary ? Math.round(summary.total_estimated_fees_kes) : 0;
  const collected = mpesa ? Math.round(mpesa.gross_collected_kes) : 0;
  const mpesaFees = mpesa ? Math.round(mpesa.estimated_payhero_fees_kes) : 0;
  const count = mpesa?.count ?? 0;

  return (
    <div className="rounded-lg border border-slate-200/90 bg-white px-3 py-2.5 text-[11px] shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Usage</p>
      {loading ? (
        <div className="mt-2 flex justify-center py-2">
          <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
        </div>
      ) : summary ? (
        <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 tabular-nums">
          <div>
            <dt className="text-slate-500">M-Pesa payments</dt>
            <dd className="font-semibold text-slate-900">{count.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Collected</dt>
            <dd className="font-semibold text-slate-900">KES {collected.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Est. M-Pesa fees</dt>
            <dd className="font-medium text-slate-800">KES {mpesaFees.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Est. total fees</dt>
            <dd className="font-medium text-slate-800">KES {totalFees.toLocaleString()}</dd>
          </div>
        </dl>
      ) : (
        <p className="mt-2 text-slate-400">No payments recorded yet.</p>
      )}
    </div>
  );
}
