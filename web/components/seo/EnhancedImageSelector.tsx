import React, { useState, useEffect } from "react";
import { ImageSelector } from "./ImageSelector";
import { ShopifyProductSelector } from "./ShopifyProductSelector";
import { isShopifyConnected, type ProductImageSource } from "@/lib/seo/shopifyImageService";

interface EnhancedImageSelectorProps {
  topic: string;
  keywords: string[];
  title?: string;
  selectedImage: string;
  onSelectImage: (url: string) => void;
  onProductSelected?: (product: ProductImageSource) => void;
}

type ImageSourceTab = "ai" | "shopify" | "custom";

export function EnhancedImageSelector({
  topic,
  keywords,
  title,
  selectedImage,
  onSelectImage,
  onProductSelected,
}: EnhancedImageSelectorProps) {
  const [activeSource, setActiveSource] = useState<ImageSourceTab>("ai");
  const [shopifyConnected, setShopifyConnected] = useState<boolean | null>(null);

  useEffect(() => {
    isShopifyConnected().then(setShopifyConnected);
  }, []);

  const sourceLabel: Record<ImageSourceTab, string> = {
    ai: "✨ AI",
    shopify: "🛍️ Product",
    custom: "🔗 Custom",
  };

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-1.5 p-1 bg-slate-100 rounded-xl">
        <button
          type="button"
          onClick={() => setActiveSource("ai")}
          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
            activeSource === "ai"
              ? "bg-white text-violet-700 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          ✨ AI Generate
        </button>

        {/* Shopify tab — shown while checking (null) or when connected */}
        {shopifyConnected !== false && (
          <button
            type="button"
            onClick={() => setActiveSource("shopify")}
            disabled={shopifyConnected === null}
            className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50 ${
              activeSource === "shopify"
                ? "bg-white text-purple-700 shadow-sm"
                : "text-slate-600 hover:text-slate-800"
            }`}
          >
            🛍️ My Products
            {shopifyConnected === null && (
              <span className="ml-1 text-[10px] text-slate-400">…</span>
            )}
          </button>
        )}

        <button
          type="button"
          onClick={() => setActiveSource("custom")}
          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
            activeSource === "custom"
              ? "bg-white text-blue-700 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          🔗 Custom URL
        </button>
      </div>

      {/* Current image preview */}
      {selectedImage && (
        <div className="relative rounded-xl overflow-hidden border-2 border-emerald-200">
          <img
            src={selectedImage}
            alt="Selected"
            className="w-full h-48 object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).src =
                "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=1200&h=675&fit=crop";
            }}
          />
          <div className="absolute top-2 right-2 flex gap-2">
            <span className="bg-black/50 backdrop-blur-sm text-white text-xs px-3 py-1 rounded-lg font-medium">
              {sourceLabel[activeSource]}
            </span>
            <button
              type="button"
              onClick={() => onSelectImage("")}
              className="bg-red-500 text-white text-xs px-3 py-1 rounded-lg hover:bg-red-600 font-medium"
            >
              Remove
            </button>
          </div>
        </div>
      )}

      {/* AI image generation */}
      {activeSource === "ai" && (
        <ImageSelector
          topic={topic}
          keywords={keywords}
          title={title}
          selectedImage={selectedImage}
          onSelectImage={onSelectImage}
        />
      )}

      {/* Shopify products via Composio */}
      {activeSource === "shopify" && (
        <ShopifyProductSelector
          topic={topic}
          keywords={keywords}
          onSelectProduct={(product) => onProductSelected?.(product)}
          onSelectImage={onSelectImage}
        />
      )}

      {/* Custom URL */}
      {activeSource === "custom" && (
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-500 block">Paste any image URL</label>
          <input
            type="url"
            value={selectedImage}
            onChange={(e) => onSelectImage(e.target.value)}
            placeholder="https://example.com/image.jpg"
            className="w-full border border-slate-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-slate-400">Recommended: 1920×1080 or 16:9 aspect ratio.</p>
        </div>
      )}

      {/* Shopify not connected nudge */}
      {shopifyConnected === false && activeSource === "ai" && (
        <div className="flex items-center gap-3 bg-purple-50 border border-purple-200 rounded-lg px-4 py-3">
          <span className="text-lg">�️</span>
          <div className="flex-1">
            <p className="text-xs font-semibold text-purple-800">Use your Shopify product images</p>
            <p className="text-xs text-purple-700">Connect Shopify in Integrations and product photos will appear here automatically.</p>
          </div>
          <a
            href="/dashboard/integrations"
            className="text-xs text-purple-600 font-semibold underline shrink-0"
          >
            Connect →
          </a>
        </div>
      )}
    </div>
  );
}
