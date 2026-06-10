"use client";

/**
 * BlogRenderer — reliable markdown → styled JSX without react-markdown.
 * Works with React 19 + Next.js 16 without any external parser dependency.
 */

import React from "react";

// ── Gradient palettes per template ────────────────────────────────────────────

const TEMPLATE_GRADIENTS: Record<string, { from: string; to: string; accent: string }> = {
  "how-to":     { from: "#3b82f6", to: "#6366f1", accent: "#818cf8" },
  "listicle":   { from: "#10b981", to: "#059669", accent: "#34d399" },
  "case-study": { from: "#f59e0b", to: "#ef4444", accent: "#fbbf24" },
  "local":      { from: "#0f172a", to: "#1e3a5f", accent: "#38bdf8" },
  "educational":{ from: "#7c3aed", to: "#4f46e5", accent: "#a78bfa" },
  "comparison": { from: "#db2777", to: "#9333ea", accent: "#f472b6" },
  default:      { from: "#1e293b", to: "#334155", accent: "#94a3b8" },
};

const TEMPLATE_LABELS: Record<string, string> = {
  "how-to": "🔧 How-to Guide",
  "listicle": "📋 Top 5 List",
  "case-study": "⭐ Success Story",
  "local": "📍 Local Authority",
  "educational": "🎓 Deep Dive",
  "comparison": "⚖️ Comparison",
};

// ── Inline formatting ──────────────────────────────────────────────────────────

function renderInline(text: string, key: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  // Bold + italic
  const re = /(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[2]) parts.push(<strong key={`${key}-bi-${i}`}><em>{m[2]}</em></strong>);
    else if (m[3]) parts.push(<strong key={`${key}-b-${i}`}>{m[3]}</strong>);
    else if (m[4]) parts.push(<em key={`${key}-i-${i}`}>{m[4]}</em>);
    else if (m[5]) parts.push(<code key={`${key}-c-${i}`} className="bg-slate-100 text-emerald-700 text-xs px-1.5 py-0.5 rounded font-mono">{m[5]}</code>);
    last = re.lastIndex;
    i++;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : <>{parts}</>;
}

// ── Main markdown → JSX converter ─────────────────────────────────────────────

function parseMarkdown(md: string): React.ReactNode[] {
  const lines = md.split("\n");
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const k = `ln-${i}`;

    // META lines — strip from visible output (SEO metadata, not reader content)
    if (/^\*{0,2}(META_TITLE|META_DESC|TAGS)\*{0,2}:/.test(line.trim())) { i++; continue; }

    // H1 — skip (shown as article title above)
    if (/^# /.test(line)) { i++; continue; }

    // H2
    if (/^## /.test(line)) {
      nodes.push(
        <h2 key={k} className="text-lg font-bold text-slate-900 mt-8 mb-3 pb-2 border-b border-slate-100">
          {renderInline(line.slice(3), k)}
        </h2>
      );
      i++; continue;
    }

    // H3
    if (/^### /.test(line)) {
      nodes.push(
        <h3 key={k} className="text-base font-semibold text-slate-800 mt-6 mb-2">
          {renderInline(line.slice(4), k)}
        </h3>
      );
      i++; continue;
    }

    // H4
    if (/^#### /.test(line)) {
      nodes.push(
        <h4 key={k} className="text-sm font-semibold text-slate-700 mt-5 mb-1.5 uppercase tracking-wide">
          {renderInline(line.slice(5), k)}
        </h4>
      );
      i++; continue;
    }

    // Unordered list block
    if (/^[*\-] /.test(line)) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && /^[*\-] /.test(lines[i])) {
        items.push(
          <li key={`${k}-li-${i}`} className="text-sm text-slate-700 leading-relaxed">
            {renderInline(lines[i].slice(2), `${k}-li-${i}`)}
          </li>
        );
        i++;
      }
      nodes.push(<ul key={k} className="list-disc list-inside space-y-1.5 my-4 pl-1">{items}</ul>);
      continue;
    }

    // Ordered list block
    if (/^\d+\. /.test(line)) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        const text = lines[i].replace(/^\d+\. /, "");
        items.push(
          <li key={`${k}-oli-${i}`} className="text-sm text-slate-700 leading-relaxed">
            {renderInline(text, `${k}-oli-${i}`)}
          </li>
        );
        i++;
      }
      nodes.push(<ol key={k} className="list-decimal list-inside space-y-1.5 my-4 pl-1">{items}</ol>);
      continue;
    }

    // Blockquote
    if (/^> /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^> /.test(lines[i])) {
        items.push(lines[i].slice(2));
        i++;
      }
      nodes.push(
        <blockquote key={k} className="border-l-4 border-emerald-400 bg-emerald-50/60 pl-4 pr-3 py-3 my-4 rounded-r-xl text-sm text-slate-700 italic">
          {items.map((t, ii) => <p key={ii}>{renderInline(t, `${k}-bq-${ii}`)}</p>)}
        </blockquote>
      );
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      nodes.push(<hr key={k} className="my-6 border-slate-100" />);
      i++; continue;
    }

    // Markdown table — lines starting with |
    if (/^\|/.test(line)) {
      const tableLines: string[] = [];
      while (i < lines.length && /^\|/.test(lines[i].trim())) {
        tableLines.push(lines[i]);
        i++;
      }
      if (tableLines.length >= 2) {
        const parseRow = (row: string) =>
          row.split("|").map(c => c.trim()).filter((_, ci, arr) => ci > 0 && ci < arr.length - 1);
        const headerCells = parseRow(tableLines[0]);
        // tableLines[1] is the separator row — skip it
        const bodyRows = tableLines.slice(2).map(parseRow);
        nodes.push(
          <div key={k} className="my-6 overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-slate-800 text-white">
                  {headerCells.map((cell, ci) => (
                    <th key={ci} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide whitespace-nowrap">
                      {renderInline(cell, `${k}-th-${ci}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bodyRows.map((row, ri) => (
                  <tr key={ri} className={ri % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                    {row.map((cell, ci) => (
                      <td key={ci} className="px-4 py-2.5 text-slate-700 border-t border-slate-100">
                        {renderInline(cell, `${k}-td-${ri}-${ci}`)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      continue;
    }

    // Blank line — skip
    if (line.trim() === "") { i++; continue; }

    // Paragraph — collect consecutive non-special lines
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^#{1,4} /.test(lines[i]) &&
      !/^[*\-] /.test(lines[i]) &&
      !/^\d+\. /.test(lines[i]) &&
      !/^> /.test(lines[i]) &&
      !/^---+$/.test(lines[i].trim()) &&
      !/^\|/.test(lines[i].trim())
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length) {
      nodes.push(
        <p key={k} className="text-sm text-slate-700 leading-7 mb-4">
          {paraLines.map((pl, pi) => (
            <React.Fragment key={pi}>
              {renderInline(pl, `${k}-p-${pi}`)}
              {pi < paraLines.length - 1 && <br />}
            </React.Fragment>
          ))}
        </p>
      );
    }
  }

  return nodes;
}

// ── Hero gradient banner ───────────────────────────────────────────────────────

function HeroBanner({
  title,
  templateId,
  wordCount,
  tags,
}: {
  title: string;
  templateId?: string;
  wordCount?: number;
  tags?: string[];
}) {
  const g = TEMPLATE_GRADIENTS[templateId ?? "default"] ?? TEMPLATE_GRADIENTS.default;
  const readMins = wordCount ? Math.max(1, Math.round(wordCount / 200)) : null;
  const label = TEMPLATE_LABELS[templateId ?? ""] || null;

  return (
    <div
      className="w-full rounded-t-xl sm:rounded-t-2xl overflow-hidden relative"
      style={{ background: `linear-gradient(135deg, ${g.from} 0%, ${g.to} 100%)` }}
    >
      {/* Decorative circles */}
      <div
        className="absolute top-0 right-0 w-48 h-48 rounded-full opacity-10"
        style={{ background: g.accent, transform: "translate(30%, -30%)" }}
      />
      <div
        className="absolute bottom-0 left-0 w-32 h-32 rounded-full opacity-10"
        style={{ background: g.accent, transform: "translate(-30%, 30%)" }}
      />

      <div className="relative px-6 py-8 sm:px-8 sm:py-10">
        {label && (
          <span className="inline-block mb-3 text-[11px] font-semibold uppercase tracking-widest rounded-full px-3 py-1 text-white/90"
            style={{ background: "rgba(255,255,255,0.15)" }}>
            {label}
          </span>
        )}
        <h1 className="text-xl sm:text-2xl font-bold text-white leading-snug max-w-2xl">
          {title.replace(/^#+\s*/, "")}
        </h1>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          {readMins && (
            <span className="text-xs text-white/70 flex items-center gap-1">
              ⏱ {readMins} min read
            </span>
          )}
          {wordCount && (
            <span className="text-xs text-white/70">{wordCount.toLocaleString()} words</span>
          )}
          {(tags ?? []).slice(0, 3).map(t => (
            <span key={t} className="text-[10px] px-2.5 py-1 rounded-full font-medium text-white/80"
              style={{ background: "rgba(255,255,255,0.15)" }}>
              {t.replace(/\*+/g, "").trim()}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Public component ───────────────────────────────────────────────────────────

export interface BlogRendererProps {
  title: string;
  content: string;
  templateId?: string;
  wordCount?: number;
  tags?: string[];
  keywords?: string[];
  metaTitle?: string;
  metaDescription?: string;
  /** If provided, show as "Published at" link */
  publishedUrl?: string;
}

export default function BlogRenderer({
  title,
  content,
  templateId,
  wordCount,
  tags,
  keywords: _keywords,
  metaTitle,
  metaDescription,
  publishedUrl,
}: BlogRendererProps) {
  const nodes = parseMarkdown(content);

  return (
    <article className="bg-white rounded-xl sm:rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
      <HeroBanner
        title={title}
        templateId={templateId}
        wordCount={wordCount}
        tags={tags}
      />

      {/* Published link only — SEO title/description are backend metadata, not shown to readers */}
      {publishedUrl && (
        <div className="px-6 py-3 bg-slate-50 border-b border-slate-100">
          <a href={publishedUrl} target="_blank" rel="noopener noreferrer"
            className="text-xs text-emerald-600 font-medium flex items-center gap-1 hover:underline">
            ✓ Live on your website →
          </a>
        </div>
      )}

      {/* Article body */}
      <div className="px-6 sm:px-8 py-6 max-w-3xl">
        {/* Hidden SEO metadata — invisible to users, readable by Google */}
        {(metaTitle || metaDescription) && (
          <div aria-hidden="true" style={{ display: "none" }}>
            {metaTitle && <span itemProp="name">{metaTitle.replace(/\*+/g, "").trim()}</span>}
            {metaDescription && <span itemProp="description">{metaDescription.replace(/\*+/g, "").trim()}</span>}
          </div>
        )}
        {nodes}
      </div>
    </article>
  );
}
