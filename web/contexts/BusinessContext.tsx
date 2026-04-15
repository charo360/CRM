"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { getBusinessType, getCurrency, getBusinessSettings } from "@/lib/auth";

interface BusinessContextType {
  businessType: string;
  currency: string;
  settings: Record<string, unknown>;
  isRestaurant: boolean;
  isSalon: boolean;
  isRetail: boolean;
  isCreator: boolean;
  refreshSettings: () => void;
}

const BusinessContext = createContext<BusinessContextType | undefined>(undefined);

export function BusinessProvider({ children }: { children: React.ReactNode }) {
  const [businessType, setBusinessType] = useState("retail");
  const [currency, setCurrency] = useState("KES");
  const [settings, setSettings] = useState<Record<string, unknown>>({});

  const refreshSettings = () => {
    setBusinessType(getBusinessType());
    setCurrency(getCurrency());
    setSettings(getBusinessSettings());
  };

  useEffect(() => {
    refreshSettings();
  }, []);

  const value: BusinessContextType = {
    businessType,
    currency,
    settings,
    isRestaurant: businessType === "restaurant",
    isSalon: businessType === "salon",
    isRetail: businessType === "retail",
    isCreator: businessType === "creator",
    refreshSettings,
  };

  return (
    <BusinessContext.Provider value={value}>
      {children}
    </BusinessContext.Provider>
  );
}

export function useBusiness() {
  const context = useContext(BusinessContext);
  if (context === undefined) {
    throw new Error("useBusiness must be used within a BusinessProvider");
  }
  return context;
}
