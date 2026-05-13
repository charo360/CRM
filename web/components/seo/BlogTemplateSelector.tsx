import React, { useState } from "react";
import { blogTemplates, type BlogTemplate } from "@/lib/seo/blogTemplates";

interface BlogTemplateSelectorProps {
  selectedTemplate: string;
  onSelectTemplate: (templateId: string) => void;
}

export function BlogTemplateSelector({ selectedTemplate, onSelectTemplate }: BlogTemplateSelectorProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-semibold text-slate-500">Blog Template</label>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-emerald-600 hover:text-emerald-700 font-medium"
        >
          {expanded ? "Hide templates" : "Browse templates"}
        </button>
      </div>

      {/* Selected template preview */}
      <div className="bg-gradient-to-br from-emerald-50 to-green-50 border border-emerald-200 rounded-xl p-4">
        {blogTemplates.map(template => {
          if (template.id !== selectedTemplate) return null;
          return (
            <div key={template.id} className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{template.preview}</span>
                <div>
                  <p className="text-sm font-bold text-slate-800">{template.name}</p>
                  <p className="text-xs text-slate-600">{template.description}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-1">
                {template.features.map(feature => (
                  <span key={feature} className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">
                    ✓ {feature}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Template grid */}
      {expanded && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
          {blogTemplates.map(template => (
            <button
              key={template.id}
              type="button"
              onClick={() => {
                onSelectTemplate(template.id);
                setExpanded(false);
              }}
              className={`text-left p-4 rounded-xl border-2 transition-all ${
                selectedTemplate === template.id
                  ? "border-emerald-500 bg-emerald-50 shadow-sm"
                  : "border-slate-200 bg-white hover:border-emerald-300 hover:shadow-sm"
              }`}
            >
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{template.preview}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-slate-800 truncate">{template.name}</p>
                    <p className="text-xs text-slate-500 line-clamp-2">{template.description}</p>
                  </div>
                </div>
                
                <div className="flex flex-wrap gap-1">
                  {template.features.slice(0, 3).map(feature => (
                    <span key={feature} className="text-[9px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                      {feature}
                    </span>
                  ))}
                  {template.features.length > 3 && (
                    <span className="text-[9px] text-slate-400 px-1">+{template.features.length - 3}</span>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
