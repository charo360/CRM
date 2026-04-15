"use client";

import { useEffect, useState } from "react";
import { settingsApi, BusinessSettings } from "@/lib/api";
import { getCurrency, getBusinessType } from "@/lib/auth";
import { Save, Loader2, Building, Globe, MessageSquare, Zap } from "lucide-react";

const BUSINESS_TYPES = [
  { value: "retail", label: "Retail Store" },
  { value: "restaurant", label: "Restaurant/Food" },
  { value: "salon", label: "Salon/Beauty" },
  { value: "services", label: "Services" },
  { value: "healthcare", label: "Healthcare" },
  { value: "creator", label: "Content Creator" },
  { value: "other", label: "Other" },
];

const CURRENCIES = [
  { code: "KES", name: "Kenyan Shilling", symbol: "KSh" },
  { code: "USD", name: "US Dollar", symbol: "$" },
  { code: "EUR", name: "Euro", symbol: "€" },
  { code: "GBP", name: "British Pound", symbol: "£" },
  { code: "NGN", name: "Nigerian Naira", symbol: "₦" },
  { code: "ZAR", name: "South African Rand", symbol: "R" },
  { code: "GHS", name: "Ghanaian Cedi", symbol: "₵" },
  { code: "UGX", name: "Ugandan Shilling", symbol: "USh" },
  { code: "TZS", name: "Tanzanian Shilling", symbol: "TSh" },
];

const COUNTRIES = [
  "Kenya", "Nigeria", "South Africa", "Ghana", "Uganda", "Tanzania", 
  "United States", "United Kingdom", "Canada", "Australia", "Other"
];

const LANGUAGES = [
  "English", "Swahili", "French", "Arabic", "Hausa", "Yoruba", "Igbo", "Zulu", "Afrikaans"
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<BusinessSettings>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState("business");

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    try {
      const data = await settingsApi.get();
      setSettings(data);
    } catch (e) {
      console.error("Failed to load settings:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      await settingsApi.update(settings);
      // Refresh user data in localStorage
      window.location.reload();
    } catch (e) {
      console.error("Failed to save settings:", e);
      alert("Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  function updateSetting(key: keyof BusinessSettings, value: any) {
    setSettings(prev => ({ ...prev, [key]: value }));
  }

  if (loading) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-200 rounded w-1/3" />
          <div className="h-32 bg-slate-200 rounded" />
        </div>
      </div>
    );
  }

  const tabs = [
    { id: "business", label: "Business Info", icon: Building },
    { id: "regional", label: "Regional", icon: Globe },
    { id: "ai", label: "AI & Messaging", icon: MessageSquare },
    { id: "advanced", label: "Advanced", icon: Zap },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Business Settings</h1>
          <p className="text-slate-500 text-sm mt-1">Configure your business profile and preferences</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          Save Changes
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === id
                ? "bg-white border-b-2 border-indigo-600 text-indigo-600"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-6">
        {activeTab === "business" && (
          <div className="space-y-6">
            <Field
              label="Business Name"
              value={settings.business_name || ""}
              onChange={(v) => updateSetting("business_name", v)}
              placeholder="Your Business Name"
            />
            <Select
              label="Business Type"
              value={settings.business_type || "retail"}
              onChange={(v) => updateSetting("business_type", v)}
              options={BUSINESS_TYPES}
            />
            <TextArea
              label="Business Description"
              value={settings.business_description || ""}
              onChange={(v) => updateSetting("business_description", v)}
              placeholder="Tell customers about your business..."
              rows={3}
            />
            <TextArea
              label="Products & Services"
              value={settings.products_services || ""}
              onChange={(v) => updateSetting("products_services", v)}
              placeholder="List your main products and services..."
              rows={4}
            />
            <Field
              label="Business Location"
              value={settings.business_location || ""}
              onChange={(v) => updateSetting("business_location", v)}
              placeholder="Your business address or area"
            />
            <TextArea
              label="Business Hours"
              value={settings.business_hours || ""}
              onChange={(v) => updateSetting("business_hours", v)}
              placeholder="Mon-Fri: 9AM-6PM, Sat: 10AM-4PM..."
              rows={2}
            />
          </div>
        )}

        {activeTab === "regional" && (
          <div className="space-y-6">
            <Select
              label="Country"
              value={settings.country || "Kenya"}
              onChange={(v) => updateSetting("country", v)}
              options={COUNTRIES.map(c => ({ value: c, label: c }))}
            />
            <Select
              label="Currency"
              value={settings.currency || "KES"}
              onChange={(v) => updateSetting("currency", v)}
              options={CURRENCIES.map(c => ({ value: c.code, label: `${c.name} (${c.symbol})` }))}
            />
            <Select
              label="Primary Language"
              value={settings.primary_language || "English"}
              onChange={(v) => updateSetting("primary_language", v)}
              options={LANGUAGES.map(l => ({ value: l, label: l }))}
            />
            <TextArea
              label="Delivery Information"
              value={settings.delivery_info || ""}
              onChange={(v) => updateSetting("delivery_info", v)}
              placeholder="Delivery areas, fees, timing..."
              rows={3}
            />
          </div>
        )}

        {activeTab === "ai" && (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="auto_reply"
                checked={settings.auto_reply_enabled || false}
                onChange={(e) => updateSetting("auto_reply_enabled", e.target.checked)}
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <label htmlFor="auto_reply" className="text-sm font-medium text-slate-700">
                Enable AI Auto-Reply
              </label>
            </div>
            <Select
              label="Auto-Reply Audience"
              value={settings.auto_reply_audience || "everyone"}
              onChange={(v) => updateSetting("auto_reply_audience", v)}
              options={[
                { value: "everyone", label: "Everyone" },
                { value: "customers_only", label: "Customers Only" },
                { value: "new_contacts_only", label: "New Contacts Only" },
              ]}
            />
            <Select
              label="AI Model"
              value={settings.ai_model || "standard"}
              onChange={(v) => updateSetting("ai_model", v)}
              options={[
                { value: "standard", label: "Standard (Fast)" },
                { value: "advanced", label: "Advanced (Better)" },
              ]}
            />
            <TextArea
              label="Special Offers"
              value={settings.special_offers || ""}
              onChange={(v) => updateSetting("special_offers", v)}
              placeholder="Current promotions, discounts..."
              rows={3}
            />
            <TextArea
              label="Frequently Asked Questions"
              value={settings.faqs || ""}
              onChange={(v) => updateSetting("faqs", v)}
              placeholder="Common questions and answers..."
              rows={4}
            />
          </div>
        )}

        {activeTab === "advanced" && (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Payment Methods</label>
              <div className="space-y-2">
                {(settings.payment_methods || []).map((method, i) => (
                  <div key={i} className="flex gap-2">
                    <input
                      value={method.name}
                      onChange={(e) => {
                        const updated = [...(settings.payment_methods || [])];
                        updated[i] = { ...method, name: e.target.value };
                        updateSetting("payment_methods", updated);
                      }}
                      placeholder="Method name"
                      className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
                    />
                    <input
                      value={method.details}
                      onChange={(e) => {
                        const updated = [...(settings.payment_methods || [])];
                        updated[i] = { ...method, details: e.target.value };
                        updateSetting("payment_methods", updated);
                      }}
                      placeholder="Details"
                      className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                      onClick={() => {
                        const updated = (settings.payment_methods || []).filter((_, idx) => idx !== i);
                        updateSetting("payment_methods", updated);
                      }}
                      className="px-3 py-2 text-red-600 hover:bg-red-50 rounded-lg"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => {
                    const updated = [...(settings.payment_methods || []), { name: "", details: "" }];
                    updateSetting("payment_methods", updated);
                  }}
                  className="text-sm text-indigo-600 hover:underline"
                >
                  + Add Payment Method
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text" }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
      />
    </div>
  );
}

function TextArea({ label, value, onChange, placeholder, rows = 3 }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; rows?: number;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 resize-none"
      />
    </div>
  );
}

function Select({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: Array<{ value: string; label: string }>;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
      >
        {options.map(({ value: v, label: l }) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    </div>
  );
}
