"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { payheroApi, type PayheroUsageSummary } from "@/lib/api";
import { PAYHERO_SMS_KES, PAYHERO_WHATSAPP_KES } from "@/lib/billing/payheroRates";

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

  return (
    <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/80 p-3 text-xs text-slate-600 space-y-2">
      <p className="font-semibold text-slate-800">PayHero usage (estimated)</p>
      <p className="text-[10px] text-slate-500">
        M-Pesa fees by amount tier · SMS KES {PAYHERO_SMS_KES.toFixed(2)} · WhatsApp KES{" "}
        {PAYHERO_WHATSAPP_KES.toFixed(2)} per message
      </p>
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
      ) : summary ? (
        <ul className="space-y-1 tabular-nums">
          <li>
            M-Pesa: {summary.mpesa_payments.count} payments · collected KES{" "}
            {Math.round(summary.mpesa_payments.gross_collected_kes).toLocaleString()} · est. fees KES{" "}
            {Math.round(summary.mpesa_payments.estimated_payhero_fees_kes).toLocaleString()}
          </li>
          <li className="font-medium text-slate-800">
            Total est. PayHero fees: KES {Math.round(summary.total_estimated_fees_kes).toLocaleString()}
          </li>
        </ul>
      ) : (
        <p className="text-slate-400">No usage recorded yet.</p>
      )}
    </div>
  );
}
