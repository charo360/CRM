"use client";

import { useState } from "react";
import { adminApi } from "@/lib/api";
import { KeyRound, LogOut, Shield, Eye, EyeOff, CheckCircle } from "lucide-react";
import { useRouter } from "next/navigation";

export default function AdminSettingsPage() {
  const router = useRouter();
  const [showPwd, setShowPwd] = useState(false);
  const [saved, setSaved] = useState(false);

  function handleLogout() {
    adminApi.logout();
    router.replace("/admin/login");
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Admin Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">Manage your admin panel configuration</p>
      </div>

      {/* Session */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Shield size={15} className="text-indigo-600" />
          <h2 className="text-sm font-semibold text-slate-800">Admin session</h2>
        </div>
        <p className="text-sm text-slate-500">
          You are signed in to the Zilo Admin panel. Your session is valid for 12 hours from login.
        </p>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-red-200 text-red-600 text-sm font-medium hover:bg-red-50 transition-colors"
        >
          <LogOut size={14} />
          Sign out of admin
        </button>
      </div>

      {/* Password info */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <KeyRound size={15} className="text-indigo-600" />
          <h2 className="text-sm font-semibold text-slate-800">Admin password</h2>
        </div>
        <p className="text-sm text-slate-500">
          The admin password is set via the <code className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded text-xs">ADMIN_PANEL_PASSWORD</code> environment variable on your backend deployment.
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-slate-700">Environment variable</p>
              <p className={`text-sm font-mono mt-0.5 ${showPwd ? "text-slate-800" : "text-slate-400 tracking-widest"}`}>
                {showPwd ? "ADMIN_PANEL_PASSWORD" : "••••••••••••••••••"}
              </p>
            </div>
            <button
              onClick={() => setShowPwd((s) => !s)}
              className="p-1.5 rounded text-slate-400 hover:text-slate-600"
            >
              {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-400">
          To change the password, update this variable on Render → Environment → Save Changes. The backend will restart automatically.
        </p>
      </div>

      {/* About */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-2">
        <div className="flex items-center gap-2">
          <CheckCircle size={15} className="text-emerald-600" />
          <h2 className="text-sm font-semibold text-slate-800">About this panel</h2>
        </div>
        <div className="text-sm text-slate-500 space-y-1">
          <p>• <strong className="text-slate-700">Route:</strong> /admin (separate from main dashboard)</p>
          <p>• <strong className="text-slate-700">Auth:</strong> Dedicated admin token (12 h), stored in localStorage</p>
          <p>• <strong className="text-slate-700">Access:</strong> Only users with correct ADMIN_PANEL_PASSWORD</p>
          <p>• <strong className="text-slate-700">Visibility:</strong> Admin route is not linked in the main app UI</p>
        </div>
      </div>

      {saved && (
        <div className="fixed bottom-5 right-5 bg-emerald-600 text-white text-sm font-medium px-4 py-2.5 rounded-xl shadow-lg">
          Saved
        </div>
      )}
    </div>
  );
}
