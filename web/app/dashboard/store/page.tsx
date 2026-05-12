"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import {
  ArrowRight, ArrowUpRight, Check, ExternalLink, Loader2, Package,
  PackagePlus, RefreshCw, ShoppingBag, ShoppingCart, Sparkles,
  Store, Trash2, TrendingUp, X, AlertCircle, Plus, Wand2,
  CreditCard, Globe, ChevronDown, ChevronUp, ImageIcon, Palette,
  Phone, Mail, MapPin, Save, Share2, Camera, MessageCircle,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useBusiness } from "@/contexts/BusinessContext";

// ── Types ──────────────────────────────────────────────────────────────────────

type ClientSite = {
  wp_slug: string;
  business_name: string;
  blog_url: string;
  industry: string;
  location: string;
  active: boolean;
  products_count?: number;
  orders_count?: number;
  features?: { shop?: boolean; forms?: boolean; blog?: boolean };
};

type WCProduct = {
  id: number;
  name: string;
  price: string;
  regular_price: string;
  sale_price: string;
  status: string;
  stock_status: string;
  total_sales: number;
  short_description: string;
  images: { src: string; alt: string }[];
  categories: { name: string }[];
};

type WCOrder = {
  id: number;
  status: string;
  total: string;
  currency: string;
  date_created: string;
  billing: { first_name: string; last_name: string; phone: string; email: string };
  line_items: { name: string; quantity: number; total: string }[];
};

type Tab = "products" | "orders" | "website" | "settings";

type SiteSettings = {
  title: string;
  tagline: string;
  logo_url: string;
  accent_color: string;
  button_color: string;
  phone: string;
  email: string;
  whatsapp: string;
  address: string;
  facebook: string;
  instagram: string;
  tiktok: string;
  twitter: string;
};

const SETTINGS_DEFAULTS: SiteSettings = {
  title: "", tagline: "", logo_url: "",
  accent_color: "#009B3A", button_color: "#009B3A",
  phone: "", email: "", whatsapp: "", address: "",
  facebook: "", instagram: "", tiktok: "", twitter: "",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

const ORDER_STATUS_COLORS: Record<string, string> = {
  pending:    "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  on_hold:    "bg-orange-100 text-orange-800",
  completed:  "bg-emerald-100 text-emerald-800",
  cancelled:  "bg-red-100 text-red-800",
  refunded:   "bg-slate-100 text-slate-600",
  failed:     "bg-red-100 text-red-700",
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

// ── Website Editor ────────────────────────────────────────────────────────────

function WebsiteEditor({ slug, storeUrl }: { slug: string; storeUrl: string }) {
  const [form, setForm] = useState<SiteSettings>(SETTINGS_DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<SiteSettings>(`/blog/clients/${slug}/site-settings`)
      .then(d => setForm(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [slug]);

  function set(key: keyof SiteSettings, val: string) {
    setForm(prev => ({ ...prev, [key]: val }));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.patch(`/blog/clients/${slug}/site-settings`, form as unknown as Record<string, unknown>);
      toast.success("Website updated — changes go live in ~30s");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center py-16">
      <Loader2 className="h-6 w-6 animate-spin text-brand" />
    </div>
  );

  const Field = ({ label, id, type = "text", placeholder, icon: Icon }: {
    label: string; id: keyof SiteSettings; type?: string; placeholder?: string; icon?: React.FC<{ className?: string }>;
  }) => (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>
      <div className="relative">
        {Icon && <Icon className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />}
        <input
          type={type}
          value={form[id]}
          onChange={e => set(id, e.target.value)}
          placeholder={placeholder}
          className={cn(
            "w-full rounded-lg border border-slate-200 bg-white py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand/30",
            Icon ? "pl-8 pr-3" : "px-3",
          )}
        />
      </div>
    </div>
  );

  return (
    <form onSubmit={save} className="space-y-4">

      {/* Identity */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Store className="h-4 w-4 text-brand" /> Site Identity
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Business name" id="title" placeholder="Jane's Bakery" />
          <Field label="Tagline" id="tagline" placeholder="Fresh baked daily" />
        </div>
        <Field label="Logo URL" id="logo_url" placeholder="https://cdn.example.com/logo.png" icon={ImageIcon} />
        <p className="text-[11px] text-slate-400">
          Paste a public image URL. Upload via{" "}
          <a href={`${storeUrl}/wp-admin/media-new.php`} target="_blank" rel="noopener noreferrer" className="underline">WordPress Media Library</a>
          , then copy the URL here.
        </p>
      </div>

      {/* Colours */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Palette className="h-4 w-4 text-brand" /> Brand Colours
        </h2>
        <div className="grid grid-cols-2 gap-4">
          {([
            { label: "Accent / link colour", id: "accent_color" as const },
            { label: "Button colour",        id: "button_color" as const },
          ] as { label: string; id: keyof SiteSettings }[]).map(({ label, id }) => (
            <div key={id}>
              <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={form[id] as string}
                  onChange={e => set(id, e.target.value)}
                  className="h-9 w-12 cursor-pointer rounded-md border border-slate-200 p-0.5"
                />
                <input
                  type="text"
                  value={form[id] as string}
                  onChange={e => set(id, e.target.value)}
                  placeholder="#009B3A"
                  className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand/30"
                />
              </div>
            </div>
          ))}
        </div>
        <div
          className="mt-1 h-10 w-full rounded-lg"
          style={{ background: `linear-gradient(135deg, ${form.accent_color} 0%, ${form.button_color} 100%)` }}
        />
      </div>

      {/* Contact */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Phone className="h-4 w-4 text-brand" /> Contact Info
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Phone" id="phone" placeholder="+254 712 345 678" icon={Phone} />
          <Field label="Email" id="email" type="email" placeholder="hello@mybiz.com" icon={Mail} />
          <Field label="WhatsApp number" id="whatsapp" placeholder="+254712345678" icon={Phone} />
          <Field label="Address" id="address" placeholder="123 Main St, Nairobi" icon={MapPin} />
        </div>
      </div>

      {/* Social */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Globe className="h-4 w-4 text-brand" /> Social Media
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Facebook URL" id="facebook" placeholder="https://facebook.com/mybiz" icon={Share2} />
          <Field label="Instagram URL" id="instagram" placeholder="https://instagram.com/mybiz" icon={Camera} />
          <Field label="TikTok URL" id="tiktok" placeholder="https://tiktok.com/@mybiz" />
          <Field label="Twitter / X URL" id="twitter" placeholder="https://x.com/mybiz" icon={MessageCircle} />
        </div>
      </div>

      {/* Advanced */}
      <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
        <p className="text-xs text-slate-500">
          Need more control?{" "}
          <a
            href={`${storeUrl}/wp-admin/customize.php`}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-brand underline"
          >
            Open WordPress Customizer
          </a>{" "}
          for full page-level editing.
        </p>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-xl bg-brand-dark px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </form>
  );
}

// ── Setup Wizard ───────────────────────────────────────────────────────────────

type WizardStep = 0 | 1 | 2;

function StoreSetupWizard({ onDone }: { onDone: () => void }) {
  const { businessType } = useBusiness();
  const [step, setStep] = useState<WizardStep>(0);
  const [saving, setSaving] = useState(false);

  async function provision() {
    setSaving(true);
    try {
      await api.post("/blog/provision", {});
      toast.success("Your store is being set up — this takes about 30 seconds.");
      setTimeout(onDone, 3000);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg py-16">
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg">
        {/* Header */}
        <div className="border-b border-slate-100 bg-gradient-to-r from-brand-dark to-brand px-6 py-5 text-white">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15">
              <Store className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-brand-light">Zilo Store</p>
              <p className="text-sm font-medium text-white/90">Set up your online store</p>
            </div>
          </div>
          {/* Progress */}
          <div className="mt-4 flex gap-1.5">
            {([0, 1, 2] as WizardStep[]).map((i) => (
              <div key={i} className={cn("h-1 flex-1 rounded-full transition", i <= step ? "bg-white" : "bg-white/30")} />
            ))}
          </div>
        </div>

        <div className="px-6 py-6">
          {step === 0 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-slate-900">Your store is ready to launch</h2>
              <p className="text-sm leading-relaxed text-slate-600">
                Zilo gives you a complete online store — products, checkout, and payments — on your own subdomain.
                Customers never see WordPress, only your brand.
              </p>
              <ul className="space-y-2 text-sm text-slate-700">
                {[
                  "AI seeds your products based on your industry",
                  "Customers pay via Stripe or PayPal",
                  "Orders appear here in your dashboard",
                  "WhatsApp AI answers product questions automatically",
                ].map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                    {item}
                  </li>
                ))}
              </ul>
              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="inline-flex items-center gap-2 rounded-xl bg-brand-dark px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand"
                >
                  Get started <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-slate-900">What will your store sell?</h2>
              <p className="text-sm text-slate-600">
                Your industry is set to <strong className="text-slate-900">{businessType || "general"}</strong>. Zilo's AI will
                generate matching products for your store automatically. You can edit or add more products after setup.
              </p>
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 text-sm text-emerald-900">
                <Sparkles className="mb-1.5 h-4 w-4 text-emerald-600" />
                <p className="font-medium">AI will seed {businessType === "bakery" ? "cake & pastry" : businessType === "salon" ? "hair & beauty" : businessType === "restaurant" ? "food & drink" : "industry-specific"} products with realistic prices and descriptions.</p>
              </div>
              <div className="flex justify-between pt-2">
                <button type="button" onClick={() => setStep(0)} className="text-sm text-slate-500 hover:text-slate-800">Back</button>
                <button type="button" onClick={() => setStep(2)} className="inline-flex items-center gap-2 rounded-xl bg-brand-dark px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand">
                  Continue <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold text-slate-900">Accept payments</h2>
              <p className="text-sm text-slate-600">
                After setup, connect your Stripe or PayPal account in your store settings to start receiving payments directly.
              </p>
              <div className="space-y-2">
                {[
                  { icon: CreditCard, title: "Stripe", desc: "Cards, M-Pesa (via Stripe) — 2.9% + 30¢ per transaction" },
                  { icon: Globe, title: "PayPal", desc: "PayPal balance & cards — ~3.49% per transaction" },
                  { icon: ShoppingCart, title: "Cash on delivery", desc: "No fees — collect payment in person" },
                ].map((opt) => (
                  <div key={opt.title} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <opt.icon className="h-5 w-5 shrink-0 text-slate-500" />
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{opt.title}</p>
                      <p className="text-xs text-slate-500">{opt.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-500">You configure this inside your store admin after launch.</p>
              <div className="flex justify-between pt-2">
                <button type="button" onClick={() => setStep(1)} className="text-sm text-slate-500 hover:text-slate-800">Back</button>
                <button
                  type="button"
                  onClick={provision}
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {saving ? "Setting up…" : "Launch my store"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Product Card ───────────────────────────────────────────────────────────────

function ProductCard({ product, slug, onDelete }: { product: WCProduct; slug: string; onDelete: (id: number) => void }) {
  const [deleting, setDeleting] = useState(false);
  const img = product.images?.[0]?.src;

  async function handleDelete() {
    if (!confirm(`Delete "${product.name}"?`)) return;
    setDeleting(true);
    try {
      await api.delete(`/blog/clients/${slug}/products/${product.id}`);
      onDelete(product.id);
      toast.success("Product deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="group relative overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md">
      {/* Image */}
      <div className="relative h-36 w-full overflow-hidden bg-slate-100">
        {img ? (
          <img src={img} alt={product.name} className="h-full w-full object-cover transition group-hover:scale-105" />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <Package className="h-10 w-10 text-slate-300" />
          </div>
        )}
        {product.sale_price && (
          <span className="absolute left-2 top-2 rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-bold text-white">SALE</span>
        )}
        <button
          type="button"
          onClick={handleDelete}
          disabled={deleting}
          className="absolute right-2 top-2 hidden rounded-lg bg-white/90 p-1.5 text-red-500 shadow-sm hover:bg-red-50 group-hover:flex disabled:opacity-50"
          title="Delete product"
        >
          {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
        </button>
      </div>

      <div className="p-3">
        <p className="line-clamp-2 text-sm font-semibold text-slate-900">{product.name}</p>
        {product.categories?.[0] && (
          <p className="mt-0.5 text-[11px] text-slate-400">{product.categories[0].name}</p>
        )}
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-baseline gap-1">
            {product.sale_price ? (
              <>
                <span className="text-sm font-bold text-red-600">{product.sale_price}</span>
                <span className="text-xs text-slate-400 line-through">{product.regular_price}</span>
              </>
            ) : (
              <span className="text-sm font-bold text-slate-900">{product.price || "—"}</span>
            )}
          </div>
          <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium",
            product.stock_status === "instock" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"
          )}>
            {product.stock_status === "instock" ? "In stock" : "Out of stock"}
          </span>
        </div>
        {product.total_sales > 0 && (
          <p className="mt-1 text-[11px] text-slate-400">{product.total_sales} sold</p>
        )}
      </div>
    </div>
  );
}

// ── Add Product Modal ──────────────────────────────────────────────────────────

function AddProductModal({ slug, onClose, onCreated }: { slug: string; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [desc, setDesc] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !price.trim()) { toast.error("Name and price required"); return; }
    setSaving(true);
    try {
      await api.post(`/blog/clients/${slug}/products`, { name, regular_price: price, description: desc, status: "publish" });
      toast.success("Product created");
      onCreated();
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-900">Add Product</h3>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form onSubmit={submit} className="space-y-4 p-5">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Product name *</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Vanilla Birthday Cake"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand" required />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Price *</label>
            <input value={price} onChange={e => setPrice(e.target.value)} placeholder="e.g. 1500"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand" required />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Description</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} placeholder="Short product description…"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand resize-none" />
          </div>
          <button type="submit" disabled={saving}
            className="w-full rounded-xl bg-brand-dark py-2.5 text-sm font-semibold text-white hover:bg-brand disabled:opacity-50">
            {saving ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : "Add product"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Order Row ──────────────────────────────────────────────────────────────────

function OrderRow({ order }: { order: WCOrder }) {
  const [open, setOpen] = useState(false);
  const name = `${order.billing.first_name} ${order.billing.last_name}`.trim() || "Guest";
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-slate-900">#{order.id} — {name}</span>
            <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize", ORDER_STATUS_COLORS[order.status] ?? "bg-slate-100 text-slate-600")}>
              {order.status.replace("_", " ")}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">{fmtDate(order.date_created)} · {order.currency} {order.total}</p>
        </div>
        {open ? <ChevronUp className="h-4 w-4 shrink-0 text-slate-400" /> : <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />}
      </button>
      {open && (
        <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-3 space-y-2">
          <p className="text-xs font-medium text-slate-500">Items</p>
          {order.line_items.map((item, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span className="text-slate-800">{item.name} <span className="text-slate-400">×{item.quantity}</span></span>
              <span className="font-medium text-slate-900">{order.currency} {item.total}</span>
            </div>
          ))}
          {order.billing.phone && <p className="text-xs text-slate-500">📞 {order.billing.phone}</p>}
          {order.billing.email && <p className="text-xs text-slate-500">✉️ {order.billing.email}</p>}
        </div>
      )}
    </div>
  );
}

// ── Main Store Page ────────────────────────────────────────────────────────────

function StorePageInner() {
  const [site, setSite] = useState<ClientSite | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("products");

  const [products, setProducts] = useState<WCProduct[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [reseeding, setReseeding] = useState(false);

  const [orders, setOrders] = useState<WCOrder[]>([]);
  const [loadingOrders, setLoadingOrders] = useState(false);

  const [showAddProduct, setShowAddProduct] = useState(false);

  const loadSite = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ sites: ClientSite[] }>("/blog/clients");
      const sites: ClientSite[] = data.sites ?? [];
      setSite(sites.find(s => s.features?.shop !== false) ?? sites[0] ?? null);
    } catch {
      setSite(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadProducts = useCallback(async (slug: string) => {
    setLoadingProducts(true);
    try {
      const data = await api.get<{ products: WCProduct[] }>(`/blog/clients/${slug}/products`);
      setProducts(data.products ?? []);
    } catch {
      setProducts([]);
    } finally {
      setLoadingProducts(false);
    }
  }, []);

  const loadOrders = useCallback(async (slug: string) => {
    setLoadingOrders(true);
    try {
      const data = await api.get<{ orders: WCOrder[] }>(`/blog/clients/${slug}/orders`);
      setOrders(data.orders ?? []);
    } catch {
      setOrders([]);
    } finally {
      setLoadingOrders(false);
    }
  }, []);

  useEffect(() => { loadSite(); }, [loadSite]);

  useEffect(() => {
    if (!site) return;
    if (tab === "products") loadProducts(site.wp_slug);
    if (tab === "orders") loadOrders(site.wp_slug);
  }, [site, tab, loadProducts, loadOrders]);

  async function reseedProducts() {
    if (!site) return;
    setReseeding(true);
    try {
      await api.post(`/blog/clients/${site.wp_slug}/reseed-products`, {});
      toast.success("AI is generating new products — refreshing in 5s…");
      setTimeout(() => loadProducts(site.wp_slug), 5000);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Reseed failed");
    } finally {
      setReseeding(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand" />
      </div>
    );
  }

  if (!site) {
    return <StoreSetupWizard onDone={loadSite} />;
  }

  const storeUrl = site.blog_url?.replace(/\/$/, "");

  return (
    <div className="min-h-[calc(100vh-3rem)] bg-[#f4f6f9]">
      <div className="mx-auto max-w-6xl px-3 pb-10 pt-3 sm:px-5 sm:pb-12 sm:pt-4">

        {/* Header */}
        <section className="mb-4 overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
          <div className="border-b border-slate-100 bg-gradient-to-br from-white via-slate-50/50 to-emerald-50/20 px-4 py-4 sm:px-6 sm:py-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Commerce</p>
                <h1 className="text-lg font-semibold tracking-tight text-slate-900 sm:text-xl">My Store</h1>
                <p className="mt-0.5 text-xs text-slate-500">{site.business_name} · {site.industry}</p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <a
                  href={`${storeUrl}/shop`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  View shop
                </a>
                <a
                  href={`${storeUrl}/wp-admin`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  <ArrowUpRight className="h-3.5 w-3.5" />
                  WP Admin
                </a>
              </div>
            </div>

            {/* Stats */}
            <div className="mt-4 grid grid-cols-3 gap-3">
              {[
                { icon: Package, label: "Products", value: site.products_count ?? products.length },
                { icon: ShoppingCart, label: "Orders", value: site.orders_count ?? 0 },
                { icon: TrendingUp, label: "Revenue", value: "—" },
              ].map(({ icon: Icon, label, value }) => (
                <div key={label} className="rounded-xl border border-slate-100 bg-slate-50/80 p-3">
                  <Icon className="h-4 w-4 text-slate-400" />
                  <p className="mt-1.5 text-lg font-bold text-slate-900">{value}</p>
                  <p className="text-[11px] text-slate-500">{label}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-0 border-b border-slate-100">
            {(["products", "orders", "website", "settings"] as Tab[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={cn(
                  "px-4 py-3 text-sm font-medium capitalize transition",
                  tab === t
                    ? "border-b-2 border-brand-dark text-brand-dark"
                    : "text-slate-500 hover:text-slate-800"
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </section>

        {/* Products Tab */}
        {tab === "products" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-700">{products.length} product{products.length !== 1 ? "s" : ""}</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={reseedProducts}
                  disabled={reseeding}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {reseeding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5 text-brand" />}
                  AI Re-seed
                </button>
                <button
                  type="button"
                  onClick={() => loadProducts(site.wp_slug)}
                  disabled={loadingProducts}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  <RefreshCw className={cn("h-3.5 w-3.5", loadingProducts && "animate-spin")} />
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddProduct(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add product
                </button>
              </div>
            </div>

            {loadingProducts ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="h-6 w-6 animate-spin text-brand" />
              </div>
            ) : products.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white py-16 text-center">
                <PackagePlus className="mb-3 h-10 w-10 text-slate-300" />
                <p className="text-sm font-medium text-slate-700">No products yet</p>
                <p className="mt-1 text-xs text-slate-400">Add manually or let AI generate them for your industry</p>
                <div className="mt-4 flex gap-2">
                  <button type="button" onClick={reseedProducts} disabled={reseeding}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark px-4 py-2 text-sm font-semibold text-white hover:bg-brand disabled:opacity-50">
                    {reseeding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                    Generate with AI
                  </button>
                  <button type="button" onClick={() => setShowAddProduct(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                    <Plus className="h-4 w-4" /> Add manually
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {products.map((p) => (
                  <ProductCard key={p.id} product={p} slug={site.wp_slug} onDelete={(id) => setProducts(prev => prev.filter(x => x.id !== id))} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Orders Tab */}
        {tab === "orders" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-700">{orders.length} recent order{orders.length !== 1 ? "s" : ""}</p>
              <button type="button" onClick={() => loadOrders(site.wp_slug)} disabled={loadingOrders}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                <RefreshCw className={cn("h-3.5 w-3.5", loadingOrders && "animate-spin")} />
                Refresh
              </button>
            </div>

            {loadingOrders ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="h-6 w-6 animate-spin text-brand" />
              </div>
            ) : orders.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white py-16 text-center">
                <ShoppingBag className="mb-3 h-10 w-10 text-slate-300" />
                <p className="text-sm font-medium text-slate-700">No orders yet</p>
                <p className="mt-1 text-xs text-slate-400">Orders will appear here once customers start buying</p>
                <a href={`${storeUrl}/shop`} target="_blank" rel="noopener noreferrer"
                  className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-brand-dark px-4 py-2 text-sm font-semibold text-white hover:bg-brand">
                  <ExternalLink className="h-4 w-4" /> View your shop
                </a>
              </div>
            ) : (
              <div className="space-y-2">
                {orders.map((o) => <OrderRow key={o.id} order={o} />)}
              </div>
            )}
          </div>
        )}

        {/* Website Tab */}
        {tab === "website" && site && (
          <WebsiteEditor slug={site.wp_slug} storeUrl={storeUrl} />
        )}

        {/* Settings Tab */}
        {tab === "settings" && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
              <h2 className="text-sm font-semibold text-slate-900">Store details</h2>
              <div className="space-y-3">
                {[
                  { label: "Store URL", value: `${storeUrl}/shop` },
                  { label: "Business name", value: site.business_name },
                  { label: "Industry", value: site.industry },
                  { label: "Location", value: site.location },
                ].map(({ label, value }) => (
                  <div key={label} className="flex items-start justify-between gap-4">
                    <span className="text-xs font-medium text-slate-500 w-28 shrink-0">{label}</span>
                    <span className="text-xs text-slate-800 text-right">{value || "—"}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
              <h2 className="text-sm font-semibold text-slate-900">Quick links</h2>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {[
                  { label: "WooCommerce settings", href: `${storeUrl}/wp-admin/admin.php?page=wc-settings` },
                  { label: "Payment gateways", href: `${storeUrl}/wp-admin/admin.php?page=wc-settings&tab=checkout` },
                  { label: "Shipping zones", href: `${storeUrl}/wp-admin/admin.php?page=wc-settings&tab=shipping` },
                  { label: "Tax settings", href: `${storeUrl}/wp-admin/admin.php?page=wc-settings&tab=tax` },
                  { label: "Coupons", href: `${storeUrl}/wp-admin/post-new.php?post_type=shop_coupon` },
                  { label: "All products", href: `${storeUrl}/wp-admin/edit.php?post_type=product` },
                ].map(({ label, href }) => (
                  <a key={label} href={href} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-white hover:shadow-sm">
                    <ArrowUpRight className="h-3 w-3 text-slate-400" />
                    {label}
                  </a>
                ))}
              </div>
              <p className="text-[11px] text-slate-400">These open your store's WordPress admin.</p>
            </div>

            <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                <div>
                  <p className="text-xs font-semibold text-amber-900">Payments not set up</p>
                  <p className="text-xs text-amber-800 mt-0.5">Go to Payment gateways above and connect Stripe or PayPal to start accepting payments.</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {showAddProduct && site && (
        <AddProductModal
          slug={site.wp_slug}
          onClose={() => setShowAddProduct(false)}
          onCreated={() => loadProducts(site.wp_slug)}
        />
      )}
    </div>
  );
}

export default function StorePage() {
  return (
    <Suspense fallback={null}>
      <StorePageInner />
    </Suspense>
  );
}
