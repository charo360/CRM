import React from "react";
import { getScoreColor, getScoreLabel } from "@/lib/seo/utils";

interface ScoreBadgeProps {
  score: number;
  grade: string;
}

export function ScoreBadge({ score, grade }: ScoreBadgeProps) {
  const color = getScoreColor(score);
  const label = getScoreLabel(score);
  
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${color}`}>
      {label} · {score}/100
    </span>
  );
}
