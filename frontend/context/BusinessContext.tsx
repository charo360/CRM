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

export interface BusinessConfig {
  catalogLabel: string;
  catalogItemLabel: string;
  showDuration: boolean;
  showStock: boolean;
  bookingsTabVisible: boolean;
  salesTabLabel: string;
  dashboardMode: 'sales' | 'bookings' | 'hybrid';
  primaryColor: string;
  // Booking workflow
  bookingMode: 'appointment' | 'rental' | 'class' | 'none';
  bookingLabel: string;          // "Appointment", "Class", "Booking", "Reservation"
  staffLabel: string;            // "Stylist", "Doctor", "Trainer", "Technician", ""
  customerLabel: string;         // "Client", "Patient", "Member", "Guest", "Customer"
  showCheckinCheckout: boolean;  // rental: true (date range), others: false (time slot)
}

const TYPE_CONFIGS: Record<string, BusinessConfig> = {
  retail: {
    catalogLabel: 'Products', catalogItemLabel: 'Product',
    showDuration: false, showStock: true,
    bookingsTabVisible: false, salesTabLabel: 'Sales',
    dashboardMode: 'sales', primaryColor: '#25D366',
    bookingMode: 'none', bookingLabel: 'Order',
    staffLabel: '', customerLabel: 'Customer',
    showCheckinCheckout: false,
  },
  salon: {
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Appointment',
    staffLabel: 'Stylist', customerLabel: 'Client',
    showCheckinCheckout: false,
  },
  services: {
    // Covers tech/IT services, freelance, trades, repairs
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Appointment',
    staffLabel: 'Technician', customerLabel: 'Client',
    showCheckinCheckout: false,
  },
  fitness: {
    catalogLabel: 'Classes', catalogItemLabel: 'Class',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'class', bookingLabel: 'Class',
    staffLabel: 'Trainer', customerLabel: 'Member',
    showCheckinCheckout: false,
  },
  restaurant: {
    catalogLabel: 'Menu', catalogItemLabel: 'Item',
    showDuration: false, showStock: false,
    bookingsTabVisible: false, salesTabLabel: 'Sales',
    dashboardMode: 'sales', primaryColor: '#25D366',
    bookingMode: 'none', bookingLabel: 'Order',
    staffLabel: '', customerLabel: 'Guest',
    showCheckinCheckout: false,
  },
  healthcare: {
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Appointment',
    staffLabel: 'Doctor', customerLabel: 'Patient',
    showCheckinCheckout: false,
  },
  creator: {
    catalogLabel: 'Products', catalogItemLabel: 'Product',
    showDuration: false, showStock: false,
    bookingsTabVisible: false, salesTabLabel: 'Sales',
    dashboardMode: 'sales', primaryColor: '#25D366',
    bookingMode: 'none', bookingLabel: 'Order',
    staffLabel: '', customerLabel: 'Customer',
    showCheckinCheckout: false,
  },
  rental: {
    // Properties, cars, equipment — check-in/checkout date range (NOT time slots)
    catalogLabel: 'Listings', catalogItemLabel: 'Listing',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Revenue',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'rental', bookingLabel: 'Booking',
    staffLabel: '', customerLabel: 'Guest',
    showCheckinCheckout: true,
  },
};

const DEFAULT_CONFIG: BusinessConfig = {
  catalogLabel: 'Products', catalogItemLabel: 'Product',
  showDuration: false, showStock: true,
  bookingsTabVisible: true, salesTabLabel: 'Sales',
  dashboardMode: 'hybrid', primaryColor: '#25D366',
  bookingMode: 'appointment', bookingLabel: 'Appointment',
  staffLabel: '', customerLabel: 'Customer',
  showCheckinCheckout: false,
};

interface BusinessContextType {
  businessType: BusinessType;
  config: BusinessConfig;
  isLoading: boolean;
  isServiceBusiness: boolean;
  isRetailBusiness: boolean;
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
