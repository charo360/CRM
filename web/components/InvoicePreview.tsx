"use client";

/**
 * Pixel-faithful invoice preview — reused by the editor (live preview) and the
 * public share page. Pure presentational component driven by a single data prop
 * so it stays print-friendly (`@media print` removes surrounding chrome).
 */

export type InvoiceItem = {
  name: string;
  description?: string;
  qty: number;
  unit_price: number;
  amount: number;
};

export type InvoiceBranding = {
  from_name?: string;
  from_email?: string;
  from_phone?: string;
  from_address?: string;
  logo_url?: string;
  accent_color?: string;
  text_color?: string;
  template?: string;
  footer?: string;
  payment_instructions?: string;
};

export type InvoiceData = {
  number: string;
  customer_name?: string;
  customer_phone?: string;
  customer_email?: string;
  customer_address?: string;
  items: InvoiceItem[];
  subtotal: number;
  discount?: number;
  discount_amount?: number;
  tax_rate: number;
  tax_amount: number;
  total: number;
  amount_paid?: number;
  currency: string;
  issue_date?: string | null;
  due_date?: string | null;
  notes?: string;
  terms?: string;
  po_number?: string | null;
  status?: string;
  branding?: InvoiceBranding;
};

function fmtMoney(n: number, cur: string) {
  return `${cur} ${(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(d?: string | null) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return d;
  }
}

const STATUS_BADGE: Record<string, { bg: string; fg: string; label: string }> = {
  draft:     { bg: "#E2E8F0", fg: "#334155", label: "DRAFT" },
  sent:      { bg: "#DBEAFE", fg: "#1D4ED8", label: "SENT" },
  viewed:    { bg: "#EDE9FE", fg: "#6D28D9", label: "VIEWED" },
  paid:      { bg: "#DCFCE7", fg: "#15803D", label: "PAID" },
  partial:   { bg: "#FEF3C7", fg: "#B45309", label: "PARTIAL" },
  overdue:   { bg: "#FEE2E2", fg: "#B91C1C", label: "OVERDUE" },
  cancelled: { bg: "#F1F5F9", fg: "#64748B", label: "CANCELLED" },
};

export default function InvoicePreview({ data, docType = "INVOICE" }: { data: InvoiceData; docType?: string }) {
  const b = data.branding || {};
  const accent = b.accent_color || "#0f766e";
  const text = b.text_color || "#0f172a";
  const template = (b.template || "modern").toLowerCase();
  const status = (data.status || "draft").toLowerCase();
  const badge = STATUS_BADGE[status] || STATUS_BADGE.draft;
  const cur = data.currency || "KES";

  const bordered = template === "classic";
  const minimal = template === "minimal";
  const bold = template === "bold";

  return (
    <div
      className="invoice-preview-root"
      style={{
        background: "white",
        color: text,
        width: "100%",
        maxWidth: 820,
        margin: "0 auto",
        padding: "40px 44px",
        fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
        fontSize: 13,
        lineHeight: 1.5,
        boxShadow: "0 1px 3px rgba(0,0,0,0.04), 0 10px 40px -12px rgba(0,0,0,0.10)",
        border: bordered ? `1px solid ${accent}` : "1px solid #e2e8f0",
        borderRadius: minimal ? 4 : 14,
      }}
    >
      {/* Header band (bold template) */}
      {bold && (
        <div
          style={{
            margin: "-40px -44px 24px",
            padding: "28px 44px",
            background: accent,
            color: "white",
            borderRadius: "14px 14px 0 0",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
            <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
              {b.logo_url && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img src={b.logo_url} alt="" style={{ height: 48, width: 48, borderRadius: 8, objectFit: "cover", background: "white" }} />
              )}
              <div>
                <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.3 }}>{b.from_name || "Your business"}</div>
                {b.from_address && <div style={{ opacity: 0.9, fontSize: 12 }}>{b.from_address}</div>}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: 1 }}>{docType}</div>
              <div style={{ opacity: 0.9 }}>#{data.number}</div>
            </div>
          </div>
        </div>
      )}

      {/* Header (non-bold) */}
      {!bold && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 28 }}>
          <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
            {b.logo_url && (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img src={b.logo_url} alt="" style={{ height: 56, width: 56, borderRadius: 8, objectFit: "cover" }} />
            )}
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: text }}>{b.from_name || "Your business"}</div>
              {b.from_address && <div style={{ color: "#64748b", fontSize: 12 }}>{b.from_address}</div>}
              <div style={{ color: "#64748b", fontSize: 12 }}>
                {[b.from_email, b.from_phone].filter(Boolean).join(" · ")}
              </div>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: 1, color: accent }}>{docType}</div>
            <div style={{ color: "#64748b", fontSize: 13, marginTop: 2 }}>#{data.number}</div>
            <span
              style={{
                display: "inline-block", marginTop: 8, padding: "3px 10px",
                background: badge.bg, color: badge.fg, borderRadius: 999,
                fontSize: 10, fontWeight: 700, letterSpacing: 0.5,
              }}
            >
              {badge.label}
            </span>
          </div>
        </div>
      )}

      {/* Bill-to + meta */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8", marginBottom: 4 }}>Bill to</div>
          <div style={{ fontWeight: 600 }}>{data.customer_name || "—"}</div>
          {data.customer_address && <div style={{ color: "#475569", fontSize: 12 }}>{data.customer_address}</div>}
          {data.customer_email && <div style={{ color: "#475569", fontSize: 12 }}>{data.customer_email}</div>}
          {data.customer_phone && <div style={{ color: "#475569", fontSize: 12 }}>{data.customer_phone}</div>}
        </div>
        <div style={{ textAlign: "right", fontSize: 12 }}>
          <div style={{ marginBottom: 3 }}><span style={{ color: "#94a3b8" }}>Issue date:&nbsp;</span>{fmtDate(data.issue_date)}</div>
          <div style={{ marginBottom: 3 }}><span style={{ color: "#94a3b8" }}>Due date:&nbsp;</span><strong>{fmtDate(data.due_date)}</strong></div>
          {data.po_number && <div><span style={{ color: "#94a3b8" }}>PO #:&nbsp;</span>{data.po_number}</div>}
        </div>
      </div>

      {/* Items */}
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 16, fontSize: 12 }}>
        <thead>
          <tr style={{ background: minimal ? "transparent" : `${accent}12`, color: accent }}>
            <th style={{ textAlign: "left",  padding: "10px 12px", fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, borderBottom: `2px solid ${accent}` }}>Description</th>
            <th style={{ textAlign: "right", padding: "10px 12px", fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, borderBottom: `2px solid ${accent}`, width: 60 }}>Qty</th>
            <th style={{ textAlign: "right", padding: "10px 12px", fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, borderBottom: `2px solid ${accent}`, width: 110 }}>Unit price</th>
            <th style={{ textAlign: "right", padding: "10px 12px", fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, borderBottom: `2px solid ${accent}`, width: 130 }}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {(data.items || []).map((it, idx) => (
            <tr key={idx} style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td style={{ padding: "10px 12px", verticalAlign: "top" }}>
                <div style={{ fontWeight: 600 }}>{it.name || "—"}</div>
                {it.description && <div style={{ color: "#64748b", fontSize: 11 }}>{it.description}</div>}
              </td>
              <td style={{ padding: "10px 12px", textAlign: "right", verticalAlign: "top" }}>{it.qty}</td>
              <td style={{ padding: "10px 12px", textAlign: "right", verticalAlign: "top" }}>{fmtMoney(it.unit_price, cur)}</td>
              <td style={{ padding: "10px 12px", textAlign: "right", verticalAlign: "top", fontWeight: 600 }}>{fmtMoney(it.qty * it.unit_price, cur)}</td>
            </tr>
          ))}
          {(!data.items || data.items.length === 0) && (
            <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "#94a3b8" }}>No items yet</td></tr>
          )}
        </tbody>
      </table>

      {/* Totals */}
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 24 }}>
        <div style={{ minWidth: 280, fontSize: 13 }}>
          <Row label="Subtotal" value={fmtMoney(data.subtotal, cur)} />
          {!!(data.discount_amount && data.discount) && (
            <Row label={`Discount (${data.discount}%)`} value={`− ${fmtMoney(data.discount_amount, cur)}`} />
          )}
          {!!data.tax_rate && (
            <Row label={`Tax (${data.tax_rate}%)`} value={fmtMoney(data.tax_amount, cur)} />
          )}
          <div style={{ borderTop: `2px solid ${accent}`, marginTop: 8, paddingTop: 8 }}>
            <Row label="Total due" value={fmtMoney(data.total, cur)} bold accent={accent} />
          </div>
          {!!(data.amount_paid && data.amount_paid > 0) && (
            <>
              <Row label="Paid" value={`− ${fmtMoney(data.amount_paid, cur)}`} />
              <Row label="Balance" value={fmtMoney(Math.max(data.total - (data.amount_paid || 0), 0), cur)} bold />
            </>
          )}
        </div>
      </div>

      {/* Payment instructions + notes + terms */}
      <div style={{ display: "grid", gridTemplateColumns: b.payment_instructions ? "1fr 1fr" : "1fr", gap: 24, marginBottom: 20 }}>
        {b.payment_instructions && (
          <div>
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8", marginBottom: 4 }}>How to pay</div>
            <div style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{b.payment_instructions}</div>
          </div>
        )}
        {(data.notes || data.terms) && (
          <div>
            {data.notes && (
              <>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8", marginBottom: 4 }}>Notes</div>
                <div style={{ whiteSpace: "pre-wrap", fontSize: 12, marginBottom: 10 }}>{data.notes}</div>
              </>
            )}
            {data.terms && (
              <>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8", marginBottom: 4 }}>Terms</div>
                <div style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{data.terms}</div>
              </>
            )}
          </div>
        )}
      </div>

      {b.footer && (
        <div style={{ textAlign: "center", color: "#64748b", fontSize: 11, borderTop: "1px solid #e2e8f0", paddingTop: 14 }}>
          {b.footer}
        </div>
      )}
    </div>
  );
}

function Row({ label, value, bold, accent }: { label: string; value: string; bold?: boolean; accent?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", color: bold ? (accent || "#0f172a") : "#475569", fontWeight: bold ? 700 : 400, fontSize: bold ? 15 : 13 }}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}
