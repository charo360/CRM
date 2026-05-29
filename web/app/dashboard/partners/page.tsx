"use client";

import TaggedContactDirectory, { DirectoryConfig } from "@/components/TaggedContactDirectory";
import { DocTypeOption } from "@/components/ContactDocumentsPanel";
import { Handshake } from "lucide-react";

const PARTNER_DOC_TYPES: DocTypeOption[] = [
  { value: "partnership_agreement", label: "Partnership agreement" },
  { value: "mou", label: "MOU" },
  { value: "contract", label: "Contract" },
  { value: "sow", label: "Statement of work" },
  { value: "nda", label: "NDA" },
  { value: "referral_agreement", label: "Referral agreement" },
  { value: "other", label: "Other" },
];

const PARTNER_CONFIG: DirectoryConfig = {
  apiPrefix: "/partners",
  title: "Partners",
  subtitle: "Manage strategic, channel, and technology partnerships",
  entityLabel: "Partner",
  icon: Handshake,
  presetTypes: [
    "Strategic",
    "Channel",
    "Technology",
    "Reseller",
    "Affiliate",
    "Distribution",
    "Marketing",
    "Other",
  ],
  typeField: "partner_type",
  typeLabel: "Partner type",
  extraFields: [
    { key: "partnership_terms", label: "Partnership terms", placeholder: "e.g. Revenue share, co-marketing, referral fee" },
    { key: "revenue_share", label: "Revenue share", placeholder: "e.g. 15% referral, 20% rev share" },
  ],
  arrayField: { key: "focus_areas", label: "Focus areas", placeholder: "e.g. East Africa, SaaS, Retail…" },
  showRating: true,
  documentTypes: PARTNER_DOC_TYPES,
  documentsLabel: "Partnership contracts",
};

export default function PartnersPage() {
  return <TaggedContactDirectory config={PARTNER_CONFIG} />;
}
