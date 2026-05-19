"use client";

import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Plus, Trash2, Edit2, BarChart3, Power, PowerOff, Loader2, TrendingUp, Users, DollarSign } from "lucide-react";

interface Campaign {
  _id: string;
  name: string;
  trigger_event: string;
  discount_type: string;
  discount_value: number;
  delivery_method: string;
  message_template: string;
  conditions: Record<string, any>;
  active: boolean;
  sent_count: number;
  conversion_count: number;
}

interface Analytics {
  campaign_id: string;
  campaign_name: string;
  trigger_event: string;
  sent_count: number;
  conversion_count: number;
  conversion_rate: number;
  revenue: number;
  active: boolean;
}

const TRIGGER_EVENTS = [
  { value: "cart_abandoned", label: "🛒 Cart Abandoned", description: "When someone adds items but doesn't checkout" },
  { value: "browsed_product", label: "👀 Product Browsing", description: "Views product multiple times without buying" },
  { value: "visited_multiple_times", label: "🔄 Returning Visitor", description: "Comes back to your site" },
  { value: "exit_intent", label: "🚪 Exit Intent", description: "About to leave the site" },
  { value: "time_on_site", label: "⏱️ Time on Site", description: "Spends significant time browsing" },
  { value: "page_views_threshold", label: "📄 Page Views", description: "Views multiple pages" },
  { value: "first_time_visitor", label: "🆕 First-Time Visitor", description: "New to your site" },
  { value: "high_value_visitor", label: "💎 High-Value Visitor", description: "Viewing expensive products" },
];

const DELIVERY_METHODS = [
  { value: "email", label: "📧 Email", description: "Requires email address" },
  { value: "sms", label: "📱 SMS", description: "Requires phone number" },
  { value: "whatsapp", label: "💬 WhatsApp", description: "Requires phone number" },
  { value: "popup", label: "🎯 Popup", description: "Shows on website (no contact needed)" },
  { value: "banner", label: "🎨 Banner", description: "Top banner (no contact needed)" },
];

export default function BehaviorDiscountsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [analytics, setAnalytics] = useState<Analytics[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [campaignsRes, analyticsRes] = await Promise.all([
        api.get<{ campaigns: Campaign[] }>("/marketing/behavior-discounts/campaigns"),
        api.get<{ analytics: Analytics[] }>("/marketing/behavior-discounts/analytics"),
      ]);
      setCampaigns(campaignsRes.campaigns);
      setAnalytics(analyticsRes.analytics);
    } catch (error) {
      console.error("Failed to load campaigns:", error);
    } finally {
      setLoading(false);
    }
  };

  const toggleCampaign = async (campaignId: string, currentActive: boolean) => {
    try {
      await api.put(`/marketing/behavior-discounts/campaigns/${campaignId}`, {
        active: !currentActive,
      });
      await loadData();
    } catch (error) {
      console.error("Failed to toggle campaign:", error);
    }
  };

  const deleteCampaign = async (campaignId: string) => {
    if (!confirm("Are you sure you want to delete this campaign?")) return;

    try {
      await api.delete(`/marketing/behavior-discounts/campaigns/${campaignId}`);
      await loadData();
    } catch (error) {
      console.error("Failed to delete campaign:", error);
    }
  };

  const totalSent = analytics.reduce((sum, a) => sum + a.sent_count, 0);
  const totalConverted = analytics.reduce((sum, a) => sum + a.conversion_count, 0);
  const totalRevenue = analytics.reduce((sum, a) => sum + a.revenue, 0);
  const avgConversionRate = analytics.length > 0
    ? analytics.reduce((sum, a) => sum + a.conversion_rate, 0) / analytics.length
    : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Behavior-Triggered Discounts</h1>
          <p className="text-slate-600 mt-1">Automatically send discounts based on visitor behavior</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-5 h-5" />
          Create Campaign
        </button>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
              <Users className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-sm text-slate-600">Discounts Sent</p>
              <p className="text-2xl font-bold text-slate-900">{totalSent.toLocaleString()}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-slate-600">Conversions</p>
              <p className="text-2xl font-bold text-slate-900">{totalConverted.toLocaleString()}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-slate-600">Avg Conversion Rate</p>
              <p className="text-2xl font-bold text-slate-900">{avgConversionRate.toFixed(1)}%</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-emerald-600" />
            </div>
            <div>
              <p className="text-sm text-slate-600">Revenue Generated</p>
              <p className="text-2xl font-bold text-slate-900">${totalRevenue.toLocaleString()}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Campaigns List */}
      <div className="bg-white rounded-xl border border-slate-200">
        <div className="p-6 border-b border-slate-200">
          <h2 className="text-xl font-semibold text-slate-900">Active Campaigns</h2>
        </div>

        {campaigns.length === 0 ? (
          <div className="p-12 text-center">
            <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-4">
              <BarChart3 className="w-8 h-8 text-slate-400" />
            </div>
            <h3 className="text-lg font-medium text-slate-900 mb-2">No campaigns yet</h3>
            <p className="text-slate-600 mb-4">Create your first behavior-triggered discount campaign</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Create Campaign
            </button>
          </div>
        ) : (
          <div className="divide-y divide-slate-200">
            {campaigns.map((campaign) => {
              const stats = analytics.find(a => a.campaign_id === campaign._id);
              const triggerEvent = TRIGGER_EVENTS.find(t => t.value === campaign.trigger_event);
              const deliveryMethod = DELIVERY_METHODS.find(d => d.value === campaign.delivery_method);

              return (
                <div key={campaign._id} className="p-6 hover:bg-slate-50 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-lg font-semibold text-slate-900">{campaign.name}</h3>
                        {campaign.active ? (
                          <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full font-medium">
                            Active
                          </span>
                        ) : (
                          <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded-full font-medium">
                            Paused
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-4 text-sm text-slate-600 mb-3">
                        <span>{triggerEvent?.label || campaign.trigger_event}</span>
                        <span>•</span>
                        <span>{deliveryMethod?.label || campaign.delivery_method}</span>
                        <span>•</span>
                        <span className="font-medium text-green-600">
                          {campaign.discount_type === "percentage" 
                            ? `${campaign.discount_value}% OFF` 
                            : `$${campaign.discount_value} OFF`}
                        </span>
                      </div>

                      {stats && (
                        <div className="flex items-center gap-6 text-sm">
                          <div>
                            <span className="text-slate-600">Sent: </span>
                            <span className="font-medium text-slate-900">{stats.sent_count}</span>
                          </div>
                          <div>
                            <span className="text-slate-600">Converted: </span>
                            <span className="font-medium text-slate-900">{stats.conversion_count}</span>
                          </div>
                          <div>
                            <span className="text-slate-600">Rate: </span>
                            <span className="font-medium text-green-600">{stats.conversion_rate.toFixed(1)}%</span>
                          </div>
                          {stats.revenue > 0 && (
                            <div>
                              <span className="text-slate-600">Revenue: </span>
                              <span className="font-medium text-emerald-600">${stats.revenue.toLocaleString()}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleCampaign(campaign._id, campaign.active)}
                        className="p-2 hover:bg-slate-200 rounded-lg transition-colors"
                        title={campaign.active ? "Pause campaign" : "Activate campaign"}
                      >
                        {campaign.active ? (
                          <PowerOff className="w-5 h-5 text-slate-600" />
                        ) : (
                          <Power className="w-5 h-5 text-slate-600" />
                        )}
                      </button>
                      <button
                        onClick={() => setEditingCampaign(campaign)}
                        className="p-2 hover:bg-slate-200 rounded-lg transition-colors"
                        title="Edit campaign"
                      >
                        <Edit2 className="w-5 h-5 text-slate-600" />
                      </button>
                      <button
                        onClick={() => deleteCampaign(campaign._id)}
                        className="p-2 hover:bg-red-100 rounded-lg transition-colors"
                        title="Delete campaign"
                      >
                        <Trash2 className="w-5 h-5 text-red-600" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Help Section */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-200 p-6">
        <h3 className="text-lg font-semibold text-blue-900 mb-2">💡 How It Works</h3>
        <ul className="text-sm text-blue-800 space-y-2">
          <li>• <strong>Choose a trigger:</strong> Cart abandoned, exit intent, product browsing, etc.</li>
          <li>• <strong>Set conditions:</strong> Minimum cart value, page views, time on site</li>
          <li>• <strong>Create discount:</strong> Percentage off, fixed amount, or free shipping</li>
          <li>• <strong>Pick delivery:</strong> Email, SMS, WhatsApp, popup, or banner</li>
          <li>• <strong>Watch conversions:</strong> Track performance in real-time</li>
        </ul>
        <a
          href="/docs/behavior-discount-guide.md"
          target="_blank"
          className="inline-block mt-4 text-sm text-blue-700 hover:text-blue-800 font-medium underline"
        >
          Read the complete guide →
        </a>
      </div>

      {/* Create/Edit Modal */}
      {(showCreateModal || editingCampaign) && (
        <CampaignModal
          campaign={editingCampaign}
          onClose={() => {
            setShowCreateModal(false);
            setEditingCampaign(null);
          }}
          onSave={async () => {
            setShowCreateModal(false);
            setEditingCampaign(null);
            await loadData();
          }}
        />
      )}
    </div>
  );
}

// Campaign Create/Edit Modal Component
function CampaignModal({
  campaign,
  onClose,
  onSave,
}: {
  campaign: Campaign | null;
  onClose: () => void;
  onSave: () => void;
}) {
  const [formData, setFormData] = useState({
    name: campaign?.name || "",
    trigger_event: campaign?.trigger_event || "cart_abandoned",
    discount_type: campaign?.discount_type || "percentage",
    discount_value: campaign?.discount_value || 10,
    delivery_method: campaign?.delivery_method || "popup",
    message_template: campaign?.message_template || "Special offer! Use code {discount_code} for {discount_value}% off!",
    conditions: campaign?.conditions || {},
    active: campaign?.active ?? true,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    try {
      if (campaign) {
        await api.put(`/marketing/behavior-discounts/campaigns/${campaign._id}`, formData);
      } else {
        await api.post("/marketing/behavior-discounts/campaigns", formData);
      }
      onSave();
    } catch (error) {
      console.error("Failed to save campaign:", error);
      alert("Failed to save campaign");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <div className="p-6 border-b border-slate-200">
            <h2 className="text-2xl font-bold text-slate-900">
              {campaign ? "Edit Campaign" : "Create Campaign"}
            </h2>
          </div>

          <div className="p-6 space-y-4">
            {/* Campaign Name */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Campaign Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Cart Recovery 15% Off"
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>

            {/* Trigger Event */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Trigger Event</label>
              <select
                value={formData.trigger_event}
                onChange={(e) => setFormData({ ...formData, trigger_event: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {TRIGGER_EVENTS.map((event) => (
                  <option key={event.value} value={event.value}>
                    {event.label} - {event.description}
                  </option>
                ))}
              </select>
            </div>

            {/* Discount Type & Value */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Discount Type</label>
                <select
                  value={formData.discount_type}
                  onChange={(e) => setFormData({ ...formData, discount_type: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="percentage">Percentage Off</option>
                  <option value="fixed_amount">Fixed Amount Off</option>
                  <option value="free_shipping">Free Shipping</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  {formData.discount_type === "percentage" ? "Percentage (%)" : "Amount ($)"}
                </label>
                <input
                  type="number"
                  value={formData.discount_value}
                  onChange={(e) => setFormData({ ...formData, discount_value: parseFloat(e.target.value) })}
                  min="0"
                  step={formData.discount_type === "percentage" ? "1" : "0.01"}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
            </div>

            {/* Delivery Method */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Delivery Method</label>
              <select
                value={formData.delivery_method}
                onChange={(e) => setFormData({ ...formData, delivery_method: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {DELIVERY_METHODS.map((method) => (
                  <option key={method.value} value={method.value}>
                    {method.label} - {method.description}
                  </option>
                ))}
              </select>
            </div>

            {/* Message Template */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Message Template</label>
              <textarea
                value={formData.message_template}
                onChange={(e) => setFormData({ ...formData, message_template: e.target.value })}
                rows={3}
                placeholder="Use {discount_code}, {discount_value}, {discount_type}"
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
              <p className="text-xs text-slate-500 mt-1">
                Variables: {"{discount_code}"}, {"{discount_value}"}, {"{discount_type}"}
              </p>
            </div>
          </div>

          <div className="p-6 border-t border-slate-200 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {saving ? "Saving..." : campaign ? "Update Campaign" : "Create Campaign"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
