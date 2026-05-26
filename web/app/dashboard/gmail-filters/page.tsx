"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

interface Filter {
  id: string;
  criteria: {
    from?: string;
    subject?: string;
    query?: string;
  };
  action: {
    addLabelIds?: string[];
    removeLabelIds?: string[];
  };
  type: string;
  created_at: string;
}

interface Suggestion {
  sender: string;
  count: number;
  sample_subjects: string[];
  suggested_action: string;
  reason: string;
  read_rate: number;
}

export default function GmailFiltersPage() {
  const router = useRouter();
  const [filters, setFilters] = useState<Filter[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"filters" | "suggestions" | "quick-setup">("filters");
  const [newFilterSender, setNewFilterSender] = useState("");
  const [customSenders, setCustomSenders] = useState<string[]>([]);
  const [newCustomSender, setNewCustomSender] = useState("");

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const userId = typeof window !== "undefined" ? localStorage.getItem("user_id") : null;

  useEffect(() => {
    if (userId) {
      loadFilters();
      if (activeTab === "suggestions") {
        loadSuggestions();
      }
    }
  }, [userId, activeTab]);

  const loadFilters = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/gmail/filters/my-filters?user_id=${userId}`);
      const data = await res.json();
      if (data.success) {
        setFilters(data.filters || []);
      }
    } catch (error) {
      console.error("Failed to load filters:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadSuggestions = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/gmail/filters/suggestions?user_id=${userId}&min_count=3`);
      const data = await res.json();
      if (data.success) {
        setSuggestions(data.suggestions || []);
      }
    } catch (error) {
      console.error("Failed to load suggestions:", error);
    }
  };

  const createArchiveFilter = async (sender: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/gmail/filters/archive-sender`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          sender: sender,
          also_mark_read: false,
        }),
      });
      const data = await res.json();
      if (data.success) {
        alert(`✓ Filter created for ${sender}`);
        loadFilters();
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (error) {
      alert(`Failed to create filter: ${error}`);
    }
  };

  const deleteFilter = async (filterId: string) => {
    if (!confirm("Are you sure you want to delete this filter?")) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/gmail/filters/delete/${filterId}?user_id=${userId}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (data.success) {
        alert("✓ Filter deleted");
        loadFilters();
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (error) {
      alert(`Failed to delete filter: ${error}`);
    }
  };

  const setupNewsletterFilters = async () => {
    if (!confirm("This will create filters for 8+ common newsletter senders. Continue?")) return;
    
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/gmail/filters/batch/newsletters`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          custom_senders: customSenders,
        }),
      });
      const data = await res.json();
      if (data.success) {
        alert(`✓ Created ${data.created} filters! ${data.failed > 0 ? `(${data.failed} failed)` : ""}`);
        loadFilters();
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (error) {
      alert(`Failed to setup filters: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const addCustomSender = () => {
    if (newCustomSender && !customSenders.includes(newCustomSender)) {
      setCustomSenders([...customSenders, newCustomSender]);
      setNewCustomSender("");
    }
  };

  const removeCustomSender = (sender: string) => {
    setCustomSenders(customSenders.filter(s => s !== sender));
  };

  if (!userId) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">Please log in</h2>
          <button
            onClick={() => router.push("/login")}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Go to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Gmail Filter Manager</h1>
          <p className="text-gray-600">
            Automate your inbox with intelligent filters. Archive newsletters, mark important senders, and more.
          </p>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-lg shadow-sm mb-6">
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              <button
                onClick={() => setActiveTab("filters")}
                className={`px-6 py-3 text-sm font-medium border-b-2 ${
                  activeTab === "filters"
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                My Filters ({filters.length})
              </button>
              <button
                onClick={() => setActiveTab("suggestions")}
                className={`px-6 py-3 text-sm font-medium border-b-2 ${
                  activeTab === "suggestions"
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                Suggestions
              </button>
              <button
                onClick={() => setActiveTab("quick-setup")}
                className={`px-6 py-3 text-sm font-medium border-b-2 ${
                  activeTab === "quick-setup"
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                Quick Setup
              </button>
            </nav>
          </div>

          <div className="p-6">
            {/* My Filters Tab */}
            {activeTab === "filters" && (
              <div>
                <div className="mb-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Create New Filter</h3>
                  <div className="flex gap-3">
                    <input
                      type="email"
                      placeholder="sender@example.com"
                      value={newFilterSender}
                      onChange={(e) => setNewFilterSender(e.target.value)}
                      className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                    <button
                      onClick={() => {
                        if (newFilterSender) {
                          createArchiveFilter(newFilterSender);
                          setNewFilterSender("");
                        }
                      }}
                      className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
                    >
                      Archive Sender
                    </button>
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Active Filters</h3>
                  {loading ? (
                    <div className="text-center py-8 text-gray-500">Loading...</div>
                  ) : filters.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      No filters yet. Create one above or try Quick Setup!
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {filters.map((filter) => (
                        <div
                          key={filter.id}
                          className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200"
                        >
                          <div className="flex-1">
                            <div className="font-medium text-gray-900">
                              {filter.criteria.from && `From: ${filter.criteria.from}`}
                              {filter.criteria.subject && `Subject: ${filter.criteria.subject}`}
                              {filter.criteria.query && `Query: ${filter.criteria.query}`}
                            </div>
                            <div className="text-sm text-gray-500 mt-1">
                              Action: {filter.action.removeLabelIds?.includes("INBOX") && "Archive"}
                              {filter.action.addLabelIds?.includes("IMPORTANT") && "Mark Important"}
                            </div>
                            <div className="text-xs text-gray-400 mt-1">
                              Type: {filter.type} • Created: {new Date(filter.created_at).toLocaleDateString()}
                            </div>
                          </div>
                          <button
                            onClick={() => deleteFilter(filter.id)}
                            className="ml-4 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg font-medium"
                          >
                            Delete
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Suggestions Tab */}
            {activeTab === "suggestions" && (
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-3">AI-Powered Suggestions</h3>
                <p className="text-gray-600 mb-6">
                  Based on your inbox patterns, we recommend creating filters for these senders:
                </p>
                
                {suggestions.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    No suggestions available. Your inbox looks clean!
                  </div>
                ) : (
                  <div className="space-y-4">
                    {suggestions.map((sugg, idx) => (
                      <div
                        key={idx}
                        className="p-4 bg-white border border-gray-200 rounded-lg hover:border-blue-300 transition"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="font-medium text-gray-900">{sugg.sender}</div>
                            <div className="text-sm text-gray-600 mt-1">
                              {sugg.count} emails • {Math.round(sugg.read_rate * 100)}% read rate
                            </div>
                            <div className="text-sm text-blue-600 mt-1">{sugg.reason}</div>
                            <div className="text-xs text-gray-500 mt-2">
                              Sample: {sugg.sample_subjects[0]}
                            </div>
                          </div>
                          <button
                            onClick={() => createArchiveFilter(sugg.sender)}
                            className="ml-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
                          >
                            Create Filter
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Quick Setup Tab */}
            {activeTab === "quick-setup" && (
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-3">Quick Newsletter Setup</h3>
                <p className="text-gray-600 mb-6">
                  Automatically create filters for common newsletter senders. This will archive emails from:
                </p>
                
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                  <h4 className="font-medium text-blue-900 mb-2">Included Senders:</h4>
                  <ul className="text-sm text-blue-800 space-y-1">
                    <li>• customerservice@exct.stansberryresearch.com</li>
                    <li>• info@exct.chaikinanalytics.com</li>
                    <li>• stocknewsletter@mail.beehiiv.com</li>
                    <li>• info@analyticsindiamag.com</li>
                    <li>• newsletters@analystratings.net</li>
                    <li>• partners@analystratings.net</li>
                    <li>• newsmax@latest.newsmax.com</li>
                    <li>• team@cmail.bark.com</li>
                    <li>• Plus: Any email with "unsubscribe" (catch-all)</li>
                  </ul>
                </div>

                <div className="mb-6">
                  <h4 className="font-medium text-gray-900 mb-3">Add Custom Senders (Optional)</h4>
                  <div className="flex gap-3 mb-3">
                    <input
                      type="email"
                      placeholder="additional@newsletter.com"
                      value={newCustomSender}
                      onChange={(e) => setNewCustomSender(e.target.value)}
                      className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                    <button
                      onClick={addCustomSender}
                      className="px-6 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 font-medium"
                    >
                      Add
                    </button>
                  </div>
                  
                  {customSenders.length > 0 && (
                    <div className="space-y-2">
                      {customSenders.map((sender, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                          <span className="text-sm text-gray-700">{sender}</span>
                          <button
                            onClick={() => removeCustomSender(sender)}
                            className="text-red-600 hover:text-red-800 text-sm"
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <button
                  onClick={setupNewsletterFilters}
                  disabled={loading}
                  className="w-full px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium disabled:bg-gray-400"
                >
                  {loading ? "Setting up..." : "Create All Filters"}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Info Box */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h4 className="font-medium text-blue-900 mb-2">💡 Pro Tips</h4>
          <ul className="text-sm text-blue-800 space-y-1">
            <li>• Filters apply to future emails only (not retroactive)</li>
            <li>• "Archive" means skip inbox but keep in All Mail</li>
            <li>• You can have up to 1,000 filters per Gmail account</li>
            <li>• Check the Suggestions tab for AI-powered recommendations</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
