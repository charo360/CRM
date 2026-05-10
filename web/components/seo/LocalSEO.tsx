import React, { useState, useEffect } from "react";

interface LocalListing {
  platform: "google-business" | "yelp" | "apple-maps" | "bing-places";
  name: string;
  address: string;
  phone: string;
  website: string;
  rating?: number;
  reviews?: number;
  status: "verified" | "pending" | "not-listed";
  lastUpdated?: string;
}

interface LocalKeyword {
  keyword: string;
  location: string;
  position: number;
  searchVolume: number;
  difficulty: "low" | "medium" | "high";
  trend: "up" | "down" | "stable";
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
  const [showAddListing, setShowAddListing] = useState(false);
  const [newListing, setNewListing] = useState({
    platform: "google-business" as const,
    name: "",
    address: "",
    phone: "",
    website: ""
  });

  useEffect(() => {
    const fetchLocalSEOData = async () => {
      try {
        const [listingsRes, keywordsRes, competitorsRes, scoreRes] = await Promise.all([
          fetch('/api/seo/local/listings'),
          fetch('/api/seo/local/keywords'),
          fetch('/api/seo/local/competitors'),
          fetch('/api/seo/local/score')
        ]);

        if (listingsRes.ok) {
          const listingsData = await listingsRes.json();
          setListings(listingsData.listings || []);
        }

        if (keywordsRes.ok) {
          const keywordsData = await keywordsRes.json();
          setLocalKeywords(keywordsData.keywords || []);
        }

        if (competitorsRes.ok) {
          const competitorsData = await competitorsRes.json();
          setCompetitors(competitorsData.competitors || []);
        }

        if (scoreRes.ok) {
          const scoreData = await scoreRes.json();
          setLocalScore(scoreData);
        }
      } catch (error) {
        console.error('Error fetching local SEO data:', error);
        // Fallback to mock data if API fails
        setListings([
          {
            platform: "google-business",
            name: "ABC Plumbing Services",
            address: "123 Main St, City, State 12345",
            phone: "(555) 123-4567",
            website: "https://abcplumbing.com",
            rating: 4.8,
            reviews: 127,
            status: "verified",
            lastUpdated: "2024-01-15"
          }
        ]);
        setLocalKeywords([
          {
            keyword: "plumber near me",
            location: "City, State",
            position: 3,
            searchVolume: 2400,
            difficulty: "high",
            trend: "up"
          }
        ]);
        setCompetitors([
          {
            name: "XYZ Plumbing",
            address: "456 Oak Ave, City, State 12345",
            rating: 4.5,
            reviews: 203,
            categories: ["Plumbing", "Emergency Services"]
          }
        ]);
        setLocalScore({
          overall: 78,
          grade: "Good",
          breakdown: {
            business_listings: 85,
            reviews_ratings: 72,
            local_rankings: 68,
            citations: 90
          },
          recommendations: [
            "Add your business to Apple Maps to increase visibility",
            "Encourage more customer reviews to improve ratings",
            "Target 'emergency plumber City' keyword - currently ranking #2"
          ]
        });
      } finally {
        setLoading(false);
      }
    };

    fetchLocalSEOData();
  }, []);

  const handleAddListing = async () => {
    try {
      const response = await fetch('/api/seo/local/listings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newListing),
      });

      if (response.ok) {
        const result = await response.json();
        setListings(prev => [...prev, result.listing]);
        setShowAddListing(false);
        setNewListing({
          platform: "google-business",
          name: "",
          address: "",
          phone: "",
          website: ""
        });
      } else {
        console.error('Failed to add listing');
        // Fallback to local state update
        const listing: LocalListing = {
          ...newListing,
          status: "pending",
          lastUpdated: new Date().toISOString()
        };
        setListings(prev => [...prev, listing]);
        setShowAddListing(false);
        setNewListing({
          platform: "google-business",
          name: "",
          address: "",
          phone: "",
          website: ""
        });
      }
    } catch (error) {
      console.error('Error adding listing:', error);
      // Fallback to local state update
      const listing: LocalListing = {
        ...newListing,
        status: "pending",
        lastUpdated: new Date().toISOString()
      };
      setListings(prev => [...prev, listing]);
      setShowAddListing(false);
      setNewListing({
        platform: "google-business",
        name: "",
        address: "",
        phone: "",
        website: ""
      });
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

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case "up": return "↑";
      case "down": return "↓";
      default: return "→";
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
                  <button className="px-3 py-1.5 bg-blue-100 text-blue-700 text-xs rounded-lg hover:bg-blue-200 font-medium">
                    Edit
                  </button>
                  <button className="px-3 py-1.5 bg-slate-100 text-slate-700 text-xs rounded-lg hover:bg-slate-200 font-medium">
                    Sync
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Local Keyword Rankings */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Local Keyword Rankings</h3>
        
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="text-left py-3 px-2 font-medium text-slate-700">Keyword</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Location</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Position</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Search Volume</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Difficulty</th>
                <th className="text-center py-3 px-2 font-medium text-slate-700">Trend</th>
              </tr>
            </thead>
            <tbody>
              {localKeywords.map((keyword, index) => (
                <tr key={index} className="border-b border-slate-50 hover:bg-slate-50">
                  <td className="py-3 px-2">
                    <span className="font-medium text-slate-800">{keyword.keyword}</span>
                  </td>
                  <td className="text-center py-3">
                    <span className="text-sm text-slate-600">{keyword.location}</span>
                  </td>
                  <td className="text-center py-3">
                    <div className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold ${
                      keyword.position <= 3 ? "bg-green-100 text-green-700" :
                      keyword.position <= 10 ? "bg-yellow-100 text-yellow-700" :
                      "bg-red-100 text-red-700"
                    }`}>
                      #{keyword.position}
                    </div>
                  </td>
                  <td className="text-center py-3">
                    <span className="font-medium text-slate-800">{keyword.searchVolume.toLocaleString()}</span>
                  </td>
                  <td className="text-center py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${getDifficultyColor(keyword.difficulty)}`}>
                      {keyword.difficulty}
                    </span>
                  </td>
                  <td className="text-center py-3">
                    <span className={`font-medium ${
                      keyword.trend === "up" ? "text-green-600" :
                      keyword.trend === "down" ? "text-red-600" :
                      "text-slate-500"
                    }`}>
                      {getTrendIcon(keyword.trend)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
    </div>
  );
}
