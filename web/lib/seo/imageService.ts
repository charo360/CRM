export interface ImageSource {
  provider: "unsplash" | "pexels" | "pixabay" | "ai-generated";
  url: string;
  thumbnail: string;
  author?: string;
  authorUrl?: string;
  description?: string;
}

export interface ImageSearchResult {
  images: ImageSource[];
  query: string;
}

/**
 * Search for relevant images based on blog topic and keywords
 */
export async function searchBlogImages(
  topic: string,
  keywords: string[],
  count: number = 5
): Promise<ImageSearchResult> {
  // This would integrate with Unsplash, Pexels, or other image APIs
  // For now, return curated free stock photo URLs
  
  const searchQuery = keywords.length > 0 ? keywords[0] : topic;
  
  // Unsplash API integration (requires UNSPLASH_ACCESS_KEY)
  const unsplashKey = process.env.NEXT_PUBLIC_UNSPLASH_ACCESS_KEY;
  
  if (unsplashKey) {
    try {
      const response = await fetch(
        `https://api.unsplash.com/search/photos?query=${encodeURIComponent(searchQuery)}&per_page=${count}&orientation=landscape`,
        {
          headers: {
            Authorization: `Client-ID ${unsplashKey}`,
          },
        }
      );
      
      if (response.ok) {
        const data = await response.json();
        return {
          query: searchQuery,
          images: data.results.map((img: any) => ({
            provider: "unsplash" as const,
            url: img.urls.regular,
            thumbnail: img.urls.small,
            author: img.user.name,
            authorUrl: img.user.links.html,
            description: img.description || img.alt_description,
          })),
        };
      }
    } catch (error) {
      console.error("Unsplash API error:", error);
    }
  }
  
  // Fallback to curated placeholder images
  return getFallbackImages(searchQuery, count);
}

/**
 * Get AI-generated image suggestions based on blog content
 */
export async function generateBlogImage(
  topic: string,
  style: "photographic" | "illustration" | "abstract" | "minimal" = "photographic"
): Promise<ImageSource | null> {
  // This would integrate with DALL-E, Midjourney, or Stable Diffusion
  // For now, return a placeholder
  
  // Example integration with OpenAI DALL-E (requires API key)
  const openaiKey = process.env.OPENAI_API_KEY;
  
  if (openaiKey) {
    try {
      const prompt = generateImagePrompt(topic, style);
      
      // Note: Actual DALL-E integration would go here
      // const response = await openai.images.generate({ prompt, size: "1792x1024" });
      
      console.log("Would generate image with prompt:", prompt);
    } catch (error) {
      console.error("Image generation error:", error);
    }
  }
  
  return null;
}

/**
 * Generate optimized image prompt for AI generation
 */
function generateImagePrompt(topic: string, style: string): string {
  const styleDescriptors = {
    photographic: "professional photography, high quality, sharp focus, natural lighting",
    illustration: "modern illustration, clean lines, vibrant colors, digital art",
    abstract: "abstract design, geometric shapes, modern aesthetic, minimalist",
    minimal: "minimal design, clean background, simple composition, elegant",
  };
  
  return `${topic}, ${styleDescriptors[style as keyof typeof styleDescriptors]}, 16:9 aspect ratio, hero image for blog post`;
}

/**
 * Fallback curated images when APIs are unavailable
 */
function getFallbackImages(query: string, count: number): ImageSearchResult {
  // Curated free stock photos from Unsplash (no API key required for these specific URLs)
  const fallbackImages: ImageSource[] = [
    {
      provider: "unsplash",
      url: "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=1200&h=675&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=400&h=225&fit=crop",
      description: "Professional workspace with laptop and coffee",
    },
    {
      provider: "unsplash",
      url: "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=1200&h=675&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=400&h=225&fit=crop",
      description: "Modern office desk setup",
    },
    {
      provider: "unsplash",
      url: "https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=1200&h=675&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=400&h=225&fit=crop",
      description: "Team collaboration and planning",
    },
    {
      provider: "unsplash",
      url: "https://images.unsplash.com/photo-1552664730-d307ca884978?w=1200&h=675&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1552664730-d307ca884978?w=400&h=225&fit=crop",
      description: "Business meeting and strategy",
    },
    {
      provider: "unsplash",
      url: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1200&h=675&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=400&h=225&fit=crop",
      description: "Data analytics and insights",
    },
  ];
  
  return {
    query,
    images: fallbackImages.slice(0, count),
  };
}

/**
 * Get recommended image for specific blog sections
 */
export function getRecommendedImagePlacement(
  contentLength: number,
  template: string
): { position: number; count: number } {
  // Recommend image placement based on content length and template
  if (contentLength < 500) {
    return { position: 0, count: 1 }; // Just hero image
  } else if (contentLength < 1000) {
    return { position: 300, count: 2 }; // Hero + 1 inline
  } else {
    return { position: 400, count: 3 }; // Hero + 2 inline images
  }
}
