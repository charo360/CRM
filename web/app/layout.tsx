import type { Metadata } from "next";
import "./globals.css";

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
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="h-full" suppressHydrationWarning>{children}</body>
    </html>
  );
}
