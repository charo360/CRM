import { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";
import type { SeoSummary } from "@/lib/api";

export function useSeoSummary(refreshTrigger?: any) {
  const [summary, setSummary] = useState<SeoSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    seoApi
      .summary()
      .then(setSummary)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load summary"))
      .finally(() => setLoading(false));
  }, [refreshTrigger]);

  return { summary, loading, error, refresh: () => setSummary(null) };
}
