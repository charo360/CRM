"use client";

import React, { useEffect, useState } from "react";
import { getUser } from "@/lib/auth";
import { Bell, Menu, Search } from "lucide-react";

type NavbarProps = {
  onMenuClick?: () => void;
  onSearchClick?: () => void;
};

export default function Navbar({ onMenuClick, onSearchClick }: NavbarProps) {
  const [user, setUser] = useState<Record<string, unknown> | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setUser(getUser());
  }, []);

  const getProfileName = () => {
    if (!user) return "User";
    return (user.name as string) || (user.email as string) || "User";
  };

  if (!mounted) {
    return (
      <nav className="h-14 lg:h-16 bg-[#071a10] border-b border-brand-dark/25 flex items-center px-3 sm:px-6 shrink-0">
        <div className="flex-1" />
      </nav>
    );
  }

  return (
    <nav className="sticky top-0 z-30 h-14 lg:h-16 bg-[#071a10] border-b border-brand-dark/25 flex items-center justify-between gap-3 px-3 sm:px-6 shrink-0 shadow-sm">
      <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          className="rounded-lg p-2 text-slate-300 hover:bg-white/10 hover:text-white lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu size={20} />
        </button>

        <div className="hidden min-w-0 flex-1 md:block">
          <div className="w-full max-w-md relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search..."
              className="w-full pl-10 pr-4 py-2 bg-white/10 border border-white/20 rounded-lg text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:border-white/40 focus:bg-white/15 transition-colors"
            />
          </div>
        </div>

        <button
          type="button"
          onClick={onSearchClick}
          className="rounded-lg p-2 text-slate-300 hover:bg-white/10 hover:text-white md:hidden"
          aria-label="Search"
        >
          <Search size={20} />
        </button>
      </div>

      <div className="flex shrink-0 items-center gap-2 sm:gap-4">
        <button className="relative rounded-lg p-2 text-slate-400 hover:bg-white/10 hover:text-slate-100 transition-colors">
          <Bell size={20} />
          <span className="absolute top-1 right-1 h-2 w-2 bg-red-500 rounded-full" />
        </button>

        <div className="flex items-center gap-2 sm:gap-3 sm:pl-4 sm:border-l sm:border-white/10">
          <div className="min-w-0 text-right">
            <p className="truncate text-sm font-medium text-slate-100 max-w-[8rem] sm:max-w-none">
              {getProfileName()}
            </p>
            <p className="hidden text-xs text-slate-400 sm:block">Account</p>
          </div>
        </div>
      </div>
    </nav>
  );
}
