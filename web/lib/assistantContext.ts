import { assistantApi } from "./api";

export async function getBusinessContext() {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (!token) throw new Error("No auth token");

  const res = await fetch(`${assistantApi.API_BASE}/assistant/context`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }

  return res.json() as Promise<{
    new_customers?: number;
    orders?: number;
    top_product?: string;
    total_revenue_window?: number;
  }>;
}
