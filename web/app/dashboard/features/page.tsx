"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useBusiness } from "@/contexts/BusinessContext";
import { settingsApi } from "@/lib/api";
import { patchStoredUserSettings } from "@/lib/auth";
import {
  FEATURE_TOGGLE_GROUPS,
  filterFeatureToggleGroups,
  getAllFeatureToggleRows,
  mergeSidebarFeatures,
  applyAllFromPartial,
  PRESET_STARTER,
  PRESET_BUSINESS,
  PRESET_PERSONAL,
  allSidebarFeaturesOn,
} from "@/lib/sidebarFeatures";
import { Layers, Loader2, Briefcase, User, Zap, ToggleLeft, Search, X } from "lucide-react";
import { toast } from "sonner";

export default function FeaturesPage() {
  const { businessType, ui, refreshSettings } = useBusiness();
  const [features, setFeatures] = useState<Record<string, boolean>>(() =>
    mergeSidebarFeatures(undefined)
  );
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const filteredGroups = useMemo(
    () => filterFeatureToggleGroups(search),
    [search]
  );
  const totalTools = getAllFeatureToggleRows().length;
  const enabledCount = useMemo(
    () => Object.values(features).filter(Boolean).length,
    [features]
  );
  const matchCount = useMemo(
    () => filteredGroups.reduce((n, g) => n + g.items.length, 0),
    [filteredGroups]
  );

  const load = useCallback(async () => {
    try {
      const s = await settingsApi.get();
      const merged = mergeSidebarFeatures(s.features);
      setFeatures(merged);
      patchStoredUserSettings({
        features: merged,
        ...(s.account_mode ? { account_mode: s.account_mode } : {}),
      });
      refreshSettings();
    } catch {
      setFeatures(mergeSidebarFeatures(undefined));
    } finally {
      setLoading(false);
    }
  }, [refreshSettings]);

  useEffect(() => {
    load();
  }, [load]);

  async function persist(next: Record<string, boolean>) {
    try {
      await settingsApi.update({ features: next });
      patchStoredUserSettings({ features: next });
      setFeatures(next);
      refreshSettings();
      toast.success("Sidebar updated");
    } catch {
      toast.error("Could not save. Try again.");
    }
  }

  async function toggle(key: string, value: boolean) {
    const next = { ...features, [key]: value };
    if (key === "nav_team") {
      if (value) {
        next.nav_collaboration = true;
      } else {
        next.nav_collaboration = false;
      }
    } else if (key === "nav_collaboration" && value && !next.nav_team) {
      next.nav_team = true;
    }
    setSavingKey(key);
    try {
      await persist(next);
    } finally {
      setSavingKey(null);
    }
  }

  async function presetAllOn() {
    setSavingKey("preset");
    try {
      await persist(allSidebarFeaturesOn());
    } finally {
      setSavingKey(null);
    }
  }

  async function presetStarter() {
    setSavingKey("preset");
    try {
      await persist(applyAllFromPartial(PRESET_STARTER, false));
    } finally {
      setSavingKey(null);
    }
  }

  async function presetBusiness() {
    setSavingKey("preset");
    try {
      await persist(applyAllFromPartial(PRESET_BUSINESS, false));
    } finally {
      setSavingKey(null);
    }
  }

  async function presetPersonal() {
    setSavingKey("preset");
    try {
      await persist(applyAllFromPartial(PRESET_PERSONAL, false));
    } finally {
      setSavingKey(null);
    }
  }

  async function presetAllOff() {
    setSavingKey("preset");
    try {
      await persist(applyAllFromPartial({}, false));
    } finally {
      setSavingKey(null);
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex justify-center py-24 text-slate-400">
        <Loader2 size={24} className="animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 w-full max-w-3xl mx-auto space-y-8 pb-16 text-slate-900">
      <div>
        <div className="flex items-center gap-2 text-[#009B3A] mb-2">
          <Layers size={22} />
          <span className="text-xs font-semibold uppercase tracking-wide">Sidebar</span>
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Features</h1>
        <p className="text-slate-600 text-sm mt-2 leading-relaxed">
          <strong className="text-slate-800">Workspace</strong> always includes {ui.overviewSubtitle}, Zilo Chat,
          Automations, <strong className="text-slate-800">Integrations</strong>, this page, and Settings. Everything
          else — Field Agents, SMS, AI Scout, and more — is optional. Search below to find a tool and toggle it on.
        </p>
        <p className="text-xs text-slate-500 mt-2">
          {enabledCount} of {totalTools} optional tools enabled
          {businessType ? (
            <>
              {" "}
              · Type: <span className="font-medium text-slate-700">{businessType.replace(/_/g, " ")}</span>
            </>
          ) : null}
        </p>
      </div>

      {/* Search tools */}
      <div className="relative">
        <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search tools… e.g. SMS, invoices, WhatsApp, SEO"
          className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-10 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-[#009B3A]/40 focus:outline-none focus:ring-2 focus:ring-[#4CD137]/30"
        />
        {search && (
          <button
            type="button"
            onClick={() => setSearch("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Clear search"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Quick Setup */}
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
          <Zap size={15} className="text-[#4CD137]" aria-hidden />
          <h2 className="text-sm font-semibold text-slate-800">Quick Setup</h2>
          <span className="text-xs text-slate-400 ml-1">— pick a preset to get started fast</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4">
          {/* Business */}
          <button
            type="button"
            onClick={presetBusiness}
            disabled={savingKey !== null}
            className="group flex items-start gap-3 rounded-xl border-2 border-[#009B3A]/35 bg-emerald-50/90 p-4 text-left text-slate-900 transition-colors hover:border-[#009B3A]/50 hover:bg-emerald-50 disabled:opacity-50"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#009B3A]">
              <Briefcase size={17} className="text-white" aria-hidden />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">Business</p>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-600">
                Messages · Customers · Orders · Invoices · Quotes · Finance · Analytics · WhatsApp · Broadcast — turn on
                Ads &amp; Social under Sales &amp; growth when you are ready
              </p>
            </div>
          </button>

          {/* Personal */}
          <button
            type="button"
            onClick={presetPersonal}
            disabled={savingKey !== null}
            className="group flex items-start gap-3 rounded-xl border-2 border-[#009B3A]/35 bg-emerald-50/90 p-4 text-left text-slate-900 transition-colors hover:border-[#009B3A]/50 hover:bg-emerald-50 disabled:opacity-50"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#009B3A]">
              <User size={17} className="text-white" aria-hidden />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">Personal</p>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-600">
                Social Inbox · Broadcast · Social Scheduler · Contacts · Follow-ups · WhatsApp
              </p>
            </div>
          </button>
        </div>

        {/* Secondary presets */}
        <div className="px-4 pb-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={presetAllOn}
            disabled={savingKey !== null}
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:opacity-50"
          >
            <ToggleLeft size={13} className="shrink-0 text-slate-600" aria-hidden /> Turn all on
          </button>
          <button
            type="button"
            onClick={presetAllOff}
            disabled={savingKey !== null}
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:opacity-50"
          >
            <ToggleLeft size={13} className="shrink-0 text-slate-600" aria-hidden /> Turn all off
          </button>
          <button
            type="button"
            onClick={presetStarter}
            disabled={savingKey !== null}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:opacity-50"
          >
            Starter pack
          </button>
        </div>
      </div>

      <div className="space-y-8">
        {search && (
          <p className="text-xs text-slate-500">
            {matchCount === 0
              ? `No tools match “${search}”`
              : `${matchCount} tool${matchCount === 1 ? "" : "s"} match “${search}”`}
          </p>
        )}
        {filteredGroups.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 py-12 text-center">
            <Search size={28} className="mx-auto mb-3 text-slate-300" />
            <p className="text-sm font-medium text-slate-700">No matching tools</p>
            <p className="text-xs text-slate-500 mt-1">Try “sms”, “invoice”, “ads”, or “email”</p>
            <button
              type="button"
              onClick={() => setSearch("")}
              className="mt-4 text-xs font-medium text-[#009B3A] hover:underline"
            >
              Clear search
            </button>
          </div>
        ) : (
          filteredGroups.map((group) => (
          <div key={group.title}>
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400 mb-3">{group.title}</h2>
            <ul className="rounded-2xl border border-slate-200 divide-y divide-slate-100 bg-white overflow-hidden shadow-sm">
              {group.items.map((row) => {
                const on = features[row.key] === true;
                const busy = savingKey === row.key;
                return (
                  <li key={row.key} className="flex items-start justify-between gap-4 px-4 py-3.5">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{row.label}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{row.description}</p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={on}
                      disabled={busy || savingKey === "preset"}
                      onClick={() => toggle(row.key, !on)}
                      className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#4CD137] disabled:opacity-50 ${
                        on ? "bg-[#009B3A]" : "bg-slate-300"
                      }`}
                    >
                      <span
                        className={`pointer-events-none absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-200 ${
                          on ? "translate-x-[1.375rem]" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
          ))
        )}
      </div>

      <p className="text-xs text-slate-400 text-center">
        KDS &amp; bookings rows only apply if your business type uses them; you can still hide them here.
      </p>
    </div>
  );
}
