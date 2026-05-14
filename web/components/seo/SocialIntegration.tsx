import React, { useState, useEffect, useCallback } from "react";
import { socialSchedulerApi, type ScheduledPost } from "@/lib/api";
import { useZernioAccounts } from "@/contexts/ZernioAccountsContext";

type Platform = "facebook" | "twitter" | "linkedin" | "instagram" | "tiktok";

interface ZernioAccount {
  id: string;
  platform: Platform;
  displayName?: string;
  username?: string;
  avatar?: string;
}

const PLATFORM_ICONS: Record<string, string> = {
  facebook: "📘",
  twitter: "𝕏",
  linkedin: "💼",
  instagram: "📷",
  tiktok: "🎵",
};

const PLATFORM_COLORS: Record<string, string> = {
  facebook: "bg-blue-100 text-blue-700 border-blue-200",
  twitter: "bg-slate-100 text-slate-700 border-slate-200",
  linkedin: "bg-indigo-100 text-indigo-700 border-indigo-200",
  instagram: "bg-pink-100 text-pink-700 border-pink-200",
  tiktok: "bg-slate-100 text-slate-800 border-slate-200",
};

const STATUS_COLORS: Record<string, string> = {
  published: "bg-green-100 text-green-700",
  scheduled: "bg-blue-100 text-blue-700",
  failed: "bg-red-100 text-red-700",
  draft: "bg-slate-100 text-slate-600",
};

const ALL_PLATFORMS: Platform[] = ["facebook", "twitter", "linkedin", "instagram"];

export default function SocialIntegration() {
  const { accounts: rawAccounts, loading: loadingAccounts, refresh: refreshAccounts, connect: zernioConnect, disconnect: zernioDisconnect } = useZernioAccounts();
  const accounts = rawAccounts.map(a => ({ ...a, platform: a.platform as Platform }));

  const [posts, setPosts] = useState<ScheduledPost[]>([]);
  const [loadingPosts, setLoadingPosts] = useState(true);
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [showCreatePost, setShowCreatePost] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deletingPost, setDeletingPost] = useState<string | null>(null);
  const [newPost, setNewPost] = useState({
    channels: [] as string[],
    content: "",
    scheduledDate: "",
    imageUrl: "",
    title: "",
  });
  const [error, setError] = useState("");

  const loadPosts = useCallback(async () => {
    setLoadingPosts(true);
    try {
      const data = await socialSchedulerApi.list();
      setPosts(data.posts || []);
    } catch {
      setPosts([]);
    } finally {
      setLoadingPosts(false);
    }
  }, []);

  useEffect(() => {
    loadPosts();
  }, [loadPosts]);

  async function handleConnect(platform: string) {
    setConnectingPlatform(platform);
    setError("");
    try {
      const redirectUrl = `${window.location.origin}/dashboard/seo?tab=social&connected=${platform}`;
      const data = await zernioConnect(platform, redirectUrl);
      if (data.authUrl) {
        const popup = window.open(data.authUrl, `connect_${platform}`, "width=600,height=700");
        const check = setInterval(() => {
          if (popup?.closed) {
            clearInterval(check);
            setConnectingPlatform(null);
            refreshAccounts();
          }
        }, 800);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to connect ${platform}`);
      setConnectingPlatform(null);
    }
  }

  async function handleDisconnect(accountId: string) {
    if (!confirm("Disconnect this account?")) return;
    setDisconnecting(accountId);
    try {
      await zernioDisconnect(accountId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to disconnect");
    } finally {
      setDisconnecting(null);
    }
  }

  async function handleCreatePost() {
    if (!newPost.content || newPost.channels.length === 0) return;
    setCreating(true);
    setError("");
    try {
      await socialSchedulerApi.create({
        title: newPost.title || newPost.content.slice(0, 60),
        body: newPost.content,
        channels: newPost.channels,
        scheduled_at: newPost.scheduledDate
          ? new Date(newPost.scheduledDate).toISOString()
          : new Date(Date.now() + 60_000).toISOString(),
        status: "scheduled",
        ...(newPost.imageUrl ? { image_url: newPost.imageUrl } : {}),
      });
      setShowCreatePost(false);
      setNewPost({ channels: [], content: "", scheduledDate: "", imageUrl: "", title: "" });
      loadPosts();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create post");
    } finally {
      setCreating(false);
    }
  }

  async function handleDeletePost(id: string) {
    if (!confirm("Delete this post?")) return;
    setDeletingPost(id);
    try {
      await socialSchedulerApi.delete(id);
      setPosts(prev => prev.filter(p => p.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete post");
    } finally {
      setDeletingPost(null);
    }
  }

  function toggleChannel(ch: string) {
    setNewPost(p => ({
      ...p,
      channels: p.channels.includes(ch) ? p.channels.filter(c => c !== ch) : [...p.channels, ch],
    }));
  }

  const connectedPlatforms = new Set(accounts.map(a => a.platform));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Social Media</h2>
          <p className="text-sm text-slate-500 mt-0.5">Auto-share blog content to your connected platforms via Zernio</p>
        </div>
        {accounts.length > 0 && (
          <button
            onClick={() => setShowCreatePost(true)}
            className="px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 font-medium"
          >
            + Create Post
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 flex items-center justify-between">
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={() => setError("")} className="text-red-400 hover:text-red-600">×</button>
        </div>
      )}

      {/* Connected Accounts */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-slate-800">Connected Accounts</h3>
          {loadingAccounts && <span className="text-xs text-slate-400">Loading…</span>}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {ALL_PLATFORMS.map((platform) => {
            const connected = accounts.filter(a => a.platform === platform);
            const isConnected = connected.length > 0;
            const isConnecting = connectingPlatform === platform;

            return (
              <div
                key={platform}
                className={`rounded-xl border p-4 flex flex-col gap-3 transition-all ${
                  isConnected
                    ? "border-green-200 bg-green-50"
                    : "border-slate-200 bg-slate-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{PLATFORM_ICONS[platform] ?? "🌐"}</span>
                    <span className={`text-sm font-semibold capitalize ${isConnected ? "text-green-800" : "text-slate-700"}`}>
                      {platform === "twitter" ? "X / Twitter" : platform}
                    </span>
                  </div>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    isConnected ? "bg-green-200 text-green-800" : "bg-slate-200 text-slate-500"
                  }`}>
                    {isConnected ? "✓ Live" : "Off"}
                  </span>
                </div>

                {isConnected ? (
                  <div className="space-y-2">
                    {connected.map(acc => (
                      <div key={acc.id} className="flex items-center justify-between gap-1">
                        <p className="text-xs text-green-700 truncate font-medium">
                          {acc.displayName || acc.username || platform}
                        </p>
                        <button
                          onClick={() => handleDisconnect(acc.id)}
                          disabled={disconnecting === acc.id}
                          className="text-[10px] text-red-500 hover:text-red-700 font-medium shrink-0 disabled:opacity-50"
                        >
                          {disconnecting === acc.id ? "…" : "Remove"}
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={() => handleConnect(platform)}
                      disabled={isConnecting}
                      className="w-full text-xs py-1 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium disabled:opacity-50"
                    >
                      {isConnecting ? "Opening…" : "+ Add account"}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => handleConnect(platform)}
                    disabled={isConnecting}
                    className="w-full py-1.5 bg-purple-600 text-white text-xs rounded-lg hover:bg-purple-700 font-medium disabled:opacity-50"
                  >
                    {isConnecting ? "Opening…" : "Connect"}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {!loadingAccounts && accounts.length === 0 && (
          <p className="text-xs text-slate-400 mt-4 text-center">
            No accounts connected yet. Click Connect to add your social platforms.
          </p>
        )}
      </div>

      {/* Scheduled / Recent Posts */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-slate-800">Scheduled Posts</h3>
          {loadingPosts && <span className="text-xs text-slate-400">Loading…</span>}
        </div>

        {!loadingPosts && posts.length === 0 && (
          <div className="text-center py-10 text-slate-400">
            <p className="text-3xl mb-2">📭</p>
            <p className="text-sm">No posts yet. Create one to get started.</p>
          </div>
        )}

        <div className="space-y-3">
          {posts.map((post) => (
            <div key={post.id} className="border border-slate-100 rounded-xl p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    {(post.channels || []).map(ch => (
                      <span key={ch} className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${PLATFORM_COLORS[ch] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
                        {PLATFORM_ICONS[ch] ?? "🌐"} {ch}
                      </span>
                    ))}
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[post.status] ?? "bg-slate-100 text-slate-600"}`}>
                      {post.status}
                    </span>
                  </div>

                  <p className="text-sm text-slate-700 line-clamp-2">{post.body}</p>

                  {post.image_url && (
                    <img src={post.image_url} alt="" className="mt-2 h-24 w-full object-cover rounded-lg" />
                  )}

                  <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                    <span>📅 {new Date(post.scheduled_at).toLocaleString()}</span>
                    {post.publish_error && (
                      <span className="text-red-500 truncate max-w-xs" title={post.publish_error}>
                        ⚠ {post.publish_error}
                      </span>
                    )}
                  </div>
                </div>

                <button
                  onClick={() => handleDeletePost(post.id)}
                  disabled={deletingPost === post.id}
                  className="text-slate-400 hover:text-red-500 text-sm font-bold shrink-0 disabled:opacity-40"
                >
                  {deletingPost === post.id ? "…" : "✕"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Create Post Modal */}
      {showCreatePost && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-800">Create Social Post</h3>
              <button onClick={() => setShowCreatePost(false)} className="text-slate-400 hover:text-slate-700 text-xl">×</button>
            </div>

            {/* Platform selector */}
            <div>
              <label className="text-xs font-semibold text-slate-500 block mb-2">Post to</label>
              <div className="flex flex-wrap gap-2">
                {ALL_PLATFORMS.map(platform => {
                  const connected = connectedPlatforms.has(platform);
                  const selected = newPost.channels.includes(platform);
                  return (
                    <button
                      key={platform}
                      type="button"
                      disabled={!connected}
                      onClick={() => toggleChannel(platform)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                        selected
                          ? "bg-purple-600 text-white border-purple-600"
                          : "bg-white text-slate-700 border-slate-200 hover:border-purple-300"
                      }`}
                    >
                      <span>{PLATFORM_ICONS[platform]}</span>
                      <span className="capitalize">{platform === "twitter" ? "X" : platform}</span>
                      {!connected && <span className="text-[9px]">(not connected)</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-500 block mb-1">Content</label>
              <textarea
                value={newPost.content}
                onChange={e => setNewPost(p => ({ ...p, content: e.target.value }))}
                rows={4}
                placeholder="Write your post…"
                className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <p className="text-[10px] text-slate-400 mt-1">{newPost.content.length} characters</p>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-500 block mb-1">Schedule date & time</label>
              <input
                type="datetime-local"
                value={newPost.scheduledDate}
                onChange={e => setNewPost(p => ({ ...p, scheduledDate: e.target.value }))}
                className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-500 block mb-1">Image URL (optional)</label>
              <input
                type="url"
                value={newPost.imageUrl}
                onChange={e => setNewPost(p => ({ ...p, imageUrl: e.target.value }))}
                placeholder="https://…"
                className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            {error && <p className="text-xs text-red-600 bg-red-50 rounded-lg p-2">{error}</p>}

            <div className="flex gap-3 pt-1">
              <button
                onClick={handleCreatePost}
                disabled={creating || !newPost.content || newPost.channels.length === 0}
                className="flex-1 py-2 bg-purple-600 text-white text-sm rounded-xl hover:bg-purple-700 font-medium disabled:opacity-50"
              >
                {creating ? "Scheduling…" : "Schedule Post"}
              </button>
              <button
                onClick={() => setShowCreatePost(false)}
                className="flex-1 py-2 bg-slate-100 text-slate-700 text-sm rounded-xl hover:bg-slate-200 font-medium"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
