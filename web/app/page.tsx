import type { Metadata } from "next";
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

export default function HomePage() {
  return <LandingPage />;
}
