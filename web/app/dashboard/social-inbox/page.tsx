"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { customersApi, zernioApi, type ZernioCommentAutoReplySettings } from "@/lib/api";
import { getToken } from "@/lib/auth";
import {
  Inbox, RefreshCw, Send,
  MessageCircle, Globe, ChevronLeft, CheckCircle, XCircle, Loader2
} from "lucide-react";

type Account = { id: string; platform: string; name: string; username?: string; avatar?: string };
type Conversation = {
  id: string;
  platform: string;
  source?: "social" | "email";
  emailProvider?: "gmail" | "microsoft";
  threadId?: string;
  subject?: string;
  accountId?: string;
  account_id?: string;
  participantId?: string;
  participant_name?: string;
  participant?: string;
  last_message?: string;
  last_message_at?: string;
  unread?: number;
  avatar?: string;
};
type Message = {
  id: string;
  content: string;
  direction: "in" | "out";
  created_at: string;
  sender?: string;
  from?: string;
  date?: string;
  body?: string;
};
type CommentedPost = {
  id: string;
  accountId?: string;
  account_id?: string;
  platform?: string;
  content?: string;
  picture?: string;
  permalink?: string;
  image?: string;
  imageUrl?: string;
  image_url?: string;
  thumbnail?: string;
  thumbnailUrl?: string;
  thumbnail_url?: string;
  caption?: string;
  message?: string;
  text?: string;
  commentCount?: number;
  comments_count?: number;
  likes?: number;
  likeCount?: number;
  like_count?: number;
  shares?: number;
  shareCount?: number;
  share_count?: number;
  saves?: number;
  saveCount?: number;
  save_count?: number;
  clicks?: number;
  clickCount?: number;
  click_count?: number;
  reach?: number;
  impressions?: number;
  createdTime?: string;
  createdAt?: string;
  created_at?: string;
};
type PostComment = {
  id: string;
  commentId?: string;
  comment_id?: string;
  message?: string;
  text?: string;
  username?: string;
  author?: string;
  from?: { id?: string; name?: string; username?: string; picture?: string; isOwner?: boolean };
  replyCount?: number;
  reply_count?: number;
  canReply?: boolean;
  can_reply?: boolean;
  isHidden?: boolean;
  is_hidden?: boolean;
  createdTime?: string;
  createdAt?: string;
  created_at?: string;
};
type AiCustomer = {
  id: string;
  name: string;
  auto_reply?: boolean;
  last_message?: string | null;
  last_contacted?: string | null;
  unread_count?: number;
};

type EngagementDebug = {
  accountId: string;
  platform: string;
  idsTried: string[];
  source: "comments/posts-merge" | "analytics-by-post" | "no-match" | "error";
  message?: string;
  likes?: number;
  shares?: number;
  comments?: number;
};

const DEFAULT_COMMENT_AUTOREPLY: ZernioCommentAutoReplySettings = {
  enabled: false,
  engine_mode: "hybrid",
  apply_all_posts: true,
  post_ids: [],
  manychat_post_ids: [],
  default_message: "Thanks for your comment. We have seen it and will follow up shortly.",
  keyword_rules: [],
  chain_steps: [],
  reply_only_unreplied: true,
};

function pickList<T = Record<string, unknown>>(
  payload: unknown,
  keys: string[]
): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (!payload || typeof payload !== "object") return [];
  const obj = payload as Record<string, unknown>;
  for (const k of keys) {
    const direct = obj[k];
    if (Array.isArray(direct)) return direct as T[];
  }
  const nested = obj.data;
  if (Array.isArray(nested)) return nested as T[];
  if (nested && typeof nested === "object") {
    const nestedObj = nested as Record<string, unknown>;
    for (const k of keys) {
      const v = nestedObj[k];
      if (Array.isArray(v)) return v as T[];
    }
  }
  return [];
}

/** Limits concurrent outbound requests (Zernio rate limit ~120/min burst-sensitive). */
async function mapInBatches<T, R>(
  items: T[],
  batchSize: number,
  delayMs: number,
  fn: (item: T) => Promise<R>
): Promise<R[]> {
  const out: R[] = [];
  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    out.push(...(await Promise.all(batch.map(fn))));
    if (i + batchSize < items.length && delayMs > 0) {
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  return out;
}

function normalizeConversation(input: Conversation): Conversation {
  const raw = input as Conversation & Record<string, unknown>;
  return {
    ...input,
    accountId: (raw.accountId as string | undefined) ?? (raw.account_id as string | undefined),
    account_id: (raw.account_id as string | undefined) ?? (raw.accountId as string | undefined),
    participantId:
      (raw.participantId as string | undefined)
      ?? (raw.participant_id as string | undefined),
    participant_name:
      (raw.participant_name as string | undefined)
      ?? (raw.participantName as string | undefined)
      ?? (raw.username as string | undefined)
      ?? (raw.senderName as string | undefined),
    participant:
      (raw.participant as string | undefined)
      ?? (raw.participant_name as string | undefined)
      ?? (raw.participantName as string | undefined),
    last_message:
      (raw.last_message as string | undefined)
      ?? (raw.lastMessage as string | undefined),
    last_message_at:
      (raw.last_message_at as string | undefined)
      ?? (raw.lastMessageAt as string | undefined)
      ?? (raw.updatedTime as string | undefined),
    unread:
      typeof raw.unread === "number"
        ? raw.unread
        : typeof raw.unreadCount === "number"
          ? raw.unreadCount
          : 0,
    avatar:
      (raw.avatar as string | undefined)
      ?? (raw.participantPicture as string | undefined),
  };
}

function normalizeMessage(input: Message, conv?: Conversation): Message {
  const raw = input as Message & Record<string, unknown>;
  const directionRaw = String(raw.direction ?? "").toLowerCase();
  const bool = (v: unknown): boolean | undefined =>
    typeof v === "boolean" ? v : undefined;
  const fromMe =
    bool(raw.fromMe)
    ?? bool(raw.from_me)
    ?? bool(raw.isFromMe)
    ?? bool(raw.is_from_me)
    ?? bool(raw.outgoing)
    ?? bool(raw.isOutgoing)
    ?? bool(raw.is_outgoing);
  const senderId = String(raw.senderId ?? raw.sender_id ?? "");
  const participantId = String(conv?.participantId ?? "");
  const accountId = String(conv?.accountId ?? conv?.account_id ?? "");
  const inferredBySender =
    senderId && participantId
      ? (senderId === participantId ? "in" : "out")
      : senderId && accountId
        ? (senderId === accountId ? "out" : "in")
        : undefined;
  return {
    ...input,
    content:
      (raw.content as string | undefined)
      ?? (raw.message as string | undefined)
      ?? "",
    direction:
      fromMe !== undefined
        ? (fromMe ? "out" : "in")
        : directionRaw.includes("in")
        ? "in"
        : directionRaw.includes("out")
          ? "out"
          : inferredBySender
            ? inferredBySender
            : "in",
    created_at:
      (raw.created_at as string | undefined)
      ?? (raw.createdAt as string | undefined)
      ?? new Date().toISOString(),
    sender:
      (raw.sender as string | undefined)
      ?? (raw.senderName as string | undefined),
  };
}

function rebalanceDirections(msgs: Message[], conv: Conversation): Message[] {
  const hasIn = msgs.some((m) => m.direction === "in");
  const hasOut = msgs.some((m) => m.direction === "out");
  if (hasIn && hasOut) return msgs;

  const participant = String(conv.participant_name || conv.participant || "").toLowerCase();
  const withNameInference = msgs.map((m) => {
    const sender = String(m.sender || "").toLowerCase();
    if (!sender || !participant) return m;
    const isParticipant = sender.includes(participant) || participant.includes(sender);
    return { ...m, direction: isParticipant ? "in" : "out" as "in" | "out" };
  });
  if (
    withNameInference.some((m) => m.direction === "in") &&
    withNameInference.some((m) => m.direction === "out")
  ) {
    return withNameInference;
  }

  const senderKeys = Array.from(
    new Set(
      msgs
        .map((m) => String(m.sender || "").trim().toLowerCase())
        .filter(Boolean)
    )
  );
  if (senderKeys.length === 2) {
    const firstSender = String(msgs[0]?.sender || "").trim().toLowerCase();
    return msgs.map((m) => {
      const k = String(m.sender || "").trim().toLowerCase();
      if (!k) return m;
      return { ...m, direction: k === firstSender ? "in" : "out" as "in" | "out" };
    });
  }

  return msgs;
}

const PLATFORM_ICON: Record<string, React.ReactNode> = {
  instagram: (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5 text-pink-500">
      <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
    </svg>
  ),
  facebook: (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5 text-blue-600">
      <path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.791-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.97h-1.513c-1.491 0-1.956.93-1.956 1.883v2.252h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/>
    </svg>
  ),
  twitter: (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5 text-sky-500">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.742l7.73-8.835L1.254 2.25H8.08l4.26 5.632zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>
  ),
  whatsapp: <MessageCircle size={14} className="text-green-500" />,
  telegram: <Send size={14} className="text-sky-400" />,
  gmail: <Inbox size={14} className="text-rose-500" />,
  microsoft: <Inbox size={14} className="text-blue-600" />,
};

const PLATFORM_COLOR: Record<string, string> = {
  instagram: "bg-pink-50 text-pink-700 border-pink-200",
  facebook: "bg-blue-50 text-blue-700 border-blue-200",
  twitter: "bg-sky-50 text-sky-700 border-sky-200",
  whatsapp: "bg-green-50 text-green-700 border-green-200",
  telegram: "bg-sky-50 text-sky-600 border-sky-200",
  gmail: "bg-rose-50 text-rose-700 border-rose-200",
  microsoft: "bg-blue-50 text-blue-700 border-blue-200",
};

function PlatformBadge({ platform }: { platform: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs border capitalize ${PLATFORM_COLOR[platform] || "bg-slate-50 text-slate-600 border-slate-200"}`}>
      {PLATFORM_ICON[platform] || <Globe size={12} />} {platform}
    </span>
  );
}

function timeAgo(dateStr?: string) {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function extractEmailAddress(input?: string): string {
  if (!input) return "";
  const m = input.match(/<([^>]+)>/);
  return (m ? m[1] : input).trim();
}

function isOlderThanHours(dateStr: string | undefined, hours: number): boolean {
  if (!dateStr) return false;
  const t = new Date(dateStr).getTime();
  if (!Number.isFinite(t)) return false;
  return Date.now() - t > hours * 60 * 60 * 1000;
}

function shortPostId(id: string): string {
  if (!id) return "unknown";
  const parts = id.split("_").filter(Boolean);
  const tail = parts[parts.length - 1] || id;
  return tail.length > 10 ? `${tail.slice(0, 10)}...` : tail;
}

function postDisplayTitle(post: CommentedPost): string {
  const text = (post.content || post.caption || post.message || post.text || "").trim();
  if (text) return text;
  const count = Number(post.commentCount ?? post.comments_count ?? 0);
  return `Post #${shortPostId(post.id)} (${count} comments)`;
}

function numberFromAny(...values: unknown[]): number {
  for (const v of values) {
    if (typeof v === "number" && Number.isFinite(v)) return v;
    if (typeof v === "string" && v.trim()) {
      const n = Number(v);
      if (Number.isFinite(n)) return n;
    }
    // Facebook Graph API returns several engagement fields as objects with a
    // nested numeric count, e.g. shares: { count: 5 }, reactions: { total_count: 12 }.
    // Without this branch those values were silently dropped (returned 0), which
    // is why posts that had real shares were displayed as "0 shares".
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const obj = v as Record<string, unknown>;
      const candidates = [obj.count, obj.total_count, obj.totalCount, obj.total, obj.value];
      for (const c of candidates) {
        if (typeof c === "number" && Number.isFinite(c)) return c;
        if (typeof c === "string" && c.trim()) {
          const n = Number(c);
          if (Number.isFinite(n)) return n;
        }
      }
    }
  }
  return 0;
}

function normalizeCommentedPost(input: CommentedPost): CommentedPost {
  const raw = input as CommentedPost & Record<string, unknown>;
  const metrics = (raw.metrics && typeof raw.metrics === "object" ? raw.metrics : {}) as Record<string, unknown>;
  const insights = (raw.insights && typeof raw.insights === "object" ? raw.insights : {}) as Record<string, unknown>;
  const engagement = (raw.engagement && typeof raw.engagement === "object" ? raw.engagement : {}) as Record<string, unknown>;
  const analytics = (raw.analytics && typeof raw.analytics === "object" ? raw.analytics : {}) as Record<string, unknown>;
  const platformAnalytics = Array.isArray(raw.platformAnalytics) ? raw.platformAnalytics : [];
  const firstPA = (
    platformAnalytics[0] && typeof platformAnalytics[0] === "object"
      ? (platformAnalytics[0] as Record<string, unknown>)
      : {}
  ) as Record<string, unknown>;

  const likes = numberFromAny(
    raw.likes,
    raw.likeCount,
    raw.like_count,
    raw.reactions,
    raw.reactionCount,
    raw.reaction_count,
    metrics.likes,
    metrics.like_count,
    metrics.reactions,
    metrics.reactions_count,
    insights.likes,
    insights.reactions,
    engagement.likes,
    analytics.likes,
    analytics.likeCount,
    analytics.like_count,
    analytics.reactions,
    analytics.reactionCount,
    analytics.reaction_count,
    analytics.reactions_count,
    firstPA.likes,
    firstPA.likeCount,
    firstPA.like_count,
    firstPA.reactions,
    firstPA.reactionCount,
    firstPA.reaction_count,
    firstPA.reactions_count,
  );
  const shares = numberFromAny(
    // Facebook returns `shares` as {count: N}; numberFromAny now unwraps that automatically.
    raw.shares,
    raw.share,
    raw.shareCount,
    raw.share_count,
    raw.sharesCount,
    (raw as Record<string, unknown>).reshares,
    (raw as Record<string, unknown>).reshareCount,
    (raw as Record<string, unknown>).reshare_count,
    (raw as Record<string, unknown>).reposts,
    (raw as Record<string, unknown>).repostCount,
    (raw as Record<string, unknown>).repost_count,
    (raw as Record<string, unknown>).forwards,
    (raw as Record<string, unknown>).forwardCount,
    (raw as Record<string, unknown>).forward_count,
    metrics.shares,
    metrics.share,
    metrics.share_count,
    metrics.shares_count,
    metrics.reshares,
    metrics.reshare_count,
    metrics.reposts,
    metrics.repost_count,
    metrics.forwards,
    metrics.forward_count,
    insights.shares,
    insights.reshares,
    engagement.shares,
    engagement.reshares,
    analytics.shares,
    analytics.share,
    analytics.shareCount,
    analytics.share_count,
    analytics.shares_count,
    analytics.reshares,
    analytics.reshare_count,
    analytics.reposts,
    analytics.repost_count,
    firstPA.shares,
    firstPA.share,
    firstPA.shareCount,
    firstPA.share_count,
    firstPA.shares_count,
    firstPA.reshares,
    firstPA.reshare_count,
    firstPA.reposts,
    firstPA.repost_count,
  );
  const comments = numberFromAny(
    raw.commentCount,
    raw.comments_count,
    raw.comments,
    raw.total_comments,
    metrics.comments,
    metrics.comment_count,
    metrics.comments_count,
    insights.comments,
    engagement.comments,
    analytics.comments,
    analytics.commentCount,
    analytics.comment_count,
    analytics.comments_count,
    firstPA.comments,
    firstPA.commentCount,
    firstPA.comment_count,
    firstPA.comments_count,
  );
  const saves = numberFromAny(
    raw.saves,
    raw.saveCount,
    raw.save_count,
    metrics.saves,
    insights.saves,
    engagement.saves,
    analytics.saves,
    analytics.saveCount,
    analytics.save_count,
    firstPA.saves,
    firstPA.saveCount,
    firstPA.save_count,
  );
  const clicks = numberFromAny(
    raw.clicks,
    raw.clickCount,
    raw.click_count,
    raw.linkClicks,
    raw.link_clicks,
    metrics.clicks,
    metrics.link_clicks,
    insights.clicks,
    insights.link_clicks,
    engagement.clicks,
    analytics.clicks,
    analytics.clickCount,
    analytics.click_count,
    analytics.linkClicks,
    analytics.link_clicks,
    firstPA.clicks,
    firstPA.clickCount,
    firstPA.click_count,
    firstPA.linkClicks,
    firstPA.link_clicks,
  );
  const reach = numberFromAny(
    raw.reach,
    raw.impressions,
    metrics.reach,
    metrics.impressions,
    insights.reach,
    insights.impressions,
    engagement.reach,
    analytics.reach,
    analytics.impressions,
    firstPA.reach,
    firstPA.impressions,
  );

  return {
    ...input,
    likes,
    likeCount: likes,
    like_count: likes,
    shares,
    shareCount: shares,
    share_count: shares,
    commentCount: comments,
    comments_count: comments,
    saves,
    saveCount: saves,
    save_count: saves,
    clicks,
    clickCount: clicks,
    click_count: clicks,
    reach,
  };
}

function pickAnalyticsRows(payload: unknown): CommentedPost[] {
  if (Array.isArray(payload)) return payload as CommentedPost[];
  if (!payload || typeof payload !== "object") return [];
  const obj = payload as Record<string, unknown>;
  if (Array.isArray(obj.data)) return obj.data as CommentedPost[];
  if (Array.isArray(obj.posts)) return obj.posts as CommentedPost[];
  // Single-post analytics shape: object contains postId + analytics.
  if (obj.postId || obj.latePostId || obj.analytics) return [obj as unknown as CommentedPost];
  const nestedData = obj.data;
  if (nestedData && typeof nestedData === "object") {
    const d = nestedData as Record<string, unknown>;
    if (Array.isArray(d.posts)) return d.posts as CommentedPost[];
    if (d.postId || d.latePostId || d.analytics) return [d as unknown as CommentedPost];
  }
  return [];
}

function postLookupKeys(post: CommentedPost): string[] {
  const raw = post as Record<string, unknown>;
  const analytics = (raw.analytics && typeof raw.analytics === "object" ? raw.analytics : {}) as Record<string, unknown>;
  const platformAnalytics = Array.isArray(raw.platformAnalytics) ? raw.platformAnalytics : [];
  const firstPA = (platformAnalytics[0] && typeof platformAnalytics[0] === "object")
    ? (platformAnalytics[0] as Record<string, unknown>)
    : ({} as Record<string, unknown>);
  const keys = [
    post.id,
    String(raw.postId || ""),
    String(raw.post_id || ""),
    String(raw.id || ""),
    String(raw.latePostId || ""),
    String(raw.late_post_id || ""),
    String(raw.platformPostId || ""),
    String(firstPA.platformPostId || ""),
    String(raw.platformPostUrl || ""),
    String(firstPA.platformPostUrl || ""),
    String(analytics.postId || ""),
    String(raw.zernio_post_id || ""),
    String(raw.external_post_id || ""),
    String(raw.permalink || ""),
  ]
    .map((x) => String(x ?? "").trim())
    .filter(Boolean);
  return Array.from(new Set(keys));
}

function postAnalyticsIds(post: CommentedPost): string[] {
  const raw = post as Record<string, unknown>;
  const ids = [
    post.id,
    String(raw.postId || ""),
    String(raw.post_id || ""),
    String(raw.latePostId || ""),
    String(raw.late_post_id || ""),
    String(raw.cid || ""),
    String(raw.external_post_id || ""),
    String(raw.zernio_post_id || ""),
  ]
    .map((x) => String(x ?? "").trim())
    .filter(Boolean);
  return Array.from(new Set(ids));
}

function postMetric(post: CommentedPost, ...keys: Array<keyof CommentedPost>): number {
  for (const k of keys) {
    const v = post[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return 0;
}

function postEngagementScore(post: CommentedPost): number {
  const comments = postMetric(post, "commentCount", "comments_count");
  const likes = postMetric(post, "likes", "likeCount", "like_count");
  const shares = postMetric(post, "shares", "shareCount", "share_count");
  const saves = postMetric(post, "saves", "saveCount", "save_count");
  const clicks = postMetric(post, "clicks", "clickCount", "click_count");
  // Weighted to prioritize stronger intent signals.
  return comments * 4 + shares * 5 + likes * 1 + saves * 3 + clicks * 3;
}

function postPerformanceHint(post: CommentedPost): string {
  const comments = postMetric(post, "commentCount", "comments_count");
  const likes = postMetric(post, "likes", "likeCount", "like_count");
  const shares = postMetric(post, "shares", "shareCount", "share_count");
  if (shares >= Math.max(3, comments)) return "High share momentum: reuse this style and boost reach.";
  if (likes >= 20 && comments <= 2) return "High likes, low conversation: add stronger CTA in caption.";
  if (comments >= 5) return "Strong comment intent: route replies fast to convert interest.";
  return "Early-stage post: monitor for another few hours before changing strategy.";
}

function postMediaUrl(post: CommentedPost): string | undefined {
  return (
    post.picture ||
    post.thumbnailUrl ||
    post.thumbnail_url ||
    post.thumbnail ||
    post.imageUrl ||
    post.image_url ||
    post.image
  );
}

function postThumbBg(seed: string): string {
  const colors = [
    "linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)",
    "linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)",
    "linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)",
    "linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)",
    "linear-gradient(135deg, #ffe4e6 0%, #fecdd3 100%)",
  ];
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) h = (h << 5) - h + seed.charCodeAt(i);
  return colors[Math.abs(h) % colors.length];
}

function PostThumbnail({ post }: { post: CommentedPost }) {
  const media = postMediaUrl(post);
  if (media) {
    return (
      <img
        src={media}
        alt="Post media"
        className="h-10 w-10 rounded-md object-cover border border-slate-200 shrink-0"
      />
    );
  }
  const platform = String(post.platform || "").toLowerCase();
  const seed = `${post.id}-${platform}`;
  return (
    <div
      className="h-10 w-10 rounded-md border border-slate-200 shrink-0 flex flex-col items-center justify-center"
      style={{ background: postThumbBg(seed) }}
      title={`Post ${shortPostId(post.id)}`}
    >
      <span className="text-[9px] leading-none font-semibold text-slate-700">
        {platform === "facebook" ? "FB" : platform === "instagram" ? "IG" : "POST"}
      </span>
      <span className="text-[8px] leading-none text-slate-600 mt-0.5">
        {shortPostId(post.id).slice(0, 4)}
      </span>
    </div>
  );
}

function avatarColorSeed(input: string): string {
  const palette = [
    "#dbeafe", // blue-100
    "#dcfce7", // green-100
    "#fee2e2", // red-100
    "#fef3c7", // amber-100
    "#e9d5ff", // violet-200
    "#cffafe", // cyan-100
    "#fde68a", // yellow-200
    "#fde2e4", // rose-100
  ];
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }
  return palette[Math.abs(hash) % palette.length];
}

function ContactAvatar({
  name,
  avatar,
  size = 36,
}: {
  name?: string;
  avatar?: string;
  size?: number;
}) {
  const initials = (name || "?").trim().charAt(0).toUpperCase();
  const bg = avatarColorSeed(name || "unknown");
  if (avatar) {
    return (
      <img
        src={avatar}
        alt={name || "Profile"}
        className="shrink-0 rounded-full object-cover border border-white/70 shadow-sm"
        style={{ width: size, height: size, backgroundColor: bg }}
      />
    );
  }
  return (
    <div
      className="shrink-0 rounded-full flex items-center justify-center text-sm font-bold text-slate-700 border border-white/70 shadow-sm"
      style={{ width: size, height: size, backgroundColor: bg }}
    >
      {initials}
    </div>
  );
}

export default function SocialInboxPage() {
  const [viewMode, setViewMode] = useState<"messages" | "comments">("messages");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [platformFilter, setPlatformFilter] = useState("");
  const [accountFilter, setAccountFilter] = useState("");
  const [sortMode, setSortMode] = useState<"newest" | "oldest" | "unanswered" | "ai_autoreply">("newest");
  const [commentSort, setCommentSort] = useState<"newest" | "oldest" | "most_comments" | "least_comments" | "best_engagement">("newest");
  const [aiCustomers, setAiCustomers] = useState<AiCustomer[]>([]);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<"ok" | "err" | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [fbTag, setFbTag] = useState<"HUMAN_AGENT">("HUMAN_AGENT");
  const [commentedPosts, setCommentedPosts] = useState<CommentedPost[]>([]);
  const [selectedPost, setSelectedPost] = useState<CommentedPost | null>(null);
  const [postComments, setPostComments] = useState<PostComment[]>([]);
  const [commentOrder, setCommentOrder] = useState<"unreplied" | "newest">("unreplied");
  const [loadingComments, setLoadingComments] = useState(false);
  const [commentReply, setCommentReply] = useState("");
  const [sendingCommentReply, setSendingCommentReply] = useState(false);
  const [selectedCommentId, setSelectedCommentId] = useState<string | null>(null);
  const [engagementDebugByPost, setEngagementDebugByPost] = useState<Record<string, EngagementDebug>>({});
  const [commentAutoReply, setCommentAutoReply] = useState<ZernioCommentAutoReplySettings>(DEFAULT_COMMENT_AUTOREPLY);
  const [savingCommentAutoReply, setSavingCommentAutoReply] = useState(false);
  const [newRuleKeyword, setNewRuleKeyword] = useState("");
  const [newRuleMessage, setNewRuleMessage] = useState("");
  const [newStepType, setNewStepType] = useState<"text" | "image" | "video" | "file">("text");
  const [newStepMessage, setNewStepMessage] = useState("");
  const [newStepMediaUrl, setNewStepMediaUrl] = useState("");
  const [newStepDelay, setNewStepDelay] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const normalizePostComment = (raw: PostComment): PostComment => {
    const c = raw as PostComment & Record<string, unknown>;
    const fromObj = (c.from && typeof c.from === "object" ? c.from : {}) as Record<string, unknown>;
    return {
      ...raw,
      commentId: (c.commentId as string | undefined) ?? (c.comment_id as string | undefined) ?? String(c.id || ""),
      comment_id: (c.comment_id as string | undefined) ?? (c.commentId as string | undefined) ?? String(c.id || ""),
      message: (c.message as string | undefined) ?? (c.text as string | undefined) ?? "",
      text: (c.text as string | undefined) ?? (c.message as string | undefined) ?? "",
      author:
        (c.author as string | undefined)
        ?? (c.username as string | undefined)
        ?? (fromObj.name as string | undefined)
        ?? (fromObj.username as string | undefined)
        ?? "User",
      username:
        (c.username as string | undefined)
        ?? (fromObj.username as string | undefined)
        ?? (fromObj.name as string | undefined),
      from: {
        id: (fromObj.id as string | undefined),
        name: (fromObj.name as string | undefined),
        username: (fromObj.username as string | undefined),
        picture: (fromObj.picture as string | undefined),
        isOwner: Boolean(fromObj.isOwner),
      },
      createdAt:
        (c.createdAt as string | undefined)
        ?? (c.created_at as string | undefined)
        ?? (c.createdTime as string | undefined),
      created_at:
        (c.created_at as string | undefined)
        ?? (c.createdAt as string | undefined)
        ?? (c.createdTime as string | undefined),
      createdTime:
        (c.createdTime as string | undefined)
        ?? (c.createdAt as string | undefined)
        ?? (c.created_at as string | undefined),
      replyCount:
        typeof c.replyCount === "number" ? c.replyCount : typeof c.reply_count === "number" ? c.reply_count : 0,
      reply_count:
        typeof c.reply_count === "number" ? c.reply_count : typeof c.replyCount === "number" ? c.replyCount : 0,
      canReply:
        typeof c.canReply === "boolean" ? c.canReply : typeof c.can_reply === "boolean" ? c.can_reply : true,
      can_reply:
        typeof c.can_reply === "boolean" ? c.can_reply : typeof c.canReply === "boolean" ? c.canReply : true,
      isHidden:
        typeof c.isHidden === "boolean" ? c.isHidden : typeof c.is_hidden === "boolean" ? c.is_hidden : false,
      is_hidden:
        typeof c.is_hidden === "boolean" ? c.is_hidden : typeof c.isHidden === "boolean" ? c.isHidden : false,
    };
  };

  const buildQuickReplyDraft = (comment: PostComment): string => {
    const author = (comment.author || "there").split(" ")[0];
    const text = String(comment.message || comment.text || "").toLowerCase();
    if (text.includes("?")) return `Hi ${author}, thanks for your question. Please share a bit more detail and we will assist right away.`;
    if (text.includes("price") || text.includes("how much")) return `Hi ${author}, thanks for checking in. Please DM us the item you want and we will share the latest price and options.`;
    if (text.includes("thank")) return `You are welcome ${author}. We appreciate your support.`;
    return `Hi ${author}, thanks for your comment. We have seen it and we will follow up shortly.`;
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [status, accs, customers, autoReplySettings, emailRes] = await Promise.all([
        zernioApi.status(),
        zernioApi.accounts().catch(() => ({})),
        customersApi.list().catch(() => [] as AiCustomer[]),
        zernioApi.getCommentAutoReplySettings().catch(() => DEFAULT_COMMENT_AUTOREPLY),
        fetch("/api/email?limit=50", { headers: authHeaders() }).catch(() => null),
      ]);
      const socialConnected = (status as { connected?: boolean }).connected === true;
      const emailPayload = emailRes && emailRes.ok
        ? (await emailRes.json() as { connected?: boolean; threads?: Array<Record<string, unknown>> })
        : null;
      const emailConnected = Boolean(emailPayload?.connected);
      const isConnected = socialConnected || emailConnected;
      setConnected(isConnected);
      if (isConnected) {
        let socialConversations: Conversation[] = [];
        const list = pickList<Account>(accs, ["accounts"]);
        setAccounts(list);
        if (socialConnected) {
          // Load social inbox
          const inbox = await zernioApi.inbox(platformFilter || undefined);
          socialConversations = pickList<Conversation>(inbox, ["conversations"]).map(normalizeConversation);
        }
        if (socialConnected) {
          const cposts = await zernioApi.commentedPosts({
            ...(platformFilter ? { platform: platformFilter } : {}),
            ...(accountFilter ? { account_id: accountFilter } : {}),
            limit: 50,
          }).catch(() => ({}));
          const [commentedRaw, postsRaw, analyticsRaw] = await Promise.all([
            Promise.resolve(pickList<CommentedPost>(cposts, ["posts", "comments"])),
            zernioApi.posts(platformFilter || undefined).then((p) => pickList<CommentedPost>(p, ["posts"])).catch(() => [] as CommentedPost[]),
            zernioApi.analytics({
              platform: platformFilter || "facebook",
              ...(accountFilter ? { account_id: accountFilter } : {}),
              metrics: "likes,comments,shares,saves,clicks,reach,impressions",
              limit: 100,
              page: 1,
            }).then((p) => pickAnalyticsRows(p)).catch(() => [] as CommentedPost[]),
          ]);
        const postsByKey = new Map<string, CommentedPost>();
        postsRaw.map(normalizeCommentedPost).forEach((p) => {
          postLookupKeys(p).forEach((k) => postsByKey.set(k, p));
        });
        analyticsRaw.map(normalizeCommentedPost).forEach((p) => {
          postLookupKeys(p).forEach((k) => postsByKey.set(k, p));
        });
        const mergedCommented = commentedRaw.map((p) => {
          const normalized = normalizeCommentedPost(p);
          const candidates = postLookupKeys(normalized);
          const matched = candidates.map((k) => postsByKey.get(k)).find(Boolean);
          if (!matched) return normalized;
          return normalizeCommentedPost({
            ...matched,
            ...normalized,
            id: normalized.id || matched.id,
            accountId: normalized.accountId || normalized.account_id || matched.accountId || matched.account_id,
            account_id: normalized.account_id || normalized.accountId || matched.account_id || matched.accountId,
            platform: normalized.platform || matched.platform,
            picture: normalized.picture || matched.picture,
            thumbnailUrl: normalized.thumbnailUrl || matched.thumbnailUrl,
            imageUrl: normalized.imageUrl || matched.imageUrl,
            commentCount: numberFromAny(normalized.commentCount, normalized.comments_count, matched.commentCount, matched.comments_count),
            comments_count: numberFromAny(normalized.comments_count, normalized.commentCount, matched.comments_count, matched.commentCount),
            likes: numberFromAny(normalized.likes, normalized.likeCount, normalized.like_count, matched.likes, matched.likeCount, matched.like_count),
            shares: numberFromAny(normalized.shares, normalized.shareCount, normalized.share_count, matched.shares, matched.shareCount, matched.share_count),
            saves: numberFromAny(normalized.saves, normalized.saveCount, normalized.save_count, matched.saves, matched.saveCount, matched.save_count),
            clicks: numberFromAny(normalized.clicks, normalized.clickCount, normalized.click_count, matched.clicks, matched.clickCount, matched.click_count),
          });
        });

        // Final fallback: per-post analytics (batched — avoids Zernio 429 bursts).
        const perPostAnalytics = await mapInBatches(
          mergedCommented.slice(0, 20),
          3,
          400,
          async (post) => {
            const accountId = String(post.accountId || post.account_id || "").trim();
            const ids = postAnalyticsIds(post);
            if (!accountId) {
              return {
                key: post.id,
                debug: {
                  accountId: "",
                  platform: String(post.platform || platformFilter || "facebook"),
                  idsTried: ids,
                  source: "error" as const,
                  message: "Missing accountId",
                },
              };
            }
            if (ids.length === 0) {
              return {
                key: post.id,
                debug: {
                  accountId,
                  platform: String(post.platform || platformFilter || "facebook"),
                  idsTried: [],
                  source: "error" as const,
                  message: "No post IDs available to query analytics",
                },
              };
            }
            const tried: string[] = [];
            for (const pid of ids) {
              try {
                tried.push(pid);
                const payload = await zernioApi.analyticsByPostId(pid, {
                  platform: String(post.platform || platformFilter || "facebook"),
                  account_id: accountId,
                  metrics: "likes,comments,shares,saves,clicks,reach,impressions",
                });
                const row = pickAnalyticsRows(payload)[0];
                if (row) {
                  const n = normalizeCommentedPost(row);
                  return {
                    key: post.id,
                    likes: numberFromAny(n.likes, n.likeCount, n.like_count),
                    shares: numberFromAny(n.shares, n.shareCount, n.share_count),
                    comments: numberFromAny(n.commentCount, n.comments_count),
                    saves: numberFromAny(n.saves, n.saveCount, n.save_count),
                    clicks: numberFromAny(n.clicks, n.clickCount, n.click_count),
                    debug: {
                      accountId,
                      platform: String(post.platform || platformFilter || "facebook"),
                      idsTried: tried,
                      source: "analytics-by-post" as const,
                      likes: numberFromAny(n.likes, n.likeCount, n.like_count),
                      shares: numberFromAny(n.shares, n.shareCount, n.share_count),
                      comments: numberFromAny(n.commentCount, n.comments_count),
                      message: "Matched analytics by postId path endpoint",
                    },
                  };
                }
              } catch (err) {
                // try next candidate id
                const msg = err instanceof Error ? err.message : "analytics request failed";
                if (tried.length === ids.length) {
                  return {
                    key: post.id,
                    debug: {
                      accountId,
                      platform: String(post.platform || platformFilter || "facebook"),
                      idsTried: tried,
                      source: "error" as const,
                      message: msg,
                    },
                  };
                }
              }
            }
            return {
              key: post.id,
              debug: {
                accountId,
                platform: String(post.platform || platformFilter || "facebook"),
                idsTried: tried,
                source: "no-match" as const,
                message: "No analytics row returned for tried IDs",
              },
            };
          }
        );

        const metricsByPostId = new Map<string, { likes: number; shares: number; comments: number; saves: number; clicks: number }>();
        perPostAnalytics.forEach((x) => {
          if (!x || !x.key) return;
          if (
            typeof x.likes === "number" &&
            typeof x.shares === "number" &&
            typeof x.comments === "number" &&
            typeof x.saves === "number" &&
            typeof x.clicks === "number"
          ) {
            metricsByPostId.set(x.key, {
              likes: x.likes,
              shares: x.shares,
              comments: x.comments,
              saves: x.saves,
              clicks: x.clicks,
            });
          }
        });
        const debugByPost: Record<string, EngagementDebug> = {};
        perPostAnalytics.forEach((x) => {
          if (!x || !x.key) return;
          if (x.debug) {
            debugByPost[x.key] = x.debug;
          } else if (!debugByPost[x.key]) {
            debugByPost[x.key] = {
              accountId: String(mergedCommented.find((p) => p.id === x.key)?.accountId || ""),
              platform: String(mergedCommented.find((p) => p.id === x.key)?.platform || ""),
              idsTried: postAnalyticsIds(mergedCommented.find((p) => p.id === x.key) || ({ id: x.key } as CommentedPost)),
              source: "no-match",
            };
          }
        });

        const withDirectAnalytics = mergedCommented.map((p) => {
          const m = metricsByPostId.get(p.id);
          if (!m) return p;
          // For likes/saves/clicks, analytics-by-post is the most accurate source.
          //
          // For comments AND shares, however, Instagram's analytics endpoint often returns
          // 0 even when the post has activity (the metric scope used for likes/reach does
          // not include comments, and shares are not exposed for organic Instagram at all).
          // Facebook returns shares as a nested {count: N} object on the post itself, which
          // /analytics may not surface. To avoid clobbering a real count with the analytics
          // 0, take the max of analytics and the post-object value.
          const inboxCommentCount = numberFromAny(p.commentCount, p.comments_count);
          const analyticsCommentCount = numberFromAny(m.comments);
          const mergedComments = Math.max(inboxCommentCount, analyticsCommentCount);
          const postShareCount = numberFromAny(p.shares, p.shareCount, p.share_count);
          const analyticsShareCount = numberFromAny(m.shares);
          const mergedShares = Math.max(postShareCount, analyticsShareCount);
          return normalizeCommentedPost({
            ...p,
            likes: numberFromAny(m.likes, p.likes, p.likeCount, p.like_count),
            shares: mergedShares,
            shareCount: mergedShares,
            share_count: mergedShares,
            commentCount: mergedComments,
            comments_count: mergedComments,
            saves: numberFromAny(m.saves, p.saves, p.saveCount, p.save_count),
            clicks: numberFromAny(m.clicks, p.clicks, p.clickCount, p.click_count),
          });
        });

        setCommentedPosts(withDirectAnalytics);
        setEngagementDebugByPost(debugByPost);

        const relevantCustomers = (customers as AiCustomer[])
          .filter((c) => c && typeof c === "object")
          .sort((a, b) => {
            const ta = new Date(a.last_contacted || 0).getTime();
            const tb = new Date(b.last_contacted || 0).getTime();
            return tb - ta;
          })
          .slice(0, 8);
        setAiCustomers(relevantCustomers);
      }
        const emailThreads = Array.isArray(emailPayload?.threads) ? emailPayload.threads : [];
        const emailConversations: Conversation[] = emailThreads.map((t) => {
          const provider = String(t.provider || "gmail").toLowerCase() as "gmail" | "microsoft";
          const threadId = String(t.id || "");
          const from = String(t.from || "").trim();
          return normalizeConversation({
            id: `email:${provider}:${threadId}`,
            threadId,
            source: "email",
            emailProvider: provider,
            platform: provider,
            participant_name: from || "(unknown sender)",
            participant: from || "(unknown sender)",
            last_message: String(t.snippet || ""),
            last_message_at: String(t.date || ""),
            unread: Number(t.unread ? 1 : 0),
            accountId: "",
            account_id: "",
            subject: String(t.subject || "(no subject)"),
          } as Conversation);
        });
        const merged = [...socialConversations, ...emailConversations].sort((a, b) =>
          new Date(b.last_message_at || 0).getTime() - new Date(a.last_message_at || 0).getTime(),
        );
        setConversations(merged);
        if (!socialConnected) {
          setCommentedPosts([]);
          setEngagementDebugByPost({});
          setAiCustomers([]);
        }
      }
      const settings = autoReplySettings as ZernioCommentAutoReplySettings;
      if (settings && typeof settings === "object") {
        setCommentAutoReply({
          ...DEFAULT_COMMENT_AUTOREPLY,
          ...settings,
          post_ids: Array.isArray(settings.post_ids) ? settings.post_ids : [],
          manychat_post_ids: Array.isArray(settings.manychat_post_ids) ? settings.manychat_post_ids : [],
          keyword_rules: Array.isArray(settings.keyword_rules) ? settings.keyword_rules : [],
          chain_steps: Array.isArray(settings.chain_steps) ? settings.chain_steps : [],
        });
      }
    } finally { setLoading(false); }
  }, [platformFilter, accountFilter]);

  useEffect(() => { load(); }, [load]);

  async function openConversation(conv: Conversation, silent = false) {
    setSelected(conv);
    if (!silent) {
      setLoadingMsgs(true);
      setMessages([]);
    }
    try {
      if (conv.source === "email" && conv.threadId) {
        const res = await fetch("/api/email", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            action: "get_thread",
            threadId: conv.threadId,
            provider: conv.emailProvider || conv.platform,
          }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json() as { messages?: Message[] };
        const normalized = pickList<Message>(data, ["messages"]).map((m) => {
          const sender = extractEmailAddress(m.from);
          const participant = extractEmailAddress(conv.participant_name || conv.participant || "");
          const maybeBody = (m as unknown as { body?: string }).body;
          return {
            ...m,
            content: maybeBody || m.content || "",
            direction: participant && sender && sender === participant ? "in" : "out",
            created_at: m.date || m.created_at || new Date().toISOString(),
          } as Message;
        });
        setMessages(normalized);
      } else {
        const data = await zernioApi.conversation(conv.id, conv.accountId || conv.account_id);
        const normalized = pickList<Message>(data, ["messages"]).map((m) => normalizeMessage(m, conv));
        setMessages(rebalanceDirections(normalized, conv));
      }
    } finally {
      if (!silent) setLoadingMsgs(false);
    }
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
  }

  async function sendReply() {
    if (!selected || !reply.trim()) return;
    setSending(true);
    setSendResult(null);
    setSendError(null);
    
    const replyText = reply.trim();
    
    // 1. Optimistic UI update: instantly append sent message to the chat list
    const tempId = "temp-" + Date.now();
    const tempMsg: Message = {
      id: tempId,
      content: replyText,
      direction: "out",
      created_at: new Date().toISOString(),
      sender: "Me",
    };
    setMessages((prev) => [...prev, tempMsg]);
    setReply(""); // Clear text input box instantly
    
    // Auto-scroll to show the newly added message
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 50);

    try {
      if (selected.source === "email") {
        const to = extractEmailAddress(selected.participant_name || selected.participant || "");
        const subjectBase = selected.subject || "Message";
        const subject = /^re:/i.test(subjectBase) ? subjectBase : `Re: ${subjectBase}`;
        const res = await fetch("/api/email", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            action: "send",
            provider: selected.emailProvider || selected.platform,
            to,
            subject,
            replyBody: replyText,
          }),
        });
        if (!res.ok) throw new Error(await res.text());
      } else {
        await zernioApi.send(
          selected.id,
          replyText,
          selected.accountId || selected.account_id,
          selected.platform,
          facebookReplyWindowClosed ? "MESSAGE_TAG" : undefined,
          facebookReplyWindowClosed ? fbTag : undefined
        );
      }
      setSendResult("ok");
      // 2. Silent reload to sync actual server-side IDs and timestamps in the background
      await openConversation(selected, true);
    } catch (e) {
      // Revert optimistic update on failure
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
      setReply(replyText); // Restore input so user doesn't lose text
      
      setSendResult("err");
      const raw = e instanceof Error ? e.message : "Could not send message";
      if (raw.toLowerCase().includes("24") || raw.toLowerCase().includes("window")) {
        setSendError(`${raw}. This thread may be outside Facebook's reply window.`);
      } else {
        setSendError(raw);
      }
    } finally { setSending(false); }
  }

  async function openCommentPost(post: CommentedPost) {
    setSelectedPost(post);
    setLoadingComments(true);
    setPostComments([]);
    try {
      const accountId = post.accountId || post.account_id;
      if (!accountId) return;
      const data = await zernioApi.postComments(post.id, accountId, {
        ...(post.platform ? { platform: post.platform } : {}),
        limit: 100,
      });
      const normalized = pickList<PostComment>(data, ["comments"]).map(normalizePostComment);
      setPostComments(normalized);
      // Self-correcting count: when we successfully fetch the comment list, the
      // returned length is the ground truth. Sync it back into the post card so
      // platforms whose analytics endpoint returns 0 comments (notably Instagram)
      // show the correct badge after the user opens the thread.
      const actualCount = normalized.length;
      if (actualCount > 0) {
        setCommentedPosts((prev) =>
          prev.map((p) =>
            p.id === post.id
              ? { ...p, commentCount: Math.max(p.commentCount || 0, actualCount), comments_count: Math.max(p.comments_count || 0, actualCount) }
              : p,
          ),
        );
        setSelectedPost((prev) =>
          prev && prev.id === post.id
            ? { ...prev, commentCount: Math.max(prev.commentCount || 0, actualCount), comments_count: Math.max(prev.comments_count || 0, actualCount) }
            : prev,
        );
      }
    } finally {
      setLoadingComments(false);
    }
  }

  async function sendCommentReply() {
    if (!selectedPost || !selectedCommentId || !commentReply.trim()) return;
    const accountId = selectedPost.accountId || selectedPost.account_id;
    if (!accountId) return;
    setSendingCommentReply(true);
    try {
      await zernioApi.replyToComment(selectedPost.id, {
        account_id: accountId,
        comment_id: selectedCommentId,
        message: commentReply.trim(),
      });
      setCommentReply("");
      await openCommentPost(selectedPost);
    } finally {
      setSendingCommentReply(false);
    }
  }

  async function saveCommentAutoReply(next: ZernioCommentAutoReplySettings) {
    setSavingCommentAutoReply(true);
    try {
      const saved = await zernioApi.updateCommentAutoReplySettings(next);
      setCommentAutoReply({
        ...DEFAULT_COMMENT_AUTOREPLY,
        ...saved,
        post_ids: Array.isArray(saved.post_ids) ? saved.post_ids : [],
        manychat_post_ids: Array.isArray(saved.manychat_post_ids) ? saved.manychat_post_ids : [],
        keyword_rules: Array.isArray(saved.keyword_rules) ? saved.keyword_rules : [],
        chain_steps: Array.isArray(saved.chain_steps) ? saved.chain_steps : [],
      });
    } finally {
      setSavingCommentAutoReply(false);
    }
  }

  // Derive the platform list from connected accounts (not from conversations) so
  // a freshly-connected platform like TikTok/Twitter/YouTube/LinkedIn shows up
  // in the filter even before any DM has arrived from it. Fall back to the
  // platforms seen in conversations + commentedPosts so anything routed in but
  // missing from /accounts (rare) is still selectable.
  const platforms = [
    ...new Set([
      ...accounts.map((a) => String(a.platform || "").toLowerCase()).filter(Boolean),
      ...conversations.map((c) => String(c.platform || "").toLowerCase()).filter(Boolean),
      ...commentedPosts.map((p) => String(p.platform || "").toLowerCase()).filter(Boolean),
    ]),
  ];

  const filteredConvs = conversations
    .filter((c) => (platformFilter ? c.platform === platformFilter : true))
    .filter((c) => {
      if (!accountFilter) return true;
      const cid = c.accountId || c.account_id || "";
      return cid === accountFilter;
    })
    .filter((c) => {
      if (sortMode !== "ai_autoreply") return true;
      const participant = String(c.participant_name || c.participant || "").trim().toLowerCase();
      if (!participant) return false;
      return aiCustomers.some((cust) => {
        if (!cust.auto_reply) return false;
        const n = String(cust.name || "").trim().toLowerCase();
        return n && (n === participant || n.includes(participant) || participant.includes(n));
      });
    })
    .sort((a, b) => {
      const ta = new Date(a.last_message_at || 0).getTime();
      const tb = new Date(b.last_message_at || 0).getTime();
      if (sortMode === "oldest") return ta - tb;
      if (sortMode === "unanswered") {
        const au = Number(a.unread || 0) > 0 ? 1 : 0;
        const bu = Number(b.unread || 0) > 0 ? 1 : 0;
        if (au !== bu) return bu - au;
      }
      return tb - ta;
    });

  const filteredCommentedPosts = commentedPosts
    .filter((p) => (platformFilter ? String(p.platform || "").toLowerCase() === platformFilter.toLowerCase() : true))
    .filter((p) => {
      if (!accountFilter) return true;
      const aid = String(p.accountId || p.account_id || "");
      return aid === accountFilter;
    })
    .sort((a, b) => {
      const ca = Number(a.commentCount ?? a.comments_count ?? 0);
      const cb = Number(b.commentCount ?? b.comments_count ?? 0);
      const ta = new Date(a.createdAt || a.created_at || 0).getTime();
      const tb = new Date(b.createdAt || b.created_at || 0).getTime();
      const ea = postEngagementScore(a);
      const eb = postEngagementScore(b);
      if (commentSort === "best_engagement") return eb - ea;
      if (commentSort === "most_comments") return cb - ca;
      if (commentSort === "least_comments") return ca - cb;
      if (commentSort === "oldest") return ta - tb;
      return tb - ta;
    });

  const facebookReplyWindowClosed =
    selected?.platform === "facebook" &&
    isOlderThanHours(selected?.last_message_at, 24);

  const orderedPostComments = [...postComments].sort((a, b) => {
    const ta = new Date(a.createdAt || a.created_at || a.createdTime || 0).getTime();
    const tb = new Date(b.createdAt || b.created_at || b.createdTime || 0).getTime();
    if (commentOrder === "newest") return tb - ta;
    const ar = Number(a.replyCount ?? a.reply_count ?? 0);
    const br = Number(b.replyCount ?? b.reply_count ?? 0);
    const aUnreplied = ar === 0 ? 1 : 0;
    const bUnreplied = br === 0 ? 1 : 0;
    if (aUnreplied !== bUnreplied) return bUnreplied - aUnreplied;
    return tb - ta;
  });
  const selectedPostAutoEnabled = !!selectedPost && (
    commentAutoReply.apply_all_posts || commentAutoReply.manychat_post_ids.includes(selectedPost.id)
  );

  // Not connected state
  if (connected === false) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50">
        <div className="text-center space-y-3 max-w-sm px-6">
          <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto">
            <Inbox size={28} className="text-slate-400" />
          </div>
          <p className="text-base font-semibold text-slate-700">Social Inbox coming soon</p>
          <p className="text-sm text-slate-400 leading-relaxed">
            Your social media channels are being set up. Once activated, all your messages from Facebook, Instagram, WhatsApp, and more will appear here.
          </p>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {loading ? "Checking…" : "Refresh"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-0px)] overflow-hidden">
      {/* Left panel — conversation list */}
      <div className={`flex flex-col border-r border-slate-200 bg-white ${(viewMode === "messages" ? selected : selectedPost) ? "hidden md:flex w-80" : "flex w-full md:w-80"}`}>
        {/* Header */}
        <div className="p-4 border-b border-slate-100">
          <div className="flex items-center justify-between mb-3">
            <h1 className="font-bold text-slate-800 flex items-center gap-2">
              <Inbox size={18} className="text-brand-dark" /> Social Inbox
            </h1>
            <button onClick={load} className="text-slate-400 hover:text-slate-700">
              <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
          <div className="mb-3 inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("messages")}
              className={`px-2.5 py-1 text-xs rounded-md ${viewMode === "messages" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}
            >
              Messages
            </button>
            <button
              type="button"
              onClick={() => setViewMode("comments")}
              className={`px-2.5 py-1 text-xs rounded-md ${viewMode === "comments" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}
            >
              Comments + Engagement
            </button>
          </div>
          {/* Connected accounts */}
          {accounts.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {accounts.map(a => (
                <span key={a.id} className="flex items-center gap-1 px-2 py-0.5 bg-green-50 border border-green-200 rounded-full text-xs text-green-700">
                  <CheckCircle size={10} /> {a.name || a.platform}
                </span>
              ))}
            </div>
          )}
          {/* Platform filter */}
          <div className="grid grid-cols-1 gap-2">
            <select
              value={platformFilter}
              onChange={(e) => {
                setPlatformFilter(e.target.value);
                setAccountFilter("");
              }}
              className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
            >
              <option value="">All platforms</option>
              {platforms.map((p) => (
                <option key={p} value={p}>
                  {p[0].toUpperCase() + p.slice(1)}
                </option>
              ))}
            </select>
            <select
              value={accountFilter}
              onChange={(e) => setAccountFilter(e.target.value)}
              className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
            >
              <option value="">All accounts</option>
              {accounts
                .filter(a => platformFilter ? String(a.platform || "").toLowerCase() === platformFilter.toLowerCase() : true)
                .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name || a.username || a.platform}
                </option>
              ))}
            </select>
            {viewMode === "messages" && (
              <select
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value as "newest" | "oldest" | "unanswered" | "ai_autoreply")}
                className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
              >
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="unanswered">Unanswered first</option>
                <option value="ai_autoreply">AI auto-reply customers</option>
              </select>
            )}
            {viewMode === "comments" && (
              <select
                value={commentSort}
                onChange={(e) => setCommentSort(e.target.value as "newest" | "oldest" | "most_comments" | "least_comments" | "best_engagement")}
                className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
              >
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="best_engagement">Best engagement</option>
                <option value="most_comments">Most comments</option>
                <option value="least_comments">Least comments</option>
              </select>
            )}
            {viewMode === "comments" ? (
              <span className="text-[11px] text-slate-500">Metrics shown as Likes · Shares · Comments</span>
            ) : null}
            {viewMode === "comments" && (
              <select
                value={selectedPost?.id || ""}
                onChange={(e) => {
                  const id = e.target.value;
                  const picked = filteredCommentedPosts.find((p) => p.id === id) || null;
                  if (picked) void openCommentPost(picked);
                  else {
                    setSelectedPost(null);
                    setPostComments([]);
                    setSelectedCommentId(null);
                  }
                }}
                className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
              >
                <option value="">Select post</option>
                {filteredCommentedPosts.map((p) => {
                  const title = postDisplayTitle(p);
                  return (
                    <option key={p.id} value={p.id}>
                      {title.slice(0, 72)}
                    </option>
                  );
                })}
              </select>
            )}
          </div>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-40 text-slate-400">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : viewMode === "messages" && filteredConvs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2 p-4 text-center">
              <Inbox size={36} className="opacity-30" />
              <p className="text-sm">No conversations yet.</p>
              <p className="text-xs">Connect your social accounts and messages will appear here.</p>
            </div>
          ) : viewMode === "messages" ? (
            filteredConvs.map(conv => (
              <button key={conv.id} onClick={() => openConversation(conv)}
                className={`w-full text-left px-4 py-3 border-b border-slate-50 hover:bg-slate-50 transition-colors ${selected?.id === conv.id ? "bg-brand/10 border-l-2 border-l-brand" : ""}`}>
                <div className="flex items-start gap-3">
                  <ContactAvatar
                    name={conv.participant_name || conv.participant || "Unknown"}
                    avatar={conv.avatar}
                    size={36}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <p className="font-medium text-slate-800 text-sm truncate">
                        {conv.participant_name || conv.participant || "Unknown"}
                      </p>
                      <span className="text-xs text-slate-400 shrink-0">{timeAgo(conv.last_message_at)}</span>
                    </div>
                    <p className="text-xs text-slate-500 truncate mt-0.5">{conv.last_message || "No messages"}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <PlatformBadge platform={conv.platform} />
                      {conv.unread ? (
                        <span className="bg-brand-dark text-white text-xs rounded-full px-1.5 py-0.5 font-bold">{conv.unread}</span>
                      ) : null}
                    </div>
                  </div>
                </div>
              </button>
            ))
          ) : filteredCommentedPosts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2 p-4 text-center">
              <MessageCircle size={36} className="opacity-30" />
              <p className="text-sm">No commented posts for this filter.</p>
              <p className="text-xs">Choose platform first, then select a post.</p>
            </div>
          ) : (
            filteredCommentedPosts.map((p) => {
              const count = Number(p.commentCount ?? p.comments_count ?? 0);
              const likes = postMetric(p, "likes", "likeCount", "like_count");
              const shares = postMetric(p, "shares", "shareCount", "share_count");
              const score = postEngagementScore(p);
              const title = postDisplayTitle(p);
              const ts = p.createdTime || p.createdAt || p.created_at;
              // Facebook's Graph API does NOT include share counts in the
              // standard /insights endpoint that Zernio uses (shares live on the
              // post object as `shares.count`, which Zernio doesn't surface).
              // Instagram does not expose organic share counts at all. Mark a
              // 0-share badge as "may be undercounted" so the owner doesn't
              // assume the post wasn't shared.
              const platformLower = String(p.platform || "").toLowerCase();
              const sharesUnreliable = (platformLower === "facebook" || platformLower === "instagram") && shares === 0;
              return (
                <button
                  key={p.id}
                  onClick={() => void openCommentPost(p)}
                  className={`w-full text-left px-4 py-3 border-b border-slate-50 hover:bg-slate-50 transition-colors ${selectedPost?.id === p.id ? "bg-brand/10 border-l-2 border-l-brand" : ""}`}
                >
                  <div className="flex items-start gap-3">
                    <PostThumbnail post={p} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-800 truncate">{title}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {likes} likes ·{" "}
                        {sharesUnreliable ? (
                          <span
                            className="underline decoration-dotted decoration-slate-400 cursor-help"
                            title={
                              platformLower === "facebook"
                                ? "Facebook share counts are not surfaced through our analytics sync (the Page insights endpoint doesn't include shares). Open the post on Facebook to see the real share count."
                                : "Instagram does not expose organic share counts via the API. Boosted posts and Reels may still show shares."
                            }
                          >
                            {shares} shares*
                          </span>
                        ) : (
                          <>{shares} shares</>
                        )}{" "}
                        · {count} comments · score {score} · #{shortPostId(p.id)}
                      </p>
                      {p.platform ? <div className="mt-1"><PlatformBadge platform={p.platform} /></div> : null}
                    </div>
                    <span className="text-xs text-slate-400 shrink-0">{timeAgo(ts)}</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right panel — messages */}
      {viewMode === "messages" && selected ? (
        <div className="flex flex-col flex-1 bg-slate-50">
          {/* Conv header */}
          <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200">
            <button onClick={() => setSelected(null)} className="md:hidden text-slate-400 hover:text-slate-700">
              <ChevronLeft size={20} />
            </button>
            <ContactAvatar
              name={selected.participant_name || selected.participant || "Unknown"}
              avatar={selected.avatar}
              size={32}
            />
            <div>
              <p className="font-semibold text-slate-800 text-sm">{selected.participant_name || selected.participant}</p>
              <PlatformBadge platform={selected.platform} />
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {loadingMsgs ? (
              <div className="flex items-center justify-center h-40 text-slate-400">
                <Loader2 size={20} className="animate-spin" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-slate-400">No messages</div>
            ) : (
              messages.map(msg => (
                <div key={msg.id} className={`flex ${msg.direction === "out" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[70%] px-3 py-2 rounded-2xl text-sm ${msg.direction === "out" ? "bg-brand-dark text-white rounded-br-sm" : "bg-white text-slate-800 border border-slate-200 rounded-bl-sm shadow-sm"}`}>
                    <p>{msg.content}</p>
                    <p className={`text-xs mt-1 ${msg.direction === "out" ? "text-white italic" : "text-slate-400 italic"}`}>
                      {timeAgo(msg.created_at)}
                    </p>
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Reply box */}
          <div className="bg-white border-t border-slate-200 p-3">
            {facebookReplyWindowClosed && (
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-2 mb-2 space-y-2">
                <p>
                  Facebook 24-hour policy: this thread is outside the standard reply window.
                  Sending uses MESSAGE_TAG + HUMAN_AGENT (deprecated tags were removed by Meta).
                </p>
                <select
                  value={fbTag}
                  onChange={(e) => setFbTag(e.target.value as typeof fbTag)}
                  className="h-8 w-full rounded-md border border-amber-300 bg-white px-2 text-xs text-amber-900"
                >
                  <option value="HUMAN_AGENT">HUMAN_AGENT</option>
                </select>
              </div>
            )}
            {sendResult === "ok" && (
              <p className="text-xs text-green-600 flex items-center gap-1 mb-2"><CheckCircle size={12} /> Message sent</p>
            )}
            {sendResult === "err" && (
              <p className="text-xs text-red-500 flex items-center gap-1 mb-2">
                <XCircle size={12} /> {sendError || "Failed to send. Try again."}
              </p>
            )}
            <div className="flex gap-2 items-end">
              <textarea
                className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand"
                rows={2}
                placeholder={`Reply on ${selected.platform}...`}
                value={reply}
                onChange={e => setReply(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendReply(); } }}
              />
              <button onClick={sendReply} disabled={sending || !reply.trim()}
                className="p-2.5 bg-brand-dark text-white rounded-xl hover:bg-brand disabled:opacity-40 transition-colors">
                {sending ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-1">Enter to send · Shift+Enter for new line</p>
          </div>
        </div>
      ) : viewMode === "comments" && selectedPost ? (
        <div className="flex flex-col flex-1 bg-slate-50">
          <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200">
            <button onClick={() => setSelectedPost(null)} className="md:hidden text-slate-400 hover:text-slate-700">
              <ChevronLeft size={20} />
            </button>
            <div>
              <p className="font-semibold text-slate-800 text-sm truncate max-w-[40rem]">
                {selectedPost.caption || selectedPost.message || selectedPost.text || "Post comments"}
              </p>
              {selectedPost.platform ? <PlatformBadge platform={selectedPost.platform} /> : null}
              <p className="text-[11px] text-slate-500 mt-1">
                {postMetric(selectedPost, "likes", "likeCount", "like_count")} likes ·{" "}
                {postMetric(selectedPost, "shares", "shareCount", "share_count")} shares ·{" "}
                {postMetric(selectedPost, "commentCount", "comments_count")} comments · score {postEngagementScore(selectedPost)}
              </p>
              <p className="text-[11px] text-blue-700 mt-0.5">
                {postPerformanceHint(selectedPost)}
              </p>
              <details className="mt-1">
                <summary className="text-[11px] text-slate-500 cursor-pointer">Debug engagement lookup</summary>
                <pre className="mt-1 text-[10px] leading-4 text-slate-600 bg-slate-100 rounded p-2 overflow-x-auto">
{JSON.stringify(
  engagementDebugByPost[selectedPost.id] || {
    source: "comments/posts-merge",
    message: "No per-post analytics debug entry for this post in current load cycle",
  },
  null,
  2
)}
                </pre>
              </details>
            </div>
          </div>
          <div className="px-4 py-2 border-b border-slate-200 bg-white">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-medium text-slate-600">Comment queue</p>
              <select
                value={commentOrder}
                onChange={(e) => setCommentOrder(e.target.value as "unreplied" | "newest")}
                className="h-7 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
              >
                <option value="unreplied">Unreplied first</option>
                <option value="newest">Newest first</option>
              </select>
            </div>
            <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 p-2.5 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-slate-700">Auto-reply</p>
                <label className="inline-flex items-center gap-1 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={commentAutoReply.enabled}
                    onChange={(e) => {
                      const next = { ...commentAutoReply, enabled: e.target.checked };
                      setCommentAutoReply(next);
                      void saveCommentAutoReply(next);
                    }}
                  />
                  Enabled
                </label>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                <select
                  className="border border-slate-200 rounded-md px-2 py-1 text-xs bg-white"
                  value={commentAutoReply.engine_mode}
                  onChange={(e) => {
                    const next = {
                      ...commentAutoReply,
                      engine_mode: e.target.value as "native_ai_all_posts" | "manychat_per_post" | "hybrid",
                    };
                    setCommentAutoReply(next);
                    void saveCommentAutoReply(next);
                  }}
                >
                  <option value="native_ai_all_posts">Native AI (all posts)</option>
                  <option value="manychat_per_post">ManyChat style (per post)</option>
                  <option value="hybrid">Hybrid (AI + per-post ManyChat)</option>
                </select>
                <label className="inline-flex items-center gap-1 text-[11px] text-slate-600">
                  <input
                    type="checkbox"
                    checked={commentAutoReply.reply_only_unreplied}
                    onChange={(e) => {
                      const next = { ...commentAutoReply, reply_only_unreplied: e.target.checked };
                      setCommentAutoReply(next);
                      void saveCommentAutoReply(next);
                    }}
                  />
                  Unreplied only
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex items-center gap-1 text-[11px] text-slate-600">
                  <input
                    type="checkbox"
                    checked={commentAutoReply.apply_all_posts}
                    onChange={(e) => {
                      const next = { ...commentAutoReply, apply_all_posts: e.target.checked };
                      setCommentAutoReply(next);
                      void saveCommentAutoReply(next);
                    }}
                  />
                  All posts
                </label>
                {selectedPost && commentAutoReply.engine_mode !== "native_ai_all_posts" && !commentAutoReply.apply_all_posts && (
                  <label className="inline-flex items-center gap-1 text-[11px] text-slate-600">
                    <input
                      type="checkbox"
                      checked={selectedPostAutoEnabled}
                      onChange={(e) => {
                        const setIds = new Set(commentAutoReply.manychat_post_ids);
                        if (e.target.checked) setIds.add(selectedPost.id);
                        else setIds.delete(selectedPost.id);
                        const next = { ...commentAutoReply, manychat_post_ids: Array.from(setIds) };
                        setCommentAutoReply(next);
                        void saveCommentAutoReply(next);
                      }}
                    />
                    Enable ManyChat on this post
                  </label>
                )}
              </div>
              {commentAutoReply.engine_mode !== "native_ai_all_posts" ? (
                <>
                  <textarea
                    className="w-full border border-slate-200 rounded-md px-2 py-1 text-xs bg-white"
                    rows={2}
                    value={commentAutoReply.default_message}
                    onChange={(e) => setCommentAutoReply({ ...commentAutoReply, default_message: e.target.value })}
                    onBlur={() => void saveCommentAutoReply(commentAutoReply)}
                    placeholder="ManyChat default message (supports {name})"
                  />
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-1.5">
                    <input
                      className="border border-slate-200 rounded-md px-2 py-1 text-xs bg-white"
                      value={newRuleKeyword}
                      onChange={(e) => setNewRuleKeyword(e.target.value)}
                      placeholder="keyword e.g price"
                    />
                    <input
                      className="md:col-span-2 border border-slate-200 rounded-md px-2 py-1 text-xs bg-white"
                      value={newRuleMessage}
                      onChange={(e) => setNewRuleMessage(e.target.value)}
                      placeholder="reply message (supports {name})"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      className="px-2 py-1 text-[11px] border border-slate-200 rounded-md bg-white hover:bg-slate-100 disabled:opacity-40"
                      disabled={!newRuleKeyword.trim() || !newRuleMessage.trim()}
                      onClick={() => {
                        const next = {
                          ...commentAutoReply,
                          keyword_rules: [
                            ...commentAutoReply.keyword_rules,
                            { keyword: newRuleKeyword.trim(), message: newRuleMessage.trim() },
                          ],
                        };
                        setCommentAutoReply(next);
                        setNewRuleKeyword("");
                        setNewRuleMessage("");
                        void saveCommentAutoReply(next);
                      }}
                    >
                      Add keyword rule
                    </button>
                    {savingCommentAutoReply ? <span className="text-[11px] text-slate-400">Saving...</span> : null}
                  </div>
                  {commentAutoReply.keyword_rules.length > 0 ? (
                    <div className="space-y-1 max-h-24 overflow-y-auto">
                      {commentAutoReply.keyword_rules.map((rule, idx) => (
                        <div key={`${rule.keyword}-${idx}`} className="flex items-center justify-between gap-2 text-[11px] rounded-md bg-white border border-slate-200 px-2 py-1">
                          <span className="text-slate-700 truncate"><b>{rule.keyword}</b>{" -> "}{rule.message}</span>
                          <button
                            type="button"
                            className="text-red-500 hover:text-red-600"
                            onClick={() => {
                              const next = {
                                ...commentAutoReply,
                                keyword_rules: commentAutoReply.keyword_rules.filter((_, i) => i !== idx),
                              };
                              setCommentAutoReply(next);
                              void saveCommentAutoReply(next);
                            }}
                          >
                            remove
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-1.5">
                    <select
                      className="border border-slate-200 rounded-md px-2 py-1 text-xs bg-white"
                      value={newStepType}
                      onChange={(e) => setNewStepType(e.target.value as "text" | "image" | "video" | "file")}
                    >
                      <option value="text">text</option>
                      <option value="image">image</option>
                      <option value="video">video</option>
                      <option value="file">file/pdf</option>
                    </select>
                    <input
                      className="md:col-span-2 border border-slate-200 rounded-md px-2 py-1 text-xs bg-white"
                      value={newStepMessage}
                      onChange={(e) => setNewStepMessage(e.target.value)}
                      placeholder="caption / message"
                    />
                    <input
                      className="md:col-span-2 border border-slate-200 rounded-md px-2 py-1 text-xs bg-white"
                      value={newStepMediaUrl}
                      onChange={(e) => setNewStepMediaUrl(e.target.value)}
                      placeholder="media URL (for image/video/file)"
                    />
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <input
                      type="number"
                      min={0}
                      max={120}
                      className="w-28 border border-slate-200 rounded-md px-2 py-1 text-xs bg-white"
                      value={newStepDelay}
                      onChange={(e) => setNewStepDelay(Number(e.target.value || 0))}
                      placeholder="delay sec"
                    />
                    <button
                      type="button"
                      className="px-2 py-1 text-[11px] border border-slate-200 rounded-md bg-white hover:bg-slate-100 disabled:opacity-40"
                      disabled={newStepType === "text" ? !newStepMessage.trim() : (!newStepMediaUrl.trim() && !newStepMessage.trim())}
                      onClick={() => {
                        const next = {
                          ...commentAutoReply,
                          chain_steps: [
                            ...commentAutoReply.chain_steps,
                            {
                              type: newStepType,
                              message: newStepMessage.trim() || undefined,
                              media_url: newStepMediaUrl.trim() || undefined,
                              delay_seconds: Math.max(0, Math.min(120, Number(newStepDelay || 0))),
                            },
                          ],
                        };
                        setCommentAutoReply(next);
                        setNewStepMessage("");
                        setNewStepMediaUrl("");
                        setNewStepDelay(0);
                        void saveCommentAutoReply(next);
                      }}
                    >
                      Add chain step
                    </button>
                  </div>
                  {commentAutoReply.chain_steps.length > 0 ? (
                    <div className="space-y-1 max-h-24 overflow-y-auto">
                      {commentAutoReply.chain_steps.map((step, idx) => (
                        <div key={`${step.type}-${idx}`} className="flex items-center justify-between gap-2 text-[11px] rounded-md bg-white border border-slate-200 px-2 py-1">
                          <span className="text-slate-700 truncate">
                            <b>{idx + 1}. {step.type}</b>{" "}
                            {step.delay_seconds ? `(${step.delay_seconds}s)` : ""}{" "}
                            {step.message || step.media_url || ""}
                          </span>
                          <button
                            type="button"
                            className="text-red-500 hover:text-red-600"
                            onClick={() => {
                              const next = {
                                ...commentAutoReply,
                                chain_steps: commentAutoReply.chain_steps.filter((_, i) => i !== idx),
                              };
                              setCommentAutoReply(next);
                              void saveCommentAutoReply(next);
                            }}
                          >
                            remove
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="text-[11px] text-slate-500">
                  Native AI mode is active for all posts. Switch to ManyChat style for keyword rules and chain steps.
                </p>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {loadingComments ? (
              <div className="flex items-center justify-center h-40 text-slate-400">
                <Loader2 size={20} className="animate-spin" />
              </div>
            ) : postComments.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-slate-400">No comments found</div>
            ) : (
              orderedPostComments.map((c) => {
                const cid = c.commentId || c.comment_id || c.id;
                const text = c.message || c.text || "";
                const author = c.username || c.author || "User";
                const replies = Number(c.replyCount ?? c.reply_count ?? 0);
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setSelectedCommentId(cid)}
                    className={`w-full text-left rounded-xl border px-3 py-2 ${selectedCommentId === cid ? "border-brand bg-emerald-50/30" : "border-slate-200 bg-white"}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs text-slate-500">{author}</p>
                      <span className={`text-[10px] rounded-full px-1.5 py-0.5 border ${replies > 0 ? "bg-slate-100 text-slate-600 border-slate-200" : "bg-emerald-50 text-emerald-700 border-emerald-200"}`}>
                        {replies > 0 ? `${replies} replies` : "unreplied"}
                      </span>
                    </div>
                    <p className="text-sm text-slate-800 mt-0.5">{text}</p>
                    <p className="text-xs text-slate-400 mt-1">{timeAgo(c.createdAt || c.created_at)}</p>
                  </button>
                );
              })
            )}
          </div>
          <div className="bg-white border-t border-slate-200 p-3">
            {selectedCommentId ? (
              <p className="text-xs text-slate-500 mb-2">
                Replying to selected comment.
              </p>
            ) : null}
            <div className="flex gap-2 items-end">
              <textarea
                className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand"
                rows={2}
                placeholder={selectedCommentId ? "Reply to selected comment..." : "Select a comment first"}
                value={commentReply}
                disabled={!selectedCommentId}
                onChange={(e) => setCommentReply(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void sendCommentReply(); } }}
              />
              <button
                onClick={() => void sendCommentReply()}
                disabled={sendingCommentReply || !selectedCommentId || !commentReply.trim()}
                className="p-2.5 bg-brand-dark text-white rounded-xl hover:bg-brand disabled:opacity-40 transition-colors"
              >
                {sendingCommentReply ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
              </button>
              <button
                type="button"
                onClick={() => {
                  const c = postComments.find((x) => (x.commentId || x.comment_id || x.id) === selectedCommentId);
                  if (!c) return;
                  setCommentReply(buildQuickReplyDraft(c));
                }}
                disabled={!selectedCommentId}
                className="px-3 py-2 text-xs border border-slate-200 rounded-xl text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-40"
              >
                Quick draft
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-1">Select a comment then press Enter to reply</p>
          </div>
        </div>
      ) : (
        <div className="hidden md:flex flex-1 items-center justify-center bg-slate-50">
          <div className="text-center text-slate-400 space-y-2">
            <Inbox size={48} className="mx-auto opacity-20" />
            <p className="text-sm">
              {viewMode === "messages" ? "Select a conversation to read messages" : "Select a post to view comments"}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
