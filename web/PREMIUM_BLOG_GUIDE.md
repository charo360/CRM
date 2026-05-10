# Premium Blog Generation Guide

## Overview

The blog generation system now includes **premium templates** and **automatic image integration** for a professional, magazine-quality blog experience.

## Features

### 🎨 Premium Templates

Choose from 5 professionally designed templates:

1. **Premium Modern** (Default)
   - Clean, sophisticated design
   - Large hero images
   - Elegant typography
   - Features: Hero image, reading time, author card, related posts, social share

2. **Magazine Style**
   - Editorial layout
   - Multi-column content
   - Featured images
   - Features: Featured image, pull quotes, image gallery, category tags

3. **Minimal Elegant**
   - Distraction-free reading
   - Focus on content
   - Subtle imagery
   - Features: Clean typography, subtle images, focus mode, print-friendly

4. **Business Professional**
   - Corporate-friendly design
   - Structured layout
   - Data visualization ready
   - Features: Stats cards, charts, testimonials, CTA sections

5. **Creative Bold**
   - Eye-catching design
   - Vibrant colors
   - Dynamic layouts
   - Features: Animated elements, color blocks, custom fonts, interactive media

### 📸 Image Integration

#### Automatic Image Search
- **Unsplash Integration**: Search thousands of high-quality, free-to-use images
- **Smart Matching**: Images automatically matched to your topic and keywords
- **Curated Fallbacks**: Professional stock photos when API is unavailable

#### Image Sources
- Unsplash (requires API key for full access)
- Pexels (optional)
- Custom URL support
- AI-generated images (future: DALL-E integration)

#### Image Placement
- **Hero images**: Full-width header images
- **Inline images**: Contextual images throughout content
- **Automatic optimization**: Images sized and positioned based on template

## Setup

### 1. Environment Variables (Optional)

For full image search capabilities, add to your `.env.local`:

```bash
# Unsplash API (recommended for image search)
NEXT_PUBLIC_UNSPLASH_ACCESS_KEY=your_unsplash_access_key

# OpenAI API (for AI-generated images - future feature)
OPENAI_API_KEY=your_openai_api_key
```

**Get Unsplash API Key:**
1. Go to https://unsplash.com/developers
2. Create a new application
3. Copy your Access Key
4. Add to `.env.local`

### 2. Backend Updates

Update your blog generation endpoint to support templates and images:

```python
# backend/seo/routes.py

@router.post("/blog/generate")
async def generate_blog(request: BlogGenerateRequest):
    # ... existing code ...
    
    # Add template and image support
    template_id = request.template_id or "premium-modern"
    auto_images = request.auto_images or False
    
    # Generate blog content
    content = await generate_blog_content(...)
    
    # Auto-fetch images if requested
    featured_image = None
    if auto_images:
        featured_image = await fetch_featured_image(
            topic=request.topic,
            keywords=request.keywords
        )
    
    return {
        "title": title,
        "content": content,
        "template_id": template_id,
        "image_url": featured_image,
        # ... other fields
    }
```

## Usage

### In Blog Generation UI

```tsx
import { BlogTemplateSelector } from "@/components/seo/BlogTemplateSelector";
import { ImageSelector } from "@/components/seo/ImageSelector";
import { PremiumBlogPreview } from "@/components/seo/PremiumBlogPreview";

function BlogGenerator() {
  const [templateId, setTemplateId] = useState("premium-modern");
  const [imageUrl, setImageUrl] = useState("");
  const [generated, setGenerated] = useState(null);

  return (
    <div className="space-y-6">
      {/* Template Selection */}
      <BlogTemplateSelector
        selectedTemplate={templateId}
        onSelectTemplate={setTemplateId}
      />

      {/* Image Selection */}
      <ImageSelector
        topic={topic}
        keywords={keywords.split(",")}
        selectedImage={imageUrl}
        onSelectImage={setImageUrl}
      />

      {/* Generate Button */}
      <button onClick={generateBlog}>Generate Premium Blog</button>

      {/* Premium Preview */}
      {generated && (
        <PremiumBlogPreview
          title={generated.title}
          content={generated.content}
          imageUrl={imageUrl}
          metaTitle={generated.meta_title}
          metaDescription={generated.meta_description}
          tags={generated.tags}
          templateId={templateId}
          readingTime={Math.ceil(generated.word_count / 200)}
        />
      )}
    </div>
  );
}
```

### Standalone Preview

```tsx
import { PremiumBlogPreview } from "@/components/seo/PremiumBlogPreview";

<PremiumBlogPreview
  title="How to Grow Your Business with SEO"
  content={markdownContent}
  imageUrl="https://images.unsplash.com/photo-..."
  metaTitle="SEO Growth Strategies | Your Business"
  metaDescription="Learn proven SEO strategies to grow your business..."
  tags={["SEO", "Marketing", "Growth"]}
  templateId="premium-modern"
  author="Your Business Name"
  readingTime={5}
/>
```

## Template Customization

Each template includes:

- **Layout**: Overall page structure
- **Header Style**: Title and hero section design
- **Content Style**: Typography and spacing
- **Image Style**: Image sizing and placement
- **Accent Color**: Primary color scheme

### Customizing Templates

Edit `lib/seo/blogTemplates.ts`:

```typescript
{
  id: "custom-template",
  name: "Custom Template",
  description: "Your custom design",
  preview: "🎯",
  style: {
    layout: "modern",
    headerStyle: "custom-header",
    contentStyle: "wide-margins",
    imageStyle: "full-bleed",
    accentColor: "purple", // emerald, blue, purple, indigo, slate
  },
  features: ["Feature 1", "Feature 2"],
}
```

## Image Best Practices

### Hero Images
- **Dimensions**: 1920x1080 or 16:9 aspect ratio
- **File size**: < 500KB (optimized)
- **Subject**: Relevant to blog topic
- **Quality**: High resolution, professional

### Inline Images
- **Dimensions**: 1200x675 or 16:9 aspect ratio
- **Placement**: Every 300-500 words
- **Relevance**: Directly related to surrounding content

### Image Attribution
When using Unsplash images, attribution is automatically included in the preview. For production:

```html
Photo by <a href="{authorUrl}">{authorName}</a> on 
<a href="https://unsplash.com">Unsplash</a>
```

## Advanced Features

### AI-Generated Images (Coming Soon)

```typescript
import { generateBlogImage } from "@/lib/seo/imageService";

const image = await generateBlogImage(
  "Modern office workspace",
  "photographic" // or "illustration", "abstract", "minimal"
);
```

### Automatic Image Placement

```typescript
import { getRecommendedImagePlacement } from "@/lib/seo/imageService";

const { position, count } = getRecommendedImagePlacement(
  contentLength,
  templateId
);
// position: Character position for first inline image
// count: Total recommended images
```

### Custom Image Sources

Add your own image providers in `lib/seo/imageService.ts`:

```typescript
export async function searchCustomImages(query: string) {
  const response = await fetch(`https://your-api.com/search?q=${query}`);
  const data = await response.json();
  
  return {
    query,
    images: data.results.map(img => ({
      provider: "custom",
      url: img.url,
      thumbnail: img.thumb,
      author: img.photographer,
    })),
  };
}
```

## Export & Publishing

### WordPress
Premium templates are automatically converted to WordPress-compatible HTML with:
- Responsive images
- SEO-optimized markup
- Schema.org structured data
- Social media meta tags

### Shopify
Templates work seamlessly with Shopify blog posts:
- Liquid template compatible
- Theme-aware styling
- Product integration ready

### Static HTML
Export as standalone HTML:

```typescript
const html = generateStaticHTML(blogPost, template);
// Includes all CSS and optimized images
```

## Performance

### Optimization Features
- **Lazy loading**: Images load as user scrolls
- **Responsive images**: Automatic srcset generation
- **CDN-ready**: Unsplash images served via CDN
- **Caching**: Template styles cached client-side

### Loading States
All components include loading states:
- Image gallery loading spinner
- Template preview skeleton
- Progressive image loading

## Troubleshooting

### Images Not Loading
1. Check Unsplash API key in `.env.local`
2. Verify API key has correct permissions
3. Check browser console for CORS errors
4. Fallback images will load automatically

### Template Not Applying
1. Verify `templateId` matches template in `blogTemplates.ts`
2. Check for CSS conflicts
3. Clear browser cache
4. Ensure Tailwind classes are compiled

### Preview Issues
1. Check that content is valid Markdown
2. Verify image URLs are accessible
3. Test with different templates
4. Check browser console for errors

## Examples

### Complete Blog Generation Flow

```tsx
// 1. Select template
<BlogTemplateSelector
  selectedTemplate="premium-modern"
  onSelectTemplate={setTemplate}
/>

// 2. Choose images
<ImageSelector
  topic="Digital Marketing"
  keywords={["SEO", "Content", "Strategy"]}
  selectedImage={imageUrl}
  onSelectImage={setImageUrl}
/>

// 3. Generate content
const result = await seoApi.generateBlog({
  topic: "Digital Marketing Strategies",
  keywords: ["SEO", "Content Marketing"],
  template_id: "premium-modern",
  auto_images: true,
});

// 4. Preview
<PremiumBlogPreview {...result} />

// 5. Save and publish
await seoApi.createPost({
  ...result,
  image_url: imageUrl,
  template_id: "premium-modern",
});
```

## Next Steps

1. **Add more templates**: Create industry-specific templates
2. **AI image generation**: Integrate DALL-E or Midjourney
3. **Video support**: Add video hero sections
4. **Interactive elements**: Charts, graphs, embedded content
5. **A/B testing**: Test different templates for engagement

## Support

For issues or questions:
- Check the troubleshooting section
- Review component documentation
- Test with fallback images
- Verify API keys and environment variables
