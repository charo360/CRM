import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { LandingPage } from "@/components/landing/LandingPage";

export const metadata: Metadata = {
  title: "Zilo — One prompt runs your entire revenue engine",
  description:
    "Connect your channels once. Tell Zilo what to do. Run your business from WhatsApp, Instagram, or wherever you already are — sales, payments, content, ads, and reconciliation around the clock.",
  openGraph: {
    title: "Zilo — One prompt runs your entire revenue engine",
    description:
      "Not a chatbot. An AI revenue team that works while you live your life. Connect once, automate forever.",
    type: "website",
  },
};

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ shop?: string; hmac?: string; timestamp?: string; locale?: string }>;
}) {
  const sp = await searchParams;
  // Shopify App Store install: forward to the backend install handler
  if (sp.shop && sp.hmac) {
    const apiBase = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/api$/, "").replace(/\/$/, "");
    const backendBase = apiBase || "https://crm-1-pnfo.onrender.com";
    const qs = new URLSearchParams({
      shop: sp.shop,
      hmac: sp.hmac,
      ...(sp.timestamp ? { timestamp: sp.timestamp } : {}),
      ...(sp.locale ? { locale: sp.locale } : {}),
    }).toString();
    redirect(`${backendBase}/api/shopify/install?${qs}`);
  }

  return <LandingPage />;
}
