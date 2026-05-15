"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  seoAgentApi,
  seoApi,
  blogApi,
  type SeoKeyword,
  type SeoBusinessContext,
  type KeywordTrackerRow,
  type SeoBrief,
  type SeoBriefAction,
} from "@/lib/api";
import { ArrowRight, CalendarDays, Clock, PenLine, RefreshCw, Rss, Search, Zap } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

type ChatMsg = {
  role: "user" | "assistant";
  content: string;
  tool_steps?: { tool: string; input?: string; output?: string }[];
};

type PublishState = "idle" | "generating" | "publishing" | "done" | "error";

// ── Helpers ───────────────────────────────────────────────────────────────────

function difficultyBadge(d: string) {
  if (!d) return null;
  const styles: Record<string, string> = {
    low: "bg-green-100 text-green-700 border-green-200",
    easy: "bg-green-100 text-green-700 border-green-200",
    medium: "bg-yellow-100 text-yellow-700 border-yellow-200",
    high: "bg-red-100 text-red-700 border-red-200",
    hard: "bg-red-100 text-red-700 border-red-200",
  };
  const label: Record<string, string> = { low: "Easy", easy: "Easy", medium: "Medium", high: "Hard", hard: "Hard" };
  const key = d.toLowerCase();
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${styles[key] ?? "bg-slate-100 text-slate-500 border-slate-200"}`}>
      {label[key] ?? d}
    </span>
  );
}

function intentBadge(i: string) {
  if (!i) return null;
  const styles: Record<string, string> = {
    transactional: "bg-emerald-100 text-emerald-700",
    local: "bg-blue-100 text-blue-700",
    informational: "bg-purple-100 text-purple-700",
    navigational: "bg-orange-100 text-orange-700",
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium capitalize ${styles[i.toLowerCase()] ?? "bg-slate-100 text-slate-500"}`}>
      {i}
    </span>
  );
}

function formatVolume(v: number) {
  if (!v) return <span className="text-slate-400 text-xs">—</span>;
  if (v >= 1000) return <span className="font-semibold text-slate-800">{(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k</span>;
  return <span className="font-semibold text-slate-800">{v.toLocaleString()}</span>;
}

// ── Quick action chips shown in empty chat ─────────────────────────────────────

const QUICK_ACTIONS = [
  { icon: "🔍", label: "Find keywords for my business", msg: "Find the best keywords for my business and show me search volumes" },
  { icon: "✍️", label: "Write a blog post", msg: "Write an SEO blog post for my top keyword and save it as a draft" },
  { icon: "📅", label: "Make a content calendar", msg: "Create a 4-week content calendar for my business" },
  { icon: "🔧", label: "Audit my website", msg: "Audit my website for SEO issues and tell me what to fix" },
  { icon: "🏆", label: "Check my rankings", msg: "Check my current Google rankings for my main keywords" },
  { icon: "🕵️", label: "Spy on competitors", msg: "Find what keywords my competitors are ranking for" },
];

// ── Keyword Tracker Row Component ─────────────────────────────────────────────

function TrackerRow({
  row,
  onPublish,
  publishState,
  publishUrl,
}: {
  row: KeywordTrackerRow;
  onPublish: (row: KeywordTrackerRow) => void;
  publishState: PublishState;
  publishUrl: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasPosts = (row.posts ?? []).length > 0;

  return (
    <div className="border-b border-slate-100 last:border-0">
      <div className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50/60 transition-colors">
        {/* Keyword + idea */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-slate-800 text-sm">{row.keyword}</span>
            {intentBadge(row.intent)}
            {difficultyBadge(row.difficulty)}
          </div>
          {row.content_idea && (
            <p className="text-xs text-slate-500 mt-0.5 truncate">💡 {row.content_idea}</p>
          )}
        </div>

        {/* Volume */}
        <div className="text-right shrink-0 w-16">
          <p className="text-[10px] text-slate-400 mb-0.5">searches/mo</p>
          {formatVolume(row.search_volume)}
        </div>

        {/* Posts */}
        <div className="shrink-0 w-20 text-center">
          {hasPosts ? (
            <button
              onClick={() => setExpanded(e => !e)}
              className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full hover:bg-emerald-100"
            >
              {row.posts.length} post{row.posts.length !== 1 ? "s" : ""} {expanded ? "▲" : "▼"}
            </button>
          ) : (
            <span className="text-[11px] text-slate-400">No posts yet</span>
          )}
        </div>

        {/* Publish action */}
        <div className="shrink-0 w-36 flex justify-end">
          {publishState === "done" ? (
            <a
              href={publishUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] px-3 py-1.5 bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700 whitespace-nowrap flex items-center gap-1"
            >
              ✓ View post →
            </a>
          ) : (
            <button
              onClick={() => onPublish(row)}
              disabled={publishState === "generating" || publishState === "publishing"}
              className="text-[11px] px-3 py-1.5 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 disabled:opacity-60 whitespace-nowrap flex items-center gap-1"
            >
              {publishState === "generating" ? (
                <><span className="animate-spin inline-block">⚙</span> Writing…</>
              ) : publishState === "publishing" ? (
                <><span className="animate-spin inline-block">⚙</span> Publishing…</>
              ) : publishState === "error" ? (
                "↺ Retry"
              ) : (
                "→ Publish to Blog"
              )}
            </button>
          )}
        </div>
      </div>

      {/* Expanded posts list */}
      {expanded && hasPosts && (
        <div className="px-4 pb-3 space-y-1.5 bg-slate-50/60 border-t border-slate-100">
          {row.posts.map((p, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="text-emerald-500">✓</span>
              <a
                href={p.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-slate-700 hover:text-indigo-600 underline underline-offset-2 flex-1 truncate"
              >
                {p.title}
              </a>
              <span className="text-slate-400 shrink-0">
                {p.published_at ? new Date(p.published_at).toLocaleDateString() : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Combined SEO page: coach + keyword tracker (embedded in /dashboard/seo) ─

/** Tabs on /dashboard/seo — opener from Start here roadmap */
export type SeoHubWorkspaceOpenTab =
  | "keywords"
  | "calendar"
  | "blog"
  | "autoblog"
  | "scheduler";

function SeoHubWorkspace({
  onOpenTab,
}: {
  onOpenTab?: (tab: SeoHubWorkspaceOpenTab) => void;
}) {
  const [profile, setProfile] = useState<SeoBusinessContext | null>(null);

  // Chat state
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [convId, setConvId] = useState<string | undefined>();
  const [chatLoading, setChatLoading] = useState(false);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Keyword tracker state
  const [trackerRows, setTrackerRows] = useState<KeywordTrackerRow[]>([]);
  const [trackerLoading, setTrackerLoading] = useState(true);
  const [publishStates, setPublishStates] = useState<Record<string, PublishState>>({});
  const [publishUrls, setPublishUrls] = useState<Record<string, string>>({});
  const [trackerError, setTrackerError] = useState("");

  // Volume enrichment
  const [enriching, setEnriching] = useState(false);
  const [enrichMsg, setEnrichMsg] = useState("");

  // Brief (autonomous SEO expert) state
  const [brief, setBrief] = useState<SeoBrief | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const [briefExecuting, setBriefExecuting] = useState<string | null>(null);

  // Quick-generate keywords banner
  const [quickGenLoading, setQuickGenLoading] = useState(false);
  const [quickGenDone, setQuickGenDone] = useState(false);

  const loadTracker = useCallback(async (silent = false) => {
    if (!silent) setTrackerLoading(true);
    try {
      const data = await blogApi.getKeywordTracker();
      setTrackerRows(data.keywords ?? []);
    } catch {
      // tracker empty — that's fine
    } finally {
      if (!silent) setTrackerLoading(false);
    }
  }, []);

  const loadBrief = useCallback(async (refresh = false) => {
    setBriefLoading(true);
    try {
      const data = await seoAgentApi.brief(refresh);
      setBrief(data);
    } catch {
      // brief unavailable — non-fatal
    } finally {
      setBriefLoading(false);
    }
  }, []);

  async function enrichVolumes() {
    setEnriching(true);
    setEnrichMsg("");
    try {
      const res = await blogApi.enrichVolumes();
      if (res.updated > 0) {
        setEnrichMsg(`✓ Updated ${res.updated} keyword${res.updated !== 1 ? "s" : ""} with real volumes`);
        await loadTracker();
      } else {
        setEnrichMsg(res.message ?? "No new volumes found");
      }
    } catch {
      setEnrichMsg("Volume lookup failed");
    } finally {
      setEnriching(false);
      setTimeout(() => setEnrichMsg(""), 4000);
    }
  }

  useEffect(() => {
    seoApi.businessContext().then(setProfile).catch(() => {});
    loadTracker();
    loadBrief();
  }, [loadTracker, loadBrief]);

  useEffect(() => {
    const el = messagesScrollRef.current;
    if (!el) return;
    // scrollIntoView on a child caused the whole page to jump when opening this tab — keep scroll inside the chat panel only
    if (messages.length === 0 && !chatLoading) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [messages, chatLoading]);

  // ── Chat ──────────────────────────────────────────────────────────────────

  async function send(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || chatLoading) return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: msg }]);
    setChatLoading(true);
    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      const res = await seoAgentApi.chat(msg, convId, history);
      setConvId(res.conversation_id);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: res.reply,
        tool_steps: res.tool_steps,
      }]);
      // Silently refresh tracker in background (agent may have added keywords/posts)
      setTimeout(() => loadTracker(true), 1500);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `Sorry, something went wrong: ${e instanceof Error ? e.message : "Please try again."}`,
      }]);
    } finally {
      setChatLoading(false);
    }
  }

  // ── Quick generate keywords ────────────────────────────────────────────────

  async function quickGenerateKeywords() {
    if (!profile?.business_type) return;
    setQuickGenLoading(true);
    setTrackerError("");
    try {
      const res = await seoApi.generateKeywords(profile.business_type, profile.location);
      const kws = (res.keywords as SeoKeyword[]).slice(0, 20);
      // Save all to tracker
      await Promise.all(kws.map(kw =>
        blogApi.saveKeywordToTracker({
          keyword: kw.keyword,
          search_volume: kw.search_volume ?? 0,
          difficulty: kw.difficulty,
          intent: kw.intent,
          content_idea: kw.content_idea,
        }).catch(() => {})
      ));
      await loadTracker();
      setQuickGenDone(true);
    } catch (e) {
      setTrackerError(e instanceof Error ? e.message : "Failed to generate keywords");
    } finally {
      setQuickGenLoading(false);
    }
  }

  // ── Execute autonomous brief action ───────────────────────────────────────

  async function executeAction(action: SeoBriefAction) {
    if (!action.agent_prompt?.trim()) return;
    setBriefExecuting(action.id);
    setMessages(prev => [...prev, {
      role: "user",
      content: `[Auto-executing: ${action.title}]\n\n${action.agent_prompt}`,
    }]);
    setChatLoading(true);
    try {
      const res = await seoAgentApi.executeAction(action.agent_prompt, convId);
      setConvId(res.conversation_id);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: res.reply,
        tool_steps: res.tool_steps,
      }]);
      setTimeout(() => { loadTracker(true); loadBrief(true); }, 1500);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `Action failed: ${e instanceof Error ? e.message : "Please try again."}`,
      }]);
    } finally {
      setChatLoading(false);
      setBriefExecuting(null);
    }
  }

  // ── Publish keyword → blog ─────────────────────────────────────────────────

  async function publishKeyword(row: KeywordTrackerRow) {
    const key = row.keyword;
    setPublishStates(s => ({ ...s, [key]: "generating" }));
    setTrackerError("");
    try {
      const post = await seoApi.generateBlog({
        topic: row.content_idea || row.keyword,
        keywords: [row.keyword],
        tone: "professional",
        length: "medium",
        business_name: profile?.business_name,
        language: profile?.language || "English",
        include_faq: true,
      });
      setPublishStates(s => ({ ...s, [key]: "publishing" }));
      const result = await blogApi.publishFromSeo({
        title: post.title,
        content: post.content,
        keywords: post.keywords || [row.keyword],
        excerpt: post.meta_description,
      });
      // Link the post back to the keyword
      await blogApi.linkPostToKeyword({
        keyword: row.keyword,
        post_title: post.title,
        post_url: result.post_url,
      }).catch(() => {});
      setPublishUrls(u => ({ ...u, [key]: result.post_url }));
      setPublishStates(s => ({ ...s, [key]: "done" }));
      await loadTracker();
    } catch (e) {
      setTrackerError(e instanceof Error ? e.message : "Publish failed — is your Autoblog activated?");
      setPublishStates(s => ({ ...s, [key]: "error" }));
    }
  }

  const isEmpty = messages.length === 0;
  const name = profile?.business_name?.trim();

  const roadmap = [
    { tab: "keywords" as const, label: "Keywords", hint: "Research & save volumes", Icon: Search },
    { tab: "calendar" as const, label: "Calendar", hint: "Plan dates", Icon: CalendarDays },
    { tab: "blog" as const, label: "Write posts", hint: "Draft articles", Icon: PenLine },
  ];

  const moreTools = [
    { tab: "scheduler" as const, label: "Schedule", Icon: Clock },
    { tab: "autoblog" as const, label: "Autoblog", Icon: Rss },
  ];

  return (
    <div className="max-w-7xl mx-auto w-full flex flex-col gap-4 sm:gap-5 flex-1 min-h-0">
      {onOpenTab && (
        <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-slate-50/80 to-emerald-50/40 px-4 py-4 sm:px-5 sm:py-4 shadow-sm">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Your workflow</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">Everything you need, in order</p>
              <p className="mt-1 text-xs text-slate-600 max-w-xl leading-relaxed">
                Research phrases on <strong className="font-medium text-slate-800">Keywords</strong> (saved automatically each month), turn them into a{" "}
                <strong className="font-medium text-slate-800">Calendar</strong>, then{" "}
                <strong className="font-medium text-slate-800">Write posts</strong> or use Autoblog. Use the tabs above anytime — this is just the guided path.
              </p>
            </div>
          </div>

          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            {roadmap.map((step, i) => {
              const Ico = step.Icon;
              return (
                <React.Fragment key={step.tab}>
                  {i > 0 && (
                    <ArrowRight className="hidden sm:block h-4 w-4 shrink-0 text-slate-300" aria-hidden />
                  )}
                  <button
                    type="button"
                    onClick={() => onOpenTab(step.tab)}
                    className="flex min-w-[140px] flex-1 items-start gap-2.5 rounded-xl border border-slate-200/90 bg-white px-3 py-2.5 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-colors hover:border-emerald-300 hover:bg-emerald-50/60 sm:flex-initial sm:min-w-0"
                  >
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white">
                      <Ico className="h-4 w-4" aria-hidden />
                    </span>
                    <span>
                      <span className="block text-xs font-bold text-slate-900">{i + 1}. {step.label}</span>
                      <span className="block text-[11px] text-slate-500">{step.hint}</span>
                    </span>
                  </button>
                </React.Fragment>
              );
            })}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100/90 pt-3">
            <span className="text-[11px] font-medium text-slate-500">Also:</span>
            {moreTools.map(({ tab, label, Icon: Ico }) => (
              <button
                key={tab}
                type="button"
                onClick={() => onOpenTab(tab)}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:border-emerald-200 hover:bg-emerald-50/50"
              >
                <Ico className="h-3 w-3 text-slate-500" aria-hidden />
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-4 sm:gap-5 flex-1 min-h-0">
        {/* ── LEFT: AI Chat ─────────────────────────────────────────────────── */}
        <div className="flex flex-col w-full lg:w-[480px] xl:w-[520px] shrink-0 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden" style={{ minHeight: 520, maxHeight: "min(780px, calc(100vh - 14rem))" }}>
          {/* Chat header */}
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-gradient-to-r from-emerald-50 to-white shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center text-white text-sm font-bold shrink-0">Z</div>
              <div>
                <p className="text-sm font-semibold text-slate-800">Zilo SEO Coach</p>
                <p className="text-[11px] text-emerald-600 font-medium flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                  Can research, write &amp; publish for you
                </p>
              </div>
            </div>
            <button
              onClick={() => { setMessages([]); setConvId(undefined); }}
              className="text-xs text-slate-400 hover:text-slate-600 px-2 py-1 rounded-lg hover:bg-slate-100"
            >
              New chat
            </button>
          </div>

          {/* Messages */}
          <div ref={messagesScrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {isEmpty && (
              <div className="space-y-5">
                {/* Greeting */}
                <div className="flex gap-3 items-start">
                  <div className="w-7 h-7 rounded-full bg-emerald-600 flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">Z</div>
                  <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-800 leading-relaxed max-w-xs">
                    {name
                      ? <>Hi! I&apos;m your SEO coach for <strong>{name}</strong>. I can research keywords, write blog posts, audit your site, and publish everything — just ask!</>
                      : <>Hi! I&apos;m your SEO coach. I can research keywords, write blog posts, audit your site, and publish everything. What would you like to do?</>}
                  </div>
                </div>

                {/* Quick action chips */}
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide px-1">Quick actions</p>
                  <div className="grid grid-cols-1 gap-2">
                    {QUICK_ACTIONS.map(qa => (
                      <button
                        key={qa.label}
                        onClick={() => send(qa.msg)}
                        className="flex items-center gap-3 text-left px-4 py-2.5 rounded-xl border border-slate-200 bg-white hover:border-emerald-300 hover:bg-emerald-50 transition-colors group"
                      >
                        <span className="text-lg shrink-0">{qa.icon}</span>
                        <span className="text-sm text-slate-700 group-hover:text-emerald-800 font-medium">{qa.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex gap-2.5 items-start ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "assistant" && (
                  <div className="w-7 h-7 rounded-full bg-emerald-600 flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">Z</div>
                )}
                <div className={`flex flex-col gap-1.5 max-w-[85%] ${m.role === "user" ? "items-end" : "items-start"}`}>
                  {/* Tool steps */}
                  {m.tool_steps && m.tool_steps.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {Array.from(new Set(m.tool_steps.map(s => s.tool))).map(tool => (
                        <span key={tool} className="text-[10px] bg-emerald-50 border border-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">
                          ⚙ {tool.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-emerald-600 text-white rounded-tr-sm"
                      : "bg-slate-100 text-slate-800 rounded-tl-sm"
                  }`}>
                    {m.role === "assistant" ? (
                      <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-1.5 prose-ul:my-1 prose-li:my-0">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                      </div>
                    ) : m.content}
                  </div>
                </div>
              </div>
            ))}

            {chatLoading && (
              <div className="flex gap-2.5 items-start">
                <div className="w-7 h-7 rounded-full bg-emerald-600 flex items-center justify-center text-white text-xs font-bold shrink-0">Z</div>
                <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 flex gap-1.5 items-center">
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="px-4 py-3 border-t border-slate-100 shrink-0 bg-white">
            <div className="flex gap-2 items-end">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                }}
                placeholder="Ask me anything… e.g. 'Write a blog post about our top service'"
                className="flex-1 resize-none border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 max-h-32"
                style={{ minHeight: "42px" }}
              />
              <button
                onClick={() => send()}
                disabled={chatLoading || !input.trim()}
                className="h-10 w-10 flex items-center justify-center bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 disabled:opacity-40 shrink-0"
              >
                <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                </svg>
              </button>
            </div>
            <p className="text-[10px] text-slate-300 mt-1.5 px-1">Enter to send · Shift+Enter for new line</p>
          </div>
        </div>

        {/* ── RIGHT: Keyword + Blog Tracker ────────────────────────────────── */}
        <div className="flex-1 min-w-0 flex flex-col gap-4">

          {/* Tracker header card */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h2 className="text-base font-bold text-slate-800 flex items-center gap-2">
                  📊 Keyword &amp; Blog Tracker
                </h2>
                <p className="text-sm text-slate-500 mt-0.5">
                  All your keywords with search volumes — click <strong>Publish to Blog</strong> to generate &amp; publish a post instantly.
                </p>
              </div>
              <div className="flex gap-2 shrink-0 flex-wrap">
                {enrichMsg && (
                  <span className="text-xs text-emerald-700 self-center font-medium">{enrichMsg}</span>
                )}
                <button
                  onClick={enrichVolumes}
                  disabled={enriching}
                  className="text-xs px-3 py-1.5 rounded-lg border border-indigo-200 text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 flex items-center gap-1"
                  title="Look up real search volumes from Google for keywords missing data"
                >
                  {enriching ? <><span className="animate-spin inline-block">⚙</span> Fetching…</> : "📊 Get volumes"}
                </button>
                <button
                  onClick={() => loadTracker()}
                  className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 flex items-center gap-1"
                >
                  ↻ Refresh
                </button>
                {profile?.business_type && (
                  <button
                    onClick={quickGenerateKeywords}
                    disabled={quickGenLoading}
                    className="text-xs px-4 py-1.5 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {quickGenLoading ? (
                      <><span className="animate-spin">⚙</span> Generating…</>
                    ) : quickGenDone ? (
                      "✓ Keywords loaded"
                    ) : (
                      "🔍 Get keyword ideas"
                    )}
                  </button>
                )}
              </div>
            </div>

            {/* Stats row */}
            {trackerRows.length > 0 && (
              <div className="mt-4 grid grid-cols-3 sm:grid-cols-4 gap-3">
                <div className="bg-slate-50 rounded-xl border border-slate-100 p-3 text-center">
                  <p className="text-2xl font-bold text-slate-800">{trackerRows.length}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">Keywords tracked</p>
                </div>
                <div className="bg-slate-50 rounded-xl border border-slate-100 p-3 text-center">
                  <p className="text-2xl font-bold text-emerald-700">
                    {trackerRows.reduce((n, r) => n + (r.posts?.length ?? 0), 0)}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5">Posts published</p>
                </div>
                <div className="bg-slate-50 rounded-xl border border-slate-100 p-3 text-center">
                  <p className="text-2xl font-bold text-blue-700">
                    {trackerRows.filter(r => r.difficulty?.toLowerCase() === "low" || r.difficulty?.toLowerCase() === "easy").length}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5">Easy wins</p>
                </div>
                <div className="hidden sm:block bg-slate-50 rounded-xl border border-slate-100 p-3 text-center">
                  <p className="text-2xl font-bold text-slate-800">
                    {trackerRows.filter(r => r.search_volume > 0).length > 0
                      ? Math.round(trackerRows.filter(r => r.search_volume > 0).reduce((s, r) => s + r.search_volume, 0) / trackerRows.filter(r => r.search_volume > 0).length).toLocaleString()
                      : "—"}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5">Avg vol/mo</p>
                </div>
              </div>
            )}
          </div>

          {/* Error alert */}
          {trackerError && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
              <span className="shrink-0">⚠</span>
              <span>{trackerError}</span>
              <button onClick={() => setTrackerError("")} className="ml-auto shrink-0 text-red-400 hover:text-red-600">×</button>
            </div>
          )}

          {/* Tracker table */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex-1">
            {/* Table header */}
            <div className="flex items-center gap-3 px-4 py-2.5 bg-slate-50 border-b border-slate-100">
              <div className="flex-1 text-[11px] font-semibold text-slate-500 uppercase tracking-wide">Keyword</div>
              <div className="w-16 text-right text-[11px] font-semibold text-slate-500 uppercase tracking-wide">Volume</div>
              <div className="w-20 text-center text-[11px] font-semibold text-slate-500 uppercase tracking-wide">Posts</div>
              <div className="w-36 text-right text-[11px] font-semibold text-slate-500 uppercase tracking-wide">Action</div>
            </div>

            {trackerLoading ? (
              <div className="flex items-center justify-center py-16 gap-3 text-slate-400">
                <span className="animate-spin text-xl">⚙</span>
                <span className="text-sm">Loading tracker…</span>
              </div>
            ) : trackerRows.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-4 px-6 text-center">
                <div className="text-5xl">🔍</div>
                <div>
                  <p className="font-semibold text-slate-700 text-base">No keywords tracked yet</p>
                  <p className="text-sm text-slate-500 mt-1 max-w-sm">
                    Click <strong>Get keyword ideas</strong> above, or ask the SEO Coach on the left — it will research keywords and add them here automatically.
                  </p>
                </div>
                {profile?.business_type && (
                  <button
                    onClick={quickGenerateKeywords}
                    disabled={quickGenLoading}
                    className="mt-2 px-5 py-2.5 bg-emerald-600 text-white text-sm font-semibold rounded-xl hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {quickGenLoading ? "Generating…" : "🔍 Get my keyword ideas now"}
                  </button>
                )}
              </div>
            ) : (
              <div className="divide-y divide-slate-50">
                {trackerRows.map(row => (
                  <TrackerRow
                    key={row.keyword}
                    row={row}
                    onPublish={publishKeyword}
                    publishState={publishStates[row.keyword] ?? "idle"}
                    publishUrl={publishUrls[row.keyword] ?? ""}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Bottom hint */}
          <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 px-4 py-3 flex items-center gap-3">
            <span className="text-emerald-600 text-lg shrink-0">💬</span>
            <p className="text-xs text-emerald-800">
              <strong>Pro tip:</strong> Ask the coach: <em>Research 20 keywords for my business and add them to the tracker</em> — it will fill this table automatically, with real search volumes.
            </p>
          </div>
        </div>
      </div>

      {/* ── SEO Expert Brief ─────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden min-h-[460px]">
        {/* Brief header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-gradient-to-r from-indigo-50/60 to-white">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shrink-0">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-800">SEO Expert — Autonomous Brief</p>
              <p className="text-[11px] text-slate-500">
                {brief
                  ? `Updated ${Math.round((Date.now() - new Date(brief.generated_at).getTime()) / 3600000)} h ago · next check ${brief.next_check}`
                  : briefLoading ? "Analysing your SEO…" : "No brief yet"}
              </p>
            </div>
          </div>
          <button
            onClick={() => loadBrief(true)}
            disabled={briefLoading}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${briefLoading ? "animate-spin" : ""}`} />
            {briefLoading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {briefLoading && !brief && (
          <div className="p-5 space-y-5 animate-pulse">
            {/* health row skeleton */}
            <div className="flex items-start gap-4">
              <div className="w-20 h-20 rounded-2xl bg-slate-100 shrink-0" />
              <div className="flex-1 space-y-2 pt-1">
                <div className="h-3 bg-slate-100 rounded w-3/4" />
                <div className="h-3 bg-slate-100 rounded w-full" />
                <div className="h-3 bg-slate-100 rounded w-5/6" />
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div className="space-y-1.5">
                    <div className="h-2.5 bg-slate-100 rounded w-1/3" />
                    <div className="h-2.5 bg-slate-100 rounded w-full" />
                    <div className="h-2.5 bg-slate-100 rounded w-4/5" />
                  </div>
                  <div className="space-y-1.5">
                    <div className="h-2.5 bg-slate-100 rounded w-1/3" />
                    <div className="h-2.5 bg-slate-100 rounded w-full" />
                    <div className="h-2.5 bg-slate-100 rounded w-3/4" />
                  </div>
                </div>
              </div>
            </div>
            {/* action cards skeleton */}
            <div>
              <div className="h-2.5 bg-slate-100 rounded w-40 mb-3" />
              <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="border border-slate-100 rounded-xl p-3.5 space-y-2">
                    <div className="flex gap-2 items-center">
                      <div className="w-6 h-6 bg-slate-100 rounded" />
                      <div className="h-3 bg-slate-100 rounded flex-1" />
                    </div>
                    <div className="h-2.5 bg-slate-100 rounded w-full" />
                    <div className="h-2.5 bg-slate-100 rounded w-3/4" />
                    <div className="flex justify-between items-center pt-1">
                      <div className="h-5 bg-slate-100 rounded-full w-16" />
                      <div className="h-6 bg-slate-100 rounded-lg w-16" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {brief && (
          <div className="p-5 space-y-5">
            {/* Health row */}
            <div className="flex flex-wrap items-start gap-4">
              {/* Score */}
              <div className={`flex flex-col items-center justify-center w-20 h-20 rounded-2xl border-2 shrink-0 ${
                brief.health_grade === "A" ? "border-emerald-400 bg-emerald-50 text-emerald-700" :
                brief.health_grade === "B" ? "border-blue-400 bg-blue-50 text-blue-700" :
                brief.health_grade === "C" ? "border-yellow-400 bg-yellow-50 text-yellow-700" :
                brief.health_grade === "D" ? "border-orange-400 bg-orange-50 text-orange-700" :
                "border-red-400 bg-red-50 text-red-700"
              }`}>
                <span className="text-3xl font-black leading-none">{brief.health_grade}</span>
                <span className="text-[11px] font-semibold mt-0.5">{brief.health_score}/100</span>
              </div>

              {/* Summary + wins/gaps */}
              <div className="flex-1 min-w-0 space-y-3">
                <p className="text-sm text-slate-700 leading-relaxed">{brief.status_summary}</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  {brief.wins?.length > 0 && (
                    <div>
                      <p className="text-[11px] font-bold text-emerald-700 uppercase tracking-wide mb-1.5">✓ Wins</p>
                      <ul className="space-y-0.5">
                        {brief.wins.slice(0, 3).map((w, i) => (
                          <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                            <span className="text-emerald-500 shrink-0 mt-0.5">•</span>{w}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {brief.gaps?.length > 0 && (
                    <div>
                      <p className="text-[11px] font-bold text-amber-700 uppercase tracking-wide mb-1.5">⚡ Gaps</p>
                      <ul className="space-y-0.5">
                        {brief.gaps.slice(0, 3).map((g, i) => (
                          <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                            <span className="text-amber-500 shrink-0 mt-0.5">•</span>{g}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Action cards */}
            {brief.actions?.length > 0 && (
              <div>
                <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide mb-2.5">Recommended actions</p>
                <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                  {brief.actions.slice(0, 6).map((action) => {
                    const typeIcon: Record<string, string> = {
                      write_post: "✍️",
                      run_audit: "🔧",
                      research_keywords: "🔍",
                      check_rankings: "🏆",
                      fix_issue: "⚠️",
                    };
                    const effortColor: Record<string, string> = {
                      low: "text-emerald-700 bg-emerald-50 border-emerald-200",
                      medium: "text-yellow-700 bg-yellow-50 border-yellow-200",
                      high: "text-red-700 bg-red-50 border-red-200",
                    };
                    const isExecuting = briefExecuting === action.id;
                    return (
                      <div key={action.id} className="flex flex-col gap-2 border border-slate-200 rounded-xl p-3.5 bg-slate-50/60 hover:border-indigo-200 hover:bg-indigo-50/30 transition-colors">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-lg shrink-0">{typeIcon[action.type] ?? "⚙️"}</span>
                            <span className="text-xs font-bold text-slate-800 leading-tight">{action.title}</span>
                          </div>
                          <span className="text-[10px] font-bold text-slate-400 shrink-0">#{action.priority}</span>
                        </div>
                        <p className="text-[11px] text-slate-500 leading-relaxed">{action.reason}</p>
                        <div className="flex items-center justify-between gap-2 mt-auto pt-1">
                          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border capitalize ${effortColor[action.effort?.toLowerCase()] ?? "text-slate-600 bg-slate-100 border-slate-200"}`}>
                            {action.effort} effort
                          </span>
                          <button
                            onClick={() => executeAction(action)}
                            disabled={!!briefExecuting || chatLoading}
                            className="flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
                          >
                            {isExecuting ? (
                              <><span className="animate-spin inline-block">⚙</span> Running…</>
                            ) : (
                              <><Zap className="w-3 h-3" /> Execute</>
                            )}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>

  );
}

export default React.memo(SeoHubWorkspace);
