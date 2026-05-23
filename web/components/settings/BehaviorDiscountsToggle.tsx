"use client";

import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Zap, TrendingUp, ShoppingCart, Loader2 } from "lucide-react";

export default function BehaviorDiscountsToggle() {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await api.get<{ behavior_discounts_enabled?: boolean }>("/settings");
      setEnabled(response.behavior_discounts_enabled || false);
    } catch (error) {
      console.error("Failed to load settings:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (newValue: boolean) => {
    setSaving(true);
    try {
      await api.put("/settings", {
        behavior_discounts_enabled: newValue,
      });
      setEnabled(newValue);
    } catch (error) {
      console.error("Failed to update setting:", error);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-4">
        <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0">
          <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center">
            <Zap className="w-6 h-6 text-white" />
          </div>
        </div>

        <div className="flex-1">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-lg font-semibold text-slate-900">
              Behavior-Triggered Discounts
            </h3>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => handleToggle(e.target.checked)}
                disabled={saving}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-green-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
            </label>
          </div>

          <p className="text-sm text-slate-600 mb-4">
            Automatically send personalized discounts to website visitors based on their behavior (cart abandonment, exit intent, browsing patterns, etc.)
          </p>

          {enabled ? (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-sm font-medium text-green-900">Active</span>
              </div>
              <p className="text-xs text-green-700 mb-3">
                Behavior-triggered discount campaigns are running. Visitors will receive offers based on your campaign settings.
              </p>
              <div className="flex items-center gap-4 text-xs text-green-800">
                <div className="flex items-center gap-1">
                  <ShoppingCart className="w-4 h-4" />
                  <span>Cart Recovery</span>
                </div>
                <div className="flex items-center gap-1">
                  <TrendingUp className="w-4 h-4" />
                  <span>Exit Intent</span>
                </div>
                <div className="flex items-center gap-1">
                  <Zap className="w-4 h-4" />
                  <span>Browsing Triggers</span>
                </div>
              </div>
              <a
                href="/dashboard/marketing/behavior-discounts"
                className="inline-block mt-3 text-xs font-medium text-green-700 hover:text-green-800 underline"
              >
                Manage Campaigns →
              </a>
            </div>
          ) : (
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
              <p className="text-sm text-slate-600 mb-3">
                <strong>What you get when enabled:</strong>
              </p>
              <ul className="text-xs text-slate-600 space-y-2 mb-3">
                <li>• <strong>25-30% cart recovery rate</strong> - Recover abandoned carts automatically</li>
                <li>• <strong>10-15% exit intent conversion</strong> - Catch visitors before they leave</li>
                <li>• <strong>15-20% first-time boost</strong> - Welcome new visitors with offers</li>
                <li>• <strong>Multi-channel delivery</strong> - Email, SMS, WhatsApp, popups, banners</li>
                <li>• <strong>Real-time analytics</strong> - Track campaign performance</li>
              </ul>
              <p className="text-xs text-slate-500">
                Enable this feature to start converting browsers into buyers with smart, timely discounts.
              </p>
            </div>
          )}
        </div>
      </div>

      {saving && (
        <div className="mt-4 flex items-center gap-2 text-sm text-blue-600">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Saving...</span>
        </div>
      )}
    </div>
  );
}
