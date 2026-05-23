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

export default function HomePage({
  searchParams,
}: {
  searchParams: { shop?: string; hmac?: string; timestamp?: string; locale?: string };
}) {
  // Shopify App Store install: forward to the backend install handler
  if (searchParams.shop && searchParams.hmac) {
    const apiBase = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/api$/, "").replace(/\/$/, "");
    const backendBase = apiBase || "https://crm-1-pnfo.onrender.com";
    const qs = new URLSearchParams({
      shop: searchParams.shop,
      hmac: searchParams.hmac,
      ...(searchParams.timestamp ? { timestamp: searchParams.timestamp } : {}),
      ...(searchParams.locale ? { locale: searchParams.locale } : {}),
    }).toString();
    redirect(`${backendBase}/api/shopify/install?${qs}`);
  }

  return <LandingPage />;
}
