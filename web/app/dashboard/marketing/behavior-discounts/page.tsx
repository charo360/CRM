"use client";

import React, { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { getBusinessId } from "@/lib/auth";
import {
  Zap, Copy, Check, Code2, BarChart2, Loader2, TrendingUp,
  Gift, Plus, Play, Pause, Trash2, RefreshCw, Save,
  Layout, X,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Campaign {
  id?: string;
  _id?: string;
  name: string;
  trigger_event: string;
  discount_type: string;
  discount_value: number;
  delivery_method: string;
  message_template: string;
  active: boolean;
  sent_count?: number;
  conversion_count?: number;
}

interface Analytics {
  total_sent: number;
  total_conversions: number;
  conversion_rate: number;
}

// ── Campaign Templates ─────────────────────────────────────────────────────────
const TEMPLATES = [
  { id: "exit_intent", name: "Exit Intent Saver", description: "Catch visitors before they leave", trigger_event: "exit_intent", discount_value: 15, delivery_method: "popup", icon: "🚪", badge: "Most Popular", badgeColor: "bg-red-100 text-red-700", color: "bg-red-50 border-red-200", message_template: "Wait! Don't leave yet 👋\n\nUse code {discount_code} for {discount_value}% off!\nLimited time offer." },
  { id: "cart_abandon", name: "Cart Recovery", description: "Recover abandoned carts automatically", trigger_event: "cart_abandoned", discount_value: 10, delivery_method: "popup", icon: "🛒", badge: "High ROI", badgeColor: "bg-orange-100 text-orange-700", color: "bg-orange-50 border-orange-200", message_template: "You left something behind! 🛒\n\nUse code {discount_code} for {discount_value}% off your order." },
  { id: "first_visit", name: "First Visit Welcome", description: "Welcome new visitors with an exclusive offer", trigger_event: "first_time_visitor", discount_value: 20, delivery_method: "popup", icon: "👋", badge: "New Visitors", badgeColor: "bg-green-100 text-green-700", color: "bg-green-50 border-green-200", message_template: "Welcome! 🎉 First visit special!\n\nGet {discount_value}% off with code {discount_code}." },
  { id: "time_on_site", name: "Engaged Visitor", description: "Reward visitors who spend time browsing", trigger_event: "time_on_site", discount_value: 12, delivery_method: "popup", icon: "⏱️", badge: "Engaged", badgeColor: "bg-blue-100 text-blue-700", color: "bg-blue-50 border-blue-200", message_template: "Thanks for browsing! 🎁\n\nHere's {discount_value}% off with code {discount_code}." },
  { id: "product_view", name: "Product Interest", description: "Convert visitors viewing the same product twice", trigger_event: "product_view_no_purchase", discount_value: 8, delivery_method: "popup", icon: "👁️", badge: "Smart", badgeColor: "bg-purple-100 text-purple-700", color: "bg-purple-50 border-purple-200", message_template: "Still thinking? 🤔\n\nGet {discount_value}% off now with code {discount_code}. Don't miss out!" },
  { id: "returning", name: "Returning Customer", description: "Reward loyal visitors who come back", trigger_event: "returning_visitor", discount_value: 5, delivery_method: "banner", icon: "🌟", badge: "Loyalty", badgeColor: "bg-yellow-100 text-yellow-700", color: "bg-yellow-50 border-yellow-200", message_template: "Welcome back! 🌟\n\nEnjoy $5 off with code {discount_code}." },
];

const TRIGGER_LABELS: Record<string, string> = {
  exit_intent: "Exit Intent",
  cart_abandoned: "Cart Abandoned",
  first_time_visitor: "First Visit",
  time_on_site: "Time on Site",
  product_view_no_purchase: "Product Interest",
  returning_visitor: "Returning Visitor",
  browsed_product: "Product Browsing",
  visited_multiple_times: "Returning Visitor",
  high_value_visitor: "High Value Visitor",
  page_views_threshold: "Page Views",
};

const DELIVERY_ICONS: Record<string, string> = {
  popup: "🎯", banner: "📢", email: "📧", sms: "💬", whatsapp: "📱",
};

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function BehaviorTrackerPage() {
  const [activeTab, setActiveTab] = useState<"overview" | "install" | "campaigns" | "analytics">("overview");
  const [enabled, setEnabled] = useState(false);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [businessId, setBusinessId] = useState<string | null>(null);
  const [ga4Id, setGa4Id] = useState("");
  const [snippetCopied, setSnippetCopied] = useState(false);
  const [activatingTemplate, setActivatingTemplate] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [togglingEnabled, setTogglingEnabled] = useState(false);
  const [newCampaign, setNewCampaign] = useState({
    name: "", trigger_event: "exit_intent", discount_type: "percentage",
    discount_value: 10, delivery_method: "popup", active: true,
    message_template: "Use code {discount_code} for {discount_value}% off!",
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [settings, campsRes] = await Promise.all([
        api.get<{ behavior_discounts_enabled?: boolean; ga4_measurement_id?: string }>("/settings"),
        api.get<{ campaigns?: Campaign[] } | Campaign[]>("/marketing/behavior-discounts/campaigns").catch(() => ({ campaigns: [] })),
      ]);
      setEnabled(settings.behavior_discounts_enabled || false);
      setGa4Id(settings.ga4_measurement_id || "");
      const camps = Array.isArray(campsRes) ? campsRes : (campsRes as { campaigns?: Campaign[] }).campaigns || [];
      setCampaigns(camps);
      if (settings.behavior_discounts_enabled) {
        const a = await api.get<Analytics>("/marketing/behavior-discounts/analytics").catch(() => null);
        setAnalytics(a);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setBusinessId(getBusinessId());
    loadData();
  }, [loadData]);

  const toggleEnabled = async (val: boolean) => {
    setTogglingEnabled(true);
    try {
      await api.put("/settings", { behavior_discounts_enabled: val });
      setEnabled(val);
    } finally {
      setTogglingEnabled(false);
    }
  };

  const saveGa4Id = async () => {
    setSavingSettings(true);
    try { await api.put("/settings", { ga4_measurement_id: ga4Id }); }
    finally { setSavingSettings(false); }
  };

  const unwrapCampaign = (res: unknown): Campaign => {
    const r = res as Record<string, unknown>;
    return (r.campaign ?? res) as Campaign;
  };

  const activateTemplate = async (tpl: typeof TEMPLATES[0]) => {
    setActivatingTemplate(tpl.id);
    try {
      const res = await api.post("/marketing/behavior-discounts/campaigns", {
        name: tpl.name, trigger_event: tpl.trigger_event, discount_type: "percentage",
        discount_value: tpl.discount_value, delivery_method: tpl.delivery_method,
        message_template: tpl.message_template, active: true,
      });
      setCampaigns(p => [...p, unwrapCampaign(res)]);
      setActiveTab("campaigns");
    } finally {
      setActivatingTemplate(null);
    }
  };

  const createCampaign = async () => {
    const res = await api.post("/marketing/behavior-discounts/campaigns", { ...newCampaign });
    setCampaigns(p => [...p, unwrapCampaign(res)]);
    setShowModal(false);
    setNewCampaign({ name: "", trigger_event: "exit_intent", discount_type: "percentage", discount_value: 10, delivery_method: "popup", message_template: "Use code {discount_code} for {discount_value}% off!" });
  };

  const getCid = (c: Campaign) => c._id || c.id || "";

  const toggleCampaign = async (id: string, currentActive: boolean) => {
    const next = !currentActive;
    await api.put(`/marketing/behavior-discounts/campaigns/${id}`, { active: next });
    setCampaigns(p => p.map(c => getCid(c) === id ? { ...c, active: next } : c));
  };

  const deleteCampaign = async (id: string) => {
    await api.delete(`/marketing/behavior-discounts/campaigns/${id}`);
    setCampaigns(p => p.filter(c => getCid(c) !== id));
  };

  const copySnippet = () => {
    const text = `<!-- GA4 Tracking -->\n<script async src="https://www.googletagmanager.com/gtag/js?id=${ga4Id || "G-XXXXXXXXXX"}"></script>\n<script>\n  window.dataLayer = window.dataLayer || [];\n  function gtag(){dataLayer.push(arguments);}\n  gtag('js', new Date());\n  gtag('config', '${ga4Id || "G-XXXXXXXXXX"}');\n</script>\n\n<!-- Zilo Behavior Tracker -->\n<script src="https://crm.zilo.pro/tracking/zilo-behavior-tracker.js"></script>\n<script>\n  ZiloBehaviorTracker.init({\n    businessId: '${businessId || "YOUR_BUSINESS_ID"}',\n    apiUrl: 'https://crm.zilo.pro/api'\n  });\n</script>`;
    navigator.clipboard.writeText(text).then(() => {
      setSnippetCopied(true);
      setTimeout(() => setSnippetCopied(false), 2000);
    });
  };

  const activeCampaigns = campaigns.filter(c => c.active).length;

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-green-600" />
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">⚡ Behavior Tracker</h1>
          <p className="text-slate-500 text-sm mt-1">Send automatic discount offers based on how visitors interact with your website</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-sm font-medium ${enabled ? "text-green-700" : "text-slate-400"}`}>
            {enabled ? "Active" : "Off"}
          </span>
          <label className="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" checked={enabled} onChange={e => toggleEnabled(e.target.checked)} disabled={togglingEnabled} className="sr-only peer" />
            <div className="w-12 h-6 bg-slate-200 rounded-full peer peer-checked:bg-green-600 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all after:border after:border-slate-300"></div>
          </label>
          {togglingEnabled && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}
        </div>
      </div>

      {!enabled && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center gap-3">
          <span className="text-2xl">💡</span>
          <div>
            <p className="text-sm font-semibold text-amber-900">Behavior Tracker is off</p>
            <p className="text-xs text-amber-700 mt-0.5">Enable it above to start sending automatic discount offers to your website visitors.</p>
          </div>
        </div>
      )}

      {/* ── Stats ── */}
      {enabled && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: "Active Campaigns", value: activeCampaigns, icon: Zap, color: "text-green-600", bg: "bg-green-50" },
            { label: "Discounts Sent", value: analytics?.total_sent ?? 0, icon: Gift, color: "text-blue-600", bg: "bg-blue-50" },
            { label: "Conversions", value: analytics?.total_conversions ?? 0, icon: TrendingUp, color: "text-purple-600", bg: "bg-purple-50" },
            { label: "Conv. Rate", value: `${(analytics?.conversion_rate ?? 0).toFixed(1)}%`, icon: BarChart2, color: "text-orange-600", bg: "bg-orange-50" },
          ].map(({ label, value, icon: Icon, color, bg }) => (
            <div key={label} className="bg-white rounded-xl border border-slate-200 p-4">
              <div className={`w-8 h-8 ${bg} rounded-lg flex items-center justify-center mb-3`}>
                <Icon className={`w-4 h-4 ${color}`} />
              </div>
              <p className="text-2xl font-bold text-slate-900">{value}</p>
              <p className="text-xs text-slate-500 mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Tabs ── */}
      <div className="flex gap-1 border-b border-slate-200 overflow-x-auto">
        {([
          { id: "overview", label: "Overview", icon: Layout },
          { id: "install", label: "Install Code", icon: Code2 },
          { id: "campaigns", label: `Campaigns${campaigns.length > 0 ? ` (${campaigns.length})` : ""}`, icon: Zap },
          { id: "analytics", label: "Analytics", icon: BarChart2 },
        ] as const).map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${activeTab === id ? "border-green-600 text-green-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            <Icon className="w-4 h-4" />{label}
          </button>
        ))}
      </div>

      {/* ── OVERVIEW TAB ── */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-base font-semibold text-slate-900 mb-4">Setup Checklist</h2>
            <div className="space-y-3">
              {[
                { label: "Enable Behavior Tracker", done: enabled, action: () => toggleEnabled(true), actionLabel: "Enable Now" },
                { label: "Add your GA4 Measurement ID (G-XXXXXXXXXX)", done: !!ga4Id && ga4Id.startsWith("G-"), action: () => setActiveTab("install"), actionLabel: "Add ID" },
                { label: "Install tracking code on your website", done: false, action: () => setActiveTab("install"), actionLabel: "Get Code" },
                { label: "Create your first campaign", done: campaigns.length > 0, action: () => setActiveTab("campaigns"), actionLabel: "Create Campaign" },
              ].map(({ label, done, action, actionLabel }) => (
                <div key={label} className="flex items-center justify-between p-3 rounded-lg bg-slate-50">
                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${done ? "bg-green-500" : "bg-slate-200"}`}>
                      {done && <Check className="w-3 h-3 text-white" />}
                    </div>
                    <span className={`text-sm ${done ? "text-slate-400 line-through" : "text-slate-800 font-medium"}`}>{label}</span>
                  </div>
                  {!done && <button onClick={action} className="text-xs font-medium text-green-700 hover:underline">{actionLabel}</button>}
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-base font-semibold text-slate-900 mb-4">How It Works</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              {[
                { icon: "🔍", step: "1", title: "Visitor browses", desc: "Tracker monitors behavior — pages viewed, time spent, exit intent, cart actions" },
                { icon: "⚡", step: "2", title: "Trigger fires", desc: "When visitor matches your campaign rules (e.g. tries to leave), system activates" },
                { icon: "🎁", step: "3", title: "Offer appears", desc: "A personalized popup shows with a unique discount code — automatically generated" },
              ].map(({ icon, step, title, desc }) => (
                <div key={step} className="text-center">
                  <div className="text-3xl mb-2">{icon}</div>
                  <div className="w-6 h-6 bg-green-100 text-green-700 rounded-full text-xs font-bold flex items-center justify-center mx-auto mb-2">{step}</div>
                  <p className="text-sm font-semibold text-slate-800 mb-1">{title}</p>
                  <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── INSTALL TAB ── */}
      {activeTab === "install" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-base font-semibold text-slate-900 mb-1">GA4 Measurement ID</h2>
            <p className="text-xs text-slate-500 mb-4">GA4 → Admin → Data Streams → your stream → Measurement ID (starts with G-)</p>
            <div className="flex gap-2">
              <input type="text" value={ga4Id} onChange={e => setGa4Id(e.target.value)} placeholder="G-XXXXXXXXXX"
                className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 font-mono" />
              <button onClick={saveGa4Id} disabled={savingSettings}
                className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 font-medium disabled:opacity-50 flex items-center gap-2">
                {savingSettings ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save
              </button>
            </div>
            {ga4Id && !ga4Id.startsWith("G-") && <p className="text-xs text-red-500 mt-2">⚠️ Should start with G-</p>}
            {ga4Id && ga4Id.startsWith("G-") && <p className="text-xs text-green-600 mt-2">✅ Valid Measurement ID</p>}
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Your Install Code</h2>
                <p className="text-xs text-slate-500 mt-0.5">Business ID pre-filled automatically — just copy and paste</p>
              </div>
              <button onClick={copySnippet}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 font-medium">
                {snippetCopied ? <><Check className="w-4 h-4" /> Copied!</> : <><Copy className="w-4 h-4" /> Copy Code</>}
              </button>
            </div>
            <pre className="bg-slate-900 text-green-400 text-[11px] rounded-xl p-4 overflow-x-auto leading-relaxed">{`<!-- GA4 Tracking -->
<script async src="https://www.googletagmanager.com/gtag/js?id=${ga4Id || "G-XXXXXXXXXX"}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', '${ga4Id || "G-XXXXXXXXXX"}');
</script>

<!-- Zilo Behavior Tracker -->
<script src="https://crm.zilo.pro/tracking/zilo-behavior-tracker.js"></script>
<script>
  ZiloBehaviorTracker.init({
    businessId: '${businessId || "YOUR_BUSINESS_ID"}',
    apiUrl: 'https://crm.zilo.pro/api'
  });
</script>`}</pre>
            <p className="text-xs text-slate-500 mt-3">📌 Paste inside your website&apos;s <code className="bg-slate-100 px-1 rounded">&lt;head&gt;</code> section.</p>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-base font-semibold text-slate-900 mb-4">Platform Installation Guides</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                { platform: "Shopify", icon: "🛒", steps: ["Go to Online Store → Themes", "Actions → Edit Code", "Open theme.liquid", "Paste before </head>"] },
                { platform: "WordPress", icon: "🔷", steps: ["Install 'Insert Headers and Footers' plugin", "Settings → Insert Headers", "Paste in Header section", "Save changes"] },
                { platform: "Wix", icon: "🌐", steps: ["Settings → Custom Code", "Add Custom Code", "Select Head section", "Paste and Save"] },
                { platform: "Squarespace", icon: "⬛", steps: ["Settings → Advanced", "Code Injection", "Paste in Header field", "Save"] },
              ].map(({ platform, icon, steps }) => (
                <div key={platform} className="bg-slate-50 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-xl">{icon}</span>
                    <span className="font-semibold text-slate-800 text-sm">{platform}</span>
                  </div>
                  <ol className="space-y-1.5">
                    {steps.map((step, i) => (
                      <li key={i} className="text-xs text-slate-600 flex gap-2">
                        <span className="text-green-600 font-bold flex-shrink-0">{i + 1}.</span>{step}
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── CAMPAIGNS TAB ── */}
      {activeTab === "campaigns" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Campaign Templates</h2>
                <p className="text-xs text-slate-500 mt-0.5">One-click activation — works immediately</p>
              </div>
              <button onClick={() => setShowModal(true)}
                className="flex items-center gap-2 px-3 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 font-medium">
                <Plus className="w-4 h-4" /> Custom
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {TEMPLATES.map((tpl) => {
                const isActive = campaigns.some(c => c.name === tpl.name);
                return (
                  <div key={tpl.id} className={`border rounded-xl p-4 ${tpl.color}`}>
                    <div className="flex items-start justify-between mb-2">
                      <span className="text-2xl">{tpl.icon}</span>
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${tpl.badgeColor}`}>{tpl.badge}</span>
                    </div>
                    <h3 className="text-sm font-semibold text-slate-900 mb-1">{tpl.name}</h3>
                    <p className="text-xs text-slate-600 mb-3 leading-relaxed">{tpl.description}</p>
                    <div className="flex items-center gap-3 mb-3 text-xs text-slate-500">
                      <span>🎯 {TRIGGER_LABELS[tpl.trigger_event]}</span>
                      <span>💰 {tpl.discount_value}% off</span>
                    </div>
                    <button onClick={() => !isActive && activateTemplate(tpl)} disabled={isActive || activatingTemplate === tpl.id}
                      className={`w-full py-2 text-xs font-semibold rounded-lg flex items-center justify-center gap-1.5 transition-colors ${
                        isActive ? "bg-green-100 text-green-700 cursor-default" : "bg-slate-900 text-white hover:bg-slate-700"
                      }`}>
                      {activatingTemplate === tpl.id ? <Loader2 className="w-3 h-3 animate-spin" /> :
                        isActive ? <><Check className="w-3 h-3" /> Active</> : <><Play className="w-3 h-3" /> Activate</>}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {campaigns.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <h2 className="text-base font-semibold text-slate-900 mb-4">Your Campaigns ({campaigns.length})</h2>
              <div className="space-y-3">
                {campaigns.map((c) => (
                  <div key={getCid(c)} className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                    <div className="flex items-center gap-3">
                      <span className="text-xl">{DELIVERY_ICONS[c.delivery_method] || "🎯"}</span>
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{c.name}</p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {TRIGGER_LABELS[c.trigger_event] || c.trigger_event} · {c.discount_type === "percentage" ? `${c.discount_value}%` : `$${c.discount_value}`} off · {c.sent_count || 0} sent · {c.conversion_count || 0} converted
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-semibold px-2 py-1 rounded-full ${c.active ? "bg-green-100 text-green-700" : "bg-slate-200 text-slate-500"}`}>
                        {c.active ? "Active" : "Paused"}
                      </span>
                      <button onClick={() => toggleCampaign(getCid(c), c.active)} className="p-1.5 text-slate-400 hover:text-slate-700 rounded">
                        {c.active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                      </button>
                      <button onClick={() => deleteCampaign(getCid(c))} className="p-1.5 text-slate-400 hover:text-red-600 rounded">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── ANALYTICS TAB ── */}
      {activeTab === "analytics" && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-slate-900">Campaign Performance</h2>
            <button onClick={loadData} className="p-2 text-slate-400 hover:text-slate-700 rounded-lg"><RefreshCw className="w-4 h-4" /></button>
          </div>
          {!enabled ? (
            <div className="text-center py-12"><BarChart2 className="w-12 h-12 text-slate-200 mx-auto mb-3" /><p className="text-slate-500 text-sm">Enable Behavior Tracker to see analytics</p></div>
          ) : campaigns.length === 0 ? (
            <div className="text-center py-12">
              <BarChart2 className="w-12 h-12 text-slate-200 mx-auto mb-3" />
              <p className="text-slate-500 text-sm">Create campaigns to see performance</p>
              <button onClick={() => setActiveTab("campaigns")} className="mt-3 text-sm text-green-700 font-medium hover:underline">Create Campaign →</button>
            </div>
          ) : (
            <div className="space-y-4">
              {campaigns.map((c) => {
                const sent = c.sent_count || 0;
                const conv = c.conversion_count || 0;
                const rate = sent > 0 ? ((conv / sent) * 100).toFixed(1) : "0.0";
                return (
                  <div key={getCid(c)} className="p-4 bg-slate-50 rounded-xl">
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-sm font-semibold text-slate-900">{c.name}</p>
                      <span className={`text-[10px] font-semibold px-2 py-1 rounded-full ${c.active ? "bg-green-100 text-green-700" : "bg-slate-200 text-slate-500"}`}>{c.active ? "Active" : "Paused"}</span>
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-center mb-3">
                      <div><p className="text-xl font-bold text-slate-900">{sent}</p><p className="text-xs text-slate-500">Sent</p></div>
                      <div><p className="text-xl font-bold text-blue-600">{conv}</p><p className="text-xs text-slate-500">Converted</p></div>
                      <div><p className="text-xl font-bold text-green-600">{rate}%</p><p className="text-xs text-slate-500">Conv. Rate</p></div>
                    </div>
                    <div className="bg-slate-200 rounded-full h-1.5">
                      <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${Math.min(Number(rate), 100)}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Create Campaign Modal ── */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold text-slate-900">Custom Campaign</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Campaign Name</label>
                <input type="text" value={newCampaign.name} onChange={e => setNewCampaign(p => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Weekend Flash Sale"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Trigger</label>
                  <select value={newCampaign.trigger_event} onChange={e => setNewCampaign(p => ({ ...p, trigger_event: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500">
                    {Object.entries(TRIGGER_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Delivery</label>
                  <select value={newCampaign.delivery_method} onChange={e => setNewCampaign(p => ({ ...p, delivery_method: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500">
                    <option value="popup">🎯 Popup</option>
                    <option value="banner">📢 Banner</option>
                    <option value="email">📧 Email</option>
                    <option value="sms">💬 SMS</option>
                    <option value="whatsapp">📱 WhatsApp</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Discount Type</label>
                  <select value={newCampaign.discount_type} onChange={e => setNewCampaign(p => ({ ...p, discount_type: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500">
                    <option value="percentage">Percentage %</option>
                    <option value="fixed">Fixed Amount $</option>
                    <option value="free_shipping">Free Shipping</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Value</label>
                  <input type="number" value={newCampaign.discount_value} min={1} max={100}
                    onChange={e => setNewCampaign(p => ({ ...p, discount_value: Number(e.target.value) }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Message Template</label>
                <textarea value={newCampaign.message_template} rows={3} onChange={e => setNewCampaign(p => ({ ...p, message_template: e.target.value }))}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 resize-none" />
                <p className="text-[10px] text-slate-400 mt-1">Use {"{discount_code}"} and {"{discount_value}"} as placeholders</p>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setShowModal(false)} className="flex-1 py-2.5 border border-slate-200 text-slate-700 text-sm rounded-xl font-medium hover:bg-slate-50">Cancel</button>
              <button onClick={createCampaign} disabled={!newCampaign.name} className="flex-1 py-2.5 bg-green-600 text-white text-sm rounded-xl font-medium hover:bg-green-700 disabled:opacity-50">Create Campaign</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
