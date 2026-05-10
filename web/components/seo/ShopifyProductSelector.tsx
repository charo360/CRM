import React, { useState } from "react";
import { searchProductsForBlog, type ProductImageSource } from "@/lib/seo/shopifyImageService";

interface ShopifyProductSelectorProps {
  topic: string;
  keywords: string[];
  onSelectProduct: (product: ProductImageSource) => void;
  onSelectImage: (imageUrl: string) => void;
}

export function ShopifyProductSelector({
  topic,
  keywords,
  onSelectProduct,
  onSelectImage,
}: ShopifyProductSelectorProps) {
  const [products, setProducts] = useState<ProductImageSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showProducts, setShowProducts] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<ProductImageSource | null>(null);

  async function loadProducts() {
    setLoading(true);
    setError("");
    try {
      const results = await searchProductsForBlog(topic, keywords);
      setProducts(results);
      setShowProducts(true);
      if (results.length === 0) {
        setError("No products with images found. Try different keywords.");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load products";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  function handleSelectProduct(product: ProductImageSource) {
    setSelectedProduct(product);
    onSelectProduct(product);
    onSelectImage(product.imageUrl);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <label className="text-xs font-semibold text-slate-500">My Shopify Products</label>
          <span className="text-[10px] bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium">
            via Composio
          </span>
        </div>
        <button
          type="button"
          onClick={loadProducts}
          disabled={loading}
          className="text-xs text-purple-600 hover:text-purple-700 font-medium disabled:opacity-50"
        >
          {loading ? "Loading…" : showProducts ? "Refresh" : "Browse products"}
        </button>
      </div>

      {/* Error — includes "not connected" guidance */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 space-y-1">
          <p className="text-xs text-red-700">{error}</p>
          {error.toLowerCase().includes("connect") && (
            <a
              href="/dashboard/integrations"
              className="text-xs text-red-600 font-semibold underline"
            >
              Go to Integrations →
            </a>
          )}
        </div>
      )}

      {/* Selected product chip */}
      {selectedProduct && (
        <div className="bg-gradient-to-br from-purple-50 to-pink-50 border-2 border-purple-200 rounded-xl p-3 flex gap-3 items-center">
          <img
            src={selectedProduct.thumbnail}
            alt={selectedProduct.productTitle}
            className="w-16 h-16 object-cover rounded-lg border border-purple-200 shrink-0"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-800 truncate">{selectedProduct.productTitle}</p>
            {selectedProduct.price && (
              <p className="text-xs text-purple-700 font-semibold">${selectedProduct.price}</p>
            )}
            <div className="flex flex-wrap gap-1 mt-1">
              {selectedProduct.tags.slice(0, 3).map(tag => (
                <span key={tag} className="text-[10px] bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">
                  {tag}
                </span>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={() => { setSelectedProduct(null); onSelectImage(""); }}
            className="text-slate-400 hover:text-red-500 text-lg shrink-0"
          >
            ✕
          </button>
        </div>
      )}

      {/* Product grid */}
      {showProducts && products.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 font-medium">
            {products.length} product{products.length !== 1 ? "s" : ""} found — click to use as hero image:
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 p-3 bg-slate-50 rounded-xl border border-slate-200 max-h-80 overflow-y-auto">
            {products.map((product) => (
              <button
                key={product.productId}
                type="button"
                onClick={() => handleSelectProduct(product)}
                className={`group relative rounded-xl overflow-hidden border-2 transition-all ${
                  selectedProduct?.productId === product.productId
                    ? "border-purple-500 ring-2 ring-purple-200 shadow-lg"
                    : "border-slate-200 hover:border-purple-300 hover:shadow-md"
                }`}
              >
                <div className="aspect-square bg-slate-100">
                  <img
                    src={product.thumbnail}
                    alt={product.productTitle}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src =
                        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop";
                    }}
                  />
                </div>
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-2">
                  <p className="text-white text-[10px] font-semibold line-clamp-2">{product.productTitle}</p>
                  {product.price && <p className="text-white/90 text-[10px] font-bold">${product.price}</p>}
                </div>
                {selectedProduct?.productId === product.productId && (
                  <div className="absolute top-1.5 right-1.5 bg-purple-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold">
                    ✓
                  </div>
                )}
                {product.price && (
                  <div className="absolute top-1.5 left-1.5 bg-purple-600/90 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-md shadow-sm">
                    ${product.price}
                  </div>
                )}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-slate-400 italic">
            💡 Images pulled from your connected Shopify store via Composio
          </p>
        </div>
      )}
    </div>
  );
}
