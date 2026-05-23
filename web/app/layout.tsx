import type { Metadata } from "next";
import "./globals.css";
import GoogleAnalytics from "@/components/analytics/GoogleAnalytics";

export const metadata: Metadata = {
  title: {
    default: "Zilo — Agent workspace",
    template: "%s · Zilo",
  },
  description:
    "Web-first agent workspace to help teams sell: chat, social, email, ads, and WhatsApp in one place — AI drafts, follow-ups, orders, and the modules you choose.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const measurementId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID || "";

  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="h-full" suppressHydrationWarning>
        {measurementId && <GoogleAnalytics measurementId={measurementId} />}
        {children}
      </body>
    </html>
  );
}
