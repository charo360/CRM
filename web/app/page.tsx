import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/LandingPage";

export const metadata: Metadata = {
  title: "Zilo — Sell on every channel from one web workspace",
  description:
    "Web-first agent workspace: Shopify on autopilot — store sync, carts, recovery — plus social, email, ads & WhatsApp. AI drafts and follow-ups so selling stays on autopilot; mobile optional.",
  openGraph: {
    title: "Zilo — Sell on every channel from one web workspace",
    description:
      "Shopify 100% on autopilot, selling on autopilot — omnichannel AI agents. Chill while Zilo runs the grind.",
    type: "website",
  },
};

export default function HomePage() {
  return <LandingPage />;
}
