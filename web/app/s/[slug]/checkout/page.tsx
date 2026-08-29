"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

type PublicOrder = {
  order_token: string;
  order_number: string;
  payment_status: string;
  payment_provider: string;
  total_amount: number;
  currency: string;
};

export default function StoreCheckoutStatusPage() {
  const { slug } = useParams<{ slug: string }>();
  const query = useSearchParams();
  const token = query.get("order") || "";
  const cancelled = query.get("cancelled") === "1";
  const [order, setOrder] = useState<PublicOrder | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const response = await fetch(`${API_BASE}/storefront/public/orders/${encodeURIComponent(token)}`);
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Order not found");
      setOrder(body);
      setError("");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not check the order status.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!token || !order || order.payment_status.toLowerCase() === "paid") return;
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [order, refresh, token]);

  async function retryPayment() {
    setRetrying(true);
    try {
      const response = await fetch(`${API_BASE}/storefront/public/orders/${encodeURIComponent(token)}/payment`, { method: "POST" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Could not restart payment");
      if (body.payment_action === "redirect" && body.checkout_url) {
        window.location.assign(body.checkout_url);
        return;
      }
      await refresh();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not restart payment.");
    } finally {
      setRetrying(false);
    }
  }

  if (!token) return <StatusCard icon="error" title="Order link missing" message="Please return to the catalog and place your order again." />;
  if (loading) return <main className="min-h-screen grid place-items-center bg-slate-50"><Loader2 className="animate-spin text-brand-dark" size={30} /></main>;
  if (error || !order) return <StatusCard icon="error" title="Could not find this order" message={error || "The order link is invalid."} />;
  const paid = order.payment_status.toLowerCase() === "paid";

  return <main className="min-h-screen grid place-items-center bg-slate-50 p-5"><div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">{paid ? <CheckCircle2 className="mx-auto text-emerald-500" size={48} /> : <Loader2 className="mx-auto animate-spin text-brand-dark" size={42} />}<h1 className="mt-5 text-xl font-bold text-slate-800">{paid ? "Payment confirmed" : cancelled ? "Payment was not completed" : "Confirming your payment"}</h1><p className="mt-2 text-sm leading-relaxed text-slate-500">{paid ? "Thank you. The business has received your order and payment." : cancelled ? "Your order is saved. You can try secure payment again when you are ready." : "Your order is saved. This page updates automatically as soon as the payment provider confirms it."}</p><div className="mt-6 rounded-xl bg-slate-50 p-4 text-left text-sm"><div className="flex justify-between gap-4"><span className="text-slate-500">Order</span><span className="font-medium">{order.order_number}</span></div><div className="mt-2 flex justify-between gap-4"><span className="text-slate-500">Total</span><span className="font-semibold">{formatCurrency(order.total_amount, order.currency)}</span></div></div>{!paid && <><button type="button" onClick={() => void refresh()} className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand-dark"><RefreshCw size={15} />Check status</button>{cancelled && order.payment_provider !== "manual" && <button type="button" disabled={retrying} onClick={() => void retryPayment()} className="mt-4 w-full rounded-xl bg-brand-dark py-3 text-sm font-bold text-white disabled:opacity-60">{retrying ? "Starting payment…" : "Try secure payment again"}</button>}</>}<a href={`/s/${encodeURIComponent(slug)}`} className="mt-6 block text-sm font-medium text-slate-500 hover:text-brand-dark">Back to catalog</a></div></main>;
}

function StatusCard({ icon, title, message }: { icon: "error"; title: string; message: string }) {
  return <main className="min-h-screen grid place-items-center bg-slate-50 p-5"><div className="max-w-sm text-center"><AlertCircle className="mx-auto text-slate-300" size={44} /><h1 className="mt-4 text-xl font-bold text-slate-800">{title}</h1><p className="mt-2 text-sm text-slate-500">{message}</p></div></main>;
}
