"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  seoApi,
  seoAgentApi,
  type SeoAudit,
  type SeoAuditIssue,
  type SeoKeyword,
  type BlogPost,
  type BlogGenerateResult,
  type ContentCalendarItem,
  type SeoSummary,
  type SeoAgentToolStep,
} from "@/lib/api";

// ── Tabs ─────────────────────────────────────────────────────────────────────

type Tab = "overview" | "audit" | "keywords" | "blog" | "calendar" | "agent";

// ── Helpers ───────────────────────────────────────────────────────────────────

function ScoreBadge({ score, grade }: { score: number; grade: string }) {
  const color =
    score >= 90 ? "bg-green-100 text-green-700 border-green-200"
    : score >= 75 ? "bg-blue-100 text-blue-700 border-blue-200"
    : score >= 60 ? "bg-yellow-100 text-yellow-700 border-yellow-200"
    : score >= 40 ? "bg-orange-100 text-orange-700 border-orange-200"
    : "bg-red-100 text-red-700 border-red-200";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${color}`}>
      {grade} · {score}/100
    </span>
  );
}

function IssuePill({ type }: { type: SeoAuditIssue["type"] }) {
  const styles = {
    critical: "bg-red-100 text-red-700",
    warning: "bg-yellow-100 text-yellow-700",
    info: "bg-blue-100 text-blue-700",
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase ${styles[type]}`}>
      {type}
    </span>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <p className="text-xs text-slate-500 font-medium">{label}</p>
      <p className="text-2xl font-bold text-slate-800 mt-1">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab({ summary }: { summary: SeoSummary | null }) {
  if (!summary) return <p className="text-slate-400 text-sm">Loading summary…</p>;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Total Blog Posts" value={summary.total_posts} />
        <StatCard label="Published" value={summary.published_posts} />
        <StatCard label="Drafts" value={summary.draft_posts} />
        <StatCard label="Site Audits Run" value={summary.total_audits} />
      </div>
      {summary.avg_seo_score !== null && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-2">Average SEO Score (last 5 audits)</p>
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-slate-100 rounded-full h-3">
              <div
                className="h-3 rounded-full bg-green-500 transition-all"
                style={{ width: `${summary.avg_seo_score}%` }}
              />
            </div>
            <span className="text-lg font-bold text-slate-800">{summary.avg_seo_score}/100</span>
          </div>
        </div>
      )}
      {summary.last_audit && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-3">Last Audit</p>
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-medium text-slate-800 break-all">{summary.last_audit.url}</p>
              <p className="text-xs text-slate-400 mt-0.5">{new Date(summary.last_audit.created_at).toLocaleString()}</p>
            </div>
            <ScoreBadge score={summary.last_audit.score} grade={summary.last_audit.grade} />
          </div>
          <div className="mt-3 flex gap-4 text-xs text-slate-500">
            <span>{summary.last_audit.issues.filter(i => i.type === "critical").length} critical</span>
            <span>{summary.last_audit.issues.filter(i => i.type === "warning").length} warnings</span>
            <span>{summary.last_audit.issues.filter(i => i.type === "info").length} info</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Audit Tab ─────────────────────────────────────────────────────────────────

function AuditTab() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [audit, setAudit] = useState<SeoAudit | null>(null);
  const [fixes, setFixes] = useState<{ field: string; issue: string; fix: string; example: string }[] | null>(null);
  const [fixLoading, setFixLoading] = useState(false);
  const [history, setHistory] = useState<SeoAudit[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    seoApi.listAudits().then(setHistory).catch(() => {});
  }, []);

  async function runAudit() {
    if (!url.trim()) return;
    setLoading(true); setErr(""); setAudit(null); setFixes(null);
    try {
      const result = await seoApi.audit(url.trim());
      setAudit(result);
      setHistory(h => [result, ...h.slice(0, 49)]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Audit failed");
    } finally {
      setLoading(false);
    }
  }

  async function getAiFixes() {
    if (!audit) return;
    setFixLoading(true);
    try {
      const res = await seoApi.aiFixSuggestions(audit.url);
      setFixes(res.suggestions);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "AI fix failed");
    } finally {
      setFixLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <p className="text-sm font-semibold text-slate-700 mb-3">Run Site Audit</p>
        <div className="flex gap-2">
          <input
            className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder="https://yourclientsite.com"
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runAudit()}
          />
          <button
            onClick={runAudit}
            disabled={loading || !url.trim()}
            className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg font-medium hover:bg-green-700 disabled:opacity-50"
          >
            {loading ? "Auditing…" : "Audit"}
          </button>
        </div>
        {err && <p className="text-red-500 text-xs mt-2">{err}</p>}
      </div>

      {audit && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-semibold text-slate-800 break-all">{audit.url}</p>
              <p className="text-xs text-slate-400 mt-0.5">{audit.word_count} words · {audit.total_images} images · {audit.images_missing_alt} missing alt</p>
            </div>
            <ScoreBadge score={audit.score} grade={audit.grade} />
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">H1 tags</p>
              <p className={`text-xl font-bold ${audit.h1_count === 1 ? "text-green-600" : "text-red-500"}`}>{audit.h1_count}</p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">H2 tags</p>
              <p className="text-xl font-bold text-slate-700">{audit.h2_count}</p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">Issues</p>
              <p className={`text-xl font-bold ${audit.issues.length === 0 ? "text-green-600" : "text-orange-500"}`}>{audit.issues.length}</p>
            </div>
          </div>

          {audit.issues.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Issues Found</p>
              {audit.issues.map((issue, i) => (
                <div key={i} className="flex gap-3 items-start border border-slate-100 rounded-lg p-3">
                  <IssuePill type={issue.type} />
                  <div>
                    <p className="text-xs font-medium text-slate-700">{issue.field}</p>
                    <p className="text-xs text-slate-500">{issue.message}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={getAiFixes}
            disabled={fixLoading}
            className="w-full py-2 bg-slate-800 text-white text-sm rounded-lg font-medium hover:bg-slate-900 disabled:opacity-50"
          >
            {fixLoading ? "Getting AI fixes…" : "Get AI Fix Suggestions"}
          </button>

          {fixes && fixes.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">AI Recommendations</p>
              {fixes.map((f, i) => (
                <div key={i} className="bg-green-50 border border-green-100 rounded-lg p-3 space-y-1">
                  <p className="text-xs font-bold text-green-800 uppercase">{f.field}</p>
                  <p className="text-xs text-slate-600"><span className="font-medium">Issue:</span> {f.issue}</p>
                  <p className="text-xs text-slate-600"><span className="font-medium">Fix:</span> {f.fix}</p>
                  {f.example && (
                    <p className="text-xs text-slate-500 italic bg-white rounded p-2 border border-green-100">{f.example}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-3">Audit History</p>
          <div className="space-y-2">
            {history.slice(0, 10).map((a) => (
              <div key={a.id} className="flex items-center justify-between gap-3 py-2 border-b border-slate-50 last:border-0">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-slate-700 truncate">{a.url}</p>
                  <p className="text-xs text-slate-400">{new Date(a.created_at).toLocaleDateString()}</p>
                </div>
                <ScoreBadge score={a.score} grade={a.grade} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Keywords Tab ──────────────────────────────────────────────────────────────

function KeywordsTab() {
  const [businessType, setBusinessType] = useState("");
  const [location, setLocation] = useState("");
  const [loading, setLoading] = useState(false);
  const [keywords, setKeywords] = useState<SeoKeyword[]>([]);
  const [err, setErr] = useState("");

  async function generate() {
    if (!businessType.trim()) return;
    setLoading(true); setErr("");
    try {
      const res = await seoApi.generateKeywords(businessType, location);
      setKeywords(res.keywords);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  const difficultyColor = (d: string) =>
    d === "low" ? "text-green-600" : d === "medium" ? "text-yellow-600" : "text-red-500";

  const intentColor = (i: string) =>
    i === "transactional" ? "bg-green-100 text-green-700"
    : i === "local" ? "bg-blue-100 text-blue-700"
    : i === "informational" ? "bg-purple-100 text-purple-700"
    : "bg-slate-100 text-slate-600";

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <p className="text-sm font-semibold text-slate-700 mb-3">AI Keyword Research</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-xs text-slate-500 font-medium block mb-1">Business Type</label>
            <input
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              placeholder="e.g. hair salon, law firm, restaurant"
              value={businessType}
              onChange={e => setBusinessType(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 font-medium block mb-1">Location (optional)</label>
            <input
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              placeholder="e.g. Nairobi, Lagos, London"
              value={location}
              onChange={e => setLocation(e.target.value)}
            />
          </div>
        </div>
        <button
          onClick={generate}
          disabled={loading || !businessType.trim()}
          className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg font-medium hover:bg-green-700 disabled:opacity-50"
        >
          {loading ? "Generating…" : "Generate Keywords"}
        </button>
        {err && <p className="text-red-500 text-xs mt-2">{err}</p>}
      </div>

      {keywords.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <p className="text-sm font-semibold text-slate-700">{keywords.length} Keywords Found</p>
          </div>
          <div className="divide-y divide-slate-50">
            {keywords.map((kw, i) => (
              <div key={i} className="px-5 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800">{kw.keyword}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{kw.content_idea}</p>
                  </div>
                  <div className="flex gap-2 shrink-0 items-center">
                    <span className={`text-xs font-bold capitalize ${difficultyColor(kw.difficulty)}`}>{kw.difficulty}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${intentColor(kw.intent)}`}>{kw.intent}</span>
                  </div>
                </div>
                <div className="mt-1 flex gap-1">
                  {Array.from({ length: 5 }, (_, p) => (
                    <div key={p} className={`h-1.5 w-4 rounded-full ${p < kw.priority ? "bg-green-500" : "bg-slate-100"}`} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Blog Tab ──────────────────────────────────────────────────────────────────

function BlogTab() {
  const [tab, setTab] = useState<"write" | "posts">("posts");
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [loadingPosts, setLoadingPosts] = useState(true);

  // Generator form
  const [topic, setTopic] = useState("");
  const [keywords, setKeywords] = useState("");
  const [tone, setTone] = useState("professional");
  const [length, setLength] = useState("medium");
  const [businessName, setBusinessName] = useState("");
  const [includeFaq, setIncludeFaq] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<BlogGenerateResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  // Publish modal
  const [publishPost, setPublishPost] = useState<BlogPost | null>(null);
  const [publishPlatform, setPublishPlatform] = useState("wordpress");
  const [wpUrl, setWpUrl] = useState("");
  const [wpUser, setWpUser] = useState("");
  const [wpPass, setWpPass] = useState("");
  const [shopifyDomain, setShopifyDomain] = useState("");
  const [shopifyToken, setShopifyToken] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<string>("");

  const loadPosts = useCallback(async () => {
    setLoadingPosts(true);
    try { setPosts(await seoApi.listPosts()); } catch { /* ignore */ }
    finally { setLoadingPosts(false); }
  }, []);

  useEffect(() => { loadPosts(); }, [loadPosts]);

  async function generate() {
    if (!topic.trim()) return;
    setGenerating(true); setErr(""); setGenerated(null);
    try {
      const res = await seoApi.generateBlog({
        topic: topic.trim(),
        keywords: keywords.split(",").map(k => k.trim()).filter(Boolean),
        tone,
        length,
        business_name: businessName,
        include_faq: includeFaq,
      });
      setGenerated(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function saveAsDraft() {
    if (!generated) return;
    setSaving(true);
    try {
      await seoApi.createPost({
        title: generated.title,
        content: generated.content,
        meta_title: generated.meta_title,
        meta_description: generated.meta_description,
        tags: generated.tags,
        status: "draft",
        platform: "internal",
      });
      await loadPosts();
      setTab("posts");
      setGenerated(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function deletePost(id: string) {
    if (!confirm("Delete this post?")) return;
    try {
      await seoApi.deletePost(id);
      setPosts(p => p.filter(x => x.id !== id));
    } catch { /* ignore */ }
  }

  async function doPublish() {
    if (!publishPost) return;
    setPublishing(true); setPublishResult("");
    try {
      const res = await seoApi.publishPost({
        post_id: publishPost.id,
        platform: publishPlatform,
        wp_url: wpUrl || undefined,
        wp_username: wpUser || undefined,
        wp_password: wpPass || undefined,
        shopify_domain: shopifyDomain || undefined,
        shopify_token: shopifyToken || undefined,
      });
      if (res.ok) {
        setPublishResult(`Published! ${res.post_url || ""}`);
        await loadPosts();
      } else {
        setPublishResult(`Error: ${res.error || "Unknown error"}`);
      }
    } catch (e) {
      setPublishResult(e instanceof Error ? e.message : "Failed");
    } finally {
      setPublishing(false);
    }
  }

  const statusColor = (s: string) =>
    s === "published" ? "bg-green-100 text-green-700"
    : s === "scheduled" ? "bg-blue-100 text-blue-700"
    : "bg-slate-100 text-slate-600";

  return (
    <div className="space-y-5">
      <div className="flex gap-2">
        {(["posts", "write"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${tab === t ? "bg-green-600 text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"}`}
          >
            {t === "posts" ? "My Posts" : "Write New Post"}
          </button>
        ))}
      </div>

      {tab === "write" && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
          <p className="text-sm font-semibold text-slate-700">AI Blog Writer</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <label className="text-xs text-slate-500 font-medium block mb-1">Topic *</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                placeholder="e.g. 5 reasons to choose a professional hair salon in Nairobi"
                value={topic}
                onChange={e => setTopic(e.target.value)}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs text-slate-500 font-medium block mb-1">Target Keywords (comma-separated)</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                placeholder="hair salon Nairobi, best salon, hair treatment"
                value={keywords}
                onChange={e => setKeywords(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-slate-500 font-medium block mb-1">Tone</label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                value={tone}
                onChange={e => setTone(e.target.value)}
              >
                <option value="professional">Professional</option>
                <option value="friendly">Friendly</option>
                <option value="casual">Casual</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 font-medium block mb-1">Length</label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                value={length}
                onChange={e => setLength(e.target.value)}
              >
                <option value="short">Short (~400 words)</option>
                <option value="medium">Medium (~800 words)</option>
                <option value="long">Long (~1500 words)</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 font-medium block mb-1">Business Name (optional)</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                placeholder="Your business name"
                value={businessName}
                onChange={e => setBusinessName(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2 pt-5">
              <input
                type="checkbox"
                id="faq"
                checked={includeFaq}
                onChange={e => setIncludeFaq(e.target.checked)}
                className="rounded"
              />
              <label htmlFor="faq" className="text-sm text-slate-600">Include FAQ section</label>
            </div>
          </div>

          <button
            onClick={generate}
            disabled={generating || !topic.trim()}
            className="px-5 py-2 bg-green-600 text-white text-sm rounded-lg font-medium hover:bg-green-700 disabled:opacity-50"
          >
            {generating ? "Writing post…" : "Generate Blog Post"}
          </button>
          {err && <p className="text-red-500 text-xs">{err}</p>}

          {generated && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-base font-bold text-slate-800">{generated.title}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{generated.word_count} words · {generated.tags.slice(0, 3).join(", ")}</p>
                </div>
                <button
                  onClick={saveAsDraft}
                  disabled={saving}
                  className="px-3 py-1.5 bg-slate-800 text-white text-xs rounded-lg font-medium hover:bg-slate-900 disabled:opacity-50 shrink-0"
                >
                  {saving ? "Saving…" : "Save as Draft"}
                </button>
              </div>

              {generated.meta_title && (
                <div className="bg-slate-50 rounded-lg p-3 space-y-1">
                  <p className="text-xs font-semibold text-slate-600">SEO Meta</p>
                  <p className="text-xs text-slate-700"><span className="font-medium">Title:</span> {generated.meta_title}</p>
                  <p className="text-xs text-slate-500">{generated.meta_description}</p>
                </div>
              )}

              <div className="bg-white border border-slate-200 rounded-lg p-4 max-h-96 overflow-y-auto">
                <pre className="text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">{generated.content}</pre>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "posts" && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          {loadingPosts ? (
            <p className="p-5 text-sm text-slate-400">Loading posts…</p>
          ) : posts.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-slate-400 text-sm">No blog posts yet.</p>
              <button onClick={() => setTab("write")} className="mt-3 px-4 py-2 bg-green-600 text-white text-sm rounded-lg font-medium">
                Write Your First Post
              </button>
            </div>
          ) : (
            <div className="divide-y divide-slate-50">
              {posts.map(post => (
                <div key={post.id} className="px-5 py-4 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{post.title}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{new Date(post.created_at).toLocaleDateString()}</p>
                    {post.tags.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {post.tags.slice(0, 3).map(t => (
                          <span key={t} className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">{t}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${statusColor(post.status)}`}>{post.status}</span>
                    {post.status !== "published" && (
                      <button
                        onClick={() => { setPublishPost(post); setPublishResult(""); }}
                        className="text-xs px-2 py-1 bg-green-600 text-white rounded-lg hover:bg-green-700"
                      >
                        Publish
                      </button>
                    )}
                    <button
                      onClick={() => deletePost(post.id)}
                      className="text-xs px-2 py-1 bg-red-50 text-red-500 rounded-lg hover:bg-red-100"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Publish Modal */}
      {publishPost && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-base font-bold text-slate-800">Publish Post</p>
              <button onClick={() => setPublishPost(null)} className="text-slate-400 hover:text-slate-600 text-xl">×</button>
            </div>
            <p className="text-sm text-slate-600 font-medium truncate">{publishPost.title}</p>

            <div>
              <label className="text-xs text-slate-500 font-medium block mb-1">Platform</label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                value={publishPlatform}
                onChange={e => setPublishPlatform(e.target.value)}
              >
                <option value="wordpress">WordPress</option>
                <option value="shopify">Shopify</option>
              </select>
            </div>

            {publishPlatform === "wordpress" && (
              <div className="space-y-2">
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="WordPress URL (e.g. https://yoursite.com)" value={wpUrl} onChange={e => setWpUrl(e.target.value)} />
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Username" value={wpUser} onChange={e => setWpUser(e.target.value)} />
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Application Password" type="password" value={wpPass} onChange={e => setWpPass(e.target.value)} />
                <p className="text-xs text-slate-400">Use a WordPress Application Password (Users → Profile → Application Passwords)</p>
              </div>
            )}

            {publishPlatform === "shopify" && (
              <div className="space-y-2">
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Shopify domain (e.g. mystore.myshopify.com)" value={shopifyDomain} onChange={e => setShopifyDomain(e.target.value)} />
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Access Token" type="password" value={shopifyToken} onChange={e => setShopifyToken(e.target.value)} />
              </div>
            )}

            {publishResult && (
              <p className={`text-xs rounded-lg p-2 ${publishResult.startsWith("Error") ? "bg-red-50 text-red-600" : "bg-green-50 text-green-700"}`}>
                {publishResult}
              </p>
            )}

            <button
              onClick={doPublish}
              disabled={publishing}
              className="w-full py-2 bg-green-600 text-white text-sm rounded-lg font-medium hover:bg-green-700 disabled:opacity-50"
            >
              {publishing ? "Publishing…" : `Publish to ${publishPlatform === "wordpress" ? "WordPress" : "Shopify"}`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Content Calendar Tab ──────────────────────────────────────────────────────

function CalendarTab() {
  const [businessType, setBusinessType] = useState("");
  const [location, setLocation] = useState("");
  const [postsPerWeek, setPostsPerWeek] = useState(2);
  const [weeks, setWeeks] = useState(4);
  const [loading, setLoading] = useState(false);
  const [calendar, setCalendar] = useState<ContentCalendarItem[]>([]);
  const [err, setErr] = useState("");

  async function generate() {
    if (!businessType.trim()) return;
    setLoading(true); setErr("");
    try {
      const res = await seoApi.contentCalendar(businessType, postsPerWeek, weeks, location);
      setCalendar(res.calendar);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  const trafficColor = (t: string) =>
    t === "high" ? "text-green-600" : t === "medium" ? "text-yellow-600" : "text-slate-400";

  const weeks_grouped = Array.from(new Set(calendar.map(c => c.week))).sort();

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <p className="text-sm font-semibold text-slate-700 mb-3">Generate Content Calendar</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-xs text-slate-500 font-medium block mb-1">Business Type *</label>
            <input
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              placeholder="e.g. law firm, restaurant, e-commerce"
              value={businessType}
              onChange={e => setBusinessType(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 font-medium block mb-1">Location (optional)</label>
            <input
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              placeholder="e.g. Nairobi"
              value={location}
              onChange={e => setLocation(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 font-medium block mb-1">Posts per week</label>
            <select
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              value={postsPerWeek}
              onChange={e => setPostsPerWeek(Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 font-medium block mb-1">Weeks</label>
            <select
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              value={weeks}
              onChange={e => setWeeks(Number(e.target.value))}
            >
              {[2, 4, 6, 8, 12].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </div>
        <button
          onClick={generate}
          disabled={loading || !businessType.trim()}
          className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg font-medium hover:bg-green-700 disabled:opacity-50"
        >
          {loading ? "Generating…" : "Generate Calendar"}
        </button>
        {err && <p className="text-red-500 text-xs mt-2">{err}</p>}
      </div>

      {calendar.length > 0 && (
        <div className="space-y-4">
          {weeks_grouped.map(week => (
            <div key={week} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <div className="px-5 py-3 bg-slate-50 border-b border-slate-100">
                <p className="text-sm font-semibold text-slate-700">Week {week}</p>
              </div>
              <div className="divide-y divide-slate-50">
                {calendar.filter(c => c.week === week).map((item, i) => (
                  <div key={i} className="px-5 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-xs text-slate-400 font-medium">{item.day}</span>
                          <span className={`text-xs font-medium capitalize ${trafficColor(item.estimated_traffic)}`}>
                            {item.estimated_traffic} traffic
                          </span>
                        </div>
                        <p className="text-sm font-semibold text-slate-800">{item.title}</p>
                        <p className="text-xs text-slate-400 mt-0.5">{item.topic}</p>
                        <div className="flex gap-1 mt-1 flex-wrap">
                          {item.keywords.map(kw => (
                            <span key={kw} className="text-[10px] bg-green-50 text-green-700 px-1.5 py-0.5 rounded">{kw}</span>
                          ))}
                        </div>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-50 text-purple-600 font-medium shrink-0">{item.intent}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Agent Chat Tab ────────────────────────────────────────────────────────────

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  tool_steps?: SeoAgentToolStep[];
}

const QUICK_PROMPTS = [
  "I want to do SEO — where do I start?",
  "Check my website and tell me what's wrong",
  "What keywords should my business rank for?",
  "Write a blog post for me",
  "Make a content plan for the next month",
];

function AgentChatTab() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [convId, setConvId] = useState<string | undefined>();
  const [conversations, setConversations] = useState<{ id: string; title: string }[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    seoAgentApi.listConversations().then(setConversations).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput("");
    const userMsg: ChatMsg = { role: "user", content: msg };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      const res = await seoAgentApi.chat(msg, convId, history);
      setConvId(res.conversation_id);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: res.reply,
        tool_steps: res.tool_steps,
      }]);
      // Refresh conversation list
      seoAgentApi.listConversations().then(setConversations).catch(() => {});
    } catch (e) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `Error: ${e instanceof Error ? e.message : "Something went wrong. Please try again."}`,
      }]);
    } finally {
      setLoading(false);
    }
  }

  async function loadConversation(id: string) {
    try {
      const data = await seoAgentApi.getConversation(id);
      setConvId(id);
      setMessages(
        data.messages.map(m => ({
          role: m.role as "user" | "assistant",
          content: m.content,
          tool_steps: m.tool_steps,
        }))
      );
      setShowHistory(false);
    } catch { /* ignore */ }
  }

  async function deleteConversation(id: string) {
    await seoAgentApi.deleteConversation(id).catch(() => {});
    setConversations(c => c.filter(x => x.id !== id));
    if (convId === id) { setConvId(undefined); setMessages([]); }
  }

  function newChat() {
    setConvId(undefined);
    setMessages([]);
    setShowHistory(false);
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-[calc(100vh-200px)] min-h-[500px] bg-white rounded-2xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100 bg-slate-50">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-sm font-semibold text-slate-700">SEO Coach</span>
          <span className="text-xs text-slate-400">knows your business · guides you step by step</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowHistory(h => !h)}
            className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100"
          >
            History
          </button>
          <button
            onClick={newChat}
            className="text-xs px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700"
          >
            New Chat
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Sidebar — conversation history */}
        {showHistory && (
          <div className="w-56 border-r border-slate-100 bg-slate-50 flex flex-col overflow-hidden shrink-0">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide px-4 py-3 border-b border-slate-100">
              Past chats
            </p>
            <div className="flex-1 overflow-y-auto">
              {conversations.length === 0 && (
                <p className="text-xs text-slate-400 px-4 py-3">No conversations yet</p>
              )}
              {conversations.map(c => (
                <div
                  key={c.id}
                  className={`flex items-start gap-2 px-4 py-2.5 cursor-pointer hover:bg-white border-b border-slate-50 ${convId === c.id ? "bg-white" : ""}`}
                  onClick={() => loadConversation(c.id)}
                >
                  <p className="text-xs text-slate-600 flex-1 leading-tight line-clamp-2">{c.title}</p>
                  <button
                    onClick={e => { e.stopPropagation(); deleteConversation(c.id); }}
                    className="text-slate-300 hover:text-red-400 text-xs shrink-0"
                  >×</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chat area */}
        <div className="flex flex-col flex-1 min-h-0">
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {isEmpty && (
              <div className="flex flex-col items-center justify-center h-full gap-5 text-center pb-10">
                <div className="space-y-1">
                  <p className="text-slate-700 font-semibold text-base">Hi! I'm your SEO Coach.</p>
                  <p className="text-slate-400 text-sm max-w-xs">I'll help your business show up on Google — step by step, in plain English. No SEO knowledge needed.</p>
                </div>
                <div className="flex flex-col gap-2 w-full max-w-sm">
                  {QUICK_PROMPTS.map(p => (
                    <button
                      key={p}
                      onClick={() => send(p)}
                      className="text-sm text-left px-4 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-green-50 hover:border-green-200 hover:text-green-700 transition-colors"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] space-y-2 ${m.role === "user" ? "items-end" : "items-start"} flex flex-col`}>
                  {/* Tool steps badge */}
                  {m.tool_steps && m.tool_steps.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {Array.from(new Set(m.tool_steps.map(s => s.tool))).map(tool => (
                        <span key={tool} className="text-[10px] bg-green-50 border border-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                          ⚙ {tool.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                  {/* Bubble */}
                  <div
                    className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                      m.role === "user"
                        ? "bg-green-600 text-white rounded-tr-sm"
                        : "bg-slate-100 text-slate-800 rounded-tl-sm"
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 flex gap-1.5 items-center">
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="px-4 py-3 border-t border-slate-100">
            <div className="flex gap-2 items-end">
              <textarea
                rows={1}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                }}
                placeholder="Ask the SEO agent anything… e.g. 'Audit mysite.com and write a blog post about our top service'"
                className="flex-1 resize-none border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 max-h-28"
                style={{ minHeight: "42px" }}
              />
              <button
                onClick={() => send()}
                disabled={loading || !input.trim()}
                className="px-4 py-2.5 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 disabled:opacity-40 shrink-0"
              >
                Send
              </button>
            </div>
            <p className="text-[10px] text-slate-300 mt-1.5 px-1">Enter to send · Shift+Enter for new line</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SeoPage() {
  const [tab, setTab] = useState<Tab>("agent");
  const [summary, setSummary] = useState<SeoSummary | null>(null);

  useEffect(() => {
    seoApi.summary().then(setSummary).catch(() => {});
  }, [tab]);

  const tabs: { id: Tab; label: string }[] = [
    { id: "agent", label: "✦ AI Agent" },
    { id: "overview", label: "Overview" },
    { id: "audit", label: "Site Audit" },
    { id: "keywords", label: "Keywords" },
    { id: "blog", label: "Blog" },
    { id: "calendar", label: "Content Calendar" },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">SEO & Blog</h1>
          <p className="text-sm text-slate-500 mt-0.5">Audit sites, research keywords, write and publish AI blog posts</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              tab === t.id ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "agent" && <AgentChatTab />}
      {tab === "overview" && <OverviewTab summary={summary} />}
      {tab === "audit" && <AuditTab />}
      {tab === "keywords" && <KeywordsTab />}
      {tab === "blog" && <BlogTab />}
      {tab === "calendar" && <CalendarTab />}
    </div>
  );
}
