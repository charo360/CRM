"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import {
  Menu,
  X,
  MessageSquare,
  Sparkles,
  Bell,
  LayoutDashboard,
  Layers,
  BarChart2,
  Megaphone,
  Shield,
  ArrowRight,
  Check,
  ChevronDown,
  Workflow,
  Plug,
  Store,
  Mail,
  Terminal,
  Blocks,
  Cpu,
  ExternalLink,
  Share2,
  ShoppingBag,
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

const FEATURES = [
  {
    icon: Share2,
    title: "Sell on every channel",
    description:
      "WhatsApp, social DMs, email, and ad surfaces in one workspace — respond, close, and plan campaigns so attention turns into revenue, not another tab.",
    accent: "from-emerald-500/15 to-emerald-600/5",
  },
  {
    icon: Sparkles,
    title: "Zilo Chat & AI drafts",
    description:
      "Draft replies that sound like you and move deals forward — across chat, email, and campaigns — so your team spends time selling, not typing.",
    accent: "from-brand/15 to-brand/5",
  },
  {
    icon: Bell,
    title: "Smart follow-ups",
    description:
      "Prioritized queues and reminders so hot leads do not go cold — tuned to help you close, not just clear an inbox.",
    accent: "from-amber-500/15 to-orange-500/5",
  },
  {
    icon: LayoutDashboard,
    title: "One web workspace",
    description:
      "The browser is home base: orders, bookings, invoices, analytics — sell and operate from the dashboard your team opens every day.",
    accent: "from-sky-500/15 to-blue-500/5",
  },
  {
    icon: Workflow,
    title: "Automations",
    description:
      "Trigger follow-ups and handoffs across channels — less manual chasing, more conversations that convert.",
    accent: "from-fuchsia-500/15 to-pink-500/5",
  },
  {
    icon: Plug,
    title: "Integrations",
    description:
      "Shopify connects deep — store sync, orders, abandoned carts, discounts — then AI + automations keep pipelines moving. Plus calendar, email, Meta, Google & X Ads, social tools, and GBP in one flow.",
    accent: "from-teal-500/15 to-cyan-500/5",
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

const STEPS = [
  {
    step: "01",
    title: "Open the web workspace",
    body: "Sign in on the web (email or WhatsApp). That is your home for selling — full screen, full modules, built for daily focus.",
  },
  {
    step: "02",
    title: "Turn on how you sell and grow",
    body: "Use Features to enable pipeline tools (Messages, Customers) and growth surfaces (Broadcast, Ads, Social) — only what your team will run weekly.",
  },
  {
    step: "03",
    title: "Connect every channel",
    body: "Link WhatsApp plus social, email, calendar, Shopify, and ad accounts. Your agents and AI drafts work across all media.",
  },
];

const PLANS = [
  {
    id: "starter",
    name: "Starter",
    usd: 10,
    blurb: "Solo operators getting started",
    features: ["2,500 messages/month", "Unlimited customers", "Follow-ups & broadcasts", "AI replies"],
    highlighted: false,
  },
  {
    id: "growth",
    name: "Growth",
    usd: 18,
    blurb: "Teams that need room to scale",
    features: [
      "5,000 messages/month",
      "Unlimited customers",
      "Follow-ups & broadcasts",
      "AI replies",
      "Priority support",
    ],
    highlighted: true,
  },
  {
    id: "pro",
    name: "Pro",
    usd: 28,
    blurb: "High volume & advanced needs",
    features: [
      "10,000 messages/month",
      "Unlimited customers",
      "Advanced analytics",
      "Custom templates",
      "Dedicated support",
    ],
    highlighted: false,
  },
];

const FAQS = [
  {
    q: "How is Zilo different from Twin or OpenClaw?",
    a: "Twin is a broad no-code platform for building autonomous agents across many domains. OpenClaw is a developer-oriented agent gateway you run yourself. Zilo is built for teams whose job is to sell: a hosted web workspace with agents, follow-ups, orders, and omnichannel tools (social, email, ads, WhatsApp) — no terminal, packaged for operators who want revenue outcomes, not infrastructure projects.",
  },
  {
    q: "Is Zilo only for WhatsApp?",
    a: "No. WhatsApp is one important channel, but Zilo is designed for selling across media — Social Inbox, Messages, Email, Broadcast, Meta & Google Ads, and more. The web dashboard is where your team focuses; mobile is optional for the field.",
  },
  {
    q: "Do I need WhatsApp to use Zilo?",
    a: "No. Sign in on the web with email and use the full workspace. Add WhatsApp under Integrations when you want chat commerce — alongside social, email, and ads as you connect them.",
  },
  {
    q: "Can I hide modules I do not use?",
    a: "Yes. Open Features in your workspace and choose a preset (e.g. Starter, Business, Personal) or toggle individual sidebar items. Your workspace always keeps core tools like Overview, Zilo Chat, Automations, and Settings.",
  },
  {
    q: "What does “Shopify 100% autopilot” mean?",
    a: "Connect your Shopify store once in Zilo. Orders, products, customers, and abandoned carts sync into your workspace — then AI drafts, follow-ups, recovery flows, and automations keep selling motions running without you living in five tabs. You still own pricing, brand, and approvals; we built the rails so commerce and outreach stay on autopilot while you chill and focus on what only you can do.",
  },
  {
    q: "Is pricing the same in every country?",
    a: "We use regional pricing so amounts match local markets. USD amounts on this page are indicative; your exact plans and currency appear in the app after sign-in.",
  },
  {
    q: "What is Zilo Chat?",
    a: "Zilo Chat is your in-workspace copilot — ask how to use the product, summarize activity, and steer your agents without leaving Zilo.",
  },
  {
    q: "Can my team use the same account?",
    a: "Yes. Invite team members, use roles where available, and use Team Analytics to track performance when you enable those modules.",
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
      {/* Subtle mesh */}
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

          <nav className="hidden items-center gap-8 md:flex" aria-label="Primary">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="text-sm font-medium text-slate-600 transition-colors hover:text-brand-dark"
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
              Get started
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <button
            type="button"
            className="rounded-lg p-2 text-slate-600 md:hidden"
            onClick={() => setOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-6 w-6" />
          </button>
        </div>

        {open && (
          <div className="fixed inset-0 z-[60] md:hidden">
            <button type="button" className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(false)} aria-label="Close menu" />
            <div className="absolute right-0 top-0 flex h-full w-[min(100%,20rem)] flex-col bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4">
                <span className="font-semibold">Menu</span>
                <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-2 text-slate-600" aria-label="Close">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <nav className="flex flex-1 flex-col gap-1 p-4" aria-label="Mobile">
                {NAV.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    className="rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
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
                  Get started
                </Link>
              </nav>
            </div>
          </div>
        )}
      </header>

      <main>
        {/* Hero */}
        <section id="product" className="relative overflow-hidden px-4 pb-20 pt-14 sm:px-6 sm:pt-20 lg:pb-28">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-3xl text-center">
              <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-[#4CD137]/35 bg-[#4CD137]/12 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[#065a24]">
                <Sparkles className="h-3.5 w-3.5 text-[#009B3A]" />
                Web-first · Sell and grow · AI
              </p>
              <h1 className="text-balance text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-[3.25rem] lg:leading-[1.1]">
                Help your team sell and grow on every channel — from one web workspace
              </h1>
              <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600 sm:text-xl">
                Zilo is not a WhatsApp-only tool. Run DMs, email, social, ads, and chat commerce in one place — with AI
                specialists for campaigns and copy, plus follow-ups built to close deals, not just store contacts. Your
                primary experience is the browser; mobile is there when you are on the move.
              </p>
              <p className="mx-auto mt-4 max-w-xl text-base font-medium text-[#0a2614]/90">
                One focus: pipeline and revenue — with growth tools beside sales so marketing is not a separate product.
              </p>
              <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-4">
                <Link
                  href="/login"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-[#007a2e] bg-[#009B3A] px-8 py-3.5 text-base font-semibold text-white shadow-lg transition hover:bg-[#4CD137] hover:text-[#0a2614] sm:w-auto"
                >
                  Start free — web workspace
                  <ArrowRight className="h-5 w-5" />
                </Link>
                <a
                  href="#how"
                  className="inline-flex w-full items-center justify-center rounded-xl border border-slate-300 bg-white px-8 py-3.5 text-base font-semibold text-slate-900 shadow-sm transition hover:border-[#009B3A]/40 hover:bg-[#f0fdf4] sm:w-auto"
                >
                  See how it works
                </a>
              </div>
              <p className="mt-4 text-sm text-slate-500">
                The full product lives on web —{" "}
                <Link href="/login" className="font-medium text-[#009B3A] underline-offset-2 hover:underline">
                  open your workspace in the browser
                </Link>
                . Mobile app? Same account when you need it on the go.
              </p>
            </div>

            {/* Hero mock */}
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
                          <span className="font-semibold tabular-nums text-slate-900">{[8, 3, 5][i]}</span>
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
                          Thanks for your message! Yes, we have that in stock — I can reserve one for you today. Would
                          delivery tomorrow work?
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800">
                            Your tone
                          </span>
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                            Catalog aware
                          </span>
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
                        <p className="mt-2 text-xs font-medium text-slate-500">Features</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Logos / trust */}
        <section className="border-y border-slate-200/80 bg-white py-10">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="text-center text-xs font-semibold uppercase tracking-wider text-slate-400">
              Sell through every touchpoint — focus work on the web
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-10 gap-y-4 text-slate-400">
              <span className="flex items-center gap-2 text-sm font-medium text-slate-500">
                <MessageSquare className="h-5 w-5" /> Chat & WhatsApp
              </span>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-500">
                <Megaphone className="h-5 w-5" /> Social & ads
              </span>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-500">
                <Mail className="h-5 w-5" /> Email & broadcast
              </span>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-500">
                <Store className="h-5 w-5" /> Shops & bookings
              </span>
            </div>
          </div>
        </section>

        {/* Shopify autopilot */}
        <section id="shopify" className="scroll-mt-20 px-4 py-12 sm:px-6 sm:py-16">
          <div className="mx-auto max-w-6xl">
            <div className="overflow-hidden rounded-3xl border border-emerald-500/30 bg-gradient-to-br from-emerald-950 via-slate-900 to-brand-ink shadow-2xl shadow-emerald-950/40">
              <div className="grid gap-10 px-6 py-12 sm:px-10 lg:grid-cols-[1.15fr_1fr] lg:items-center lg:gap-14 lg:px-14 lg:py-14">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-emerald-300">
                    <ShoppingBag className="h-3.5 w-3.5" aria-hidden />
                    Shopify · built for hands-off revenue
                  </div>
                  <h2 className="mt-5 text-3xl font-bold leading-tight tracking-tight text-white sm:text-4xl lg:text-[2.35rem] lg:leading-[1.15]">
                    Shopify 100% on autopilot. Selling 100% on autopilot.
                  </h2>
                  <p className="mt-5 text-lg leading-relaxed text-emerald-50/90">
                    Connect your store once. Orders, inventory signals, customers, abandoned carts, and discounts flow into
                    Zilo — then AI follow-ups, recovery, broadcasts, and workflows keep the money motion running. You chill,
                    tweak strategy when you want, and let the system sell around the clock.
                  </p>
                  <p className="mt-4 text-sm font-medium text-white/90">
                    That is what we built — commerce and outreach on rails, not another tab to babysit.
                  </p>
                  <Link
                    href="/login"
                    className="mt-8 inline-flex items-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-semibold text-emerald-950 shadow-lg transition hover:bg-emerald-50"
                  >
                    Connect Shopify in Zilo
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
                <ul className="space-y-4 text-sm leading-relaxed text-emerald-50/95">
                  {[
                    "Store sync: products, orders, and customers without manual exports",
                    "Abandoned carts & recovery plays — nudges while you are offline",
                    "Discounts and growth levers tied to real Shopify data",
                    "AI + automations so replies and follow-ups match your catalog and orders",
                    "One web HQ — selling stays on autopilot; you step in when you choose",
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
              <p className="border-t border-white/10 px-6 py-4 text-center text-xs text-white/45 sm:px-10 lg:px-14">
                You stay in charge of pricing, policies, and brand voice — automation handles the repeat selling work.
              </p>
            </div>
          </div>
        </section>

        {/* Benchmark: Twin vs OpenClaw vs Zilo */}
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
                , here is where <strong className="text-slate-800">Zilo</strong> fits — same agent wave, different job
                to be done.
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
                  Broad autonomous agents: describe outcomes in plain language, connect APIs and the browser, ship
                  interfaces and workflows across many domains — a horizontal &quot;AI company builder.&quot;
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
                  Open-source stack: a gateway, many chat channels, tools (files, shell, browser), memory and skills —
                  powerful for builders who are happy on a machine, in config, and in the repo.
                </p>
                <p className="mt-4 text-xs text-slate-500">
                  Best when you want maximum control and you speak developer.
                </p>
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
                  We host the workspace — no daemon, no terminal. Your team sells from the browser across WhatsApp,
                  social, email, and ads: follow-ups, orders, broadcasts, Zilo Chat, automations — built for revenue, not
                  for hacking the OS.
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

        {/* Features grid */}
        <section className="px-4 py-20 sm:px-6" aria-labelledby="features-heading">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <h2 id="features-heading" className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
                Built to help you sell — not juggle fifteen tabs
              </h2>
              <p className="mt-4 text-lg text-slate-600">
                One web workspace for conversations, campaigns, and closing — whether the lead came from Instagram, email,
                an ad click, or WhatsApp.
              </p>
            </div>
            <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((f) => (
                <article
                  key={f.title}
                  className={cn(
                    "group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm transition hover:border-brand/30 hover:shadow-md",
                  )}
                >
                  <div
                    className={cn(
                      "mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br text-[#009B3A]",
                      f.accent,
                    )}
                  >
                    <f.icon className="h-6 w-6" strokeWidth={1.75} />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{f.description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Modules */}
        <section id="modules" className="scroll-mt-20 border-y border-slate-200/80 bg-white px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
              <div>
                <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Your workspace, your channels</h2>
                <p className="mt-4 text-lg text-slate-600">
                  Turn on only the surfaces you sell through — Social Inbox, Ads, Email, Broadcast, WhatsApp — from{" "}
                  <strong className="text-slate-800">Features</strong>. The web dashboard stays fast and focused on helping
                  you convert.
                </p>
                <ul className="mt-8 space-y-4">
                  {["Presets: Starter, Business, Personal — match how you sell", "Industry-aware labels (shop, menu, services…)", "Core workspace: Overview, Zilo Chat, Automations, Integrations"].map((t) => (
                    <li key={t} className="flex gap-3 text-slate-700">
                      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                        <Check className="h-3.5 w-3.5" />
                      </span>
                      {t}
                    </li>
                  ))}
                </ul>
                <Link href="/login" className="mt-10 inline-flex items-center gap-2 font-semibold text-brand-dark hover:text-brand-dark">
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

        {/* Industries we support */}
        <section id="industries" className="scroll-mt-20 border-y border-slate-200/80 bg-slate-50/80 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto max-w-2xl text-center">
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
                <Store className="h-3.5 w-3.5 text-brand-dark" aria-hidden />
                Business types
              </div>
              <h2 className="mt-4 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
                Every industry we support
              </h2>
              <p className="mt-4 text-lg text-slate-600">
                Pick your type at signup — the app adjusts labels (Shop vs Menu vs Services), bookings, catalog, and
                defaults so the workspace feels built for you. Same list on{" "}
                <strong className="text-slate-800">web and mobile</strong>.
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
              Don&apos;t see a perfect fit? Choose <strong className="text-slate-700">General / other</strong> — you can
              still enable every module (Shopify, bookings, social, email, and more).
            </p>
          </div>
        </section>

        {/* How */}
        <section id="how" className="scroll-mt-20 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">How it works</h2>
            <p className="mx-auto mt-4 max-w-2xl text-center text-lg text-slate-600">
              From first login in the browser to selling across all your channels in three steps.
            </p>
            <div className="mt-14 grid gap-8 md:grid-cols-3">
              {STEPS.map((s) => (
                <div key={s.step} className="relative rounded-2xl border border-slate-200/80 bg-white p-8 shadow-sm">
                  <span className="text-4xl font-bold text-brand-light">{s.step}</span>
                  <h3 className="mt-4 text-lg font-semibold text-slate-900">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{s.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Security strip */}
        <section className="border-y border-slate-200/80 bg-slate-900 px-4 py-12 text-white sm:px-6">
          <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 text-center md:flex-row md:justify-between md:text-left">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/10">
                <Shield className="h-6 w-6 text-emerald-400" />
              </div>
              <div>
                <p className="font-semibold">Built for real businesses</p>
                <p className="text-sm text-slate-400">Roles, audit-friendly workflows, and integrations you control.</p>
              </div>
            </div>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-2.5 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
            >
              Create account
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="scroll-mt-20 px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Simple, transparent plans</h2>
              <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-600">
                Indicative USD pricing. Regional pricing applies at checkout — amounts are tailored to your market.
              </p>
            </div>
            <div className="mt-14 grid gap-6 lg:grid-cols-3">
              {PLANS.map((plan) => (
                <div
                  key={plan.id}
                  className={cn(
                    "relative flex flex-col rounded-2xl border p-8",
                    plan.highlighted
                      ? "border-[#4CD137]/50 bg-white shadow-xl shadow-[#009B3A]/10 ring-2 ring-[#4CD137]/30"
                      : "border-slate-200 bg-white shadow-sm",
                  )}
                >
                  {plan.highlighted && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-[#009B3A] px-3 py-0.5 text-xs font-semibold text-white ring-1 ring-[#007a2e]">
                      Most popular
                    </span>
                  )}
                  <h3 className="text-lg font-semibold text-slate-900">{plan.name}</h3>
                  <p className="mt-1 text-sm text-slate-500">{plan.blurb}</p>
                  <p className="mt-6 flex items-baseline gap-1">
                    <span className="text-4xl font-bold tracking-tight text-slate-900">${plan.usd}</span>
                    <span className="text-slate-500">/month</span>
                  </p>
                  <p className="mt-1 text-xs text-slate-400">USD · indicative</p>
                  <ul className="mt-8 flex-1 space-y-3">
                    {plan.features.map((f) => (
                      <li key={f} className="flex gap-2 text-sm text-slate-600">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Link
                    href="/login"
                    className={cn(
                      "mt-8 block w-full rounded-xl py-3 text-center text-sm font-semibold transition",
                      plan.highlighted
                        ? "border border-[#007a2e] bg-[#009B3A] text-white hover:bg-[#4CD137] hover:text-[#0a2614]"
                        : "border border-slate-300 bg-white text-slate-900 hover:border-[#009B3A]/35 hover:bg-[#f0fdf4]",
                    )}
                  >
                    Get started
                  </Link>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="scroll-mt-20 border-t border-slate-200/80 bg-white px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-3xl">
            <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
              Frequently asked questions
            </h2>
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
            <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Ready to sell smarter across every channel?
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-white/95">
              Join teams using the Zilo web workspace — AI agents, follow-ups, and omnichannel selling without the sprawl.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row sm:gap-6">
              <Link
                href="/login"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-white/30 bg-white px-8 py-3.5 text-base font-semibold text-[#0a2614] shadow-lg transition hover:bg-[#f0fdf4] sm:w-auto"
              >
                Get started free
                <ArrowRight className="h-5 w-5 shrink-0" />
              </Link>
              <a
                href="#product"
                className="text-sm font-semibold text-white underline decoration-white/70 underline-offset-4 hover:decoration-white"
              >
                Back to top
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
              Web-first agent workspace for teams that sell on chat, social, email, and ads — one place to focus and close.
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
                  <a href="#industries" className="hover:text-brand-dark">
                    Industries we support
                  </a>
                </li>
                <li>
                  <a href="#modules" className="hover:text-brand-dark">
                    Modules
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
        <div className="mx-auto mt-12 max-w-6xl border-t border-slate-100 pt-8 text-center text-xs text-slate-400">
          © {new Date().getFullYear()} Zilo. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
