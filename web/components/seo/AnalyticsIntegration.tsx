import React, { useState, useEffect } from "react";

interface AnalyticsData {
  totalVisitors: number;
  organicTraffic: number;
  topPages: Array<{
    url: string;
    pageviews: number;
    visitors: number;
    avgTime: string;
  }>;
  keywordRankings: Array<{
    keyword: string;
    position: number;
    url: string;
    traffic: number;
  }>;
  trafficSources: Array<{
    source: string;
    visitors: number;
    percentage: number;
  }>;
}

interface ConnectedAccount {
  platform: "google-analytics" | "search-console" | "google-ads";
  connected: boolean;
  lastSync?: string;
  accountId?: string;
}

export default function AnalyticsIntegration() {
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData | null>(null);
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccount[]>([
    { platform: "google-analytics", connected: false },
    { platform: "search-console", connected: false },
    { platform: "google-ads", connected: false }
  ]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [showConnectModal, setShowConnectModal] = useState<string | null>(null);

  useEffect(() => {
    // Simulate loading analytics data
    const mockData: AnalyticsData = {
      totalVisitors: 2847,
      organicTraffic: 1823,
      topPages: [
        {
          url: "/blog/5-signs-emergency-plumbing",
          pageviews: 1247,
          visitors: 892,
          avgTime: "4:32"
        },
        {
          url: "/blog/water-heater-maintenance",
          pageviews: 756,
          visitors: 543,
          avgTime: "3:18"
        },
        {
          url: "/blog/dental-cleaning-guide",
          pageviews: 623,
          visitors: 412,
          avgTime: "5:21"
        }
      ],
      keywordRankings: [
        {
          keyword: "emergency plumber near me",
          position: 3,
          url: "/blog/5-signs-emergency-plumbing",
          traffic: 342
        },
        {
          keyword: "water heater repair cost",
          position: 7,
          url: "/blog/water-heater-maintenance",
          traffic: 189
        },
        {
          keyword: "teeth cleaning price",
          position: 5,
          url: "/blog/dental-cleaning-guide",
          traffic: 156
        }
      ],
      trafficSources: [
        { source: "Google Organic", visitors: 1823, percentage: 64 },
        { source: "Direct", visitors: 567, percentage: 20 },
        { source: "Referral", visitors: 284, percentage: 10 },
        { source: "Social", visitors: 173, percentage: 6 }
      ]
    };

    setTimeout(() => {
      setAnalyticsData(mockData);
      setLoading(false);
    }, 1000);
  }, []);

  const handleConnect = async (platform: string) => {
    // Simulate OAuth flow
    setSyncing(platform);
    setTimeout(() => {
      setConnectedAccounts(prev => 
        prev.map(acc => 
          acc.platform === platform 
            ? { ...acc, connected: true, lastSync: new Date().toISOString(), accountId: "123456" }
            : acc
        )
      );
      setSyncing(null);
      setShowConnectModal(null);
    }, 2000);
  };

  const handleSync = async (platform: string) => {
    setSyncing(platform);
    setTimeout(() => {
      setConnectedAccounts(prev => 
        prev.map(acc => 
          acc.platform === platform 
            ? { ...acc, lastSync: new Date().toISOString() }
            : acc
        )
      );
      setSyncing(null);
    }, 1500);
  };

  const getPlatformIcon = (platform: string) => {
    switch (platform) {
      case "google-analytics": return "📊";
      case "search-console": return "🔍";
      case "google-ads": return "💰";
      default: return "🌐";
    }
  };

  const getPlatformName = (platform: string) => {
    switch (platform) {
      case "google-analytics": return "Google Analytics";
      case "search-console": return "Google Search Console";
      case "google-ads": return "Google Ads";
      default: return platform;
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-200 rounded w-1/4"></div>
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 bg-slate-100 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Analytics Integration</h2>
          <p className="text-sm text-slate-500 mt-1">Connect your analytics platforms to track real SEO performance</p>
        </div>
        <button
          onClick={() => setShowConnectModal("google-analytics")}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-medium"
        >
          Connect Analytics
        </button>
      </div>

      {/* Connected Accounts */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Connected Accounts</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {connectedAccounts.map((account) => (
            <div
              key={account.platform}
              className={`border rounded-lg p-4 ${
                account.connected 
                  ? "border-green-200 bg-green-50" 
                  : "border-slate-200 bg-slate-50"
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{getPlatformIcon(account.platform)}</span>
                  <span className={`font-medium ${
                    account.connected ? "text-green-800" : "text-slate-600"
                  }`}>
                    {getPlatformName(account.platform)}
                  </span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  account.connected 
                    ? "bg-green-200 text-green-800" 
                    : "bg-slate-200 text-slate-600"
                }`}>
                  {account.connected ? "Connected" : "Not connected"}
                </span>
              </div>

              {account.connected ? (
                <div className="space-y-2">
                  <p className="text-xs text-green-700">
                    Account ID: {account.accountId}
                  </p>
                  <p className="text-xs text-green-600">
                    Last sync: {account.lastSync ? new Date(account.lastSync).toLocaleString() : "Never"}
                  </p>
                  <button
                    onClick={() => handleSync(account.platform)}
                    disabled={syncing === account.platform}
                    className="w-full px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium"
                  >
                    {syncing === account.platform ? "Syncing..." : "Sync Now"}
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowConnectModal(account.platform)}
                  disabled={syncing === account.platform}
                  className="w-full px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                >
                  {syncing === account.platform ? "Connecting..." : "Connect"}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Analytics Dashboard */}
      {analyticsData && connectedAccounts.some(acc => acc.connected) && (
        <div className="space-y-6">
          {/* Traffic Overview */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">Traffic Overview</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="bg-slate-50 rounded-lg p-4">
                <p className="text-sm text-slate-600 mb-1">Total Visitors</p>
                <p className="text-2xl font-bold text-slate-800">{analyticsData.totalVisitors.toLocaleString()}</p>
                <p className="text-xs text-slate-500 mt-1">Last 30 days</p>
              </div>
              <div className="bg-emerald-50 rounded-lg p-4">
                <p className="text-sm text-emerald-600 mb-1">Organic Traffic</p>
                <p className="text-2xl font-bold text-emerald-800">{analyticsData.organicTraffic.toLocaleString()}</p>
                <p className="text-xs text-emerald-500 mt-1">{Math.round((analyticsData.organicTraffic / analyticsData.totalVisitors) * 100)}% of total</p>
              </div>
              <div className="bg-blue-50 rounded-lg p-4">
                <p className="text-sm text-blue-600 mb-1">SEO Growth</p>
                <p className="text-2xl font-bold text-blue-800">+42%</p>
                <p className="text-xs text-blue-500 mt-1">vs last month</p>
              </div>
            </div>

            {/* Traffic Sources */}
            <div>
              <h4 className="text-sm font-semibold text-slate-700 mb-3">Traffic Sources</h4>
              <div className="space-y-2">
                {analyticsData.trafficSources.map((source, index) => (
                  <div key={index} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-32 bg-slate-100 rounded-full h-2">
                        <div 
                          className="bg-blue-500 h-2 rounded-full" 
                          style={{ width: `${source.percentage}%` }}
                        />
                      </div>
                      <span className="text-sm text-slate-700">{source.source}</span>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-medium text-slate-800">{source.visitors.toLocaleString()}</span>
                      <span className="text-xs text-slate-500 ml-2">({source.percentage}%)</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Top Performing Pages */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">Top Performing Pages</h3>
            
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left py-3 px-2 font-medium text-slate-700">Page</th>
                    <th className="text-center py-3 px-2 font-medium text-slate-700">Pageviews</th>
                    <th className="text-center py-3 px-2 font-medium text-slate-700">Visitors</th>
                    <th className="text-center py-3 px-2 font-medium text-slate-700">Avg Time</th>
                  </tr>
                </thead>
                <tbody>
                  {analyticsData.topPages.map((page, index) => (
                    <tr key={index} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="py-3 px-2">
                        <span className="text-emerald-600 font-medium">{page.url}</span>
                      </td>
                      <td className="text-center py-3">
                        <span className="font-medium text-slate-800">{page.pageviews.toLocaleString()}</span>
                      </td>
                      <td className="text-center py-3">
                        <span className="font-medium text-slate-800">{page.visitors.toLocaleString()}</span>
                      </td>
                      <td className="text-center py-3">
                        <span className="font-medium text-slate-800">{page.avgTime}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Keyword Rankings */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">Keyword Rankings</h3>
            
            <div className="space-y-3">
              {analyticsData.keywordRankings.map((ranking, index) => (
                <div key={index} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <div className="flex-1">
                    <p className="font-medium text-slate-800">{ranking.keyword}</p>
                    <p className="text-xs text-slate-500">{ranking.url}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-center">
                      <div className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold ${
                        ranking.position <= 3 ? "bg-green-100 text-green-700" :
                        ranking.position <= 10 ? "bg-yellow-100 text-yellow-700" :
                        "bg-red-100 text-red-700"
                      }`}>
                        #{ranking.position}
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-slate-800">{ranking.traffic}</p>
                      <p className="text-xs text-slate-500">visitors</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Connect Modal */}
      {showConnectModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-800">
                Connect {getPlatformName(showConnectModal)}
              </h3>
              <button
                onClick={() => setShowConnectModal(null)}
                className="text-slate-400 hover:text-slate-600 text-xl"
              >
                ×
              </button>
            </div>

            <div className="space-y-4">
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-4">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-2xl">{getPlatformIcon(showConnectModal)}</span>
                  <span className="font-medium text-blue-800">{getPlatformName(showConnectModal)}</span>
                </div>
                <p className="text-sm text-blue-700">
                  Connect your {getPlatformName(showConnectModal)} account to import real traffic data and keyword rankings.
                </p>
              </div>

              <div className="space-y-2">
                <h4 className="text-sm font-medium text-slate-700">What you'll get:</h4>
                <ul className="text-sm text-slate-600 space-y-1">
                  <li className="flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">•</span>
                    <span>Real traffic data and visitor analytics</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">•</span>
                    <span>Keyword ranking positions and traffic estimates</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">•</span>
                    <span>Top performing pages and content insights</span>
                  </li>
                </ul>
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => handleConnect(showConnectModal)}
                  disabled={syncing === showConnectModal}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                >
                  {syncing === showConnectModal ? "Connecting..." : "Connect Account"}
                </button>
                <button
                  onClick={() => setShowConnectModal(null)}
                  className="flex-1 px-4 py-2 bg-slate-100 text-slate-700 text-sm rounded-lg hover:bg-slate-200 font-medium"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
