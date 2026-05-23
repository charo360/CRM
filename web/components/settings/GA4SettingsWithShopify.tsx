"use client";

import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, CheckCircle, XCircle, Copy, ExternalLink, Zap } from "lucide-react";

interface GA4SettingsProps {
  onSave?: () => void;
}

export default function GA4SettingsWithShopify({ onSave }: GA4SettingsProps) {
  const [measurementId, setMeasurementId] = useState("");
  const [autoInjectShopify, setAutoInjectShopify] = useState(false);
  const [shopifyConnected, setShopifyConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    loadSettings();
    checkShopifyConnection();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await api.get<{ ga4_measurement_id?: string }>("/settings");
      setMeasurementId(response.ga4_measurement_id || "");
    } catch (error) {
      console.error("Failed to load settings:", error);
    } finally {
      setLoading(false);
    }
  };

  const checkShopifyConnection = async () => {
    try {
      const response = await api.get<{ shopify: boolean | null }>("/composio/connections");
      setShopifyConnected(response.shopify === true);
    } catch (error) {
      console.error("Failed to check Shopify connection:", error);
    }
  };

  const handleSave = async () => {
    if (!measurementId.trim()) {
      setMessage({ type: "error", text: "Please enter a GA4 Measurement ID" });
      return;
    }

    if (!measurementId.startsWith("G-")) {
      setMessage({ type: "error", text: "Measurement ID must start with 'G-'" });
      return;
    }

    setSaving(true);
    setMessage(null);

    try {
      await api.put("/settings", {
        ga4_measurement_id: measurementId.trim(),
        auto_inject_shopify: autoInjectShopify && shopifyConnected,
      });

      setMessage({
        type: "success",
        text: autoInjectShopify && shopifyConnected
          ? "GA4 settings saved and tracking codes injected to Shopify!"
          : "GA4 settings saved successfully!",
      });

      if (onSave) onSave();
    } catch (error: any) {
      setMessage({
        type: "error",
        text: error.message || "Failed to save settings",
      });
    } finally {
      setSaving(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setMessage({ type: "success", text: "Copied to clipboard!" });
    setTimeout(() => setMessage(null), 2000);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-slate-900">Google Analytics 4 Settings</h2>
        <p className="text-slate-600 mt-1">
          Track visitor behavior and trigger automatic discount campaigns
        </p>
      </div>

      {/* Measurement ID Input */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <label className="block text-sm font-medium text-slate-700 mb-2">
          GA4 Measurement ID
        </label>
        <input
          type="text"
          value={measurementId}
          onChange={(e) => setMeasurementId(e.target.value)}
          placeholder="G-XXXXXXXXXX"
          className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-sm text-slate-500 mt-2">
          Find this in Google Analytics → Admin → Data Streams → Your Stream
        </p>
      </div>

      {/* Shopify Auto-Inject */}
      {shopifyConnected && (
        <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl border border-green-200 p-6">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0">
              <Zap className="w-6 h-6 text-green-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-green-900 mb-2">
                Shopify Auto-Inject Available! 🎉
              </h3>
              <p className="text-sm text-green-800 mb-4">
                Your Shopify store is connected. We can automatically inject the tracking codes for you - no manual code needed!
              </p>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoInjectShopify}
                  onChange={(e) => setAutoInjectShopify(e.target.checked)}
                  className="w-5 h-5 text-green-600 rounded focus:ring-2 focus:ring-green-500"
                />
                <span className="text-sm font-medium text-green-900">
                  Automatically inject tracking codes to my Shopify store
                </span>
              </label>
              <p className="text-xs text-green-700 mt-2 ml-8">
                This will add both GA4 tracking and Zilo Behavior Tracker to your store automatically
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Manual Installation (if not auto-injecting) */}
      {(!shopifyConnected || !autoInjectShopify) && measurementId && (
        <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-4">
            Manual Installation Instructions
          </h3>

          {!shopifyConnected && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
              <p className="text-sm text-blue-800">
                💡 <strong>Tip:</strong> Connect your Shopify store to enable automatic code injection!
              </p>
            </div>
          )}

          <div className="space-y-4">
            {/* GA4 Tracking Code */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-slate-700">
                  1. GA4 Tracking Code
                </label>
                <button
                  onClick={() => copyToClipboard(`<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=${measurementId}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', '${measurementId}');
</script>`)}
                  className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
                >
                  <Copy className="w-4 h-4" />
                  Copy
                </button>
              </div>
              <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg text-xs overflow-x-auto">
{`<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=${measurementId}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', '${measurementId}');
</script>`}
              </pre>
            </div>

            {/* Zilo Behavior Tracker */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-slate-700">
                  2. Zilo Behavior Tracker
                </label>
                <button
                  onClick={() => copyToClipboard(`<!-- Zilo Behavior Tracker -->
<script src="https://crm.zilo.pro/tracking/zilo-behavior-tracker.js"></script>
<script>
  ZiloBehaviorTracker.init({
    businessId: 'YOUR_BUSINESS_ID',
    apiUrl: 'https://crm.zilo.pro/api'
  });
</script>`)}
                  className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
                >
                  <Copy className="w-4 h-4" />
                  Copy
                </button>
              </div>
              <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg text-xs overflow-x-auto">
{`<!-- Zilo Behavior Tracker -->
<script src="https://crm.zilo.pro/tracking/zilo-behavior-tracker.js"></script>
<script>
  ZiloBehaviorTracker.init({
    businessId: 'YOUR_BUSINESS_ID',
    apiUrl: 'https://crm.zilo.pro/api'
  });
</script>`}
              </pre>
            </div>

            {/* Platform Instructions */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <h4 className="font-medium text-slate-900 mb-3">Where to add the code:</h4>
              <ul className="space-y-2 text-sm text-slate-700">
                <li>
                  <strong>Shopify:</strong> Online Store → Themes → Edit Code → theme.liquid → Before {`</head>`}
                </li>
                <li>
                  <strong>Wix:</strong> Settings → Custom Code → Header Code
                </li>
                <li>
                  <strong>WordPress:</strong> Appearance → Theme Editor → header.php → Before {`</head>`}
                </li>
                <li>
                  <strong>Squarespace:</strong> Settings → Advanced → Code Injection → Header
                </li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Save Button */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleSave}
          disabled={saving || !measurementId.trim()}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {saving ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Saving...
            </>
          ) : (
            "Save Settings"
          )}
        </button>

        {message && (
          <div className={`flex items-center gap-2 ${message.type === "success" ? "text-green-600" : "text-red-600"}`}>
            {message.type === "success" ? (
              <CheckCircle className="w-5 h-5" />
            ) : (
              <XCircle className="w-5 h-5" />
            )}
            <span className="text-sm font-medium">{message.text}</span>
          </div>
        )}
      </div>

      {/* Help Links */}
      <div className="bg-blue-50 rounded-xl border border-blue-200 p-6">
        <h3 className="text-lg font-semibold text-blue-900 mb-3">Need Help?</h3>
        <div className="space-y-2 text-sm text-blue-800">
          <a
            href="/docs/ga4-universal-setup.md"
            target="_blank"
            className="flex items-center gap-2 hover:text-blue-900"
          >
            <ExternalLink className="w-4 h-4" />
            GA4 Setup Guide
          </a>
          <a
            href="/docs/behavior-discount-guide.md"
            target="_blank"
            className="flex items-center gap-2 hover:text-blue-900"
          >
            <ExternalLink className="w-4 h-4" />
            Behavior-Triggered Discounts Guide
          </a>
        </div>
      </div>
    </div>
  );
}
