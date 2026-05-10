import type { SeoAuditIssue, SeoBusinessContext, SeoKeyword, BlogPost, ContentCalendarItem } from "@/lib/api";

export type Tab = "overview" | "audit" | "keywords" | "blog" | "calendar" | "agent" | "roi" | "scheduler" | "analytics" | "local" | "social";

export type CalendarWritePayload = { 
  title: string; 
  keywords: string[] 
};

export type DraftStatus = { 
  [title: string]: "generating" | "done" | "error" 
};

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  tool_steps?: Array<{ tool: string }>;
}

export interface SeoMemory {
  audit_history: { date: string; score: number; url: string; critical_issues: string[] }[];
  published_count: number;
  draft_count: number;
  published_topics: { title: string; tags: string[]; keywords: string[] }[];
  score_trend: "improving" | "declining" | "stable";
  analysis: { 
    working: string[]; 
    not_working: string[]; 
    next_month_focus: string[]; 
    score_trend: string 
  };
  kw_months: string[];
}

export interface BusinessData {
  profile: SeoBusinessContext | null;
  summary: any;
  memory: SeoMemory | null;
  posts: BlogPost[];
  keywords: any[];
  lastUpdated: string;
}

export interface PerformanceData {
  contentVelocity: number;
  avgSeoScore: number;
  topPerformingContent: BlogPost[];
  keywordGaps: string[];
  improvementOpportunities: string[];
}

export type { SeoAuditIssue, SeoBusinessContext, SeoKeyword, BlogPost, ContentCalendarItem };
