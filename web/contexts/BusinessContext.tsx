"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  getAccountMode,
  getBusinessType,
  getCurrency,
  getBusinessSettings,
  getSidebarFeatures,
} from "@/lib/auth";
import { getWebBusinessUi, type WebBusinessUi } from "@/lib/businessUi";

/** Hotels & dining: "Reservations" (rooms/tables). Same /bookings API as appointments. */
const RESERVATION_LABEL_TYPES = new Set(["hotel", "restaurant", "food", "bakery"]);

/** Match mobile app: no Bookings/Reservations nav for pure product / ticket businesses. */
const HIDE_BOOKINGS_NAV_TYPES = new Set(["retail", "creator", "wholesale", "support", "grocery"]);

interface BusinessContextType {
  /** Solo vs company-style workspace (drives overview copy and future feature gates). */
  accountMode: "individual" | "business";
  businessType: string;
  currency: string;
  settings: Record<string, unknown>;
  isRestaurant: boolean;
  isSalon: boolean;
  isRetail: boolean;
  isCreator: boolean;
  /** Whether sidebar shows Bookings or Reservations */
  showBookingsNav: boolean;
  /** "Bookings" for salons/services; "Reservations" for hotel/restaurant/food/bakery */
  bookingsNavLabel: string;
  bookingsNavHref: string;
  /** Labels, nav titles, and feature flags for this business type */
  ui: WebBusinessUi;
  /** Which optional sidebar links are on (user.settings.features). Workspace links are always on. */
  sidebarFeatures: Record<string, boolean>;
  refreshSettings: () => void;
}

const BusinessContext = createContext<BusinessContextType | undefined>(undefined);

export function BusinessProvider({ children }: { children: React.ReactNode }) {
  const [accountMode, setAccountMode] = useState<"individual" | "business">("business");
  const [businessType, setBusinessType] = useState("retail");
  const [currency, setCurrency] = useState("KES");
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [sidebarFeatures, setSidebarFeatures] = useState<Record<string, boolean>>(getSidebarFeatures);

  const refreshSettings = useCallback(() => {
    setAccountMode(getAccountMode());
    setBusinessType(getBusinessType());
    setCurrency(getCurrency());
    setSettings(getBusinessSettings());
    setSidebarFeatures(getSidebarFeatures());
  }, []);

  useEffect(() => {
    refreshSettings();
  }, [refreshSettings]);

  const usesReservationNaming = RESERVATION_LABEL_TYPES.has(businessType);
  const showBookingsNav = !HIDE_BOOKINGS_NAV_TYPES.has(businessType);
  const bookingsNavLabel = usesReservationNaming ? "Reservations" : "Bookings";
  const bookingsNavHref = usesReservationNaming ? "/dashboard/reservations" : "/dashboard/bookings";
  const ui = getWebBusinessUi(businessType, accountMode);

  const value: BusinessContextType = {
    accountMode,
    businessType,
    currency,
    settings,
    isRestaurant: businessType === "restaurant",
    isSalon: businessType === "salon",
    isRetail: businessType === "retail",
    isCreator: businessType === "creator",
    showBookingsNav,
    bookingsNavLabel,
    bookingsNavHref,
    ui,
    sidebarFeatures,
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
