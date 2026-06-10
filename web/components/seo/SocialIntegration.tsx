import React, { useState, useEffect, useCallback } from "react";
import { seoApi, type BlogPost } from "@/lib/api";
import { toast } from "sonner";
import { useZernioAccounts } from "@/contexts/ZernioAccountsContext";
import { SOCIAL_PLATFORMS } from "@/components/ZernioSocialPanel";

type Platform = "facebook" | "twitter" | "linkedin" | "instagram" | "tiktok";

interface ZernioAccount {
  id: string;
  platform: string;
  displayName?: string;
  username?: string;
}

const ALL_PLATFORMS: Platform[] = ["facebook", "twitter", "linkedin", "instagram"];

const PLATFORM_ICONS: Record<string, string> = {
  facebook: "📘", twitter: "𝕏", linkedin: "💼", instagram: "📷", tiktok: "🎵",
};

function buildCaption(post: BlogPost): string {
  const clean = post.content.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
  const intro = clean.slice(0, 240).trim();
  const truncated = clean.length > 240 ? intro + "…" : intro;
  const link = post.site_post_url ? `\n\n🔗 ${post.site_post_url}` : "";
  return `${post.title}\n\n${truncated}${link}`;
}

export default function SocialIntegration() {
  const {
    accounts: rawZernioAccounts,
    loading: loadingAccounts,
    refresh: refreshAccounts,
    connect: zernioConnect,
    disconnect: zernioDisconnect,
  } = useZernioAccounts();

  const accounts: ZernioAccount[] = (rawZernioAccounts as any[]).map((a: any) => ({
    id: String(a.id || a._id || ""),
    platform: String(a.platform || "").toLowerCase(),
    displayName: a.displayName || a.name || a.username || "",
    username: a.username || a.displayName || "",
  }));

  // Blog posts state
  const [blogPosts, setBlogPosts] = useState<BlogPost[]>([]);
  const [loadingPosts, setLoadingPosts] = useState(true);

  // Auto-share settings state
  const [autoEnabled, setAutoEnabled] = useState(false);
  const [autoTrigger, setAutoTrigger] = useState<"published" | "scheduled" | "both">("published");
  const [autoAccountIds, setAutoAccountIds] = useState<string[]>([]);
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);

  // Connect / disconnect state
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [connError, setConnError] = useState("");

  // Share modal state
  const [sharePost, setSharePost] = useState<BlogPost | null>(null);
  const [shareAccId, setShareAccId] = useState("");
  const [sharePlatform, setSharePlatform] = useState("");
  const [shareCaption, setShareCaption] = useState("");
  const [sharing, setSharing] = useState(false);
  const [shareResult, setShareResult] = useState("");

  const loadBlogPosts = useCallback(async () => {
    setLoadingPosts(true);
    try { setBlogPosts(await seoApi.listPosts()); }
    catch { setBlogPosts([]); }
    finally { setLoadingPosts(false); }
  }, []);

  const loadSettings = useCallback(async () => {
    setLoadingSettings(true);
    try {
      const s = await seoApi.getAutoShareSettings();
      setAutoEnabled(s.enabled ?? false);
      setAutoTrigger((s.trigger as any) ?? "published");
      setAutoAccountIds(s.account_ids ?? []);
    } catch { /* keep defaults */ }
    finally { setLoadingSettings(false); }
  }, []);

  async function saveSettings() {
    setSavingSettings(true);
    try {
      const account_platforms: Record<string, string> = {};
      for (const acc of accounts) {
        if (autoAccountIds.includes(acc.id)) account_platforms[acc.id] = acc.platform;
      }
      await seoApi.updateAutoShareSettings({ enabled: autoEnabled, trigger: autoTrigger, account_ids: autoAccountIds, account_platforms });
      toast.success("Auto-share settings saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSavingSettings(false);
    }
  }

  function toggleAutoAccount(id: string) {
    setAutoAccountIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  useEffect(() => { loadBlogPosts(); loadSettings(); }, [loadBlogPosts, loadSettings]);

  function openShare(post: BlogPost) {
    const firstAcc = accounts[0];
    setSharePost(post);
    setShareCaption(buildCaption(post));
    setShareAccId(firstAcc?.id ?? "");
    setSharePlatform(firstAcc?.platform ?? "");
    setShareResult("");
  }

  async function doShare() {
    if (!sharePost || !shareAccId || !sharePlatform || !shareCaption.trim()) return;
    setSharing(true); setShareResult("");
    try {
      await seoApi.shareBlogToSocial(sharePost.id, {
        platform: sharePlatform,
        account_id: shareAccId,
        caption: shareCaption.trim(),
        link_url: sharePost.site_post_url ?? "",
        image_url: sharePost.image_url ?? "",
      });
      const label = SOCIAL_PLATFORMS.find(p => p.id === sharePlatform)?.label ?? sharePlatform;
      setShareResult(`✓ Posted to ${label}`);
      // update local social_shares
      setBlogPosts(prev => prev.map(p => p.id === sharePost.id ? {
        ...p,
        social_shares: [...(p.social_shares ?? []), {
          platform: sharePlatform, account_id: shareAccId,
          social_post_id: "", caption: shareCaption.trim(),
          link_url: sharePost.site_post_url ?? "", shared_at: new Date().toISOString(),
        }],
      } : p));
      setTimeout(() => setSharePost(null), 1800);
    } catch (e) {
      setShareResult("Error: " + (e instanceof Error ? e.message : "Share failed"));
    } finally {
      setSharing(false);
    }
  }

  async function handleConnect(platform: string) {
    setConnectingPlatform(platform); setConnError("");
    try {
      const redirectUrl = `${window.location.origin}/dashboard/seo?tab=social&connected=${platform}`;
      const data = await zernioConnect(platform, redirectUrl);
      if ((data as any).authUrl) {
        const popup = window.open((data as any).authUrl, `connect_${platform}`, "width=600,height=700");
        const check = setInterval(() => {
          if (popup?.closed) { clearInterval(check); setConnectingPlatform(null); void refreshAccounts(); }
        }, 800);
      }
    } catch (e) {
      setConnError(e instanceof Error ? e.message : `Failed to connect ${platform}`);
      setConnectingPlatform(null);
    }
  }

  async function handleDisconnect(accountId: string) {
    if (!confirm("Disconnect this account?")) return;
    setDisconnecting(accountId);
    try { await zernioDisconnect(accountId); }
    catch (e) { setConnError(e instanceof Error ? e.message : "Failed to disconnect"); }
    finally { setDisconnecting(null); }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-800">Share Blogs to Social</h2>
        <p className="text-sm text-slate-500 mt-0.5">Pick a blog post and publish it directly to your connected social accounts</p>
      </div>

      {connError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 flex items-center justify-between">
          <p className="text-sm text-red-700">{connError}</p>
          <button onClick={() => setConnError("")} className="text-red-400 hover:text-red-600 text-lg">×</button>
        </div>
      )}

      {/* Connected Accounts — compact strip */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700">Connected Accounts</h3>
          {loadingAccounts && <span className="text-xs text-slate-400">Loading…</span>}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {ALL_PLATFORMS.map(platform => {
            const connected = accounts.filter(a => a.platform === platform);
            const isConnected = connected.length > 0;
            const isConnecting = connectingPlatform === platform;
            return (
              <div key={platform} className={`rounded-xl border p-3 flex flex-col gap-2 ${isConnected ? "border-green-200 bg-green-50" : "border-slate-200 bg-slate-50"}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-base">{PLATFORM_ICONS[platform]}</span>
                    <span className={`text-xs font-semibold ${isConnected ? "text-green-800" : "text-slate-600"}`}>
                      {platform === "twitter" ? "X / Twitter" : platform.charAt(0).toUpperCase() + platform.slice(1)}
                    </span>
                  </div>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${isConnected ? "bg-green-200 text-green-800" : "bg-slate-200 text-slate-500"}`}>
                    {isConnected ? "✓" : "Off"}
                  </span>
                </div>
                {isConnected ? (
                  <div className="space-y-1">
                    {connected.map(acc => (
                      <div key={acc.id} className="flex items-center justify-between gap-1">
                        <p className="text-[11px] text-green-700 truncate font-medium">{acc.displayName || acc.username || platform}</p>
                        <button onClick={() => handleDisconnect(acc.id)} disabled={disconnecting === acc.id}
                          className="text-[10px] text-red-500 hover:text-red-700 shrink-0 disabled:opacity-50">
                          {disconnecting === acc.id ? "…" : "Remove"}
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <button onClick={() => handleConnect(platform)} disabled={isConnecting}
                    className="w-full py-1 bg-purple-600 text-white text-[11px] rounded-lg hover:bg-purple-700 font-medium disabled:opacity-50">
                    {isConnecting ? "Opening…" : "Connect"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
        {!loadingAccounts && accounts.length === 0 && (
          <p className="text-xs text-slate-400 mt-3 text-center">
            No accounts connected yet.{" "}
            <a href="/dashboard/integrations" className="text-purple-600 hover:underline font-medium">Go to Integrations →</a>
          </p>
        )}
      </div>

      {/* Auto-Share Settings */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Auto-Share</h3>
            <p className="text-xs text-slate-400 mt-0.5">Automatically post to social when a blog is published or scheduled</p>
          </div>
          {/* Master toggle */}
          <button
            type="button"
            onClick={() => setAutoEnabled(v => !v)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
              autoEnabled ? "bg-purple-600" : "bg-slate-200"
            }`}
          >
            <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
              autoEnabled ? "translate-x-6" : "translate-x-1"
            }`} />
          </button>
        </div>

        {autoEnabled && (
          <>
            {/* Trigger */}
            <div>
              <p className="text-xs font-semibold text-slate-500 mb-2">Post when…</p>
              <div className="flex gap-2">
                {(["published", "scheduled", "both"] as const).map(t => (
                  <button key={t} type="button" onClick={() => setAutoTrigger(t)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                      autoTrigger === t ? "bg-purple-600 text-white border-purple-600" : "bg-white text-slate-600 border-slate-200 hover:border-purple-300"
                    }`}>
                    {t === "published" ? "🚀 Published" : t === "scheduled" ? "📅 Scheduled" : "⚡ Both"}
                  </button>
                ))}
              </div>
            </div>

            {/* Account picker */}
            <div>
              <p className="text-xs font-semibold text-slate-500 mb-2">Share to these accounts</p>
              {accounts.length === 0 ? (
                <p className="text-xs text-slate-400">No accounts connected yet. Connect one above first.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {accounts.map(acc => {
                    const pDef = SOCIAL_PLATFORMS.find(p => p.id === acc.platform);
                    const checked = autoAccountIds.includes(acc.id);
                    return (
                      <label key={acc.id} className={`flex items-center gap-3 px-3 py-2.5 rounded-xl border cursor-pointer transition-all ${
                        checked ? "border-purple-400 bg-purple-50" : "border-slate-200 hover:border-slate-300 bg-white"
                      }`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleAutoAccount(acc.id)}
                          className="accent-purple-600 w-4 h-4 rounded" />
                        <span className={`w-6 h-6 flex items-center justify-center rounded-full ${pDef?.bg ?? "bg-slate-100"}`}>
                          {pDef?.logo ?? <span className="text-sm">{PLATFORM_ICONS[acc.platform] ?? "🌐"}</span>}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className={`text-xs font-semibold ${pDef?.text ?? "text-slate-700"}`}>{pDef?.label ?? acc.platform}</p>
                          <p className="text-[10px] text-slate-400 truncate">{acc.displayName || acc.username || acc.id}</p>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button type="button" onClick={saveSettings}
                disabled={savingSettings || autoAccountIds.length === 0}
                className="px-4 py-2 bg-purple-600 text-white text-sm rounded-xl font-semibold hover:bg-purple-700 disabled:opacity-50 transition-colors">
                {savingSettings ? "Saving…" : "Save auto-share settings"}
              </button>
              {autoAccountIds.length === 0 && autoEnabled && (
                <p className="text-xs text-amber-600">Select at least one account</p>
              )}
            </div>
          </>
        )}

        {!autoEnabled && (
          <p className="text-xs text-slate-400">Toggle on to set up automatic social posting whenever you publish or schedule a blog post.</p>
        )}
      </div>

      {/* Blog Posts List */}
      <div className="bg-white rounded-xl border border-slate-200">
        <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">Your Blog Posts</h3>
          <div className="flex items-center gap-2">
            {loadingPosts && <span className="text-xs text-slate-400">Loading…</span>}
            <button onClick={loadBlogPosts} className="text-xs text-slate-400 hover:text-slate-600">↻ Refresh</button>
          </div>
        </div>

        {!loadingPosts && blogPosts.length === 0 && (
          <div className="text-center py-14 text-slate-400">
            <p className="text-4xl mb-3">✍️</p>
            <p className="text-sm font-medium text-slate-500">No blog posts yet</p>
            <p className="text-xs mt-1">Write a post in the Blog tab first, then share it here</p>
            <a href="/dashboard/seo?tab=blog" className="inline-block mt-3 text-xs text-purple-600 hover:underline font-medium">Go to Blog tab →</a>
          </div>
        )}

        <div className="divide-y divide-slate-50">
          {blogPosts.map(post => {
            const shares = post.social_shares ?? [];
            const sharedPlatforms = [...new Set(shares.map(s => s.platform))];
            const canShare = accounts.length > 0;
            return (
              <div key={post.id} className="px-5 py-4 flex items-start justify-between gap-4 hover:bg-slate-50/60 transition-colors">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-800 truncate">{post.title}</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {post.created_at ? new Date(post.created_at).toLocaleDateString() : ""}
                    {post.word_count ? ` · ${post.word_count} words` : ""}
                    {post.site_post_url && (
                      <a href={post.site_post_url} target="_blank" rel="noopener noreferrer"
                        className="ml-2 text-emerald-600 hover:underline">✓ Live</a>
                    )}
                  </p>
                  {/* Shared platform badges */}
                  {sharedPlatforms.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {sharedPlatforms.map(plat => {
                        const pDef = SOCIAL_PLATFORMS.find(p => p.id === plat);
                        return (
                          <span key={plat} className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${pDef?.bg ?? "bg-slate-100"} ${pDef?.text ?? "text-slate-600"} ${pDef?.border ?? "border-slate-200"}`}>
                            {pDef?.logo}
                            {pDef?.label ?? plat}
                          </span>
                        );
                      })}
                      <span className="text-[10px] text-slate-400 self-center">{shares.length === 1 ? "1 share" : `${shares.length} shares`}</span>
                    </div>
                  )}
                </div>
                <div className="shrink-0 flex items-center gap-2">
                  {canShare ? (
                    <button
                      onClick={() => openShare(post)}
                      className="text-xs px-3 py-1.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-medium whitespace-nowrap"
                    >
                      📤 Share
                    </button>
                  ) : (
                    <span className="text-[11px] text-slate-400 italic">Connect an account first</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Share Modal */}
      {sharePost && (
        <div className="fixed inset-0 bg-black/50 z-[70] flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-5">
            <div className="flex items-center justify-between">
              <p className="text-base font-bold text-slate-800">📤 Share to Social</p>
              <button onClick={() => setSharePost(null)} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
            </div>

            <p className="text-sm text-slate-600 font-medium truncate">{sharePost.title}</p>

            {/* Account selector */}
            <div>
              <label className="text-xs font-semibold text-slate-500 mb-2 block">Post from account</label>
              <div className="flex flex-col gap-2 max-h-40 overflow-y-auto pr-1">
                {accounts.map(acc => {
                  const pDef = SOCIAL_PLATFORMS.find(p => p.id === acc.platform);
                  const selected = shareAccId === acc.id;
                  return (
                    <button key={acc.id} type="button"
                      onClick={() => { setShareAccId(acc.id); setSharePlatform(acc.platform); }}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-all ${selected ? "border-purple-500 bg-purple-50 ring-2 ring-purple-200" : "border-slate-200 hover:border-slate-300 bg-white"}`}>
                      <span className={`w-7 h-7 flex items-center justify-center rounded-full ${pDef?.bg ?? "bg-slate-100"}`}>
                        {pDef?.logo ?? <span className="text-sm">{PLATFORM_ICONS[acc.platform] ?? "🌐"}</span>}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className={`text-xs font-semibold ${pDef?.text ?? "text-slate-700"}`}>{pDef?.label ?? acc.platform}</p>
                        <p className="text-[10px] text-slate-400 truncate">{acc.displayName || acc.username || acc.id}</p>
                      </div>
                      {selected && <span className="text-purple-600 text-sm font-bold">✓</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Caption */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-semibold text-slate-500">Caption</label>
                <span className={`text-[10px] font-medium ${shareCaption.length > 2200 ? "text-red-500" : "text-slate-400"}`}>{shareCaption.length} chars</span>
              </div>
              <textarea value={shareCaption} onChange={e => setShareCaption(e.target.value)} rows={6}
                className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                placeholder="Caption for this post…" />
              <p className="text-[10px] text-slate-400 mt-1">Twitter/X caps at 280 · LinkedIn/Facebook up to 2,200</p>
            </div>

            {shareResult && (
              <p className={`text-sm font-medium ${shareResult.startsWith("Error") ? "text-red-600" : "text-emerald-600"}`}>{shareResult}</p>
            )}

            <div className="flex gap-3">
              <button type="button" onClick={() => void doShare()}
                disabled={sharing || !shareAccId || !shareCaption.trim()}
                className="flex-1 py-2.5 bg-purple-600 text-white text-sm rounded-xl font-semibold hover:bg-purple-700 disabled:opacity-50 transition-colors">
                {sharing ? "Posting…" : "Post now"}
              </button>
              <button type="button" onClick={() => setSharePost(null)}
                className="px-4 py-2.5 bg-slate-100 text-slate-700 text-sm rounded-xl font-medium hover:bg-slate-200">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
