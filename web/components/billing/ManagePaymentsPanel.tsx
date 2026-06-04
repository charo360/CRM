"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  ArrowRightLeft,
  Loader2,
  Plug,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import {
  merchantPaymentsApi,
  type MerchantPaymentProvider,
  type MerchantPaymentTransaction,
  type MerchantPaymentsOverview,
} from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

const PROVIDER_LABELS: Record<MerchantPaymentProvider, string> = {
  paystack: "Paystack",
  stripe: "Stripe",
  flutterwave: "Flutterwave",
  payhero: "PayHero",
};

const PROVIDER_ORDER: MerchantPaymentProvider[] = [
  "paystack",
  "stripe",
  "flutterwave",
  "payhero",
];

function connectedProviders(data: MerchantPaymentsOverview | null): MerchantPaymentProvider[] {
  if (!data) return [];
  if (data.connected_providers?.length) {
    return PROVIDER_ORDER.filter((p) => data.connected_providers.includes(p));
  }
  return PROVIDER_ORDER.filter((p) => data.connections[p]?.connected);
}

function statusBadge(status: string) {
  if (status === "refunded") {
    return "bg-slate-100 text-slate-600";
  }
  return "bg-emerald-50 text-emerald-700";
}

export function ManagePaymentsPanel() {
  const [data, setData] = useState<MerchantPaymentsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [refundingId, setRefundingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const overview = await merchantPaymentsApi.overview(60);
      setData(overview);
    } catch {
      setData(null);
      toast.error("Could not load payment activity");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function setPreferred(provider: MerchantPaymentProvider | null) {
    if (!data) return;
    setBusyProvider(provider || "clear");
    try {
      await merchantPaymentsApi.setPreferredProvider(provider);
      toast.success(
        provider
          ? `${PROVIDER_LABELS[provider]} is now your default checkout provider`
          : "Default checkout provider cleared"
      );
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update default provider");
    } finally {
      setBusyProvider(null);
    }
  }

  async function refund(tx: MerchantPaymentTransaction) {
    if (tx.status === "refunded" || !tx.refundable) return;
    const label = PROVIDER_LABELS[tx.provider];
    const amount =
      tx.amount_major != null
        ? formatCurrency(tx.amount_major, tx.currency)
        : "the full amount";
    const extra =
      tx.refund_mode === "manual"
        ? "\n\nPayHero: Zilo will mark the order refunded. You still need to send M-Pesa to the customer from your PayHero or bank account."
        : "";
    if (
      !confirm(
        `Issue a full refund of ${amount} via ${label}? Funds will be reversed through ${label} (including from your linked subaccount where applicable).${extra}`
      )
    ) {
      return;
    }
    setRefundingId(tx.id);
    try {
      const res = await merchantPaymentsApi.refund({
        provider: tx.provider,
        ledger_id: tx.id,
      });
      if (res.manual_followup) {
        toast.success("Marked refunded in Zilo", { description: res.manual_followup });
      } else {
        toast.success("Refund submitted", {
          description: res.provider_refund_id
            ? `Reference: ${res.provider_refund_id}`
            : undefined,
        });
      }
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Refund failed");
    } finally {
      setRefundingId(null);
    }
  }

  const connections = data?.connections;
  const activeProviders = connectedProviders(data);
  const anyConnected = activeProviders.length > 0;

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-ink">Manage payment</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            See charges and payouts for your connected payment providers, set which one to use at
            checkout, and issue full refunds when needed.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh
        </button>
      </div>

      {!anyConnected && !loading && (
        <div className="mt-6 rounded-xl border border-dashed border-slate-200 bg-slate-50/80 p-5 text-sm text-slate-600">
          <p className="font-medium text-slate-800">No payment providers connected</p>
          <p className="mt-1">
            Connect Stripe, Paystack, PayHero, or Flutterwave under Integrations to collect payments
            on orders and Shopify flows.
          </p>
          <Link
            href="/dashboard/integrations"
            className="mt-3 inline-flex items-center gap-1.5 font-semibold text-brand-dark hover:underline"
          >
            <Plug className="h-4 w-4" />
            Open Integrations
          </Link>
        </div>
      )}

      {connections && anyConnected && (
        <div
          className={`mt-6 grid gap-3 ${
            activeProviders.length >= 3
              ? "sm:grid-cols-2 lg:grid-cols-3"
              : activeProviders.length === 2
                ? "sm:grid-cols-2"
                : "max-w-md"
          }`}
        >
          {activeProviders.map((key) => {
            const c = connections[key];
            if (!c) return null;
            const isDefault = data?.preferred_provider === key;
            const ready =
              key !== "stripe" || Boolean(c && "checkout_ready" in c && c.checkout_ready);
            return (
              <div
                key={key}
                className="rounded-xl border border-slate-200 bg-white p-4 text-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-900">{PROVIDER_LABELS[key]}</p>
                  {isDefault && (
                    <span className="rounded-full bg-brand/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-brand-dark">
                      Default
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-500">{c?.label || "Connected"}</p>
                {activeProviders.length > 1 && (
                  <button
                    type="button"
                    disabled={!ready || busyProvider !== null || isDefault}
                    onClick={() => void setPreferred(key)}
                    className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-dark hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busyProvider === key ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <ArrowRightLeft className="h-3 w-3" />
                    )}
                    Use for checkout
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {data?.preferred_provider && activeProviders.length > 1 && (
        <p className="mt-4 text-xs text-slate-500">
          Orders and checkout links prefer{" "}
          <strong>{PROVIDER_LABELS[data.preferred_provider]}</strong> when multiple providers are
          available.{" "}
          <button
            type="button"
            className="font-semibold text-brand-dark hover:underline"
            disabled={busyProvider !== null}
            onClick={() => void setPreferred(null)}
          >
            Clear default
          </button>
        </p>
      )}

      {anyConnected && (
      <div className="mt-8 overflow-hidden rounded-xl border border-slate-200">
        <div className="border-b border-slate-100 bg-slate-50 px-4 py-3">
          <p className="text-sm font-semibold text-slate-800">Recent transactions</p>
          <p className="text-xs text-slate-500">
            Charges on your connected accounts only (newest first). Use{" "}
            <strong className="font-semibold text-slate-700">Full refund</strong> in Actions to
            reverse a payment.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Reference</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Date</th>
                <th className="sticky right-0 z-10 bg-slate-50 px-4 py-3 shadow-[-4px_0_8px_-4px_rgba(0,0,0,0.08)]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-slate-400">
                    <Loader2 className="mx-auto h-6 w-6 animate-spin" />
                  </td>
                </tr>
              ) : !data?.transactions?.length ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                    No transactions yet for your connected providers. Collect a payment from Orders
                    or your connected store.
                  </td>
                </tr>
              ) : (
                data.transactions.map((tx) => (
                  <TransactionRow
                    key={`${tx.provider}-${tx.id}`}
                    tx={tx}
                    refunding={refundingId === tx.id}
                    onRefund={() => void refund(tx)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      )}
    </section>
  );
}

function TransactionRow({
  tx,
  refunding,
  onRefund,
}: {
  tx: MerchantPaymentTransaction;
  refunding: boolean;
  onRefund: () => void;
}) {
  const when = tx.created_at ? new Date(tx.created_at).toLocaleString() : "—";
  const customer = tx.customer_email || (typeof tx.channel === "string" ? tx.channel : "") || "—";
  return (
    <tr className="group border-b border-slate-50 hover:bg-slate-50/80">
      <td className="px-4 py-3 font-medium text-slate-800">{PROVIDER_LABELS[tx.provider]}</td>
      <td className="px-4 py-3 tabular-nums font-semibold text-slate-900">
        {tx.amount_major != null ? formatCurrency(tx.amount_major, tx.currency) : "—"}
      </td>
      <td className="max-w-[140px] truncate px-4 py-3 text-slate-600">{customer}</td>
      <td className="max-w-[120px] truncate px-4 py-3 font-mono text-xs text-slate-500">
        {tx.reference || "—"}
      </td>
      <td className="px-4 py-3">
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ${statusBadge(tx.status)}`}
        >
          {tx.status}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{when}</td>
      <td className="sticky right-0 z-10 bg-white px-4 py-3 shadow-[-4px_0_8px_-4px_rgba(0,0,0,0.06)] group-hover:bg-slate-50/80">
        {tx.refundable && tx.status !== "refunded" ? (
          <button
            type="button"
            onClick={onRefund}
            disabled={refunding}
            className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-60"
          >
            {refunding ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RotateCcw className="h-3 w-3" />
            )}
            Full refund
          </button>
        ) : tx.refund_mode === "manual" && tx.status === "refunded" ? (
          <span className="text-xs text-slate-400">Manual M-Pesa sent</span>
        ) : (
          <span className="text-xs text-slate-300">—</span>
        )}
      </td>
    </tr>
  );
}
