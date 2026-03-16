import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { settingsAPI } from './api';
import { useAuth } from './AuthContext';

export type BusinessType =
  | 'retail'
  | 'salon'
  | 'services'
  | 'fitness'
  | 'restaurant'
  | 'healthcare'
  | 'creator'
  | 'rental'
  | '';

// ── Per-type config ────────────────────────────────────────────────────────────

export interface BusinessConfig {
  catalogLabel: string;       // "Products" | "Services" | "Menu"
  catalogItemLabel: string;   // "Product" | "Service" | "Item"
  showDuration: boolean;      // service businesses track duration, not stock
  showStock: boolean;         // retail tracks stock
  bookingsTabVisible: boolean;// tab shows in main bar vs 3-dot menu
  salesTabLabel: string;      // "Sales" for all, could be "Revenue" etc.
  dashboardMode: 'sales' | 'bookings' | 'hybrid';
  primaryColor: string;       // accent for type-specific UI (all use #25D366 for now)
}

const TYPE_CONFIGS: Record<string, BusinessConfig> = {
  retail: {
    catalogLabel: 'Products', catalogItemLabel: 'Product',
    showDuration: false, showStock: true,
    bookingsTabVisible: false, salesTabLabel: 'Sales',
    dashboardMode: 'sales', primaryColor: '#25D366',
  },
  salon: {
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
  },
  services: {
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
  },
  fitness: {
    catalogLabel: 'Services', catalogItemLabel: 'Class',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
  },
  restaurant: {
    catalogLabel: 'Menu', catalogItemLabel: 'Item',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
  },
  healthcare: {
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
  },
  creator: {
    catalogLabel: 'Products', catalogItemLabel: 'Product',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
  },
  rental: {
    catalogLabel: 'Listings', catalogItemLabel: 'Listing',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Revenue',
    dashboardMode: 'bookings', primaryColor: '#25D366',
  },
};

const DEFAULT_CONFIG: BusinessConfig = {
  catalogLabel: 'Products', catalogItemLabel: 'Product',
  showDuration: false, showStock: true,
  bookingsTabVisible: true, salesTabLabel: 'Sales',
  dashboardMode: 'hybrid', primaryColor: '#25D366',
};

// ── Context ────────────────────────────────────────────────────────────────────

interface BusinessContextType {
  businessType: BusinessType;
  config: BusinessConfig;
  isLoading: boolean;
  isServiceBusiness: boolean;   // salon | services | fitness | healthcare
  isRetailBusiness: boolean;    // retail | restaurant | creator
  refresh: () => Promise<void>;
}

const BusinessContext = createContext<BusinessContextType | undefined>(undefined);

export function BusinessProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [businessType, setBusinessType] = useState<BusinessType>('');
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async () => {
    if (!isAuthenticated) { setIsLoading(false); return; }
    try {
      const settings = await settingsAPI.getSettings();
      setBusinessType((settings.business_type as BusinessType) || '');
    } catch (_) {
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => { load(); }, [load]);

  const config = TYPE_CONFIGS[businessType] ?? DEFAULT_CONFIG;
  const isServiceBusiness = ['salon', 'services', 'fitness', 'healthcare', 'rental'].includes(businessType);
  const isRetailBusiness  = ['retail', 'restaurant', 'creator'].includes(businessType);

  return (
    <BusinessContext.Provider value={{
      businessType, config, isLoading, isServiceBusiness, isRetailBusiness, refresh: load,
    }}>
      {children}
    </BusinessContext.Provider>
  );
}

export function useBusiness() {
  const ctx = useContext(BusinessContext);
  if (!ctx) throw new Error('useBusiness must be used within BusinessProvider');
  return ctx;
}
