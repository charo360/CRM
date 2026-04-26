/**
 * Post types and recommended canvas sizes for social scheduling.
 * Used by UI labels and future API validation — not enforced in the stub layer.
 */

export type PostKind = "text" | "image" | "video" | "carousel" | "link" | "mixed";

export type PostPlacementId =
  | "custom"
  | "ig_feed_square"
  | "ig_feed_portrait"
  | "ig_story"
  | "ig_reel"
  | "fb_feed"
  | "fb_story"
  | "linkedin_link"
  | "linkedin_square"
  | "x_post_landscape"
  | "x_post_square"
  | "youtube_thumb"
  | "tiktok_9_16"
  | "pinterest_2_3";

export type PlacementPreset = {
  id: PostPlacementId;
  label: string;
  /** Recommended pixel size (design safe zone) */
  width: number;
  height: number;
  aspect: string;
  networks: string;
};

export const PLACEMENT_PRESETS: PlacementPreset[] = [
  { id: "ig_feed_square", label: "Instagram — Feed square", width: 1080, height: 1080, aspect: "1:1", networks: "Instagram" },
  { id: "ig_feed_portrait", label: "Instagram — Feed portrait", width: 1080, height: 1350, aspect: "4:5", networks: "Instagram" },
  { id: "ig_story", label: "Instagram — Story / highlight", width: 1080, height: 1920, aspect: "9:16", networks: "Instagram, Facebook story" },
  { id: "ig_reel", label: "Instagram — Reel", width: 1080, height: 1920, aspect: "9:16", networks: "Instagram" },
  { id: "fb_feed", label: "Facebook — Feed (landscape)", width: 1200, height: 630, aspect: "~1.91:1", networks: "Facebook" },
  { id: "fb_story", label: "Facebook — Story", width: 1080, height: 1920, aspect: "9:16", networks: "Facebook" },
  { id: "linkedin_link", label: "LinkedIn — Link / article card", width: 1200, height: 627, aspect: "~1.91:1", networks: "LinkedIn" },
  { id: "linkedin_square", label: "LinkedIn — Square post", width: 1080, height: 1080, aspect: "1:1", networks: "LinkedIn" },
  { id: "x_post_landscape", label: "X — Image / video landscape", width: 1600, height: 900, aspect: "16:9", networks: "X" },
  { id: "x_post_square", label: "X — Square", width: 1080, height: 1080, aspect: "1:1", networks: "X" },
  { id: "youtube_thumb", label: "YouTube — Thumbnail", width: 1280, height: 720, aspect: "16:9", networks: "YouTube" },
  { id: "tiktok_9_16", label: "TikTok — Vertical", width: 1080, height: 1920, aspect: "9:16", networks: "TikTok" },
  { id: "pinterest_2_3", label: "Pinterest — Pin standard", width: 1000, height: 1500, aspect: "2:3", networks: "Pinterest" },
  { id: "custom", label: "Custom size", width: 1080, height: 1080, aspect: "—", networks: "Any" },
];

export function presetById(id: PostPlacementId | undefined): PlacementPreset {
  return PLACEMENT_PRESETS.find((p) => p.id === id) ?? PLACEMENT_PRESETS[0];
}

export function derivePostKind(assetCount: number, hasVideo: boolean, hasImage: boolean): PostKind {
  if (assetCount === 0) return "text";
  if (assetCount === 1 && hasVideo) return "video";
  if (assetCount === 1 && hasImage) return "image";
  if (assetCount > 1) return hasVideo && hasImage ? "mixed" : "carousel";
  return "text";
}

export const POST_KIND_LABELS: Record<PostKind, string> = {
  text: "Text",
  image: "Image",
  video: "Video",
  carousel: "Carousel",
  link: "Link",
  mixed: "Mixed media",
};
