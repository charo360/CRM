"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { socialInboxApi } from "@/lib/api";

export interface ZernioAccount {
  id: string;
  platform: string;
  displayName?: string;
  username?: string;
  avatar?: string;
}

interface ZernioAccountsContextType {
  accounts: ZernioAccount[];
  apiConnected: boolean | null;
  loading: boolean;
  refresh: () => Promise<void>;
  connect: (platform: string, redirectUrl?: string, headless?: boolean) => Promise<{ authUrl?: string }>;
  disconnect: (accountId: string) => Promise<void>;
}

const ZernioAccountsContext = createContext<ZernioAccountsContextType | undefined>(undefined);

export function ZernioAccountsProvider({ children }: { children: React.ReactNode }) {
  const [accounts, setAccounts] = useState<ZernioAccount[]>([]);
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await socialInboxApi.status();
      const isConnected = status.connected === true;
      setApiConnected(isConnected);
      const raw = (status.accounts as any[]) ?? [];
      setAccounts(
        raw.map((a: any) => ({
          id: String(a.id || a._id || ""),
          platform: String(a.platform || "").toLowerCase(),
          displayName: a.displayName || a.name || a.username || "",
          username: a.username || a.displayName || "",
          avatar: a.avatar || a.picture || "",
        }))
      );
    } catch {
      setApiConnected(false);
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const connect = useCallback(
    async (platform: string, redirectUrl?: string, headless?: boolean) => {
      const data = await socialInboxApi.connect(platform, redirectUrl);
      return data as { authUrl?: string };
    },
    []
  );

  const disconnect = useCallback(async (accountId: string) => {
    await socialInboxApi.disconnect(accountId);
    setAccounts(prev => prev.filter(a => a.id !== accountId));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <ZernioAccountsContext.Provider value={{ accounts, apiConnected, loading, refresh, connect, disconnect }}>
      {children}
    </ZernioAccountsContext.Provider>
  );
}

export function useZernioAccounts() {
  const ctx = useContext(ZernioAccountsContext);
  if (!ctx) throw new Error("useZernioAccounts must be used inside ZernioAccountsProvider");
  return ctx;
}
