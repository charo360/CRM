"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { productsApi, storefrontApi, Product, ProductModifierGroup, ProductVariant } from "@/lib/api";
import { formatCurrency, resolveMediaUrl } from "@/lib/utils";
import {
  Plus,
  Pencil,
  Trash2,
  ExternalLink,
  Store,
  Loader2,
  X,
  Trash,
  ImagePlus,
  Wand2,
  Sparkles,
} from "lucide-react";
import { useBusiness } from "@/contexts/BusinessContext";
import { getShopCatalogConfig } from "@/lib/shopCatalog";

type TierRow = { min_qty: string; price: string };

type VariantRow = { name: string; price: string };

type ModifierOptionRow = { name: string; price_delta: string };

type ModifierGroupRow = {
  name: string;
  required: boolean;
  multi_select: boolean;
  options: ModifierOptionRow[];
};

type PendingImage = { file: File; url: string };

type FormState = {
  name: string;
  price: string;
  description: string;
  category: string;
  sub_category: string;
  discount_price: string;
  in_stock: boolean;
  stock_quantity: string;
  unit: string;
  moq: string;
  pricing_tiers: TierRow[];
  /** Resolved URLs already on the server (edit mode). */
  imageUrls: string[];
  variants: VariantRow[];
  modifier_groups: ModifierGroupRow[];
};

const MAX_IMAGES_PER_PRODUCT = 5;

function productImageUrls(p: Product): string[] {
  const imgs = [...(p.images || [])];
  const orig = p.image_url;
  if (orig && !imgs.includes(orig)) imgs.unshift(orig);
  return imgs;
}

function mapBusinessTypeForAi(bt: string | undefined): string {
  const t = (bt || "retail").toLowerCase();
  if (t === "creator") return "creator";
  if (t === "restaurant") return "restaurant";
  if (t === "food") return "restaurant";
  if (t === "bakery") return "restaurant";
  if (t === "grocery") return "retail";
  if (t === "wholesale") return "retail";
  if (t === "rental") return "rental";
  if (t === "hotel") return "hotel";
  if (t === "support") return "support";
  if (t === "healthcare" || t === "clinic") return "healthcare";
  if (t === "fitness" || t === "gym") return "fitness";
  if (t === "services" || t === "repair") return "services";
  if (t === "salon" || t === "beauty") return "salon";
  if (t === "spa") return "salon";
  if (t === "cleaning") return "services";
  if (t === "events" || t === "photography") return "retail";
  return "retail";
}

function modifierGroupToRow(g: ProductModifierGroup): ModifierGroupRow {
  return {
    name: g.name || "",
    required: !!g.required,
    multi_select: !!g.multi_select,
    options: (g.options || []).map((o) => ({
      name: o.name || "",
      price_delta: String(o.price_delta ?? 0),
    })),
  };
}

function variantToRow(v: ProductVariant): VariantRow {
  return { name: v.name || "", price: String(v.price ?? "") };
}

function emptyTier(): TierRow {
  return { min_qty: "", price: "" };
}

function initialForm(supportStyle: boolean, withTierRow: boolean): FormState {
  return {
    name: "",
    price: supportStyle ? "0" : "",
    description: "",
    category: "",
    sub_category: "",
    discount_price: "",
    in_stock: true,
    stock_quantity: "",
    unit: "",
    moq: "",
    pricing_tiers: withTierRow ? [emptyTier()] : [],
    imageUrls: [],
    variants: [],
    modifier_groups: [],
  };
}

function productToForm(p: Product, includeTierRow: boolean): FormState {
  const tiers = (p.pricing_tiers || []).map((t) => ({
    min_qty: String(t.min_qty),
    price: String(t.price),
  }));
  const variants = (p.variants || []).map(variantToRow);
  const modifier_groups = (p.modifier_groups || []).map(modifierGroupToRow);
  return {
    name: p.name,
    price: String(p.price ?? ""),
    description: p.description || "",
    category: p.category || "",
    sub_category: p.sub_category || "",
    discount_price: p.discount_price != null ? String(p.discount_price) : "",
    in_stock: p.in_stock !== false,
    stock_quantity: p.stock_quantity != null ? String(p.stock_quantity) : "",
    unit: p.unit || "",
    moq: p.moq != null ? String(p.moq) : "",
    pricing_tiers: tiers.length > 0 ? tiers : includeTierRow ? [emptyTier()] : [],
    imageUrls: productImageUrls(p),
    variants,
    modifier_groups,
  };
}

export default function ShopPage() {
  const { ui, currency, businessType } = useBusiness();
  const catalog = useMemo(() => getShopCatalogConfig(businessType), [businessType]);
  const isSupport = businessType === "support";

  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<"add" | "edit" | null>(null);
  const [editing, setEditing] = useState<Product | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<FormState>(() => initialForm(false, false));

  const [shopUrl, setShopUrl] = useState("");
  const [linkNotice, setLinkNotice] = useState("");
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [uploadingAI, setUploadingAI] = useState(false);
  const [aiDescBusy, setAiDescBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const aiFileInputRef = useRef<HTMLInputElement>(null);

  function revokePendingUrls(items: PendingImage[]) {
    for (const p of items) URL.revokeObjectURL(p.url);
  }

  function clearPendingImages() {
    setPendingImages((prev) => {
      revokePendingUrls(prev);
      return [];
    });
  }

  useEffect(() => {
    async function loadStorefront() {
      try {
        const store = await storefrontApi.mine();
        setShopUrl(store.public_url);
        // Say why the link is not simply the business name, rather than
        // leaving the merchant to wonder where the extra characters came from.
        if (store.name_taken) {
          setLinkNotice(`Another shop already uses “${store.preferred_slug}”, so yours has extra characters on the end. Change your business name to claim a shorter link.`);
        } else if (store.name_reserved) {
          setLinkNotice(`“${store.preferred_slug}” is a Zilo page, so it cannot be used as a shop link. Change your business name to claim a shorter one.`);
        } else {
          setLinkNotice("");
        }
      } catch (error) {
        console.error("Could not load public catalog link", error);
      }
    }
    void loadStorefront();
    void load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      setProducts(await productsApi.list());
    } finally {
      setLoading(false);
    }
  }

  function openAdd() {
    clearPendingImages();
    const cfg = getShopCatalogConfig(businessType);
    setForm(initialForm(isSupport, cfg.showPricingTiers));
    setEditing(null);
    setModal("add");
  }

  function openEdit(product: Product) {
    clearPendingImages();
    setForm(productToForm(product, catalog.showPricingTiers));
    setEditing(product);
    setModal("edit");
  }

  function closeModal() {
    clearPendingImages();
    setModal(null);
  }

  function currentImageCount() {
    return form.imageUrls.length + pendingImages.length;
  }

  function appendImageFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    const room = MAX_IMAGES_PER_PRODUCT - currentImageCount();
    if (room <= 0) {
      alert(`You can have at most ${MAX_IMAGES_PER_PRODUCT} images per item.`);
      return;
    }
    const slice = arr.slice(0, room);
    setPendingImages((prev) => [
      ...prev,
      ...slice.map((file) => ({ file, url: URL.createObjectURL(file) })),
    ]);
  }

  async function handleAiUploadPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    e.target.value = "";
    if (!files?.length) return;
    setUploadingAI(true);
    try {
      const res = await productsApi.uploadWithAI(Array.from(files));
      await load();
      if (res.products?.length) {
        const first = res.products[0];
        setForm(productToForm(first as Product, catalog.showPricingTiers));
        setEditing(first as Product);
        setModal("edit");
        if (res.products.length > 1) {
          alert(`${res.products.length} items created from photos. You are editing the first — refresh the list for the rest.`);
        }
      }
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : "AI upload failed");
    } finally {
      setUploadingAI(false);
    }
  }

  async function handleAiDescription(mode: "generate" | "improve") {
    if (!form.name.trim()) {
      alert("Enter a name first, then run AI on the description.");
      return;
    }
    setAiDescBusy(true);
    try {
      const res = await productsApi.aiDescription({
        product_name: form.name.trim(),
        category: form.category.trim() || undefined,
        business_type: mapBusinessTypeForAi(businessType),
        current_description: mode === "improve" ? form.description.trim() || undefined : undefined,
        mode,
      });
      if (res.description) setForm((f) => ({ ...f, description: res.description }));
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : "AI description failed");
    } finally {
      setAiDescBusy(false);
    }
  }

  function setTier(i: number, field: keyof TierRow, value: string) {
    setForm((f) => {
      const next = [...f.pricing_tiers];
      next[i] = { ...next[i], [field]: value };
      return { ...f, pricing_tiers: next };
    });
  }

  function addTier() {
    setForm((f) => ({ ...f, pricing_tiers: [...f.pricing_tiers, emptyTier()] }));
  }

  function removeTier(i: number) {
    setForm((f) => ({
      ...f,
      pricing_tiers: f.pricing_tiers.filter((_, j) => j !== i),
    }));
  }

  function setVariantRow(i: number, field: keyof VariantRow, value: string) {
    setForm((f) => {
      const next = [...f.variants];
      next[i] = { ...next[i], [field]: value };
      return { ...f, variants: next };
    });
  }

  function addVariantRow() {
    setForm((f) => ({ ...f, variants: [...f.variants, { name: "", price: "" }] }));
  }

  function removeVariantRow(i: number) {
    setForm((f) => ({ ...f, variants: f.variants.filter((_, j) => j !== i) }));
  }

  function addModifierGroup() {
    setForm((f) => ({
      ...f,
      modifier_groups: [
        ...f.modifier_groups,
        {
          name: "",
          required: false,
          multi_select: false,
          options: [{ name: "", price_delta: "0" }],
        },
      ],
    }));
  }

  function removeModifierGroup(i: number) {
    setForm((f) => ({ ...f, modifier_groups: f.modifier_groups.filter((_, j) => j !== i) }));
  }

  function setModifierGroupField(i: number, field: keyof Pick<ModifierGroupRow, "name" | "required" | "multi_select">, value: string | boolean) {
    setForm((f) => {
      const next = [...f.modifier_groups];
      next[i] = { ...next[i], [field]: value } as ModifierGroupRow;
      return { ...f, modifier_groups: next };
    });
  }

  function setModifierOption(gi: number, oi: number, field: keyof ModifierOptionRow, value: string) {
    setForm((f) => {
      const groups = [...f.modifier_groups];
      const opts = [...groups[gi].options];
      opts[oi] = { ...opts[oi], [field]: value };
      groups[gi] = { ...groups[gi], options: opts };
      return { ...f, modifier_groups: groups };
    });
  }

  function addModifierOption(gi: number) {
    setForm((f) => {
      const groups = [...f.modifier_groups];
      groups[gi] = {
        ...groups[gi],
        options: [...groups[gi].options, { name: "", price_delta: "0" }],
      };
      return { ...f, modifier_groups: groups };
    });
  }

  function removeModifierOption(gi: number, oi: number) {
    setForm((f) => {
      const groups = [...f.modifier_groups];
      const opts = groups[gi].options.filter((_, j) => j !== oi);
      groups[gi] = { ...groups[gi], options: opts.length ? opts : [{ name: "", price_delta: "0" }] };
      return { ...f, modifier_groups: groups };
    });
  }

  async function handleDeleteExistingImage(index: number) {
    if (!editing) return;
    try {
      await productsApi.deleteImage(editing.id, index);
      setForm((f) => ({
        ...f,
        imageUrls: f.imageUrls.filter((_, j) => j !== index),
      }));
      const list = await productsApi.list();
      setProducts(list);
      const fresh = list.find((x) => x.id === editing.id);
      if (fresh) setEditing(fresh);
    } catch (e) {
      console.error(e);
      alert(e instanceof Error ? e.message : "Could not remove image");
    }
  }

  async function handleSave() {
    if (!form.name.trim()) {
      alert(`${catalog.nameLabel} is required.`);
      return;
    }
    const priceNum = parseFloat(form.price);
    if (form.price.trim() === "" || Number.isNaN(priceNum) || priceNum < 0) {
      alert("Enter a valid price (0 is allowed for non-priced items).");
      return;
    }
    let discountNum: number | null = null;
    if (catalog.showDiscount && form.discount_price.trim()) {
      discountNum = parseFloat(form.discount_price);
      if (Number.isNaN(discountNum) || discountNum < 0) {
        alert("Invalid sale price.");
        return;
      }
      if (discountNum >= priceNum) {
        alert("Sale price must be less than the regular price.");
        return;
      }
    }

    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        price: priceNum,
        category: form.category.trim() || "Other",
        description: form.description.trim() || undefined,
        in_stock: form.in_stock,
      };

      if (catalog.showSubCategory && form.sub_category.trim()) {
        body.sub_category = form.sub_category.trim();
      }
      if (discountNum !== null) {
        body.discount_price = discountNum;
      }

      if (catalog.showStock && form.stock_quantity.trim()) {
        const q = parseInt(form.stock_quantity, 10);
        if (!Number.isNaN(q)) body.stock_quantity = q;
      }

      if (catalog.showUnitMoq) {
        if (form.unit.trim()) body.unit = form.unit.trim();
        if (form.moq.trim()) {
          const m = parseInt(form.moq, 10);
          if (!Number.isNaN(m) && m > 0) body.moq = m;
        }
      }

      if (catalog.showPricingTiers) {
        const tiers = form.pricing_tiers
          .filter((r) => r.min_qty.trim() && r.price.trim())
          .map((r) => ({
            min_qty: parseInt(r.min_qty, 10),
            price: parseFloat(r.price),
          }))
          .filter((t) => !Number.isNaN(t.min_qty) && t.min_qty > 0 && !Number.isNaN(t.price) && t.price >= 0);
        body.pricing_tiers = tiers;
      }

      const variants = form.variants
        .filter((v) => v.name.trim())
        .map((v) => ({
          name: v.name.trim(),
          price: parseFloat(v.price),
        }))
        .filter((v) => !Number.isNaN(v.price) && v.price >= 0);
      body.variants = variants;

      const modifier_groups = form.modifier_groups
        .filter((g) => g.name.trim())
        .map((g) => ({
          name: g.name.trim(),
          required: g.required,
          multi_select: g.multi_select,
          options: g.options
            .filter((o) => o.name.trim())
            .map((o) => ({
              name: o.name.trim(),
              price_delta: parseFloat(o.price_delta) || 0,
            })),
        }))
        .filter((g) => g.options.length > 0);
      body.modifier_groups = modifier_groups;

      let productId = editing?.id;
      if (editing) {
        await productsApi.update(editing.id, body);
      } else {
        const created = await productsApi.create(body);
        productId = created.id;
      }

      if (pendingImages.length > 0 && productId) {
        await productsApi.addImages(
          productId,
          pendingImages.map((p) => p.file)
        );
      }

      clearPendingImages();
      closeModal();
      await load();
    } catch (e) {
      console.error(e);
      alert(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm(`Remove this ${catalog.itemSingular.toLowerCase()} from the shop?`)) return;
    await productsApi.delete(id);
    await load();
  }

  const categories = [...new Set(products.map((p) => p.category || "Uncategorised"))];

  const displayPrice = (p: Product) => {
    if (p.discount_price != null && p.discount_price < p.price) {
      return (
        <span className="flex flex-wrap items-baseline gap-1">
          <span className="font-bold text-brand-dark">{formatCurrency(p.discount_price, currency)}</span>
          <span className="text-xs text-slate-400 line-through">{formatCurrency(p.price, currency)}</span>
        </span>
      );
    }
    return <span className="font-bold text-brand-dark">{formatCurrency(p.price, currency)}</span>;
  };

  const cardImage = (p: Product) => {
    const raw = p.images?.[0] || p.image_url;
    const src = resolveMediaUrl(raw || undefined);
    return src;
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{ui.shopNavLabel}</h1>
          <p className="text-slate-500 text-sm mt-1 max-w-xl">{catalog.pageSubtitle}</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <input
            ref={aiFileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => void handleAiUploadPick(e)}
          />
          <button
            type="button"
            disabled={uploadingAI}
            onClick={() => aiFileInputRef.current?.click()}
            className="flex items-center gap-2 px-4 py-2 text-sm border border-violet-200 bg-violet-50 text-violet-800 rounded-lg font-semibold hover:bg-violet-100 disabled:opacity-50 transition-colors"
          >
            {uploadingAI ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            Create from photos (AI)
          </button>
          {shopUrl && (
            <a
              href={shopUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 font-medium"
            >
              <ExternalLink size={14} />
              View Shop
            </a>
          )}
          <button
            type="button"
            onClick={openAdd}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-brand-dark text-white rounded-lg font-semibold hover:bg-brand transition-colors"
          >
            <Plus size={15} />
            {catalog.addButtonLabel}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3 bg-brand/10 border border-brand/30 rounded-xl px-4 py-3">
        <Store size={18} className="text-brand-dark shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-brand-ink">Your shop link</p>
          <p className="text-xs text-brand truncate">{shopUrl || "Sign in to see your shop URL"}</p>
          {linkNotice && <p className="mt-1 text-xs text-amber-700">{linkNotice}</p>}
        </div>
        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(shopUrl)}
          disabled={!shopUrl}
          className="text-xs font-medium text-brand-dark hover:underline shrink-0 disabled:opacity-40"
        >
          Copy
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse">
              <div className="h-32 bg-slate-100 rounded-lg mb-3" />
              <div className="h-4 bg-slate-100 rounded w-3/4 mb-1" />
              <div className="h-3 bg-slate-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : products.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-4 bg-white rounded-xl border border-slate-200">
          <Store size={40} className="text-slate-300" />
          <p className="text-slate-600 font-medium">{catalog.emptyTitle}</p>
          <p className="text-slate-400 text-sm text-center max-w-md">{catalog.emptyHint}</p>
          <button
            type="button"
            onClick={openAdd}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-brand-dark text-white rounded-lg font-semibold hover:bg-brand"
          >
            <Plus size={15} /> {catalog.addButtonLabel}
          </button>
        </div>
      ) : (
        <div className="space-y-8">
          {categories.map((cat) => (
            <div key={cat}>
              <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">{cat}</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                {products
                  .filter((p) => (p.category || "Uncategorised") === cat)
                  .map((product) => (
                    <div
                      key={product.id}
                      className="bg-white rounded-xl border border-slate-200 hover:shadow-md transition-shadow flex flex-col overflow-hidden"
                    >
                      <div className="h-32 bg-slate-100 flex items-center justify-center text-slate-300 overflow-hidden">
                        {cardImage(product) ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={cardImage(product)!}
                            alt={product.name}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <Store size={28} />
                        )}
                      </div>
                      <div className="p-3 flex-1 flex flex-col gap-1">
                        <p className="text-sm font-semibold text-slate-800 line-clamp-2">{product.name}</p>
                        {product.sub_category && (
                          <p className="text-[11px] text-slate-400 line-clamp-1">{product.sub_category}</p>
                        )}
                        {product.description && (
                          <p className="text-xs text-slate-500 line-clamp-2">{product.description}</p>
                        )}
                        <div className="text-sm mt-auto pt-1 flex flex-col gap-0.5">
                          {displayPrice(product)}
                          {product.unit ? (
                            <span className="text-[11px] text-slate-400">{product.unit}</span>
                          ) : null}
                        </div>
                      </div>
                      <div className="flex border-t border-slate-100">
                        <button
                          type="button"
                          onClick={() => openEdit(product)}
                          className="flex-1 flex items-center justify-center gap-1 py-2 text-xs text-slate-500 hover:bg-slate-50 transition-colors"
                        >
                          <Pencil size={12} /> Edit
                        </button>
                        <div className="w-px bg-slate-100" />
                        <button
                          type="button"
                          onClick={() => handleDelete(product.id)}
                          className="flex-1 flex items-center justify-center gap-1 py-2 text-xs text-red-500 hover:bg-red-50 transition-colors"
                        >
                          <Trash2 size={12} /> Remove
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto"
          onClick={() => closeModal()}
          role="presentation"
        >
          <div
            className="bg-white rounded-2xl shadow-xl w-full my-8 max-w-2xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">
                {modal === "add" ? catalog.modalAddTitle : catalog.modalEditTitle}
              </h3>
              <button type="button" onClick={() => closeModal()} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4 max-h-[min(85vh,800px)] overflow-y-auto">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) appendImageFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              <Field
                label={`${catalog.nameLabel} *`}
                value={form.name}
                onChange={(v) => setForm((f) => ({ ...f, name: v }))}
                placeholder={catalog.namePlaceholder}
              />
              <Field
                label={`${catalog.priceLabel} (${currency}) *`}
                type="number"
                step="any"
                value={form.price}
                onChange={(v) => setForm((f) => ({ ...f, price: v }))}
                placeholder={isSupport ? "0" : "250"}
              />
              {isSupport && (
                <p className="text-xs text-slate-500 -mt-2">{catalog.stockHelp}</p>
              )}

              <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-semibold text-slate-700">Photos</p>
                    <p className="text-[11px] text-slate-500">
                      Up to {MAX_IMAGES_PER_PRODUCT} images per item. New files upload when you save.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={currentImageCount() >= MAX_IMAGES_PER_PRODUCT}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-40"
                  >
                    <ImagePlus size={14} />
                    Add photos
                  </button>
                </div>
                {(form.imageUrls.length > 0 || pendingImages.length > 0) && (
                  <div className="flex flex-wrap gap-2">
                    {form.imageUrls.map((url, i) => (
                      <div key={`ex-${i}-${url}`} className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-200 bg-white shrink-0">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={resolveMediaUrl(url) || url}
                          alt=""
                          className="w-full h-full object-cover"
                        />
                        {editing && (
                          <button
                            type="button"
                            onClick={() => void handleDeleteExistingImage(i)}
                            className="absolute top-0.5 right-0.5 p-0.5 rounded bg-black/50 text-white hover:bg-black/70"
                            aria-label="Remove image"
                          >
                            <X size={12} />
                          </button>
                        )}
                      </div>
                    ))}
                    {pendingImages.map((p) => (
                      <div key={p.url} className="relative w-20 h-20 rounded-lg overflow-hidden border border-dashed border-brand/50 bg-white shrink-0">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={p.url} alt="" className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => {
                            URL.revokeObjectURL(p.url);
                            setPendingImages((prev) => prev.filter((x) => x.url !== p.url));
                          }}
                          className="absolute top-0.5 right-0.5 p-0.5 rounded bg-black/50 text-white hover:bg-black/70"
                          aria-label="Remove pending photo"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {catalog.showDiscount && (
                <Field
                  label={catalog.discountLabel || "Sale price (optional)"}
                  type="number"
                  step="any"
                  value={form.discount_price}
                  onChange={(v) => setForm((f) => ({ ...f, discount_price: v }))}
                  placeholder="Lower than regular price"
                />
              )}

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">{catalog.categoryLabel}</label>
                <input
                  type="text"
                  value={form.category}
                  onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                  placeholder={catalog.categoryPlaceholder}
                  list="shop-category-options"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand"
                />
                <datalist id="shop-category-options">
                  {catalog.categoryOptions.map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
              </div>

              {catalog.showSubCategory && (
                <Field
                  label={catalog.subCategoryLabel}
                  value={form.sub_category}
                  onChange={(v) => setForm((f) => ({ ...f, sub_category: v }))}
                  placeholder={catalog.subCategoryPlaceholder}
                />
              )}

              {catalog.showUnitMoq && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Unit / pack</label>
                    <input
                      type="text"
                      value={form.unit}
                      onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))}
                      placeholder={catalog.unitPlaceholder}
                      list="shop-unit-options"
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand"
                    />
                    <datalist id="shop-unit-options">
                      {catalog.unitSuggestions.map((u) => (
                        <option key={u} value={u} />
                      ))}
                    </datalist>
                  </div>
                  <Field
                    label="Minimum order qty (MOQ)"
                    type="number"
                    value={form.moq}
                    onChange={(v) => setForm((f) => ({ ...f, moq: v }))}
                    placeholder="e.g. 10"
                  />
                </div>
              )}

              <div className="rounded-xl border border-slate-200 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700">Variants (optional)</label>
                  <button
                    type="button"
                    onClick={addVariantRow}
                    className="text-xs font-medium text-brand-dark hover:underline"
                  >
                    + Add variant
                  </button>
                </div>
                <p className="text-[11px] text-slate-500">Different sizes or options with their own price (e.g. Small / Medium / Large).</p>
                {form.variants.map((row, i) => (
                  <div key={i} className="flex gap-2 items-center">
                    <input
                      value={row.name}
                      onChange={(e) => setVariantRow(i, "name", e.target.value)}
                      placeholder="Name (e.g. Large)"
                      className="flex-1 px-2 py-2 text-sm border border-slate-200 rounded-lg"
                    />
                    <input
                      type="number"
                      step="any"
                      value={row.price}
                      onChange={(e) => setVariantRow(i, "price", e.target.value)}
                      placeholder={`Price (${currency})`}
                      className="w-28 px-2 py-2 text-sm border border-slate-200 rounded-lg"
                    />
                    <button
                      type="button"
                      onClick={() => removeVariantRow(i)}
                      className="p-2 text-slate-400 hover:text-red-600"
                      aria-label="Remove variant"
                    >
                      <Trash size={16} />
                    </button>
                  </div>
                ))}
              </div>

              <div className="rounded-xl border border-slate-200 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700">Add-ons / modifiers (optional)</label>
                  <button
                    type="button"
                    onClick={addModifierGroup}
                    className="text-xs font-medium text-brand-dark hover:underline"
                  >
                    + Add group
                  </button>
                </div>
                <p className="text-[11px] text-slate-500">
                  Groups like &quot;Toppings&quot; or &quot;Extras&quot; with optional price changes.
                </p>
                {form.modifier_groups.map((g, gi) => (
                  <div key={gi} className="border border-slate-100 rounded-lg p-3 space-y-2 bg-slate-50/50">
                    <div className="flex gap-2 items-start">
                      <input
                        value={g.name}
                        onChange={(e) => setModifierGroupField(gi, "name", e.target.value)}
                        placeholder="Group name (e.g. Toppings)"
                        className="flex-1 px-2 py-2 text-sm border border-slate-200 rounded-lg"
                      />
                      <button
                        type="button"
                        onClick={() => removeModifierGroup(gi)}
                        className="p-2 text-slate-400 hover:text-red-600 shrink-0"
                        aria-label="Remove group"
                      >
                        <Trash size={16} />
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs">
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={g.required}
                          onChange={(e) => setModifierGroupField(gi, "required", e.target.checked)}
                          className="rounded border-slate-300"
                        />
                        Required
                      </label>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={g.multi_select}
                          onChange={(e) => setModifierGroupField(gi, "multi_select", e.target.checked)}
                          className="rounded border-slate-300"
                        />
                        Multi-select
                      </label>
                    </div>
                    <div className="space-y-1.5">
                      {g.options.map((o, oi) => (
                        <div key={oi} className="flex gap-2 items-center">
                          <input
                            value={o.name}
                            onChange={(e) => setModifierOption(gi, oi, "name", e.target.value)}
                            placeholder="Option name"
                            className="flex-1 px-2 py-1.5 text-sm border border-slate-200 rounded-lg"
                          />
                          <input
                            type="number"
                            step="any"
                            value={o.price_delta}
                            onChange={(e) => setModifierOption(gi, oi, "price_delta", e.target.value)}
                            placeholder="+0"
                            className="w-20 px-2 py-1.5 text-sm border border-slate-200 rounded-lg"
                          />
                          <button
                            type="button"
                            onClick={() => removeModifierOption(gi, oi)}
                            className="p-1 text-slate-400 hover:text-red-600"
                            aria-label="Remove option"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ))}
                      <button
                        type="button"
                        onClick={() => addModifierOption(gi)}
                        className="text-[11px] font-medium text-brand-dark hover:underline"
                      >
                        + Option
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {catalog.showPricingTiers && (
                <div className="space-y-2">
                  <label className="block text-xs font-medium text-slate-700">Volume pricing (optional)</label>
                  <p className="text-xs text-slate-500">Lower price at higher quantities (min qty → price).</p>
                  {form.pricing_tiers.map((row, i) => (
                    <div key={i} className="flex gap-2 items-center">
                      <input
                        type="number"
                        min={1}
                        value={row.min_qty}
                        onChange={(e) => setTier(i, "min_qty", e.target.value)}
                        placeholder="Min qty"
                        className="w-24 px-2 py-2 text-sm border border-slate-200 rounded-lg"
                      />
                      <span className="text-slate-400">→</span>
                      <input
                        type="number"
                        step="any"
                        value={row.price}
                        onChange={(e) => setTier(i, "price", e.target.value)}
                        placeholder={`Price (${currency})`}
                        className="flex-1 px-2 py-2 text-sm border border-slate-200 rounded-lg"
                      />
                      <button
                        type="button"
                        onClick={() => removeTier(i)}
                        className="p-2 text-slate-400 hover:text-red-600"
                        aria-label="Remove tier"
                      >
                        <Trash size={16} />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={addTier}
                    className="text-xs font-medium text-brand-dark hover:underline"
                  >
                    + Add tier
                  </button>
                </div>
              )}

              {catalog.showStock && (
                <div className="space-y-2 rounded-lg border border-slate-100 bg-slate-50/80 p-3">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.in_stock}
                      onChange={(e) => setForm((f) => ({ ...f, in_stock: e.target.checked }))}
                      className="rounded border-slate-300 text-brand-dark focus:ring-brand"
                    />
                    <span className="text-sm font-medium text-slate-700">Available / in stock</span>
                  </label>
                  <Field
                    label="Stock quantity (optional)"
                    type="number"
                    value={form.stock_quantity}
                    onChange={(v) => setForm((f) => ({ ...f, stock_quantity: v }))}
                    placeholder="e.g. 24"
                  />
                  {catalog.stockHelp && <p className="text-xs text-slate-500">{catalog.stockHelp}</p>}
                </div>
              )}

              <div>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <label className="block text-xs font-medium text-slate-700">Description</label>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={aiDescBusy}
                      onClick={() => void handleAiDescription("generate")}
                      className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-md border border-violet-200 bg-violet-50 text-violet-800 hover:bg-violet-100 disabled:opacity-50"
                    >
                      {aiDescBusy ? <Loader2 size={12} className="animate-spin" /> : <Wand2 size={12} />}
                      AI write
                    </button>
                    <button
                      type="button"
                      disabled={aiDescBusy || !form.description.trim()}
                      onClick={() => void handleAiDescription("improve")}
                      className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      <Sparkles size={12} />
                      AI improve
                    </button>
                  </div>
                </div>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder={catalog.descriptionPlaceholder}
                  rows={4}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand resize-none"
                />
              </div>

              {catalog.advancedNote && (
                <p className="text-xs text-slate-500 border-t border-slate-100 pt-3">{catalog.advancedNote}</p>
              )}

              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={saving || !form.name.trim() || form.price.trim() === ""}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-brand-dark text-white font-semibold rounded-xl hover:bg-brand disabled:opacity-50 transition-colors text-sm"
              >
                {saving && <Loader2 size={15} className="animate-spin" />}
                {modal === "add" ? `Save ${catalog.itemSingular}` : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  type = "text",
  value,
  onChange,
  placeholder,
  step,
}: {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  step?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <input
        type={type}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-brand"
      />
    </div>
  );
}
