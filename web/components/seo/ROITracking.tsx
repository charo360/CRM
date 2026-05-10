import React, { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";

interface ROIMetric {
  title: string;
  value: string | number;
  change: string;
  trend: "up" | "down" | "neutral";
  icon: string;
}

interface ContentPerformance {
  id: string;
  title: string;
  published_at: string;
  views: number;
  traffic_source: string;
  keywords_ranked: number;
  conversion_rate?: number;
}

interface CompetitorInsight {
  competitor: string;
  their_posts: number;
  your_posts: number;
  content_gap: string[];
}

export default function ROITracking() {
  const [metrics, setMetrics] = useState<ROIMetric[]>([]);
  const [topContent, setTopContent] = useState<ContentPerformance[]>([]);
  const [competitors, setCompetitors] = useState<CompetitorInsight[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<"30d" | "90d" | "all">("30d");

  useEffect(() => {
    const loadROIData = async () => {
      try {
        // Simulate ROI data - in production, this would come from analytics APIs
        const mockMetrics: ROIMetric[] = [
          {
            title: "Organic Traffic",
            value: "+142%",
            change: "+89 visitors",
            trend: "up",
            icon: "📈"
          },
          {
            title: "Keyword Rankings",
            value: "23",
            change: "+15 this month",
            trend: "up",
            icon: "🎯"
          },
          {
            title: "Content ROI",
            value: "$3,420",
            change: "+$1,240",
            trend: "up",
            icon: "💰"
          },
          {
            title: "Lead Generation",
            value: "47",
            change: "+32%",
            trend: "up",
            icon: "🔥"
          }
        ];

        const mockContent: ContentPerformance[] = [
          {
            id: "1",
            title: "5 Signs You Need Emergency Plumbing Services",
            published_at: "2024-01-15",
            views: 1247,
            traffic_source: "Google Organic",
            keywords_ranked: 8,
            conversion_rate: 3.2
          },
          {
            id: "2",
            title: "Complete Guide to Dental Cleaning: What to Expect",
            published_at: "2024-01-08",
            views: 892,
            traffic_source: "Google Organic",
            keywords_ranked: 5,
            conversion_rate: 2.8
          },
          {
            id: "3",
            title: "Water Heater Maintenance Guide: Extend Your Unit's Life",
            published_at: "2024-01-22",
            views: 756,
            traffic_source: "Direct",
            keywords_ranked: 4,
            conversion_rate: 4.1
          }
        ];

        const mockCompetitors: CompetitorInsight[] = [
          {
            competitor: "Competitor A",
            their_posts: 12,
            your_posts: 18,
            content_gap: ["Local SEO guides", "Video tutorials", "Case studies"]
          },
          {
            competitor: "Competitor B", 
            their_posts: 8,
            your_posts: 18,
            content_gap: ["Industry trends", "Price comparisons", "DIY vs Pro"]
          }
        ];

        setMetrics(mockMetrics);
        setTopContent(mockContent);
        setCompetitors(mockCompetitors);
      } catch (error) {
        console.error("Failed to load ROI data:", error);
      } finally {
        setLoading(false);
      }
    };

    loadROIData();
  }, [timeframe]);

  const getTrendColor = (trend: "up" | "down" | "neutral") => {
    switch (trend) {
      case "up": return "text-green-500";
      case "down": return "text-red-500";
      default: return "text-slate-400";
    }
  };

  const getTrendIcon = (trend: "up" | "down" | "neutral") => {
    switch (trend) {
      case "up": return "↑";
      case "down": return "↓";
      default: return "→";
    }
  };

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

  return (
    <div className="space-y-6">
      {/* Header with timeframe selector */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">ROI Tracking</h2>
          <p className="text-sm text-slate-500 mt-1">Measure your SEO content performance and business impact</p>
        </div>
        <div className="flex gap-2">
          {(["30d", "90d", "all"] as const).map(period => (
            <button
              key={period}
              onClick={() => setTimeframe(period)}
              className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                timeframe === period
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {period === "30d" ? "30 days" : period === "90d" ? "90 days" : "All time"}
            </button>
          ))}
        </div>
      </div>

      {/* ROI Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((metric, index) => (
          <div key={index} className="bg-white rounded-xl border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-2xl">{metric.icon}</span>
              <div className={`flex items-center gap-1 text-sm font-medium ${getTrendColor(metric.trend)}`}>
                <span>{getTrendIcon(metric.trend)}</span>
                <span>{metric.change}</span>
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-800">{metric.value}</div>
            <div className="text-sm text-slate-600 mt-1">{metric.title}</div>
          </div>
        ))}
      </div>

      {/* Before/After Comparison */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Before/After SEO Performance</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Before */}
          <div className="bg-slate-50 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-slate-700 mb-3">Before Implementation</h4>
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-600">Monthly organic traffic</span>
                <span className="text-sm font-medium text-slate-800">342</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-600">Keyword rankings</span>
                <span className="text-sm font-medium text-slate-800">8</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-600">Blog posts</span>
                <span className="text-sm font-medium text-slate-800">3</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-600">Leads from content</span>
                <span className="text-sm font-medium text-slate-800">12</span>
              </div>
            </div>
          </div>

          {/* After */}
          <div className="bg-emerald-50 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-emerald-700 mb-3">After Implementation</h4>
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-emerald-600">Monthly organic traffic</span>
                <span className="text-sm font-medium text-emerald-800">828 (+142%)</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-emerald-600">Keyword rankings</span>
                <span className="text-sm font-medium text-emerald-800">23 (+187%)</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-emerald-600">Blog posts</span>
                <span className="text-sm font-medium text-emerald-800">18 (+500%)</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-emerald-600">Leads from content</span>
                <span className="text-sm font-medium text-emerald-800">47 (+292%)</span>
              </div>
            </div>
          </div>
        </div>

        {/* ROI Calculation */}
        <div className="mt-6 p-4 bg-blue-50 border border-blue-100 rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-semibold text-blue-800">Estimated Monthly ROI</h4>
              <p className="text-xs text-blue-600 mt-0.5">Based on industry average $150/lead value</p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-blue-800">$5,250</div>
              <div className="text-xs text-blue-600">+292% vs baseline</div>
            </div>
          </div>
        </div>
      </div>

      {/* Top Performing Content */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Top Performing Content</h3>
        
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="text-left py-3 px-2 font-medium text-slate-700">Content</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Views</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Traffic Source</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Keywords Ranked</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Conversion Rate</th>
              </tr>
            </thead>
            <tbody>
              {topContent.map((content) => (
                <tr key={content.id} className="border-b border-slate-50 hover:bg-slate-50">
                  <td className="py-3 px-2">
                    <div>
                      <p className="font-medium text-slate-800 text-sm">{content.title}</p>
                      <p className="text-xs text-slate-500">{new Date(content.published_at).toLocaleDateString()}</p>
                    </div>
                  </td>
                  <td className="text-center py-3 px-2">
                    <span className="font-medium text-slate-800">{content.views.toLocaleString()}</span>
                  </td>
                  <td className="text-center py-3 px-2">
                    <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">
                      {content.traffic_source}
                    </span>
                  </td>
                  <td className="text-center py-3 px-2">
                    <span className="font-medium text-slate-800">{content.keywords_ranked}</span>
                  </td>
                  <td className="text-center py-3 px-2">
                    <span className="font-medium text-emerald-600">
                      {content.conversion_rate ? `${content.conversion_rate}%` : "N/A"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Competitive Analysis */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Competitive Advantage</h3>
        
        <div className="space-y-4">
          {competitors.map((competitor, index) => (
            <div key={index} className="border border-slate-100 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-medium text-slate-800">{competitor.competitor}</h4>
                <div className="flex gap-4 text-sm">
                  <div className="text-center">
                    <div className="font-medium text-slate-800">{competitor.their_posts}</div>
                    <div className="text-xs text-slate-500">Their posts</div>
                  </div>
                  <div className="text-center">
                    <div className="font-medium text-emerald-600">{competitor.your_posts}</div>
                    <div className="text-xs text-slate-500">Your posts</div>
                  </div>
                </div>
              </div>
              
              <div>
                <p className="text-xs font-medium text-slate-600 mb-2">Content opportunities they're missing:</p>
                <div className="flex flex-wrap gap-1">
                  {competitor.content_gap.map((gap, i) => (
                    <span key={i} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded">
                      {gap}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
