"use client";

import { Check } from "lucide-react";
import { PRICING_ROWS } from "@/lib/billing/plans";

function Cell({ value }: { value: string | boolean }) {
  if (value === true) {
    return <Check className="inline h-4 w-4 text-brand-dark" aria-label="Included" />;
  }
  if (value === false) {
    return <span className="text-slate-400">—</span>;
  }
  return <>{value}</>;
}

export function PricingTable({ highlightGrowth = true }: { highlightGrowth?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full min-w-[640px] border-collapse text-left text-sm">
        <thead>
          <tr className="bg-brand-ink text-white">
            <th className="px-4 py-4 font-semibold"> </th>
            <th className="px-4 py-4 font-semibold">Starter</th>
            <th className={`px-4 py-4 font-semibold ${highlightGrowth ? "bg-brand-dark" : ""}`}>Growth</th>
            <th className="px-4 py-4 font-semibold">Pro</th>
          </tr>
        </thead>
        <tbody className="text-slate-700">
          {PRICING_ROWS.map((row, i) => (
            <tr key={row.label} className={i < PRICING_ROWS.length - 1 ? "border-b border-slate-100" : ""}>
              <td className="px-4 py-3 font-medium text-slate-900">{row.label}</td>
              <td className="px-4 py-3">
                <Cell value={row.starter} />
              </td>
              <td className={`px-4 py-3 ${highlightGrowth ? "bg-brand/10 font-medium" : ""}`}>
                <Cell value={row.growth} />
              </td>
              <td className="px-4 py-3">
                <Cell value={row.pro} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
