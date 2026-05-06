"use client";

import React, { useState } from "react";
import { X, ExternalLink, CheckCircle2, Presentation } from "lucide-react";

interface Template {
  id: string;
  name: string;
  description: string;
  tags: string;
  preview_url: string;
}

interface TemplateGalleryProps {
  themes: Template[];
  onSelect: (themeId: string, themeName: string) => void;
  onClose: () => void;
}

export function TemplateGallery({ themes, onSelect, onClose }: TemplateGalleryProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedTheme = themes.find((t) => t.id === selectedId);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-green-50 flex items-center justify-center">
              <Presentation className="w-4 h-4 text-green-700" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-gray-900">Choose a Template</h2>
              <p className="text-xs text-gray-500">Pick a design — I'll fill it with your content</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {themes.map((theme) => {
              const isSelected = selectedId === theme.id;
              const tags = typeof theme.tags === "string"
                ? theme.tags.split(",").map((t) => t.trim()).filter(Boolean).slice(0, 3)
                : [];

              return (
                <div
                  key={theme.id}
                  onClick={() => setSelectedId(theme.id)}
                  className={`group relative border-2 rounded-xl overflow-hidden cursor-pointer transition-all ${
                    isSelected
                      ? "border-green-600 ring-2 ring-green-600/20 shadow-md"
                      : "border-gray-200 hover:border-gray-300 hover:shadow-sm"
                  }`}
                >
                  {/* Preview — iframe pointing directly at 2Slides template URL */}
                  <div className="relative aspect-video bg-gray-100 overflow-hidden">
                    <iframe
                      src={theme.preview_url}
                      title={theme.name}
                      className="w-[200%] h-[200%] -translate-x-1/4 -translate-y-1/4 scale-50 pointer-events-none origin-top-left"
                      sandbox="allow-same-origin allow-scripts"
                      loading="lazy"
                    />
                    {/* Click shield so clicks select the card, not the iframe */}
                    <div className="absolute inset-0" />
                    {/* External link */}
                    <a
                      href={theme.preview_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      title="Open full preview"
                      className="absolute top-2 right-2 p-1.5 bg-white/80 hover:bg-white rounded-md shadow opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <ExternalLink className="w-3.5 h-3.5 text-gray-600" />
                    </a>
                    {/* Selected badge */}
                    {isSelected && (
                      <div className="absolute top-2 left-2 bg-green-600 text-white rounded-full p-0.5">
                        <CheckCircle2 className="w-4 h-4" />
                      </div>
                    )}
                  </div>

                  {/* Info */}
                  <div className="p-3 bg-white">
                    <p className="font-medium text-gray-900 text-sm line-clamp-1 mb-1">{theme.name}</p>
                    {tags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {tags.map((tag, i) => (
                          <span key={i} className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t px-6 py-4 flex items-center justify-between bg-gray-50">
          <p className="text-sm text-gray-500">
            {selectedTheme ? (
              <span>
                Selected: <span className="font-medium text-gray-800">{selectedTheme.name}</span>
              </span>
            ) : (
              "Click a template to select it"
            )}
          </p>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              disabled={!selectedId}
              onClick={() => {
                if (selectedTheme) {
                  onSelect(selectedTheme.id, selectedTheme.name);
                  onClose();
                }
              }}
              className="px-5 py-2 text-sm font-medium text-white bg-green-700 hover:bg-green-800 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg transition-colors"
            >
              Use this template →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
