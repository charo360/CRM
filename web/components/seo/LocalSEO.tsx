import React, { useState, useEffect, useCallback } from "react";
import { seoApi } from "@/lib/api";

interface LocalListing {
  id: string;
  platform: string;
  name: string;
  address: string;
  phone: string;
  website: string;
  rating?: number;
  reviews?: number;
  status: "verified" | "pending" | "not-listed";
  created_at?: string;
  updated_at?: string;
  lastUpdated?: string;
}

interface LocalKeyword {
  keyword: string;
  location: string;
  position: number | null;
  search_volume?: number;
  searchVolume?: number;
  difficulty: "low" | "medium" | "high";
  trend: "up" | "down" | "stable" | "new" | "untracked";
  volume_trend?: "up" | "down" | "stable" | null;
  content_idea?: string;
  article_url?: string | null;
  article_title?: string | null;
}

interface CompetitorListing {
  name: string;
  address: string;
  rating: number;
  reviews: number;
  categories: string[];
}

export default function LocalSEO() {
  const [listings, setListings] = useState<LocalListing[]>([]);
  const [localKeywords, setLocalKeywords] = useState<LocalKeyword[]>([]);
  const [competitors, setCompetitors] = useState<CompetitorListing[]>([]);
  const [localScore, setLocalScore] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState("");
  const [showAddListing, setShowAddListing] = useState(false);
  const [newListing, setNewListing] = useState({
    platform: "google-business" as const,
    name: "",
    address: "",
    phone: "",
    website: ""
  });
  const [editingListing, setEditingListing] = useState<LocalListing | null>(null);
  const [editForm, setEditForm] = useState<Partial<LocalListing>>({});
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [trackingKeyword, setTrackingKeyword] = useState<string | null>(null);
  const [trackDomain, setTrackDomain] = useState("");
  const [showTrackModal, setShowTrackModal] = useState(false);
  const [trackingInProgress, setTrackingInProgress] = useState<string | null>(null);
  const [trackResult, setTrackResult] = useState<{ position: number | null; error?: string } | null>(null);
  const [keywordsSource, setKeywordsSource] = useState<string>("");
  const [trackArticleUrl, setTrackArticleUrl] = useState("");
  const [trackArticleTitle, setTrackArticleTitle] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadErr("");
      try {
        const [listingsData, keywordsData, competitorsData, scoreData, ctxData] = await Promise.all([
          seoApi.getLocalListings(),
          seoApi.getLocalKeywords(),
          seoApi.getLocalCompetitors(),
          seoApi.getLocalScore(),
          seoApi.businessContext().catch(() => null),
        ]);
        if (cancelled) return;
        setListings((listingsData.listings || []) as unknown as LocalListing[]);
        setLocalKeywords((keywordsData.keywords || []) as unknown as LocalKeyword[]);
        setKeywordsSource((keywordsData as Record<string, unknown>).source as string || "");
        setCompetitors((competitorsData.competitors || []) as unknown as CompetitorListing[]);
        setLocalScore(scoreData);
        if (ctxData?.website_url) {
          const raw = ctxData.website_url.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];
          setWebsiteUrl(raw);
          setTrackDomain(raw);
        }
      } catch (error) {
        console.error("Error fetching local SEO data:", error);
        if (!cancelled) {
          setLoadErr("Could not load Local SEO data. Sign in and ensure the CRM backend is running (same API as Keywords).");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleAddListing = async () => {
    try {
      const result = await seoApi.addLocalListing(newListing);
      const stored = result.listing as Record<string, unknown>;
      const listing: LocalListing = {
        platform: stored.platform === "yelp" || stored.platform === "apple-maps" || stored.platform === "bing-places"
          ? stored.platform
          : "google-business",
        name: String(stored.name ?? newListing.name),
        address: String(stored.address ?? newListing.address),
        phone: String(stored.phone ?? newListing.phone),
        website: String(stored.website ?? newListing.website),
        status:
          stored.status === "verified" || stored.status === "not-listed" ? stored.status : "pending",
        lastUpdated:
          typeof stored.updated_at === "string"
            ? stored.updated_at
            : typeof stored.created_at === "string"
              ? stored.created_at
              : new Date().toISOString(),
      };
      setListings(prev => [...prev, listing]);
      setShowAddListing(false);
      setNewListing({
        platform: "google-business",
        name: "",
        address: "",
        phone: "",
        website: "",
      });
    } catch (error) {
      console.error("Error adding listing:", error);
      const listing: LocalListing = {
        ...newListing,
        status: "pending",
        lastUpdated: new Date().toISOString(),
      };
      setListings(prev => [...prev, listing]);
      setShowAddListing(false);
      setNewListing({
        platform: "google-business",
        name: "",
        address: "",
        phone: "",
        website: "",
      });
    }
  };

  const openTrackModal = (keyword: string) => {
    const kw = localKeywords.find(k => k.keyword === keyword);
    setTrackingKeyword(keyword);
    setTrackDomain(websiteUrl || "");
    setTrackArticleUrl(kw?.article_url || "");
    setTrackArticleTitle(kw?.article_title || "");
    setTrackResult(null);
    setShowTrackModal(true);
  };

  const closeTrackModal = () => {
    setShowTrackModal(false);
    setTrackResult(null);
    setTrackingKeyword(null);
    setTrackArticleUrl("");
    setTrackArticleTitle("");
  };

  const handleTrackKeyword = async () => {
    if (!trackingKeyword || !trackDomain.trim()) return;
    const domain = trackDomain.trim().replace(/^https?:\/\/(www\.)?/, "").split("/")[0];
    const articleUrl = trackArticleUrl.trim() || undefined;
    const articleTitle = trackArticleTitle.trim() || undefined;
    setTrackingInProgress(trackingKeyword);
    setTrackResult(null);
    try {
      const result = await seoApi.checkRanking(trackingKeyword, domain, undefined, articleUrl, articleTitle);
      const pos = result.position ?? null;
      setTrackResult({ position: pos });
      setLocalKeywords(prev => prev.map(k =>
        k.keyword === trackingKeyword
          ? { ...k, position: pos, trend: pos != null ? "new" : "untracked", article_url: articleUrl ?? k.article_url, article_title: articleTitle ?? k.article_title }
          : k
      ));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to check ranking. Is the backend running?";
      setTrackResult({ position: null, error: msg });
    } finally {
      setTrackingInProgress(null);
    }
  };

  const handleUpdateListing = async () => {
    if (!editingListing?.id) return;
    try {
      await seoApi.updateLocalListing(editingListing.id, editForm);
      setListings(prev => prev.map(l => l.id === editingListing.id ? { ...l, ...editForm } : l));
    } catch (e) {
      console.error("Error updating listing:", e);
    } finally {
      setEditingListing(null);
      setEditForm({});
    }
  };

  const handleDeleteListing = async (listing: LocalListing) => {
    if (!listing.id) return;
    setDeletingId(listing.id);
    try {
      await seoApi.deleteLocalListing(listing.id);
      setListings(prev => prev.filter(l => l.id !== listing.id));
    } catch (e) {
      console.error("Error deleting listing:", e);
    } finally {
      setDeletingId(null);
    }
  };

  const getPlatformIcon = (platform: string) => {
    switch (platform) {
      case "google-business": return "🗺️";
      case "yelp": return "⭐";
      case "apple-maps": return "🍎";
      case "bing-places": return "🔍";
      default: return "📍";
    }
  };

  const getPlatformName = (platform: string) => {
    switch (platform) {
      case "google-business": return "Google Business Profile";
      case "yelp": return "Yelp";
      case "apple-maps": return "Apple Maps";
      case "bing-places": return "Bing Places";
      default: return platform;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "verified": return "bg-green-100 text-green-700";
      case "pending": return "bg-yellow-100 text-yellow-700";
      default: return "bg-slate-100 text-slate-600";
    }
  };

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty) {
      case "low": return "bg-green-100 text-green-700";
      case "medium": return "bg-yellow-100 text-yellow-700";
      case "high": return "bg-red-100 text-red-700";
      default: return "bg-slate-100 text-slate-600";
    }
  };

  const getTrendBadge = (trend: string, volumeTrend?: string | null) => {
    // trend = position trend (from SERP history); volumeTrend = search volume trend from DataForSEO
    switch (trend) {
      case "up":
        return <span className="inline-flex items-center gap-1 text-green-700 font-semibold text-xs" title="Position improving — your ranking moved up since last check">↑ Rising</span>;
      case "down":
        return <span className="inline-flex items-center gap-1 text-red-600 font-semibold text-xs" title="Position dropped since last check">↓ Falling</span>;
      case "stable":
        return <span className="inline-flex items-center gap-1 text-slate-500 text-xs" title="Position unchanged since last check">→ Stable</span>;
      case "new":
        return (
          <span className="inline-flex items-center gap-1 text-xs" title="Position just tracked for the first time">
            <span className="bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">New</span>
            {volumeTrend === "up" && <span className="text-green-600" title="Search volume rising">▲</span>}
            {volumeTrend === "down" && <span className="text-red-500" title="Search volume declining">▼</span>}
          </span>
        );
      case "untracked":
        return (
          <span className="inline-flex items-center gap-1 text-xs text-slate-400" title="Not yet tracked — click Track to check this keyword's ranking">
            <span>–</span>
            {volumeTrend === "up" && <span className="text-green-600 font-semibold" title="Search volume is rising — good keyword to target">▲ vol</span>}
            {volumeTrend === "down" && <span className="text-red-400" title="Search volume declining">▼ vol</span>}
          </span>
        );
      default:
        return <span className="text-slate-400 text-xs">–</span>;
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
          <h2 className="text-xl font-bold text-slate-800">Local SEO</h2>
          <p className="text-sm text-slate-500 mt-1">Manage your local business listings and track local rankings</p>
        </div>
        <button
          onClick={() => setShowAddListing(true)}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-medium"
        >
          Add Listing
        </button>
      </div>

      {loadErr && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {loadErr}
        </div>
      )}

      {/* Local Listings */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Business Listings</h3>
        
        <div className="space-y-4">
          {listings.map((listing, index) => (
            <div key={index} className="border border-slate-100 rounded-lg p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-lg">{getPlatformIcon(listing.platform)}</span>
                    <h4 className="font-medium text-slate-800">{listing.name}</h4>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${getStatusColor(listing.status)}`}>
                      {listing.status === "verified" ? "Verified" : 
                       listing.status === "pending" ? "Pending" : "Not Listed"}
                    </span>
                  </div>
                  
                  <div className="space-y-1 text-sm text-slate-600">
                    <p>📍 {listing.address}</p>
                    <p>📞 {listing.phone}</p>
                    <p>🌐 {listing.website}</p>
                  </div>

                  {listing.rating && (
                    <div className="flex items-center gap-3 mt-3">
                      <div className="flex items-center gap-1">
                        <span className="text-yellow-500">⭐</span>
                        <span className="font-medium text-slate-800">{listing.rating}</span>
                        <span className="text-sm text-slate-500">({listing.reviews} reviews)</span>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex gap-2 ml-4">
                  <button
                    onClick={() => { setEditingListing(listing); setEditForm({ name: listing.name, address: listing.address, phone: listing.phone, website: listing.website, status: listing.status, rating: listing.rating, reviews: listing.reviews }); }}
                    className="px-3 py-1.5 bg-blue-100 text-blue-700 text-xs rounded-lg hover:bg-blue-200 font-medium"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeleteListing(listing)}
                    disabled={deletingId === listing.id}
                    className="px-3 py-1.5 bg-red-50 text-red-600 text-xs rounded-lg hover:bg-red-100 font-medium disabled:opacity-50"
                  >
                    {deletingId === listing.id ? "…" : "Delete"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Local Keyword Rankings */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-800">Keyword Opportunities</h3>
            <p className="text-xs text-slate-500 mt-0.5">Keywords people in your industry actually search for — sorted by monthly volume</p>
          </div>
          {keywordsSource === "dataforseo_seeds" && (
            <span className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-1 rounded-full font-medium">
              Real search data
            </span>
          )}
        </div>
        
        <div className="space-y-3">
          {localKeywords.map((keyword, index) => {
            const vol = keyword.search_volume ?? keyword.searchVolume ?? null;
            const hasArticle = !!keyword.article_url;
            return (
              <div key={index} className="border border-slate-200 rounded-xl overflow-hidden">
                {/* Keyword row */}
                <div className="flex items-center justify-between px-4 py-3 bg-white">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-semibold text-slate-800 text-sm">{keyword.keyword}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${getDifficultyColor(keyword.difficulty)}`}>
                      {keyword.difficulty}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                    {vol != null && vol > 0 ? (
                      <span className="text-sm font-bold text-slate-800">
                        {vol >= 1000 ? `${(vol / 1000).toFixed(vol >= 10000 ? 0 : 1)}k` : vol.toLocaleString()}
                        <span className="text-xs font-normal text-slate-400">/mo</span>
                        {keyword.volume_trend === "up" && <span className="ml-1 text-green-500 text-xs" title="Search volume rising">▲</span>}
                        {keyword.volume_trend === "down" && <span className="ml-1 text-red-400 text-xs" title="Search volume declining">▼</span>}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400 italic">no data</span>
                    )}
                  </div>
                </div>

                {/* Article row */}
                <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 border-t border-slate-100">
                  <div className="flex items-center gap-2 min-w-0">
                    {hasArticle ? (
                      <>
                        <span className="text-slate-400 text-xs">📄</span>
                        <span className="text-xs text-slate-600 truncate max-w-[240px]" title={keyword.article_url || ""}>
                          {keyword.article_title || keyword.article_url}
                        </span>
                        {keyword.position != null ? (
                          <span className={`inline-flex items-center text-xs font-bold px-2 py-0.5 rounded-full flex-shrink-0 ${
                            keyword.position <= 3 ? "bg-green-100 text-green-700" :
                            keyword.position <= 10 ? "bg-yellow-100 text-yellow-700" :
                            "bg-red-100 text-red-700"
                          }`}>
                            #{keyword.position}
                            {keyword.trend === "up" && <span className="ml-0.5">↑</span>}
                            {keyword.trend === "down" && <span className="ml-0.5">↓</span>}
                          </span>
                        ) : (
                          <span className="text-xs text-slate-400 italic">not ranked yet</span>
                        )}
                      </>
                    ) : (
                      <span className="text-xs text-slate-400 italic">No article linked yet</span>
                    )}
                  </div>
                  <div className="flex-shrink-0 ml-2">
                    {trackingInProgress === keyword.keyword ? (
                      <span className="text-xs text-slate-400 italic">Checking…</span>
                    ) : (
                      <button
                        onClick={() => openTrackModal(keyword.keyword)}
                        className={`px-3 py-1 text-xs rounded-lg font-medium transition ${
                          hasArticle
                            ? "bg-slate-200 text-slate-600 hover:bg-slate-300"
                            : "bg-blue-600 text-white hover:bg-blue-700"
                        }`}
                      >
                        {hasArticle ? "Update" : "Link Article"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Local Competitors */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Local Competitors</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {competitors.map((competitor, index) => (
            <div key={index} className="border border-slate-100 rounded-lg p-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h4 className="font-medium text-slate-800">{competitor.name}</h4>
                  <p className="text-sm text-slate-600">{competitor.address}</p>
                </div>
                <div className="text-right">
                  <div className="flex items-center gap-1">
                    <span className="text-yellow-500">⭐</span>
                    <span className="font-medium text-slate-800">{competitor.rating}</span>
                  </div>
                  <p className="text-xs text-slate-500">{competitor.reviews} reviews</p>
                </div>
              </div>
              
              <div className="flex flex-wrap gap-1">
                {competitor.categories.map((category, i) => (
                  <span key={i} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                    {category}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Local SEO Score */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Local SEO Score</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Overall Score */}
          <div className="text-center">
            <div className="inline-flex items-center justify-center w-32 h-32 rounded-full border-8 border-emerald-100 mb-4">
              <div>
                <div className="text-3xl font-bold text-emerald-600">{localScore?.overall || 78}</div>
                <div className="text-sm text-emerald-600">{localScore?.grade || "Good"}</div>
              </div>
            </div>
            <p className="text-sm text-slate-600">
              {localScore?.overall >= 80 ? "Your local SEO is performing excellently" :
               localScore?.overall >= 60 ? "Your local SEO is performing well" :
               "Your local SEO needs improvement"}
            </p>
          </div>

          {/* Score Breakdown */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-600">Business Listings</span>
              <div className="flex items-center gap-2">
                <div className="w-24 bg-slate-100 rounded-full h-2">
                  <div className="bg-green-500 h-2 rounded-full" style={{ width: `${localScore?.breakdown?.business_listings || 85}%` }} />
                </div>
                <span className="text-sm font-medium text-slate-800">{localScore?.breakdown?.business_listings || 85}%</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-600">Reviews & Ratings</span>
              <div className="flex items-center gap-2">
                <div className="w-24 bg-slate-100 rounded-full h-2">
                  <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${localScore?.breakdown?.reviews_ratings || 72}%` }} />
                </div>
                <span className="text-sm font-medium text-slate-800">{localScore?.breakdown?.reviews_ratings || 72}%</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-600">Local Rankings</span>
              <div className="flex items-center gap-2">
                <div className="w-24 bg-slate-100 rounded-full h-2">
                  <div className="bg-yellow-500 h-2 rounded-full" style={{ width: `${localScore?.breakdown?.local_rankings || 68}%` }} />
                </div>
                <span className="text-sm font-medium text-slate-800">{localScore?.breakdown?.local_rankings || 68}%</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-600">Citations</span>
              <div className="flex items-center gap-2">
                <div className="w-24 bg-slate-100 rounded-full h-2">
                  <div className="bg-purple-500 h-2 rounded-full" style={{ width: `${localScore?.breakdown?.citations || 90}%` }} />
                </div>
                <span className="text-sm font-medium text-slate-800">{localScore?.breakdown?.citations || 90}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Recommendations */}
        <div className="mt-6 p-4 bg-blue-50 border border-blue-100 rounded-lg">
          <h4 className="text-sm font-semibold text-blue-800 mb-2">Recommendations</h4>
          <ul className="text-sm text-blue-700 space-y-1">
            {(localScore?.recommendations || [
              "Add your business to Apple Maps to increase visibility",
              "Encourage more customer reviews to improve ratings",
              "Target local keyword opportunities in your area"
            ]).map((rec: string, index: number) => (
              <li key={index} className="flex items-start gap-2">
                <span className="text-blue-500 mt-0.5">•</span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Add Listing Modal */}
      {showAddListing && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-800">Add Business Listing</h3>
              <button
                onClick={() => setShowAddListing(false)}
                className="text-slate-400 hover:text-slate-600 text-xl"
              >
                ×
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Platform</label>
                <select
                  value={newListing.platform}
                  onChange={(e) => setNewListing({...newListing, platform: e.target.value as any})}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="google-business">Google Business Profile</option>
                  <option value="yelp">Yelp</option>
                  <option value="apple-maps">Apple Maps</option>
                  <option value="bing-places">Bing Places</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Business Name</label>
                <input
                  type="text"
                  value={newListing.name}
                  onChange={(e) => setNewListing({...newListing, name: e.target.value})}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Your business name"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Address</label>
                <input
                  type="text"
                  value={newListing.address}
                  onChange={(e) => setNewListing({...newListing, address: e.target.value})}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="123 Main St, City, State 12345"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Phone</label>
                <input
                  type="tel"
                  value={newListing.phone}
                  onChange={(e) => setNewListing({...newListing, phone: e.target.value})}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="(555) 123-4567"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Website</label>
                <input
                  type="url"
                  value={newListing.website}
                  onChange={(e) => setNewListing({...newListing, website: e.target.value})}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="https://yourwebsite.com"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  onClick={handleAddListing}
                  disabled={!newListing.name || !newListing.address}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                >
                  Add Listing
                </button>
                <button
                  onClick={() => setShowAddListing(false)}
                  className="flex-1 px-4 py-2 bg-slate-100 text-slate-700 text-sm rounded-lg hover:bg-slate-200 font-medium"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Link Article + Track Modal */}
      {showTrackModal && trackingKeyword && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-base font-semibold text-slate-800">Link Article & Check Ranking</h3>
              <button onClick={closeTrackModal} className="text-slate-400 hover:text-slate-600 text-xl">×</button>
            </div>
            <p className="text-sm font-medium text-blue-700 mb-1 truncate">"{trackingKeyword}"</p>
            <p className="text-xs text-slate-400 mb-4">Link the article you wrote for this keyword, then check its Google ranking.</p>

            {/* Result feedback */}
            {trackResult && !trackResult.error && (
              <div className="mb-4 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-center">
                {trackResult.position != null ? (
                  <>
                    <p className="text-2xl font-bold text-green-700">#{trackResult.position}</p>
                    <p className="text-xs text-green-600 mt-1">
                      {trackArticleUrl ? `Your article ranks #${trackResult.position} for this keyword.` : `Your site ranks #${trackResult.position} for this keyword.`}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-sm font-semibold text-slate-600">Not in top results yet</p>
                    <p className="text-xs text-slate-400 mt-1">Not found in top 20. Keep building authority — it takes time.</p>
                  </>
                )}
              </div>
            )}
            {trackResult?.error && (
              <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
                {trackResult.error}
              </div>
            )}

            {!trackResult && (
              <>
                <div className="mb-3">
                  <label className="block text-xs font-medium text-slate-700 mb-1.5">Article URL <span className="text-slate-400 font-normal">(optional)</span></label>
                  <input
                    type="text"
                    value={trackArticleUrl}
                    onChange={(e) => setTrackArticleUrl(e.target.value)}
                    placeholder="yoursite.com/blog/sick-leave-email"
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={!!trackingInProgress}
                  />
                </div>
                <div className="mb-3">
                  <label className="block text-xs font-medium text-slate-700 mb-1.5">Article title <span className="text-slate-400 font-normal">(optional)</span></label>
                  <input
                    type="text"
                    value={trackArticleTitle}
                    onChange={(e) => setTrackArticleTitle(e.target.value)}
                    placeholder="How to Write a Sick Leave Email"
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={!!trackingInProgress}
                  />
                </div>
                <div className="mb-4">
                  <label className="block text-xs font-medium text-slate-700 mb-1.5">Your website domain</label>
                  <input
                    type="text"
                    value={trackDomain}
                    onChange={(e) => setTrackDomain(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleTrackKeyword(); }}
                    placeholder="yourdomain.com"
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={!!trackingInProgress}
                  />
                  <p className="text-[11px] text-slate-400 mt-1">Without http:// or www</p>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={handleTrackKeyword}
                    disabled={!trackDomain.trim() || !!trackingInProgress}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                  >
                    {trackingInProgress === trackingKeyword ? "Checking…" : "Check Ranking"}
                  </button>
                  <button
                    onClick={closeTrackModal}
                    disabled={!!trackingInProgress}
                    className="flex-1 px-4 py-2 bg-slate-100 text-slate-700 text-sm rounded-lg hover:bg-slate-200 font-medium disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}

            {trackResult && (
              <button
                onClick={closeTrackModal}
                className="w-full mt-2 px-4 py-2 bg-slate-100 text-slate-700 text-sm rounded-lg hover:bg-slate-200 font-medium"
              >
                Close
              </button>
            )}
          </div>
        </div>
      )}

      {/* Edit Listing Modal */}
      {editingListing && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-800">Edit Listing</h3>
              <button onClick={() => setEditingListing(null)} className="text-slate-400 hover:text-slate-600 text-xl">×</button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Business Name</label>
                <input
                  type="text"
                  value={editForm.name ?? ""}
                  onChange={(e) => setEditForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Address</label>
                <input
                  type="text"
                  value={editForm.address ?? ""}
                  onChange={(e) => setEditForm(f => ({ ...f, address: e.target.value }))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Phone</label>
                <input
                  type="tel"
                  value={editForm.phone ?? ""}
                  onChange={(e) => setEditForm(f => ({ ...f, phone: e.target.value }))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Website</label>
                <input
                  type="url"
                  value={editForm.website ?? ""}
                  onChange={(e) => setEditForm(f => ({ ...f, website: e.target.value }))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Status</label>
                <select
                  value={editForm.status ?? "pending"}
                  onChange={(e) => setEditForm(f => ({ ...f, status: e.target.value as LocalListing["status"] }))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="pending">Pending</option>
                  <option value="verified">Verified</option>
                  <option value="not-listed">Not Listed</option>
                </select>
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  onClick={handleUpdateListing}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-medium"
                >
                  Save Changes
                </button>
                <button
                  onClick={() => setEditingListing(null)}
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
