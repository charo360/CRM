/**
 * Web dashboard copy & visibility by `settings.business_type`.
 * Aligned with mobile `TYPE_CONFIGS` naming where possible.
 */

export interface WebBusinessUi {
  /** Main dashboard heading (e.g. Overview vs Home) */
  overviewTitle: string;
  /** First link under Sales (usually matches POS / revenue tab) */
  salesNavLabel: string;
  /** Main people list (same `/customers` route) */
  customersNavLabel: string;
  /** `/dashboard/shop` sidebar label */
  shopNavLabel: string;
  /** Line under “Overview” on the home dashboard */
  overviewSubtitle: string;
  /** Panel title for the latest order list */
  recentOrdersTitle: string;
  /** KPI card — in-flight orders */
  activeOrdersLabel: string;
  /** KPI card — completed payment count */
  paidOrdersLabel: string;
  /** Kitchen display — F&B only */
  showKdsNav: boolean;
  /** Lowercase for phrases like “your customers” */
  customerTerm: string;
}

const DEFAULT_UI: WebBusinessUi = {
  overviewTitle: "Overview",
  salesNavLabel: "Sales",
  customersNavLabel: "Customers",
  shopNavLabel: "Shop",
  overviewSubtitle: "Selling and growing in one workspace — revenue, people, and today's momentum.",
  recentOrdersTitle: "Recent Orders",
  activeOrdersLabel: "Active Orders",
  paidOrdersLabel: "Paid Orders",
  showKdsNav: false,
  customerTerm: "customers",
};

const BY_TYPE: Record<string, Partial<WebBusinessUi>> = {
  restaurant: {
    shopNavLabel: "Menu",
    overviewSubtitle: "Orders, reservations, and kitchen in one place.",
    showKdsNav: true,
    customerTerm: "guests",
  },
  food: {
    shopNavLabel: "Menu",
    overviewSubtitle: "Orders, reservations, and kitchen in one place.",
    showKdsNav: true,
    customerTerm: "guests",
  },
  bakery: {
    shopNavLabel: "Menu",
    overviewSubtitle: "Orders, reservations, and kitchen in one place.",
    showKdsNav: true,
    customerTerm: "guests",
  },
  hotel: {
    salesNavLabel: "Revenue",
    shopNavLabel: "Rooms",
    overviewSubtitle: "Reservations, revenue, and guest relationships.",
    customerTerm: "guests",
  },
  salon: {
    shopNavLabel: "Services",
    customersNavLabel: "Clients",
    overviewSubtitle: "Appointments, retail, and client messaging.",
    customerTerm: "clients",
  },
  spa: {
    shopNavLabel: "Treatments",
    customersNavLabel: "Clients",
    overviewSubtitle: "Bookings, treatments, and client care.",
    customerTerm: "clients",
  },
  healthcare: {
    shopNavLabel: "Services",
    customersNavLabel: "Patients",
    overviewSubtitle: "Appointments, follow-ups, and patient communication.",
    customerTerm: "patients",
  },
  services: {
    shopNavLabel: "Services",
    overviewSubtitle: "Jobs, invoices, and client work.",
    customerTerm: "clients",
  },
  repair: {
    shopNavLabel: "Services",
    overviewSubtitle: "Repairs, parts, and customer updates.",
    customerTerm: "customers",
  },
  cleaning: {
    shopNavLabel: "Packages",
    overviewSubtitle: "Jobs, schedules, and client accounts.",
    customerTerm: "clients",
  },
  fitness: {
    shopNavLabel: "Classes",
    customersNavLabel: "Customers",
    overviewSubtitle: "Classes, memberships, and customer engagement.",
    customerTerm: "customers",
  },
  events: {
    salesNavLabel: "Revenue",
    shopNavLabel: "Packages",
    overviewSubtitle: "Bookings, packages, and client events.",
    customerTerm: "clients",
  },
  rental: {
    salesNavLabel: "Revenue",
    shopNavLabel: "Listings",
    overviewSubtitle: "Listings, bookings, and guest coordination.",
    customerTerm: "guests",
  },
  creator: {
    shopNavLabel: "Catalog",
    overviewSubtitle: "Fans, monetization, and messages.",
    customerTerm: "fans",
  },
  wholesale: {
    overviewSubtitle: "Orders, accounts, and wholesale clients.",
    customerTerm: "clients",
  },
  grocery: {
    shopNavLabel: "Products",
    overviewSubtitle: "Stock, orders, and shopper relationships.",
    customerTerm: "customers",
  },
  retail: {
    overviewSubtitle: "Sales, inventory, and customer relationships.",
    customerTerm: "customers",
  },
  support: {
    salesNavLabel: "Activity",
    shopNavLabel: "Knowledge",
    overviewSubtitle: "Tickets, knowledge base, and customer care.",
    customerTerm: "customers",
  },
  general: {
    shopNavLabel: "Resources",
    overviewSubtitle: "Sales, bookings, and contacts in one view.",
    customerTerm: "customers",
  },
  other: {
    overviewSubtitle: "Sales, pipeline, and growth activity across your business in one view.",
    customerTerm: "customers",
  },
};

export function getWebBusinessUi(
  businessType: string,
  accountMode: "individual" | "business" = "business"
): WebBusinessUi {
  const patch = BY_TYPE[businessType] ?? {};
  const merged: WebBusinessUi = { ...DEFAULT_UI, ...patch };

  if (accountMode === "individual") {
    const typeNice = businessType.replace(/_/g, " ");
    return {
      ...merged,
      overviewTitle: "Home",
      overviewSubtitle: `Conversations, Zilo Chat, and automations — plus reach and campaigns when you need them. Personalized for ${typeNice}.`,
      recentOrdersTitle: "Recent activity",
      activeOrdersLabel: "Open",
      paidOrdersLabel: "Done",
    };
  }

  return merged;
}
