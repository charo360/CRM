import { redirect } from "next/navigation";

/** Legacy URL — Autoblogging lives under Website & SEO → Autoblog tab. */
export default function BlogRedirectPage() {
  redirect("/dashboard/seo?tab=autoblog");
}
