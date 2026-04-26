"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Inbox, RefreshCw, Search, Send, Sparkles, X, ChevronLeft,
  Loader2, Mail, MailOpen, Clock, Bot, ToggleLeft, ToggleRight,
  Star, Reply, Pencil, Zap, AlertCircle,
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
  date: string;
  snippet: string;
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
  return btoa(unescape(encodeURIComponent(lines.join("\r\n"))))
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

  const usedCatIds = autoreply.targets.filter((t) => t.type === "category").map((t) => t.id);
  const availableCats = categories.filter((c) => !usedCatIds.includes(c.id));

  function addCategoryTarget(cat: Category) {
    onSave({ ...autoreply, targets: [...autoreply.targets, { id: cat.id, type: "category", label: cat.name, tone: "professional", context: "" }] });
    setShowAdd(false);
  }

  function addSenderTarget() {
    const email = senderInput.trim();
    if (!email || !email.includes("@")) { toast.error("Enter a valid email"); return; }
    if (autoreply.targets.find((t) => t.id.toLowerCase() === email.toLowerCase())) { toast.error("Already added"); return; }
    onSave({ ...autoreply, targets: [...autoreply.targets, { id: email, type: "sender", label: email, tone: "professional", context: "" }] });
    setSenderInput(""); setShowSenderInput(false); setShowAdd(false);
  }

  function removeTarget(id: string) {
    onSave({ ...autoreply, targets: autoreply.targets.filter((t) => t.id !== id) });
    if (expandedId === id) setExpandedId(null);
  }

  function startEdit(target: AutoreplyTarget) {
    setExpandedId(target.id); setEditTone(target.tone); setEditContext(target.context); setEditInput("");
  }

  function saveEdit(id: string) {
    onSave({ ...autoreply, targets: autoreply.targets.map((t) => t.id === id ? { ...t, tone: editTone, context: editContext } : t) });
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
      {autoreply.targets.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 py-5 text-center">
          <p className="text-[11px] text-slate-400">No targets yet.<br />Add a category or sender below.</p>
        </div>
      )}

      <div className="space-y-2">
        {autoreply.targets.map((target) => {
          const cat = categories.find((c) => c.id === target.id);
          const isExpanded = expandedId === target.id;
          const chips = target.context ? target.context.split("\n").filter(Boolean) : [];
          return (
            <div key={target.id} className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
              <div className="flex items-center gap-2 px-3 py-2">
                {cat ? <div className={cn("w-2 h-2 rounded-full shrink-0", cat.colorBg)} /> : <UserCheck size={10} className="text-slate-400 shrink-0" />}
                <span className="text-[11px] font-medium text-slate-700 flex-1 truncate">{target.label}</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-brand/10 text-brand-dark font-medium capitalize shrink-0">{target.tone}</span>
                <button onClick={() => isExpanded ? setExpandedId(null) : startEdit(target)} className="p-0.5 text-slate-400 hover:text-brand-dark transition-colors ml-1">
                  <Pencil size={9} />
                </button>
                <button onClick={() => removeTarget(target.id)} className="p-0.5 text-slate-400 hover:text-rose-500 transition-colors">
                  <X size={9} />
                </button>
              </div>
              {!isExpanded && chips.length > 0 && (
                <div className="px-3 pb-2 flex flex-wrap gap-1">
                  {chips.map((c, i) => <span key={i} className="text-[9px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-full">{c}</span>)}
                </div>
              )}
              {isExpanded && (
                <div className="px-3 pb-3 space-y-2 border-t border-slate-200 pt-2">
                  <div className="flex gap-1 flex-wrap">
                    {(["professional", "friendly", "concise"] as const).map((t) => (
                      <button key={t} onClick={() => setEditTone(t)} className={cn("text-[10px] px-2 py-0.5 rounded-lg capitalize font-medium transition-colors", editTone === t ? "bg-brand-dark text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-100")}>
                        {t}
                      </button>
                    ))}
                  </div>
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
                    <input value={editInput} onChange={(e) => setEditInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (editInput.trim()) { setEditContext([...editItems, editInput.trim()].join("\n")); setEditInput(""); } } }} placeholder="Add context…" className="flex-1 bg-white text-[10px] text-slate-700 placeholder-slate-400 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-brand border border-slate-200 min-w-0" />
                    <button onClick={() => { if (editInput.trim()) { setEditContext([...editItems, editInput.trim()].join("\n")); setEditInput(""); } }} disabled={!editInput.trim()} className="px-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-500 disabled:opacity-40 transition-colors"><Plus size={9} /></button>
                  </div>
                  <button onClick={() => saveEdit(target.id)} className="w-full py-1 rounded-lg bg-brand-dark hover:bg-brand text-white text-[10px] font-semibold transition-colors">Save</button>
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
  prefillTo = "",
  prefillSubject = "",
  prefillBody = "",
}: {
  provider: "gmail" | "microsoft" | null;
  onClose: () => void;
  onSent: () => void;
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
    if (!subject.trim()) { toast.error("Enter a subject first"); return; }
    setDrafting(true);
    try {
      const data = await apiPost("/api/email/draft", {
        threadSubject: subject,
        latestMessage: body || "(no prior content)",
        tone,
      }) as { draft: string };
      setBody(data.draft);
    } catch { toast.error("AI draft failed"); }
    finally { setDrafting(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:justify-end bg-black/30 backdrop-blur-sm p-4 md:pb-6 md:pr-6">
      <div className="bg-white border border-slate-200 rounded-2xl w-full md:w-[480px] shadow-xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Pencil size={13} className="text-brand-dark" />
            <span className="text-sm font-semibold text-slate-800">New Email</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 transition-colors"><X size={15} /></button>
        </div>

        {/* Fields */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="To"
            className="w-full bg-white text-sm text-slate-800 placeholder-slate-400 rounded-xl px-4 py-2.5 outline-none focus:ring-2 focus:ring-brand border border-slate-200"
          />
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            className="w-full bg-white text-sm text-slate-800 placeholder-slate-400 rounded-xl px-4 py-2.5 outline-none focus:ring-2 focus:ring-brand border border-slate-200"
          />

          {/* Tone selector */}
          <div className="flex items-center gap-1.5 pt-1">
            <span className="text-[10px] text-slate-500 font-medium">Tone:</span>
            {(["professional", "friendly", "concise"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTone(t)}
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded-full capitalize transition-colors font-medium",
                  tone === t ? "bg-brand-dark text-white" : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                )}
              >
                {t}
              </button>
            ))}
          </div>

          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Write your message…"
            rows={10}
            className="w-full bg-white text-sm text-slate-800 placeholder-slate-400 rounded-xl border border-slate-200 p-3 outline-none focus:ring-2 focus:ring-brand resize-none leading-relaxed"
          />
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 px-4 pb-4 pt-2 border-t border-slate-100">
          <button
            onClick={aiWrite}
            disabled={drafting}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs text-slate-600 font-medium disabled:opacity-50 transition-colors"
          >
            {drafting ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} className="text-brand-dark" />}
            AI Write
          </button>
          <div className="flex-1" />
          <button onClick={onClose} className="px-3 py-2 text-xs text-slate-400 hover:text-slate-700 transition-colors">
            Discard
          </button>
          <button
            onClick={send}
            disabled={sending}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold disabled:opacity-50 transition-colors"
          >
            {sending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            Send
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
  const [provider, setProvider] = useState<"gmail" | "microsoft" | null>(null);
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
  const [showDraftSettings, setShowDraftSettings] = useState(false);

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

  const loadThreads = useCallback(async (q = "") => {
    setLoading(true);
    try {
      const data = await apiGet(`/api/email?q=${encodeURIComponent(q)}&limit=50`);
      setConnected(data.connected);
      setProvider(data.provider ?? null);
      setThreads(data.threads ?? []);
    } catch {
      toast.error("Failed to load inbox");
    } finally {
      setLoading(false);
    }
  }, []);

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

  async function openThread(thread: Thread) {
    setSelected(thread);
    setMessages([]);
    setReplyText("");
    setShowReply(false);
    setQuickReplies([]);
    setShowDraftSettings(false);
    setThreadLoading(true);
    try {
      const data = await apiPost("/api/email", { action: "get_thread", threadId: thread.id }) as { messages: Message[] };
      const msgs = data.messages ?? [];
      setMessages(msgs);
      if (thread.unread && msgs.length) {
        const last = msgs[msgs.length - 1];
        await apiPost("/api/email", { action: "mark_read", messageId: last.id });
        setThreads((prev) => prev.map((t) => t.id === thread.id ? { ...t, unread: false } : t));
      }
      if (msgs.length) generateQuickReplies(thread.subject, msgs[msgs.length - 1]);
      if (msgs.length >= 3) generateThreadSummary(thread, msgs);
      setSummaryExpanded(false);
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
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

  async function handleAiDraft() {
    if (!selected || !messages.length) return;
    setDrafting(true);
    try {
      const latest = messages[messages.length - 1];
      const cat = getCatForThread(selected.id);
      const summary = threadSummaries[selected.id];
      // Find matching auto-reply target (category first, then sender)
      let arTarget: AutoreplyTarget | undefined;
      if (autoreply.enabled && autoreply.targets.length) {
        if (cat) arTarget = autoreply.targets.find((t) => t.type === "category" && t.id === cat.id);
        if (!arTarget) {
          const senderEmail = extractEmail(latest.from);
          arTarget = autoreply.targets.find((t) => t.type === "sender" && t.id.toLowerCase() === senderEmail.toLowerCase());
        }
      }
      const contextParts: string[] = [];
      if (extraContext.trim()) contextParts.push(extraContext.trim());
      if (arTarget?.context) contextParts.push(`Context: ${arTarget.context.replace(/\n/g, "; ")}`);
      if (summary) contextParts.push(`Conversation summary: ${summary.summary}`);
      const richContext = contextParts.join("\n");
      const effectiveTone = arTarget ? arTarget.tone : draftTone;
      const data = await apiPost("/api/email/draft", {
        threadSubject: selected.subject,
        latestMessage: stripHtml(latest.body).slice(0, 1500),
        senderName: latest.from,
        tone: effectiveTone,
        extraContext: richContext || undefined,
      }) as { draft: string };
      setReplyText(data.draft);
      setShowReply(true);
      setTimeout(() => replyRef.current?.focus(), 50);
    } catch { toast.error("AI draft failed"); }
    finally { setDrafting(false); }
  }

  async function handleSend() {
    if (!selected || !replyText.trim()) return;
    setSending(true);
    try {
      const latest = messages[messages.length - 1];
      const subject = selected.subject.startsWith("Re:") ? selected.subject : `Re: ${selected.subject}`;
      if (provider === "gmail") {
        await apiPost("/api/email", { action: "send", raw: buildRaw({ to: latest.from, subject, body: replyText, inReplyTo: latest.id }) });
      } else {
        await apiPost("/api/email", { action: "send", to: latest.from, subject, replyBody: replyText });
      }
      toast.success("Sent!");
      setReplyText("");
      setShowReply(false);
      await openThread(selected);
    } catch { toast.error("Send failed"); }
    finally { setSending(false); }
  }

  function handleSearch(e: React.FormEvent) {
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
              {provider && (
                <span className="text-[10px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full font-medium">
                  {provider === "gmail" ? "Gmail" : "Outlook"}
                </span>
              )}
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
            </div>
          </div>

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

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {threadLoading ? (
              <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-slate-300" /></div>
            ) : messages.length === 0 ? (
              <div className="text-center text-slate-400 text-sm py-10">No messages</div>
            ) : (
              <>
                {messages.map((msg, i) => {
                  const isLast = i === messages.length - 1;
                  return (
                    <div key={msg.id} className={cn("rounded-2xl border p-4 transition-all", isLast ? "border-slate-200 bg-white shadow-sm" : "border-slate-100 bg-slate-50")}>
                      <div className="flex items-start justify-between gap-3 mb-3">
                        <div className="flex items-center gap-2.5">
                          <div className={cn("w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0", avatarColor(msg.from))}>
                            {initials(msg.from)}
                          </div>
                          <div>
                            <p className="text-xs font-bold text-slate-900">{msg.from.split("<")[0].trim()}</p>
                            <p className="text-[10px] text-slate-400">To: {msg.to.split(",")[0]}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 text-[10px] text-slate-400 shrink-0">
                          <Clock size={10} />
                          {new Date(msg.date).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </div>
                      </div>
                      <div
                        className="text-sm text-slate-700 leading-relaxed"
                        dangerouslySetInnerHTML={{ __html: msg.body.includes("<") ? msg.body : msg.body.replace(/\n/g, "<br/>") }}
                      />
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Quick replies */}
          {!showReply && messages.length > 0 && (
            <div className="px-4 pb-3 flex items-center gap-2 flex-wrap border-t border-slate-100 pt-3 bg-white">
              <span className="text-[10px] text-slate-400 shrink-0 font-medium">Quick reply:</span>
              {loadingQuick ? (
                <Loader2 size={12} className="animate-spin text-slate-400" />
              ) : (
                quickReplies.map((qr, i) => (
                  <button
                    key={i}
                    onClick={() => { setReplyText(qr); setShowReply(true); setTimeout(() => replyRef.current?.focus(), 50); }}
                    className="text-[11px] px-3 py-1.5 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 transition-colors shadow-sm"
                  >
                    {qr}
                  </button>
                ))
              )}
              <button
                onClick={() => { setShowReply(true); setTimeout(() => replyRef.current?.focus(), 50); }}
                className="flex items-center gap-1 text-[11px] px-3 py-1.5 rounded-xl bg-white hover:bg-brand/5 border border-slate-200 hover:border-brand/30 text-brand-dark transition-colors ml-auto shadow-sm font-medium"
              >
                <Reply size={11} /> Reply
              </button>
            </div>
          )}

          {/* Reply composer */}
          {showReply && (
            <div className="border-t border-slate-100 bg-white p-4 space-y-3">
              {/* AI draft settings */}
              {showDraftSettings && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-brand-dark flex items-center gap-1.5"><Sparkles size={11} /> AI Draft</span>
                    <button onClick={() => setShowDraftSettings(false)}><X size={12} className="text-slate-400" /></button>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500 w-8 font-medium">Tone</span>
                    {(["professional", "friendly", "concise"] as const).map((t) => (
                      <button key={t} onClick={() => setDraftTone(t)} className={cn("text-[10px] px-2 py-0.5 rounded-lg capitalize transition-colors font-medium", draftTone === t ? "bg-brand-dark text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50")}>
                        {t}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500 w-8 font-medium">Hint</span>
                    <input
                      value={extraContext}
                      onChange={(e) => setExtraContext(e.target.value)}
                      placeholder="e.g. mention 30-day return policy"
                      className="flex-1 text-[11px] bg-white border border-slate-200 text-slate-700 placeholder-slate-400 rounded-lg px-3 py-1.5 outline-none focus:ring-1 focus:ring-brand"
                    />
                  </div>
                  <button onClick={handleAiDraft} disabled={drafting} className="w-full py-1.5 rounded-lg bg-brand-dark hover:bg-brand text-white text-xs font-semibold flex items-center justify-center gap-1.5 disabled:opacity-50 transition-colors">
                    {drafting ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                    {drafting ? "Writing…" : "Generate"}
                  </button>
                </div>
              )}

              {autoreply.enabled && (
                <div className="flex items-center gap-2 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-2 font-medium">
                  <Zap size={11} /> Auto-reply active for new emails
                </div>
              )}

              <div className="relative">
                <textarea
                  ref={replyRef}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Write a reply…"
                  rows={4}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleSend(); }
                  }}
                  className="w-full bg-white text-sm text-slate-800 placeholder-slate-400 rounded-xl border border-slate-200 p-3 pr-10 outline-none focus:ring-2 focus:ring-brand resize-none leading-relaxed"
                />
                <span className="absolute right-3 bottom-2 text-[9px] text-slate-400">⌘↵ send</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowDraftSettings((v) => !v)}
                  className={cn("flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-colors", showDraftSettings ? "bg-brand/10 text-brand-dark border border-brand/20" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}
                >
                  <Sparkles size={12} /> AI Draft
                </button>
                <button onClick={() => { setShowReply(false); setReplyText(""); }} className="px-3 py-2 rounded-xl text-xs text-slate-400 hover:text-slate-700 transition-colors">
                  Cancel
                </button>
                <div className="flex-1" />
                <button
                  onClick={handleSend}
                  disabled={sending || !replyText.trim()}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold disabled:opacity-40 transition-colors"
                >
                  {sending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                  {sending ? "Sending…" : "Send"}
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
