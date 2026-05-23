"use client";

import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";

interface GA4Status {
  blog_exists: boolean;
  ga4_configured: boolean;
  ga4_active: boolean;
  measurement_id?: string;
  blog_measurement_id?: string;
  activated_at?: string;
  needs_update?: boolean;
}

type Platform = "shopify" | "wix" | "wordpress" | "squarespace" | "custom" | "zilo-blog";

export default function GA4SettingsUniversal() {
  const [measurementId, setMeasurementId] = useState("");
  const [selectedPlatform, setSelectedPlatform] = useState<Platform>("shopify");
  const [status, setStatus] = useState<GA4Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showInstructions, setShowInstructions] = useState(false);
  const [activatingBlog, setActivatingBlog] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const [settings, ga4Status] = await Promise.all([
        api.get<{ ga4_measurement_id?: string }>("/settings"),
        api.get<GA4Status>("/blog/ga4/status").catch(() => null),
      ]);
      
      setMeasurementId(settings.ga4_measurement_id || "");
      if (ga4Status) setStatus(ga4Status);
    } catch (error) {
      console.error("Failed to load GA4 status:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    
    try {
      await api.put("/settings", { ga4_measurement_id: measurementId.trim() });
      setMessage({ type: "success", text: "GA4 Measurement ID saved!" });
      await loadStatus();
    } catch (error) {
      setMessage({ type: "error", text: "Failed to save GA4 Measurement ID" });
    } finally {
      setSaving(false);
    }
  };

  const handleActivateBlog = async () => {
    setActivatingBlog(true);
    setMessage(null);
    
    try {
      const result = await api.post<{ success: boolean; message: string }>("/blog/ga4/activate", {});
      
      if (result.success) {
        setMessage({ type: "success", text: "GA4 activated on your Zilo blog!" });
        await loadStatus();
      } else {
        setMessage({ type: "error", text: result.message || "Failed to activate" });
      }
    } catch (error: any) {
      setMessage({ 
        type: "error", 
        text: error.response?.data?.detail || "Failed to activate on blog" 
      });
    } finally {
      setActivatingBlog(false);
    }
  };

  const getTrackingCode = () => {
    if (!measurementId) return "";
    return `<!-- Google Analytics 4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id=${measurementId}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', '${measurementId}');
</script>
<!-- End Google Analytics 4 -->`;
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(getTrackingCode());
    setMessage({ type: "success", text: "Tracking code copied to clipboard!" });
    setTimeout(() => setMessage(null), 3000);
  };

  const platforms = [
    { id: "shopify", name: "Shopify", icon: "🛍️" },
    { id: "wix", name: "Wix", icon: "🎨" },
    { id: "wordpress", name: "WordPress", icon: "📝" },
    { id: "squarespace", name: "Squarespace", icon: "🎯" },
    { id: "custom", name: "Custom Website", icon: "💻" },
    { id: "zilo-blog", name: "Zilo Blog (Auto)", icon: "⚡" },
  ];

  const getPlatformInstructions = (platform: Platform) => {
    const code = getTrackingCode();
    
    const instructions: Record<Platform, { steps: string[]; note?: string }> = {
      shopify: {
        steps: [
          "Go to your Shopify Admin → Online Store → Themes",
          "Click Actions → Edit code",
          "Find theme.liquid in the Layout folder",
          "Paste the tracking code just before the closing </head> tag",
          "Click Save",
        ],
        note: "💡 Alternatively, use Shopify's Google Analytics integration in Settings → Apps and sales channels",
      },
      wix: {
        steps: [
          "Go to your Wix Dashboard → Settings → Custom Code",
          "Click + Add Custom Code",
          "Paste the tracking code",
          "Select 'Head' as the placement",
          "Select 'All Pages'",
          "Click Apply",
        ],
      },
      wordpress: {
        steps: [
          "Install a plugin like 'Insert Headers and Footers' or 'WPCode'",
          "Go to Settings → Insert Headers and Footers (or WPCode → Header & Footer)",
          "Paste the tracking code in the 'Header' section",
          "Click Save",
        ],
        note: "💡 Or add it directly to your theme's header.php file before </head>",
      },
      squarespace: {
        steps: [
          "Go to Settings → Advanced → Code Injection",
          "Paste the tracking code in the 'Header' section",
          "Click Save",
        ],
      },
      custom: {
        steps: [
          "Open your website's HTML files",
          "Find the <head> section in your main template/layout file",
          "Paste the tracking code just before the closing </head> tag",
          "Save and upload the file to your server",
        ],
      },
      "zilo-blog": {
        steps: [
          "Your Zilo blog can be automatically configured!",
          "Just click the 'Auto-Activate on Zilo Blog' button below",
          "The system will inject the tracking code for you",
        ],
        note: "✨ This only works for your Zilo-hosted blog, not external websites",
      },
    };

    return instructions[platform];
  };

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-6 animate-pulse">
        <div className="h-6 bg-slate-200 rounded w-1/3 mb-4" />
        <div className="h-4 bg-slate-100 rounded w-2/3" />
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
            📊 Google Analytics 4
          </h3>
          <p className="text-sm text-slate-500 mt-1">
            Track visitor behavior on your website (works with any platform)
          </p>
        </div>
        {status?.ga4_configured && (
          <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full font-medium">
            ✓ Configured
          </span>
        )}
      </div>

      {message && (
        <div
          className={`mb-4 p-3 rounded-lg text-sm ${
            message.type === "success"
              ? "bg-green-50 text-green-800 border border-green-200"
              : "bg-red-50 text-red-800 border border-red-200"
          }`}
        >
          {message.text}
        </div>
      )}

      <div className="space-y-4">
        {/* Step 1: Get GA4 Measurement ID */}
        <div className="bg-slate-50 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">
              1
            </div>
            <div className="flex-1">
              <h4 className="font-medium text-slate-800 text-sm mb-2">Get your GA4 Measurement ID</h4>
              <p className="text-xs text-slate-600 mb-3">
                Go to{" "}
                <a
                  href="https://analytics.google.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  Google Analytics
                </a>{" "}
                → Admin → Data Streams → Select your stream → Copy the Measurement ID (G-XXXXXXXXXX)
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={measurementId}
                  onChange={(e) => setMeasurementId(e.target.value)}
                  placeholder="G-XXXXXXXXXX"
                  className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  onClick={handleSave}
                  disabled={saving || !measurementId.trim()}
                  className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {saving ? "Saving..." : "Save"}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Step 2: Choose Platform & Get Instructions */}
        {measurementId && (
          <div className="bg-slate-50 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">
                2
              </div>
              <div className="flex-1">
                <h4 className="font-medium text-slate-800 text-sm mb-3">Add tracking to your website</h4>
                
                {/* Platform Selector */}
                <div className="grid grid-cols-3 gap-2 mb-4">
                  {platforms.map((platform) => (
                    <button
                      key={platform.id}
                      onClick={() => setSelectedPlatform(platform.id as Platform)}
                      className={`p-3 rounded-lg border-2 text-xs font-medium transition-all ${
                        selectedPlatform === platform.id
                          ? "border-blue-600 bg-blue-50 text-blue-900"
                          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                      }`}
                    >
                      <div className="text-lg mb-1">{platform.icon}</div>
                      {platform.name}
                    </button>
                  ))}
                </div>

                {/* Instructions */}
                {selectedPlatform === "zilo-blog" ? (
                  <div className="bg-white rounded-lg border border-slate-200 p-4">
                    <h5 className="font-medium text-slate-800 text-sm mb-2">⚡ Auto-Activate on Zilo Blog</h5>
                    {status?.blog_exists ? (
                      <div>
                        {status.ga4_active && status.blog_measurement_id === measurementId ? (
                          <p className="text-xs text-green-700 mb-2">
                            ✓ GA4 is already active on your Zilo blog!
                          </p>
                        ) : (
                          <div>
                            <p className="text-xs text-slate-600 mb-3">
                              Click below to automatically add GA4 tracking to your Zilo blog
                            </p>
                            <button
                              onClick={handleActivateBlog}
                              disabled={activatingBlog}
                              className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                            >
                              {activatingBlog ? "Activating..." : "Auto-Activate on Zilo Blog"}
                            </button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-amber-600">
                        ⚠️ You need to activate your Zilo blog first
                      </p>
                    )}
                  </div>
                ) : (
                  <div>
                    <button
                      onClick={() => setShowInstructions(!showInstructions)}
                      className="w-full mb-3 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      {showInstructions ? "Hide Instructions" : "Show Instructions"}
                    </button>

                    {showInstructions && (
                      <div className="bg-white rounded-lg border border-slate-200 p-4 space-y-3">
                        <h5 className="font-medium text-slate-800 text-sm">
                          How to add GA4 to {platforms.find(p => p.id === selectedPlatform)?.name}:
                        </h5>
                        <ol className="text-xs text-slate-700 space-y-2 list-decimal list-inside">
                          {getPlatformInstructions(selectedPlatform).steps.map((step, idx) => (
                            <li key={idx}>{step}</li>
                          ))}
                        </ol>
                        {getPlatformInstructions(selectedPlatform).note && (
                          <p className="text-xs text-blue-700 bg-blue-50 p-2 rounded">
                            {getPlatformInstructions(selectedPlatform).note}
                          </p>
                        )}

                        {/* Tracking Code */}
                        <div className="mt-4">
                          <div className="flex items-center justify-between mb-2">
                            <h6 className="text-xs font-medium text-slate-700">Your Tracking Code:</h6>
                            <button
                              onClick={copyToClipboard}
                              className="text-xs text-blue-600 hover:text-blue-700 font-medium"
                            >
                              📋 Copy Code
                            </button>
                          </div>
                          <pre className="bg-slate-900 text-green-400 text-xs p-3 rounded overflow-x-auto">
                            {getTrackingCode()}
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Help Section */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h4 className="font-medium text-blue-900 text-sm mb-2">💡 Why use Google Analytics 4?</h4>
          <ul className="text-xs text-blue-800 space-y-1">
            <li>• Track visitor numbers and behavior on ANY website platform</li>
            <li>• See which pages are most popular</li>
            <li>• Understand where your visitors come from</li>
            <li>• Works with Shopify, Wix, WordPress, custom sites, and more</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
