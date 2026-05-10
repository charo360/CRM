import React, { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";
import type { BlogPost } from "@/lib/seo/types";

interface PublishModalProps {
  post: BlogPost;
  onClose: () => void;
  onPublished: () => void;
}

export function PublishModal({ post, onClose, onPublished }: PublishModalProps) {
  const [platform, setPlatform] = useState("wordpress");
  const [wpUrl, setWpUrl] = useState("");
  const [wpUser, setWpUser] = useState("");
  const [wpPass, setWpPass] = useState("");
  const [shopifyDomain, setShopifyDomain] = useState("");
  const [shopifyToken, setShopifyToken] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [result, setResult] = useState("");
  const [credsSaved, setCredsSaved] = useState(false);

  useEffect(() => {
    setCredsSaved(false);
    seoApi.getPublishCredentials(platform).then(creds => {
      if (!creds?.platform) return;
      if (platform === "wordpress") {
        if (creds.wp_url) setWpUrl(creds.wp_url);
        if (creds.wp_username) setWpUser(creds.wp_username);
        if (creds.wp_password) setWpPass(creds.wp_password);
      } else if (platform === "shopify") {
        if (creds.shopify_domain) setShopifyDomain(creds.shopify_domain);
        if (creds.shopify_token) setShopifyToken(creds.shopify_token);
      }
      setCredsSaved(true);
    }).catch(() => {});
  }, [platform]);

  async function handlePublish() {
    setPublishing(true);
    setResult("");
    try {
      seoApi.savePublishCredentials({
        platform,
        wp_url: wpUrl || undefined,
        wp_username: wpUser || undefined,
        wp_password: wpPass || undefined,
        shopify_domain: shopifyDomain || undefined,
        shopify_token: shopifyToken || undefined,
      }).catch(() => {});

      const res = await seoApi.publishPost({
        post_id: post.id,
        platform,
        wp_url: wpUrl || undefined,
        wp_username: wpUser || undefined,
        wp_password: wpPass || undefined,
        shopify_domain: shopifyDomain || undefined,
        shopify_token: shopifyToken || undefined,
      });

      if (res.ok) {
        setResult(`Published! ${res.post_url || ""}`);
        onPublished();
      } else {
        setResult(`Error: ${res.error || "Unknown error"}`);
      }
    } catch (e) {
      setResult(e instanceof Error ? e.message : "Failed");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-base font-bold text-slate-800">Publish Post</p>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl">×</button>
        </div>
        <p className="text-sm text-slate-600 font-medium truncate">{post.title}</p>

        <div>
          <label className="text-xs text-slate-500 font-medium block mb-1">Platform</label>
          <select
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
            value={platform}
            onChange={e => setPlatform(e.target.value)}
          >
            <option value="wordpress">WordPress</option>
            <option value="shopify">Shopify</option>
          </select>
        </div>

        {platform === "wordpress" && (
          <div className="space-y-2">
            {credsSaved && <p className="text-[10px] text-emerald-600 font-medium">✓ Credentials loaded from last time</p>}
            <input 
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" 
              placeholder="WordPress URL (e.g. https://yoursite.com)" 
              value={wpUrl} 
              onChange={e => setWpUrl(e.target.value)} 
            />
            <input 
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" 
              placeholder="Username" 
              value={wpUser} 
              onChange={e => setWpUser(e.target.value)} 
            />
            <input 
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" 
              placeholder="Application Password" 
              type="password" 
              value={wpPass} 
              onChange={e => setWpPass(e.target.value)} 
            />
            <p className="text-xs text-slate-400">Use a WordPress Application Password (Users → Profile → Application Passwords)</p>
          </div>
        )}

        {platform === "shopify" && (
          <div className="space-y-2">
            {credsSaved && <p className="text-[10px] text-emerald-600 font-medium">✓ Credentials loaded from last time</p>}
            <input 
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" 
              placeholder="Shopify domain (e.g. mystore.myshopify.com)" 
              value={shopifyDomain} 
              onChange={e => setShopifyDomain(e.target.value)} 
            />
            <input 
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" 
              placeholder="Access Token" 
              type="password" 
              value={shopifyToken} 
              onChange={e => setShopifyToken(e.target.value)} 
            />
          </div>
        )}

        {result && (
          <p className={`text-xs rounded-lg p-2 ${result.startsWith("Error") ? "bg-red-50 text-red-600" : "bg-green-50 text-green-700"}`}>
            {result}
          </p>
        )}

        <button
          onClick={handlePublish}
          disabled={publishing}
          className="w-full py-2 bg-emerald-600 text-white text-sm rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50"
        >
          {publishing ? "Publishing…" : `Publish to ${platform === "wordpress" ? "WordPress" : "Shopify"}`}
        </button>
      </div>
    </div>
  );
}
