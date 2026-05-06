"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Users, Link2, Copy, ExternalLink, Eye, FileText, ShoppingCart, CreditCard, ChevronRight } from "lucide-react";

interface Customer {
  _id: string;
  name: string;
  email?: string;
  phone?: string;
  created_at: string;
}

export default function ClientPortalPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ customers: Customer[] }>("/customers")
      .then(d => setCustomers((d.customers || []).slice(0, 50)))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function getPortalUrl(customerId: string) {
    return `${typeof window !== "undefined" ? window.location.origin : ""}/portal/${customerId}`;
  }

  function copyLink(id: string) {
    navigator.clipboard.writeText(getPortalUrl(id));
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Users size={22} className="text-green-600" /> Client Portal
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Share a personal portal link with each client so they can view their invoices, proposals, and order history.
        </p>
      </div>

      {/* Info banner */}
      <div className="bg-green-50 border border-green-100 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { icon: FileText, label: "Proposals", desc: "View all shared proposals" },
          { icon: ShoppingCart, label: "Orders", desc: "Track order history" },
          { icon: CreditCard, label: "Invoices", desc: "Download & review invoices" },
        ].map(({ icon: Icon, label, desc }) => (
          <div key={label} className="flex items-start gap-3">
            <div className="w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center shrink-0">
              <Icon size={15} className="text-green-600" />
            </div>
            <div>
              <p className="text-sm font-semibold text-green-800">{label}</p>
              <p className="text-xs text-green-600">{desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Customer list */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse h-14" />
          ))}
        </div>
      ) : customers.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
          <Users size={32} className="mx-auto text-slate-300 mb-3" />
          <p className="text-slate-500">No customers yet. Add customers to share portal links.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100">
          <div className="px-5 py-3 bg-slate-50 rounded-t-xl grid grid-cols-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
            <span>Client</span>
            <span>Contact</span>
            <span className="text-right">Portal Link</span>
          </div>
          {customers.map(c => (
            <div key={c._id} className="px-5 py-3.5 grid grid-cols-3 items-center">
              <p className="text-sm font-medium text-slate-800">{c.name}</p>
              <p className="text-xs text-slate-500">{c.email || c.phone || "—"}</p>
              <div className="flex items-center gap-2 justify-end">
                <button onClick={() => copyLink(c._id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                  <Copy size={11} /> {copied === c._id ? "Copied!" : "Copy Link"}
                </button>
                <a href={getPortalUrl(c._id)} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                  <Eye size={11} /> Preview
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
