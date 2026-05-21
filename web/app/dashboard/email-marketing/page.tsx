"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Mail, Plus, Send, Trash2, BarChart2, Settings,
  Loader2, CheckCircle2, Clock, FileText, RefreshCw, X,
  Zap, Users, AlertCircle, Eye, Play,
} from "lucide-react";
import { getToken } from "@/lib/auth";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

type CampaignStatus = "draft" | "scheduled" | "sending" | "sent" | "partial";

type Campaign = {
  id: string;
  name: string;
  subject: string;
  status: CampaignStatus;
  recipients: number;
  stats: { sent: number; failed: number };
  sent_at: string | null;
  created_at: string | null;
};

type Stats = {
  campaigns: { total: number; sent: number; draft: number; scheduled: number };
  emails_sent: number;
  emails_failed: number;
};

type ProviderSettings = {
  provider: string;
  from_name: string;
  from_email: string;
  credentials: Record<string, string>;
};

type Tab = "campaigns" | "settings";

// ── API helpers ───────────────────────────────────────────────────────────────

function headers(): Record<string, string> {
  const t = getToken();
  return {
    ...(t ? { Authorization: `Bearer ${t}` } : {}),
    "Content-Type": "application/json",
  };
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { ...init, headers: headers() });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_MAP: Record<CampaignStatus, { label: string; cls: string; icon: React.ReactNode }> = {
  draft:     { label: "Draft",     cls: "bg-slate-100 text-slate-600",   icon: <FileText size={11} /> },
  scheduled: { label: "Scheduled", cls: "bg-blue-100 text-blue-700",     icon: <Clock size={11} /> },
  sending:   { label: "Sending…",  cls: "bg-yellow-100 text-yellow-700", icon: <Loader2 size={11} className="animate-spin" /> },
  sent:      { label: "Sent",      cls: "bg-green-100 text-green-700",   icon: <CheckCircle2 size={11} /> },
  partial:   { label: "Partial",   cls: "bg-orange-100 text-orange-700", icon: <AlertCircle size={11} /> },
};

function StatusBadge({ status }: { status: CampaignStatus }) {
  const s = STATUS_MAP[status] ?? STATUS_MAP.draft;
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium", s.cls)}>
      {s.icon} {s.label}
    </span>
  );
}

// ── Create Campaign Modal ─────────────────────────────────────────────────────

function CreateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: "", subject: "", from_name: "", from_email: "",
    body_html: "", recipient_emails: "", recipient_tags: "",
  });

  function set(k: keyof typeof form, v: string) {
    setForm(p => ({ ...p, [k]: v }));
  }

  async function submit(sendNow: boolean) {
    if (!form.name || !form.subject || !form.body_html) {
      toast.error("Name, subject, and body are required");
      return;
    }
    setBusy(true);
    try {
      const body = {
        name: form.name, subject: form.subject,
        from_name: form.from_name, from_email: form.from_email,
        body_html: form.body_html,
        recipient_emails: form.recipient_emails
          ? form.recipient_emails.split(",").map(e => e.trim()).filter(Boolean)
          : [],
        recipient_tags: form.recipient_tags
          ? form.recipient_tags.split(",").map(t => t.trim()).filter(Boolean)
          : [],
      };
      const created = await apiFetch<{ id: string }>("/api/email-marketing/campaigns", {
        method: "POST", body: JSON.stringify(body),
      });
      if (sendNow) {
        await apiFetch(`/api/email-marketing/campaigns/${created.id}/send`, {
          method: "POST", body: JSON.stringify({}),
        });
        toast.success("Campaign sent!");
      } else {
        toast.success("Campaign saved as draft");
      }
      onDone();
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="text-lg font-semibold text-slate-800">New Campaign</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Campaign name *">
              <input value={form.name} onChange={e => set("name", e.target.value)}
                placeholder="e.g. June Flash Sale"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>
            <Field label="Subject line *">
              <input value={form.subject} onChange={e => set("subject", e.target.value)}
                placeholder="e.g. 🔥 50% off this weekend only"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field label="From name">
              <input value={form.from_name} onChange={e => set("from_name", e.target.value)}
                placeholder="Your Brand"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>
            <Field label="From email">
              <input value={form.from_email} onChange={e => set("from_email", e.target.value)}
                placeholder="hello@yourdomain.com"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>
          </div>

          <Field label="Recipients — emails (comma-separated)">
            <input value={form.recipient_emails} onChange={e => set("recipient_emails", e.target.value)}
              placeholder="alice@example.com, bob@example.com"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </Field>

          <Field label="Recipients — contact tags (comma-separated)" hint="Sends to all contacts/customers with these tags">
            <input value={form.recipient_tags} onChange={e => set("recipient_tags", e.target.value)}
              placeholder="vip, newsletter, shopify-customers"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </Field>

          <Field label="Email body (HTML) *">
            <textarea value={form.body_html} onChange={e => set("body_html", e.target.value)}
              rows={8} placeholder="<p>Hello! Here's our latest offer...</p>"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
          </Field>

          {form.body_html && (
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <div className="bg-slate-50 px-4 py-2 flex items-center gap-2 text-xs text-slate-500 font-medium border-b">
                <Eye size={12} /> Preview
              </div>
              <div className="p-4 max-h-48 overflow-y-auto text-sm"
                dangerouslySetInnerHTML={{ __html: form.body_html }} />
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100">
          <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-700">Cancel</button>
          <div className="flex gap-2">
            <button onClick={() => submit(false)} disabled={busy}
              className="flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />}
              Save draft
            </button>
            <button onClick={() => submit(true)} disabled={busy}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
              Send now
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Send / Test modal ─────────────────────────────────────────────────────────

function SendModal({ campaign, onClose, onSent }: {
  campaign: Campaign; onClose: () => void; onSent: () => void;
}) {
  const [testEmail, setTestEmail] = useState("");
  const [busy, setBusy] = useState(false);

  async function sendTest() {
    if (!testEmail) { toast.error("Enter a test email"); return; }
    setBusy(true);
    try {
      await apiFetch(`/api/email-marketing/campaigns/${campaign.id}/send`, {
        method: "POST", body: JSON.stringify({ test_email: testEmail }),
      });
      toast.success(`Test sent to ${testEmail}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Test failed");
    } finally { setBusy(false); }
  }

  async function sendAll() {
    setBusy(true);
    try {
      const res = await apiFetch<{ sent: number; failed: number }>(
        `/api/email-marketing/campaigns/${campaign.id}/send`,
        { method: "POST", body: JSON.stringify({}) }
      );
      toast.success(`Sent to ${res.sent} recipients`);
      onSent();
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Send failed");
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="text-lg font-semibold text-slate-800">Send Campaign</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={20} /></button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div className="bg-slate-50 rounded-xl p-4">
            <p className="font-medium text-slate-800 text-sm">{campaign.name}</p>
            <p className="text-xs text-slate-500 mt-0.5">Subject: {campaign.subject}</p>
          </div>
          <Field label="Send a test first (optional)">
            <div className="flex gap-2">
              <input value={testEmail} onChange={e => setTestEmail(e.target.value)}
                placeholder="your@email.com"
                className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              <button onClick={sendTest} disabled={busy}
                className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                Test
              </button>
            </div>
          </Field>
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-slate-100">
          <button onClick={onClose}
            className="flex-1 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button onClick={sendAll} disabled={busy}
            className="flex-1 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 flex items-center justify-center gap-2">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
            Send to all
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Provider Settings ─────────────────────────────────────────────────────────

const PROVIDERS = [
  { value: "platform", label: "Zilo Platform (recommended)", desc: "Built-in email via Resend. Zero setup required." },
  { value: "sendgrid", label: "SendGrid",    desc: "Use your own SendGrid API key." },
  { value: "brevo",    label: "Brevo",       desc: "Use your own Brevo (Sendinblue) API key." },
  { value: "mailgun",  label: "Mailgun",     desc: "Use your Mailgun account and domain." },
  { value: "smtp",     label: "Custom SMTP", desc: "Any SMTP server (Gmail, Outlook, custom)." },
];

function SettingsPanel() {
  const [cfg, setCfg] = useState<ProviderSettings>({
    provider: "platform", from_name: "", from_email: "", credentials: {},
  });
  const [saving, setSaving] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    apiFetch<ProviderSettings>("/api/email-marketing/settings")
      .then(d => setCfg(d))
      .catch(() => {});
  }, []);

  function setCred(k: string, v: string) {
    setCfg(p => ({ ...p, credentials: { ...p.credentials, [k]: v } }));
  }

  async function save() {
    setSaving(true);
    try {
      await apiFetch("/api/email-marketing/settings", { method: "POST", body: JSON.stringify(cfg) });
      toast.success("Settings saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally { setSaving(false); }
  }

  async function test() {
    if (!testEmail) { toast.error("Enter a test email address"); return; }
    setTesting(true);
    try {
      const res = await apiFetch<{ ok: boolean; message: string }>(
        "/api/email-marketing/settings/test",
        { method: "POST", body: JSON.stringify({ ...cfg, test_email: testEmail }) }
      );
      toast.success(res.message);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Test failed");
    } finally { setTesting(false); }
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* Provider picker */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="font-semibold text-slate-800">Email Provider</h3>
          <p className="text-sm text-slate-500 mt-0.5">Choose how emails are sent from your account</p>
        </div>
        <div className="p-6 space-y-3">
          {PROVIDERS.map(p => (
            <label key={p.value}
              className={cn("flex items-start gap-3 p-4 border-2 rounded-xl cursor-pointer transition-colors",
                cfg.provider === p.value
                  ? "border-indigo-500 bg-indigo-50"
                  : "border-slate-200 hover:border-slate-300")}>
              <input type="radio" name="provider" value={p.value}
                checked={cfg.provider === p.value}
                onChange={() => setCfg(c => ({ ...c, provider: p.value }))}
                className="mt-0.5 accent-indigo-600" />
              <div>
                <div className="text-sm font-medium text-slate-800">{p.label}</div>
                <div className="text-xs text-slate-500">{p.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Sender details + credentials */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="font-semibold text-slate-800">Sender Details</h3>
        </div>
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="From name">
              <input value={cfg.from_name} onChange={e => setCfg(c => ({ ...c, from_name: e.target.value }))}
                placeholder="Your Brand"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>
            <Field label="From email">
              <input value={cfg.from_email} onChange={e => setCfg(c => ({ ...c, from_email: e.target.value }))}
                placeholder="hello@yourdomain.com"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>
          </div>

          {cfg.provider === "sendgrid" && (
            <Field label="SendGrid API Key">
              <input type="password" value={cfg.credentials.api_key ?? ""}
                onChange={e => setCred("api_key", e.target.value)} placeholder="SG.xxxxxx"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>
          )}

          {cfg.provider === "brevo" && (
            <Field label="Brevo API Key">
              <input type="password" value={cfg.credentials.api_key ?? ""}
                onChange={e => setCred("api_key", e.target.value)} placeholder="xkeysib-xxxxxx"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </Field>
          )}

          {cfg.provider === "mailgun" && (
            <div className="grid grid-cols-2 gap-4">
              <Field label="Mailgun API Key">
                <input type="password" value={cfg.credentials.api_key ?? ""}
                  onChange={e => setCred("api_key", e.target.value)} placeholder="key-xxxxxx"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </Field>
              <Field label="Mailgun Domain">
                <input value={cfg.credentials.domain ?? ""}
                  onChange={e => setCred("domain", e.target.value)} placeholder="mg.yourdomain.com"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </Field>
            </div>
          )}

          {cfg.provider === "smtp" && (
            <div className="grid grid-cols-2 gap-4">
              <Field label="SMTP Host">
                <input value={cfg.credentials.host ?? ""}
                  onChange={e => setCred("host", e.target.value)} placeholder="smtp.gmail.com"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </Field>
              <Field label="Port">
                <input value={cfg.credentials.port ?? "587"}
                  onChange={e => setCred("port", e.target.value)} placeholder="587"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </Field>
              <Field label="Username">
                <input value={cfg.credentials.username ?? ""}
                  onChange={e => setCred("username", e.target.value)} placeholder="you@gmail.com"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </Field>
              <Field label="Password">
                <input type="password" value={cfg.credentials.password ?? ""}
                  onChange={e => setCred("password", e.target.value)} placeholder="App password"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </Field>
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-100 flex items-center gap-3">
          <div className="flex gap-2 flex-1">
            <input value={testEmail} onChange={e => setTestEmail(e.target.value)}
              placeholder="Test to: your@email.com"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <button onClick={test} disabled={testing}
              className="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 flex items-center gap-1.5">
              {testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
              Test
            </button>
          </div>
          <button onClick={save} disabled={saving}
            className="px-5 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2">
            {saving && <Loader2 size={13} className="animate-spin" />}
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Small helpers ─────────────────────────────────────────────────────────────

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-slate-700">{label}</label>
      {children}
      {hint && <p className="text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function EmailMarketingPage() {
  const [tab, setTab] = useState<Tab>("campaigns");
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [sendTarget, setSendTarget] = useState<Campaign | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, s] = await Promise.all([
        apiFetch<{ campaigns: Campaign[] }>("/api/email-marketing/campaigns"),
        apiFetch<Stats>("/api/email-marketing/stats"),
      ]);
      setCampaigns(c.campaigns);
      setStats(s);
    } catch {
      toast.error("Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function deleteCampaign(id: string) {
    setDeleting(id);
    try {
      await apiFetch(`/api/email-marketing/campaigns/${id}`, { method: "DELETE" });
      setCampaigns(p => p.filter(c => c.id !== id));
      toast.success("Deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  }

  const statCards = stats
    ? [
        { label: "Total campaigns",  value: stats.campaigns.total,  icon: <Mail size={18} />,         color: "text-indigo-600 bg-indigo-50" },
        { label: "Sent",             value: stats.campaigns.sent,   icon: <CheckCircle2 size={18} />, color: "text-green-600 bg-green-50" },
        { label: "Emails delivered", value: stats.emails_sent,      icon: <Send size={18} />,         color: "text-blue-600 bg-blue-50" },
        { label: "Drafts",           value: stats.campaigns.draft,  icon: <FileText size={18} />,     color: "text-slate-600 bg-slate-100" },
      ]
    : [];

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-sm">
              <Mail size={20} className="text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-800">Email Marketing</h1>
              <p className="text-sm text-slate-500">Create and send campaigns to your contacts</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load}
              className="p-2 text-slate-400 hover:text-slate-600 transition-colors rounded-lg hover:bg-slate-100">
              <RefreshCw size={17} />
            </button>
            {tab === "campaigns" && (
              <button onClick={() => setShowCreate(true)}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 shadow-sm">
                <Plus size={15} /> New Campaign
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">
        {/* Stats */}
        {statCards.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {statCards.map(s => (
              <div key={s.label} className="bg-white rounded-2xl border border-slate-200 p-4 flex items-center gap-3">
                <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", s.color)}>
                  {s.icon}
                </div>
                <div>
                  <div className="text-2xl font-bold text-slate-800">{s.value.toLocaleString()}</div>
                  <div className="text-xs text-slate-500">{s.label}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 bg-slate-100 rounded-xl p-1 w-fit">
          {([ { id: "campaigns" as Tab, label: "Campaigns", icon: <BarChart2 size={14} /> },
              { id: "settings"  as Tab, label: "Settings",  icon: <Settings size={14} /> },
          ]).map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={cn("flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                tab === t.id ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600 hover:text-slate-800")}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* Campaigns list */}
        {tab === "campaigns" && (
          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 size={24} className="animate-spin text-indigo-500" />
              </div>
            ) : campaigns.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center px-6">
                <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center mb-4">
                  <Mail size={28} className="text-indigo-400" />
                </div>
                <h3 className="text-lg font-semibold text-slate-700 mb-1">No campaigns yet</h3>
                <p className="text-sm text-slate-400 mb-5 max-w-xs">
                  Create your first email campaign to reach your customers.
                </p>
                <button onClick={() => setShowCreate(true)}
                  className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700">
                  <Plus size={15} /> Create campaign
                </button>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100 text-left">
                    {["Campaign", "Status", "Sent", "Date", ""].map(h => (
                      <th key={h} className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider
                        first:table-cell [&:nth-child(2)]:hidden md:[&:nth-child(2)]:table-cell
                        [&:nth-child(3)]:hidden lg:[&:nth-child(3)]:table-cell
                        [&:nth-child(4)]:hidden lg:[&:nth-child(4)]:table-cell">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {campaigns.map(c => (
                    <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-5 py-4">
                        <div className="font-medium text-slate-800 text-sm">{c.name}</div>
                        <div className="text-xs text-slate-400 mt-0.5 truncate max-w-xs">{c.subject}</div>
                      </td>
                      <td className="px-5 py-4 hidden md:table-cell">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="px-5 py-4 hidden lg:table-cell">
                        {(c.stats?.sent ?? 0) > 0 ? (
                          <div className="flex items-center gap-1 text-sm">
                            <Users size={12} className="text-slate-400" />
                            <span className="text-slate-700">{c.stats.sent.toLocaleString()}</span>
                            {(c.stats.failed ?? 0) > 0 && (
                              <span className="text-red-400 text-xs ml-1">({c.stats.failed} failed)</span>
                            )}
                          </div>
                        ) : <span className="text-xs text-slate-400">—</span>}
                      </td>
                      <td className="px-5 py-4 hidden lg:table-cell">
                        <span className="text-xs text-slate-400">
                          {c.sent_at
                            ? new Date(c.sent_at).toLocaleDateString()
                            : c.created_at
                              ? new Date(c.created_at).toLocaleDateString()
                              : "—"}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-1 justify-end">
                          {c.status === "draft" && (
                            <button onClick={() => setSendTarget(c)}
                              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-medium hover:bg-indigo-100">
                              <Play size={11} /> Send
                            </button>
                          )}
                          <button onClick={() => deleteCampaign(c.id)} disabled={deleting === c.id}
                            className="p-1.5 text-slate-400 hover:text-red-500 transition-colors disabled:opacity-50 rounded">
                            {deleting === c.id
                              ? <Loader2 size={13} className="animate-spin" />
                              : <Trash2 size={13} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Settings tab */}
        {tab === "settings" && <SettingsPanel />}
      </div>

      {/* Modals */}
      {showCreate && (
        <CreateModal onClose={() => setShowCreate(false)} onDone={load} />
      )}
      {sendTarget && (
        <SendModal campaign={sendTarget} onClose={() => setSendTarget(null)} onSent={load} />
      )}
    </div>
  );
}
