"use client";

import { useEffect, useMemo, useState } from "react";
import { productsApi, Product } from "@/lib/api";
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
} from "lucide-react";
import { useBusiness } from "@/contexts/BusinessContext";
import { getShopCatalogConfig } from "@/lib/shopCatalog";

type TierRow = { min_qty: string; price: string };

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
};

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
  };
}

function productToForm(p: Product, includeTierRow: boolean): FormState {
  const tiers = (p.pricing_tiers || []).map((t) => ({
    min_qty: String(t.min_qty),
    price: String(t.price),
  }));
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

  const shopUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/shop/${encodeURIComponent(
          localStorage.getItem("user")
            ? JSON.parse(localStorage.getItem("user") || "{}").business_slug || "my-shop"
            : "my-shop"
        )}`
      : "";

  async function load() {
    setLoading(true);
    try {
      setProducts(await productsApi.list());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function openAdd() {
    const cfg = getShopCatalogConfig(businessType);
    setForm(initialForm(isSupport, cfg.showPricingTiers));
    setEditing(null);
    setModal("add");
  }

  function openEdit(product: Product) {
    setForm(productToForm(product, catalog.showPricingTiers));
    setEditing(product);
    setModal("edit");
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

      if (editing) {
        await productsApi.update(editing.id, body);
      } else {
        await productsApi.create(body);
      }
      setModal(null);
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
          <span className="font-bold text-indigo-600">{formatCurrency(p.discount_price, currency)}</span>
          <span className="text-xs text-slate-400 line-through">{formatCurrency(p.price, currency)}</span>
        </span>
      );
    }
    return <span className="font-bold text-indigo-600">{formatCurrency(p.price, currency)}</span>;
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
        <div className="flex items-center gap-3">
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
            className="flex items-center gap-2 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition-colors"
          >
            <Plus size={15} />
            {catalog.addButtonLabel}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3">
        <Store size={18} className="text-indigo-600 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-indigo-900">Your shop link</p>
          <p className="text-xs text-indigo-500 truncate">{shopUrl || "Sign in to see your shop URL"}</p>
        </div>
        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(shopUrl)}
          className="text-xs font-medium text-indigo-700 hover:underline shrink-0"
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
            className="flex items-center gap-2 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700"
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
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto">
          <div
            className={`bg-white rounded-2xl shadow-xl w-full my-8 ${
              catalog.showPricingTiers || catalog.showUnitMoq ? "max-w-xl" : "max-w-md"
            }`}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">
                {modal === "add" ? catalog.modalAddTitle : catalog.modalEditTitle}
              </h3>
              <button type="button" onClick={() => setModal(null)} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4 max-h-[min(85vh,800px)] overflow-y-auto">
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
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
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
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
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
                    className="text-xs font-medium text-indigo-600 hover:underline"
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
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
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
                <label className="block text-xs font-medium text-slate-700 mb-1">Description</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder={catalog.descriptionPlaceholder}
                  rows={4}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>

              {catalog.advancedNote && (
                <p className="text-xs text-slate-500 border-t border-slate-100 pt-3">{catalog.advancedNote}</p>
              )}

              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={saving || !form.name.trim() || form.price.trim() === ""}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors text-sm"
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
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
      />
    </div>
  );
}
