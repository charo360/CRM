"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  settingsApi,
  businessKnowledgeApi,
  authApi,
  BusinessSettings,
  BusinessKnowledge,
} from "@/lib/api";
import { getUser, setUser } from "@/lib/auth";
import { useBusiness } from "@/contexts/BusinessContext";
import { Save, Loader2, Building, Globe, MessageSquare, Zap, Briefcase, Sparkles, RefreshCw } from "lucide-react";
import { TypeFields } from "./TypeFields";
import {
  ALL_CURRENCY_CODES,
  WORLD_COUNTRIES,
  getCountryByCode,
} from "@/lib/worldCountries";

/** Same set as mobile `BusinessType` (app). */
const BUSINESS_TYPES = [
  { value: "retail", label: "Retail store" },
  { value: "wholesale", label: "Wholesale" },
  { value: "restaurant", label: "Restaurant / food service" },
  { value: "food", label: "Food & beverage" },
  { value: "bakery", label: "Bakery" },
  { value: "grocery", label: "Grocery" },
  { value: "salon", label: "Salon / beauty" },
  { value: "spa", label: "Spa / wellness" },
  { value: "services", label: "Professional services" },
  { value: "repair", label: "Repair & technical" },
  { value: "cleaning", label: "Cleaning" },
  { value: "fitness", label: "Fitness / gym" },
  { value: "events", label: "Events / creative" },
  { value: "healthcare", label: "Healthcare" },
  { value: "rental", label: "Rental (property / vehicle)" },
  { value: "hotel", label: "Hotel / lodging" },
  { value: "support", label: "Support / helpdesk" },
  { value: "creator", label: "Content creator" },
  { value: "general", label: "General / mixed" },
  { value: "other", label: "Other" },
];

const LANGUAGES = [
  "English", "Swahili", "French", "Arabic", "Hausa", "Yoruba", "Igbo", "Zulu", "Afrikaans",
];

const MESSAGE_TONES = [
  { value: "friendly", label: "Friendly" },
  { value: "professional", label: "Professional" },
  { value: "formal", label: "Formal" },
  { value: "casual", label: "Casual" },
];

function countryCodeFromSettings(us: { country_code?: string; country?: string }): string {
  const raw = us.country_code?.trim().toUpperCase();
  if (raw && getCountryByCode(raw)) return raw;
  const name = us.country?.trim();
  if (name) {
    const byName = WORLD_COUNTRIES.find((c) => c.name === name);
    if (byName) return byName.code;
  }
  return "KE";
}

/** Keeps dashboard `BusinessContext` (sidebar, labels, currency) in sync with form edits. */
function patchStoredUserSettings(partial: Record<string, unknown>) {
  const prev = getUser() || {};
  const prevSettings = ((prev.settings as Record<string, unknown>) || {}) as Record<string, unknown>;
  setUser({
    ...prev,
    settings: { ...prevSettings, ...partial },
  });
}

export default function SettingsPage() {
  const { refreshSettings } = useBusiness();
  const [userSettings, setUserSettings] = useState<BusinessSettings>({});
  const [bk, setBk] = useState<BusinessKnowledge>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState("business");
  const [aiAboutBusy, setAiAboutBusy] = useState(false);

  const currencyDisplay = useMemo(() => {
    try {
      return new Intl.DisplayNames(["en"], { type: "currency" });
    } catch {
      return null;
    }
  }, []);

  const currencyOptions = useMemo(
    () =>
      ALL_CURRENCY_CODES.map((code) => ({
        value: code,
        label: currencyDisplay ? `${code} — ${currencyDisplay.of(code) ?? code}` : code,
      })),
    [currencyDisplay]
  );

  const currencySelectOptions = useMemo(() => {
    const cur = (userSettings.currency || "KES").trim();
    if (!cur || ALL_CURRENCY_CODES.includes(cur)) return currencyOptions;
    return [{ value: cur, label: cur }, ...currencyOptions];
  }, [currencyOptions, userSettings.currency]);

  const loadSettings = useCallback(async () => {
    try {
      const [us, knowledge] = await Promise.all([
        settingsApi.get(),
        businessKnowledgeApi.get(),
      ]);
      setUserSettings({
        ...us,
        payment_methods: Array.isArray(knowledge.payment_methods)
          ? (knowledge.payment_methods as BusinessSettings["payment_methods"])
          : us.payment_methods,
      });
      const { payment_methods: _pm, ...restBk } = knowledge;
      setBk(restBk);
    } catch (e) {
      console.error("Failed to load settings:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const patchBk = useCallback((p: Record<string, unknown>) => {
    setBk((prev) => ({ ...prev, ...p }));
  }, []);

  async function handleSave() {
    setSaving(true);
    try {
      await settingsApi.update({
        business_name: userSettings.business_name,
        owner_name: userSettings.owner_name,
        business_type: userSettings.business_type,
        currency: userSettings.currency,
        country_code: userSettings.country_code,
        primary_language: userSettings.primary_language,
        country: userSettings.country,
        auto_reply_enabled: userSettings.auto_reply_enabled,
        auto_reply_audience: userSettings.auto_reply_audience,
        ai_model: userSettings.ai_model,
        notification_enabled: userSettings.notification_enabled,
        notification_time: userSettings.notification_time,
        daily_alert_count: userSettings.daily_alert_count,
        message_tone: userSettings.message_tone,
        daily_pulse_enabled: userSettings.daily_pulse_enabled,
        daily_pulse_time: userSettings.daily_pulse_time,
        restaurant_has_reservations: userSettings.restaurant_has_reservations,
        payment_methods: userSettings.payment_methods,
      });

      const toSave = { ...bk, business_type: userSettings.business_type || bk.business_type };
      await businessKnowledgeApi.update(toSave);

      try {
        const me = await authApi.me();
        const prev = getUser() || {};
        setUser({
          ...prev,
          ...me,
          settings: {
            ...((prev.settings as object) || {}),
            business_type: userSettings.business_type,
            currency: userSettings.currency,
            country: userSettings.country,
            primary_language: userSettings.primary_language,
            country_code: userSettings.country_code,
          },
        });
      } catch {
        /* non-fatal */
      }

      await loadSettings();
      refreshSettings();
    } catch (e) {
      console.error(e);
      alert("Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  function updateUser<K extends keyof BusinessSettings>(key: K, value: BusinessSettings[K]) {
    setUserSettings((prev) => ({ ...prev, [key]: value }));
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

  const bt = userSettings.business_type || "retail";

  async function handleAiGenerateAbout() {
    setAiAboutBusy(true);
    try {
      const result = await settingsApi.generateAiAbout({
        business_type: bt,
        mode: "generate",
      });
      if (result.description) {
        patchBk({ business_description: result.description });
      }
    } catch (e) {
      console.error(e);
      alert(
        e instanceof Error
          ? e.message
          : "Could not generate a description. Try again or write your own."
      );
    } finally {
      setAiAboutBusy(false);
    }
  }

  async function handleAiImproveAbout() {
    const current = String(bk.business_description ?? "").trim();
    if (!current) {
      await handleAiGenerateAbout();
      return;
    }
    setAiAboutBusy(true);
    try {
      const result = await settingsApi.generateAiAbout({
        business_type: bt,
        current_description: current,
        mode: "improve",
      });
      if (result.description) {
        patchBk({ business_description: result.description });
      }
    } catch (e) {
      console.error(e);
      alert(
        e instanceof Error ? e.message : "Could not improve the description. Try editing manually."
      );
    } finally {
      setAiAboutBusy(false);
    }
  }

  const tabs = [
    { id: "business", label: "Business", icon: Building },
    { id: "regional", label: "Location & region", icon: Globe },
    { id: "ai", label: "AI & notifications", icon: MessageSquare },
    { id: "operations", label: "Operations", icon: Briefcase },
    { id: "advanced", label: "Advanced", icon: Zap },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Business settings</h1>
          <p className="text-slate-500 text-sm mt-1">
            Same options as the mobile app — profile, region, AI, and per–business-type operations.
          </p>
        </div>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          Save changes
        </button>
      </div>

      <div className="flex gap-1 border-b border-slate-200 overflow-x-auto">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap ${
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
              label="Business name"
              value={userSettings.business_name || ""}
              onChange={(v) => updateUser("business_name", v)}
              placeholder="Your business name"
            />
            <Field
              label="Owner name"
              value={userSettings.owner_name || ""}
              onChange={(v) => updateUser("owner_name", v)}
              placeholder="Your name"
            />
            <Select
              label="Business type"
              value={bt}
              onChange={(v) => {
                updateUser("business_type", v);
                patchStoredUserSettings({ business_type: v });
                refreshSettings();
              }}
              options={BUSINESS_TYPES.filter((x, i, a) => a.findIndex((y) => y.value === x.value) === i)}
            />
            {(bt === "restaurant" || bt === "food") && (
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="resv"
                  checked={userSettings.restaurant_has_reservations || false}
                  onChange={(e) => updateUser("restaurant_has_reservations", e.target.checked)}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <label htmlFor="resv" className="text-sm font-medium text-slate-700">
                  Accept table / reservations (AI will collect date & time)
                </label>
              </div>
            )}
            <div>
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                <label className="block text-sm font-medium text-slate-700">Business description</label>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void handleAiGenerateAbout()}
                    disabled={aiAboutBusy}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 disabled:opacity-50 disabled:pointer-events-none transition-colors"
                  >
                    {aiAboutBusy ? (
                      <Loader2 size={14} className="animate-spin shrink-0" />
                    ) : (
                      <Sparkles size={14} className="shrink-0" />
                    )}
                    {aiAboutBusy ? "Working…" : "AI draft"}
                  </button>
                  {String(bk.business_description ?? "").trim() ? (
                    <button
                      type="button"
                      onClick={() => void handleAiImproveAbout()}
                      disabled={aiAboutBusy}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-slate-700 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 disabled:opacity-50 disabled:pointer-events-none transition-colors"
                    >
                      <RefreshCw size={14} className="shrink-0" />
                      Improve with AI
                    </button>
                  ) : null}
                </div>
              </div>
              <p className="text-xs text-slate-500 mb-2">
                Uses your business type above. Save when you are happy with the text.
              </p>
              <textarea
                value={String(bk.business_description ?? "")}
                onChange={(e) => patchBk({ business_description: e.target.value })}
                placeholder="Tell customers about your business..."
                rows={4}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>
            <TextArea
              label="Products & services"
              value={String(bk.products_services ?? "")}
              onChange={(v) => patchBk({ products_services: v })}
              placeholder="List main products and services..."
              rows={4}
            />
            <TextArea
              label="Pricing info (optional)"
              value={String(bk.pricing_info ?? "")}
              onChange={(v) => patchBk({ pricing_info: v })}
              placeholder="Price ranges, packages..."
              rows={2}
            />
          </div>
        )}

        {activeTab === "regional" && (
          <div className="space-y-6">
            <Select
              label="Country"
              value={countryCodeFromSettings(userSettings)}
              onChange={(iso2) => {
                const c = getCountryByCode(iso2);
                if (!c) return;
                setUserSettings((prev) => ({
                  ...prev,
                  country_code: c.code,
                  country: c.name,
                  currency: c.currency,
                }));
                patchStoredUserSettings({
                  country_code: c.code,
                  country: c.name,
                  currency: c.currency,
                });
                refreshSettings();
              }}
              options={WORLD_COUNTRIES.map((c) => ({
                value: c.code,
                label: `${c.name} (${c.code})`,
              }))}
            />
            <Select
              label="Currency"
              value={(userSettings.currency || "KES").trim()}
              onChange={(v) => {
                updateUser("currency", v);
                patchStoredUserSettings({ currency: v });
                refreshSettings();
              }}
              options={currencySelectOptions}
            />
            <Select
              label="Primary language"
              value={userSettings.primary_language || "English"}
              onChange={(v) => {
                updateUser("primary_language", v);
                patchStoredUserSettings({ primary_language: v });
                refreshSettings();
              }}
              options={LANGUAGES.map((l) => ({ value: l, label: l }))}
            />
            <TextArea
              label="Location / address"
              value={String(bk.business_location ?? "")}
              onChange={(v) => patchBk({ business_location: v })}
              placeholder="Area, building, directions..."
              rows={2}
            />
            <TextArea
              label="Business hours"
              value={String(bk.business_hours ?? "")}
              onChange={(v) => patchBk({ business_hours: v })}
              placeholder="Mon–Fri 9–6..."
              rows={2}
            />
            <TextArea
              label="Delivery information"
              value={String(bk.delivery_info ?? "")}
              onChange={(v) => patchBk({ delivery_info: v })}
              placeholder="Zones, fees, timing..."
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
                checked={userSettings.auto_reply_enabled || false}
                onChange={(e) => updateUser("auto_reply_enabled", e.target.checked)}
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <label htmlFor="auto_reply" className="text-sm font-medium text-slate-700">
                Enable AI auto-reply
              </label>
            </div>
            <Select
              label="Auto-reply audience"
              value={userSettings.auto_reply_audience || "everyone"}
              onChange={(v) => updateUser("auto_reply_audience", v)}
              options={[
                { value: "everyone", label: "Everyone" },
                { value: "customers_only", label: "Customers only" },
                { value: "new_contacts_only", label: "New contacts only" },
              ]}
            />
            <Select
              label="AI model"
              value={userSettings.ai_model || "standard"}
              onChange={(v) => updateUser("ai_model", v)}
              options={[
                { value: "standard", label: "Standard (fast)" },
                { value: "advanced", label: "Advanced (better)" },
              ]}
            />
            <Select
              label="Message tone"
              value={userSettings.message_tone || "friendly"}
              onChange={(v) => updateUser("message_tone", v)}
              options={MESSAGE_TONES}
            />
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="notif"
                checked={userSettings.notification_enabled !== false}
                onChange={(e) => updateUser("notification_enabled", e.target.checked)}
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <label htmlFor="notif" className="text-sm font-medium text-slate-700">
                Daily summary notifications
              </label>
            </div>
            <Field
              label="Notification time"
              type="time"
              value={userSettings.notification_time || "08:00"}
              onChange={(v) => updateUser("notification_time", v)}
            />
            <Field
              label="Daily alert count"
              type="number"
              value={String(userSettings.daily_alert_count ?? 5)}
              onChange={(v) => updateUser("daily_alert_count", parseInt(v, 10) || 5)}
            />
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="pulse"
                checked={userSettings.daily_pulse_enabled || false}
                onChange={(e) => updateUser("daily_pulse_enabled", e.target.checked)}
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <label htmlFor="pulse" className="text-sm font-medium text-slate-700">
                Daily pulse (business insight message)
              </label>
            </div>
            <Field
              label="Daily pulse time"
              type="time"
              value={userSettings.daily_pulse_time || "20:00"}
              onChange={(v) => updateUser("daily_pulse_time", v)}
            />
            <TextArea
              label="Special offers"
              value={String(bk.special_offers ?? "")}
              onChange={(v) => patchBk({ special_offers: v })}
              placeholder="Promotions, discounts..."
              rows={3}
            />
            <TextArea
              label="Frequently asked questions"
              value={String(bk.faqs ?? "")}
              onChange={(v) => patchBk({ faqs: v })}
              placeholder="Common Q&A..."
              rows={4}
            />
          </div>
        )}

        {activeTab === "operations" && (
          <div className="space-y-8">
            <TypeFields key={bt} businessType={bt} bk={bk} patchBk={patchBk} />
            <div className="border-t border-slate-200 pt-6">
              <h3 className="text-sm font-semibold text-slate-900 mb-3">Payment methods shown to customers</h3>
              <div className="space-y-2">
                {(userSettings.payment_methods || []).map((method, i) => (
                  <div key={i} className="flex gap-2">
                    <input
                      value={method.name}
                      onChange={(e) => {
                        const updated = [...(userSettings.payment_methods || [])];
                        updated[i] = { ...method, name: e.target.value };
                        updateUser("payment_methods", updated);
                      }}
                      placeholder="Method name"
                      className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
                    />
                    <input
                      value={method.details}
                      onChange={(e) => {
                        const updated = [...(userSettings.payment_methods || [])];
                        updated[i] = { ...method, details: e.target.value };
                        updateUser("payment_methods", updated);
                      }}
                      placeholder="Details"
                      className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const updated = (userSettings.payment_methods || []).filter((_, idx) => idx !== i);
                        updateUser("payment_methods", updated);
                      }}
                      className="px-3 py-2 text-red-600 hover:bg-red-50 rounded-lg"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => {
                    const updated = [...(userSettings.payment_methods || []), { name: "", details: "" }];
                    updateUser("payment_methods", updated);
                  }}
                  className="text-sm text-indigo-600 hover:underline"
                >
                  + Add payment method
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === "advanced" && (
          <div className="space-y-4 text-sm text-slate-600">
            <p>
              Payment methods and journey settings sync with the mobile app. Business type controls
              labels and features across the web dashboard.
            </p>
            <p className="text-slate-500">
              Navigation and labels update as soon as you change business type or save.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
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

function TextArea({
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
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

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
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
          <option key={v + l} value={v}>
            {l}
          </option>
        ))}
      </select>
    </div>
  );
}
