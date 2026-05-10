import React, { useState } from "react";
import { seoApi } from "@/lib/api";

type ImageStyle = "photographic" | "illustration" | "abstract" | "minimal";

const STYLES: { value: ImageStyle; label: string; desc: string; icon: string }[] = [
  { value: "photographic", label: "Photo", desc: "Editorial photography", icon: "📷" },
  { value: "illustration", label: "Illustration", desc: "Modern digital art", icon: "🎨" },
  { value: "abstract",     label: "Abstract",     desc: "Conceptual shapes",  icon: "🌀" },
  { value: "minimal",      label: "Minimal",      desc: "Clean & elegant",    icon: "⬜" },
];

interface ImageSelectorProps {
  topic: string;
  keywords: string[];
  selectedImage: string;
  onSelectImage: (url: string) => void;
  title?: string;
}

export function ImageSelector({ topic, keywords, selectedImage, onSelectImage, title }: ImageSelectorProps) {
  const [style, setStyle] = useState<ImageStyle>("photographic");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generatedImages, setGeneratedImages] = useState<string[]>([]);

  async function generate(overrideStyle?: ImageStyle) {
    const chosenStyle = overrideStyle ?? style;
    if (!topic && !title && keywords.length === 0) {
      setError("Enter a topic or keywords first");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await seoApi.generateBlogImage({
        title: title || topic,
        topic,
        keywords,
        style: chosenStyle,
        quality: "fast",
      });
      onSelectImage(result.image_url);
      setGeneratedImages(prev => [result.image_url, ...prev.slice(0, 3)]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Image generation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      {/* Style picker + generate button */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-slate-500">AI-Generated Image</label>
          <span className="text-[10px] bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full font-medium">
            Gemini
          </span>
        </div>

        <div className="grid grid-cols-4 gap-1.5">
          {STYLES.map(s => (
            <button
              key={s.value}
              type="button"
              onClick={() => { setStyle(s.value); generate(s.value); }}
              disabled={loading}
              className={`flex flex-col items-center gap-1 p-2 rounded-xl border text-center transition-all disabled:opacity-50 ${
                style === s.value
                  ? "border-violet-400 bg-violet-50 text-violet-700"
                  : "border-slate-200 hover:border-violet-300 hover:bg-slate-50 text-slate-600"
              }`}
            >
              <span className="text-lg">{s.icon}</span>
              <span className="text-[10px] font-semibold leading-tight">{s.label}</span>
              <span className="text-[9px] text-slate-400 leading-tight hidden sm:block">{s.desc}</span>
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => generate()}
          disabled={loading || (!topic && !title && keywords.length === 0)}
          className="w-full py-2.5 bg-gradient-to-r from-violet-600 to-purple-600 text-white text-sm rounded-xl hover:from-violet-700 hover:to-purple-700 font-semibold disabled:opacity-50 flex items-center justify-center gap-2 transition-all"
        >
          {loading ? (
            <>
              <span className="animate-spin text-base">⚙</span>
              Generating image…
            </>
          ) : (
            <>
              ✨ Generate {style} image
            </>
          )}
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
      )}

      {/* Selected image preview */}
      {selectedImage && (
        <div className="relative rounded-xl overflow-hidden border-2 border-violet-200">
          <img
            src={selectedImage}
            alt="Generated blog image"
            className="w-full h-48 object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent pointer-events-none" />
          <div className="absolute top-2 right-2 flex gap-2">
            <button
              type="button"
              onClick={() => generate()}
              disabled={loading}
              className="bg-white/90 backdrop-blur-sm text-violet-700 text-xs px-3 py-1.5 rounded-lg hover:bg-white font-semibold shadow-sm disabled:opacity-50"
            >
              {loading ? "…" : "↻ Regenerate"}
            </button>
            <button
              type="button"
              onClick={() => onSelectImage("")}
              className="bg-red-500 text-white text-xs px-2 py-1.5 rounded-lg hover:bg-red-600 font-medium shadow-sm"
            >
              ✕
            </button>
          </div>
          <div className="absolute bottom-2 left-3">
            <span className="bg-black/50 backdrop-blur-sm text-white text-[10px] px-2 py-1 rounded-lg font-medium">
              ✨ Gemini • {style}
            </span>
          </div>
        </div>
      )}

      {/* Recent generations */}
      {generatedImages.length > 1 && (
        <div className="space-y-1">
          <p className="text-[10px] text-slate-400 font-medium">Recent generations — click to use:</p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {generatedImages.map((url, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onSelectImage(url)}
                className={`shrink-0 rounded-lg overflow-hidden border-2 transition-all ${
                  selectedImage === url
                    ? "border-violet-500 ring-2 ring-violet-200"
                    : "border-slate-200 hover:border-violet-300"
                }`}
              >
                <img src={url} alt="" className="w-20 h-14 object-cover" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Hint when nothing generated yet */}
      {!selectedImage && !loading && (
        <p className="text-[10px] text-slate-400 text-center italic">
          Pick a style above — Gemini will create a unique image that matches your blog story
        </p>
      )}
    </div>
  );
}
