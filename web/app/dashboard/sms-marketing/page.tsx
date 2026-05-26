"use client";

import { useCallback, useEffect, useState } from "react";
import {
  MessageSquare, Plus, Send, Trash2, BarChart2, Settings,
  Loader2, CheckCircle2, Clock, FileText, RefreshCw, X,
  Users, AlertCircle, Inbox, Smartphone, ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { WORLD_COUNTRIES, getCountryByCode } from "@/lib/worldCountries";
import { SmsApplicationForm, type SmsFormValues } from "@/components/sms/SmsApplicationForm";

const PHONE_PLACEHOLDERS: Record<string, string> = {
  FI: "+358401234567",
  CA: "+14165551234",
  US: "+14155551234",
  GB: "+447911123456",
  KE: "+254712345678",
};

function phonePlaceholder(countryCode: string) {
  return PHONE_PLACEHOLDERS[countryCode] || "+1234567890 (include country code)";
}

function countryCodeFromSettings(settings: { country_code?: string; country?: string }) {
  const raw = (settings.country_code || "").trim().toUpperCase();
  if (raw && getCountryByCode(raw)) return raw;
  const name = (settings.country || "").trim();
  if (name) {
    const match = WORLD_COUNTRIES.find((c) => c.name === name);
    if (match) return match.code;
  }
  return "";
}

type Tab = "campaigns" | "inbox" | "settings";

type Campaign = {
  id: string;
  name: string;
  template_id: string;
  template_name?: string;
  template_parameters?: Record<string, string>;
  status: "draft" | "sending" | "sent" | "partial";
  stats: { sent: number; failed: number; delivered?: number };
  recipient_phones?: string[];
  recipient_tags?: string[];
  require_opt_in?: boolean;
  sent_at?: string;
  created_at: string;
};

type SmsMessage = {
  id: string;
  direction: "inbound" | "outbound";
  phone: string;
  body: string;
  status: string;
  created_at: string;
};

type SentTemplate = {
  id: string;
  name: string;
  category: string;
  status: string;
  channels: string[];
  variables?: string[];
};

type Stats = {
  campaigns: { total: number; sent: number; draft: number };
  messages_sent: number;
  messages_failed: number;
  customers_opted_in: number;
  inbound_messages: number;
};

type SmsSettings = {
  provider: "platform" | "own";
  api_key?: string;
  sentdm_customer_id?: string;
  sentdm_profile_id?: string;
  sender_name?: string;
  from_number?: string;
  default_template_id?: string;
  country_code?: string;
  webhook_secret?: string;
  notifications_enabled?: boolean;
  owner_notification_phone?: string;
};

type SmsCapabilities = {
  platform_notifications: boolean;
  owner_phone_linked: boolean;
  marketing_sms: boolean;
};

type Application = {
  status: "none" | "pending" | "approved" | "active" | "rejected";
  business_name?: string;
  business_country?: string;
  sender_name?: string;
  from_number?: string;
  profile_status?: string;
  use_case?: string;
  created_at?: string;
};

function StatusBadge({ status }: { status: Campaign["status"] }) {
  const map: Record<string, { label: string; cls: string }> = {
    draft:   { label: "Draft",   cls: "bg-slate-100 text-slate-600" },
    sending: { label: "Sending", cls: "bg-yellow-100 text-yellow-700" },
    sent:    { label: "Sent",    cls: "bg-green-100 text-green-700" },
    partial: { label: "Partial", cls: "bg-orange-100 text-orange-700" },
  };
  const s = map[status] ?? map.draft;
  return (
    <span className={cn("inline-flex px-2 py-0.5 rounded-full text-xs font-medium", s.cls)}>
      {s.label}
    </span>
  );
}

function CampaignModal({
  templates,
  phoneExample,
  onClose,
  onSaved,
}: {
  templates: SentTemplate[];
  phoneExample: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [paramsJson, setParamsJson] = useState('{"name": "Customer"}');
  const [phones, setPhones] = useState("");
  const [tags, setTags] = useState("");
  const [requireOptIn, setRequireOptIn] = useState(true);
  const [saving, setSaving] = useState(false);

  const selected = templates.find((t) => t.id === templateId);

  async function handleSave(sendAfter = false) {
    if (!name.trim() || !templateId) {
      toast.error("Name and template are required");
      return;
    }
    let template_parameters: Record<string, string> = {};
    try {
      template_parameters = JSON.parse(paramsJson || "{}");
    } catch {
      toast.error("Template parameters must be valid JSON");
      return;
    }
    setSaving(true);
    try {
      const res = await api.post<{ id: string }>("/sms-marketing/campaigns", {
        name: name.trim(),
        template_id: templateId,
        template_name: selected?.name || "",
        template_parameters,
        recipient_phones: phones.split(/[\n,;]+/).map((p) => p.trim()).filter(Boolean),
        recipient_tags: tags.split(/[,;]+/).map((t) => t.trim()).filter(Boolean),
        require_opt_in: requireOptIn,
      });
      if (sendAfter && res.id) {
        await api.post(`/sms-marketing/campaigns/${res.id}/send`, {});
        toast.success("Campaign sent");
      } else {
        toast.success("Campaign saved");
      }
      onSaved();
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to save campaign");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="font-semibold text-slate-800">New SMS Campaign</h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <label className="text-sm font-medium text-slate-700">Campaign name</label>
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Spring promo"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700">Message template</label>
            <select
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
            >
              <option value="">Select template…</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.category})
                </option>
              ))}
            </select>
            {selected?.variables?.length ? (
              <p className="text-xs text-slate-500 mt-1">
                Variables: {selected.variables.join(", ")}
              </p>
            ) : null}
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700">Template parameters (JSON)</label>
            <textarea
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm font-mono h-24"
              value={paramsJson}
              onChange={(e) => setParamsJson(e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700">Phone numbers (optional)</label>
            <textarea
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm h-20"
              value={phones}
              onChange={(e) => setPhones(e.target.value)}
              placeholder={`${phoneExample}, one per line or comma-separated`}
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700">Tags (optional)</label>
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="VIP, Returning"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={requireOptIn}
              onChange={(e) => setRequireOptIn(e.target.checked)}
            />
            Only send to customers with SMS opt-in
          </label>
        </div>
        <div className="flex gap-2 px-6 py-4 border-t bg-slate-50 rounded-b-2xl">
          <button
            type="button"
            disabled={saving}
            onClick={() => handleSave(false)}
            className="flex-1 py-2 rounded-lg border text-sm font-medium hover:bg-white"
          >
            Save draft
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => handleSave(true)}
            className="flex-1 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-dark disabled:opacity-50"
          >
            {saving ? <Loader2 size={16} className="animate-spin mx-auto" /> : "Save & send"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SmsMarketingPage() {
  const [tab, setTab] = useState<Tab>("campaigns");
  const [loading, setLoading] = useState(true);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [messages, setMessages] = useState<SmsMessage[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [templates, setTemplates] = useState<SentTemplate[]>([]);
  const [settings, setSettings] = useState<SmsSettings>({ provider: "platform" });
  const [capabilities, setCapabilities] = useState<SmsCapabilities>({
    platform_notifications: true,
    owner_phone_linked: false,
    marketing_sms: false,
  });
  const [application, setApplication] = useState<Application>({ status: "none" });
  const [showModal, setShowModal] = useState(false);

  const [accountCountry, setAccountCountry] = useState("");
  const [appPrefill, setAppPrefill] = useState<Partial<SmsFormValues>>({});
  const [testPhone, setTestPhone] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);
  const [submittingApp, setSubmittingApp] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cRes, sRes, setRes, mRes, userSetRes] = await Promise.all([
        api.get<{ campaigns: Campaign[] }>("/sms-marketing/campaigns"),
        api.get<Stats>("/sms-marketing/stats"),
        api.get<{ settings: SmsSettings; application: Application; capabilities: SmsCapabilities }>("/sms-marketing/settings"),
        api.get<{ messages: SmsMessage[] }>("/sms-marketing/messages?limit=50"),
        api.get<{ country_code?: string; country?: string; business_name?: string; owner_name?: string; email?: string }>("/settings").catch(() => null),
      ]);
      setCampaigns(cRes.campaigns || []);
      setStats(sRes);
      setSettings(setRes.settings || { provider: "platform" });
      setCapabilities(setRes.capabilities || {
        platform_notifications: true,
        owner_phone_linked: false,
        marketing_sms: false,
      });
      setApplication(setRes.application || { status: "none" });

      const resolvedCountry =
        setRes.application?.business_country ||
        setRes.settings?.country_code ||
        (userSetRes ? countryCodeFromSettings(userSetRes) : "");
      if (resolvedCountry) {
        setAccountCountry(resolvedCountry);
        setAppPrefill({
          business_country: resolvedCountry,
          business_name: userSetRes?.business_name || "",
          contact_name: userSetRes?.owner_name || "",
          contact_email: userSetRes?.email || "",
        });
      }
      setMessages(mRes.messages || []);
      try {
        const tRes = await api.get<{ templates: SentTemplate[] }>("/sms-marketing/templates");
        setTemplates(tRes.templates || []);
      } catch {
        setTemplates([]);
      }
    } catch (e) {
      console.error(e);
      toast.error("Failed to load SMS marketing data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (application.status !== "pending") return;
    const timer = setInterval(() => {
      void loadAll();
    }, 30000);
    return () => clearInterval(timer);
  }, [application.status, loadAll]);

  async function handleDeleteCampaign(id: string) {
    if (!confirm("Delete this campaign?")) return;
    try {
      await api.delete(`/sms-marketing/campaigns/${id}`);
      toast.success("Campaign deleted");
      void loadAll();
    } catch {
      toast.error("Could not delete campaign");
    }
  }

  async function handleSendCampaign(id: string) {
    try {
      await api.post(`/sms-marketing/campaigns/${id}/send`, {});
      toast.success("Campaign queued");
      void loadAll();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Send failed");
    }
  }

  async function saveSettings() {
    setSavingSettings(true);
    try {
      await api.post("/sms-marketing/settings", settings);
      toast.success("Settings saved");
      void loadAll();
    } catch {
      toast.error("Could not save settings");
    } finally {
      setSavingSettings(false);
    }
  }

  async function submitApplication(formValues: SmsFormValues) {
    setSubmittingApp(true);
    try {
      await api.post("/sms-marketing/application", {
        ...formValues,
        business_country: formValues.business_country || accountCountry,
      });
      toast.success("Application submitted");
      void loadAll();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Application failed");
    } finally {
      setSubmittingApp(false);
    }
  }

  async function sendTestSms(mode: "platform" | "marketing") {
    if (!testPhone.trim()) {
      toast.error("Enter a test phone number");
      return;
    }
    try {
      await api.post("/sms-marketing/settings/test", {
        test_phone: testPhone,
        sandbox: true,
        mode,
        default_template_id: settings.default_template_id,
      });
      toast.success(mode === "marketing" ? "Marketing test queued" : "Notification test queued");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Test send failed");
    }
  }

  const isActive = application.status === "active" || application.status === "approved";
  const isPending = application.status === "pending";
  const canSendCampaigns = capabilities.marketing_sms;
  const platformReady = capabilities.platform_notifications;
  const displaySender = application.sender_name || settings.sender_name;
  const displayNumber = application.from_number || settings.from_number;
  const formCountry = accountCountry;
  const phoneExample = phonePlaceholder(formCountry);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "campaigns", label: "Campaigns", icon: <Send size={16} /> },
    { id: "inbox", label: "Inbox", icon: <Inbox size={16} /> },
    { id: "settings", label: "Setup", icon: <Settings size={16} /> },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 className="animate-spin text-brand" size={32} />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Smartphone className="text-brand" size={26} />
            SMS Marketing
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Two ways to use SMS: get notifications from Zilo on your phone, and/or apply for your own sender to message customers.
          </p>
        </div>
        {tab === "campaigns" && canSendCampaigns && (
          <button
            type="button"
            onClick={() => setShowModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-dark"
          >
            <Plus size={16} /> New campaign
          </button>
        )}
      </div>

      {!canSendCampaigns && tab === "campaigns" && (
        <div className={cn(
          "rounded-xl border px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3",
          isPending ? "bg-yellow-50 border-yellow-200" : "bg-blue-50 border-blue-200"
        )}>
          <div className="flex items-start gap-3">
            {isPending ? (
              <Clock size={20} className="text-yellow-700 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle size={20} className="text-blue-700 shrink-0 mt-0.5" />
            )}
            <div>
              <p className="font-medium text-slate-800">
                {isPending
                  ? "Your SMS marketing account is being set up"
                  : "Apply for your own SMS sender to run campaigns"}
              </p>
              <p className="text-sm text-slate-600 mt-0.5">
                {isPending
                  ? displaySender
                    ? `We're setting up "${displaySender}" for customer campaigns.`
                    : "We're setting up your business sender — we'll notify you when it's ready."
                  : platformReady
                    ? "Customer notifications via Zilo are available under Setup. Campaigns need your own SMS marketing account."
                    : "Under Setup, link your number for Zilo alerts and/or apply for your own business sender."}
              </p>
            </div>
          </div>
          {!isPending && (
            <button
              type="button"
              onClick={() => setTab("settings")}
              className="shrink-0 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-dark"
            >
              Go to Setup
            </button>
          )}
        </div>
      )}

      {platformReady && !canSendCampaigns && tab !== "campaigns" && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          Customer SMS notifications are on. Apply under Setup when you want your own sender name for campaigns.
        </div>
      )}

      {canSendCampaigns && isActive && (
        <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-900 space-y-1">
          <p className="flex items-center gap-2 font-medium">
            <CheckCircle2 size={18} />
            SMS is active — create a campaign or check customer replies in Inbox.
          </p>
          {(displaySender || displayNumber) && (
            <p className="text-green-800 pl-7">
              {displaySender && <>Sender name: <span className="font-medium">{displaySender}</span></>}
              {displaySender && displayNumber && " · "}
              {displayNumber && <>Number: <span className="font-medium">{displayNumber}</span></>}
            </p>
          )}
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "Campaigns", value: stats.campaigns.total, icon: FileText },
            { label: "Messages sent", value: stats.messages_sent, icon: Send },
            { label: "Opted in", value: stats.customers_opted_in, icon: Users },
            { label: "Inbound", value: stats.inbound_messages, icon: Inbox },
          ].map(({ label, value, icon: Icon }) => (
            <div key={label} className="bg-white border rounded-xl p-4">
              <div className="flex items-center gap-2 text-slate-500 text-xs">
                <Icon size={14} /> {label}
              </div>
              <p className="text-2xl font-semibold text-slate-900 mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-1 border-b">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t.id
                ? "border-brand text-brand-dark"
                : "border-transparent text-slate-500 hover:text-slate-700"
            )}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {tab === "campaigns" && (
        <div className="bg-white border rounded-xl overflow-hidden">
          {campaigns.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <MessageSquare size={40} className="mx-auto mb-3 opacity-40" />
              <p>No campaigns yet. Create one to start sending SMS.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="text-left px-4 py-3 font-medium">Name</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="text-left px-4 py-3 font-medium">Sent</th>
                  <th className="text-right px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id} className="border-t">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{c.name}</p>
                      <p className="text-xs text-slate-400 truncate max-w-xs">{c.template_name || c.template_id}</p>
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={c.status} /></td>
                    <td className="px-4 py-3 text-slate-600">
                      {c.stats?.sent ?? 0} sent
                      {(c.stats?.failed ?? 0) > 0 && (
                        <span className="text-red-500 ml-1">({c.stats.failed} failed)</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      {c.status === "draft" && (
                        <button
                          type="button"
                          onClick={() => handleSendCampaign(c.id)}
                          className="text-brand hover:underline text-xs font-medium"
                        >
                          Send
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDeleteCampaign(c.id)}
                        className="text-red-500 hover:underline text-xs"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "inbox" && (
        <div className="bg-white border rounded-xl divide-y max-h-[60vh] overflow-y-auto">
          {messages.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <Inbox size={40} className="mx-auto mb-3 opacity-40" />
              <p>Inbound and outbound SMS will appear here.</p>
              <p className="text-xs mt-2">Replies from customers will show here once your account is active.</p>
            </div>
          ) : (
            messages.map((m) => (
              <div key={m.id} className="px-4 py-3 flex gap-3">
                <div className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                  m.direction === "inbound" ? "bg-blue-100 text-blue-600" : "bg-green-100 text-green-600"
                )}>
                  <MessageSquare size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-800">{m.phone}</span>
                    <span className="text-xs text-slate-400 capitalize">{m.direction}</span>
                    <span className="text-xs text-slate-400">{m.status}</span>
                  </div>
                  <p className="text-sm text-slate-600 mt-0.5 break-words">{m.body || "—"}</p>
                  <p className="text-xs text-slate-400 mt-1">
                    {new Date(m.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {tab === "settings" && (
        <div className="space-y-6">
          {/* Mode 1: Platform / Zilo notifications */}
          <div className="bg-white border rounded-xl p-6 space-y-4">
            <h2 className="font-semibold text-slate-800">Notifications from Zilo</h2>
            <p className="text-sm text-slate-500">
              Link your mobile number to receive SMS alerts from us, and optionally send order-style notifications to customers who opted in — no marketing application required.
            </p>
            <div>
              <label className="text-sm font-medium text-slate-700">Your mobile number</label>
              <input
                className="mt-1 w-full max-w-md border rounded-lg px-3 py-2 text-sm"
                placeholder={phoneExample}
                value={settings.owner_notification_phone || ""}
                onChange={(e) => setSettings({ ...settings, owner_notification_phone: e.target.value })}
              />
              <p className="text-xs text-slate-400 mt-1">We&apos;ll text this number about SMS activity and account updates.</p>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={settings.notifications_enabled !== false}
                onChange={(e) => setSettings({ ...settings, notifications_enabled: e.target.checked })}
              />
              Send SMS to customers who opted in (order updates, reminders, etc.) via Zilo
            </label>
            <button
              type="button"
              disabled={savingSettings}
              onClick={saveSettings}
              className="py-2 px-4 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-dark disabled:opacity-50"
            >
              {savingSettings ? "Saving…" : "Save notification settings"}
            </button>
            {platformReady && (
              <div className="pt-2 border-t">
                <p className="text-sm font-medium text-slate-700 mb-2">Test customer notification</p>
                <div className="flex gap-2 max-w-md">
                  <input
                    className="flex-1 border rounded-lg px-3 py-2 text-sm"
                    placeholder={phoneExample}
                    value={testPhone}
                    onChange={(e) => setTestPhone(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => void sendTestSms("platform")}
                    className="px-4 py-2 rounded-lg border text-sm font-medium hover:bg-slate-50"
                  >
                    Send test
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Mode 2: Own SMS marketing account */}
          <div className="bg-white border rounded-xl p-6">
            <h2 className="font-semibold text-slate-800 flex items-center gap-2">
              <ShieldCheck size={18} className="text-brand" />
              Your own SMS marketing account
            </h2>
            <p className="text-sm text-slate-500 mt-1 mb-4">
              Apply to send campaigns under your business name and number. Required for the Campaigns tab and inbound replies on your sender.
            </p>
            {application.status === "none" || application.status === "rejected" ? (
              <SmsApplicationForm
                defaultCountry={accountCountry}
                prefill={appPrefill}
                submitting={submittingApp}
                onSubmit={submitApplication}
              />
            ) : (
              <div className="space-y-2">
                <div className={cn(
                  "inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium",
                  application.status === "pending" ? "bg-yellow-100 text-yellow-800" : "bg-green-100 text-green-800"
                )}>
                  {application.status === "pending" ? <Clock size={14} /> : <CheckCircle2 size={14} />}
                  {application.status === "pending" ? "Under review — setting up your SMS account" : "Account active"}
                </div>
                {application.business_name && (
                  <p className="text-sm text-slate-600">Business: {application.business_name}</p>
                )}
                {displaySender && application.status === "pending" && (
                  <p className="text-sm text-slate-600">Sender name: {displaySender}</p>
                )}
                {displayNumber && isActive && (
                  <p className="text-sm text-slate-600">Number: {displayNumber}</p>
                )}
              </div>
            )}
          </div>

          {canSendCampaigns && (
            <div className="bg-white border rounded-xl p-6">
              <h2 className="font-semibold text-slate-800 mb-1">Test your marketing sender</h2>
              <p className="text-sm text-slate-500 mb-3">Sends using your business name and number.</p>
              <div className="flex gap-2 max-w-md">
                <input
                  className="flex-1 border rounded-lg px-3 py-2 text-sm"
                  placeholder={phoneExample}
                  value={testPhone}
                  onChange={(e) => setTestPhone(e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => void sendTestSms("marketing")}
                  className="px-4 py-2 rounded-lg border text-sm font-medium hover:bg-slate-50"
                >
                  Send test
                </button>
              </div>
            </div>
          )}

          {/* Opt-in info */}
          <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-900">
            <p className="font-medium flex items-center gap-2">
              <Users size={16} /> Customer SMS opt-in
            </p>
            <p className="mt-1 text-green-800">
              Customers can opt in from their profile or by replying START. They can opt out anytime with STOP.
              Campaigns with &quot;require opt-in&quot; only reach customers marked as opted in.
            </p>
          </div>
        </div>
      )}

      {showModal && (
        <CampaignModal
          templates={templates}
          phoneExample={phoneExample}
          onClose={() => setShowModal(false)}
          onSaved={loadAll}
        />
      )}
    </div>
  );
}
