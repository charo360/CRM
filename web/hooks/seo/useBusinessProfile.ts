import { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";
import type { SeoBusinessContext } from "@/lib/seo/types";

export function useBusinessProfile() {
  const [profile, setProfile] = useState<SeoBusinessContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    seoApi
      .businessContext()
      .then(setProfile)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load profile"))
      .finally(() => setLoading(false));
  }, []);

  return { profile, loading, error };
}
