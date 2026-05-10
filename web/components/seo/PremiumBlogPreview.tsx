import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getTemplateById, getDefaultTemplate } from "@/lib/seo/blogTemplates";

interface PremiumBlogPreviewProps {
  title: string;
  content: string;
  imageUrl?: string;
  metaTitle?: string;
  metaDescription?: string;
  tags?: string[];
  templateId?: string;
  author?: string;
  readingTime?: number;
}

export function PremiumBlogPreview({
  title,
  content,
  imageUrl,
  metaTitle,
  metaDescription,
  tags = [],
  templateId,
  author = "Your Business",
  readingTime,
}: PremiumBlogPreviewProps) {
  const template = templateId ? getTemplateById(templateId) : getDefaultTemplate();
  const accentColor = template?.style.accentColor || "emerald";

  const colorClasses = {
    emerald: "from-emerald-600 to-green-600",
    blue: "from-blue-600 to-cyan-600",
    purple: "from-purple-600 to-pink-600",
    indigo: "from-indigo-600 to-blue-600",
    slate: "from-slate-600 to-gray-600",
  };

  const gradientClass = colorClasses[accentColor as keyof typeof colorClasses] || colorClasses.emerald;

  return (
    <div className="bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-200">
      {/* Hero Section */}
      {imageUrl && (
        <div className="relative h-80 overflow-hidden">
          <img 
            src={imageUrl} 
            alt={title} 
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />
          
          {/* Title overlay on image */}
          <div className="absolute bottom-0 left-0 right-0 p-8 text-white">
            <div className="max-w-4xl mx-auto">
              {tags.length > 0 && (
                <div className="flex gap-2 mb-3">
                  {tags.slice(0, 3).map(tag => (
                    <span key={tag} className="text-xs bg-white/20 backdrop-blur-sm px-3 py-1 rounded-full border border-white/30">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              <h1 className="text-4xl font-bold mb-3 leading-tight">{title}</h1>
              <div className="flex items-center gap-4 text-sm">
                <span className="flex items-center gap-2">
                  <span className="w-8 h-8 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
                    ✍️
                  </span>
                  {author}
                </span>
                {readingTime && (
                  <span className="flex items-center gap-1">
                    <span>📖</span>
                    {readingTime} min read
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Header without image */}
      {!imageUrl && (
        <div className={`bg-gradient-to-br ${gradientClass} p-12 text-white`}>
          <div className="max-w-4xl mx-auto">
            {tags.length > 0 && (
              <div className="flex gap-2 mb-4">
                {tags.slice(0, 3).map(tag => (
                  <span key={tag} className="text-xs bg-white/20 backdrop-blur-sm px-3 py-1 rounded-full border border-white/30">
                    {tag}
                  </span>
                ))}
              </div>
            )}
            <h1 className="text-5xl font-bold mb-4 leading-tight">{title}</h1>
            {metaDescription && (
              <p className="text-xl text-white/90 leading-relaxed">{metaDescription}</p>
            )}
            <div className="flex items-center gap-4 text-sm mt-6">
              <span className="flex items-center gap-2">
                <span className="w-8 h-8 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
                  ✍️
                </span>
                {author}
              </span>
              {readingTime && (
                <span className="flex items-center gap-1">
                  <span>📖</span>
                  {readingTime} min read
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Meta info bar */}
      {metaTitle && metaDescription && (
        <div className="bg-slate-50 border-b border-slate-200 px-8 py-4">
          <div className="max-w-4xl mx-auto">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">SEO Preview</p>
            <p className="text-sm font-medium text-blue-600">{metaTitle}</p>
            <p className="text-xs text-slate-600 mt-1">{metaDescription}</p>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="px-8 py-12">
        <article className="max-w-4xl mx-auto">
          <div className="prose prose-lg prose-slate max-w-none
            prose-headings:font-bold prose-headings:tracking-tight
            prose-h1:text-4xl prose-h1:mb-6 prose-h1:mt-8
            prose-h2:text-3xl prose-h2:mb-4 prose-h2:mt-8 prose-h2:border-b prose-h2:border-slate-200 prose-h2:pb-2
            prose-h3:text-2xl prose-h3:mb-3 prose-h3:mt-6
            prose-p:text-lg prose-p:leading-relaxed prose-p:mb-6 prose-p:text-slate-700
            prose-a:text-emerald-600 prose-a:no-underline hover:prose-a:underline
            prose-strong:text-slate-900 prose-strong:font-semibold
            prose-ul:my-6 prose-ol:my-6
            prose-li:text-lg prose-li:leading-relaxed prose-li:mb-2 prose-li:text-slate-700
            prose-blockquote:border-l-4 prose-blockquote:border-emerald-500 prose-blockquote:bg-emerald-50 prose-blockquote:py-4 prose-blockquote:px-6 prose-blockquote:my-6 prose-blockquote:rounded-r-lg
            prose-code:bg-slate-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:text-slate-800
            prose-pre:bg-slate-900 prose-pre:text-slate-100 prose-pre:rounded-xl prose-pre:p-6
            prose-img:rounded-xl prose-img:shadow-lg prose-img:my-8"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>

          {/* Call to action */}
          <div className={`mt-12 p-8 bg-gradient-to-br ${gradientClass} rounded-2xl text-white`}>
            <div className="text-center">
              <h3 className="text-2xl font-bold mb-3">Ready to get started?</h3>
              <p className="text-lg mb-6 text-white/90">Contact us today to learn more about our services.</p>
              <button className="bg-white text-slate-900 px-8 py-3 rounded-xl font-semibold hover:bg-slate-100 transition-colors shadow-lg">
                Get in Touch
              </button>
            </div>
          </div>

          {/* Tags footer */}
          {tags.length > 0 && (
            <div className="mt-8 pt-8 border-t border-slate-200">
              <p className="text-sm font-semibold text-slate-600 mb-3">Related Topics:</p>
              <div className="flex flex-wrap gap-2">
                {tags.map(tag => (
                  <span key={tag} className="text-sm bg-slate-100 text-slate-700 px-4 py-2 rounded-full hover:bg-slate-200 transition-colors cursor-pointer">
                    #{tag}
                  </span>
                ))}
              </div>
            </div>
          )}
        </article>
      </div>

      {/* Author card */}
      <div className="bg-slate-50 border-t border-slate-200 px-8 py-8">
        <div className="max-w-4xl mx-auto flex items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-emerald-400 to-green-500 flex items-center justify-center text-white text-2xl font-bold">
            {author.charAt(0)}
          </div>
          <div className="flex-1">
            <p className="font-semibold text-slate-800">{author}</p>
            <p className="text-sm text-slate-600">Creating valuable content to help your business grow.</p>
          </div>
          <div className="flex gap-2">
            <button className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center hover:bg-slate-100 transition-colors">
              <span className="text-sm">🔗</span>
            </button>
            <button className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center hover:bg-slate-100 transition-colors">
              <span className="text-sm">📧</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
