import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { settingsAPI } from './api';
import { useAuth } from './AuthContext';

export type BusinessType =
  | 'retail'
  | 'wholesale'
  | 'restaurant'
  | 'food'
  | 'bakery'
  | 'grocery'
  | 'salon'
  | 'spa'
  | 'services'
  | 'repair'
  | 'cleaning'
  | 'fitness'
  | 'events'
  | 'healthcare'
  | 'rental'
  | 'hotel'
  | 'support'
  | 'creator'
  | 'tech'
  | 'general'
  | '';

/** The types a merchant can choose, shown wherever we ask. */
export const BUSINESS_TYPE_OPTIONS: { id: BusinessType; label: string; icon: string }[] = [
  { id: 'retail', label: 'Retail shop', icon: 'storefront-outline' },
  { id: 'restaurant', label: 'Restaurant', icon: 'restaurant-outline' },
  { id: 'food', label: 'Food business', icon: 'fast-food-outline' },
  { id: 'bakery', label: 'Bakery', icon: 'cafe-outline' },
  { id: 'grocery', label: 'Grocery', icon: 'basket-outline' },
  { id: 'wholesale', label: 'Wholesale', icon: 'cube-outline' },
  { id: 'salon', label: 'Salon', icon: 'cut-outline' },
  { id: 'spa', label: 'Spa', icon: 'flower-outline' },
  { id: 'fitness', label: 'Fitness', icon: 'barbell-outline' },
  { id: 'healthcare', label: 'Healthcare', icon: 'medkit-outline' },
  { id: 'services', label: 'Services', icon: 'briefcase-outline' },
  { id: 'repair', label: 'Repair', icon: 'construct-outline' },
  { id: 'cleaning', label: 'Cleaning', icon: 'sparkles-outline' },
  { id: 'events', label: 'Events', icon: 'balloon-outline' },
  { id: 'tech', label: 'Tech services', icon: 'laptop-outline' },
  { id: 'rental', label: 'Rentals', icon: 'key-outline' },
  { id: 'hotel', label: 'Hotel', icon: 'bed-outline' },
  { id: 'creator', label: 'Creator', icon: 'videocam-outline' },
  { id: 'support', label: 'Support', icon: 'headset-outline' },
  { id: 'general', label: 'Something else', icon: 'ellipsis-horizontal-outline' },
];

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
    // Covers freelance, trades, repairs
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Appointment',
    staffLabel: 'Technician', customerLabel: 'Client',
    showCheckinCheckout: false,
  },
  tech: {
    // Tech/IT services, software, consultancy
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Revenue',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Appointment',
    staffLabel: 'Consultant', customerLabel: 'Client',
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
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'hybrid', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Reservation',
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
    catalogLabel: 'Content', catalogItemLabel: 'Item',
    showDuration: false, showStock: false,
    bookingsTabVisible: false, salesTabLabel: 'Sales',
    dashboardMode: 'sales', primaryColor: '#25D366',
    bookingMode: 'none', bookingLabel: 'Order',
    staffLabel: '', customerLabel: 'Fan',
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
  hotel: {
    catalogLabel: 'Rooms', catalogItemLabel: 'Room',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Revenue',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'rental', bookingLabel: 'Reservation',
    staffLabel: '', customerLabel: 'Guest',
    showCheckinCheckout: true,
  },
  support: {
    // Customer support / care agent — catalog holds FAQ articles & known answers
    catalogLabel: 'Knowledge Base', catalogItemLabel: 'Article',
    showDuration: false, showStock: false,
    bookingsTabVisible: false, salesTabLabel: 'Activity',
    dashboardMode: 'hybrid', primaryColor: '#25D366',
    bookingMode: 'none', bookingLabel: 'Ticket',
    staffLabel: 'Agent', customerLabel: 'Customer',
    showCheckinCheckout: false,
  },
  general: {
    // Flexible — can have products, services, or both
    catalogLabel: 'Resources', catalogItemLabel: 'Resource',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'hybrid', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Booking',
    staffLabel: '', customerLabel: 'Customer',
    showCheckinCheckout: false,
  },
  wholesale: {
    catalogLabel: 'Products', catalogItemLabel: 'Product',
    showDuration: false, showStock: true,
    bookingsTabVisible: false, salesTabLabel: 'Sales',
    dashboardMode: 'sales', primaryColor: '#25D366',
    bookingMode: 'none', bookingLabel: 'Order',
    staffLabel: '', customerLabel: 'Client',
    showCheckinCheckout: false,
  },
  food: {
    catalogLabel: 'Menu', catalogItemLabel: 'Item',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'hybrid', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Reservation',
    staffLabel: '', customerLabel: 'Guest',
    showCheckinCheckout: false,
  },
  bakery: {
    catalogLabel: 'Menu', catalogItemLabel: 'Item',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'hybrid', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Pre-order',
    staffLabel: '', customerLabel: 'Guest',
    showCheckinCheckout: false,
  },
  grocery: {
    catalogLabel: 'Products', catalogItemLabel: 'Product',
    showDuration: false, showStock: true,
    bookingsTabVisible: false, salesTabLabel: 'Sales',
    dashboardMode: 'sales', primaryColor: '#25D366',
    bookingMode: 'none', bookingLabel: 'Order',
    staffLabel: '', customerLabel: 'Customer',
    showCheckinCheckout: false,
  },
  spa: {
    catalogLabel: 'Treatments', catalogItemLabel: 'Treatment',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Appointment',
    staffLabel: 'Therapist', customerLabel: 'Client',
    showCheckinCheckout: false,
  },
  repair: {
    catalogLabel: 'Services', catalogItemLabel: 'Service',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Appointment',
    staffLabel: 'Technician', customerLabel: 'Client',
    showCheckinCheckout: false,
  },
  cleaning: {
    catalogLabel: 'Packages', catalogItemLabel: 'Package',
    showDuration: true, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Sales',
    dashboardMode: 'bookings', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Booking',
    staffLabel: '', customerLabel: 'Client',
    showCheckinCheckout: false,
  },
  events: {
    catalogLabel: 'Packages', catalogItemLabel: 'Package',
    showDuration: false, showStock: false,
    bookingsTabVisible: true, salesTabLabel: 'Revenue',
    dashboardMode: 'hybrid', primaryColor: '#25D366',
    bookingMode: 'appointment', bookingLabel: 'Booking',
    staffLabel: 'Photographer', customerLabel: 'Client',
    showCheckinCheckout: false,
  },
};

const DEFAULT_CONFIG: BusinessConfig = {
  catalogLabel: 'Products', catalogItemLabel: 'Product',
  showDuration: false, showStock: true,
  bookingsTabVisible: false, salesTabLabel: 'Sales',
  dashboardMode: 'sales', primaryColor: '#25D366',
  bookingMode: 'none', bookingLabel: 'Appointment',
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
    // Re-arm loading on every (re)load — without this, the early
    // not-authenticated pass sets isLoading=false and the tabs mount with the
    // default config (Bookings/Broadcast hidden) before settings arrive.
    setIsLoading(true);
    try {
      const settings = await settingsAPI.getSettings();
      // Accounts without a business_type get 'general' (hybrid): Bookings and
      // Broadcast both visible — matches the original production app where
      // these tabs were never hidden.
      setBusinessType((settings.business_type as BusinessType) || 'general');
    } catch (_) {
      // Settings fetch failed — show the full tab set rather than hiding tabs.
      setBusinessType((prev) => prev || 'general');
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => { load(); }, [load]);

  const config = TYPE_CONFIGS[businessType] ?? DEFAULT_CONFIG;
  const isServiceBusiness = ['salon', 'spa', 'services', 'repair', 'cleaning', 'fitness', 'events', 'healthcare', 'rental', 'hotel', 'support'].includes(businessType);
  const isRetailBusiness  = ['retail', 'wholesale', 'restaurant', 'food', 'bakery', 'grocery', 'creator', 'general'].includes(businessType);

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
