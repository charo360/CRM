# Shopify Product Image Integration Guide

## Overview

Use your **Shopify product images** directly in blog posts! Perfect for e-commerce businesses writing product reviews, buying guides, comparisons, and promotional content.

## Why Use Product Images?

### ✅ **Benefits**
- **Authentic**: Real product photos from your store
- **Consistent**: Match your brand and product catalog
- **SEO-Optimized**: Product images already optimized for web
- **Automatic**: Pull images directly from Shopify API
- **Contextual**: Write about what you actually sell

### 🎯 **Perfect For**
- Product reviews and comparisons
- Buying guides and how-tos
- New product announcements
- Gift guides and collections
- Seasonal promotions
- Product tutorials

## Setup

### 1. Get Shopify API Credentials

**Create a Private App:**
1. Go to your Shopify Admin
2. Navigate to **Apps** → **App and sales channel settings**
3. Click **Develop apps** → **Create an app**
4. Name it "Blog Image Integration"
5. Click **Configure Admin API scopes**
6. Enable these permissions:
   - `read_products`
   - `read_product_listings`
   - `read_images`
7. Click **Save** → **Install app**
8. Copy your **Admin API access token**

### 2. Add Credentials to Your CRM

**In Settings:**
```
Shopify Store Domain: your-store.myshopify.com
Shopify Access Token: shpat_xxxxxxxxxxxxx
```

Or add to `.env.local`:
```bash
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxx
```

## Usage

### Basic Usage

```tsx
import { EnhancedImageSelector } from "@/components/seo/EnhancedImageSelector";

<EnhancedImageSelector
  topic="Best Running Shoes"
  keywords={["running", "shoes", "athletic"]}
  selectedImage={imageUrl}
  onSelectImage={setImageUrl}
  shopDomain="your-store.myshopify.com"
  shopifyAccessToken="shpat_xxxxx"
  onProductSelected={(product) => {
    // Optional: Use product data in blog
    console.log("Selected:", product.productTitle, product.price);
  }}
/>
```

### Features

**Three Image Sources:**
1. **📸 Stock Photos** - Unsplash professional images
2. **🛍️ My Products** - Your Shopify product images
3. **🔗 Custom URL** - Any image URL

**Product Selector Shows:**
- Product images with hover preview
- Product titles and pricing
- Product tags for context
- Quick selection interface

## Product-Focused Templates

Use specialized templates for product content:

### 1. **Product Showcase** 🛍️
Perfect for: Single product features, new arrivals
```tsx
templateId="product-showcase"
```
Features:
- Large product images
- Pricing display
- Buy buttons
- Specifications table
- Image gallery

### 2. **Product Comparison** ⚖️
Perfect for: "X vs Y" posts, product roundups
```tsx
templateId="product-comparison"
```
Features:
- Side-by-side comparison
- Feature matrix
- Price comparison
- Pros/cons lists
- Winner recommendations

### 3. **Product Review** ⭐
Perfect for: In-depth reviews, testing results
```tsx
templateId="product-review"
```
Features:
- Star ratings
- Pros/cons boxes
- Verdict section
- Alternative suggestions
- FAQ section

### 4. **Buying Guide** 📋
Perfect for: How to choose, buyer's guides
```tsx
templateId="product-guide"
```
Features:
- Step-by-step instructions
- Decision trees
- Checklists
- Expert tips
- Product recommendations

### 5. **Product Collection** 🎁
Perfect for: Gift guides, seasonal collections
```tsx
templateId="product-collection"
```
Features:
- Product grid layout
- Category filters
- Quick view modals
- Collection themes
- Add to cart buttons

## Advanced Features

### Search Products by Topic

```typescript
import { searchProductsForBlog } from "@/lib/seo/shopifyImageService";

const products = await searchProductsForBlog(
  "your-store.myshopify.com",
  "shpat_xxxxx",
  "summer collection",
  ["dress", "casual", "beach"]
);

// Returns products matching keywords with images
```

### Generate Product Showcase

```typescript
import { generateProductShowcase } from "@/lib/seo/shopifyImageService";

const markdown = generateProductShowcase(product, imageUrl);

// Outputs:
// ## Featured Product: Summer Dress
// ![Summer Dress](image-url)
// Beautiful lightweight dress perfect for summer...
// **Price:** $49.99
// [Shop Now](link)
```

### Get Product Collections

```typescript
import { getProductCollection } from "@/lib/seo/shopifyImageService";

const products = await getProductCollection(
  "your-store.myshopify.com",
  "shpat_xxxxx",
  "collection-id"
);

// Get all products from a specific collection
// Perfect for themed blog posts
```

### Generate Blog Ideas

```typescript
import { generateProductBlogIdeas } from "@/lib/seo/shopifyImageService";

const ideas = generateProductBlogIdeas(products);

// Returns:
// - "How to Use Summer Dress: A Complete Guide"
// - "Summer Dress Review: Features, Benefits & Pricing"
// - "Top Dresses Options: Featuring Summer Dress"
// - "Summer Dress vs Alternatives: Which is Best?"
```

## Complete Example

### Product Review Blog Post

```tsx
import { EnhancedImageSelector } from "@/components/seo/EnhancedImageSelector";
import { PremiumBlogPreview } from "@/components/seo/PremiumBlogPreview";
import { BlogTemplateSelector } from "@/components/seo/BlogTemplateSelector";

function ProductReviewBlog() {
  const [topic, setTopic] = useState("Best Running Shoes for Beginners");
  const [keywords, setKeywords] = useState("running shoes, beginner, comfortable");
  const [templateId, setTemplateId] = useState("product-review");
  const [imageUrl, setImageUrl] = useState("");
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [generated, setGenerated] = useState(null);

  async function generateBlog() {
    const result = await seoApi.generateBlog({
      topic,
      keywords: keywords.split(","),
      template_id: templateId,
      product_context: selectedProduct ? {
        title: selectedProduct.productTitle,
        price: selectedProduct.price,
        tags: selectedProduct.tags,
      } : undefined,
    });

    setGenerated(result);
  }

  return (
    <div className="space-y-6">
      {/* Template Selection */}
      <BlogTemplateSelector
        selectedTemplate={templateId}
        onSelectTemplate={setTemplateId}
      />

      {/* Topic & Keywords */}
      <input value={topic} onChange={e => setTopic(e.target.value)} />
      <input value={keywords} onChange={e => setKeywords(e.target.value)} />

      {/* Image Selection with Shopify Products */}
      <EnhancedImageSelector
        topic={topic}
        keywords={keywords.split(",")}
        selectedImage={imageUrl}
        onSelectImage={setImageUrl}
        shopDomain={process.env.NEXT_PUBLIC_SHOPIFY_DOMAIN}
        shopifyAccessToken={process.env.SHOPIFY_ACCESS_TOKEN}
        onProductSelected={setSelectedProduct}
      />

      {/* Selected Product Info */}
      {selectedProduct && (
        <div className="bg-purple-50 p-4 rounded-lg">
          <p className="font-semibold">{selectedProduct.productTitle}</p>
          <p className="text-sm text-purple-700">${selectedProduct.price}</p>
          <p className="text-xs text-slate-600">
            This product will be featured in your blog post
          </p>
        </div>
      )}

      {/* Generate */}
      <button onClick={generateBlog}>Generate Product Review</button>

      {/* Premium Preview */}
      {generated && (
        <PremiumBlogPreview
          title={generated.title}
          content={generated.content}
          imageUrl={imageUrl}
          templateId={templateId}
          tags={generated.tags}
        />
      )}
    </div>
  );
}
```

## Blog Content Ideas

### For E-commerce Stores

**Product Reviews:**
- "Honest Review: [Product Name]"
- "We Tested [Product] for 30 Days - Here's What Happened"
- "[Product] Review: Is It Worth the Hype?"

**Buying Guides:**
- "How to Choose the Perfect [Product Category]"
- "Ultimate Buying Guide: [Product Type]"
- "5 Things to Consider Before Buying [Product]"

**Comparisons:**
- "[Product A] vs [Product B]: Which is Better?"
- "Top 5 [Product Category] Compared"
- "Budget vs Premium: [Product] Comparison"

**Collections:**
- "10 Must-Have [Products] for [Season]"
- "Gift Guide: Best [Products] for [Occasion]"
- "Our Favorite [Product Category] This Month"

**How-To Guides:**
- "How to Use [Product]: Complete Guide"
- "5 Ways to Style [Product]"
- "Getting Started with [Product]"

## SEO Best Practices

### Product Image Optimization

**Alt Text:**
```typescript
// Automatically uses product title
alt={product.productTitle}

// Or customize:
alt="Blue running shoes for beginners - comfortable and affordable"
```

**Image Size:**
- Hero images: 1920x1080 (16:9)
- Product thumbnails: 800x800 (1:1)
- Inline images: 1200x675 (16:9)

**File Names:**
- Use descriptive names: `blue-running-shoes-beginner.jpg`
- Include keywords: `comfortable-athletic-footwear.jpg`

### Product Schema Markup

Add structured data for better SEO:

```json
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Running Shoes Pro",
  "image": "https://...",
  "description": "...",
  "brand": "Your Brand",
  "offers": {
    "@type": "Offer",
    "price": "89.99",
    "priceCurrency": "USD"
  }
}
```

## Troubleshooting

### Products Not Loading

**Check:**
1. Shopify credentials are correct
2. API token has `read_products` permission
3. Store domain includes `.myshopify.com`
4. Products exist in your store
5. Products are published (not draft)

**Error Messages:**
- "Shopify credentials not configured" → Add credentials in Settings
- "No products found" → Try different keywords or check product tags
- "API error" → Verify API token permissions

### Images Not Displaying

**Solutions:**
1. Check image URLs are publicly accessible
2. Verify Shopify CDN is not blocked
3. Try different product images
4. Use fallback stock photos
5. Check browser console for CORS errors

### Template Not Working

**Fixes:**
1. Verify template ID matches available templates
2. Clear browser cache
3. Check for CSS conflicts
4. Test with default template first

## API Reference

### searchProductsForBlog
```typescript
searchProductsForBlog(
  shopDomain: string,
  accessToken: string,
  topic: string,
  keywords: string[]
): Promise<ProductImageSource[]>
```

### getProductImages
```typescript
getProductImages(
  shopDomain: string,
  accessToken: string,
  productId: string
): Promise<ShopifyProductImage[]>
```

### generateProductShowcase
```typescript
generateProductShowcase(
  product: ShopifyProduct,
  imageUrl: string
): string
```

### formatProductForBlog
```typescript
formatProductForBlog(
  product: ShopifyProduct
): {
  title: string;
  description: string;
  images: string[];
  features: string[];
  price: string;
  url: string;
}
```

## Security Notes

**API Token Security:**
- Never commit tokens to version control
- Use environment variables
- Rotate tokens regularly
- Limit token permissions to read-only
- Use separate tokens for dev/production

**Best Practices:**
- Store tokens server-side when possible
- Use HTTPS for all API calls
- Validate image URLs before display
- Sanitize product data before rendering

## Next Steps

1. **Set up Shopify credentials** in Settings
2. **Test product search** with your inventory
3. **Try product templates** for different content types
4. **Create your first product blog** post
5. **Optimize images** for SEO and performance
6. **Track performance** of product-focused content

Your e-commerce blog content just got a major upgrade! 🚀
