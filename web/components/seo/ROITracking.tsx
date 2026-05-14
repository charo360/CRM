import React, { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";

interface SummaryData {
  total_posts: number;
  published_posts: number;
  draft_posts: number;
  total_audits: number;
  avg_seo_score: number | null;
  last_audit: { score: number; grade: string; url: string; created_at: string } | null;
  audit_trend: { date: string; score: number; url: string }[];
}

interface PostData {
  id: string;
  title: string;
  status: string;
  created_at?: string;
  published_at?: string;
  keywords?: string[];
  platform?: string;
}

export default function ROITracking() {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [posts, setPosts] = useState<PostData[]>([]);
  const [keywordMonths, setKeywordMonths] = useState<number>(0);
  const [totalKeywords, setTotalKeywords] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<"30d" | "90d" | "all">("30d");

  useEffect(() => {
    const loadROIData = async () => {
      setLoading(true);
      try {
        const [summaryData, postsData, savedKw] = await Promise.all([
          seoApi.summary(),
          seoApi.listPosts(),
          seoApi.listSavedKeywords(),
        ]);
        setSummary(summaryData as SummaryData);
        setPosts(postsData as PostData[]);
        setKeywordMonths(savedKw.length);
        setTotalKeywords(savedKw.reduce((acc, m) => acc + (m.count || 0), 0));
      } catch (error) {
        console.error("Failed to load ROI data:", error);
      } finally {
        setLoading(false);
      }
    };
    loadROIData();
  }, [timeframe]);

  const filteredPosts = posts.filter(p => {
    if (timeframe === "all") return true;
    const date = new Date(p.created_at || p.published_at || "");
    if (isNaN(date.getTime())) return true;
    const days = timeframe === "30d" ? 30 : 90;
    return (Date.now() - date.getTime()) / 86400000 <= days;
  });

  const publishedPosts = filteredPosts.filter(p => p.status === "published");
  const auditScore = summary?.avg_seo_score ?? summary?.last_audit?.score ?? null;

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse">
              <div className="h-16 bg-slate-100 rounded mb-3"></div>
              <div className="h-4 bg-slate-200 rounded w-3/4"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const statCards = [
    { icon: "📝", label: "Total Posts", value: summary?.total_posts ?? 0, sub: `${summary?.published_posts ?? 0} published` },
    { icon: "🎯", label: "Keyword Batches", value: keywordMonths, sub: `${totalKeywords} keywords saved` },
    { icon: "🔍", label: "SEO Score", value: auditScore !== null ? `${auditScore}/100` : "—", sub: summary?.last_audit ? `Last audit: ${new Date(summary.last_audit.created_at).toLocaleDateString()}` : "No audit yet" },
    { icon: "📊", label: "Site Audits", value: summary?.total_audits ?? 0, sub: summary?.last_audit?.grade ? `Latest grade: ${summary.last_audit.grade}` : "Run an audit to start" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">ROI Tracking</h2>
          <p className="text-sm text-slate-500 mt-1">Your real SEO content performance — no estimates</p>
        </div>
        <div className="flex gap-2">
          {(["30d", "90d", "all"] as const).map(period => (
            <button
              key={period}
              onClick={() => setTimeframe(period)}
              className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                timeframe === period ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {period === "30d" ? "30 days" : period === "90d" ? "90 days" : "All time"}
            </button>
          ))}
        </div>
      </div>

      {/* Real stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((card, i) => (
          <div key={i} className="bg-white rounded-xl border border-slate-200 p-5">
            <span className="text-2xl">{card.icon}</span>
            <div className="text-2xl font-bold text-slate-800 mt-2">{card.value}</div>
            <div className="text-sm font-medium text-slate-700 mt-1">{card.label}</div>
            <div className="text-xs text-slate-500 mt-0.5">{card.sub}</div>
          </div>
        ))}
      </div>

      {/* Audit score trend */}
      {summary && summary.audit_trend.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-800 mb-4">SEO Score History</h3>
          <div className="flex items-end gap-3 h-24">
            {summary.audit_trend.map((t, i) => (
              <div key={i} className="flex flex-col items-center flex-1 gap-1">
                <span className="text-xs font-medium text-slate-600">{t.score}</span>
                <div
                  className="w-full rounded-t bg-emerald-500"
                  style={{ height: `${Math.max(8, (t.score / 100) * 80)}px` }}
                />
                <span className="text-xs text-slate-400">{new Date(t.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Published posts */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">
          Published Content
          <span className="ml-2 text-sm font-normal text-slate-500">({publishedPosts.length} posts)</span>
        </h3>
        {publishedPosts.length === 0 ? (
          <div className="text-center py-10 text-slate-400">
            <p className="text-3xl mb-2">📝</p>
            <p className="text-sm">No published posts yet in this period.</p>
            <p className="text-xs mt-1">Head to the Blog tab to generate and publish your first post.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="text-left py-3 px-2 font-medium text-slate-700">Title</th>
                  <th className="text-center py-3 px-2 font-medium text-slate-700">Published</th>
                  <th className="text-center py-3 px-2 font-medium text-slate-700">Platform</th>
                  <th className="text-center py-3 px-2 font-medium text-slate-700">Keywords</th>
                </tr>
              </thead>
              <tbody>
                {publishedPosts.slice(0, 10).map(post => (
                  <tr key={post.id} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-3 px-2 font-medium text-slate-800 max-w-xs truncate">{post.title}</td>
                    <td className="text-center py-3 px-2 text-slate-500 text-xs">
                      {post.published_at || post.created_at
                        ? new Date(post.published_at || post.created_at!).toLocaleDateString()
                        : "—"}
                    </td>
                    <td className="text-center py-3 px-2">
                      <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full capitalize">
                        {post.platform || "internal"}
                      </span>
                    </td>
                    <td className="text-center py-3 px-2 text-slate-600">
                      {post.keywords?.length ? post.keywords.slice(0, 2).join(", ") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Connect Google Analytics CTA */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-6 flex items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-blue-800">Connect Google Analytics for Traffic Data</h3>
          <p className="text-xs text-blue-600 mt-1">
            Real visitor counts, keyword rankings and conversion data require a Google Analytics / Search Console connection.
            Go to the <span className="font-medium">Analytics</span> tab to connect.
          </p>
        </div>
        <span className="text-3xl flex-shrink-0">📈</span>
      </div>
    </div>
  );
}
