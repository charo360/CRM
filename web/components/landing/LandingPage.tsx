"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import {
  Menu,
  X,
  MessageSquare,
  Sparkles,
  BarChart2,
  Megaphone,
  ArrowRight,
  Check,
  ChevronDown,
  Store,
  Mail,
  Share2,
  ShoppingBag,
  AtSign,
  PlayCircle,
  Layers,
  Blocks,
  Terminal,
  Cpu,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ZiloLogo } from "@/components/ZiloLogo";
import { SUPPORTED_INDUSTRIES } from "@/lib/supportedIndustries";

const NAV = [
  { href: "#product", label: "Product" },
  { href: "#benchmark", label: "Compare" },
  { href: "#shopify", label: "Shopify" },
  { href: "#modules", label: "Modules" },
  { href: "#industries", label: "Industries" },
  { href: "#how", label: "How it works" },
  { href: "#pricing", label: "Pricing" },
  { href: "#faq", label: "FAQ" },
];

const OPERATOR_ROWS: { handle: string; avoid: string }[] = [
  {
    handle: "Auto-replies across every channel",
    avoid: "Manually respond to the same questions on WhatsApp, Instagram, email, and DMs",
  },
  {
    handle: "Follow-ups that close deals",
    avoid: "Chase leads and pray they come back",
  },
  {
    handle: "Payment links, invoices, reconciliation",
    avoid: "Track who paid, who didn't, and what your books look like",
  },
  {
    handle: "Social posts, carousels, ad creative",
    avoid: "Stare at a blank content calendar",
  },
  {
    handle: "Meta, Google, and X Ads campaigns",
    avoid: "Learn three ad platforms on top of running a business",
  },
  {
    handle: "Abandoned cart recovery",
    avoid: "Watch revenue walk out the door",
  },
  {
    handle: "Orders, bookings, inventory",
    avoid: "Juggle Shopify, a booking tool, and a spreadsheet",
  },
];

const STEPS = [
  {
    step: "1",
    title: "Open your workspace",
    body: "Sign in on the web. This is your command center — but you won't need to live here.",
  },
  {
    step: "2",
    title: "Connect your channels",
    body: "Link WhatsApp, Instagram, email, Shopify, Stripe, your ad accounts, your calendar. Once.",
  },
  {
    step: "3",
    title: "Write your prompt or set an automation",
    body: '"Follow up with anyone who added to cart but didn\'t buy, offer 10% off, send payment link." Done. Zilo runs this forever.',
  },
];

const MODULE_GROUPS = [
  {
    title: "Revenue & ops",
    items: ["Sales & POS", "Orders & payments", "Invoices & quotes", "Finance / P&L", "Inventory", "Bookings & reservations"],
  },
  {
    title: "Sales & growth",
    items: [
      "Broadcast & follow-ups",
      "Social scheduler & inbox",
      "Meta, Google & X Ads",
      "Google Business Profile",
      "Zilo Chat specialists",
      "Loyalty & NPS",
    ],
  },
  {
    title: "Productivity",
    items: ["Shopify (autopilot store + selling)", "Email inbox", "Calendar", "Imports", "Team & roles"],
  },
];

const CHANNEL_ROWS: { channel: string; does: string }[] = [
  {
    channel: "WhatsApp",
    does: "Auto-replies, broadcast campaigns, payment links, order updates",
  },
  {
    channel: "Instagram & social DMs",
    does: "Unified inbox, suggested replies, comment-to-DM conversion",
  },
  {
    channel: "Email",
    does: "Full Gmail/Outlook inbox, AI drafts, follow-up sequences",
  },
  {
    channel: "Ads",
    does: "Meta, Google, X — creative drafts, campaign planning, performance surface",
  },
  {
    channel: "Shopify",
    does: "Full autopilot: orders, inventory, carts, discounts",
  },
  {
    channel: "Stripe",
    does: "Payments, invoices, reconciliation, finance/P&L",
  },
];

const ANYWHERE_ROWS: { app: string; response: string }[] = [
  {
    app: "WhatsApp",
    response: '"Today\'s sales: KES 124,500. 3 orders in progress. 5 follow-ups due."',
  },
  {
    app: "Instagram DM",
    response: '"Campaign draft ready. Want me to launch?"',
  },
  {
    app: "Email",
    response: "Full P&L attached. Inventory alert flagged.",
  },
];

const REVENUE_LOOP = [
  { title: "Sell", body: "Customer inquires on Instagram" },
  { title: "Auto-reply", body: "Zilo answers, checks inventory, suggests products" },
  { title: "Close", body: "Follow-up sequence if they go quiet" },
  { title: "Pay", body: "Payment link sent, Stripe processed" },
  { title: "Reconcile", body: "Payment matched to order, P&L updated" },
  { title: "Grow", body: "Customer tagged for loyalty, future campaigns" },
];

const FAQS = [
  {
    q: "Do I need to know how to code?",
    a: "No. You connect accounts and write prompts in plain language — or use pre-built automation templates.",
  },
  {
    q: "Does it really work forever from one setup?",
    a: "Yes. Your automations run until you change them. Prompts persist. Zilo operates continuously.",
  },
  {
    q: "What if I want to step in manually?",
    a: "Always. You're in charge. Zilo handles the repeat work; you jump in for strategy, edge cases, and personal touches.",
  },
  {
    q: "Can my team use it too?",
    a: "Yes. Assign roles, control access, route conversations — all from the workspace.",
  },
  {
    q: "What channels does it support?",
    a: "WhatsApp, Instagram, Facebook, email (Gmail/Outlook), Meta Ads, Google Ads, X Ads, Google Business Profile, Shopify, Stripe, and more via integrations.",
  },
  {
    q: "How is this different from a chatbot?",
    a: "Chatbots answer questions. Zilo runs your revenue — it sells, recovers carts, sends invoices, reconciles payments, creates and publishes content, and manages campaigns. It's an operator, not a responder.",
  },
  {
    q: "How is this different from Twin or OpenClaw?",
    a: "Twin is a no-code agent builder — you build the agent yourself. OpenClaw is for developers. Zilo is the finished product: an operator built for selling, pre-integrated, ready on Monday — hosted with no terminal, follow-ups and omnichannel tools packaged for revenue outcomes.",
  },
];

export function LandingPage() {
  const [open, setOpen] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  useEffect(() => {
    if (open) document.body.style.overflow = "hidden";
    else document.body.style.overflow = "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <div className="min-h-screen bg-[#fafbfc] text-slate-900 antialiased">
      <div
        className="pointer-events-none fixed inset-0 -z-10 opacity-[0.4]"
        style={{
          backgroundImage: `
            radial-gradient(ellipse 80% 50% at 50% -20%, rgba(76, 209, 55, 0.14), transparent),
            radial-gradient(ellipse 60% 40% at 100% 0%, rgba(164, 230, 55, 0.1), transparent)
          `,
        }}
      />

      <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <a href="/" className="flex items-center gap-1 font-semibold tracking-tight text-slate-900">
            <ZiloLogo size={36} className="shrink-0" priority />
            <span>Zilo</span>
          </a>

          <nav className="hidden items-center gap-4 xl:flex" aria-label="Primary">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="whitespace-nowrap text-sm font-medium text-slate-600 transition-colors hover:text-brand-dark"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="hidden items-center gap-3 md:flex">
            <Link
              href="/login"
              className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900"
            >
              Log in
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 rounded-xl border border-[#007a2e] bg-[#009B3A] px-4 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-[#4CD137] hover:text-[#0a2614]"
            >
              Free trial
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <button
            type="button"
            className="rounded-lg p-2 text-slate-600 xl:hidden"
            onClick={() => setOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-6 w-6" />
          </button>
        </div>

        {open && (
          <div className="fixed inset-0 z-[60] xl:hidden">
            <button type="button" className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(false)} aria-label="Close menu" />
            <div className="absolute right-0 top-0 flex h-full w-[min(100%,20rem)] flex-col bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4">
                <span className="font-semibold">Menu</span>
                <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-2 text-slate-600" aria-label="Close">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <nav className="flex max-h-[calc(100vh-5rem)] flex-1 flex-col gap-0.5 overflow-y-auto p-4" aria-label="Mobile">
                {NAV.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    className="rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    onClick={() => setOpen(false)}
                  >
                    {item.label}
                  </a>
                ))}
                <hr className="my-2 border-slate-100" />
                <Link href="/login" className="rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={() => setOpen(false)}>
                  Log in
                </Link>
                <Link
                  href="/login"
                  className="mt-2 rounded-xl border border-[#007a2e] bg-[#009B3A] px-3 py-3 text-center text-sm font-semibold text-white shadow-md transition hover:bg-[#4CD137] hover:text-[#0a2614]"
                  onClick={() => setOpen(false)}
                >
                  Free trial
                </Link>
              </nav>
            </div>
          </div>
        )}
      </header>

      <main>
        {/* Hero */}
        <section id="product" className="relative overflow-hidden px-4 pb-16 pt-14 sm:px-6 sm:pt-20 lg:pb-24">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-3xl text-center">
              <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-[#4CD137]/35 bg-[#4CD137]/12 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[#065a24]">
                <Sparkles className="h-3.5 w-3.5 text-[#009B3A]" />
                Zilo
              </p>
              <h1 className="text-balance text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-[3.25rem] lg:leading-[1.1]">
                One prompt runs your entire revenue engine. Forever.
              </h1>
              <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600 sm:text-xl">
                Connect your channels once. Tell Zilo what to do. Then run your business from WhatsApp, Instagram, or wherever you
                already are — while it handles sales, payments, content, ads, and reconciliation around the clock.
              </p>
              <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-4">
                <Link
                  href="/login"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-[#007a2e] bg-[#009B3A] px-8 py-3.5 text-base font-semibold text-white shadow-lg transition hover:bg-[#4CD137] hover:text-[#0a2614] sm:w-auto"
                >
                  Free trial
                  <ArrowRight className="h-5 w-5" />
                </Link>
                <a
                  href="#how"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-8 py-3.5 text-base font-semibold text-slate-900 shadow-sm transition hover:border-[#009B3A]/40 hover:bg-[#f0fdf4] sm:w-auto"
                >
                  <PlayCircle className="h-5 w-5 text-[#009B3A]" aria-hidden />
                  Watch Zilo in Action
                </a>
              </div>
              <p className="mt-6 text-sm font-medium text-slate-500">No code. No terminal. No babysitting.</p>
            </div>

            <div className="relative mx-auto mt-16 max-w-5xl">
              <div className="absolute -inset-4 rounded-3xl bg-gradient-to-br from-brand/20 via-transparent to-emerald-500/15 blur-2xl" />
              <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-xl shadow-slate-900/5">
                <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/80 px-4 py-3">
                  <div className="flex gap-1.5">
                    <span className="h-3 w-3 rounded-full bg-red-400/80" />
                    <span className="h-3 w-3 rounded-full bg-amber-400/80" />
                    <span className="h-3 w-3 rounded-full bg-emerald-400/80" />
                  </div>
                  <span className="ml-2 text-xs font-medium text-slate-500">app.zilo — Overview</span>
                </div>
                <div className="flex flex-wrap gap-1.5 border-b border-slate-100 bg-white px-4 py-2.5">
                  {["WhatsApp", "Instagram", "Email", "Meta Ads", "Google Ads", "X Ads"].map((ch) => (
                    <span
                      key={ch}
                      className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600"
                    >
                      {ch}
                    </span>
                  ))}
                </div>
                <div className="grid gap-0 lg:grid-cols-[1fr_1.1fr]">
                  <div className="border-b border-slate-100 p-6 lg:border-b-0 lg:border-r">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Today</p>
                    <p className="mt-2 text-2xl font-bold text-slate-900">KES 124,500</p>
                    <p className="text-sm text-emerald-600">+12% vs last week</p>
                    <div className="mt-6 space-y-3">
                      {["Follow-ups due", "Orders in progress", "AI drafts ready"].map((label, i) => (
                        <div key={label} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5 text-sm">
                          <span className="text-slate-600">{label}</span>
                          <span className="font-semibold tabular-nums text-slate-900">{[5, 3, 5][i]}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="bg-gradient-to-br from-slate-50 to-brand/5 p-6">
                    <div className="flex items-start gap-3 rounded-xl border border-brand/15 bg-white p-4 shadow-sm">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500 text-white">
                        <MessageSquare className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-slate-500">Suggested reply</p>
                        <p className="mt-1 text-sm leading-relaxed text-slate-700">
                          Yes, we have the blue one in stock — want me to reserve it for you today?
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800">Inventory-aware</span>
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">Your tone</span>
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3">
                      <div className="rounded-xl border border-white/80 bg-white/80 p-3 shadow-sm">
                        <BarChart2 className="h-5 w-5 text-brand" />
                        <p className="mt-2 text-xs font-medium text-slate-500">Analytics</p>
                      </div>
                      <div className="rounded-xl border border-white/80 bg-white/80 p-3 shadow-sm">
                        <Layers className="h-5 w-5 text-brand" />
                        <p className="mt-2 text-xs font-medium text-slate-500">Automations</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Channel touchpoints — visual trust strip */}
        <section className="border-y border-slate-200/80 bg-white py-10" aria-label="Channels you can run from Zilo">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="text-center text-xs font-semibold uppercase tracking-wider text-slate-400">
              Sell through every touchpoint — focus work on the web
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-10 gap-y-4 text-slate-400">
              <span className="flex items-center gap-2 text-sm font-medium text-slate-500">
                <MessageSquare className="h-5 w-5 shrink-0 text-slate-400" aria-hidden /> Chat &amp; WhatsApp
              </span>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-500">
                <Megaphone className="h-5 w-5 shrink-0 text-slate-400" aria-hidden /> Social &amp; ads
              </span>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-500">
                <Mail className="h-5 w-5 shrink-0 text-slate-400" aria-hidden /> Email &amp; broadcast
              </span>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-500">
                <Store className="h-5 w-5 shrink-0 text-slate-400" aria-hidden /> Shops &amp; bookings
              </span>
            </div>
          </div>
        </section>

        <section className="border-y border-slate-200/80 bg-white px-4 py-12 sm:px-6">
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-xl font-semibold text-slate-900 sm:text-2xl">You don&apos;t need a bigger team. You need an operator.</p>
          </div>
        </section>

        {/* What Zilo actually does */}
        <section id="operator" className="scroll-mt-20 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">What Zilo actually does</h2>
              <p className="mt-4 text-lg text-slate-600">
                Not a chatbot. Not another dashboard to babysit. An AI revenue team that works while you live your life.
              </p>
            </div>
            <div className="mt-12 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="grid grid-cols-1 md:grid-cols-2">
                <div className="border-b border-slate-200 bg-slate-900 px-4 py-3 text-sm font-semibold text-white md:border-b-0 md:border-r">
                  Zilo handles
                </div>
                <div className="border-b border-slate-200 bg-slate-900 px-4 py-3 text-sm font-semibold text-white">So you don&apos;t have to</div>
              </div>
              {OPERATOR_ROWS.map((row) => (
                <div key={row.handle} className="grid grid-cols-1 border-b border-slate-100 last:border-0 md:grid-cols-2">
                  <div className="border-b border-slate-100 px-4 py-3 text-sm text-slate-800 md:border-b-0 md:border-r md:border-slate-100">
                    {row.handle}
                  </div>
                  <div className="px-4 py-3 text-sm text-slate-600">{row.avoid}</div>
                </div>
              ))}
            </div>
            <p className="mt-8 text-center text-base font-medium text-[#0a2614]/90">You set the strategy. Zilo does the work.</p>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="scroll-mt-20 border-y border-slate-200/80 bg-slate-50/80 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
              How it works: three steps, no code, never again
            </h2>
            <div className="mt-14 grid gap-8 md:grid-cols-3">
              {STEPS.map((s) => (
                <div key={s.step} className="relative rounded-2xl border border-slate-200/80 bg-white p-8 shadow-sm">
                  <span className="text-4xl font-bold text-brand-light">{s.step}</span>
                  <h3 className="mt-4 text-lg font-semibold text-slate-900">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{s.body}</p>
                </div>
              ))}
            </div>
            <div className="mx-auto mt-16 max-w-3xl rounded-2xl border border-brand/20 bg-white p-8 text-center shadow-sm">
              <h3 className="text-xl font-semibold text-slate-900">Then talk to Zilo from anywhere</h3>
              <p className="mt-3 text-lg leading-relaxed text-slate-600">
                Message it on WhatsApp to check today&apos;s sales. Tell it on Instagram to launch a flash campaign. Email it to
                generate this month&apos;s P&amp;L. Same Zilo. Same business. Any app you&apos;re already on.
              </p>
            </div>
          </div>
        </section>

        {/* Shopify */}
        <section id="shopify" className="scroll-mt-20 px-4 py-12 sm:px-6 sm:py-16">
          <div className="mx-auto max-w-6xl">
            <div className="overflow-hidden rounded-3xl border border-emerald-500/30 bg-gradient-to-br from-emerald-950 via-slate-900 to-brand-ink shadow-2xl shadow-emerald-950/40">
              <div className="grid gap-10 px-6 py-12 sm:px-10 lg:grid-cols-[1.15fr_1fr] lg:items-center lg:gap-14 lg:px-14 lg:py-14">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-emerald-300">
                    <ShoppingBag className="h-3.5 w-3.5" aria-hidden />
                    The Shopify autopilot: proof this isn&apos;t a toy
                  </div>
                  <h2 className="mt-5 text-3xl font-bold leading-tight tracking-tight text-white sm:text-4xl lg:text-[2.35rem] lg:leading-[1.15]">
                    Connect your store once. The operator takes over.
                  </h2>
                  <p className="mt-5 text-lg leading-relaxed text-emerald-50/90">
                    Orders, inventory, customers, and abandoned carts flow into Zilo automatically.
                  </p>
                  <p className="mt-4 text-sm font-medium text-white/90">Then the operator takes over:</p>
                  <Link
                    href="/login"
                    className="mt-8 inline-flex items-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-semibold text-emerald-950 shadow-lg transition hover:bg-emerald-50"
                  >
                    See Shopify Autopilot
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
                <ul className="space-y-4 text-sm leading-relaxed text-emerald-50/95">
                  {[
                    "Abandoned cart recovery — nudges while you're offline",
                    "Inventory-aware replies — \"Yes, we have the blue one in stock — want me to reserve it?\"",
                    "Discounts tied to real data — not guesswork",
                    "Post-purchase follow-ups — reviews, referrals, repeat orders",
                  ].map((line) => (
                    <li key={line} className="flex gap-3">
                      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-500/25 text-emerald-200">
                        <Check className="h-3.5 w-3.5" />
                      </span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <p className="border-t border-white/10 px-6 py-5 text-center text-base italic text-white/90 sm:px-10 lg:px-14">
                &ldquo;You chill, tweak strategy when you want, and let the system sell around the clock.&rdquo;
              </p>
            </div>
          </div>
        </section>

        {/* Compare — Twin vs OpenClaw vs Zilo */}
        <section id="benchmark" className="scroll-mt-20 border-y border-slate-200/80 bg-gradient-to-b from-slate-50 to-white px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-xs font-semibold uppercase tracking-wider text-brand-dark">Benchmark</p>
              <h2 className="mt-2 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
                Agent platforms are not all the same audience
              </h2>
              <p className="mt-4 text-lg text-slate-600">
                If you follow tools like{" "}
                <a
                  href="https://twin.so"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-brand-dark underline decoration-brand/50 underline-offset-2 hover:text-brand-ink"
                >
                  Twin
                </a>{" "}
                or{" "}
                <a
                  href="https://openclaw.ai"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-brand-dark underline decoration-brand/50 underline-offset-2 hover:text-brand-ink"
                >
                  OpenClaw
                </a>
                , here is where <strong className="text-slate-800">Zilo</strong> fits — same agent wave, different job to be done.
              </p>
            </div>

            <div className="mt-12 grid gap-6 lg:grid-cols-3">
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center gap-2 text-slate-500">
                  <Blocks className="h-5 w-5" aria-hidden />
                  <span className="text-xs font-semibold uppercase tracking-wide">Twin.so</span>
                </div>
                <h3 className="mt-3 text-lg font-semibold text-slate-900">No-code company agents</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                  Broad autonomous agents: describe outcomes in plain language, connect APIs and the browser, ship interfaces and
                  workflows across many domains — a horizontal &quot;AI company builder.&quot;
                </p>
                <p className="mt-4 text-xs text-slate-500">
                  Best when you want to automate almost anything and build custom agent surfaces from scratch.
                </p>
                <a
                  href="https://twin.so"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-brand-dark hover:text-brand-ink"
                >
                  twin.so <ExternalLink className="h-3 w-3" />
                </a>
              </article>

              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center gap-2 text-slate-500">
                  <Terminal className="h-5 w-5" aria-hidden />
                  <span className="text-xs font-semibold uppercase tracking-wide">OpenClaw</span>
                </div>
                <h3 className="mt-3 text-lg font-semibold text-slate-900">Dev-first agent gateway</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                  Open-source stack: a gateway, many chat channels, tools (files, shell, browser), memory and skills — powerful for
                  builders who are happy on a machine, in config, and in the repo.
                </p>
                <p className="mt-4 text-xs text-slate-500">Best when you want maximum control and you speak developer.</p>
                <a
                  href="https://openclaw.ai"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-brand-dark hover:text-brand-ink"
                >
                  openclaw.ai <ExternalLink className="h-3 w-3" />
                </a>
              </article>

              <article className="relative rounded-2xl border-2 border-brand/30 bg-gradient-to-b from-brand/10 to-white p-6 shadow-md shadow-brand/5">
                <div className="absolute -top-3 right-4 rounded-full bg-brand-dark px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                  You are here
                </div>
                <div className="flex items-center gap-2 text-brand-dark">
                  <Cpu className="h-5 w-5" aria-hidden />
                  <span className="text-xs font-semibold uppercase tracking-wide">Zilo</span>
                </div>
                <h3 className="mt-3 text-lg font-semibold text-slate-900">Selling-first agents on the web</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                  We host the workspace — no daemon, no terminal. Your team sells from the browser across WhatsApp, social, email, and
                  ads: follow-ups, orders, broadcasts, Zilo Chat, automations — built for revenue, not for hacking the OS.
                </p>
                <p className="mt-4 text-xs font-medium text-brand-ink/80">
                  Same agent direction as OpenClaw (channels + tools), packaged so sellers can ship Monday — on every medium you use.
                </p>
                <Link
                  href="/login"
                  className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand-dark hover:text-brand-ink"
                >
                  Open Zilo <ArrowRight className="h-4 w-4" />
                </Link>
              </article>
            </div>
          </div>
        </section>

        {/* Every channel */}
        <section id="channels" className="scroll-mt-20 border-y border-slate-200/80 bg-white px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Every channel. One operator.</h2>
              <p className="mt-4 text-lg text-slate-600">Stop logging into fifteen things.</p>
            </div>
            <div className="mt-12 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="grid grid-cols-1 bg-slate-900 md:grid-cols-[minmax(0,1fr)_2fr]">
                <div className="border-b border-white/10 px-4 py-3 text-sm font-semibold text-white md:border-b-0 md:border-r md:border-white/10">
                  Channel
                </div>
                <div className="px-4 py-3 text-sm font-semibold text-white">What Zilo does there</div>
              </div>
              {CHANNEL_ROWS.map((row) => (
                <div key={row.channel} className="grid grid-cols-1 border-b border-slate-100 last:border-0 md:grid-cols-[minmax(0,1fr)_2fr]">
                  <div className="border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-900 md:border-b-0 md:border-r md:border-slate-100">
                    {row.channel}
                  </div>
                  <div className="px-4 py-3 text-sm text-slate-600">{row.does}</div>
                </div>
              ))}
            </div>
            <p className="mt-8 text-center text-base font-medium text-slate-700">You don&apos;t open each app. Zilo works across all of them.</p>
          </div>
        </section>

        {/* Content & ads */}
        <section id="content" className="scroll-mt-20 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:items-center">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
                  <Megaphone className="h-3.5 w-3.5 text-brand-dark" aria-hidden />
                  Content &amp; ads
                </div>
                <h2 className="mt-4 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Content and ads: from blank page to published</h2>
                <p className="mt-4 text-lg text-slate-600">
                  Tell Zilo: &ldquo;Create three Instagram posts about our new summer menu, make a carousel for Facebook, and draft a
                  Google Ad for the same campaign.&rdquo;
                </p>
                <p className="mt-4 text-base text-slate-700">It generates. You approve. It publishes and schedules.</p>
              </div>
              <ul className="space-y-3 rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
                {[
                  "Social posts, carousels, reels concepts",
                  "Ad creative across Meta, Google, X",
                  "Brand-aware copy that matches your tone",
                  "Video flows via Shotstack + Kling",
                ].map((line) => (
                  <li key={line} className="flex gap-3 text-sm text-slate-700">
                    <Check className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" />
                    {line}
                  </li>
                ))}
                <li className="pt-2 text-sm font-semibold text-slate-900">Your creative team. In one prompt.</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Revenue loop */}
        <section id="loop" className="scroll-mt-20 border-y border-slate-200/80 bg-gradient-to-b from-slate-50 to-white px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">The full revenue loop: sell → get paid → know your numbers</h2>
              <p className="mt-4 text-lg text-slate-600">Most tools stop at &ldquo;message sent.&rdquo; Zilo closes the loop.</p>
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {REVENUE_LOOP.map((step, i) => (
                <div key={step.title} className="relative rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <span className="text-xs font-bold uppercase tracking-wide text-brand-dark">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-2 text-lg font-semibold text-slate-900">{step.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{step.body}</p>
                </div>
              ))}
            </div>
            <p className="mt-10 text-center text-base font-medium text-slate-700">No manual steps. No missed money.</p>
          </div>
        </section>

        {/* Modules — workspace + grouped features */}
        <section id="modules" className="scroll-mt-20 border-y border-slate-200/80 bg-white px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="grid gap-12 lg:grid-cols-2 lg:items-start">
              <div>
                <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Your workspace, your channels</h2>
                <p className="mt-4 text-lg text-slate-600">
                  Turn on only the surfaces you sell through — Social Inbox, Ads, Email, Broadcast, WhatsApp — from{" "}
                  <strong className="text-slate-800">Features</strong>. The web dashboard stays fast and focused on helping you convert.
                </p>
                <ul className="mt-8 space-y-4">
                  {[
                    "Presets: Starter, Business, Personal — match how you sell",
                    "Industry-aware labels (shop, menu, services…)",
                    "Core workspace: Overview, Zilo Chat, Automations, Integrations",
                  ].map((t) => (
                    <li key={t} className="flex gap-3 text-slate-700">
                      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                        <Check className="h-3.5 w-3.5" />
                      </span>
                      {t}
                    </li>
                  ))}
                </ul>
                <Link href="/login" className="mt-10 inline-flex items-center gap-2 font-semibold text-brand-dark hover:text-brand-ink">
                  Open the web workspace
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
              <div className="space-y-4">
                {MODULE_GROUPS.map((g) => (
                  <div key={g.title} className="rounded-2xl border border-slate-200 bg-slate-50/50 p-6">
                    <p className="text-sm font-semibold text-brand-dark">{g.title}</p>
                    <ul className="mt-3 flex flex-wrap gap-2">
                      {g.items.map((item) => (
                        <li
                          key={item}
                          className="rounded-lg border border-slate-200/80 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm"
                        >
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Works for how you work */}
        <section id="work" className="scroll-mt-20 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Works for how you work</h2>
              <p className="mt-4 text-lg text-slate-600">Zilo adapts to your business, not the other way around.</p>
            </div>
            <ul className="mx-auto mt-12 max-w-3xl space-y-6 text-left">
              <li className="flex gap-3">
                <Check className="mt-1 h-5 w-5 shrink-0 text-emerald-500" />
                <p className="text-slate-700">
                  <strong className="text-slate-900">Choose your type at signup</strong> — labels, catalog, and defaults shift to your
                  world: Retail gets &ldquo;Shop.&rdquo; Restaurants get &ldquo;Menu.&rdquo; Salons get &ldquo;Services&rdquo; and &ldquo;Bookings.&rdquo;
                </p>
              </li>
              <li className="flex gap-3">
                <Check className="mt-1 h-5 w-5 shrink-0 text-emerald-500" />
                <p className="text-slate-700">
                  <strong className="text-slate-900">Enable only what you use</strong> — toggle modules from Features. Your workspace stays
                  fast and focused. No clutter.
                </p>
              </li>
              <li className="flex gap-3">
                <Check className="mt-1 h-5 w-5 shrink-0 text-emerald-500" />
                <p className="text-slate-700">
                  <strong className="text-slate-900">20+ industries supported</strong> — Retail, wholesale, restaurants, hotels, salons,
                  clinics, freelancers, creators, and more.
                </p>
              </li>
            </ul>
          </div>
        </section>

        {/* Industries */}
        <section id="industries" className="scroll-mt-20 border-y border-slate-200/80 bg-slate-50/80 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
                <Store className="h-3.5 w-3.5 text-brand-dark" aria-hidden />
                Business types
              </div>
              <h2 className="mt-4 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Every industry we support</h2>
              <p className="mt-4 text-lg text-slate-600">
                Pick your type at signup — the app adjusts labels, bookings, catalog, and defaults so the workspace feels built for you.
              </p>
            </div>
            <div className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {SUPPORTED_INDUSTRIES.map((row) => (
                <div
                  key={row.id}
                  className="flex gap-3 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm transition hover:border-brand/30 hover:shadow-md"
                >
                  <span className="text-2xl leading-none" aria-hidden>
                    {row.emoji}
                  </span>
                  <div className="min-w-0">
                    <p className="font-semibold text-slate-900">{row.label}</p>
                    <p className="mt-0.5 text-xs leading-snug text-slate-500">{row.blurb}</p>
                  </div>
                </div>
              ))}
            </div>
            <p className="mx-auto mt-10 max-w-2xl text-center text-sm text-slate-500">
              Don&apos;t see a perfect fit? Choose <strong className="text-slate-700">General / other</strong> — you can still enable every
              module.
            </p>
          </div>
        </section>

        {/* Talk from anywhere */}
        <section id="anywhere" className="scroll-mt-20 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <div className="inline-flex items-center gap-2 text-brand-dark">
                <AtSign className="h-5 w-5" aria-hidden />
                <Share2 className="h-5 w-5" aria-hidden />
              </div>
              <h2 className="mt-4 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Talk to Zilo from wherever you already are</h2>
              <p className="mt-4 text-lg font-medium text-slate-700">This is the part that changes everything.</p>
            </div>
            <div className="mt-12 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="grid grid-cols-1 bg-slate-900 md:grid-cols-[minmax(0,1fr)_2fr]">
                <div className="border-b border-white/10 px-4 py-3 text-sm font-semibold text-white md:border-b-0 md:border-r md:border-white/10">
                  You message Zilo on
                </div>
                <div className="px-4 py-3 text-sm font-semibold text-white">Zilo responds with</div>
              </div>
              {ANYWHERE_ROWS.map((row) => (
                <div key={row.app} className="grid grid-cols-1 border-b border-slate-100 last:border-0 md:grid-cols-[minmax(0,1fr)_2fr]">
                  <div className="border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-900 md:border-b-0 md:border-r md:border-slate-100">
                    {row.app}
                  </div>
                  <div className="px-4 py-3 text-sm text-slate-600">{row.response}</div>
                </div>
              ))}
            </div>
            <p className="mt-8 text-center text-base text-slate-600">
              You don&apos;t learn a new platform. You don&apos;t sit at a dashboard. You talk to your business like you talk to your best
              employee.
            </p>
          </div>
        </section>

        {/* Built for real businesses */}
        <section id="built" className="scroll-mt-20 border-y border-slate-200/80 bg-slate-900 px-4 py-16 text-white sm:px-6">
          <div className="mx-auto max-w-6xl">
            <h2 className="text-center text-2xl font-bold sm:text-3xl">Built for real businesses</h2>
            <ul className="mx-auto mt-10 grid max-w-4xl gap-4 text-sm text-slate-300 sm:grid-cols-2">
              <li className="flex gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                Team roles &amp; permissions — control who does what
              </li>
              <li className="flex gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                Audit-friendly — every action logged
              </li>
              <li className="flex gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                Imports — bring your existing data
              </li>
              <li className="flex gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                Integrations that matter — Shopify, Stripe, Gmail/Outlook, Klaviyo, Mailchimp, Slack, Notion, Telegram, and more
              </li>
            </ul>
            <div className="mt-10 flex justify-center">
              <Link
                href="/login"
                className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-2.5 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
              >
                Create account
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>

        {/* Pricing — screenshot: Starter $49/5k, Growth $79/10k, Pro $200/25k */}
        <section id="pricing" className="scroll-mt-20 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Plans</h2>
              <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-600">
                Simple pricing. Regional-adjusted. No surprises.
              </p>
            </div>
            <div className="mt-12 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                <thead>
                  <tr className="bg-[#0f172a] text-white">
                    <th className="px-4 py-4 font-semibold"> </th>
                    <th className="px-4 py-4 font-semibold">Starter</th>
                    <th className="bg-sky-900/60 px-4 py-4 font-semibold">Growth</th>
                    <th className="px-4 py-4 font-semibold">Pro</th>
                  </tr>
                </thead>
                <tbody className="text-slate-700">
                  <tr className="border-b border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">Price</td>
                    <td className="px-4 py-3">$49/mo</td>
                    <td className="bg-sky-50 px-4 py-3 font-medium">$79/mo</td>
                    <td className="px-4 py-3">$200/mo</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">Messages</td>
                    <td className="px-4 py-3">5,000</td>
                    <td className="bg-sky-50 px-4 py-3">10,000</td>
                    <td className="px-4 py-3">25,000</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">Customers</td>
                    <td className="px-4 py-3">Unlimited</td>
                    <td className="bg-sky-50 px-4 py-3">Unlimited</td>
                    <td className="px-4 py-3">Unlimited</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">AI replies</td>
                    <td className="px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                    <td className="bg-sky-50 px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                    <td className="px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">Follow-ups &amp; broadcasts</td>
                    <td className="px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                    <td className="bg-sky-50 px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                    <td className="px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">Priority support</td>
                    <td className="px-4 py-3 text-slate-400">—</td>
                    <td className="bg-sky-50 px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                    <td className="px-4 py-3 text-slate-400">—</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">Dedicated support</td>
                    <td className="px-4 py-3 text-slate-400">—</td>
                    <td className="bg-sky-50 px-4 py-3 text-slate-400">—</td>
                    <td className="px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">Advanced analytics</td>
                    <td className="px-4 py-3 text-slate-400">—</td>
                    <td className="bg-sky-50 px-4 py-3 text-slate-400">—</td>
                    <td className="px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                  </tr>
                  <tr>
                    <td className="px-4 py-3 font-medium text-slate-900">Custom templates</td>
                    <td className="px-4 py-3 text-slate-400">—</td>
                    <td className="bg-sky-50 px-4 py-3 text-slate-400">—</td>
                    <td className="px-4 py-3">
                      <Check className="inline h-4 w-4 text-emerald-500" aria-label="Yes" />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-4 text-center text-xs text-slate-500">USD shown as reference; regional pricing applies at checkout.</p>
            <div className="mt-10 flex justify-center">
              <Link
                href="/plans"
                className="inline-flex items-center gap-2 rounded-xl border border-[#007a2e] bg-[#009B3A] px-8 py-3 text-sm font-semibold text-white shadow-md transition hover:bg-[#4CD137] hover:text-[#0a2614]"
              >
                View all plans
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="scroll-mt-20 border-t border-slate-200/80 bg-white px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-3xl">
            <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Frequently asked questions</h2>
            <div className="mt-12 space-y-2">
              {FAQS.map((item, i) => (
                <div key={item.q} className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50/50">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-sm font-semibold text-slate-900"
                    onClick={() => setOpenFaq(openFaq === i ? null : i)}
                    aria-expanded={openFaq === i}
                  >
                    {item.q}
                    <ChevronDown className={cn("h-5 w-5 shrink-0 text-slate-400 transition", openFaq === i && "rotate-180")} />
                  </button>
                  {openFaq === i && (
                    <div className="border-t border-slate-200/80 px-5 pb-4 pt-0">
                      <p className="text-sm leading-relaxed text-slate-600">{item.a}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="px-4 pb-24 pt-4 sm:px-6">
          <div className="mx-auto max-w-4xl overflow-hidden rounded-3xl border border-[#007a2e] bg-gradient-to-br from-[#009B3A] via-[#067c30] to-[#4CD137] px-8 py-16 text-center shadow-xl shadow-[#0a2614]/20">
            <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">One prompt runs your entire revenue engine.</h2>
            <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-white/95">
              Connect your channels. Tell Zilo what to do. Run your business from any app you&apos;re already on.
            </p>
            <p className="mt-3 text-sm text-white/85">No code. No terminal. No babysitting.</p>
            <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row sm:gap-6">
              <Link
                href="/login"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-white/30 bg-white px-8 py-3.5 text-base font-semibold text-[#0a2614] shadow-lg transition hover:bg-[#f0fdf4] sm:w-auto"
              >
                Start free trial
                <ArrowRight className="h-5 w-5 shrink-0" />
              </Link>
              <a
                href="#how"
                className="inline-flex w-full items-center justify-center rounded-xl border border-white/40 bg-white/10 px-8 py-3.5 text-base font-semibold text-white backdrop-blur-sm transition hover:bg-white/20 sm:w-auto"
              >
                See How It Works
              </a>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-200 bg-white px-4 py-12 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-8 md:flex-row md:items-start">
          <div className="flex flex-col items-center md:items-start">
            <div className="flex items-center gap-1 font-semibold text-slate-900">
              <ZiloLogo size={32} className="shrink-0" />
              <span>Zilo</span>
            </div>
            <p className="mt-3 max-w-xs text-center text-sm text-slate-500 md:text-left">
              One prompt runs your revenue engine — from WhatsApp, Instagram, email, and the channels you already use.
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-8 text-sm md:justify-end">
            <div>
              <p className="font-semibold text-slate-900">Product</p>
              <ul className="mt-3 space-y-2 text-slate-600">
                <li>
                  <a href="#benchmark" className="hover:text-brand-dark">
                    Compare (Twin · OpenClaw)
                  </a>
                </li>
                <li>
                  <a href="#shopify" className="hover:text-brand-dark">
                    Shopify autopilot
                  </a>
                </li>
                <li>
                  <a href="#modules" className="hover:text-brand-dark">
                    Modules
                  </a>
                </li>
                <li>
                  <a href="#loop" className="hover:text-brand-dark">
                    Revenue loop
                  </a>
                </li>
                <li>
                  <a href="#industries" className="hover:text-brand-dark">
                    Industries
                  </a>
                </li>
                <li>
                  <a href="#pricing" className="hover:text-brand-dark">
                    Pricing
                  </a>
                </li>
                <li>
                  <Link href="/login" className="hover:text-brand-dark">
                    Log in
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-slate-900">App</p>
              <ul className="mt-3 space-y-2 text-slate-600">
                <li>
                  <Link href="/dashboard" className="hover:text-brand-dark">
                    Dashboard
                  </Link>
                </li>
                <li>
                  <Link href="/login" className="hover:text-brand-dark">
                    Sign up
                  </Link>
                </li>
              </ul>
            </div>
          </div>
        </div>
        <div className="mx-auto mt-12 max-w-6xl border-t border-slate-100 pt-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-left text-xs text-slate-500">
              <Link href="/privacy-policy" className="hover:text-brand-dark">
                Privacy Policy
              </Link>
              <Link href="/terms" className="hover:text-brand-dark">
                Terms &amp; Conditions
              </Link>
            </div>
            <p className="text-left text-xs text-slate-400 sm:text-right">
              © {new Date().getFullYear()} Zilo. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
