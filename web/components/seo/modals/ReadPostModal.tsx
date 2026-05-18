import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { BlogPost } from "@/lib/seo/types";

interface ReadPostModalProps {
  post: BlogPost;
  onClose: () => void;
  onPublish?: () => void;
  onRewrite?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}

export function ReadPostModal({ 
  post, 
  onClose, 
  onPublish, 
  onRewrite, 
  onEdit, 
  onDelete 
}: ReadPostModalProps) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-start justify-end p-0 sm:p-4">
      <div className="bg-white w-full sm:w-[680px] h-full sm:h-[calc(100vh-2rem)] sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-start justify-between gap-3 shrink-0">
          <div className="min-w-0">
            <p className="text-base font-bold text-slate-800 leading-snug">{post.title}</p>
            <p className="text-xs text-slate-400 mt-0.5">
              {post.created_at ? new Date(post.created_at).toLocaleDateString() : ""}
              {(post as BlogPost & { word_count?: number }).word_count
                ? ` · ${(post as BlogPost & { word_count?: number }).word_count} words`
                : ""}
              {" · "}
              <span className={`font-medium ${post.status === "published" ? "text-green-600" : "text-slate-500"}`}>
                {post.status}
              </span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 text-2xl leading-none shrink-0 mt-0.5"
          >×</button>
        </div>

        {post.image_url && (
          <div className="w-full overflow-hidden bg-slate-100 border-b border-slate-200">
            <img src={post.image_url} alt={post.title} className="w-full h-56 object-cover" />
          </div>
        )}

        {(post.meta_title || post.meta_description) && (
          <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 shrink-0 space-y-0.5">
            {post.meta_title && (
              <p className="text-xs text-slate-600">
                <span className="font-semibold">Meta title:</span> {post.meta_title}
              </p>
            )}
            {post.meta_description && (
              <p className="text-xs text-slate-500">{post.meta_description}</p>
            )}
            {(post.tags ?? []).length > 0 && (
              <div className="flex gap-1 flex-wrap pt-1">
                {(post.tags ?? []).map(t => (
                  <span key={t} className="text-[10px] bg-emerald-50 text-emerald-700 px-1.5 py-0.5 rounded border border-emerald-100">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 space-y-2">
          {(post.keywords ?? []).length > 0 && (
            <div className="flex flex-wrap gap-2">
              <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wide">Keywords:</span>
              {(post.keywords ?? []).map((kw, idx) => (
                <span key={`${post.id}-preview-keyword-${idx}`} className="text-[11px] px-2 py-1 bg-slate-100 text-slate-600 rounded-full">
                  {kw}
                </span>
              ))}
            </div>
          )}
          {(post as any).calendar_week != null && (
            <p className="text-[10px] text-slate-500 uppercase tracking-wide">
              Calendar post · Week {(post as any).calendar_week}{(post as any).calendar_day ? ` · ${(post as any).calendar_day}` : ""}
            </p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="prose prose-sm prose-slate max-w-none prose-headings:font-semibold prose-h1:text-xl prose-h2:text-base prose-h2:mt-6 prose-p:leading-relaxed prose-li:text-sm prose-p:text-sm">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ children }) => (
                  <div className="my-4 overflow-x-auto rounded-xl border border-slate-200 shadow-sm not-prose">
                    <table className="w-full text-sm border-collapse">{children}</table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide bg-slate-800 text-white whitespace-nowrap">{children}</th>
                ),
                td: ({ children }) => (
                  <td className="px-4 py-2.5 text-slate-700 border-t border-slate-100">{children}</td>
                ),
                tr: ({ children, ...props }) => (
                  <tr className="even:bg-slate-50 odd:bg-white" {...(props as React.HTMLAttributes<HTMLTableRowElement>)}>{children}</tr>
                ),
              }}
            >{post.content}</ReactMarkdown>
          </div>
        </div>

        <div className="px-5 py-3 border-t border-slate-100 flex items-center gap-2 shrink-0 bg-white">
          {post.status !== "published" && onPublish && (
            <button
              onClick={onPublish}
              className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg font-medium hover:bg-emerald-700"
            >
              Publish
            </button>
          )}
          {onRewrite && (
            <button
              onClick={onRewrite}
              className="px-4 py-2 bg-slate-100 text-slate-700 text-sm rounded-lg font-medium hover:bg-slate-200"
            >
              Rewrite
            </button>
          )}
          {onEdit && (
            <button
              onClick={onEdit}
              className="px-3 py-2 bg-slate-100 text-slate-700 text-sm rounded-lg font-medium hover:bg-slate-200"
            >
              Edit Post
            </button>
          )}
          {onDelete && (
            <button
              onClick={onDelete}
              className="px-3 py-2 bg-red-50 text-red-500 text-sm rounded-lg font-medium hover:bg-red-100 ml-auto"
            >
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
