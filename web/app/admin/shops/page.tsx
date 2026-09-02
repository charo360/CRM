"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, type AdminShopReport } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { AlertTriangle, Check, Loader2, RefreshCw, ShieldOff, Store } from "lucide-react";

const REASON_LABELS: Record<string, string> = {
  scam: "Looks like a scam",
  not_delivered: "Paid, never received",
  counterfeit: "Fake or misdescribed",
  offensive: "Offensive or illegal",
  other: "Something else",
};

export default function AdminShopReportsPage() {
  const [reports, setReports] = useState<AdminShopReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [showReviewed, setShowReviewed] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await adminApi.listShopReports(showReviewed);
      setReports(data.reports || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load reports");
    } finally {
      setLoading(false);
    }
  }, [showReviewed]);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggleShop(report: AdminShopReport) {
    setBusyId(report.id);
    try {
      await adminApi.setShopEnabled(report.business_id, !report.shop_enabled);
      setReports((current) =>
        current.map((row) =>
          row.business_id === report.business_id ? { ...row, shop_enabled: !report.shop_enabled } : row,
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not change the shop");
    } finally {
      setBusyId("");
    }
  }

  async function markReviewed(report: AdminShopReport) {
    setBusyId(report.id);
    try {
      await adminApi.reviewShopReport(report.id, !report.reviewed);
      setReports((current) => current.filter((row) => row.id !== report.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update the report");
    } finally {
      setBusyId("");
    }
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Reported shops</h1>
          <p className="mt-1 text-sm text-slate-500">Shops that buyers have flagged from the public catalog.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowReviewed((current) => !current)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            {showReviewed ? "Show open" : "Show reviewed"}
          </button>
          <button
            type="button"
            onClick={() => void load()}
            className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>
      )}

      {loading ? (
        <div className="mt-10 grid place-items-center">
          <Loader2 className="animate-spin text-slate-400" size={28} />
        </div>
      ) : reports.length === 0 ? (
        <div className="mt-6 rounded-xl border border-slate-200 bg-white p-10 text-center">
          <Check className="mx-auto text-emerald-500" size={32} />
          <p className="mt-3 text-sm text-slate-500">
            {showReviewed ? "No reviewed reports." : "No open reports. Nothing needs your attention."}
          </p>
        </div>
      ) : (
        <div className="mt-6 grid gap-3">
          {reports.map((report) => (
            <div key={report.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Store size={16} className="shrink-0 text-slate-400" />
                    <p className="truncate font-semibold text-slate-900">{report.business_name || report.slug}</p>
                    {!report.shop_enabled && (
                      <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-700">
                        Disabled
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    /{report.slug}
                    {report.created_at ? ` · ${formatDateTime(report.created_at)}` : ""}
                  </p>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-800">
                  <AlertTriangle size={12} />
                  {REASON_LABELS[report.reason] || report.reason}
                </span>
              </div>

              {report.detail && (
                <p className="mt-3 whitespace-pre-line rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
                  {report.detail}
                </p>
              )}

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busyId === report.id}
                  onClick={() => void toggleShop(report)}
                  className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold disabled:opacity-50 ${
                    report.shop_enabled
                      ? "bg-rose-600 text-white hover:bg-rose-700"
                      : "border border-slate-200 text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <ShieldOff size={14} />
                  {report.shop_enabled ? "Disable shop" : "Re-enable shop"}
                </button>
                <button
                  type="button"
                  disabled={busyId === report.id}
                  onClick={() => void markReviewed(report)}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  <Check size={14} />
                  {report.reviewed ? "Reopen" : "Mark reviewed"}
                </button>
                <a
                  href={`/${encodeURIComponent(report.slug)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  View shop
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
