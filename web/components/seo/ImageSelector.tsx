"use client";

import React from "react";

interface ImageSelectorProps {
  topic: string;
  title?: string;
  keywords: string[];
  selectedImage?: string;
  onSelectImage: (url: string) => void;
}

export default function ImageSelector({
  topic,
  title,
  keywords,
  selectedImage,
  onSelectImage,
}: ImageSelectorProps) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-medium text-slate-700 mb-2">Featured Image</p>
        <p className="text-xs text-slate-500">
          AI image generation is not available. Please provide an image URL manually.
        </p>
      </div>

      <div className="p-4 border border-slate-200 rounded-lg bg-slate-50">
        <p className="text-xs text-slate-400 text-center">
          To add an image, use the "Optional featured image URL" field in the options above.
        </p>
      </div>
    </div>
  );
}
