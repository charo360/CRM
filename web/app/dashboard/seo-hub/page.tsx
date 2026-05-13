import { redirect } from "next/navigation";

/** Legacy URL — SEO Hub is now the "Start here" tab under Website & SEO. */
export default function SeoHubRedirectPage() {
  redirect("/dashboard/seo?tab=hub");
}
