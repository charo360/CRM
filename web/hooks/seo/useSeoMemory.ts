import { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";
import type { SeoMemory } from "@/lib/seo/types";

export function useSeoMemory() {
  const [memory, setMemory] = useState<SeoMemory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    seoApi
      .getSeoMemory()
      .then(setMemory)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load memory"))
      .finally(() => setLoading(false));
  }, []);

  return { memory, loading, error };
}
