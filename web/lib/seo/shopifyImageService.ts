import { seoApi } from "@/lib/api";

/** Shape returned by the backend /seo/shopify/products endpoint */
export interface ShopifyBlogProduct {
  id: string;
  title: string;
  handle: string;
  description: string;
  image_url: string;
  all_images: string[];
  price: string;
  tags: string[];
  product_type: string;
  vendor: string;
}

/** Normalised shape used by image selector components */
export interface ProductImageSource {
  productId: string;
  productTitle: string;
  productHandle: string;
  imageUrl: string;
  thumbnail: string;
  alt?: string;
  price?: string;
  tags: string[];
  allImages: string[];
}

/** Check if Shopify is connected via the existing Composio integration */
export async function isShopifyConnected(): Promise<boolean> {
  try {
    const result = await seoApi.shopifyConnection();
    return result.connected;
  } catch {
    return false;
  }
}

/**
 * Search the user's Shopify products via backend (Composio proxy).
 * No separate credentials needed — uses the user's existing Composio Shopify connection.
 */
export async function searchProductsForBlog(
  topic: string,
  keywords: string[]
): Promise<ProductImageSource[]> {
  // Try topic first, then first keyword as fallback
  const searchTerms = [topic, ...keywords].filter(Boolean);
  const seen = new Set<string>();
  const results: ProductImageSource[] = [];

  for (const term of searchTerms.slice(0, 2)) {
    try {
      const data = await seoApi.shopifyProducts(term, 12);
      for (const p of data.products) {
        if (seen.has(p.id)) continue;
        seen.add(p.id);
        results.push(toProductImageSource(p));
      }
    } catch {
      // Ignore per-term errors; surface error only if all fail
    }
    if (results.length >= 20) break;
  }

  // If no results from search terms, fetch recent products
  if (results.length === 0) {
    try {
      const data = await seoApi.shopifyProducts("", 20);
      for (const p of data.products) {
        if (!seen.has(p.id)) {
          seen.add(p.id);
          results.push(toProductImageSource(p));
        }
      }
    } catch {
      throw new Error("Could not load products. Make sure Shopify is connected in the Integrations page.");
    }
  }

  return results;
}

function toProductImageSource(p: ShopifyBlogProduct): ProductImageSource {
  return {
    productId: p.id,
    productTitle: p.title,
    productHandle: p.handle,
    imageUrl: p.image_url,
    thumbnail: p.image_url,
    alt: p.title,
    price: p.price || undefined,
    tags: p.tags,
    allImages: p.all_images,
  };
}

/** Generate blog idea titles from product data */
export function generateProductBlogIdeas(products: ShopifyBlogProduct[]): string[] {
  const ideas: string[] = [];
  for (const p of products) {
    if (p.title) {
      ideas.push(
        `How to Use ${p.title}: A Complete Guide`,
        `${p.title} Review: Features, Benefits & Pricing`,
        p.product_type ? `Top ${p.product_type} Options: Featuring ${p.title}` : `Why ${p.title} Stands Out`,
        `${p.title} vs Alternatives: Which is Best?`
      );
    }
  }
  return ideas.slice(0, 10);
}

/** Create a product showcase Markdown block to insert into blog content */
export function generateProductShowcase(product: ShopifyBlogProduct): string {
  const price = product.price ? `**Price:** $${product.price}\n\n` : "";
  const features = product.tags.length
    ? `**Features:**\n${product.tags.slice(0, 5).map(t => `- ${t}`).join("\n")}\n\n`
    : "";
  return `## Featured Product: ${product.title}

![${product.title}](${product.image_url})

${product.description ? product.description.replace(/<[^>]*>/g, "").trim() + "\n\n" : ""}${features}${price}[View Product](/products/${product.handle})
`;
}
