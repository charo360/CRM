import React, { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";
import { splitCommaSeparated } from "@/lib/seo/utils";
import type { BlogPost } from "@/lib/seo/types";

interface EditPostModalProps {
  post: BlogPost;
  onClose: () => void;
  onSave: (updatedPost: BlogPost) => void;
}

export function EditPostModal({ post, onClose, onSave }: EditPostModalProps) {
  const [editTitle, setEditTitle] = useState(post.title);
  const [editContent, setEditContent] = useState(post.content);
  const [editMetaTitle, setEditMetaTitle] = useState(post.meta_title);
  const [editMetaDescription, setEditMetaDescription] = useState(post.meta_description);
  const [editImageUrl, setEditImageUrl] = useState(post.image_url || "");
  const [editKeywords, setEditKeywords] = useState((post.keywords ?? []).join(", "));
  const [editTags, setEditTags] = useState((post.tags ?? []).join(", "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const updated = await seoApi.updatePost(post.id, {
        title: editTitle,
        content: editContent,
        meta_title: editMetaTitle,
        meta_description: editMetaDescription,
        image_url: editImageUrl || undefined,
        keywords: splitCommaSeparated(editKeywords),
        tags: splitCommaSeparated(editTags),
      });
      onSave(updated);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-lg font-bold text-slate-800">Edit Blog Post</p>
            <p className="text-sm text-slate-500">Save changes to the generated blog post content and SEO metadata.</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-xl">×</button>
        </div>

        <div className="grid grid-cols-1 gap-4">
          <div>
            <label className="text-xs font-semibold text-slate-500 mb-1 block">Title</label>
            <input
              value={editTitle}
              onChange={e => setEditTitle(e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 mb-1 block">SEO meta title</label>
            <input
              value={editMetaTitle}
              onChange={e => setEditMetaTitle(e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 mb-1 block">Meta description</label>
            <textarea
              value={editMetaDescription}
              onChange={e => setEditMetaDescription(e.target.value)}
              rows={3}
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 mb-1 block">Featured image URL</label>
            <input
              type="url"
              value={editImageUrl}
              onChange={e => setEditImageUrl(e.target.value)}
              placeholder="https://..."
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <p className="text-xs text-slate-400 mt-1">Optional hero image shown in the premium blog preview.</p>
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 mb-1 block">Keywords (comma-separated)</label>
            <input
              value={editKeywords}
              onChange={e => setEditKeywords(e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <p className="text-xs text-slate-400 mt-1">Add the target keywords that this post should rank for.</p>
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 mb-1 block">Tags (comma-separated)</label>
            <input
              value={editTags}
              onChange={e => setEditTags(e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 mb-1 block">Content</label>
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              rows={12}
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
            />
          </div>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-200"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
