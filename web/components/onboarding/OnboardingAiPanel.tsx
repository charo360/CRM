"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { Briefcase, Globe, Loader2, Send, Sparkles, User } from "lucide-react";
import { toast } from "sonner";
import { assistantApi, businessKnowledgeApi, onboardingApi, settingsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

type Msg = { role: "user" | "assistant"; content: string };

/** First tap — who are we setting up for? (no typing needed) */
const PRIMARY_CHOICES: {
  id: string;
  title: string;
  subtitle: string;
  message: string;
  icon: typeof User;
}[] = [
  {
    id: "solo",
    title: "Just me",
    subtitle: "Solo creator, freelancer, or personal brand",
    message:
      "I'm setting this up for myself — solo. Please guide me for a one-person workflow and what to fill in Zilo first.",
    icon: User,
  },
  {
    id: "business",
    title: "My business or team",
    subtitle: "Shop, services, company with staff",
    message:
      "I'm setting this up for my business or team. Please guide me on team-friendly setup and what to configure first.",
    icon: Briefcase,
  },
  {
    id: "both",
    title: "Both — me and my business",
    subtitle: "I wear both hats",
    message:
      "I'm both the owner and the face of the brand. Please suggest a balanced setup for personal and business use.",
    icon: Sparkles,
  },
];

/** Rotating tap options after each exchange — feels like the chat is offering next steps */
const SUGGESTION_ROUNDS: string[][] = [
  [
    "What should I set up first for sales and growth?",
    "Where do I add hours, FAQs, and business details?",
    "How do Features and Settings differ?",
  ],
  [
    "Walk me through connecting WhatsApp",
    "How do I turn on only the tools I need?",
    "Where is Business knowledge in the app?",
  ],
  [
    "Help me plan my first week in Zilo",
    "What should I connect: Shopify, email, or ads first?",
    "Give me a short checklist for my industry",
  ],
  [
    "Anything I'm missing before I go live?",
    "How does Zilo Chat help after onboarding?",
    "Summarize my next 3 actions",
  ],
];

type Analysis = {
  business_name?: string;
  summary: string;
  business_about_draft: string;
  products_services_hint: string;
  services: { name: string; description: string; price: string }[];
  location?: string;
  contact_email?: string;
  contact_phone?: string;
  website_url?: string;
  where_to_fill: { label: string; path: string; tip: string }[];
};

export function OnboardingAiPanel({
  industryId,
  industryLabel,
}: {
  industryId: string;
  industryLabel: string;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [convId, setConvId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [url, setUrl] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [applying, setApplying] = useState(false);
  const [urlSectionOpen, setUrlSectionOpen] = useState(true);
  const [personaSaved, setPersonaSaved] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const userMsgCount = useMemo(() => messages.filter((m) => m.role === "user").length, [messages]);
  const suggestionIdx = Math.min(Math.max(userMsgCount - 1, 0), SUGGESTION_ROUNDS.length - 1);
  const currentSuggestions = SUGGESTION_ROUNDS[suggestionIdx];
  /** When there is no site summary, prioritize “ask me questions” and Settings path in early rounds. */
  const displaySuggestions = useMemo(() => {
    const base = [...currentSuggestions];
    if (analysis) return base;
    if (suggestionIdx === 0) {
      return [
        "What should I set up first?",
        "Ask me a few questions — I don't have a website to analyze",
        "I'll type my business details in Settings instead",
      ];
    }
    if (suggestionIdx === 1) {
      return [
        "Walk me through connecting WhatsApp",
        "Ask what else you need to know about my business",
        "Remind me where to fill everything manually in Settings",
      ];
    }
    return base;
  }, [analysis, currentSuggestions, suggestionIdx]);
  /** Hide big cards once user sent a message OR we analyzed a URL (either path starts the guided chat). */
  const showPrimaryCards = userMsgCount === 0 && !analysis;

  useEffect(() => {
    setMessages([]);
  }, [industryLabel]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, analysis]);

  async function selectPersona(choice: (typeof PRIMARY_CHOICES)[number]) {
    void sendChat(choice.message);
    if (personaSaved) return;
    try {
      await settingsApi.update({ onboarding_persona: choice.id } as Record<string, unknown>);
      setPersonaSaved(true);
    } catch {
      // non-critical — chat still proceeds
    }
  }

  const sendChat = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;
      setSending(true);
      setMessages((m) => [...m, { role: "user", content: trimmed }]);
      const webContext = analysis
        ? `- Website analysis has already been shown on screen. Reference those facts naturally — do not re-ask for anything already in the summary.\n`
        : `- No website was analyzed. If you need to learn about their business, ask one short focused question at a time — avoid a long list of questions. Remind them they can also fill details manually in Dashboard → Settings → Business tab.\n`;
      const contextual =
        `[ONBOARDING MODE — read carefully before replying]
You are Zilo in first-time setup mode. This user is brand new — they have no CRM data yet.

Your ONLY job right now is to:
1. Help them understand what to set up first in Zilo based on their industry (${industryLabel}).
2. Answer any questions about how Zilo works — features, where things are, what each section does.
3. Guide them to the right places: Settings → Business, Features, Integrations, etc.
4. Be encouraging, concise, and practical — like a knowledgeable friend walking them through the app.

Rules for this conversation:
- Do NOT call any CRM data tools (customers, orders, revenue, etc.) — the user has no data yet.
- Do NOT ask for information you already have from context below.
- Keep replies short and scannable — bullet points over paragraphs.
- If they ask something unrelated to onboarding or Zilo, gently redirect: "Let's get you set up first — you can explore that once you're in."
${webContext}
User message: ${trimmed}`;
      try {
        const res = await assistantApi.chat({
          message: contextual,
          conversation_id: convId,
          auto_approve: true,
        });
        if (!convId) setConvId(res.conversation_id);
        setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      } catch (e) {
        setMessages((m) => m.slice(0, -1));
        toast.error(e instanceof Error ? e.message : "Message failed");
      } finally {
        setSending(false);
      }
    },
    [analysis, convId, industryId, industryLabel, sending],
  );

  async function analyzeUrl() {
    const u = url.trim();
    if (!u) {
      toast.error("Paste a website URL first");
      return;
    }
    setAnalyzing(true);
    setAnalysis(null);
    try {
      const res = await onboardingApi.analyzeWebsite({
        url: u,
        business_type: industryId,
      });
      setAnalysis({
        business_name: res.business_name ?? "",
        summary: res.summary ?? "",
        business_about_draft: res.business_about_draft ?? "",
        products_services_hint: res.products_services_hint ?? "",
        services: (res.services ?? []) as { name: string; description: string; price: string }[],
        location: res.location ?? "",
        contact_email: res.contact_email ?? "",
        contact_phone: res.contact_phone ?? "",
        website_url: res.website_url ?? "",
        where_to_fill: (res.where_to_fill ?? []) as unknown as { label: string; path: string; tip: string }[],
      });
      setUrlSectionOpen(false);
      toast.success("Website analyzed — scroll up for summary, or tap a suggested reply below.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not analyze URL");
    } finally {
      setAnalyzing(false);
    }
  }

  async function applyDraft() {
    if (!analysis?.business_about_draft?.trim()) {
      toast.error("Nothing to apply yet");
      return;
    }
    setApplying(true);
    try {
      // 1. Save business name, location, website to top-level Settings
      const settingsPatch: Record<string, unknown> = {
        business_type: industryId,
      };
      if (analysis.business_name) settingsPatch.business_name = analysis.business_name;
      if (analysis.location) settingsPatch.business_location = analysis.location;
      if (analysis.website_url) settingsPatch.website_url = analysis.website_url;
      await settingsApi.update(settingsPatch as Parameters<typeof settingsApi.update>[0]);

      // 2. Build services string — each service on its own line with price if available
      const servicesText = analysis.services.length > 0
        ? analysis.services
            .map((s) => {
              const price = s.price ? ` — ${s.price}` : "";
              const desc = s.description ? `\n  ${s.description}` : "";
              return `• ${s.name}${price}${desc}`;
            })
            .join("\n")
        : analysis.products_services_hint || undefined;

      // 3. Save full business knowledge
      await businessKnowledgeApi.update({
        business_type: industryId,
        business_description: analysis.business_about_draft,
        products_services: servicesText,
        business_location: analysis.location || undefined,
        website_url: analysis.website_url || undefined,
        contact_email: analysis.contact_email || undefined,
        contact_phone: analysis.contact_phone || undefined,
      } as Record<string, unknown>);

      toast.success("Profile saved — business name, location, services and about are all filled in Settings.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save");
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="space-y-4">

      {/* Primary one-tap choices */}
      {showPrimaryCards && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Pick one to continue</p>
          <div className="grid gap-2 sm:grid-cols-3">
            {PRIMARY_CHOICES.map((c) => (
              <button
                key={c.id}
                type="button"
                disabled={sending}
                onClick={() => void selectPersona(c)}
                className={cn(
                  "flex flex-col items-start rounded-2xl border-2 border-slate-200 bg-white p-3 text-left text-slate-900 transition",
                  "hover:border-[#009B3A]/40 hover:bg-emerald-50/80 hover:shadow-sm",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              >
                <c.icon className="h-5 w-5 text-[#009B3A]" aria-hidden />
                <span className="mt-2 text-sm font-semibold text-slate-900">{c.title}</span>
                <span className="mt-0.5 text-[11px] leading-snug text-slate-500">{c.subtitle}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Website — collapsible section */}
      <div className="rounded-xl border border-[#009B3A]/20 bg-gradient-to-br from-emerald-50/70 to-white p-4 text-slate-900">
        <button
          type="button"
          onClick={() => setUrlSectionOpen((o) => !o)}
          className="flex w-full items-center justify-between gap-2 text-left text-slate-900"
        >
          <div className="flex items-center gap-2 text-[#009B3A]">
            <Globe className="h-4 w-4 shrink-0" aria-hidden />
            <span className="text-xs font-semibold uppercase tracking-wide">Have a website?</span>
          </div>
          <span className="text-xs font-medium text-[#009B3A]">{urlSectionOpen ? "Hide" : "Paste URL"}</span>
        </button>
        {urlSectionOpen && (
          <>
            <p className="mt-2 text-xs text-slate-600">
              We read public pages only. If it fails or you have no site, use chat — Zilo can ask you questions — or{" "}
              <Link href="/dashboard/settings" className="font-semibold text-[#009B3A] hover:underline">
                fill details in Settings
              </Link>
              .
            </p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void analyzeUrl(); } }}
                placeholder="https://yourbusiness.com"
                className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[#009B3A]"
              />
              <button
                type="button"
                onClick={analyzeUrl}
                disabled={analyzing || sending}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[#009B3A] px-4 py-2 text-sm font-semibold text-white hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-50"
              >
                {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {analyzing ? "Analyzing…" : "Analyze site"}
              </button>
            </div>
          </>
        )}
      </div>

      {/* Website analysis results */}
      {analysis && (
        <div className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">What we found</p>
          {analysis.business_name && (
            <p className="text-sm font-semibold text-slate-900">{analysis.business_name}</p>
          )}
          <p className="text-sm text-slate-700">{analysis.summary}</p>
          {(analysis.location || analysis.contact_email || analysis.contact_phone) && (
            <div className="flex flex-wrap gap-3 text-xs text-slate-500">
              {analysis.location && <span>📍 {analysis.location}</span>}
              {analysis.contact_email && <span>✉️ {analysis.contact_email}</span>}
              {analysis.contact_phone && <span>📞 {analysis.contact_phone}</span>}
            </div>
          )}
          {analysis.services.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">Services & products found</p>
              <ul className="space-y-2">
                {analysis.services.map((s, i) => (
                  <li key={i} className="rounded-lg border border-white/80 bg-white/90 px-3 py-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-900">{s.name}</span>
                      {s.price && (
                        <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">
                          {s.price}
                        </span>
                      )}
                    </div>
                    {s.description && (
                      <p className="mt-0.5 text-xs text-slate-500">{s.description}</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {analysis.where_to_fill.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-slate-600">Where to fill things next</p>
              <ul className="space-y-2">
                {analysis.where_to_fill.map((w, i) => (
                  <li
                    key={i}
                    className="flex flex-col gap-0.5 rounded-lg border border-white/80 bg-white/90 p-2 text-sm sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <span className="font-medium text-slate-900">{w.label}</span>
                      <p className="text-xs text-slate-500">{w.tip}</p>
                    </div>
                    <Link
                      href={w.path.startsWith("/") ? w.path : `/${w.path}`}
                      className="shrink-0 text-xs font-semibold text-[#009B3A] hover:underline"
                    >
                      Open →
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button
            type="button"
            onClick={applyDraft}
            disabled={applying}
            className="w-full rounded-lg bg-emerald-600 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {applying ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : "Save business name, services & profile to Settings"}
          </button>
        </div>
      )}

      {/* Chat messages — only show once conversation has started */}
      {(messages.length > 0 || sending) && (
      <div className="rounded-xl border border-slate-200 bg-slate-50/60">
        <div className="flex max-h-72 flex-col gap-3 overflow-y-auto p-3">
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "max-w-[95%] rounded-xl px-3 py-2 text-sm leading-relaxed",
                m.role === "user"
                  ? "ml-auto bg-[#009B3A] text-white"
                  : "mr-auto border border-slate-200 bg-white text-slate-800 shadow-sm",
              )}
            >
              {m.role === "assistant" ? (
                <div className="prose prose-sm prose-slate max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0 prose-strong:text-slate-900 prose-a:text-[#009B3A]">
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap [text-wrap:pretty]">{m.content}</p>
              )}
            </div>
          ))}
          {sending && (
            <div className="mr-auto flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-400 shadow-sm">
              <Loader2 className="h-3 w-3 animate-spin" /> Zilo is thinking…
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
      )}

      {/* Suggestion buttons — shown after first exchange */}
      {!showPrimaryCards && (
        <div>
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-500">Suggested replies</p>
          <div className="flex flex-col gap-2">
            {displaySuggestions.map((label) => (
              <button
                key={label}
                type="button"
                onClick={() => void sendChat(label)}
                disabled={sending}
                className={cn(
                  "rounded-xl border-2 border-[#009B3A]/30 bg-white px-4 py-2.5 text-left text-sm font-medium text-slate-900",
                  "shadow-sm transition hover:border-[#009B3A]/55 hover:bg-emerald-50/90",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Free-text input */}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const t = input.trim();
          if (!t) return;
          setInput("");
          void sendChat(t);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Or type your own question…"
          className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[#009B3A]"
          disabled={sending}
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="inline-flex shrink-0 items-center justify-center rounded-xl bg-[#009B3A] px-3 py-2 text-sm font-semibold text-white hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-40"
          aria-label="Send"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}
