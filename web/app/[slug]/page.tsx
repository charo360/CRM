"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { AlertCircle, CalendarDays, Check, ChevronDown, Loader2, MessageCircle, Minus, Plus, Search, ShoppingBag, X } from "lucide-react";
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
  duration?: number | null;
  moq?: number;
  pricing_tiers?: { min_qty: number; price: number }[];
  variants?: Variant[];
  modifier_groups?: ModifierGroup[];
};
type Store = {
  slug: string;
  business_name: string;
  currency: string;
  /** Digits only, present only when the shop has WhatsApp linked. */
  whatsapp?: string | null;
  /** "shop" sells goods from a cart; "booking" sells time. */
  mode?: "shop" | "booking";
  booking_kind?: "appointment" | "stay" | null;
  /** A restaurant sells from its menu and also holds tables. */
  takes_table_bookings?: boolean;
  /** What this trade calls a booking: Appointment, Reservation, Class... */
  booking_label?: string;
  item_label?: string;
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

// Stands in for a service when what is being booked is a table. Module level
// so its identity survives a re-render — the dialog compares against it.
const TABLE = { id: "", name: "Table booking", duration: null } as unknown as Product;

/** "Appointment" -> "an appointment"; "Reservation" -> "a reservation". */
function withArticle(word: string): string {
  const lower = word.toLowerCase();
  return `${/^[aeiou]/.test(lower) ? "an" : "a"} ${lower}`;
}

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
  const [orderNumber, setOrderNumber] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [reportOpen, setReportOpen] = useState(false);
  const [reportReason, setReportReason] = useState("scam");
  const [reportDetail, setReportDetail] = useState("");
  const [reportSent, setReportSent] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [bookingFor, setBookingFor] = useState<Product | null>(null);
  const [bookingDate, setBookingDate] = useState("");
  const [bookingTime, setBookingTime] = useState("");
  const [bookingCheckout, setBookingCheckout] = useState("");
  const [bookingBusy, setBookingBusy] = useState(false);
  const [bookingError, setBookingError] = useState("");
  const [tableOpen, setTableOpen] = useState(false);
  const [partySize, setPartySize] = useState("2");
  const confirmationRef = useRef<HTMLDivElement>(null);

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

  async function submitReport() {
    if (!store) return;
    setReportBusy(true);
    try {
      await fetch(`${API_BASE}/storefront/public/${encodeURIComponent(store.slug)}/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reportReason, detail: reportDetail }),
      });
      setReportSent(true);
    } catch {
      // A failed report should not leave the buyer stuck in the dialog.
      setReportSent(true);
    } finally {
      setReportBusy(false);
    }
  }

  const isBooking = store?.mode === "booking";
  const isStay = store?.booking_kind === "stay";
  const takesTables = Boolean(store?.takes_table_bookings);
  const bookingWord = store?.booking_label || "Booking";
  const overlayOpen = Boolean(selected) || cartOpen || checkoutOpen || reportOpen || Boolean(bookingFor) || tableOpen;

  function closeOverlays() {
    setSelected(null);
    setCartOpen(false);
    setCheckoutOpen(false);
    setReportOpen(false);
    setBookingFor(null);
    setTableOpen(false);
    setFormError("");
  }

  function beginBooking(service: Product) {
    setBookingFor(service);
    setBookingDate("");
    setBookingTime("");
    setBookingCheckout("");
    setBookingError("");
  }

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!store || !bookingFor) return;
    setBookingBusy(true);
    setBookingError("");
    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API_BASE}/storefront/public/${encodeURIComponent(store.slug)}/bookings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service_id: bookingFor === TABLE ? "" : bookingFor.id,
          party_size: bookingFor === TABLE ? Number(partySize) : undefined,
          date: bookingDate,
          time: isStay ? "00:00" : bookingTime,
          checkout_date: isStay ? bookingCheckout : "",
          customer_name: data.get("name"),
          phone: data.get("phone"),
          notes: data.get("notes"),
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || "Could not request this booking.");
      setBookingFor(null);
      setOrderNumber(result.booking_number || "");
      setOrderMessage(
        `${result.booking_number} requested for ${result.date}${result.checkout_date ? ` to ${result.checkout_date}` : result.time ? ` at ${result.time}` : ""}. The business will confirm it shortly.`,
      );
    } catch (reason: unknown) {
      setBookingError(reason instanceof Error ? reason.message : "Could not request this booking.");
    } finally {
      setBookingBusy(false);
    }
  }

  // A product opens over the shop rather than as its own page, so the phone's
  // back button would leave the shop entirely instead of returning to the
  // list. Add a history entry while anything is open and close it on back.
  useEffect(() => {
    if (!overlayOpen) return;
    window.history.pushState({ zilo: "overlay" }, "");
    const handlePop = () => closeOverlays();
    window.addEventListener("popstate", handlePop);
    return () => {
      window.removeEventListener("popstate", handlePop);
      // Closed from the page instead of the back button, so drop the entry
      // that was added or the next back press would do nothing.
      if (window.history.state?.zilo === "overlay") window.history.back();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayOpen]);

  // The order confirmation, and the WhatsApp button in it, sit above whatever
  // the buyer was looking at. Take them to it rather than leaving them where
  // the checkout closed.
  useEffect(() => {
    if (!orderMessage) return;
    let cancelled = false;
    const bring = (behavior: ScrollBehavior) => {
      const element = confirmationRef.current;
      if (cancelled || !element) return;
      const { top, bottom } = element.getBoundingClientRect();
      if (top >= 0 && bottom <= window.innerHeight) return;
      element.scrollIntoView({ behavior, block: "center" });
    };
    // The checkout sheet is unmounting and the cart emptying in this same
    // render, so wait a frame before moving.
    const frame = requestAnimationFrame(() => bring("smooth"));
    // On a phone the keyboard used to fill the form dismisses after that,
    // changing the viewport height and carrying the page away from where it
    // just scrolled. Check once more and correct if it drifted.
    const settle = setTimeout(() => bring("auto"), 700);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      clearTimeout(settle);
    };
  }, [orderMessage]);

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
        window.location.assign(`/${encodeURIComponent(store.slug)}/checkout?order=${encodeURIComponent(result.order_token)}&cancelled=1`);
        return;
      }
      setCart([]);
      setCheckoutOpen(false);
      setOrderNumber(result.order_number || "");
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
      <header className="bg-brand-ink text-white"><div className="mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-7"><p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-light">Zilo catalog</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">{store.business_name}</h1><p className="mt-1.5 text-sm text-white/70">Browse, order, and pay securely.</p>
        {takesTables && <button
          type="button"
          onClick={() => { setBookingFor(TABLE); setBookingDate(""); setBookingTime(""); setBookingError(""); }}
          className="mt-4 mr-2 inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/20"
        ><CalendarDays size={16} />Book a table</button>}
        {store.whatsapp && <a
          href={`https://wa.me/${store.whatsapp}?text=${encodeURIComponent(`Hi ${store.business_name}, I have a question about your shop.`)}`}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/20"
        ><MessageCircle size={16} />Message us on WhatsApp</a>}
      </div></header>

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
          {categories.length > 2 && <div className="mt-3 flex gap-2 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
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
          {orderMessage && <div ref={confirmationRef} className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
            <div className="flex gap-3"><Check className="mt-0.5 shrink-0" size={18} />{orderMessage}</div>
            {store.whatsapp && <a
              href={`https://wa.me/${store.whatsapp}?text=${encodeURIComponent(`Hi ${store.business_name}, I just placed order ${orderNumber} on your shop.`)}`}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700"
            ><MessageCircle size={16} />Continue on WhatsApp</a>}
          </div>}
          {store.products.length === 0 ? <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">This catalog does not have products available right now.</div> : filteredProducts.length === 0 ? <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">No products match your search.</div> : (
            <div className="columns-2 gap-2 sm:columns-3 sm:gap-3 xl:columns-4">
              {filteredProducts.map((product) => {
                const image = resolveMediaUrl(product.images?.[0] || product.image_url);
                const salePrice = displayedPrice(product);
                const hasDiscount = product.discount_price != null && product.discount_price < product.price;
                const savePercent = hasDiscount ? Math.round((1 - product.discount_price! / product.price) * 100) : 0;
                const lowStock = product.in_stock && product.stock_quantity != null && product.stock_quantity > 0 && product.stock_quantity <= 5;
                // Columns (not grid) so each card is only as tall as its own
                // photo — a grid row stretches every card to the tallest one,
                // which is what left the big empty gap under short cards.
                return <article key={product.id} className="group mb-2 break-inside-avoid overflow-hidden rounded-xl bg-white transition-shadow hover:shadow-md sm:mb-3">
                  <button type="button" onClick={() => beginAdd(product)} className="relative block w-full text-left" aria-label={`View ${product.name}`}>
                    {image
                      ? <img src={image} alt={product.name} className={`w-full max-h-[26rem] object-cover transition-transform duration-300 group-hover:scale-105 ${!product.in_stock ? "opacity-50 grayscale" : ""}`} />
                      : <div className="grid aspect-square place-items-center bg-slate-100 text-slate-300"><ShoppingBag size={40} /></div>}
                    {hasDiscount && <span className="absolute left-2 top-2 rounded-full bg-orange-500 px-2 py-0.5 text-[11px] font-bold text-white shadow-sm">-{savePercent}%</span>}
                    {!product.in_stock && <span className="absolute inset-0 grid place-items-center bg-slate-900/10"><span className="rounded-full bg-slate-900/80 px-3 py-1 text-xs font-semibold text-white">Out of stock</span></span>}
                  </button>
                  <div className="px-2 pb-2.5 pt-2">
                    <button type="button" onClick={() => beginAdd(product)} className="line-clamp-2 text-left text-[13px] font-medium leading-snug text-slate-800 hover:text-brand-dark sm:text-sm">{product.name}</button>
                    {lowStock && <p className="mt-1 text-[11px] font-semibold text-orange-600">Only {product.stock_quantity} left</p>}
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-baseline gap-1">
                        <p className={`truncate text-base font-bold ${hasDiscount ? "text-orange-600" : "text-brand-dark"}`}>{formatCurrency(salePrice, store.currency)}</p>
                        {hasDiscount && <p className="shrink-0 text-[11px] text-slate-400 line-through">{formatCurrency(product.price, store.currency)}</p>}
                      </div>
                      {isBooking ? <button
                        type="button"
                        disabled={!product.in_stock}
                        onClick={() => beginBooking(product)}
                        className="shrink-0 rounded-full bg-brand-dark px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                      >Book</button> : <button
                        type="button"
                        disabled={!product.in_stock}
                        onClick={() => beginAdd(product)}
                        aria-label={product.in_stock ? `Add ${product.name}` : "Out of stock"}
                        className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-dark text-white transition-colors hover:bg-brand disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                      ><Plus size={16} /></button>}
                    </div>
                    {isBooking && product.duration ? <p className="mt-0.5 text-[11px] text-slate-400">{product.duration} min</p> : product.unit ? <p className="mt-0.5 text-[11px] text-slate-400">{product.unit}</p> : null}
                  </div>
                </article>;
              })}
            </div>
          )}
        </section>
        <aside className="hidden h-fit rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:sticky lg:top-6 lg:block">{cart.length === 0 ? <><div className="flex items-center justify-between"><h2 className="font-bold">Your order</h2><span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">0 items</span></div><p className="py-8 text-center text-sm text-slate-500">Your bag is empty.</p></> : <CartSummary store={store} />}</aside>
      </div>

      <footer className="mx-auto max-w-6xl px-4 pb-24 text-center sm:px-6 lg:pb-8">
        <button type="button" onClick={() => { setReportOpen(true); setReportSent(false); }} className="text-xs text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline">
          Report this shop
        </button>
      </footer>

      {bookingFor && <div className="fixed inset-0 z-50 grid place-items-end bg-slate-900/40 sm:place-items-center sm:p-4" onMouseDown={() => setBookingFor(null)}>
        <form onSubmit={submitBooking} className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl" onMouseDown={(event) => event.stopPropagation()}>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="font-bold">{bookingFor === TABLE ? "Book a table" : isStay ? "Request these dates" : `Request ${withArticle(bookingWord)}`}</h2>
              <p className="mt-0.5 truncate text-sm text-slate-500">
                {bookingFor === TABLE ? store.business_name : <>
                  {bookingFor.name}
                  {bookingFor.duration ? ` · ${bookingFor.duration} min` : ""}
                  {` · ${formatCurrency(displayedPrice(bookingFor), store.currency)}`}
                </>}
              </p>
            </div>
            <button type="button" aria-label="Close" onClick={() => setBookingFor(null)} className="shrink-0 text-slate-400"><X /></button>
          </div>

          {bookingError && <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{bookingError}</p>}

          <div className="mt-4 grid gap-3">
            <label className="text-sm font-medium">{isStay ? "Check in" : "Date"}
              <input type="date" required value={bookingDate} min={new Date().toISOString().slice(0, 10)}
                onChange={(event) => setBookingDate(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm" />
            </label>
            {isStay ? (
              <label className="text-sm font-medium">Check out
                <input type="date" required value={bookingCheckout} min={bookingDate || new Date().toISOString().slice(0, 10)}
                  onChange={(event) => setBookingCheckout(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
            ) : (
              <label className="text-sm font-medium">Preferred time
                <input type="time" required value={bookingTime}
                  onChange={(event) => setBookingTime(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm" />
              </label>
            )}
            {bookingFor === TABLE && <label className="text-sm font-medium">How many people
              <input type="number" required min={1} max={50} value={partySize}
                onChange={(event) => setPartySize(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm" />
            </label>}
            <input name="name" required placeholder="Your name" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm" />
            <input name="phone" required type="tel" placeholder="Phone number with country code" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm" />
            <textarea name="notes" placeholder="Anything they should know (optional)" className="min-h-16 rounded-lg border border-slate-200 px-3 py-2.5 text-sm" />
          </div>

          <button disabled={bookingBusy} className="mt-5 flex w-full items-center justify-center rounded-xl bg-brand-dark py-3 text-sm font-bold text-white disabled:opacity-60">
            {bookingBusy ? <Loader2 className="animate-spin" size={18} /> : bookingFor === TABLE ? "Request table" : `Request ${bookingWord.toLowerCase()}`}
          </button>
          <p className="mt-2 text-center text-xs text-slate-500">{store.business_name} will confirm your time. Nothing is charged now.</p>
        </form>
      </div>}

      {reportOpen && <div className="fixed inset-0 z-50 grid place-items-end bg-slate-900/40 sm:place-items-center sm:p-4" onMouseDown={() => setReportOpen(false)}>
        <div className="w-full max-w-md rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl" onMouseDown={(event) => event.stopPropagation()}>
          <div className="flex items-center justify-between">
            <h2 className="font-bold">{reportSent ? "Report sent" : "Report this shop"}</h2>
            <button type="button" aria-label="Close" onClick={() => setReportOpen(false)} className="text-slate-400"><X /></button>
          </div>
          {reportSent ? (
            <>
              <p className="mt-3 text-sm text-slate-600">Thank you. Our team will review this shop.</p>
              <button type="button" onClick={() => setReportOpen(false)} className="mt-5 w-full rounded-xl bg-brand-dark py-3 text-sm font-bold text-white">Close</button>
            </>
          ) : (
            <>
              <p className="mt-1 text-sm text-slate-500">Tell us what is wrong with {store.business_name}.</p>
              <div className="mt-4 grid gap-2">
                {[
                  ["scam", "It looks like a scam"],
                  ["not_delivered", "I paid and never received my order"],
                  ["counterfeit", "The products are fake or not as described"],
                  ["offensive", "Offensive or illegal content"],
                  ["other", "Something else"],
                ].map(([value, label]) => (
                  <button
                    type="button"
                    key={value}
                    onClick={() => setReportReason(value)}
                    className={`rounded-xl border px-4 py-3 text-left text-sm ${reportReason === value ? "border-brand-dark bg-emerald-50 text-brand-ink" : "border-slate-200 bg-white"}`}
                  >{label}</button>
                ))}
              </div>
              <textarea
                value={reportDetail}
                onChange={(event) => setReportDetail(event.target.value)}
                placeholder="Anything else we should know (optional)"
                className="mt-3 min-h-20 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm"
              />
              <button type="button" disabled={reportBusy} onClick={() => void submitReport()} className="mt-4 flex w-full items-center justify-center rounded-xl bg-brand-dark py-3 text-sm font-bold text-white disabled:opacity-60">
                {reportBusy ? <Loader2 className="animate-spin" size={18} /> : "Send report"}
              </button>
            </>
          )}
        </div>
      </div>}

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
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-[0_-8px_24px_rgba(15,23,42,0.08)]"><div className="mx-auto flex max-w-2xl items-center gap-3">{isBooking ? <button type="button" onClick={() => { const service = selected; setSelected(null); beginBooking(service); }} className="flex-1 rounded-xl bg-brand-dark py-3.5 text-sm font-bold text-white">Book this · {formatCurrency(selectedPrice, store.currency)}</button> : <><div className="flex shrink-0 items-center rounded-xl border border-slate-200"><button type="button" onClick={() => setQuantity((current) => Math.max(Number(selected.moq || 1), current - 1))} className="p-3" aria-label="Reduce quantity"><Minus size={18} /></button><span className="w-9 text-center font-medium">{quantity}</span><button type="button" onClick={() => setQuantity((current) => current + 1)} className="p-3" aria-label="Increase quantity"><Plus size={18} /></button></div><button type="button" onClick={addSelected} className="flex-1 rounded-xl bg-brand-dark py-3.5 text-sm font-bold text-white">Add to cart · {formatCurrency(selectedPrice * quantity, store.currency)}</button></>}</div>{formError && <p className="mx-auto mt-2 max-w-2xl text-sm text-rose-600">{formError}</p>}</div>
      </div>}

      {checkoutOpen && <div className="fixed inset-0 z-50 grid place-items-end bg-slate-900/40 sm:place-items-center sm:p-4" onMouseDown={() => setCheckoutOpen(false)}><form onSubmit={submitOrder} className="w-full max-w-md rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-center justify-between"><h2 className="font-bold">Checkout</h2><button type="button" onClick={() => setCheckoutOpen(false)} className="text-slate-400"><X /></button></div><p className="mt-1 text-sm text-slate-500">{formatCurrency(total, store.currency)} · {store.business_name}</p>{formError && <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{formError}</p>}<div className="mt-4 grid gap-3"><input name="name" required placeholder="Your name" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/><input name="phone" required type="tel" placeholder="Phone number with country code" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/>{store.checkout.online_payment_available && <input name="email" required type="email" placeholder="Email for secure payment" className="rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/>}<label className="text-sm font-medium">Delivery<select name="delivery_type" className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"><option value="pickup">Pickup</option><option value="delivery">Delivery</option></select></label><textarea name="delivery_address" placeholder="Delivery address (if needed)" className="min-h-20 rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/><textarea name="notes" placeholder="Order note (optional)" className="min-h-16 rounded-lg border border-slate-200 px-3 py-2.5 text-sm"/></div><button disabled={submitting} className="mt-5 flex w-full items-center justify-center rounded-xl bg-brand-dark py-3 text-sm font-bold text-white disabled:opacity-60">{submitting ? <Loader2 className="animate-spin" size={18} /> : store.checkout.online_payment_available ? "Continue to secure payment" : "Place order"}</button></form></div>}
    </main>
  );
}
