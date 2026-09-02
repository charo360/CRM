"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { AlertCircle, Check, ChevronDown, Loader2, Minus, Plus, Search, ShoppingBag, X } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { formatCurrency, resolveMediaUrl } from "@/lib/utils";

type ModifierOption = { name: string; price_delta?: number };
type ModifierGroup = { name: string; required?: boolean; multi_select?: boolean; options: ModifierOption[] };
type Variant = { name: string; price: number };
type Product = {
  id: string;
  name: string;
  description: string;
  price: number;
  discount_price?: number | null;
  category: string;
  image_url?: string;
  images: string[];
  in_stock: boolean;
  stock_quantity?: number | null;
  unit?: string;
  moq?: number;
  pricing_tiers?: { min_qty: number; price: number }[];
  variants?: Variant[];
  modifier_groups?: ModifierGroup[];
};
type Store = {
  slug: string;
  business_name: string;
  currency: string;
  products: Product[];
  checkout: { online_payment_available: boolean; provider?: string | null; payment_label: string };
};
type SelectedModifier = { group: string; option: string };
type CartLine = {
  key: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: number;
  price: number;
  variant_name?: string;
  modifiers: SelectedModifier[];
};

function displayedPrice(product: Product): number {
  return Number(product.discount_price ?? product.price ?? 0);
}

function itemUnitPrice(product: Product, quantity: number, variantName: string, modifiers: SelectedModifier[]): number {
  const variant = (product.variants || []).find((row) => row.name === variantName);
  let value = variant ? Number(variant.price) : displayedPrice(product);
  const tiers = (product.pricing_tiers || [])
    .filter((tier) => Number(tier.min_qty) <= quantity && Number(tier.price) >= 0)
    .sort((a, b) => Number(b.min_qty) - Number(a.min_qty));
  // Match the server's trusted pricing rule exactly. This keeps the price a
  // buyer sees on the catalog consistent with the final Paystack checkout.
  if (tiers[0]) value = Number(tiers[0].price);
  for (const selected of modifiers) {
    const group = (product.modifier_groups || []).find((row) => row.name === selected.group);
    const option = group?.options.find((row) => row.name === selected.option);
    value += Number(option?.price_delta || 0);
  }
  return Math.max(0, Number(value.toFixed(2)));
}

export default function PublicStorePage() {
  const { slug } = useParams<{ slug: string }>();
  const [store, setStore] = useState<Store | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cart, setCart] = useState<CartLine[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [variantName, setVariantName] = useState("");
  const [modifiers, setModifiers] = useState<SelectedModifier[]>([]);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [cartOpen, setCartOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [orderMessage, setOrderMessage] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    setError("");
    fetch(`${API_BASE}/storefront/public/${encodeURIComponent(slug)}`)
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || "This catalog is unavailable.");
        }
        return response.json() as Promise<Store>;
      })
      .then(setStore)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load this catalog."))
      .finally(() => setLoading(false));
  }, [slug]);

  const total = useMemo(() => cart.reduce((sum, line) => sum + line.price, 0), [cart]);
  const itemCount = useMemo(() => cart.reduce((sum, line) => sum + line.quantity, 0), [cart]);
  const categories = useMemo(() => {
    const cats = new Set((store?.products || []).map((product) => product.category || "Other"));
    return ["All", ...Array.from(cats).sort()];
  }, [store]);
  const filteredProducts = useMemo(() => {
    let list = store?.products || [];
    if (selectedCategory !== "All") list = list.filter((product) => (product.category || "Other") === selectedCategory);
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter((product) =>
        product.name.toLowerCase().includes(q) ||
        (product.description || "").toLowerCase().includes(q) ||
        (product.category || "").toLowerCase().includes(q)
      );
    }
    return list;
  }, [store, selectedCategory, searchQuery]);
  const selectedPrice = selected ? itemUnitPrice(selected, quantity, variantName, modifiers) : 0;
  const selectedImages = selected
    ? Array.from(new Set<string>([...(selected.images || []), selected.image_url || ""]))
        .filter(Boolean)
        .map((image) => resolveMediaUrl(image))
        .filter((image): image is string => Boolean(image))
    : [];

  function beginAdd(product: Product) {
    setSelected(product);
    setSelectedImageIndex(0);
    setQuantity(Math.max(1, Number(product.moq || 1)));
    setVariantName("");
    setModifiers([]);
  }

  function toggleModifier(group: ModifierGroup, option: ModifierOption) {
    setModifiers((current) => {
      const has = current.some((row) => row.group === group.name && row.option === option.name);
      if (has) return current.filter((row) => !(row.group === group.name && row.option === option.name));
      const withoutGroup = group.multi_select ? current : current.filter((row) => row.group !== group.name);
      return [...withoutGroup, { group: group.name, option: option.name }];
    });
  }

  function addSelected() {
    if (!selected) return;
    for (const group of selected.modifier_groups || []) {
      if (group.required && !modifiers.some((row) => row.group === group.name)) {
        setFormError(`Choose an option for ${group.name}.`);
        return;
      }
    }
    const productId = selected.id;
    const key = `${productId}|${variantName}|${modifiers.map((row) => `${row.group}:${row.option}`).sort().join("|")}`;
    const unitPrice = itemUnitPrice(selected, quantity, variantName, modifiers);
    setCart((current) => {
      const match = current.find((line) => line.key === key);
      if (match) {
        return current.map((line) => line.key === key
          ? { ...line, quantity: line.quantity + quantity, price: Number((unitPrice * (line.quantity + quantity)).toFixed(2)), unit_price: unitPrice }
          : line);
      }
      return [...current, {
        key,
        product_id: productId,
        product_name: selected.name,
        quantity,
        unit_price: unitPrice,
        price: Number((unitPrice * quantity).toFixed(2)),
        variant_name: variantName || undefined,
        modifiers,
      }];
    });
    setFormError("");
    setSelected(null);
  }

  function changeLineQuantity(key: string, next: number) {
    if (next < 1) {
      setCart((current) => current.filter((line) => line.key !== key));
      return;
    }
    setCart((current) => current.map((line) => line.key === key
      ? { ...line, quantity: next, price: Number((line.unit_price * next).toFixed(2)) }
      : line));
  }

  async function submitOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!store || cart.length === 0) return;
    setSubmitting(true);
    setFormError("");
    const data = new FormData(event.currentTarget);
    const body = {
      customer_name: data.get("name"),
      phone: data.get("phone"),
      email: data.get("email"),
      delivery_type: data.get("delivery_type"),
      delivery_address: data.get("delivery_address"),
      notes: data.get("notes"),
      items: cart.map(({ product_id, quantity, variant_name, modifiers }) => ({ product_id, quantity, variant_name, modifiers })),
    };
    try {
      const response = await fetch(`${API_BASE}/storefront/public/${encodeURIComponent(store.slug)}/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || "Could not place your order.");
      if (result.payment_action === "redirect" && result.checkout_url) {
        window.location.assign(result.checkout_url);
        return;
      }
      if (result.payment_action === "payment_unavailable" && result.order_token) {
        window.location.assign(`/s/${encodeURIComponent(store.slug)}/checkout?order=${encodeURIComponent(result.order_token)}&cancelled=1`);
        return;
      }
      setCart([]);
      setCheckoutOpen(false);
      setOrderMessage(result.payment_action === "awaiting_mobile_money"
        ? "A payment prompt has been sent to your phone. Your order will confirm after payment."
        : `Order ${result.order_number} received. The business will confirm it shortly.`);
    } catch (reason: unknown) {
      setFormError(reason instanceof Error ? reason.message : "Could not place your order.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <main className="min-h-screen grid place-items-center bg-slate-50"><Loader2 className="animate-spin text-brand-dark" size={30} /></main>;
  if (error || !store) return (
    <main className="min-h-screen grid place-items-center bg-slate-50 p-6 text-center">
      <div className="max-w-sm"><AlertCircle size={42} className="mx-auto mb-4 text-slate-300" /><h1 className="text-xl font-bold text-slate-800">Catalog unavailable</h1><p className="mt-2 text-sm text-slate-500">{error || "This catalog could not be found."}</p></div>
    </main>
  );

  function CartSummary({ store: activeStore }: { store: Store }) {
    return <>
      <div className="flex items-center justify-between"><h2 className="font-bold">Your order</h2><span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{itemCount} items</span></div>
      <div className="mt-4 divide-y divide-slate-100">
        {cart.map((line) => <div key={line.key} className="py-3"><p className="text-sm font-medium">{line.product_name}</p>{line.variant_name && <p className="text-xs text-slate-400">{line.variant_name}</p>}{line.modifiers.map((modifier) => <p className="text-xs text-slate-400" key={`${modifier.group}:${modifier.option}`}>{modifier.group}: {modifier.option}</p>)}<div className="mt-2 flex items-center justify-between"><div className="flex items-center rounded-lg border border-slate-200"><button aria-label="Reduce quantity" onClick={() => changeLineQuantity(line.key, line.quantity - 1)} className="p-1.5 text-slate-500"><Minus size={14} /></button><span className="w-7 text-center text-sm">{line.quantity}</span><button aria-label="Increase quantity" onClick={() => changeLineQuantity(line.key, line.quantity + 1)} className="p-1.5 text-slate-500"><Plus size={14} /></button></div><span className="text-sm font-semibold">{formatCurrency(line.price, activeStore.currency)}</span></div></div>)}
      </div>
      <div className="mt-4 flex justify-between border-t border-slate-200 pt-4 font-bold"><span>Total</span><span>{formatCurrency(total, activeStore.currency)}</span></div>
      <button onClick={() => { setCartOpen(false); setCheckoutOpen(true); }} className="mt-4 w-full rounded-xl bg-brand-dark px-4 py-3 text-sm font-bold text-white hover:bg-brand">{activeStore.checkout.payment_label}</button>
      {!activeStore.checkout.online_payment_available && <p className="mt-2 text-center text-xs text-slate-500">The business will confirm payment details after your order.</p>}
    </>;
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="bg-brand-ink text-white"><div className="mx-auto max-w-6xl px-4 py-7 sm:px-6"><p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-light">Zilo catalog</p><h1 className="mt-1 text-3xl font-bold">{store.business_name}</h1><p className="mt-2 text-sm text-white/70">Browse, order, and pay securely.</p></div></header>

      <div className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto max-w-6xl px-4 py-3 sm:px-6">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search products..."
              className="w-full rounded-full border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-4 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
          </div>
          {categories.length > 2 && <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {categories.map((category) => <button
              key={category}
              type="button"
              onClick={() => setSelectedCategory(category)}
              className={`shrink-0 rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${category === selectedCategory ? "bg-brand-dark text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
            >{category}</button>)}
          </div>}
        </div>
      </div>

      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-7 pb-28 sm:px-6 lg:grid-cols-[1fr_340px] lg:pb-7">
        <section>
          {orderMessage && <div className="mb-5 flex gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"><Check className="mt-0.5 shrink-0" size={18} />{orderMessage}</div>}
          {store.products.length === 0 ? <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">This catalog does not have products available right now.</div> : filteredProducts.length === 0 ? <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">No products match your search.</div> : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 xl:grid-cols-4">
              {filteredProducts.map((product) => {
                const image = resolveMediaUrl(product.images?.[0] || product.image_url);
                const salePrice = displayedPrice(product);
                const hasDiscount = product.discount_price != null && product.discount_price < product.price;
                const savePercent = hasDiscount ? Math.round((1 - product.discount_price! / product.price) * 100) : 0;
                const lowStock = product.in_stock && product.stock_quantity != null && product.stock_quantity > 0 && product.stock_quantity <= 5;
                return <article key={product.id} className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md">
                  <button type="button" onClick={() => beginAdd(product)} className="relative block w-full text-left" aria-label={`View ${product.name}`}>
                    <div className="aspect-square overflow-hidden bg-gradient-to-b from-slate-100 to-slate-50">{image ? <img src={image} alt={product.name} className={`h-full w-full object-cover transition-transform duration-300 group-hover:scale-105 ${!product.in_stock ? "opacity-50 grayscale" : ""}`} /> : <div className="grid h-full place-items-center text-slate-300"><ShoppingBag size={40} /></div>}</div>
                    {hasDiscount && <span className="absolute left-2 top-2 rounded-full bg-orange-500 px-2 py-0.5 text-[11px] font-bold text-white shadow-sm">-{savePercent}%</span>}
                    {!product.in_stock && <span className="absolute inset-0 grid place-items-center bg-slate-900/10"><span className="rounded-full bg-slate-900/80 px-3 py-1 text-xs font-semibold text-white">Out of stock</span></span>}
                  </button>
                  <div className="p-3 sm:p-4"><p className="truncate text-[11px] text-slate-400 sm:text-xs">{product.category}</p><button type="button" onClick={() => beginAdd(product)} className="mt-1 line-clamp-2 min-h-10 text-left text-sm font-semibold leading-snug hover:text-brand-dark hover:underline sm:text-base">{product.name}</button>{product.description && <p className="mt-1 line-clamp-2 text-xs text-slate-500 sm:text-sm">{product.description}</p>}<div className="mt-3"><div className="flex items-baseline gap-1.5"><p className={`text-sm font-bold sm:text-base ${hasDiscount ? "text-orange-600" : "text-brand-dark"}`}>{formatCurrency(salePrice, store.currency)}</p>{hasDiscount && <p className="text-xs text-slate-400 line-through">{formatCurrency(product.price, store.currency)}</p>}</div>{product.unit && <p className="text-xs text-slate-400">{product.unit}</p>}{lowStock && <p className="mt-1 text-xs font-semibold text-orange-600">Only {product.stock_quantity} left</p>}<button type="button" disabled={!product.in_stock} onClick={() => beginAdd(product)} className="mt-3 w-full rounded-lg bg-brand-dark px-2 py-2 text-xs font-semibold text-white hover:bg-brand disabled:cursor-not-allowed disabled:bg-slate-300">{product.in_stock ? "View details" : "Out of stock"}</button></div></div>
                </article>;
              })}
            </div>
          )}
        </section>
        <aside className="hidden h-fit rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:sticky lg:top-6 lg:block">{cart.length === 0 ? <><div className="flex items-center justify-between"><h2 className="font-bold">Your order</h2><span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">0 items</span></div><p className="py-8 text-center text-sm text-slate-500">Your bag is empty.</p></> : <CartSummary store={store} />}</aside>
      </div>

      {cart.length > 0 && <button type="button" onClick={() => setCartOpen(true)} className="fixed inset-x-4 bottom-4 z-40 flex items-center justify-between rounded-2xl bg-brand-dark px-5 py-4 text-sm font-bold text-white shadow-xl lg:hidden"><span className="flex items-center gap-2"><ShoppingBag size={18} />View cart <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs">{itemCount}</span></span><span>{formatCurrency(total, store.currency)}</span></button>}

      {cartOpen && <div className="fixed inset-0 z-50 grid place-items-end bg-slate-900/40 sm:place-items-center sm:p-4" onMouseDown={() => setCartOpen(false)}><div className="max-h-[80vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-bold">Your cart</h2><button type="button" aria-label="Close cart" onClick={() => setCartOpen(false)} className="text-slate-400"><X /></button></div><CartSummary store={store} /></div></div>}

      {selected && <div className="fixed inset-0 z-50 overflow-y-auto bg-white text-slate-900" role="dialog" aria-modal="true" aria-label={`${selected.name} details`}>
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-100 bg-white/95 px-4 backdrop-blur">
          <button type="button" onClick={() => { setSelected(null); setFormError(""); }} className="rounded-full p-2 text-slate-700 hover:bg-slate-100" aria-label="Back to catalog"><span aria-hidden="true">←</span></button>
          <p className="max-w-[70%] truncate text-sm font-semibold">{selected.name}</p>
          <button type="button" onClick={() => { setSelected(null); setFormError(""); }} className="rounded-full p-2 text-slate-500 hover:bg-slate-100" aria-label="Close product details"><X size={20} /></button>
        </header>
        <div className="mx-auto max-w-2xl pb-28">
          {selectedImages.length > 0 ? <section className="bg-slate-50">
            <div className="relative aspect-square overflow-hidden bg-slate-100 sm:aspect-[4/3]">
              <img src={selectedImages[Math.min(selectedImageIndex, selectedImages.length - 1)]} alt={`${selected.name} photo ${selectedImageIndex + 1}`} className="h-full w-full object-contain" />
              {selectedImages.length > 1 && <span className="absolute bottom-3 right-3 rounded-full bg-slate-900/70 px-2.5 py-1 text-xs font-medium text-white">{selectedImageIndex + 1} / {selectedImages.length}</span>}
            </div>
            {selectedImages.length > 1 && <div className="flex snap-x gap-2 overflow-x-auto px-4 py-3">
              {selectedImages.map((image, index) => <button type="button" key={image} onClick={() => setSelectedImageIndex(index)} aria-label={`View photo ${index + 1}`} className={`h-16 w-16 shrink-0 snap-start overflow-hidden rounded-lg border-2 ${index === selectedImageIndex ? "border-brand-dark" : "border-transparent"}`}><img src={image} alt="" className="h-full w-full object-cover" /></button>)}
            </div>}
          </section> : <div className="grid aspect-square place-items-center bg-slate-100 text-slate-300"><ShoppingBag size={42} /></div>}

          <section className="px-4 pt-5">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{selected.category}</p>
            <div className="mt-1 flex items-start justify-between gap-4"><h2 className="text-2xl font-bold leading-tight">{selected.name}</h2><p className="shrink-0 text-xl font-bold text-brand-dark">{formatCurrency(selectedPrice, store.currency)}</p></div>
            {selected.discount_price != null && selected.discount_price < selected.price && <p className="mt-1 text-sm text-slate-400 line-through">{formatCurrency(selected.price, store.currency)}</p>}
            {selected.description && <p className="mt-5 whitespace-pre-line text-sm leading-6 text-slate-600">{selected.description}</p>}
            {selected.unit && <p className="mt-4 text-sm text-slate-500">Sold as: {selected.unit}</p>}

            {(selected.variants || []).length > 0 && <label className="mt-6 block text-sm font-semibold">Choose an option<select value={variantName} onChange={(event) => setVariantName(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm"><option value="">Standard — {formatCurrency(displayedPrice(selected), store.currency)}</option>{selected.variants!.map((variant) => <option key={variant.name} value={variant.name}>{variant.name} — {formatCurrency(variant.price, store.currency)}</option>)}</select></label>}
            {(selected.modifier_groups || []).map((group) => <div key={group.name} className="mt-6"><p className="text-sm font-semibold">{group.name}{group.required && <span className="text-rose-500"> *</span>}</p><div className="mt-2 grid gap-2">{group.options.map((option) => { const picked = modifiers.some((row) => row.group === group.name && row.option === option.name); return <button type="button" key={option.name} onClick={() => toggleModifier(group, option)} className={`flex items-center justify-between rounded-xl border px-4 py-3 text-left text-sm ${picked ? "border-brand-dark bg-emerald-50 text-brand-ink" : "border-slate-200 bg-white"}`}><span>{option.name}</span><span>{Number(option.price_delta || 0) > 0 ? `+${formatCurrency(option.price_delta, store.currency)}` : ""}</span></button>; })}</div></div>)}
          </section>
        </div>
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-[0_-8px_24px_rgba(15,23,42,0.08)]"><div className="mx-auto flex max-w-2xl items-center gap-3"><div className="flex shrink-0 items-center rounded-xl border border-slate-200"><button type="button" onClick={() => setQuantity((current) => Math.max(Number(selected.moq || 1), current - 1))} className="p-3" aria-label="Reduce quantity"><Minus size={18} /></button><span className="w-9 text-center font-medium">{quantity}</span><button type="button" onClick={() => setQuantity((current) => current + 1)} className="p-3" aria-label="Increase quantity"><Plus size={18} /></button></div><button type="button" onClick={addSelected} className="flex-1 rounded-xl bg-brand-dark py-3.5 text-sm font-bold text-white">Add to cart · {formatCurrency(selectedPrice * quantity, store.currency)}</button></div>{formError && <p className="mx-auto mt-2 max-w-2xl text-sm text-rose-600">{formError}</p>}</div>
      </div>}

      {checkoutOpen && <div className="fixed inset-0 z-50 grid place-items-end bg-slate-900/40 sm:place-items-center sm:p-4" onMouseDown={() => setCheckoutOpen(false)}><form onSubmit={submitOrder} className="w-full max-w-md rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-center justify-between"><h2 className="font-bold">Checkout</h2><button type="button" onClick={() => setCheckoutOpen(false)} className="text-slate-400"><X /></button></div><p className="mt-1 text-sm text-slate-500">{formatCurrency(total, store.currency)} · {store.business_name}</p>{formError && <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{formError}</p>}<div className="mt-4 grid gap-3"><input name="name" required placeholder="Your name" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/><input name="phone" required type="tel" placeholder="Phone number with country code" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/>{store.checkout.online_payment_available && <input name="email" required type="email" placeholder="Email for secure payment" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/>}<label className="text-sm font-medium">Delivery<select name="delivery_type" className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"><option value="pickup">Pickup</option><option value="delivery">Delivery</option></select></label><textarea name="delivery_address" placeholder="Delivery address (if needed)" className="min-h-20 rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/><textarea name="notes" placeholder="Order note (optional)" className="min-h-16 rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/></div><button disabled={submitting} className="mt-5 flex w-full items-center justify-center rounded-xl bg-brand-dark py-3 text-sm font-bold text-white disabled:opacity-60">{submitting ? <Loader2 className="animate-spin" size={18} /> : store.checkout.online_payment_available ? "Continue to secure payment" : "Place order"}</button></form></div>}
    </main>
  );
}
