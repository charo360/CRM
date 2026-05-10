import React from "react";

interface HelpTooltipProps {
  text: string;
}

export function HelpTooltip({ text }: HelpTooltipProps) {
  return (
    <span className="group relative inline-block ml-1">
      <span className="text-slate-400 hover:text-slate-600 cursor-help text-xs">ⓘ</span>
      <span className="invisible group-hover:visible absolute left-0 top-5 z-10 w-48 bg-slate-800 text-white text-xs rounded-lg px-3 py-2 shadow-lg">
        {text}
      </span>
    </span>
  );
}
