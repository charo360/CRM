"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  collaborationApi,
  teamApi,
  type ChannelAccessGrant,
  type CollaborationWorkspace,
  type InboundRoutingRule,
  type TeamMember,
} from "@/lib/api";
import { getUser } from "@/lib/auth";
import { FolderKanban, Plus, Trash2, Save, FlaskConical, Link2 } from "lucide-react";

const LEVELS = ["off", "read", "reply", "admin"] as const;

export default function CollaborationPage() {
  const [tab, setTab] = useState<"workspaces" | "access" | "routing">("workspaces");
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [workspaces, setWorkspaces] = useState<CollaborationWorkspace[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [grants, setGrants] = useState<ChannelAccessGrant[]>([]);
  const [routingEnabled, setRoutingEnabled] = useState(false);
  const [routingReplace, setRoutingReplace] = useState(false);
  const [routingDefault, setRoutingDefault] = useState("owner");
  const [rules, setRules] = useState<InboundRoutingRule[]>([]);
  const [previewText, setPreviewText] = useState("I need a refund please");
  const [previewResult, setPreviewResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<{ type: "ok" | "err"; msg: string } | null>(null);
  const [wsForm, setWsForm] = useState({ name: "", description: "" });
  const [assetForm, setAssetForm] = useState<{ workspaceId: string; title: string; url: string }>({
    workspaceId: "",
    title: "",
    url: "",
  });

  const ownerUserId = useMemo(() => {
    const u = getUser();
    if (!u) return "";
    return (u.business_id as string) || (u._id as string) || "";
  }, []);

  const roster = useMemo(() => {
    const rows: { user_id: string; label: string }[] = [];
    if (ownerUserId) {
      rows.push({ user_id: ownerUserId, label: "Owner / business" });
    }
    for (const m of members) {
      const uid = m.user_id;
      if (!uid || uid === ownerUserId) continue;
      rows.push({ user_id: uid, label: `${m.name} (${m.role})` });
    }
    return rows;
  }, [members, ownerUserId]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setBanner(null);
    try {
      const [ws, tm, ca, ir] = await Promise.all([
        collaborationApi.listWorkspaces(),
        teamApi.list().catch(() => [] as TeamMember[]),
        collaborationApi.getChannelAccess().catch(() => null),
        collaborationApi.getInboundRouting().catch(() => null),
      ]);
      setWorkspaces(ws.workspaces || []);
      setMembers(Array.isArray(tm) ? tm : []);
      if (ca) {
        setChannels(ca.channels || []);
        setGrants(ca.grants || []);
      }
      if (ir) {
        setRoutingEnabled(ir.enabled);
        setRoutingReplace(ir.replace_existing);
        setRoutingDefault(ir.default_assignee || "owner");
        setRules(ir.rules?.length ? ir.rules : []);
      }
    } catch (e) {
      setBanner({
        type: "err",
        msg: e instanceof Error ? e.message : "Could not load collaboration settings (managers only for some sections).",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  function grantKey(userId: string, channel: string) {
    return `${userId}::${channel}`;
  }

  function getLevel(userId: string, channel: string): string {
    const g = grants.find((x) => x.user_id === userId && x.channel === channel);
    return g?.level || "off";
  }

  function setLevel(userId: string, channel: string, level: string) {
    const next = grants.filter((x) => !(x.user_id === userId && x.channel === channel));
    if (level !== "off") next.push({ user_id: userId, channel, level });
    setGrants(next);
  }

  async function saveAccess() {
    setSaving(true);
    try {
      await collaborationApi.putChannelAccess(grants);
      setBanner({ type: "ok", msg: "Channel access saved." });
    } catch (e) {
      setBanner({ type: "err", msg: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setSaving(false);
    }
  }

  async function saveRouting() {
    setSaving(true);
    try {
      await collaborationApi.putInboundRouting({
        enabled: routingEnabled,
        replace_existing: routingReplace,
        default_assignee: routingDefault,
        rules: rules.map((r) => ({
          ...r,
          keywords: r.keywords || [],
          channels: r.channels?.length ? r.channels : ["whatsapp", "social", "email"],
        })),
      });
      setBanner({ type: "ok", msg: "Routing rules saved. They apply to new WhatsApp and social inbox messages when enabled." });
    } catch (e) {
      setBanner({ type: "err", msg: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setSaving(false);
    }
  }

  async function runPreview() {
    try {
      const r = await collaborationApi.previewInboundRouting({
        text: previewText,
        channel: "whatsapp",
      });
      setPreviewResult(
        `Would assign to: ${r.assignee_user_id}${r.matched_rule ? ` (rule: ${r.matched_rule})` : " (default)"}`,
      );
    } catch (e) {
      setPreviewResult(e instanceof Error ? e.message : "Preview failed");
    }
  }

  async function createWorkspace() {
    if (!wsForm.name.trim()) return;
    setSaving(true);
    try {
      await collaborationApi.createWorkspace({
        name: wsForm.name.trim(),
        description: wsForm.description.trim(),
      });
      setWsForm({ name: "", description: "" });
      await loadAll();
      setBanner({ type: "ok", msg: "Workspace created." });
    } catch (e) {
      setBanner({ type: "err", msg: e instanceof Error ? e.message : "Failed" });
    } finally {
      setSaving(false);
    }
  }

  async function addAsset() {
    if (!assetForm.workspaceId || !assetForm.title.trim()) return;
    setSaving(true);
    try {
      await collaborationApi.addWorkspaceAsset(assetForm.workspaceId, {
        type: "link",
        title: assetForm.title.trim(),
        url: assetForm.url.trim(),
      });
      setAssetForm({ workspaceId: "", title: "", url: "" });
      await loadAll();
      setBanner({ type: "ok", msg: "Link added." });
    } catch (e) {
      setBanner({ type: "err", msg: e instanceof Error ? e.message : "Failed" });
    } finally {
      setSaving(false);
    }
  }

  async function removeWorkspace(id: string) {
    if (!confirm("Delete this workspace?")) return;
    try {
      await collaborationApi.deleteWorkspace(id);
      await loadAll();
    } catch (e) {
      setBanner({ type: "err", msg: e instanceof Error ? e.message : "Failed" });
    }
  }

  const assigneeOptions = useMemo(() => roster, [roster]);

  return (
    <div className="mx-auto max-w-5xl min-w-0 space-y-6 p-4 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Collaboration</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Shared workspaces for campaigns and docs, per-channel access for social integrations, and keyword routing for
            incoming WhatsApp and unified social messages (assigns conversations in Messages).
          </p>
        </div>
      </div>

      {banner && (
        <div
          className={`rounded-lg px-4 py-3 text-sm ${banner.type === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}
        >
          {banner.msg}
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {(
          [
            ["workspaces", "Workspaces"],
            ["access", "Channel access"],
            ["routing", "Message routing"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
              tab === id ? "bg-brand text-white shadow-sm" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : tab === "workspaces" ? (
        <div className="space-y-8">
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <FolderKanban className="h-4 w-4 text-brand-dark" />
              New workspace
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Use one workspace per campaign or project. Leave members empty so the whole team can see it.
            </p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <input
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                placeholder="Name (e.g. Summer ad launch)"
                value={wsForm.name}
                onChange={(e) => setWsForm((s) => ({ ...s, name: e.target.value }))}
              />
              <input
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                placeholder="Short description (optional)"
                value={wsForm.description}
                onChange={(e) => setWsForm((s) => ({ ...s, description: e.target.value }))}
              />
              <button
                type="button"
                disabled={saving}
                onClick={() => void createWorkspace()}
                className="inline-flex items-center justify-center gap-1 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
              >
                <Plus className="h-4 w-4" />
                Create
              </button>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-slate-800">Your workspaces</h2>
            {workspaces.length === 0 ? (
              <p className="text-sm text-slate-500">No workspaces yet.</p>
            ) : (
              <ul className="space-y-3">
                {workspaces.map((w) => (
                  <li key={w.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="font-medium text-slate-900">{w.name}</div>
                        {w.description ? (
                          <p className="mt-1 text-sm text-slate-600">{w.description}</p>
                        ) : null}
                        {w.linked_conversation_id ? (
                          <p className="mt-2 text-xs text-slate-500">
                            Linked Zilo chat: <code className="rounded bg-slate-100 px-1">{w.linked_conversation_id}</code>
                          </p>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        onClick={() => void removeWorkspace(w.id)}
                        className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                    {w.assets && w.assets.length > 0 ? (
                      <ul className="mt-3 space-y-1 border-t border-slate-100 pt-3">
                        {w.assets.map((a) => (
                          <li key={a.id} className="text-xs text-slate-600">
                            <Link2 className="mr-1 inline h-3 w-3" />
                            {a.url ? (
                              <a href={a.url} className="text-brand-dark underline" target="_blank" rel="noreferrer">
                                {a.title || a.url}
                              </a>
                            ) : (
                              a.title
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 bg-slate-50/80 p-4">
            <h3 className="text-sm font-semibold text-slate-800">Add a link to a workspace</h3>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end">
              <select
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                value={assetForm.workspaceId}
                onChange={(e) => setAssetForm((s) => ({ ...s, workspaceId: e.target.value }))}
              >
                <option value="">Select workspace…</option>
                {workspaces.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
              <input
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                placeholder="Label"
                value={assetForm.title}
                onChange={(e) => setAssetForm((s) => ({ ...s, title: e.target.value }))}
              />
              <input
                className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                placeholder="https://…"
                value={assetForm.url}
                onChange={(e) => setAssetForm((s) => ({ ...s, url: e.target.value }))}
              />
              <button
                type="button"
                disabled={saving}
                onClick={() => void addAsset()}
                className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
              >
                Add link
              </button>
            </div>
          </section>
        </div>
      ) : tab === "access" ? (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            <strong className="text-slate-800">Managers only.</strong> Leave the table empty to keep the default: everyone
            can use connected social features. After you save any row, the matrix applies to social API actions (read /
            reply / connect).
          </p>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="min-w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="p-2 font-semibold text-slate-700">Person</th>
                  {channels.map((c) => (
                    <th key={c} className="p-2 font-semibold capitalize text-slate-700">
                      {c.replace("_", " ")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {roster.map((person) => (
                  <tr key={person.user_id} className="border-b border-slate-100">
                    <td className="p-2 text-slate-800">{person.label}</td>
                    {channels.map((c) => (
                      <td key={grantKey(person.user_id, c)} className="p-2">
                        <select
                          className="w-full max-w-[5.5rem] rounded border border-slate-200 bg-white px-1 py-1"
                          value={getLevel(person.user_id, c)}
                          onChange={(e) => setLevel(person.user_id, c, e.target.value)}
                        >
                          {LEVELS.map((l) => (
                            <option key={l} value={l}>
                              {l}
                            </option>
                          ))}
                        </select>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            disabled={saving}
            onClick={() => void saveAccess()}
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            Save channel access
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
            <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
              <input
                type="checkbox"
                checked={routingEnabled}
                onChange={(e) => setRoutingEnabled(e.target.checked)}
              />
              Enable keyword routing for incoming WhatsApp &amp; social (unified inbox) messages
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={routingReplace}
                onChange={(e) => setRoutingReplace(e.target.checked)}
              />
              Re-assign on every message (overrides existing assignment)
            </label>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-slate-600">Default assignee if no keyword matches:</span>
              <select
                className="rounded-lg border border-slate-200 px-2 py-1"
                value={routingDefault}
                onChange={(e) => setRoutingDefault(e.target.value)}
              >
                <option value="owner">Owner</option>
                {assigneeOptions.map((o) => (
                  <option key={o.user_id} value={o.user_id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">Rules (first match wins)</h2>
              <button
                type="button"
                className="text-sm font-medium text-brand-dark hover:underline"
                onClick={() =>
                  setRules((r) => [
                    ...r,
                    {
                      name: "New rule",
                      keywords: [],
                      channels: ["whatsapp", "social", "email"],
                      assignee_user_id: ownerUserId,
                    },
                  ])
                }
              >
                + Add rule
              </button>
            </div>
            {rules.map((rule, idx) => (
              <div key={rule.id || idx} className="rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-2">
                <input
                  className="w-full rounded border border-slate-200 px-2 py-1 text-sm"
                  value={rule.name}
                  placeholder="Rule name"
                  onChange={(e) => {
                    const next = [...rules];
                    next[idx] = { ...rule, name: e.target.value };
                    setRules(next);
                  }}
                />
                <input
                  className="w-full rounded border border-slate-200 px-2 py-1 text-sm"
                  value={(rule.keywords || []).join(", ")}
                  placeholder="Keywords (comma-separated), e.g. refund, money back"
                  onChange={(e) => {
                    const next = [...rules];
                    next[idx] = {
                      ...rule,
                      keywords: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    };
                    setRules(next);
                  }}
                />
                <div className="flex flex-wrap gap-2 items-center">
                  <span className="text-xs text-slate-500">Assign to</span>
                  <select
                    className="rounded border border-slate-200 px-2 py-1 text-sm"
                    value={rule.assignee_user_id}
                    onChange={(e) => {
                      const next = [...rules];
                      next[idx] = { ...rule, assignee_user_id: e.target.value };
                      setRules(next);
                    }}
                  >
                    {assigneeOptions.map((o) => (
                      <option key={o.user_id} value={o.user_id}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="ml-auto text-xs text-red-600 hover:underline"
                    onClick={() => setRules((r) => r.filter((_, i) => i !== idx))}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </section>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={() => void saveRouting()}
              className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              Save routing
            </button>
          </div>

          <section className="rounded-xl border border-dashed border-slate-300 bg-white p-4">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <FlaskConical className="h-4 w-4" />
              Try a sample message
            </h3>
            <textarea
              className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              rows={2}
              value={previewText}
              onChange={(e) => setPreviewText(e.target.value)}
            />
            <button
              type="button"
              onClick={() => void runPreview()}
              className="mt-2 rounded-lg bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-200"
            >
              Preview assignment
            </button>
            {previewResult ? <p className="mt-2 text-sm text-slate-700">{previewResult}</p> : null}
          </section>

          <p className="text-xs text-slate-500">
            Support email routing uses the same rules when those messages are connected to the CRM; today this applies to
            WhatsApp (Evolution) and Zernio webhook traffic. Extend keywords for billing, shipping, or VIP customers.
          </p>
        </div>
      )}
    </div>
  );
}
