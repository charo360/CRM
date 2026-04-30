"use client";

import { useEffect, useState } from "react";
import { teamApi, TeamMember } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Users, Plus, Trash2, Edit, Shield, User, Crown, Phone, Copy, Check, KeyRound } from "lucide-react";

const ROLES = [
  { value: "owner",    label: "Owner",    icon: Crown,  color: "text-brand-dark" },
  { value: "manager",  label: "Manager",  icon: Shield, color: "text-blue-600" },
  { value: "employee", label: "Employee", icon: User,   color: "text-green-600" },
];

const STATUS_STYLES: Record<string, string> = {
  active:    "bg-green-100 text-green-700",
  invited:   "bg-amber-100 text-amber-700",
  suspended: "bg-red-100   text-red-600",
};

const PERMISSIONS = [
  "view_customers", "edit_customers", "view_orders", "edit_orders",
  "view_sales", "edit_sales", "view_analytics", "manage_team",
  "manage_settings", "send_messages", "manage_broadcasts"
];

export default function TeamPage() {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [tempPasswordInfo, setTempPasswordInfo] = useState<{ name: string; email: string; password: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone_number: "",
    role: "employee",
    permissions: [] as string[],
  });

  useEffect(() => {
    loadMembers();
  }, []);

  async function loadMembers() {
    try {
      const data = await teamApi.list();
      setMembers(data);
    } catch (e) {
      console.error("Failed to load team members:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      if (editingId) {
        await teamApi.update(editingId, form);
        setShowCreate(false);
        setEditingId(null);
        setForm({ name: "", email: "", phone_number: "", role: "employee", permissions: [] });
        await loadMembers();
      } else {
        const created = await teamApi.create(form);
        setShowCreate(false);
        setForm({ name: "", email: "", phone_number: "", role: "employee", permissions: [] });
        await loadMembers();
        if (created?.temp_password) {
          setTempPasswordInfo({ name: created.name, email: created.email, password: created.temp_password });
        }
      }
    } catch (e) {
      console.error("Failed to save team member:", e);
      alert("Failed to save team member");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Remove ${name} from the team?`)) return;
    try {
      await teamApi.delete(id);
      await loadMembers();
    } catch (e) {
      console.error("Failed to delete team member:", e);
      alert("Failed to remove team member");
    }
  }

  function copyPassword() {
    if (!tempPasswordInfo) return;
    navigator.clipboard.writeText(tempPasswordInfo.password);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleEdit(member: TeamMember) {
    setForm({
      name: member.name,
      email: member.email || "",
      phone_number: member.phone_number || "",
      role: member.role,
      permissions: member.permissions || [],
    });
    setEditingId(member.id);
    setShowCreate(true);
  }

  function togglePermission(permission: string) {
    setForm(f => ({
      ...f,
      permissions: f.permissions.includes(permission)
        ? f.permissions.filter(p => p !== permission)
        : [...f.permissions, permission]
    }));
  }

  const roleConfig = ROLES.find(r => r.value === form.role) || ROLES[2];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Team Management</h1>
          <p className="text-slate-500 text-sm mt-1">Manage your team members and their permissions</p>
        </div>
        <button
          onClick={() => {
            setForm({ name: "", email: "", phone_number: "", role: "employee", permissions: [] });
            setEditingId(null);
            setShowCreate(true);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm font-semibold rounded-lg hover:bg-brand transition-colors"
        >
          <Plus size={15} /> Add Member
        </button>
      </div>

      {/* Team Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {ROLES.map(({ value, label, icon: Icon, color }) => {
          const count = members.filter(m => m.role === value).length;
          return (
            <div key={value} className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="flex items-center gap-3">
                <Icon size={20} className={color} />
                <div>
                  <p className="text-2xl font-bold text-slate-900">{count}</p>
                  <p className="text-sm text-slate-500">{label}{count !== 1 ? "s" : ""}</p>
                </div>
              </div>
            </div>
          );
        })}
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <Users size={20} className="text-slate-400" />
            <div>
              <p className="text-2xl font-bold text-slate-900">{members.length}</p>
              <p className="text-sm text-slate-500">Total</p>
            </div>
          </div>
        </div>
      </div>

      {/* Members List */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {["Member", "Role", "Status", "Permissions", "Joined", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 5 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <div className="h-4 bg-slate-100 rounded animate-pulse" />
                        </td>
                      ))}
                    </tr>
                  ))
                : members.map((member) => {
                    const roleInfo = ROLES.find(r => r.value === member.role) || ROLES[3];
                    const RoleIcon = roleInfo.icon;
                    return (
                      <tr key={member.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-full bg-brand/15 flex items-center justify-center">
                              <span className="text-brand-dark font-semibold text-xs">
                                {member.name.charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div>
                              <p className="font-medium text-slate-800">{member.name}</p>
                              <p className="text-xs text-slate-500">{member.email || member.phone_number || "—"}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <RoleIcon size={14} className={roleInfo.color} />
                            <span className="font-medium text-slate-700">{roleInfo.label}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-xs font-medium px-2.5 py-1 rounded-full capitalize ${
                            STATUS_STYLES[member.status || "invited"] ?? "bg-slate-100 text-slate-600"
                          }`}>
                            {member.status || "invited"}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {(member.permissions || []).slice(0, 2).map(perm => (
                              <span key={perm} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                                {perm.replace(/_/g, " ")}
                              </span>
                            ))}
                            {(member.permissions || []).length > 2 && (
                              <span className="text-xs text-slate-400">
                                +{(member.permissions || []).length - 2} more
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-400">
                          {member.created_at ? formatDate(member.created_at) : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1">
                            <button
                              onClick={() => handleEdit(member)}
                              className="p-1.5 rounded-lg text-slate-400 hover:bg-blue-100 hover:text-blue-600 transition-colors"
                              title="Edit"
                            >
                              <Edit size={14} />
                            </button>
                            <button
                              onClick={() => handleDelete(member.id, member.name)}
                              className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600 transition-colors"
                              title="Remove"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
          {!loading && members.length === 0 && (
            <div className="text-center py-12">
              <Users size={48} className="mx-auto text-slate-300 mb-4" />
              <p className="text-slate-500 text-lg font-medium">No team members yet</p>
              <p className="text-slate-400 text-sm mt-1">Add your first team member to get started</p>
            </div>
          )}
        </div>
      </div>

      {/* Temp Password Dialog */}
      {tempPasswordInfo && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
                <KeyRound size={20} className="text-green-600" />
              </div>
              <div>
                <h3 className="font-bold text-slate-900">Member Added</h3>
                <p className="text-sm text-slate-500">{tempPasswordInfo.name} can now log in</p>
              </div>
            </div>

            <div className="bg-slate-50 rounded-xl p-4 space-y-2">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Share these login details</p>
              <div className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Email</span>
                  <span className="font-medium text-slate-800">{tempPasswordInfo.email}</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-slate-500">Temp password</span>
                  <span className="font-mono font-bold text-slate-900 text-base tracking-widest">{tempPasswordInfo.password}</span>
                </div>
              </div>
            </div>

            <p className="text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
              This password is shown only once. Share it with {tempPasswordInfo.name} and ask them to log in at the web dashboard.
            </p>

            <div className="flex gap-2">
              <button
                onClick={copyPassword}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 border border-slate-200 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
              >
                {copied ? <Check size={15} className="text-green-500" /> : <Copy size={15} />}
                {copied ? "Copied!" : "Copy Password"}
              </button>
              <button
                onClick={() => { setTempPasswordInfo(null); setCopied(false); }}
                className="flex-1 py-2.5 bg-brand-dark text-white font-semibold rounded-xl text-sm hover:bg-brand transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">
                {editingId ? "Edit Team Member" : "Add Team Member"}
              </h3>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-600">
                ×
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Name *</label>
                  <input
                    value={form.name}
                    onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="Full name"
                    required
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-brand"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
                    placeholder="email@example.com"
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-brand"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Phone Number <span className="text-slate-400 font-normal text-xs">(optional)</span>
                </label>
                <div className="relative">
                  <Phone size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="tel"
                    value={form.phone_number}
                    onChange={(e) => setForm(f => ({ ...f, phone_number: e.target.value }))}
                    placeholder="+1234567890"
                    className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-brand"
                  />
                </div>
                <p className="text-xs text-slate-400 mt-1">Only needed for mobile app login. Include country code if provided.</p>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Role</label>
                <div className="grid grid-cols-2 gap-2">
                  {ROLES.filter(r => r.value !== "owner").map(({ value, label, icon: Icon, color }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setForm(f => ({ ...f, role: value }))}
                      className={`flex items-center gap-2 p-3 rounded-lg border transition-colors ${
                        form.role === value
                          ? "border-brand bg-brand/10 text-brand-dark"
                          : "border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <Icon size={16} className={form.role === value ? "text-brand-dark" : color} />
                      <span className="text-sm font-medium">{label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Permissions</label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {PERMISSIONS.map(permission => (
                    <label key={permission} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={form.permissions.includes(permission)}
                        onChange={() => togglePermission(permission)}
                        className="w-4 h-4 text-brand-dark rounded focus:ring-brand"
                      />
                      <span className="text-sm text-slate-700">
                        {permission.replace("_", " ").replace(/\b\w/g, l => l.toUpperCase())}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                disabled={creating}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-brand-dark text-white font-semibold rounded-xl hover:bg-brand disabled:opacity-50 text-sm"
              >
                {creating && <Users size={15} className="animate-spin" />}
                {editingId ? "Update Member" : "Add Member"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
