"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Inbox, RefreshCw, Search, Send, Sparkles, X, ChevronLeft,
  Loader2, Mail, MailOpen, Clock, Bot, ToggleLeft, ToggleRight,
  Star, Reply, Pencil, AlertCircle,
  Tag, Plus, UserCheck, Cpu, Trash2, Brain, ChevronUp,
} from "lucide-react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

type Thread = {
  id: string;
  subject: string;
  from: string;
  to?: string;
  date: string;
  snippet: string;
  body?: string;
  messages?: Message[];
  unread: boolean;
  messageCount: number;
  provider: "gmail" | "microsoft";
  starred?: boolean;
};

type Message = {
  id: string;
  from: string;
  to: string;
  subject: string;
  date: string;
  body: string;
  unread: boolean;
};

type AutoreplyTarget = {
  id: string;   // category id OR email address
  type: "category" | "sender";
  label: string;
  tone: "professional" | "friendly" | "concise";
  context: string; // newline-separated chips
};

type AutoreplyRule = {
  enabled: boolean;
  targets: AutoreplyTarget[];
};

type Category = {
  id: string;
  name: string;
  colorBg: string;
  colorText: string;
  mode: "ai" | "vip";
  description?: string;
  addresses?: string[];
};

type ThreadSummary = {
  threadId: string;
  summary: string;
  messageCount: number;
  generatedAt: string;
};

type Tab = "all" | "unread" | "starred" | string;

// ── API helpers ───────────────────────────────────────────────────────────────

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {} as Record<string, string>;
}

async function apiGet(path: string) {
  const res = await fetch(path, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(path: string, body: unknown) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function buildRaw(opts: { to: string; subject: string; body: string; inReplyTo?: string }) {
  const lines = [
    `To: ${opts.to}`,
    `Subject: ${opts.subject}`,
    `Content-Type: text/plain; charset="UTF-8"`,
    `MIME-Version: 1.0`,
    ...(opts.inReplyTo ? [`In-Reply-To: ${opts.inReplyTo}`, `References: ${opts.inReplyTo}`] : []),
    "",
    opts.body,
  ];
  const bytes = new TextEncoder().encode(lines.join("\r\n"));
  return btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(""))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function formatDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (diffDays === 0) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diffDays < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function stripHtml(html: string) {
  if (typeof document !== "undefined") {
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    return tmp.textContent ?? tmp.innerText ?? "";
  }
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

/** Remove inline CID image references that browsers can't load from HTML emails */
function sanitizeEmailHtml(html: string): string {
  return html
    .replace(/src="cid:[^"]*"/gi, 'src="" style="display:none"')
    .replace(/src='cid:[^']*'/gi, "src='' style='display:none'");
}

/**
 * Strip quoted reply content from an email body so only the new message shows.
 * Handles Gmail/Outlook inline quotes and "> " style quoting.
 */
function stripQuotedReply(raw: string): string {
  if (!raw) return raw;

  // ── HTML emails ──────────────────────────────────────────────────────────────
  if (raw.includes("<")) {
    const cleaned = raw
      .replace(/<blockquote[^>]*>[\s\S]*?<\/blockquote>/gi, "")
      .replace(/<div[^>]*class="[^"]*gmail_quote[^"]*"[^>]*>[\s\S]*/gi, "")
      .replace(/<div[^>]*id="[^"]*appendonsend[^"]*"[^>]*>[\s\S]*/gi, "")
      .replace(/(<br\s*\/?>\s*)+$/gi, "")
      .trim();
    return cleaned || raw;
  }

  // ── Plain text ───────────────────────────────────────────────────────────────
  let text = raw;

  // Gmail: "On Mon, Jan 1, 2026, 9:00 PM Name <email> wrote:" — may be inline
  // This pattern is specific enough (requires a 4-digit year + "wrote:") to avoid false cuts
  text = text.replace(
    /\s*On [A-Za-z]{2,9},?\s+[A-Za-z]{2,9}\.?\s+\d{1,2},?\s+\d{4}[\s\S]*?wrote:\s*/i,
    ""
  ).trim();

  // Outlook / other clients
  text = text.replace(/\s*-{3,}\s*original message\s*-{3,}[\s\S]*/i, "").trim();
  text = text.replace(/\s*_{5,}[\s\S]*/i, "").trim();

  // Strip "> " quoted lines (may appear after the separator is cut)
  text = text
    .split("\n")
    .filter(l => !l.trim().startsWith(">"))
    .join("\n")
    .trim();

  // Fallback: return original if we stripped everything accidentally
  return text || raw.split("\n")[0].trim();
}

function initials(from: string) {
  const name = from.split("<")[0].trim() || from;
  return name.split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2) || "?";
}

const AVATAR_COLORS = [
  "bg-brand-dark", "bg-emerald-500", "bg-blue-500", "bg-amber-500",
  "bg-rose-500", "bg-cyan-500", "bg-pink-500", "bg-orange-500",
];
function avatarColor(from: string) {
  let h = 0;
  for (let i = 0; i < from.length; i++) h = (h * 31 + from.charCodeAt(i)) & 0xffffffff;
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}

const CAT_COLORS = [
  { bg: "bg-purple-500",  text: "text-purple-600",  label: "Purple" },
  { bg: "bg-blue-500",    text: "text-blue-600",    label: "Blue"   },
  { bg: "bg-emerald-500", text: "text-emerald-600", label: "Green"  },
  { bg: "bg-orange-500",  text: "text-orange-600",  label: "Orange" },
  { bg: "bg-pink-500",    text: "text-pink-600",    label: "Pink"   },
  { bg: "bg-rose-500",    text: "text-rose-600",    label: "Red"    },
  { bg: "bg-amber-500",   text: "text-amber-600",   label: "Yellow" },
  { bg: "bg-cyan-500",    text: "text-cyan-600",    label: "Cyan"   },
];

function extractEmail(from: string): string {
  const m = from.match(/<([^>]+)>/);
  return m ? m[1] : from.trim();
}

// ── No-connection state ───────────────────────────────────────────────────────

function NoConnection({ inline = false }: { inline?: boolean }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-4 text-center px-8", inline ? "h-full" : "py-16")}>
      <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center">
        <Mail size={26} className="text-slate-400" />
      </div>
      <div>
        <p className="font-semibold text-slate-700 text-sm">No email connected</p>
        <p className="text-xs text-slate-500 mt-1 leading-relaxed">
          Connect Gmail or Outlook in{" "}
          <a href="/dashboard/integrations" className="text-brand-dark underline underline-offset-2">
            Integrations
          </a>{" "}
          to unlock your inbox.
        </p>
      </div>
    </div>
  );
}

// ── Auto-reply panel ──────────────────────────────────────────────────────────

function AutoreplyPanel({
  autoreply,
  categories,
  onSave,
}: {
  autoreply: AutoreplyRule;
  categories: Category[];
  onSave: (r: AutoreplyRule) => void;
}) {
  const [showAdd, setShowAdd] = useState(false);
  const [showSenderInput, setShowSenderInput] = useState(false);
  const [senderInput, setSenderInput] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editTone, setEditTone] = useState<"professional" | "friendly" | "concise">("professional");
  const [editContext, setEditContext] = useState("");
  const [editInput, setEditInput] = useState("");

  const targets = autoreply.targets ?? [];
  const usedCatIds = targets.filter((t) => t.type === "category").map((t) => t.id);
  const availableCats = categories.filter((c) => !usedCatIds.includes(c.id));

  function addCategoryTarget(cat: Category) {
    onSave({ ...autoreply, targets: [...targets, { id: cat.id, type: "category", label: cat.name, tone: "professional", context: "" }] });
    setShowAdd(false);
  }

  function addSenderTarget() {
    const email = senderInput.trim();
    if (!email || !email.includes("@")) { toast.error("Enter a valid email"); return; }
    if (targets.find((t) => t.id.toLowerCase() === email.toLowerCase())) { toast.error("Already added"); return; }
    onSave({ ...autoreply, targets: [...targets, { id: email, type: "sender", label: email, tone: "professional", context: "" }] });
    setSenderInput(""); setShowSenderInput(false); setShowAdd(false);
  }

  function removeTarget(id: string) {
    onSave({ ...autoreply, targets: targets.filter((t) => t.id !== id) });
    if (expandedId === id) setExpandedId(null);
  }

  function startEdit(target: AutoreplyTarget) {
    setExpandedId(target.id); setEditTone(target.tone); setEditContext(target.context); setEditInput("");
  }

  function saveEdit(id: string) {
    onSave({ ...autoreply, targets: targets.map((t) => t.id === id ? { ...t, tone: editTone, context: editContext } : t) });
    setExpandedId(null);
  }

  const editItems = editContext ? editContext.split("\n").map((s) => s.trim()).filter(Boolean) : [];

  return (
    <div className="flex flex-col h-full p-4 space-y-3 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Bot size={13} className="text-brand-dark" />
        <span className="text-xs font-semibold text-slate-800">Auto-reply</span>
        <span className="ml-auto text-[10px] text-emerald-700 font-medium bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">Live</span>
      </div>

      <p className="text-[11px] text-slate-500 leading-relaxed">
        Replies only to selected categories or specific senders — not everyone.
      </p>

      {/* Target list */}
      {targets.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 py-5 text-center">
          <p className="text-[11px] text-slate-400">No targets yet.<br />Add a category or sender below.</p>
        </div>
      )}

      <div className="space-y-2">
        {targets.map((target) => {
          const cat = categories.find((c) => c.id === target.id);
          const isExpanded = expandedId === target.id;
          const chips = target.context ? target.context.split("\n").filter(Boolean) : [];
          return (
            <div key={target.id} className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
              {/* Target header row */}
              <div className="flex items-center gap-2 px-3 py-2">
                {cat ? <div className={cn("w-2 h-2 rounded-full shrink-0", cat.colorBg)} /> : <UserCheck size={10} className="text-slate-400 shrink-0" />}
                <span className="text-[11px] font-semibold text-slate-700 flex-1 truncate">{target.label}</span>
                <button onClick={() => isExpanded ? setExpandedId(null) : startEdit(target)} className="p-0.5 text-slate-400 hover:text-brand-dark transition-colors">
                  <Pencil size={9} />
                </button>
                <button onClick={() => removeTarget(target.id)} className="p-0.5 text-slate-400 hover:text-rose-500 transition-colors">
                  <X size={9} />
                </button>
              </div>
              {/* Inline tone selector — always visible */}
              <div className="px-3 pb-2 flex gap-1">
                {(["professional", "friendly", "concise"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => onSave({ ...autoreply, targets: targets.map((tg) => tg.id === target.id ? { ...tg, tone: t } : tg) })}
                    className={cn(
                      "text-[9px] px-2 py-0.5 rounded-full capitalize font-medium transition-colors",
                      target.tone === t ? "bg-brand-dark text-white" : "bg-white border border-slate-200 text-slate-500 hover:bg-slate-100"
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>
              {/* Context chips preview */}
              {!isExpanded && chips.length > 0 && (
                <div className="px-3 pb-2 flex flex-wrap gap-1">
                  {chips.map((c, i) => <span key={i} className="text-[9px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-full">{c}</span>)}
                </div>
              )}
              {/* Expanded context editor */}
              {isExpanded && (
                <div className="px-3 pb-3 space-y-2 border-t border-slate-200 pt-2">
                  <p className="text-[9px] text-slate-400 font-semibold uppercase tracking-wide">Context</p>
                  {editItems.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {editItems.map((item, i) => (
                        <div key={i} className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg px-1.5 py-0.5">
                          <span className="text-[10px] text-slate-700 max-w-[110px] truncate">{item}</span>
                          <button onClick={() => setEditContext(editItems.filter((_, j) => j !== i).join("\n"))} className="text-slate-400 hover:text-rose-500"><X size={7} /></button>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="flex gap-1">
                    <input value={editInput} onChange={(e) => setEditInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (editInput.trim()) { setEditContext([...editItems, editInput.trim()].join("\n")); setEditInput(""); } } }} placeholder="Hours, policies, FAQs…" className="flex-1 bg-white text-[10px] text-slate-700 placeholder-slate-400 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-brand border border-slate-200 min-w-0" />
                    <button onClick={() => { if (editInput.trim()) { setEditContext([...editItems, editInput.trim()].join("\n")); setEditInput(""); } }} disabled={!editInput.trim()} className="px-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-500 disabled:opacity-40 transition-colors"><Plus size={9} /></button>
                  </div>
                  <button onClick={() => saveEdit(target.id)} className="w-full py-1 rounded-lg bg-brand-dark hover:bg-brand text-white text-[10px] font-semibold transition-colors">Save context</button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Add target */}
      {!showAdd ? (
        <button onClick={() => setShowAdd(true)} className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl border border-dashed border-slate-300 text-[11px] text-slate-400 hover:text-slate-600 hover:border-slate-400 transition-colors">
          <Plus size={11} /> Add category or sender
        </button>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          {availableCats.length > 0 && (
            <>
              <p className="text-[9px] text-slate-400 px-3 pt-2 pb-1 font-semibold uppercase tracking-wide">Categories</p>
              {availableCats.map((cat) => (
                <button key={cat.id} onClick={() => addCategoryTarget(cat)} className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-50 transition-colors">
                  <div className={cn("w-2 h-2 rounded-full shrink-0", cat.colorBg)} />
                  <span className="text-[11px] text-slate-700 flex-1 text-left">{cat.name}</span>
                  <span className="text-[9px] text-slate-400">{cat.mode === "vip" ? "VIP" : "AI"}</span>
                </button>
              ))}
            </>
          )}
          <div className={cn(availableCats.length > 0 && "border-t border-slate-100")}>
            {!showSenderInput ? (
              <button onClick={() => setShowSenderInput(true)} className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-slate-50 transition-colors">
                <UserCheck size={11} className="text-slate-400 shrink-0" />
                <span className="text-[11px] text-slate-600">Specific sender…</span>
              </button>
            ) : (
              <div className="p-2 flex gap-1.5">
                <input value={senderInput} onChange={(e) => setSenderInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addSenderTarget(); }} placeholder="email@example.com" autoFocus className="flex-1 bg-slate-50 text-[11px] text-slate-700 placeholder-slate-400 rounded-lg px-2 py-1.5 outline-none focus:ring-1 focus:ring-brand border border-slate-200 min-w-0" />
                <button onClick={addSenderTarget} disabled={!senderInput.trim()} className="px-2.5 rounded-lg bg-brand-dark hover:bg-brand text-white disabled:opacity-40 transition-colors text-[10px] font-semibold">Add</button>
              </div>
            )}
          </div>
          <div className="border-t border-slate-100 px-3 py-2">
            <button onClick={() => { setShowAdd(false); setShowSenderInput(false); setSenderInput(""); }} className="text-[10px] text-slate-400 hover:text-slate-600 transition-colors">Cancel</button>
          </div>
        </div>
      )}

      {/* Turn off */}
      <button onClick={() => onSave({ ...autoreply, enabled: false })} className="flex items-center gap-1.5 text-[11px] text-rose-600 hover:text-rose-500 transition-colors pt-1">
        <AlertCircle size={11} /> Turn off
      </button>
    </div>
  );
}

// ── Category Manager modal ────────────────────────────────────────────────────

function CategoryManager({
  categories,
  onSave,
  onClose,
}: {
  categories: Category[];
  onSave: (cats: Category[]) => void;
  onClose: () => void;
}) {
  const [cats, setCats] = useState<Category[]>(categories);
  const [creating, setCreating] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"ai" | "vip">("ai");
  const [description, setDescription] = useState("");
  const [addresses, setAddresses] = useState("");
  const [colorIdx, setColorIdx] = useState(0);

  function resetForm() {
    setName(""); setMode("ai"); setDescription(""); setAddresses(""); setColorIdx(0);
    setCreating(false); setEditId(null);
  }

  function startEdit(cat: Category) {
    const ci = CAT_COLORS.findIndex((c) => c.bg === cat.colorBg);
    setEditId(cat.id); setName(cat.name); setMode(cat.mode);
    setDescription(cat.description ?? ""); setAddresses((cat.addresses ?? []).join(", "));
    setColorIdx(ci >= 0 ? ci : 0); setCreating(true);
  }

  function saveCategory() {
    if (!name.trim()) { toast.error("Name required"); return; }
    const color = CAT_COLORS[colorIdx];
    const cat: Category = {
      id: editId ?? Date.now().toString(),
      name: name.trim(), colorBg: color.bg, colorText: color.text, mode,
      description: mode === "ai" ? description.trim() || undefined : undefined,
      addresses: mode === "vip" ? addresses.split(",").map((a) => a.trim()).filter(Boolean) : undefined,
    };
    const next = editId ? cats.map((c) => (c.id === editId ? cat : c)) : [...cats, cat];
    setCats(next); onSave(next); resetForm();
    toast.success(editId ? "Category updated" : "Category created");
  }

  function deleteCategory(id: string) {
    const next = cats.filter((c) => c.id !== id);
    setCats(next); onSave(next);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-4">
      <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-[420px] shadow-xl flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Tag size={14} className="text-brand-dark" />
            <span className="font-semibold text-sm text-slate-800">Email Categories</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 transition-colors"><X size={15} /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {cats.length === 0 && !creating && (
            <div className="text-center py-8 text-slate-400">
              <Tag size={28} className="mx-auto mb-3 opacity-30" />
              <p className="text-xs leading-relaxed">No categories yet.<br />Create one to auto-sort your inbox.</p>
            </div>
          )}

          {cats.map((cat) => (
            <div key={cat.id} className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-slate-50 border border-slate-200">
              <div className={cn("w-2 h-2 rounded-full shrink-0", cat.colorBg)} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-slate-800">{cat.name}</span>
                  <span className={cn("text-[9px] px-1.5 py-0.5 rounded-full font-medium", cat.mode === "vip" ? "bg-amber-100 text-amber-700" : "bg-brand/10 text-brand-dark")}>
                    {cat.mode === "vip" ? "VIP" : "AI"}
                  </span>
                </div>
                {cat.mode === "ai" && cat.description && <p className="text-[10px] text-slate-500 truncate mt-0.5">{cat.description}</p>}
                {cat.mode === "vip" && cat.addresses?.length ? <p className="text-[10px] text-slate-500 truncate mt-0.5">{cat.addresses.join(", ")}</p> : null}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => startEdit(cat)} className="p-1.5 rounded-lg text-slate-400 hover:text-brand-dark hover:bg-slate-100 transition-colors"><Pencil size={10} /></button>
                <button onClick={() => deleteCategory(cat.id)} className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-colors"><Trash2 size={10} /></button>
              </div>
            </div>
          ))}

          {creating ? (
            <div className="rounded-xl border border-brand/20 bg-brand/5 p-4 space-y-3">
              <p className="text-xs font-semibold text-slate-800">{editId ? "Edit Category" : "New Category"}</p>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (e.g. Boss, Partners, Clients)" autoFocus className="w-full bg-white text-sm text-slate-800 placeholder-slate-400 rounded-xl px-3 py-2.5 outline-none focus:ring-1 focus:ring-brand border border-slate-200" />
              <div className="flex gap-2">
                <button onClick={() => setMode("ai")} className={cn("flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium border transition-colors", mode === "ai" ? "bg-brand/10 border-brand/30 text-brand-dark" : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50")}>
                  <Cpu size={11} /> AI sorts
                </button>
                <button onClick={() => setMode("vip")} className={cn("flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium border transition-colors", mode === "vip" ? "bg-amber-50 border-amber-300 text-amber-700" : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50")}>
                  <UserCheck size={11} /> VIP senders
                </button>
              </div>
              {mode === "ai" ? (
                <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Hint: e.g. 'supplier invoices and business proposals'" className="w-full bg-white text-xs text-slate-800 placeholder-slate-400 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-200" />
              ) : (
                <input value={addresses} onChange={(e) => setAddresses(e.target.value)} placeholder="Emails comma-separated: boss@co.com, cfo@co.com" className="w-full bg-white text-xs text-slate-800 placeholder-slate-400 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-200" />
              )}
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-500 shrink-0">Color</span>
                <div className="flex gap-1.5 flex-wrap">
                  {CAT_COLORS.map((c, i) => (
                    <button key={i} onClick={() => setColorIdx(i)} className={cn("w-4 h-4 rounded-full transition-all", c.bg, colorIdx === i ? "ring-2 ring-brand-dark ring-offset-1 ring-offset-white scale-110" : "hover:scale-105")} />
                  ))}
                </div>
              </div>
              <div className="flex gap-2 pt-1">
                <button onClick={resetForm} className="flex-1 py-2 rounded-xl text-xs text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors font-medium">Cancel</button>
                <button onClick={saveCategory} className="flex-1 py-2 rounded-xl text-xs font-semibold bg-brand-dark hover:bg-brand text-white transition-colors">{editId ? "Save changes" : "Create"}</button>
              </div>
            </div>
          ) : (
            <button onClick={() => setCreating(true)} className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-dashed border-slate-300 text-xs text-slate-400 hover:text-slate-600 hover:border-slate-400 transition-colors">
              <Plus size={12} /> Add category
            </button>
          )}
        </div>

        <div className="px-5 py-3 border-t border-slate-100">
          <button onClick={onClose} className="w-full py-2 rounded-xl text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Compose modal ─────────────────────────────────────────────────────────────

function ComposeModal({
  provider,
  onClose,
  onSent,
  contacts = [],
  prefillTo = "",
  prefillSubject = "",
  prefillBody = "",
}: {
  provider: "gmail" | "microsoft" | null;
  onClose: () => void;
  onSent: () => void;
  contacts?: string[];
  prefillTo?: string;
  prefillSubject?: string;
  prefillBody?: string;
}) {
  const [to, setTo] = useState(prefillTo);
  const [subject, setSubject] = useState(prefillSubject);
  const [body, setBody] = useState(prefillBody);
  const [sending, setSending] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [tone, setTone] = useState<"professional" | "friendly" | "concise">("professional");
  const [directions, setDirections] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  function handleToChange(val: string) {
    setTo(val);
    const query = val.split(",").pop()?.trim().toLowerCase() ?? "";
    if (query.length >= 1) {
      const matches = contacts.filter((c) => c.toLowerCase().includes(query)).slice(0, 6);
      setSuggestions(matches);
      setShowSuggestions(matches.length > 0);
    } else {
      setShowSuggestions(false);
    }
  }

  function selectContact(contact: string) {
    const parts = to.split(",");
    parts[parts.length - 1] = " " + extractEmail(contact);
    setTo(parts.join(",").trimStart());
    setShowSuggestions(false);
  }

  async function send() {
    if (!to.trim() || !subject.trim()) { toast.error("To and Subject are required"); return; }
    setSending(true);
    try {
      if (provider === "gmail") {
        const raw = buildRaw({ to, subject, body });
        await apiPost("/api/email", { action: "send", raw });
      } else {
        await apiPost("/api/email", { action: "send", to, subject, replyBody: body });
      }
      toast.success("Sent!");
      onSent();
      onClose();
    } catch { toast.error("Send failed"); }
    finally { setSending(false); }
  }

  async function aiWrite() {
    if (!subject.trim() && !directions.trim()) { toast.error("Add a subject or directions first"); return; }
    setDrafting(true);
    try {
      const data = await apiPost("/api/email/draft", {
        threadSubject: subject || "New email",
        latestMessage: "(composing new email)",
        senderName: to || "the recipient",
        tone,
        extraContext: directions.trim() || undefined,
      }) as { draft: string };
      setBody(data.draft);
      setTimeout(() => bodyRef.current?.focus(), 50);
    } catch { toast.error("AI draft failed"); }
    finally { setDrafting(false); }
  }

  async function aiRewrite() {
    if (!body.trim()) { toast.error("Nothing to rewrite yet"); return; }
    setDrafting(true);
    try {
      const data = await apiPost("/api/email/draft", {
        threadSubject: subject || "New email",
        latestMessage: body,
        senderName: to || "the recipient",
        tone,
        extraContext: `Rewrite and improve this draft.${directions.trim() ? " " + directions.trim() : ""}`,
      }) as { draft: string };
      setBody(data.draft);
      setTimeout(() => bodyRef.current?.focus(), 50);
    } catch { toast.error("AI rewrite failed"); }
    finally { setDrafting(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:justify-end bg-black/30 backdrop-blur-sm p-4 md:pb-6 md:pr-6">
      <div className="bg-white border border-slate-200 rounded-2xl w-full md:w-[520px] shadow-xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Pencil size={13} className="text-brand-dark" />
            <span className="text-sm font-semibold text-slate-800">New Email</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 transition-colors"><X size={15} /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {/* To field with contact autocomplete */}
          <div className="relative">
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5 focus-within:ring-2 focus-within:ring-brand bg-white">
              <span className="text-xs text-slate-400 shrink-0 font-medium w-12">To</span>
              <input
                value={to}
                onChange={(e) => handleToChange(e.target.value)}
                onFocus={() => to && setShowSuggestions(suggestions.length > 0)}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                placeholder="recipient@email.com"
                autoFocus
                className="flex-1 bg-transparent text-sm text-slate-800 placeholder-slate-400 outline-none min-w-0"
              />
            </div>
            {showSuggestions && (
              <div className="absolute left-0 right-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-lg z-10 overflow-hidden">
                {suggestions.map((c, i) => (
                  <button
                    key={i}
                    onMouseDown={() => selectContact(c)}
                    className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-slate-50 transition-colors text-left"
                  >
                    <div className={cn("w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold text-white shrink-0", avatarColor(c))}>
                      {initials(c)}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-slate-800 truncate">{c.split("<")[0].trim() || c}</p>
                      <p className="text-[10px] text-slate-400 truncate">{extractEmail(c)}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Subject */}
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5 focus-within:ring-2 focus-within:ring-brand bg-white">
            <span className="text-xs text-slate-400 shrink-0 font-medium w-12">Subject</span>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="What's this about?"
              className="flex-1 bg-transparent text-sm text-slate-800 placeholder-slate-400 outline-none min-w-0"
            />
          </div>

          {/* AI directions bar */}
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <Sparkles size={11} className="text-brand-dark shrink-0" />
            <input
              value={directions}
              onChange={(e) => setDirections(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); aiWrite(); } }}
              placeholder="Tell AI what to write… schedule a meeting, follow up on invoice, pitch the product"
              className="flex-1 bg-transparent text-xs text-slate-700 placeholder-slate-400 outline-none min-w-0"
            />
            <div className="flex gap-1 shrink-0">
              {(["professional", "friendly", "concise"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTone(t)}
                  className={cn(
                    "text-[9px] px-1.5 py-0.5 rounded-full capitalize font-medium transition-colors",
                    tone === t ? "bg-brand-dark text-white" : "text-slate-400 hover:text-slate-700"
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Body */}
          <div className="relative">
            <textarea
              ref={bodyRef}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write your message, or use AI to draft it…"
              rows={10}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); } }}
              className="w-full bg-white text-sm text-slate-800 placeholder-slate-400 rounded-xl border border-slate-200 p-3 pr-10 outline-none focus:ring-2 focus:ring-brand resize-none leading-relaxed"
            />
            {drafting && (
              <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-white/80">
                <div className="flex items-center gap-2 text-brand-dark text-xs font-medium">
                  <Loader2 size={14} className="animate-spin" /> Writing…
                </div>
              </div>
            )}
            <span className="absolute right-3 bottom-2 text-[9px] text-slate-400">⌘↵ send</span>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 px-4 pb-4 pt-2 border-t border-slate-100">
          <button
            onClick={aiWrite}
            disabled={drafting}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-brand/10 text-brand-dark hover:bg-brand/20 border border-brand/20 text-xs font-semibold disabled:opacity-50 transition-colors"
          >
            {drafting ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            AI Write
          </button>
          {body.trim() && (
            <button
              onClick={aiRewrite}
              disabled={drafting}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-medium disabled:opacity-50 transition-colors"
            >
              <Sparkles size={12} className="text-brand-dark" /> Rewrite
            </button>
          )}
          <div className="flex-1" />
          <button onClick={onClose} className="px-3 py-2 text-xs text-slate-400 hover:text-slate-700 transition-colors">
            Discard
          </button>
          <button
            onClick={send}
            disabled={sending || !to.trim() || !subject.trim()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold disabled:opacity-40 transition-colors"
          >
            {sending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            {sending ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function EmailPage() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [lastSynced, setLastSynced] = useState<Date | null>(null);
  const [syncStatus, setSyncStatus] = useState<{ status: string; total_threads?: number; last_week?: string; progress_pct?: number } | null>(null);
  const syncPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [provider, setProvider] = useState<"gmail" | "microsoft" | null>(null);
  const [connectedProviders, setConnectedProviders] = useState<("gmail" | "microsoft")[]>([]);
  const [activeProvider, setActiveProvider] = useState<"gmail" | "microsoft" | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [tab, setTab] = useState<Tab>("all");

  const [selected, setSelected] = useState<Thread | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [threadLoading, setThreadLoading] = useState(false);

  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [showReply, setShowReply] = useState(false);

  const [draftTone, setDraftTone] = useState<"professional" | "friendly" | "concise">("professional");
  const [extraContext, setExtraContext] = useState("");
  const [drafting, setDrafting] = useState(false);

  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const [loadingQuick, setLoadingQuick] = useState(false);

  const [autoreply, setAutoreply] = useState<AutoreplyRule>({ enabled: false, targets: [] });

  const [showCompose, setShowCompose] = useState(false);

  const [starred, setStarred] = useState<Set<string>>(new Set());

  // Categories
  const [categories, setCategories] = useState<Category[]>([]);
  const [threadCategories, setThreadCategories] = useState<Record<string, string>>({});
  const [showCategoryManager, setShowCategoryManager] = useState(false);

  // Thread summaries
  const [threadSummaries, setThreadSummaries] = useState<Record<string, ThreadSummary>>({});
  const [summaryExpanded, setSummaryExpanded] = useState(false);

  const replyRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [threadLimit, setThreadLimit] = useState(50);
  const [hasMore, setHasMore] = useState(false);

  const loadThreads = useCallback(async (q = "", providerOverride?: "gmail" | "microsoft", limit = 50) => {
    setLoading(true);
    try {
      const pParam = providerOverride ?? activeProvider;
      const url = `/api/email?q=${encodeURIComponent(q)}&limit=${limit}${pParam ? `&provider=${pParam}` : ""}`;
      const data = await apiGet(url);
      setConnected(data.connected);
      setProvider(data.provider ?? null);
      setConnectedProviders(data.connectedProviders ?? []);
      if (!activeProvider && data.provider) setActiveProvider(data.provider);
      const incoming = data.threads ?? [];
      setThreads(incoming);
      setHasMore(incoming.length >= limit);
    } catch {
      toast.error("Failed to load inbox");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProvider]);

  useEffect(() => { loadThreads(); }, [loadThreads]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("email_autoreply");
      if (saved) setAutoreply(JSON.parse(saved) as AutoreplyRule);
      const savedStarred = localStorage.getItem("email_starred");
      if (savedStarred) setStarred(new Set(JSON.parse(savedStarred) as string[]));
      const savedCats = localStorage.getItem("email_categories");
      if (savedCats) setCategories(JSON.parse(savedCats) as Category[]);
      const savedAssign = localStorage.getItem("email_thread_categories");
      if (savedAssign) setThreadCategories(JSON.parse(savedAssign) as Record<string, string>);
      const savedSummaries = localStorage.getItem("email_thread_summaries");
      if (savedSummaries) setThreadSummaries(JSON.parse(savedSummaries) as Record<string, ThreadSummary>);
    } catch { /* ignore */ }
  }, []);

  function switchProvider(p: "gmail" | "microsoft") {
    setActiveProvider(p);
    setSelected(null);
    setMessages([]);
    loadThreads(activeSearch, p);
  }

  function saveAutoreply(rule: AutoreplyRule) {
    setAutoreply(rule);
    localStorage.setItem("email_autoreply", JSON.stringify(rule));
  }

  function toggleStar(threadId: string) {
    setStarred((prev) => {
      const next = new Set(prev);
      next.has(threadId) ? next.delete(threadId) : next.add(threadId);
      localStorage.setItem("email_starred", JSON.stringify([...next]));
      return next;
    });
  }

  function saveCategories(cats: Category[]) {
    setCategories(cats);
    localStorage.setItem("email_categories", JSON.stringify(cats));
  }

  function saveThreadCategory(threadId: string, categoryId: string) {
    setThreadCategories((prev) => {
      const next = { ...prev, [threadId]: categoryId };
      localStorage.setItem("email_thread_categories", JSON.stringify(next));
      return next;
    });
  }

  function getCatForThread(threadId: string): Category | undefined {
    const catId = threadCategories[threadId];
    return catId ? categories.find((c) => c.id === catId) : undefined;
  }

  async function generateThreadSummary(thread: Thread, msgs: Message[]) {
    if (msgs.length < 3) return;
    const existing = threadSummaries[thread.id];
    if (existing && existing.messageCount >= msgs.length) return;
    try {
      const data = await apiPost("/api/email/summarize", {
        subject: thread.subject,
        messages: msgs.map((m) => ({ from: m.from, date: m.date, body: stripHtml(m.body).slice(0, 600) })),
      }) as { summary: string | null };
      if (!data.summary) return;
      const entry: ThreadSummary = {
        threadId: thread.id,
        summary: data.summary,
        messageCount: msgs.length,
        generatedAt: new Date().toISOString(),
      };
      setThreadSummaries((prev) => {
        const next = { ...prev, [thread.id]: entry };
        localStorage.setItem("email_thread_summaries", JSON.stringify(next));
        return next;
      });
    } catch { /* ignore */ }
  }

  const classifyThreadsInBackground = useCallback(async (ts: Thread[], cats: Category[]) => {
    if (cats.length === 0) return;
    const vipCats = cats.filter((c) => c.mode === "vip");
    const aiCats = cats.filter((c) => c.mode === "ai");
    const saved = JSON.parse(localStorage.getItem("email_thread_categories") ?? "{}") as Record<string, string>;

    for (const thread of ts.slice(0, 30)) {
      const email = extractEmail(thread.from);
      const vip = vipCats.find((c) => c.addresses?.some((a) => a.toLowerCase() === email.toLowerCase()));
      if (vip) { saveThreadCategory(thread.id, vip.id); continue; }
      if (saved[thread.id]) continue;
      if (aiCats.length > 0) {
        try {
          const data = await apiPost("/api/email/classify", {
            subject: thread.subject,
            from: thread.from,
            snippet: thread.snippet,
            categories: aiCats.map((c) => ({ id: c.id, name: c.name, description: c.description })),
          }) as { categoryId: string | null };
          if (data.categoryId) saveThreadCategory(thread.id, data.categoryId);
        } catch { /* ignore */ }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (threads.length > 0 && categories.length > 0) {
      classifyThreadsInBackground(threads, categories);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threads.length, categories.length]);

  const filteredThreads = threads.filter((t) => {
    if (tab === "unread") return t.unread;
    if (tab === "starred") return starred.has(t.id);
    if (tab !== "all") return threadCategories[t.id] === tab;
    return true;
  });

  const unreadCount = threads.filter((t) => t.unread).length;
  const starredCount = threads.filter((t) => starred.has(t.id)).length;

  const contacts = useMemo(() => {
    const seen = new Set<string>();
    return threads
      .map((t) => t.from.trim())
      .filter((f) => { const e = extractEmail(f); if (seen.has(e)) return false; seen.add(e); return true; });
  }, [threads]);

  // Keep a ref to always have the freshest loadThreads inside the interval
  const loadThreadsRef = useRef(loadThreads);
  useEffect(() => { loadThreadsRef.current = loadThreads; }, [loadThreads]);

  function startSyncPolling() {
    if (syncPollRef.current) clearInterval(syncPollRef.current);
    syncPollRef.current = setInterval(async () => {
      try {
        const token = getToken();
        // Check sync status
        const statusRes = await fetch("/api/email/sync-status", {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (statusRes.ok) {
          const data = await statusRes.json() as { status: string; total_threads?: number; last_month?: string };
          setSyncStatus(data);
          if (data.status === "complete" || data.status === "never_synced") {
            if (syncPollRef.current) clearInterval(syncPollRef.current);
            setSyncStatus(null);
          }
        }
        // Always refresh thread list using latest loadThreads ref
        await loadThreadsRef.current("", undefined, threadLimit);
      } catch { /* ignore */ }
    }, 5000);
  }

  // Cleanup poll on unmount
  useEffect(() => () => { if (syncPollRef.current) clearInterval(syncPollRef.current); }, []);

  async function syncEmails() {
    setSyncing(true);
    try {
      const res = await apiPost("/api/email", { action: "sync" }) as { synced_threads?: number; deep_sync?: string };
      setLastSynced(new Date());
      await loadThreads(activeSearch);
      if (res.deep_sync === "started") {
        toast.success("Latest emails loaded — syncing full history in background…");
        startSyncPolling();
      } else {
        toast.success("Inbox synced!");
      }
    } catch {
      toast.error("Sync failed — please try again.");
    } finally {
      setSyncing(false);
    }
  }

  async function openThread(thread: Thread) {
    setSelected(thread);
    setMessages([]);
    setReplyText("");
    setShowReply(false);
    setExtraContext("");
    setQuickReplies([]);
    setThreadLoading(true);
    try {
      let msgs: Message[] = [];
      // Always fetch the full thread to get all messages in the conversation.
      // The list view only embeds the latest message, so we must re-fetch for complete history.
      try {
        const data = await apiPost("/api/email", { action: "get_thread", threadId: thread.id, provider: activeProvider }) as { messages: Message[] };
        msgs = data.messages ?? [];
      } catch {
        // Fallback: use whatever is embedded in the thread object
        if (thread.messages && thread.messages.length > 0) {
          msgs = thread.messages;
        } else if (thread.body !== undefined) {
          msgs = [{
            id: thread.id,
            from: thread.from,
            to: thread.to ?? "",
            subject: thread.subject,
            date: thread.date,
            body: thread.body,
            unread: thread.unread,
          }];
        }
      }
      setMessages(msgs);
      if (thread.unread && msgs.length) {
        const last = msgs[msgs.length - 1];
        await apiPost("/api/email", { action: "mark_read", messageId: last.id, provider: activeProvider });
        setThreads((prev) => prev.map((t) => t.id === thread.id ? { ...t, unread: false } : t));
      }
      if (msgs.length) generateQuickReplies(thread.subject, msgs[msgs.length - 1]);
      if (msgs.length >= 3) generateThreadSummary(thread, msgs);
      setSummaryExpanded(false);
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);

      // Auto-open reply + generate draft if thread matches an auto-reply target
      if (msgs.length) {
        const arTargets = autoreply.targets ?? [];
        if (autoreply.enabled && arTargets.length) {
          const cat = getCatForThread(thread.id);
          let matched: AutoreplyTarget | undefined;
          if (cat) matched = arTargets.find((t) => t.type === "category" && t.id === cat.id);
          if (!matched) {
            const senderEmail = extractEmail(msgs[msgs.length - 1].from);
            matched = arTargets.find((t) => t.type === "sender" && t.id.toLowerCase() === senderEmail.toLowerCase());
          }
          if (matched) {
            setShowReply(true);
            generateDraft({ thread, msgs, directions: "" });
          }
        }
      }
    } catch {
      toast.error("Failed to load thread");
    } finally {
      setThreadLoading(false);
    }
  }

  async function generateQuickReplies(subject: string, latest: Message) {
    setLoadingQuick(true);
    try {
      const data = await apiPost("/api/email/draft", {
        threadSubject: subject,
        latestMessage: stripHtml(latest.body).slice(0, 800),
        senderName: latest.from,
        tone: "concise",
        extraContext: "Generate 3 very short reply options (max 15 words each), separated by ||. Do not number them. Just the reply text.",
      }) as { draft: string };
      const raw = data.draft ?? "";
      const options = raw.split("||").map((s) => s.trim()).filter(Boolean).slice(0, 3);
      setQuickReplies(options);
    } catch { /* ignore */ }
    finally { setLoadingQuick(false); }
  }

  async function generateDraft(opts?: { thread?: Thread; msgs?: Message[]; directions?: string }) {
    const t = opts?.thread ?? selected;
    const m = opts?.msgs ?? messages;
    if (!t || !m.length) return;
    setDrafting(true);
    setShowReply(true);
    try {
      const latest = m[m.length - 1];
      const cat = getCatForThread(t.id);
      const summary = threadSummaries[t.id];
      // Find matching auto-reply target (category first, then sender)
      let arTarget: AutoreplyTarget | undefined;
      const arTargets = autoreply.targets ?? [];
      if (autoreply.enabled && arTargets.length) {
        if (cat) arTarget = arTargets.find((tg) => tg.type === "category" && tg.id === cat.id);
        if (!arTarget) {
          const senderEmail = extractEmail(latest.from);
          arTarget = arTargets.find((tg) => tg.type === "sender" && tg.id.toLowerCase() === senderEmail.toLowerCase());
        }
      }
      const directions = opts?.directions !== undefined ? opts.directions : extraContext;
      const contextParts: string[] = [];
      if (directions.trim()) contextParts.push(directions.trim());
      if (arTarget?.context) contextParts.push(`Context: ${arTarget.context.replace(/\n/g, "; ")}`);
      if (summary) contextParts.push(`Conversation summary: ${summary.summary}`);
      const data = await apiPost("/api/email/draft", {
        threadSubject: t.subject,
        latestMessage: stripHtml(latest.body).slice(0, 1500),
        senderName: latest.from,
        tone: arTarget ? arTarget.tone : draftTone,
        extraContext: contextParts.join("\n") || undefined,
      }) as { draft: string };
      setReplyText(data.draft);
      setTimeout(() => replyRef.current?.focus(), 50);
    } catch { toast.error("AI draft failed"); }
    finally { setDrafting(false); }
  }

  async function handleSend() {
    if (!selected || !replyText.trim()) return;
    // Use last loaded message as context; fall back to thread sender if messages aren't loaded yet
    const latest = messages[messages.length - 1];
    const replyTo = latest?.from ?? selected.from;
    const replyMsgId = latest?.id;
    setSending(true);
    try {
      const subject = selected.subject.startsWith("Re:") ? selected.subject : `Re: ${selected.subject}`;
      // Send explicit fields for all providers so Composio doesn't need to parse raw.
      // Also include raw for Nango Gmail which requires it.
      await apiPost("/api/email", {
        action: "send",
        provider: activeProvider,
        to: replyTo,
        subject,
        replyBody: replyText,
        raw: buildRaw({ to: replyTo, subject, body: replyText, inReplyTo: replyMsgId }),
      });
      toast.success("Reply sent!");
      setReplyText("");
      setShowReply(false);
      // Refresh thread
      openThread(selected).catch(() => {});
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Send failed — please try again.");
    } finally {
      setSending(false);
    }
  }

  function handleSearch(e: React.SyntheticEvent) {
    e.preventDefault();
    setActiveSearch(searchInput);
    loadThreads(searchInput);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "c") { e.preventDefault(); setShowCompose(true); }
      if (e.key === "r" && selected) { e.preventDefault(); setShowReply(true); setTimeout(() => replyRef.current?.focus(), 50); }
      if (e.key === "Escape") { setSelected(null); setShowReply(false); }
      if (e.key === "s" && selected) { e.preventDefault(); toggleStar(selected.id); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  return (
    <div className="flex h-full bg-slate-50 text-slate-900 overflow-hidden">

      {/* ── Left pane ─────────────────────────────────────────────────────── */}
      <div className={cn(
        "flex flex-col border-r border-slate-200 bg-white shrink-0 transition-all duration-200",
        selected ? "w-80 hidden md:flex" : "w-full md:w-96"
      )}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-slate-100">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Inbox size={15} className="text-brand-dark" />
              <span className="font-bold text-sm text-slate-900">Inbox</span>
              {/* Provider switcher — shown when multiple accounts connected */}
              {connectedProviders.length > 1 ? (
                <div className="flex items-center gap-0.5 bg-slate-100 rounded-lg p-0.5">
                  {connectedProviders.map((p) => (
                    <button
                      key={p}
                      onClick={() => switchProvider(p)}
                      className={cn(
                        "text-[10px] px-2 py-0.5 rounded-md font-medium transition-colors",
                        activeProvider === p ? "bg-white text-slate-800 shadow-sm" : "text-slate-400 hover:text-slate-600"
                      )}
                    >
                      {p === "gmail" ? "Gmail" : "Outlook"}
                    </button>
                  ))}
                </div>
              ) : provider ? (
                <span className="text-[10px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full font-medium">
                  {provider === "gmail" ? "Gmail" : "Outlook"}
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setShowCategoryManager(true)}
                className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-brand-dark transition-colors"
                title="Categories"
              >
                <Tag size={12} />
              </button>
              <button
                onClick={() => setShowCompose(true)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-brand-dark hover:bg-brand text-white text-xs font-semibold transition-colors"
                title="Compose (C)"
              >
                <Pencil size={11} /> Compose
              </button>
              <button onClick={() => loadThreads(activeSearch)} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 transition-colors" title="Refresh">
                <RefreshCw size={12} />
              </button>
              <button
                onClick={syncEmails}
                disabled={syncing}
                title={lastSynced ? `Last synced ${lastSynced.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "Sync inbox"}
                className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium text-brand-dark bg-brand/10 hover:bg-brand/20 border border-brand/20 transition-colors disabled:opacity-50"
              >
                {syncing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                {syncing ? "Syncing…" : "Sync"}
              </button>
            </div>
          </div>

          {/* Sync progress banner */}
          {syncStatus && syncStatus.status === "running" && (
            <div className="mx-3 mb-1 px-3 py-2 rounded-xl bg-brand/10 border border-brand/20 flex items-center gap-2">
              <Loader2 size={12} className="animate-spin text-brand-dark shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <p className="text-[11px] font-semibold text-brand-dark">Syncing email history…</p>
                  {syncStatus.progress_pct !== undefined && (
                    <span className="text-[10px] text-brand-dark font-bold">{syncStatus.progress_pct}%</span>
                  )}
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  {syncStatus.last_week ? `Week of ${syncStatus.last_week}` : "Starting…"}
                  {syncStatus.total_threads ? ` · ${syncStatus.total_threads} emails saved` : ""}
                </p>
                <div className="w-full h-1 bg-brand/20 rounded-full overflow-hidden mt-1.5">
                  <div
                    className="h-full bg-brand-dark rounded-full transition-all duration-500"
                    style={{ width: `${syncStatus.progress_pct ?? 5}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Search */}
          <form onSubmit={handleSearch}>
            <div className="flex items-center gap-2 bg-slate-50 rounded-xl px-3 py-2 border border-slate-200">
              <Search size={12} className="text-slate-400 shrink-0" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search emails…"
                className="flex-1 bg-transparent text-xs text-slate-700 placeholder-slate-400 outline-none min-w-0"
              />
              {searchInput && (
                <button type="button" onClick={() => { setSearchInput(""); setActiveSearch(""); loadThreads(""); }}>
                  <X size={11} className="text-slate-400" />
                </button>
              )}
            </div>
          </form>
        </div>

        {/* Tabs */}
        <div className="flex flex-wrap border-b border-slate-100">
          {([
            { id: "all", label: "All" },
            { id: "unread", label: "Unread", count: unreadCount },
            { id: "starred", label: "Starred", count: starredCount },
          ] as { id: Tab; label: string; count?: number }[]).map(({ id, label, count }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "shrink-0 px-3 py-2.5 text-xs font-medium flex items-center gap-1 transition-colors border-b-2",
                tab === id
                  ? "text-brand-dark border-brand-dark"
                  : "text-slate-500 border-transparent hover:text-slate-700"
              )}
            >
              {label}
              {count != null && count > 0 && (
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full font-semibold",
                  tab === id ? "bg-brand-dark text-white" : "bg-slate-100 text-slate-500"
                )}>{count}</span>
              )}
            </button>
          ))}
          {/* Category tabs */}
          {categories.map((cat) => {
            const count = threads.filter((t) => threadCategories[t.id] === cat.id).length;
            return (
              <button
                key={cat.id}
                onClick={() => setTab(cat.id)}
                className={cn(
                  "shrink-0 px-3 py-2.5 text-xs font-medium flex items-center gap-1.5 transition-colors border-b-2",
                  tab === cat.id
                    ? `${cat.colorText} border-current`
                    : "text-slate-500 border-transparent hover:text-slate-700"
                )}
              >
                <div className={cn("w-1.5 h-1.5 rounded-full shrink-0", cat.colorBg)} />
                {cat.name}
                {count > 0 && (
                  <span className={cn(
                    "text-[9px] px-1.5 py-0.5 rounded-full font-semibold",
                    tab === cat.id ? `${cat.colorBg} text-white` : "bg-slate-100 text-slate-500"
                  )}>{count}</span>
                )}
              </button>
            );
          })}
        </div>

        {/* Auto-reply bar */}
        <div className="px-3 py-2 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <Bot size={12} className="text-brand-dark" />
            Auto-reply
          </div>
          <button
            onClick={() => saveAutoreply({ ...autoreply, enabled: !autoreply.enabled })}
            className={cn("flex items-center gap-1 text-[11px] font-semibold transition-colors", autoreply.enabled ? "text-emerald-600" : "text-slate-400")}
          >
            {autoreply.enabled ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
            {autoreply.enabled ? "On" : "Off"}
          </button>
        </div>

        {/* Thread list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin text-slate-300" /></div>
          ) : connected === false ? (
            <NoConnection />
          ) : filteredThreads.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-slate-300">
              <MailOpen size={24} />
              <p className="text-xs text-slate-400">{tab === "unread" ? "All caught up!" : tab === "starred" ? "No starred emails" : "No emails"}</p>
            </div>
          ) : (
            filteredThreads.map((thread) => {
              const isStarred = starred.has(thread.id);
              const initStr = initials(thread.from);
              const color = avatarColor(thread.from);
              const cat = getCatForThread(thread.id);
              return (
                <div
                  key={thread.id}
                  onClick={() => openThread(thread)}
                  className={cn(
                    "group w-full text-left px-3 py-3 border-b border-slate-100 hover:bg-slate-50 transition-colors cursor-pointer relative",
                    selected?.id === thread.id && "bg-brand/5 border-l-2 border-l-brand-dark",
                    thread.unread && selected?.id !== thread.id && "border-l-2 border-l-brand"
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    {/* Avatar */}
                    <div className={cn("w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold text-white shrink-0", color)}>
                      {initStr}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1">
                        <span className={cn("text-xs truncate", thread.unread ? "font-bold text-slate-900" : "text-slate-700 font-medium")}>
                          {thread.from.split("<")[0].trim() || thread.from}
                        </span>
                        <span className="text-[10px] text-slate-400 shrink-0">{formatDate(thread.date)}</span>
                      </div>
                      <p className={cn("text-[11px] truncate mt-0.5", thread.unread ? "text-slate-800 font-semibold" : "text-slate-500")}>
                        {thread.subject}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <p className="text-[10px] text-slate-400 line-clamp-1 flex-1">{thread.snippet}</p>
                        {cat && (
                          <div className="flex items-center gap-0.5 shrink-0">
                            <div className={cn("w-1.5 h-1.5 rounded-full", cat.colorBg)} />
                            <span className={cn("text-[9px] font-semibold", cat.colorText)}>{cat.name}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Hover quick actions */}
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-1 bg-white rounded-lg p-1 shadow-md border border-slate-200">
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleStar(thread.id); }}
                      className={cn("p-1 rounded transition-colors", isStarred ? "text-amber-500" : "text-slate-400 hover:text-amber-500")}
                      title="Star (S)"
                    >
                      <Star size={11} fill={isStarred ? "currentColor" : "none"} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); openThread(thread); setShowReply(true); }}
                      className="p-1 rounded text-slate-400 hover:text-brand-dark transition-colors"
                      title="Quick reply"
                    >
                      <Reply size={11} />
                    </button>
                  </div>

                  {thread.unread && (
                    <span className="absolute right-2 bottom-2 w-1.5 h-1.5 rounded-full bg-brand" />
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Load more */}
        {hasMore && !loading && (
          <div className="px-3 py-2 border-t border-slate-100">
            <button
              onClick={() => {
                const next = threadLimit + 50;
                setThreadLimit(next);
                loadThreads(activeSearch, activeProvider, next);
              }}
              className="w-full text-xs text-brand-dark font-medium py-2 rounded-xl hover:bg-brand/5 border border-brand/20 transition-colors"
            >
              Load more emails
            </button>
          </div>
        )}

        {/* Keyboard hint */}
        <div className="px-3 py-2 border-t border-slate-100 flex items-center gap-3 flex-wrap bg-slate-50/50">
          {[["C", "Compose"], ["R", "Reply"], ["S", "Star"], ["Esc", "Close"]].map(([k, label]) => (
            <span key={k} className="text-[10px] text-slate-400 flex items-center gap-1">
              <kbd className="text-[9px] bg-slate-100 text-slate-500 px-1 py-0.5 rounded font-mono border border-slate-200">{k}</kbd>
              {label}
            </span>
          ))}
        </div>

      </div>

      {/* ── Right pane ────────────────────────────────────────────────────── */}
      {selected ? (
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-white">
          {/* Thread header */}
          <div className="px-4 py-3 border-b border-slate-100 bg-white flex items-center gap-3">
            <button onClick={() => setSelected(null)} className="md:hidden p-1.5 rounded-lg text-slate-400 hover:bg-slate-100">
              <ChevronLeft size={16} />
            </button>
            <div className="flex-1 min-w-0">
              <p className="font-bold text-sm truncate text-slate-900">{selected.subject}</p>
              <p className="text-xs text-slate-500 truncate">{selected.from}</p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => toggleStar(selected.id)}
                className={cn("p-2 rounded-lg transition-colors", starred.has(selected.id) ? "text-amber-500" : "text-slate-400 hover:text-amber-500 hover:bg-slate-100")}
                title="Star"
              >
                <Star size={14} fill={starred.has(selected.id) ? "currentColor" : "none"} />
              </button>
              {selected.messageCount > 1 && (
                <span className="text-[10px] text-slate-500 bg-slate-100 px-2 py-1 rounded-lg font-medium">
                  {selected.messageCount} messages
                </span>
              )}
            </div>
          </div>

          {/* Conversation summary card */}
          {selected && threadSummaries[selected.id] && (
            <div className="px-4 pt-3">
              <div className="rounded-xl border border-brand/20 bg-brand/5 overflow-hidden">
                <button
                  onClick={() => setSummaryExpanded((v) => !v)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-brand/10 transition-colors"
                >
                  <Brain size={12} className="text-brand-dark shrink-0" />
                  <span className="text-[11px] font-semibold text-brand-dark flex-1">Conversation memory</span>
                  <span className="text-[10px] text-slate-500">{threadSummaries[selected.id].messageCount} messages</span>
                  <ChevronUp size={12} className={cn("text-slate-400 transition-transform", !summaryExpanded && "rotate-180")} />
                </button>
                {summaryExpanded && (
                  <div className="px-3 pb-3">
                    <div className="text-[11px] text-slate-700 leading-relaxed whitespace-pre-line">
                      {threadSummaries[selected.id].summary}
                    </div>
                    <p className="text-[9px] text-slate-400 mt-2">
                      Generated {new Date(threadSummaries[selected.id].generatedAt).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Chat bubbles */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1 bg-[#f0f2f5]">
            {threadLoading ? (
              <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-slate-400" /></div>
            ) : messages.length === 0 ? (
              <div className="text-center text-slate-400 text-sm py-10">No messages</div>
            ) : (
              <>
                {messages.map((msg, i) => {
                  const isOutgoing = extractEmail(msg.from) !== extractEmail(selected.from);
                  const showAvatar = !isOutgoing && (i === 0 || extractEmail(messages[i - 1].from) !== extractEmail(msg.from));

                  // Date separator
                  const msgDate = new Date(msg.date);
                  const prevDate = i > 0 ? new Date(messages[i - 1].date) : null;
                  const showDateSep = !prevDate || msgDate.toDateString() !== prevDate.toDateString();
                  const dateLabel = (() => {
                    const today = new Date();
                    const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
                    if (msgDate.toDateString() === today.toDateString()) return "Today";
                    if (msgDate.toDateString() === yesterday.toDateString()) return "Yesterday";
                    return msgDate.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
                  })();

                  const cleanBody = stripQuotedReply(msg.body);
                  const bodyHtml = cleanBody.includes("<") ? sanitizeEmailHtml(cleanBody) : cleanBody.replace(/\n/g, "<br/>");
                  const timeStr = msgDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

                  return (
                    <div key={msg.id}>
                      {showDateSep && (
                        <div className="flex justify-center my-3">
                          <span className="text-[11px] text-slate-500 bg-white/80 px-3 py-1 rounded-full shadow-sm border border-slate-200/60">
                            {dateLabel}
                          </span>
                        </div>
                      )}
                      <div className={cn("flex items-end gap-2 mb-1", isOutgoing ? "justify-end" : "justify-start")}>
                        {/* Incoming avatar */}
                        {!isOutgoing && (
                          <div className={cn("w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0 mb-0.5", showAvatar ? avatarColor(msg.from) : "opacity-0")}>
                            {initials(msg.from)}
                          </div>
                        )}
                        <div className={cn("max-w-[72%] flex flex-col", isOutgoing ? "items-end" : "items-start")}>
                          {showAvatar && !isOutgoing && (
                            <span className="text-[10px] text-slate-500 font-medium mb-0.5 ml-1">
                              {msg.from.split("<")[0].trim() || msg.from}
                            </span>
                          )}
                          <div className={cn(
                            "rounded-2xl px-4 py-2.5 shadow-sm text-sm leading-relaxed break-words",
                            isOutgoing
                              ? "bg-[#005c4b] text-white rounded-br-sm"
                              : "bg-white text-slate-800 rounded-bl-sm"
                          )}>
                            <div
                              className="max-w-none [&_a]:underline [&_a]:opacity-80 [&_p]:mb-1 [&_p:last-child]:mb-0 [&_img]:max-w-full [&_img]:rounded"
                              dangerouslySetInnerHTML={{ __html: bodyHtml }}
                            />
                          </div>
                          <span className={cn("text-[10px] mt-0.5 px-1", isOutgoing ? "text-slate-400" : "text-slate-400")}>
                            {timeStr}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Quick reply chips */}
          {!showReply && (quickReplies.length > 0 || loadingQuick) && (
            <div className="px-3 py-2 flex items-center gap-1.5 flex-wrap bg-[#f0f2f5] border-t border-slate-200/60">
              {loadingQuick ? (
                <Loader2 size={11} className="animate-spin text-slate-400" />
              ) : (
                quickReplies.map((qr, i) => (
                  <button
                    key={i}
                    onClick={() => { setReplyText(qr); setShowReply(true); setTimeout(() => replyRef.current?.focus(), 50); }}
                    className="text-[11px] px-3 py-1 rounded-full bg-white border border-slate-200 text-slate-600 hover:bg-brand/5 hover:border-brand/30 hover:text-brand-dark transition-colors shadow-sm"
                  >
                    {qr}
                  </button>
                ))
              )}
            </div>
          )}

          {/* WhatsApp-style compose bar — always visible when a thread is open */}
          {(
            <div className="bg-[#f0f2f5] border-t border-slate-200/60 px-3 py-2.5">
              {/* AI context bar — shown when focused */}
              {showReply && (
                <div className="flex items-center gap-2 bg-white rounded-xl border border-slate-200 px-3 py-1.5 mb-2">
                  <Sparkles size={11} className="text-brand-dark shrink-0" />
                  <input
                    value={extraContext}
                    onChange={(e) => setExtraContext(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); generateDraft(); } }}
                    placeholder="AI direction: mention discount, ask for timeline…"
                    className="flex-1 bg-transparent text-xs text-slate-600 placeholder-slate-400 outline-none min-w-0"
                  />
                  <div className="flex gap-1 shrink-0">
                    {(["professional", "friendly", "concise"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setDraftTone(t)}
                        className={cn(
                          "text-[9px] px-1.5 py-0.5 rounded-full capitalize font-medium transition-colors",
                          draftTone === t ? "bg-brand-dark text-white" : "text-slate-400 hover:text-slate-700"
                        )}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex items-end gap-2">
                {/* AI Draft button */}
                <button
                  onClick={() => { setShowReply(true); generateDraft(); setTimeout(() => replyRef.current?.focus(), 50); }}
                  disabled={drafting}
                  title="AI Draft"
                  className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center shrink-0 hover:bg-brand/5 hover:border-brand/30 transition-colors shadow-sm disabled:opacity-50"
                >
                  {drafting ? <Loader2 size={14} className="animate-spin text-brand-dark" /> : <Sparkles size={14} className="text-brand-dark" />}
                </button>
                {/* Text input */}
                <div className="relative flex-1">
                  <textarea
                    ref={replyRef}
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    onFocus={() => setShowReply(true)}
                    placeholder="Type a reply…"
                    rows={1}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleSend(); }
                    }}
                    style={{ maxHeight: "120px" }}
                    className="w-full bg-white text-sm text-slate-800 placeholder-slate-400 rounded-2xl border border-slate-200 px-4 py-2.5 outline-none focus:ring-2 focus:ring-brand/30 resize-none leading-relaxed shadow-sm overflow-hidden"
                    onInput={(e) => {
                      const t = e.currentTarget;
                      t.style.height = "auto";
                      t.style.height = Math.min(t.scrollHeight, 120) + "px";
                    }}
                  />
                  {drafting && (
                    <div className="absolute inset-0 flex items-center px-4 rounded-2xl bg-white/90">
                      <span className="text-xs text-brand-dark font-medium flex items-center gap-1.5">
                        <Loader2 size={12} className="animate-spin" /> Writing…
                      </span>
                    </div>
                  )}
                </div>
                {/* Send button */}
                <button
                  onClick={handleSend}
                  disabled={sending || !replyText.trim()}
                  className="w-10 h-10 rounded-full bg-[#005c4b] hover:bg-[#017561] flex items-center justify-center shrink-0 transition-colors disabled:opacity-40 shadow-sm"
                >
                  {sending ? <Loader2 size={16} className="animate-spin text-white" /> : <Send size={16} className="text-white" />}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 bg-slate-50">
          {connected === false ? (
            <NoConnection inline />
          ) : (
            <>
              <MailOpen size={40} className="text-slate-200" />
              <p className="text-sm text-slate-400">Select a conversation</p>
              <button
                onClick={() => setShowCompose(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-sm text-slate-600 transition-colors mt-2 shadow-sm"
              >
                <Pencil size={14} className="text-brand-dark" /> Compose new email
              </button>
            </>
          )}
        </div>
      )}

      {/* ── Auto-reply right panel ─────────────────────────────────────────── */}
      {autoreply.enabled && (
        <div className="w-64 border-l border-slate-200 bg-white flex flex-col shrink-0">
          <AutoreplyPanel autoreply={autoreply} categories={categories} onSave={saveAutoreply} />
        </div>
      )}

      {/* Compose modal */}
      {showCompose && (
        <ComposeModal
          provider={provider}
          contacts={contacts}
          onClose={() => setShowCompose(false)}
          onSent={() => loadThreads(activeSearch)}
        />
      )}

      {/* Category manager */}
      {showCategoryManager && (
        <CategoryManager
          categories={categories}
          onSave={saveCategories}
          onClose={() => setShowCategoryManager(false)}
        />
      )}
    </div>
  );
}
