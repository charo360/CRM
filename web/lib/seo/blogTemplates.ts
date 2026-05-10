export interface BlogTemplate {
  id: string;
  name: string;
  description: string;
  preview: string;
  style: {
    layout: "classic" | "modern" | "magazine" | "minimal" | "premium";
    headerStyle: string;
    contentStyle: string;
    imageStyle: string;
    accentColor: string;
  };
  features: string[];
}

export const blogTemplates: BlogTemplate[] = [
  {
    id: "premium-modern",
    name: "Premium Modern",
    description: "Clean, sophisticated design with large hero images and elegant typography",
    preview: "🎨 Modern",
    style: {
      layout: "premium",
      headerStyle: "gradient-header",
      contentStyle: "wide-margins",
      imageStyle: "full-bleed",
      accentColor: "emerald",
    },
    features: ["Hero image", "Reading time", "Author card", "Related posts", "Social share"],
  },
  {
    id: "magazine-style",
    name: "Magazine Style",
    description: "Editorial layout with featured images and multi-column content",
    preview: "📰 Magazine",
    style: {
      layout: "magazine",
      headerStyle: "bold-title",
      contentStyle: "multi-column",
      imageStyle: "featured-large",
      accentColor: "blue",
    },
    features: ["Featured image", "Pull quotes", "Image gallery", "Category tags"],
  },
  {
    id: "minimal-elegant",
    name: "Minimal Elegant",
    description: "Distraction-free reading experience with focus on content",
    preview: "✨ Minimal",
    style: {
      layout: "minimal",
      headerStyle: "simple-title",
      contentStyle: "centered-narrow",
      imageStyle: "inline-medium",
      accentColor: "slate",
    },
    features: ["Clean typography", "Subtle images", "Focus mode", "Print-friendly"],
  },
  {
    id: "business-professional",
    name: "Business Professional",
    description: "Corporate-friendly design with structured layout and data visualization",
    preview: "💼 Business",
    style: {
      layout: "classic",
      headerStyle: "professional",
      contentStyle: "structured",
      imageStyle: "boxed",
      accentColor: "indigo",
    },
    features: ["Stats cards", "Charts", "Testimonials", "CTA sections"],
  },
  {
    id: "creative-bold",
    name: "Creative Bold",
    description: "Eye-catching design with vibrant colors and dynamic layouts",
    preview: "🎭 Creative",
    style: {
      layout: "modern",
      headerStyle: "creative-header",
      contentStyle: "asymmetric",
      imageStyle: "creative-grid",
      accentColor: "purple",
    },
    features: ["Animated elements", "Color blocks", "Custom fonts", "Interactive media"],
  },
];

export function getTemplateById(id: string): BlogTemplate | undefined {
  return blogTemplates.find(t => t.id === id);
}

export function getDefaultTemplate(): BlogTemplate {
  return blogTemplates[0]; // Premium Modern
}
