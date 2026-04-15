"use client";

import { useEffect, useState } from "react";
import { teamApi, TeamMember } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Users, Plus, Trash2, Edit, Mail, Shield, User, Crown } from "lucide-react";

const ROLES = [
  { value: "owner", label: "Owner", icon: Crown, color: "text-purple-600" },
  { value: "admin", label: "Admin", icon: Shield, color: "text-blue-600" },
  { value: "manager", label: "Manager", icon: User, color: "text-green-600" },
  { value: "staff", label: "Staff", icon: User, color: "text-slate-600" },
];

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
  const [form, setForm] = useState({
    name: "",
    email: "",
    role: "staff",
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
      } else {
        await teamApi.create(form);
      }
      setShowCreate(false);
      setEditingId(null);
      setForm({ name: "", email: "", role: "staff", permissions: [] });
      await loadMembers();
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

  function handleEdit(member: TeamMember) {
    setForm({
      name: member.name,
      email: member.email,
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

  const roleConfig = ROLES.find(r => r.value === form.role) || ROLES[3];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Team Management</h1>
          <p className="text-slate-500 text-sm mt-1">Manage your team members and their permissions</p>
        </div>
        <button
          onClick={() => {
            setForm({ name: "", email: "", role: "staff", permissions: [] });
            setEditingId(null);
            setShowCreate(true);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus size={15} /> Add Member
        </button>
      </div>

      {/* Team Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
      </div>

      {/* Members List */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {["Member", "Role", "Permissions", "Joined", "Actions"].map((h) => (
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
                            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center">
                              <span className="text-indigo-600 font-semibold text-xs">
                                {member.name.charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div>
                              <p className="font-medium text-slate-800">{member.name}</p>
                              <p className="text-xs text-slate-500">{member.email}</p>
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
                          <div className="flex flex-wrap gap-1">
                            {(member.permissions || []).slice(0, 3).map(perm => (
                              <span key={perm} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                                {perm.replace("_", " ")}
                              </span>
                            ))}
                            {(member.permissions || []).length > 3 && (
                              <span className="text-xs text-slate-400">
                                +{(member.permissions || []).length - 3} more
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
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Email *</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
                    placeholder="email@example.com"
                    required
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Role</label>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {ROLES.map(({ value, label, icon: Icon, color }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setForm(f => ({ ...f, role: value }))}
                      className={`flex items-center gap-2 p-3 rounded-lg border transition-colors ${
                        form.role === value
                          ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                          : "border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <Icon size={16} className={form.role === value ? "text-indigo-600" : color} />
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
                        className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
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
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm"
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
