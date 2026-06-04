/**
 * Client-side persistence for marketing UIs until backend APIs exist.
 * Replace calls with real API modules when endpoints are ready.
 */

import type { PostKind, PostPlacementId } from "./social-post-presets";

const PREFIX = "zilo_marketing_stub_v1";

function load<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(`${PREFIX}:${key}`);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function save<T>(key: string, data: T) {
  if (typeof window === "undefined") return;
  localStorage.setItem(`${PREFIX}:${key}`, JSON.stringify(data));
}

function id() {
  return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 9)}`;
}

// ─── Social scheduler ─────────────────────────────────────────────────────────

export type SocialChannel = "facebook" | "instagram" | "youtube" | "linkedin" | "x" | "tiktok";

export type ScheduledPostStatus = "draft" | "scheduled" | "published" | "failed";

export interface PostAsset {
  file_name: string;
  mime_type: string;
  preview_data_url?: string;
}

export interface ScheduledPost {
  id: string;
  title: string;
  body: string;
  channels: SocialChannel[];
  scheduled_at: string; // ISO
  status: ScheduledPostStatus;
  created_at: string;
  /** Resolved kind for publishing (text, image, video, carousel, link, …) */
  post_kind?: PostKind;
  /** Recommended / target canvas — see `social-post-presets` */
  placement_id?: PostPlacementId;
  placement_width?: number;
  placement_height?: number;
  /** For link posts */
  link_url?: string;
  /** Multi-asset (carousel, mixed); preferred over legacy single-media fields */
  assets?: PostAsset[];
  /** @deprecated use assets[] */
  media_file_name?: string;
  /** @deprecated use assets[] */
  media_preview_data_url?: string;
}

const POSTS_KEY = "social_posts";

export function listScheduledPosts(): ScheduledPost[] {
  return load<ScheduledPost[]>(POSTS_KEY, []);
}

export function upsertScheduledPost(row: Partial<ScheduledPost> & { title: string; body: string }): ScheduledPost {
  const posts = listScheduledPosts();
  const now = new Date().toISOString();
  const existing = row.id ? posts.find((p) => p.id === row.id) : undefined;
  const next: ScheduledPost = {
    id: row.id || id(),
    title: row.title,
    body: row.body,
    channels: row.channels?.length ? row.channels : ["facebook"],
    scheduled_at: row.scheduled_at || now,
    status: row.status ?? "draft",
    created_at: existing?.created_at ?? now,
    post_kind: row.post_kind ?? existing?.post_kind,
    placement_id: row.placement_id ?? existing?.placement_id,
    placement_width: row.placement_width ?? existing?.placement_width,
    placement_height: row.placement_height ?? existing?.placement_height,
    link_url: row.link_url ?? existing?.link_url,
    assets: row.assets !== undefined ? row.assets : existing?.assets,
    media_file_name: row.media_file_name ?? existing?.media_file_name,
    media_preview_data_url: row.media_preview_data_url ?? existing?.media_preview_data_url,
  };
  const rest = posts.filter((p) => p.id !== next.id);
  save(POSTS_KEY, [next, ...rest]);
  return next;
}

export function deleteScheduledPost(postId: string) {
  const posts = listScheduledPosts().filter((p) => p.id !== postId);
  save(POSTS_KEY, posts);
}

/** Skip embedding huge files in localStorage — previews only for smaller assets */
export const MAX_MEDIA_PREVIEW_BYTES = 380_000;

export function fileToPreviewDataUrl(file: File): Promise<string | undefined> {
  if (file.size > MAX_MEDIA_PREVIEW_BYTES) return Promise.resolve(undefined);
  return new Promise((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(typeof r.result === "string" ? r.result : undefined);
    r.onerror = () => resolve(undefined);
    r.readAsDataURL(file);
  });
}

// ─── Ads (Meta / Google) — shared shape ───────────────────────────────────────

export type AdsCampaignStatus = "draft" | "active" | "paused" | "ended";

export interface AdsCampaign {
  id: string;
  name: string;
  objective: string;
  daily_budget: number;
  currency: string;
  status: AdsCampaignStatus;
  /** Mock metrics until reporting API exists */
  spend: number;
  impressions: number;
  clicks: number;
  created_at: string;
}

/** @deprecated for the Meta Ads dashboard — `app/dashboard/meta-ads` uses `marketingApi` + Mongo. */
const META_KEY = "meta_campaigns";
const GOOGLE_KEY = "google_campaigns";
/** @deprecated — `app/dashboard/x-ads` uses `marketingApi` + Mongo `x_ads_campaign_drafts`. */
const X_ADS_KEY = "x_ads_campaigns";

function listCampaigns(key: string): AdsCampaign[] {
  return load<AdsCampaign[]>(key, []);
}

function saveCampaigns(key: string, rows: AdsCampaign[]) {
  save(key, rows);
}

export function listMetaCampaigns(): AdsCampaign[] {
  return listCampaigns(META_KEY);
}

export function listGoogleCampaigns(): AdsCampaign[] {
  return listCampaigns(GOOGLE_KEY);
}

export function listXAdsCampaigns(): AdsCampaign[] {
  return listCampaigns(X_ADS_KEY);
}

export function upsertMetaCampaign(row: Partial<AdsCampaign> & { name: string }): AdsCampaign {
  return upsertCampaign(META_KEY, row);
}

export function upsertGoogleCampaign(row: Partial<AdsCampaign> & { name: string }): AdsCampaign {
  return upsertCampaign(GOOGLE_KEY, row);
}

export function upsertXAdsCampaign(row: Partial<AdsCampaign> & { name: string }): AdsCampaign {
  return upsertCampaign(X_ADS_KEY, row);
}

function upsertCampaign(
  storageKey: string,
  row: Partial<AdsCampaign> & { name: string }
): AdsCampaign {
  const rows = listCampaigns(storageKey);
  const now = new Date().toISOString();
  const existing = row.id ? rows.find((r) => r.id === row.id) : undefined;
  const next: AdsCampaign = {
    id: row.id || id(),
    name: row.name,
    objective: row.objective ?? "awareness",
    daily_budget: row.daily_budget ?? 25,
    currency: row.currency ?? "USD",
    status: row.status ?? "draft",
    spend: row.spend ?? existing?.spend ?? 0,
    impressions: row.impressions ?? existing?.impressions ?? 0,
    clicks: row.clicks ?? existing?.clicks ?? 0,
    created_at: existing?.created_at ?? now,
  };
  const rest = rows.filter((r) => r.id !== next.id);
  saveCampaigns(storageKey, [next, ...rest]);
  return next;
}

export function deleteMetaCampaign(campaignId: string) {
  saveCampaigns(
    META_KEY,
    listMetaCampaigns().filter((r) => r.id !== campaignId)
  );
}

export function deleteGoogleCampaign(campaignId: string) {
  saveCampaigns(
    GOOGLE_KEY,
    listGoogleCampaigns().filter((r) => r.id !== campaignId)
  );
}

export function deleteXAdsCampaign(campaignId: string) {
  saveCampaigns(
    X_ADS_KEY,
    listXAdsCampaigns().filter((r) => r.id !== campaignId)
  );
}
