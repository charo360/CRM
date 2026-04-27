"use client";

/**
 * Public quote view — no auth. Pulled by share token via /api/quotes/public/{token}.
 * Recipient can print/save as PDF, copy link, contact via WhatsApp, or accept the quote.
 */

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { quotesApi } from "@/lib/api";
import { printNode } from "@/lib/printInvoice";
import InvoicePreview, { type InvoiceData } from "@/components/InvoicePreview";
import { Download, Copy, Check, MessageCircle, AlertCircle, CheckCircle2 } from "lucide-react";

export default function PublicQuotePage() {
  const { token } = useParams() as { token: string };
  const [data, setData] = useState<InvoiceData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const previewRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const r = await quotesApi.getPublic(token);
        setData(r as unknown as InvoiceData);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load quote");
      }
    })();
  }, [token]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  }

  if (err) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
        <div className="bg-white rounded-xl border border-slate-200 p-6 max-w-md text-center space-y-3">
          <AlertCircle className="mx-auto text-red-500" size={36} />
          <h1 className="text-lg font-semibold text-slate-800">Quote unavailable</h1>
          <p className="text-sm text-slate-500">{err}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-400">
        Loading quote…
      </div>
    );
  }

  const raw = data as unknown as {
    customer_phone?: string;
    branding?: { from_phone?: string; from_name?: string };
    subject?: string;
    status?: string;
  };
  const phone = (raw.branding?.from_phone || "").replace(/[^\d]/g, "");
  const waHref = phone
    ? `https://wa.me/${phone}?text=${encodeURIComponent(`Hi, I'm responding to quote ${data.number}…`)}`
    : "";

  return (
    <div className="min-h-screen bg-slate-100">
      {/* Top bar */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="text-sm text-slate-500 truncate">
            <span className="text-[10px] uppercase tracking-widest font-semibold text-violet-600 mr-2">QUOTE</span>
            <strong className="text-slate-800">{data.number}</strong>
            {raw.branding?.from_name && <span> · {raw.branding.from_name}</span>}
            {raw.subject && <span className="hidden sm:inline text-slate-400"> — {raw.subject}</span>}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {waHref && (
              <a href={waHref} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-green-200 text-green-800 bg-green-50 hover:bg-green-100">
                <MessageCircle size={14} /> Contact
              </a>
            )}
            <button onClick={copyLink}
              className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700">
              {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy link</>}
            </button>
            <button
              onClick={() => {
                const node = previewRef.current?.querySelector<HTMLElement>(".invoice-preview-root") ?? null;
                printNode(node, `Quote ${data?.number || ""}`.trim());
              }}
              className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-slate-900 text-white hover:bg-slate-700">
              <Download size={14} /> Download PDF
            </button>
          </div>
        </div>
      </div>

      {/* Status banner for accepted/declined */}
      {raw.status === "accepted" && (
        <div className="bg-green-50 border-b border-green-200">
          <div className="max-w-4xl mx-auto px-4 py-2 flex items-center gap-2 text-green-800 text-sm font-medium">
            <CheckCircle2 size={16} /> This quote has been accepted.
          </div>
        </div>
      )}
      {raw.status === "declined" && (
        <div className="bg-red-50 border-b border-red-200">
          <div className="max-w-4xl mx-auto px-4 py-2 flex items-center gap-2 text-red-700 text-sm font-medium">
            <AlertCircle size={16} /> This quote has been declined.
          </div>
        </div>
      )}
      {raw.status === "expired" && (
        <div className="bg-amber-50 border-b border-amber-200">
          <div className="max-w-4xl mx-auto px-4 py-2 flex items-center gap-2 text-amber-700 text-sm font-medium">
            <AlertCircle size={16} /> This quote has expired.
          </div>
        </div>
      )}

      <div ref={previewRef} className="py-8 px-4">
        <InvoicePreview data={data} docType="QUOTE" />
      </div>

      <div className="no-print text-center text-xs text-slate-400 py-6">
        Powered by your CRM · Secure share link
      </div>
    </div>
  );
}
