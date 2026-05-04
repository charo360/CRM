"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Layers, Plus, Pencil, Trash2, RefreshCw, Star,
  Image as ImageIcon, ChevronDown, Check, X, Loader2,
  FileText, Upload, ExternalLink, Grid3X3, List,
  ZoomIn, ChevronLeft, ChevronRight, Download, Film,
  Presentation, Sparkles,
} from "lucide-react";
import { api, designTemplatesApi } from "@/lib/api";
import { toast } from "sonner";
import { cn, resolveMediaUrl, downloadAsset as downloadAssetRaw } from "@/lib/utils";

// ΓöÇΓöÇ Types ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

type AssetKind = "image" | "video" | "pdf" | "ppt" | "";
type AssetCategory = "image" | "video" | "pdf" | "ppt";
type Category = "all" | "image" | "video";

type DesignTemplate = {
  id: string;
  name: string;
  external_template_id: number;
  source?: string;
  file_url?: string;
  asset_kind?: AssetKind;
  platform: string;
  format: string;
  format_label: string;
  content_type: string;
  use_for: string[];
  thumbnail_url: string;
  field_schema: Record<string, string>;
  is_default: boolean;
  created_at: string;
};

type Meta = {
  platforms: string[];
  formats: { value: string; label: string }[];
  content_types: string[];
  material_types?: { value: string; label: string }[];
  sources?: string[];
  max_brand_image_batch?: number;
};

type PendingFile = { file: File; url: string };

// ΓöÇΓöÇ Helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function capitalize(s: string) { return s.charAt(0).toUpperCase() + s.slice(1); }

function contentTypeLabel(c: string) {
  const map: Record<string, string> = {
    create_social_graphic: "Social graphic",
    render_orshot_template: "Orshot graphic",
    create_business_document: "PDF",
    create_presentation: "Slides", brand_logo: "Logo", brand_image: "Brand image",
    brand_reference: "Reference PDF", brand_other: "Brand file",
    ad: "Ad", post: "Post", story: "Story", carousel: "Carousel",
    email_header: "Email header", presentation: "Presentation", general: "General",
  };
  return map[c] ?? capitalize(c);
}

function sourceLabel(s: string) {
  return ({ any: "All", brand_kit: "Brand kit", assistant_generated: "From chat", manual: "Manual" } as Record<string, string>)[s] ?? capitalize(s);
}

function getCategory(t: DesignTemplate): AssetCategory {
  if (t.asset_kind === "video") return "video";
  if (t.asset_kind === "pdf") return "pdf";
  if (t.asset_kind === "ppt") return "ppt";
  if (t.asset_kind === "image") return "image";
  if (t.content_type === "create_presentation") return "ppt";
  if (t.content_type === "create_business_document" || t.content_type === "brand_reference") return "pdf";
  if (["brand_logo", "brand_image", "brand_other", "create_social_graphic", "render_orshot_template"].includes(t.content_type)) return "image";
  return "image";
}

// ΓöÇΓöÇ Size system ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

type SizeInfo = {
  label: string;
  ratio: string;    // CSS aspect-ratio
  spec: string;     // human spec e.g. "1080├ù1080"
  kind: "social" | "document";
  platforms: string[];
};

const SIZE_MAP: Record<string, SizeInfo> = {
  // Social media
  square: { label: "1:1 Square", ratio: "1 / 1", spec: "1080├ù1080 px", kind: "social", platforms: ["instagram", "facebook", "linkedin", "x"] },
  story: { label: "9:16 Story", ratio: "9 / 16", spec: "1080├ù1920 px", kind: "social", platforms: ["instagram", "facebook", "tiktok", "youtube"] },
  landscape: { label: "16:9 Landscape", ratio: "16 / 9", spec: "1920├ù1080 px", kind: "social", platforms: ["facebook", "linkedin", "x", "youtube", "tiktok"] },
  portrait: { label: "4:5 Portrait", ratio: "4 / 5", spec: "1080├ù1350 px", kind: "social", platforms: ["instagram", "facebook"] },
  general: { label: "Custom", ratio: "16 / 9", spec: "", kind: "social", platforms: [] },
  // Documents
  a4: { label: "A4", ratio: "210 / 297", spec: "210├ù297 mm", kind: "document", platforms: [] },
  letter: { label: "Letter", ratio: "85 / 110", spec: "8.5├ù11 in", kind: "document", platforms: [] },
  slide_169: { label: "Slide 16:9", ratio: "16 / 9", spec: "1920├ù1080 px", kind: "document", platforms: [] },
  slide_43: { label: "Slide 4:3", ratio: "4 / 3", spec: "1024├ù768 px", kind: "document", platforms: [] },
  slide_a4: { label: "Slide A4", ratio: "297 / 210", spec: "297├ù210 mm", kind: "document", platforms: [] },
};

const SOCIAL_FORMAT_FILTERS = [
  { value: "any", label: "All sizes" },
  { value: "square", label: "1:1 Square" },
  { value: "story", label: "9:16 Story" },
  { value: "landscape", label: "16:9 Landscape" },
  { value: "portrait", label: "4:5 Portrait" },
];

const DOC_FORMAT_FILTERS = [
  { value: "any", label: "All sizes" },
  { value: "a4", label: "A4" },
  { value: "letter", label: "Letter" },
  { value: "slide_169", label: "Slide 16:9" },
  { value: "slide_43", label: "Slide 4:3" },
  { value: "slide_a4", label: "Slide A4" },
];

const PLATFORM_COLORS: Record<string, string> = {
  instagram: "bg-pink-100 text-pink-700",
  facebook: "bg-blue-100 text-blue-700",
  linkedin: "bg-sky-100 text-sky-800",
  tiktok: "bg-gray-900 text-white",
  youtube: "bg-red-100 text-red-700",
  x: "bg-gray-100 text-gray-700",
  general: "bg-gray-100 text-gray-500",
};

const PLATFORM_LABELS: Record<string, string> = {
  instagram: "Instagram", facebook: "Facebook", linkedin: "LinkedIn",
  tiktok: "TikTok", youtube: "YouTube", x: "X (Twitter)", general: "General",
};

function getSizeInfo(t: DesignTemplate): SizeInfo {
  return SIZE_MAP[t.format] ?? SIZE_MAP.general;
}

function getCardAspect(t: DesignTemplate): string {
  const cat = getCategory(t);
  if (cat === "pdf" || cat === "ppt") {
    return SIZE_MAP[t.format]?.ratio ?? "210 / 297"; // default A4 portrait
  }
  return SIZE_MAP[t.format]?.ratio ?? "1 / 1";
}

function isDocCategory(cat: string) { return cat === "pdf" || cat === "ppt"; }

async function downloadAsset(url: string, name: string) {
  try {
    await downloadAssetRaw(url, name);
  } catch {
    toast.error("Could not download file");
  }
}

const EMPTY_FORM = {
  name: "", external_template_id: "", platform: "general", format: "general",
  content_type: "general", use_for: "", thumbnail_url: "", field_schema_raw: "", is_default: false,
};

const CATEGORIES: { key: Category; label: string; icon: React.ReactNode; accept: string; hint: string }[] = [
  { key: "image", label: "Images", icon: <ImageIcon className="w-5 h-5" />, accept: "image/*", hint: "JPG, PNG, WebP, GIF" },
  { key: "video", label: "Videos", icon: <Film className="w-5 h-5" />, accept: "video/mp4,video/quicktime,video/webm,video/x-msvideo", hint: "MP4, MOV, WebM" },
];

// ΓöÇΓöÇ Page ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

export default function DesignTemplatesPage() {
  const [templates, setTemplates] = useState<DesignTemplate[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<Category>("all");
  const [filterPlatform, setFilterPlatform] = useState("any");
  const [filterFormat, setFilterFormat] = useState("any");
  const [filterSource, setFilterSource] = useState("any");
  const [filterContentType, setFilterContentType] = useState("any");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // upload state
  const [uploadCategory, setUploadCategory] = useState<Category>("image");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [brandKind, setBrandKind] = useState("brand_image");
  const [brandDefaultLogo, setBrandDefaultLogo] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingRef = useRef<PendingFile[]>([]);
  pendingRef.current = pendingFiles;

  // brand settings state
  const [brandFont, setBrandFont] = useState("");
  const [brandPrimaryColor, setBrandPrimaryColor] = useState("");
  const [brandSecondaryColor, setBrandSecondaryColor] = useState("");
  const [brandAccentColor, setBrandAccentColor] = useState("");
  const [brandLogoPlacement, setBrandLogoPlacement] = useState("");
  const [brandSettingsSaving, setBrandSettingsSaving] = useState(false);
  const [fontOptions, setFontOptions] = useState<string[]>([]);

  // document style state
  const [docStyle, setDocStyle] = useState<Record<string, string>>({
    tone: "", font_style: "", primary_color: "", secondary_color: "",
    logo_placement: "", header_text: "", footer_text: "",
    signature_name: "", signature_title: "", signature_contact: "",
    date_format: "", currency: "", standing_instructions: "",
  });
  const [docStyleSaving, setDocStyleSaving] = useState(false);
  const [docStyleOpen, setDocStyleOpen] = useState(false);

  // modal state
  const [preview, setPreview] = useState<DesignTemplate | null>(null);
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editing, setEditing] = useState<DesignTemplate | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => () => { pendingRef.current.forEach((p) => URL.revokeObjectURL(p.url)); }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tmpl, m, bs, ds] = await Promise.all([
        api.get<DesignTemplate[]>(`/design-templates?platform=any&content_type=any&source=${filterSource}`),
        meta ? Promise.resolve(meta) : api.get<Meta>("/design-templates/meta"),
        api.get<{ brand_font: string; brand_primary_color: string; brand_secondary_color?: string; brand_accent_color?: string; logo_placement?: string; font_options: string[] }>("/design-templates/settings/brand").catch(() => null),
        api.get<{ profile: Record<string, string> }>("/design-templates/document-style").catch(() => null),
      ]);
      setTemplates(tmpl);
      if (!meta) setMeta(m as Meta);
      if (bs) {
        setBrandFont(bs.brand_font || "");
        setBrandPrimaryColor(bs.brand_primary_color || "");
        setBrandSecondaryColor(bs.brand_secondary_color || "");
        setBrandAccentColor(bs.brand_accent_color || "");
        setBrandLogoPlacement(bs.logo_placement || "");
        if (bs.font_options?.length) setFontOptions(bs.font_options);
      }
      if (ds?.profile) setDocStyle((prev) => ({ ...prev, ...ds.profile }));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to load");
    } finally { setLoading(false); }
  }, [filterSource]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveBrandSettings() {
    setBrandSettingsSaving(true);
    try {
      await api.post("/design-templates/settings/brand", {
        brand_font: brandFont || null,
        brand_primary_color: brandPrimaryColor || null,
        brand_secondary_color: brandSecondaryColor || null,
        brand_accent_color: brandAccentColor || null,
        logo_placement: brandLogoPlacement || null,
      });
      toast.success("Brand settings saved");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to save");
    } finally { setBrandSettingsSaving(false); }
  }

  async function saveDocStyle() {
    setDocStyleSaving(true);
    try {
      await api.put("/design-templates/document-style", docStyle);
      toast.success("Document style saved ΓÇö Zilo will apply it to every document");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to save");
    } finally { setDocStyleSaving(false); }
  }

  useEffect(() => { load(); }, [load]);

  const maxFiles = meta?.max_brand_image_batch ?? 10;
  const catConf = CATEGORIES.find((c) => c.key === uploadCategory)!;

  function appendFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    setPendingFiles((prev) => {
      const room = maxFiles - prev.length;
      if (room <= 0) { toast.error(`Max ${maxFiles} files at a time`); return prev; }
      return [...prev, ...arr.slice(0, room).map((file) => ({ file, url: URL.createObjectURL(file) }))];
    });
  }

  function clearPending() {
    setPendingFiles((prev) => { prev.forEach((p) => URL.revokeObjectURL(p.url)); return []; });
  }

  function switchUploadCategory(c: Category) {
    clearPending();
    setDisplayName("");
    setBrandKind("brand_image");
    setBrandDefaultLogo(false);
    setUploadCategory(c);
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (pendingFiles.length === 0) { toast.error("Add at least one file"); return; }
    setUploading(true);
    try {
      if (uploadCategory === "image") {
        const materialTypes = meta?.material_types ?? [];
        const mt = materialTypes.find((m) => m.value === brandKind) ? brandKind : "brand_image";
        const res = await designTemplatesApi.uploadBrandKitImages(
          pendingFiles.map((p) => p.file),
          { material_type: mt, name_base: displayName, is_default_logo: brandKind === "brand_logo" && brandDefaultLogo }
        );
        toast.success(`${res.created} image${res.created !== 1 ? "s" : ""} saved`);
      } else {
        for (const p of pendingFiles) {
          const contentTypeMap: Record<string, string> = {
            video: "brand_other", image: "brand_image", all: "brand_other",
          };
          await designTemplatesApi.uploadBrandKitFile(p.file, {
            name: (displayName || p.file.name.replace(/\.[^.]+$/, "")).slice(0, 200),
            material_type: contentTypeMap[uploadCategory],
            is_default_logo: false,
          });
        }
        toast.success(`${pendingFiles.length} file${pendingFiles.length !== 1 ? "s" : ""} saved`);
      }
      clearPending();
      setDisplayName("");
      await load();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally { setUploading(false); }
  }

  function openCreate() { setEditing(null); setForm(EMPTY_FORM); setModal("create"); }
  function openEdit(t: DesignTemplate) {
    setEditing(t);
    setForm({
      name: t.name, external_template_id: String(t.external_template_id),
      platform: t.platform, format: t.format, content_type: t.content_type,
      use_for: t.use_for.join(", "), thumbnail_url: t.thumbnail_url,
      field_schema_raw: Object.entries(t.field_schema).map(([k, v]) => `${k}: ${v}`).join("\n"),
      is_default: t.is_default,
    });
    setModal("edit");
  }

  function parseForm() {
    const use_for = form.use_for.split(",").map((s) => s.trim()).filter(Boolean);
    const field_schema: Record<string, string> = {};
    for (const line of form.field_schema_raw.split("\n")) {
      const idx = line.indexOf(":");
      if (idx < 1) continue;
      field_schema[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    }
    const extParsed = parseInt(form.external_template_id.trim(), 10);
    return {
      name: form.name.trim(), external_template_id: Number.isNaN(extParsed) ? 0 : extParsed,
      platform: form.platform, format: form.format, content_type: form.content_type,
      use_for, thumbnail_url: form.thumbnail_url.trim(), field_schema, is_default: form.is_default,
    };
  }

  async function handleSave() {
    if (!form.name.trim()) { toast.error("Name is required"); return; }
    setSaving(true);
    try {
      if (modal === "create") { await api.post("/design-templates", parseForm()); toast.success("Template registered"); }
      else if (editing) { await api.put(`/design-templates/${editing.id}`, parseForm()); toast.success("Updated"); }
      setModal(null); await load();
    } catch (e: unknown) { toast.error(e instanceof Error ? e.message : "Save failed"); }
    finally { setSaving(false); }
  }

  async function handleDelete(id: string) {
    setDeleting(id);
    try {
      await api.delete(`/design-templates/${id}`);
      toast.success("Removed");
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch (e: unknown) { toast.error(e instanceof Error ? e.message : "Delete failed"); }
    finally { setDeleting(null); }
  }

  // derived
  // Only show image + video assets in Design Library (docs belong in Documents tab)
  const visualTemplates = templates.filter((t) => getCategory(t) === "image" || getCategory(t) === "video");
  // Base = only category filter applied — used to compute which filter options have items
  const baseTemplates = category === "all" ? visualTemplates : visualTemplates.filter((t) => getCategory(t) === category);

  const displayed = baseTemplates.filter((t) => {
    if (filterPlatform !== "any" && t.platform !== filterPlatform) return false;
    if (filterFormat !== "any" && t.format !== filterFormat) return false;
    if (filterContentType !== "any" && t.content_type !== filterContentType) return false;
    return true;
  });
  const counts: Record<Category, number> = {
    all: visualTemplates.length,
    image: visualTemplates.filter((t) => getCategory(t) === "image").length,
    video: visualTemplates.filter((t) => getCategory(t) === "video").length,
  };
  const materialTypes = meta?.material_types ?? [];

  // Smart options ΓÇö only show values that have at least one item in the base set
  const availablePlatforms = new Set(baseTemplates.map((t) => t.platform));
  const availableFormats = new Set(baseTemplates.map((t) => t.format));
  const availableSources = new Set(baseTemplates.map((t) => t.source ?? "manual"));
  const availableTypes = new Set(baseTemplates.map((t) => t.content_type));

  const allPlatforms = meta?.platforms ?? [];
  const allFormats = meta?.formats ?? [];
  const sourceOptions = (meta?.sources ?? ["brand_kit", "assistant_generated", "manual"])
    .filter((s) => availableSources.has(s));

  const platforms = allPlatforms.filter((p) => p === "general" || availablePlatforms.has(p));
  const formats = allFormats.filter((f) => availableFormats.has(f.value));
  const contentTypes = meta?.content_types ?? [];

  return (
    <div className="min-h-screen bg-gray-50/50">

      {/* ΓöÇΓöÇ Header ΓöÇΓöÇ */}
      <div className="bg-white border-b border-gray-100 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand to-brand-dark flex items-center justify-center shadow-sm">
              <Layers className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-gray-900">Design Library</h1>
              <p className="text-xs text-gray-500">Brand assets &amp; templates ΓÇö Zilo Chat reads these every turn</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </button>
            <button onClick={openCreate} className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand-dark/90 transition-colors shadow-sm">
              <Plus className="w-4 h-4" /> Add entry
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-5 space-y-5">

        {/* ΓöÇΓöÇ Upload panel ΓöÇΓöÇ */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          {/* upload category tabs */}
          <div className="grid grid-cols-2 border-b border-gray-100">
            {CATEGORIES.map((c) => (
              <button
                key={c.key}
                type="button"
                onClick={() => switchUploadCategory(c.key)}
                className={cn(
                  "flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors border-b-2",
                  uploadCategory === c.key
                    ? "text-brand-dark border-brand-dark bg-brand/5"
                    : "text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-50"
                )}
              >
                <span className={cn(uploadCategory === c.key ? "text-brand-dark" : "text-gray-400")}>{c.icon}</span>
                <span className="hidden sm:inline">{c.label}</span>
              </button>
            ))}
          </div>

          {/* Upload body */}
          <form onSubmit={handleUpload} className="p-4 space-y-3">
            <input
              key={uploadCategory}
              ref={fileInputRef}
              type="file"
              accept={catConf.accept}
              multiple={uploadCategory === "image"}
              className="hidden"
              onChange={(e) => { if (e.target.files?.length) appendFiles(e.target.files); e.target.value = ""; }}
            />

            {/* Drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files.length) appendFiles(e.dataTransfer.files); }}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "flex items-center gap-3 border-2 border-dashed rounded-xl px-4 py-3 cursor-pointer transition-all",
                dragging ? "border-brand bg-brand/5" : "border-gray-200 hover:border-brand/50 hover:bg-gray-50"
              )}
            >
              <div className={cn("w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors", dragging ? "bg-brand/20" : "bg-gray-100")}>
                <Upload className={cn("w-4 h-4", dragging ? "text-brand-dark" : "text-gray-400")} />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700">{dragging ? "Drop here" : `Drop ${catConf.label.toLowerCase()} or click to browse`}</p>
                <p className="text-xs text-gray-400">{catConf.hint}{uploadCategory === "image" ? ` ΓÇö up to ${maxFiles} files` : ""}</p>
              </div>
            </div>

            {/* Pending previews */}
            {pendingFiles.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {pendingFiles.map((p) => (
                  <div key={p.url} className="relative w-16 h-16 rounded-lg overflow-hidden border border-gray-200 bg-gray-50 shrink-0 group">
                    {p.file.type.startsWith("image/") ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={p.url} alt="" className="w-full h-full object-cover" />
                    ) : p.file.type.startsWith("video/") ? (
                      <div className="w-full h-full flex flex-col items-center justify-center bg-gray-900 text-gray-300 gap-1">
                        <Film className="w-5 h-5" />
                        <span className="text-[9px]">{p.file.name.split(".").pop()?.toUpperCase()}</span>
                      </div>
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center bg-gray-100 text-gray-400 gap-1">
                        {/\.(pptx?|ppt)$/i.test(p.file.name) ? <Presentation className="w-5 h-5" /> : <FileText className="w-5 h-5" />}
                        <span className="text-[9px]">{p.file.name.split(".").pop()?.toUpperCase()}</span>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); URL.revokeObjectURL(p.url); setPendingFiles((prev) => prev.filter((x) => x.url !== p.url)); }}
                      className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-center justify-center"
                    >
                      <X className="w-4 h-4 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Controls */}
            <div className="flex flex-wrap items-end gap-3">
              {uploadCategory === "image" && (
                <div className="min-w-[130px]">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
                  <NativeSelect
                    value={brandKind}
                    onChange={(v) => { setBrandKind(v); if (v !== "brand_logo") setBrandDefaultLogo(false); }}
                    options={materialTypes.length
                      ? materialTypes.filter((m) => m.value !== "brand_reference").map((m) => ({ value: m.value, label: m.label }))
                      : [{ value: "brand_logo", label: "Logo" }, { value: "brand_image", label: "Brand image" }, { value: "brand_other", label: "Other" }]}
                  />
                </div>
              )}
              <div className="flex-1 min-w-[160px]">
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  {uploadCategory === "image" && pendingFiles.length > 1 ? "Name prefix" : "Display name"}
                  {" "}<span className="text-gray-400">(optional)</span>
                </label>
                <input className={inputCls} placeholder={uploadCategory === "video" ? "e.g. Product ad 30s" : "e.g. Brand guidelines"} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              </div>
              {uploadCategory === "image" && brandKind === "brand_logo" && (
                <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer pb-2 select-none">
                  <input type="checkbox" checked={brandDefaultLogo} onChange={(e) => setBrandDefaultLogo(e.target.checked)} className="rounded border-gray-300 accent-brand-dark" />
                  Set as default logo
                </label>
              )}
              <button
                type="submit"
                disabled={uploading || pendingFiles.length === 0}
                className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand-dark/90 disabled:opacity-50 transition-colors whitespace-nowrap"
              >
                {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {uploading ? "UploadingΓÇª" : `Upload${pendingFiles.length > 0 ? ` (${pendingFiles.length})` : ""}`}
              </button>
            </div>

            {uploadCategory === "image" && (
              <div className="flex items-center gap-2 px-3 py-2 bg-sky-50 border border-sky-100 rounded-lg text-xs text-sky-700">
                <Sparkles className="w-3.5 h-3.5 shrink-0" />
                Zilo Chat uses brand images and logos every turn — upload logos, product shots, and brand visuals here.
              </div>
            )}
          </form>
        </div>

        {/* ΓöÇΓöÇ Brand Settings ΓöÇΓöÇ */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Brand Settings</h2>
              <p className="text-xs text-gray-500 mt-0.5">Applied to every AI-generated design automatically</p>
            </div>
            <button
              onClick={saveBrandSettings}
              disabled={brandSettingsSaving}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand-dark/90 disabled:opacity-50 transition-colors"
            >
              {brandSettingsSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
              Save
            </button>
          </div>
          <div className="space-y-5">
            {/* Font picker */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Brand Font</label>
              <div className="flex gap-2">
                <select
                  value={brandFont}
                  onChange={(e) => setBrandFont(e.target.value)}
                  className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 bg-white focus:outline-none focus:ring-2 focus:ring-brand-dark/20"
                >
                  <option value="">Default (per style)</option>
                  {fontOptions.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
                {brandFont && (
                  <button onClick={() => setBrandFont("")} className="p-2 text-gray-400 hover:text-gray-600 border border-gray-200 rounded-lg transition-colors" title="Clear font">
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              {brandFont && (
                <p className="text-xs text-gray-400 mt-1.5" style={{ fontFamily: `'${brandFont}', sans-serif` }}>
                  Preview: The quick brown fox — {brandFont}
                </p>
              )}
            </div>

            {/* 3 brand colors */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">Brand Colors</label>
              <div className="grid grid-cols-3 gap-3">
                {([
                  { label: "Primary", value: brandPrimaryColor, set: setBrandPrimaryColor, placeholder: "#1e1e2f", hint: "Main brand color" },
                  { label: "Secondary", value: brandSecondaryColor, set: setBrandSecondaryColor, placeholder: "#f5a623", hint: "Supporting color" },
                  { label: "Accent", value: brandAccentColor, set: setBrandAccentColor, placeholder: "#00c47d", hint: "Highlight / CTA" },
                ] as const).map(({ label, value, set, placeholder, hint }) => (
                  <div key={label} className="flex flex-col gap-1.5">
                    <span className="text-[11px] font-medium text-gray-500">{label}</span>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="color"
                        value={value || placeholder}
                        onChange={(e) => set(e.target.value)}
                        className="w-9 h-9 border border-gray-200 rounded-lg cursor-pointer p-0.5 bg-white shrink-0"
                      />
                      <input
                        type="text"
                        value={value}
                        onChange={(e) => set(e.target.value)}
                        placeholder={placeholder}
                        maxLength={9}
                        className="flex-1 min-w-0 border border-gray-200 rounded-lg px-2 py-1.5 text-xs font-mono text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20"
                      />
                    </div>
                    <span className="text-[10px] text-gray-400">{hint}</span>
                    {value && (
                      <div className="h-1.5 rounded-full" style={{ backgroundColor: value }} />
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Logo placement — visual selector */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">Logo Placement</label>
              <div className="grid grid-cols-4 gap-2">
                {([
                  { value: "top-left",   label: "Top left",   pos: "items-start justify-start" },
                  { value: "top-center", label: "Top center", pos: "items-start justify-center" },
                  { value: "top-right",  label: "Top right",  pos: "items-start justify-end" },
                  { value: "none",       label: "No logo",    pos: "items-center justify-center" },
                ] as const).map(({ value, label, pos }) => {
                  const active = brandLogoPlacement === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setBrandLogoPlacement(value)}
                      className={cn(
                        "flex flex-col items-center gap-1.5 p-2 rounded-xl border-2 transition-all",
                        active ? "border-brand-dark bg-brand/5" : "border-gray-100 hover:border-gray-300"
                      )}
                    >
                      <div className={cn("w-full h-10 rounded-lg bg-gray-100 flex p-1.5", pos)}>
                        {value === "none"
                          ? <span className="text-gray-300 text-xs leading-none">✕</span>
                          : <div className="w-4 h-2 rounded-sm" style={{ backgroundColor: brandPrimaryColor || "#1e1e2f" }} />}
                      </div>
                      <span className={cn("text-[10px] font-medium leading-none", active ? "text-brand-dark" : "text-gray-500")}>{label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* ΓöÇΓöÇ Document Style Profile ΓöÇΓöÇ */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <button
            type="button"
            onClick={() => setDocStyleOpen((o) => !o)}
            className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center shrink-0">
                <FileText className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-left">
                <h2 className="text-sm font-semibold text-gray-900">Document Style Profile</h2>
                <p className="text-xs text-gray-500 mt-0.5">Zilo reads this before writing every document ΓÇö tone, signature, headers, and more</p>
              </div>
            </div>
            <ChevronDown className={cn("w-4 h-4 text-gray-400 transition-transform", docStyleOpen && "rotate-180")} />
          </button>
          {docStyleOpen && (
            <div className="px-5 pb-5 border-t border-gray-50">
              <div className="grid sm:grid-cols-2 gap-4 mt-4">
                {/* Tone */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Tone &amp; Voice</label>
                  <select value={docStyle.tone} onChange={(e) => setDocStyle((p) => ({ ...p, tone: e.target.value }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 bg-white focus:outline-none focus:ring-2 focus:ring-brand-dark/20">
                    <option value="">Select toneΓÇª</option>
                    {["Formal","Conversational","Bold","Friendly","Professional","Concise"].map((t) => <option key={t} value={t.toLowerCase()}>{t}</option>)}
                  </select>
                </div>
                {/* Font style */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Font Style</label>
                  <select value={docStyle.font_style} onChange={(e) => setDocStyle((p) => ({ ...p, font_style: e.target.value }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 bg-white focus:outline-none focus:ring-2 focus:ring-brand-dark/20">
                    <option value="">Select styleΓÇª</option>
                    {["Serif","Sans-serif","Modern","Classic","Minimal"].map((t) => <option key={t} value={t.toLowerCase()}>{t}</option>)}
                  </select>
                </div>
                {/* Primary color */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Primary Color</label>
                  <div className="flex items-center gap-2">
                    <input type="color" value={docStyle.primary_color || "#1e1e2f"}
                      onChange={(e) => setDocStyle((p) => ({ ...p, primary_color: e.target.value }))}
                      className="w-10 h-10 border border-gray-200 rounded-lg cursor-pointer p-0.5 bg-white" />
                    <input type="text" value={docStyle.primary_color}
                      onChange={(e) => setDocStyle((p) => ({ ...p, primary_color: e.target.value }))}
                      placeholder="#1e1e2f" maxLength={9}
                      className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20" />
                  </div>
                </div>
                {/* Secondary color */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Secondary Color</label>
                  <div className="flex items-center gap-2">
                    <input type="color" value={docStyle.secondary_color || "#f5a623"}
                      onChange={(e) => setDocStyle((p) => ({ ...p, secondary_color: e.target.value }))}
                      className="w-10 h-10 border border-gray-200 rounded-lg cursor-pointer p-0.5 bg-white" />
                    <input type="text" value={docStyle.secondary_color}
                      onChange={(e) => setDocStyle((p) => ({ ...p, secondary_color: e.target.value }))}
                      placeholder="#f5a623" maxLength={9}
                      className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20" />
                  </div>
                </div>
                {/* Logo placement moved to Brand Settings above */}
                {/* Date format */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Date Format</label>
                  <select value={docStyle.date_format} onChange={(e) => setDocStyle((p) => ({ ...p, date_format: e.target.value }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 bg-white focus:outline-none focus:ring-2 focus:ring-brand-dark/20">
                    <option value="">Select formatΓÇª</option>
                    {["DD Month YYYY","Month DD, YYYY","DD/MM/YYYY","MM/DD/YYYY","YYYY-MM-DD"].map((f) => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>
                {/* Currency */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Default Currency</label>
                  <select value={docStyle.currency} onChange={(e) => setDocStyle((p) => ({ ...p, currency: e.target.value }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 bg-white focus:outline-none focus:ring-2 focus:ring-brand-dark/20">
                    <option value="">Select currencyΓÇª</option>
                    {["KES","USD","EUR","GBP","ZAR","NGN","GHS","UGX","TZS"].map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                {/* Header text */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Header Text</label>
                  <input type="text" value={docStyle.header_text}
                    onChange={(e) => setDocStyle((p) => ({ ...p, header_text: e.target.value }))}
                    placeholder="e.g. Confidential ΓÇö Company Name"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20" />
                </div>
                {/* Footer text */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Footer Text</label>
                  <input type="text" value={docStyle.footer_text}
                    onChange={(e) => setDocStyle((p) => ({ ...p, footer_text: e.target.value }))}
                    placeholder="e.g. ┬⌐ 2025 Company Ltd. All rights reserved."
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20" />
                </div>
                {/* Signature name */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Signature Name</label>
                  <input type="text" value={docStyle.signature_name}
                    onChange={(e) => setDocStyle((p) => ({ ...p, signature_name: e.target.value }))}
                    placeholder="e.g. James Kariuki"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20" />
                </div>
                {/* Signature title */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Signature Title</label>
                  <input type="text" value={docStyle.signature_title}
                    onChange={(e) => setDocStyle((p) => ({ ...p, signature_title: e.target.value }))}
                    placeholder="e.g. Chief Executive Officer"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20" />
                </div>
                {/* Signature contact */}
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Signature Contact</label>
                  <input type="text" value={docStyle.signature_contact}
                    onChange={(e) => setDocStyle((p) => ({ ...p, signature_contact: e.target.value }))}
                    placeholder="e.g. james@company.co.ke | +254 712 345 678"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20" />
                </div>
                {/* Standing instructions */}
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Standing Instructions</label>
                  <textarea value={docStyle.standing_instructions}
                    onChange={(e) => setDocStyle((p) => ({ ...p, standing_instructions: e.target.value }))}
                    rows={3}
                    placeholder="e.g. Always include a Payment Terms section. Always end with a CTA. Never use passive voice."
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-dark/20 resize-none" />
                  <p className="text-xs text-gray-400 mt-1">Zilo will follow these rules on every document, automatically.</p>
                </div>
              </div>
              <div className="flex justify-end mt-4">
                <button onClick={saveDocStyle} disabled={docStyleSaving}
                  className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors">
                  {docStyleSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                  Save Document Style
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ΓöÇΓöÇ Category selector ΓöÇΓöÇ */}
        <div className="grid grid-cols-3 gap-2">
          {([{ key: "all" as Category, label: "All assets", icon: <Layers className="w-5 h-5" />, color: "gray" }, ...CATEGORIES.map((c) => ({ ...c, color: c.key }))] as { key: Category; label: string; icon: React.ReactNode; color: string }[]).map((c) => { // eslint-disable-line @typescript-eslint/no-explicit-any
            const colorMap: Record<string, string> = {
              gray: "bg-gray-100 text-gray-500",
              image: "bg-blue-100 text-blue-600",
              video: "bg-violet-100 text-violet-600",
            };
            const activeMap: Record<string, string> = {
              gray: "ring-gray-400",
              image: "ring-blue-400",
              video: "ring-violet-400",
            };
            const isActive = category === c.key;
            return (
              <button
                key={c.key}
                onClick={() => { setCategory(c.key); setFilterFormat("any"); setFilterPlatform("any"); setFilterContentType("any"); }}
                className={cn(
                  "flex items-center gap-3 p-3 bg-white rounded-xl border transition-all text-left",
                  isActive ? `border-transparent ring-2 ${activeMap[c.color]} shadow-sm` : "border-gray-100 hover:border-gray-200 hover:shadow-sm"
                )}
              >
                <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0 [&>svg]:w-4 [&>svg]:h-4", colorMap[c.color])}>
                  {c.icon}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-800">{counts[c.key]}</p>
                  <p className="text-xs text-gray-500 truncate">{c.label}</p>
                </div>
              </button>
            );
          })}
        </div>

        {/* ΓöÇΓöÇ Filters ΓöÇΓöÇ */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 space-y-2.5">
          {/* Platform ΓÇö only for social media categories, only show platforms that have items */}
          {!isDocCategory(category) && platforms.filter((p) => p !== "general").length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-gray-400 w-14 shrink-0">Platform</span>
              <FilterPills
                value={filterPlatform}
                onChange={setFilterPlatform}
                options={[{ value: "any", label: "All" }, ...platforms.filter((p) => p !== "general").map((p) => ({ value: p, label: PLATFORM_LABELS[p] ?? capitalize(p) }))]}
                colorMap={PLATFORM_COLORS}
              />
            </div>
          )}
          {/* Size ΓÇö only show sizes that have items */}
          {formats.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-gray-400 w-14 shrink-0">
                {isDocCategory(category) ? "Page size" : "Size"}
              </span>
              <FilterPills
                value={filterFormat}
                onChange={setFilterFormat}
                options={[{ value: "any", label: "All sizes" }, ...formats.map((f) => ({ value: f.value, label: f.label }))]}
              />
            </div>
          )}
          {/* Content type (Post / Ad / Story / Carousel) ΓÇö only shown if any exist */}
          {(["post", "ad", "story", "carousel"] as const).some((v) => availableTypes.has(v)) && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-gray-400 w-14 shrink-0">Type</span>
              <FilterPills
                value={filterContentType}
                onChange={setFilterContentType}
                options={[
                  { value: "any", label: "All" },
                  ...([
                    { value: "post", label: "Post" },
                    { value: "ad", label: "Ad" },
                    { value: "story", label: "Story" },
                    { value: "carousel", label: "Carousel" },
                  ].filter((o) => availableTypes.has(o.value)))
                ]}
                colorMap={{ post: "bg-green-100 text-green-700", ad: "bg-amber-100 text-amber-700", story: "bg-pink-100 text-pink-700", carousel: "bg-cyan-100 text-cyan-700" }}
              />
            </div>
          )}
          {/* Source + count + view */}
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-gray-400 w-14 shrink-0">Source</span>
              <FilterPills
                value={filterSource}
                onChange={setFilterSource}
                options={[{ value: "any", label: "All" }, ...sourceOptions.map((s) => ({ value: s, label: sourceLabel(s) }))]}
              />
              <span className="text-xs text-gray-400 ml-1">{displayed.length} item{displayed.length !== 1 ? "s" : ""}</span>
            </div>
            <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
              <button onClick={() => setViewMode("grid")} className={cn("p-1.5 rounded-md transition-colors", viewMode === "grid" ? "bg-white shadow-sm text-gray-700" : "text-gray-400 hover:text-gray-600")}><Grid3X3 className="w-3.5 h-3.5" /></button>
              <button onClick={() => setViewMode("list")} className={cn("p-1.5 rounded-md transition-colors", viewMode === "list" ? "bg-white shadow-sm text-gray-700" : "text-gray-400 hover:text-gray-600")}><List className="w-3.5 h-3.5" /></button>
            </div>
          </div>
        </div>

        {/* ΓöÇΓöÇ Grid / List ΓöÇΓöÇ */}
        {loading ? (
          <div className={cn("grid gap-4", viewMode === "grid" ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3" : "grid-cols-1")}>
            {[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className={cn("bg-white rounded-2xl border border-gray-100 animate-pulse", viewMode === "grid" ? "h-60" : "h-16")} />)}
          </div>
        ) : displayed.length === 0 ? (
          <EmptyState category={category} onUpload={() => { if (category !== "all") switchUploadCategory(category); }} onAdd={openCreate} />
        ) : viewMode === "grid" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {displayed.map((t) => (
              <TemplateCard key={t.id} template={t} onPreview={() => setPreview(t)} onEdit={() => openEdit(t)} onDelete={() => handleDelete(t.id)} deleting={deleting === t.id} />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {displayed.map((t) => (
              <TemplateRow key={t.id} template={t} onPreview={() => setPreview(t)} onEdit={() => openEdit(t)} onDelete={() => handleDelete(t.id)} deleting={deleting === t.id} />
            ))}
          </div>
        )}
      </div>

      {/* ΓöÇΓöÇ Preview lightbox ΓöÇΓöÇ */}
      {preview && (
        <PreviewModal
          template={preview}
          templates={displayed}
          onClose={() => setPreview(null)}
          onNavigate={(t) => setPreview(t)}
          onEdit={() => { setPreview(null); openEdit(preview); }}
        />
      )}

      {/* ΓöÇΓöÇ Edit/Create modal ΓöÇΓöÇ */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">{modal === "create" ? "Register manual entry" : "Edit entry"}</h2>
              <button onClick={() => setModal(null)} className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"><X className="w-5 h-5" /></button>
            </div>
            <div className="px-6 py-4 space-y-4">
              <FormField label="Template name *">
                <input className={inputCls} placeholder="e.g. Product launch ΓÇô square" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </FormField>
              <FormField label="External template ID" hint="Leave blank if not using an external template system">
                <input className={inputCls} type="number" placeholder="e.g. 12345" value={form.external_template_id} onChange={(e) => setForm({ ...form, external_template_id: e.target.value })} />
              </FormField>
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Platform">
                  <NativeSelect value={form.platform} onChange={(v) => setForm({ ...form, platform: v })} options={[{ value: "general", label: "General" }, ...platforms.filter((p) => p !== "general").map((p) => ({ value: p, label: capitalize(p) }))]} />
                </FormField>
                <FormField label="Content type">
                  <NativeSelect value={form.content_type} onChange={(v) => setForm({ ...form, content_type: v })} options={contentTypes.map((c) => ({ value: c, label: contentTypeLabel(c) }))} />
                </FormField>
              </div>
              <FormField label="Format / size">
                <NativeSelect value={form.format} onChange={(v) => setForm({ ...form, format: v })} options={[{ value: "general", label: "Custom size" }, ...formats.filter((f) => f.value !== "general").map((f) => ({ value: f.value, label: f.label }))]} />
              </FormField>
              <FormField label="Thumbnail URL" hint="Optional preview image">
                <input className={inputCls} placeholder="https://..." value={form.thumbnail_url} onChange={(e) => setForm({ ...form, thumbnail_url: e.target.value })} />
                {form.thumbnail_url && <img src={form.thumbnail_url} alt="preview" className="mt-2 rounded-lg w-full max-h-28 object-cover border border-gray-100" onError={(e) => (e.currentTarget.style.display = "none")} />}
              </FormField>
              <FormField label="Use for tags" hint="Comma-separated: new arrival, flash sale">
                <input className={inputCls} placeholder="new arrival, flash sale, product launch" value={form.use_for} onChange={(e) => setForm({ ...form, use_for: e.target.value })} />
              </FormField>
              <FormField label="Field schema" hint="One per line: field_id: description">
                <textarea className={cn(inputCls, "h-20 resize-none font-mono text-xs")} placeholder={"title: Product title\nsubtitle: Short tagline"} value={form.field_schema_raw} onChange={(e) => setForm({ ...form, field_schema_raw: e.target.value })} />
              </FormField>
              <label className="flex items-center gap-3 cursor-pointer select-none">
                <div onClick={() => setForm({ ...form, is_default: !form.is_default })} className={cn("w-9 h-5 rounded-full transition-colors relative shrink-0", form.is_default ? "bg-brand-dark" : "bg-gray-200")}>
                  <span className={cn("absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform", form.is_default ? "translate-x-4" : "translate-x-0.5")} />
                </div>
                <span className="text-sm text-gray-700">Set as default for this platform + content type</span>
              </label>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100">
              <button onClick={() => setModal(null)} className="px-4 py-2 text-sm text-gray-500 hover:text-gray-800 transition-colors">Cancel</button>
              <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-5 py-2 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand-dark/90 disabled:opacity-50 transition-colors">
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                {modal === "create" ? "Register" : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ΓöÇΓöÇ Sub-components ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

const CATEGORY_ICON: Record<string, React.ReactNode> = {
  all: <Layers className="w-5 h-5" />,
  image: <ImageIcon className="w-5 h-5" />,
  video: <Film className="w-5 h-5" />,
  pdf: <FileText className="w-5 h-5" />,
  ppt: <Presentation className="w-5 h-5" />,
};

function AssetThumbnail({ t, className }: { t: DesignTemplate; className?: string }) {
  const thumbSrc = resolveMediaUrl(t.thumbnail_url || t.file_url) || null;
  const kind = t.asset_kind || getCategory(t);

  if (thumbSrc && kind !== "video") {
    return <img src={thumbSrc} alt={t.name} className={cn("object-cover", className)} onError={(e) => { (e.currentTarget as HTMLElement).style.display = "none"; }} />; // eslint-disable-line @next/next/no-img-element
  }
  if (kind === "video") {
    return (
      <div className={cn("flex flex-col items-center justify-center bg-gray-900 text-gray-400 gap-1", className)}>
        <Film className="w-8 h-8 text-violet-400" />
        <span className="text-xs">Video</span>
      </div>
    );
  }
  if (kind === "pdf") {
    return (
      <div className={cn("flex flex-col items-center justify-center bg-red-50 text-red-300 gap-1", className)}>
        <FileText className="w-8 h-8" />
        <span className="text-xs">PDF</span>
      </div>
    );
  }
  if (kind === "ppt") {
    return (
      <div className={cn("flex flex-col items-center justify-center bg-orange-50 text-orange-300 gap-1", className)}>
        <Presentation className="w-8 h-8" />
        <span className="text-xs">PPT</span>
      </div>
    );
  }
  return (
    <div className={cn("flex flex-col items-center justify-center bg-gray-50 text-gray-300 gap-1", className)}>
      <ImageIcon className="w-8 h-8" />
      <span className="text-xs">No preview</span>
    </div>
  );
}

const CONTENT_TYPE_BADGE: Record<string, { label: string; cls: string }> = {
  post: { label: "Post", cls: "bg-green-100 text-green-700" },
  ad: { label: "Ad", cls: "bg-amber-100 text-amber-700" },
  story: { label: "Story", cls: "bg-pink-100 text-pink-700" },
  carousel: { label: "Carousel", cls: "bg-cyan-100 text-cyan-700" },
};

function ContentTypeBadge({ template: t }: { template: DesignTemplate }) {
  const badge = CONTENT_TYPE_BADGE[t.content_type];
  if (!badge) return null;
  return (
    <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded-full text-[11px] font-semibold", badge.cls)}>
      {badge.label}
    </span>
  );
}

function CategoryBadge({ template: t }: { template: DesignTemplate }) {
  const cat = getCategory(t);
  const map: Record<Category, { label: string; cls: string }> = {
    all: { label: "", cls: "" },
    image: { label: "", cls: "" },
    video: { label: "Video", cls: "bg-violet-100 text-violet-700" },
    pdf: { label: "PDF", cls: "bg-red-100 text-red-700" },
    ppt: { label: "PPT", cls: "bg-orange-100 text-orange-700" },
  };
  const { label, cls } = map[cat] ?? map.image;
  return label ? (
    <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[11px] font-semibold", cls)}>
      {CATEGORY_ICON[cat] && <span className="w-3 h-3">{CATEGORY_ICON[cat]}</span>}
      {label}
    </span>
  ) : null;
}

function TemplateCard({ template: t, onPreview, onEdit, onDelete, deleting }: { template: DesignTemplate; onPreview: () => void; onEdit: () => void; onDelete: () => void; deleting: boolean }) {
  const sizeInfo = getSizeInfo(t);
  const aspect = getCardAspect(t);
  return (
    <div className="group bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md hover:border-gray-200 transition-all overflow-hidden">
      <div className="relative overflow-hidden cursor-pointer" style={{ aspectRatio: aspect }} onClick={onPreview}>
        <AssetThumbnail t={t} className="w-full h-full group-hover:scale-105 transition-transform duration-300" />

        {/* Zoom overlay */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/25 transition-colors flex items-center justify-center">
          <div className="opacity-0 group-hover:opacity-100 transition-opacity w-9 h-9 rounded-full bg-white/90 backdrop-blur-sm flex items-center justify-center shadow-lg">
            <ZoomIn className="w-4 h-4 text-gray-700" />
          </div>
        </div>

        {/* Badges */}
        <div className="absolute top-2.5 left-2.5 flex flex-wrap gap-1">
          <CategoryBadge template={t} />
          {t.source === "brand_kit" && <SourceBadge color="sky">Brand kit</SourceBadge>}
          {t.source === "assistant_generated" && <SourceBadge color="emerald">From chat</SourceBadge>}
          {t.is_default && <SourceBadge color="amber"><Star className="w-3 h-3" /> Default</SourceBadge>}
        </div>

        {/* Actions */}
        <div className="absolute top-2.5 right-2.5 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
          {(t.file_url || t.thumbnail_url) && <ActionBtn onClick={() => downloadAsset(t.file_url || t.thumbnail_url, t.name)} title="Download"><Download className="w-3.5 h-3.5" /></ActionBtn>}
          <ActionBtn onClick={onEdit} title="Edit"><Pencil className="w-3.5 h-3.5" /></ActionBtn>
          <ActionBtn onClick={onDelete} disabled={deleting} danger title="Delete">{deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}</ActionBtn>
        </div>

        {t.file_url && t.asset_kind === "pdf" && (
          <a href={resolveMediaUrl(t.file_url) || t.file_url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
            className="absolute bottom-2.5 right-2.5 flex items-center gap-1 px-2 py-1 bg-white/90 backdrop-blur-sm rounded-lg text-xs font-medium text-gray-700 hover:bg-white transition-colors shadow-sm">
            <ExternalLink className="w-3 h-3" /> Open
          </a>
        )}
      </div>

      <div className="p-3 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <p className="font-semibold text-sm text-gray-900 leading-snug line-clamp-1">{t.name}</p>
          {t.external_template_id > 0 && <span className="shrink-0 text-xs text-gray-400 font-mono bg-gray-50 px-1.5 py-0.5 rounded">#{t.external_template_id}</span>}
        </div>
        {/* Size + platform row */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {t.format !== "general" && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-gray-900 text-white text-[11px] font-semibold tracking-wide">
              {sizeInfo.label}
            </span>
          )}
          {t.platform !== "general" && (
            <span className={cn("inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold", PLATFORM_COLORS[t.platform] ?? "bg-gray-100 text-gray-600")}>
              {PLATFORM_LABELS[t.platform] ?? capitalize(t.platform)}
            </span>
          )}
          {t.content_type !== "general" && (
            CONTENT_TYPE_BADGE[t.content_type]
              ? <ContentTypeBadge template={t} />
              : <Tag variant="purple">{contentTypeLabel(t.content_type)}</Tag>
          )}
        </div>
        {t.use_for.length > 0 && <p className="text-xs text-gray-400 truncate">{t.use_for.slice(0, 3).join(" ┬╖ ")}</p>}
      </div>
    </div>
  );
}

function TemplateRow({ template: t, onPreview, onEdit, onDelete, deleting }: { template: DesignTemplate; onPreview: () => void; onEdit: () => void; onDelete: () => void; deleting: boolean }) {
  return (
    <div className="group flex items-center gap-3 bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-md hover:border-gray-200 transition-all p-3">
      <div className="w-12 h-12 rounded-lg overflow-hidden shrink-0 cursor-pointer relative" onClick={onPreview}>
        <AssetThumbnail t={t} className="w-full h-full" />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
          <ZoomIn className="w-4 h-4 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <p className="font-medium text-sm text-gray-900 truncate">{t.name}</p>
          <CategoryBadge template={t} />
          {t.source === "brand_kit" && <SourceBadge color="sky">Brand kit</SourceBadge>}
          {t.source === "assistant_generated" && <SourceBadge color="emerald">From chat</SourceBadge>}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap mt-1">
          {t.format !== "general" && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-gray-900 text-white text-[10px] font-semibold tracking-wide">
              {getSizeInfo(t).label}
            </span>
          )}
          {t.platform !== "general" && (
            <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold", PLATFORM_COLORS[t.platform] ?? "bg-gray-100 text-gray-600")}>
              {PLATFORM_LABELS[t.platform] ?? capitalize(t.platform)}
            </span>
          )}
          {t.content_type !== "general" && (
            CONTENT_TYPE_BADGE[t.content_type]
              ? <ContentTypeBadge template={t} />
              : <Tag variant="purple">{contentTypeLabel(t.content_type)}</Tag>
          )}
          {t.use_for.slice(0, 2).map((u) => <Tag key={u} variant="slate">{u}</Tag>)}
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {t.file_url && <a href={resolveMediaUrl(t.file_url) || t.file_url} target="_blank" rel="noopener noreferrer" className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors" title="Open file"><ExternalLink className="w-3.5 h-3.5" /></a>}
        {(t.file_url || t.thumbnail_url) && <ActionBtn onClick={() => downloadAsset(t.file_url || t.thumbnail_url, t.name)} title="Download"><Download className="w-3.5 h-3.5" /></ActionBtn>}
        <ActionBtn onClick={onEdit} title="Edit"><Pencil className="w-3.5 h-3.5" /></ActionBtn>
        <ActionBtn onClick={onDelete} disabled={deleting} danger title="Delete">{deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}</ActionBtn>
      </div>
    </div>
  );
}

function PreviewModal({ template: t, templates, onClose, onNavigate, onEdit }: { template: DesignTemplate; templates: DesignTemplate[]; onClose: () => void; onNavigate: (t: DesignTemplate) => void; onEdit: () => void }) {
  const idx = templates.findIndex((x) => x.id === t.id);
  const prev = idx > 0 ? templates[idx - 1] : null;
  const next = idx < templates.length - 1 ? templates[idx + 1] : null;
  const thumbSrc = resolveMediaUrl(t.thumbnail_url) || null;
  const fileSrc = resolveMediaUrl(t.file_url) || t.file_url || null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && prev) onNavigate(prev);
      if (e.key === "ArrowRight" && next) onNavigate(next);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prev, next, onClose, onNavigate]);

  const cat = getCategory(t);
  const previewSrc =
    cat === "image" && fileSrc
      ? fileSrc
      : thumbSrc || fileSrc;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative flex max-h-[90vh] w-fit max-w-[min(96vw,1200px)] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex min-w-0 max-w-[min(96vw,1200px)] items-center justify-between gap-2 border-b border-gray-100 px-5 py-3 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <p className="font-semibold text-gray-900 truncate">{t.name}</p>
            <CategoryBadge template={t} />
            {t.is_default && <SourceBadge color="amber"><Star className="w-3 h-3" />Default</SourceBadge>}
          </div>
          <div className="flex items-center gap-1 shrink-0 ml-2">
            <button onClick={onEdit} className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"><Pencil className="w-3.5 h-3.5" /> Edit</button>
            {fileSrc && <a href={fileSrc} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"><ExternalLink className="w-3.5 h-3.5" /> Open</a>}
            {(fileSrc || thumbSrc) && <button onClick={() => downloadAsset((fileSrc || thumbSrc)!, t.name)} className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"><Download className="w-3.5 h-3.5" /> Download</button>}
            <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors ml-1"><X className="w-4 h-4" /></button>
          </div>
        </div>

        {/* Content: w-fit so the dark frame hugs the graphic (no huge side gutters) */}
        <div className="relative flex min-h-[240px] shrink-0 items-center justify-center overflow-hidden bg-gray-900 px-3 py-4">
          {t.asset_kind === "video" && fileSrc ? (
            <video src={fileSrc} controls className="max-h-[min(72vh,calc(90vh-8rem))] max-w-full" />
          ) : previewSrc ? (
            <div className="relative w-fit max-w-full">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewSrc}
                alt={t.name}
                className="block max-h-[min(72vh,calc(90vh-8rem))] w-auto max-w-[min(96vw-2rem,900px)] object-contain"
                decoding="async"
              />
            </div>
          ) : t.asset_kind === "pdf" || t.asset_kind === "ppt" ? (
            <div className="flex flex-col items-center gap-3 p-10 text-gray-400">
              {t.asset_kind === "pdf" ? <FileText className="w-16 h-16 text-red-400" /> : <Presentation className="w-16 h-16 text-orange-400" />}
              <p className="text-sm text-gray-400">{t.asset_kind === "pdf" ? "PDF" : "Presentation"} ΓÇö no thumbnail</p>
              {fileSrc && <a href={fileSrc} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand-dark/90 transition-colors"><ExternalLink className="w-4 h-4" /> Open file</a>}
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 p-10 text-gray-500"><ImageIcon className="w-14 h-14" /><p className="text-sm">No preview</p></div>
          )}

          {prev && <button onClick={() => onNavigate(prev)} className="absolute left-3 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-white/90 backdrop-blur-sm shadow-lg flex items-center justify-center text-gray-700 hover:bg-white transition-colors"><ChevronLeft className="w-5 h-5" /></button>}
          {next && <button onClick={() => onNavigate(next)} className="absolute right-3 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-white/90 backdrop-blur-sm shadow-lg flex items-center justify-center text-gray-700 hover:bg-white transition-colors"><ChevronRight className="w-5 h-5" /></button>}
        </div>

        {/* Footer */}
        <div className="flex max-w-[min(96vw,1200px)] shrink-0 flex-wrap items-center gap-2 border-t border-gray-100 px-5 py-2.5">
          {t.format !== "general" && (() => {
            const s = getSizeInfo(t); return (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-gray-900 text-white text-xs font-semibold">
                {s.label}{s.spec ? <><span className="opacity-40">┬╖</span> {s.spec}</> : null}
              </span>
            );
          })()}
          {t.platform !== "general" && (
            <span className={cn("inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold", PLATFORM_COLORS[t.platform] ?? "bg-gray-100 text-gray-600")}>
              {PLATFORM_LABELS[t.platform] ?? capitalize(t.platform)}
            </span>
          )}
          {t.content_type !== "general" && <Tag variant="purple">{contentTypeLabel(t.content_type)}</Tag>}
          {t.use_for.map((u) => <Tag key={u} variant="slate">{u}</Tag>)}
          <span className="ml-auto text-xs text-gray-400">{idx + 1} / {templates.length}</span>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ category, onUpload, onAdd }: { category: Category; onAdd: () => void; onUpload: () => void }) {
  const labels: Record<string, string> = { all: "Your library is empty", image: "No images yet", video: "No videos yet" };
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand/20 to-brand-dark/20 flex items-center justify-center text-brand-dark">
        {CATEGORY_ICON[category]}
      </div>
      <div>
        <p className="font-semibold text-gray-800">{labels[category]}</p>
        <p className="text-sm text-gray-500 mt-1 max-w-xs">Upload assets or create a manual entry. Chat-generated files appear here automatically.</p>
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onUpload} className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand-dark/90 transition-colors shadow-sm"><Upload className="w-4 h-4" /> Upload</button>
        <button onClick={onAdd} className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"><Plus className="w-4 h-4" /> Add entry</button>
      </div>
    </div>
  );
}

function ActionBtn({ onClick, disabled, danger, title, children }: { onClick: () => void; disabled?: boolean; danger?: boolean; title?: string; children: React.ReactNode }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title} className={cn("p-1.5 rounded-lg transition-colors disabled:opacity-50", danger ? "text-red-400 hover:text-red-600 hover:bg-red-50" : "text-gray-400 hover:text-gray-600 hover:bg-gray-100")}>
      {children}
    </button>
  );
}

function SourceBadge({ children, color }: { children: React.ReactNode; color: "sky" | "emerald" | "amber" }) {
  const cls = { sky: "bg-sky-100 text-sky-700", emerald: "bg-emerald-100 text-emerald-700", amber: "bg-amber-100 text-amber-700" }[color];
  return <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", cls)}>{children}</span>;
}

function FilterPills({ value, onChange, options, colorMap }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; colorMap?: Record<string, string> }) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {options.map((o) => {
        const isActive = value === o.value;
        const platformCls = colorMap?.[o.value];
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            className={cn(
              "px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors",
              isActive
                ? platformCls ? platformCls + " ring-2 ring-offset-1 ring-current" : "bg-brand-dark text-white"
                : platformCls ? "bg-gray-100 text-gray-600 hover:bg-gray-200" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function NativeSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div className="relative">
      <select value={value} onChange={(e) => onChange(e.target.value)} className={cn(inputCls, "appearance-none pr-7 cursor-pointer")}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
    </div>
  );
}

function FormField({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      {hint && <p className="text-xs text-gray-400">{hint}</p>}
      {children}
    </div>
  );
}

function Tag({ children, variant = "blue" }: { children: React.ReactNode; variant?: "blue" | "purple" | "slate" }) {
  const cls = { blue: "bg-blue-50 text-blue-700", purple: "bg-brand/10 text-brand-dark", slate: "bg-gray-100 text-gray-600" }[variant];
  return <span className={cn("px-1.5 py-0.5 rounded text-[11px] font-medium", cls)}>{children}</span>;
}

const inputCls = "w-full px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-brand-dark/20 focus:border-brand-dark/40 transition-all";
