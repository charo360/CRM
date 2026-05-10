import { useState, useEffect, useCallback } from "react";
import { seoApi } from "@/lib/api";
import type { BlogPost } from "@/lib/seo/types";

export function useBlogPosts() {
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPosts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await seoApi.listPosts();
      setPosts(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load posts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPosts();
  }, [loadPosts]);

  const deletePost = useCallback(async (id: string) => {
    if (!confirm("Delete this post?")) return false;
    try {
      await seoApi.deletePost(id);
      setPosts(p => p.filter(x => x.id !== id));
      return true;
    } catch {
      return false;
    }
  }, []);

  const updatePost = useCallback((updatedPost: BlogPost) => {
    setPosts(current => current.map(p => p.id === updatedPost.id ? updatedPost : p));
  }, []);

  return { posts, loading, error, loadPosts, deletePost, updatePost };
}
