"use client";

import { useCallback, useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { api } from "@/lib/api";
import {
  Zap,
  Trash2,
  Loader2,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  MessageCircle,
  Bell,
  UserPlus,
  Wand2,
  Pencil,
  Globe,
  ShoppingBag,
  CreditCard,
  BadgePercent,
  AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { WorkflowEditModal, type WorkflowEditable } from "./workflow-edit-modal";
import { WorkflowFlowDiagram } from "./workflow-flow-diagram";

// ── Types ──────────────────────────────────────────────────────────────────────

interface WorkflowStep {
  id?: string;
  action: string;
  params: Record<string, unknown>;
  delay_minutes?: number;
}

interface WorkflowTrigger {
  type: string;
  condition?: string;
}

interface Workflow {
  id: string;
  name: string;
  description?: string;
  trigger: WorkflowTrigger;
  steps: WorkflowStep[];
  enabled: boolean;
  run_count: number;
  last_run_at?: string;
  created_at: string;
}

interface WorkflowRun {
  id: string;
  workflow_id: string;
  status: string;
  started_at: string;
  finished_at?: string;
  error?: string;
}

interface Capability {
  description: string;
  params: Record<string, { type: string; required: boolean; description: string; default?: unknown }>;
}

interface Meta {
  capabilities: Record<string, Capability>;
  trigger_types: Record<string, { description: string; condition_examples: string[] }>;
}

/** Payload for POST /workflows — matches backend WorkflowCreate */
interface WorkflowCreatePayload {
  name: string;
  description: string;
  trigger: WorkflowTrigger;
  steps: Array<{
    id: string;
    action: string;
    params: Record<string, unknown>;
    delay_minutes?: number;
  }>;
  enabled: boolean;
}

// ── Human-readable labels (engine uses snake_case keys) ───────────────────────

const ACTION_LABELS: Record<string, string> = {
  send_message: "Send message",
  tag_contact: "Add tag to contact",
  assign_owner: "Assign conversation",
  notify_owner: "Notify owner",
  create_followup: "Create follow-up reminder",
  move_pipeline_stage: "Move pipeline stage",
  escalate_to_human: "Escalate to human",
  wait: "Wait",
  if_no_reply: "If no reply",
  shopify_fulfill_order: "Shopify: Fulfill order",
  shopify_create_discount: "Shopify: Create discount",
  shopify_send_recovery: "Shopify: Send recovery message",
  browser_navigate: "Browser: Navigate tab",
  browser_click: "Browser: Click element",
  browser_type: "Browser: Type text",
  browser_scroll: "Browser: Scroll to element",
  browser_extract: "Browser: Extract data",
  create_invoice_draft: "Billing: Create Invoice Draft",
  social_publish_post: "Social: Publish Social Post",
  design_and_publish_post: "AI Design: Generate & Publish Banner",
  run_ai_specialist_agent: "AI Swarm: Run Specialist Agent",
  gmail_send_email: "Gmail: Send customized email",
  linkedin_send_outreach: "Social: Send automated outreach",
  meta_pause_campaign: "Meta Ads: Pause underperforming ad",
  run_funding_scan: "Grants: Scan funding opportunities",
  generate_presentation_deck: "Slides: Compile presentation deck",
  generate_business_forecast: "BI Analytics: Run urgency forecast",
};

function friendlyAction(action: string) {
  return ACTION_LABELS[action] ?? action.replace(/_/g, " ");
}

function sendMessageDestinationLabel(params: Record<string, unknown>) {
  const d = String(params.destination ?? "customer_whatsapp").toLowerCase();
  if (d === "owner_push" || d === "notify_me") return "Push alert to you (no WhatsApp)";
  return "WhatsApp to customer";
}

// ── One-click starters (no AI wait — instant “it works”) ──────────────────────

const QUICK_TEMPLATES: {
  id: string;
  title: string;
  blurb: string;
  icon: LucideIcon;
  aiHint: string;
  payload: WorkflowCreatePayload;
}[] = [
  {
    id: "welcome",
    title: "Welcome every new chat",
    blurb: "Instant reply + tag as new lead",
    icon: MessageCircle,
    aiHint:
      "When anyone messages us, send a friendly welcome and tag them new_lead. Keep the tone warm and short.",
    payload: {
      name: "Welcome new chats",
      description: "Greets new conversations and tags the contact.",
      trigger: { type: "incoming_message", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "send_message",
          params: {
            destination: "customer_whatsapp",
            message:
              "Hi {customer_name}! Thanks for messaging {business_name} — we’re glad you reached out. How can we help you today?",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "tag_contact",
          params: { tag: "new_lead" },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "price",
    title: "Price questions",
    blurb: "Alert you when someone asks pricing",
    icon: Bell,
    aiHint:
      "When a message contains price or cost keywords, notify the business owner with the customer name, then create a follow-up in 24 hours.",
    payload: {
      name: "Price inquiry alert",
      description: "Notifies you when pricing comes up.",
      trigger: { type: "incoming_message", condition: "message_contains('price')" },
      steps: [
        {
          id: "step_1",
          action: "notify_owner",
          params: {
            title: "Pricing question",
            message: "{customer_name} asked about pricing — follow up when you can.",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "create_followup",
          params: {
            note: "Follow up on pricing discussion",
            due_hours: 24,
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "new_customer",
    title: "New customer",
    blurb: "Hello + move to “lead” stage",
    icon: UserPlus,
    aiHint:
      "When a new customer is created, send a short thank-you message and move them to the lead pipeline stage.",
    payload: {
      name: "New customer onboarding",
      description: "Welcomes first-time customers and sets pipeline stage.",
      trigger: { type: "customer_created", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "send_message",
          params: {
            destination: "customer_whatsapp",
            message:
              "Welcome to {business_name}, {customer_name}! We’ve saved your details — reply anytime you need us.",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "move_pipeline_stage",
          params: { stage: "lead" },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "shopify_dropship_procure",
    title: "Auto-order dropshipping",
    blurb: "Auto order via Browser Companion",
    icon: Globe,
    aiHint:
      "When a Shopify order is placed, use the browser companion tab to navigate to the supplier, type the shipping name and details, and extract the supplier order number to notify the owner.",
    payload: {
      name: "Auto dropship procurement",
      description: "Triggers browser companion to place orders on supplier sites.",
      trigger: { type: "shopify_order_created", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "browser_navigate",
          params: {
            url: "https://cjdropshipping.com/buy-now",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "browser_type",
          params: {
            selector: "input[name='shipping_name']",
            text: "{customer_name}",
          },
          delay_minutes: 0,
        },
        {
          id: "step_3",
          action: "browser_extract",
          params: {
            selector: ".supplier-order-id",
            data_type: "text",
          },
          delay_minutes: 0,
        },
        {
          id: "step_4",
          action: "notify_owner",
          params: {
            title: "Dropship order placed",
            message: "Supplier order for {customer_name} placed! Ref: {extracted_text}",
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "payhero_mpesa_confirm",
    title: "M-Pesa payment receipts",
    blurb: "Confirm payments & tag paid customer",
    icon: CreditCard,
    aiHint:
      "When a PayHero M-Pesa payment is received, thank the customer on WhatsApp with the amount, tag them as paid_customer, and mark their pipeline stage as won.",
    payload: {
      name: "M-Pesa auto-receipts",
      description: "Confirms payments received via PayHero and tags the customer.",
      trigger: { type: "payhero_payment_received", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "send_message",
          params: {
            destination: "customer_whatsapp",
            message: "Thank you {customer_name}! We have received your M-Pesa payment of Ksh. {amount}. Your order is now being processed.",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "tag_contact",
          params: { tag: "paid_customer" },
          delay_minutes: 0,
        },
        {
          id: "step_3",
          action: "move_pipeline_stage",
          params: { stage: "won" },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "shopify_abandoned_cart_recovery",
    title: "Cart recovery sequence",
    blurb: "Recover carts & send discount code",
    icon: BadgePercent,
    aiHint:
      "When a Shopify cart is abandoned, auto-create a 10% discount, send an abandoned cart recovery WhatsApp message, wait 24 hours, and send a final follow-up if they have not replied.",
    payload: {
      name: "Cart recovery sequence",
      description: "Recovers abandoned Shopify carts with a custom discount code.",
      trigger: { type: "shopify_abandoned_cart", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "shopify_send_recovery",
          params: {
            message: "Hi {first_name}! We saved your cart. Use code {discount_code} for 10% off: {recovery_url}",
            discount_value: 10,
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "wait",
          params: { hours: 24 },
          delay_minutes: 0,
        },
        {
          id: "step_3",
          action: "if_no_reply",
          params: {},
          delay_minutes: 0,
        },
        {
          id: "step_4",
          action: "send_message",
          params: {
            destination: "customer_whatsapp",
            message: "Hey {first_name}! Just a quick reminder that your 10% discount code {discount_code} is expiring soon. Click here to grab your items: {recovery_url}",
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "shopify_vip_escalation",
    title: "VIP onboarding",
    blurb: "VIP Order alert & human handoff",
    icon: ShoppingBag,
    aiHint:
      "When a high-value Shopify order is created (value > 200), tag them as vip_customer, send a welcome WhatsApp, alert the business owner, and escalate for human care.",
    payload: {
      name: "VIP high-value onboarding",
      description: "Tags, alerts, and escalates high-value shopify customers.",
      trigger: { type: "shopify_order_created", condition: "order_value > 200" },
      steps: [
        {
          id: "step_1",
          action: "tag_contact",
          params: { tag: "vip_customer" },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "send_message",
          params: {
            destination: "customer_whatsapp",
            message: "Hi {customer_name}! Thank you for your VIP order of {order_value}. Our premium preparation team is hand-packaging your items.",
          },
          delay_minutes: 0,
        },
        {
          id: "step_3",
          action: "notify_owner",
          params: {
            title: "VIP Order Alert!",
            message: "VIP Customer {customer_name} placed an order of {order_value}! Please initiate premium package prep.",
          },
          delay_minutes: 0,
        },
        {
          id: "step_4",
          action: "escalate_to_human",
          params: { reason: "VIP onboarding and custom hand-written thank you note requested." },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "shopify_low_stock_sourcing",
    title: "Low stock auto-procure",
    blurb: "Restock alert & browser navigate",
    icon: AlertTriangle,
    aiHint:
      "When a Shopify product's stock drops below 5, send a notification to the business owner, and open the companion browser tab to the supplier inventory management portal.",
    payload: {
      name: "Low stock sourcing flow",
      description: "Alerts low stock and pre-opens supplier portal on the browser companion.",
      trigger: { type: "shopify_low_stock", condition: "quantity < 5" },
      steps: [
        {
          id: "step_1",
          action: "notify_owner",
          params: {
            title: "Low Stock Alert!",
            message: "Product {product_name} is running low (only {quantity} left). Restock immediately.",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "browser_navigate",
          params: { url: "https://cjdropshipping.com/my-products" },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "unified_mpesa_dropship_flow",
    title: "Unified M-Pesa to Dropship",
    blurb: "M-Pesa payment auto-sources items",
    icon: Wand2,
    aiHint:
      "When a PayHero M-Pesa payment is received, thank the customer on WhatsApp, tag them as fully_paid, move them to won, navigate the browser to supplier, fill their details, extract order code, notify owner and schedule follow up.",
    payload: {
      name: "Omnichannel PayHero to CJdropship",
      description: "Complete cross-system pipeline bridging M-Pesa, CRM, Browser Extension, Follow-ups & Notifications.",
      trigger: { type: "payhero_payment_received", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "send_message",
          params: {
            destination: "customer_whatsapp",
            message: "Thanks {customer_name}! Your M-Pesa payment of Ksh. {amount} is confirmed. We are procuring your item right now!",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "tag_contact",
          params: { tag: "fully_paid" },
          delay_minutes: 0,
        },
        {
          id: "step_3",
          action: "move_pipeline_stage",
          params: { stage: "won" },
          delay_minutes: 0,
        },
        {
          id: "step_4",
          action: "browser_navigate",
          params: { url: "https://cjdropshipping.com/buy-now" },
          delay_minutes: 0,
        },
        {
          id: "step_5",
          action: "browser_type",
          params: {
            selector: "input[name='shipping_phone']",
            text: "{phone}",
          },
          delay_minutes: 0,
        },
        {
          id: "step_6",
          action: "browser_extract",
          params: {
            selector: ".supplier-order-id",
            data_type: "text",
          },
          delay_minutes: 0,
        },
        {
          id: "step_7",
          action: "notify_owner",
          params: {
            title: "Dropship order purchased",
            message: "M-Pesa payment of Ksh.{amount} by {customer_name} auto-procured! CJ Ref: {extracted_text}",
          },
          delay_minutes: 0,
        },
        {
          id: "step_8",
          action: "create_followup",
          params: {
            note: "Verify CJ shipment tracking for order {extracted_text} for client {customer_name}",
            due_hours: 48,
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "billing_auto_delivery_flow",
    title: "Onboarding invoice delivery",
    blurb: "Auto-create & send invoice drafts",
    icon: CreditCard,
    aiHint:
      "When a new customer is created, draft an invoice of KES 5000 for setup fees, and send a WhatsApp with the dynamic invoice_url.",
    payload: {
      name: "Onboarding Setup Retainer",
      description: "Auto-creates a setup fee invoice draft and shares it on WhatsApp.",
      trigger: { type: "customer_created", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "create_invoice_draft",
          params: {
            currency: "KES",
            items: [
              { name: "Setup retainer & workspace onboarding configuration", rate: 5000, qty: 1 }
            ],
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "send_message",
          params: {
            destination: "customer_whatsapp",
            message: "Hi {customer_name}! Your onboarding setup retainer is ready. Access the invoice here: {invoice_url}",
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "social_celebrate_invoice_paid",
    title: "Invoice paid social celebrator",
    blurb: "Celebrate invoices paid on socials",
    icon: Sparkles,
    aiHint:
      "When an invoice is paid, publish a celebratory social post welcoming the customer, and push notify the owner.",
    payload: {
      name: "Client welcome celebrator",
      description: "Auto-welcomes paid clients on Facebook and LinkedIn, and triggers owner alert.",
      trigger: { type: "invoice_paid", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "social_publish_post",
          params: {
            message: "We just onboarded a new customer! Shout out to {customer_name} for choosing {business_name}! Let's make great things happen together! 🎉🚀",
            platforms: ["facebook", "linkedin"],
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "notify_owner",
          params: {
            title: "Celebrated on socials!",
            message: "Successfully pushed social celebration post for {customer_name}'s payment of {amount}!",
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "ai_design_and_publish_campaign",
    title: "AI social media campaign",
    blurb: "Design & publish to socials with AI",
    icon: Wand2,
    aiHint:
      "When a Shopify order is marked as fulfilled, use Gemini AI to generate a highly polished custom design graphic celebrating the order, and automatically publish it on Facebook, Instagram, and LinkedIn.",
    payload: {
      name: "Fulfillment celebration campaign",
      description: "Generates an elite Gemini graphic design and publishes it across all active channels.",
      trigger: { type: "shopify_order_fulfilled", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "design_and_publish_post",
          params: {
            headline: "Another order shipped successfully!",
            subtext: "Quality and speed are our brand guarantees. Enjoy premium delivery!",
            cta: "Shop Now",
            brand_color: "#4CD137",
            style: "split horizon",
            product_description: "Premium fulfillment and global dropshipping delivery services.",
            platforms: ["facebook", "instagram", "linkedin"],
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "notify_owner",
          params: {
            title: "AI Post Published",
            message: "Gemini successfully designed and published a congratulations post for your recent fulfillment!",
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "auto_nda_document_generator",
    title: "Autonomous contract generator",
    blurb: "Draft complex agreements autonomously",
    icon: Sparkles,
    aiHint:
      "When a new customer is created, deploy the autonomous Document specialist agent in the background to draft a professional Non-Disclosure Agreement (NDA) customized for them, and deliver the draft on WhatsApp.",
    payload: {
      name: "Autonomous NDA Generation",
      description: "Deploys background agents to generate custom contracts and deliver drafts instantly.",
      trigger: { type: "customer_created", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "run_ai_specialist_agent",
          params: {
            agent_id: "document",
            task_description: "Draft a formal, concise Mutual Non-Disclosure Agreement (NDA) between our business ({business_name}) and customer {customer_name}. Include standard clauses for confidentiality, duration of 2 years, and governing law.",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "send_message",
          params: {
            destination: "customer_whatsapp",
            message: "Hi {customer_name}! We are excited to partner with you. Our Zilo AI Document specialist has automatically drafted our Mutual Non-Disclosure Agreement (NDA) based on your details:\n\n{agent_result}\n\nPlease reply if you need any adjustments!",
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "omnichannel_outreach_campaign",
    title: "Omnichannel lead scout",
    blurb: "Draft & dispatch social cold pitches",
    icon: Wand2,
    aiHint:
      "When a new social lead is discovered on Facebook or LinkedIn, use a background Specialist agent to draft a highly customized, natural initial message, automatically post outreach, and queue a pitch email.",
    payload: {
      name: "Social Lead Auto-Outreach",
      description: "Auto-reaches out to social leads via LinkedIn/Facebook and follows up on email.",
      trigger: { type: "social_lead_discovered", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "run_ai_specialist_agent",
          params: {
            agent_id: "social",
            task_description: "Write a short, engaging, non-salesy initial cold message to the lead {lead_author} who is interested in {keyword}. Reference their post text: '{lead_text}'",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "linkedin_send_outreach",
          params: {
            url: "{url}",
            message: "{agent_result}",
          },
          delay_minutes: 0,
        },
        {
          id: "step_3",
          action: "notify_owner",
          params: {
            title: "Outreach Sent!",
            message: "Sent automated outreach pitch to {lead_author} on social media.",
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
  {
    id: "meta_ads_budget_safeguard",
    title: "Ad budget autopilot safeguard",
    blurb: "Pause wasting ad campaigns instantly",
    icon: Sparkles,
    aiHint:
      "When an ad performance threshold fails or CPC spikes, automatically pause the underperforming Facebook/Instagram campaign and send a mobile push alert.",
    payload: {
      name: "Ads Budget Safeguard",
      description: "Auto-pauses losing Meta ad campaigns and push notifies you.",
      trigger: { type: "meta_ad_health_alert", condition: "always" },
      steps: [
        {
          id: "step_1",
          action: "meta_pause_campaign",
          params: {
            campaign_id: "{campaign_id}",
          },
          delay_minutes: 0,
        },
        {
          id: "step_2",
          action: "notify_owner",
          params: {
            title: "🛑 Meta Ad Paused",
            message: "Ad campaign {campaign_id} was automatically paused due to high CPC / poor return indicators to protect your budget.",
          },
          delay_minutes: 0,
        },
      ],
      enabled: true,
    },
  },
];

const EXAMPLE_PROMPTS = [
  "When someone asks about delivery times, send them our standard hours and tag the chat as shipping.",
  "If a VIP tag is added, notify the owner and create a follow-up for the same day.",
  "When intent is booking, send a message asking for their preferred date and move them to prospect.",
];

const AI_LOADING_LINES = [
  "Understanding what you want…",
  "Choosing the right trigger…",
  "Lining up the steps…",
  "Almost there…",
];

// ── API helpers ────────────────────────────────────────────────────────────────

const workflowsApi = {
  list: () => api.get<Workflow[]>("/workflows"),
  get: (id: string) => api.get<Workflow>(`/workflows/${id}`),
  create: (body: unknown) => api.post<Workflow>("/workflows", body),
  update: (id: string, body: unknown) => api.put<Workflow>(`/workflows/${id}`, body),
  toggle: (id: string) => api.post<{ enabled: boolean }>(`/workflows/${id}/toggle`, {}),
  delete: (id: string) => api.delete<{ deleted: boolean }>(`/workflows/${id}`),
  runs: (id: string) => api.get<WorkflowRun[]>(`/workflows/${id}/runs`),
  meta: () => api.get<Meta>("/workflows/meta/capabilities"),
  build: (description: string) => api.post<Workflow>("/workflows/build/from-description", { description }),
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtDate(iso?: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function TriggerBadge({ trigger }: { trigger: WorkflowTrigger }) {
  const labels: Record<string, string> = {
    incoming_message: "Message received",
    intent_detected: "Intent detected",
    tag_added: "Tag added",
    customer_created: "New customer",
    pipeline_stage_changed: "Stage changed",
    payhero_payment_received: "M-Pesa Paid",
    shopify_order_created: "Shopify Order placed",
    shopify_order_fulfilled: "Shopify Order fulfilled",
    shopify_abandoned_cart: "Shopify Cart abandoned",
    shopify_low_stock: "Shopify Low stock",
    shopify_refund_created: "Shopify Refunded",
    invoice_created: "Invoice Created",
    invoice_paid: "Invoice Paid",
    gmail_email_received: "Email received",
    social_lead_discovered: "Lead discovered",
    meta_ad_health_alert: "Ad health alert",
  };
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-[#009B3A] ring-1 ring-[#009B3A]/20">
      <Zap size={10} className="shrink-0" aria-hidden />
      {labels[trigger.type] ?? trigger.type}
      {trigger.condition && trigger.condition !== "always" && (
        <span className="ml-1 text-[#0a2614]/80">· {trigger.condition}</span>
      )}
    </span>
  );
}

function StatusDot({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${enabled ? "bg-emerald-500" : "bg-slate-300"}`}
    />
  );
}

/** Turns workflow execution on/off (`enabled` in API). When off, triggers do not run. */
function RunsSwitch({
  enabled,
  busy,
  onToggle,
}: {
  enabled: boolean;
  busy: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-center gap-2" title={enabled ? "Runs are on — click to pause" : "Runs are off — click to enable"}>
      <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide hidden sm:inline">
        Runs
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={enabled ? "Turn automation runs off" : "Turn automation runs on"}
        disabled={busy}
        onClick={onToggle}
        className={cn(
          "relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#4CD137] focus-visible:ring-offset-2",
          enabled ? "bg-[#009B3A]" : "bg-slate-300",
          busy && "opacity-60 pointer-events-none"
        )}
      >
        <span
          className={cn(
            "pointer-events-none absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-200 ease-out",
            enabled ? "translate-x-[1.375rem]" : "translate-x-0"
          )}
        />
      </button>
      <span
        className={cn(
          "text-xs font-bold tabular-nums min-w-[1.75rem]",
          enabled ? "text-emerald-600" : "text-slate-400"
        )}
      >
        {enabled ? "On" : "Off"}
      </span>
    </div>
  );
}

// ── Quick-start cards (instant create + optional AI customize) ────────────────

function QuickStartGrid({
  compact,
  busyId,
  onUse,
  onCustomize,
}: {
  compact?: boolean;
  busyId: string | null;
  onUse: (tpl: (typeof QUICK_TEMPLATES)[number]) => void;
  onCustomize: (hint: string) => void;
}) {
  return (
    <div className={compact ? "grid sm:grid-cols-3 gap-2" : "grid sm:grid-cols-3 gap-3"}>
      {QUICK_TEMPLATES.map((tpl) => {
        const Icon = tpl.icon;
        const busy = busyId === tpl.id;
        return (
          <div
            key={tpl.id}
            className={`flex flex-col rounded-xl border border-slate-200 bg-white text-left text-slate-900 ${compact ? "p-3" : "p-4 shadow-sm"}`}
          >
            <div className="mb-2 flex items-start gap-2">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-50 ring-1 ring-[#009B3A]/15">
                <Icon size={18} className="text-[#009B3A]" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className={`font-semibold text-slate-900 ${compact ? "text-xs" : "text-sm"}`}>{tpl.title}</p>
                <p className="text-[11px] text-slate-500 leading-snug mt-0.5">{tpl.blurb}</p>
              </div>
            </div>
            <div className="mt-auto flex flex-col gap-1.5">
              <button
                type="button"
                disabled={busy || busyId !== null}
                onClick={() => onUse(tpl)}
                className="w-full rounded-lg bg-[#009B3A] py-2 text-center text-xs font-medium text-white transition-colors hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-50"
              >
                {busy ? (
                  <span className="inline-flex items-center justify-center gap-1">
                    <Loader2 size={12} className="animate-spin" /> Adding…
                  </span>
                ) : (
                  "Use this"
                )}
              </button>
              <button
                type="button"
                disabled={busy || busyId !== null}
                onClick={() => onCustomize(tpl.aiHint)}
                className="w-full py-1.5 text-center text-xs font-medium text-slate-700 underline-offset-2 hover:text-[#009B3A] hover:underline disabled:opacity-50"
              >
                Tweak with AI instead
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── AI Builder Modal ───────────────────────────────────────────────────────────

function AIBuilderModal({
  onClose,
  onCreated,
  initialDescription = "",
}: {
  onClose: () => void;
  onCreated: (wf: Workflow) => void;
  initialDescription?: string;
}) {
  const [desc, setDesc] = useState(initialDescription);
  const [loading, setLoading] = useState(false);
  const [loadingLine, setLoadingLine] = useState(0);
  /** After a successful build, show flow diagram before closing. */
  const [built, setBuilt] = useState<Workflow | null>(null);

  useEffect(() => {
    setDesc(initialDescription);
  }, [initialDescription]);

  useEffect(() => {
    if (!loading) {
      setLoadingLine(0);
      return;
    }
    const t = window.setInterval(() => {
      setLoadingLine((i) => (i + 1) % AI_LOADING_LINES.length);
    }, 1400);
    return () => clearInterval(t);
  }, [loading]);

  async function handleBuild() {
    if (desc.trim().length < 10) {
      toast.error("Add a sentence or two — what should happen, and when?");
      return;
    }
    setLoading(true);
    try {
      const wf = await workflowsApi.build(desc.trim());
      onCreated(wf);
      setBuilt(wf);
      toast.success(`“${wf.name}” is ready`, {
        description: "Review the map below, then tap Done.",
        duration: 4500,
      });
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to build workflow");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className={cn(
          "w-full rounded-2xl bg-white p-6 shadow-xl",
          built ? "max-w-2xl" : "max-w-lg",
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {built ? (
          <div className="text-slate-900">
            <div className="mb-4 flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50 ring-1 ring-emerald-200">
                <CheckCircle2 size={22} className="text-emerald-600" aria-hidden />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Your automation is ready</h2>
                <p className="mt-0.5 text-sm text-slate-600">
                  <strong className="text-slate-800">{built.name}</strong> is saved and turned on (unless you disabled
                  it on the card). Here is how it runs — expand the card anytime for full step text and run history.
                </p>
              </div>
            </div>
            <WorkflowFlowDiagram trigger={built.trigger} steps={built.steps} />
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => {
                  setBuilt(null);
                  onClose();
                }}
                className="rounded-lg bg-[#009B3A] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#4CD137] hover:text-[#0a2614]"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="mb-3 flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50 ring-1 ring-[#009B3A]/20">
                <Wand2 size={20} className="text-[#009B3A]" aria-hidden />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Describe it in plain English</h2>
                <p className="mt-0.5 text-sm text-slate-600">
                  No rules or menus — say what you want to happen when customers message you. We’ll turn it into steps
                  you can edit anytime.
                </p>
              </div>
            </div>

            <textarea
              className="min-h-[120px] w-full resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-sm leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#4CD137]"
              placeholder='Example: “When someone asks about prices, let me know on my phone and remind me to follow up tomorrow.”'
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              disabled={loading}
            />

            <p className="mb-1.5 mt-3 text-[11px] font-medium uppercase tracking-wide text-slate-500">Try an example</p>
            <div className="flex flex-col gap-1.5">
              {EXAMPLE_PROMPTS.map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  disabled={loading}
                  onClick={() => setDesc(p)}
                  className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs text-slate-800 transition-colors hover:border-[#009B3A]/30 hover:bg-emerald-50/50 disabled:opacity-50"
                >
                  {p}
                </button>
              ))}
            </div>

            {loading && (
              <p className="mt-3 flex items-center gap-2 text-sm text-[#009B3A]">
                <Loader2 size={14} className="shrink-0 animate-spin" aria-hidden />
                <span className="animate-pulse">{AI_LOADING_LINES[loadingLine]}</span>
              </p>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleBuild}
                disabled={loading}
                className="flex items-center gap-2 rounded-lg bg-[#009B3A] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-60"
              >
                {loading ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <Sparkles size={14} aria-hidden />}
                Create automation
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Run History ────────────────────────────────────────────────────────────────

function RunHistory({ workflowId }: { workflowId: string }) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    workflowsApi.runs(workflowId).then(setRuns).catch(() => {}).finally(() => setLoading(false));
  }, [workflowId]);

  if (loading) return <div className="py-4 text-center text-sm text-slate-400"><Loader2 size={14} className="animate-spin inline" /></div>;
  if (!runs.length) return <p className="text-sm text-slate-400 py-2">No runs yet.</p>;

  const icon = (status: string) => {
    if (status === "completed") return <CheckCircle2 size={13} className="text-emerald-500" />;
    if (status === "failed") return <XCircle size={13} className="text-red-400" />;
    return <AlertCircle size={13} className="text-amber-400" />;
  };

  return (
    <div className="space-y-1.5 mt-2">
      {runs.map((r) => (
        <div key={r.id} className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 rounded-lg px-3 py-2">
          {icon(r.status)}
          <span className="capitalize font-medium">{r.status}</span>
          <span className="text-slate-400 ml-auto">{fmtDate(r.started_at)}</span>
          {r.error && <span className="text-red-400 ml-2 truncate max-w-[160px]">{r.error}</span>}
        </div>
      ))}
    </div>
  );
}

// ── Workflow Card ──────────────────────────────────────────────────────────────

function WorkflowCard({
  wf,
  onToggle,
  onDelete,
  onEdit,
}: {
  wf: Workflow;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onEdit: (wf: Workflow) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toggling, setToggling] = useState(false);

  async function handleToggle() {
    setToggling(true);
    await onToggle(wf.id);
    setToggling(false);
  }

  async function handleDelete() {
    if (!confirm(`Delete "${wf.name}"?`)) return;
    setDeleting(true);
    await onDelete(wf.id);
    setDeleting(false);
  }

  return (
    <div className={`bg-white rounded-xl border ${wf.enabled ? "border-slate-200" : "border-slate-100"} shadow-sm`}>
      <div className="flex items-start gap-3 p-4">
        <StatusDot enabled={wf.enabled} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm text-slate-800">{wf.name}</span>
            <TriggerBadge trigger={wf.trigger} />
          </div>
          {wf.description && (
            <p className="text-xs text-slate-500 mt-0.5 truncate">{wf.description}</p>
          )}
          <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-400">
            <span className="flex items-center gap-1"><Play size={10} /> {wf.run_count} runs</span>
            {wf.last_run_at && (
              <span className="flex items-center gap-1"><Clock size={10} /> {fmtDate(wf.last_run_at)}</span>
            )}
            <span>{wf.steps.length} step{wf.steps.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onEdit(wf)}
            title="Edit messages & destination"
            className="p-1.5 rounded-lg hover:bg-brand/10 text-slate-400 hover:text-brand-dark transition-colors"
          >
            <Pencil size={14} />
          </button>
          <RunsSwitch enabled={wf.enabled} busy={toggling} onToggle={handleToggle} />
          <button
            onClick={handleDelete}
            disabled={deleting}
            title="Delete"
            className="p-1.5 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors"
          >
            {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
          </button>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 transition-colors"
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="space-y-4 border-t border-slate-100 px-4 pb-4 pt-3">
          <WorkflowFlowDiagram trigger={wf.trigger} steps={wf.steps} />

          {/* Steps */}
          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">Step details</p>
            <div className="space-y-1.5">
              {wf.steps.map((step, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <span className="w-5 h-5 rounded-full bg-brand/10 text-brand-dark flex items-center justify-center font-semibold shrink-0 text-[10px]">
                    {i + 1}
                  </span>
                  <div className="min-w-0">
                    <span className="font-medium text-slate-700">{friendlyAction(step.action)}</span>
                    {step.action === "send_message" && (
                      <span className="ml-2 text-[10px] text-brand-dark font-medium">
                        · {sendMessageDestinationLabel(step.params)}
                      </span>
                    )}
                    {step.action === "send_message" && step.params.message != null && (
                      <p className="text-slate-500 mt-1 whitespace-pre-wrap break-words">
                        {String(step.params.message)}
                      </p>
                    )}
                    {step.action !== "send_message" &&
                      Object.entries(step.params).map(([k, v]) => (
                        <span key={k} className="ml-2 text-slate-400">
                          {k}: <span className="text-slate-600">{String(v)}</span>
                        </span>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Run history */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-1">Recent runs</p>
            <RunHistory workflowId={wf.id} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAI, setShowAI] = useState(false);
  const [aiSeed, setAiSeed] = useState("");
  const [templateBusy, setTemplateBusy] = useState<string | null>(null);
  const [editWf, setEditWf] = useState<Workflow | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await workflowsApi.list();
      setWorkflows(data);
    } catch {
      toast.error("Failed to load workflows");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleToggle(id: string) {
    try {
      const res = await workflowsApi.toggle(id);
      setWorkflows((prev) =>
        prev.map((w) => (w.id === id ? { ...w, enabled: res.enabled } : w))
      );
    } catch {
      toast.error("Failed to toggle workflow");
    }
  }

  async function handleDelete(id: string) {
    try {
      await workflowsApi.delete(id);
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
      toast.success("Workflow deleted");
    } catch {
      toast.error("Failed to delete workflow");
    }
  }

  /** Adds the workflow to the list; modal stays open until the user finishes the success step. */
  function handleCreated(wf: Workflow) {
    setWorkflows((prev) => [wf, ...prev]);
  }

  async function handleUseTemplate(tpl: (typeof QUICK_TEMPLATES)[number]) {
    setTemplateBusy(tpl.id);
    try {
      const wf = await workflowsApi.create(tpl.payload);
      setWorkflows((prev) => [wf, ...prev]);
      toast.success(`“${wf.name}” is ready`, {
        description:
          "It’s turned on — new chats will follow these steps automatically. Expand the card anytime to review or pause.",
        duration: 5500,
      });
    } catch {
      toast.error("Couldn’t create that automation. Check your connection and try again.");
    } finally {
      setTemplateBusy(null);
    }
  }

  function openDescribeModal(seed: string) {
    setAiSeed(seed);
    setShowAI(true);
  }

  const active = workflows.filter((w) => w.enabled).length;

  return (
    <div className="mx-auto w-full max--3xl p-6 text-slate-900">
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-slate-900">
            <Zap size={20} className="text-[#4CD137]" aria-hidden />
            Automations
          </h1>
          <p className="text-sm text-slate-500 mt-0.5 max-w-md">
            Set up once — welcome messages, alerts, and follow-ups run on WhatsApp without you doing the same
            thing twice.
          </p>
          {!loading && (
            <p className="text-xs text-slate-400 mt-1">
              {workflows.length} workflow{workflows.length !== 1 ? "s" : ""} · {active} active
            </p>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            type="button"
            onClick={() => openDescribeModal("")}
            className="flex items-center gap-2 rounded-lg bg-[#009B3A] px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#4CD137] hover:text-[#0a2614]"
          >
            <Sparkles size={14} aria-hidden />
            Describe with AI
          </button>
        </div>
      </div>

      {/* Empty state */}
      {!loading && workflows.length === 0 && (
        <div className="space-y-8 pb-12">
          <div className="rounded-2xl border border-brand/15 bg-gradient-to-br from-brand/10 to-white px-5 py-8 sm:px-8">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-dark mb-2">Get started</p>
            <h2 className="text-lg sm:text-xl font-bold text-slate-800 mb-2">Pick a ready-made automation</h2>
            <p className="text-sm text-slate-600 mb-6 max-w-lg">
              One click and you’re done — no typing required. Or use your own words and we’ll build the steps for
              you.
            </p>
            <QuickStartGrid
              busyId={templateBusy}
              onUse={handleUseTemplate}
              onCustomize={(hint) => openDescribeModal(hint)}
            />
            <div className="relative my-8">
              <div className="absolute inset-0 flex items-center" aria-hidden>
                <div className="w-full border-t border-slate-200" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-white px-3 text-slate-400">or describe your own</span>
              </div>
            </div>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => openDescribeModal("")}
                className="inline-flex items-center gap-2 rounded-xl bg-[#009B3A] px-5 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-[#4CD137] hover:text-[#0a2614]"
              >
                <Wand2 size={16} aria-hidden />
                Describe with AI
              </button>
              <p className="text-xs text-slate-500 text-center sm:text-left">
                Tip: tap an example inside — you can edit before creating.
              </p>
            </div>
          </div>

          <div className="grid sm:grid-cols-3 gap-4 text-center sm:text-left">
            <div className="rounded-xl bg-slate-50 border border-slate-100 p-4">
              <p className="text-xs font-bold text-brand-dark mb-1">1</p>
              <p className="text-sm font-medium text-slate-800">Choose or describe</p>
              <p className="text-xs text-slate-500 mt-1">Use a template or one sentence in plain English.</p>
            </div>
            <div className="rounded-xl bg-slate-50 border border-slate-100 p-4">
              <p className="text-xs font-bold text-brand-dark mb-1">2</p>
              <p className="text-sm font-medium text-slate-800">We create the steps</p>
              <p className="text-xs text-slate-500 mt-1">Triggers, messages, tags — visible on the card.</p>
            </div>
            <div className="rounded-xl bg-slate-50 border border-slate-100 p-4">
              <p className="text-xs font-bold text-brand-dark mb-1">3</p>
              <p className="text-sm font-medium text-slate-800">It runs automatically</p>
              <p className="text-xs text-slate-500 mt-1">Toggle off anytime — you stay in control.</p>
            </div>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20 text-slate-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}

      {/* Quick add (when user already has workflows) */}
      {!loading && workflows.length > 0 && (
        <div className="mb-5 rounded-2xl border border-slate-200 bg-slate-50/90 p-4">
          <p className="text-xs font-semibold text-slate-600 mb-3">Add another in seconds</p>
          <QuickStartGrid
            compact
            busyId={templateBusy}
            onUse={handleUseTemplate}
            onCustomize={(hint) => openDescribeModal(hint)}
          />
        </div>
      )}

      {/* List */}
      {!loading && workflows.length > 0 && (
        <div className="space-y-3">
          {workflows.map((wf) => (
            <WorkflowCard
              key={wf.id}
              wf={wf}
              onToggle={handleToggle}
              onDelete={handleDelete}
              onEdit={(w) => setEditWf(w)}
            />
          ))}
        </div>
      )}

      {/* AI Modal */}
      {showAI && (
        <AIBuilderModal
          key={aiSeed}
          initialDescription={aiSeed}
          onClose={() => {
            setShowAI(false);
            setAiSeed("");
          }}
          onCreated={handleCreated}
        />
      )}

      <WorkflowEditModal
        workflow={editWf as WorkflowEditable | null}
        open={!!editWf}
        onClose={() => setEditWf(null)}
        onSaved={(updated) => {
          setWorkflows((prev) =>
            prev.map((w) => (w.id === updated.id ? ({ ...w, ...updated } as Workflow) : w))
          );
        }}
      />
    </div>
  );
}
