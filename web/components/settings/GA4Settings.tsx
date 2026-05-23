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

export default function GA4Settings() {
  const [measurementId, setMeasurementId] = useState("");
  const [status, setStatus] = useState<GA4Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activating, setActivating] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const [settings, ga4Status] = await Promise.all([
        api.get<{ ga4_measurement_id?: string }>("/settings"),
        api.get<GA4Status>("/blog/ga4/status"),
      ]);
      
      setMeasurementId(settings.ga4_measurement_id || "");
      setStatus(ga4Status);
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
      setMessage({ type: "success", text: "GA4 Measurement ID saved successfully!" });
      await loadStatus();
    } catch (error) {
      setMessage({ type: "error", text: "Failed to save GA4 Measurement ID" });
    } finally {
      setSaving(false);
    }
  };

  const handleActivate = async () => {
    setActivating(true);
    setMessage(null);
    
    try {
      const result = await api.post<{ success: boolean; message: string }>("/blog/ga4/activate", {});
      
      if (result.success) {
        setMessage({ type: "success", text: "GA4 tracking activated on your website!" });
        await loadStatus();
      } else {
        setMessage({ type: "error", text: result.message || "Failed to activate GA4 tracking" });
      }
    } catch (error: any) {
      setMessage({ 
        type: "error", 
        text: error.response?.data?.detail || "Failed to activate GA4 tracking" 
      });
    } finally {
      setActivating(false);
    }
  };

  const handleDeactivate = async () => {
    if (!confirm("Are you sure you want to remove GA4 tracking from your website?")) {
      return;
    }
    
    setActivating(true);
    setMessage(null);
    
    try {
      const result = await api.post<{ success: boolean; message: string }>("/blog/ga4/deactivate", {});
      
      if (result.success) {
        setMessage({ type: "success", text: "GA4 tracking removed from your website" });
        await loadStatus();
      } else {
        setMessage({ type: "error", text: result.message || "Failed to remove GA4 tracking" });
      }
    } catch (error: any) {
      setMessage({ 
        type: "error", 
        text: error.response?.data?.detail || "Failed to remove GA4 tracking" 
      });
    } finally {
      setActivating(false);
    }
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
            Track visitor behavior on your website with Google Analytics 4
          </p>
        </div>
        {status?.ga4_active && (
          <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full font-medium">
            ✓ Active
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
                → Admin → Data Streams → Select your stream → Copy the Measurement ID (starts with G-)
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

        {/* Step 2: Activate on Website */}
        {status?.ga4_configured && (
          <div className="bg-slate-50 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">
                2
              </div>
              <div className="flex-1">
                <h4 className="font-medium text-slate-800 text-sm mb-2">Activate tracking on your website</h4>
                {!status.blog_exists ? (
                  <p className="text-xs text-amber-600 mb-3">
                    ⚠️ You need to activate your blog first before enabling GA4 tracking
                  </p>
                ) : status.ga4_active ? (
                  <div>
                    <p className="text-xs text-green-700 mb-2">
                      ✓ GA4 tracking is active on your website
                    </p>
                    {status.activated_at && (
                      <p className="text-xs text-slate-500 mb-3">
                        Activated on {new Date(status.activated_at).toLocaleDateString()}
                      </p>
                    )}
                    {status.needs_update && (
                      <p className="text-xs text-amber-600 mb-3">
                        ⚠️ Your saved Measurement ID is different from the active one. Click "Update Tracking" to sync.
                      </p>
                    )}
                    <div className="flex gap-2">
                      {status.needs_update && (
                        <button
                          onClick={handleActivate}
                          disabled={activating}
                          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                        >
                          {activating ? "Updating..." : "Update Tracking"}
                        </button>
                      )}
                      <button
                        onClick={handleDeactivate}
                        disabled={activating}
                        className="px-4 py-2 bg-red-50 text-red-600 text-sm font-medium rounded-lg hover:bg-red-100 disabled:opacity-50 transition-colors"
                      >
                        {activating ? "Removing..." : "Remove Tracking"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <p className="text-xs text-slate-600 mb-3">
                      Click the button below to add GA4 tracking code to your website
                    </p>
                    <button
                      onClick={handleActivate}
                      disabled={activating}
                      className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                    >
                      {activating ? "Activating..." : "Activate GA4 Tracking"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Help Text */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h4 className="font-medium text-blue-900 text-sm mb-2">💡 Why use Google Analytics 4?</h4>
          <ul className="text-xs text-blue-800 space-y-1">
            <li>• Track how many people visit your website</li>
            <li>• See which pages are most popular</li>
            <li>• Understand where your visitors come from</li>
            <li>• Measure conversions and user engagement</li>
            <li>• Make data-driven decisions to grow your business</li>
          </ul>
          <p className="text-xs text-blue-700 mt-3">
            <a
              href="https://support.google.com/analytics/answer/9304153"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:no-underline"
            >
              Learn more about Google Analytics 4 →
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
