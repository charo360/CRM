import React, { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";

interface AnalyticsEvent {
  id: string;
  type: string;
  created_at: string;
  payload?: Record<string, unknown>;
}

const PLATFORMS = [
  {
    id: "google-analytics",
    name: "Google Analytics 4",
    icon: "📊",
    description: "Visitor counts, session data, top pages and conversion events.",
    setupUrl: "https://analytics.google.com",
    comingSoon: true,
  },
  {
    id: "search-console",
    name: "Google Search Console",
    icon: "🔍",
    description: "Keyword impressions, click-through rates and real ranking positions.",
    setupUrl: "https://search.google.com/search-console",
    comingSoon: true,
  },
  {
    id: "google-ads",
    name: "Google Ads",
    icon: "💰",
    description: "Paid campaign spend, clicks, impressions and ROI.",
    setupUrl: "https://ads.google.com",
    comingSoon: true,
  },
];

export default function AnalyticsIntegration() {
  const [events, setEvents] = useState<AnalyticsEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await seoApi.analyticsEvents(50);
        setEvents(data as AnalyticsEvent[]);
      } catch {
        setEvents([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-6 animate-pulse">
        <div className="h-6 bg-slate-200 rounded w-1/4 mb-4"></div>
        {[1, 2, 3].map(i => <div key={i} className="h-16 bg-slate-100 rounded mb-3"></div>)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-800">Analytics Integration</h2>
        <p className="text-sm text-slate-500 mt-1">
          Connect your analytics platforms to pull real traffic, ranking and ROI data.
        </p>
      </div>

      {/* Platform cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PLATFORMS.map(p => (
          <div key={p.id} className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{p.icon}</span>
                <span className="font-semibold text-slate-800 text-sm">{p.name}</span>
              </div>
              <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
                Coming soon
              </span>
            </div>
            <p className="text-xs text-slate-500 flex-1">{p.description}</p>
            <a
              href={p.setupUrl}
              target="_blank"
              rel="noreferrer"
              className="w-full text-center px-3 py-2 bg-slate-100 text-slate-600 text-xs rounded-lg hover:bg-slate-200 font-medium transition-colors"
            >
              Open {p.name} ↗
            </a>
          </div>
        ))}
      </div>

      {/* Zilo internal events */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-1">Zilo Activity Log</h3>
        <p className="text-xs text-slate-500 mb-4">Actions tracked inside your Zilo workspace (audits run, posts created, keywords saved, etc.)</p>

        {events.length === 0 ? (
          <div className="text-center py-10 text-slate-400">
            <p className="text-3xl mb-2">📋</p>
            <p className="text-sm">No activity recorded yet.</p>
            <p className="text-xs mt-1">Run an audit, generate a keyword list or publish a post to start tracking.</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {events.map(ev => (
              <div key={ev.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg text-sm">
                <div className="flex items-center gap-3">
                  <span className="text-base">
                    {ev.type === "post_created" ? "📝"
                      : ev.type === "post_published" ? "🚀"
                      : ev.type === "audit_run" ? "🔍"
                      : ev.type === "keywords_saved" ? "🎯"
                      : "📌"}
                  </span>
                  <span className="text-slate-700 capitalize">{ev.type.replace(/_/g, " ")}</span>
                </div>
                <span className="text-xs text-slate-400">
                  {new Date(ev.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info banner */}
      <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-sm text-amber-800">
        <strong>Note:</strong> Google Analytics and Search Console integrations require OAuth setup.
        This is on the Zilo roadmap — vote for it or check back soon.
      </div>
    </div>
  );
}
