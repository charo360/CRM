"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { AlertCircle, Check, ChevronDown, Loader2, Minus, Plus, ShoppingBag, X } from "lucide-react";
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
  if (!variant && tiers[0]) value = Number(tiers[0].price);
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
  const [quantity, setQuantity] = useState(1);
  const [variantName, setVariantName] = useState("");
  const [modifiers, setModifiers] = useState<SelectedModifier[]>([]);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [orderMessage, setOrderMessage] = useState("");

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
  const selectedPrice = selected ? itemUnitPrice(selected, quantity, variantName, modifiers) : 0;

  function beginAdd(product: Product) {
    setSelected(product);
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

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="bg-brand-ink text-white"><div className="mx-auto max-w-6xl px-4 py-7 sm:px-6"><p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-light">Zilo catalog</p><h1 className="mt-1 text-3xl font-bold">{store.business_name}</h1><p className="mt-2 text-sm text-white/70">Browse, order, and pay securely.</p></div></header>
      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-7 sm:px-6 lg:grid-cols-[1fr_340px]">
        <section>
          {orderMessage && <div className="mb-5 flex gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"><Check className="mt-0.5 shrink-0" size={18} />{orderMessage}</div>}
          {store.products.length === 0 ? <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">This catalog does not have products available right now.</div> : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {store.products.map((product) => {
                const image = resolveMediaUrl(product.images?.[0] || product.image_url);
                const salePrice = displayedPrice(product);
                return <article key={product.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                  <div className="aspect-[4/3] bg-slate-100">{image ? <img src={image} alt={product.name} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-slate-300"><ShoppingBag size={30} /></div>}</div>
                  <div className="p-4"><p className="text-xs text-slate-400">{product.category}</p><h2 className="mt-1 font-semibold leading-snug">{product.name}</h2>{product.description && <p className="mt-1 line-clamp-2 text-sm text-slate-500">{product.description}</p>}<div className="mt-3 flex items-end justify-between gap-2"><div><p className="font-bold text-brand-dark">{formatCurrency(salePrice, store.currency)}</p>{product.discount_price != null && product.discount_price < product.price && <p className="text-xs text-slate-400 line-through">{formatCurrency(product.price, store.currency)}</p>}{product.unit && <p className="text-xs text-slate-400">{product.unit}</p>}</div><button type="button" disabled={!product.in_stock} onClick={() => beginAdd(product)} className="rounded-lg bg-brand-dark px-3 py-2 text-xs font-semibold text-white hover:bg-brand disabled:cursor-not-allowed disabled:bg-slate-300">{product.in_stock ? "Add" : "Out of stock"}</button></div></div>
                </article>;
              })}
            </div>
          )}
        </section>
        <aside className="h-fit rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:sticky lg:top-6"><div className="flex items-center justify-between"><h2 className="font-bold">Your order</h2><span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{itemCount} items</span></div>{cart.length === 0 ? <p className="py-8 text-center text-sm text-slate-500">Your bag is empty.</p> : <><div className="mt-4 divide-y divide-slate-100">{cart.map((line) => <div key={line.key} className="py-3"><p className="text-sm font-medium">{line.product_name}</p>{line.variant_name && <p className="text-xs text-slate-400">{line.variant_name}</p>}{line.modifiers.map((modifier) => <p className="text-xs text-slate-400" key={`${modifier.group}:${modifier.option}`}>{modifier.group}: {modifier.option}</p>)}<div className="mt-2 flex items-center justify-between"><div className="flex items-center rounded-lg border border-slate-200"><button aria-label="Reduce quantity" onClick={() => changeLineQuantity(line.key, line.quantity - 1)} className="p-1.5 text-slate-500"><Minus size={14} /></button><span className="w-7 text-center text-sm">{line.quantity}</span><button aria-label="Increase quantity" onClick={() => changeLineQuantity(line.key, line.quantity + 1)} className="p-1.5 text-slate-500"><Plus size={14} /></button></div><span className="text-sm font-semibold">{formatCurrency(line.price, store.currency)}</span></div></div>)}</div><div className="mt-4 flex justify-between border-t border-slate-200 pt-4 font-bold"><span>Total</span><span>{formatCurrency(total, store.currency)}</span></div><button onClick={() => setCheckoutOpen(true)} className="mt-4 w-full rounded-xl bg-brand-dark px-4 py-3 text-sm font-bold text-white hover:bg-brand">{store.checkout.payment_label}</button>{!store.checkout.online_payment_available && <p className="mt-2 text-center text-xs text-slate-500">The business will confirm payment details after your order.</p>}</>}</aside>
      </div>

      {selected && <div className="fixed inset-0 z-50 grid place-items-end bg-slate-900/40 p-0 sm:place-items-center sm:p-4" onMouseDown={() => { setSelected(null); setFormError(""); }}><div className="w-full max-w-md rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-start justify-between gap-4"><div><h2 className="font-bold">{selected.name}</h2><p className="mt-1 text-sm text-brand-dark">{formatCurrency(selectedPrice, store.currency)} each</p></div><button onClick={() => setSelected(null)} className="text-slate-400"><X /></button></div>{(selected.variants || []).length > 0 && <label className="mt-4 block text-sm font-medium">Option<select value={variantName} onChange={(event) => setVariantName(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2"><option value="">Standard — {formatCurrency(displayedPrice(selected), store.currency)}</option>{selected.variants!.map((variant) => <option key={variant.name} value={variant.name}>{variant.name} — {formatCurrency(variant.price, store.currency)}</option>)}</select></label>}{(selected.modifier_groups || []).map((group) => <div key={group.name} className="mt-4"><p className="text-sm font-medium">{group.name}{group.required && <span className="text-rose-500"> *</span>}</p><div className="mt-2 grid gap-2">{group.options.map((option) => { const picked = modifiers.some((row) => row.group === group.name && row.option === option.name); return <button type="button" key={option.name} onClick={() => toggleModifier(group, option)} className={`flex items-center justify-between rounded-lg border px-3 py-2 text-left text-sm ${picked ? "border-brand-dark bg-emerald-50 text-brand-ink" : "border-slate-200"}`}><span>{option.name}</span><span>{Number(option.price_delta || 0) > 0 ? `+${formatCurrency(option.price_delta, store.currency)}` : ""}</span></button>; })}</div></div>)}<div className="mt-5 flex items-center justify-between"><span className="text-sm font-medium">Quantity</span><div className="flex items-center rounded-lg border border-slate-200"><button onClick={() => setQuantity((current) => Math.max(Number(selected.moq || 1), current - 1))} className="p-2"><Minus size={16} /></button><span className="w-9 text-center">{quantity}</span><button onClick={() => setQuantity((current) => current + 1)} className="p-2"><Plus size={16} /></button></div></div>{formError && <p className="mt-3 text-sm text-rose-600">{formError}</p>}<button onClick={addSelected} className="mt-5 w-full rounded-xl bg-brand-dark py-3 text-sm font-bold text-white">Add to order — {formatCurrency(selectedPrice * quantity, store.currency)}</button></div></div>}

      {checkoutOpen && <div className="fixed inset-0 z-50 grid place-items-end bg-slate-900/40 sm:place-items-center sm:p-4" onMouseDown={() => setCheckoutOpen(false)}><form onSubmit={submitOrder} className="w-full max-w-md rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-center justify-between"><h2 className="font-bold">Checkout</h2><button type="button" onClick={() => setCheckoutOpen(false)} className="text-slate-400"><X /></button></div><p className="mt-1 text-sm text-slate-500">{formatCurrency(total, store.currency)} · {store.business_name}</p>{formError && <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{formError}</p>}<div className="mt-4 grid gap-3"><input name="name" required placeholder="Your name" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/><input name="phone" required type="tel" placeholder="Phone number with country code" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/>{store.checkout.online_payment_available && <input name="email" required type="email" placeholder="Email for secure payment" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/>}<label className="text-sm font-medium">Delivery<select name="delivery_type" className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"><option value="pickup">Pickup</option><option value="delivery">Delivery</option></select></label><textarea name="delivery_address" placeholder="Delivery address (if needed)" className="min-h-20 rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/><textarea name="notes" placeholder="Order note (optional)" className="min-h-16 rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/></div><button disabled={submitting} className="mt-5 flex w-full items-center justify-center rounded-xl bg-brand-dark py-3 text-sm font-bold text-white disabled:opacity-60">{submitting ? <Loader2 className="animate-spin" size={18} /> : store.checkout.online_payment_available ? "Continue to secure payment" : "Place order"}</button></form></div>}
    </main>
  );
}
