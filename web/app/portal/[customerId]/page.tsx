"use client";

import { useEffect, useState } from "react";
import { use } from "react";
import { FileText, ShoppingCart, CreditCard, Loader2, AlertCircle, Download, ExternalLink } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

interface Order { _id: string; order_number?: string; total_amount: number; payment_status: string; created_at: string; }
interface Invoice { _id: string; invoice_number?: string; amount: number; status: string; created_at: string; file_url?: string; }
interface DealRoom { _id: string; title: string; status: string; created_at: string; token: string; }
interface CustomerInfo { name: string; email?: string; }

type Tab = "proposals" | "orders" | "invoices";

export default function ClientPortalViewer({ params }: { params: Promise<{ customerId: string }> }) {
  const { customerId } = use(params);
  const [tab, setTab] = useState<Tab>("proposals");
  const [customer, setCustomer] = useState<CustomerInfo | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [proposals, setProposals] = useState<DealRoom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [cRes, oRes, iRes, dRes] = await Promise.all([
          fetch(`${API_BASE}/customers/${customerId}`),
          fetch(`${API_BASE}/orders?customer_id=${customerId}`),
          fetch(`${API_BASE}/invoices?customer_id=${customerId}`),
          fetch(`${API_BASE}/growth/deal-room?customer_id=${customerId}`),
        ]);
        if (!cRes.ok) { setError("Client not found."); return; }
        const c = await cRes.json();
        setCustomer({ name: c.name || c.customer?.name || "Client", email: c.email || c.customer?.email });
        const o = await oRes.json(); setOrders(o.orders || o || []);
        const inv = await iRes.json(); setInvoices(inv.invoices || inv || []);
        const d = await dRes.json(); setProposals((d.deal_rooms || []).filter((r: DealRoom) => r.status !== "declined"));
      } catch { setError("Unable to load portal."); }
      finally { setLoading(false); }
    }
    load();
  }, [customerId]);

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <Loader2 size={32} className="text-slate-400 animate-spin" />
    </div>
  );

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="text-center">
        <AlertCircle size={40} className="mx-auto text-slate-300 mb-3" />
        <p className="text-slate-600 font-medium">{error}</p>
      </div>
    </div>
  );

  const tabs: { id: Tab; label: string; icon: React.ElementType; count: number }[] = [
    { id: "proposals", label: "Proposals", icon: FileText, count: proposals.length },
    { id: "orders", label: "Orders", icon: ShoppingCart, count: orders.length },
    { id: "invoices", label: "Invoices", icon: CreditCard, count: invoices.length },
  ];

  const STATUS_COLORS: Record<string, string> = {
    signed: "bg-emerald-100 text-emerald-700",
    viewed: "bg-amber-100 text-amber-700",
    sent: "bg-blue-100 text-blue-700",
    Paid: "bg-emerald-100 text-emerald-700",
    Pending: "bg-amber-100 text-amber-700",
    Partial: "bg-blue-100 text-blue-700",
    paid: "bg-emerald-100 text-emerald-700",
    unpaid: "bg-rose-100 text-rose-700",
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-5">
        <div className="max-w-3xl mx-auto">
          <div className="w-10 h-10 rounded-full bg-brand/20 flex items-center justify-center mb-3">
            <span className="text-brand-dark font-bold text-lg">
              {(customer?.name || "C")[0].toUpperCase()}
            </span>
          </div>
          <h1 className="text-xl font-bold text-slate-900">Welcome, {customer?.name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">Your client portal — view your proposals, orders, and invoices</p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto p-6 space-y-4">
        {/* Tabs */}
        <div className="flex gap-1 bg-white border border-slate-200 rounded-xl p-1">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-medium rounded-lg transition-colors ${
                tab === t.id ? "bg-brand-dark text-white" : "text-slate-600 hover:bg-slate-50"
              }`}>
              <t.icon size={14} />
              {t.label}
              {t.count > 0 && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-semibold ${
                  tab === t.id ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500"
                }`}>{t.count}</span>
              )}
            </button>
          ))}
        </div>

        {/* Proposals */}
        {tab === "proposals" && (
          proposals.length === 0 ? (
            <EmptyState icon={FileText} message="No proposals yet" />
          ) : (
            <div className="space-y-3">
              {proposals.map(p => (
                <div key={p._id} className="bg-white rounded-xl border border-slate-200 p-4 flex items-center justify-between">
                  <div>
                    <p className="font-medium text-slate-800 text-sm">{p.title}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{new Date(p.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[p.status] || "bg-slate-100 text-slate-500"}`}>
                      {p.status}
                    </span>
                    <a href={`/deal/${p.token}`}
                      className="flex items-center gap-1 text-xs text-brand-dark hover:underline font-medium">
                      View <ExternalLink size={10} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )
        )}

        {/* Orders */}
        {tab === "orders" && (
          orders.length === 0 ? (
            <EmptyState icon={ShoppingCart} message="No orders yet" />
          ) : (
            <div className="space-y-3">
              {orders.map(o => (
                <div key={o._id} className="bg-white rounded-xl border border-slate-200 p-4 flex items-center justify-between">
                  <div>
                    <p className="font-medium text-slate-800 text-sm">
                      Order #{o.order_number || o._id.slice(-6)}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">{new Date(o.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[o.payment_status] || "bg-slate-100 text-slate-500"}`}>
                      {o.payment_status}
                    </span>
                    <span className="text-sm font-semibold text-slate-800">${o.total_amount.toLocaleString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )
        )}

        {/* Invoices */}
        {tab === "invoices" && (
          invoices.length === 0 ? (
            <EmptyState icon={CreditCard} message="No invoices yet" />
          ) : (
            <div className="space-y-3">
              {invoices.map(inv => (
                <div key={inv._id} className="bg-white rounded-xl border border-slate-200 p-4 flex items-center justify-between">
                  <div>
                    <p className="font-medium text-slate-800 text-sm">
                      Invoice #{inv.invoice_number || inv._id.slice(-6)}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">{new Date(inv.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[inv.status] || "bg-slate-100 text-slate-500"}`}>
                      {inv.status}
                    </span>
                    <span className="text-sm font-semibold text-slate-800">${inv.amount?.toLocaleString()}</span>
                    {inv.file_url && (
                      <a href={inv.file_url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 text-xs text-brand-dark hover:underline font-medium">
                        <Download size={10} /> PDF
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}

function EmptyState({ icon: Icon, message }: { icon: React.ElementType; message: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
      <Icon size={32} className="mx-auto text-slate-200 mb-3" />
      <p className="text-sm text-slate-400">{message}</p>
    </div>
  );
}
