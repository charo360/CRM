import React from "react";
import { getIssueTypeStyle } from "@/lib/seo/utils";
import type { SeoAuditIssue } from "@/lib/seo/types";

interface IssuePillProps {
  type: SeoAuditIssue["type"];
}

export function IssuePill({ type }: IssuePillProps) {
  const style = getIssueTypeStyle(type);
  
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase ${style}`}>
      {type}
    </span>
  );
}
