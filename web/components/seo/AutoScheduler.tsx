import React, { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";

interface ScheduledPost {
  id: string;
  title: string;
  scheduled_date: string;
  platform: "wordpress" | "shopify" | "social";
  status: "scheduled" | "published" | "failed";
  content_preview: string;
}

interface PublishingCredentials {
  platform?: string;
  wp_url?: string;
  wp_username?: string;
  wp_password?: string;
  shopify_domain?: string;
  shopify_token?: string;
  updated_at?: string;
}

export default function AutoScheduler() {
  const [scheduledPosts, setScheduledPosts] = useState<ScheduledPost[]>([]);
  const [credentials, setCredentials] = useState<PublishingCredentials | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoPublish, setAutoPublish] = useState(false);
  const [publishTime, setPublishTime] = useState("09:00");
  const [frequency, setFrequency] = useState<"daily" | "weekly" | "custom">("weekly");
  const [showCredentials, setShowCredentials] = useState(false);
  const [newCredential, setNewCredential] = useState({
    platform: "wordpress" as "wordpress" | "shopify" | "social",
    url: "",
    username: "",
    api_key: ""
  });

  useEffect(() => {
    const loadSchedulerData = async () => {
      try {
        // Load publishing credentials - try WordPress first
        let creds = null;
        try {
          const wpCreds = await seoApi.getPublishCredentials("wordpress");
          creds = wpCreds as PublishingCredentials;
        } catch {
          try {
            const shopifyCreds = await seoApi.getPublishCredentials("shopify");
            creds = shopifyCreds as PublishingCredentials;
          } catch {
            // No credentials saved yet
          }
        }
        setCredentials(creds);

        // Load real scheduled posts from backend
        try {
          const scheduled = await seoApi.scheduledPosts();
          setScheduledPosts(scheduled.map(p => ({
            id: p.id,
            title: p.title,
            scheduled_date: p.scheduled_at,
            platform: p.platform as "wordpress" | "shopify" | "social",
            status: p.status as "scheduled" | "published" | "failed",
            content_preview: p.content_preview,
          })));
        } catch {
          setScheduledPosts([]);
        }

      } catch (error) {
        console.error("Failed to load scheduler data:", error);
      } finally {
        setLoading(false);
      }
    };

    loadSchedulerData();
  }, []);

  const handleSaveCredentials = async () => {
    try {
      // Map to existing API structure
      const payload = newCredential.platform === "wordpress" 
        ? { 
            platform: newCredential.platform,
            wp_url: newCredential.url, 
            wp_username: newCredential.username, 
            wp_password: newCredential.api_key 
          }
        : { 
            platform: newCredential.platform,
            shopify_domain: newCredential.url, 
            shopify_token: newCredential.api_key 
          };
      
      await seoApi.savePublishCredentials(payload);
      
      // Reload credentials
      const creds = await seoApi.getPublishCredentials(newCredential.platform);
      setCredentials(creds as PublishingCredentials);
      setShowCredentials(false);
      setNewCredential({ platform: "wordpress", url: "", username: "", api_key: "" });
    } catch (error) {
      console.error("Failed to save credentials:", error);
    }
  };

  const handleSchedulePost = async (postId: string, date: string) => {
    try {
      // Mock implementation - would need backend endpoint
      console.log("Scheduling post:", postId, "for date:", date);
      
      // Update local state
      setScheduledPosts(prev => 
        prev.map(post => 
          post.id === postId 
            ? { ...post, scheduled_date: date, status: "scheduled" as const }
            : post
        )
      );
    } catch (error) {
      console.error("Failed to schedule post:", error);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "published": return "bg-green-100 text-green-700";
      case "failed": return "bg-red-100 text-red-700";
      default: return "bg-blue-100 text-blue-700";
    }
  };

  const getPlatformIcon = (platform: string) => {
    switch (platform) {
      case "wordpress": return "📝";
      case "shopify": return "🛍️";
      case "social": return "📱";
      default: return "🌐";
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
          <h2 className="text-xl font-bold text-slate-800">Auto-Publishing Scheduler</h2>
          <p className="text-sm text-slate-500 mt-1">Automatically publish your content to multiple platforms</p>
        </div>
        <button
          onClick={() => setShowCredentials(true)}
          className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 font-medium"
        >
          {credentials ? "Manage Platforms" : "Connect Platform"}
        </button>
      </div>

      {/* Auto-publish Settings */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Auto-Publish Settings</h3>
        
        <div className="space-y-4">
          {/* Auto-publish toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-slate-700">Enable Auto-Publishing</p>
              <p className="text-sm text-slate-500">Automatically publish scheduled content</p>
            </div>
            <button
              onClick={() => setAutoPublish(!autoPublish)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                autoPublish ? "bg-emerald-600" : "bg-slate-200"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  autoPublish ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          {/* Publish time */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Default Publish Time
            </label>
            <input
              type="time"
              value={publishTime}
              onChange={(e) => setPublishTime(e.target.value)}
              className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          {/* Frequency */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Publishing Frequency
            </label>
            <div className="flex gap-2">
              {(["daily", "weekly", "custom"] as const).map(freq => (
                <button
                  key={freq}
                  onClick={() => setFrequency(freq)}
                  className={`px-3 py-2 text-sm rounded-lg font-medium transition-colors ${
                    frequency === freq
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {freq.charAt(0).toUpperCase() + freq.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Connected Platforms */}
      {credentials && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-800 mb-4">Connected Platforms</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {credentials?.wp_url && (
              <div className="border border-green-200 bg-green-50 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">📝</span>
                  <span className="font-medium text-green-800">WordPress</span>
                  <span className="text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded-full">Connected</span>
                </div>
                <p className="text-xs text-green-700">{credentials.wp_url}</p>
              </div>
            )}
            
            {credentials?.shopify_domain && (
              <div className="border border-green-200 bg-green-50 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">🛍️</span>
                  <span className="font-medium text-green-800">Shopify</span>
                  <span className="text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded-full">Connected</span>
                </div>
                <p className="text-xs text-green-700">{credentials.shopify_domain}</p>
              </div>
            )}
            
            {credentials?.platform === "social" && (
              <div className="border border-green-200 bg-green-50 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">📱</span>
                  <span className="font-medium text-green-800">Social Media</span>
                  <span className="text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded-full">Connected</span>
                </div>
                <p className="text-xs text-green-700">Social platforms connected</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Scheduled Posts */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Scheduled Posts</h3>
        
        {scheduledPosts.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-slate-400 text-sm mb-4">No posts scheduled yet</p>
            <button
              onClick={() => window.location.href = "/dashboard/seo?tab=blog"}
              className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 font-medium"
            >
              Schedule Your First Post
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {scheduledPosts.map((post) => (
              <div key={post.id} className="border border-slate-100 rounded-lg p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-lg">{getPlatformIcon(post.platform)}</span>
                      <h4 className="font-medium text-slate-800">{post.title}</h4>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${getStatusColor(post.status)}`}>
                        {post.status}
                      </span>
                    </div>
                    <p className="text-sm text-slate-600 line-clamp-2">{post.content_preview}</p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                      <span>Scheduled: {new Date(post.scheduled_date).toLocaleString()}</span>
                      <span>Platform: {post.platform}</span>
                    </div>
                  </div>
                  
                  <div className="flex gap-2 ml-4">
                    {post.status === "scheduled" && (
                      <>
                        <button
                          onClick={() => handleSchedulePost(post.id, new Date().toISOString())}
                          className="px-3 py-1.5 bg-emerald-100 text-emerald-700 text-xs rounded-lg hover:bg-emerald-200 font-medium"
                        >
                          Publish Now
                        </button>
                        <button
                          className="px-3 py-1.5 bg-slate-100 text-slate-700 text-xs rounded-lg hover:bg-slate-200 font-medium"
                        >
                          Reschedule
                        </button>
                      </>
                    )}
                    <button
                      className="px-3 py-1.5 bg-red-100 text-red-700 text-xs rounded-lg hover:bg-red-200 font-medium"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Calendar View */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Publishing Calendar</h3>
        
        <div className="grid grid-cols-7 gap-1 mb-4">
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(day => (
            <div key={day} className="text-xs font-medium text-slate-500 text-center py-2">
              {day}
            </div>
          ))}
        </div>
        
        <div className="grid grid-cols-7 gap-1">
          {/* Simple calendar grid - in production would show actual scheduled posts */}
          {Array.from({ length: 35 }, (_, i) => {
            const date = i - 2; // Start from previous month
            const isCurrentMonth = date >= 1 && date <= 31;
            const hasPost = [5, 8, 12, 15, 20, 25].includes(date);
            
            return (
              <div
                key={i}
                className={`aspect-square border rounded-lg p-1 text-xs ${
                  !isCurrentMonth ? "bg-slate-50 text-slate-300" : "bg-white"
                } ${hasPost ? "border-emerald-200 bg-emerald-50" : "border-slate-100"}`}
              >
                {isCurrentMonth && date > 0 && (
                  <div>
                    <div className="font-medium text-slate-700">{date}</div>
                    {hasPost && (
                      <div className="w-1 h-1 bg-emerald-500 rounded-full mx-auto mt-1"></div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Credentials Modal */}
      {showCredentials && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-800">Connect Publishing Platform</h3>
              <button
                onClick={() => setShowCredentials(false)}
                className="text-slate-400 hover:text-slate-600 text-xl"
              >
                ×
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Platform</label>
                <select
                  value={newCredential.platform}
                  onChange={(e) => setNewCredential({...newCredential, platform: e.target.value as any})}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="wordpress">WordPress</option>
                  <option value="shopify">Shopify</option>
                  <option value="social">Social Media</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  {newCredential.platform === "wordpress" ? "Site URL" : 
                   newCredential.platform === "shopify" ? "Store URL" : "Platform URL"}
                </label>
                <input
                  type="url"
                  value={newCredential.url}
                  onChange={(e) => setNewCredential({...newCredential, url: e.target.value})}
                  placeholder={newCredential.platform === "wordpress" ? "https://yoursite.com" : "https://yourstore.myshopify.com"}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Username/Email</label>
                <input
                  type="text"
                  value={newCredential.username}
                  onChange={(e) => setNewCredential({...newCredential, username: e.target.value})}
                  placeholder="admin@yoursite.com"
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">API Key / Password</label>
                <input
                  type="password"
                  value={newCredential.api_key}
                  onChange={(e) => setNewCredential({...newCredential, api_key: e.target.value})}
                  placeholder="Application password or API key"
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  onClick={handleSaveCredentials}
                  disabled={!newCredential.url || !newCredential.username || !newCredential.api_key}
                  className="flex-1 px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 disabled:opacity-50 font-medium"
                >
                  Connect Platform
                </button>
                <button
                  onClick={() => setShowCredentials(false)}
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
