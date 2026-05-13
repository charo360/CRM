import type { BlogTemplate } from "./blogTemplates";

/**
 * Product-focused blog templates optimized for e-commerce content
 */
export const productBlogTemplates: BlogTemplate[] = [
  {
    id: "product-showcase",
    name: "Product Showcase",
    description: "Highlight products with large images, pricing, and buy buttons",
    preview: "🛍️ Showcase",
    style: {
      layout: "premium",
      headerStyle: "product-hero",
      contentStyle: "product-focused",
      imageStyle: "product-gallery",
      accentColor: "purple",
    },
    features: ["Product cards", "Pricing display", "Buy buttons", "Image gallery", "Specifications"],
  },
  {
    id: "product-comparison",
    name: "Product Comparison",
    description: "Compare multiple products side-by-side with features and pricing",
    preview: "⚖️ Compare",
    style: {
      layout: "modern",
      headerStyle: "comparison-header",
      contentStyle: "comparison-table",
      imageStyle: "side-by-side",
      accentColor: "blue",
    },
    features: ["Comparison table", "Feature matrix", "Price comparison", "Pros/cons", "Winner badge"],
  },
  {
    id: "product-review",
    name: "Product Review",
    description: "In-depth product reviews with ratings, pros/cons, and recommendations",
    preview: "⭐ Review",
    style: {
      layout: "magazine",
      headerStyle: "review-header",
      contentStyle: "review-format",
      imageStyle: "review-images",
      accentColor: "emerald",
    },
    features: ["Star ratings", "Pros/cons boxes", "Verdict section", "Alternatives", "FAQ"],
  },
  {
    id: "product-guide",
    name: "Buying Guide",
    description: "Help customers choose the right product with detailed guides",
    preview: "📋 Guide",
    style: {
      layout: "classic",
      headerStyle: "guide-header",
      contentStyle: "step-by-step",
      imageStyle: "instructional",
      accentColor: "indigo",
    },
    features: ["Step-by-step", "Decision tree", "Checklists", "Expert tips", "Product links"],
  },
  {
    id: "product-collection",
    name: "Product Collection",
    description: "Curated collections and gift guides featuring multiple products",
    preview: "🎁 Collection",
    style: {
      layout: "modern",
      headerStyle: "collection-hero",
      contentStyle: "grid-layout",
      imageStyle: "collection-grid",
      accentColor: "purple",
    },
    features: ["Product grid", "Category filters", "Quick view", "Add to cart", "Collection theme"],
  },
];

/**
 * Get product template by ID
 */
export function getProductTemplateById(id: string): BlogTemplate | undefined {
  return productBlogTemplates.find(t => t.id === id);
}

/**
 * Get all templates (regular + product)
 */
export function getAllTemplates(): BlogTemplate[] {
  const { blogTemplates } = require('./blogTemplates');
  return [...blogTemplates, ...productBlogTemplates];
}
