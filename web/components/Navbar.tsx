"use client";

import React, { useEffect, useState } from "react";
import { getUser } from "@/lib/auth";
import { Bell, ChevronDown, Search } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Navbar() {
  const [user, setUser] = useState<Record<string, unknown> | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setUser(getUser());
  }, []);

  // Get profile name or display name
  const getProfileName = () => {
    if (!user) return "User";
    return (user.name as string) || (user.email as string) || "User";
  };

  if (!mounted) {
    return (
      <nav className="h-16 bg-[#071a10] border-b border-brand-dark/25 flex items-center px-6 shrink-0">
        <div className="flex-1" />
      </nav>
    );
  }

  return (
    <nav className="sticky top-0 z-40 h-16 bg-[#071a10] border-b border-brand-dark/25 flex items-center justify-between px-6 shrink-0 shadow-sm">
      {/* Left side - Search Input */}
      <div className="flex-1">
        <div className="w-96 relative">
          <Search size={16} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search..."
            className="w-full pl-10 pr-4 py-2 bg-white/10 border border-white/20 rounded-lg text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:border-white/40 focus:bg-white/15 transition-colors"
          />
        </div>
      </div>

      {/* Right side - Notifications and Profile */}
      <div className="flex items-center gap-4">
        {/* Notification bell */}
        <button className="relative p-2 text-slate-400 hover:text-slate-100 hover:bg-white/10 rounded-lg transition-colors">
          <Bell size={20} />
          <span className="absolute top-0 right-0 h-2 w-2 bg-red-500 rounded-full"></span>
        </button>

        {/* Profile section */}
        <div className="flex items-center gap-3 pl-4 border-l border-white/10">
          <div className="text-right">
            <p className="text-sm font-medium text-slate-100">{getProfileName()}</p>
            <p className="text-xs text-slate-400">Account</p>
          </div>
          {/* <button className="p-2 hover:bg-white/10 rounded-lg transition-colors">
            <ChevronDown size={18} className="text-slate-400" />
          </button> */}
        </div>
      </div>
    </nav>
  );
}
