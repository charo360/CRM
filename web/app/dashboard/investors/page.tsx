"use client";

import TaggedContactDirectory, { DirectoryConfig } from "@/components/TaggedContactDirectory";
import { DocTypeOption } from "@/components/ContactDocumentsPanel";
import { Landmark } from "lucide-react";

const INVESTOR_DOC_TYPES: DocTypeOption[] = [
  { value: "term_sheet", label: "Term sheet" },
  { value: "investment_agreement", label: "Investment agreement" },
  { value: "nda", label: "NDA" },
  { value: "pitch_deck", label: "Pitch deck" },
  { value: "due_diligence", label: "Due diligence" },
  { value: "cap_table", label: "Cap table" },
  { value: "other", label: "Other" },
];

const INVESTOR_CONFIG: DirectoryConfig = {
  apiPrefix: "/investors",
  title: "Investors",
  subtitle: "Track funding conversations, pipeline stages, and investor relationships",
  entityLabel: "Investor",
  icon: Landmark,
  presetTypes: [
    "Angel",
    "VC",
    "Private Equity",
    "Family Office",
    "Crowdfunding",
    "Angel Syndicate",
    "Corporate",
    "Other",
  ],
  typeField: "investor_type",
  typeLabel: "Investor type",
  stages: ["Prospect", "Intro", "Pitch", "Due Diligence", "Term Sheet", "Closed", "Passed"],
  stageField: "investment_stage",
  stageLabel: "Pipeline stage",
  extraFields: [
    { key: "ticket_size", label: "Ticket size", placeholder: "e.g. $50K–$500K" },
    { key: "investor_notes", label: "Notes", placeholder: "Meeting notes, interests, warm intro path…", multiline: true },
  ],
  documentTypes: INVESTOR_DOC_TYPES,
  documentsLabel: "Investment documents",
};

export default function InvestorsPage() {
  return <TaggedContactDirectory config={INVESTOR_CONFIG} />;
}
