"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Briefcase,
  Check,
  Loader2,
  MessageSquare,
  Plug,
  ShoppingBag,
  Sparkles,
  User,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { settingsApi } from "@/lib/api";
import { patchStoredUserSettings } from "@/lib/auth";
import { useBusiness } from "@/contexts/BusinessContext";
import { cn } from "@/lib/utils";
import { ZiloLogo } from "@/components/ZiloLogo";
import {
  SUPPORTED_INDUSTRIES,
  type SupportedIndustryId,
} from "@/lib/supportedIndustries";
import {
  applyAllFromPartial,
  allSidebarFeaturesOn,
  PRESET_BUSINESS,
  PRESET_PERSONAL,
  PRESET_STARTER,
} from "@/lib/sidebarFeatures";
import { OnboardingAiPanel } from "@/components/onboarding/OnboardingAiPanel";

const STEPS = ["Welcome", "Industry", "AI guide", "Workspace", "Connect", "Done"] as const;

type PresetChoice = "starter" | "business" | "personal" | "full";

export function OnboardingWizard() {
  const router = useRouter();
  const { refreshSettings, businessType } = useBusiness();
  const [loading, setLoading] = useState(true);
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [industry, setIndustry] = useState<SupportedIndustryId>("retail");
  const [preset, setPreset] = useState<PresetChoice>("business");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await settingsApi.get();
      if (s.onboarding_v1_completed === false) {
        setVisible(true);
        const bt = (s.business_type as SupportedIndustryId) || "retail";
        const match = SUPPORTED_INDUSTRIES.find((x) => x.id === bt);
        setIndustry(match ? bt : "retail");
      } else {
        setVisible(false);
      }
    } catch {
      setVisible(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** Keep industry in sync if context loads later */
  useEffect(() => {
    if (!visible || loading) return;
    const match = SUPPORTED_INDUSTRIES.find((x) => x.id === businessType);
    if (match) setIndustry(match.id);
  }, [businessType, visible, loading]);

  async function completeOnboarding() {
    setSaving(true);
    try {
      await settingsApi.update({ onboarding_v1_completed: true });
      patchStoredUserSettings({ onboarding_v1_completed: true });
      refreshSettings();
      setVisible(false);
      toast.success("You're all set — welcome to Zilo.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save. Try again.");
    } finally {
      setSaving(false);
    }
  }

  async function completeAndNavigate(href: string) {
    setSaving(true);
    try {
      await settingsApi.update({ onboarding_v1_completed: true });
      patchStoredUserSettings({ onboarding_v1_completed: true });
      refreshSettings();
      setVisible(false);
      router.push(href);
      toast.success("Setup saved — you're in.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function skipEntirely() {
    setSaving(true);
    try {
      await settingsApi.update({ onboarding_v1_completed: true });
      patchStoredUserSettings({ onboarding_v1_completed: true });
      refreshSettings();
      setVisible(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function persistIndustryAndNext() {
    setSaving(true);
    try {
      await settingsApi.update({ business_type: industry });
      patchStoredUserSettings({ business_type: industry });
      refreshSettings();
      setStep(2);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save industry.");
    } finally {
      setSaving(false);
    }
  }

  async function persistPresetAndNext() {
    setSaving(true);
    try {
      let features = applyAllFromPartial({}, false);
      if (preset === "starter") features = applyAllFromPartial(PRESET_STARTER, false);
      else if (preset === "business") features = applyAllFromPartial(PRESET_BUSINESS, false);
      else if (preset === "personal") features = applyAllFromPartial(PRESET_PERSONAL, false);
      else features = allSidebarFeaturesOn();

      await settingsApi.update({ features });
      patchStoredUserSettings({ features });
      refreshSettings();
      setStep(4);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save workspace.");
    } finally {
      setSaving(false);
    }
  }

  if (loading || !visible) return null;

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-title"
    >
      <div className="absolute inset-0 bg-slate-950/65 backdrop-blur-sm" aria-hidden />
      <div
        className={cn(
          "relative z-10 w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/20",
          step === 2 ? "max-w-3xl lg:max-w-4xl" : "max-w-lg",
        )}
      >
        <div className="border-b border-slate-100 bg-gradient-to-r from-brand-dark to-brand px-6 py-4 text-white">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1">
              <ZiloLogo size={32} className="shrink-0 rounded-md bg-white/15 p-0.5" />
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-light">Guided setup</p>
                <p className="text-sm font-medium text-white/90">Chat, URL & workspace</p>
              </div>
            </div>
            <button
              type="button"
              onClick={skipEntirely}
              disabled={saving}
              className="rounded-lg p-1.5 text-white/80 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
              aria-label="Skip setup"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="mt-4 flex gap-1">
            {STEPS.map((label, i) => (
              <div
                key={label}
                className={cn(
                  "h-1 flex-1 rounded-full transition",
                  i <= step ? "bg-white" : "bg-white/25",
                )}
              />
            ))}
          </div>
        </div>

        <div
          className={cn(
            "overflow-y-auto bg-white px-6 py-6 text-slate-900",
            step === 2 ? "max-h-[min(88vh,720px)]" : "max-h-[min(70vh,520px)]",
          )}
        >
          {step === 0 && (
            <div className="space-y-4">
              <h2 id="onboarding-title" className="text-xl font-bold text-slate-900">
                Welcome to Zilo
              </h2>
              <p className="text-sm leading-relaxed text-slate-600">
                We&apos;ll tailor labels, your sidebar, and defaults to how you sell — takes about a minute. You can
                change everything later in Settings and Features.
              </p>
              <ul className="space-y-2 text-sm text-slate-600">
                <li className="flex gap-2">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                  Pick your industry
                </li>
                <li className="flex gap-2">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                  Chat with AI or paste your website — we&apos;ll guide where to fill details
                </li>
                <li className="flex gap-2">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                  Choose a workspace preset, then connect channels when you want
                </li>
              </ul>
              <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={skipEntirely}
                  disabled={saving}
                  className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  Skip for now
                </button>
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-dark px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand"
                >
                  Let&apos;s go
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-slate-900">What kind of business are you?</h2>
              <p className="text-sm text-slate-600">This sets navigation labels and defaults across the web app.</p>
              <div className="grid max-h-64 grid-cols-1 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
                {SUPPORTED_INDUSTRIES.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    onClick={() => setIndustry(row.id)}
                    className={cn(
                      "flex gap-2 rounded-xl border p-3 text-left text-sm text-slate-900 transition",
                      industry === row.id
                        ? "border-[#009B3A] bg-emerald-50 ring-2 ring-[#4CD137]/40 ring-offset-2 ring-offset-white"
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
                    )}
                  >
                    <span className="text-lg leading-none">{row.emoji}</span>
                    <span>
                      <span className="font-medium text-slate-900">{row.label}</span>
                      <span className="mt-0.5 block text-xs text-slate-500">{row.blurb}</span>
                    </span>
                  </button>
                ))}
              </div>
              <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-between">
                <button
                  type="button"
                  onClick={() => setStep(0)}
                  className="text-sm font-medium text-slate-500 hover:text-slate-800"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={persistIndustryAndNext}
                  disabled={saving}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-dark px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand disabled:opacity-50"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-slate-900">Tell us about you or your business</h2>
              <p className="text-sm text-slate-600">
                Tap an option, chat with Zilo, or paste your website. This will make the AI customised for you.
                If we can&apos;t read a site, Zilo may ask a few questions — or fill everything in Settings whenever you like.
              </p>
              <OnboardingAiPanel
                industryId={industry}
                industryLabel={
                  SUPPORTED_INDUSTRIES.find((x) => x.id === industry)?.label || industry
                }
              />
              <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-between">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="text-sm font-medium text-slate-500 hover:text-slate-800"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-dark px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand"
                >
                  Continue to workspace
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-slate-900">How should your workspace look?</h2>
              <p className="text-sm text-slate-600">
                We&apos;ll turn on the right sidebar modules. You can fine-tune anytime under{" "}
                <strong className="text-slate-800">Features</strong>.
              </p>
              <div className="space-y-2">
                {(
                  [
                    {
                      id: "starter" as const,
                      title: "Starter",
                      desc: "Messages, customers, follow-ups, WhatsApp — lean inbox.",
                      icon: Zap,
                      color: "border-slate-200 bg-white hover:bg-slate-50",
                    },
                    {
                      id: "business" as const,
                      title: "Business",
                      desc: "Sales, orders, invoices, finance, analytics — full ops.",
                      icon: Briefcase,
                      color: "border-slate-200 bg-white hover:bg-slate-50",
                    },
                    {
                      id: "personal" as const,
                      title: "Personal / creator",
                      desc: "Social inbox, broadcast, scheduler — content & DMs.",
                      icon: User,
                      color: "border-slate-200 bg-white hover:bg-slate-50",
                    },
                    {
                      id: "full" as const,
                      title: "Turn everything on",
                      desc: "All optional modules visible — power user.",
                      icon: Sparkles,
                      color: "border-slate-200 bg-white hover:bg-amber-50",
                    },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setPreset(opt.id)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-xl border p-3 text-left text-slate-900 transition",
                      preset === opt.id
                        ? "border-[#009B3A] bg-emerald-50 ring-2 ring-[#4CD137]/50 ring-offset-2 ring-offset-white"
                        : opt.color,
                    )}
                  >
                    <opt.icon className="mt-0.5 h-5 w-5 shrink-0 text-[#009B3A]" aria-hidden />
                    <span>
                      <span className="font-semibold text-slate-900">{opt.title}</span>
                      <span className="mt-0.5 block text-xs text-slate-600">{opt.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
              <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-between">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="text-sm font-medium text-slate-500 hover:text-slate-800"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={persistPresetAndNext}
                  disabled={saving}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-dark px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand disabled:opacity-50"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-slate-900">Connect your channels (optional)</h2>
              <p className="text-sm text-slate-600">
                Link tools when you&apos;re ready — your workspace is already usable. Selling works across web, social,
                email, and WhatsApp.
              </p>
              <div className="space-y-2">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => completeAndNavigate("/dashboard/whatsapp")}
                  className="flex w-full items-center gap-3 rounded-xl border border-slate-200 p-3 text-left text-sm font-medium text-slate-800 transition hover:border-brand/30 hover:bg-slate-50 disabled:opacity-50"
                >
                  <MessageSquare className="h-5 w-5 shrink-0 text-green-600" />
                  WhatsApp — business messaging
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => completeAndNavigate("/dashboard/shopify")}
                  className="flex w-full items-center gap-3 rounded-xl border border-slate-200 p-3 text-left text-sm font-medium text-slate-800 transition hover:border-brand/30 hover:bg-slate-50 disabled:opacity-50"
                >
                  <ShoppingBag className="h-5 w-5 shrink-0 text-emerald-600" />
                  Shopify — store on autopilot
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => completeAndNavigate("/dashboard/integrations")}
                  className="flex w-full items-center gap-3 rounded-xl border border-slate-200 p-3 text-left text-sm font-medium text-slate-800 transition hover:border-brand/30 hover:bg-slate-50 disabled:opacity-50"
                >
                  <Plug className="h-5 w-5 shrink-0 text-brand-dark" />
                  Integrations — email, calendar, ads, more
                </button>
              </div>
              <p className="text-xs text-slate-500">
                Choosing a destination saves your setup and opens that page. Or finish below without leaving.
              </p>
              <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-between">
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="text-sm font-medium text-slate-500 hover:text-slate-800"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={() => setStep(5)}
                  className="text-sm font-medium text-brand-dark hover:text-brand-ink"
                >
                  Skip connections
                </button>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                <Check className="h-7 w-7" />
              </div>
              <h2 className="text-xl font-bold text-slate-900">You&apos;re ready to sell</h2>
              <p className="text-sm text-slate-600">
                Your workspace is configured. Head to Overview, open Zilo Chat anytime, and add connections under
                Integrations when you want.
              </p>
              <button
                type="button"
                onClick={completeOnboarding}
                disabled={saving}
                className="mt-2 w-full rounded-xl bg-brand-dark py-3 text-sm font-semibold text-white shadow-sm hover:bg-brand disabled:opacity-50"
              >
                {saving ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : "Go to dashboard"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
